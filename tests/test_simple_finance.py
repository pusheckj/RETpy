"""Tests for the simple "Get my money in order" page logic (ui/utils/simple_finance.py)
and the page's session-state contract (ui/components/simple_mode.py)."""
import json
import math
import os
import sys
from datetime import date

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from utils import simple_finance as sf  # noqa: E402

TODAY = date(2026, 10, 23)


def _inputs(**overrides):
    d = sf.normalize_inputs(sf.DEFAULT_INPUTS)
    d.update(overrides)
    return sf.normalize_inputs(d)


def _debt(name, balance, apr, minimum):
    return {"name": name, "balance": balance, "apr_pct": apr, "min_payment": minimum}


def _steps(inputs):
    return {s.key: s for s in sf.priority_ladder(inputs, TODAY)}


# ---------------------------------------------------------------------------
# Savings rate and emergency fund
# ---------------------------------------------------------------------------
class TestSavingsRate:
    def test_zero_take_home_is_unknown_not_a_crash(self):
        r = sf.savings_rate(0, 1000, 500)
        assert r.rate is None and r.band == "unknown"
        assert r.monthly_savings == -1500

    @pytest.mark.parametrize("saved, band", [(-100, "negative"), (0, "low"), (99, "low"),
                                             (100, "healthy"), (199, "healthy"),
                                             (200, "strong"), (500, "strong")])
    def test_bands(self, saved, band):
        r = sf.savings_rate(1000, 1000 - saved, 0)
        assert r.band == band
        assert r.rate == pytest.approx(saved / 1000)

    def test_rate_formula(self):
        r = sf.savings_rate(4000, 2000, 1200)
        assert r.rate == pytest.approx(0.20) and r.monthly_savings == 800


class TestEmergencyFund:
    def test_zero_essentials(self):
        f = sf.emergency_fund(5000, 0)
        assert f.months is None and f.status == "unknown"
        assert f.gap_to_min == 0 and f.gap_to_max == 0

    def test_zero_cash_gaps(self):
        f = sf.emergency_fund(0, 2000)
        assert f.months == 0 and f.status == "none"
        assert f.gap_to_min == 6000 and f.gap_to_max == 12000

    def test_months_and_gaps(self):
        f = sf.emergency_fund(5000, 2000, target_months=4)
        assert f.months == pytest.approx(2.5) and f.status == "building"
        assert f.gap_to_min == 1000 and f.gap_to_max == 7000 and f.gap_to_target == 3000

    @pytest.mark.parametrize("cash, status", [(6000, "ok"), (12000, "ok"), (12001, "plenty")])
    def test_range_status(self, cash, status):
        f = sf.emergency_fund(cash, 2000)
        assert f.status == status
        assert f.gap_to_min == 0

    def test_target_months_clamped(self):
        assert sf.emergency_fund(0, 1000, target_months=12).target_months == 6
        assert sf.emergency_fund(0, 1000, target_months=1).target_months == 3


# ---------------------------------------------------------------------------
# Next-dollar ladder
# ---------------------------------------------------------------------------
_ORDER = ["starter_emergency", "employer_match", "high_interest_debt", "full_emergency",
          "hsa", "roth_ira", "max_401k", "moderate_debt", "invest_and_goals"]


class TestLadder:
    def test_fixed_order_and_numbers(self):
        steps = sf.priority_ladder(sf.DEFAULT_INPUTS, TODAY)
        assert [s.key for s in steps] == _ORDER
        assert [s.number for s in steps] == list(range(1, 10))

    def test_debt_steps_with_no_debt_do_not_say_aim_for_none(self):
        steps = _steps(_inputs(debts=[]))
        for key in ("high_interest_debt", "moderate_debt"):
            assert steps[key].status == "done" and steps[key].target_label == "$0 owed"

    def test_default_example_statuses(self):
        s = _steps(sf.DEFAULT_INPUTS)
        assert s["starter_emergency"].status == "done"       # $3,500 >= one month ($2,300)
        assert s["employer_match"].status == "current"       # 3% < 4% match
        assert s["high_interest_debt"].status == "next"
        assert s["hsa"].status == "skip"                     # not eligible by default
        for k in ("full_emergency", "roth_ira", "max_401k", "moderate_debt", "invest_and_goals"):
            assert s[k].status == "later", k

    def test_exactly_one_current_then_one_next(self):
        statuses = [x.status for x in sf.priority_ladder(sf.DEFAULT_INPUTS, TODAY)]
        assert statuses.count("current") == 1 and statuses.count("next") == 1
        open_ = [st for st in statuses if st not in ("done", "skip")]
        assert open_[0] == "current" and open_[1] == "next"
        assert set(open_[2:]) <= {"later"}

    def test_starter_fund_is_1000_or_one_month(self):
        assert _steps(_inputs(needs_monthly=500))["starter_emergency"].target == 1000
        assert _steps(_inputs(needs_monthly=2500))["starter_emergency"].target == 2500
        s = _steps(_inputs(needs_monthly=2500, cash_savings=2000))
        assert s["starter_emergency"].status == "current"

    def test_match_under_shows_free_money(self):
        s = _steps(_inputs(gross_salary_annual=80_000, retirement_contrib_pct=2,
                           employer_match_pct=5, cash_savings=50_000))
        step = s["employer_match"]
        assert step.status == "current"
        assert step.target == pytest.approx(4000)            # 5% of $80k
        assert "$2,400/yr" in step.detail                    # (5% - 2%) of $80k

    def test_match_at_match_is_done(self):
        s = _steps(_inputs(retirement_contrib_pct=4, employer_match_pct=4))
        assert s["employer_match"].status == "done"
        assert s["high_interest_debt"].status == "current"

    def test_no_match_or_no_salary_skips(self):
        assert _steps(_inputs(employer_match_pct=0))["employer_match"].status == "skip"
        s = _steps(_inputs(gross_salary_annual=0))
        assert s["employer_match"].status == "skip" and s["max_401k"].status == "skip"

    def test_high_vs_moderate_vs_low_debt_thresholds(self):
        debts = [_debt("At 8", 1000, 8.0, 50), _debt("Just under 8", 2000, 7.99, 50),
                 _debt("At 4", 3000, 4.0, 50), _debt("Under 4", 4000, 3.99, 50)]
        s = _steps(_inputs(debts=debts))
        assert s["high_interest_debt"].target == 1000
        assert "At 8" in s["high_interest_debt"].detail
        assert s["moderate_debt"].target == 5000
        assert "Just under 8" in s["moderate_debt"].detail and "At 4 " in s["moderate_debt"].detail
        assert "Under 4" in s["invest_and_goals"].detail

    def test_high_interest_highest_rate_first(self):
        debts = [_debt("Card A", 5000, 19.0, 100), _debt("Card B", 900, 27.0, 30)]
        detail = _steps(_inputs(debts=debts))["high_interest_debt"].detail
        assert detail.index("Card B") < detail.index("Card A")

    def test_no_high_or_moderate_debt_is_done(self):
        s = _steps(_inputs(debts=[_debt("Low", 9000, 3.0, 100)]))
        assert s["high_interest_debt"].status == "done"
        assert s["moderate_debt"].status == "done"

    def test_paid_off_debt_is_ignored(self):
        s = _steps(_inputs(debts=[_debt("Old card", 0, 25.0, 0)]))
        assert s["high_interest_debt"].status == "done"

    def test_full_emergency_uses_target_months(self):
        s = _steps(_inputs(needs_monthly=2000, emergency_target_months=5))
        assert s["full_emergency"].target == 10_000
        assert "5 months" in s["full_emergency"].title
        assert _steps(_inputs(needs_monthly=2000, cash_savings=10_000,
                              emergency_target_months=5))["full_emergency"].status == "done"

    def test_hsa_ineligible_eligible_and_maxed(self):
        limits = sf.contribution_limits(False, TODAY)
        assert _steps(_inputs(hsa_eligible=False))["hsa"].status == "skip"
        assert _steps(_inputs(hsa_eligible=True))["hsa"].status in ("next", "later")
        assert _steps(_inputs(hsa_eligible=True, hsa_contrib_annual=limits["hsa"]))["hsa"].status == "done"

    def test_hsa_family_has_higher_limit(self):
        solo = _steps(_inputs(hsa_eligible=True))["hsa"].target
        fam = _steps(_inputs(hsa_eligible=True, hsa_family=True))["hsa"].target
        assert fam > solo

    def test_roth_and_401k_done_at_limit(self):
        lim = sf.contribution_limits(False, TODAY)
        s = _steps(_inputs(ira_contrib_annual=lim["ira"], gross_salary_annual=200_000,
                           retirement_contrib_pct=100 * lim["401k"] / 200_000))
        assert s["roth_ira"].status == "done" and s["max_401k"].status == "done"
        assert "backdoor Roth" in s["roth_ira"].why

    def test_everything_done_leaves_invest_current(self):
        lim = sf.contribution_limits(True, TODAY)
        s = _steps(_inputs(cash_savings=100_000, needs_monthly=3000, gross_salary_annual=300_000,
                           retirement_contrib_pct=10, employer_match_pct=5, hsa_eligible=True,
                           hsa_family=True, hsa_contrib_annual=lim["hsa"],
                           ira_contrib_annual=lim["ira"], debts=[]))
        assert s["invest_and_goals"].status == "current"
        assert all(x.status == "done" for k, x in s.items() if k != "invest_and_goals")

    def test_status_moves_down_the_ladder(self):
        """Fixing the current step promotes the next one."""
        base = dict(cash_savings=500, needs_monthly=2000)
        assert _steps(_inputs(**base))["starter_emergency"].status == "current"
        assert _steps(_inputs(**base))["employer_match"].status == "next"
        s = _steps(_inputs(**{**base, "cash_savings": 2000}))
        assert s["starter_emergency"].status == "done"
        assert s["employer_match"].status == "current"
        assert s["high_interest_debt"].status == "next"

    def test_limits_are_this_years_irs_figures(self):
        """The page tells people what to do THIS year, so it shows the current
        IRS limits in actual dollars (2026: 401(k) $24,500, IRA $7,500, HSA
        $4,400 / $8,750), not the engine's constant-2024-dollar table."""
        from datetime import date
        lim = sf.contribution_limits(False, date(2026, 6, 1))
        assert (lim["401k"], lim["ira"], lim["hsa"]) == (24_500, 7_500, 4_400)
        assert sf.contribution_limits(True, date(2026, 6, 1))["hsa"] == 8_750
        # a later year uses the latest known limits; an earlier one the config base
        assert sf.contribution_limits(False, date(2031, 1, 1))["401k"] == 24_500
        assert sf.contribution_limits(False, date(2024, 1, 1))["401k"] == cfg.get_inflation_adjusted_limit("401k", 0)


# ---------------------------------------------------------------------------
# Roth IRA income limits (2026: single $153,000-$168,000, joint $242,000-$252,000)
# ---------------------------------------------------------------------------
def _roth(**kw):
    base = dict(retirement_contrib_pct=0.0, hsa_eligible=False, hsa_contrib_annual=0.0)
    return sf.roth_check(_inputs(**{**base, **kw}), TODAY)


class TestRothLimits:
    def test_table_is_labelled_2026(self):
        assert sf.ROTH_PHASEOUT[2026] == {"single": (153_000, 168_000), "joint": (242_000, 252_000)}
        assert sf.roth_phaseout(False, TODAY) == (153_000, 168_000)
        assert sf.roth_phaseout(True, TODAY) == (242_000, 252_000)
        assert sf.roth_phaseout(True, date(2031, 1, 1)) == (242_000, 252_000)   # latest known year

    def test_earlier_years_fall_back_to_the_engines_2024_ranges(self):
        d = date(2024, 5, 1)
        assert sf.roth_phaseout(False, d) == cfg.ROTH_IRA_PHASEOUT_BY_STATUS["S"]
        assert sf.roth_phaseout(True, d) == cfg.ROTH_IRA_PHASEOUT_BY_STATUS["MFJ"]

    @pytest.mark.parametrize("married", [False, True])
    def test_straight_line_from_full_to_zero(self, married):
        lo, hi = sf.roth_phaseout(married, TODAY)
        for magi in (0, lo - 1, lo, lo + 1, (lo + hi) / 2, hi - 1, hi, hi + 1, 1e7):
            expected = 7_500 if magi <= lo else 0 if magi >= hi else math.floor(7_500 * (hi - magi) / (hi - lo))
            assert sf.roth_direct_limit(magi, married, TODAY) == expected

    def test_formula_shape_matches_the_engine_on_the_fallback_years(self):
        d = date(2024, 5, 1)
        for married, status in ((False, "Single"), (True, "Married filing jointly")):
            lo, hi = sf.roth_phaseout(married, d)
            for magi in (0, lo, lo + 1, (lo + hi) / 2, hi - 1, hi, hi + 5):
                eng = cfg.roth_ira_allowed(sf.contribution_limits(False, d)["ira"], magi, status)
                assert sf.roth_direct_limit(magi, married, d) == pytest.approx(math.floor(eng + 1e-9))

    # -- single --------------------------------------------------------------
    def test_single_below_range_is_direct(self):
        r = _roth(gross_salary_annual=100_000)
        assert (r.case, r.direct_limit) == ("direct", 7_500)
        assert "full $7,500" in r.note

    def test_single_at_bottom_of_range_is_still_full(self):
        assert _roth(gross_salary_annual=153_000).case == "direct"

    def test_single_inside_range_is_reduced(self):
        r = _roth(gross_salary_annual=160_500)               # halfway
        assert (r.case, r.direct_limit) == ("reduced", 3_750)
        assert "$3,750" in r.note and "backdoor Roth" in r.note

    def test_single_reduced_amount_rounds_down_to_a_whole_dollar(self):
        assert _roth(gross_salary_annual=160_001).direct_limit == 3_999    # 3999.5
        assert _roth(gross_salary_annual=153_001).direct_limit == 7_499    # 7499.5

    def test_single_at_or_over_top_is_backdoor_only(self):
        for pay in (168_000, 200_000, 2_000_000):
            r = _roth(gross_salary_annual=pay)
            assert (r.case, r.direct_limit) == ("backdoor", 0.0), pay

    def test_a_dollar_under_the_top_that_rounds_to_zero_is_backdoor_only(self):
        r = _roth(gross_salary_annual=167_999)               # 0.5 -> $0 direct
        assert (r.case, r.direct_limit) == ("backdoor", 0.0)

    # -- married filing jointly ----------------------------------------------
    def test_joint_uses_the_higher_range(self):
        assert _roth(married=True, gross_salary_annual=200_000).case == "direct"
        r = _roth(married=True, gross_salary_annual=150_000, partner_salary_annual=100_000)
        assert (r.case, r.direct_limit) == ("reduced", 1_500)            # $250,000 in $242-252k
        assert _roth(married=True, gross_salary_annual=252_000).case == "backdoor"

    def test_same_income_is_backdoor_single_but_direct_when_joint_alone(self):
        assert _roth(gross_salary_annual=200_000).case == "backdoor"
        assert _roth(married=True, gross_salary_annual=200_000).case == "direct"

    def test_partner_pay_pushes_a_married_couple_over(self):
        assert _roth(married=True, gross_salary_annual=120_000,
                     partner_salary_annual=150_000).case == "backdoor"

    def test_partner_pay_is_ignored_when_not_married(self):
        r = _roth(married=False, gross_salary_annual=100_000, partner_salary_annual=500_000)
        assert (r.case, r.magi) == ("direct", 100_000)

    def test_salary_zero(self):
        r = _roth(gross_salary_annual=0)
        assert (r.case, r.magi, r.direct_limit) == ("direct", 0, 7_500)
        assert _roth(gross_salary_annual=0, married=True, partner_salary_annual=300_000).case == "backdoor"
        assert _roth(gross_salary_annual=0, partner_salary_annual=300_000).case == "direct"

    # -- what lowers MAGI ----------------------------------------------------
    def test_401k_deferral_lowers_magi(self):
        assert _roth(gross_salary_annual=170_000).case == "backdoor"
        r = _roth(gross_salary_annual=170_000, retirement_contrib_pct=5)       # -8,500
        assert (r.magi, r.case, r.direct_limit) == (161_500, "reduced", 3_250)
        r = _roth(gross_salary_annual=170_000, retirement_contrib_pct=10)      # -17,000
        assert (r.magi, r.case) == (153_000, "direct")

    def test_401k_deferral_is_capped_at_the_yearly_limit(self):
        r = _roth(gross_salary_annual=400_000, retirement_contrib_pct=100)
        assert r.magi == 400_000 - 24_500

    def test_hsa_contribution_lowers_magi_only_when_eligible(self):
        r = _roth(gross_salary_annual=170_000, retirement_contrib_pct=5,
                  hsa_eligible=True, hsa_contrib_annual=4_000)
        assert (r.magi, r.case, r.direct_limit) == (157_500, "reduced", 5_250)
        r = _roth(gross_salary_annual=170_000, retirement_contrib_pct=5,
                  hsa_eligible=False, hsa_contrib_annual=4_000)
        assert r.magi == 161_500

    def test_partner_pay_and_your_deferrals_combine(self):
        i = _inputs(married=True, gross_salary_annual=150_000, partner_salary_annual=100_000,
                    retirement_contrib_pct=10, hsa_eligible=True, hsa_contrib_annual=5_000)
        assert sf.roth_magi(i, TODAY) == 150_000 + 100_000 - 15_000 - 5_000

    def test_magi_never_goes_negative(self):
        assert sf.roth_magi(_inputs(gross_salary_annual=10_000, hsa_eligible=True,
                                    hsa_contrib_annual=50_000), TODAY) == 0

    # -- the ladder step -----------------------------------------------------
    def test_step_under_the_range_is_unchanged(self):
        s = _steps(_inputs(gross_salary_annual=100_000))["roth_ira"]
        assert s.title == "Max out a Roth IRA" and s.target == 7_500
        assert s.target_label == "$7,500/yr"

    def test_step_inside_the_range_aims_for_the_reduced_amount(self):
        s = _steps(_inputs(gross_salary_annual=160_500, retirement_contrib_pct=0))["roth_ira"]
        assert s.key == "roth_ira" and s.number == 6
        assert s.title == "Max out a Roth IRA" and s.target == 3_750
        assert s.target_label == "$3,750/yr"
        assert "cuts the direct Roth limit to $3,750" in s.detail
        assert "backdoor Roth" in s.detail

    def test_step_inside_the_range_is_done_at_the_reduced_amount(self):
        base = dict(gross_salary_annual=160_500, retirement_contrib_pct=0)
        assert _steps(_inputs(**base, ira_contrib_annual=3_749))["roth_ira"].status != "done"
        s = _steps(_inputs(**base, ira_contrib_annual=3_750))["roth_ira"]
        assert s.status == "done" and "cuts the direct Roth limit" in s.detail

    def test_step_over_the_range_becomes_a_backdoor_roth(self):
        s = _steps(_inputs(gross_salary_annual=200_000, retirement_contrib_pct=0))["roth_ira"]
        assert s.key == "roth_ira" and s.number == 6
        assert s.title == "Max out a backdoor Roth IRA"
        assert s.target == 7_500 and s.target_label == "$7,500/yr"
        assert "too much to put money in a Roth directly" in s.why
        assert "traditional IRA" in s.why and "convert" in s.why
        assert "pro-rata rule" in s.why

    def test_the_pro_rata_caution_only_shows_over_the_range(self):
        for pay in (50_000, 160_500):
            s = _steps(_inputs(gross_salary_annual=pay, retirement_contrib_pct=0))["roth_ira"]
            assert "pro-rata" not in s.why + s.detail

    def test_still_one_ladder_in_the_same_order(self):
        for pay in (50_000, 160_500, 200_000):
            steps = sf.priority_ladder(_inputs(gross_salary_annual=pay), TODAY)
            assert [x.key for x in steps] == _ORDER

    def test_married_couple_step_uses_the_joint_range(self):
        s = _steps(_inputs(married=True, gross_salary_annual=150_000, partner_salary_annual=100_000,
                           retirement_contrib_pct=0))["roth_ira"]
        assert s.target == 1_500 and "$1,500" in s.detail

    def test_analyze_ladder_follows_roth_case(self):
        res = sf.analyze(_inputs(gross_salary_annual=200_000, retirement_contrib_pct=0), TODAY)
        assert next(x for x in res["ladder"] if x.key == "roth_ira").title.startswith("Max out a backdoor")


class TestMax401kPct:
    def test_percent_that_reaches_the_limit(self):
        assert sf.max_401k_pct(100_000, TODAY) == 24.5
        assert sf.max_401k_pct(50_000, TODAY) == 49.0

    def test_rounds_up_so_the_limit_is_reached(self):
        pct = sf.max_401k_pct(65_000, TODAY)                  # 37.6923...
        assert pct == 37.7 and 65_000 * pct / 100 >= 24_500

    def test_caps_at_100_and_no_salary_gives_none(self):
        assert sf.max_401k_pct(20_000, TODAY) == 100.0
        assert sf.max_401k_pct(0, TODAY) is None


class TestNormalizeRothFields:
    def test_defaults(self):
        assert sf.DEFAULT_INPUTS["married"] is False and sf.DEFAULT_INPUTS["partner_salary_annual"] == 0.0
        assert sf.normalize_inputs(None)["married"] is False

    def test_old_saved_dicts_load(self):
        old = {k: v for k, v in sf.DEFAULT_INPUTS.items() if k not in ("married", "partner_salary_annual")}
        d = sf.normalize_inputs(old)
        assert d["married"] is False and d["partner_salary_annual"] == 0.0
        assert d["gross_salary_annual"] == old["gross_salary_annual"]

    def test_coercion_and_clamps(self):
        d = sf.normalize_inputs({"married": "yes", "partner_salary_annual": "$85,000"})
        assert d["married"] is True and d["partner_salary_annual"] == 85_000.0
        d = sf.normalize_inputs({"married": "maybe", "partner_salary_annual": -5})
        assert d["married"] is False and d["partner_salary_annual"] == 0.0
        assert sf.normalize_inputs({"partner_salary_annual": 1e12})["partner_salary_annual"] == sf.BALANCE_MAX


# ---------------------------------------------------------------------------
# Debt payoff
# ---------------------------------------------------------------------------
_MIXED = [_debt("Big card", 8000, 22.0, 200), _debt("Small loan", 1500, 5.0, 60),
          _debt("Store card", 3000, 27.0, 90)]


class TestPayoff:
    def test_avalanche_never_costs_more_interest(self):
        for extra in (0, 100, 500):
            cmp = sf.compare_payoff(_MIXED, extra, TODAY)
            assert cmp["avalanche"].paid_off and cmp["snowball"].paid_off
            assert cmp["avalanche"].total_interest <= cmp["snowball"].total_interest + 1e-6
            assert cmp["interest_saved"] >= -1e-6

    def test_strategy_orders(self):
        av = sf.simulate_payoff(_MIXED, 300, "avalanche", TODAY)
        sb = sf.simulate_payoff(_MIXED, 300, "snowball", TODAY)
        assert av.order[0]["name"] == "Store card"            # highest APR
        assert sb.order[0]["name"] == "Small loan"            # smallest balance
        assert av.focus_order == ["Store card", "Big card", "Small loan"]
        assert sb.focus_order == ["Small loan", "Store card", "Big card"]

    def test_single_debt_matches_amortization_formula(self):
        b, apr, n = 10_000.0, 12.0, 60
        r = apr / 1200
        payment = b * r / (1 - (1 + r) ** -n)
        res = sf.simulate_payoff([_debt("Loan", b, apr, payment)], 0, "avalanche", TODAY)
        assert res.paid_off and res.months == n
        assert res.total_interest == pytest.approx(payment * n - b, abs=0.01)
        assert res.total_paid == pytest.approx(payment * n, abs=0.01)

    def test_single_debt_month_count_closed_form(self):
        b, apr, p = 5_000.0, 18.0, 150.0
        r = apr / 1200
        n = -math.log(1 - r * b / p) / math.log(1 + r)
        res = sf.simulate_payoff([_debt("Card", b, apr, p)], 0, "snowball", TODAY)
        assert res.months == math.ceil(n)

    def test_minimum_below_interest_is_flagged(self):
        debts = [_debt("Underwater", 10_000, 24.0, 150), _debt("Fine", 2000, 10.0, 100)]
        res = sf.simulate_payoff(debts, 0, "avalanche", TODAY)
        assert res.underwater == ["Underwater"]
        assert sf.underwater_debts([_debt("Exact", 12_000, 12.0, 120)]) == ["Exact"]

    def test_extra_payment_shortens_payoff(self):
        base = sf.simulate_payoff(_MIXED, 0, "avalanche", TODAY)
        more = sf.simulate_payoff(_MIXED, 250, "avalanche", TODAY)
        assert more.months < base.months
        assert more.total_interest < base.total_interest

    def test_freed_minimums_roll_over(self):
        debts = [_debt("Small", 500, 10.0, 100), _debt("Big", 5000, 10.0, 100)]
        both = sf.simulate_payoff(debts, 0, "snowball", TODAY)
        alone = sf.simulate_payoff(debts[1:], 0, "snowball", TODAY)
        assert both.months < alone.months
        # The total paid each month stays at the starting budget until the end.
        assert both.monthly_payment == 200
        assert both.total_paid == pytest.approx(sum(d["balance"] for d in debts) + both.total_interest)

    def test_600_month_cap(self):
        res = sf.simulate_payoff([_debt("Stuck", 10_000, 24.0, 150)], 0, "avalanche", TODAY)
        assert not res.paid_off
        assert res.months == sf.MAX_PAYOFF_MONTHS == 600
        assert res.debt_free_date is None
        assert len(res.balances) == 601
        assert res.remaining_balance > 10_000
        assert res.order[0]["payoff_month"] is None
        cmp = sf.compare_payoff([_debt("Stuck", 10_000, 24.0, 150)], 0, TODAY)
        assert cmp["interest_saved"] is None

    def test_extra_rescues_underwater_debt(self):
        res = sf.simulate_payoff([_debt("Stuck", 10_000, 24.0, 150)], 200, "avalanche", TODAY)
        assert res.paid_off and res.underwater == ["Stuck"]

    def test_no_debts(self):
        res = sf.simulate_payoff([], 100, "avalanche", TODAY)
        assert res.paid_off and res.months == 0 and res.balances == [0.0] and res.order == []

    def test_dates_and_balance_series(self):
        res = sf.simulate_payoff([_debt("Card", 300, 0.0, 100)], 0, "avalanche", TODAY)
        assert res.months == 3 and res.debt_free_date == "Jan 2027"
        assert res.balances == pytest.approx([300, 200, 100, 0])
        assert res.order[0]["payoff_date"] == "Jan 2027"
        assert sf.month_label(date(2026, 12, 1), 1) == "Jan 2027"
        assert sf.month_date(date(2026, 11, 5), 2) == date(2027, 1, 1)

    def test_zero_interest_total_interest_zero(self):
        res = sf.simulate_payoff([_debt("Friend", 1000, 0.0, 250)], 0, "snowball", TODAY)
        assert res.total_interest == 0 and res.months == 4


# ---------------------------------------------------------------------------
# 50/30/20
# ---------------------------------------------------------------------------
class TestBudget:
    def test_exact_503020(self):
        b = {x.key: x for x in sf.budget_503020(4000, 2000, 1200)}
        assert b["needs"].share == pytest.approx(0.5)
        assert b["wants"].share == pytest.approx(0.3)
        assert b["savings"].share == pytest.approx(0.2) and b["savings"].amount == 800
        assert all(x.status == "on_track" for x in b.values())

    def test_over_and_under(self):
        b = {x.key: x for x in sf.budget_503020(4000, 2600, 1300)}
        assert b["needs"].status == "off" and "Housing" in b["needs"].message
        assert b["wants"].status == "close"
        assert b["savings"].status == "off" and b["savings"].share == pytest.approx(0.025)

    def test_negative_savings(self):
        b = {x.key: x for x in sf.budget_503020(3000, 2500, 1000)}
        assert b["savings"].amount == -500 and b["savings"].share < 0

    def test_zero_take_home(self):
        assert all(x.share is None and x.status == "unknown" for x in sf.budget_503020(0, 100, 100))


# ---------------------------------------------------------------------------
# normalize_inputs
# ---------------------------------------------------------------------------
class TestNormalize:
    @pytest.mark.parametrize("bad", [None, {}, "garbage", 42, [1, 2], 3.5, True])
    def test_non_dicts_and_empty_give_defaults(self, bad):
        assert sf.normalize_inputs(bad) == sf.normalize_inputs(sf.DEFAULT_INPUTS)

    def test_defaults_are_already_normal_and_idempotent(self):
        once = sf.normalize_inputs(sf.DEFAULT_INPUTS)
        assert once == sf.DEFAULT_INPUTS
        weird = {"take_home_monthly": "$5,000", "debts": [{"balance": "-3"}, "x"], "zzz": 1}
        assert sf.normalize_inputs(sf.normalize_inputs(weird)) == sf.normalize_inputs(weird)

    def test_garbage_types_fall_back_to_defaults(self):
        d = sf.normalize_inputs({
            "take_home_monthly": "lots", "needs_monthly": None, "wants_monthly": [1],
            "cash_savings": float("nan"), "gross_salary_annual": float("inf"),
            "retirement_contrib_pct": True, "hsa_eligible": "maybe", "hsa_family": {"a": 1},
            "emergency_target_months": "soon", "debts": "none", "extra_debt_payment_monthly": {},
        })
        for k in ("take_home_monthly", "needs_monthly", "wants_monthly", "cash_savings",
                  "gross_salary_annual", "retirement_contrib_pct", "hsa_eligible",
                  "hsa_family", "emergency_target_months", "debts", "extra_debt_payment_monthly"):
            assert d[k] == sf.DEFAULT_INPUTS[k], k

    def test_unknown_keys_dropped_and_partial_filled(self):
        d = sf.normalize_inputs({"take_home_monthly": 5000, "legacy_field": 1, "__proto__": "x"})
        assert set(d) == set(sf.DEFAULT_INPUTS)
        assert d["take_home_monthly"] == 5000.0
        assert d["needs_monthly"] == sf.DEFAULT_INPUTS["needs_monthly"]

    def test_negative_values_clamped_to_zero(self):
        d = sf.normalize_inputs({"take_home_monthly": -10, "cash_savings": -500,
                                 "debts": [{"name": "Card", "balance": -1200, "apr_pct": -3,
                                            "min_payment": -50}]})
        assert d["take_home_monthly"] == 0 and d["cash_savings"] == 0
        assert d["debts"] == [{"name": "Card", "balance": 0.0, "apr_pct": 0.0, "min_payment": 0.0,
                               "kind": "credit_card"}]      # type guessed from the name

    def test_coercion_and_clamps(self):
        d = sf.normalize_inputs({"take_home_monthly": "$4,250.50", "retirement_contrib_pct": "6%",
                                 "employer_match_pct": 500, "hsa_eligible": "yes",
                                 "hsa_family": 0, "emergency_target_months": 12.7})
        assert d["take_home_monthly"] == 4250.5 and d["retirement_contrib_pct"] == 6.0
        assert d["employer_match_pct"] == 100.0
        assert d["hsa_eligible"] is True and d["hsa_family"] is False
        assert d["emergency_target_months"] == 6
        assert sf.normalize_inputs({"emergency_target_months": 0})["emergency_target_months"] == 3

    def test_debt_rows(self):
        rows = [{"name": "  Visa  ", "balance": "2,000", "apr_pct": "19.9", "min_payment": 40},
                "not a dict", None, {"balance": 100}, {"name": 123, "apr_pct": 250}]
        d = sf.normalize_inputs({"debts": rows})["debts"]
        assert [r["name"] for r in d] == ["Visa", "Debt 2", "123"]
        assert d[0]["balance"] == 2000.0 and d[0]["apr_pct"] == 19.9
        assert d[2]["apr_pct"] == 100.0
        assert sf.normalize_inputs({"debts": []})["debts"] == []
        long = sf.normalize_inputs({"debts": [{"name": "x" * 99, "balance": 1}] * 50})["debts"]
        assert len(long) == sf.MAX_DEBTS and len(long[0]["name"]) == sf.DEBT_NAME_MAX_LEN

    def test_json_round_trip_and_no_aliasing(self):
        d = sf.normalize_inputs(None)
        assert sf.normalize_inputs(json.loads(json.dumps(d))) == d
        d["debts"][0]["balance"] = 1
        d["debts"].append({})
        assert sf.DEFAULT_INPUTS["debts"][0]["balance"] != 1
        assert len(sf.normalize_inputs(None)["debts"]) == len(sf.DEFAULT_INPUTS["debts"])

    def test_analyze_survives_garbage(self):
        for bad in (None, {}, "x", {"debts": [{"balance": "abc"}], "take_home_monthly": 0}):
            res = sf.analyze(bad, TODAY)
            assert {"savings_rate", "emergency_fund", "ladder", "payoff", "budget",
                    "warnings"} <= set(res)

    def test_analyze_warnings(self):
        res = sf.analyze(_inputs(needs_monthly=100, take_home_monthly=1000, wants_monthly=900,
                                 extra_debt_payment_monthly=300), TODAY)
        assert len(res["warnings"]) == 2


# ---------------------------------------------------------------------------
# Page contract (Streamlit AppTest; no browser)
# ---------------------------------------------------------------------------
def _page_script():
    import os
    import sys
    sys.path[:0] = [os.environ["SIMPLE_TEST_UI"], os.environ["SIMPLE_TEST_ROOT"]]
    import streamlit as st
    from components import simple_mode
    simple_mode.render(st)


@pytest.fixture
def page(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SIMPLE_TEST_UI", _UI)
    monkeypatch.setenv("SIMPLE_TEST_ROOT", _ROOT)
    at = AppTest.from_function(_page_script, default_timeout=30)
    return at


def _by_key(widgets, key):
    return next(w for w in widgets if w.key == key)


class TestPage:
    def test_first_run_writes_normalized_defaults(self, page):
        page.run()
        assert not page.exception, page.exception
        assert page.session_state["simple_inputs"] == sf.normalize_inputs(sf.DEFAULT_INPUTS)

    def test_editing_a_debt_updates_inputs(self, page):
        page.run()
        _by_key(page.number_input, "simple_w_debt_0_balance").set_value(1234.0).run()
        assert not page.exception, page.exception
        assert page.session_state["simple_inputs"]["debts"][0]["balance"] == 1234.0

    def test_restored_inputs_reseed_widgets(self, page):
        page.run()
        restored = {"take_home_monthly": 6100, "debts": [_debt("Only one", 999, 9.0, 50)]}
        page.session_state["simple_inputs"] = restored
        page.run()
        assert not page.exception, page.exception
        assert _by_key(page.number_input, "simple_w_take_home_monthly").value == 6100.0
        assert _by_key(page.text_input, "simple_w_debt_0_name").value == "Only one"
        assert page.session_state["simple_inputs"]["debts"] == [{**_debt("Only one", 999.0, 9.0, 50.0),
                                                                 "kind": "other"}]

    def test_add_and_remove_debt(self, page):
        page.run()
        n = len(sf.DEFAULT_INPUTS["debts"])
        _by_key(page.button, "simple_debt_add").click().run()
        assert len(page.session_state["simple_inputs"]["debts"]) == n + 1
        _by_key(page.button, "simple_debt_rm_0").click().run()
        debts = page.session_state["simple_inputs"]["debts"]
        assert not page.exception, page.exception
        assert len(debts) == n
        assert debts[0]["name"] == sf.DEFAULT_INPUTS["debts"][1]["name"]
        assert _by_key(page.text_input, "simple_w_debt_0_name").value == debts[0]["name"]

    def _markdown_text(self, page):
        return " ".join(m.value for m in page.markdown)

    def test_extra_goes_to_line_only_when_there_is_extra(self, page):
        page.session_state["simple_inputs"] = {"extra_debt_payment_monthly": 0}
        page.run()
        assert "extra goes to" not in self._markdown_text(page)
        page.session_state["simple_inputs"] = {"extra_debt_payment_monthly": 200}
        page.run()
        assert "extra goes to" in self._markdown_text(page)

    def test_wont_pay_off_state_renders(self, page):
        page.session_state["simple_inputs"] = {"debts": [_debt("Stuck", 10_000, 24.0, 150)],
                                               "extra_debt_payment_monthly": 0}
        page.run()
        assert not page.exception, page.exception
        assert any("doesn't cover" in w.value for w in page.warning)
        assert "Won't pay off at these payments" in self._markdown_text(page)

    def test_no_debts_and_zero_income_render(self, page):
        page.session_state["simple_inputs"] = {"debts": [], "take_home_monthly": 0,
                                               "needs_monthly": 0, "wants_monthly": 0}
        page.run()
        assert not page.exception, page.exception
        text = self._markdown_text(page)
        assert "No debts entered" in text
        assert "Add your take-home pay" in text

    # -- Roth income note and "Max out" buttons ------------------------------
    def _button_keys(self, page):
        return {b.key for b in page.button}

    def _captions(self, page):
        return " ".join(c.value for c in page.caption)

    def test_roth_note_says_which_case_applies(self, page):
        page.run()
        assert "full $7,500 directly" in self._markdown_text(page).replace("&#36;", "$")
        page.session_state["simple_inputs"] = {"gross_salary_annual": 160_500, "retirement_contrib_pct": 0}
        page.run()
        assert "cuts the direct Roth limit to $3,750" in self._markdown_text(page).replace("&#36;", "$")
        page.session_state["simple_inputs"] = {"gross_salary_annual": 200_000, "retirement_contrib_pct": 0}
        page.run()
        assert "backdoor Roth is the way in" in self._markdown_text(page)

    def test_partner_pay_input_shows_only_when_married(self, page):
        page.run()
        assert not any(w.key == "simple_w_partner_salary_annual" for w in page.number_input)
        page.toggle(key="simple_w_married").set_value(True).run()
        assert not page.exception, page.exception
        _by_key(page.number_input, "simple_w_partner_salary_annual").set_value(90_000.0).run()
        saved = page.session_state["simple_inputs"]
        assert saved["married"] is True and saved["partner_salary_annual"] == 90_000.0

    def test_partner_pay_survives_hiding_the_input(self, page):
        page.session_state["simple_inputs"] = {"married": True, "partner_salary_annual": 70_000}
        page.run()
        page.toggle(key="simple_w_married").set_value(False).run()
        page.toggle(key="simple_w_married").set_value(True).run()
        assert page.session_state["simple_inputs"]["partner_salary_annual"] == 70_000.0

    def test_hsa_answers_survive_the_toggle_going_off_and_on(self, page):
        page.session_state["simple_inputs"] = {"hsa_eligible": True, "hsa_family": True,
                                               "hsa_contrib_annual": 1_200}
        page.run()
        page.toggle(key="simple_w_hsa_eligible").set_value(False).run()
        page.toggle(key="simple_w_hsa_eligible").set_value(True).run()
        saved = page.session_state["simple_inputs"]
        assert saved["hsa_contrib_annual"] == 1_200.0 and saved["hsa_family"] is True
        assert _by_key(page.number_input, "simple_w_hsa_contrib_annual").value == 1_200.0
        assert page.toggle(key="simple_w_hsa_family").value is True

    def test_a_typed_ira_above_the_limit_says_over_not_at_the_limit(self, page):
        page.session_state["simple_inputs"] = {"ira_contrib_annual": 9_000}
        page.run()
        assert "simple_max_ira_contrib_annual" not in self._button_keys(page)
        assert "Over the limit" in self._captions(page)

    def test_max_out_tooltips_say_it_is_this_years_limit(self, page):
        page.run()
        assert "this year's limit" in _by_key(page.button, "simple_max_ira_contrib_annual").help

    def test_max_out_401k_sets_the_percent_and_then_steps_aside(self, page):
        page.run()
        _by_key(page.button, "simple_max_retirement_contrib_pct").click().run()
        assert not page.exception, page.exception
        assert page.session_state["simple_inputs"]["retirement_contrib_pct"] == 37.7   # $65,000 salary
        assert "simple_max_retirement_contrib_pct" not in self._button_keys(page)
        assert "At the limit" in self._captions(page)
        step = next(x for x in sf.priority_ladder(page.session_state["simple_inputs"]) if x.key == "max_401k")
        assert step.status == "done"

    def test_no_401k_button_without_a_salary(self, page):
        page.session_state["simple_inputs"] = {"gross_salary_annual": 0}
        page.run()
        assert "simple_max_retirement_contrib_pct" not in self._button_keys(page)

    def test_max_out_hsa_only_when_eligible(self, page):
        page.run()
        assert "simple_max_hsa_contrib_annual" not in self._button_keys(page)
        page.toggle(key="simple_w_hsa_eligible").set_value(True).run()
        _by_key(page.button, "simple_max_hsa_contrib_annual").click().run()
        assert page.session_state["simple_inputs"]["hsa_contrib_annual"] == 4_400.0
        page.toggle(key="simple_w_hsa_family").set_value(True).run()
        _by_key(page.button, "simple_max_hsa_contrib_annual").click().run()      # family limit is higher
        assert page.session_state["simple_inputs"]["hsa_contrib_annual"] == 8_750.0
        assert "simple_max_hsa_contrib_annual" not in self._button_keys(page)

    def test_max_out_ira_and_its_tooltip_names_the_backdoor(self, page):
        page.run()
        btn = _by_key(page.button, "simple_max_ira_contrib_annual")
        assert "$7,500" in btn.help and "backdoor" not in btn.help
        btn.click().run()
        assert page.session_state["simple_inputs"]["ira_contrib_annual"] == 7_500.0
        assert "simple_max_ira_contrib_annual" not in self._button_keys(page)
        for pay in (160_500, 200_000):
            page.session_state["simple_inputs"] = {"gross_salary_annual": pay,
                                                   "retirement_contrib_pct": 0, "ira_contrib_annual": 0}
            page.run()
            assert "backdoor Roth" in _by_key(page.button, "simple_max_ira_contrib_annual").help



class TestHiddenInputsKeepTheirValues:
    """Streamlit forgets a widget's value on a run that doesn't draw it, and a number
    input then reads back as its default (0). In a real browser that wiped the
    partner's pay and the HSA amount after a version flip or a toggle off and on.
    AppTest keeps the value, so these use a plain dict for the session and play the
    forgetting by hand."""

    @staticmethod
    def _sm():
        from components import simple_mode
        return simple_mode

    def _page_away(self, sm):
        """What the session holds after the planner was shown: the widgets read as
        their defaults and the toggles are gone."""
        ss = {sm._W + "partner_salary_annual": 0.0, sm._W + "hsa_contrib_annual": 0.0,
              sm._W + "hsa_family": False, sm._DRAWN_KEY: {"partner_salary_annual"}}
        return ss

    def test_back_from_the_planner_reseeds_the_hidden_inputs(self):
        sm = self._sm()
        stored = sf.normalize_inputs({"married": True, "partner_salary_annual": 41_000,
                                      "hsa_eligible": True, "hsa_family": True,
                                      "hsa_contrib_annual": 1_200})
        ss = self._page_away(sm)
        sm._seed(ss, stored, force=False)
        assert ss[sm._W + "partner_salary_annual"] == 41_000
        assert ss[sm._W + "hsa_contrib_annual"] == 1_200
        assert ss[sm._W + "hsa_family"] is True

    def test_toggle_back_on_reseeds_an_input_hidden_on_the_last_run(self):
        sm = self._sm()
        stored = sf.normalize_inputs({"partner_salary_annual": 41_000})
        ss = {sm._W + f: stored[f] for f in sm._SCALARS}
        ss[sm._W + "partner_salary_annual"] = 0.0          # forgotten while hidden
        ss[sm._DRAWN_KEY] = set()
        ss[sm._W + "married"] = True                        # the toggle was just switched on
        sm._seed(ss, stored, force=False)
        assert ss[sm._W + "partner_salary_annual"] == 41_000

    def test_a_live_input_is_not_overwritten_by_the_stored_value(self):
        sm = self._sm()
        stored = sf.normalize_inputs({"married": True, "partner_salary_annual": 41_000})
        ss = {sm._W + f: stored[f] for f in sm._SCALARS}
        ss[sm._W + "partner_salary_annual"] = 52_000        # typed, or set by a button
        ss[sm._DRAWN_KEY] = {"partner_salary_annual"}
        sm._seed(ss, stored, force=False)
        assert ss[sm._W + "partner_salary_annual"] == 52_000

    def test_collect_ignores_a_hidden_widget_value(self):
        sm = self._sm()
        base = sf.normalize_inputs({"married": True, "partner_salary_annual": 41_000})
        ss = {sm._W + f: base[f] for f in sm._SCALARS}
        ss[sm._W + "married"] = False
        ss[sm._W + "partner_salary_annual"] = 0.0           # reads back as the default
        got = sm._collect(ss, base)
        assert got["partner_salary_annual"] == 41_000 and got["married"] is False


# ---------------------------------------------------------------------------
# QA round: age catch-ups, thousands echo, save/load, payoff wording
# ---------------------------------------------------------------------------
class TestAgeCatchUps:
    D = date(2026, 6, 1)

    def test_no_age_means_no_catch_up(self):
        assert sf.contribution_limits(False, self.D) == sf.contribution_limits(False, self.D, 0)
        assert sf.contribution_limits(False, self.D, 49) == {"401k": 24_500, "ira": 7_500, "hsa": 4_400}

    def test_catch_ups_start_at_50_and_55(self):
        assert sf.contribution_limits(False, self.D, 50) == {"401k": 32_500, "ira": 8_600, "hsa": 4_400}
        assert sf.contribution_limits(False, self.D, 55)["hsa"] == 5_400
        assert sf.contribution_limits(True, self.D, 55)["hsa"] == 9_750

    def test_super_catch_up_for_60_to_63_only(self):
        assert sf.contribution_limits(False, self.D, 59)["401k"] == 32_500
        assert [sf.contribution_limits(False, self.D, a)["401k"] for a in (60, 63)] == [35_750, 35_750]
        assert sf.contribution_limits(False, self.D, 64)["401k"] == 32_500

    def test_years_before_the_table_use_the_engine_catch_ups(self):
        base = sf.contribution_limits(False, date(2024, 1, 1))
        old = sf.contribution_limits(False, date(2024, 1, 1), 52)
        assert old["401k"] == base["401k"] + cfg.get_inflation_adjusted_limit("401k_catchup", 0)

    def test_age_moves_the_ladder_and_max_out(self):
        young = _steps(_inputs(gross_salary_annual=300_000, retirement_contrib_pct=100 * 24_500 / 300_000))
        older = _steps(_inputs(gross_salary_annual=300_000, retirement_contrib_pct=100 * 24_500 / 300_000, age=52))
        assert young["max_401k"].status == "done" and older["max_401k"].status != "done"
        assert older["max_401k"].target == 32_500
        assert sf.max_401k_pct(100_000, TODAY, 52) == 32.5

    def test_age_is_repaired_like_every_other_input(self):
        assert sf.normalize_inputs({"age": "52"})["age"] == 52
        assert sf.normalize_inputs({"age": -4})["age"] == 0
        assert sf.normalize_inputs({"age": 900})["age"] == 100
        assert sf.normalize_inputs({"age": "x"})["age"] == 0


class TestCheckupPage:
    def test_age_input_changes_the_limits_shown(self, page):
        page.run()
        _by_key(page.number_input, "simple_w_age").set_value(52).run()
        assert not page.exception, page.exception
        assert page.session_state["simple_inputs"]["age"] == 52
        assert any("32,500" in (b.help or "") for b in page.button if b.key == "simple_max_retirement_contrib_pct")

    def test_large_money_gets_a_separator_echo(self, page):
        page.session_state["simple_inputs"] = {"gross_salary_annual": 320_000, "cash_savings": 800}
        page.run()
        captions = [c.value for c in page.caption]
        assert "\\$320,000" in captions and "\\$800" not in captions

    def test_wont_pay_off_does_not_print_a_compounded_balance(self, page):
        page.session_state["simple_inputs"] = {"debts": [_debt("Huge", 50_000, 24.0, 100)],
                                               "extra_debt_payment_monthly": 0}
        page.run()
        text = " ".join(m.value for m in page.markdown)
        assert "The balance keeps growing" in text and "still owe" not in text

    def test_a_name_with_markdown_and_dollars_is_escaped_in_the_warning(self, page):
        page.session_state["simple_inputs"] = {"debts": [_debt("Loan $5k or $9k", 10_000, 24.0, 100)],
                                               "extra_debt_payment_monthly": 0}
        page.run()
        assert any("\\$5k or \\$9k" in w.value for w in page.warning)


class TestCheckupSaveLoad:
    def test_round_trip(self):
        from utils.profile_io import serialize_checkup, deserialize_checkup
        i = sf.normalize_inputs({**sf.DEFAULT_INPUTS, "gross_salary_annual": 91_000, "age": 53,
                                 "debts": [_debt("Card", 1_200, 21.0, 40)]})
        assert sf.normalize_inputs(deserialize_checkup(serialize_checkup(i))) == i

    def test_other_files_are_refused_with_a_reason(self):
        from utils.profile_io import deserialize_checkup, serialize_overrides
        for bad in ("not json", "[1, 2]", serialize_overrides({"YOUR_AGE": 30}), b"\xff\xfe"):
            with pytest.raises(ValueError):
                deserialize_checkup(bad)

    def test_page_offers_a_download(self, page):
        page.run()
        assert not page.exception, page.exception
        assert any(b.label == "Download my answers" for b in page.get("download_button"))

    def test_loading_replaces_every_answer(self, page):
        """The Load button's callback (AppTest can't upload a file): it normalizes the
        answers and forces every widget to reseed from them."""
        from components import simple_mode
        ss = {}
        simple_mode._load_checkup(ss, {"gross_salary_annual": "91,000", "age": 53, "junk": 1})
        assert ss["simple_inputs"]["gross_salary_annual"] == 91_000.0 and ss["simple_inputs"]["age"] == 53
        assert "junk" not in ss["simple_inputs"] and ss["_simple_inputs_synced"] is None
        page.session_state["simple_inputs"] = ss["simple_inputs"]
        page.run()
        assert not page.exception, page.exception
        assert _by_key(page.number_input, "simple_w_age").value == 53
