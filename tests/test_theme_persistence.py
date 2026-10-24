"""Dark mode must survive screens that don't render the Settings popover.

Streamlit drops a widget's session value after any run that doesn't render that
widget, so the theme radio's value vanished on entering the guided setup or the
check-up. ``theme_toggle.persist_appearance`` mirrors it into a plain key."""
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(_ROOT, "ui", "app.py")
DARK = "mc-dark-theme"


def _is_dark(at) -> bool:
    return any(DARK in str(m.value) for m in at.markdown)


def _app(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.button(key="device_skip").click().run()
    return at


def test_dark_mode_persists_into_setup_checkup_and_planner(monkeypatch):
    # (AppTest can't re-run the planner's segmented control, so the last run ends there.)
    at = _app(monkeypatch)
    assert not _is_dark(at)
    at.session_state["theme_mode"] = "🌙 Dark"      # what picking Dark in Settings does
    at.run()                                         # welcome: the radio isn't rendered here
    next(b for b in at.button if b.label == "Open the retirement planner").click().run()
    assert at.session_state["setup"]["status"] == "active"
    assert _is_dark(at), "dark mode was lost on entering the guided setup"

    at.radio(key="mode_switch_full").set_value("Money check-up").run()
    assert not at.exception, at.exception
    assert _is_dark(at), "dark mode was lost on entering the check-up"
    at.radio(key="mode_switch_simple").set_value("Retirement planner").run()
    assert _is_dark(at)

    at.button(key="gs_skip").click().run()                                  # the planner
    assert _is_dark(at)
    assert at.radio(key="theme_mode").value == "🌙 Dark"            # and its radio agrees


def test_light_stays_light(monkeypatch):
    at = _app(monkeypatch)
    next(b for b in at.button if b.label == "Start the money check-up").click().run()
    assert not _is_dark(at)


def test_profile_switch_keeps_the_saved_appearance():
    src = open(os.path.join(_ROOT, "ui", "components", "profile_picker.py")).read()
    keep = re.search(r"_PRESERVE = \{(.*?)\}", src, re.DOTALL).group(1)
    assert '"_appearance_saved"' in keep


def test_persist_appearance_restores_a_dropped_widget_value():
    """Simulates Streamlit deleting the radio's key after a run that didn't render it."""
    import sys
    sys.path[:0] = [os.path.join(_ROOT, "ui"), _ROOT]
    from components.theme_toggle import persist_appearance

    class St:
        session_state = {}

    st = St()
    st.session_state.update(theme_mode="🌙 Dark", font_choice="Inter")
    persist_appearance(st)                                   # a run that rendered the popover
    for k in ("theme_mode", "font_choice"):
        del st.session_state[k]                              # ...then Streamlit drops the widget keys
    persist_appearance(st)                                   # next run (setup / check-up)
    assert st.session_state["theme_mode"] == "🌙 Dark"
    assert st.session_state["font_choice"] == "Inter"
    assert "palette_choice" not in st.session_state          # never chosen: nothing invented
    st.session_state["theme_mode"] = "☀ Light"               # an explicit change wins
    persist_appearance(st)
    del st.session_state["theme_mode"]
    persist_appearance(st)
    assert st.session_state["theme_mode"] == "☀ Light"
