"""Sidebar inputs for housing, healthcare and retirement lifestyle (AppTest).

Big purchases: the "Add a move" list writes HOME_EVENTS; an old plan's single
house move shows up in it with its exact loan and payment. Expenses: the current
loan's rate. Assumptions: marketplace prices (replacing a dead healthcare box).
Retirement goals: go-go extra and later-years drop.
"""
import os
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.conftest import load_sample_household  # noqa: E402


def _section_script():
    import os
    import sys
    sys.path.insert(0, os.environ["HOUSING_TEST_UI_DIR"])
    import streamlit as st
    import importlib
    importlib.import_module("components." + os.environ["HOUSING_TEST_SECTION"]).render_body(st)


@pytest.fixture
def section(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("HOUSING_TEST_UI_DIR", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")

    def make(name, **overrides):
        monkeypatch.setenv("HOUSING_TEST_SECTION", name)
        at = AppTest.from_function(_section_script, default_timeout=60)
        at.session_state["user_overrides"] = dict(overrides)
        at.run()
        assert not at.exception, at.exception
        return at
    return make


RENTER = {"YOUR_AGE": 27, "PARTNER_AGE": 27, "SPEND_RENT_MONTHLY": 2_000,
          "HOME_VALUE": 0, "MORTGAGE_MONTHLY": 0, "TARGET_RETIREMENT_AGE": 60}


def test_add_a_move_for_a_renter(section):
    at = section("sec_big_purchases", **RENTER)
    at.button(key="bp_add_move").click().run()
    events = at.session_state["user_overrides"]["HOME_EVENTS"]
    assert len(events) == 1 and events[0]["action"] == "buy" and events[0]["age"] == 32
    assert at.selectbox(key="bp_ev0_kind").value == 0
    at.number_input(key="bp_ev0_price").set_value(500_000).run()
    at.number_input(key="bp_ev0_age").set_value(30).run()
    (e,) = at.session_state["user_overrides"]["HOME_EVENTS"]
    assert e["price"] == 500_000 and e["age"] == 30 and "loan" not in e
    assert any("buy for $500,000" in c.value.replace("\\$", "$") for c in at.caption)
    # A second move after buying offers the owner's choices.
    at.button(key="bp_add_move").click().run()
    at.selectbox(key="bp_ev1_kind").set_value(1).run()          # "Sell and rent"
    events = at.session_state["user_overrides"]["HOME_EVENTS"]
    assert events[1]["action"] == "sell_rent" and "selling_cost_pct" in events[1]
    at.button(key="bp_ev0_del").click().run()
    assert len(at.session_state["user_overrides"]["HOME_EVENTS"]) == 1


def test_old_plan_house_move_is_listed_with_its_exact_loan(section):
    ov = load_sample_household()
    at = section("sec_big_purchases", **ov)
    new = at.session_state["user_overrides"]
    assert new["HOUSE_MOVE_ENABLED"] is False
    (e,) = new["HOME_EVENTS"]
    assert e["action"] == "sell_buy" and e["age"] == ov["HOUSE_MOVE_AGE"]
    assert e["loan"] == ov["NEW_MORTGAGE_BALANCE"] and e["monthly"] == ov["NEW_MORTGAGE_MONTHLY"]
    from retirement_sim import config as cfg
    from utils.derived import housing_timeline
    assert housing_timeline(new) == housing_timeline(ov)          # same engine input
    assert cfg.HOUSE_MOVE_ENABLED is False
    # Editing a number drops the carried-over payment so it is re-derived.
    at.number_input(key="bp_ev0_rate").set_value(5.0).run()
    (e,) = at.session_state["user_overrides"]["HOME_EVENTS"]
    assert "monthly" not in e and e["rate"] == 0.05


def test_cost_basis_input_for_an_owner_who_sells(section):
    at = section("sec_big_purchases", YOUR_AGE=58, PARTNER_AGE=0, HOME_VALUE=650_000,
                 HOME_EVENTS=[{"age": 72, "action": "sell_rent", "rent": 2_500}])
    assert at.number_input(key="bp_home_cost_basis").value == 650_000
    assert at.session_state["user_overrides"].get("HOME_COST_BASIS") is None
    at.number_input(key="bp_home_cost_basis").set_value(200_000).run()
    assert at.session_state["user_overrides"]["HOME_COST_BASIS"] == 200_000


def test_current_loan_rate_input(section):
    at = section("sec_expenses", YOUR_AGE=40, HOME_VALUE=600_000, MORTGAGE_BALANCE=400_000,
                 MORTGAGE_MONTHLY=3_000, MORTGAGE_YEARS_REMAINING=25)
    assert at.number_input(key="se_mortgage_rate").value == pytest.approx(6.5)
    at.number_input(key="se_mortgage_rate").set_value(3.25).run()
    assert at.session_state["user_overrides"]["MORTGAGE_RATE_FOR_PAYOFF"] == pytest.approx(0.0325)
    renter = section("sec_expenses", **RENTER)
    assert "se_mortgage_rate" not in [w.key for w in renter.number_input]


def test_marketplace_price_inputs_replace_the_dead_box(section):
    at = section("sec_assumptions")
    keys = [w.key for w in at.number_input]
    assert "sa_hc_early" not in keys
    at.number_input(key="sa_aca_benchmark").set_value(800).run()
    at.number_input(key="sa_aca_child").set_value(450).run()
    ov = at.session_state["user_overrides"]
    assert ov["ACA_BENCHMARK_MONTHLY_AT_40"] == 800 and ov["ACA_CHILD_MONTHLY"] == 450


def test_lifestyle_inputs_follow_household_until_chosen(section):
    single = section("sec_retirement_goals", PARTNER_AGE=0, TARGET_RETIREMENT_AGE=68)
    assert single.number_input(key="rg_leisure_amount").value == 6_667
    assert single.session_state["user_overrides"].get("EARLY_RETIREMENT_LEISURE_INCREASE") is None
    assert any("Retiring at 68" in c.value and "until 73" in c.value and "from 78" in c.value
               for c in single.caption)
    couple = section("sec_retirement_goals", PARTNER_AGE=40, TARGET_RETIREMENT_AGE=60)
    assert couple.number_input(key="rg_leisure_amount").value == 10_000
    couple.number_input(key="rg_leisure_amount").set_value(4_000).run()
    couple.slider(key="rg_late_pct").set_value(25).run()
    couple.number_input(key="rg_late_from").set_value(80).run()
    ov = couple.session_state["user_overrides"]
    assert ov["EARLY_RETIREMENT_LEISURE_INCREASE"] == 4_000
    assert ov["LATE_RETIREMENT_LEISURE_DECREASE"] == pytest.approx(0.25)
    assert ov["LATE_RETIREMENT_START_AGE"] == 80


def test_new_widgets_restore_from_a_profile():
    from utils.widget_sync import DIRECT_MAPPINGS
    assert DIRECT_MAPPINGS["se_mortgage_rate"][1](0.0325) == pytest.approx(3.25)
    assert DIRECT_MAPPINGS["sa_aca_benchmark"][0] == "ACA_BENCHMARK_MONTHLY_AT_40"
    assert DIRECT_MAPPINGS["rg_late_pct"][1](0.15) == 15
    assert "bp_house_move_enable" not in DIRECT_MAPPINGS


def test_spending_chart_shows_the_go_go_extra():
    from components import spending_chart as sc
    assert sc._go_go_extra({"PARTNER_AGE": 0}, 65, 60) == pytest.approx(10_000 * 2 / 3)
    assert sc._go_go_extra({"PARTNER_AGE": 0}, 70, 60) == 0.0
    assert sc._go_go_extra({"PARTNER_AGE": 50}, 59, 60) == 0.0          # still working
    assert sc._go_go_extra({"PARTNER_AGE": 50, "EARLY_RETIREMENT_LEISURE_INCREASE": 3_000},
                           71, 68) == 3_000                              # late retiree


def test_spending_chart_housing_is_rent_then_mortgage():
    from components import spending_chart as sc
    ov = {"YOUR_AGE": 27, "SPEND_RENT_MONTHLY": 2_000, "SPEND_FOOD_MONTHLY": 500,
          "HOME_EVENTS": [{"age": 30, "action": "buy", "price": 450_000, "down_pct": 0.2,
                           "rate": 0.065, "years": 30}]}
    ages = list(range(27, 70))
    series, payoff = sc.build_category_series(ages, ov, {}, 60,
                                              inflation_factors=[1.03 ** i for i in range(len(ages))])
    label, _, housing = series[0]
    assert label == "Housing"
    assert housing[0] == 24_000 and housing[2] == pytest.approx(24_000 * 1.03 ** 2)  # rent inflates
    assert housing[3] == housing[4]                                       # the payment doesn't
    assert payoff == 60
