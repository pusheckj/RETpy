"""Parallel Monte Carlo workers (process-pool).

Kept ENGINE-SIDE and deliberately UI-FREE: spawned workers import only this
module + the fast engine (``account_simulation`` / ``config`` / numpy), never
Streamlit/Plotly — otherwise per-worker startup would dwarf the speedup.

The parent process fully configures ``config`` (applies user overrides +
recomputes derived constants), snapshots its plain-data attributes, and hands
that snapshot to each worker's ``worker_init`` so the worker's ``config`` is an
exact replica — no re-derivation logic (and thus no UI imports) needed in the
worker.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from retirement_sim import account_simulation as sim
from retirement_sim import config as cfg


def cfg_snapshot() -> Dict[str, Any]:
    """Flat dict of ``config``'s plain-data module attributes (for pickling to
    workers). Skips dunders and non-data objects (functions, modules)."""
    snap: Dict[str, Any] = {}
    for k, v in vars(cfg).items():
        if k.startswith("__"):
            continue
        if isinstance(v, (int, float, str, bool, list, dict, tuple)) or v is None:
            snap[k] = v
    return snap


def worker_init(snapshot: Dict[str, Any]) -> None:
    """Pool initializer: replicate the parent's fully-configured ``config`` state
    onto this worker's ``config`` module."""
    for k, v in snapshot.items():
        try:
            setattr(cfg, k, v)
        except Exception:
            pass


def _trajectory_from_portfolio(portfolio) -> List[Tuple[int, float]]:
    out: List[Tuple[int, float]] = []
    for record in (getattr(portfolio, "yearly_history", None) or []):
        try:
            out.append((int(record["age"]), float(record["total"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _bytype_from_portfolio(portfolio) -> List[Dict[str, float]]:
    """Per-year balance by account category (AccountType.value keys) — needed for
    the bridge-years / accessible-balance analysis. The engine already stores
    ``record['by_type']``; this just surfaces it (plain floats, picklable)."""
    out: List[Dict[str, float]] = []
    for record in (getattr(portfolio, "yearly_history", None) or []):
        try:
            bt = record.get("by_type") or {}
            row: Dict[str, float] = {"age": int(record["age"])}
            for k, v in bt.items():
                row[str(k)] = float(v)
            out.append(row)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def sim_task(args) -> Dict[str, Any]:
    """Run a batch of ``n_sims`` detailed simulations at ``age``.

    ``args = (age, n_sims, detail_k, seed)``. Returns aggregate scalars for all
    sims plus full per-path detail (trajectory + withdrawal_log as plain dicts)
    for up to ``detail_k`` of them — everything picklable, no portfolio objects.

    ``spending_by_age`` is every sim's guardrail-adjusted living spending by age
    (``{age: [dollars, ...]}``), so the spending-range chart covers the same
    runs as the success rate rather than only the ``detail_k`` sample.

    A simulation that RAISES is dropped from both ``successes`` and ``finals``,
    which silently shrinks the denominator the caller divides by — a config that
    made 30% of paths crash would report a confident success rate over the
    surviving 70%. The batch therefore also reports ``errors`` (how many runs
    raised) and ``first_error`` (repr of the first exception) so the caller can
    surface a warning instead of quietly reporting a biased rate.
    """
    age, n_sims, detail_k, seed = args
    import random as _random
    np.random.seed(int(seed))
    _random.seed(int(seed))

    successes = 0
    errors = 0
    first_error = None
    finals: List[float] = []
    details: List[dict] = []
    spending_by_age: Dict[int, List[float]] = {}
    for _ in range(int(n_sims)):
        try:
            success, portfolio = sim.run_detailed_simulation(age, verbose=False)
        except Exception as exc:  # noqa: BLE001 - a crashed path must not kill the batch
            errors += 1
            if first_error is None:
                first_error = repr(exc)
            continue
        if success:
            successes += 1
        fb = float(portfolio.get_total_balance())
        finals.append(fb)
        for row in (getattr(portfolio, "spending_log", None) or []):
            spending_by_age.setdefault(int(row["age"]), []).append(float(row.get("living", 0.0)))
        if len(details) < detail_k:
            traj = _trajectory_from_portfolio(portfolio)
            if traj:
                details.append({
                    "success": bool(success),
                    "final": fb,
                    "trajectory": traj,
                    "bytype": _bytype_from_portfolio(portfolio),
                    "withdrawal_log": [dict(r) for r in (getattr(portfolio, "withdrawal_log", None) or [])],
                })
    return {"age": age, "n": len(finals), "successes": successes, "finals": finals,
            "details": details, "spending_by_age": spending_by_age,
            "errors": errors, "first_error": first_error}
