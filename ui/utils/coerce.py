"""Safe type coercion helpers."""
from __future__ import annotations

import math


def safe_int(value, default: int = 0) -> int:
    """Coerce a value to int, falling back to default for None/invalid/NaN/inf."""
    try:
        if value is None:
            return int(default)
        if isinstance(value, float) and not math.isfinite(value):
            return int(default)
        # Route through float() so a DECIMAL/EXPONENT numeric string truncates
        # rather than raising. int("150000.0") raises ValueError, which silently
        # collapsed a hand-edited or externally-produced profile to the default —
        # a saved "YOUR_BASE_SALARY": "150000.0" made the sidebar report $0 income.
        # (widget_sync._as_int already used int(float(v)); this matches it.)
        if isinstance(value, str):
            v = value.strip()
            if not v:
                return int(default)
            f = float(v)
            if not math.isfinite(f):
                return int(default)
            return int(f)
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def safe_float(value, default: float = 0.0) -> float:
    """Coerce a value to float, falling back to default for None/invalid/NaN/inf."""
    try:
        if value is None:
            return float(default)
        result = float(value)
        if not math.isfinite(result):
            return float(default)
        return result
    except (TypeError, ValueError):
        return float(default)


def as_fraction(value, default: float = 0.0) -> float:
    """Accept a fractional (0.04) or whole-number percent (4.0) and return fractional form."""
    v = safe_float(value, default)
    if v > 1.5:  # user or upstream wrote a whole-number percent
        v = v / 100.0
    return v


def ensure_default(st, key: str, default):
    """Seed ``st.session_state[key]`` with ``default`` if not already set.

    Use BEFORE rendering a widget whose ``key=`` you also want to manage via
    the Session State API. Streamlit raises an error if a widget is
    constructed with a ``value=`` default AND its session_state key has been
    set programmatically — so widgets that rely on session_state-driven
    initialization (via ``sync_widgets_from_overrides``) must omit ``value=``
    and call ``ensure_default`` to seed the initial value.

    Args:
        st: the Streamlit module (or a mock).
        key: widget key.
        default: fallback value used only on first render.

    Returns:
        The current value at ``st.session_state[key]`` (may be the default
        just-seeded, may be a previously synced / user-edited value).
    """
    try:
        if key not in st.session_state:
            st.session_state[key] = default
        return st.session_state[key]
    except Exception:
        return default

