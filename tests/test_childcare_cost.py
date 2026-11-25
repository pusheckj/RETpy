"""Typical childcare cost by BiggerPockets Money's method, and the engine's childcare field.

BPM's README works one example by hand: San Diego County, two children, 35-44 parent,
household of 4, full-time center care: $35,244 a year in 2026 dollars.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from utils import budget_data as bd  # noqa: E402
from utils import childcare_cost as cc  # noqa: E402
from utils import derived  # noqa: E402

SD = "San Diego-Chula Vista-Carlsbad, CA"
LOW_RENT_AREA = "Appalachian Highlands (WV / VA / KY)"     # no county figure, rents 54% of the US


def test_bpms_worked_example_for_san_diego_county():
    """BPM's README: parent 35-44, household of 4, so its own age weights. We keep that
    method here only to check the data and rounding against BPM."""
    w = cc.bpm_weights(parent_age=40, household_size=4)
    two = cc.estimate("CA", SD, n_children=2, weights=w)
    assert two.annual == 35_244                        # BPM README, to the dollar
    assert two.coverage == "county"
    assert two.weights == pytest.approx([0.10, 0.30, 0.60, 0.0])   # school-age moved to preschool
    assert cc.estimate("CA", SD, weights=w).per_child == 17_622    # 17,110 in 2025 dollars x 1.0299


def test_the_app_weights_follow_a_childs_first_five_years():
    # NDCP tiers: infant under 2, toddler 2, preschool 3 to 5 (school-age starts at 5).
    # Ages 0 to 4 are two years of infant, one of toddler, two of preschool.
    assert cc.TIME_IN_TIER == pytest.approx([0.4, 0.2, 0.4, 0.0])
    assert sum(cc.TIME_IN_TIER) == pytest.approx(1.0)
    assert cc.estimate("CA", SD).weights == cc.TIME_IN_TIER


def test_weights_follow_only_the_childcare_years_still_ahead():
    assert cc.weights_from_age(0) == cc.TIME_IN_TIER
    assert cc.weights_from_age(1) == pytest.approx([0.25, 0.25, 0.5, 0])        # ages 1 to 4
    assert cc.weights_from_age(2) == pytest.approx([0, 1 / 3, 2 / 3, 0])        # ages 2 to 4
    assert cc.weights_from_age(3) == pytest.approx([0, 0, 1.0, 0])
    assert cc.weights_from_age(4) == pytest.approx([0, 0, 1.0, 0])
    assert cc.weights_from_age(5) == [0, 0, 0, 0] and cc.weights_from_age(9) == [0, 0, 0, 0]
    assert cc.weights_from_age(-2) == cc.TIME_IN_TIER                            # not born yet: all five years
    assert cc.estimate("CA", SD, child_age=3).per_child < cc.estimate("CA", SD).per_child   # preschool costs less than infant care
    assert cc.estimate("CA", SD, child_age=5).per_child == 0


def test_for_household_takes_the_childs_age():
    ov = {"STATE_CHOICE": "CA", "BENCH_AREA": SD, "CHILDREN": [{}]}
    assert cc.for_household(ov, child_age=4)[0] == cc.estimate("CA", SD, child_age=4)
    assert cc.for_household(ov)[0] == cc.estimate("CA", SD)


def test_san_diego_county_per_child_with_the_app_weights():
    e = cc.estimate("CA", SD)
    prices = [round(p * 1.172) for p in (19719, 16859, 12616)]
    assert e.per_child == round((prices[0] * 0.4 + prices[1] * 0.2 + prices[2] * 0.4) * 1.0299)
    assert e.per_child == 19_682


def test_a_county_is_used_as_it_is_whatever_its_rents():
    a = cc.estimate("CA", SD, renormalize=True)
    b = cc.estimate("CA", SD, renormalize=False)
    assert a.per_child == b.per_child                  # the rents index never touches a county


def test_a_state_with_no_area_uses_the_state_price_unscaled():
    e = cc.estimate("CA", None)
    assert e.coverage == "state" and e.prices_2022 == bd.state_childcare_prices("CA")
    prices = [round(p * 1.172) for p in bd.state_childcare_prices("CA")]
    expected = (prices[0] * 0.4 + prices[1] * 0.2 + prices[2] * 0.4) * 1.0299
    assert e.per_child == pytest.approx(expected, abs=1)


def test_an_area_without_a_county_figure_scales_its_states_price_by_its_rents():
    row = bd.area(LOW_RENT_AREA)
    assert bd.county_childcare_prices(LOW_RENT_AREA) is None and row["rr"] == 54
    e = cc.estimate(row["st"], LOW_RENT_AREA)
    assert e.coverage == "area"
    # Rents are 0.54 of the US, below BPM's floor of 0.65, so the floor applies.
    assert e.prices_2022 == [int(p * 0.65 + 0.5) for p in bd.state_childcare_prices(row["st"])]  # half up, as BPM rounds


def test_no_state_falls_back_to_bpms_national_prices():
    e = cc.estimate(None, None)
    assert e.coverage == "national" and e.prices_2022 == bd.constants()["NATIONAL"]


def test_bpms_age_weights_move_with_the_parent_and_stay_available_for_checks():
    young = cc.estimate("TX", None, weights=cc.bpm_weights(28, 3)).per_child
    middle = cc.estimate("TX", None, weights=cc.bpm_weights(40, 3)).per_child
    older = cc.estimate("TX", None, weights=cc.bpm_weights(50, 3)).per_child
    assert young > middle > older > 0
    assert cc.bpm_weights(58, 3) == pytest.approx([0, 0, 1.0, 0])


def test_household_size_and_age_pick_the_bands():
    assert [cc.age_band(a) for a in (20, 25, 34, 35, 44, 45, 54, 55, 64, 65, 90)] == [
        "Under25", "25-34", "25-34", "35-44", "35-44", "45-54", "45-54", "55-64", "55-64", "65+", "65+"]
    assert [cc.size_key(n) for n in (0, 1, 4, 5, 9)] == ["1", "1", "4", "5+", "5+"]


def test_for_household_does_not_depend_on_the_parents_age_or_the_household_size():
    ov = {"YOUR_AGE": 34, "PARTNER_AGE": 33, "STATE_CHOICE": "CA", "BENCH_AREA": SD,
          "CHILDREN": [{"years_until_birth": -2}, {"years_until_birth": 3}]}
    est, where = cc.for_household(ov)
    assert where == SD and est.coverage == "county"
    assert est == cc.estimate("CA", SD)
    other, _ = cc.for_household({**ov, "YOUR_AGE": 52, "PARTNER_AGE": 0})
    assert other == est


def test_for_household_names_the_state_without_an_area_and_none_without_children():
    est, where = cc.for_household({"YOUR_AGE": 34, "STATE_CHOICE": "TX", "CHILDREN": [{}]})
    assert where == "Texas" and est.coverage == "state"
    assert cc.for_household({"YOUR_AGE": 34, "STATE_CHOICE": "TX", "CHILDREN": []}) is None
    _, where = cc.for_household({"STATE_CHOICE": "No state tax", "CHILDREN": [{}]})
    assert where == "the US"


# ---- the engine: childcare_monthly runs for the first five years, on top of monthly_cost

@pytest.fixture
def one_child(monkeypatch):
    monkeypatch.setattr(cfg, "YOUR_AGE", 30)
    monkeypatch.setattr(cfg, "CHILDREN", [{"years_until_birth": 2, "monthly_cost": 1_000,
                                           "childcare_monthly": 1_500, "leaves_home_age": 18}])


def test_childcare_is_charged_only_while_the_child_is_under_five(one_child):
    spend = {age: cfg.calculate_child_expenses(age) for age in (31, 32, 36, 37, 49, 50)}
    assert spend[31] == 0                                  # not born yet
    assert spend[32] == (1_000 + 1_500) * 12               # born: both
    assert spend[36] == (1_000 + 1_500) * 12               # age 4: still both
    assert spend[37] == 1_000 * 12                         # age 5: childcare stops
    assert spend[49] == 1_000 * 12
    assert spend[50] == 0                                  # age 18: left home


def test_a_child_with_no_childcare_costs_what_it_did_before(monkeypatch):
    monkeypatch.setattr(cfg, "YOUR_AGE", 30)
    monkeypatch.setattr(cfg, "CHILDREN", [{"years_until_birth": 0, "monthly_cost": 2_100}])
    assert cfg.CHILD_DEFAULTS["childcare_monthly"] == 0
    assert cfg.calculate_child_expenses(30) == 2_100 * 12
    assert cfg.normalize_children(cfg.CHILDREN)[0]["childcare_monthly"] == 0


def test_spending_today_counts_childcare_for_a_young_child_only():
    base = {"YOUR_AGE": 35}
    young = {"years_until_birth": -2, "monthly_cost": 1_000, "childcare_monthly": 1_500}
    school = {"years_until_birth": -7, "monthly_cost": 1_000, "childcare_monthly": 1_500}
    assert derived.child_monthly_now(cfg.normalize_children([young])[0]) == 2_500
    assert derived.child_monthly_now(cfg.normalize_children([school])[0]) == 1_000
    no_kids = derived.compute_expenses_today({**base, "CHILDREN": []})
    with_kid = derived.compute_expenses_today({**base, "CHILDREN": [young]})
    assert with_kid - no_kids == 2_500 * 12


def test_children_from_an_old_two_child_profile_have_every_field_including_childcare():
    kids = cfg.children_in({"YEARS_UNTIL_FIRST_CHILD": 0, "FIRST_CHILD_MONTHLY_COST": 2_100})
    assert len(kids) == 2
    assert all(k["childcare_monthly"] == 0 and set(k) == set(cfg.CHILD_DEFAULTS) for k in kids)
