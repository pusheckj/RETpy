"""The planner page keeps the same top-level layout with and without a stale warning.

A block that appears or disappears shifts every element after it. Streamlit then
re-mounts the charts below (about 45 Plotly charts, a 2.4 s freeze). The stale
warning, the setup banner and the bridge tile therefore always take a slot.
"""
import os
import re

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.path.join(_ROOT, "ui", "app.py")
APP = open(APP_PATH, encoding="utf-8").read()
CSS = open(os.path.join(_ROOT, "ui", "styles", "theme.css"), encoding="utf-8").read()

STALE_TEXT = "Your inputs changed since this simulation ran"


@pytest.fixture(autouse=True)
def _planner_can_rerun(monkeypatch):
    """AppTest reads a segmented control's single choice as a list; teach it that so
    the planner can be rerun."""
    from streamlit.testing.v1 import element_tree as et

    def indices(self):
        values = [self.value] if isinstance(self.value, str) else self.value
        return [self.options.index(self.format_func(v)) for v in values]
    monkeypatch.setattr(et.ButtonGroup, "indices", property(indices))


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
        assert at.session_state["results"] is not None
        yield at
    finally:
        mp.undo()


def _signature(at):
    """Block keys and leaf positions of the main block's direct children, in order.

    A leaf's type is not compared: an empty slot and the warning that fills it take the
    same place in the page (AppTest shows the empty one as an UnknownElement)."""
    out = []
    for c in at.main.children.values():
        proto = getattr(c, "proto", None)
        ident = getattr(proto, "id", "") if proto is not None else ""
        m = re.search(r"-(mc-[a-z0-9-]+)$", ident or "")
        is_block = type(c).__name__ == "Block"
        out.append(("Block", m.group(1) if m else "") if is_block else ("leaf", ""))
    return out


def _texts(at):
    return [w.value for w in at.main.warning]


def test_stale_toggle_keeps_the_top_level_layout(planner):
    fresh_hash = planner.session_state["last_run_inputs_hash"]
    assert not any(STALE_TEXT in t for t in _texts(planner))
    fresh = _signature(planner)

    planner.session_state["last_run_inputs_hash"] = "not-the-current-hash"
    planner.run()
    assert not planner.exception, planner.exception
    assert any(STALE_TEXT in t for t in _texts(planner))
    stale = _signature(planner)

    planner.session_state["last_run_inputs_hash"] = fresh_hash
    planner.run()
    assert not any(STALE_TEXT in t for t in _texts(planner))
    back = _signature(planner)

    assert len(fresh) == len(stale) == len(back)
    assert fresh == stale == back


def test_setup_banner_and_bridge_slot_always_take_a_slot(planner):
    sig = _signature(planner)
    assert ("Block", "mc-setup-banner-slot") in sig
    assert ("Block", "mc-bridge-slot") in sig
    assert ("Block", "mc-tile-bridge") not in sig  # the tile is inside the slot


def _block_keys(node, out=None):
    out = [] if out is None else out
    for c in node.children.values():
        if type(c).__name__ == "Block":
            ident = getattr(getattr(c, "proto", None), "id", "") or ""
            m = re.search(r"-(mc-[a-z0-9-]+)$", ident)
            if m:
                out.append(m.group(1))
            _block_keys(c, out)
    return out


def test_bridge_tile_is_drawn_only_with_results(planner):
    """With no results, the slot is there but no bordered bridge tile. The phone chips look
    for the tile element, and a bordered block is drawn in the page even when it is empty."""
    assert "mc-tile-bridge" in _block_keys(planner.main)
    with_results = planner.session_state["results"]
    try:
        planner.session_state["results"] = None
        planner.run()
        assert not planner.exception, planner.exception
        keys = _block_keys(planner.main)
        assert "mc-bridge-slot" in keys
        assert "mc-tile-bridge" not in keys
    finally:
        planner.session_state["results"] = with_results
        planner.run()


def test_app_draws_the_slots_unconditionally():
    assert 'key="mc-setup-banner-slot"' in APP
    # The slot is unbordered (Streamlit draws an empty one as nothing); the tile is bordered.
    assert re.search(r'st\.container\(key="mc-bridge-slot"\)', APP)
    assert not re.search(r'container\(border=True, key="mc-bridge-slot"', APP)
    assert re.search(r'if results:\s*\n\s*with st\.container\(border=True, key="mc-tile-bridge"', APP)


def test_no_css_hides_the_bridge_tile():
    assert "st-key-mc-tile-bridge:not(" not in CSS
