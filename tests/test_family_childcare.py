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

from retirement_sim import config as cfg  # noqa: E402
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


def _care(at, i):
    return next(b for b in at.button if b.key == f"se_kid{i}_use_care")


def _monthly(overrides=FAMILY):
    est, _ = cc.for_household(overrides)
    return round(est.per_child / 12)


def _lifetime(kid):
    """What the engine charges for one child over their years at home (today's dollars)."""
    years = kid["leaves_home_age"]
    return (kid["monthly_cost"] * 12 * years
            + kid["childcare_monthly"] * 12 * min(cfg.CHILDCARE_END_AGE, years))


def test_use_typical_moves_childcare_into_its_box_and_lowers_the_monthly_cost(draw):
    at = draw({**FAMILY, "BENCH_AREA": SD})
    monthly = _monthly({**FAMILY, "BENCH_AREA": SD})
    buttons = [b for b in at.button if b.key and b.key.endswith("use_care")]
    assert len(buttons) == 2 and f"${monthly:,}" in buttons[0].label.replace("\\", "")
    before = _kids(at)
    assert [k["childcare_monthly"] for k in before] == [0, 0]       # nothing changes on its own
    buttons[0].click().run()
    assert not at.exception, at.exception
    after = _kids(at)
    lowered = round(monthly * cfg.CHILDCARE_END_AGE / 18)
    assert after[0]["childcare_monthly"] == monthly
    assert after[0]["monthly_cost"] == 2_100 - lowered
    assert after[1] == before[1]                                    # only the child you clicked
    assert at.number_input(key="se_kid0_care").value == monthly
    assert at.number_input(key="se_kid0_cost").value == 2_100 - lowered
    assert _care(at, 0).disabled                                    # already at the typical figure


def test_use_typical_says_what_it_did_in_a_visible_caption(draw):
    at = draw({**FAMILY, "BENCH_AREA": SD})
    monthly = _monthly({**FAMILY, "BENCH_AREA": SD})
    _care(at, 0).click().run()
    lowered = round(monthly * cfg.CHILDCARE_END_AGE / 18)
    assert (f"Monthly cost lowered from $2,100 to ${2_100 - lowered:,}. "
            "The childcare part now sits in its own box.") in _captions(at)


def test_with_the_default_figures_a_childs_lifetime_cost_is_unchanged(draw):
    """The default $2,100 a month already holds childcare. Moving it to the early years must not
    add to the total (to the rounding of whole dollars a month)."""
    at = draw({**FAMILY, "BENCH_AREA": SD})
    before = _kids(at)
    _care(at, 0).click().run()
    _care(at, 1).click().run()
    after = _kids(at)
    for old, new in zip(before, after):
        assert abs(_lifetime(new) - _lifetime(old)) <= 12 * 18          # under one dollar a month either way
        assert new["childcare_monthly"] > 0 and new["monthly_cost"] < old["monthly_cost"]


def test_a_monthly_cost_never_goes_below_zero(draw):
    at = draw({**FAMILY, "BENCH_AREA": SD,
               "CHILDREN": [{"years_until_birth": -1, "monthly_cost": 200, "childcare_monthly": 0}]})
    _care(at, 0).click().run()
    assert _kids(at)[0]["monthly_cost"] == 0


def test_clicking_again_after_a_change_moves_only_the_difference(draw):
    at = draw({**FAMILY, "BENCH_AREA": SD})
    monthly = _monthly({**FAMILY, "BENCH_AREA": SD})
    at.number_input(key="se_kid0_care").set_value(monthly - 500).run()
    cost = _kids(at)[0]["monthly_cost"]
    _care(at, 0).click().run()
    assert _kids(at)[0]["monthly_cost"] == max(0, cost - round(500 * cfg.CHILDCARE_END_AGE / 18))


def test_childcare_box_is_only_for_planned_children_and_children_under_five(draw):
    kids = [{"years_until_birth": -4, "monthly_cost": 1_000}, {"years_until_birth": -5, "monthly_cost": 1_000},
            {"years_until_birth": 2, "monthly_cost": 1_000}, {"years_until_birth": 0, "monthly_cost": 1_000}]
    at = draw({**FAMILY, "CHILDREN": kids})
    keys = {n.key for n in at.number_input}
    assert "se_kid0_care" in keys and "se_kid2_care" in keys and "se_kid3_care" in keys   # age 4, planned, newborn
    assert "se_kid1_care" not in keys                                                   # age 5
    assert not [b for b in at.button if b.key == "se_kid1_use_care"]


def test_the_childcare_box_is_its_own_input_and_is_saved(draw):
    at = draw(FAMILY)
    at.number_input(key="se_kid1_care").set_value(900).run()
    assert _kids(at)[1]["childcare_monthly"] == 900
    assert _kids(at)[0]["childcare_monthly"] == 0


def test_the_help_text_says_where_childcare_sits_and_is_right_about_the_years(draw):
    at = draw({**FAMILY, "CHILDREN": [{"years_until_birth": -1, "monthly_cost": 900,
                                       "childcare_monthly": 1_500}]})
    assert "Childcare for the first five years is in the box below" in at.number_input(key="se_kid0_cost").help
    plain = draw(FAMILY)
    help_text = plain.number_input(key="se_kid0_cost").help
    assert "lower this by the same amount" not in help_text
    assert "Use typical" in help_text
    assert "lowers the monthly cost" in plain.number_input(key="se_kid0_care").help


def test_no_children_no_suggestion_and_no_area_picker(draw):
    at = draw({**FAMILY, "CHILDREN": []})
    assert not [c for c in _captions(at) if c.startswith("Typical childcare")]
    assert not [s for s in at.selectbox if s.key == "se_kid_area"]


def test_no_suggestion_when_every_child_is_past_the_childcare_years(draw):
    at = draw({**FAMILY, "CHILDREN": [{"years_until_birth": -9, "monthly_cost": 1_000},
                                      {"years_until_birth": -6, "monthly_cost": 1_000}]})
    assert not [c for c in _captions(at) if c.startswith("Typical childcare")]
    assert not [s for s in at.selectbox if s.key == "se_kid_area"]


def test_the_summary_counts_childcare_for_a_child_under_five(draw):
    from components import sec_family
    s = sec_family.family_summary({**FAMILY, "CHILDREN": [
        {"years_until_birth": -1, "monthly_cost": 2_000, "childcare_monthly": 1_000},
        {"years_until_birth": -8, "monthly_cost": 500, "childcare_monthly": 1_000}]})
    assert s["monthly_cost"] == 3_000 + 500                          # the 8-year-old's childcare has ended
