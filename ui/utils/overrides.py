"""Shared helpers for reading/writing user override values in session state.

Centralizes the `st.session_state["user_overrides"]` dict access pattern that
was previously duplicated as per-file `_get`/`_set` helpers across the UI.
"""
from __future__ import annotations


def get_override(st, key, default=None):
    """Return the stored override for `key`, or `default` if not set."""
    return st.session_state.get("user_overrides", {}).get(key, default)


def set_override(st, key, value):
    """Store `value` as the override for `key` in session state."""
    st.session_state.setdefault("user_overrides", {})
    st.session_state["user_overrides"][key] = value
