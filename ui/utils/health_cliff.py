"""The ACA cliff, as the results screen tells it.

Each simulated year somebody is on the marketplace, the engine records whether income was at or
above 400% of the poverty line (no premium credit) and the credit that cost
(``spending_log["aca_over"]`` / ``["aca_lost"]``). ``compact`` boils the runs down to a few
numbers per age; ``first_crossing`` names the first year most runs are over.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import numpy as np


def compact(by_age: Dict[int, List[Optional[float]]]) -> Dict[int, Dict[str, float]]:
    """``{age: [lost or None, ...]}`` (one entry per run) -> ``{age: {"n", "over", "lost"}}``:
    runs counted, runs over the cliff, and the median credit lost among those."""
    out: Dict[int, Dict[str, float]] = {}
    for age, vals in by_age.items():
        vals = list(vals or [])
        if not vals:
            continue
        lost = [float(v) for v in vals if v is not None]
        out[int(age)] = {"n": len(vals), "over": len(lost),
                         "lost": float(np.median(lost)) if lost else 0.0}
    return out


def from_spending_logs(logs: Iterable[Iterable[dict]]) -> Dict[int, Dict[str, float]]:
    """``compact`` for per-run ``portfolio.spending_log`` lists."""
    by_age: Dict[int, List[Optional[float]]] = {}
    for log in logs or []:
        for row in log or []:
            if "aca_over" in row:
                by_age.setdefault(int(row["age"]), []).append(
                    float(row["aca_lost"]) if row["aca_over"] else None)
    return compact(by_age)


def merge(chunks: Iterable[Dict[int, List[Optional[float]]]]) -> Dict[int, List[Optional[float]]]:
    """Join the per-age lists of several batches."""
    out: Dict[int, List[Optional[float]]] = {}
    for chunk in chunks:
        for age, vals in (chunk or {}).items():
            out.setdefault(int(age), []).extend(vals)
    return out


def first_crossing(by_year: Dict[Any, Dict[str, float]], your_age: int, current_year: int,
                   majority: float = 0.5) -> Optional[dict]:
    """The first year at least ``majority`` of the runs are over the cliff:
    ``{"age", "year", "lost", "share"}``, or None when none is."""
    for age in sorted(int(a) for a in (by_year or {})):
        row = by_year.get(age) or by_year.get(str(age))
        if row and row["n"] and row["over"] / row["n"] >= majority:
            return {"age": age, "year": int(current_year) + age - int(your_age),
                    "lost": float(row["lost"]), "share": row["over"] / row["n"]}
    return None
