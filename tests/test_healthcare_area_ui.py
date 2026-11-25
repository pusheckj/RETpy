"""The side panel's healthcare-by-area controls (ui/components/sec_assumptions.py) and the
results-screen cliff note. AppTest drives the real Assumptions section; nothing here reads a
personal profile.
"""
import json
import os
import sys
from types import SimpleNamespace

import pytest

os.environ.setdefault("RETIREMENT_SIM_PROFILE", "/nonexistent/retirement-sim-test-profile.json")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components.profile_picker import PROFILES  # noqa: E402
from retirement_sim import healthcare_data as hd  # noqa: E402
from utils import health_area as ha  # noqa: E402
from utils import health_cliff as hc  # noqa: E402
from utils import widget_sync as ws  # noqa: E402

COUPLE = "Mid-career couple (40, kids)"


def _panel():
    import importlib
    import os
    import sys
    sys.path[:0] = [os.environ["HEALTH_TEST_UI"], os.path.dirname(os.environ["HEALTH_TEST_UI"])]
    import streamlit as st
    for name in ("sec_about_you", "sec_family", "sec_income", "sec_taxes", "sec_house",
                 "sec_expenses", "sec_debts", "account_inputs", "sec_investments",
                 "sec_retirement_goals", "sec_assumptions"):        # app.py's order
        importlib.import_module("components." + name).render(st)


def _open(monkeypatch, **extra):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("HEALTH_TEST_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    at = AppTest.from_function(_panel, default_timeout=120)
    overrides = {**PROFILES[COUPLE], **extra}
    at.session_state["user_overrides"] = overrides
    at.session_state["si_comp_customized"] = "YOUR_COMPENSATION_BY_AGE" in PROFILES[COUPLE]
    at.run()
    assert not at.exception, at.exception
    return at


def _text(at):
    return "\n".join(str(e.value) for kind in (at.caption, at.markdown) for e in kind)


def _ov(at):
    return at.session_state["user_overrides"]


def _use_zip(at, zip_code):
    at.text_input(key="sa_health_zip").set_value(zip_code)
    at.button(key="sa_health_zip_btn").click().run()
    assert not at.exception, at.exception
    return at


def test_without_an_area_the_flat_figures_say_they_are_2026(monkeypatch):
    at = _open(monkeypatch)
    assert "HEALTH_AREA" not in _ov(at)
    assert "2026 plan year" in _text(at)
    assert "2027 plan year" not in _text(at)


def test_a_zip_code_finds_the_area_and_fills_the_price_boxes(monkeypatch):
    at = _open(monkeypatch)
    _use_zip(at, "35004")
    ov = _ov(at)
    assert ov["HEALTH_AREA"] == "AL:3" and ov["HEALTH_PLAN"] == "silver"
    ref = hd.reference_prices("AL:3")
    assert ov["ACA_BENCHMARK_MONTHLY_AT_40"] == round(ref["benchmark_at_40"])
    assert ov["ACA_CHILD_MONTHLY"] == round(ref["child"])
    assert at.number_input(key="sa_aca_benchmark").value == round(ref["benchmark_at_40"])
    text = _text(at)
    assert "Alabama, rating area 3" in text and "2027 plan year" in text
    assert "BiggerPockets Money" in text
    # Dead-input guard: what the panel stored is what the engine is given.
    from utils.config_builder import build_config_overrides
    built = build_config_overrides(ov)
    assert built["ACA_AREA_KEY"] == "AL:3" and built["ACA_AREA_PLAN_RATIO"] == 1.0
    assert built["ACA_AREA_SILVER_MONTHLY"][40] == pytest.approx(ref["benchmark_at_40"], abs=0.01)
    assert "35004" not in json.dumps(ov, default=str)          # the ZIP itself is not kept
    assert at.text_input(key="sa_health_zip").value == ""
    assert "35004" not in json.dumps({k: str(v) for k, v in at.session_state.filtered_state.items()
                                      if k != "sa_health_zip_btn"}, default=str)


def test_the_grow_caption_shows_with_or_without_an_area(monkeypatch):
    for extra in ({}, {"HEALTH_AREA": "AL:1"}):
        at = _open(monkeypatch, **extra)
        assert "grow 6% a year" in _text(at) and "3\u00bc% above inflation" in _text(at)


def test_a_family_tier_state_shows_no_child_price(monkeypatch):
    at = _open(monkeypatch, HEALTH_AREA="NY:avg")
    assert at.number_input(key="sa_aca_child").disabled
    text = _text(at)
    assert "New York, statewide average" in text and "for a child" not in text
    ok = _open(monkeypatch, HEALTH_AREA="AL:1")
    assert not ok.number_input(key="sa_aca_child").disabled and "for a child" in _text(ok)


def test_a_bad_zip_changes_nothing_and_says_so(monkeypatch):
    at = _open(monkeypatch)
    _use_zip(at, "00000")
    assert "HEALTH_AREA" not in _ov(at)
    assert "was not found" in _text(at)


def test_the_state_button_uses_the_state_chosen_under_taxes(monkeypatch):
    at = _open(monkeypatch, STATE_CHOICE="TX")
    at.button(key="sa_health_state_btn").click().run()
    assert not at.exception, at.exception
    assert _ov(at)["HEALTH_AREA"] == "TX:avg"
    assert "Texas, statewide average" in _text(at)


def test_the_plan_type_reaches_the_overrides_and_back(monkeypatch):
    at = _open(monkeypatch, HEALTH_AREA="AL:1", HEALTH_PLAN="silver")
    at.radio(key="sa_health_plan").set_value("Lowest-cost Bronze").run()
    assert _ov(at)["HEALTH_PLAN"] == "bronze"
    from utils.config_builder import build_config_overrides
    assert 0 < build_config_overrides(_ov(at))["ACA_AREA_PLAN_RATIO"] < 1.0
    at.radio(key="sa_health_plan").set_value("Benchmark Silver").run()
    assert _ov(at)["HEALTH_PLAN"] == "silver"


def test_going_back_to_the_national_figures_restores_the_boxes(monkeypatch):
    at = _open(monkeypatch)
    _use_zip(at, "35004")
    at.button(key="sa_health_clear_btn").click().run()
    assert not at.exception, at.exception
    ov = _ov(at)
    assert "HEALTH_AREA" not in ov and "HEALTH_PLAN" not in ov
    assert ov["ACA_BENCHMARK_MONTHLY_AT_40"] == 625 and ov["ACA_CHILD_MONTHLY"] == 390
    assert at.number_input(key="sa_aca_benchmark").value == 625
    assert "2026 plan year" in _text(at)


def test_a_loaded_profile_with_an_area_shows_it_and_keeps_its_prices(monkeypatch):
    ref = hd.reference_prices("AL:1")
    at = _open(monkeypatch, HEALTH_AREA="AL:1", HEALTH_PLAN="bronze")
    assert at.radio(key="sa_health_plan").value == "Lowest-cost Bronze"
    assert "Alabama, rating area 1" in _text(at)
    # The boxes were not in the profile: they start at the area's figures, not the national 625.
    assert at.number_input(key="sa_aca_benchmark").value == round(ref["benchmark_at_40"])


def test_widget_sync_maps_the_plan_type():
    st = SimpleNamespace(session_state={"user_overrides": {"HEALTH_AREA": "AL:1", "HEALTH_PLAN": "bronze"}})
    ws.sync_widgets_from_overrides(st)
    assert st.session_state["sa_health_plan"] == "Lowest-cost Bronze"
    st = SimpleNamespace(session_state={"user_overrides": {}, "sa_health_plan": "Lowest-cost Bronze"})
    ws.reset_input_widget_state(st)
    assert "sa_health_plan" not in st.session_state


def test_a_zip_left_in_the_box_is_dropped_on_a_profile_switch():
    st = SimpleNamespace(session_state={"sa_health_zip": "35004", "sa_health_msg": "x"})
    ws.reset_input_widget_state(st)
    assert "sa_health_zip" not in st.session_state


# ------------------------------------------------------------------ the cliff note

def _results(by_year):
    return {"primary_result": {"aca_cliff_by_year": by_year}}


def test_the_cliff_note_names_the_year_and_the_credit_lost():
    msg = hc.message({"age": 57, "year": 2033, "lost": 12_119.0, "share": 0.6}, 2027)
    assert "2033" in msg and "age 57" in msg and "$12,100" in msg and "400%" in msg
    assert "60% of simulations" in msg and "2027" in msg
    assert all(len(sentence.split()) <= 20 for sentence in msg.split(". "))


def test_a_tiny_credit_loss_is_not_worth_a_warning():
    shown = []
    st = SimpleNamespace(warning=lambda t: shown.append(t))
    small = hc.compact({55: [40.0] * 4})                      # would read "about $0"
    hc.render_note(st, _results(small), {"YOUR_AGE": 50}, current_year=2026)
    assert shown == []
    # The first year over a real amount is named, not the first year over the cliff.
    mixed = hc.compact({55: [40.0] * 4, 56: [900.0] * 4})
    hc.render_note(st, _results(mixed), {"YOUR_AGE": 50}, current_year=2026)
    assert len(shown) == 1 and "age 56" in shown[0]


def test_the_cliff_year_falls_back_to_the_configs_age_not_zero():
    from retirement_sim import config as cfg
    shown = []
    st = SimpleNamespace(warning=lambda t: shown.append(t))
    hc.render_note(st, _results(hc.compact({cfg.YOUR_AGE + 3: [5_000.0] * 4})), {}, current_year=2026)
    assert "2029" in shown[0]


def test_the_cliff_note_is_drawn_only_when_the_plan_crosses():
    shown = []
    st = SimpleNamespace(warning=lambda t: shown.append(t))
    by_year = hc.compact({55: [None] * 4, 56: [7_000.0] * 4})
    hc.render_note(st, _results(by_year), {"YOUR_AGE": 50, "HEALTH_AREA": "AL:1"}, current_year=2026)
    assert len(shown) == 1 and "2032" in shown[0] and "2027" in shown[0]
    shown.clear()
    hc.render_note(st, _results(hc.compact({55: [None] * 4})), {"YOUR_AGE": 50}, current_year=2026)
    hc.render_note(st, None, {"YOUR_AGE": 50}, current_year=2026)
    hc.render_note(st, {"primary_result": {}}, {"YOUR_AGE": 50}, current_year=2026)
    assert shown == []
    hc.render_note(st, _results(by_year), {"YOUR_AGE": 50}, current_year=2026)    # no area: 2026 rules
    assert "2026" in shown[0]


def test_the_spending_chart_labels_the_health_band_with_its_plan_year():
    from components import spending_chart as sc
    ages = list(range(58, 66))
    health = {a: 20_000.0 for a in ages}
    ov = {"YOUR_AGE": 58, "SPEND_FOOD_MONTHLY": 500}
    series, _ = sc.build_category_series(ages, ov, {}, 58, health_by_age=health)
    assert "Health insurance (ACA 2026 prices, Medicare)" in {s[0] for s in series}
    series, _ = sc.build_category_series(ages, {**ov, "HEALTH_AREA": "AL:1"}, {}, 58, health_by_age=health)
    assert "Health insurance (ACA 2027 prices, Medicare)" in {s[0] for s in series}


def test_a_zip_typed_but_not_applied_is_not_saved_to_the_browser():
    """Remember me and the tab copy hold the plan's overrides, never the ZIP box."""
    from utils import persist
    state = {"app_mode": "full", "remember_device": True, "sa_health_zip": "35004",
             "user_overrides": {"HEALTH_AREA": "AL:3", "HEALTH_PLAN": "silver"}}
    tab, device, _prefs = persist.build_payload(state)
    assert "35004" not in json.dumps(tab) + json.dumps(device)
    assert "AL:3" in json.dumps(tab)


def _chart():
    import os
    import sys
    sys.path[:0] = [os.environ["HEALTH_TEST_UI"], os.path.dirname(os.environ["HEALTH_TEST_UI"])]
    import streamlit as st
    from components import spending_chart
    spending_chart.render(st, st.session_state["_results"])


def test_the_results_screen_shows_the_cliff_note_under_the_spending_chart(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("HEALTH_TEST_UI", _UI)
    by_year = hc.compact({54: [None] * 4, 55: [9_000.0] * 3 + [None]})
    ov = {**PROFILES[COUPLE], "HEALTH_AREA": "AL:1", "YOUR_AGE": 40}
    at = AppTest.from_function(_chart, default_timeout=120)
    at.session_state["user_overrides"] = ov
    at.session_state["_results"] = {"primary_result": {"aca_cliff_by_year": by_year, "health_by_year": []}}
    at.run()
    assert not at.exception, at.exception
    warnings = [w.value for w in at.warning]
    assert len(warnings) == 1 and "age 55" in warnings[0] and "75% of simulations" in warnings[0]
    assert "2027 plan year" in warnings[0] and "$9,000" in warnings[0].replace("\\", "")
    assert any("2027 plan year" in str(c.value) for c in at.caption)
    at.session_state["_results"] = {"primary_result": {"aca_cliff_by_year": hc.compact({54: [None] * 4})}}
    at.run()
    assert not at.warning
