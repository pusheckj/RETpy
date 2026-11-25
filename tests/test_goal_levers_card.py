"""The "Ways to reach your goal" card and the hero's success band.

The card (components/goal_levers.py) is driven through AppTest with a lever
result already in session state, the way app._queue_extras leaves it: Try it
previews without touching the inputs, Keep writes the overrides + syncs the
side-panel widgets + re-arms the run, Undo puts everything back. The hero
band (components/hero_metric.py) is checked on its HTML.
"""
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components.profile_picker import PROFILES  # noqa: E402
from utils.sim_runner import _hashable  # noqa: E402

APP = open(os.path.join(_UI, "app.py"), encoding="utf-8").read()
CSS = open(os.path.join(_UI, "styles", "theme.css"), encoding="utf-8").read()
BLOCK = CSS[CSS.index("Results headline: success band"):CSS.index("-- end Results headline --")]

N_SIMS = 1000


def _overrides():
    return dict(PROFILES["Mid-career couple (40, kids)"], TARGET_RETIREMENT_AGE=48,
                PARTNER_RETIREMENT_AGE=46)


def _stamp(ov):
    return hash((_hashable(ov), N_SIMS))


def _levers(stamp, mode="reach"):
    rows = [
        {"id": "later-3", "kind": "later", "label": "Retire at 51 instead of 48",
         "sub": "3 more working years", "value": 0.937, "hit": True, "age": 51,
         "changes": {"TARGET_RETIREMENT_AGE": 51}},
        {"id": "spend-0.15", "kind": "spend", "label": "Spend 15% less in retirement",
         "sub": "about $1,100/mo less", "value": 0.86, "hit": False, "age": 48,
         "changes": {"RETIREMENT_SPENDING_MODE": "% of today's expenses",
                     "RETIREMENT_SPENDING_PCT": 0.85}},
    ]
    return {"mode": mode, "goal": 0.90 if mode == "reach" else None, "target": 0.80,
            "base": 0.737, "target_age": 48, "n": N_SIMS, "rows": rows, "_inputs_hash": stamp}


def _results():
    return {"primary_result": {"success_rate": 0.737, "retirement_age": 48},
            "config_snapshot": {"TARGET_SUCCESS_RATE": 0.80}, "earliest_retirement_age": 50}


def _card_page():
    import os
    import sys
    sys.path[:0] = [os.environ["GOAL_TEST_UI"], os.path.dirname(os.environ["GOAL_TEST_UI"])]
    import streamlit as st
    from components import goal_levers
    goal_levers.render(st, st.session_state.get("results"))


@pytest.fixture
def card():
    from streamlit.testing.v1 import AppTest
    os.environ["GOAL_TEST_UI"] = _UI
    ov = _overrides()
    at = AppTest.from_function(_card_page, default_timeout=60)
    at.session_state["user_overrides"] = ov
    at.session_state["n_simulations"] = N_SIMS
    at.session_state["results"] = _results()
    at.session_state["last_run_inputs_hash"] = _stamp(ov)
    at.session_state["goal_levers_result"] = _levers(_stamp(ov))
    at.session_state["_autorun_done"] = True
    at.session_state["ay_target_age"] = 48
    return at


def _text(at):
    return " ".join(m.value for m in at.markdown)


def test_card_shows_the_goal_and_one_row_per_lever(card):
    card.run()
    assert not card.exception, card.exception
    text = _text(card)
    assert "Ways to reach 90%" in text and "today 73.7%" in text
    assert "Retire at 51 instead of 48" in text and "Spend 15% less in retirement" in text
    assert "✓ goal" in text and text.count("✓ goal") == 1      # only the row that reaches it
    assert "&#36;1,100" in text                                 # no bare $ (KaTeX)
    assert [b.label for b in card.button] == ["Try it", "Try it"]


def test_try_it_previews_without_changing_inputs(card):
    card.run()
    before = dict(card.session_state["user_overrides"])
    card.button(key="goal_try_later-3").click().run()
    assert not card.exception, card.exception
    preview = _text(card)
    assert "Preview:" in preview and "73.7%" in preview and "93.7%" in preview
    assert "target retirement age to 51" in preview
    assert card.session_state["user_overrides"] == before
    assert card.button(key="goal_try_later-3").label == "Close"
    card.button(key="goal_cancel_btn").click().run()
    assert "Preview:" not in _text(card)


def test_keep_writes_syncs_and_reruns_then_undo_restores(card):
    card.run()
    card.button(key="goal_try_later-3").click().run()
    card.button(key="goal_keep_btn").click().run()
    assert not card.exception, card.exception
    ss = card.session_state
    assert ss["user_overrides"]["TARGET_RETIREMENT_AGE"] == 51
    assert ss["ay_target_age"] == 51                    # the side panel shows it
    assert ss["results"] is None                        # results belong to old inputs
    assert "_autorun_done" not in ss                    # so the plan runs again
    assert ss["goal_undo"]["applied"] == {"TARGET_RETIREMENT_AGE": 51}
    # Pretend the rerun finished: the card shows the Undo bar for the kept change.
    ov = dict(ss["user_overrides"])
    ss["results"] = _results()
    ss["last_run_inputs_hash"] = _stamp(ov)
    card.run()
    assert "Kept:" in _text(card) and "Retire at 51 instead of 48" in _text(card)
    card.button(key="goal_undo_btn").click().run()
    assert not card.exception, card.exception
    assert ss["user_overrides"]["TARGET_RETIREMENT_AGE"] == 48
    assert ss["ay_target_age"] == 48
    assert ss["results"] is None and "goal_undo" not in ss


def test_undo_of_a_missing_key_removes_it_and_reseeds_the_widget(card):
    card.run()
    ov = dict(card.session_state["user_overrides"])
    ov.pop("RETIREMENT_SPENDING_PCT", None)
    card.session_state["user_overrides"] = ov
    card.session_state["last_run_inputs_hash"] = _stamp(ov)
    card.session_state["goal_levers_result"] = _levers(_stamp(ov))
    card.run()
    card.button(key="goal_try_spend-0.15").click().run()
    card.button(key="goal_keep_btn").click().run()
    ss = card.session_state
    assert ss["user_overrides"]["RETIREMENT_SPENDING_PCT"] == 0.85
    assert ss["rg_spend_pct"] == 85.0
    assert ss["goal_undo"]["prev"]["RETIREMENT_SPENDING_PCT"] == "__missing__"
    ss["results"] = _results()
    card.run()
    card.button(key="goal_undo_btn").click().run()
    assert "RETIREMENT_SPENDING_PCT" not in ss["user_overrides"]
    assert "rg_spend_pct" not in ss                      # seeds again from the inputs


def test_undo_bar_goes_once_the_input_is_changed_by_hand(card):
    card.run()
    card.button(key="goal_try_later-3").click().run()
    card.button(key="goal_keep_btn").click().run()
    ss = card.session_state
    ss["user_overrides"] = dict(ss["user_overrides"], TARGET_RETIREMENT_AGE=53)
    ss["results"] = _results()
    card.run()
    assert "Kept:" not in _text(card)


def test_keep_is_off_when_the_results_are_stale(card):
    card.run()
    card.session_state["user_overrides"] = dict(card.session_state["user_overrides"], YOUR_AGE=41)
    card.button(key="goal_try_later-3").click().run()
    assert card.button(key="goal_keep_btn").disabled
    assert any("Run the simulation again" in c.value for c in card.caption)


def test_placeholder_while_computing_and_nothing_for_other_runs(card):
    card.session_state["goal_levers_result"] = None
    card.session_state["_extras_pending"] = [("levers", None, None)]
    card.run()
    assert "Finding ways to reach 80%…" in _text(card)
    assert not card.get("progress")                       # never st.progress (overlay)
    card.session_state["_extras_pending"] = []
    card.session_state["goal_levers_result"] = _levers(12345)    # another run's levers
    card.run()
    assert "Ways to reach" not in _text(card) and not card.button


def test_room_variant(card):
    card.session_state["goal_levers_result"] = _levers(card.session_state["last_run_inputs_hash"], "room")
    card.run()
    text = _text(card)
    assert "You have room" in text and "still meet your 80% target" in text
    assert "✓ target" in text


def test_app_queues_the_levers_and_draws_the_card_under_the_hero():
    assert 'plans.append(("levers", goal_levers.plan_goal_levers(' in APP
    hero = APP.index('_safe_render("components.hero_metric", results=results)')
    card = APP.index('_safe_render("components.goal_levers", results=results)')
    narrative = APP.index('_safe_render("components.decision_narrative", results=results)')
    assert hero < card < narrative
    assert "def _sec_goal_levers" in APP                   # a fragment: Try it redraws the card only
    src = open(os.path.join(_UI, "components", "goal_levers.py"), encoding="utf-8").read()
    assert "st.progress(" not in src


# ---------------------------------------------------------------- hero band

class _FakeSt:
    def __init__(self, overrides=None):
        self.session_state = {"user_overrides": overrides or {}}
        self.calls = []

    def markdown(self, text, **kwargs):
        self.calls.append(text)


def _hero(rate=0.737, snap=None, overrides=None, networth=None, n=1000):
    from components import hero_metric
    st = _FakeSt(overrides)
    primary = {"retirement_age": 48, "success_rate": rate, "n_simulations": n}
    if networth is not None:
        primary["networth_by_year"] = networth
    hero_metric.render(st, {"earliest_retirement_age": 50, "primary_result": primary,
                            "config_snapshot": snap or {"TARGET_SUCCESS_RATE": 0.80}})
    return "\n".join(st.calls)


COUPLE_SNAP = {"TARGET_SUCCESS_RATE": 0.80, "YOUR_AGE": 40, "PARTNER_AGE": 38,
               "PLAN_UNTIL_AGE": 95, "PARTNER_PLAN_UNTIL_AGE": 95, "DYNAMIC_SPENDING_ENABLED": True}


@pytest.mark.parametrize("rate,band", [(0.40, "Needs attention"), (0.737, "Fair"),
                                        (0.85, "Good"), (0.993, "Strong")])
def test_band_names_the_zone_and_marks_it(rate, band):
    html = _hero(rate, COUPLE_SNAP)
    assert f"<b>{band}.</b>" in html
    assert re.search(rf'mc-band-label mc-band-on[^"]*"[^>]*>{band}<', html)
    for name in ("Needs attention", "Fair", "Good", "Strong"):
        assert f">{name}</span>" in html
    assert "Fair: 65% to 80%" in html and "Needs attention: below 65%" in html  # thresholds on hover


def test_band_counts_markets_until_the_plan_ends():
    html = _hero(0.737, COUPLE_SNAP)
    assert "737 of 1,000 simulated markets last until your partner turns 95." in html
    single = dict(COUPLE_SNAP, PARTNER_AGE=0)
    assert "until you turn 95." in _hero(0.737, single)


def test_cushion_uses_the_median_balance_and_the_rule():
    ov = _overrides()
    nw = [{"age": 48, "p50": 3_000_000.0}]
    html = _hero(0.737, COUPLE_SNAP, ov, nw)
    assert "Your cushion:" in html and "&#36;3.0M" in html
    assert "&#36;900,000</b> (30%)" in html
    assert "$" not in re.sub(r"&#36;", "", html)
    rule = {"floor_trigger": 0.80, "floor_reduction": 0.15, "ceiling_trigger": 1.3, "ceiling_increase": 0}
    html = _hero(0.737, COUPLE_SNAP, dict(ov, SPENDING_GUARDRAILS=rule), nw)
    assert "&#36;600,000</b> (20%)" in html


def test_no_cushion_when_spending_never_adjusts():
    html = _hero(0.737, dict(COUPLE_SNAP, DYNAMIC_SPENDING_ENABLED=False,
                             RETURN_BASED_SPENDING_ENABLED=False), _overrides(),
                 [{"age": 48, "p50": 3_000_000.0}])
    assert "Spending never adjusts." in html and "Your cushion" not in html


def test_band_css_has_phone_and_dark_rules():
    assert ".mc-band-label.mc-band-alt { top: 16px; }" in BLOCK      # staggered names on a phone
    assert '.stApp:has([id$="dark-theme"]) .mc-band-z1' in BLOCK
    assert '.stApp:has([id$="dark-theme"]) :is(.mc-goal-fill, .mc-goal-dot)' in BLOCK
