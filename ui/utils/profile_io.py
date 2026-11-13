"""Serialization helpers for saving/loading user_overrides profiles.

The UI stores user edits in ``st.session_state.user_overrides`` — a plain dict
whose keys mirror ``retirement_sim.config`` constants. This module provides a
small, versioned JSON envelope so users can download their current inputs and
restore them later, even across releases.

The envelope may also carry an optional top-level ``"label"`` (the name shown
in the profile picker). :func:`deserialize_overrides` ignores it, so it never
leaks into the overrides.

Loading also brings an older profile up to today's keys (its two-child keys
become a ``CHILDREN`` list; the retired wedding flag is dropped -- see
``retirement_sim.config.migrate_legacy_overrides``), so it gives the same
results and saves back in the new form.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime
from typing import Any

from retirement_sim import config as cfg
from retirement_sim import debts

SCHEMA_VERSION = "1.0"
_MISSING = object()
APP_TAG = "retirement-monte-carlo"

# Your own "My situation" profile lives OUTSIDE the repository so personal
# numbers are never committed. RETIREMENT_SIM_PROFILE overrides the location.
PERSONAL_PROFILE_ENV = "RETIREMENT_SIM_PROFILE"
DEFAULT_PERSONAL_PROFILE = "~/.config/retirement-sim/my_profile.json"


def personal_profile_path() -> str:
    """Absolute path of the private profile (it may not exist)."""
    raw = os.environ.get(PERSONAL_PROFILE_ENV, "").strip() or DEFAULT_PERSONAL_PROFILE
    return os.path.abspath(os.path.expanduser(raw))


def _stringify_keys(obj: Any) -> Any:
    """Recursively convert dict keys to strings (JSON requirement)."""
    if isinstance(obj, dict):
        return {str(k): _stringify_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_stringify_keys(v) for v in obj]
    if isinstance(obj, tuple):
        return [_stringify_keys(v) for v in obj]
    return obj


def _restore_int_keys(obj: Any) -> Any:
    """Recursively convert numeric-looking dict keys back to int."""
    if isinstance(obj, dict):
        restored = {}
        for k, v in obj.items():
            new_key = k
            if isinstance(k, str) and k.lstrip("-").isdigit():
                try:
                    new_key = int(k)
                except ValueError:
                    new_key = k
            restored[new_key] = _restore_int_keys(v)
        return restored
    if isinstance(obj, list):
        return [_restore_int_keys(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Loading must never crash on a hand-edited or damaged file. Every value is
# checked against the type of the config constant it overrides: one that does not
# fit is dropped (so the default applies), never passed on. Keys the config does
# not know are left alone (the engine ignores them).
# ---------------------------------------------------------------------------

# Keys the UI itself stores, which are not config constants (so there is no default to read).
_UI_KEY_DEFAULTS = {"TARGET_RETIREMENT_AGE": 60, "HOUSEHOLD_INCOME_QUICK": 0,
                    "TOTAL_SAVINGS_QUICK": 0, "NEW_HOME_ESCROW_PCT": 0.0135}
_TRUE, _FALSE = {"true", "yes", "on", "1"}, {"false", "no", "off", "0"}
# A home move's fields (utils.derived.housing_timeline): text for "action", numbers for the rest.
_MOVE_FIELDS = {"action": "", "age": 0, "price": 0, "down_pct": 0, "rate": 0, "years": 0, "costs": 0,
                "selling_cost_pct": 0, "rent": 0, "loan": 0, "monthly": 0}


def _number(v):
    """``v`` as a finite number (numeric text is accepted), else None."""
    if isinstance(v, str):
        try:
            v = float(v.strip())
        except ValueError:
            return None
        v = int(v) if v.is_integer() and abs(v) < 1e15 else v
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return v if math.isfinite(v) else None


def _fit(value, default):
    """(ok, value): ``value`` as the type of ``default``, or (False, None) when it does not fit."""
    if isinstance(default, bool):
        text = value.strip().lower() if isinstance(value, str) else None
        if isinstance(value, bool):
            return True, value
        if _number(value) in (0, 1) and not isinstance(value, str):
            return True, bool(value)
        if text in _TRUE | _FALSE:
            return True, text in _TRUE
        return False, None
    if isinstance(default, (int, float)):
        n = _number(value)
        return (n is not None), n
    if default is None:                                  # numeric when set (an age, a $ amount)
        n = _number(value)
        return (True, None) if value is None else ((n is not None), n)
    if isinstance(default, str):
        return isinstance(value, str), value
    if isinstance(default, dict):
        return _fit_dict(value, default)
    if isinstance(default, (list, tuple)):
        return isinstance(value, (list, tuple)), list(value) if isinstance(value, (list, tuple)) else None
    return True, value


def _fit_dict(value, default):
    if not isinstance(value, dict):
        return False, None
    flat = default and all(isinstance(k, str) for k in default) and not any(
        isinstance(v, (dict, list, tuple)) for v in default.values())
    if not flat:
        return True, value
    out = dict(value)                                    # what was saved stays; a bad entry gets its default
    for k in default:
        if k in value:
            ok, fixed = _fit(value[k], default[k])
            out[k] = fixed if ok else default[k]
    return True, out


def _fit_comp_table(table, default):
    """YOUR_COMPENSATION_BY_AGE: {age: {base, bonus, ...}}. Only int ages and dict rows stay;
    inside a row, a number that is not a number goes (the row's other entries stay)."""
    if not isinstance(table, dict):
        return None
    row0 = next(iter(default.values()))
    rows = {}
    for age, row in table.items():
        if isinstance(age, int) and isinstance(row, dict):
            rows[age] = {k: v for k, v in row.items()
                         if k not in row0 or _fit(v, row0[k])[0]}
    return rows or None


def _fit_rows(rows, defaults, keep):
    """A list of dicts (children, home moves): non-dicts go, a bad number is dropped
    from its row (the default fills in), and ``keep(row)`` can reject a row."""
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fixed = {}
        for k, v in row.items():
            ok, v = _fit(v, defaults[k]) if k in defaults else (True, v)
            if ok:
                fixed[k] = v
        if keep(fixed):
            out.append(fixed)
    return out


def sanitize_overrides(overrides: dict) -> dict:
    """``overrides`` with every value that cannot be what its key stands for dropped,
    so a hand-edited or damaged profile loads (on the defaults) instead of crashing."""
    out = {}
    for key, value in overrides.items():
        if not isinstance(key, str):
            continue
        default = (_UI_KEY_DEFAULTS[key] if key in _UI_KEY_DEFAULTS
                   else cfg.LEGACY_CHILD_KEYS[key] if key in cfg.LEGACY_CHILD_KEYS
                   else getattr(cfg, key, _MISSING))
        if default is _MISSING:
            out[key] = value
        elif key == "YOUR_COMPENSATION_BY_AGE":
            table = _fit_comp_table(value, default)
            if table is not None:
                out[key] = table
        elif key == "CHILDREN":
            ok, rows = _fit(value, [])
            if ok:
                out[key] = _fit_rows(rows, cfg.CHILD_DEFAULTS, lambda r: True)
        elif key == "DEBTS":
            if isinstance(value, list):                  # the debts module's own cleaner never raises
                out[key] = debts.normalize_debts(value)
        elif key == "HOME_EVENTS":
            ok, rows = _fit(value, [])
            if ok:
                out[key] = _fit_rows(rows, _MOVE_FIELDS, lambda r: r.get("action") in cfg._HOME_ACTIONS
                                     and _number(r.get("age")) is not None)
        else:
            ok, fixed = _fit(value, default)
            if ok:
                out[key] = fixed
    return out


def serialize_overrides(user_overrides: dict) -> str:
    """Serialize user_overrides dict to a JSON string with metadata envelope."""
    if not isinstance(user_overrides, dict):
        raise TypeError(
            f"user_overrides must be a dict, got {type(user_overrides).__name__}"
        )
    payload = {
        "version": SCHEMA_VERSION,
        "app": APP_TAG,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "overrides": _stringify_keys(user_overrides),
    }
    return json.dumps(payload, indent=2, default=str)


def deserialize_overrides(json_str: str) -> dict:
    """Parse JSON produced by :func:`serialize_overrides` and return the
    overrides dict.

    Accepts both the versioned envelope and a raw dict of overrides (tolerant
    for hand-edited files or legacy saves). An envelope with no version is read
    as the current one. Values that do not fit what their key stands for are
    dropped (see :func:`sanitize_overrides`), so a damaged file loads on the
    defaults. Anything that cannot be read at all raises ``ValueError``.
    """
    if not isinstance(json_str, (str, bytes, bytearray)):
        raise ValueError(
            f"Expected JSON string/bytes, got {type(json_str).__name__}"
        )
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON: {exc.msg} (line {exc.lineno}, col {exc.colno})") from exc
    except RecursionError as exc:
        raise ValueError("Malformed JSON: nested too deeply") from exc

    if not isinstance(data, dict):
        raise ValueError("Top-level JSON value must be an object/dict.")

    # Versioned envelope: any of these keys marks the file as our envelope. A
    # hand-edited file may wrap the envelope in another one: open each layer.
    for _ in range(3):
        if not any(k in data for k in ("version", "app", "overrides")):
            break
        overrides = data.get("overrides")
        if not isinstance(overrides, dict):
            raise ValueError("Envelope 'overrides' must be an object/dict.")
        file_version = "" if data.get("version") is None else str(data["version"])
        file_major = file_version.split(".", 1)[0]
        expected_major = SCHEMA_VERSION.split(".", 1)[0]
        if file_version and file_major != expected_major:
            raise ValueError(
                f"Incompatible profile schema version {file_version!r} "
                f"(expected major {expected_major}.x)."
            )
        data = overrides
    # else: a bare dict (legacy, no envelope keys) is the overrides themselves.

    try:
        values = sanitize_overrides(_restore_int_keys(data))
        return cfg.migrate_legacy_overrides(values)
    except RecursionError as exc:
        raise ValueError("Malformed JSON: nested too deeply") from exc


# ---------------------------------------------------------------------------
# Money check-up answers (utils/simple_finance.py): their own small envelope,
# so a check-up file is never mistaken for a planner profile (or the reverse).
# ---------------------------------------------------------------------------
CHECKUP_APP_TAG = "retirement-money-checkup"


def serialize_checkup(inputs: dict) -> str:
    """JSON text for the check-up's answers (a ``normalize_inputs`` dict)."""
    if not isinstance(inputs, dict):
        raise TypeError(f"inputs must be a dict, got {type(inputs).__name__}")
    payload = {"version": SCHEMA_VERSION, "app": CHECKUP_APP_TAG,
               "saved_at": datetime.now().isoformat(timespec="seconds"), "checkup": inputs}
    return json.dumps(payload, indent=2, default=str)


def deserialize_checkup(json_str: Any) -> dict:
    """The check-up answers in ``json_str`` (not yet normalized: pass them to
    ``simple_finance.normalize_inputs``). Raises ValueError with a plain reason."""
    if not isinstance(json_str, (str, bytes, bytearray)):
        raise ValueError(f"Expected JSON string/bytes, got {type(json_str).__name__}")
    try:
        data = json.loads(json_str)
    except (ValueError, RecursionError) as exc:
        raise ValueError("That isn't a valid JSON file.") from exc
    if not isinstance(data, dict):
        raise ValueError("Top-level JSON value must be an object/dict.")
    if data.get("app") != CHECKUP_APP_TAG or not isinstance(data.get("checkup"), dict):
        raise ValueError("That file isn't saved money check-up answers. "
                         "Planner profiles load in the Retirement planner.")
    return data["checkup"]
