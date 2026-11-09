"""Big purchases & goals now live at the end of Expenses, and Early retirement
access at the end of Retirement. Neither is a sidebar section of its own.

Widget keys, override keys and stored values did not change, so a saved profile
loads exactly as before.
"""
import ast
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

CAR_VACATION_KEYS = {"bp_car_onetime_enable", "bp_car_recurring_enable", "bp_vacation_enable"}
EARLY_ACCESS_KEYS = {"ea_rule55", "ea_sepp", "ea_ladder", "ea_coast"}

PROFILE = {
    "CAR_ONETIME_ENABLED": True, "CAR_ONETIME_AGE": 45, "CAR_ONETIME_AMOUNT": 33_000,
    "CAR_RECURRING_ENABLED": True, "CAR_RECURRING_START_AGE": 50,
    "CAR_RECURRING_EVERY_YEARS": 9, "CAR_RECURRING_AMOUNT": 28_000,
    "RETIREMENT_VACATION_ENABLED": True, "RETIREMENT_VACATION_ANNUAL": 17_000,
    "RETIREMENT_VACATION_UNTIL_AGE": 72,
    "RULE_OF_55_ENABLED": True, "SEPP_72T_ENABLED": True, "SEPP_72T_START_AGE": 52,
    "SEPP_72T_RATE": 0.04, "SEPP_72T_CARVEOUT": 400_000,
    "ROTH_LADDER_ENABLED": True, "COAST_FIRE_ENABLED": True, "COAST_FIRE_AGE": 48,
}


def _script():
    import os
    import sys
    sys.path[:0] = [os.environ["MS_TEST_UI"], os.path.dirname(os.environ["MS_TEST_UI"])]
    import streamlit as st
    from components import sec_expenses, sec_retirement_goals
    {"expenses": sec_expenses, "retirement": sec_retirement_goals}[os.environ["MS_TEST_WHAT"]].render(st)


@pytest.fixture
def draw(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("MS_TEST_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")

    def make(what, overrides):
        monkeypatch.setenv("MS_TEST_WHAT", what)
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


def _labels(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    return [(c.args[1].value, c.args[2].value) for c in ast.walk(tree)
            if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "section_expander"]


def _sublabels(at):
    out = []
    for m in at.markdown:
        txt = m.value
        if "text-transform: uppercase" in txt:
            out.append(txt.split(">", 1)[1].split("<", 1)[0])
    return out


def test_old_sections_have_no_expander_of_their_own():
    comp = os.path.join(_UI, "components")
    assert _labels(os.path.join(comp, "sec_big_purchases.py")) == []
    assert _labels(os.path.join(comp, "sec_early_access.py")) == []
    assert _labels(os.path.join(comp, "sec_expenses.py")) == [("Expenses", "shopping_cart")]
    assert _labels(os.path.join(comp, "sec_retirement_goals.py")) == [("Retirement", "flag")]


def test_the_old_modules_still_expose_render_body():
    from components import sec_big_purchases, sec_early_access
    assert callable(sec_big_purchases.render_body)
    assert callable(sec_early_access.render_body)


def test_car_and_vacation_toggles_sit_inside_expenses(draw):
    at = draw("expenses", load_sample_household())
    assert CAR_VACATION_KEYS <= _keys(at)
    assert [e.label for e in at.get("status")] == ["Expenses"]
    labels = _sublabels(at)
    assert labels[-3:] == ["Current spending", "Car", "Retirement vacation (early years)"]
    assert labels.index("Monthly spending") < labels.index("Car")


def test_early_access_toggles_sit_inside_retirement(draw):
    at = draw("retirement", load_sample_household())
    assert EARLY_ACCESS_KEYS <= _keys(at)
    assert [e.label for e in at.get("status")] == ["Retirement"]
    labels = _sublabels(at)
    assert labels.index("Success target") < labels.index("Early retirement access")
    assert labels[labels.index("Early retirement access") + 1].startswith("1 ")
    assert labels[-1].startswith("5 ")


def test_moved_blocks_are_not_drawn_twice(draw):
    assert not (EARLY_ACCESS_KEYS & _keys(draw("expenses", load_sample_household())))
    assert not (CAR_VACATION_KEYS & _keys(draw("retirement", load_sample_household())))


def test_a_saved_profile_loads_unchanged_into_the_merged_sections(draw):
    base = load_sample_household()
    ov = {**base, **PROFILE}
    exp = draw("expenses", ov)
    assert exp.toggle(key="bp_car_onetime_enable").value is True
    assert exp.number_input(key="bp_car_onetime_age").value == 45
    assert exp.number_input(key="bp_car_onetime_amount").value == 33_000
    assert exp.number_input(key="bp_car_recurring_start").value == 50
    assert exp.number_input(key="bp_car_recurring_every").value == 9
    assert exp.number_input(key="bp_car_recurring_amount").value == 28_000
    assert exp.toggle(key="bp_vacation_enable").value is True
    assert exp.number_input(key="bp_vacation_annual").value == 17_000
    assert exp.number_input(key="bp_vacation_until").value == 72
    ret = draw("retirement", ov)
    for key in ("ea_rule55", "ea_sepp", "ea_ladder", "ea_coast"):
        assert ret.toggle(key=key).value is True, key
    assert ret.number_input(key="ea_sepp_age").value == 52
    assert ret.number_input(key="ea_sepp_rate").value == pytest.approx(4.0)
    assert ret.number_input(key="ea_sepp_carveout").value == 400_000
    assert ret.number_input(key="ea_coast_age").value == 48
    # Rendering must not rewrite what the profile stored
    for at in (exp, ret):
        got = at.session_state["user_overrides"]
        for k, v in PROFILE.items():
            assert got[k] == pytest.approx(v), k


def test_turning_a_toggle_on_still_writes_its_override(draw):
    exp = draw("expenses", load_sample_household())
    exp.toggle(key="bp_car_onetime_enable").set_value(True).run()
    assert exp.session_state["user_overrides"]["CAR_ONETIME_ENABLED"] is True
    exp.toggle(key="bp_vacation_enable").set_value(True).run()
    assert exp.session_state["user_overrides"]["RETIREMENT_VACATION_ENABLED"] is True
    ret = draw("retirement", load_sample_household())
    ret.toggle(key="ea_rule55").set_value(True).run()
    assert ret.session_state["user_overrides"]["RULE_OF_55_ENABLED"] is True
    ret.toggle(key="ea_ladder").set_value(True).run()
    assert ret.session_state["user_overrides"]["ROTH_LADDER_ENABLED"] is True
