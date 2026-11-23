"""Tests for ui/utils/device_store.py, the private on-device (localStorage) store.

Covers the pure envelope/migrate/hash helpers, the component's static frontend
(protocol strings present; no network APIs), the Python state machine driven by
simulated browser posts, and an AppTest smoke run of sync/save/forget.
The real browser round trip (localStorage, reloads, server restart) is
verified separately with Playwright/WebKit; it can't run in pytest here.
"""
import json
import os
import re
import sys
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
if _UI not in sys.path:
    sys.path.insert(0, _UI)

import pytest

from utils import device_store as ds

PAYLOAD = {"mode": "simple", "inputs": {"age": 34, "income": 180000.0, "kids": [1, 2]},
           "profile": '{"version": 3}'}


# --------------------------------------------------------------------------
# Envelope + migrate
# --------------------------------------------------------------------------

class TestEnvelope:
    def test_round_trip_through_json(self):
        env = ds.make_envelope(PAYLOAD)
        assert env["schema"] == 1 == ds.SCHEMA_VERSION
        assert env["payload"] == PAYLOAD
        assert ds.migrate(json.dumps(env)) == PAYLOAD   # as stored (string)
        assert ds.migrate(env) == PAYLOAD               # already parsed

    def test_saved_at_is_iso_utc(self):
        saved_at = ds.make_envelope(PAYLOAD)["saved_at"]
        assert saved_at.endswith("Z")
        parsed = datetime.fromisoformat(saved_at.replace("Z", "+00:00"))
        assert parsed.utcoffset().total_seconds() == 0

    def test_envelope_payload_is_a_copy(self):
        src = {"inputs": {"age": 30}}
        env = ds.make_envelope(src)
        src["inputs"]["age"] = 99
        assert env["payload"]["inputs"]["age"] == 30

    def test_non_json_payload_raises(self):
        with pytest.raises(TypeError):
            ds.make_envelope({"when": datetime.now()})


class TestMigrate:
    def test_schema_1_ok(self):
        assert ds.migrate({"schema": 1, "saved_at": "2026-01-01T00:00:00Z", "payload": {"a": 1}}) == {"a": 1}

    def test_saved_at_is_optional(self):
        assert ds.migrate({"schema": 1, "payload": {"a": 1}}) == {"a": 1}

    @pytest.mark.parametrize("schema", [0, 2, 99, -1, "1", 1.0, True, None])
    def test_unknown_or_newer_schema_returns_none(self, schema):
        assert ds.migrate({"schema": schema, "saved_at": "x", "payload": {"a": 1}}) is None

    @pytest.mark.parametrize("env", [
        {"saved_at": "x", "payload": {"a": 1}},          # no schema
        {"schema": 1, "saved_at": "x"},                  # no payload
        {"schema": 1, "payload": None},
        {"schema": 1, "payload": ["not", "a", "dict"]},
        {"schema": 1, "payload": "string"},
        {},
    ])
    def test_missing_or_bad_fields_return_none(self, env):
        assert ds.migrate(env) is None

    @pytest.mark.parametrize("raw", ["{not json", "", "null", "42", "[1, 2]", '"str"',
                                     None, 42, [1], b"\xff\xfe", object()])
    def test_corrupt_input_returns_none(self, raw):
        assert ds.migrate(raw) is None


class TestPayloadHash:
    def test_changes_when_payload_changes(self):
        a = ds.payload_hash(PAYLOAD)
        changed = json.loads(json.dumps(PAYLOAD))
        changed["inputs"]["age"] = 35
        assert ds.payload_hash(changed) != a
        assert ds.payload_hash({**PAYLOAD, "mode": "advanced"}) != a

    def test_stable_across_key_order(self):
        reordered = {"profile": PAYLOAD["profile"],
                     "inputs": {"kids": [1, 2], "income": 180000.0, "age": 34},
                     "mode": "simple"}
        assert ds.payload_hash(reordered) == ds.payload_hash(PAYLOAD)

    def test_list_order_matters(self):
        assert ds.payload_hash({"k": [1, 2]}) != ds.payload_hash({"k": [2, 1]})

    def test_hash_matches_what_a_reload_returns(self):
        # int dict keys come back from JSON as strings; same content, same hash.
        assert ds.payload_hash({"comp": {34: 1}}) == ds.payload_hash({"comp": {"34": 1}})


# --------------------------------------------------------------------------
# Component frontend (static index.html)
# --------------------------------------------------------------------------

class TestComponentFiles:
    def _html(self):
        return (ds.COMPONENT_DIR / "index.html").read_text(encoding="utf-8")

    def test_component_dir_exists(self):
        assert ds.COMPONENT_DIR.is_dir()
        assert (ds.COMPONENT_DIR / "index.html").is_file()

    def test_index_html_speaks_the_component_protocol(self):
        html = self._html()
        for needle in ("streamlit:componentReady", "apiVersion: 1", "streamlit:render",
                       "streamlit:setComponentValue", 'dataType: "json"',
                       "streamlit:setFrameHeight", "isStreamlitMessage", "localStorage", "sessionStorage",
                       "retpy-prefs", "mcView", "matchMedia", "write_error", "drop_device"):
            assert needle in html, needle

    def test_index_html_has_no_network_channel(self):
        html = self._html()
        for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "EventSource",
                       "importScripts", "<img", "<link", "src="):
            assert banned not in html, banned
        assert not re.search(r"https?://", html)

    def test_python_module_writes_no_files_and_logs_nothing(self):
        src = open(ds.__file__, encoding="utf-8").read()
        for banned in ("import logging", "print(", "open(", "requests", "urllib", "socket"):
            assert banned not in src, banned


# --------------------------------------------------------------------------
# State machine (simulated browser posts, no Streamlit runtime)
# --------------------------------------------------------------------------

class _FakeSt:
    def __init__(self):
        self.session_state = {}


def _fresh():
    st = _FakeSt()
    return st, ds._store(st, ds.DEFAULT_KEY)


def _target(raw=None, ok=True, error="SecurityError"):
    if not ok:
        return {"ok": False, "error": error}
    return {"ok": True, "raw": raw}


def _read_post(store, tab=None, device=None, prefs=None, token=None, view_client=None, narrow=None,
               tab_ok=True, device_ok=True, prefs_ok=True):
    """What the reader iframe posts. tab/device are envelope dicts or JSON strings or None."""
    def raw(v):
        return json.dumps(v) if isinstance(v, (dict, list)) else v
    msg = {"kind": "read", "token": token or store["read_token"],
           "tab": _target(raw(tab), tab_ok), "device": _target(raw(device), device_ok),
           "prefs": _target(raw(prefs), prefs_ok), "view_client": view_client, "narrow": narrow}
    msg["ok"] = bool(tab_ok or device_ok)
    if not msg["ok"]:
        msg["error"] = "SecurityError"
    return msg


class TestStateMachine:
    def test_fresh_session_is_loading_and_save_cannot_clobber(self):
        st, store = _fresh()
        assert ds._public(store)["status"] == "loading"
        ds.save(st, PAYLOAD, PAYLOAD, {"theme_mode": "x"})
        assert store["op"] is None

    def test_read_message_carries_tab_device_prefs_view_and_narrow(self):
        _, store = _fresh()
        tab_env, dev_env = ds.make_envelope(PAYLOAD), ds.make_envelope({**PAYLOAD, "mode": "full"})
        view = {"scrollY": 480, "tabs": {"mc-tile-deepdives": "Sensitivity"}}
        ds._consume(store, _read_post(store, tab=tab_env, device=dev_env,
                                      prefs={"theme_mode": "Dark", "n_simulations": 5000},
                                      view_client=view, narrow=True))
        state = ds._public(store)
        assert state["status"] == "ready" and state["error"] is None
        assert state["tab"] == PAYLOAD
        assert state["device"] == {**PAYLOAD, "mode": "full"}
        assert state["prefs"] == {"theme_mode": "Dark", "n_simulations": 5000}
        assert state["view_client"] == view
        assert state["narrow"] is True
        assert state["targets"] == {"tab": "ok", "device": "ok", "prefs": "ok"}
        assert state["saved_at"] == tab_env["saved_at"]
        assert store["read_token"] is None

    def test_read_with_nothing_saved_is_ready_with_no_data(self):
        _, store = _fresh()
        ds._consume(store, _read_post(store))
        state = ds._public(store)
        assert state["status"] == "ready"
        assert state["tab"] is None and state["device"] is None and state["prefs"] == {}

    def test_corrupt_or_newer_stored_value_is_ignored_per_target(self):
        for raw in ("{oops", json.dumps({"schema": 7, "payload": {"a": 1}})):
            _, store = _fresh()
            ds._consume(store, _read_post(store, tab=raw, device=ds.make_envelope(PAYLOAD), prefs="not json"))
            assert store["status"] == "ready"
            assert store["tab"] is None and store["device"] == PAYLOAD and store["prefs"] == {}

    def test_one_blocked_target_does_not_block_the_others(self):
        _, store = _fresh()
        ds._consume(store, _read_post(store, tab_ok=False, device=ds.make_envelope(PAYLOAD)))
        assert store["status"] == "ready"
        assert store["targets"] == {"tab": "blocked", "device": "ok", "prefs": "ok"}
        assert store["device"] == PAYLOAD

    def test_all_storage_blocked_is_unavailable_and_blocks_save(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store, tab_ok=False, device_ok=False, prefs_ok=False))
        assert store["status"] == "unavailable"
        assert store["error"] == "SecurityError"
        ds.save(st, PAYLOAD, PAYLOAD)
        assert store["op"] is None

    def test_stale_or_repeated_posts_are_ignored(self):
        _, store = _fresh()
        ds._consume(store, _read_post(store, token="someone-else"))
        assert store["status"] == "loading"
        good = _read_post(store)
        ds._consume(store, good)
        ds._consume(store, _read_post(store, tab=ds.make_envelope(PAYLOAD), token=good["token"]))
        assert store["tab"] is None
        for junk in (None, "x", 3, {"kind": "nope"}, {}):
            ds._consume(store, junk)
        assert store["status"] == "ready"

    def test_save_queues_only_the_targets_whose_hash_changed(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store))
        ds.save(st, PAYLOAD, None, {"theme_mode": "Dark"})
        op = store["op"]
        assert op["kind"] == "set"
        assert set(op) >= {"sig", "tab", "prefs"} and "device" not in op
        env = json.loads(op["tab"])
        assert set(env) == {"schema", "saved_at", "payload"} and env["schema"] == 1
        assert ds.migrate(op["tab"]) == PAYLOAD
        assert json.loads(op["prefs"]) == {"theme_mode": "Dark"}
        same = store["op"]
        ds.save(st, dict(reversed(list(PAYLOAD.items()))), None, {"theme_mode": "Dark"})   # same content
        assert store["op"] is same
        ds.save(st, {**PAYLOAD, "mode": "full"}, None, {"theme_mode": "Dark"})
        assert set(store["op"]) >= {"tab", "prefs"}                 # unwritten older targets ride along
        assert ds.migrate(store["op"]["tab"])["mode"] == "full"
        assert store["op"]["sig"] != op["sig"]

    def test_resaving_what_was_loaded_writes_nothing(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store, tab=ds.make_envelope(PAYLOAD), device=ds.make_envelope(PAYLOAD),
                                      prefs={"a": 1}))
        ds.save(st, PAYLOAD, PAYLOAD, {"a": 1})
        assert store["op"] is None

    def test_hashes_have_no_timestamps(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store))
        ds.save(st, PAYLOAD, None)
        first = dict(store["hashes"])
        store["op"] = None
        ds.save(st, PAYLOAD, None)
        assert store["op"] is None and store["hashes"] == first

    def test_op_is_retired_after_three_renders(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store))
        ds.save(st, PAYLOAD, None)
        assert store["op"]["renders"] == 0
        for expected in (1, 2, 3):
            ds._note_render(store)
            assert store["op"]["renders"] == expected
        ds._retire_spent_op(store)
        assert store["op"] is None
        ds.save(st, PAYLOAD, None)                       # unchanged: not queued again
        assert store["op"] is None

    def test_toggle_off_drops_the_device_copy_once(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store))
        ds.save(st, PAYLOAD, PAYLOAD)
        assert "device" in store["op"] and not store["op"].get("drop_device")
        store["op"] = None
        ds.save(st, PAYLOAD, None)                       # Remember me turned off
        op = store["op"]
        assert op["drop_device"] is True and op["device"] is None and "tab" not in op
        store["op"] = None
        ds.save(st, PAYLOAD, None)                       # and only once
        assert store["op"] is None

    def test_a_device_copy_this_session_never_wrote_is_left_alone(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store, device=ds.make_envelope(PAYLOAD)))
        ds.save(st, PAYLOAD, None)
        assert store["op"] is None or not store["op"].get("drop_device")

    def test_over_the_cap_is_never_written(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store))
        ds.save(st, {"blob": "x" * (ds.MAX_ITEM_BYTES + 10)}, None)
        assert store["op"] is None

    def test_forget_resets_to_ready_none_and_queues_removal(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store, tab=ds.make_envelope(PAYLOAD), device=ds.make_envelope(PAYLOAD)))
        ds.forget(st)
        state = ds._public(store)
        assert state["status"] == "ready" and state["tab"] is None and state["device"] is None
        assert store["op"]["kind"] == "remove"
        assert store["forgot_pending"] is True   # outside a run: sync() applies it
        ds.save(st, PAYLOAD, None)                # a later run may save again (no live run here)
        assert store["op"]["kind"] == "set"

    def test_forget_while_loading_cancels_the_read(self):
        st, store = _fresh()
        token = store["read_token"]
        ds.forget(st)
        ds._consume(store, _read_post(store, tab=ds.make_envelope(PAYLOAD), token=token))
        assert (store["status"], store["tab"]) == ("ready", None)

    def test_write_error_marks_only_that_target(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store))
        ds.save(st, PAYLOAD, PAYLOAD)
        ds._consume(store, {"kind": "write_error", "sig": "other", "target": "tab", "error": "x"})
        assert store["targets"]["tab"] == "ok"
        ds._consume(store, {"kind": "write_error", "sig": store["op"]["sig"], "target": "device",
                            "error": "QuotaExceededError"})
        assert store["status"] == "ready"
        assert store["targets"] == {"tab": "ok", "device": "failed", "prefs": "ok"}
        assert store["error"] == "QuotaExceededError"
        ds._consume(store, {"kind": "write_error", "sig": (store["op"] or {}).get("sig", "none"),
                            "target": "tab", "error": "QuotaExceededError"})

    def test_a_failed_target_is_not_written_again(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store))
        ds.save(st, PAYLOAD, None)
        ds._consume(store, {"kind": "write_error", "sig": store["op"]["sig"], "target": "tab", "error": "x"})
        ds.save(st, {**PAYLOAD, "mode": "full"}, None)
        assert store["op"] is None or "tab" not in store["op"]

    def test_save_rejects_non_dict(self):
        st, _ = _fresh()
        with pytest.raises(TypeError):
            ds.save(st, ["not", "a", "dict"], None)

    def test_public_state_is_a_copy(self):
        _, store = _fresh()
        ds._consume(store, _read_post(store, tab=ds.make_envelope(PAYLOAD)))
        ds._public(store)["tab"]["mode"] = "mutated"
        assert store["tab"]["mode"] == "simple"

    def test_store_dict_seeded_by_a_test_gets_its_missing_fields(self):
        st = _FakeSt()
        st.session_state[ds.STATE_KEY_PREFIX + ds.DEFAULT_KEY] = {"status": "ready", "tab": PAYLOAD}
        store = ds._store(st, ds.DEFAULT_KEY)
        assert store["op"] is None and store["hashes"] and store["targets"]
        assert ds._public(store)["tab"] == PAYLOAD


class TestLoadTimeout:
    def test_timeout_is_four_seconds(self):
        assert ds.LOAD_TIMEOUT_S == 4.0

    def test_pure_timeout_check(self):
        assert ds.timed_out(started=100.0, now=103.9) is False
        assert ds.timed_out(started=100.0, now=104.1) is True
        assert ds.timed_out(started=100.0, now=106.0, limit=10.0) is False


# --------------------------------------------------------------------------
# AppTest smoke run (real ScriptRunner; the browser side is not simulated)
# --------------------------------------------------------------------------

_SCRIPT = f"""
import sys
sys.path.insert(0, {_UI!r})
import streamlit as st
from utils import device_store
state = device_store.sync(st)
st.write("STATUS", state["status"])
device_store.save(st, {{"a": 1}}, None)
if st.button("forget"):
    device_store.forget(st)
    device_store.save(st, {{"a": 2}}, None)   # ignored: forget wins for the rest of the run
"""


def test_apptest_sync_save_forget_smoke(tmp_path):
    from streamlit.testing.v1 import AppTest

    script = tmp_path / "ds_app.py"
    script.write_text(_SCRIPT)
    at = AppTest.from_file(str(script)).run()
    assert not at.exception
    assert at.markdown[0].value == "STATUS loading"
    store = at.session_state[ds.STATE_KEY_PREFIX + ds.DEFAULT_KEY]
    assert store["op"] is None                      # save() was a no-op while loading
    at.button[0].click().run()
    assert not at.exception
    store = at.session_state[ds.STATE_KEY_PREFIX + ds.DEFAULT_KEY]
    assert store["status"] == "ready" and store["op"]["kind"] == "remove"
    at.run()                                       # next run: forget no longer blocks saves
    store = at.session_state[ds.STATE_KEY_PREFIX + ds.DEFAULT_KEY]
    assert not at.exception and store["op"]["kind"] == "set"
