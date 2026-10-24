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
import os
from datetime import datetime
from typing import Any

from retirement_sim import config as cfg

SCHEMA_VERSION = "1.0"
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
    for hand-edited files or legacy saves).
    """
    if not isinstance(json_str, (str, bytes, bytearray)):
        raise ValueError(
            f"Expected JSON string/bytes, got {type(json_str).__name__}"
        )
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON: {exc.msg} (line {exc.lineno}, col {exc.colno})") from exc

    if not isinstance(data, dict):
        raise ValueError("Top-level JSON value must be an object/dict.")

    # Versioned envelope: any of these keys marks the file as our envelope.
    if any(k in data for k in ("version", "app", "overrides")):
        overrides = data.get("overrides")
        if not isinstance(overrides, dict):
            raise ValueError("Envelope 'overrides' must be an object/dict.")
        file_version = str(data.get("version", ""))
        file_major = file_version.split(".", 1)[0]
        expected_major = SCHEMA_VERSION.split(".", 1)[0]
        if file_major != expected_major:
            raise ValueError(
                f"Incompatible profile schema version {file_version!r} "
                f"(expected major {expected_major}.x)."
            )
    else:
        # Bare dict (legacy, no envelope keys) — treat the whole thing as overrides.
        overrides = data

    return cfg.migrate_legacy_overrides(_restore_int_keys(overrides))
