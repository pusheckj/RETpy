"""Household structure, children, plan length and Social Security claiming.

* Children are a list (cfg.CHILDREN). Old profiles' two-child keys are turned
  into the equivalent list, so they give the same results as before.
* A single household (PARTNER_AGE 0) has no partner accounts, contributions or
  working years, whatever stray partner numbers the profile still carries; the
  side panel hides and zeroes every partner input.
* The plan runs until the later of the two people's plan-until ages, and the
  partner can claim Social Security at their own age.
"""
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import account_simulation as sim  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402
from utils.profile_io import deserialize_overrides, _restore_int_keys  # noqa: E402

_FIXTURES = os.path.join(_ROOT, "tests", "fixtures")


def _fixture(name: str) -> dict:
    with open(os.path.join(_FIXTURES, name), encoding="utf-8") as fh:
        return deserialize_overrides(fh.read())


def _run(overrides: dict, age: int, n: int = 40, seed: int = 7):
    """(success rate, median final balance) through the planner's own path."""
    original = sr._apply_overrides(build_config_overrides(overrides))
    try:
        r = sim.run_monte_carlo_detailed(int(age), n_simulations=n, random_seed=seed)
    finally:
        sr._restore_overrides(original)
    return r["success_rate"], float(r["median_final"])


def _kid(years_until_birth, monthly_cost=1_000, leaves=18, pct=0.0, fee=40_000, years=4):
    return {"years_until_birth": years_until_birth, "monthly_cost": monthly_cost,
            "leaves_home_age": leaves, "college_annual_cost": fee, "college_years": years,
            "college_funding_pct": pct}


# ---------------------------------------------------------------------------
# 1. Old two-child keys == the equivalent CHILDREN list
# ---------------------------------------------------------------------------

def _old_rules(v: dict, your_age: int, age: int):
    """The engine's previous two-child rules, copied verbatim in spirit:
    (child cost, children at home, 529 saving, college bill)."""
    b1 = your_age + v["YEARS_UNTIL_FIRST_CHILD"]
    b2 = b1 + v["YEARS_BETWEEN_CHILDREN"]
    leave = v["CHILD_LEAVES_HOME_AGE"]
    one, both = v["FIRST_CHILD_MONTHLY_COST"] * 12, v["BOTH_CHILDREN_MONTHLY_COST"] * 12
    if age < b1:
        cost = 0
    elif age < b2:
        cost = one if age < b1 + leave else 0
    elif age < b1 + leave:
        cost = both
    elif age < b2 + leave:
        cost = both - one
    else:
        cost = 0
    home = [age - b for b in (b1, b2) if 0 <= age - b < leave]
    per = v["COLLEGE_ANNUAL_COST"] * v["COLLEGE_YEARS"] * v["COLLEGE_FUNDING_PCT"] / 18
    saving = sum(per for b in (b1, b2) if 0 <= age - b < 18)
    bill = sum(v["COLLEGE_ANNUAL_COST"] * v["COLLEGE_FUNDING_PCT"] for b in (b1, b2)
               if 18 <= age - b < 18 + v["COLLEGE_YEARS"])
    return cost, home, saving, bill


@pytest.mark.parametrize("first", [-25, -5, 0, 2, 99])
@pytest.mark.parametrize("between", [1, 3, 20])
@pytest.mark.parametrize("costs", [(2_100, 3_500), (1_800, 1_800), (0, 0)])
@pytest.mark.parametrize("leave", [16, 18, 22])
def test_old_two_child_keys_equal_the_children_list(monkeypatch, first, between, costs, leave):
    v = {**cfg.LEGACY_CHILD_KEYS, "YEARS_UNTIL_FIRST_CHILD": first,
         "YEARS_BETWEEN_CHILDREN": between, "FIRST_CHILD_MONTHLY_COST": costs[0],
         "BOTH_CHILDREN_MONTHLY_COST": costs[1], "CHILD_LEAVES_HOME_AGE": leave,
         "COLLEGE_FUNDING_PCT": 0.5}
    monkeypatch.setattr(cfg, "YOUR_AGE", 30)
    monkeypatch.setattr(cfg, "CHILDREN", cfg.legacy_children(v))
    for age in range(30, 120):
        cost, home, saving, bill = _old_rules(v, 30, age)
        assert cfg.calculate_child_expenses(age) == cost, age
        assert cfg.children_at_home_ages(age) == home, age
        assert cfg.calculate_529_contribution(age) == pytest.approx(saving), age
        assert cfg.calculate_college_expenses(age)["total"] == pytest.approx(bill), age


def test_migration_folds_old_keys_and_drops_the_wedding_flag():
    old = {"YEARS_UNTIL_FIRST_CHILD": -4, "FIRST_CHILD_MONTHLY_COST": 1_800,
           "BOTH_CHILDREN_MONTHLY_COST": 3_000, "FIRST_CHILD_ANNUAL_COST": 1,
           "YEARS_UNTIL_WEDDING": 0, "YOUR_AGE": 40}
    new = cfg.migrate_legacy_overrides(old)
    assert set(new) == {"YOUR_AGE", "CHILDREN"}
    assert [(k["years_until_birth"], k["monthly_cost"]) for k in new["CHILDREN"]] == [
        (-4, 1_800), (-1, 1_200)]
    # A CHILDREN list already there wins; nothing to do returns the same dict.
    assert cfg.migrate_legacy_overrides({**old, "CHILDREN": []})["CHILDREN"] == []
    plain = {"YOUR_AGE": 40}
    assert cfg.migrate_legacy_overrides(plain) is plain
    assert cfg.legacy_children({"YEARS_UNTIL_FIRST_CHILD": 99}) == []


def test_presets_give_the_same_results_as_their_old_two_child_form():
    """The presets now carry CHILDREN; their previous form (two-child keys,
    everything else the same) must simulate identically."""
    from components.profile_picker import PROFILES
    old_first_child = {"Median US 25-year-old household": 3, "Young professional (28, single)": 99,
                       "Mid-career couple (40, kids)": -5, "Near retirement (55)": -25}
    for name, years in old_first_child.items():
        preset = PROFILES[name]
        old = {k: v for k, v in preset.items() if k != "CHILDREN"}
        old["YEARS_UNTIL_FIRST_CHILD"] = years
        age = preset["TARGET_RETIREMENT_AGE"]
        assert _run(old, age) == _run(dict(preset), age), name


def test_the_sample_fixture_gives_the_same_results_in_either_form():
    """tests/fixtures/sample_household.json is an old export (two-child keys).
    Read raw (keys translated where overrides reach cfg) or loaded (translated
    on load), it simulates exactly like the explicit list."""
    with open(os.path.join(_FIXTURES, "sample_household.json"), encoding="utf-8") as fh:
        raw = _restore_int_keys(json.load(fh)["overrides"])
    assert "YEARS_UNTIL_FIRST_CHILD" in raw
    loaded = _fixture("sample_household.json")
    assert "YEARS_UNTIL_FIRST_CHILD" not in loaded and len(loaded["CHILDREN"]) == 2
    explicit = {k: v for k, v in raw.items() if k not in cfg.LEGACY_CHILD_KEYS}
    explicit["CHILDREN"] = [_kid(1, 2_000), _kid(3, 1_500)]
    age = raw["TARGET_RETIREMENT_AGE"]
    assert _run(raw, age) == _run(loaded, age) == _run(explicit, age)


# ---------------------------------------------------------------------------
# 2. Any number of children, each with their own costs and leave-home age
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [0, 1, 3, 5])
def test_any_number_of_children(monkeypatch, n):
    monkeypatch.setattr(cfg, "YOUR_AGE", 30)
    monkeypatch.setattr(cfg, "CHILDREN", [_kid(-i, 100 * (i + 1)) for i in range(n)])
    assert len(cfg.children_at_home_ages(30)) == n
    assert cfg.calculate_child_expenses(30) == 12 * sum(100 * (i + 1) for i in range(n))
    portfolio = sim.create_initial_portfolio()
    assert sorted(a for a in portfolio.accounts if a.endswith("_529")) == sorted(
        f"child{i}_529" for i in range(1, n + 1))


def test_children_leave_home_at_their_own_ages(monkeypatch):
    monkeypatch.setattr(cfg, "YOUR_AGE", 40)
    monkeypatch.setattr(cfg, "CHILDREN", [_kid(-10, 1_000, leaves=18), _kid(-10, 500, leaves=22)])
    assert cfg.calculate_child_expenses(47) == 18_000      # both 17
    assert cfg.calculate_child_expenses(48) == 6_000       # first left at 18
    assert cfg.calculate_child_expenses(51) == 6_000
    assert cfg.calculate_child_expenses(52) == 0           # second left at 22
    assert cfg.children_at_home_ages(50) == [20]


def test_each_child_saves_into_and_pays_college_from_their_own_529(monkeypatch):
    """Two children with different funding shares, zero returns so the dollars
    are exact: each 529 fills to its own target by 18, and college -- here
    during the working years -- is paid from it, leaving nothing stranded."""
    monkeypatch.setattr(cfg, "YOUR_AGE", 30)
    monkeypatch.setattr(cfg, "CHILDREN", [_kid(0, 0, pct=0.5, fee=36_000),
                                          _kid(0, 0, pct=1.0, fee=36_000)])
    monkeypatch.setattr(cfg, "HOUSE_MOVE_ENABLED", False)
    monkeypatch.setattr(cfg, "CAR_ONETIME_ENABLED", False)
    monkeypatch.setattr(cfg, "CAR_RECURRING_ENABLED", False)
    p = sim.create_initial_portfolio()
    for age in range(30, 48):
        sim.simulate_accumulation_year(p, age, 0.0)
    assert p.accounts["child1_529"].balance == pytest.approx(36_000 * 4 * 0.5)
    assert p.accounts["child2_529"].balance == pytest.approx(36_000 * 4 * 1.0)
    living_before = p.spending_log[-1]["living"]
    sim.simulate_accumulation_year(p, 48, 0.0)                 # first college year
    assert p.accounts["child1_529"].balance == pytest.approx(36_000 * 3 * 0.5)
    assert p.spending_log[-1]["living"] == pytest.approx(living_before)   # 529 paid it all
    for age in range(49, 52):
        sim.simulate_accumulation_year(p, age, 0.0)
    assert p.accounts["child1_529"].balance == pytest.approx(0)
    assert p.accounts["child2_529"].balance == pytest.approx(0)


def test_three_children_cost_more_than_two(monkeypatch):
    base = _fixture("couple_three_kids.json")
    two = {**base, "CHILDREN": base["CHILDREN"][:2]}
    assert _run(base, 58)[1] < _run(two, 58)[1]


# ---------------------------------------------------------------------------
# 3. Single households keep no partner money
# ---------------------------------------------------------------------------

_LEAKED = {"PARTNER_401K": 7_000, "PARTNER_ROTH_IRA": 2_500, "PARTNER_BROKERAGE": 1_000,
           "PARTNER_CASH": 3_000, "PARTNER_401K_CONTRIBUTION": 2_500,
           "PARTNER_ROTH_CONTRIBUTION": 2_000, "PARTNER_BROKERAGE_CONTRIBUTION": 5_000,
           "PARTNER_SALARY": 42_000}


def test_single_household_has_no_partner_accounts_or_flows(monkeypatch):
    for k, v in {**_LEAKED, "PARTNER_AGE": 0, "FILING_STATUS": "Single"}.items():
        monkeypatch.setattr(cfg, k, v)
    p = sim.create_initial_portfolio()
    assert not any(a.owner == "partner" for a in p.accounts.values())
    start = p.get_total_balance()
    for age in range(cfg.YOUR_AGE, cfg.YOUR_AGE + 3):
        sim.simulate_accumulation_year(p, age, 0.0)
    assert not any(a.owner == "partner" for a in p.accounts.values())
    assert p.get_total_balance() > start                    # the primary still saves


def test_stray_partner_numbers_change_nothing_for_a_single():
    single = _fixture("single_renter.json")
    assert _run({**single, **_LEAKED}, 60) == _run(single, 60)


def test_partner_roth_follows_the_income_phase_out_not_marriage(monkeypatch):
    """Marriage is the filing status (the wedding-year flag is gone), and the
    partner's direct Roth follows the Roth income phase-out of their return --
    being married no longer blocks it (that was the author's own situation:
    a joint income over the phase-out)."""
    monkeypatch.setattr(cfg, "PARTNER_ROTH_CONTRIBUTION", 2_000)
    for status, partner_pay, expected in (("Single", None, 2_000),
                                          ("Married filing jointly", None, 2_000),
                                          ("Married filing jointly", 400_000, 0)):
        monkeypatch.setattr(cfg, "FILING_STATUS", status)
        if partner_pay is not None:
            monkeypatch.setattr(cfg, "PARTNER_SALARY", partner_pay)
        p = sim.create_initial_portfolio()
        before = p.accounts["partner_roth_ira"].balance
        sim.simulate_accumulation_year(p, cfg.YOUR_AGE, 0.0)
        assert p.accounts["partner_roth_ira"].balance - before == expected, (status, partner_pay)


# ---------------------------------------------------------------------------
# 4. Plan length and Social Security claiming
# ---------------------------------------------------------------------------

def test_plan_runs_to_the_younger_partners_plan_until_age(monkeypatch):
    monkeypatch.setattr(cfg, "YOUR_AGE", 40)
    monkeypatch.setattr(cfg, "PARTNER_AGE", 30)
    monkeypatch.setattr(cfg, "PLAN_UNTIL_AGE", 95)
    monkeypatch.setattr(cfg, "YOUR_BROKERAGE", 50_000_000)     # never runs out
    assert cfg.plan_end_age() == 105
    ok, p = sim.run_detailed_simulation(55, random_seed=1)
    assert ok and p.yearly_history[-1]["age"] == 105
    monkeypatch.setattr(cfg, "PARTNER_PLAN_UNTIL_AGE", 80)    # partner's own horizon
    assert cfg.plan_end_age() == 95
    monkeypatch.setattr(cfg, "PARTNER_AGE", 0)                  # single: yours only
    monkeypatch.setattr(cfg, "PARTNER_PLAN_UNTIL_AGE", None)
    assert cfg.plan_end_age() == 95
    assert cfg.plan_end_age({"PARTNER_AGE": 25, "YOUR_AGE": 40}) == 110


def test_partner_claims_social_security_at_their_own_age(monkeypatch):
    monkeypatch.setattr(cfg, "YOUR_AGE", 60)
    monkeypatch.setattr(cfg, "PARTNER_AGE", 60)
    monkeypatch.setattr(cfg, "YOUR_SS_MONTHLY_FRA", 2_000)
    monkeypatch.setattr(cfg, "PARTNER_SS_MONTHLY_FRA", 1_000)
    assert cfg.calculate_social_security(62, 67) == 0           # same claim age (default)
    monkeypatch.setattr(cfg, "PARTNER_SS_CLAIM_AGE", 62)
    assert cfg.calculate_social_security(62, 67) == pytest.approx(1_000 * 0.70 * 12)
    assert cfg.calculate_social_security(67, 67) == pytest.approx((2_000 + 700) * 12)
    monkeypatch.setattr(cfg, "PARTNER_SS_CLAIM_AGE", 70)
    assert cfg.calculate_social_security(67, 67) == pytest.approx(2_000 * 12)
    assert cfg.calculate_social_security(70, 67) == pytest.approx((2_000 + 1_240) * 12)


# ---------------------------------------------------------------------------
# 5. Fixtures for household shapes other than the sample couple
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,kids,partner", [
    ("single_renter.json", 0, False),
    ("single_parent_hoh.json", 1, False),
    ("couple_three_kids.json", 3, True),
])
def test_household_fixtures_load_and_run(name, kids, partner):
    ov = _fixture(name)
    assert len(ov["CHILDREN"]) == kids and (ov["PARTNER_AGE"] > 0) == partner
    original = sr._apply_overrides(build_config_overrides(ov))
    try:
        assert cfg.has_partner() == partner
        p = sim.create_initial_portfolio()
        assert any(a.owner == "partner" for a in p.accounts.values()) == partner
        assert sum(a.endswith("_529") for a in p.accounts) == kids
        if name == "single_parent_hoh.json":
            assert cfg.normalize_filing_status() == "HOH"
            assert cfg.calculate_child_expenses(cfg.YOUR_AGE) == 1_500 * 12
        rate = sim.run_monte_carlo_detailed(ov["TARGET_RETIREMENT_AGE"], 30, 3)["success_rate"]
        assert 0.0 <= rate <= 1.0
    finally:
        sr._restore_overrides(original)


# ---------------------------------------------------------------------------
# 6. The side panel: no partner inputs without a partner; children rows
# ---------------------------------------------------------------------------

def _panel_script():
    import os
    import sys
    sys.path[:0] = [os.environ["HH_TEST_UI"], os.path.dirname(os.environ["HH_TEST_UI"])]
    import streamlit as st
    from components import (account_inputs, sec_about_you, sec_expenses,
                            sec_retirement_goals, sec_savings)
    sec_about_you.render_body(st)
    account_inputs.render(st)
    sec_expenses.render_body(st)
    sec_savings.render_body(st)
    sec_retirement_goals.render_body(st)


@pytest.fixture
def panel(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("HH_TEST_UI", _UI)

    def make(overrides):
        at = AppTest.from_function(_panel_script, default_timeout=60)
        at.session_state["user_overrides"] = dict(overrides)
        at.run()
        assert not at.exception, at.exception
        return at
    return make


def _widget_keys(at):
    keys = set()
    for kind in ("number_input", "slider", "toggle", "radio", "selectbox"):
        keys |= {w.key for w in getattr(at, kind) if w.key}
    return keys


def test_single_household_panel_shows_and_keeps_no_partner_inputs(panel):
    at = panel({**_fixture("single_renter.json"), **_LEAKED,
                "PRIMARY_PAYS_HOUSING": True, "SAVINGS_MODE": "Manual amounts"})
    assert at.radio(key="ay_household").value == "Just me"
    assert not [k for k in _widget_keys(at) if "partner" in k or k == "sv_primary_housing"]
    ov = at.session_state["user_overrides"]
    assert all(ov[k] == 0 for k in _LEAKED), {k: ov[k] for k in _LEAKED}
    assert ov["PRIMARY_PAYS_HOUSING"] is False and ov["PARTNER_AGE"] == 0


def test_couple_panel_shows_the_partner_inputs(panel):
    at = panel({**_fixture("couple_three_kids.json"), "SAVINGS_MODE": "Manual amounts"})
    assert at.radio(key="ay_household").value == "Me and my spouse"
    assert {"ay_partner_age", "ay_partner_plan_until", "ai_partner_401k",
            "sv_manual_partner_401k", "sv_primary_housing",
            "rg_partner_ss_claim"} <= _widget_keys(at)
    assert at.session_state["user_overrides"]["PARTNER_401K"] == 60_000


def test_choosing_just_me_zeroes_the_partner(panel):
    at = panel(_fixture("couple_three_kids.json"))
    at.radio(key="ay_household").set_value("Just me").run()
    ov = at.session_state["user_overrides"]
    assert ov["PARTNER_AGE"] == 0 and ov["PARTNER_401K"] == 0 and ov["PARTNER_SALARY"] == 0
    assert ov["FILING_STATUS"] in ("Single", "Head of household")


def test_children_rows_follow_the_count(panel):
    at = panel(_fixture("couple_three_kids.json"))
    assert at.number_input(key="se_kids_n").value == 3
    assert at.number_input(key="se_kid0_age").value == 8
    assert at.number_input(key="se_kid2_in").value == 1
    at.number_input(key="se_kids_n").set_value(5).run()
    kids = at.session_state["user_overrides"]["CHILDREN"]
    assert [k["years_until_birth"] for k in kids] == [-8, -5, 1, 4, 7]
    at.number_input(key="se_kid1_cost").set_value(900)
    at.number_input(key="se_kid1_leaves").set_value(22).run()
    kid = at.session_state["user_overrides"]["CHILDREN"][1]
    assert (kid["monthly_cost"], kid["leaves_home_age"]) == (900, 22)
    at.number_input(key="se_kids_n").set_value(0).run()
    assert at.session_state["user_overrides"]["CHILDREN"] == []


def test_an_old_profile_fills_the_children_rows(panel):
    old = {k: v for k, v in _fixture("single_renter.json").items() if k != "CHILDREN"}
    at = panel({**old, "YEARS_UNTIL_FIRST_CHILD": -3, "FIRST_CHILD_MONTHLY_COST": 1_200,
                "BOTH_CHILDREN_MONTHLY_COST": 1_200})
    assert at.number_input(key="se_kids_n").value == 2      # the old model's two
    assert at.number_input(key="se_kid0_cost").value == 1_200
    assert at.number_input(key="se_kid1_cost").value == 0


def test_married_spouse_gets_the_spousal_top_up(monkeypatch):
    """A married spouse with a small own benefit is topped up to half of the
    other's once both have claimed (reduced if claimed early, no delayed
    credit); an unmarried partner is not; the toggle restores the old rule."""
    monkeypatch.setattr(cfg, "YOUR_AGE", 60)
    monkeypatch.setattr(cfg, "PARTNER_AGE", 60)
    monkeypatch.setattr(cfg, "FILING_STATUS", "Married filing jointly")
    monkeypatch.setattr(cfg, "YOUR_SS_MONTHLY_FRA", 3_000)
    monkeypatch.setattr(cfg, "PARTNER_SS_MONTHLY_FRA", 500)
    own = (3_000 + 500) * 12
    assert cfg.calculate_social_security(67, 67) == pytest.approx(own + 1_000 * 12)
    monkeypatch.setattr(cfg, "PARTNER_SS_CLAIM_AGE", 62)       # spouse files early
    assert cfg.calculate_social_security(66, 67) == pytest.approx(500 * 0.70 * 12)  # you haven't
    assert cfg.calculate_social_security(67, 67) == pytest.approx(
        (3_000 + 350) * 12 + 1_000 * 12 * cfg.ss_spousal_factor(67))  # top-up starts at 67
    monkeypatch.setattr(cfg, "FILING_STATUS", "Single")         # unmarried partners
    assert cfg.calculate_social_security(67, 67) == pytest.approx((3_000 + 350) * 12)
    monkeypatch.setattr(cfg, "FILING_STATUS", "Married filing jointly")
    monkeypatch.setattr(cfg, "MODEL_SPOUSAL_SS_BENEFIT", False)
    assert cfg.calculate_social_security(67, 67) == pytest.approx((3_000 + 350) * 12)
    assert cfg.ss_spousal_factor(62) == pytest.approx(0.65)
    assert cfg.ss_spousal_factor(70) == 1.0
