"""A safety net under every bounded Streamlit widget.

Streamlit raises (``StreamlitValueAboveMaxError``, ``ValueError: x is not in
iterable``, ...) when a widget's session-state value no longer fits the widget:
a number outside ``min_value``..``max_value``, or a choice that is not one of the
options. That happens whenever the value came from somewhere with other bounds: a
saved profile from an older version, a hand-edited file, another widget with a
wider range, a default computed from your age. ``_safe_render`` then replaces the
whole section with "couldn't be displayed".

``install(st)`` wraps the bounded widgets once (the module's and every DeltaGenerator's). Before each call it checks the
widget's own key in ``st.session_state`` and, only when the value does not fit,
moves it to the nearest value that does (numbers) or to the widget's default
choice (options). A value that fits is never touched. Nothing else changes.

A number box that had to move a saved value says so in a short caption under it
("Your saved value 400,000 is outside 0 to 250,000, so 250,000 is used."), as the
slider helper does (``utils/slider_input.py``), never silently. The caption stays
while the box still holds the value that was used. Values ``utils.widget_sync`` had
to clamp at load (it records them in ``_sync_notes``) get the same caption.
"""
from __future__ import annotations

import functools
import math

_MARK = "_widget_guard_installed"
NOTES = "_guard_notes"          # widget key -> (value it held, value now, lo, hi)


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
    if current is None and (start is None or kwargs.get("placeholder") is not None):
        return                                                   # an empty box (value=None, or a placeholder) is valid
    if ranged and isinstance(current, (tuple, list)) and len(current) == 2:
        fixed = type(current)(fit_number(v, lo, hi, step) for v in current)
    else:
        fixed = fit_number(current, lo, hi, step, fallback=start)
        if fixed is not None and not ranged:                     # no bound given: Streamlit's own
            fixed = max(-_JS_MAX, min(_JS_MAX, fixed))
    if fixed is not None and fixed != current:
        if not ranged and _is_number(current) and math.isfinite(current):
            notes = ss.get(NOTES)
            if not isinstance(notes, dict):
                notes = ss[NOTES] = {}
            notes[key] = (current, fixed, lo, hi)
        ss[key] = fixed
    elif fixed is None:
        del ss[key]


def _num(v) -> str:
    return f"{v:,.0f}" if float(v) == int(v) else f"{v:,.4g}"


def note_text(st, key, lo, hi):
    """The sentence for a number box whose saved value was moved into range, else None.
    Two sources: this guard (a value that did not fit the box) and ``widget_sync``
    (a value it clamped when a profile loaded). Only while the box still holds the value used."""
    ss = st.session_state
    if key is None or key not in ss or str(key).endswith("__box"):
        return None
    pair = None
    guard = (ss.get(NOTES) or {}).get(key)
    if guard and ss[key] == guard[1]:
        pair, lo, hi = (guard[0], guard[1]), guard[2], guard[3]
    else:
        sync = (ss.get("_sync_notes") or {}).get(key)
        if sync and ss[key] == sync[1]:
            pair = sync
    if pair is None or not _is_number(pair[0]) or not math.isfinite(pair[0]):
        return None
    where = f" is outside {_num(lo)} to {_num(hi)}," if lo is not None and hi is not None else " did not fit,"
    return f"Your saved value {_num(pair[0])}{where} so {_num(pair[1])} is used."


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


def _say(st, say, args, kwargs, out):
    """Caption under a number box that moved a saved value (never raises)."""
    try:
        text = note_text(st, kwargs.get("key"), _arg(args, kwargs, 1, "min_value"),
                         _arg(args, kwargs, 2, "max_value"))
        if text:
            say.caption(text)
    except Exception:
        pass
    return out


def _wrap(st, original, fit, method=False, notes=False):
    """``original`` with ``fit`` run first. ``method``: a DeltaGenerator method (it gets ``self``).
    ``notes``: caption a value the fit had to move (number boxes)."""
    if method:
        @functools.wraps(original)
        def guarded(self, *args, **kwargs):
            try:
                fit(st, args, kwargs)
            except Exception:                                    # a guard must never be the crash
                pass
            out = original(self, *args, **kwargs)
            return _say(st, self, args, kwargs, out) if notes else out
    else:
        @functools.wraps(original)
        def guarded(*args, **kwargs):
            try:
                fit(st, args, kwargs)
            except Exception:
                pass
            out = original(*args, **kwargs)
            return _say(st, st, args, kwargs, out) if notes else out
    setattr(guarded, _MARK, True)
    return guarded


def install(st) -> None:
    """Wrap the bounded widgets on the ``streamlit`` module AND on ``DeltaGenerator``
    (``col.number_input``, ``st.sidebar.slider``, ``container.radio``). Safe to call every run."""
    from streamlit.delta_generator import DeltaGenerator
    for name, fit in _FITTERS.items():
        original = getattr(st, name, None)
        if original is not None and not getattr(original, _MARK, False):
            setattr(st, name, _wrap(st, original, fit, notes=name == "number_input"))
        method = getattr(DeltaGenerator, name, None)
        if method is not None and not getattr(method, _MARK, False):
            setattr(DeltaGenerator, name, _wrap(st, method, fit, method=True, notes=name == "number_input"))
