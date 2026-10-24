"""Function-level coverage for pure ``retirement_sim.config`` helpers that had
NO direct test (function-gap sweep, 2026-08-22).

Everything here is a pure function of module state, so each test pins the
happy path plus the boundaries (0 / negative / exactly-at-threshold / beyond the
table). ``monkeypatch.setattr`` is used for every config mutation so no test
leaks module state into the rest of the suite.

Gaps closed: get_inflation_adjusted_limit, get_ira_limit, get_hsa_limit,
get_401k_limit (age boundary), normalize_filing_status, calculate_529_contribution,
calculate_ltc_cost, calculate_return_based_spending_adjustment,
lifecycle_spend_delta_annual, get_historical_returns_for_sequence,
single_life_expectancy, calculate_your_total_savings,
calculate_partner_total_savings, and the SEPP 72(t) round-trip.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from retirement_sim import config as cfg


# ---------------------------------------------------------------------------
# Contribution limits
# ---------------------------------------------------------------------------
class TestContributionLimits:
    def test_unknown_limit_type_returns_zero(self):
        assert cfg.get_inflation_adjusted_limit("not_a_limit", 0) == 0
        assert cfg.get_inflation_adjusted_limit("", 5) == 0

    @pytest.mark.parametrize("limit_type", ["401k", "401k_total", "401k_catchup",
                                            "ira", "ira_catchup", "hsa_catchup"])
    def test_zero_inflation_is_identity_for_500_multiples(self, limit_type):
        """CONTRIBUTION_LIMIT_INFLATION_RATE is 0 (all-real frame), so the
        base-year limit must come back unchanged."""
        assert cfg.CONTRIBUTION_LIMIT_INFLATION_RATE == 0.0
        assert (cfg.get_inflation_adjusted_limit(limit_type, 0)
                == cfg.CONTRIBUTION_LIMITS_2024[limit_type])

    # FIXED 2026-08-22: was xfail(strict) while the defect stood; the fix is in.
    @pytest.mark.parametrize("limit_type", ["hsa_family", "hsa_individual"])
    def test_zero_inflation_is_identity_for_hsa(self, limit_type):
        assert (cfg.get_inflation_adjusted_limit(limit_type, 0)
                == cfg.CONTRIBUTION_LIMITS_2024[limit_type])

    def test_limits_are_flat_across_years_in_real_terms(self):
        for year in (2024, 2030, 2060):
            assert cfg.get_401k_limit(40, year) == cfg.get_401k_limit(40, 2024)
            assert cfg.get_ira_limit(40, year) == cfg.get_ira_limit(40, 2024)

    def test_401k_catchup_boundary_at_50(self):
        assert cfg.get_401k_limit(49, 2024) == cfg.CONTRIBUTION_LIMITS_2024["401k"]
        assert (cfg.get_401k_limit(50, 2024)
                == cfg.CONTRIBUTION_LIMITS_2024["401k"]
                + cfg.CONTRIBUTION_LIMITS_2024["401k_catchup"])

    def test_ira_catchup_boundary_at_50(self):
        assert cfg.get_ira_limit(49, 2024) == cfg.CONTRIBUTION_LIMITS_2024["ira"]
        assert (cfg.get_ira_limit(50, 2024)
                == cfg.CONTRIBUTION_LIMITS_2024["ira"]
                + cfg.CONTRIBUTION_LIMITS_2024["ira_catchup"])

    def test_401k_total_limit_exceeds_employee_limit(self):
        assert cfg.get_401k_total_limit(40, 2024) > cfg.get_401k_limit(40, 2024)
        assert (cfg.get_401k_total_limit(50, 2024) - cfg.get_401k_total_limit(49, 2024)
                == cfg.CONTRIBUTION_LIMITS_2024["401k_catchup"])

    def test_hsa_family_exceeds_individual_and_catchup_at_55(self):
        fam = cfg.get_hsa_limit(40, 2024, is_family=True)
        ind = cfg.get_hsa_limit(40, 2024, is_family=False)
        assert fam > ind > 0
        # 55+ catch-up (not 50) for HSA.
        assert cfg.get_hsa_limit(54, 2024) == fam
        assert (cfg.get_hsa_limit(55, 2024) - fam
                == cfg.CONTRIBUTION_LIMITS_2024["hsa_catchup"])

    def test_negative_years_from_2024_does_not_crash(self):
        assert cfg.get_inflation_adjusted_limit("401k", -5) > 0


# ---------------------------------------------------------------------------
# Filing status / brackets
# ---------------------------------------------------------------------------
class TestNormalizeFilingStatus:
    @pytest.mark.parametrize("raw,expected", [
        ("MFJ", "MFJ"), ("mfj", "MFJ"), ("Married filing jointly", "MFJ"),
        ("married", "MFJ"), ("m", "MFJ"), ("  MARRIED FILING JOINTLY  ", "MFJ"),
        ("S", "S"), ("single", "S"), ("Single", "S"),
        ("HOH", "HOH"), ("head of household", "HOH"), ("Head-of-household", "HOH"),
    ])
    def test_known_forms(self, raw, expected):
        assert cfg.normalize_filing_status(raw) == expected

    def test_none_uses_module_default(self):
        assert (cfg.normalize_filing_status(None)
                == cfg.normalize_filing_status(cfg.FILING_STATUS))

    def test_none_follows_overridden_default(self, monkeypatch):
        monkeypatch.setattr(cfg, "FILING_STATUS", "Single")
        assert cfg.normalize_filing_status() == "S"

    @pytest.mark.parametrize("raw", ["", "???", "zzz", 0, 12.5])
    def test_unknown_falls_back_to_mfj(self, raw):
        assert cfg.normalize_filing_status(raw) == "MFJ"

    def test_idempotent(self):
        for raw in ("Married filing jointly", "Single", "Head of household"):
            once = cfg.normalize_filing_status(raw)
            assert cfg.normalize_filing_status(once) == once

    def test_brackets_track_status_and_are_well_formed(self):
        for status in ("MFJ", "S", "HOH"):
            brackets = cfg.get_federal_brackets(status)
            caps = [c for c, _ in brackets]
            rates = [r for _, r in brackets]
            assert caps == sorted(caps), status
            assert caps[-1] == float("inf"), status
            assert rates == sorted(rates), status
        # MFJ thresholds are the widest at every step.
        mfj = cfg.get_federal_brackets("MFJ")
        single = cfg.get_federal_brackets("S")
        assert all(m >= s for (m, _), (s, _) in zip(mfj[:-1], single[:-1]))


class TestStandardDeduction:
    def test_age_65_boundary_mfj(self, monkeypatch):
        monkeypatch.setattr(cfg, "FILING_STATUS", "MFJ")
        base = cfg.get_standard_deduction(64, 64)
        assert base == cfg.STANDARD_DEDUCTION_MFJ_2024
        one_old = cfg.get_standard_deduction(65, 64)
        both_old = cfg.get_standard_deduction(65, 65)
        assert one_old - base == cfg.ADDITIONAL_STD_DEDUCTION_65_PLUS
        assert both_old - base == 2 * cfg.ADDITIONAL_STD_DEDUCTION_65_PLUS

    def test_single_ignores_partner_age(self, monkeypatch):
        monkeypatch.setattr(cfg, "FILING_STATUS", "Single")
        assert (cfg.get_standard_deduction(40, 70)
                == cfg.get_standard_deduction(40, 40)
                == cfg.STANDARD_DEDUCTION_SINGLE_2024)
        assert (cfg.get_standard_deduction(65, 0) - cfg.STANDARD_DEDUCTION_SINGLE_2024
                == cfg.ADDITIONAL_STD_DEDUCTION_65_PLUS_SINGLE)


# ---------------------------------------------------------------------------
# 529 contributions
# ---------------------------------------------------------------------------
class TestFiveTwoNineContribution:
    @pytest.fixture(autouse=True)
    def _per_child(self, monkeypatch):
        monkeypatch.setattr(cfg, "YOUR_AGE", 30)
        monkeypatch.setattr(cfg, "YEARS_UNTIL_FIRST_CHILD", 2)
        monkeypatch.setattr(cfg, "YEARS_BETWEEN_CHILDREN", 3)
        monkeypatch.setattr(cfg, "SAVINGS_529_PER_CHILD_ANNUAL", 5_000.0)

    def test_zero_before_first_birth(self):
        assert cfg.calculate_529_contribution(31) == 0

    def test_starts_the_year_the_child_is_born(self):
        # First child born at your_age 32; second at 35.
        assert cfg.calculate_529_contribution(32) == 5_000.0

    def test_two_children_overlap_doubles(self):
        assert cfg.calculate_529_contribution(35) == 10_000.0

    def test_stops_at_child_18_exclusive(self):
        # First child turns 18 when you are 50 -> first child stops; second
        # (born when you were 35) is 15, still funded.
        assert cfg.calculate_529_contribution(49) == 10_000.0
        assert cfg.calculate_529_contribution(50) == 5_000.0
        assert cfg.calculate_529_contribution(53) == 0

    def test_zero_per_child_amount_yields_zero(self, monkeypatch):
        monkeypatch.setattr(cfg, "SAVINGS_529_PER_CHILD_ANNUAL", 0.0)
        assert cfg.calculate_529_contribution(35) == 0

    def test_child_free_household_never_contributes(self, monkeypatch):
        monkeypatch.setattr(cfg, "YEARS_UNTIL_FIRST_CHILD", 999)
        assert all(cfg.calculate_529_contribution(a) == 0 for a in range(25, 95))


# ---------------------------------------------------------------------------
# Long-term care
# ---------------------------------------------------------------------------
class TestLtcCost:
    def test_zero_when_draw_says_no(self):
        assert cfg.calculate_ltc_cost(90, 1.0, needs_ltc=False) == 0.0

    def test_zero_when_disabled(self, monkeypatch):
        monkeypatch.setattr(cfg, "LTC_ENABLED", False)
        assert cfg.calculate_ltc_cost(90, 1.0, needs_ltc=True) == 0.0

    def test_start_age_boundary(self, monkeypatch):
        monkeypatch.setattr(cfg, "LTC_ENABLED", True)
        monkeypatch.setattr(cfg, "LTC_START_AGE", 85)
        assert cfg.calculate_ltc_cost(84, 1.0, True) == 0.0
        assert cfg.calculate_ltc_cost(85, 1.0, True) == pytest.approx(cfg.LTC_ANNUAL_COST)

    def test_age_intensity_steps(self, monkeypatch):
        monkeypatch.setattr(cfg, "LTC_ENABLED", True)
        monkeypatch.setattr(cfg, "LTC_START_AGE", 83)
        base = cfg.LTC_ANNUAL_COST
        assert cfg.calculate_ltc_cost(86, 1.0, True) == pytest.approx(base)
        assert cfg.calculate_ltc_cost(87, 1.0, True) == pytest.approx(base * 1.15)
        assert cfg.calculate_ltc_cost(89, 1.0, True) == pytest.approx(base * 1.15)
        assert cfg.calculate_ltc_cost(90, 1.0, True) == pytest.approx(base * 1.25)

    def test_scales_linearly_with_inflation_factor(self, monkeypatch):
        monkeypatch.setattr(cfg, "LTC_ENABLED", True)
        monkeypatch.setattr(cfg, "LTC_START_AGE", 83)
        one = cfg.calculate_ltc_cost(88, 1.0, True)
        two = cfg.calculate_ltc_cost(88, 2.0, True)
        assert two == pytest.approx(2 * one)
        assert cfg.calculate_ltc_cost(88, 0.0, True) == 0.0


# ---------------------------------------------------------------------------
# Return-based spending
# ---------------------------------------------------------------------------
class TestReturnBasedSpendingAdjustment:
    @pytest.fixture(autouse=True)
    def _enabled(self, monkeypatch):
        monkeypatch.setattr(cfg, "RETURN_BASED_SPENDING_ENABLED", True)
        monkeypatch.setattr(cfg, "RETURN_BASED_SPENDING_RULES", {
            "excellent_return_threshold": 0.15, "excellent_spending_boost": 0.10,
            "good_return_threshold": 0.08, "good_spending_boost": 0.05,
            "poor_return_threshold": 0.0, "poor_spending_cut": 0.10,
            "bad_return_threshold": -0.10, "bad_spending_cut": 0.20,
        })

    def test_disabled_is_neutral(self, monkeypatch):
        monkeypatch.setattr(cfg, "RETURN_BASED_SPENDING_ENABLED", False)
        for r in (-0.5, 0.0, 0.5):
            assert cfg.calculate_return_based_spending_adjustment(r) == 1.0

    @pytest.mark.parametrize("annual_return,expected", [
        (0.40, 1.10),    # excellent
        (0.15, 1.10),    # exactly at excellent threshold -> excellent
        (0.1499, 1.05),  # just below -> good
        (0.08, 1.05),    # exactly at good threshold
        (0.0799, 1.0),   # normal band
        (0.0, 1.0),      # exactly at poor threshold -> NOT a cut (strict <)
        (-0.0001, 0.90),  # poor
        (-0.10, 0.90),   # exactly at bad threshold -> still only "poor"
        (-0.1001, 0.80),  # bad
        (-1.0, 0.80),
    ])
    def test_thresholds(self, annual_return, expected):
        assert cfg.calculate_return_based_spending_adjustment(annual_return) == pytest.approx(expected)

    def test_monotone_non_decreasing_in_return(self):
        rs = [-0.5, -0.2, -0.05, 0.0, 0.05, 0.09, 0.2]
        vals = [cfg.calculate_return_based_spending_adjustment(r) for r in rs]
        assert vals == sorted(vals)


# ---------------------------------------------------------------------------
# Lifecycle spending delta
# ---------------------------------------------------------------------------
class TestLifecycleSpendDelta:
    def test_empty_preset_is_zero(self, monkeypatch):
        monkeypatch.setattr(cfg, "SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE", {})
        assert cfg.lifecycle_spend_delta_annual(70) == 0.0

    def test_delta_is_relative_to_todays_monthly_times_12(self, monkeypatch):
        monkeypatch.setattr(cfg, "SPEND_FOOD_MONTHLY", 1_000)
        monkeypatch.setattr(cfg, "SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE",
                            {"SPEND_FOOD_MONTHLY": {70: 0.8, 71: 1.0, 72: 1.25}})
        assert cfg.lifecycle_spend_delta_annual(70) == pytest.approx(-2_400.0)
        assert cfg.lifecycle_spend_delta_annual(71) == pytest.approx(0.0)
        assert cfg.lifecycle_spend_delta_annual(72) == pytest.approx(3_000.0)

    def test_missing_age_is_neutral(self, monkeypatch):
        monkeypatch.setattr(cfg, "SPEND_FOOD_MONTHLY", 1_000)
        monkeypatch.setattr(cfg, "SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE",
                            {"SPEND_FOOD_MONTHLY": {70: 0.5}})
        assert cfg.lifecycle_spend_delta_annual(99) == 0.0

    def test_unset_category_is_skipped_not_crashed(self, monkeypatch):
        monkeypatch.setattr(cfg, "SPEND_FOOD_MONTHLY", None)
        monkeypatch.setattr(cfg, "SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE",
                            {"SPEND_FOOD_MONTHLY": {70: 0.5},
                             "NOT_A_REAL_CATEGORY": {70: 0.5}})
        assert cfg.lifecycle_spend_delta_annual(70) == 0.0

    def test_scales_with_inflation_factor(self, monkeypatch):
        monkeypatch.setattr(cfg, "SPEND_DISCRETIONARY_MONTHLY", 500)
        monkeypatch.setattr(cfg, "SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE",
                            {"SPEND_DISCRETIONARY_MONTHLY": {80: 1.5}})
        one = cfg.lifecycle_spend_delta_annual(80, 1.0)
        assert one == pytest.approx(3_000.0)
        assert cfg.lifecycle_spend_delta_annual(80, 2.5) == pytest.approx(2.5 * one)

    def test_multiple_categories_sum(self, monkeypatch):
        monkeypatch.setattr(cfg, "SPEND_FOOD_MONTHLY", 100)
        monkeypatch.setattr(cfg, "SPEND_DISCRETIONARY_MONTHLY", 200)
        monkeypatch.setattr(cfg, "SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE", {
            "SPEND_FOOD_MONTHLY": {60: 2.0},
            "SPEND_DISCRETIONARY_MONTHLY": {60: 0.5},
        })
        # +100*12 and -100*12 cancel exactly.
        assert cfg.lifecycle_spend_delta_annual(60) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Historical sequences
# ---------------------------------------------------------------------------
class TestHistoricalSequences:
    def test_unknown_sequence_returns_empty_list(self):
        assert cfg.get_historical_returns_for_sequence("nope") == []
        assert cfg.get_historical_returns_for_sequence("") == []

    @pytest.mark.parametrize("name", sorted(cfg.SEQUENCE_TESTS))
    def test_known_sequences_length_matches_years(self, name):
        years = cfg.SEQUENCE_TESTS[name]["years"]
        returns = cfg.get_historical_returns_for_sequence(name)
        assert len(returns) == len(years)
        assert all(isinstance(r, (int, float)) for r in returns)
        assert all(-1.0 < r < 1.0 for r in returns)

    def test_missing_year_falls_back_to_seven_percent(self, monkeypatch):
        monkeypatch.setitem(cfg.SEQUENCE_TESTS, "_sweep_fake",
                            {"name": "fake", "years": [1800, 1801], "description": ""})
        assert cfg.get_historical_returns_for_sequence("_sweep_fake") == [0.07, 0.07]


# ---------------------------------------------------------------------------
# IRS single life table + 72(t) SEPP
# ---------------------------------------------------------------------------
class TestSingleLifeExpectancy:
    def test_anchor_points_exact(self):
        assert cfg.single_life_expectancy(50) == pytest.approx(36.2)
        assert cfg.single_life_expectancy(60) == pytest.approx(27.1)
        assert cfg.single_life_expectancy(90) == pytest.approx(5.7)

    def test_clamps_outside_the_table(self):
        assert cfg.single_life_expectancy(0) == cfg.single_life_expectancy(30)
        assert cfg.single_life_expectancy(-5) == cfg.single_life_expectancy(30)
        assert cfg.single_life_expectancy(120) == cfg.single_life_expectancy(90)

    def test_linear_interpolation_midpoint(self):
        # 55 -> 31.6, 57 -> 29.8; midpoint 56 -> 30.7
        assert cfg.single_life_expectancy(56) == pytest.approx(30.7)
        # 40 -> 45.7, 45 -> 41.0; 42 is 2/5 of the way
        assert cfg.single_life_expectancy(42) == pytest.approx(45.7 + 0.4 * (41.0 - 45.7))

    def test_strictly_decreasing_across_the_table(self):
        vals = [cfg.single_life_expectancy(a) for a in range(30, 91)]
        assert all(b < a for a, b in zip(vals, vals[1:]))

    def test_always_positive(self):
        assert all(cfg.single_life_expectancy(a) > 0 for a in range(0, 121))


class TestSepp72t:
    def test_zero_and_negative_balance(self):
        assert cfg.sepp_72t_annual_amount(0, 50) == 0.0
        assert cfg.sepp_72t_annual_amount(-100, 50) == 0.0
        assert cfg.sepp_72t_annual_amount(None, 50) == 0.0

    def test_zero_rate_is_straight_line_division(self):
        le = cfg.single_life_expectancy(50)
        assert cfg.sepp_72t_annual_amount(1_000_000, 50, rate=0.0) == pytest.approx(1_000_000 / le)

    def test_amortized_payment_exceeds_straight_line(self):
        amort = cfg.sepp_72t_annual_amount(1_000_000, 50, rate=0.05)
        straight = cfg.sepp_72t_annual_amount(1_000_000, 50, rate=0.0)
        assert amort > straight

    @pytest.mark.parametrize("age", [45, 50, 55, 59])
    @pytest.mark.parametrize("rate", [0.0, 0.02, 0.05, 0.12])
    def test_round_trip_balance_payment_balance(self, age, rate):
        balance = 750_000.0
        payment = cfg.sepp_72t_annual_amount(balance, age, rate=rate)
        assert cfg.sepp_72t_balance_for_payment(payment, age, rate=rate) == pytest.approx(balance)

    def test_balance_for_payment_edges(self):
        assert cfg.sepp_72t_balance_for_payment(0, 50) == 0.0
        assert cfg.sepp_72t_balance_for_payment(-1, 50) == 0.0
        assert cfg.sepp_72t_balance_for_payment(None, 50) == 0.0

    def test_older_age_gives_larger_payment_for_same_balance(self):
        assert (cfg.sepp_72t_annual_amount(500_000, 58)
                > cfg.sepp_72t_annual_amount(500_000, 45))

    def test_must_continue_no_schedule(self):
        assert cfg.sepp_72t_must_continue(50, None) is False

    def test_must_continue_five_year_and_595_rules(self, monkeypatch):
        monkeypatch.setattr(cfg, "SEPP_72T_MIN_YEARS", 5)
        # Started at 50: locked through 55 (5 years) AND on until 59.5.
        assert cfg.sepp_72t_must_continue(54.9, 50) is True
        assert cfg.sepp_72t_must_continue(55, 50) is True      # still < 59.5
        assert cfg.sepp_72t_must_continue(59.4, 50) is True
        assert cfg.sepp_72t_must_continue(59.5, 50) is False
        # Started at 58: the 5-year clock dominates past 59.5.
        assert cfg.sepp_72t_must_continue(60, 58) is True
        assert cfg.sepp_72t_must_continue(63, 58) is False


# ---------------------------------------------------------------------------
# Savings roll-ups
# ---------------------------------------------------------------------------
class TestTotalSavingsHelpers:
    def test_your_total_savings_inside_the_table(self, monkeypatch):
        monkeypatch.setattr(cfg, "YOUR_COMPENSATION_BY_AGE", {
            40: {"base": 100_000, "bonus": 0, "rsu_gross": 0,
                 "total_comp": 100_000, "after_tax": 70_000, "saved": 10_000},
        })
        monkeypatch.setattr(cfg, "YOUR_401K_CONTRIBUTION", 23_000)
        monkeypatch.setattr(cfg, "YOUR_401K_MATCH_PCT", 0.05)
        monkeypatch.setattr(cfg, "YOUR_HSA_TOTAL", 8_300)
        assert cfg.calculate_your_total_savings(40) == pytest.approx(
            10_000 + 23_000 + 100_000 * 0.05 + 8_300)

    def test_your_total_savings_projects_beyond_the_table(self, monkeypatch):
        monkeypatch.setattr(cfg, "YOUR_COMPENSATION_BY_AGE", {
            40: {"base": 100_000, "bonus": 0, "rsu_gross": 0,
                 "total_comp": 100_000, "after_tax": 70_000, "saved": 10_000},
        })
        monkeypatch.setattr(cfg, "YOUR_401K_CONTRIBUTION", 0)
        monkeypatch.setattr(cfg, "YOUR_401K_MATCH_PCT", 0.0)
        monkeypatch.setattr(cfg, "YOUR_HSA_TOTAL", 0)
        monkeypatch.setattr(cfg, "YOUR_SALARY_GROWTH_RATE", 0.03)
        assert cfg.calculate_your_total_savings(43) == pytest.approx(10_000 * 1.03 ** 3)
        # Ages BELOW the table are also extrapolated (negative exponent).
        assert cfg.calculate_your_total_savings(38) == pytest.approx(10_000 * 1.03 ** -2)

    def test_partner_total_savings_components(self, monkeypatch):
        monkeypatch.setattr(cfg, "PARTNER_401K_CONTRIBUTION", 5_000)
        monkeypatch.setattr(cfg, "PARTNER_ROTH_CONTRIBUTION", 6_000)
        monkeypatch.setattr(cfg, "PARTNER_ANNUAL_SPENDING", 20_000)
        salary = 100_000
        # Take-home from the real tax rules (the flat 20% partner rate is gone).
        after_tax = cfg.working_year_taxes(partner_wages=salary, partner_401k=5_000,
                                           status="S", partner=True)["partner"]["take_home"]
        expected = 5_000 + 6_000 + max(0, after_tax - 6_000 - 20_000)
        assert cfg.calculate_partner_total_savings(salary, 0, married=False) == pytest.approx(expected)

    def test_partner_roth_follows_income_not_marriage(self, monkeypatch):
        """Marriage no longer zeroes the partner's Roth; the phase-out does."""
        monkeypatch.setattr(cfg, "PARTNER_401K_CONTRIBUTION", 0)
        monkeypatch.setattr(cfg, "PARTNER_ROTH_CONTRIBUTION", 7_000)
        monkeypatch.setattr(cfg, "PARTNER_ANNUAL_SPENDING", 10_000_000)   # no brokerage
        assert cfg.calculate_partner_total_savings(80_000, 0, married=True) == pytest.approx(7_000)
        assert cfg.calculate_partner_total_savings(300_000, 0, married=True) == 0.0

    def test_partner_savings_floors_brokerage_at_zero(self, monkeypatch):
        monkeypatch.setattr(cfg, "PARTNER_401K_CONTRIBUTION", 1_000)
        monkeypatch.setattr(cfg, "PARTNER_ROTH_CONTRIBUTION", 0)
        monkeypatch.setattr(cfg, "PARTNER_ANNUAL_SPENDING", 60_000)
        salary = 20_000
        # Spending swamps after-tax income -> savings is just the 401k, never negative.
        assert cfg.calculate_partner_total_savings(salary, 0) == pytest.approx(1_000)

    def test_partner_savings_ignores_years_from_now(self, monkeypatch):
        """``years_from_now`` is accepted but unused — pin it so a future change
        that starts honouring it has to update this expectation deliberately."""
        monkeypatch.setattr(cfg, "PARTNER_ANNUAL_SPENDING", 10_000)
        a = cfg.calculate_partner_total_savings(80_000, 0)
        b = cfg.calculate_partner_total_savings(80_000, 25)
        assert a == b
