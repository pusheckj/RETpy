"""Family section: typical childcare for the household's area, and the box it fills.

The figure is BiggerPockets Money's method over DOL childcare prices (utils/childcare_cost.py).
"Use typical" copies it into the child's own childcare box; nothing is changed until you click.
"""
import os
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import childcare_cost as cc  # noqa: E402

SD = "San Diego-Chula Vista-Carlsbad, CA"
FAMILY = {"YOUR_AGE": 34, "PARTNER_AGE": 33, "STATE_CHOICE": "CA",
          "CHILDREN": [{"years_until_birth": -1, "monthly_cost": 2_100, "childcare_monthly": 0},
                       {"years_until_birth": 3, "monthly_cost": 1_400, "childcare_monthly": 0}]}


def _script():
    import os
    import sys
    sys.path[:0] = [os.environ["FC_TEST_UI"], os.path.dirname(os.environ["FC_TEST_UI"])]
    import streamlit as st
    from components import sec_family
    sec_family.render_body(st)


@pytest.fixture
def draw(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("FC_TEST_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")

    def make(overrides):
        at = AppTest.from_function(_script, default_timeout=60)
        at.session_state["user_overrides"] = dict(overrides)
        at.run()
        assert not at.exception, at.exception
        return at
    return make


def _captions(at):
    return [c.value.replace("\\$", "$") for c in at.caption]


def _typical(at):
    return next(c for c in _captions(at) if c.startswith("Typical childcare in"))


def _kids(at):
    return at.session_state["user_overrides"]["CHILDREN"]


def test_the_state_figure_shows_with_its_source(draw):
    at = draw(FAMILY)
    est, _ = cc.for_household(FAMILY)
    line = _typical(at)
    assert line.startswith(f"Typical childcare in California: ${est.per_child:,}/yr per child (2026 dollars)")
    assert "Source: US Dept. of Labor childcare prices" in line and "BiggerPockets Money" in line
    assert "not a quote" in line


def test_picking_an_area_changes_the_figure_and_is_saved(draw):
    at = draw(FAMILY)
    state_line = _typical(at)
    box = at.selectbox(key="se_kid_area")
    assert box.value == "California (statewide average)" and SD in box.options
    box.select(SD).run()
    assert not at.exception, at.exception
    est, _ = cc.for_household({**FAMILY, "BENCH_AREA": SD})
    assert _typical(at).startswith(f"Typical childcare in {SD}: ${est.per_child:,}/yr per child")
    assert _typical(at) != state_line
    assert at.session_state["user_overrides"]["BENCH_AREA"] == SD
    # Back to the statewide choice forgets the area.
    at.selectbox(key="se_kid_area").select("California (statewide average)").run()
    assert "BENCH_AREA" not in at.session_state["user_overrides"]


def test_use_typical_fills_that_childs_childcare_and_leaves_the_rest(draw):
    at = draw({**FAMILY, "BENCH_AREA": SD})
    est, _ = cc.for_household({**FAMILY, "BENCH_AREA": SD})
    monthly = round(est.per_child / 12)
    buttons = [b for b in at.button if b.key and b.key.endswith("use_care")]
    assert len(buttons) == 2 and f"${monthly:,}" in buttons[0].label.replace("\\", "")
    before = _kids(at)
    assert [k["childcare_monthly"] for k in before] == [0, 0]       # nothing changes on its own
    buttons[0].click().run()
    assert not at.exception, at.exception
    after = _kids(at)
    assert after[0]["childcare_monthly"] == monthly
    assert after[1]["childcare_monthly"] == 0                        # only the child you clicked
    assert [k["monthly_cost"] for k in after] == [2_100, 1_400]      # the flat cost is not touched
    assert at.number_input(key="se_kid0_care").value == monthly
    done = next(b for b in at.button if b.key == "se_kid0_use_care")
    assert done.disabled                                             # already at the typical figure


def test_the_childcare_box_is_its_own_input_and_is_saved(draw):
    at = draw(FAMILY)
    at.number_input(key="se_kid1_care").set_value(900).run()
    assert _kids(at)[1]["childcare_monthly"] == 900
    assert _kids(at)[0]["childcare_monthly"] == 0


def test_the_monthly_cost_help_points_at_the_childcare_box_once_it_is_used(draw):
    at = draw({**FAMILY, "CHILDREN": [{"years_until_birth": -1, "monthly_cost": 900,
                                       "childcare_monthly": 1_500}]})
    help_text = at.number_input(key="se_kid0_cost").help
    assert "Childcare is in the box below" in help_text


def test_no_children_no_suggestion_and_no_area_picker(draw):
    at = draw({**FAMILY, "CHILDREN": []})
    assert not [c for c in _captions(at) if c.startswith("Typical childcare")]
    assert not [s for s in at.selectbox if s.key == "se_kid_area"]


def test_the_summary_counts_childcare_for_a_child_under_five(draw):
    from components import sec_family
    s = sec_family.family_summary({**FAMILY, "CHILDREN": [
        {"years_until_birth": -1, "monthly_cost": 2_000, "childcare_monthly": 1_000},
        {"years_until_birth": -8, "monthly_cost": 500, "childcare_monthly": 1_000}]})
    assert s["monthly_cost"] == 3_000 + 500                          # the 8-year-old's childcare has ended
