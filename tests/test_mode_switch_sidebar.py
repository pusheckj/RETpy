"""The Money check-up | Retirement planner switch in the planner: two radios that
do the same thing (Streamlit cannot draw one widget twice), one at the top of the
side panel and one in the page's top gutter. theme.css shows exactly one. The
check-up and the guided setup keep their single switch at the top of the page."""
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(_ROOT, "ui", "app.py")
CSS = open(os.path.join(_ROOT, "ui", "styles", "theme.css"), encoding="utf-8").read()
SIDEBAR_KEY, PAGE_KEY = "mode_switch_full_sidebar", "mode_switch_full"
OPTIONS = ["Money check-up", "Retirement planner"]


@pytest.fixture(autouse=True)
def _planner_can_rerun(monkeypatch):
    """AppTest cannot rerun a page that holds a segmented control (the planner's
    Retirement plan | Spending toggle): it reads a single choice as a list. Teach
    it that, so a click on the version switch can be run."""
    from streamlit.testing.v1 import element_tree as et

    def indices(self):
        values = [self.value] if isinstance(self.value, str) else self.value
        return [self.options.index(self.format_func(v)) for v in values]
    monkeypatch.setattr(et.ButtonGroup, "indices", property(indices))


def _switches(at):
    """Keys of the mode-switch radios on the page (``at.radio`` covers the side panel
    too). A set: after the planner's first lazy rerun AppTest's tree lists some
    widgets twice (``portfolio_breakdown_main_view`` too); the browser draws one."""
    return sorted({r.key for r in at.radio if str(r.key).startswith("mode_switch_")})


def _radio(at, key):
    return [r for r in at.radio if r.key == key][-1]            # the live copy of a doubled widget


def _welcome(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.button(key="device_skip").click().run()
    return at


def _planner(monkeypatch):
    at = _welcome(monkeypatch)
    next(b for b in at.button if b.label == "Open the retirement planner").click().run()
    at.button(key="gs_skip").click().run()
    assert not at.exception, at.exception
    return at


def test_planner_has_both_radios_with_the_right_keys(monkeypatch):
    at = _planner(monkeypatch)
    assert _switches(at) == sorted([PAGE_KEY, SIDEBAR_KEY])
    page, panel = _radio(at, PAGE_KEY), at.sidebar.radio(key=SIDEBAR_KEY)
    assert page.options == panel.options == OPTIONS
    assert page.value == panel.value == "Retirement planner"
    # the panel's is the first widget in the panel, above About you
    assert at.sidebar.radio[0].key == SIDEBAR_KEY


@pytest.mark.parametrize("which", [SIDEBAR_KEY, PAGE_KEY])
def test_either_switch_opens_the_checkup_and_keeps_the_planner_answers(monkeypatch, which):
    at = _planner(monkeypatch)
    ov = dict(at.session_state["user_overrides"])
    _radio(at, which).set_value("Money check-up").run()
    assert not at.exception, at.exception
    assert at.session_state["app_mode"] == "simple"
    assert _switches(at) == ["mode_switch_simple"]              # exactly the check-up's own switch
    at.radio(key="mode_switch_simple").set_value("Retirement planner").run()
    assert not at.exception, at.exception
    assert at.session_state["app_mode"] == "full"
    assert _switches(at) == sorted([PAGE_KEY, SIDEBAR_KEY])
    assert at.session_state["user_overrides"] == ov              # nothing lost on the round trip


def test_checkup_and_setup_keep_exactly_one_switch(monkeypatch):
    at = _welcome(monkeypatch)
    next(b for b in at.button if b.label == "Start the money check-up").click().run()
    assert _switches(at) == ["mode_switch_simple"]
    at.radio(key="mode_switch_simple").set_value("Retirement planner").run()
    assert at.session_state["setup"]["status"] == "active"      # the walkthrough, no side panel
    assert _switches(at) == [PAGE_KEY]
    assert not at.sidebar.children


def test_css_shows_exactly_one_switch_in_each_state():
    block = CSS[CSS.index("Mode switch in sidebar"):]
    assert block.count("Mode switch in sidebar") == 1
    # panel closed -> the panel's copy is display:none
    assert 'aria-expanded="false"]) [data-testid="stLayoutWrapper"]:has(> .st-key-mc-mode-switch-sidebar)' in block
    # phones -> the panel's copy is display:none even when the drawer is open
    assert "@media (max-width: 640px)" in block
    # panel open on a wider-than-phone screen -> the page's copy is display:none
    assert ("@media (min-width: 641px)" in block
            and 'aria-expanded="true"]) [data-testid="stLayoutWrapper"]:has(> .st-key-mc-mode-switch-gutter)' in block)
    assert block.count("display: none;") >= 3
