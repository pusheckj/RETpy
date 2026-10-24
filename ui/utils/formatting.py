"""Formatting helpers for the UI."""
from __future__ import annotations

import math
from typing import Union


def _is_bad(value) -> bool:
    """Return True for None, NaN, or infinite values."""
    if value is None:
        return True
    if isinstance(value, float) and not math.isfinite(value):
        return True
    return False


def success_tier(rate, target) -> str:
    """"good" (>= target), "warn" (>= 75% of target) or "bad", for the user's target."""
    rate = rate or 0.0
    if rate >= target - 1e-9:
        return "good"
    if rate >= 0.75 * target - 1e-9:
        return "warn"
    return "bad"


def money(value: Union[int, float, None], precision: int = 0, shorten: bool = False) -> str:
    """Format a dollar amount.

    Args:
        value: numeric value (None/NaN/inf renders as em-dash)
        precision: decimal places
        shorten: if True, use K/M/B suffixes for large numbers

    Examples:
        money(1234567) -> "$1,234,567"
        money(1234567, shorten=True) -> "$1.23M"
        money(-1000) -> "-$1,000"
        money(None) -> "—"
    """
    if _is_bad(value):
        return "—"
    negative = value < 0
    value = abs(value)
    if shorten:
        abs_val = value
        if abs_val >= 1e9:
            body = f"{abs_val / 1e9:,.{precision + 1}f}B"
        elif abs_val >= 1e6:
            body = f"{abs_val / 1e6:,.{precision + 1}f}M"
        elif abs_val >= 1e3:
            body = f"{abs_val / 1e3:,.{precision + 1}f}K"
        else:
            body = f"{abs_val:,.{precision}f}"
    else:
        body = f"{value:,.{precision}f}"
    return f"-${body}" if negative else f"${body}"


def money_md(value: Union[int, float, None], precision: int = 0, shorten: bool = False) -> str:
    """``money()`` with the ``$`` escaped for Streamlit markdown/captions.

    Streamlit renders ``$...$`` as LaTeX math, so two dollar amounts in one
    caption get mangled into italic math. Use this in st.caption/st.markdown
    text (NOT in Plotly, where a literal ``$`` is fine).
    """
    return money(value, precision=precision, shorten=shorten).replace("$", "\\$")


def pct(value: Union[float, None], precision: int = 1) -> str:
    """Format as percentage (expects 0.82 -> '82.0%')."""
    if _is_bad(value):
        return "—"
    return f"{value * 100:.{precision}f}%"


def age(value: Union[int, float, None]) -> str:
    """Format an age."""
    if _is_bad(value):
        return "—"
    return f"Age {int(round(value))}"


def years(value: Union[int, float, None]) -> str:
    """Format a year count."""
    if _is_bad(value):
        return "—"
    n = int(round(value))
    return f"{n} year{'s' if n != 1 else ''}"


def basis_points(value: Union[float, None]) -> str:
    """Format basis points (expects 0.0015 -> '15 bps')."""
    if _is_bad(value):
        return "—"
    return f"{int(round(value * 10_000))} bps"


def signed_pct(value: Union[float, None], precision: int = 1) -> str:
    """Format signed percentage with explicit + or -."""
    if _is_bad(value):
        return "—"
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value) * 100:.{precision}f}%"
