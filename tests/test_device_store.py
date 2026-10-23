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
                       "streamlit:setFrameHeight", "isStreamlitMessage", "localStorage"):
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


def _read_post(store, raw, ok=True, token=None):
    msg = {"kind": "read", "token": token or store["read_token"], "ok": ok}
    msg.update({"raw": raw} if ok else {"error": "SecurityError"})
    return msg


class TestStateMachine:
    def test_fresh_session_is_loading_and_save_cannot_clobber(self):
        st, store = _fresh()
        assert ds._public(store)["status"] == "loading"
        ds.save(st, PAYLOAD)
        assert store["op"] is None

    def test_read_with_saved_envelope_becomes_ready(self):
        _, store = _fresh()
        env = ds.make_envelope(PAYLOAD)
        ds._consume(store, _read_post(store, json.dumps(env)))
        state = ds._public(store)
        assert state == {"status": "ready", "data": PAYLOAD, "saved_at": env["saved_at"], "error": None}
        assert store["read_token"] is None

    def test_read_with_nothing_saved_is_ready_none(self):
        _, store = _fresh()
        ds._consume(store, _read_post(store, None))
        assert ds._public(store)["status"] == "ready"
        assert ds._public(store)["data"] is None

    def test_corrupt_or_newer_stored_value_is_ready_none(self):
        for raw in ("{oops", json.dumps({"schema": 7, "payload": {"a": 1}})):
            _, store = _fresh()
            ds._consume(store, _read_post(store, raw))
            assert (store["status"], store["data"]) == ("ready", None)

    def test_storage_error_is_unavailable_and_blocks_save(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store, None, ok=False))
        assert store["status"] == "unavailable"
        assert store["error"] == "SecurityError"
        ds.save(st, PAYLOAD)
        assert store["op"] is None

    def test_stale_or_repeated_posts_are_ignored(self):
        _, store = _fresh()
        ds._consume(store, _read_post(store, None, token="someone-else"))
        assert store["status"] == "loading"
        good = _read_post(store, None)
        ds._consume(store, good)
        ds._consume(store, _read_post(store, json.dumps(ds.make_envelope(PAYLOAD)), token=good["token"]))
        assert (store["status"], store["data"]) == ("ready", None)
        for junk in (None, "x", 3, {"kind": "nope"}, {}):
            ds._consume(store, junk)
        assert store["status"] == "ready"

    def test_save_queues_versioned_envelope_and_dedupes_by_hash(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store, None))
        ds.save(st, PAYLOAD)
        op = store["op"]
        assert op["kind"] == "set" and op["sig"] == ds.payload_hash(PAYLOAD)
        env = json.loads(op["value"])
        assert set(env) == {"schema", "saved_at", "payload"} and env["schema"] == 1
        assert ds.migrate(op["value"]) == PAYLOAD
        assert ds._public(store)["data"] == PAYLOAD
        ds.save(st, dict(reversed(list(PAYLOAD.items()))))  # same content
        assert store["op"] is op
        ds.save(st, {**PAYLOAD, "mode": "advanced"})
        assert store["op"]["sig"] != op["sig"]

    def test_resaving_what_was_loaded_writes_nothing(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store, json.dumps(ds.make_envelope(PAYLOAD))))
        ds.save(st, PAYLOAD)
        assert store["op"] is None

    def test_forget_resets_to_ready_none_and_queues_removal(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store, json.dumps(ds.make_envelope(PAYLOAD))))
        ds.forget(st)
        assert ds._public(store) == {"status": "ready", "data": None, "saved_at": None, "error": None}
        assert store["op"]["kind"] == "remove"
        assert store["forgot_pending"] is True   # outside a run: sync() will apply it
        ds.save(st, PAYLOAD)                      # a later run may save again (no live run here)
        assert store["op"]["kind"] == "set"

    def test_forget_while_loading_cancels_the_read(self):
        st, store = _fresh()
        token = store["read_token"]
        ds.forget(st)
        ds._consume(store, _read_post(store, json.dumps(ds.make_envelope(PAYLOAD)), token=token))
        assert (store["status"], store["data"]) == ("ready", None)

    def test_write_error_marks_unavailable(self):
        st, store = _fresh()
        ds._consume(store, _read_post(store, None))
        ds.save(st, PAYLOAD)
        ds._consume(store, {"kind": "write_error", "sig": "other", "error": "x"})
        assert store["status"] == "ready"
        ds._consume(store, {"kind": "write_error", "sig": store["op"]["sig"], "error": "QuotaExceededError"})
        assert (store["status"], store["error"], store["op"]) == ("unavailable", "QuotaExceededError", None)

    def test_save_rejects_non_dict(self):
        st, _ = _fresh()
        with pytest.raises(TypeError):
            ds.save(st, ["not", "a", "dict"])

    def test_public_state_is_a_copy(self):
        _, store = _fresh()
        ds._consume(store, _read_post(store, json.dumps(ds.make_envelope(PAYLOAD))))
        ds._public(store)["data"]["mode"] = "mutated"
        assert store["data"]["mode"] == "simple"


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
device_store.save(st, {{"a": 1}})
if st.button("forget"):
    device_store.forget(st)
    device_store.save(st, {{"a": 2}})   # ignored: forget wins for the rest of the run
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
