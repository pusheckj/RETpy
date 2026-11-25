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
    assert line.startswith(f"Typical childcare in California: ${est.per_child:,}/yr per child over the first five years (2026 dollars)")
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


def _monthly(overrides, age=0):
    """The typical childcare a month for a child of this age (0 = planned or newborn)."""
    est, _ = cc.for_household(overrides, child_age=age)
    return round(est.per_child / 12)


def _shift(delta, age=None, leaves=18):
    """How far the monthly cost falls when childcare rises by ``delta`` a month: the money moves
    over the childcare years still ahead against the years at home still ahead."""
    a = max(0, age or 0)
    return round(delta * max(0, cfg.CHILDCARE_END_AGE - a) / max(1, leaves - a))


def _future_cost(kid, age=0):
    """What the plan still charges for one child from today (today's dollars, before growth)."""
    a, leaves = max(0, age), kid["leaves_home_age"]
    return (kid["monthly_cost"] * 12 * max(0, leaves - a)
            + kid["childcare_monthly"] * 12 * max(0, cfg.CHILDCARE_END_AGE - a))


KID_AGE1, KID_PLANNED = 1, 0          # FAMILY's two children: age 1 now, and planned


def test_use_typical_moves_childcare_into_its_box_and_lowers_the_monthly_cost(draw):
    ov = {**FAMILY, "BENCH_AREA": SD}
    at = draw(ov)
    m_planned, m_age1 = _monthly(ov, 0), _monthly(ov, 1)
    buttons = [b for b in at.button if b.key and b.key.endswith("use_care")]
    assert len(buttons) == 2
    assert f"${m_age1:,}" in buttons[0].label.replace("\\", "")       # the child's own years ahead
    assert f"${m_planned:,}" in buttons[1].label.replace("\\", "")
    before = _kids(at)
    assert [k["childcare_monthly"] for k in before] == [0, 0]       # nothing changes on its own
    buttons[0].click().run()
    assert not at.exception, at.exception
    after = _kids(at)
    assert after[0]["childcare_monthly"] == m_age1
    assert after[0]["monthly_cost"] == 2_100 - _shift(m_age1, age=1)   # 4 childcare years of 17 at home
    assert after[1] == before[1]                                    # only the child you clicked
    assert at.number_input(key="se_kid0_care").value == m_age1
    assert at.number_input(key="se_kid0_cost").value == after[0]["monthly_cost"]
    assert _care(at, 0).disabled                                    # already at the typical figure


def test_a_planned_child_uses_five_over_the_years_at_home(draw):
    ov = {**FAMILY, "BENCH_AREA": SD}
    at = draw(ov)
    m = _monthly(ov, 0)
    _care(at, 1).click().run()
    assert _kids(at)[1]["monthly_cost"] == 1_400 - round(m * 5 / 18)


def test_a_child_of_three_or_four_gets_a_figure_for_the_preschool_years_still_ahead(draw):
    ov = {**FAMILY, "BENCH_AREA": SD, "CHILDREN": [{"years_until_birth": -3, "monthly_cost": 2_100},
                                                   {"years_until_birth": -4, "monthly_cost": 2_100}]}
    for age in (3, 4):
        assert cc.estimate("CA", SD, child_age=age).weights == pytest.approx([0, 0, 1.0, 0])
    at = draw(ov)
    for age, i in ((3, 0), (4, 1)):
        m = _monthly(ov, age)
        assert m < _monthly(ov, 0)                       # preschool alone costs less than the 0-4 mix
        _care(at, i).click().run()
        kid = _kids(at)[i]
        assert kid["childcare_monthly"] == m
        assert kid["monthly_cost"] == 2_100 - _shift(m, age=age)        # (5-age) of (18-age) years


def test_the_future_cost_is_unchanged_for_every_age(draw):
    ov = {**FAMILY, "BENCH_AREA": SD}
    for age in (0, 1, 2, 3, 4):
        kids = [{"years_until_birth": -age, "monthly_cost": 2_100}]
        at = draw({**ov, "CHILDREN": kids})
        before = _kids(at)[0]
        _care(at, 0).click().run()
        after = _kids(at)[0]
        assert after["childcare_monthly"] > 0 and after["monthly_cost"] < before["monthly_cost"]
        assert abs(_future_cost(after, age) - _future_cost(before, age)) <= 12 * (18 - age)   # < $1 a month


def test_a_planned_childs_total_is_unchanged_with_the_default_figures(draw):
    at = draw({**FAMILY, "BENCH_AREA": SD})
    before = _kids(at)
    _care(at, 0).click().run()
    _care(at, 1).click().run()
    for old, new, age in zip(before, _kids(at), (1, 0)):
        assert abs(_future_cost(new, age) - _future_cost(old, age)) <= 12 * 18


def test_use_typical_says_what_it_did_in_a_visible_caption(draw):
    ov = {**FAMILY, "BENCH_AREA": SD}
    at = draw(ov)
    m = _monthly(ov, 1)
    _care(at, 0).click().run()
    assert (f"Monthly cost lowered from $2,100 to ${2_100 - _shift(m, age=1):,}. "
            "The childcare part now sits in its own box.") in _captions(at)


def test_the_caption_goes_when_you_type_a_different_amount_and_does_not_come_back(draw):
    ov = {**FAMILY, "BENCH_AREA": SD}
    at = draw(ov)
    m = _monthly(ov, 1)
    _care(at, 0).click().run()
    assert any(c.startswith("Monthly cost lowered") for c in _captions(at))
    at.number_input(key="se_kid0_care").set_value(m + 50).run()
    assert not any(c.startswith("Monthly cost") for c in _captions(at))
    at.number_input(key="se_kid0_care").set_value(m).run()          # back to the typical figure by hand
    assert not any(c.startswith("Monthly cost") for c in _captions(at))


def test_when_the_monthly_cost_would_go_below_zero_the_childcare_amount_is_capped(draw):
    ov = {**FAMILY, "BENCH_AREA": SD,
          "CHILDREN": [{"years_until_birth": 0, "monthly_cost": 200, "childcare_monthly": 0}]}
    at = draw(ov)
    typical = _monthly(ov, 0)
    _care(at, 0).click().run()
    kid = _kids(at)[0]
    assert kid["monthly_cost"] == 0
    assert 0 < kid["childcare_monthly"] < typical                   # capped: only $200 a month can move
    assert abs(_future_cost(kid) - 200 * 12 * 18) <= 12 * 18        # the total is still what it was
    text = " ".join(_captions(at))
    assert "Childcare is set to" in text and "cannot go below $0" in text
    assert "lowered" not in text


def test_a_cost_that_rises_is_not_called_lowered(draw):
    ov = {**FAMILY, "BENCH_AREA": SD,
          "CHILDREN": [{"years_until_birth": 0, "monthly_cost": 1_000, "childcare_monthly": 5_000}]}
    at = draw(ov)
    _care(at, 0).click().run()
    text = " ".join(_captions(at))
    assert "Monthly cost raised from" in text and "lowered" not in text


def test_clicking_again_after_a_change_moves_only_the_difference(draw):
    ov = {**FAMILY, "BENCH_AREA": SD}
    at = draw(ov)
    m = _monthly(ov, 1)
    at.number_input(key="se_kid0_care").set_value(m - 500).run()
    cost = _kids(at)[0]["monthly_cost"]
    _care(at, 0).click().run()
    assert _kids(at)[0]["monthly_cost"] == max(0, cost - _shift(500, age=1))


def test_no_button_once_a_child_has_no_childcare_years_left_even_with_an_amount(draw):
    at = draw({**FAMILY, "BENCH_AREA": SD, "CHILDREN": [
        {"years_until_birth": -5, "monthly_cost": 1_000, "childcare_monthly": 800}]})
    assert "se_kid0_care" in {n.key for n in at.number_input}      # the amount can still be seen and cleared
    assert not [b for b in at.button if b.key == "se_kid0_use_care"]
    assert not [c for c in _captions(at) if c.startswith("Typical childcare")]


def test_the_typical_figure_follows_the_age_you_just_typed(draw):
    ov = {**FAMILY, "BENCH_AREA": SD, "CHILDREN": [{"years_until_birth": -1, "monthly_cost": 2_100}]}
    at = draw(ov)
    at.number_input(key="se_kid0_age").set_value(4).run()          # in the same run, not the next
    assert _care(at, 0).label.replace("\\", "").endswith(f"${_monthly(ov, 4):,}/mo")
    at.number_input(key="se_kid0_age").set_value(6).run()
    assert not [b for b in at.button if b.key == "se_kid0_use_care"]
    assert not [c for c in _captions(at) if c.startswith("Typical childcare")]


def test_move_childcare_arithmetic():
    from components import sec_family as sf
    assert sf.move_childcare(2_100, 0, 1_500, leaves_home_age=18, age=None) == (2_100 - round(1_500 * 5 / 18), 1_500)
    assert sf.move_childcare(2_100, 0, 1_500, 18, age=3) == (2_100 - round(1_500 * 2 / 15), 1_500)
    assert sf.move_childcare(2_100, 500, 300, 18, age=0)[0] > 2_100     # childcare falls: cost rises
    cost, care = sf.move_childcare(100, 0, 3_000, 18, age=0)
    assert cost == 0 and care == round(100 * 18 / 5)


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
    assert "Lowers the monthly cost" in _care(plain, 0).help


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


def test_every_sentence_of_the_family_childcare_copy_is_short(draw):
    import re
    at = draw({**FAMILY, "BENCH_AREA": SD})
    _care(at, 0).click().run()
    texts = _captions(at) + [b.help for b in at.button if b.key and b.key.endswith("use_care")]
    texts += [at.number_input(key=k).help for k in ("se_kid0_cost", "se_kid0_care")]
    for text in texts:
        for sentence in re.split(r"(?<=[.!?])\s+", text.replace("Source:", ". Source:")):
            assert len(sentence.split()) <= 20, sentence
