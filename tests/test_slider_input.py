"""Sliders with a typed box beside them (ui/utils/slider_input.py).

Every planner slider keeps its own widget key (saved profiles, widget_sync and
user_overrides read it) and gets a number box under ``key + "__box"``. The two
stay in step through ``on_change`` callbacks, so a change to either is visible
on the very next draw. These tests drive the helper on its own, then through
the real sections (percent shown 4.0 / stored 0.04 included).
"""
import os
import re
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import slider_input as si  # noqa: E402


# ------------------------------------------------------------------ snap()

def test_snap_clamps_and_explains():
    assert si.snap(63, 0, 100, 5, True) == (63, None)            # off the step grid is kept
    v, note = si.snap(250, 0, 100, 5, True)
    assert v == 100 and "highest value is 100" in note
    v, note = si.snap(-4, 0, 100, 5, True)
    assert v == 0 and "lowest value is 0" in note


def test_snap_rounds_to_the_precision_of_the_step():
    assert si.snap(2.376, 0.0, 10.0, 0.25, False) == (2.38, None)
    assert si.snap(2.4, 0.0, 10.0, 0.5, False) == (2.4, None)
    assert si.snap(7.77, 0.0, 10.0, 0.5, False) == (7.8, None)    # one decimal for a 0.5 step
    assert si.snap(62.5, 50.0, 150.0, 5.0, False) == (62.0, None)  # a 5.0 step: whole numbers
    assert si.snap("abc", 0, 100, 5, True) == (None, None)


# ------------------------------------------------------------------ the helper alone

def _lone_slider():
    import os
    import sys
    sys.path[:0] = [os.environ["SLB_UI"]]
    import streamlit as st
    from utils.slider_input import slider_with_box
    st.session_state.setdefault("calls", 0)
    st.session_state["calls"] += 1
    v = slider_with_box(st, "Stock allocation (%)", 0, 100, 5, key="stock", unit="%",
                        value=80, help="Share in stocks.")
    st.session_state["got"] = v
    f = slider_with_box(st, "Inflation (%)", 0.0, 10.0, 0.25, key="infl", unit="%", value=2.75)
    st.session_state["got_f"] = f


@pytest.fixture
def lone(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SLB_UI", _UI)
    at = AppTest.from_function(_lone_slider, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def test_slider_keeps_its_key_and_the_box_has_a_derived_one(lone):
    assert [s.key for s in lone.slider] == ["stock", "infl"]
    assert [n.key for n in lone.number_input] == ["stock__box", "infl__box"]
    assert lone.slider(key="stock").value == 80 and lone.number_input(key="stock__box").value == 80
    assert lone.number_input(key="infl__box").value == pytest.approx(2.75)
    assert lone.session_state["got"] == 80 and lone.session_state["got_f"] == pytest.approx(2.75)


def test_dragging_the_slider_updates_the_box_on_the_same_run(lone):
    lone.slider(key="stock").set_value(40).run()
    assert not lone.exception
    assert lone.number_input(key="stock__box").value == 40
    assert lone.session_state["got"] == 40


def test_typing_in_the_box_moves_the_slider_on_the_same_run(lone):
    lone.number_input(key="stock__box").set_value(63).run()
    assert not lone.exception
    assert lone.slider(key="stock").value == 63
    assert lone.session_state["got"] == 63                         # the value callers use
    lone.number_input(key="infl__box").set_value(3.1).run()
    assert lone.slider(key="infl").value == pytest.approx(3.1)


class _FakeSt:
    def __init__(self, **state):
        self.session_state = dict(state)


@pytest.mark.parametrize("box_first", [False, True])
def test_a_stale_box_in_the_same_request_does_not_undo_the_slider(box_first):
    """A held arrow key sends the next request before the browser has the box value the
    last pass pushed, so the request has the NEW slider value beside the box's OLD one.
    Streamlit then calls both callbacks, in either order. The box must not count as a
    typed edit (it used to reset the slider: most key presses were lost)."""
    st = _FakeSt(s=61, s__box=55, s__seen=60)                      # slider moved 60 -> 61, box is stale
    if box_first:
        si._on_box(st, "s", 0, 100, 1, True)
        si._on_slider(st, "s", True, 0)
    else:
        si._on_slider(st, "s", True, 0)
        si._on_box(st, "s", 0, 100, 1, True)
    assert st.session_state["s"] == 61 and st.session_state["s__box"] == 61
    st.session_state.pop("s__moved", None)                         # the next draw clears the flag
    st.session_state["s__box"] = 30                                # a real typed value still works
    si._on_box(st, "s", 0, 100, 1, True)
    assert st.session_state["s"] == 30


def test_typing_outside_the_range_clamps_with_a_short_note(lone):
    lone.number_input(key="stock__box").set_value(250).run()
    assert lone.slider(key="stock").value == 100
    assert lone.number_input(key="stock__box").value == 100
    assert any("highest value is 100" in c.value for c in lone.caption)
    lone.number_input(key="stock__box").set_value(-5).run()
    assert lone.slider(key="stock").value == 0
    assert any("lowest value is 0" in c.value for c in lone.caption)
    # The note goes away with the next ordinary change.
    lone.slider(key="stock").set_value(50).run()
    assert not any("value is" in c.value for c in lone.caption)


def test_no_session_state_api_warning(lone):
    """The slider never gets value= (the caller or helper seeds the key), so
    Streamlit's "created with a default value but also set via Session State" is not raised."""
    lone.number_input(key="stock__box").set_value(10).run()
    lone.slider(key="stock").set_value(70).run()
    assert not lone.exception
    assert not [w for w in lone.warning]


def test_an_outside_change_to_the_slider_key_reseeds_the_box(monkeypatch):
    """A profile or preset load writes the slider's key (and widget_sync clears the box's)."""
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SLB_UI", _UI)
    at = AppTest.from_function(_lone_slider, default_timeout=30).run()
    at.session_state["stock"] = 25            # the slider's key moved, the box's keys did not
    at.run()
    assert not at.exception
    assert at.number_input(key="stock__box").value == 25
    # ... even when only the slider key moved and the helper's own keys survived.
    at.session_state["infl"] = 4.5
    at.run()
    assert at.number_input(key="infl__box").value == pytest.approx(4.5)


# ------------------------------------------------------------------ real sections

def _section_script():
    import os
    import sys
    sys.path[:0] = [os.environ["SLB_UI"], os.path.dirname(os.environ["SLB_UI"])]
    import streamlit as st
    from components import sec_assumptions, sec_retirement_goals, sec_income
    st.session_state.setdefault("user_overrides", {})
    if "load_profile" in st.session_state:        # what a preset / JSON load does, before the widgets draw
        from utils.widget_sync import sync_widgets_from_overrides
        st.session_state["user_overrides"] = st.session_state.pop("load_profile")
        sync_widgets_from_overrides(st)
    sec_assumptions.render_investing_body(st) if hasattr(sec_assumptions, "render_investing_body") \
        else sec_assumptions.render_body(st)
    sec_income.render_body(st)
    sec_retirement_goals.render_body(st)


@pytest.fixture
def planner_bits(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SLB_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    at = AppTest.from_function(_section_script, default_timeout=60)
    at.session_state["user_overrides"] = {"YOUR_AGE": 35, "PARTNER_AGE": 33,
                                          "TARGET_RETIREMENT_AGE": 55,
                                          "STOCK_ALLOCATION": 0.7, "EXPECTED_INFLATION": 0.03}
    at.run()
    assert not at.exception, at.exception
    return at


def test_existing_slider_keys_are_unchanged_and_each_has_a_box(planner_bits):
    keys = {s.key for s in planner_bits.slider}
    assert {"sa_stock_alloc", "sa_inflation", "sa_fee_bps", "ay_target_age",
            "rg_ss_claim", "rg_target_success", "si_your_growth"} <= keys
    boxes = {n.key for n in planner_bits.number_input if n.key.endswith("__box")}
    assert boxes == {k + "__box" for k in keys}


def test_a_typed_percent_is_stored_as_a_fraction(planner_bits):
    """Shown 4.5, stored 0.045: the conversion stays with the caller."""
    planner_bits.number_input(key="sa_inflation__box").set_value(4.5).run()
    assert planner_bits.slider(key="sa_inflation").value == pytest.approx(4.5)
    assert planner_bits.session_state["user_overrides"]["EXPECTED_INFLATION"] == pytest.approx(0.045)
    planner_bits.number_input(key="sa_stock_alloc__box").set_value(63).run()
    assert planner_bits.session_state["user_overrides"]["STOCK_ALLOCATION"] == pytest.approx(0.63)
    planner_bits.number_input(key="sa_fee_bps__box").set_value(12).run()
    assert planner_bits.session_state["user_overrides"]["INVESTMENT_FEE_RATE"] == pytest.approx(0.0012)


def test_dragging_a_real_slider_shows_in_its_box(planner_bits):
    planner_bits.slider(key="ay_target_age").set_value(50).run()
    assert planner_bits.number_input(key="ay_target_age__box").value == 50
    assert planner_bits.session_state["user_overrides"]["TARGET_RETIREMENT_AGE"] == 50


def test_boxes_start_on_the_loaded_profile(planner_bits):
    assert planner_bits.number_input(key="sa_stock_alloc__box").value == 70
    assert planner_bits.number_input(key="sa_inflation__box").value == pytest.approx(3.0)
    assert planner_bits.number_input(key="ay_target_age__box").value == 55


def test_sync_from_overrides_updates_the_boxes(planner_bits):
    """A preset or JSON load: widget_sync writes the slider keys, then the page redraws."""
    new = dict(planner_bits.session_state["user_overrides"])
    new.update(STOCK_ALLOCATION=0.55, EXPECTED_INFLATION=0.02, TARGET_RETIREMENT_AGE=62,
               INVESTMENT_FEE_RATE=0.0035)
    planner_bits.session_state["load_profile"] = new
    planner_bits.run()
    assert not planner_bits.exception
    assert planner_bits.slider(key="sa_stock_alloc").value == pytest.approx(55)
    assert planner_bits.number_input(key="sa_stock_alloc__box").value == 55
    assert planner_bits.number_input(key="sa_inflation__box").value == pytest.approx(2.0)
    assert planner_bits.number_input(key="ay_target_age__box").value == 62
    assert planner_bits.number_input(key="sa_fee_bps__box").value == 35


def test_reset_clears_the_helper_keys():
    from utils.widget_sync import reset_input_widget_state

    class _St:
        session_state = {"sa_stock_alloc": 70, "sa_stock_alloc__box": 70, "sa_stock_alloc__seen": 70,
                         "sa_stock_alloc__note": "x", "gs_target__box": 40, "keep_me": 1}
    reset_input_widget_state(_St)
    assert _St.session_state == {"keep_me": 1}


def test_every_slider_in_the_ui_goes_through_the_helper():
    """No bare st.slider is left in a component (a numeric select_slider is listed here on purpose)."""
    bare = []
    for name in sorted(os.listdir(os.path.join(_UI, "components"))):
        if name.endswith(".py"):
            text = open(os.path.join(_UI, "components", name), encoding="utf-8").read()
            bare += [name for m in re.finditer(r"\bst\.slider\(", text)]
    assert not bare, bare


def test_the_box_css_sits_before_the_top_card_block():
    css = open(os.path.join(_UI, "styles", "theme.css"), encoding="utf-8").read()
    start = css.index("Sliders with a typed box (utils/slider_input.py)")
    assert start < css.index("Top card layout. The card")
    assert "-- end Sliders with a typed box --" in css


def test_partner_retirement_can_be_typed_as_years_after_you(planner_bits):
    """The slider is in the partner's own age, so "3 years after me" needs arithmetic:
    a number box beside it says it directly and moves the slider."""
    at = planner_bits
    assert at.number_input(key="ay_partner_later").value == 0            # together by default
    at.number_input(key="ay_partner_later").set_value(3).run()
    assert not at.exception, at.exception
    assert at.slider(key="ay_partner_target_age").value == 56            # you retire at 55: partner is 53
    assert at.session_state["user_overrides"]["PARTNER_RETIREMENT_AGE"] == 56
    assert any("3 years after you" in c.value for c in at.caption)
    assert at.number_input(key="ay_partner_later").value == 3
    at.slider(key="ay_partner_target_age").set_value(50).run()           # drag instead: the box follows
    assert at.number_input(key="ay_partner_later").value == -3
    at.number_input(key="ay_partner_later").set_value(-2).run()
    assert at.session_state["user_overrides"]["PARTNER_RETIREMENT_AGE"] == 51
