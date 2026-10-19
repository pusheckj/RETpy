"""Auto-run must fire EXACTLY ONCE per session, on first page open.

The whole point of warming the page automatically is that the user doesn't
click buttons. The hazard is the opposite failure: Streamlit reruns the entire
script on every keystroke, so anything that re-arms the guard turns a single
slider nudge into a ~95s simulation sweep.

The bug these pin: ``_autorun_done`` was not in profile_picker's ``_PRESERVE``
set, so switching profiles wildcard-deleted it AND cleared ``results`` --
re-arming the auto-run. Switching profiles is very much "changing a value" from
the user's point of view.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

GUARD = "_autorun_done"


def _autorun_would_fire(state: dict) -> bool:
    """Mirror of app._autorun_all's gate (it can't be imported without a live
    Streamlit runtime, so the condition is asserted directly)."""
    if state.get(GUARD):
        return False
    if state.get("results") is not None:
        return False
    return True


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------

def test_fires_on_a_cold_first_open():
    assert _autorun_would_fire({"results": None}) is True


def test_does_not_fire_once_the_guard_is_set():
    assert _autorun_would_fire({GUARD: True, "results": None}) is False


def test_does_not_fire_when_results_already_exist():
    """e.g. the user clicked Run before the warm-up got there."""
    assert _autorun_would_fire({"results": {"x": 1}}) is False


def test_does_not_fire_after_a_sidebar_edit():
    """An edit leaves results in place (marked stale) -- no re-simulation."""
    state = {GUARD: True, "results": {"x": 1}}
    state["user_overrides"] = {"YOUR_AGE": 33}      # the "edit"
    assert _autorun_would_fire(state) is False


# ---------------------------------------------------------------------------
# The profile-switch regression
# ---------------------------------------------------------------------------

def test_profile_switch_preserves_the_autorun_guard():
    """THE regression: a profile switch must not re-arm the auto-run."""
    import components.profile_picker as pp
    import inspect
    src = inspect.getsource(pp.render)
    assert '"_autorun_done"' in src, (
        "_autorun_done is missing from profile_picker's _PRESERVE set, so a "
        "profile switch will delete it and silently start a full simulation "
        "sweep"
    )


def test_profile_switch_simulation_does_not_refire():
    """Simulate the switch: clear results + wildcard-drop non-preserved keys,
    then assert the auto-run stays off."""
    import components.profile_picker as pp
    import inspect
    import re

    src = inspect.getsource(pp.render)
    m = re.search(r"_PRESERVE = \{(.*?)\}", src, re.DOTALL)
    assert m, "could not locate _PRESERVE"
    preserve = set(re.findall(r'"([^"]+)"', m.group(1)))

    state = {GUARD: True, "results": {"x": 1}, "profile": "A",
             "user_overrides": {}, "se_food": 2000}
    # what _apply_profile does:
    state["results"] = None
    for k in list(state):
        if k not in preserve:
            del state[k]

    assert GUARD in state, "guard was dropped by the profile switch"
    assert _autorun_would_fire(state) is False


def test_json_load_also_does_not_refire():
    """save_load clears results but leaves the guard -> no auto-simulation."""
    state = {GUARD: True, "results": {"x": 1}}
    state["results"] = None          # what _apply_restored does
    assert _autorun_would_fire(state) is False


# ---------------------------------------------------------------------------
# The sidebar payoff projection must not recompute every rerun
# ---------------------------------------------------------------------------

def test_sidebar_payoff_projection_is_memoised():
    """_payoff_projection_for monkeypatches cfg and recomputes every derived
    constant; the sidebar reruns on every keystroke, so it must be cached."""
    import components.sec_big_purchases as bp
    import inspect
    src = inspect.getsource(bp.render_body)
    assert "_bp_payoff_memo" in src, (
        "the sidebar payoff projection is not memoised -- it mutates global "
        "engine state on every keystroke"
    )
