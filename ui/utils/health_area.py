"""The side panel's healthcare-by-area setting (components/sec_assumptions.py).

``HEALTH_AREA`` in ``user_overrides`` holds the resolved area key ("AL:3"), never the ZIP code:
the ZIP is looked up once, the box is emptied, and only the area is kept (and saved with a
profile). ``utils.config_builder.health_area_overrides`` turns the key into engine values.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from retirement_sim import config as cfg
from retirement_sim import healthcare_data as hd

try:
    from utils.config_builder import STARTING_PRICES
except ImportError:  # pragma: no cover
    from ui.utils.config_builder import STARTING_PRICES  # type: ignore

PLAN_LABELS = {"silver": "Benchmark Silver", "bronze": "Lowest-cost Bronze"}

ZIP_KEY = "sa_health_zip"
PLAN_KEY = "sa_health_plan"
MSG_KEY = "sa_health_msg"
_BENCH_KEY = "sa_aca_benchmark"
_CHILD_KEY = "sa_aca_child"


def _overrides(st) -> Dict[str, Any]:
    st.session_state.setdefault("user_overrides", {})
    return st.session_state["user_overrides"]


def area_key(overrides: Dict[str, Any]) -> Optional[str]:
    """The plan's valid area key, or None."""
    key = (overrides or {}).get("HEALTH_AREA")
    return hd.area(key)["key"] if hd.area(key) else None


def coverage_year(overrides: Dict[str, Any]) -> int:
    """Plan year of the plan's healthcare prices: 2027 with an area, 2026 without."""
    return hd.coverage_year((overrides or {}).get("HEALTH_AREA"))


def year_phrase(overrides: Dict[str, Any]) -> str:
    return f"{coverage_year(overrides)} plan year"


def apply_area(st, key: str) -> None:
    """Price the marketplace for ``key``: store it, fill the two price boxes with the area's
    own figures, and keep the plan type already chosen (Silver to start)."""
    ov = _overrides(st)
    ov["HEALTH_AREA"] = key
    ov.setdefault("HEALTH_PLAN", "silver")
    ref = hd.reference_prices(key)
    for box, name, value in ((_BENCH_KEY, "ACA_BENCHMARK_MONTHLY_AT_40", ref["benchmark_at_40"]),
                             (_CHILD_KEY, "ACA_CHILD_MONTHLY", ref["child"])):
        if value is None:           # a family-tier area has no child price
            continue
        ov[name] = int(round(value))
        st.session_state[box] = int(round(value))
    st.session_state[PLAN_KEY] = PLAN_LABELS[ov["HEALTH_PLAN"]]
    st.session_state[ZIP_KEY] = ""            # the ZIP is not kept
    st.session_state[MSG_KEY] = f"Using prices for {hd.area_label(key)}."


def apply_zip(st) -> None:
    """Button callback: find the area for the ZIP in the box."""
    key = hd.zip_to_area(str(st.session_state.get(ZIP_KEY, "") or ""))
    if key is None:
        st.session_state[MSG_KEY] = "That ZIP code was not found. Enter a 5-digit US ZIP code."
        return
    apply_area(st, key)


def apply_state(st) -> None:
    """Button callback: the average for the state chosen under Taxes."""
    key = hd.state_average_key(state_choice_code(_overrides(st)))
    if key is None:
        st.session_state[MSG_KEY] = "Choose a state under Taxes, or enter a ZIP code."
        return
    apply_area(st, key)


def clear_area(st) -> None:
    """Button callback: back to the flat national figures (boxes to their starting values)."""
    ov = _overrides(st)
    ov.pop("HEALTH_AREA", None)
    ov.pop("HEALTH_PLAN", None)
    for box, name in ((_BENCH_KEY, "ACA_BENCHMARK_MONTHLY_AT_40"), (_CHILD_KEY, "ACA_CHILD_MONTHLY")):
        ov[name] = int(STARTING_PRICES[name])
        st.session_state[box] = int(STARTING_PRICES[name])
    st.session_state.pop(PLAN_KEY, None)
    st.session_state[MSG_KEY] = "Back to the national figures."


def state_choice_code(overrides: Dict[str, Any]) -> Optional[str]:
    """The state code the Taxes section holds, or None for "no state tax" and "flat rate"."""
    code = cfg.resolve_state_code((overrides or {}).get("STATE_CHOICE", "CA") or "CA")
    return code if hd.state_average_key(code) else None
