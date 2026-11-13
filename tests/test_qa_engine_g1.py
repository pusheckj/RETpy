"""Engine-correctness regressions found by the QA personas (group G1).

One class per finding: renter spending, the HSA limit for a single filer, the
partner's backdoor Roth, Social Security claimed while working, a mortgage with
no home value, inflation neutrality, the last plan year, state tax in
retirement, the 529 in the allocation and the 2026 contribution limits.
"""
import copy
import os
import sys

import numpy as np
import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
for _p in (_ROOT, os.path.join(_ROOT, "ui"), _TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from conftest import load_sample_household  # noqa: E402
from retirement_sim import account_simulation as sim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from utils import derived, planner_max, sim_runner as sr  # noqa: E402


class applied:
    """``with applied(overrides):`` -- the engine config as the UI sets it."""

    def __init__(self, overrides):
        self.overrides = overrides

    def __enter__(self):
        self.original = sr._apply_overrides(sr.build_config_overrides(self.overrides))
        return cfg

    def __exit__(self, *exc):
        sr._restore_overrides(self.original)


def renter(**kw):
    ov = load_sample_household()
    ov.update(HOME_VALUE=0, MORTGAGE_BALANCE=0, MORTGAGE_MONTHLY=0, MORTGAGE_YEARS_REMAINING=0,
              SPEND_RENT_MONTHLY=1_500, HOUSE_MOVE_ENABLED=False, HOME_EVENTS=[])
    ov.update(kw)
    return ov


# ---------------------------------------------------------------- 1. renters' spending
class TestRentInCurrentExpenses:
    def test_renter_total_includes_rent(self):
        with applied(renter()) as c:
            base = c.granular_nonhousing_annual()
            assert c.CURRENT_ANNUAL_EXPENSES == pytest.approx(base + 1_500 * 12)

    def test_owner_total_unchanged_by_rent_key(self):
        ov = load_sample_household()
        with applied({**ov, "SPEND_RENT_MONTHLY": 0}) as c:
            owner = c.CURRENT_ANNUAL_EXPENSES
        with applied({**ov, "SPEND_RENT_MONTHLY": 9_999}) as c:
            assert c.CURRENT_ANNUAL_EXPENSES == owner       # an owner's rent is ignored

    def test_matches_the_engines_first_year_living_cost(self):
        """Today's total is the engine's year-1 cost without children, so rent is
        counted once (calculate_annual_expenses adds it, nothing adds it twice)."""
        with applied(renter(CHILDREN=[])) as c:
            first_year = c.calculate_annual_expenses(c.YOUR_AGE, 1.0, 1.0)
            assert c.CURRENT_ANNUAL_EXPENSES == pytest.approx(first_year)

    def test_debts_are_not_folded_in(self):
        debts = [{"name": "Visa", "kind": "credit_card", "balance": 5_000, "apr": 0.2,
                  "min_payment": 150}]
        with applied(renter()) as c:
            plain = c.CURRENT_ANNUAL_EXPENSES
        with applied(renter(DEBTS=debts)) as c:
            assert c.CURRENT_ANNUAL_EXPENSES == plain

    def test_fi_number_grid_and_basis_use_the_full_total(self):
        ov = renter()
        basis = sr.retirement_spending_basis(ov, 55)
        with applied(ov) as c:
            assert basis["today"] == pytest.approx(c.CURRENT_ANNUAL_EXPENSES)
        assert basis["today"] >= 1_500 * 12


# ---------------------------------------------------------------- 2. HSA limit
class TestHsaLimitFollowsHousehold:
    def _hsa(self, ov, age):
        ov = {**ov, "YOUR_HSA_CONTRIBUTION": 20_000}     # far over any limit
        with applied(ov):
            return sim.working_year_cashflow(age)["your_hsa"]

    def single(self, **kw):
        ov = load_sample_household()
        ov.update(PARTNER_AGE=0, PARTNER_BASE_SALARY=0, CHILDREN=[], YOUR_AGE=40)
        ov.update(kw)
        return ov

    def test_single_without_children_is_self_only(self):
        assert self._hsa(self.single(), 40) == cfg.CONTRIBUTION_LIMITS_2026["hsa_individual"]

    def test_catch_up_from_55_on_the_self_only_limit(self):
        L = cfg.CONTRIBUTION_LIMITS_2026
        assert self._hsa(self.single(YOUR_AGE=56), 56) == L["hsa_individual"] + L["hsa_catchup"]

    def test_a_child_or_a_partner_gets_the_family_limit(self):
        fam = cfg.CONTRIBUTION_LIMITS_2026["hsa_family"]
        kid = [{"years_until_birth": 2, "monthly_cost": 1_000}]
        assert self._hsa(self.single(CHILDREN=kid), 40) == fam
        assert self._hsa(self.single(PARTNER_AGE=38, PARTNER_BASE_SALARY=50_000), 40) == fam

    def test_engine_ui_and_max_out_agree(self):
        for ov in (self.single(), self.single(PARTNER_AGE=38, PARTNER_BASE_SALARY=50_000)):
            with applied(ov) as c:
                engine = c.get_hsa_limit(40, c.CURRENT_YEAR, is_family=c.hsa_is_family())
            assert planner_max.irs_limit(planner_max.YOUR_HSA, ov) == engine
            assert derived.get_limit("hsa", 40, family=derived.hsa_family(ov)) == engine

    def test_auto_allocate_fills_the_self_only_cap_for_a_single(self):
        out = derived.auto_allocate_savings(100_000, self.single())
        assert out["YOUR_HSA_CONTRIBUTION"] == cfg.CONTRIBUTION_LIMITS_2026["hsa_individual"]


# ---------------------------------------------------------------- 3. partner backdoor Roth
class TestPartnerBackdoorRoth:
    def rich_couple(self):
        ov = load_sample_household()
        ov.update(YOUR_BASE_SALARY=300_000, YOUR_BONUS_AMOUNT=0, YOUR_RSU_AMOUNT=0,
                  PARTNER_BASE_SALARY=300_000, PARTNER_BONUS_AMOUNT=0, PARTNER_RSU_AMOUNT=0,
                  YOUR_COMPENSATION_BY_AGE={},
                  PARTNER_ROTH_CONTRIBUTION=7_500, YOUR_BACKDOOR_ROTH=7_500, STATE_CHOICE="TX",
                  FILING_STATUS="MFJ")
        return ov

    def test_partner_over_the_income_limit_still_gets_the_roth(self):
        ov = self.rich_couple()
        with applied(ov):
            cf = sim.working_year_cashflow(cfg.YOUR_AGE)
        assert cf["your_roth"] == 7_500
        assert cf["partner_roth"] == 7_500        # was 0: direct-Roth phase-out

    def test_ui_allowance_matches_the_engine(self):
        ov = self.rich_couple()
        assert derived.partner_roth_allowed(ov, {}) == cfg.CONTRIBUTION_LIMITS_2026["ira"]
        assert planner_max.max_out_target(planner_max.PARTNER_ROTH, ov) == 7_500

    def test_still_limited_by_earned_income(self):
        ov = self.rich_couple()
        ov.update(PARTNER_BASE_SALARY=0, PARTNER_BONUS_AMOUNT=0, PARTNER_RSU_AMOUNT=0,
                  YOUR_BASE_SALARY=0, HOUSEHOLD_INCOME_QUICK=0)
        assert derived.partner_roth_allowed(ov, {}) == 0


# ---------------------------------------------------------------- 4. Social Security claim
class TestSocialSecurityStartsAtClaimAge:
    def ov(self, claim):
        ov = load_sample_household()
        ov.update(YOUR_AGE=60, PARTNER_AGE=0, PARTNER_BASE_SALARY=0, SS_CLAIM_AGE=claim,
                  INCLUDE_SOCIAL_SECURITY=True, YOUR_SS_MONTHLY_FRA=2_800,
                  YOUR_COMPENSATION_BY_AGE={}, YOUR_BASE_SALARY=95_000, YOUR_BONUS_AMOUNT=0,
                  YOUR_RSU_AMOUNT=0, CHILDREN=[], STATE_CHOICE="TX", FILING_STATUS="Single",
                  HOME_VALUE=0, MORTGAGE_MONTHLY=0, MORTGAGE_BALANCE=0, HOME_EVENTS=[],
                  HOUSE_MOVE_ENABLED=False)
        return ov

    def test_claiming_at_62_pays_the_reduced_benefit_while_still_working(self):
        with applied(self.ov(62)) as c:
            expected = 2_800 * c.ss_claim_factor(62) * 12
            assert sim.working_year_cashflow(61)["social_security"] == 0
            assert sim.working_year_cashflow(62)["social_security"] == pytest.approx(expected)
            assert sim.working_year_cashflow(64)["social_security"] == pytest.approx(expected)

    def test_it_adds_cash_and_tax_to_the_working_year(self):
        ov = self.ov(62)
        with applied(ov):
            with_ss = sim.working_year_cashflow(63)
        with applied({**ov, "INCLUDE_SOCIAL_SECURITY": False}):
            without = sim.working_year_cashflow(63)
        assert with_ss["your_take_home"] > without["your_take_home"]
        assert with_ss["total_tax"] > without["total_tax"]           # the taxable part
        gain = with_ss["your_take_home"] - without["your_take_home"]
        assert gain < with_ss["social_security"]
        assert with_ss["gross_income"] == pytest.approx(
            without["gross_income"] + with_ss["social_security"])

    def test_no_benefit_while_working_before_the_claim_age(self):
        with applied(self.ov(67)):
            assert sim.working_year_cashflow(65)["social_security"] == 0

    def test_toggle_off_means_none(self):
        with applied({**self.ov(62), "INCLUDE_SOCIAL_SECURITY": False}):
            assert sim.working_year_cashflow(63)["social_security"] == 0

    def test_a_partner_working_year_after_you_retire_adds_no_second_payment(self):
        """you_working=False years are paid by the retirement path, not here."""
        with applied(self.ov(62)):
            assert sim.working_year_cashflow(66, you_working=False)["social_security"] == 0


# ---------------------------------------------------------------- 5. mortgage, no home value
class TestMortgageWithoutHomeValue:
    def test_payment_without_value_is_an_owner_everywhere(self):
        from utils.widget_sync import _derive_rent_own
        ov = {"HOME_VALUE": 0, "MORTGAGE_MONTHLY": 3_800}
        assert _derive_rent_own(ov) == "Own home"
        assert _derive_rent_own({"HOME_VALUE": 0, "MORTGAGE_MONTHLY": 0}) == "Renting"
        assert _derive_rent_own({"HOME_VALUE": 500_000, "MORTGAGE_MONTHLY": 0}) == "Own home"
        with applied({**load_sample_household(), **ov, "HOUSE_MOVE_ENABLED": False,
                      "HOME_EVENTS": []}) as c:
            assert not c.is_renter()

    def test_house_section_keeps_the_payment(self):
        from streamlit.testing.v1 import AppTest
        os.environ["G1_UI"] = os.path.join(_ROOT, "ui")

        def script():
            import os
            import sys
            sys.path[:0] = [os.environ["G1_UI"], os.path.dirname(os.environ["G1_UI"])]
            import streamlit as st
            from components import sec_house
            sec_house.render_body(st)

        ov = load_sample_household()
        ov.update(HOME_VALUE=0, HOUSE_MOVE_ENABLED=False, HOME_EVENTS=[],
                  MORTGAGE_MONTHLY=3_800, MORTGAGE_BALANCE=400_000, MORTGAGE_YEARS_REMAINING=15)
        at = AppTest.from_function(script, default_timeout=60)
        at.session_state["user_overrides"] = ov
        at.run()
        assert not at.exception
        assert at.session_state["se_rent_own"] == "Own home"
        assert at.session_state["user_overrides"]["MORTGAGE_MONTHLY"] == 3_800


# ---------------------------------------------------------------- 6. inflation neutrality
class TestInflationSliderIsNotAFreeLunch:
    def test_category_premiums_do_not_move_with_the_slider(self):
        for general in (0.0, 0.0275, 0.10):
            old = copy.deepcopy(cfg.INFLATION_RATES)
            vol = cfg.INFLATION_VOLATILITY
            try:
                cfg.INFLATION_RATES["general"] = general
                cfg.INFLATION_VOLATILITY = 0.0
                f = {"general": 1.0, "healthcare": 1.0, "childcare": 1.0}
                sim.update_inflation_factors(f)
            finally:
                cfg.INFLATION_RATES.clear()
                cfg.INFLATION_RATES.update(old)
                cfg.INFLATION_VOLATILITY = vol
            assert f["general"] == 1.0
            assert f["healthcare"] == pytest.approx(1.0175)
            assert f["childcare"] == pytest.approx(1.0125)

    def test_default_premiums_are_the_documented_ones(self):
        assert cfg.INFLATION_REAL_EXCESS["healthcare"] == pytest.approx(0.0175)
        assert cfg.INFLATION_REAL_EXCESS["childcare"] == pytest.approx(0.0125)

    def test_success_rate_barely_moves_with_expected_inflation(self):
        """Was 0.50 / 0.82 / 0.99 at 0% / 2.5% / 10%. What remains is the faster
        decay of the frozen-nominal tax thresholds (a small, legitimate drag)."""
        rates = []
        for infl in (0.0, 0.025, 0.10):
            ov = {**load_sample_household(), "EXPECTED_INFLATION": infl}
            with applied(ov):
                np.random.seed(11)
                rates.append(sim.run_monte_carlo_detailed(45, 300, random_seed=11)["success_rate"])
        assert max(rates) - min(rates) < 0.08, rates


# ---------------------------------------------------------------- 7 and 8. last year, state tax
@pytest.fixture(scope="module")
def analysis():
    ov = load_sample_household()
    ov.update(STATE_CHOICE="CA", PLAN_UNTIL_AGE=92, PARTNER_PLAN_UNTIL_AGE=None)
    r = sr.run_full_analysis(ov, n_simulations=200, target_retirement_age=45,
                             scan_age_range=(45, 46, 1))
    with applied(ov) as c:
        end = c.plan_end_age()
    return r["primary_result"], end


def _finite(o):
    if isinstance(o, float):
        return np.isfinite(o)
    if isinstance(o, dict):
        return all(_finite(v) for v in o.values())
    if isinstance(o, (list, tuple)):
        return all(_finite(v) for v in o)
    return True


class TestLastPlanYear:
    def test_every_per_year_series_ends_on_the_last_simulated_year(self, analysis):
        pr, end = analysis
        last = end - 1
        for key in ("taxes_by_year", "income_sources_by_year", "withdrawals_by_year",
                    "spending_by_year"):
            assert pr[key][-1]["age"] == last, key

    def test_the_last_tax_row_is_a_real_year(self, analysis):
        pr, end = analysis
        row = pr["taxes_by_year"][-1]
        assert row["age"] == end - 1
        assert row["gross_income"] > 0          # the year is filled in, not an empty row

    def test_no_nan_in_the_charts_data(self, analysis):
        pr, _ = analysis
        for key in ("taxes_by_year", "income_sources_by_year", "spending_by_year",
                    "withdrawals_by_year"):
            assert _finite(pr[key]), key

    def test_non_finite_spending_never_reaches_the_percentiles(self):
        logs = [[{"age": 90, "living": 50_000.0}], [{"age": 90, "living": float("nan")}]]
        by_age = sr._spending_by_age(logs)
        assert by_age[90] == [50_000.0]


class TestStateTaxInRetirement:
    def test_withdrawal_rows_carry_the_state_part(self):
        ov = {**load_sample_household(), "STATE_CHOICE": "CA"}
        with applied(ov):
            np.random.seed(3)
            ok, pf = sim.run_detailed_simulation(45, verbose=False)
        rows = pf.withdrawal_log
        assert rows and all(0.0 <= r["state_tax"] <= r["total_taxes"] + 1e-6 for r in rows)
        assert sum(r["state_tax"] for r in rows) > 0
        assert pf.total_state_taxes_paid <= pf.total_taxes_paid + 1e-6

    def test_california_shows_state_tax_and_no_state_for_texas(self, analysis):
        pr, end = analysis
        ret = [r for r in pr["taxes_by_year"] if r["age"] >= 45]
        assert sum(r["state"] for r in ret) > 0
        for r in ret:       # state is reported on its own, federal is the rest
            assert r["federal"] >= 0.0

    def test_texas_has_none(self):
        ov = {**load_sample_household(), "STATE_CHOICE": "TX"}
        with applied(ov):
            np.random.seed(3)
            ok, pf = sim.run_detailed_simulation(45, verbose=False)
        assert pf.total_state_taxes_paid == pytest.approx(0.0, abs=1e-6)

    def test_rows_add_back_to_the_total(self):
        ov = {**load_sample_household(), "STATE_CHOICE": "CA"}
        with applied(ov):
            np.random.seed(5)
            wd = [{"age": 70, "total_taxes": 30_000.0, "niit": 1_000.0, "state_tax": 4_000.0,
                   "total": 100_000.0}]
            row = sr._approximate_taxes(wd, 45)[70 - cfg.YOUR_AGE]
        assert row["state"] == 4_000.0
        assert row["federal"] + row["state"] + row["niit"] == pytest.approx(30_000.0)


# ---------------------------------------------------------------- 9. the 529 in the allocation
class TestAllocationIncludesThe529:
    def household(self, salary=120_000, kids=True):
        ov = load_sample_household()
        ov.update(SAVINGS_MODE=derived.AUTO_ALLOCATE_MODE, YOUR_BASE_SALARY=salary,
                  YOUR_BONUS_AMOUNT=0, YOUR_RSU_AMOUNT=0, YOUR_COMPENSATION_BY_AGE={},
                  PARTNER_BASE_SALARY=0, PARTNER_BONUS_AMOUNT=0, PARTNER_RSU_AMOUNT=0,
                  PARTNER_AGE=0, STATE_CHOICE="TX", YOUR_AFTER_TAX_401K_PCT=0.0,
                  HOME_VALUE=0, MORTGAGE_MONTHLY=0, MORTGAGE_BALANCE=0, SPEND_RENT_MONTHLY=1_000,
                  HOME_EVENTS=[], HOUSE_MOVE_ENABLED=False,
                  CHILDREN=([{"years_until_birth": -1, "monthly_cost": 0,
                              "college_funding_pct": 1.0}] if kids else []))
        return ov

    def test_allocated_plus_set_aside_never_exceeds_what_is_left(self):
        for salary in (110_000, 120_000, 150_000):
            b = derived.savings_budget(self.household(salary))
            set_aside = sum(b["set_aside"].values())
            assert set_aside > 0
            assert sum(b["amounts"].values()) + set_aside <= b["disposable"] + 2

    def test_the_529_takes_its_share_before_the_accounts_are_filled(self):
        with_529 = derived.savings_budget(self.household(105_000))
        without = derived.savings_budget(self.household(105_000, kids=False))
        assert (with_529["amounts"]["YOUR_401K_CONTRIBUTION"]
                < without["amounts"]["YOUR_401K_CONTRIBUTION"])
        # ... and together they use the whole of what is left, as "Total allocated" says.
        total = sum(with_529["amounts"].values()) + sum(with_529["set_aside"].values())
        assert total == pytest.approx(with_529["disposable"], abs=2)

    def test_first_year_cash_is_not_drained_by_the_529(self):
        ov = self.household()
        b = derived.savings_budget(ov)
        with applied({**ov, **b["amounts"]}):
            cf = sim.working_year_cashflow(cfg.YOUR_AGE)
            living = cfg.calculate_annual_expenses(cfg.YOUR_AGE, 1.0, 1.0)
            college = sum(cfg.child_529_contributions(cfg.YOUR_AGE))
        residual = cf["your_take_home"] - living - cf["your_roth"] - college
        assert college > 0
        assert residual >= -50, residual         # no shortfall for the portfolio to cover


# ---------------------------------------------------------------- 10. 2026 limits
class TestLimits2026:
    def test_base_values(self):
        L = cfg.CONTRIBUTION_LIMITS_2026
        assert (L["401k"], L["401k_catchup"], L["401k_supercatchup"]) == (24_500, 8_000, 11_250)
        assert (L["ira"], L["ira_catchup"]) == (7_500, 1_100)
        assert (L["hsa_individual"], L["hsa_family"], L["hsa_catchup"]) == (4_400, 8_750, 1_000)
        assert L["401k_total"] == 72_000
        assert cfg.LIMITS_BASE_YEAR == 2026

    def test_limits_by_age(self):
        assert cfg.get_401k_limit(49, 2026) == 24_500
        assert cfg.get_401k_limit(50, 2026) == 32_500
        assert cfg.get_401k_limit(59, 2026) == 32_500
        assert cfg.get_401k_limit(60, 2026) == 35_750
        assert cfg.get_401k_limit(63, 2026) == 35_750
        assert cfg.get_401k_limit(64, 2026) == 32_500
        assert cfg.get_401k_total_limit(40, 2026) == 72_000
        assert cfg.get_401k_total_limit(61, 2026) == 72_000 + 11_250
        assert cfg.get_ira_limit(50, 2026) == 8_600
        assert cfg.get_hsa_limit(55, 2026, is_family=False) == 5_400

    def test_held_flat_in_the_real_frame_for_later_years(self):
        assert cfg.get_401k_limit(40, 2060) == cfg.get_401k_limit(40, 2026)
        assert cfg.get_hsa_limit(40, 2060, True) == 8_750        # not rounded to $500

    def test_the_ui_reads_the_engine(self):
        assert derived.get_limit("401k", 61) == cfg.get_401k_limit(61, cfg.CURRENT_YEAR)
        assert derived.get_limit("ira", 30) == 7_500
