"""sim_runner stability and security: the shared caches, the config module and
the worker pool must survive hostile or broken input.

Covers: browser results never enter the shared cache, a hung pool worker is cut
off at the deadline, a failed override leaves the shared config clean, engine
errors and a made-up trajectory are reported, every small cache is cleared and
bounded, and a target-age-only change reuses the success-by-age scans.
"""
import json
import logging
import os
import sys
import time

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import mc_jobs  # noqa: E402
from utils import browser_compute as bc  # noqa: E402
from utils import sim_runner as sr  # noqa: E402

SINGLE = {"YOUR_AGE": 30, "PARTNER_AGE": 0, "FILING_STATUS": "Single", "YOUR_BASE_SALARY": 130_000,
          "YOUR_401K": 40_000, "YOUR_CASH": 20_000, "TARGET_RETIREMENT_AGE": 55,
          "SPEND_RENT_MONTHLY": 500}
SCAN_RANGE = (50, 53, 1)


@pytest.fixture(autouse=True)
def _no_disk_cache(monkeypatch):
    monkeypatch.setattr(sr, "_disk", lambda: None)
    sr.clear_cache(include_disk=False)
    yield
    sr.clear_cache(include_disk=False)


class _St:
    def __init__(self):
        self.session_state = {}


@pytest.fixture
def fake_st(monkeypatch):
    monkeypatch.setenv("RETIREMENT_SIM_BROWSER_COMPUTE", "1")
    return _St()


def _full_plan(target=55):
    return sr.plan_full_analysis(SINGLE, 60, target, SCAN_RANGE)


def _scan_calls(plan):
    return [c for c in plan.job["calls"] if c[0] == "scan"]


# ------------------------------------------------------------- cache poisoning

def test_forged_browser_scan_reply_never_reaches_the_shared_cache(fake_st):
    plan = _full_plan()
    got = {}
    bc.submit(fake_st, "main", plan, lambda r: got.setdefault("result", r), run_here=plan.local)
    job = bc.pending(fake_st, "main")[0]
    forged = [{"age": c[2][0], "n": c[2][1], "successes": c[2][1], "errors": 0, "first_error": None}
              for c in (plan.job["calls"][i] for i in job["remote"])]
    msg = {"type": "result", "id": job["id"], "results": json.dumps(forged), "boot": "b", "seq": 1}
    assert bc._receive(fake_st, msg) is True
    assert "result" in got                                   # this visitor still gets an answer
    assert sr._CACHE.lookup(plan.key) is None                # ... but nobody else is served it
    assert not sr._SCAN_CACHE


def test_server_results_are_still_cached():
    plan = _full_plan()
    sr.execute_plan(plan)
    assert sr._CACHE.lookup(plan.key) is not None


def test_finish_plan_from_browser_skips_the_store():
    stored = []
    plan = sr.Plan("x", ("k",), {}, job={"calls": []}, finish=lambda r: {"v": 1}, store=stored.append)
    assert sr.finish_plan(plan, [], from_browser=True) == {"v": 1} and stored == []
    sr.finish_plan(plan, [])
    assert stored == [{"v": 1}]


# ------------------------------------------------------------------- pool wait

def test_hung_pool_worker_is_cut_off_at_the_deadline(monkeypatch):
    parent = os.getpid()

    def slow_in_workers(call, patches):
        if os.getpid() != parent:
            time.sleep(25)                                    # a hung worker
        return call[2][0]

    monkeypatch.setattr(mc_jobs, "run_call", slow_in_workers)
    monkeypatch.setattr(sr, "_POOL_TIMEOUT_S", 1)
    monkeypatch.setattr(sr, "_available_cpus", lambda: 4)
    monkeypatch.setenv("RETIREMENT_SIM_MAX_WORKERS", "2")
    job = {"calls": [["x", 0, [i]] for i in range(4)], "patches": []}
    t0 = time.time()
    out = sr._run_calls(job, [0, 1, 2, 3])
    assert out == [0, 1, 2, 3]                                # serial fallback, same results
    assert time.time() - t0 < 10


# ------------------------------------------------------------ dirty shared cfg

def test_failed_override_leaves_config_clean():
    before = {k: getattr(cfg, k) for k in ("YOUR_AGE", "YOUR_401K", "TOTAL_RETIREMENT_ACCOUNTS",
                                           "TOTAL_INVESTMENTS", "YOUR_BIRTH_YEAR")}
    with pytest.raises(Exception):
        sr._apply_overrides({"YOUR_401K": 123_456, "YOUR_AGE": "not-a-number"})
    assert {k: getattr(cfg, k) for k in before} == before
    assert sr.CONFIG_LOCK.acquire(timeout=1)                  # lock was released
    sr.CONFIG_LOCK.release()
    original = sr._apply_overrides({"YOUR_AGE": 41})          # a clean cycle still works
    try:
        assert cfg.YOUR_AGE == 41
    finally:
        sr._restore_overrides(original)
    assert {k: getattr(cfg, k) for k in before} == before


# ------------------------------------------------------- errors and fabrication

def _chunk(**kw):
    chunk = {"finals": [1e6] * 70, "successes": 70, "n": 70, "details": [], "spending_by_age": {},
             "errors": 30, "first_error": "ValueError('boom')"}
    chunk.update(kw)
    return chunk


def test_engine_errors_are_reported_not_dropped():
    primary = sr._assemble_primary_from_chunks(55, [_chunk(), _chunk(errors=0, first_error=None)])
    assert primary["sim_errors"] == 30
    assert primary["sim_first_error"] == "ValueError('boom')"
    assert primary["success_rate"] == 1.0                     # the maths is unchanged


def test_scan_errors_are_totalled_in_the_analysis_result():
    plan = _full_plan()
    n_primary = len(plan.job["calls"]) - len(_scan_calls(plan))
    primary = sr.run_plan_calls(plan, list(range(n_primary)))
    scans = [{"age": c[2][0], "n": 70, "successes": 70, "errors": 30, "first_error": "KeyError('x')"}
             for c in _scan_calls(plan)]
    result = sr.finish_plan(plan, primary + scans)
    assert result["scan_sim_errors"] == 30 * len(scans)
    assert result["scan_sim_first_error"] == "KeyError('x')"
    assert result["primary_result"]["sim_errors"] == 0


def test_chunk_path_flags_a_made_up_trajectory(caplog):
    with caplog.at_level(logging.WARNING, logger=sr.logger.name):
        primary = sr._assemble_primary_from_chunks(55, [_chunk()])
    assert primary["trajectory_is_synthetic"] is True
    assert any("placeholder" in r.message for r in caplog.records)
    real = {"trajectory": [(30, 1e5), (90, 2e5)], "success": True, "withdrawal_log": [], "bytype": []}
    assert sr._assemble_primary_from_chunks(55, [_chunk(details=[real])])["trajectory_is_synthetic"] is False


def test_collect_trajectories_logs_the_failure_and_the_caller_can_tell(monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("engine broke")
    monkeypatch.setattr(sr.sim, "run_detailed_simulation", boom)
    with caplog.at_level(logging.WARNING, logger=sr.logger.name):
        paths, portfolios, successes = sr._collect_trajectories(55, n_paths=3, seed=1)
    assert portfolios == [None] and successes == [False]
    assert any("engine broke" in r.message for r in caplog.records)
    monkeypatch.setattr(sr.sim, "run_monte_carlo_detailed", lambda **k: {"success_rate": 0.5})
    original = sr._apply_overrides(sr.build_config_overrides(SINGLE))
    try:
        assert sr._run_primary_at_age(55, 60)["trajectory_is_synthetic"] is True
    finally:
        sr._restore_overrides(original)


# ------------------------------------------------------------- the small caches

def test_clear_cache_empties_the_mortgage_cache():
    sr._MORTGAGE_CACHE[("k",)] = {"curve": []}
    sr.clear_cache(include_disk=True)
    assert not sr._MORTGAGE_CACHE


def test_every_small_cache_is_registered_for_clearing():
    for cache in (sr._NW_CACHE, sr._SWR_CACHE, sr._PLACE_CACHE, sr._MORTGAGE_CACHE, sr._SCAN_CACHE):
        assert any(cache is c for c in sr._SMALL_CACHES)


def test_disk_hits_respect_the_small_cache_bound(monkeypatch):
    monkeypatch.setattr(sr, "_disk_key", lambda kind, key: "k")
    monkeypatch.setattr(sr, "_disk_load", lambda dk: {"v": 1})
    cache = {}
    for i in range(sr._SMALL_CACHE_MAX + 10):
        sr._small_cache_lookup(cache, "x", (i,))
    assert len(cache) == sr._SMALL_CACHE_MAX


# ------------------------------------------------------- target-only change

def test_target_only_change_reuses_scans_and_matches_a_cold_run():
    sr.execute_plan(_full_plan(55))
    warm_plan = _full_plan(56)
    assert _scan_calls(warm_plan) == []                       # no scan work to do
    warm = sr.execute_plan(warm_plan)
    sr.clear_cache(include_disk=False)
    cold_plan = _full_plan(56)
    assert len(_scan_calls(cold_plan)) == 3
    cold = sr.execute_plan(cold_plan)
    assert mc_jobs.dumps(warm) == mc_jobs.dumps(cold)


def test_scans_are_recomputed_when_other_inputs_change():
    sr.execute_plan(_full_plan(55))
    other = sr.plan_full_analysis({**SINGLE, "YOUR_401K": 90_000}, 60, 56, SCAN_RANGE)
    assert len(_scan_calls(other)) == 3


def test_browser_scans_are_not_kept_for_reuse(fake_st):
    plan = _full_plan()
    bc.submit(fake_st, "main", plan, lambda r: None, run_here=plan.local)
    job = bc.pending(fake_st, "main")[0]
    forged = [{"age": c[2][0], "n": c[2][1], "successes": c[2][1], "errors": 0, "first_error": None}
              for c in (plan.job["calls"][i] for i in job["remote"])]
    bc._receive(fake_st, {"type": "result", "id": job["id"], "results": json.dumps(forged),
                          "boot": "b", "seq": 1})
    assert len(_scan_calls(_full_plan(56))) == 3
