"""Function-level coverage for pure ``retirement_sim.account_simulation``
helpers that had NO direct test (function-gap sweep, 2026-08-22).

Targets the small pure functions the whole engine leans on:
``_progressive_tax`` (shared by every bracket schedule), ``_withdrawal_category``
(the withdrawal-log taxonomy the UI charts consume), ``_withdrawal_order`` (the
tax-efficient ordering itself) and ``_select_state_tax_brackets``.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from retirement_sim import config as cfg
from retirement_sim import account_simulation as asim
from retirement_sim.account_simulation import AccountType


# ---------------------------------------------------------------------------
# _progressive_tax
# ---------------------------------------------------------------------------
SIMPLE = [(100.0, 0.10), (200.0, 0.20), (float("inf"), 0.30)]


class TestProgressiveTax:
    @pytest.mark.parametrize("income", [0, -1, -1_000_000])
    def test_zero_or_negative_income_is_untaxed(self, income):
        assert asim._progressive_tax(SIMPLE, income) == 0

    def test_within_first_bracket(self):
        assert asim._progressive_tax(SIMPLE, 50) == pytest.approx(5.0)

    def test_exactly_at_a_bracket_boundary(self):
        # $100 all at 10% -- the boundary dollar belongs to the LOWER bracket.
        assert asim._progressive_tax(SIMPLE, 100) == pytest.approx(10.0)
        assert asim._progressive_tax(SIMPLE, 200) == pytest.approx(10.0 + 20.0)

    def test_one_dollar_past_a_boundary_only_taxes_the_dollar_higher(self):
        assert (asim._progressive_tax(SIMPLE, 101) - asim._progressive_tax(SIMPLE, 100)
                == pytest.approx(0.20))

    def test_top_open_ended_bracket(self):
        assert asim._progressive_tax(SIMPLE, 1_200) == pytest.approx(10 + 20 + 1_000 * 0.30)

    def test_very_large_income_stays_below_top_rate(self):
        income = 1e12
        tax = asim._progressive_tax(SIMPLE, income)
        assert tax < income * 0.30
        assert tax / income == pytest.approx(0.30, rel=1e-6)

    def test_monotone_and_effective_rate_never_exceeds_top_marginal(self):
        prev = -1.0
        for income in range(0, 2_000, 37):
            tax = asim._progressive_tax(SIMPLE, income)
            assert tax >= prev
            if income:
                assert tax / income <= 0.30 + 1e-12
            prev = tax

    def test_matches_federal_brackets_hand_calc(self):
        brackets = cfg.get_federal_brackets("MFJ")
        # $100k taxable MFJ: 23,200@10% + (94,300-23,200)@12% + (100,000-94,300)@22%
        expected = 23_200 * 0.10 + (94_300 - 23_200) * 0.12 + (100_000 - 94_300) * 0.22
        assert asim._progressive_tax(brackets, 100_000) == pytest.approx(expected)

    def test_single_pays_more_than_mfj_at_the_same_income(self):
        for income in (60_000, 150_000, 400_000):
            assert (asim._progressive_tax(cfg.get_federal_brackets("S"), income)
                    > asim._progressive_tax(cfg.get_federal_brackets("MFJ"), income))

    def test_bracket_classes_delegate_to_progressive_tax(self):
        fed = asim.TaxBrackets()
        ca = asim.CaliforniaTaxBrackets()
        for income in (0, 25_000, 250_000, 2_000_000):
            assert fed.calculate_tax(income) == pytest.approx(
                asim._progressive_tax(fed.brackets, income))
            assert ca.calculate_tax(income) == pytest.approx(
                asim._progressive_tax(ca.brackets, income))


# ---------------------------------------------------------------------------
# State tax model selection
# ---------------------------------------------------------------------------
class TestStateTaxSelection:
    def test_default_ca(self, monkeypatch):
        monkeypatch.setattr(cfg, "STATE_CHOICE", "CA")
        model = asim._select_state_tax_brackets()
        assert isinstance(model, asim.CaliforniaTaxBrackets)
        assert model.calculate_tax(100_000) > 0

    def test_no_state_tax(self, monkeypatch):
        monkeypatch.setattr(cfg, "STATE_CHOICE", "No state tax")
        model = asim._select_state_tax_brackets()
        assert isinstance(model, asim.NoStateTax)
        assert model.calculate_tax(10_000_000) == 0.0
        assert model.calculate_tax(-5) == 0.0

    def test_other_uses_marginal_rate_flat(self, monkeypatch):
        monkeypatch.setattr(cfg, "STATE_CHOICE", "Other")
        monkeypatch.setattr(cfg, "YOUR_MARGINAL_TAX_RATE", 0.07)
        model = asim._select_state_tax_brackets()
        assert isinstance(model, asim.FlatRateStateTax)
        assert model.calculate_tax(100_000) == pytest.approx(7_000)
        assert model.calculate_tax(0) == 0.0
        assert model.calculate_tax(-100) == 0.0

    def test_unrecognized_choice_falls_back_to_ca(self, monkeypatch):
        monkeypatch.setattr(cfg, "STATE_CHOICE", "Freedonia")
        assert isinstance(asim._select_state_tax_brackets(), asim.CaliforniaTaxBrackets)


# ---------------------------------------------------------------------------
# _withdrawal_category
# ---------------------------------------------------------------------------
class TestWithdrawalCategory:
    @pytest.mark.parametrize("acct,expected", [
        (AccountType.CASH, "cash"),
        (AccountType.TAXABLE, "taxable"),
        (AccountType.TRADITIONAL_401K, "traditional"),
        (AccountType.TRADITIONAL_IRA, "traditional"),
        (AccountType.ROTH_401K, "roth"),
        (AccountType.ROTH_IRA, "roth"),
        (AccountType.HSA, "hsa"),
        (AccountType.COLLEGE_529, None),
    ])
    def test_mapping(self, acct, expected):
        assert asim._withdrawal_category(acct) == expected

    def test_every_account_type_is_handled(self):
        """No AccountType may fall through unmapped except the 529 (deliberate)."""
        unmapped = [t.name for t in AccountType if asim._withdrawal_category(t) is None]
        assert unmapped == ["COLLEGE_529"]

    def test_categories_are_the_set_the_ui_charts_expect(self):
        cats = {asim._withdrawal_category(t) for t in AccountType} - {None}
        assert cats == {"cash", "taxable", "traditional", "roth", "hsa"}


# ---------------------------------------------------------------------------
# _withdrawal_order
# ---------------------------------------------------------------------------
def _flat(order):
    """[(types, treatment)] -> [(AccountType, treatment)] in withdrawal order."""
    return [(t, treat) for types, treat in order for t in types]


class TestWithdrawalOrder:
    @pytest.mark.parametrize("age", [30, 59.4, 59.5, 60, 70, 95])
    @pytest.mark.parametrize("medical", [False, True])
    def test_cash_is_always_first_and_free(self, age, medical):
        order = asim._withdrawal_order(age, medical)
        assert order[0] == ([AccountType.CASH], "none")

    @pytest.mark.parametrize("age", [30, 59.5, 80])
    @pytest.mark.parametrize("medical", [False, True])
    def test_no_account_type_appears_twice(self, age, medical):
        types = [t for t, _ in _flat(asim._withdrawal_order(age, medical))]
        assert len(types) == len(set(types))

    @pytest.mark.parametrize("age", [30, 59.5, 80])
    @pytest.mark.parametrize("medical", [False, True])
    def test_every_spendable_account_type_is_reachable(self, age, medical):
        """A type missing from the order can never fund a withdrawal, so the
        portfolio would look richer than it can actually spend."""
        types = {t for t, _ in _flat(asim._withdrawal_order(age, medical))}
        expected = {t for t in AccountType if t != AccountType.COLLEGE_529}
        assert types == expected

    def test_before_595_roth_precedes_traditional(self):
        seq = [t for t, _ in _flat(asim._withdrawal_order(45, False))]
        assert seq.index(AccountType.ROTH_IRA) < seq.index(AccountType.TRADITIONAL_IRA)

    def test_after_595_traditional_precedes_roth(self):
        seq = [t for t, _ in _flat(asim._withdrawal_order(65, False))]
        assert seq.index(AccountType.TRADITIONAL_IRA) < seq.index(AccountType.ROTH_IRA)

    def test_boundary_is_inclusive_at_595(self):
        assert asim._withdrawal_order(59.5, False) == asim._withdrawal_order(60, False)
        assert asim._withdrawal_order(59.49, False) == asim._withdrawal_order(50, False)
        assert asim._withdrawal_order(59.5, False) != asim._withdrawal_order(59.49, False)

    def test_medical_puts_hsa_second_and_tax_free(self):
        for age in (45, 70):
            order = asim._withdrawal_order(age, True)
            assert order[1] == ([AccountType.HSA], "none")

    def test_non_medical_hsa_is_last_resort(self):
        for age in (45, 70):
            types, _ = asim._withdrawal_order(age, False)[-1]
            assert types == [AccountType.HSA]

    def test_early_non_medical_hsa_is_penalized(self):
        treat = dict(_flat(asim._withdrawal_order(45, False)))
        assert treat[AccountType.HSA] == "hsa_nonmedical"

    def test_traditional_treatment_flips_at_595(self):
        assert dict(_flat(asim._withdrawal_order(45, False)))[AccountType.TRADITIONAL_401K] == "income_early"
        assert dict(_flat(asim._withdrawal_order(65, False)))[AccountType.TRADITIONAL_401K] == "income"

    def test_taxable_is_always_ltcg(self):
        for age in (30, 59.5, 90):
            for medical in (False, True):
                assert dict(_flat(asim._withdrawal_order(age, medical)))[AccountType.TAXABLE] == "ltcg"

    # FIXED 2026-08-22: was xfail(strict) while the defect stood; the fix is in.
    @pytest.mark.parametrize("age", [59.5, 60, 62, 64.9])
    def test_non_medical_hsa_penalized_until_65(self, age):
        assert cfg.EARLY_WITHDRAWAL_AGE_HSA == 65
        treat = dict(_flat(asim._withdrawal_order(age, False)))
        assert treat[AccountType.HSA] == "hsa_nonmedical"

    def test_non_medical_hsa_after_65_is_income_only(self):
        treat = dict(_flat(asim._withdrawal_order(70, False)))
        assert treat[AccountType.HSA] == "income"

    def test_order_follows_cfg_early_withdrawal_age(self, monkeypatch):
        monkeypatch.setattr(cfg, "EARLY_WITHDRAWAL_AGE_401K_IRA", 55)
        seq = [t for t, _ in _flat(asim._withdrawal_order(56, False))]
        assert seq.index(AccountType.TRADITIONAL_IRA) < seq.index(AccountType.ROTH_IRA)


# ---------------------------------------------------------------------------
# update_inflation_factors (all-real frame invariants)
# ---------------------------------------------------------------------------
class TestUpdateInflationFactors:
    def test_general_factor_never_grows(self):
        factors = {"general": 1.0, "healthcare": 1.0, "childcare": 1.0}
        for _ in range(30):
            asim.update_inflation_factors(factors)
        assert factors["general"] == 1.0

    def test_unknown_categories_are_left_alone(self):
        factors = {"general": 1.0, "not_a_category": 3.0}
        asim.update_inflation_factors(factors)
        assert factors["not_a_category"] == 3.0

    def test_healthcare_outpaces_general_on_average(self):
        import numpy as np
        np.random.seed(1234)
        ends = []
        for _ in range(50):
            factors = {"general": 1.0, "healthcare": 1.0}
            for _ in range(20):
                asim.update_inflation_factors(factors)
            ends.append(factors["healthcare"])
        assert sum(ends) / len(ends) > 1.0

    def test_no_keys_no_crash(self):
        factors = {}
        asim.update_inflation_factors(factors)
        assert factors == {}
