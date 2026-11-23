"""The "All conservative / typical assumptions" buttons (ui/components/assumption_presets.py).

AppTest drives the real side-panel sections in the app's order, so a click goes through the
same callback, widget sync and redraw as in the browser. Every test points the profile
loader at a file that does not exist: nothing here reads a personal profile.
"""
import os
import re
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
from retirement_sim import config as cfg  # noqa: E402
from utils import assumption_presets as ap  # noqa: E402
from utils import widget_sync as ws  # noqa: E402

COUPLE = "Mid-career couple (40, kids)"
SINGLE = "Young professional (28, single)"
MEDIAN = "Median US 25-year-old household"
APP = os.path.join(_UI, "app.py")


@pytest.fixture(autouse=True)
def _pin_the_year(monkeypatch):
    """The Conservative Social Security share depends on the year."""
    monkeypatch.setattr(cfg, "CURRENT_YEAR", 2026)


def _panel():
    import importlib
    import os
    import sys
    sys.path[:0] = [os.environ["ASSUME_TEST_UI"], os.path.dirname(os.environ["ASSUME_TEST_UI"])]
    import streamlit as st
    for name in ("sec_about_you", "sec_family", "sec_income", "sec_taxes", "sec_house",
                 "sec_expenses", "sec_debts", "account_inputs", "sec_investments",
                 "sec_retirement_goals", "sec_assumptions"):        # app.py's order
        importlib.import_module("components." + name).render(st)


def _open(monkeypatch, profile=COUPLE, **extra):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("ASSUME_TEST_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    at = AppTest.from_function(_panel, default_timeout=120)
    overrides = dict(PROFILES[profile])
    overrides.update(extra)
    at.session_state["user_overrides"] = overrides
    at.session_state["si_comp_customized"] = "YOUR_COMPENSATION_BY_AGE" in PROFILES[profile]
    at.run()
    assert not at.exception, at.exception
    return at


def _click(at, name):
    at.button(key=f"assume_btn_{name}").click().run()
    assert not at.exception, at.exception
    return at


def _text(at):
    return "\n".join(str(e.value) for kind in (at.caption, at.markdown) for e in kind)


def _snapshot(at):
    ov = at.session_state["user_overrides"]
    return {k: ov.get(k, ap.MISSING) for k in ap.PRESET_KEYS}


def _expected(at, name):
    ov = at.session_state["user_overrides"]
    return {k: v for k, (v, _) in
            ap.compute_preset(name, ov, bool(at.session_state["si_comp_customized"])).items()}


def _buttons(at):
    return {b.key for b in at.button if b.key}


# ------------------------------------------------------------------ clicking

def test_typical_click_writes_the_preset_and_syncs_the_widgets(monkeypatch):
    at = _open(monkeypatch)
    want = _expected(at, "typical")
    _click(at, "typical")
    ov = at.session_state["user_overrides"]
    for key, value in want.items():
        assert ov[key] == pytest.approx(value), key
    assert at.radio(key="sa_scenario").value == "Conservative"
    assert at.radio(key="sa_glide_shape").value == "Bond tent"
    assert at.slider(key="ay_plan_until").value == 100
    assert at.slider(key="ay_partner_plan_until").value == 100
    assert at.slider(key="rg_ss_payable").value == pytest.approx(78.0)
    assert at.slider(key="rg_ltc_prob").value == 15
    assert at.slider(key="sa_stock_alloc").value == pytest.approx(60.0)
    assert at.slider(key="sa_fee_bps").value == 10
    assert at.toggle(key="ea_ladder").value is True
    assert at.toggle(key="ea_rule55").value is True
    text = _text(at)
    assert "Now using: Typical assumptions." in text
    assert re.search(r"What changed \(\d+ settings?\)", text)
    assert "Return scenario: " in text and "→" in text
    assert "Click Run simulation to see results with these numbers." in text
    assert "For long plans, Typical uses the Conservative return set." in text
    assert "assume_undo" in _buttons(at)


def test_conservative_click_writes_the_preset(monkeypatch):
    at = _open(monkeypatch)
    want = _expected(at, "conservative")
    _click(at, "conservative")
    ov = at.session_state["user_overrides"]
    for key, value in want.items():
        assert ov[key] == pytest.approx(value), key
    assert at.radio(key="sa_scenario").value == "Forward-looking"
    assert at.slider(key="sa_fee_bps").value == 30
    assert at.slider(key="rg_target_success").value == 95
    assert at.toggle(key="sa_ret_spend").value is False
    assert "Now using: Conservative assumptions." in _text(at)
    assert "For long plans, Typical uses" not in _text(at)


def test_the_what_changed_count_matches_the_lines(monkeypatch):
    at = _open(monkeypatch)
    _click(at, "typical")
    last = at.session_state["assume_last"]
    n = len(last["changes"])
    assert f"What changed ({n} settings)" in _text(at)
    text = _text(at)
    for key in last["changes"]:
        line = f"{ap.LABELS[key]}: {ap.format_value(key, last['old'][key])} → {ap.format_value(key, last['after'][key])}"
        assert line.replace("$", "\\$") in text, line
    assert n >= 5


def test_every_preset_value_sits_in_its_widget(monkeypatch):
    at = _open(monkeypatch)
    _click(at, "conservative")
    notes = at.session_state["_sync_notes"] if "_sync_notes" in at.session_state else {}
    assert not notes


def test_clicking_the_other_button_replaces_the_first(monkeypatch):
    at = _open(monkeypatch)
    _click(at, "typical")
    _click(at, "conservative")
    assert "Now using: Conservative assumptions." in _text(at)
    ov = at.session_state["user_overrides"]
    assert ov["TARGET_SUCCESS_RATE"] == pytest.approx(0.95)


# ------------------------------------------------------------------ undo

def test_undo_restores_exactly(monkeypatch):
    at = _open(monkeypatch)
    before = _snapshot(at)
    widgets_before = {k: at.session_state[k] for k in ("sa_scenario", "sa_inflation", "ay_plan_until",
                                                        "rg_ss_payable", "rg_ltc_prob")}
    _click(at, "typical")
    assert _snapshot(at) != before
    at.button(key="assume_undo").click().run()
    assert not at.exception, at.exception
    after = _snapshot(at)
    for key, old in before.items():
        if old is ap.MISSING:
            assert after[key] is ap.MISSING or key in ("GLIDE_PATH_TENT_RISE_YEARS",), key
        else:
            assert after[key] == pytest.approx(old) if not isinstance(old, (str, bool)) else after[key] == old, key
    for key, old in widgets_before.items():
        assert at.session_state[key] == old, key
    assert "assume_last" not in at.session_state
    assert "assume_undo" not in _buttons(at)
    assert "Back to your settings from before you picked a preset." in _text(at)
    assert "Now using: Typical" not in _text(at)


def test_undo_pops_keys_that_were_missing(monkeypatch):
    at = _open(monkeypatch)
    ov = at.session_state["user_overrides"]
    ov.pop("RULE_OF_55_ENABLED", None)
    ov.pop("GLIDE_PATH_TENT_RISE_YEARS", None)
    at.session_state["user_overrides"] = ov
    at.session_state["assume_probe"] = 1               # keeps the state object alive across runs
    at.run()
    _click(at, "typical")
    assert at.session_state["user_overrides"]["RULE_OF_55_ENABLED"] is True
    assert at.toggle(key="ea_rule55").value is True
    at.button(key="assume_undo").click().run()
    assert not at.exception, at.exception
    assert "assume_last" not in at.session_state
    # The keys that were missing are missing again, or the widgets re-seeded them to the default.
    ov = at.session_state["user_overrides"]
    for key in ("RULE_OF_55_ENABLED", "GLIDE_PATH_TENT_RISE_YEARS"):
        assert key not in ov or ov[key] == getattr(cfg, key), (key, ov.get(key))
    assert at.toggle(key="ea_rule55").value is bool(cfg.RULE_OF_55_ENABLED)


def test_unit_undo_is_exact_without_the_page(monkeypatch):
    """The snapshot logic alone: keys that were missing are missing again."""
    ss = {"user_overrides": {"YOUR_AGE": 40, "PARTNER_AGE": 0, "TARGET_RETIREMENT_AGE": 55,
                             "STOCK_ALLOCATION": 0.9}}
    st = SimpleNamespace(session_state=ss)
    original = dict(ss["user_overrides"])
    ap.apply_preset(st, "typical")
    assert ss["user_overrides"]["STOCK_ALLOCATION"] != 0.9
    assert "ACTIVE_RETURN_SCENARIO" in ss["user_overrides"]
    assert ap.undo_available(st)
    ap.undo_preset(st)
    assert ss["user_overrides"] == original
    assert "assume_last" not in ss
    assert ss["sa_stock_alloc"] == pytest.approx(90.0)          # a key that existed goes back
    assert "sa_scenario" not in ss and "rg_ss_payable" not in ss  # keys that did not exist re-seed


def test_unit_undo_refuses_when_a_key_was_edited_since():
    ss = {"user_overrides": {"YOUR_AGE": 40, "PARTNER_AGE": 0, "TARGET_RETIREMENT_AGE": 55}}
    st = SimpleNamespace(session_state=ss)
    ap.apply_preset(st, "conservative")
    assert ap.undo_available(st)
    ss["user_overrides"]["EXPECTED_INFLATION"] = 0.05
    assert not ap.undo_available(st)


# ------------------------------------------------------------------ custom, outdated, no-op

def test_a_manual_edit_shows_custom_and_removes_undo(monkeypatch):
    at = _open(monkeypatch)
    _click(at, "typical")
    at.slider(key="sa_inflation").set_value(3.5).run()
    assert not at.exception, at.exception
    text = _text(at)
    assert "Custom: you changed Expected inflation after picking Typical." in text
    assert "assume_undo" not in _buttons(at)
    assert "What changed" not in text


def test_custom_names_two_settings_then_counts_the_rest(monkeypatch):
    at = _open(monkeypatch)
    _click(at, "typical")
    at.slider(key="sa_inflation").set_value(3.5).run()
    at.slider(key="sa_fee_bps").set_value(60).run()
    at.slider(key="rg_target_success").set_value(75).run()
    text = _text(at)
    assert re.search(r"Custom: you changed .+ and .+ and 1 more after picking Typical\.", text), text


def test_a_changed_retirement_age_marks_the_preset_as_old(monkeypatch):
    at = _open(monkeypatch)
    _click(at, "typical")
    assert at.session_state["user_overrides"]["RULE_OF_55_ENABLED"] is True
    at.slider(key="ay_target_age").set_value(45).run()
    assert not at.exception, at.exception
    assert "set for your old plan" in _text(at)
    assert "Your situation changed. Click Typical again to update." in _text(at)
    _click(at, "typical")
    ov = at.session_state["user_overrides"]
    assert ov["RULE_OF_55_ENABLED"] is False          # retiring at 45: not a Rule of 55 case
    assert at.toggle(key="ea_rule55").value is False
    assert "Now using: Typical assumptions." in _text(at)


def test_clicking_twice_changes_nothing_and_keeps_the_undo(monkeypatch):
    at = _open(monkeypatch)
    original = _snapshot(at)
    _click(at, "typical")
    first = dict(at.session_state["user_overrides"])
    _click(at, "typical")
    assert dict(at.session_state["user_overrides"]) == first
    text = _text(at)
    assert "Your settings already match Typical. Nothing changed." in text
    assert "What changed" in text and "assume_undo" in _buttons(at)       # the first click can still be undone
    at.button(key="assume_undo").click().run()
    assert not at.exception, at.exception
    assert _snapshot(at)["EXPECTED_INFLATION"] == original["EXPECTED_INFLATION"]
    assert "Back to your settings from before you picked a preset." in _text(at)


def test_unit_a_second_click_keeps_the_first_snapshot():
    ss = {"user_overrides": {"YOUR_AGE": 40, "PARTNER_AGE": 0, "TARGET_RETIREMENT_AGE": 55}}
    st = SimpleNamespace(session_state=ss)
    ap.apply_preset(st, "typical")
    snap = ss["assume_last"]
    assert ap.undo_available(st) and "assume_noop" not in ss
    ap.apply_preset(st, "typical")
    assert ss["assume_last"] is snap and ap.undo_available(st)
    assert ss["assume_noop"] == "typical"
    ap.undo_preset(st)
    assert "assume_noop" not in ss and "assume_last" not in ss
    assert "EXPECTED_INFLATION" not in ss["user_overrides"]


def test_unit_a_match_with_missing_keys_still_gives_feedback():
    """Every value matches but a key is missing (it holds the default). The click writes
    the key and says nothing changed. It used to show nothing at all."""
    ss = {"user_overrides": {"YOUR_AGE": 40, "PARTNER_AGE": 0, "TARGET_RETIREMENT_AGE": 55}}
    st = SimpleNamespace(session_state=ss)
    ap.apply_preset(st, "typical")
    ss.pop("assume_last")
    plan = ap.compute_preset("typical", ss["user_overrides"], False)
    gone = next(k for k, (v, _) in plan.items() if ap._same(ap.default_for(k), v))
    del ss["user_overrides"][gone]
    ap.apply_preset(st, "typical")
    assert gone in ss["user_overrides"]
    assert ss["assume_noop"] == "typical" and "assume_last" not in ss
    assert ap.status(st)[0] == "typical"


def test_the_nothing_changed_line_shows_with_missing_keys(monkeypatch):
    at = _open(monkeypatch)
    _click(at, "typical")
    at.session_state["assume_last"] = None
    ov = at.session_state["user_overrides"]
    plan = ap.compute_preset("typical", ov, bool(at.session_state["si_comp_customized"]))
    gone = next(k for k, (v, _) in plan.items() if ap._same(ap.default_for(k), v))
    ov.pop(gone)
    at.session_state["user_overrides"] = ov
    _click(at, "typical")
    assert "Your settings already match Typical. Nothing changed." in _text(at)


# ------------------------------------------------------------------ situations

def test_glide_off_first_comes_on_with_in_range_sliders(monkeypatch):
    at = _open(monkeypatch, GLIDE_PATH_ENABLED=False)
    assert at.toggle(key="sa_glide_enable").value is False
    _click(at, "conservative")
    assert at.toggle(key="sa_glide_enable").value is True
    assert at.radio(key="sa_glide_shape").value == "Bond tent"
    assert at.slider(key="sa_glide_start").value == pytest.approx(50.0)
    assert at.slider(key="sa_glide_end").value == pytest.approx(70.0)
    assert at.slider(key="sa_tent_years").value == 15


def test_a_single_gets_no_partner_keys(monkeypatch):
    at = _open(monkeypatch, SINGLE)
    before = set(at.session_state["user_overrides"])
    _click(at, "typical")
    ov = at.session_state["user_overrides"]
    assert ov["PLAN_UNTIL_AGE"] == 100
    assert "PARTNER_PLAN_UNTIL_AGE" not in ov or "PARTNER_PLAN_UNTIL_AGE" in before
    assert "PARTNER_SALARY_GROWTH_RATE" not in ov or "PARTNER_SALARY_GROWTH_RATE" in before
    assert "assume_last" in at.session_state
    assert not [k for k in at.session_state["assume_last"]["after"] if k.startswith("PARTNER_")]


def test_a_couple_gets_both_partner_keys(monkeypatch):
    at = _open(monkeypatch, COUPLE)
    _click(at, "typical")
    after = at.session_state["assume_last"]["after"]
    assert "PARTNER_PLAN_UNTIL_AGE" in after and "PARTNER_SALARY_GROWTH_RATE" in after


def test_a_household_change_is_not_a_custom_edit(monkeypatch):
    """Switching to Just me clears the partner's plan-until age. The user changed no
    assumption, so the line says the preset is for the old plan."""
    at = _open(monkeypatch)
    _click(at, "typical")
    at.radio(key="ay_household").set_value("Just me").run()
    assert not at.exception, at.exception
    assert at.session_state["user_overrides"]["PARTNER_PLAN_UNTIL_AGE"] is None
    text = _text(at)
    assert "set for your old plan" in text, text
    assert "Custom:" not in text


def test_unit_a_household_change_is_outdated_not_custom():
    from utils import household
    ss = {"user_overrides": {"YOUR_AGE": 40, "PARTNER_AGE": 38, "TARGET_RETIREMENT_AGE": 55}}
    st = SimpleNamespace(session_state=ss)
    ap.apply_preset(st, "typical")
    assert "PARTNER_PLAN_UNTIL_AGE" in ss["assume_last"]["after"]
    household.clear_partner(ss["user_overrides"])
    assert ss["user_overrides"]["PARTNER_PLAN_UNTIL_AGE"] is None
    assert ap.status(st)[0] == "outdated"
    ss["user_overrides"]["EXPECTED_INFLATION"] = 0.05              # a real edit still shows
    assert ap.status(st)[0] == "custom"


def test_the_situation_line_adds_up_with_a_younger_partner():
    from components.assumption_presets import _situation_line
    ss = {"user_overrides": {"YOUR_AGE": 40, "PARTNER_AGE": 34, "TARGET_RETIREMENT_AGE": 55}}
    st = SimpleNamespace(session_state=ss)
    ap.apply_preset(st, "typical")
    last = ss["assume_last"]
    end = last["plan_end"]
    assert end == 106                                    # the partner's 100 is age 106 for you
    line = _situation_line(last)
    assert f"money lasting until you're {end} and your partner is 100" in line
    assert f"That is {end - 55} years of retirement." in line


def test_a_single_situation_line_names_one_age():
    from components.assumption_presets import _situation_line
    ss = {"user_overrides": {"YOUR_AGE": 28, "PARTNER_AGE": 0, "TARGET_RETIREMENT_AGE": 55}}
    st = SimpleNamespace(session_state=ss)
    ap.apply_preset(st, "typical")
    line = _situation_line(ss["assume_last"])
    assert "money lasting until you're 100." in line and "That is 45 years" in line


def test_a_hand_edited_pay_table_keeps_salary_growth(monkeypatch):
    at = _open(monkeypatch, MEDIAN)
    at.session_state["si_comp_customized"] = True
    at.run()
    growth = at.session_state["user_overrides"]["YOUR_SALARY_GROWTH_RATE"]
    _click(at, "typical")
    assert at.session_state["user_overrides"]["YOUR_SALARY_GROWTH_RATE"] == growth
    assert "Your salary growth: kept, because you edited your pay table" in _text(at)


# ------------------------------------------------------------------ persistence

def test_values_loaded_from_a_profile_show_the_matching_preset(monkeypatch):
    probe = _open(monkeypatch)
    plan = {k: v for k, (v, _) in ap.compute_preset("typical", probe.session_state["user_overrides"],
                                                    False).items()}
    loaded = _open(monkeypatch, **plan)
    assert "Now using: Typical assumptions." in _text(loaded)
    assert "assume_last" not in loaded.session_state


def test_a_profile_switch_clears_the_undo_note():
    ss = {"user_overrides": {}, "assume_last": {"name": "typical"}, "assume_undone": True,
          "profile": "x"}
    ws.reset_input_widget_state(SimpleNamespace(session_state=ss))
    assert "assume_last" not in ss and "assume_undone" not in ss
    assert "user_overrides" in ss


def test_the_status_line_with_nothing_set_says_own_settings(monkeypatch):
    at = _open(monkeypatch)
    assert "Now using: your own settings." in _text(at)


# ------------------------------------------------------------------ layout and copy

def test_the_buttons_are_stacked_and_labelled(monkeypatch):
    at = _open(monkeypatch)
    labels = [b.label for b in at.button if b.key and b.key.startswith("assume_btn_")]
    assert labels == ["All conservative assumptions", "All typical assumptions"]


def test_the_buttons_come_first_in_the_conservative_then_typical_order(monkeypatch):
    at = _open(monkeypatch)
    keys = [b.key for b in at.button if b.key]
    assert keys.index("assume_btn_conservative") < keys.index("assume_btn_typical")


def test_the_returns_section_points_to_the_presets(monkeypatch):
    at = _open(monkeypatch)
    assert any("The Assumptions section can set these for you in one click." in c.value
               for c in at.caption)


def test_copy_lint_on_the_rendered_text(monkeypatch):
    at = _open(monkeypatch)
    _click(at, "typical")
    texts = [str(c.value) for c in at.caption] + [str(m.value) for m in at.markdown]
    mine = [t for t in texts if "What changed" in t or "Typical" in t or "Nothing changed" in t
            or "number" in t.lower()]
    assert mine
    for t in mine:
        assert ";" not in t, t
        assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", t), t
        for line in t.splitlines():
            for sentence in re.split(r"(?<=[.!?])\s+", line.strip()):
                assert len(sentence.split()) <= 20, sentence
    for b in at.button:
        if b.key and b.key.startswith("assume_"):
            assert not b.label.startswith("**")


# ------------------------------------------------------------------ the real app

def test_planner_click_marks_results_stale_and_does_not_raise(monkeypatch):
    from streamlit.testing.v1 import AppTest, element_tree as et

    def indices(self):
        values = [self.value] if isinstance(self.value, str) else self.value
        return [self.options.index(self.format_func(v)) for v in values]
    monkeypatch.setattr(et.ButtonGroup, "indices", property(indices))
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    at = AppTest.from_file(APP, default_timeout=600).run()
    at.button(key="device_skip").click().run()
    next(b for b in at.button if b.label == "Open the retirement planner").click().run()
    at.button(key="gs_skip").click().run()
    assert not at.exception, at.exception
    at.button(key="assume_btn_typical").click().run()
    assert not at.exception, at.exception
    assert at.sidebar.button(key="assume_undo")
    assert any("Now using: Typical assumptions." in str(c.value) for c in at.sidebar.caption)


# ------------------------------------------------------------------ the pay-table flag

def test_a_loaded_profile_with_the_built_pay_table_is_not_edited_by_hand():
    from components.save_load import _apply_restored
    from utils.config_builder import comp_table_from_salary
    base = {"YOUR_AGE": 30, "TARGET_RETIREMENT_AGE": 55, "YOUR_BASE_SALARY": 90_000,
            "YOUR_BONUS_AMOUNT": 5_000, "YOUR_RSU_AMOUNT": 0, "YOUR_SALARY_GROWTH_RATE": 0.015}
    built = comp_table_from_salary(30, 55, 90_000, 5_000, 0, 0.015)
    st = SimpleNamespace(session_state={})
    _apply_restored(st, dict(base, YOUR_COMPENSATION_BY_AGE=built), "a.json")
    assert st.session_state["si_comp_customized"] is False
    edited = {a: dict(r) for a, r in built.items()}
    edited[35]["base"] += 10_000
    _apply_restored(st, dict(base, YOUR_COMPENSATION_BY_AGE=edited), "b.json")
    assert st.session_state["si_comp_customized"] is True
    _apply_restored(st, dict(base), "c.json")
    assert st.session_state["si_comp_customized"] is False
    _apply_restored(st, {"YOUR_AGE": 30, "YOUR_COMPENSATION_BY_AGE": built}, "d.json")
    assert st.session_state["si_comp_customized"] is True       # no inputs to rebuild it from


# ------------------------------------------------------------------ review fixes (round 2)

def test_two_clicks_then_undo_go_back_to_the_settings_before_any_preset(monkeypatch):
    at = _open(monkeypatch)
    before = _snapshot(at)
    scenario_before = at.session_state["sa_scenario"]
    _click(at, "typical")
    _click(at, "conservative")
    at.button(key="assume_undo").click().run()
    assert not at.exception, at.exception
    after = _snapshot(at)
    for key, old in before.items():
        if old is ap.MISSING:
            assert after[key] is ap.MISSING or key == "GLIDE_PATH_TENT_RISE_YEARS", key
        elif isinstance(old, (str, bool)):
            assert after[key] == old, key
        else:
            assert after[key] == pytest.approx(old), key
    assert at.session_state["sa_scenario"] == scenario_before


def test_dollar_amounts_are_escaped_for_markdown():
    from components import assumption_presets as comp
    last = {"changes": ["LTC_ANNUAL_COST"], "old": {"LTC_ANNUAL_COST": 120_000},
            "after": {"LTC_ANNUAL_COST": 115_000}, "facts": {}}
    (line,) = comp._change_lines(last)
    assert line == "Annual care cost: \\$120,000 → \\$115,000"


def test_the_long_plan_note_shows_only_when_the_return_set_changed(monkeypatch):
    at = _open(monkeypatch, ACTIVE_RETURN_SCENARIO="conservative")
    _click(at, "typical")
    last = at.session_state["assume_last"]
    if last["scenario"] == "conservative":
        assert "ACTIVE_RETURN_SCENARIO" not in last["changes"]
        assert ap.COPY["long_plan_note"] not in _text(at)


def test_the_climb_length_is_not_listed_when_the_shape_does_not_use_it(monkeypatch):
    # A 55-year-old couple retiring at 62 with Typical gets a short retirement: "Ease into bonds"
    # only when the horizon is 30 years or less, so force it with a late retirement.
    at = _open(monkeypatch, YOUR_AGE=60, PARTNER_AGE=60, TARGET_RETIREMENT_AGE=67,
               GLIDE_PATH_TENT_RISE_YEARS=15)
    _click(at, "typical")
    last = at.session_state["assume_last"]
    assert last["after"]["GLIDE_PATH_SHAPE"] == "down"
    assert "GLIDE_PATH_TENT_RISE_YEARS" not in last["changes"]
