"""Healthcare prices by area, plan year 2027 (pre-Medicare marketplace).

Static public tables, loaded lazily from ``retirement_sim/data/healthcare/2027/``:
CMS 2027 Rate PUF and Plan Attributes PUF (federal-exchange rating areas), KFF 2027
benchmark premiums (state-exchange states), Covered California 2027 prices by ZIP group,
the federal and state age curves, the Rev. Proc. 2026-26 premium tax credit table and the
2026 HHS poverty guidelines. The tables and the formulas below come from the BiggerPockets
Money Healthcare Costs Estimator v3.6.2 (captured 2026-11-25); see docs/DATA_SOURCES.md.

This module is the only reader of those files. It is NOT part of the engine bundle that goes
to the browser: ``area_overrides`` turns an area into plain config values (price tables by
age, plan ratio, out-of-pocket table, credit bands, poverty line) and the engine reads only
those. An area key is ``"ST:area"`` (``"AL:3"``, ``"CA:19b"``) or ``"ST:avg"`` for the
state's average. A ZIP code is only ever looked up here, never stored.
"""
from __future__ import annotations

import bisect
import functools
import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

YEAR = 2027             # plan year of the prices, credit table and out-of-pocket limits
LEGACY_YEAR = 2026      # plan year of the flat figures used when no area is set
FPL_YEAR = 2026         # HHS guideline year that governs 2027 coverage
#: Pre-Medicare premium growth per year, nominal (the owner's reference file, base case).
PREMIUM_GROWTH_NOMINAL = 0.06
BRONZE_FALLBACK_RATIO = 0.72   # the estimator's fallback when a state lists no bronze ratio

SOURCE_LINE = ("2027 plan year. Prices from the CMS Rate PUF, KFF and Covered California; credit table "
               "from Rev. Proc. 2026-26; poverty guidelines from HHS (2026). Method and tables from "
               "BiggerPockets Money's Healthcare Costs Estimator v3.6.2. See docs/DATA_SOURCES.md.")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "healthcare", str(YEAR))

_ANCHORS = (21, 30, 40, 50, 60, 64)
_ANCHOR_KEYS = ("s21", "s30", "s40", "s50", "s60", "s64")


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def _json(name: str) -> Any:
    with open(os.path.join(DATA_DIR, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def _ffe() -> Dict[str, Dict[str, dict]]:
    return _json("rating_areas_ffe")


def _sbe() -> Dict[str, dict]:
    return _json("sbe_benchmarks")


def _ca() -> Dict[str, dict]:
    return _json("ca_pricing_groups")["CA"]["areas"]


def state_names() -> Dict[str, str]:
    """State code -> name, for the 50 states and DC."""
    return _json("state_names")


@functools.lru_cache(maxsize=1)
def age_factors() -> Dict[int, float]:
    """The federal age curve, ages 0-64."""
    return {int(k): float(v) for k, v in _json("age_factors").items()}


@functools.lru_cache(maxsize=None)
def _curve(name: str) -> Dict[int, float]:
    return {int(k): float(v) for k, v in _json("age_curves")[name].items()}


@functools.lru_cache(maxsize=1)
def zip_ranges() -> Tuple[List[int], List[int], List[str], List[str]]:
    """The ZIP crosswalk decoded: (starts, ends, states, areas), sorted by start.

    The file stores, per state, a list of rating-area names ``r`` and a string ``d`` of
    ``area.start.length`` runs in base 36: each start is a distance from the previous run's
    end, each length is the distance from start to end.
    """
    rows: List[Tuple[int, int, str, str]] = []
    for state, obj in _json("zipra_encoded").items():
        prev = 0
        for part in obj["d"].split(","):
            idx, gap, span = part.split(".")
            start = prev + int(gap, 36)
            end = start + int(span, 36)
            prev = end
            rows.append((start, end, state, obj["r"][int(idx, 36)]))
    rows.sort()
    return ([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows])


# ---------------------------------------------------------------------------
# Areas
# ---------------------------------------------------------------------------

def _zip5(value: Any) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value).strip() if isinstance(value, str) else "%05d" % value
    return text if re.fullmatch(r"\d{5}", text) else None


def zip_to_area(zip_code: Any) -> Optional[str]:
    """The area key for a 5-digit ZIP, or None.

    A federal-exchange state resolves to its rating area, California to its Covered California
    price group. Any other ZIP falls back to its state's average through the first three digits.
    """
    z = _zip5(zip_code)
    if z is None:
        return None
    starts, ends, states, areas = zip_ranges()
    n = int(z)
    i = bisect.bisect_right(starts, n) - 1
    if i >= 0 and n <= ends[i]:
        return f"{states[i]}:{areas[i]}"
    return state_average_key(_json("zip3_prefixes").get(z[:3]))


def state_average_key(state: Any) -> Optional[str]:
    """``"ST:avg"`` for a state code the data covers, else None."""
    code = str(state or "").strip().upper()
    return f"{code}:avg" if code in state_names() else None


def _split_key(key: Any) -> Optional[Tuple[str, str]]:
    if not isinstance(key, str) or key.count(":") != 1:
        return None
    state, area = (p.strip() for p in key.split(":"))
    state = state.upper()
    return (state, area) if state in state_names() and area else None


_AVERAGED = ("s21", "s30", "s40", "s50", "s60", "s64", "schild", "tob_pct", "b21")


def _ffe_average(state: str) -> dict:
    """Rating areas weighted by silver plan count (the estimator's enrollment proxy)."""
    areas = [v for v in _ffe()[state].values() if v.get("s21")]
    entry: Dict[str, Any] = {}
    for field in _AVERAGED:
        num = den = 0.0
        for v in areas:
            if v.get(field) is not None:
                w = v.get("n") or 1
                num += v[field] * w
                den += w
        entry[field] = num / den if den else None
    entry["n"] = sum(v.get("n") or 0 for v in areas)
    # One filed curve in every area (Utah) stays exact on the average.
    if all(v.get("curve") for v in areas) and len({v["curve"] for v in areas}) == 1:
        entry["curve"] = areas[0]["curve"]
    return entry


def area(key: Any) -> Optional[dict]:
    """``{"key", "state", "source", "entry"}`` for an area key, or None if it names nothing.

    ``source`` is ``"ffe"`` (federal exchange, rating-area rates) or ``"sbe"`` (state exchange).
    """
    return _area(key) if isinstance(key, str) else None


@functools.lru_cache(maxsize=None)
def _area(key: str) -> Optional[dict]:
    parts = _split_key(key)
    if parts is None:
        return None
    state, name = parts
    if state in _ffe():
        if name == "avg":
            entry = _ffe_average(state)
        elif name in _ffe()[state]:
            entry = _ffe()[state][name]
        else:
            return None
        return {"key": f"{state}:{name}", "state": state, "source": "ffe", "entry": entry}
    if state in _sbe():
        if name == "avg":
            entry = _sbe()[state]
        elif state == "CA" and name in _ca():
            entry = _ca()[name]
        else:
            return None
        return {"key": f"{state}:{name}", "state": state, "source": "sbe", "entry": entry}
    return None


def area_label(key: Any) -> str:
    """A plain-words name for an area key ('' for a bad key)."""
    a = area(key)
    if a is None:
        return ""
    state = state_names()[a["state"]]
    name = a["key"].split(":", 1)[1]
    if name == "avg":
        return f"{state}, statewide average"
    if a["state"] == "CA":
        return f"{state}, Covered California region {a['entry'].get('reg', name)}"
    return f"{state}, rating area {name}"


def coverage_year(key: Any) -> int:
    """Plan year of the healthcare prices a plan uses: 2027 with an area, 2026 without."""
    return YEAR if area(key) is not None else LEGACY_YEAR


# ---------------------------------------------------------------------------
# The estimator's price formulas
# ---------------------------------------------------------------------------

def _factor(age: int) -> Optional[float]:
    return age_factors().get(age)


def _bronze_ratio(a: dict) -> Optional[float]:
    e = a["entry"]
    s21 = e.get("s21") or (e["s40"] / 1.278 if a["source"] == "sbe" and e.get("s40") else None)
    b21 = e.get("b21") or (e["s40"] * e["b_ratio"] / 1.278
                           if a["source"] == "sbe" and e.get("s40") and e.get("b_ratio") else None)
    return b21 / s21 if s21 and b21 else None


def rate_at_age(a: dict, age: int, plan: str = "silver") -> float:
    """One adult's monthly price at ``age`` (0 from 65)."""
    age = int(age)
    if age >= 65:
        return 0.0
    age = max(0, age)
    e, source = a["entry"], a["source"]
    curve = _curve(e["curve"]) if e.get("curve") else None
    if source == "ffe":
        if curve:
            base = e["s21"] * curve[min(64, age)]
        elif age < 21:
            base = e["s21"] * (_factor(age) if _factor(age) is not None else 0.765)
        else:
            base = _interpolate(e, age)
    elif curve:
        base = e["s21"] * curve[min(64, age)]
    elif e.get("cr"):
        base = e["s40"]
    else:
        s21 = e.get("s21") or e["s40"] / 1.278
        base = s21 * (_factor(age) or _factor(63))
    if plan == "bronze":
        ratio = _bronze_ratio(a)
        if ratio:
            base *= ratio
    return base


def _interpolate(e: dict, age: int) -> float:
    """A filed rate between the anchor ages, in federal-factor space (linear in age would
    overprice young adults by up to 5.6%)."""
    pts = [(ag, e[k]) for ag, k in zip(_ANCHORS, _ANCHOR_KEYS) if e.get(k) is not None]
    if age <= pts[0][0]:
        return pts[0][1]
    if age >= pts[-1][0]:
        return pts[-1][1]
    for (a1, r1), (a2, r2) in zip(pts, pts[1:]):
        if a1 <= age <= a2:
            fa, f1, f2 = _factor(age), _factor(a1), _factor(a2)
            if None not in (fa, f1, f2) and f2 != f1:
                t = (fa - f1) / (f2 - f1)
            else:
                t = (age - a1) / (a2 - a1)
            return r1 + t * (r2 - r1)
    return pts[-1][1]


def child_rate_at(a: dict, age: int, plan: str = "silver") -> float:
    """One child's monthly price at ``age`` (0-20; older ages are priced as 20)."""
    age = max(0, min(20, int(age)))
    e, source = a["entry"], a["source"]
    curve = _curve(e["curve"]) if e.get("curve") else None
    if curve:
        base = e["schild"] if (e.get("schild") and curve[age] == curve[0]) else e["s21"] * curve[age]
    elif source == "ffe":
        base = e["schild"] if (age <= 14 and e.get("schild")) else \
            e["s21"] * (_factor(age) if _factor(age) is not None else 0.765)
    else:
        s21 = e.get("s21") or e["s40"] / 1.278
        base = e["s40"] * 0.765 if e.get("cr") else s21 * (_factor(age) if _factor(age) is not None else 0.765)
    if plan == "bronze":
        base *= _bronze_ratio(a) or BRONZE_FALLBACK_RATIO
    return base


def tier_multiple(e: dict, n_adults: int, any_kids: bool) -> float:
    """New York and Vermont rate a household as a multiple of the single community rate."""
    t = e["tiers"]
    if n_adults >= 2:
        return t["fam"] if any_kids else 2.0
    if n_adults == 1:
        return t["spk"] if any_kids else 1.0
    return t["spk"] if any_kids else 0.0


def household_monthly(a: dict, adult_ages: Sequence[int], kid_ages: Sequence[int] = (),
                      plan: str = "silver") -> float:
    """A household's monthly price: adults under 65, the three oldest children under 21 at
    child rates, and children 21-25 at adult rates. New York and Vermont use family tiers."""
    adults = [int(x) for x in adult_ages if int(x) < 65]
    kids = [int(x) for x in kid_ages]
    e = a["entry"]
    if e.get("cr") and e.get("tiers"):
        single = e["b21"] if plan == "bronze" else e["s40"]
        return single * tier_multiple(e, len(adults), any(0 <= k < 26 for k in kids))
    total = sum(rate_at_age(a, x, plan) for x in adults)
    under21 = sorted((k for k in kids if 0 <= k < 21), reverse=True)
    total += sum(child_rate_at(a, k, plan) for k in under21[:3])
    total += sum(rate_at_age(a, k, plan) for k in kids if 21 <= k < 26)
    return total


# ---------------------------------------------------------------------------
# Credit table, poverty line, out-of-pocket
# ---------------------------------------------------------------------------

def ptc_bands() -> Tuple[Tuple[float, float, float, float], ...]:
    """The Rev. Proc. 2026-26 applicable percentages as (FPL ratio low, high, initial, final)
    rows, the shape ``config.ACA_APPLICABLE_PCT_BANDS`` uses. Flat 2.15% below 133%,
    linear between breakpoints, flat 10.22% from 300% to 400%, no credit above 400%."""
    t = _json("ptc_table")
    pts = [(0.0, float(t["below_133_pct"]))] + [(float(b["fpl_ratio"]), float(b["applicable_pct"]))
                                                for b in t["breakpoints"]]
    rows = [(0.0, pts[1][0], pts[0][1], pts[0][1])]
    for (r1, p1), (r2, p2) in zip(pts[1:], pts[2:]):
        rows.append((r1, r2, p1, p2))
    return tuple(rows)


def applicable_pct(fpl_ratio: float) -> Optional[float]:
    """Share of income expected toward the benchmark plan, or None outside 100%-400% FPL."""
    if fpl_ratio < 1.0 or fpl_ratio > 4.0:
        return None
    for lo, hi, initial, final in ptc_bands():
        if fpl_ratio < hi:
            return initial if fpl_ratio <= lo else initial + (fpl_ratio - lo) / (hi - lo) * (final - initial)
    return ptc_bands()[-1][3]


def fpl_guideline(state: Optional[str] = None) -> Tuple[float, float]:
    """(first person, each additional person) for the state: Alaska and Hawaii differ."""
    t = _json("fpl_2026")
    row = t["alaska"] if state == "AK" else t["hawaii"] if state == "HI" else t["contiguous_48_plus_dc"]
    return float(row["base_1_person"]), float(row["per_additional_person"])


def fpl(household_size: int, state: Optional[str] = None) -> float:
    base, extra = fpl_guideline(state)
    return base + extra * (max(1, int(household_size)) - 1)


def oop_at_age(age: float) -> float:
    """Out-of-pocket dollars a year for one person on a standard (silver) plan."""
    if age >= 65:
        return 0.0
    pts = [(c["age"], float(c["dollars_per_person_per_year"])) for c in _json("oop_curve")["curve"]]
    if age <= pts[0][0]:
        return pts[0][1]
    if age >= pts[-1][0]:
        return pts[-1][1]
    for (a1, v1), (a2, v2) in zip(pts, pts[1:]):
        if a1 <= age <= a2:
            return v1 + (age - a1) / (a2 - a1) * (v2 - v1)
    return 0.0


def bronze_oop_factor() -> float:
    return float(_json("oop_curve")["bronze_oop_factor"])


def household_oop(ages: Sequence[int], plan: str = "silver") -> float:
    factor = bronze_oop_factor() if plan == "bronze" else 1.0
    return sum(oop_at_age(a) for a in ages) * factor


# ---------------------------------------------------------------------------
# For the engine and the side panel
# ---------------------------------------------------------------------------

def _silver_table(a: dict) -> List[float]:
    """Monthly silver price at each age 0-64: children's rates below 21, adults' from 21."""
    return [child_rate_at(a, age, "silver") if age < 21 else rate_at_age(a, age, "silver")
            for age in range(65)]


def reference_prices(key: Any) -> Optional[Dict[str, float]]:
    """The two figures the side panel shows and lets you change: the benchmark Silver price for a
    40-year-old and for a child, per month, before any credit."""
    a = area(key)
    if a is None:
        return None
    table = _silver_table(a)
    return {"benchmark_at_40": table[40], "child": table[10]}


def area_overrides(key: Any, plan: str = "silver", benchmark_at_40: Optional[float] = None,
                   child: Optional[float] = None) -> Dict[str, Any]:
    """Plain engine settings (``retirement_sim.config`` keys) that price the marketplace for an
    area; ``{}`` for a key that names nothing.

    ``plan`` is ``"silver"`` (the benchmark, which also sets the credit) or ``"bronze"`` (the
    lowest-cost bronze, priced through the state's bronze-to-silver ratio). ``benchmark_at_40``
    and ``child`` are the side panel's two price boxes: a figure that is not the area's own
    (to the dollar) rescales that group of prices, like a quote you know.
    """
    a = area(key)
    if a is None:
        return {}
    bronze = plan == "bronze"
    table = _silver_table(a)
    ref = {"benchmark_at_40": table[40], "child": table[10]}
    adult_scale = _scale(benchmark_at_40, ref["benchmark_at_40"])
    child_scale = _scale(child, ref["child"])
    table = [round(v * (child_scale if age < 21 else adult_scale), 4) for age, v in enumerate(table)]
    e = a["entry"]
    tiers = None
    if e.get("cr") and e.get("tiers"):
        tiers = {"single": round(e["s40"] * adult_scale, 4),
                 "spk": float(e["tiers"]["spk"]), "fam": float(e["tiers"]["fam"])}
    ratio = (_bronze_ratio(a) or BRONZE_FALLBACK_RATIO) if bronze else 1.0
    factor = bronze_oop_factor() if bronze else 1.0
    first, extra = fpl_guideline(a["state"])
    return {
        "ACA_AREA_KEY": a["key"],
        "ACA_AREA_SILVER_MONTHLY": table,
        "ACA_AREA_TIERS": tiers,
        "ACA_AREA_PLAN_RATIO": round(ratio, 6),
        "ACA_AREA_OOP_ANNUAL": [round(oop_at_age(age) * factor, 2) for age in range(65)],
        "ACA_APPLICABLE_PCT_BANDS": ptc_bands(),
        "ACA_FPL_FIRST_PERSON": first,
        "ACA_FPL_PER_ADDITIONAL_PERSON": extra,
        "ACA_PREMIUM_GROWTH_NOMINAL": PREMIUM_GROWTH_NOMINAL,
        "ACA_COVERAGE_YEAR": YEAR,
    }


def _scale(typed: Optional[float], area_value: float) -> float:
    """1.0 unless ``typed`` is a real figure other than the area's own, to the dollar."""
    try:
        t = float(typed)
    except (TypeError, ValueError):
        return 1.0
    if t <= 0 or area_value <= 0 or round(t) == round(area_value):
        return 1.0
    return t / area_value
