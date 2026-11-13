"""A slider with a small typed number box beside it ("drag OR type").

``slider_with_box(st, label, min_value, max_value, step, key=...)`` is a drop-in
for ``st.slider``. It returns the slider's value, exactly as before.

Seams (see the module tests in tests/test_slider_input.py):

- The SLIDER keeps the caller's own widget key. Saved profiles, widget_sync,
  user_overrides and the tests all read that key, so nothing about it changes.
- The BOX lives under ``key + "__box"``. Two helper entries sit beside it:
  ``key + "__seen"`` (the slider value the box last showed) and
  ``key + "__note"`` (a short message after a typed value was clamped).
- Both widgets use ``on_change`` callbacks. A callback runs BEFORE the next
  draw, so the other widget is already updated when the page redraws (no lag of
  one rerun, and no "created with a default value but also had its value set
  via the Session State API" warning: the slider never gets ``value=``).
- When the slider's key changes from OUTSIDE (a profile or preset load, the
  guided setup handing over, a reset), ``__seen`` no longer matches it, so the
  box re-seeds itself on the next draw. ``utils.widget_sync`` also clears the
  helper keys, so both routes work.

Units: the slider and the box are both in DISPLAY units (percent as 4.0, not
0.04). The caller converts, as it did with ``st.slider``.
"""
from __future__ import annotations

import math
from typing import Any, Optional

BOX = "__box"
SEEN = "__seen"
NOTE = "__note"
SUFFIXES = (BOX, SEEN, NOTE)

BOX_WIDTH = 76          # px; "100.00" fits with the pill padding, even on a phone


def _decimals(step) -> int:
    """Digits after the point that ``step`` needs (0.25 -> 2, 5.0 -> 0, 1 -> 0)."""
    text = f"{float(step):g}"
    return len(text.split(".")[1]) if "." in text else 0


def _is_int(*numbers) -> bool:
    return all(isinstance(n, int) and not isinstance(n, bool) for n in numbers)


def _fmt(value, decimals: int) -> str:
    return f"{value:,.{decimals}f}" if decimals else f"{int(round(value))}"


def snap(raw, lo, hi, step, as_int: bool):
    """(value, note) for a typed ``raw``: clamped to [lo, hi] and rounded to the
    precision the step uses (a whole number for whole-number sliders). It is NOT
    forced onto the step grid: a box that turns 63 into 65 would defeat typing an
    exact value. ``note`` is a short sentence when the value had to move, else None."""
    decimals = 0 if as_int else _decimals(step)
    try:
        value = round(float(raw), decimals)
    except (TypeError, ValueError, OverflowError):
        return None, None
    if not math.isfinite(value):                   # NaN and infinity are not values
        return None, None
    note = None
    if value < lo:
        value, note = lo, f"The lowest value is {_fmt(lo, decimals)}, so {_fmt(lo, decimals)} was used."
    elif value > hi:
        value, note = hi, f"The highest value is {_fmt(hi, decimals)}, so {_fmt(hi, decimals)} was used."
    value = int(value) if as_int else float(value)
    return value, note


def _to_box(value, as_int: bool, decimals: int):
    """What the box holds for a slider value: a plain int or float of one type."""
    try:
        return int(round(float(value))) if as_int else round(float(value), decimals)
    except (TypeError, ValueError):
        return 0 if as_int else 0.0


def _loaded_note(ss, key: str):
    """The (loaded value, value used) pair ``widget_sync`` recorded when it had to move
    this slider's saved value into range, while the slider still holds that value."""
    pair = (ss.get("_sync_notes") or {}).get(key)
    return pair if pair and ss.get(key) == pair[1] else None


def _on_slider(st, key: str, as_int: bool, decimals: int) -> None:
    ss = st.session_state
    (ss.get("_sync_notes") or {}).pop(key, None)
    ss[key + BOX] = _to_box(ss[key], as_int, decimals)
    ss[key + SEEN] = ss[key]
    ss.pop(key + NOTE, None)


def _on_box(st, key: str, lo, hi, step, as_int: bool) -> None:
    ss = st.session_state
    (ss.get("_sync_notes") or {}).pop(key, None)
    decimals = 0 if as_int else _decimals(step)
    value, note = snap(ss.get(key + BOX), lo, hi, step, as_int)
    if value is None:                              # the box was emptied: keep the slider's value
        value = ss.get(key, lo)
    ss[key] = value
    ss[key + BOX] = _to_box(value, as_int, decimals)
    ss[key + SEEN] = value
    if note:
        ss[key + NOTE] = note
    else:
        ss.pop(key + NOTE, None)


def forget_box(st, key: str) -> None:
    """Drop the box's state for slider ``key`` so the box re-seeds from the slider."""
    for suffix in SUFFIXES:
        try:
            st.session_state.pop(key + suffix, None)
        except Exception:  # pragma: no cover - a mock without .pop
            pass


def slider_with_box(st, label: str, min_value, max_value, step=1, *, key: str,
                    value=None, help: Optional[str] = None, unit: str = "",
                    format: Optional[str] = None) -> Any:
    """Draw ``st.slider`` and a typed box beside it, kept in sync both ways.

    ``unit`` is shown on the slider ("%", " bps", " yr"); the box is the bare
    number (its label, read by screen readers, names the unit). ``value`` seeds
    the slider only when ``key`` is not in session state yet (callers normally
    seed it themselves with ``ensure_default``). Returns the slider's value.
    """
    ss = st.session_state
    as_int = _is_int(min_value, max_value, step)
    decimals = 0 if as_int else _decimals(step)

    if key not in ss:
        ss[key] = value if value is not None else min_value
    if max_value <= min_value:
        # Nothing to slide: st.slider raises when min and max are equal (a 99-year-old's
        # retirement age can only be 99). Show the one value as text.
        ss[key] = min_value
        shown = f"{_fmt(min_value, decimals)}{unit}"
        st.markdown(f"{label}: **{shown}**")
        return min_value
    try:
        inside = min_value <= ss[key] <= max_value
    except TypeError:
        inside = False
    if not inside:                          # a value past the ends (a saved plan, another widget) moves in
        fitted, _ = snap(ss[key], min_value, max_value, step, as_int)
        ss[key] = min_value if fitted is None else fitted
    bkey = key + BOX
    if bkey not in ss or ss.get(key + SEEN) != ss[key]:
        ss[bkey] = _to_box(ss[key], as_int, decimals)     # changed from outside: follow it
        ss[key + SEEN] = ss[key]
        ss.pop(key + NOTE, None)

    base = "%d" if as_int else f"%.{decimals}f"
    fmt = format or (base + unit.replace("%", "%%") if unit else None)

    with st.container(key=f"sbx-{key}", horizontal=True, vertical_alignment="bottom"):
        out = st.slider(label, min_value=min_value, max_value=max_value, step=step,
                        key=key, help=help, format=fmt,
                        on_change=_on_slider, args=(st, key, as_int, decimals))
        st.number_input(f"{label}: type a value", step=step, key=bkey, format=base,
                        label_visibility="collapsed", width=BOX_WIDTH,
                        on_change=_on_box, args=(st, key, min_value, max_value, step, as_int))
    note = ss.get(key + NOTE)
    loaded = _loaded_note(ss, key)
    if note:
        st.caption(note)
    elif loaded:
        st.caption(f"Your saved value {loaded[0]:g} is outside {min_value:g} to {max_value:g}, "
                   f"so {loaded[1]:g} is used.")
    return out
