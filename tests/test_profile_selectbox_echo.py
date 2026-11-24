"""After the guided setup hands over, a rerun that carries the old profile name must not
switch profiles. That echo used to load the sample household over the visitor's answers and
clear their results (seen in the browser under load)."""
import os
import sys

import pytest

os.environ.setdefault("RETIREMENT_SIM_PROFILE", "/nonexistent/retirement-sim-test-profile.json")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CUSTOM = "Custom (keep current values)"


def _wkey(at):
    """The profile selectbox's current widget key (AppTest's session state has no .get)."""
    from components import profile_picker as pp
    gen = at.session_state[pp.GEN_KEY] if pp.GEN_KEY in at.session_state else 0
    return f"profile_selectbox_w{int(gen or 0)}"


@pytest.fixture
def planner(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from streamlit.testing.v1 import element_tree as et
    from components import profile_picker as pp

    def indices(self):            # AppTest reads a segmented control's single choice as a list
        values = [self.value] if isinstance(self.value, str) else self.value
        return [self.options.index(self.format_func(v)) for v in values]
    monkeypatch.setattr(et.ButtonGroup, "indices", property(indices))
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    at = AppTest.from_file(os.path.join(_UI, "app.py"), default_timeout=300).run()
    at.button(key="device_skip").click().run()
    next(b for b in at.button if b.label == "Open the retirement planner").click().run()
    key_before = _wkey(at)
    at.button(key="gs_skip").click().run()
    assert at.session_state["results"] is not None
    return at, key_before


def test_the_handover_gives_the_selectbox_a_new_widget_showing_custom(planner):
    """A rerun that still carries the old widget's value (the sample name the browser showed)
    belongs to a widget that no longer exists, so it cannot switch profiles."""
    from components import profile_picker as pp
    at, key_before = planner
    assert at.session_state["profile"] == CUSTOM
    assert at.session_state["profile_selectbox"] == CUSTOM
    key_now = _wkey(at)
    assert key_now != key_before
    assert at.selectbox(key=key_now).value == CUSTOM


def test_a_real_pick_still_switches_and_a_rerun_keeps_the_answers(planner):
    from components import profile_picker as pp
    at, _ = planner
    answers = dict(at.session_state["user_overrides"])
    at.run()                                           # a plain rerun changes nothing
    assert at.session_state["results"] is not None
    assert at.session_state["user_overrides"] == answers
    pick = next(n for n in pp.PROFILES if n != CUSTOM)
    at.selectbox(key=_wkey(at)).set_value(pick).run()
    assert not at.exception, at.exception
    assert at.session_state["profile"] == pick
    assert at.session_state["profile_selectbox"] == pick
    assert at.session_state["results"] is None          # a switch waits for an explicit Run


def test_a_value_for_a_replaced_selectbox_does_not_switch():
    """The browser can send a value for the selectbox it showed before code replaced it, and
    Streamlit still runs that old selectbox's callback. It must not switch profiles."""
    from components import profile_picker as pp
    pick = next(n for n in pp.PROFILES if n != CUSTOM)
    answers = {"YOUR_AGE": 33}
    state = {"profile": pick, "user_overrides": answers}
    captured = {}

    class _St:
        session_state = state

        @staticmethod
        def markdown(*a, **k):
            pass

        @staticmethod
        def selectbox(*a, on_change=None, key=None, **k):
            captured["cb"], captured["key"] = on_change, key
            captured["index"] = k.get("index")

    pp.render(_St)                              # the selectbox the browser shows (shows `pick`)
    old_cb, old_key = captured["cb"], captured["key"]
    assert captured["index"] == list(pp.PROFILES).index(pick)   # its default is the current profile
    assert old_key not in state                                 # code never writes the widget key
    state["profile"] = CUSTOM                   # the guided setup hands over ...
    pp.seed_selectbox(state, CUSTOM)            # ... and points a new selectbox at Custom
    assert pp.widget_key(state) != old_key
    state[old_key] = pick                       # the browser's echo for the old selectbox
    old_cb()
    assert state["profile"] == CUSTOM
    assert state["user_overrides"] == answers
