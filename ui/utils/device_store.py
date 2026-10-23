"""Private, on-device storage for a visitor's saved inputs (browser localStorage).

PRIVACY GUARANTEE
    Saved inputs live ONLY in the visitor's own browser, in localStorage for
    this app's origin. This module never writes them to the server's disk, a
    database, a cache file or a log, and it makes no network calls. A hidden
    component iframe (served from the app's own origin, so it shares the app's
    localStorage) talks only to its same-origin parent page, which relays
    values to this visitor's own Streamlit session over the app's existing
    connection. Because the server keeps nothing, saved inputs survive page
    reloads and app redeploys, and the app owner has no copy of them.

LIMITS
    * While a session runs, the server process holds the inputs in memory, as
      it must to compute results (and to relay a save to the browser). Nothing
      is kept once the session ends.
    * localStorage is not encrypted. Anyone using the same browser profile,
      extensions with access to the page, and any other code served from this
      same origin can read it.
    * Storage is per browser and per origin. Another device, browser, profile,
      domain or port starts empty. Clearing site data, or closing a private
      window, erases it.
    * Visitors are trusting the deployed code. A modified app could read the
      data and send it elsewhere; this module does not.

USAGE (from the main script body, not inside an ``st.fragment``)::

    state = device_store.sync(st)          # exactly once per run, near the top
    if state["status"] == "loading":       # first run of a fresh session only
        ...                                # show a brief loading state
    ...
    device_store.save(st, {"mode": "simple", "inputs": {...}})
    device_store.forget(st)                # "forget me on this device"

Status semantics (``sync`` return value ``{"status", "data", "saved_at", "error"}``):
    loading      The browser has not answered yet. Always true on the first run
                 of a new session (page load/reload). The component reads
                 localStorage on mount and posts once, which triggers exactly
                 one rerun; that rerun sees "ready" or "unavailable".
    ready        Storage works. ``data`` is the saved payload (``None`` if
                 nothing is saved, or the stored copy is unreadable/from an
                 unknown schema). After ``save``/``forget`` it mirrors what is
                 now on the device.
    unavailable  localStorage threw (private mode / blocked), a write failed
                 (e.g. quota), or the browser never answered within
                 ``LOAD_TIMEOUT_S`` (checked on the next rerun). ``error``
                 says why. ``save`` is a no-op.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_KEY = "retpy"
# A rerun that finds the store still loading after this long gives up
# ("unavailable"). A healthy load answers well under a second.
LOAD_TIMEOUT_S = 10.0

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "components" / "device_store"
# sync() wraps the hidden iframes in st.container(key=f"{CONTAINER_KEY_PREFIX}-{key}"),
# which Streamlit renders with the CSS class "st-key-mc-device-store-<key>".
CONTAINER_KEY_PREFIX = "mc-device-store"
_HIDE_CSS = '<style>[class*="st-key-mc-device-store"]{display:none !important}</style>'
# session_state key holding a store's cached state: f"{STATE_KEY_PREFIX}{key}".
STATE_KEY_PREFIX = "_device_store_"

_component_func = None


# --------------------------------------------------------------------------
# Envelope helpers (pure)
# --------------------------------------------------------------------------

def _normalize(payload: dict) -> Any:
    """JSON round trip: the exact value a later load will return (and a deep
    copy). Raises TypeError if the payload is not JSON-serializable."""
    return json.loads(json.dumps(payload, ensure_ascii=False))


def _hash_normalized(normalized: Any) -> str:
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def payload_hash(payload: dict) -> str:
    """Content hash of a payload, stable across dict key order."""
    return _hash_normalized(_normalize(payload))


def _envelope(normalized: Any) -> dict:
    saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {"schema": SCHEMA_VERSION, "saved_at": saved_at, "payload": normalized}


def make_envelope(payload: dict) -> dict:
    """Wrap a payload as ``{"schema": 1, "saved_at": <ISO UTC>, "payload": {...}}``."""
    return _envelope(_normalize(payload))


def _parse_envelope(raw: Any) -> dict | None:
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    return raw if isinstance(raw, dict) else None


def migrate(envelope: Any) -> dict | None:
    """Return the payload from a stored envelope (dict or JSON string), upgrading
    older schemas here as they appear. Unknown/newer schemas, missing fields and
    corrupt JSON return None instead of raising."""
    env = _parse_envelope(envelope)
    if env is None:
        return None
    schema = env.get("schema")
    if isinstance(schema, bool) or not isinstance(schema, int):
        return None
    # When SCHEMA_VERSION is bumped, upgrade older envelopes here, before the
    # current-version branch (e.g. `if schema == 1: env, schema = _v1_to_v2(env), 2`).
    if schema == 1:
        payload = env.get("payload")
        return payload if isinstance(payload, dict) else None
    return None


# --------------------------------------------------------------------------
# Streamlit plumbing
# --------------------------------------------------------------------------

def _ctx():
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx()
    except Exception:
        return None


def _component():
    """Declare the static-HTML component (cached once it is registered with a
    running app; declaring outside a script run does not register it)."""
    global _component_func
    if _component_func is not None:
        return _component_func
    import streamlit.components.v1 as components
    func = components.declare_component("device_store", path=str(COMPONENT_DIR))
    if _ctx() is not None:
        _component_func = func
    return func


def _store(st, key: str) -> dict:
    name = STATE_KEY_PREFIX + key
    store = st.session_state.get(name)
    if not isinstance(store, dict) or "status" not in store:
        store = {
            "status": "loading", "data": None, "saved_at": None, "error": None,
            "read_token": uuid.uuid4().hex, "started": time.monotonic(),
            "scope": uuid.uuid4().hex[:12],  # per-session id for the browser's dedupe marker
            "synced_sig": None,       # hash of the payload as loaded from the device
            "op": None,              # latest desired device state, re-rendered every run
            "forgot_pending": False,  # forget() ran before sync() this run (e.g. a callback)
            "run": None,              # this run's writer slot + bookkeeping
        }
        st.session_state[name] = store
    return store


def _public(store: dict) -> dict:
    data = store["data"]
    return {
        "status": store["status"],
        "data": json.loads(json.dumps(data)) if data is not None else None,
        "saved_at": store["saved_at"],
        "error": store["error"],
    }


def _set_unavailable(store: dict, error: str) -> None:
    store.update(status="unavailable", error=error, read_token=None)


def _consume(store: dict, value: Any) -> None:
    """Apply a value posted by the browser. Stale or repeated values are ignored,
    so a widget value that lingers across reruns is harmless."""
    if not isinstance(value, dict):
        return
    kind = value.get("kind")
    if kind == "read":
        token = value.get("token")
        if store["status"] != "loading" or not token or token != store["read_token"]:
            return
        store["read_token"] = None
        if not value.get("ok"):
            _set_unavailable(store, str(value.get("error") or "localStorage unavailable"))
            return
        env = _parse_envelope(value.get("raw"))
        payload = migrate(env)
        saved_at = env.get("saved_at") if payload is not None else None
        store.update(status="ready", error=None, data=payload,
                     saved_at=saved_at if isinstance(saved_at, str) else None,
                     synced_sig=_hash_normalized(payload) if payload is not None else None)
    elif kind == "write_error":
        op = store.get("op")
        if op and value.get("sig") == op.get("sig"):
            store["op"] = None
            _set_unavailable(store, str(value.get("error") or "write failed"))


def _live_run(store: dict) -> dict | None:
    """This run's bookkeeping if sync() already ran in THIS script run, else None
    (e.g. inside a widget callback, which runs before the script body, or a
    fragment rerun). ``ctx.cursors`` is replaced at the start of every run and
    the record holds a reference to it, so identity is an exact test."""
    run = store.get("run")
    ctx = _ctx()
    if not run or ctx is None or run.get("cursors") is not ctx.cursors:
        return None
    return run


def _render_writer(store: dict, key: str, run: dict) -> None:
    """Render the writer iframe for the current op: in place when called from
    sync(), else into this run's slot (save()/forget() after sync()).

    The widget key is derived from the op's signature. The same op keeps the
    same iframe across runs (Streamlit keys widget elements by id, so the
    iframe moves from the slot to its in-place position without remounting):
    it is applied once, and a failure it posts is read back on the next run.
    A new op gets a new key, which also lets a run re-render the slot."""
    op = store["op"]
    wkey = f"{STATE_KEY_PREFIX}{key}_w_{op['sig']}"
    if wkey in run["keys"]:
        wkey = f"{wkey}_{len(run['keys'])}"
    run["keys"].add(wkey)
    run["sig"] = op["sig"]
    with run["slot"] if run["slot"] is not None else contextlib.nullcontext():
        value = _component()(storage_key=key, op=op, scope=store["scope"], height=0,
                             key=wkey, default=None)
    _consume(store, value)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def sync(st, key: str = DEFAULT_KEY) -> dict:
    """Render the hidden storage component (call exactly once per script run,
    near the top) and return ``{"status", "data", "saved_at", "error"}``.

    The loaded state is cached in ``st.session_state[STATE_KEY_PREFIX + key]``,
    so later runs never depend on the browser re-posting. Also re-sends the
    latest save/forget each run, so a write survives an immediate st.rerun()."""
    store = _store(st, key)
    ctx = _ctx()
    run = store["run"] = {
        "cursors": ctx.cursors if ctx is not None else None,
        "slot": None, "sig": None, "keys": set(),
        "forgot": bool(store["forgot_pending"]),
    }
    store["forgot_pending"] = False
    st.html(_HIDE_CSS)  # style-only st.html goes to the event container: no layout space
    with st.container(key=f"{CONTAINER_KEY_PREFIX}-{key}"):
        # The latest op is rendered in place, NOT via an st.empty() filled
        # afterwards: an empty placeholder delta would briefly replace the
        # keyed iframe and remount it every run.
        if store["op"] is not None:
            _render_writer(store, key, run)
        run["slot"] = st.empty()  # target for save()/forget() later in this run
        if store["status"] == "loading":
            value = _component()(storage_key=key, read_token=store["read_token"], height=0,
                                 key=f"{STATE_KEY_PREFIX}{key}_read", default=None)
            _consume(store, value)
    if store["status"] == "loading" and time.monotonic() - store["started"] > LOAD_TIMEOUT_S:
        _set_unavailable(store, "timed out waiting for browser storage")
    return _public(store)


def save(st, payload: dict, key: str = DEFAULT_KEY) -> None:
    """Save ``payload`` (a JSON-serializable dict) to this browser, in this run.

    A no-op unless status is "ready" (so a save can never clobber stored data
    before it was loaded) and after forget() earlier in the same run. The
    browser writes only when the payload's content hash changes; ``saved_at``
    is the time of the last actual change. Raises TypeError for a non-dict or
    non-JSON-serializable payload."""
    if not isinstance(payload, dict):
        raise TypeError(f"device_store.save() needs a dict payload, got {type(payload).__name__}")
    normalized = _normalize(payload)
    store = _store(st, key)
    if store["status"] != "ready":
        return
    run = _live_run(store)
    if run is not None and run["forgot"]:
        return
    sig = _hash_normalized(normalized)
    op = store["op"]
    on_device = op["sig"] if op else store["synced_sig"]  # what the device holds now
    if sig != on_device:
        envelope = _envelope(normalized)
        store["op"] = {"kind": "set", "sig": sig,
                       "value": json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)}
        store["data"] = envelope["payload"]
        store["saved_at"] = envelope["saved_at"]
    if store["op"] is not None and run is not None and run["sig"] != store["op"]["sig"]:
        _render_writer(store, key, run)


def forget(st, key: str = DEFAULT_KEY) -> None:
    """Remove the saved inputs from this browser and reset the cached state to
    ready / no data (stays "unavailable" if storage is unavailable). Any save()
    later in the same run is ignored; turn your "remember" setting off too, or
    the next run will save again."""
    store = _store(st, key)
    store["op"] = {"kind": "remove", "sig": "rm-" + uuid.uuid4().hex[:12]}
    store["read_token"] = None
    if store["status"] != "unavailable":
        store.update(status="ready", error=None)
    store.update(data=None, saved_at=None, synced_sig=None)
    run = _live_run(store)
    if run is None:
        store["forgot_pending"] = True  # sync() renders the removal and blocks saves this run
        return
    run["forgot"] = True
    _render_writer(store, key, run)
