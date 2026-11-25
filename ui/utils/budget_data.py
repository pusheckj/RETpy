"""Public cost-of-living data behind the childcare suggestion and the spending benchmark.

The files in ``ui/data/budget/`` are copied unchanged from BiggerPockets Money's
Household Spending Comparison v2.4.0 (captured 2026-11-25). They hold only public
numbers from US agencies: BLS Consumer Expenditure (CE) 2025, BEA Regional Price
Parities (RPP) 2024, HUD Fair Market Rents FY2027, DOL National Database of
Childcare Prices (NDCP) 2022, and BLS CPI. Credits and the list of constants that
come from BPM's method: docs/DATA_SOURCES.md.

Loaded lazily and cached: nothing is read until a budget feature draws.

BEA RPP is renormalized so each US component is exactly 1.00, the same way the
app's own ``place_costs.py`` does it. BPM's files carry the raw BEA index (100 =
US), and the raw US goods index is 99.6 and other services 100.1, so a raw
reading would put the whole country slightly off 1.00.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from retirement_sim import config as cfg

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "budget"

CREDIT = ("BiggerPockets Money Household Spending Comparison v2.4.0 (captured 2026-11-25); "
          "BLS Consumer Expenditure 2025, BEA Regional Price Parities 2024, HUD Fair Market "
          "Rents FY2027, DOL National Database of Childcare Prices")

# The US value of each raw BEA index BPM stores (All items, Goods, Rents, Services: other).
# All items and Rents are 100 by construction. Goods and other services are the raw US
# readings in docs/data_sources/2026_verification.md.
US_RAW = {"ra": 100.0, "rg": 99.6, "rr": 100.0, "rs": 100.1}

STATEWIDE_SUFFIX = "(statewide avg)"


def round_half_up(x: float) -> int:
    """JavaScript's Math.round (BPM's rounding), not Python's round-half-to-even."""
    return int(math.floor(x + 0.5))


@lru_cache(maxsize=None)
def _load(name: str) -> Any:
    with open(DATA_DIR / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def ce_xtab() -> dict:
    """CE 2025 quintile means (Q), size ratios (S), age ratios (A) and DAMP."""
    return _load("ce_xtab")


def cpi_factors() -> Dict[str, float]:
    return _load("cpi_factors")


def constants() -> dict:
    return _load("constants")


def locations() -> List[dict]:
    """The 739 areas: BEA RPP (ra, rg, rr, rs) and HUD FY2027 rents (f0..f4)."""
    return _load("locations")


@lru_cache(maxsize=None)
def _by_label() -> Dict[str, dict]:
    return {row["l"]: row for row in locations()}


@lru_cache(maxsize=None)
def _statewide() -> Dict[str, dict]:
    return {row["st"]: row for row in locations() if row["l"].endswith(STATEWIDE_SUFFIX)}


def area(label: Optional[str]) -> Optional[dict]:
    """The location row for an area label, or None."""
    return _by_label().get(label) if isinstance(label, str) else None


def statewide(state: Optional[str]) -> Optional[dict]:
    """A state's "statewide average" row (every state and DC has one), or None."""
    return _statewide().get(str(state or "").upper())


def area_labels(state: Optional[str] = None) -> List[str]:
    """Area labels sorted by name, the statewide rows left out. One state's, or all 739."""
    st = str(state or "").upper()
    rows = [r["l"] for r in locations()
            if not r["l"].endswith(STATEWIDE_SUFFIX) and (not st or r["st"] == st)]
    return sorted(rows)


def price_levels(row: Optional[dict], renormalize: bool = True) -> Dict[str, float]:
    """BEA price levels of a location row as ratios to the US (ra, rg, rr, rs).
    No row: 1.0 for each. ``renormalize=False`` gives BPM's raw reading (index / 100)."""
    if row is None:
        return {k: 1.0 for k in US_RAW}
    return {k: row[k] / (US_RAW[k] if renormalize else 100.0) for k in US_RAW}


def state_childcare_prices(state: Optional[str]) -> Optional[List[int]]:
    """NDCP 2022 state prices: center infant, toddler, preschool, school-age, then home."""
    return _load("childcare_state_prices").get(str(state or "").upper())


def county_childcare_prices(label: Optional[str]) -> Optional[List[int]]:
    """NDCP 2022 county medians for an area label (BPM's crosswalk), or None."""
    fips = _load("childcare_county_crosswalk").get(label or "")
    return _load("childcare_county_medians").get(fips) if fips else None


def state_code(overrides: dict) -> Optional[str]:
    """The plan's state as a two-letter code, or None (no state tax / a flat rate)."""
    code = cfg.resolve_state_code(overrides.get("STATE_CHOICE", cfg.STATE_CHOICE))
    return code if statewide(code) else None


def picked_area(overrides: dict) -> Optional[str]:
    """The saved area label (``BENCH_AREA``) if it is one of the 739, else None."""
    label = overrides.get("BENCH_AREA")
    return label if area(label) else None
