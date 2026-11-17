"""The shared-cache control must not be drawn for hosted visitors."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ui"))

from components import cache_panel  # noqa: E402


class _Spy:
    """Records every st.* call the panel makes."""
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*a, **k):
            self.calls.append(name)
            raise AssertionError(f"st.{name} drawn")
        return call


@pytest.mark.parametrize("flag", ["1", "true", "yes"])
def test_hosted_draws_nothing(monkeypatch, flag):
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", flag)
    spy = _Spy()
    cache_panel.render(spy)
    assert spy.calls == []


def _panel_app():
    import os
    import sys
    import streamlit as st
    sys.path.insert(0, os.environ["CACHE_PANEL_TEST_UI_DIR"])
    from components import cache_panel
    cache_panel.render(st)


def _run(monkeypatch, hosted):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", hosted)
    monkeypatch.setenv("CACHE_PANEL_TEST_UI_DIR",
                       os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ui")))
    at = AppTest.from_function(_panel_app)
    at.run(timeout=60)
    assert not at.exception
    return [b for b in at.button if b.key == "cache_clear_btn"]


def test_hosted_app_has_no_recompute_button(monkeypatch):
    assert _run(monkeypatch, "1") == []


def test_local_still_draws_the_button(monkeypatch):
    assert _run(monkeypatch, "0")
