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


_UNITS = ((1e9, "B"), (1e6, "M"), (1e3, "K"))


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
        digits = precision + 1
        body = f"{abs_val:,.{precision}f}"
        for i, (size, suffix) in enumerate(_UNITS):
            if abs_val >= size:
                # A value that rounds up to 1000 of its unit is one of the next
                # unit ($999,999 -> "$1.0M", not "$1,000.0K").
                if i and round(abs_val / size, digits) >= 1000:
                    size, suffix = _UNITS[i - 1]
                body = f"{abs_val / size:,.{digits}f}{suffix}"
                break
    else:
        body = f"{value:,.{precision}f}"
    return f"-${body}" if negative else f"${body}"


def months_text(n: float) -> str:
    """A count of months for a sentence: "5.3 months", "1 month"; a cash pile
    that covers decades reads "over 100 years", not "1000000.0 months"."""
    if _is_bad(n):
        return "—"
    if n >= 1200:
        return "over 100 years"
    text = f"{n:.1f}".rstrip("0").rstrip(".") if n < 100 else f"{n:,.0f}"
    return f"{text} month" + ("" if text == "1" else "s")


def money_precise(value: Union[int, float, None]) -> str:
    """Shortened dollars with a second decimal from a million up, for balances:
    money_precise(1_957_300) -> "$1.96M"; under a million it matches
    ``money(value, shorten=True)`` ("$34.0K")."""
    precision = 1 if not _is_bad(value) and abs(value) >= 1e6 else 0
    return money(value, precision=precision, shorten=True)


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


def metric_row(st, items: list, wrap_chars: int = 14) -> None:
    """A row of ``st.metric`` cells (``(label, value, kwargs)`` tuples) that stays
    aligned on a phone, where the row wraps to two per line: a pair whose longer
    label may wrap gets a hidden marker, so theme.css makes both labels reserve
    two lines and the values share a baseline."""
    cols = st.columns(len(items))
    for i, (label, value, kw) in enumerate(items):
        pair = items[i - i % 2: i - i % 2 + 2]
        with cols[i]:
            if any(len(p[0]) > wrap_chars for p in pair):
                st.markdown('<span class="mc-l2-mark"></span>', unsafe_allow_html=True)
            st.metric(label, value, **kw)
