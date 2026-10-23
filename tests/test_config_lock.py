"""Two visitors' runs must never see each other's inputs.

The engine reads one shared config module and a run works by writing the
user's inputs onto it and restoring them afterwards (sim_runner._apply_overrides
/ _restore_overrides). Streamlit serves every visitor from one process, so the
pair must hold CONFIG_LOCK for its whole duration.
"""
import os
import sys
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg
from utils import sim_runner as sr


def _visitor(age, delay, seen):
    time.sleep(delay)
    original = sr._apply_overrides({"YOUR_AGE": age})
    try:
        time.sleep(0.2)                  # mid-run: the other visitor starts now
        seen[age] = cfg.YOUR_AGE
    finally:
        sr._restore_overrides(original)


def test_overlapping_runs_do_not_see_each_others_inputs():
    before = cfg.YOUR_AGE
    seen = {}
    threads = [threading.Thread(target=_visitor, args=(30, 0.0, seen)),
               threading.Thread(target=_visitor, args=(50, 0.05, seen))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert seen == {30: 30, 50: 50}
    assert cfg.YOUR_AGE == before


def test_failed_apply_releases_the_lock(monkeypatch):
    def boom(_overrides):
        raise ValueError("bad override")
    monkeypatch.setattr(sr, "_write_overrides", boom)
    try:
        sr._apply_overrides({"YOUR_AGE": 40})
    except ValueError:
        pass
    acquired = sr.CONFIG_LOCK.acquire(timeout=1)
    assert acquired
    sr.CONFIG_LOCK.release()


def test_worker_cap_from_env(monkeypatch):
    monkeypatch.setenv("RETIREMENT_SIM_MAX_WORKERS", "1")
    assert sr._max_workers() == 1
    monkeypatch.setenv("RETIREMENT_SIM_MAX_WORKERS", "nonsense")
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    assert sr._max_workers() == 8
    monkeypatch.delenv("RETIREMENT_SIM_MAX_WORKERS")
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    assert sr._max_workers() == 2
    assert sr._available_cpus() >= 1


def test_hosted_app_writes_no_results_to_disk(monkeypatch):
    """Other people's inputs (and results keyed by them) must never be persisted
    on the server: the disk cache tier is off when hosted."""
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    assert sr._disk() is None
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    assert sr._disk() is not None
