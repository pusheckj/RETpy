"""Assumption presets: the pure rules (ui/utils/assumption_presets.py).

``compute_preset(name, overrides, comp_customized)`` returns ``{config_key: (value, reason)}``
for "typical" or "conservative". It reads only facts about the household (ages, retirement
age, loans), never the current assumption values, so the same situation always gets the
same answer. These tests pin the rules, their direction (conservative is never more
hopeful than typical), their scope and that every value fits its widget.
"""
import os
import sys

import pytest

# Never load a personal profile: point the loader at a file that does not exist.
os.environ.setdefault("RETIREMENT_SIM_PROFILE", "/nonexistent/retirement-sim-test-profile.json")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components.profile_picker import PROFILES  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from utils import assumption_presets as ap  # noqa: E402
from utils import widget_sync as ws  # noqa: E402

DEMOS = ["Median US 25-year-old household", "Young professional (28, single)",
         "Mid-career couple (40, kids)", "Near retirement (55)"]
RETIREE_66 = {"YOUR_AGE": 66, "PARTNER_AGE": 0, "TARGET_RETIREMENT_AGE": 66,
              "MORTGAGE_BALANCE": 0, "MORTGAGE_MONTHLY": 0, "DEBTS": []}


def _demo(name):
    return dict(PROFILES[name])


def _all_cases():
    cases = [(n, _demo(n)) for n in DEMOS]
    cases.append(("Single retiree at 66", dict(RETIREE_66)))
    return cases


def val(plan, key):
    return plan[key][0]


def preset(name, overrides, comp=False):
    return ap.compute_preset(name, overrides, comp)


def facts(age=40, partner=0, retire=60, **extra):
    base = {"YOUR_AGE": age, "PARTNER_AGE": partner, "TARGET_RETIREMENT_AGE": retire,
            "MORTGAGE_BALANCE": 0, "MORTGAGE_MONTHLY": 0, "DEBTS": []}
    return {**base, **extra}


# ------------------------------------------------------------------ plan-until age

@pytest.mark.parametrize("age,couple,expected", [
    (30, False, 100), (49, False, 100), (50, False, 95), (84, False, 95), (85, False, 100),
    (49, True, 100), (50, True, 96), (59, True, 96), (60, True, 95), (99, False, 100),
    (99, True, 100),
])
def test_typical_plan_until_table(age, couple, expected):
    assert ap.plan_until_age("typical", age, couple) == expected


@pytest.mark.parametrize("age", [18, 30, 50, 70, 90, 99])
@pytest.mark.parametrize("couple", [False, True])
def test_conservative_plan_until_is_100_and_bounds_hold(age, couple):
    assert ap.plan_until_age("conservative", age, couple) == 100
    for name in ("typical", "conservative"):
        v = ap.plan_until_age(name, age, couple)
        assert max(75, min(100, age + 1)) <= v <= 100


# ------------------------------------------------------------------ timeline and returns

def test_situation_numbers_for_a_couple():
    s = ap.situation(facts(40, 38, 55), "typical")
    assert (s["A"], s["P"], s["R"]) == (40, 38, 55)
    assert s["E"] == 102 and s["H"] == 47 and s["YL"] == 62 and s["Y"] == 15


def test_situation_for_someone_already_retired():
    s = ap.situation(RETIREE_66, "typical")
    assert s["Y"] == 0 and s["E"] == 95 and s["H"] == 29 and s["YL"] == 29


@pytest.mark.parametrize("years_left,typical,conservative", [
    (35, "forward", "pessimistic"), (36, "conservative", "forward"),
    (10, "forward", "pessimistic"), (75, "conservative", "forward"),
])
def test_return_scenario_threshold(years_left, typical, conservative):
    assert ap.return_scenario("typical", years_left) == typical
    assert ap.return_scenario("conservative", years_left) == conservative


def test_historical_is_never_chosen():
    for yl in range(1, 90):
        for name in ("typical", "conservative"):
            assert ap.return_scenario(name, yl) != "historical"


# ------------------------------------------------------------------ glide path

@pytest.mark.parametrize("h,expected", [
    (20, ("down", 0.50, 0.40, 10)), (30, ("down", 0.50, 0.40, 10)),
    (31, ("tent", 0.50, 0.60, 10)), (40, ("tent", 0.50, 0.60, 10)),
    (41, ("tent", 0.60, 0.70, 10)), (47, ("tent", 0.60, 0.70, 10)),
])
def test_typical_glide_bands(h, expected):
    assert ap.glide_band("typical", h) == expected


@pytest.mark.parametrize("h,expected", [
    (20, ("tent", 0.40, 0.60, 10)), (30, ("tent", 0.40, 0.60, 10)),
    (31, ("tent", 0.40, 0.60, 15)), (40, ("tent", 0.40, 0.60, 15)),
    (41, ("tent", 0.50, 0.70, 15)), (60, ("tent", 0.50, 0.70, 15)),
])
def test_conservative_glide_bands(h, expected):
    assert ap.glide_band("conservative", h) == expected


@pytest.mark.parametrize("y,expected", [
    (1, 50), (2, 50), (3, 50), (4, 55), (5, 55), (10, 55), (15, 60), (20, 65), (25, 70),
    (30, 75), (35, 75), (40, 80),
])
def test_working_stock_mix(y, expected):
    assert ap.working_stock_pct(y, 50) == expected


def test_working_mix_when_already_retired_is_the_start_percent():
    assert ap.working_stock_pct(0, 50) == 50
    assert ap.working_stock_pct(0, 60) == 60


def test_working_mix_never_falls_with_more_years_and_never_below_start():
    for start in (40, 50, 60):
        prev = 0
        for y in range(0, 60):
            v = ap.working_stock_pct(y, start)
            assert v >= prev and v >= start and v % 5 == 0
            prev = v


def test_glide_is_always_on():
    for _, ov in _all_cases():
        for name in ("typical", "conservative"):
            assert val(preset(name, ov), "GLIDE_PATH_ENABLED") is True


# ------------------------------------------------------------------ social security

def test_typical_ss_share_is_78_percent_always():
    for _, ov in _all_cases():
        assert val(preset("typical", ov), "SS_PAYABLE_FRACTION") == 0.78


@pytest.mark.parametrize("age,end,expected", [(25, 100, 0.67), (40, 102, 0.70), (55, 102, 0.73),
                                              (65, 100, 0.75)])
def test_conservative_ss_share_examples(age, end, expected):
    assert ap.ss_payable("conservative", age, 67, end) == pytest.approx(expected, abs=0.011)


def test_conservative_ss_share_is_capped_and_never_rises_for_the_young():
    prev = 0.0
    for age in range(18, 90, 3):
        v = ap.ss_payable("conservative", age, 67, 100)
        assert 0.5 <= v <= 0.75
        assert v >= prev - 1e-9      # an older person (nearer 2033) gets the higher share
        prev = v


# ------------------------------------------------------------------ care, inflation, success

def test_ltc_probability_is_on_the_step_and_in_range():
    for _, ov in _all_cases():
        for name in ("typical", "conservative"):
            p = val(preset(name, ov), "LTC_PROBABILITY")
            assert 0.05 <= p <= 1.0
            assert abs(p * 100 / 5 - round(p * 100 / 5)) < 1e-9


@pytest.mark.parametrize("end,couple,typical,conservative", [
    (95, False, 0.10, 0.20), (100, False, 0.05, 0.15),
])
def test_ltc_probability_examples(end, couple, typical, conservative):
    assert ap.ltc_probability("typical", end, couple) == pytest.approx(typical)
    assert ap.ltc_probability("conservative", end, couple) == pytest.approx(conservative)


@pytest.mark.parametrize("end", [95, 98, 100, 102])
def test_ltc_expected_care_years_match_the_research_within_one_step(end):
    years = end - 83 + 1
    for name, k in (("typical", 1.3), ("conservative", 2.6)):
        for couple, n in ((False, 1), (True, 2)):
            p = ap.ltc_probability(name, end, couple)
            assert abs(p * years - k * n) <= 0.05 * years + 1e-9


@pytest.mark.parametrize("end", [95, 100, 102])
def test_ltc_ordering(end):
    for couple in (False, True):
        assert ap.ltc_probability("conservative", end, couple) >= ap.ltc_probability("typical", end, couple)
    assert ap.ltc_probability("typical", end, True) >= ap.ltc_probability("typical", end, False)
    assert ap.ltc_probability("conservative", end, True) >= ap.ltc_probability("conservative", end, False)
    assert ap.LTC_COST["conservative"] > ap.LTC_COST["typical"]


@pytest.mark.parametrize("extra,loan", [
    ({}, False), ({"MORTGAGE_MONTHLY": 1500}, True), ({"MORTGAGE_BALANCE": 100_000}, True),
    ({"DEBTS": [{"name": "Card", "balance": 1000}]}, True), ({"DEBTS": []}, False),
    ({"MORTGAGE_MONTHLY": 0, "MORTGAGE_BALANCE": 0}, False),
])
def test_inflation_rule(extra, loan):
    ov = facts(40, 0, 60, **extra)
    assert val(preset("typical", ov), "EXPECTED_INFLATION") == 0.025
    assert val(preset("conservative", ov), "EXPECTED_INFLATION") == (0.025 if loan else 0.030)


def test_success_target_by_horizon():
    # H = E - max(R, A): a single who retires at 65 and plans to 95 has H = 30
    short = facts(65, 0, 65)
    assert val(preset("typical", short), "TARGET_SUCCESS_RATE") == 0.85
    long_ = facts(25, 0, 50)           # H = 50
    assert val(preset("typical", long_), "TARGET_SUCCESS_RATE") == 0.90
    assert val(preset("conservative", long_), "TARGET_SUCCESS_RATE") == 0.95
    assert val(preset("conservative", short), "TARGET_SUCCESS_RATE") == 0.90


def test_constants():
    ov = facts(40, 38, 55)
    t, c = preset("typical", ov), preset("conservative", ov)
    assert val(t, "INVESTMENT_FEE_RATE") == 0.0010 and val(c, "INVESTMENT_FEE_RATE") == 0.0030
    assert val(t, "DYNAMIC_SPENDING_ENABLED") is True and val(c, "DYNAMIC_SPENDING_ENABLED") is True
    assert val(t, "RETURN_BASED_SPENDING_ENABLED") is True
    assert val(c, "RETURN_BASED_SPENDING_ENABLED") is False
    assert val(t, "LATE_RETIREMENT_LEISURE_DECREASE") == 0.15
    assert val(c, "LATE_RETIREMENT_LEISURE_DECREASE") == 0.0
    assert val(t, "LATE_RETIREMENT_START_AGE") == 75 == val(c, "LATE_RETIREMENT_START_AGE")
    for p in (t, c):
        assert val(p, "ACA_ENABLED") is True and val(p, "LTC_ENABLED") is True
        assert val(p, "LTC_START_AGE") == 83
    assert val(t, "LTC_ANNUAL_COST") == 115_000 and val(c, "LTC_ANNUAL_COST") == 130_000


# ------------------------------------------------------------------ salary growth, early access

def test_typical_salary_growth_by_own_age():
    for age, expected in ((30, 0.015), (34, 0.015), (35, 0.010), (44, 0.010), (45, 0.005),
                          (54, 0.005), (55, 0.0), (70, 0.0)):
        assert val(preset("typical", facts(age, 0, 60)), "YOUR_SALARY_GROWTH_RATE") == expected


def test_conservative_salary_growth_by_own_age():
    for age, expected in ((30, 0.005), (44, 0.005), (45, 0.0), (60, 0.0)):
        assert val(preset("conservative", facts(age, 0, 70)), "YOUR_SALARY_GROWTH_RATE") == expected


def test_partner_growth_uses_the_partners_own_age():
    p = preset("typical", facts(55, 34, 60))
    assert val(p, "YOUR_SALARY_GROWTH_RATE") == 0.0
    assert val(p, "PARTNER_SALARY_GROWTH_RATE") == 0.015


@pytest.mark.parametrize("name", ["typical", "conservative"])
def test_hand_edited_pay_table_keeps_salary_growth(name):
    p = preset(name, facts(40, 38, 55), comp=True)
    assert "YOUR_SALARY_GROWTH_RATE" not in p and "PARTNER_SALARY_GROWTH_RATE" not in p


@pytest.mark.parametrize("retire,ladder,rule55_typ", [
    (50, True, False), (54, True, False), (55, True, True), (59, True, True),
    (60, False, False), (65, False, False),
])
def test_early_access(retire, ladder, rule55_typ):
    ov = facts(40, 0, retire)
    t, c = preset("typical", ov), preset("conservative", ov)
    assert val(t, "ROTH_LADDER_ENABLED") is ladder and val(c, "ROTH_LADDER_ENABLED") is ladder
    assert val(t, "RULE_OF_55_ENABLED") is rule55_typ
    assert val(c, "RULE_OF_55_ENABLED") is False


# ------------------------------------------------------------------ short vs long, single vs couple

def test_short_and_long_retirements_get_different_settings():
    short = facts(66, 0, 66)
    long_ = facts(30, 0, 45)
    ts, tl = preset("typical", short), preset("typical", long_)
    assert val(ts, "GLIDE_PATH_SHAPE") == "down" and val(tl, "GLIDE_PATH_SHAPE") == "tent"
    assert val(ts, "ACTIVE_RETURN_SCENARIO") == "forward"
    assert val(tl, "ACTIVE_RETURN_SCENARIO") == "conservative"
    assert val(ts, "TARGET_SUCCESS_RATE") == 0.85 and val(tl, "TARGET_SUCCESS_RATE") == 0.90


def test_single_gets_no_partner_keys_and_couple_gets_both():
    s = preset("typical", facts(28, 0, 55))
    assert not [k for k in s if k.startswith("PARTNER_")]
    c = preset("typical", facts(40, 38, 55))
    assert "PARTNER_PLAN_UNTIL_AGE" in c and "PARTNER_SALARY_GROWTH_RATE" in c


def test_late_retirement_rule_does_not_depend_on_owning_a_home():
    base = facts(40, 38, 55)
    renter = preset("typical", base)
    owner = preset("typical", {**base, "HOME_VALUE": 600_000})
    assert {k: v[0] for k, v in renter.items()} == {k: v[0] for k, v in owner.items()}


# ------------------------------------------------------------------ worked examples

def test_worked_example_median_25_year_old():
    ov = _demo("Median US 25-year-old household")
    t, c = preset("typical", ov), preset("conservative", ov)
    assert (val(t, "PLAN_UNTIL_AGE"), val(t, "PARTNER_PLAN_UNTIL_AGE")) == (100, 100)
    assert val(t, "ACTIVE_RETURN_SCENARIO") == "conservative"
    assert val(t, "STOCK_ALLOCATION") == 0.75
    assert (val(t, "GLIDE_PATH_SHAPE"), val(t, "GLIDE_PATH_START_STOCK_PCT"),
            val(t, "GLIDE_PATH_END_STOCK_PCT"), val(t, "GLIDE_PATH_TENT_RISE_YEARS")) == ("tent", 0.5, 0.6, 10)
    assert val(t, "SS_PAYABLE_FRACTION") == 0.78 and val(t, "TARGET_SUCCESS_RATE") == 0.90
    assert val(t, "LTC_PROBABILITY") == pytest.approx(0.15) and val(t, "LTC_ANNUAL_COST") == 115_000
    assert val(t, "EXPECTED_INFLATION") == 0.025
    assert val(c, "ACTIVE_RETURN_SCENARIO") == "forward"
    assert (val(c, "GLIDE_PATH_START_STOCK_PCT"), val(c, "GLIDE_PATH_END_STOCK_PCT"),
            val(c, "GLIDE_PATH_TENT_RISE_YEARS")) == (0.4, 0.6, 15)
    assert val(c, "SS_PAYABLE_FRACTION") == pytest.approx(0.67, abs=0.011)
    assert val(c, "TARGET_SUCCESS_RATE") == 0.95
    assert val(c, "LTC_PROBABILITY") == pytest.approx(0.30) and val(c, "LTC_ANNUAL_COST") == 130_000
    assert val(c, "EXPECTED_INFLATION") == 0.030


def test_worked_example_young_professional():
    ov = _demo("Young professional (28, single)")
    t, c = preset("typical", ov), preset("conservative", ov)
    assert val(t, "PLAN_UNTIL_AGE") == 100 and "PARTNER_PLAN_UNTIL_AGE" not in t
    assert val(t, "STOCK_ALLOCATION") == 0.70
    assert (val(t, "GLIDE_PATH_START_STOCK_PCT"), val(t, "GLIDE_PATH_END_STOCK_PCT")) == (0.6, 0.7)
    assert val(t, "TARGET_SUCCESS_RATE") == 0.90 and val(t, "LTC_PROBABILITY") == pytest.approx(0.05)
    assert val(c, "ACTIVE_RETURN_SCENARIO") == "forward"
    assert (val(c, "GLIDE_PATH_START_STOCK_PCT"), val(c, "GLIDE_PATH_END_STOCK_PCT"),
            val(c, "GLIDE_PATH_TENT_RISE_YEARS")) == (0.5, 0.7, 15)
    assert val(c, "SS_PAYABLE_FRACTION") == pytest.approx(0.68, abs=0.011)
    assert val(c, "LTC_PROBABILITY") == pytest.approx(0.15)


def test_worked_example_mid_career_couple():
    ov = _demo("Mid-career couple (40, kids)")
    t, c = preset("typical", ov), preset("conservative", ov)
    assert (val(t, "PLAN_UNTIL_AGE"), val(t, "PARTNER_PLAN_UNTIL_AGE")) == (100, 100)
    assert val(t, "ACTIVE_RETURN_SCENARIO") == "conservative"
    assert val(t, "STOCK_ALLOCATION") == 0.60
    assert val(t, "LTC_PROBABILITY") == pytest.approx(0.15)
    assert val(c, "ACTIVE_RETURN_SCENARIO") == "forward"
    assert val(c, "EXPECTED_INFLATION") == 0.025        # the mortgage rule
    assert val(c, "SS_PAYABLE_FRACTION") == pytest.approx(0.70, abs=0.011)
    assert val(c, "LTC_PROBABILITY") == pytest.approx(0.25)


def test_worked_example_near_retirement():
    ov = _demo("Near retirement (55)")
    t, c = preset("typical", ov), preset("conservative", ov)
    assert (val(t, "PLAN_UNTIL_AGE"), val(t, "PARTNER_PLAN_UNTIL_AGE")) == (96, 96)
    assert val(t, "ACTIVE_RETURN_SCENARIO") == "conservative"
    assert val(t, "STOCK_ALLOCATION") == 0.55
    assert val(t, "TARGET_SUCCESS_RATE") == 0.90 and val(t, "LTC_PROBABILITY") == pytest.approx(0.15)
    assert (val(c, "PLAN_UNTIL_AGE"), val(c, "PARTNER_PLAN_UNTIL_AGE")) == (100, 100)
    assert val(c, "ACTIVE_RETURN_SCENARIO") == "forward"
    assert val(c, "SS_PAYABLE_FRACTION") == pytest.approx(0.73, abs=0.011)
    assert val(c, "TARGET_SUCCESS_RATE") == 0.95 and val(c, "LTC_PROBABILITY") == pytest.approx(0.25)


def test_worked_example_single_retiree_at_66():
    t, c = preset("typical", RETIREE_66), preset("conservative", RETIREE_66)
    assert val(t, "PLAN_UNTIL_AGE") == 95 and val(t, "ACTIVE_RETURN_SCENARIO") == "forward"
    assert (val(t, "GLIDE_PATH_SHAPE"), val(t, "GLIDE_PATH_START_STOCK_PCT"),
            val(t, "GLIDE_PATH_END_STOCK_PCT")) == ("down", 0.5, 0.4)
    assert val(t, "TARGET_SUCCESS_RATE") == 0.85 and val(t, "LTC_PROBABILITY") == pytest.approx(0.10)
    assert val(c, "PLAN_UNTIL_AGE") == 100 and val(c, "ACTIVE_RETURN_SCENARIO") == "pessimistic"
    assert val(c, "GLIDE_PATH_SHAPE") == "tent" and val(c, "GLIDE_PATH_START_STOCK_PCT") == 0.4
    assert val(c, "TARGET_SUCCESS_RATE") == 0.90 and val(c, "SS_PAYABLE_FRACTION") == 0.75
    assert val(c, "LTC_PROBABILITY") == pytest.approx(0.15)


# ------------------------------------------------------------------ direction

RANK = {"pessimistic": 0, "forward": 1, "conservative": 2}


@pytest.mark.parametrize("label,ov", _all_cases())
def test_conservative_is_never_more_hopeful_than_typical(label, ov):
    t, c = preset("typical", ov), preset("conservative", ov)
    assert RANK[val(c, "ACTIVE_RETURN_SCENARIO")] <= RANK[val(t, "ACTIVE_RETURN_SCENARIO")]
    assert val(c, "INVESTMENT_FEE_RATE") >= val(t, "INVESTMENT_FEE_RATE")
    loan = ap.situation(ov, "typical")["has_loan"]
    if loan:
        assert val(c, "EXPECTED_INFLATION") == val(t, "EXPECTED_INFLATION")
    else:
        assert val(c, "EXPECTED_INFLATION") >= val(t, "EXPECTED_INFLATION")
    assert val(c, "PLAN_UNTIL_AGE") >= val(t, "PLAN_UNTIL_AGE")
    assert val(c, "SS_PAYABLE_FRACTION") <= val(t, "SS_PAYABLE_FRACTION")
    assert val(c, "TARGET_SUCCESS_RATE") >= val(t, "TARGET_SUCCESS_RATE")
    assert val(c, "LTC_PROBABILITY") >= val(t, "LTC_PROBABILITY")
    assert val(c, "LTC_ANNUAL_COST") >= val(t, "LTC_ANNUAL_COST")
    assert val(c, "LATE_RETIREMENT_LEISURE_DECREASE") <= val(t, "LATE_RETIREMENT_LEISURE_DECREASE")
    assert val(c, "YOUR_SALARY_GROWTH_RATE") <= val(t, "YOUR_SALARY_GROWTH_RATE")
    assert not (val(c, "RETURN_BASED_SPENDING_ENABLED") and not val(t, "RETURN_BASED_SPENDING_ENABLED"))
    if "PARTNER_PLAN_UNTIL_AGE" in t:
        assert val(c, "PARTNER_PLAN_UNTIL_AGE") >= val(t, "PARTNER_PLAN_UNTIL_AGE")
        assert val(c, "PARTNER_SALARY_GROWTH_RATE") <= val(t, "PARTNER_SALARY_GROWTH_RATE")


# ------------------------------------------------------------------ scope, determinism

def test_preset_keys_cover_the_output_and_exclude_personal_facts():
    forbidden_fragments = ("BALANCE", "SPEND_", "CHILD", "MORTGAGE", "SS_CLAIM", "SS_MONTHLY",
                           "ROTH_CONVERSION", "ENABLE_ROTH", "ACA_BENCHMARK", "ACA_CHILD", "LIFECYCLE",
                           "LEISURE_INCREASE", "YOUR_AGE", "PARTNER_AGE", "RETIREMENT_AGE")
    assert len(set(ap.PRESET_KEYS)) == len(ap.PRESET_KEYS)
    for key in ap.PRESET_KEYS:
        assert not any(f in key for f in forbidden_fragments), key
        assert hasattr(cfg, key), key
    for _, ov in _all_cases():
        for name in ("typical", "conservative"):
            assert set(preset(name, ov)) <= set(ap.PRESET_KEYS)


def test_every_value_is_a_plain_value_and_every_key_has_a_reason():
    for _, ov in _all_cases():
        for name in ("typical", "conservative"):
            for key, (value, reason) in preset(name, ov).items():
                assert isinstance(value, (str, int, float, bool)), key
                assert isinstance(reason, str) and reason.strip(), key


def test_the_preset_does_not_read_the_current_assumption_values():
    base = _demo("Mid-career couple (40, kids)")
    a = dict(base, ACTIVE_RETURN_SCENARIO="historical", STOCK_ALLOCATION=1.0, EXPECTED_INFLATION=0.1,
             PLAN_UNTIL_AGE=75, SS_PAYABLE_FRACTION=1.0, LTC_PROBABILITY=0.0, TARGET_SUCCESS_RATE=0.7)
    b = dict(base, ACTIVE_RETURN_SCENARIO="pessimistic", STOCK_ALLOCATION=0.2, EXPECTED_INFLATION=0.0,
             PLAN_UNTIL_AGE=100, SS_PAYABLE_FRACTION=0.5, LTC_PROBABILITY=1.0, TARGET_SUCCESS_RATE=0.95)
    for name in ("typical", "conservative"):
        assert preset(name, a) == preset(name, b)
        assert preset(name, a) == preset(name, a)


def test_unknown_preset_name_is_an_error():
    with pytest.raises(ValueError):
        preset("wild", facts())


def test_missing_facts_fall_back_to_config_defaults():
    plan = preset("typical", {})
    assert plan and val(plan, "PLAN_UNTIL_AGE") >= 75


# ------------------------------------------------------------------ widget ranges

def _by_override_key():
    out = {}
    for widget, (key, cast) in ws.DIRECT_MAPPINGS.items():
        out.setdefault(key, []).append((widget, cast))
    return out


@pytest.mark.parametrize("label,ov", _all_cases())
@pytest.mark.parametrize("name", ["typical", "conservative"])
def test_no_preset_value_is_clamped_by_its_widget(label, ov, name):
    by_key = _by_override_key()
    for key, (value, _) in preset(name, ov).items():
        for widget, cast in by_key.get(key, []):
            if widget.startswith(("sp_", "sr_", "sv_manual", "sv_inflation")):
                continue                    # older duplicates of other keys; not these
            ws._clamped.log = []
            try:
                cast(value)
                assert not ws._clamped.log, (widget, value, ws._clamped.log)
            finally:
                ws._clamped.log = None


@pytest.mark.parametrize("label,ov", _all_cases())
@pytest.mark.parametrize("name", ["typical", "conservative"])
def test_values_sit_on_the_widget_steps(label, ov, name):
    plan = preset(name, ov)

    def on_step(x, step):
        q = x / step
        return abs(q - round(q)) < 1e-6
    for key in ("STOCK_ALLOCATION", "GLIDE_PATH_START_STOCK_PCT", "GLIDE_PATH_END_STOCK_PCT",
                "LTC_PROBABILITY", "LATE_RETIREMENT_LEISURE_DECREASE"):
        assert on_step(val(plan, key) * 100, 5), key
    assert on_step(val(plan, "INVESTMENT_FEE_RATE") * 10_000, 5)
    assert on_step(val(plan, "EXPECTED_INFLATION") * 100, 0.25)
    assert on_step(val(plan, "LTC_ANNUAL_COST"), 5_000)
    assert on_step(val(plan, "SS_PAYABLE_FRACTION") * 100, 1)
    assert on_step(val(plan, "TARGET_SUCCESS_RATE") * 100, 1)
    for key in ("YOUR_SALARY_GROWTH_RATE", "PARTNER_SALARY_GROWTH_RATE"):
        if key in plan:
            assert on_step(val(plan, key) * 100, 0.5), key
    assert 30 <= val(plan, "GLIDE_PATH_START_STOCK_PCT") * 100 <= 100
    assert 20 <= val(plan, "GLIDE_PATH_END_STOCK_PCT") * 100 <= 100
    assert 3 <= val(plan, "GLIDE_PATH_TENT_RISE_YEARS") <= 25
    assert 75 <= val(plan, "PLAN_UNTIL_AGE") <= 100


# ------------------------------------------------------------------ engine wiring

@pytest.mark.parametrize("label,ov", _all_cases())
@pytest.mark.parametrize("name", ["typical", "conservative"])
def test_preset_keys_pass_the_engine_audit(label, ov, name):
    from utils import sim_runner
    from utils.config_builder import build_config_overrides
    merged = dict(ov)
    merged.update({k: v for k, (v, _) in preset(name, ov).items()})
    assert sim_runner.audit_override_keys(build_config_overrides(merged)) == []


# ------------------------------------------------------------------ comparing and describing

def test_matches_ignores_float_noise_and_skipped_keys():
    ov = facts(40, 38, 55)
    plan = preset("typical", ov)
    current = dict(ov, **{k: v for k, (v, _) in plan.items()})
    current["INVESTMENT_FEE_RATE"] += 1e-9
    assert ap.matches(current, plan)
    current["STOCK_ALLOCATION"] = 0.1
    assert not ap.matches(current, plan)


def test_label_table_covers_every_preset_key():
    for key in ap.PRESET_KEYS:
        assert key in ap.LABELS, key


def test_format_value_uses_the_widgets_units():
    f = ap.format_value
    assert f("ACTIVE_RETURN_SCENARIO", "conservative") == "Conservative"
    assert f("ACTIVE_RETURN_SCENARIO", "forward") == "Forward-looking"
    assert f("STOCK_ALLOCATION", 0.75) == "75%"
    assert f("INVESTMENT_FEE_RATE", 0.003) == "30 bps"
    assert f("EXPECTED_INFLATION", 0.025) == "2.5%"
    assert f("EXPECTED_INFLATION", 0.0275) == "2.75%"
    assert f("PLAN_UNTIL_AGE", 100) == "100"
    assert f("GLIDE_PATH_SHAPE", "tent") == "Bond tent"
    assert f("GLIDE_PATH_ENABLED", True) == "On" and f("ACA_ENABLED", False) == "Off"
    assert f("LTC_ANNUAL_COST", 115000) == "$115,000"
    assert f("SS_PAYABLE_FRACTION", 0.78) == "78%"
    assert f("YOUR_SALARY_GROWTH_RATE", 0.015) == "1.5%"
    assert f("LTC_PROBABILITY", ap.MISSING) == "not set"


def test_copy_lint_on_every_string_the_module_shows():
    import re
    texts = []
    for _, ov in _all_cases():
        for name in ("typical", "conservative"):
            texts += [r for _, r in preset(name, ov).values()]
    texts += list(ap.COPY.values())
    for t in texts:
        assert ";" not in t and "**" not in t, t
        assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", t), t
        for sentence in re.split(r"(?<=[.!?])\s+", t.strip()):
            assert len(sentence.split()) <= 24, sentence
