"""A safety net under every bounded Streamlit widget.

Streamlit raises (``StreamlitValueAboveMaxError``, ``ValueError: x is not in
iterable``, ...) when a widget's session-state value no longer fits the widget:
a number outside ``min_value``..``max_value``, or a choice that is not one of the
options. That happens whenever the value came from somewhere with other bounds: a
saved profile from an older version, a hand-edited file, another widget with a
wider range, a default computed from your age. ``_safe_render`` then replaces the
whole section with "couldn't be displayed".

``install(st)`` wraps the bounded widgets once. Before each call it checks the
widget's own key in ``st.session_state`` and, only when the value does not fit,
moves it to the nearest value that does (numbers) or to the widget's default
choice (options). A value that fits is never touched. Nothing else changes.
"""
from __future__ import annotations

import functools
import math

_MARK = "_widget_guard_installed"


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _whole(*numbers) -> bool:
    return all(n is None or (isinstance(n, int) and not isinstance(n, bool)) for n in numbers)


def fit_number(value, lo, hi, step=None, fallback=None):
    """``value`` clamped into [lo, hi] (either may be None), as an int when the
    widget's numbers are all whole. Text that reads as a number is accepted. A value
    that is not a usable number becomes ``fallback`` (clamped), else ``lo``, else None."""
    def _clamp(v):
        if lo is not None and v < lo:
            v = lo
        if hi is not None and v > hi:
            v = hi
        return v

    if not _is_number(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = None
    if value is None or isinstance(value, bool) or math.isnan(value) or math.isinf(value):
        value = fallback if _is_number(fallback) else lo
        if value is None:
            return None
    value = _clamp(value)
    return int(round(value)) if _whole(lo, hi, step) and lo is not None else value


def _arg(args, kwargs, pos, name, default=None):
    """A widget parameter given by position (``pos`` counts the label as 0) or by name."""
    if name in kwargs:
        return kwargs[name]
    return args[pos] if len(args) > pos else default


# What Streamlit accepts for a number_input with no min_value / max_value (the largest
# integer a browser holds exactly): anything past it raises like any other out-of-range value.
_JS_MAX = 2 ** 53 - 1


def _fit_numeric(st, args, kwargs, ranged=False) -> None:
    """Fit a number_input / slider state. ``ranged`` is a slider, which may hold a (low, high) pair."""
    key = kwargs.get("key")
    ss = st.session_state
    if key is None or key not in ss:
        return
    lo, hi = _arg(args, kwargs, 1, "min_value"), _arg(args, kwargs, 2, "max_value")
    start = _arg(args, kwargs, 3, "value", "min")
    step = _arg(args, kwargs, 4, "step")
    current = ss[key]
    if current is None and start is None:
        return                                                   # value=None: an empty box is valid
    if ranged and isinstance(current, (tuple, list)) and len(current) == 2:
        fixed = type(current)(fit_number(v, lo, hi, step) for v in current)
    else:
        fixed = fit_number(current, lo, hi, step, fallback=start)
        if fixed is not None and not ranged:                     # no bound given: Streamlit's own
            fixed = max(-_JS_MAX, min(_JS_MAX, fixed))
    if fixed is not None and fixed != current:
        ss[key] = fixed
    elif fixed is None:
        del ss[key]


def _options(args, kwargs):
    raw = _arg(args, kwargs, 1, "options", None)
    try:
        return list(raw)
    except TypeError:
        return None


def _fit_choice(st, args, kwargs, index_pos=None, several=False) -> None:
    """Fit a choice widget's state to its options. ``several`` is a widget that holds a list."""
    key = kwargs.get("key")
    ss = st.session_state
    if key is None or key not in ss:
        return
    options = _options(args, kwargs)
    if options is None:
        return
    current = ss[key]
    if current is None:
        return                                                   # "nothing chosen" is a valid state
    if several and isinstance(current, (list, tuple, set)):      # multiselect / multi-pills
        kept = [v for v in current if v in options]
        if len(kept) != len(current):
            ss[key] = kept
        return
    try:
        if current in options:
            return
    except TypeError:                                            # e.g. a list: not a choice
        pass
    index = _arg(args, kwargs, index_pos, "index", 0) if index_pos else kwargs.get("index", 0)
    if _is_number(index) and 0 <= index < len(options):
        ss[key] = options[int(index)]
    elif options:
        ss[key] = options[0]
    else:
        del ss[key]


# widget name -> how to fit its state (positions: label is 0)
_FITTERS = {
    "number_input": lambda st, a, k: _fit_numeric(st, a, k),
    "slider": lambda st, a, k: _fit_numeric(st, a, k, ranged=True),
    "selectbox": lambda st, a, k: _fit_choice(st, a, k, index_pos=2),
    "radio": lambda st, a, k: _fit_choice(st, a, k, index_pos=2),
    "select_slider": lambda st, a, k: _fit_choice(st, a, k),
    "segmented_control": lambda st, a, k: _fit_choice(st, a, k, several=True),
    "pills": lambda st, a, k: _fit_choice(st, a, k, several=True),
    "multiselect": lambda st, a, k: _fit_choice(st, a, k, several=True),
}


def _wrap(st, name, original, fit):
    @functools.wraps(original)
    def guarded(*args, **kwargs):
        try:
            fit(st, args, kwargs)
        except Exception:                                        # a guard must never be the crash
            pass
        return original(*args, **kwargs)
    setattr(guarded, _MARK, True)
    return guarded


def install(st) -> None:
    """Wrap the bounded widgets on the ``streamlit`` module. Safe to call every run."""
    for name, fit in _FITTERS.items():
        original = getattr(st, name, None)
        if original is None or getattr(original, _MARK, False):
            continue
        setattr(st, name, _wrap(st, name, original, fit))
