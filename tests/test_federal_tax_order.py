"""Federal tax order inside one year: ordinary income, gains, Social Security.

The engine taxes each event as it happens (a pension draw, a taxable-account sale, then
Social Security at year end). The IRS return is one calculation on the whole year
(Qualified Dividends and Capital Gain Tax Worksheet), so the sum of the booked taxes must
equal that calculation, whatever order the events came in:

* ordinary income (taxable Social Security included) is taxed first, after the deduction;
* gains stack on top of ordinary taxable income for the 0 / 15 / 20% limits;
* the deduction takes ordinary income first, and any unused part shelters gains;
* the OBBBA senior deduction shrinks with the return's MAGI (ordinary income + gains);
* NIIT is 3.8% of the lesser of the gains and the MAGI above its threshold.

Every example is hand-computed from the 2026 tables (Rev. Proc. 2025-32) in Texas, so the
state tax is zero. The figures match the independent engine in tools/tax_crosscheck.
"""
import itertools

import pytest

from retirement_sim import account_simulation as sim
from retirement_sim import config as cfg
from retirement_sim.account_simulation import Account, AccountPortfolio, AccountType


def _portfolio(monkeypatch, status, age):
    for key, value in {"CURRENT_YEAR": 2026, "FILING_STATUS": status, "YOUR_AGE": age,
                       "PARTNER_AGE": age if status == "MFJ" else 0, "STATE_CHOICE": "TX",
                       "RETIREMENT_STATE_CHOICE": None, "INCLUDE_SOCIAL_SECURITY": True,
                       "CHILDREN": []}.items():
        monkeypatch.setattr(cfg, key, value, raising=False)
    pf = AccountPortfolio()
    pf.update_ages(age)
    pf.reset_yearly_income()
    return pf


def _ordinary(pf, amount):
    return pf.calculate_marginal_tax_on_income(amount, owner="you", retirement=True)


def _gains(pf, amount):
    return pf._tax_home_sale_gain(amount)


def _social_security(pf, amount):
    return sim._true_up_social_security_tax(pf, amount, 0.0)


# ---------------------------------------------------------------------------
# 1. Gains are taxed before Social Security is added to income
# ---------------------------------------------------------------------------
class TestGainsStackOnSocialSecurity:
    def test_ltcg_example(self, monkeypatch):
        """Single 62: pension 35,000, gains 20,000, Social Security 30,000.

        Provisional income 35,000 + 20,000 + 15,000 = 70,000, so 85% of the benefit
        is taxable: 25,500. AGI 80,500, deduction 16,100, taxable 64,400, of which
        ordinary 44,400: 1,240 + 12% x 32,000 = 5,080.
        Gains stack from 44,400 to 64,400. The 0% band ends at 49,450, so 5,050 is
        free and 14,950 x 15% = 2,242.50. The old order stacked the gains on the
        pension alone (18,900 to 38,900, all in the 0% band) and charged 0.
        """
        pf = _portfolio(monkeypatch, "Single", 62)
        booked = _ordinary(pf, 35_000) + _gains(pf, 20_000) + _social_security(pf, 30_000)
        assert booked == pytest.approx(5_080 + 2_242.50)
        assert pf.total_niit_paid == 0.0

    def test_ltcg_example_with_senior_deduction(self, monkeypatch):
        """Single 70, same income: taxable SS 25,500, AGI 80,500. Senior deduction
        6,000 - 6% x 5,500 = 5,670, so the deduction is 16,100 + 2,050 + 5,670 = 23,820.
        Taxable 56,680, ordinary 36,680 (1,240 + 12% x 24,280 = 4,153.60). Gains stack
        from 36,680: 0% to 49,450 (12,770), then 7,230 x 15% = 1,084.50."""
        pf = _portfolio(monkeypatch, "Single", 70)
        ordinary_tax = _ordinary(pf, 35_000)
        gain_tax = _gains(pf, 20_000)
        ss_tax = _social_security(pf, 30_000)
        assert ordinary_tax + gain_tax + ss_tax == pytest.approx(4_153.60 + 1_084.50)

    def test_niit_with_senior_deduction(self, monkeypatch):
        """Single 70: pension 150,000, gains 40,000, Social Security 40,000 (taxable
        34,000). MAGI 224,000: NIIT = 3.8% x min(40,000, 24,000) = 912."""
        pf = _portfolio(monkeypatch, "Single", 70)
        _ordinary(pf, 150_000)
        _gains(pf, 40_000)
        _social_security(pf, 40_000)
        assert pf.total_niit_paid == pytest.approx(912.0)

    def test_roth_conversion_pushes_gains_up(self, monkeypatch):
        """Gains already realized are re-priced when a Roth conversion adds income.

        Single 62: gains 20,000 first (all inside the deduction and 0% band: free).
        A 40,000 conversion then adds income: AGI 60,000, deduction 16,100, taxable
        43,900, all ordinary-first: ordinary taxable 40,000 - 16,100 = 23,900
        (1,240 + 12% x 11,500 = 2,620); gains stack from 23,900 to 43,900: all under
        the 0% limit of 49,450. Conversion costs 2,620 and the gains stay free."""
        pf = _portfolio(monkeypatch, "Single", 62)
        assert _gains(pf, 20_000) == pytest.approx(0.0)
        roth = Account("your_roth_ira", AccountType.ROTH_IRA, 0.0, "you")
        trad = Account("your_trad_ira", AccountType.TRADITIONAL_IRA, 100_000, "you")
        pf.accounts = {"your_roth_ira": roth, "your_trad_ira": trad}
        monkeypatch.setattr(cfg, "ENABLE_ROTH_CONVERSION", True)
        monkeypatch.setattr(cfg, "ROTH_CONVERSION_STOP_AGE", 80, raising=False)
        monkeypatch.setattr(cfg, "ROTH_CONVERSION_MAX_ANNUAL", 40_000, raising=False)
        monkeypatch.setattr(cfg, "roth_conversion_target", lambda status=None: 1_000_000)
        converted, tax = pf.perform_roth_conversion(62)
        assert converted == pytest.approx(40_000)
        assert tax == pytest.approx(2_620.0)

    def test_roth_conversion_over_the_zero_band(self, monkeypatch):
        """Single 62: gains 40,000 (taxable 23,900, free), then a 60,000 conversion.
        AGI 100,000, deduction 16,100, taxable 83,900: ordinary 60,000 - 16,100 =
        43,900 (1,240 + 12% x 31,500 = 5,020); gains stack 43,900 to 83,900, 0% to
        49,450 (5,550), then 34,450 x 15% = 5,167.50. The conversion costs
        5,020 + 5,167.50 = 10,187.50: the gains it pushes up are taxed too."""
        pf = _portfolio(monkeypatch, "Single", 62)
        assert _gains(pf, 40_000) == pytest.approx(0.0)
        roth = Account("your_roth_ira", AccountType.ROTH_IRA, 0.0, "you")
        trad = Account("your_trad_ira", AccountType.TRADITIONAL_IRA, 100_000, "you")
        pf.accounts = {"your_roth_ira": roth, "your_trad_ira": trad}
        monkeypatch.setattr(cfg, "ENABLE_ROTH_CONVERSION", True)
        monkeypatch.setattr(cfg, "ROTH_CONVERSION_STOP_AGE", 80, raising=False)
        monkeypatch.setattr(cfg, "ROTH_CONVERSION_MAX_ANNUAL", 60_000, raising=False)
        monkeypatch.setattr(cfg, "roth_conversion_target", lambda status=None: 1_000_000)
        converted, tax = pf.perform_roth_conversion(62)
        assert converted == pytest.approx(60_000)
        assert tax == pytest.approx(5_020 + 5_167.50)

    def test_mfj_example(self, monkeypatch):
        """MFJ 62/62: pension 70,000, gains 40,000, Social Security 55,000.

        Provisional income 70,000 + 40,000 + 27,500 = 137,500, taxable SS =
        min(46,750, 0.85 x (137,500 - 44,000) + min(6,000, 27,500)) = 46,750.
        AGI 156,750, deduction 32,200, taxable 124,550, ordinary 84,550:
        2,480 + 12% x (84,550 - 24,800) = 9,650.
        Gains from 84,550 to 124,550: 0% to 98,900 (14,350), 15% on 25,650 = 3,847.50.
        """
        pf = _portfolio(monkeypatch, "MFJ", 62)
        booked = _ordinary(pf, 70_000) + _gains(pf, 40_000) + _social_security(pf, 55_000)
        assert booked == pytest.approx(9_650 + 3_847.50)

    def test_niit_sees_taxable_social_security(self, monkeypatch):
        """Single 62: pension 150,000, gains 40,000 (MAGI 190,000, under the 200,000
        NIIT line), then Social Security 30,000: taxable 25,500, MAGI 215,500.

        NIIT = 3.8% x min(40,000, 15,500) = 589. Taxable 199,400, ordinary 159,400:
        1,240 + 4,560 + 12,166 + 24% x 53,700 = 30,854. Gains all at 15% = 6,000.
        """
        pf = _portfolio(monkeypatch, "Single", 62)
        booked = _ordinary(pf, 150_000) + _gains(pf, 40_000) + _social_security(pf, 30_000)
        assert pf.total_niit_paid == pytest.approx(589.0)
        assert booked == pytest.approx(30_854 + 6_000 + 589)

    def test_order_of_events_does_not_change_the_total(self, monkeypatch):
        """A pension draw, a sale and a second draw, in every order, cost the same."""
        events = [("ord", 20_000), ("gain", 40_000), ("ord", 30_000)]
        totals = set()
        for order in itertools.permutations(events):
            pf = _portfolio(monkeypatch, "Single", 62)
            total = sum(_ordinary(pf, a) if kind == "ord" else _gains(pf, a)
                        for kind, a in order)
            totals.add(round(total, 4))
        # AGI 90,000, taxable 73,900, ordinary 33,900: 1,240 + 12% x 21,500 = 3,820.
        # Gains 33,900 to 73,900: 15,550 free, 24,450 x 15% = 3,667.50.
        assert totals == {round(3_820 + 3_667.50, 4)}

    def test_withdrawal_path_matches_home_sale_path(self, monkeypatch):
        """A taxable-account sale (_withdraw_single_pass) and a home sale price gains alike."""
        pf = _portfolio(monkeypatch, "Single", 62)
        _ordinary(pf, 35_000)
        brokerage = Account("brokerage", AccountType.TAXABLE, 40_000, "you")
        brokerage.cost_basis = 0.0                      # every dollar sold is a gain
        pf.accounts = {"brokerage": brokerage}
        _, cost = pf._withdraw_single_pass(20_000, your_age=62)
        other = _portfolio(monkeypatch, "Single", 62)
        _ordinary(other, 35_000)
        assert cost == pytest.approx(_gains(other, 20_000))
        # The pension alone leaves 18,900 taxable; 20,000 of gains end at 38,900: all 0%.
        assert cost == pytest.approx(0.0)
        assert pf.year_investment_income == pytest.approx(20_000)


# ---------------------------------------------------------------------------
# 2. Unused deduction shelters gains
# ---------------------------------------------------------------------------
class TestUnusedDeductionShelterGains:
    def test_low_ordinary_income(self, monkeypatch):
        """Single 62: ordinary 10,000, gains 60,000. The deduction (16,100) uses 10,000
        on ordinary income and the other 6,100 on gains: taxable gains 53,900 starting
        at 0. 0% to 49,450, then 4,450 x 15% = 667.50. (The old code taxed all 60,000
        from 0: 10,550 x 15% = 1,582.50.)"""
        pf = _portfolio(monkeypatch, "Single", 62)
        booked = _ordinary(pf, 10_000) + _gains(pf, 60_000)
        assert booked == pytest.approx(667.50)

    def test_gains_only_mfj(self, monkeypatch):
        """MFJ 62/62: gains only, 150,000. Deduction 32,200 all goes to gains: 117,800
        taxable. 0% to 98,900, then 18,900 x 15% = 2,835. (Old: 51,100 x 15% = 7,665.)"""
        pf = _portfolio(monkeypatch, "MFJ", 62)
        assert _gains(pf, 150_000) == pytest.approx(2_835.0)

    def test_gains_before_ordinary_income_end_the_same(self, monkeypatch):
        """Gains first use the whole deduction. The ordinary income that follows takes
        it back, so its marginal tax includes the extra tax on the gains."""
        pf = _portfolio(monkeypatch, "Single", 62)
        booked = _gains(pf, 60_000)                     # 43,900 taxable, all 0%
        assert booked == pytest.approx(0.0)
        booked += _ordinary(pf, 10_000)
        assert booked == pytest.approx(667.50)

    def test_withdrawal_path(self, monkeypatch):
        pf = _portfolio(monkeypatch, "Single", 62)
        _ordinary(pf, 10_000)
        brokerage = Account("brokerage", AccountType.TAXABLE, 60_000, "you")
        brokerage.cost_basis = 0.0
        pf.accounts = {"brokerage": brokerage}
        _, cost = pf._withdraw_single_pass(60_000, your_age=62)
        assert cost == pytest.approx(667.50)


# ---------------------------------------------------------------------------
# 3. The senior deduction is re-priced when later income raises MAGI
# ---------------------------------------------------------------------------
class TestSeniorDeductionRepriced:
    def test_gains_after_ordinary_income(self, monkeypatch):
        """Single 67 in 2026: ordinary 90,000, then gains 30,000.

        MAGI 120,000 cuts the senior deduction to 6,000 - 6% x 45,000 = 3,300 (it was
        5,100 at MAGI 90,000). Deduction 16,100 + 2,050 + 3,300 = 21,450; ordinary
        taxable 68,550: 1,240 + 4,560 + 22% x 18,150 = 9,793.
        Gains 30,000 start above the 0% band: all 15% = 4,500. NIIT 0 (MAGI < 200,000).
        The old code kept the deduction at its MAGI-90,000 value: 9,397, 396 low.
        """
        pf = _portfolio(monkeypatch, "Single", 67)
        booked = _ordinary(pf, 90_000) + _gains(pf, 30_000)
        assert booked == pytest.approx(9_793 + 4_500)

    def test_social_security_after_ordinary_income(self, monkeypatch):
        """Single 67: pension 50,000, Social Security 40,000 at year end.

        Provisional 70,000 > 34,000: taxable = min(34,000, 0.85 x 36,000 + 4,500) = 34,000.
        MAGI 84,000: senior 6,000 - 6% x 9,000 = 5,460, deduction 23,610, taxable
        60,390: 1,240 + 4,560 + 22% x 9,990 = 7,997.80. Booked pension tax + SS tax
        must add to the whole-return figure (the pension alone: MAGI 50,000, full 6,000,
        deduction 24,150, taxable 25,850: 1,240 + 12% x 13,450 = 2,854).
        """
        pf = _portfolio(monkeypatch, "Single", 67)
        booked = _ordinary(pf, 50_000) + _social_security(pf, 40_000)
        assert booked == pytest.approx(7_997.80)

    def test_whole_year_calculation_agrees(self, monkeypatch):
        """Booked taxes equal one IRS-order calculation on the final figures."""
        pf = _portfolio(monkeypatch, "Single", 67)
        booked = _ordinary(pf, 90_000) + _gains(pf, 30_000)
        agi = 120_000
        deduction = cfg.standard_deduction_for_return("Single", [67], agi, 0.0)
        ordinary_taxable = max(0.0, 90_000 - deduction)
        whole = (cfg.progressive_tax(cfg.get_federal_brackets("Single"), ordinary_taxable)
                 + sim.calculate_ltcg_tax(30_000, ordinary_taxable, status="Single"))
        assert booked == pytest.approx(whole)


# ---------------------------------------------------------------------------
# The worksheet's last line: never more than the ordinary tax on all taxable income
# ---------------------------------------------------------------------------
class TestWorksheetCap:
    def test_gain_in_the_12_percent_band(self, monkeypatch):
        """Single 62: ordinary taxable 49,950 (66,050 less 16,100), then a 450 gain.

        Worksheet: ordinary tax 1,240 + 12% x 37,550 = 5,746, plus 450 x 15% = 67.50
        (the 0% band ended at 49,450) = 5,813.50. Ordinary tax on all 50,400 taxable is
        1,240 + 12% x 38,000 = 5,800. The return pays the lesser, 5,800."""
        pf = _portfolio(monkeypatch, "Single", 62)
        booked = _ordinary(pf, 66_050) + _gains(pf, 450)
        assert booked == pytest.approx(5_800.0)

    def test_largest_case_single(self, monkeypatch):
        """Ordinary taxable 49,450, 950 of gain to the 12% top: 15% x 950 = 142.50 on the
        worksheet against 12% x 950 = 114 as ordinary: the cap saves 28.50."""
        pf = _portfolio(monkeypatch, "Single", 62)
        booked = _ordinary(pf, 65_550) + _gains(pf, 950)
        ordinary_only = cfg.progressive_tax(cfg.get_federal_brackets("Single"), 50_400)
        assert booked == pytest.approx(ordinary_only)

    def test_cap_does_not_bind_above_the_band(self, monkeypatch):
        """Gains in the 22% bracket: the 15% rate is lower, the worksheet wins."""
        pf = _portfolio(monkeypatch, "Single", 62)
        booked = _ordinary(pf, 100_000) + _gains(pf, 20_000)
        taxable_ord = 100_000 - 16_100
        assert booked == pytest.approx(
            cfg.progressive_tax(cfg.get_federal_brackets("Single"), taxable_ord) + 0.15 * 20_000)


# ---------------------------------------------------------------------------
# State tax: the same order independence
# ---------------------------------------------------------------------------
def _state_portfolio(monkeypatch, state, status, age, partner_age=0):
    pf = _portfolio(monkeypatch, status, age)
    for key, value in {"STATE_CHOICE": state, "PARTNER_AGE": partner_age}.items():
        monkeypatch.setattr(cfg, key, value, raising=False)
    pf = AccountPortfolio()
    pf.update_ages(age)
    pf.reset_yearly_income()
    return pf


def _state_total(monkeypatch, state, status, age, order, partner_age=0):
    pf = _state_portfolio(monkeypatch, state, status, age, partner_age)
    for kind, amount, owner in order:
        if kind == "gain":
            pf._tax_home_sale_gain(amount)
        else:
            pf.calculate_marginal_tax_on_income(amount, owner=owner, retirement=True)
    return pf.total_state_taxes_paid


class TestStateTaxOrder:
    """A sale and a pension draw cost the same state tax in either order: income that
    comes after a sale starts above the gains already booked, in the state's brackets."""

    @pytest.mark.parametrize("state", ["CA", "MN", "NY", "CO", "AR", "ND", "SC", "WI"])
    @pytest.mark.parametrize("status,age", [("Single", 62), ("MFJ", 62)])
    def test_sale_then_pension_equals_pension_then_sale(self, monkeypatch, state, status, age):
        events = [("ord", 60_000, "you"), ("gain", 100_000, "you"), ("ord", 30_000, "you")]
        totals = {round(_state_total(monkeypatch, state, status, age, order), 4)
                  for order in itertools.permutations(events)}
        assert len(totals) == 1, totals

    @pytest.mark.parametrize("state", ["CA", "MN", "CO", "AR"])
    def test_unmarried_couple_two_returns(self, monkeypatch, state):
        events = [("ord", 60_000, "you"), ("gain", 100_000, "you"),
                  ("ord", 45_000, "partner"), ("ord", 20_000, "you")]
        totals = {round(_state_total(monkeypatch, state, "Single", 62, order, partner_age=60), 4)
                  for order in itertools.permutations(events)}
        assert len(totals) == 1, totals

    def test_california_example(self, monkeypatch):
        """CA Single: a 100,000 gain then 60,000 of ordinary income costs the same as the
        reverse. The pension draw starts above the gain, so it sits in CA's higher brackets,
        not the low ones it would reuse if the sale were left out of the state base."""
        sale_first = _state_total(monkeypatch, "CA", "Single", 62,
                                  [("gain", 100_000, "you"), ("ord", 60_000, "you")])
        pension_first = _state_total(monkeypatch, "CA", "Single", 62,
                                     [("ord", 60_000, "you"), ("gain", 100_000, "you")])
        assert sale_first == pytest.approx(pension_first)
        assert sale_first > 0

    def test_exclusion_state_counts_prior_gains_after_the_exclusion(self, monkeypatch):
        """Arkansas excludes 50% of gains. 100,000 sold counts as 50,000 in the state base
        for income that follows, not 100,000 (which would over-tax the later income)."""
        pf = _state_portfolio(monkeypatch, "AR", "Single", 62)
        pf._tax_home_sale_gain(100_000)
        state = pf._state_model("you")
        base = 50_000.0
        deduction = getattr(state, "deduction")
        expected = (state.calculate_tax(max(0.0, base + 40_000 - deduction))
                    - state.calculate_tax(max(0.0, base - deduction)))
        _, _, quoted = pf._marginal_tax_breakdown(40_000, owner="you", retirement=False)
        assert quoted == pytest.approx(expected)
