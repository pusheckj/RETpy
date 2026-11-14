"""Remaining model gaps (fix/remaining-gaps):

1. Social Security earnings test (withholding before full retirement age, the
   credit back after it), per person.
2. 2026 Roth IRA phase-out and Social Security wage base (one source for the
   check-up and the planner).
3. SECURE 2.0 Roth catch-up for high earners.
4. Student loan interest deduction (working years).
5. The spending chart follows the engine's spending rules at every age.
6. The mortgage payoff projection honours the extra payment's start / stop ages.
7. The housing label is true after payoff.
"""
import os
import sys
from contextlib import contextmanager

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.conftest import load_sample_household  # noqa: E402
from retirement_sim import account_simulation as sim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils import simple_finance as sf  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402
from utils.derived import mortgage_schedule  # noqa: E402


@contextmanager
def applied(ov):
    original = sr._apply_overrides(build_config_overrides(ov))
    try:
        yield cfg
    finally:
        sr._restore_overrides(original)


def comp(base, start, years=50):
    return {a: {"base": base, "bonus": 0, "rsu_gross": 0, "total_comp": base}
            for a in range(start, start + years)}


def single(age, pay, **kw):
    """A single renter with flat pay, no children, no state income tax."""
    ov = {"YOUR_AGE": age, "PARTNER_AGE": 0, "PARTNER_SALARY": 0, "PARTNER_BASE_SALARY": 0,
          "FILING_STATUS": "Single", "CHILDREN": [], "STATE_CHOICE": "TX",
          "YOUR_COMPENSATION_BY_AGE": comp(pay, age), "YOUR_SALARY_GROWTH_RATE": 0.0,
          "SPEND_RENT_MONTHLY": 1_500, "HOME_VALUE": 0, "MORTGAGE_MONTHLY": 0,
          "MORTGAGE_BALANCE": 0, "HOME_EVENTS": [], "HOUSE_MOVE_ENABLED": False,
          "YOUR_HSA_CONTRIBUTION": 0}
    ov.update(kw)
    return ov


# ---------------------------------------------------------------- 1. earnings test
class TestEarningsTestRule:
    def test_limits_are_the_2026_figures(self):
        assert cfg.SS_EARNINGS_TEST_LIMIT == 24_480
        assert cfg.SS_EARNINGS_TEST_LIMIT_FRA_YEAR == 65_160

    def test_one_dollar_in_two_before_the_fra_year(self):
        assert cfg.ss_earnings_test_withholding(20_000, 24_480, 63) == 0.0
        assert cfg.ss_earnings_test_withholding(20_000, 34_480, 63) == pytest.approx(5_000)
        assert cfg.ss_earnings_test_withholding(20_000, 200_000, 63) == 20_000   # all of it

    def test_one_dollar_in_three_in_the_fra_year(self):
        assert cfg.ss_earnings_test_withholding(20_000, 65_160, 66) == 0.0
        assert cfg.ss_earnings_test_withholding(20_000, 80_160, 66) == pytest.approx(5_000)

    def test_nothing_from_full_retirement_age(self):
        assert cfg.ss_earnings_test_withholding(20_000, 500_000, 67) == 0.0

    def test_switch_off(self, monkeypatch):
        monkeypatch.setattr(cfg, "SS_EARNINGS_TEST_ENABLED", False)
        assert cfg.ss_earnings_test_withholding(20_000, 200_000, 63) == 0.0


class TestEarningsTestInTheEngine:
    def ov(self, pay):
        return single(60, pay, SS_CLAIM_AGE=62, YOUR_SS_MONTHLY_FRA=2_800,
                      INCLUDE_SOCIAL_SECURITY=True)

    def test_high_pay_withholds_the_whole_benefit(self):
        with applied(self.ov(95_000)) as c:
            full = 2_800 * c.ss_claim_factor(62) * 12
            cf = sim.working_year_cashflow(62)
            assert cf["social_security"] == 0.0
            assert cf["social_security_withheld"] == pytest.approx(full)

    def test_moderate_pay_withholds_part(self):
        with applied(self.ov(40_000)) as c:
            full = 2_800 * c.ss_claim_factor(62) * 12
            cf = sim.working_year_cashflow(63)
            assert cf["social_security_withheld"] == pytest.approx((40_000 - 24_480) / 2)
            assert cf["social_security"] == pytest.approx(full - (40_000 - 24_480) / 2)

    def test_withheld_months_come_back_after_full_retirement_age(self):
        # Fully withheld at 62-65, retired at 66: 48 months come back, so from
        # 67 the benefit is the one for a claim at 66.
        with applied(self.ov(95_000)) as c:
            assert sim.social_security_for_year(66, 66)["total"] == pytest.approx(
                2_800 * 12 * c.ss_claim_factor(62))
            assert sim.social_security_for_year(67, 66)["total"] == pytest.approx(
                2_800 * 12 * c.ss_claim_factor(66))
            # In the full-retirement-age year only $1 in $3 above $65,160 is
            # withheld: 48 months plus (95,000 - 65,160) / 3 of a month's benefit.
            months = 48 + (95_000 - 65_160) / 3 / (2_800 * c.ss_claim_factor(62))
            assert sim.social_security_for_year(70, 69)["total"] == pytest.approx(
                2_800 * 12 * c.ss_claim_factor(62 + months / 12))
        with applied(self.ov(300_000)):
            # Never past the full benefit, however long you worked.
            assert sim.social_security_for_year(70, 69)["total"] == pytest.approx(2_800 * 12)

    def test_retirement_path_pays_the_credited_benefit(self):
        with applied(self.ov(95_000)) as c:
            p = sim.create_initial_portfolio()
            p.separation_age = 66.0
            p.update_ages(68)
            ss, _ = sim._collect_social_security(p, 68, 1.0)
            assert ss == pytest.approx(2_800 * 12 * c.ss_claim_factor(66))

    def test_partner_tested_on_their_own_pay(self):
        ov = load_sample_household()
        ov.update(YOUR_AGE=63, PARTNER_AGE=63, SS_CLAIM_AGE=62, PARTNER_SS_CLAIM_AGE=62,
                  YOUR_SS_MONTHLY_FRA=2_000, PARTNER_SS_MONTHLY_FRA=2_000,
                  INCLUDE_SOCIAL_SECURITY=True, PARTNER_RETIREMENT_AGE=66,
                  PARTNER_SALARY=50_000, PARTNER_BASE_SALARY=50_000, PARTNER_BONUS_AMOUNT=0,
                  PARTNER_RSU_AMOUNT=0, PARTNER_SALARY_GROWTH_RATE=0.0, MODEL_SPOUSAL_SS_BENEFIT=False)
        with applied(ov) as c:
            each = 2_000 * 12 * c.ss_claim_factor(62)
            # You retired at 63; your partner works on to 66 at $50k.
            year = sim.social_security_for_year(64, 63)
            assert year["you"] == pytest.approx(each)
            assert year["partner"] == pytest.approx(each - (50_000 - 24_480) / 2)

    def test_claiming_at_full_retirement_age_is_untouched(self):
        with applied(single(60, 300_000, SS_CLAIM_AGE=67, YOUR_SS_MONTHLY_FRA=2_800)):
            assert sim.social_security_for_year(67)["total"] == pytest.approx(2_800 * 12)
            assert sim.social_security_for_year(67)["withheld"] == 0.0

    def test_ui_path_matches_the_engine(self):
        ov = self.ov(95_000)
        path = sr.social_security_path(ov, range(61, 70), 66)
        with applied(ov):
            for age in range(61, 70):
                want = sim.social_security_for_year(age, None if age < 66 else 66)["total"]
                assert path[age] == pytest.approx(want)
        assert path[63] == 0.0 and path[67] > path[66] > 0


# ---------------------------------------------------------------- 2. 2026 values
class TestValues2026:
    def test_wage_base(self):
        assert cfg.SS_WAGE_BASE == 184_500
        t = cfg.working_year_taxes(300_000, status="S", partner=False, state="TX")
        assert t["fica"] == pytest.approx(184_500 * 0.062 + 300_000 * 0.0145
                                          + 0.009 * (300_000 - 200_000))

    def test_roth_phaseout_is_one_table(self):
        assert cfg.ROTH_IRA_PHASEOUT_BY_STATUS["S"] == (153_000, 168_000)
        assert cfg.ROTH_IRA_PHASEOUT_BY_STATUS["HOH"] == (153_000, 168_000)
        assert cfg.ROTH_IRA_PHASEOUT_BY_STATUS["MFJ"] == (242_000, 252_000)
        assert sf.roth_phaseout(False) == cfg.ROTH_IRA_PHASEOUT_BY_STATUS["S"]
        assert sf.roth_phaseout(True) == cfg.ROTH_IRA_PHASEOUT_BY_STATUS["MFJ"]


# ---------------------------------------------------------------- 3. Roth catch-up
class TestRothCatchUp:
    def ov(self, age, pay, deferral):
        return single(age, pay, YOUR_401K_CONTRIBUTION=deferral, YOUR_401K_MATCH_PCT=0.04)

    def test_rule(self):
        assert cfg.ROTH_CATCHUP_WAGE_THRESHOLD == 150_000
        assert cfg.roth_catchup_amount(32_500, 55, 2026, 200_000) == 8_000
        assert cfg.roth_catchup_amount(32_500, 55, 2026, 150_000) == 0.0    # not above
        assert cfg.roth_catchup_amount(24_500, 55, 2026, 200_000) == 0.0    # no catch-up made
        assert cfg.roth_catchup_amount(35_750, 61, 2026, 200_000) == 11_250  # 60-63 super catch-up
        assert cfg.roth_catchup_amount(32_500, 49, 2026, 200_000) == 0.0

    def test_high_earner_catch_up_is_after_tax_and_lands_in_roth(self):
        with applied(self.ov(55, 220_000, 32_500)):
            cf = sim.working_year_cashflow(55)
            assert cf["your_401k"] == 32_500 and cf["your_401k_roth"] == 8_000
            assert cf["your_agi"] == pytest.approx(220_000 - 24_500)
            p = sim.create_initial_portfolio()
            k0, r0 = p.accounts["your_401k"].balance, p.accounts["your_roth_ira"].balance
            sim.simulate_accumulation_year(p, 55, 0.0)
            assert p.accounts["your_401k"].balance - k0 == pytest.approx(24_500 + cf["your_match"])
            assert p.accounts["your_roth_ira"].balance - r0 >= 8_000

    def test_take_home_pays_for_it(self, monkeypatch):
        with applied(self.ov(55, 220_000, 32_500)):
            on = sim.working_year_cashflow(55)
            monkeypatch.setattr(cfg, "MODEL_ROTH_CATCHUP_RULE", False)
            off = sim.working_year_cashflow(55)
        assert off["your_401k_roth"] == 0.0
        assert on["total_tax"] > off["total_tax"]
        # The same $32,500 leaves the paycheck either way; the Roth part is taxed first.
        assert on["your_take_home"] == pytest.approx(
            off["your_take_home"] - (on["total_tax"] - off["total_tax"]))

    def test_lower_earner_keeps_it_pre_tax(self):
        with applied(self.ov(55, 120_000, 32_500)):
            cf = sim.working_year_cashflow(55)
            assert cf["your_401k_roth"] == 0.0
            assert cf["your_agi"] == pytest.approx(120_000 - 32_500)

    def test_sidebar_tax_agrees(self):
        from utils import derived
        ov = {"YOUR_AGE": 55, "PARTNER_AGE": 0, "YOUR_BASE_SALARY": 220_000,
              "YOUR_401K_CONTRIBUTION": 32_500, "FILING_STATUS": "Single", "STATE_CHOICE": "TX"}
        with_rule = derived.compute_taxes(ov)
        t = cfg.working_year_taxes(220_000, status="S", partner=False, state="TX",
                                   your_401k=24_500, your_age=55, children_under_17=0)
        assert with_rule["federal"] == pytest.approx(t["federal"])


# ---------------------------------------------------------------- 4. student loans
LOAN = {"name": "Federal loans", "kind": "student_loan", "balance": 45_000, "apr": 0.065,
        "min_payment": 510}
CARD = {"name": "Visa", "kind": "credit_card", "balance": 45_000, "apr": 0.065, "min_payment": 510}


class TestStudentLoanDeduction:
    def test_capped_and_phased_out(self):
        with applied(single(27, 70_000, DEBTS=[LOAN])) as c:
            assert c.student_loan_interest_for_age(27) == pytest.approx(2_828, abs=1)
            assert c.student_loan_interest_deduction(27, 70_000, "S") == 2_500
            assert c.student_loan_interest_deduction(27, 92_500, "S") == pytest.approx(1_250)
            assert c.student_loan_interest_deduction(27, 100_000, "S") == 0.0
            assert c.student_loan_interest_deduction(27, 190_000, "MFJ") == pytest.approx(1_250)
            # The $2,500 cap is not indexed: worth less in today's dollars later.
            assert c.student_loan_interest_deduction(28, 70_000, "S") < 2_500

    def test_only_student_loans_count(self):
        with applied(single(27, 70_000, DEBTS=[CARD])) as c:
            assert c.student_loan_interest_for_age(27) == 0.0
            assert sim.working_year_cashflow(27)["student_loan_deduction"] == 0.0

    def test_lowers_working_year_tax(self):
        with applied(single(27, 70_000, DEBTS=[LOAN])):
            with_loan = sim.working_year_cashflow(27)
        with applied(single(27, 70_000, DEBTS=[LOAN], STUDENT_LOAN_INTEREST_DEDUCTION_MAX=0)):
            without = sim.working_year_cashflow(27)
        assert with_loan["student_loan_deduction"] == 2_500
        assert without["student_loan_deduction"] == 0.0
        # 22% bracket at $67.3k of AGI (Single, 2024 table).
        assert without["federal"] - with_loan["federal"] == pytest.approx(0.22 * 2_500)
        assert with_loan["your_agi"] == pytest.approx(without["your_agi"] - 2_500)
        assert with_loan["fica"] == pytest.approx(without["fica"])

    def test_interest_paid_by_year_from_the_payoff_math(self):
        from retirement_sim import debts as dm
        p = dm.amortize([LOAN])
        by_year = dm.student_interest_by_year([LOAN], 0, "avalanche")
        assert sum(by_year) == pytest.approx(p.total_interest)


# ---------------------------------------------------------------- 5. spending chart
def _chart_and_engine(ov, ret):
    from components import spending_chart as sc
    from components.spending_inputs import compute_lifecycle_multipliers, first_child_window
    cur, end = int(ov["YOUR_AGE"]), cfg.plan_end_age(ov)
    ages = list(range(cur, end + 1))
    yufc, leave = first_child_window(cfg.children_in(ov))
    with sc._cfg_patched(ov, sc._CHILD_CFG_KEYS + sc._LIFESTYLE_CFG_KEYS):
        mult = compute_lifecycle_multipliers(
            preset=str(ov.get("SPEND_LIFECYCLE_PRESET", "Flat (no change)")), current_age=cur,
            retirement_age=ret, plan_until_age=end, years_until_first_child=yufc,
            child_leaves_home_age=leave)
    series, _ = sc.build_category_series(ages, ov, mult, ret)
    chart = {a: sum(ys[i] for label, _, ys in series
                    if not label.startswith(("Car", "Long-term")))
             for i, a in enumerate(ages)}
    with applied(ov):
        _, p = sim.run_detailed_simulation(ret, random_seed=1)
    engine = {r["age"]: r["living"] for r in p.spending_log}
    return chart, engine, series


# Deterministic engine spending: guardrails, long-term care, cars and the
# volatility of healthcare / childcare growth off.
_DETERMINISTIC = dict(DYNAMIC_SPENDING_ENABLED=False, RETURN_BASED_SPENDING_ENABLED=False,
                      LTC_ENABLED=False, CAR_ONETIME_ENABLED=False, CAR_RECURRING_ENABLED=False,
                      INFLATION_VOLATILITY=0.0)


class TestSpendingChartFollowsTheEngine:
    @pytest.mark.parametrize("extra", [
        {},
        {"RETIREMENT_SPENDING_MODE": "% of today's expenses", "RETIREMENT_SPENDING_PCT": 0.8},
        {"SPEND_LIFECYCLE_PRESET": "Early-retirement travel boom, quieter later"},
        {"SPEND_LIFECYCLE_PRESET": "Conservative senior years",
         "RETIREMENT_SPENDING_MODE": "% of today's expenses", "RETIREMENT_SPENDING_PCT": 0.7},
    ])
    def test_every_age_matches(self, extra):
        ov = {**load_sample_household(), **_DETERMINISTIC, **extra}
        chart, engine, _ = _chart_and_engine(ov, 45)
        for age, spent in engine.items():
            assert chart[age] == pytest.approx(spent, abs=0.01), age

    def test_later_years_cut_is_drawn(self):
        ov = {**load_sample_household(), **_DETERMINISTIC}
        chart, _, _ = _chart_and_engine(ov, 45)
        housing = mortgage_schedule(ov, range(34, 96))["by_age"]
        assert housing[74]["housing"] == pytest.approx(housing[80]["housing"])   # paid off
        h = housing[80]["housing"]
        assert (chart[80] - h) == pytest.approx(
            (chart[74] - h) * (1 - cfg.LATE_RETIREMENT_LEISURE_DECREASE))

    def test_college_years_in_retirement(self):
        from tests.conftest import _TESTS
        from utils.profile_io import deserialize_overrides
        with open(os.path.join(_TESTS, "fixtures", "single_parent_hoh.json"), encoding="utf-8") as fh:
            ov = {**deserialize_overrides(fh.read()), **_DETERMINISTIC}
        ret = int(ov["YOUR_AGE"]) + 1
        chart, engine, series = _chart_and_engine(ov, ret)
        assert "College" in [s[0] for s in series]
        for age, spent in engine.items():
            if age >= ret:
                assert chart[age] == pytest.approx(spent, abs=0.01), age

    def test_ltc_expected_value_grows_like_healthcare(self):
        from components import spending_chart as sc
        ov = {**load_sample_household(), "LTC_ENABLED": True}
        age = 88
        got = sc._ltc_expected(ov, age)
        with applied(ov) as c:
            factor = c.expected_cost_growth("healthcare", age - int(ov["YOUR_AGE"]))
            want = c.LTC_PROBABILITY * c.calculate_ltc_cost(age, factor, True)
        assert got == pytest.approx(want)
        assert factor > 1.5

    def test_simulation_median_line(self):
        from components import spending_chart as sc
        ov = load_sample_household()
        ages = list(range(60, 70))
        fig = sc._build_figure(ages, ov, {}, 34, 45, 95, "Flat (no change)",
                               sim_median=[50_000.0] * len(ages), title="t", subtitle="s",
                               yaxis_title="y")
        assert any(t.name == "Simulation median spent" for t in fig.data)


# ---------------------------------------------------------------- 6. paydown window
OWNER = {"YOUR_AGE": 40, "HOME_VALUE": 600_000, "MORTGAGE_BALANCE": 400_000,
         "MORTGAGE_MONTHLY": 3_200, "MORTGAGE_YEARS_REMAINING": 25,
         "MORTGAGE_RATE_FOR_PAYOFF": 0.065, "TRACK_HOME_EQUITY_PAYDOWN": True,
         "EXTRA_MORTGAGE_PAYMENT_ANNUAL": 12_000}


class TestPaydownWindow:
    @pytest.mark.parametrize("start,stop", [(None, None), (50, None), (50, 55), (None, 45)])
    def test_projection_matches_the_schedule(self, start, stop):
        ov = {**OWNER, "EXTRA_MORTGAGE_PAYMENT_START_AGE": start,
              "EXTRA_MORTGAGE_PAYMENT_STOP_AGE": stop}
        proj = sr._payoff_projection_for(ov, 12_000)
        assert proj["payoff_age"] == mortgage_schedule(ov, range(40, 90))["payoff_age"]

    def test_window_changes_the_payoff(self):
        always = sr._payoff_projection_for(OWNER, 12_000)["payoff_age"]
        later = sr._payoff_projection_for({**OWNER, "EXTRA_MORTGAGE_PAYMENT_START_AGE": 50}, 12_000)
        short = sr._payoff_projection_for({**OWNER, "EXTRA_MORTGAGE_PAYMENT_START_AGE": 50,
                                           "EXTRA_MORTGAGE_PAYMENT_STOP_AGE": 55}, 12_000)
        assert always < later["payoff_age"] < short["payoff_age"] <= 65

    def test_projection_matches_the_engine_balance(self):
        ov = {**OWNER, "EXTRA_MORTGAGE_PAYMENT_START_AGE": 50, "EXTRA_MORTGAGE_PAYMENT_STOP_AGE": 55}
        payoff = sr._payoff_projection_for(ov, 12_000)["payoff_age"]
        with applied(ov):
            _, p = sim.run_detailed_simulation(70, random_seed=2)
        bal = {r["age"]: r["mortgage_balance"] for r in p.yearly_history}
        assert bal[payoff - 1] > 0 and bal[payoff] == 0


# ---------------------------------------------------------------- 7. housing label
class TestHousingLabel:
    def legacy(self, **kw):
        ov = {"YOUR_AGE": 40, "HOME_VALUE": 500_000, "MORTGAGE_MONTHLY": 3_000,
              "MORTGAGE_BALANCE": 200_000, "MORTGAGE_YEARS_REMAINING": 10,
              "HOUSE_MOVE_ENABLED": True, "HOUSE_MOVE_AGE": 55, "NEW_HOME_VALUE": 600_000,
              "NEW_MORTGAGE_BALANCE": 300_000, "NEW_MORTGAGE_MONTHLY": 2_500,
              "NEW_MORTGAGE_YEARS": 15, "SPEND_FOOD_MONTHLY": 500}
        ov.update(kw)
        return ov

    def label(self, ov, ages):
        from components import spending_chart as sc
        return sc.build_category_series(ages, ov, {}, 60)[0][0][0]

    def test_legacy_move_paid_off_is_not_called_a_mortgage(self):
        assert self.label(self.legacy(), list(range(40, 91))) == \
            "Housing (mortgage, then tax + insurance)"

    def test_still_mortgage_while_a_loan_runs_every_year(self):
        assert self.label(self.legacy(), list(range(40, 50))) == "Housing (mortgage)"

    def test_bought_outright_with_no_loan_is_tax_and_insurance(self):
        ov = self.legacy(MORTGAGE_BALANCE=0, MORTGAGE_MONTHLY=0, MORTGAGE_YEARS_REMAINING=0,
                         NEW_MORTGAGE_BALANCE=0, NEW_MORTGAGE_MONTHLY=0)
        assert self.label(ov, list(range(40, 91))) == "Housing (property tax, insurance)"
