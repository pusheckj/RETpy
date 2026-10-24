"""Simulation batches that can run on the server or in the visitor's browser:
retirement_sim/mc_jobs.py (the shared work unit), sim_runner plans, and
utils/browser_compute.py (hand-off, validation, server takeover)."""
import json
import math
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import mc_jobs  # noqa: E402
from utils import browser_compute as bc  # noqa: E402
from utils import sim_runner as sr  # noqa: E402

SINGLE = {"YOUR_AGE": 30, "PARTNER_AGE": 0, "FILING_STATUS": "Single", "YOUR_BASE_SALARY": 90_000,
          "YOUR_401K": 40_000, "YOUR_CASH": 20_000, "TARGET_RETIREMENT_AGE": 55}


@pytest.fixture(autouse=True)
def _no_disk_cache(monkeypatch):
    monkeypatch.setattr(sr, "_disk", lambda: None)
    sr.clear_cache(include_disk=False)
    yield
    sr.clear_cache(include_disk=False)


# ---------------------------------------------------------------- codec + config state

def test_codec_round_trips_what_json_cannot_hold():
    obj = {"t": (1, 2.5, "x"), 3: "int key", (1, 2): [np.float64(1.5), np.int64(7)],
           "inf": float("inf"), "neg": float("-inf"), "$dollar": True, "arr": np.array([1.0, 2.0])}
    back = mc_jobs.loads(mc_jobs.dumps(obj))
    assert back["t"] == (1, 2.5, "x") and back[3] == "int key" and back[(1, 2)] == [1.5, 7]
    assert back["inf"] == math.inf and back["neg"] == -math.inf and back["$dollar"] is True
    assert back["arr"] == [1.0, 2.0]
    assert math.isnan(mc_jobs.loads(mc_jobs.dumps(float("nan"))))
    json.loads(mc_jobs.dumps(obj))                      # strict JSON: no bare Infinity/NaN


def test_config_state_restores_everything():
    before = mc_jobs.snapshot()
    with mc_jobs.config_state({"YOUR_AGE": 77, "BRAND_NEW_KEY": 1}):
        assert cfg.YOUR_AGE == 77 and cfg.BRAND_NEW_KEY == 1
    assert mc_jobs.snapshot() == before and not hasattr(cfg, "BRAND_NEW_KEY")
    assert mc_jobs.diff({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4}) == {"b": 3, "c": 4}


# ---------------------------------------------------------------- early-stopping age scan

def test_scan_stops_early_only_far_from_the_target():
    orig = sr._apply_overrides(sr.build_config_overrides(SINGLE))
    try:
        hopeless = mc_jobs.scan_age(31, 200, 1, 0.80)          # retire next year: plainly fails
        assert hopeless["n"] < 200 and hopeless["successes"] / hopeless["n"] < 0.5
        again = mc_jobs.scan_age(31, 200, 1, 0.80)
        assert again == hopeless                                 # deterministic
        # near the target nothing stops: same as running every simulation
        near = mc_jobs.scan_age(31, 200, 1, hopeless["successes"] / hopeless["n"])
        assert near["n"] == 200
    finally:
        sr._restore_overrides(orig)


# ---------------------------------------------------------------- server == browser

_CHILD = r'''
import sys, json
sys.path.insert(0, sys.argv[1])
from retirement_sim import mc_jobs
job = sys.stdin.read()
n = mc_jobs.browser_load("j", job)
print(json.dumps([mc_jobs.browser_run("j", i) for i in range(n)]))
'''


def test_a_fresh_interpreter_with_only_the_job_matches_the_server():
    """What the browser does: start from config defaults, apply the job's plain
    data snapshot, run the calls. Must equal the server, bit for bit."""
    ov = {**SINGLE, "HOME_VALUE": 400_000, "MORTGAGE_BALANCE": 250_000, "MORTGAGE_MONTHLY": 2_000,
          "MORTGAGE_YEARS_REMAINING": 25, "HOUSE_MOVE_ENABLED": True}
    plan = sr.plan_mortgage_paydown(ov, 40, 55, extra_grid=[0, 12_000])
    assert plan.job["patches"][1] == {"EXTRA_MORTGAGE_PAYMENT_ANNUAL": 12_000.0}
    server = [mc_jobs.dumps(r) for r in sr.run_plan_calls(plan)]
    out = subprocess.run([sys.executable, "-c", _CHILD, _ROOT], input=mc_jobs.dumps(plan.job),
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == server


def test_a_fresh_interpreter_matches_the_server_with_three_children():
    """Children travel as a plain list in the config snapshot: three of them,
    one with college funding (its own 529), plus a younger partner whose
    plan-until age lengthens the plan."""
    kid = {"leaves_home_age": 18, "college_annual_cost": 30_000, "college_years": 4,
           "college_funding_pct": 0.0}
    ov = {**SINGLE, "PARTNER_AGE": 24, "FILING_STATUS": "Married filing jointly",
          "CHILDREN": [{**kid, "years_until_birth": -4, "monthly_cost": 1_200,
                        "college_funding_pct": 0.5},
                       {**kid, "years_until_birth": 1, "monthly_cost": 900},
                       {**kid, "years_until_birth": 4, "monthly_cost": 900}],
          "HOME_VALUE": 400_000, "MORTGAGE_BALANCE": 250_000, "MORTGAGE_MONTHLY": 2_000,
          "MORTGAGE_YEARS_REMAINING": 25}
    plan = sr.plan_mortgage_paydown(ov, 40, 55, extra_grid=[0, 12_000])
    assert len(plan.job["base"]["CHILDREN"]) == 3
    server = [mc_jobs.dumps(r) for r in sr.run_plan_calls(plan)]
    out = subprocess.run([sys.executable, "-c", _CHILD, _ROOT], input=mc_jobs.dumps(plan.job),
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == server


def test_split_plan_equals_the_all_server_run():
    plan = sr.plan_full_analysis(SINGLE, 120, 55)
    assert plan.local and all(plan.job["calls"][i][0] == "batch" for i in plan.local)
    whole = sr.execute_plan(sr.plan_full_analysis(SINGLE, 120, 55, (25, 76, 1)))
    sr.clear_cache(include_disk=False)
    plan = sr.plan_full_analysis(SINGLE, 120, 55)
    results = [None] * len(plan.job["calls"])
    for i, r in zip(plan.local, sr.run_plan_calls(plan, list(plan.local))):
        results[i] = r
    remote = [i for i in range(len(results)) if results[i] is None]
    with mc_jobs.config_state(mc_jobs.snapshot()):        # browser_run sets config globally
        mc_jobs.browser_load("t", mc_jobs.dumps(plan.job))
        for i in remote:
            results[i] = mc_jobs.loads(mc_jobs.browser_run("t", i))
    split = sr.finish_plan(plan, results)
    assert split["success_rate_by_age"] == whole["success_rate_by_age"]
    assert split["earliest_retirement_age"] == whole["earliest_retirement_age"]
    assert split["primary_result"]["success_rate"] == whole["primary_result"]["success_rate"]


def test_no_mortgage_means_no_paydown_sweep():
    plan = sr.plan_mortgage_paydown(SINGLE, 2000, 55)
    assert plan.result is not None and plan.result["no_mortgage"] and plan.result["curve"] == []


# ---------------------------------------------------------------- hand-off rules

class _St:
    def __init__(self):
        self.session_state = {}


@pytest.fixture
def fake_st(monkeypatch):
    monkeypatch.setenv("RETIREMENT_SIM_BROWSER_COMPUTE", "1")
    return _St()


def _browser_reply(job):
    """What the component would post for ``job``."""
    with mc_jobs.config_state(mc_jobs.snapshot()):
        n = mc_jobs.browser_load(job["id"], job["payload"])
        texts = [mc_jobs.browser_run(job["id"], i) for i in range(n)]
    return "[" + ",".join(texts) + "]"


def _submit(st, ov=SINGLE, n=60):
    sr.clear_cache(include_disk=False)              # a fresh job each time, not a cache hit
    got = {}
    plan = sr.plan_networth_analysis(ov, n_simulations=n)
    bc.submit(st, "fi", plan, lambda r: got.setdefault("result", r))
    return got, bc.pending(st, "fi")[0]


def test_result_is_taken_once_and_matches_the_server(fake_st):
    got, job = _submit(fake_st)
    msg = {"type": "result", "id": job["id"], "results": _browser_reply(job), "boot": "b1", "seq": 1}
    assert bc._receive(fake_st, msg) is True and not bc.pending(fake_st)
    assert bc._receive(fake_st, msg) is False                     # Streamlit re-delivers: ignored
    assert fake_st.session_state[bc.STATE]["ack"] == {"boot": "b1", "seq": 1}
    sr.clear_cache(include_disk=False)
    assert got["result"] == sr.run_networth_analysis(SINGLE, n_simulations=60)


def test_bad_reply_makes_the_server_do_it(fake_st):
    got, job = _submit(fake_st)
    forged = json.loads(_browser_reply(job))
    forged[0] = json.dumps({"success_rate": 7.0})                 # impossible rate
    msg = {"type": "result", "id": job["id"], "results": "[" + ",".join(
        f if isinstance(f, str) else json.dumps(f) for f in forged) + "]", "boot": "b", "seq": 1}
    assert bc._receive(fake_st, msg) is True
    assert 0.0 <= got["result"]["success_by_networth"][0]["success"] <= 1.0
    got2, job2 = _submit(fake_st)
    bc._receive(fake_st, {"type": "result", "id": job2["id"], "results": "not json", "boot": "b", "seq": 2})
    assert "result" in got2 and not bc.pending(fake_st)


def test_error_and_unavailable_hand_work_back(fake_st, monkeypatch):
    got, job = _submit(fake_st)
    bc._receive(fake_st, {"type": "error", "id": job["id"], "reason": "boom", "boot": "b", "seq": 1})
    assert "result" in got
    got, job = _submit(fake_st)
    bc._receive(fake_st, {"type": "status", "state": "unavailable", "reason": "no wasm", "boot": "b", "seq": 2})
    assert not bc.usable(fake_st) and bc.overdue(fake_st) == [job]
    assert bc.take_over_one(fake_st) and "result" in got and not bc.pending(fake_st)


def test_deadline_and_silent_component(fake_st, monkeypatch):
    got, job = _submit(fake_st)
    assert bc.overdue(fake_st) == []
    job["submitted"] -= bc.DEADLINE_EXTRA_S + 1
    assert bc.overdue(fake_st) == [job]
    s = fake_st.session_state[bc.STATE]
    s["seen"] = time.time() - bc.SILENT_COMPONENT_S - 1           # never heard from the browser
    assert not bc.usable(fake_st)


def test_disabled_locally_by_default(monkeypatch):
    monkeypatch.delenv("RETIREMENT_SIM_BROWSER_COMPUTE", raising=False)
    monkeypatch.delenv("RETIREMENT_SIM_HOSTED", raising=False)
    monkeypatch.setattr(bc, "is_hosted", lambda: False)
    assert not bc.enabled()
    monkeypatch.setattr(bc, "is_hosted", lambda: True)
    assert bc.enabled()
    monkeypatch.setenv("RETIREMENT_SIM_BROWSER_COMPUTE", "0")
    assert not bc.enabled()


def test_engine_bundle_is_the_engine_package():
    eng = bc.engine()
    assert set(eng["files"]) >= {"retirement_sim/__init__.py", "retirement_sim/config.py",
                                 "retirement_sim/account_simulation.py", "retirement_sim/mc_jobs.py",
                                 "retirement_sim/mc_parallel.py"}
    assert len(eng["hash"]) == 16


def test_a_job_submitted_after_drawing_asks_for_a_rerun(fake_st):
    assert not bc.unsent(fake_st)
    _submit(fake_st)
    assert bc.unsent(fake_st)            # app.main reruns so the component gets the job


def test_main_result_only_waits_for_a_ready_browser(fake_st):
    assert bc.usable(fake_st) and not bc.ready(fake_st)           # nothing heard yet: not ready
    bc._receive(fake_st, {"type": "status", "state": "loading", "has_files": True, "boot": "b", "seq": 1})
    assert bc.usable(fake_st) and not bc.ready(fake_st)           # extras may queue; main runs here
    bc._receive(fake_st, {"type": "status", "state": "ready", "engine": "x", "boot": "b", "seq": 2})
    assert bc.ready(fake_st)
