"""The page script (components/animations.py::_ANIM_JS) is the only component iframe
the planner needs.

It used to share the page with a second iframe (the sidebar keyboard navigation) at
the bottom of main(). That iframe moved whenever the content above it changed, so
Streamlit rebuilt it on 1 to 3 reruns out of every rerun. The keyboard code now lives
in the page script, which sits at the top of the page and never moves.

The script's behaviour (folding, lazy tiles, scroll restore) is checked in a real
browser. These tests pin the hooks it depends on.
"""
import os
import re

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.path.join(_ROOT, "ui", "app.py")
APP = open(APP_PATH, encoding="utf-8").read()
ANIM = open(os.path.join(_ROOT, "ui", "components", "animations.py"), encoding="utf-8").read()
JS = ANIM[ANIM.index('_ANIM_JS = """'):ANIM.index("_RECOVER_JS = ")]


def _fn(name):
    """Source of one function in the page script (from its header to the next blank line)."""
    start = JS.index(name)
    return JS[start:JS.index("\n\n", start)]


# ---------------------------------------------------------------- one iframe

def test_app_no_longer_builds_a_keyboard_nav_iframe():
    assert "_inject_keyboard_nav" not in APP
    assert "components.html" not in APP


def test_page_script_carries_the_keyboard_navigation():
    for part in ("stSidebar", "mc-kbd-focus", "'ArrowUp'", "'ArrowRight'", "scrollIntoView",
                 "ae.isContentEditable", "role') === 'slider'"):
        assert part in JS, part
    # one keydown listener at a time: the previous load's is removed before a new one is added
    assert "D.removeEventListener('keydown', P.__mcKbdKey, true)" in JS
    assert "D.addEventListener('keydown', P.__mcKbdKey, true)" in JS


def test_page_script_tags_radio_groups_without_its_own_observer():
    assert "function tagRadios()" in JS
    assert re.search(r"function scan\(\)\{[^}]*tagRadios\(\)", JS)
    assert "P.__mcTagInterval" in JS          # the old script's interval is cleared
    assert "new P.MutationObserver" in JS
    assert JS.count("new P.MutationObserver") == 1, "one DOM observer for the whole page script"


# ------------------------------------------------------------------- folding

def test_fold_map_is_read_once_and_written_on_a_toggle():
    assert "function foldMap(){ return FOLD; }" in JS
    assert JS.count("localStorage.getItem(FOLD_KEY)") == 1
    assert "function foldLoad()" in JS
    # the only writer is foldStore, called from setFold and foldAll
    assert JS.count("localStorage.setItem(FOLD_KEY") == 1
    # another tab's change is picked up
    assert "addEventListener('storage', P.__mcFoldStorage)" in JS


def test_fold_runs_once_per_frame_before_paint():
    obs = JS[JS.index("P.__mcAnimObs = new P.MutationObserver"):]
    obs = obs[:obs.index("P.__mcAnimObs.observe")]
    assert "P.requestAnimationFrame(function(){ foldQ = false; try{ applyFold(); }" in obs
    assert "if(!foldQ){" in obs
    # no direct, synchronous applyFold in the observer: every call goes through the frame hook
    assert obs.count("applyFold()") == 1


def test_a_tile_without_its_heading_yet_is_folded_by_name():
    fold = _fn("function applyFold()")
    assert fold.index("if(name) folded = !!m[name];") < fold.index("if(name && h){")


# ---------------------------------------------------------------- lazy tiles

def test_lazy_poll_restarts_when_new_placeholders_appear():
    assert "function lazyPoll()" in JS
    assert re.search(r"function scan\(\)\{.*lazyPoll\(\)", JS, re.S)


def test_lazy_click_waits_for_the_button_and_retries_every_two_seconds():
    lazy = JS[JS.index("function checkLazy()"):JS.index("var _lzPend")]
    # no button yet: no try is spent
    assert lazy.index("if(!btn) return;") < lazy.index("ph.__lzTries = (ph.__lzTries || 0) + 1")
    assert "< 2000) return;" in lazy
    assert "ph.__lzTries >= 3" in lazy


# ----------------------------------------------------- view state for a refresh

def test_view_state_is_written_to_session_storage_with_no_rerun():
    assert "var VIEW_KEY = 'mcView'" in JS
    assert "P.sessionStorage.setItem(VIEW_KEY" in JS
    write = _fn("function viewWrite(patch)")
    assert "patch.scrollY" in write and "patch.tab" in write and "v.tabs" in write


def test_open_tab_is_stored_per_group():
    group = _fn("function tabGroup(list)")
    assert "mc-tile-" in group and "mc-spending-tabs" in group
    note = _fn("function noteTab(ev)")
    assert "closest('[role=\"tab\"]')" in note and "aria-selected" in note
    assert "D.addEventListener('click', P.__mcTabClick, true)" in JS


def test_scroll_is_saved_throttled_and_on_page_hide():
    assert "}, 500);" in JS[JS.index("P.__mcScrollFn = function"):JS.index("P.__mcScrollHide = noteScroll")]
    assert "P.addEventListener('pagehide', P.__mcScrollHide)" in JS
    # the scroll container is the one the jump chips scroll
    assert "function mainEl(){ return D.querySelector('section[data-testid=\"stMain\"]'); }" in JS
    assert "ev.target !== mainEl()" in JS
    # a refresh while a restore is still pending must not overwrite the saved place with 0
    assert "if(m && !P.__mcRestoring)" in JS


def test_scroll_restore_runs_once_waits_for_height_and_gives_up():
    restore = JS[JS.index("// Scroll restore, once per page load"):JS.index("// ---------- scan (debounced")]
    assert "if(P.__mcScrollRestored) return;" in restore
    assert "m.scrollHeight >= target + m.clientHeight" in restore
    assert "> 6000" in restore
    assert "requestAnimationFrame(step)" in restore
    # a visitor who scrolls first keeps their place
    for ev in ("wheel", "touchstart", "keydown", "pointerdown"):
        assert f"'{ev}'" in restore


# ----------------------------------------------------- the page in AppTest

@pytest.fixture(scope="module")
def planner():
    from streamlit.testing.v1 import AppTest
    mp = pytest.MonkeyPatch()
    mp.setenv("RETIREMENT_SIM_HOSTED", "1")
    try:
        at = AppTest.from_file(APP_PATH, default_timeout=300).run()
        at.button(key="device_skip").click().run()
        next(b for b in at.button if b.label == "Open the retirement planner").click().run()
        at.button(key="gs_skip").click().run()
        assert not at.exception, at.exception
        yield at
    finally:
        mp.undo()


def test_planner_page_has_no_keyboard_nav_iframe(planner):
    docs = [str(getattr(f.proto, "srcdoc", "")) for f in planner.get("iframe")]
    # the page script (animations) is the one that carries the keyboard code
    with_kbd = [d for d in docs if "mc-kbd-focus" in d]
    assert len(with_kbd) == 1 and "mcFoldedTiles" in with_kbd[0]
    # nothing else in the page injects a script that touches the sidebar expanders
    assert not [d for d in docs if "stSidebar" in d and "mcFoldedTiles" not in d]
