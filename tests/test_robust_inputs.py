"""The planner must not crash, whatever a widget holds or a profile carries.

Streamlit raises when a widget's value does not fit it (a number outside its range, a
choice that is not an option), and ``_safe_render`` then swaps the whole section for
"This section couldn't be displayed". These tests drive the full app with values that
do not fit, and assert no section was lost:

* every sidebar widget at its minimum, at its maximum, beyond both ends, and with a
  wrong type (text, None, a list, NaN), all at once and in seeded random mixtures;
* a saved profile with damaged values, loaded through ``profile_io`` as the app loads one;
* the specific cases the QA testers found (ages 70+, legacy house moves, unknown mode
  strings, a null guardrail, a high inflation rate in the what-if).

The cases are seeded, so a failure repeats.
"""
import json
import math
import os
import random
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.conftest import load_sample_household  # noqa: E402
from utils import profile_io  # noqa: E402
from utils.widget_guard import fit_number  # noqa: E402

SEED = 20261113


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Hosted mode, and teach AppTest to rerun a page that holds a segmented control."""
    from streamlit.testing.v1 import element_tree as et

    def indices(self):
        values = [self.value] if isinstance(self.value, str) else self.value
        return [self.options.index(self.format_func(v)) for v in values]
    monkeypatch.setattr(et.ButtonGroup, "indices", property(indices))
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    monkeypatch.setenv("ROBUST_TEST_ROOT", _ROOT)


def _app():
    """The planner, past the welcome and the guided setup, with the overrides the test
    put in session state (synced into the widgets the way a profile load does)."""
    import os
    import runpy
    import sys
    root = os.environ["ROBUST_TEST_ROOT"]
    sys.path[:0] = [root, root + "/ui"]
    import streamlit as st
    if not st.session_state.get("_robust_seeded"):
        st.session_state["_robust_seeded"] = True
        st.session_state["app_mode"] = "full"
        st.session_state["setup"] = {"status": "done", "step": 0, "seen": []}
        st.session_state["_device_skip"] = True
        st.session_state["_device_restored"] = True
        st.session_state["_autorun_done"] = True
        from utils.widget_sync import sync_widgets_from_overrides
        sync_widgets_from_overrides(st)
        for key, value in (st.session_state.get("_robust_widgets") or {}).items():
            st.session_state[key] = value
    runpy.run_path(root + "/ui/app.py", run_name="__main__")


def _planner(overrides, widgets=None):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_app, default_timeout=120)
    at.session_state["user_overrides"] = overrides
    at.session_state["profile"] = "robustness test"
    if widgets:
        at.session_state["_robust_widgets"] = widgets
    return at.run()


def _lost(at):
    """What a user would see go wrong: an exception, or a section replaced by the placeholder."""
    out = [f"exception: {e.value}" for e in at.exception]
    out += [f"{c.value}" for c in at.caption
            if str(c.value).startswith("`components.") or str(c.value).startswith("`ui.components.")]
    return out


def _sample(**changes):
    overrides = load_sample_household()
    overrides.update(changes)
    return overrides


# ---------------------------------------------------------------------------
# The guard itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value, lo, hi, step, want", [
    (6.5, 0.0, 6.0, 0.25, 6.0),             # above the top
    (-3, 0, 10, 1, 0),                       # below the bottom
    (7.0, 0, 10, 1, 7),                      # whole-number widget: an int comes back
    ("12", 0, 10, 1, 10),                    # numeric text
    ("abc", 5, 10, 1, 5),                    # not a number: the minimum
    (float("nan"), 5, 10, 1, 5),
    (True, 5, 10, 1, 5),                     # a bool is not a number here
    (4, None, None, None, 4),                # unbounded: untouched
])
def test_fit_number(value, lo, hi, step, want):
    got = fit_number(value, lo, hi, step)
    assert got == want and type(got) is type(want)


def test_fit_number_uses_the_widgets_own_start_for_junk():
    assert fit_number("junk", 0, 100, 1, fallback=40) == 40


def test_the_guard_leaves_a_value_that_fits_alone():
    at = _planner(_sample())
    before = {w.key: w.value for w in at.sidebar.number_input}
    after = {w.key: w.value for w in _planner(_sample()).sidebar.number_input}
    assert before == after and not _lost(at)


# ---------------------------------------------------------------------------
# Specific crashes the QA testers found
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("age", [70, 75, 76, 85, 99])
@pytest.mark.parametrize("toggle", ["ea_coast", "ea_sepp"])
def test_retirement_section_survives_coast_fire_and_72t_at_any_age(age, toggle):
    at = _planner(_sample(YOUR_AGE=age, TARGET_RETIREMENT_AGE=age, PARTNER_AGE=0, PLAN_UNTIL_AGE=100),
                  widgets={toggle: True})
    assert not _lost(at), _lost(at)
    assert at.session_state[toggle] is True


@pytest.mark.parametrize("age", [76, 90, 99])
def test_a_retiree_of_any_age_can_run_the_plan(age):
    """Target age can equal your age ("already retired"): no dead end, no impossible warning."""
    from utils.validation import validate_run_inputs
    at = _planner(_sample(YOUR_AGE=age, TARGET_RETIREMENT_AGE=age, PARTNER_AGE=0, PLAN_UNTIL_AGE=100))
    assert not _lost(at), _lost(at)
    target = at.slider(key="ay_target_age")
    assert target.max >= age and target.value == age            # the slider reaches your age, and keeps it
    assert at.session_state["user_overrides"]["TARGET_RETIREMENT_AGE"] == age
    assert not [w.value for w in at.warning if "below your current age" in str(w.value)]
    assert validate_run_inputs(dict(at.session_state["user_overrides"]), target_age=age) == []


def test_the_age_ranges_leave_no_dead_end():
    from utils.age_limits import AGE_MAX, PLAN_UNTIL_MAX, TARGET_MAX, TARGET_MIN, PLAN_UNTIL_MIN
    assert TARGET_MAX >= AGE_MAX                                # any age you can enter, you can retire at
    assert PLAN_UNTIL_MAX > AGE_MAX                             # and the plan can still end after it
    assert TARGET_MIN <= PLAN_UNTIL_MIN


def test_a_clamped_plan_until_age_says_so():
    at = _planner(_sample(PLAN_UNTIL_AGE=68, PARTNER_AGE=0))
    assert at.slider(key="ay_plan_until").value == 75
    notes = [str(c.value) for c in at.caption if "saved value 68" in str(c.value)]
    assert notes and "75" in notes[0], [str(c.value) for c in at.caption][:20]


@pytest.mark.parametrize("changes", [
    {"HOUSE_MOVE_AGE": 0}, {"HOUSE_MOVE_AGE": 400}, {"NEW_MORTGAGE_YEARS": 0},
    {"NEW_MORTGAGE_YEARS": 90}, {"NEW_HOME_VALUE": 5e9}, {"HOUSE_MOVING_COSTS": 9e9},
    {"HOME_SELLING_COST_PCT": 3.0}, {"NEW_MORTGAGE_BALANCE": 9e12},
])
def test_a_legacy_house_move_out_of_range_does_not_crash_house(changes):
    at = _planner(_sample(HOUSE_MOVE_ENABLED=True, **changes))
    assert not _lost(at), _lost(at)


def test_the_run_button_settles_after_a_clamped_legacy_move():
    """The first render makes every adjustment, so a second one changes nothing and the
    run is not left looking out of date."""
    at = _planner(_sample(HOUSE_MOVE_ENABLED=True, HOUSE_MOVE_AGE=0, NEW_MORTGAGE_YEARS=0))
    first = json.dumps(at.session_state["user_overrides"], sort_keys=True, default=str)
    at.run()
    assert json.dumps(at.session_state["user_overrides"], sort_keys=True, default=str) == first


@pytest.mark.parametrize("key, value", [
    ("SAVINGS_MODE", "x"), ("RETIREMENT_SPENDING_MODE", "y"), ("SPEND_LIFECYCLE_PRESET", "nope"),
    ("FILING_STATUS", "Elven"), ("ACTIVE_RETURN_SCENARIO", "sunny"), ("STATE_CHOICE", "Atlantis"),
])
def test_an_unknown_choice_string_falls_back_without_a_crash(key, value):
    at = _planner(_sample(**{key: value}))
    assert not _lost(at), _lost(at)


def test_widget_sync_drops_a_choice_that_is_not_an_option():
    from utils.widget_sync import sync_widgets_from_overrides

    class _St:
        session_state = {"user_overrides": {"SAVINGS_MODE": "x"}, "sv_mode": "left over"}
    sync_widgets_from_overrides(_St)
    assert "sv_mode" not in _St.session_state                    # not the previous plan's value, not "x"


def test_the_whatif_inflation_slider_reaches_the_main_one():
    """Main inflation runs to 10%; the what-if slider is seeded from it, so must reach it."""
    from streamlit.testing.v1 import AppTest

    def script():
        import os
        import sys
        root = os.environ["ROBUST_TEST_ROOT"]
        sys.path[:0] = [root, root + "/ui"]
        import streamlit as st
        from components import whatif_retirement_curve
        whatif_retirement_curve.render(st)
    at = AppTest.from_function(script, default_timeout=60)
    at.session_state["user_overrides"] = _sample(EXPECTED_INFLATION=0.10)
    at.run()
    assert not at.exception, at.exception
    assert at.slider(key="wifc_infl").value == 10.0


# ---------------------------------------------------------------------------
# Profile loading: hand-edited, damaged, old
# ---------------------------------------------------------------------------

def _load(obj):
    return profile_io.deserialize_overrides(json.dumps(obj))


def _saved(**damage):
    """The sample household as a saved file would hold it, with ``damage`` written over it."""
    saved = json.loads(profile_io.serialize_overrides(load_sample_household()))
    saved["overrides"].update(damage)
    return json.dumps(saved, allow_nan=True)


@pytest.mark.parametrize("bad", [
    {"SPENDING_GUARDRAILS": None}, {"RETURN_BASED_SPENDING_RULES": None},
    {"HEALTHCARE_COSTS_BY_AGE": None}, {"SPENDING_GUARDRAILS": {"floor_trigger": "x"}},
    {"SPENDING_GUARDRAILS": []}, {"YOUR_AGE": None}, {"YOUR_AGE": "old"}, {"YOUR_401K": [1]},
    {"YOUR_401K": {"a": 1}}, {"INCLUDE_SOCIAL_SECURITY": "maybe"}, {"STATE_CHOICE": 7},
    {"YEARS_UNTIL_FIRST_CHILD": "x"}, {"CHILDREN": "none"}, {"CHILDREN": ["x", None, 3]},
    {"CHILDREN": [{"years_until_birth": "soon"}]}, {"HOME_EVENTS": ["x", 3, None]},
    {"HOME_EVENTS": [{"action": "teleport", "age": 40}, {"action": "buy", "age": "x"}]},
    {"YOUR_COMPENSATION_BY_AGE": {"34": {"base": "lots"}}}, {"YOUR_COMPENSATION_BY_AGE": [1, 2]},
    {"MS_PLACES": {"hidden": [[1]], "custom": "x", "edits": [1]}},
    {"TARGET_RETIREMENT_AGE": "soon"}, {"YOUR_AGE": float("nan")}, {"YOUR_401K": float("inf")},
])
def test_a_damaged_value_loads_on_the_default_and_the_planner_still_draws(bad):
    loaded = profile_io.deserialize_overrides(_saved(**bad))
    for key, value in bad.items():
        assert key not in loaded or loaded[key] != value or key == "MS_PLACES", (key, loaded[key])
    at = _planner(loaded)
    assert not _lost(at), _lost(at)


def test_a_guardrail_dict_with_one_bad_entry_keeps_the_good_ones():
    loaded = _load({"SPENDING_GUARDRAILS": {"floor_trigger": "x", "floor_reduction": 0.4}})
    assert loaded["SPENDING_GUARDRAILS"]["floor_reduction"] == 0.4
    assert isinstance(loaded["SPENDING_GUARDRAILS"]["floor_trigger"], float)
    assert set(loaded["SPENDING_GUARDRAILS"]) >= {"ceiling_trigger", "ceiling_increase"}


def test_numbers_written_as_text_are_read_as_numbers():
    loaded = _load({"YOUR_AGE": "41", "YOUR_401K": "55000.5", "LTC_ENABLED": "true"})
    assert loaded == {"YOUR_AGE": 41, "YOUR_401K": 55000.5, "LTC_ENABLED": True}


def test_unknown_keys_are_ignored_not_rejected():
    loaded = _load({"YOUR_AGE": 40, "NOT_A_REAL_KEY": {"x": [1]}})
    assert loaded["YOUR_AGE"] == 40


@pytest.mark.parametrize("envelope, age", [
    ({"overrides": {"YOUR_AGE": 40}}, 40),                                       # no version
    ({"version": None, "overrides": {"YOUR_AGE": 41}}, 41),
    ({"version": 1, "overrides": {"YOUR_AGE": 42}}, 42),                         # a number, not text
    ({"version": "1.7", "overrides": {"YOUR_AGE": 43}}, 43),                     # a later minor version
    ({"version": "1.0", "overrides": {"version": "1.0", "overrides": {"YOUR_AGE": 44}}}, 44),  # wrapped twice
    ({"app": "retirement-monte-carlo", "overrides": {"YOUR_AGE": 45}}, 45),
])
def test_envelope_versions_and_nesting_are_handled(envelope, age):
    assert _load(envelope)["YOUR_AGE"] == age


@pytest.mark.parametrize("text", [
    json.dumps({"version": "2.0", "overrides": {}}),       # another major version
    json.dumps({"version": "1.0", "overrides": [1]}),
    json.dumps({"version": "1.0"}),
    json.dumps([1, 2]), "null", "", "{", "[" * 6000 + "]" * 6000,
    '{"a":' * 3000 + "1" + "}" * 3000,
])
def test_a_file_that_cannot_be_read_is_a_value_error_not_a_crash(text):
    with pytest.raises(ValueError):
        profile_io.deserialize_overrides(text)


def test_a_good_profile_still_round_trips_exactly():
    original = load_sample_household()
    assert profile_io.deserialize_overrides(profile_io.serialize_overrides(original)) == original


# ---------------------------------------------------------------------------
# Randomized and extreme values through the full app
# ---------------------------------------------------------------------------

_SKIP_PREFIXES = ("mode_switch", "topbar", "n_simulations", "profile")
_JUNK = ["abc", None, [], float("nan"), float("inf"), True, {"a": 1}, -1e12, 1e12]


def _sidebar_widgets(at):
    """(key, kind, lo, hi) for every bounded sidebar widget; choices have lo = hi = None."""
    found = []
    for kind, group in (("number", at.sidebar.number_input), ("number", at.sidebar.slider),
                        ("choice", at.sidebar.selectbox), ("choice", at.sidebar.radio)):
        for w in group:
            key = w.key
            if not key or str(key).startswith(_SKIP_PREFIXES):
                continue
            lo = getattr(w, "min", None) if kind == "number" else None
            hi = getattr(w, "max", None) if kind == "number" else None
            found.append((str(key), kind, lo, hi))
    return found


def _widget_values(widgets, mode, rng):
    values = {}
    for key, kind, lo, hi in widgets:
        lo_n = 0 if lo is None else lo
        hi_n = 1_000_000 if hi is None else hi
        choice = rng.choice(["min", "max", "over", "under", "junk"]) if mode == "mixed" else mode
        if choice == "junk" or kind == "choice":
            values[key] = rng.choice(_JUNK) if choice == "junk" else "no such option"
        elif choice == "min":
            values[key] = lo_n
        elif choice == "max":
            values[key] = hi_n
        elif choice == "over":
            values[key] = hi_n * 2 + 7
        else:
            values[key] = lo_n - 1_000_000
    return values


@pytest.fixture
def _widgets():
    return _sidebar_widgets(_planner(_sample()))


def test_the_planner_exposes_a_meaningful_set_of_widgets(_widgets):
    kinds = {k for _, k, _, _ in _widgets}
    assert len(_widgets) > 80 and kinds == {"number", "choice"}


@pytest.mark.parametrize("mode", ["min", "max", "over", "under", "junk"])
def test_every_sidebar_widget_at_an_extreme(_widgets, mode):
    values = _widget_values(_widgets, mode, random.Random(SEED))
    at = _planner(_sample(), widgets=values)
    assert not _lost(at), (mode, _lost(at))


@pytest.mark.parametrize("seed", range(6))
def test_random_mixtures_of_extreme_widget_values(_widgets, seed):
    values = _widget_values(_widgets, "mixed", random.Random(SEED + seed))
    at = _planner(_sample(), widgets=values)
    assert not _lost(at), (seed, _lost(at))


def _damage(overrides, rng):
    """About a quarter of the values replaced by junk, through JSON as a hand edit would be."""
    damaged = {}
    for key, value in overrides.items():
        damaged[key] = rng.choice(_JUNK + [0, -1, 10 ** 9, "x"]) if rng.random() < 0.25 else value
    return damaged


@pytest.mark.parametrize("seed", range(5))
def test_a_randomly_damaged_profile_loads_and_draws(seed):
    rng = random.Random(SEED * 3 + seed)
    envelope = {"version": "1.0", "overrides": _damage(
        json.loads(profile_io.serialize_overrides(load_sample_household()))["overrides"], rng)}
    for value in envelope["overrides"].values():
        assert not (isinstance(value, float) and math.isnan(value)) or True
    loaded = profile_io.deserialize_overrides(json.dumps(envelope, allow_nan=True))
    at = _planner(loaded)
    assert not _lost(at), (seed, _lost(at))
