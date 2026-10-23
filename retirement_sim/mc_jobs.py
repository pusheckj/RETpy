"""Batches of independent, seeded engine calls: the unit of work shared by the
server and the visitor's browser.

A job is plain data::

    {"base":    <config snapshot>,           # mc_parallel.cfg_snapshot()
     "patches": [<config diff>, ...],         # a few keys on top of base
     "calls":   [[fn, patch_index, args], ...]}

Every call seeds its own random numbers, so the calls of a job can run in any
order, on any number of workers, on the server (CPython) or in the browser
(Pyodide in Web Workers), and give the same answer. ``patch_index`` is -1 for
"base only"; otherwise that patch is applied for the call and undone after.

Everything crosses JSON (Streamlit component args, Worker messages), so
``dumps``/``loads`` tag what JSON can't carry: tuples, dicts with non-string
keys, and inf/nan. Imports only the engine and numpy, so the browser loads
nothing else.
"""
from __future__ import annotations

import json
import math
import random as _random
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional

import numpy as np

from retirement_sim import account_simulation as sim
from retirement_sim import config as cfg
from retirement_sim import mc_parallel

_MISSING = object()


# ---------------------------------------------------------------------------
# JSON codec
# ---------------------------------------------------------------------------

def encode(obj: Any) -> Any:
    """Plain data -> JSON-safe structure (inverse: ``decode``)."""
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return f if math.isfinite(f) else {"$f": repr(f)}       # 'inf', '-inf', 'nan'
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return [encode(v) for v in obj.tolist()]
    if isinstance(obj, tuple):
        return {"$t": [encode(v) for v in obj]}
    if isinstance(obj, list):
        return [encode(v) for v in obj]
    if isinstance(obj, dict):
        if all(isinstance(k, str) and not k.startswith("$") for k in obj):
            return {k: encode(v) for k, v in obj.items()}
        return {"$d": [[encode(k), encode(v)] for k, v in obj.items()]}
    raise TypeError(f"not plain data: {type(obj).__name__}")


def decode(obj: Any) -> Any:
    if isinstance(obj, list):
        return [decode(v) for v in obj]
    if isinstance(obj, dict):
        if len(obj) == 1:
            (tag, val), = obj.items()
            if tag == "$f":
                return float(val)
            if tag == "$t":
                return tuple(decode(v) for v in val)
            if tag == "$d":
                return {_key(decode(k)): decode(v) for k, v in val}
        return {k: decode(v) for k, v in obj.items()}
    return obj


def _key(k: Any) -> Any:
    return tuple(k) if isinstance(k, list) else k       # dict keys must be hashable


def dumps(obj: Any) -> str:
    return json.dumps(encode(obj), separators=(",", ":"), allow_nan=False)


def loads(text: str) -> Any:
    return decode(json.loads(text))


# ---------------------------------------------------------------------------
# Config state
# ---------------------------------------------------------------------------

def snapshot() -> Dict[str, Any]:
    return mc_parallel.cfg_snapshot()


def diff(base: Dict[str, Any], other: Dict[str, Any]) -> Dict[str, Any]:
    """Keys whose value in ``other`` differs from ``base``."""
    return {k: v for k, v in other.items() if base.get(k, _MISSING) != v}


@contextmanager
def config_state(values: Optional[Dict[str, Any]]) -> Iterator[None]:
    """Set config attributes for the duration of the block, then restore them."""
    saved = {k: getattr(cfg, k, _MISSING) for k in (values or {})}
    try:
        for k, v in (values or {}).items():
            setattr(cfg, k, v)
        yield
    finally:
        for k, v in saved.items():
            if v is _MISSING:
                try:
                    delattr(cfg, k)
                except AttributeError:
                    pass
            else:
                setattr(cfg, k, v)


# ---------------------------------------------------------------------------
# The calls
# ---------------------------------------------------------------------------

def _seed(seed: int) -> None:
    np.random.seed(int(seed))
    _random.seed(int(seed))


def _wilson(successes: int, n: int, z: float):
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return mid - half, mid + half


def scan_age(age: int, max_n: int, seed: int, target: float,
             min_n: int = 50, step: int = 50, z: float = 2.576, margin: float = 0.05) -> Dict[str, Any]:
    """Success rate of retiring at ``age``, for the success-by-age curve.

    Stops early, in steps of ``step`` runs after the first ``min_n``, once the
    99% interval is clear of ``target`` by ``margin``: an age that is plainly
    hopeless or plainly safe doesn't need ``max_n`` runs to show it, while the
    ages near the target -- the ones that decide the earliest retirement age --
    always get all of them. Deterministic: one seeded stream, fixed checkpoints.
    """
    _seed(seed)
    successes = n = errors = 0
    first_error = None
    for i in range(int(max_n)):
        try:
            ok, _pf = sim.run_detailed_simulation(age, verbose=False)
        except Exception as exc:  # noqa: BLE001 - one bad path must not kill the batch
            errors += 1
            first_error = first_error or repr(exc)
            continue
        n += 1
        successes += bool(ok)
        done = i + 1
        if done >= min_n and done % step == 0 and done < max_n:
            lo, hi = _wilson(successes, n, z)
            if hi < target - margin or lo > target + margin:
                break
    return {"age": int(age), "n": n, "successes": successes, "errors": errors,
            "first_error": first_error}


def mc_summary(age: int, n: int, seed: int) -> Dict[str, float]:
    """``run_monte_carlo_detailed``: success rate and final-balance percentiles."""
    r = sim.run_monte_carlo_detailed(int(age), n_simulations=int(n), random_seed=int(seed))
    return {k: float(r.get(k, 0.0)) for k in
            ("success_rate", "median_final", "percentile_10", "percentile_90")}


def networth(target: float, n: int, max_work_age: int, seed: int) -> Dict[str, Any]:
    r = sim.run_monte_carlo_networth(float(target), n_simulations=int(n),
                                     max_work_age=int(max_work_age), random_seed=int(seed))
    return {k: (None if v is None else float(v)) for k, v in r.items()}


def investable_at_retirement(age: int, n: int = 40, seed: int = 98765) -> float:
    """Median investable balance AT the retirement year across n detailed sims
    (accumulation-only, independent of retirement spending). Excludes 529."""
    _seed(seed)
    vals = []
    for _ in range(int(n)):
        try:
            _ok, pf = sim.run_detailed_simulation(int(age), verbose=False)
        except Exception:  # noqa: BLE001
            continue
        rec = next((r for r in (getattr(pf, "yearly_history", None) or [])
                    if int(r.get("age", -1)) == int(age)), None)
        if rec:
            total = float(rec.get("total", 0.0) or 0.0)
            c529 = float((rec.get("by_type") or {}).get("college_529", 0.0) or 0.0)
            vals.append(max(0.0, total - c529))
    return float(np.median(vals)) if vals else 0.0


def median_year1_withdrawal(age: int, n: int = 20, seed: int = 13579) -> float:
    """Median first-retirement-year total withdrawal across n sims at the
    current spending settings. Seeded, so an SWR grid reuses the same paths."""
    _seed(seed)
    vals = []
    for _ in range(int(n)):
        try:
            _ok, pf = sim.run_detailed_simulation(int(age), verbose=False)
        except Exception:  # noqa: BLE001
            continue
        log = getattr(pf, "withdrawal_log", None) or []
        row = next((r for r in log if int(r.get("age", -1)) == int(age)), (log[0] if log else None))
        if row:
            vals.append(float(row.get("total", 0.0) or 0.0))
    return float(np.median(vals)) if vals else 0.0


CALLS: Dict[str, Callable[..., Any]] = {
    "batch": lambda age, n, detail, seed: mc_parallel.sim_task((age, n, detail, seed)),
    "scan": scan_age,
    "mc": mc_summary,
    "networth": networth,
    "investable": investable_at_retirement,
    "w1": median_year1_withdrawal,
}


def run_call(call: List[Any], patches: List[Dict[str, Any]]) -> Any:
    """One call, under its patch. ``call = [fn, patch_index, args]``."""
    fn, patch_index, args = call
    patch = patches[patch_index] if 0 <= int(patch_index) < len(patches) else None
    with config_state(patch):
        return CALLS[fn](*args)


def run_local(job: Dict[str, Any], indices: Optional[List[int]] = None) -> List[Any]:
    """Run calls in this process under the job's base config (the reference
    the browser must match). Returns results in ``indices`` order."""
    idx = list(range(len(job["calls"]))) if indices is None else list(indices)
    with config_state(job["base"]):
        return [run_call(job["calls"][i], job["patches"]) for i in idx]


# ---------------------------------------------------------------------------
# Browser entry points (called from the Web Workers through Pyodide)
# ---------------------------------------------------------------------------

_JOBS: Dict[str, Dict[str, Any]] = {}
_APPLIED: Optional[str] = None


def browser_load(job_id: str, job_json: str) -> int:
    """Keep a job's base, patches and calls in this worker; returns the call count."""
    _JOBS[job_id] = loads(job_json)
    while len(_JOBS) > 4:                                   # a worker only needs recent jobs
        _JOBS.pop(next(iter(_JOBS)))
    return len(_JOBS[job_id]["calls"])


def browser_run(job_id: str, index: int) -> str:
    """Run call ``index`` of a loaded job; JSON text of the result."""
    global _APPLIED
    job = _JOBS[job_id]
    if _APPLIED != job_id:
        mc_parallel.worker_init(job["base"])
        _APPLIED = job_id
    return dumps(run_call(job["calls"][int(index)], job["patches"]))
