"""What if and Deep dives are ordinary section tiles (no longer hidden in a
collapsed expander), and every planner tile folds to its heading in the browser.

The folding is client-side only (components/animations.py, "collapsible
section tiles", plus theme.css, "Collapsible section tiles"), so these tests pin
the hooks it depends on; the behaviour itself was checked in a real browser.
"""
import ast
import os
import re

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.path.join(_ROOT, "ui", "app.py")
APP = open(APP_PATH, encoding="utf-8").read()
ANIM = open(os.path.join(_ROOT, "ui", "components", "animations.py"), encoding="utf-8").read()
CSS = open(os.path.join(_ROOT, "ui", "styles", "theme.css"), encoding="utf-8").read()
EXPORT = open(os.path.join(_ROOT, "ui", "components", "export_page.py"), encoding="utf-8").read()
FOLD_CSS = CSS[CSS.index("Collapsible section tiles. Only this block"):CSS.index("-- end Collapsible section tiles --")]
FOLD_JS = ANIM[ANIM.index("// ---------- collapsible section tiles ----------"):ANIM.index("// ---------- scan (debounced")]

DEEP_DIVE_TABS = ["Trajectories", "Withdrawal", "Sensitivity", "Stress tests", "Mortgage paydown"]


@pytest.fixture(autouse=True)
def _planner_can_rerun(monkeypatch):
    """AppTest reads a segmented control's single choice as a list (see
    test_mode_switch_sidebar); teach it that so the planner can be rerun."""
    from streamlit.testing.v1 import element_tree as et

    def indices(self):
        values = [self.value] if isinstance(self.value, str) else self.value
        return [self.options.index(self.format_func(v)) for v in values]
    monkeypatch.setattr(et.ButtonGroup, "indices", property(indices))


@pytest.fixture(scope="module")
def planner():
    """The hosted planner after its first (automatic) run."""
    from streamlit.testing.v1 import AppTest
    mp = pytest.MonkeyPatch()
    mp.setenv("RETIREMENT_SIM_HOSTED", "1")
    try:
        at = AppTest.from_file(APP_PATH, default_timeout=120).run()
        at.button(key="device_skip").click().run()
        next(b for b in at.button if b.label == "Open the retirement planner").click().run()
        at.button(key="gs_skip").click().run()
        assert not at.exception, at.exception
        assert at.session_state["results"] is not None
        yield at
    finally:
        mp.undo()


def _blocks(node):
    for c in node.children.values():
        if type(c).__name__ == "Block":
            yield c
            yield from _blocks(c)


def _tiles(at):
    """{tile name: Block} for every keyed mc-tile-* container, in page order."""
    out = {}
    for b in _blocks(at.main):
        m = re.search(r"-mc-tile-([a-z0-9-]+)$", getattr(b.proto, "id", "") if b.proto else "")
        if m:
            out[m.group(1)] = b
    return out


def _first(block):
    return next(iter(block.children.values()))


def _leaves(node):
    for c in node.children.values():
        if type(c).__name__ == "Block":
            yield from _leaves(c)
        else:
            yield c


# ---------------------------------------------------------------- the tiles

def test_what_if_and_deep_dives_are_tiles_not_expanders(planner):
    tiles = _tiles(planner)
    assert list(tiles)[-2:] == ["whatif", "deepdives"]          # last, after Life expectancy
    assert not [e for e in planner.main.expander if e.label in ("What if", "Deep dives")]
    assert 'st.expander("What if"' not in APP
    assert 'key="mc-tile-whatif"' in APP and 'key="mc-tile-deepdives"' in APP


def test_every_planner_tile_starts_with_its_heading(planner):
    """The fold toggle is the heading in the tile's FIRST row (the page script and
    the CSS both rely on it), so every tile must open with an .mc-section."""
    tiles = _tiles(planner)
    assert {"retirement", "freedom", "fi", "swr", "bridge", "spending", "savings", "income",
            "tax", "lifespan", "whatif", "deepdives"} <= set(tiles)
    for name, tile in tiles.items():
        first = _first(tile)
        assert type(first).__name__ == "Markdown" and 'class="mc-section' in first.value, name
    assert "What if" in _first(tiles["whatif"]).value
    assert "Deep dives" in _first(tiles["deepdives"]).value
    # Life expectancy's heading is drawn by the tile, so it is there before the lazy load.
    assert "Your life expectancy" in _first(tiles["lifespan"]).value


def test_what_if_and_deep_dives_stay_lazy_and_load(planner):
    at = planner
    tiles = _tiles(at)
    for name in ("whatif", "deepdives"):
        keys = [getattr(c, "key", None) for c in _leaves(tiles[name])]
        assert f"_lzb_{name}" in keys, name                 # skeleton + hidden load button
    assert not list(tiles["deepdives"].tabs)
    at.button(key="_lzb_deepdives").click().run()
    at.button(key="_lzb_whatif").click().run()
    at.run()                        # the load button's fragment rerun is not redrawn by AppTest
    assert not at.exception, at.exception
    tiles = _tiles(at)
    assert [t.label for t in tiles["deepdives"].tabs] == DEEP_DIVE_TABS
    md = " ".join(m.value for m in tiles["whatif"].markdown)
    assert "What-if: when can you retire?" in md and "Scenario comparison" in md


def test_pre_run_captions_are_kept():
    for name, what in (("whatif", "what-if comparisons"), ("deepdives", "trajectories, withdrawals")):
        body = APP[APP.index(f'key="mc-tile-{name}"'):]
        body = body[:body.index("_lazy_ph(")]
        assert "if not results:" in body and f'_run_hint("{what}' in body, name


def test_jump_chips_include_the_new_tiles():
    sections = dict(ast.literal_eval(re.search(r"_JUMP_SECTIONS = (\[.*?\])\n", APP, re.S).group(1)))
    assert sections["whatif"] == "What if" and sections["deepdives"] == "Deep dives"


def test_collapse_all_control_sits_above_the_first_tile(planner):
    assert APP.index('data-mc-fold-all="1"') < APP.index('key="mc-tile-retirement"')
    assert re.search(r'role="button" tabindex="0" data-mc-fold-all="1">Collapse all<', APP)
    assert re.search(r'role="button" tabindex="0" data-mc-fold-all="0">Expand all<', APP)
    md = [m.value for m in planner.main.markdown if m.value.startswith('<div class="mc-fold-all"')]
    assert len(md) == 1


# ------------------------------------------------------- the page script hooks

def test_page_script_folds_tile_headings():
    # only the planner tiles (the money check-up's mc-tile-simple-* stay as they are)
    assert """[class*="st-key-mc-tile-"]:not([class*="st-key-mc-tile-simple-"])""" in FOLD_JS
    # the toggle is the heading in the tile's first row, never a sub-heading
    assert "t.firstElementChild" in FOLD_JS and "querySelector('.mc-section')" in FOLD_JS
    for attr in ("'data-mc-fold'", "'role', 'button'", "'tabindex', '0'", "'aria-expanded'",
                 "'data-mc-folded'"):
        assert attr in FOLD_JS, attr
    # keyboard: Enter and Space
    assert "ev.key !== 'Enter' && ev.key !== ' '" in FOLD_JS


def test_fold_state_persists_in_local_storage():
    assert "var FOLD_KEY = 'mcFoldedTiles'" in FOLD_JS
    assert "P.localStorage.getItem(FOLD_KEY)" in FOLD_JS and "P.localStorage.setItem(FOLD_KEY" in FOLD_JS
    # re-applied on every rerun: synchronously in the DOM observer (no flash) and in scan()
    obs = ANIM[ANIM.index("P.__mcAnimObs = new P.MutationObserver"):]
    assert obs.index("applyFold()") < obs.index("if(pend) return")
    assert re.search(r"function scan\(\)\{[^}]*applyFold\(\)", ANIM)


def test_listeners_are_reinstalled_per_iframe_load():
    assert "D.removeEventListener('click', P.__mcFoldClick, true)" in FOLD_JS
    assert "D.addEventListener('click', P.__mcFoldClick, true)" in FOLD_JS
    assert "D.addEventListener('keydown', P.__mcFoldKey, true)" in FOLD_JS


def test_opening_a_tile_loads_its_lazy_charts():
    # a folded tile's placeholder is display:none, which checkLazy already skips ...
    assert "if(ph.offsetParent === null) return;" in ANIM
    # ... and opening a tile (or Expand all) checks the placeholders right away
    set_fold = FOLD_JS[FOLD_JS.index("function setFold"):FOLD_JS.index("function foldAll")]
    fold_all = FOLD_JS[FOLD_JS.index("function foldAll"):FOLD_JS.index("P.__mcFoldOpen")]
    assert "checkLazy()" in set_fold and "checkLazy()" in fold_all


def test_jumping_to_a_section_opens_it():
    jump = ANIM[ANIM.index("function mcJump"):ANIM.index("function mcShowResults")]
    assert "P.__mcFoldOpen(name)" in jump
    assert "P.__mcFoldOpen = function(name)" in FOLD_JS


# ------------------------------------------------------------------ the CSS

def test_css_block_sits_before_the_top_card_block():
    assert CSS.index("Collapsible section tiles. Only this block") < CSS.index("Top card layout. The card")
    assert CSS.index("-- end Collapsible section tiles --") < CSS.index("Top card layout. The card")


def test_folded_tile_hides_all_but_its_heading_on_screen_only():
    hide = re.search(r"@media screen \{\s*html:not\(\[data-mc-exporting\]\) "
                     r"\[class\*=\"st-key-mc-tile-\"\]\[data-mc-folded\] > :not\(:first-child\) \{\s*"
                     r"display: none !important;", FOLD_CSS)
    assert hide, "the hide rule must be screen-only and off while exporting"
    assert "@media print" in FOLD_CSS
    # export opens folded tiles for the capture
    assert "setAttribute('data-mc-exporting'" in EXPORT and "removeAttribute('data-mc-exporting')" in EXPORT


def test_heading_toggle_styles():
    assert re.search(r"\.mc-section\[data-mc-fold\] \{[^}]*cursor: pointer", FOLD_CSS)
    assert re.search(r'\.mc-section\[data-mc-fold\]\[aria-expanded="false"\]::before \{\s*transform: rotate', FOLD_CSS)
    assert ".mc-section[data-mc-fold]:focus-visible" in FOLD_CSS
    # the chevron's room is kept in both states (no layout shift)
    assert not re.search(r'aria-expanded="false"\]\s*\{[^}]*padding', FOLD_CSS)


def test_collapse_all_uses_the_design_tokens():
    pill = re.search(r"\.mc-fold-all a \{([^}]*)\}", FOLD_CSS).group(1)
    for token in ("var(--mc-pill-h)", "var(--mc-ctl-r)", "var(--mc-btn-border)", "var(--mc-btn-fill)",
                  "var(--mc-pill-fs)"):
        assert token in pill, token
    touch = FOLD_CSS[FOLD_CSS.index("@media (hover: none) and (pointer: coarse)"):]
    assert re.search(r"\.mc-fold-all a \{[^}]*min-height: 44px", touch)
