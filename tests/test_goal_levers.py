"""Ways to reach your goal (utils/goal_levers.py): the goal rule, the lever
overrides, the plan's rows, and the guardrail cushion the hero card shows.

The key promise: a lever's success rate is exactly what the plan shows after
"Keep this change" -- the lever runs the main run's seeded market paths under
the very overrides Keep writes.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components.profile_picker import PROFILES  # noqa: E402
from utils import goal_levers as gl  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402
from retirement_sim import config as cfg, mc_jobs, mc_parallel  # noqa: E402

COUPLE = "Mid-career couple (40, kids)"
N = 120


def _plan(age, **extra):
    return dict(PROFILES[COUPLE], TARGET_RETIREMENT_AGE=age, **extra)


def _main(ov, age, n=N):
    """The parts of a full analysis the levers read, without the age scan."""
    rate = _rate(ov, age, n)
    return {"primary_result": {"success_rate": rate, "retirement_age": age},
            "config_snapshot": {"TARGET_SUCCESS_RATE": float(ov.get("TARGET_SUCCESS_RATE") or 0.80)},
            "earliest_retirement_age": None}


def _rate(ov, age, n=N):
    """Success over the main run's seeded paths (what the hero shows for ``ov``)."""
    o = sr._apply_overrides(build_config_overrides(ov))
    try:
        r = mc_parallel.sim_task((age, n, 0, mc_jobs.PATH_SEED))
    finally:
        sr._restore_overrides(o)
    return r["successes"] / r["n"]


# ---------------------------------------------------------------- pure rules

@pytest.mark.parametrize("success,target,goal", [
    (0.737, 0.80, 0.80),      # below your own target: reach it
    (0.85, 0.80, 0.90),       # above it: the next step up
    (0.92, 0.80, 0.95),
    (0.93, 0.95, 0.95),       # a 95% target
    (0.95, 0.80, None),       # 95% and up: "You have room"
    (0.99, 0.80, None),
])
def test_goal_rule(success, target, goal):
    assert gl.goal_for(success, target) == goal


@pytest.mark.parametrize("rate,band", [(0.10, "Needs attention"), (0.649, "Needs attention"),
                                        (0.65, "Fair"), (0.799, "Fair"), (0.80, "Good"),
                                        (0.899, "Good"), (0.90, "Strong"), (1.0, "Strong")])
def test_success_band(rate, band):
    assert gl.success_band(rate) == band


def test_monthly_text_rounds_and_never_says_zero():
    assert gl.monthly_text(12 * 1_830) == "$1,800"
    assert gl.monthly_text(12 * 473) == "$450"
    assert gl.monthly_text(12 * 10) == "$50"
    assert gl.monthly_text(-12 * 1_830) == "$1,800"


def test_lever_sims_follow_the_main_run_but_are_capped():
    assert gl.lever_sims(500) == 500
    assert gl.lever_sims(1000) == 1000
    assert gl.lever_sims(10_000) == 2000


def test_spend_changes_keep_the_plans_own_terms():
    same = {"RETIREMENT_SPENDING_MODE": "Same as today's expenses"}
    assert gl.spend_changes(same, 0.85, 80_000) == {
        "RETIREMENT_SPENDING_MODE": gl.PCT_MODE, "RETIREMENT_SPENDING_PCT": 0.85}
    pct = {"RETIREMENT_SPENDING_MODE": gl.PCT_MODE, "RETIREMENT_SPENDING_PCT": 0.80}
    assert gl.spend_changes(pct, 0.90, 80_000)["RETIREMENT_SPENDING_PCT"] == 0.72
    absolute = {"RETIREMENT_SPENDING_MODE": gl.ABS_MODE, "RETIREMENT_SPENDING_ABSOLUTE": 70_000}
    assert gl.spend_changes(absolute, 0.85, 80_000) == {"RETIREMENT_SPENDING_ABSOLUTE": 59_500}
    # Below the slider's 50%, the share becomes an absolute amount.
    low = {"RETIREMENT_SPENDING_MODE": gl.PCT_MODE, "RETIREMENT_SPENDING_PCT": 0.55}
    assert gl.spend_changes(low, 0.75, 80_000) == {
        "RETIREMENT_SPENDING_MODE": gl.ABS_MODE, "RETIREMENT_SPENDING_ABSOLUTE": 33_000}


# ---------------------------------------------------------------- the plan

@pytest.fixture(scope="module", autouse=True)
def _no_disk_cache():
    """Never read or write the disk tier (a hit would skip building the job)."""
    mp = pytest.MonkeyPatch()
    mp.setattr(sr, "_disk", lambda: None)
    sr.clear_cache(include_disk=False)
    yield
    sr.clear_cache(include_disk=False)
    mp.undo()


@pytest.fixture(scope="module")
def reach():
    ov = _plan(48)
    main = _main(ov, 48)
    plan = gl.plan_goal_levers(ov, N, 48, main)
    return ov, main, plan, sr.execute_plan(plan)


def test_reach_rows_are_honest_and_ordered(reach):
    ov, main, plan, res = reach
    assert res["mode"] == "reach" and res["n"] == N
    assert res["base"] == main["primary_result"]["success_rate"]
    assert res["goal"] == gl.goal_for(res["base"], 0.80)
    rows = res["rows"]
    assert 1 <= len(rows) <= gl.MAX_ROWS
    for r in rows:
        assert r["value"] > res["base"]                      # every row helps
        assert r["hit"] == (r["value"] >= res["goal"])       # the mark matches the value
        assert set(r["changes"]) <= {"TARGET_RETIREMENT_AGE", "PARTNER_RETIREMENT_AGE",
                                     "RETIREMENT_SPENDING_MODE", "RETIREMENT_SPENDING_PCT",
                                     "RETIREMENT_SPENDING_ABSOLUTE"}
    assert rows[0]["hit"] or not any(r["hit"] for r in rows)    # goal rows lead


def test_keeping_a_lever_reproduces_its_rate(reach):
    """The value on a row is what the plan shows after Keep: same paths, same overrides."""
    ov, main, plan, res = reach
    for r in res["rows"][:3]:
        kept = {**ov, **r["changes"]}
        age = int(kept["TARGET_RETIREMENT_AGE"])
        assert _rate(kept, age) == pytest.approx(r["value"]), r["label"]


def test_plan_calls_are_plain_data_and_cached(reach):
    ov, main, plan, res = reach
    # The browser gets the job as JSON and replies per call.
    assert mc_jobs.loads(mc_jobs.dumps(plan.job))["calls"] == plan.job["calls"]
    assert all(c[0] == "scan" and c[2][1] == N and c[2][4] == N for c in plan.job["calls"])
    again = gl.plan_goal_levers(ov, N, 48, main)
    assert again.result == res and again.job is None


def test_browser_replies_for_the_calls_are_accepted(reach):
    from utils import browser_compute as bc
    ov, main, plan, res = reach
    call = plan.job["calls"][0]
    reply = sr.run_plan_calls(plan, [0])[0]
    assert bc._plausible(call, mc_jobs.loads(mc_jobs.dumps(reply)))


def test_partner_lever_only_for_a_working_partner():
    ov = _plan(48)
    o = sr._apply_overrides(build_config_overrides(ov))
    try:
        ctx = gl._plan_context(ov)
    finally:
        sr._restore_overrides(o)
    kinds = {s["kind"] for s in gl._scenarios(ov, ctx, 48, 0.8, 0.8, None)}
    assert {"later", "spend", "partner", "combo"} == kinds
    single = dict(ctx, has_partner=False)
    assert "partner" not in {s["kind"] for s in gl._scenarios(ov, single, 48, 0.8, 0.8, None)}
    retired = dict(ctx, your_age=50)                 # already past the target age
    kinds = {s["kind"] for s in gl._scenarios(ov, retired, 48, 0.8, 0.8, None)}
    assert "later" not in kinds and "combo" not in kinds


def test_room_variant_for_a_strong_plan():
    ov = _plan(55)
    main = _main(ov, 55)
    main["earliest_retirement_age"] = 50
    assert main["primary_result"]["success_rate"] >= gl.ROOM_AT
    res = gl.run_goal_levers(ov, N, 55, main)
    assert res["mode"] == "room" and res["goal"] is None
    assert {r["kind"] for r in res["rows"]} <= {"earlier", "more"}
    for r in res["rows"]:
        assert r["value"] >= res["target"] and r["hit"]
    earlier = [r for r in res["rows"] if r["kind"] == "earlier"]
    if earlier:
        assert earlier[0]["changes"]["TARGET_RETIREMENT_AGE"] < 55


# ---------------------------------------------------------------- cushion

def test_cushion_reads_the_engines_guardrail():
    ov = _plan(48)
    c = gl.guardrail_cushion(ov, 48)
    o = sr._apply_overrides(build_config_overrides(ov))
    try:
        core = cfg.calculate_annual_expenses(48, 1.0, 1.0, retirement=True, retirement_age=48)
        flexible = (core - cfg.housing_annual(48)) * cfg.DISCRETIONARY_EXPENSE_RATIO
        g = cfg.SPENDING_GUARDRAILS
    finally:
        sr._restore_overrides(o)
    assert c["enabled"] is True
    assert c["drop"] == pytest.approx(1 - g["floor_trigger"])
    assert c["trim_year"] == pytest.approx(g["floor_reduction"] * flexible)


def test_cushion_follows_a_custom_rule_and_the_off_switch():
    rule = {**cfg.SPENDING_GUARDRAILS, "floor_trigger": 0.80, "floor_reduction": 0.10}
    c = gl.guardrail_cushion(_plan(48, SPENDING_GUARDRAILS=rule), 48)
    assert c["drop"] == pytest.approx(0.20) and c["cut"] == pytest.approx(0.10)
    off = gl.guardrail_cushion(_plan(48, DYNAMIC_SPENDING_ENABLED=False), 48)
    assert off["enabled"] is False


def test_clear_cache_clears_the_lever_caches():
    gl._CACHE[("x",)] = 1
    gl._CUSHION_CACHE[("y",)] = 2
    sr.clear_cache(include_disk=False)
    assert not gl._CACHE and not gl._CUSHION_CACHE


def test_guardrail_cushion_second_call_hits_the_cache(monkeypatch):
    """The cache is keyed on a digest. A second call must read it, not rebuild."""
    ov = _plan(48)
    gl._CUSHION_CACHE.clear()
    first = gl.guardrail_cushion(ov, 48)
    calls = []
    real = sr._apply_overrides
    monkeypatch.setattr(sr, "_apply_overrides", lambda o: calls.append(1) or real(o))
    assert gl.guardrail_cushion(ov, 48) == first
    assert calls == []
    gl._CUSHION_CACHE.clear()
