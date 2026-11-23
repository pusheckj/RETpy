"""Private, in-browser storage for a visitor's inputs (sessionStorage and localStorage).

PRIVACY GUARANTEE
    Saved inputs live ONLY in the visitor's own browser, for this app's origin.
    This module never writes them to the server's disk, a database, a cache
    file or a log, and it makes no network calls. A hidden component iframe
    (served from the app's own origin, so it shares the app's storage) talks
    only to its same-origin parent page, which relays values to this visitor's
    own Streamlit session over the app's existing connection. Because the
    server keeps nothing, saved inputs survive page reloads and app redeploys,
    and the app owner has no copy of them.

WHAT IS STORED, AND WHERE (one reader round trip reads all of it)
    tab      sessionStorage["retpy"]      this tab's inputs, always on; a refresh
                                          keeps them, closing the tab erases them
    device   localStorage["retpy"]        the same inputs, written only while
                                          "Remember me" is on; kept after the tab closes
    prefs    localStorage["retpy-prefs"]  display choices only (theme, font, simulation count)
    view     sessionStorage["mcView"]     scroll position and open tabs; written by the
                                          page script, read here (never written here)
    The tab and device copies share one envelope, ``{schema: 1, saved_at, payload}``.
    New payload fields are optional, so the schema stays 1 and a rollback is safe.

LIMITS
    * While a session runs, the server process holds the inputs in memory, as
      it must to compute results (and to relay a save to the browser). Nothing
      is kept once the session ends.
    * Browser storage is not encrypted. Anyone using the same browser profile,
      extensions with access to the page, and any other code served from this
      same origin can read it.
    * Storage is per browser and per origin. Another device, browser, profile,
      domain or port starts empty. Clearing site data, or closing a private
      window, erases it.
    * Visitors are trusting the deployed code. A modified app could read the
      data and send it elsewhere; this module does not.

USAGE (from the main script body, not inside an ``st.fragment``)::

    state = device_store.sync(st)          # exactly once per run, first thing
    if state["status"] == "loading":       # first run of a fresh session only
        ...                                # show a brief loading state
    ...
    device_store.save(st, tab_payload, device_payload_or_None, prefs)
    device_store.forget(st)                # "forget me on this device"

Status semantics (``sync`` return value: ``status``, ``tab``, ``device``,
``prefs``, ``view_client``, ``narrow``, ``targets``, ``saved_at``, ``error``):
    loading      The browser has not answered yet. Always true on the first run
                 of a new session (page load/reload). The component reads the
                 stores on mount and posts once, which triggers exactly one
                 rerun; that rerun sees "ready" or "unavailable".
    ready        Storage works. ``tab`` and ``device`` are the saved payloads
                 (``None`` if nothing is saved, or the stored copy is
                 unreadable or from an unknown schema). ``targets`` says per
                 store whether it works ("ok", "blocked" or "failed").
    unavailable  Neither the tab nor the device store works, or the browser
                 never answered within ``LOAD_TIMEOUT_S``. ``error`` says why.
                 ``save`` is a no-op.
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
# A load that is still waiting after this long gives up ("unavailable"). A
# healthy load answers well under a second. The loading screen checks the clock
# on its own timer (app._loading_screen), so a silent iframe cannot hold it forever.
LOAD_TIMEOUT_S = 4.0
# One stored item (tab or device envelope, or prefs) is never written above this.
MAX_ITEM_BYTES = 200_000
# A queued write is sent with this many renders, then dropped (not with every rerun).
OP_MAX_RENDERS = 3
# The stores one reader round trip covers.
TARGETS = ("tab", "device", "prefs")

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "components" / "device_store"
# sync() wraps the hidden iframes in st.container(key=f"{CONTAINER_KEY_PREFIX}-{key}"),
# which Streamlit renders with the CSS class "st-key-mc-device-store-<key>".
CONTAINER_KEY_PREFIX = "mc-device-store"
_HIDE_CSS = '<style>[class*="st-key-mc-device-store"]{display:none !important}</style>'
# session_state key holding a store's cached state: f"{STATE_KEY_PREFIX}{key}".
STATE_KEY_PREFIX = "_device_store_"

# Which part of a "set" op belongs to which target (merged per target when a
# newer save arrives before the older op has been sent three times).
_OP_FIELDS = {"tab": ("tab", "drop_tab"), "device": ("device", "drop_device"), "prefs": ("prefs",)}

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
    """Content hash of a payload, stable across dict key order. It covers the
    payload only, never the envelope's ``saved_at``."""
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


def timed_out(started: float, now: float | None = None, limit: float | None = None) -> bool:
    """True once a load that began at ``started`` (time.monotonic) has waited
    longer than ``limit`` (default LOAD_TIMEOUT_S)."""
    now = time.monotonic() if now is None else now
    return now - started > (LOAD_TIMEOUT_S if limit is None else limit)


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


def _defaults() -> dict:
    return {
        "status": "loading", "tab": None, "device": None, "prefs": {},
        "view_client": None, "narrow": None, "saved_at": None, "error": None,
        "targets": {t: "ok" for t in TARGETS},   # per store: "ok", "blocked" (read threw) or "failed" (write threw)
        "read_token": uuid.uuid4().hex, "started": time.monotonic(),
        "scope": uuid.uuid4().hex[:12],   # per-session id for the browser's dedupe marker
        "hashes": None,                   # per target: hash of what the browser holds now
        "device_on": False,               # this session wrote a device copy (so turning Remember me off removes it)
        "op": None,                       # queued write, sent for a few renders then dropped
        "published": False,               # narrow / view tabs were copied to session_state
        "forgot_pending": False,          # forget() ran before sync() this run (e.g. a callback)
        "run": None,                      # this run's writer slot + bookkeeping
    }


def _store(st, key: str) -> dict:
    name = STATE_KEY_PREFIX + key
    store = st.session_state.get(name)
    if not isinstance(store, dict) or "status" not in store:
        store = _defaults()
        st.session_state[name] = store
        return store
    for field, value in _defaults().items():   # a seeded or older dict gets what it lacks
        store.setdefault(field, value)
    if store["hashes"] is None:
        store["hashes"] = {t: (_hash_normalized(store[t]) if store.get(t) else None) for t in TARGETS}
    return store


def _public(store: dict) -> dict:
    return {
        "status": store["status"],
        "tab": _copy(store["tab"]),
        "device": _copy(store["device"]),
        "prefs": _copy(store["prefs"]) if store["prefs"] is not None else {},
        "view_client": _copy(store["view_client"]),
        "narrow": store["narrow"],
        "targets": dict(store["targets"]),
        "saved_at": store["saved_at"],
        "error": store["error"],
    }


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value)) if value is not None else None


def _set_unavailable(store: dict, error: str) -> None:
    store.update(status="unavailable", error=error, read_token=None)


def _view_client(value: Any) -> dict | None:
    """The page script's {scrollY, tabs} note, cleaned up (None if unusable)."""
    if not isinstance(value, dict):
        return None
    tabs = value.get("tabs")
    tabs = {str(g): lbl for g, lbl in tabs.items() if isinstance(lbl, str)} if isinstance(tabs, dict) else {}
    scroll = value.get("scrollY")
    scroll = int(scroll) if isinstance(scroll, (int, float)) and not isinstance(scroll, bool) else 0
    return {"scrollY": max(scroll, 0), "tabs": tabs}


def _prefs(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _consume_read(store: dict, value: dict) -> None:
    token = value.get("token")
    if store["status"] != "loading" or not token or token != store["read_token"]:
        return
    store["read_token"] = None
    targets, errors = {}, []
    for name in TARGETS:
        part = value.get(name)
        if isinstance(part, dict) and part.get("ok"):
            targets[name] = "ok"
        else:
            targets[name] = "blocked"
            errors.append(str(part.get("error")) if isinstance(part, dict) and part.get("error") else "")
    store["targets"] = targets
    if targets["tab"] != "ok" and targets["device"] != "ok":
        _set_unavailable(store, next((e for e in errors if e), str(value.get("error") or "storage unavailable")))
        return
    envs, payloads = {}, {}
    for name in ("tab", "device"):
        if targets[name] == "ok":
            envs[name] = _parse_envelope(value[name].get("raw"))
            payloads[name] = migrate(envs[name])
        else:
            payloads[name] = None
    prefs = _prefs(value["prefs"].get("raw")) if targets["prefs"] == "ok" else {}
    saved_at = next((envs[n].get("saved_at") for n in ("tab", "device") if payloads[n] is not None), None)
    narrow = value.get("narrow")
    store.update(
        status="ready", error=None, tab=payloads["tab"], device=payloads["device"], prefs=prefs,
        view_client=_view_client(value.get("view_client")),
        narrow=narrow if isinstance(narrow, bool) else None,
        saved_at=saved_at if isinstance(saved_at, str) else None,
        hashes={"tab": _hash_normalized(payloads["tab"]) if payloads["tab"] is not None else None,
                "device": _hash_normalized(payloads["device"]) if payloads["device"] is not None else None,
                "prefs": _hash_normalized(prefs) if prefs else None},
    )


def _consume(store: dict, value: Any) -> None:
    """Apply a value posted by the browser. Stale or repeated values are ignored,
    so a widget value that lingers across reruns is harmless."""
    if not isinstance(value, dict):
        return
    kind = value.get("kind")
    if kind == "read":
        _consume_read(store, value)
    elif kind == "write_error":
        op = store.get("op")
        target = value.get("target")
        if op and value.get("sig") == op.get("sig") and target in TARGETS:
            store["op"] = None
            store["targets"][target] = "failed"
            store["error"] = str(value.get("error") or "write failed")
            if all(store["targets"][t] != "ok" for t in ("tab", "device")):
                store["status"] = "unavailable"


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


def _note_render(store: dict) -> None:
    op = store["op"]
    op["renders"] = op.get("renders", 0) + 1


def _retire_spent_op(store: dict) -> None:
    """Drop a queued write that has been sent OP_MAX_RENDERS times. (Each run
    used to re-send the whole payload, 11 to 40 KB, for the life of the session.)"""
    op = store["op"]
    if op is not None and op.get("renders", 0) >= OP_MAX_RENDERS:
        store["op"] = None


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
    if run.get("counted") != op["sig"]:
        run["counted"] = op["sig"]
        _note_render(store)
    args = {k: v for k, v in op.items() if k != "renders"}
    with run["slot"] if run["slot"] is not None else contextlib.nullcontext():
        value = _component()(storage_key=key, op=args, scope=store["scope"], height=0,
                             key=wkey, default=None)
    _consume(store, value)


def _in_fragment() -> bool:
    ctx = _ctx()
    return ctx is not None and getattr(ctx, "current_fragment_id", None) is not None


def in_full_run(st, key: str = DEFAULT_KEY) -> bool:
    """True when sync() already ran in this script run (a full run, not a fragment-only rerun)."""
    return _live_run(_store(st, key)) is not None


def _render_writer_in_fragment(store: dict, key: str) -> None:
    """A fragment rerun does not run sync(), so the write goes out from a hidden iframe drawn in
    the fragment itself (the main run's slot is out of reach). The next full run sends it again."""
    op = store["op"]
    _note_render(store)
    args = {k: v for k, v in op.items() if k != "renders"}
    import streamlit as st
    with st.container(key=f"{CONTAINER_KEY_PREFIX}-{key}-frag"):
        _component()(storage_key=key, op=args, scope=store["scope"], height=0,
                     key=f"{STATE_KEY_PREFIX}{key}_wf_{op['sig']}", default=None)


def _publish(st, store: dict) -> None:
    """Hand the browser's viewport and open-tab notes to the app, once."""
    if store["published"] or store["status"] == "loading":
        return
    store["published"] = True
    if isinstance(store["narrow"], bool):
        st.session_state["_viewport_narrow"] = store["narrow"]
    view = store.get("view_client")
    if isinstance(view, dict) and view.get("tabs"):
        st.session_state["_view_tabs"] = dict(view["tabs"])


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def sync(st, key: str = DEFAULT_KEY) -> dict:
    """Render the hidden storage component (call exactly once per script run,
    first thing) and return the store's public state (see the module docstring).

    The loaded state is cached in ``st.session_state[STATE_KEY_PREFIX + key]``,
    so later runs never depend on the browser re-posting. A queued save or
    forget is re-sent for a few runs (so it survives an immediate st.rerun()),
    then dropped."""
    store = _store(st, key)
    ctx = _ctx()
    run = store["run"] = {
        "cursors": ctx.cursors if ctx is not None else None,
        "slot": None, "sig": None, "keys": set(),
        "forgot": bool(store["forgot_pending"]),
    }
    store["forgot_pending"] = False
    _retire_spent_op(store)
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
    if store["status"] == "loading" and timed_out(store["started"]):
        _set_unavailable(store, "timed out waiting for browser storage")
    _publish(st, store)
    return _public(store)


def _queue(store: dict, changes: dict) -> None:
    """Merge ``changes`` (a dict of op fields) into the queued write. An older op
    that has not been sent three times yet keeps the targets this one does not touch."""
    old = store["op"] if store["op"] and store["op"].get("kind") == "set" else {}
    op = {"kind": "set"}
    for fields in _OP_FIELDS.values():
        source = changes if any(f in changes for f in fields) else old
        for f in fields:
            if f in source:
                op[f] = source[f]
    op["sig"] = _hash_normalized({k: v for k, v in op.items() if k != "kind"})
    op["renders"] = 0
    store["op"] = op


def save(st, tab: dict | None, device: dict | None, prefs: dict | None = None,
         key: str = DEFAULT_KEY) -> None:
    """Save the tab copy, the device copy (``None`` removes it, once, if this
    session wrote one) and the display prefs to this browser, in this run.

    Only targets whose content hash changed are written, and each as its own
    browser item, so one write is small. A no-op unless status is "ready" (a
    save can never clobber stored data before it was loaded), for a target the
    browser refused, and after forget() earlier in the same run. Raises
    TypeError for a non-dict or non-JSON-serializable payload."""
    parts = {"tab": tab, "device": device, "prefs": prefs}
    for name, payload in parts.items():
        if payload is not None and not isinstance(payload, dict):
            raise TypeError(f"device_store.save() needs a dict {name} payload, got {type(payload).__name__}")
    normalized = {name: _normalize(p) if p is not None else None for name, p in parts.items()}
    store = _store(st, key)
    if store["status"] != "ready":
        return
    run = _live_run(store)
    if run is not None and run["forgot"]:
        return
    changes: dict = {}
    for name in TARGETS:
        if store["targets"].get(name) != "ok":
            continue
        value = normalized[name]
        if name == "device":
            if value is None:
                if store["device_on"]:           # Remember me was turned off: remove the copy, once
                    store["device_on"] = False
                    store["device"] = None
                    store["hashes"]["device"] = None
                    changes.update(device=None, drop_device=True)
                continue
            store["device_on"] = True
        if not value:
            continue
        digest = _hash_normalized(value)
        if digest == store["hashes"].get(name):
            continue
        if name == "prefs":
            raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        else:
            envelope = _envelope(value)
            raw = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)
        if len(raw.encode("utf-8")) > MAX_ITEM_BYTES:
            continue                              # never stored; the app trims optional parts first
        changes[name] = raw
        store["hashes"][name] = digest
        if name != "prefs":
            store[name] = value
            store["saved_at"] = envelope["saved_at"]
    if changes:
        _queue(store, changes)
    if store["op"] is not None and run is not None and run["sig"] != store["op"]["sig"]:
        _render_writer(store, key, run)
    elif store["op"] is not None and run is None and changes and _in_fragment():
        _render_writer_in_fragment(store, key)


def drop_tab(st, key: str = DEFAULT_KEY) -> None:
    """Remove this tab's saved copy (a copy that could not be restored). A save
    later in the run writes a fresh one over it."""
    store = _store(st, key)
    if store["status"] != "ready" or store["targets"].get("tab") != "ok":
        return
    store["tab"] = None
    store["hashes"]["tab"] = None
    _queue(store, {"drop_tab": True})
    run = _live_run(store)
    if run is not None and run["sig"] != store["op"]["sig"]:
        _render_writer(store, key, run)


def forget(st, key: str = DEFAULT_KEY) -> None:
    """Remove the saved inputs (tab copy, device copy and view note) from this
    browser and reset the cached state to ready / no data (stays "unavailable"
    if storage is unavailable). Any save() later in the same run is ignored;
    turn your "remember" setting off too, or the next run will save again."""
    store = _store(st, key)
    store["op"] = {"kind": "remove", "sig": "rm-" + uuid.uuid4().hex[:12], "renders": 0}
    store["read_token"] = None
    if store["status"] != "unavailable":
        store.update(status="ready", error=None)
    store.update(tab=None, device=None, saved_at=None, device_on=False)
    store["hashes"].update(tab=None, device=None)
    run = _live_run(store)
    if run is None:
        store["forgot_pending"] = True  # sync() renders the removal and blocks saves this run
        return
    run["forgot"] = True
    _render_writer(store, key, run)
