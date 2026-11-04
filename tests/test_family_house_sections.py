"""The Family and House sidebar sections.

Family holds the children rows (moved out of Expenses); House holds housing,
home moves and extra mortgage payments (moved out of Expenses and Big purchases
& goals). The widget keys did not change, so saved profiles load as before.
"""
import ast
import os
import re
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
_FIXTURES = os.path.join(_TESTS, "fixtures")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.profile_io import deserialize_overrides  # noqa: E402


def _fixture(name: str) -> dict:
    with open(os.path.join(_FIXTURES, name), encoding="utf-8") as fh:
        return deserialize_overrides(fh.read())


def _script():
    import os
    import sys
    sys.path[:0] = [os.environ["FH_TEST_UI"], os.path.dirname(os.environ["FH_TEST_UI"])]
    import streamlit as st
    from components import (sec_big_purchases, sec_expenses, sec_family, sec_house)
    which = os.environ["FH_TEST_WHAT"]
    if which == "all":                      # the planner's order: House before Expenses
        for mod in (sec_family, sec_house, sec_expenses, sec_big_purchases):
            mod.render(st)
    else:
        {"family": sec_family, "house": sec_house, "expenses": sec_expenses,
         "big": sec_big_purchases}[which].render_body(st)


@pytest.fixture
def draw(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("FH_TEST_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")

    def make(what, overrides):
        monkeypatch.setenv("FH_TEST_WHAT", what)
        at = AppTest.from_function(_script, default_timeout=60)
        at.session_state["user_overrides"] = dict(overrides)
        at.run()
        assert not at.exception, at.exception
        return at
    return make


def _keys(at):
    keys = set()
    for kind in ("number_input", "slider", "toggle", "radio", "selectbox", "button"):
        keys |= {w.key for w in getattr(at, kind) if w.key}
    return keys


def _text(at):
    return [c.value.replace("\\$", "$") for c in at.caption]


SINGLE = {"YOUR_AGE": 35, "PARTNER_AGE": 0, "CHILDREN": [], "SPEND_RENT_MONTHLY": 2_000,
          "HOME_VALUE": 0, "MORTGAGE_MONTHLY": 0, "TARGET_RETIREMENT_AGE": 60}


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def test_sections_render_for_a_single_household(draw):
    at = draw("all", SINGLE)
    assert [e.label for e in at.get("status")]  # icon expanders == ["Family", "House", "Expenses", "Big purchases & goals"]
    assert "No children in the plan." in _text(at)
    keys = _keys(at)
    assert {"se_kids_n", "se_rent_own", "se_rent_monthly"} <= keys
    assert not [k for k in keys if k.startswith("se_kid") and k != "se_kids_n"]


def test_sections_render_for_a_couple_with_children(draw):
    at = draw("all", _fixture("couple_three_kids.json"))
    keys = _keys(at)
    assert {"se_kids_n", "se_kid0_age", "se_kid2_in", "se_kid0_cost", "se_kid0_leaves",
            "se_kid0_college", "se_rent_own", "se_home_value", "se_mortgage_monthly",
            "se_mortgage_years", "bp_add_move"} <= keys
    assert at.number_input(key="se_kids_n").value == 3
    assert any("at home now" in c for c in _text(at))
    assert any(c.startswith("Housing costs") for c in _text(at))


def test_the_summaries_follow_an_edit_in_the_same_run(draw):
    at = draw("family", {**SINGLE, "CHILDREN": [{"years_until_birth": -5, "monthly_cost": 1_000,
                                                 "leaves_home_age": 18}]})
    assert any("1 child at home now, $1,000/mo today" in c for c in _text(at))
    at.number_input(key="se_kid0_cost").set_value(1_500).run()
    assert any("$1,500/mo today" in c for c in _text(at))
    house = draw("house", SINGLE)
    house.number_input(key="se_rent_monthly").set_value(2_600).run()
    assert any(c.startswith("Housing costs $2,600/mo this year: rent.") for c in _text(house))


# --------------------------------------------------------------------------
# The moved widgets keep their keys, and live in one place only
# --------------------------------------------------------------------------

OWNER = {"YOUR_AGE": 40, "PARTNER_AGE": 0, "HOME_VALUE": 600_000, "MORTGAGE_BALANCE": 300_000,
         "MORTGAGE_MONTHLY": 2_800, "MORTGAGE_YEARS_REMAINING": 20,
         "MORTGAGE_RATE_FOR_PAYOFF": 0.05, "TARGET_RETIREMENT_AGE": 60,
         "HOME_EVENTS": [{"age": 50, "action": "sell_buy", "price": 700_000, "down_pct": 0.2,
                          "rate": 0.06, "years": 30, "costs": 10_000}],
         "EXTRA_MORTGAGE_PAYMENT_ANNUAL": 12_000}


def test_house_widgets_keep_their_keys(draw):
    keys = _keys(draw("house", OWNER))
    assert {"se_rent_own", "se_home_value", "se_mortgage_monthly", "se_mortgage_balance",
            "se_mortgage_years", "se_mortgage_rate", "bp_ev0_kind", "bp_ev0_price",
            "bp_ev0_age", "bp_ev0_sell", "bp_add_move", "bp_new_home_escrow_pct",
            "bp_home_cost_basis", "bp_extra_mortgage"} <= keys


def test_moved_widgets_are_not_drawn_in_their_old_sections(draw):
    expenses = _keys(draw("expenses", OWNER))
    assert not [k for k in expenses if k.startswith(("se_kid", "se_mortgage", "se_home", "se_rent"))]
    big = _keys(draw("big", OWNER))
    assert not [k for k in big if k.startswith(("bp_ev", "bp_extra", "bp_new_home", "bp_home", "bp_add"))]
    assert {"bp_car_onetime_enable", "bp_car_recurring_enable", "bp_vacation_enable"} <= big
    assert "se_kids_n" not in _keys(draw("house", OWNER))


def test_every_moved_key_is_still_synced_from_a_profile():
    from utils.widget_sync import DIRECT_MAPPINGS
    for key in ("se_home_value", "se_mortgage_balance", "se_mortgage_monthly", "se_mortgage_years",
                "se_mortgage_rate", "se_rent_monthly", "bp_extra_mortgage"):
        assert key in DIRECT_MAPPINGS, key


def test_a_profile_still_loads_into_the_moved_widgets(draw):
    from retirement_sim import config as cfg
    ov = _fixture("couple_three_kids.json")
    at = draw("all", ov)
    assert at.session_state["user_overrides"]["CHILDREN"] == cfg.children_in(ov)
    assert at.session_state["user_overrides"]["HOME_VALUE"] == ov["HOME_VALUE"]


# --------------------------------------------------------------------------
# Order in the planner
# --------------------------------------------------------------------------

def test_planner_renders_the_sections_in_the_new_order():
    src = open(os.path.join(_UI, "app.py"), encoding="utf-8").read()
    body = src[src.index("    with st.sidebar:\n        # Linear walkthrough"):]
    body = body[:body.index('_safe_render("components.faq")')]
    order = re.findall(r'_safe_render\("components\.(\w+)"\)', body)
    assert order == ["sec_about_you", "sec_family", "account_inputs", "sec_income", "sec_taxes",
                     "sec_house", "sec_expenses", "sec_big_purchases", "sec_savings",
                     "sec_retirement_goals", "sec_early_access", "sec_assumptions"]
    # Expenses reads House's rent-or-own radio, so House must come first.
    assert order.index("sec_house") < order.index("sec_expenses")


def test_section_labels_and_icons():
    labels = {}
    for name in ("sec_family", "sec_house"):
        tree = ast.parse(open(os.path.join(_UI, "components", name + ".py"), encoding="utf-8").read())
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and getattr(n.func, "id", "") == "section_expander")
        labels[name] = (call.args[1].value, call.args[2].value)
    assert labels == {"sec_family": ("Family", "family_restroom"), "sec_house": ("House", "home")}


# --------------------------------------------------------------------------
# The summary lines, for a synthetic household
# --------------------------------------------------------------------------

def test_family_summary_counts_kids_at_home_and_when_the_last_leaves():
    from components.sec_family import family_summary, _summary_line
    kid = {"leaves_home_age": 18, "college_funding_pct": 0.0}
    ov = {"YOUR_AGE": 40, "CHILDREN": [
        {**kid, "years_until_birth": -5, "monthly_cost": 1_000},      # 5 today
        {**kid, "years_until_birth": 2, "monthly_cost": 800},         # not born yet
        {**kid, "years_until_birth": -20, "monthly_cost": 500}]}      # grown up, left at 38
    s = family_summary(ov)
    assert (s["children"], s["at_home"], s["monthly_cost"], s["last_leaves_age"]) == (3, 1, 1_000, 60)
    assert _summary_line(s) == "1 child at home now, \\$1,000/mo today. The last one leaves home when you're 60."
    gone = family_summary({"YOUR_AGE": 60, "CHILDREN": [{**kid, "years_until_birth": -25,
                                                        "monthly_cost": 500}]})
    assert _summary_line(gone) == "All your children have left home."
    assert _summary_line(family_summary({"YOUR_AGE": 30, "CHILDREN": []})) == "No children in the plan."
    later = family_summary({"YOUR_AGE": 30, "CHILDREN": [{**kid, "years_until_birth": 3,
                                                         "monthly_cost": 900}]})
    assert _summary_line(later) == "No children at home yet. The last one leaves home when you're 51."


def test_family_summary_uses_the_same_rule_as_the_planner_total():
    """Kids at home today add exactly their monthly cost to compute_expenses_today."""
    from components.sec_family import family_summary
    from utils.derived import compute_expenses_today
    kid = {"leaves_home_age": 18, "college_funding_pct": 0.0, "years_until_birth": -4}
    base = {**SINGLE, "PARTNER_OTHER_MONTHLY": 0}
    two = {**base, "CHILDREN": [{**kid, "monthly_cost": 700}, {**kid, "monthly_cost": 300}]}
    gap = compute_expenses_today(two) - compute_expenses_today({**base, "CHILDREN": []})
    assert gap == family_summary(two)["monthly_cost"] * 12 == 12_000


def test_house_summary_for_an_owner_with_and_without_extra_payments():
    from components.sec_house import house_summary, _summary_lines
    from utils.derived import mortgage_schedule
    ov = {k: v for k, v in OWNER.items() if k != "HOME_EVENTS"}
    s = house_summary(ov)
    assert s["kind"] == "mortgage" and s["monthly"] == pytest.approx(2_800)
    assert s["monthly_extra"] == pytest.approx(1_000)
    assert s["payoff_age_no_extra"] == 60                         # 20 years left at 40
    assert s["payoff_age"] < 60
    assert s["payoff_age"] == mortgage_schedule(ov, range(40, 101))["payoff_age"]
    lines = _summary_lines(s)
    assert lines[0] == ("Housing costs \\$2,800/mo this year: mortgage payment, with property "
                        "tax and insurance. Plus \\$1,000/mo extra principal.")
    assert lines[1] == f"Mortgage paid off at {s['payoff_age']} with your extra payments, 60 without."
    plain = house_summary({**ov, "EXTRA_MORTGAGE_PAYMENT_ANNUAL": 0})
    assert plain["payoff_age"] == plain["payoff_age_no_extra"] == 60
    assert _summary_lines(plain) == [
        "Housing costs \\$2,800/mo this year: mortgage payment, with property tax and insurance.",
        "Mortgage paid off at 60."]


def test_house_summary_for_a_renter_and_a_paid_off_owner():
    from components.sec_house import house_summary, _summary_lines
    renter = house_summary(SINGLE)
    assert renter["kind"] == "rent" and renter["monthly"] == pytest.approx(2_000)
    assert renter["payoff_age"] is None and len(_summary_lines(renter)) == 1
    paid = house_summary({"YOUR_AGE": 62, "HOME_VALUE": 500_000, "MORTGAGE_BALANCE": 0,
                          "MORTGAGE_MONTHLY": 0, "MORTGAGE_YEARS_REMAINING": 0})
    assert paid["kind"] == "owned" and paid["payoff_age"] is None
    assert paid["monthly"] == pytest.approx(500_000 * 0.0135 / 12)
    assert "property tax and insurance, no mortgage" in _summary_lines(paid)[0]
