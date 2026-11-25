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


#: A credit loss under this (dollars a year) is not worth a warning.
MIN_LOST = 100.0


def first_crossing(by_year: Dict[Any, Dict[str, float]], your_age: int, current_year: int,
                   majority: float = 0.5, min_lost: float = MIN_LOST) -> Optional[dict]:
    """The first year at least ``majority`` of the runs are over the cliff AND the credit lost
    is at least ``min_lost``: ``{"age", "year", "lost", "share"}``, or None when none is."""
    for age in sorted(int(a) for a in (by_year or {})):
        row = by_year.get(age) or by_year.get(str(age))
        if row and row["n"] and row["over"] / row["n"] >= majority and row["lost"] >= min_lost:
            return {"age": age, "year": int(current_year) + age - int(your_age),
                    "lost": float(row["lost"]), "share": row["over"] / row["n"]}
    return None


def message(crossing: dict, plan_year: int) -> str:
    """One short note for the results screen. ``crossing`` is ``first_crossing``'s answer."""
    lost = int(round(crossing["lost"], -2))
    share = int(round(100 * crossing["share"]))
    return (f"Health insurance cliff: from {crossing['year']} (age {crossing['age']}), your income tops "
            f"400% of the poverty line in {share}% of simulations. The ACA premium credit stops. "
            f"That year it costs you about ${lost:,} in credit. "
            f"Prices and credit rules are for the {plan_year} plan year, in today's dollars.")


def render_note(st, results: Optional[dict], overrides: dict, current_year: int) -> None:
    """Show the cliff note when the plan's runs cross 400% of the poverty line."""
    by_year = ((results or {}).get("primary_result") or {}).get("aca_cliff_by_year")
    if not by_year:
        return
    try:
        from utils import health_area
    except ImportError:  # pragma: no cover
        from ui.utils import health_area  # type: ignore
    from retirement_sim import config as cfg
    age = (overrides or {}).get("YOUR_AGE")
    crossing = first_crossing(by_year, int(age if age is not None else cfg.YOUR_AGE), current_year)
    if crossing is not None:
        st.warning(message(crossing, health_area.coverage_year(overrides)).replace("$", "\\$"))
