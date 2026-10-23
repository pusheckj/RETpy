"""First-time visitors pick a path on the welcome screen; the simple check-up
and the full planner each render on their own."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(_ROOT, "ui", "app.py")


def test_hosted_visitor_sees_the_welcome_screen_then_the_simple_page(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    # No browser here to answer the on-device storage check: the brief loading
    # screen's Continue button is the way through (and must always exist).
    assert [b.label for b in at.button] == ["Continue"]
    at.button(key="device_skip").click().run()
    labels = [b.label for b in at.button]
    assert "Start the money check-up" in labels and "Open the retirement planner" in labels
    assert "app_mode" not in at.session_state or at.session_state["app_mode"] is None

    next(b for b in at.button if b.label == "Start the money check-up").click().run()
    assert not at.exception
    assert at.session_state["app_mode"] == "simple"
    # the version switch replaces the old one-way link
    assert at.radio(key="mode_switch_simple").value == "Money check-up"
    assert at.radio(key="mode_switch_simple").options == ["Money check-up", "Retirement planner"]


def test_welcome_paths_cover_both_versions():
    sys.path[:0] = [os.path.join(_ROOT, "ui"), _ROOT]
    from components import welcome
    assert [m for m, *_ in welcome.PATHS] == ["simple", "full"]
