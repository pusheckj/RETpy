"""session_wake against Streamlit's real Runtime, with no sockets.

A small script runs in a real session (Runtime, AppSession, ScriptRunner). A fake
browser sends the visitor's edits as ``rerun_script`` messages. The waker asks for a
rerun at about the same moment. Whatever the order, the last edit must be the value
the script sees in its last run, and every finished job must be picked up."""
import asyncio
import os
import random
import sys
import tempfile
import time
import types

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from streamlit.proto.BackMsg_pb2 import BackMsg  # noqa: E402
from streamlit.proto.ClientState_pb2 import ClientState  # noqa: E402
from streamlit.runtime import Runtime, RuntimeConfig  # noqa: E402
from streamlit.runtime.caching.storage.dummy_cache_storage import MemoryCacheStorageManager  # noqa: E402
from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage  # noqa: E402
from streamlit.runtime.memory_session_storage import MemorySessionStorage  # noqa: E402
from streamlit.runtime.memory_uploaded_file_manager import MemoryUploadedFileManager  # noqa: E402

SCRIPT = '''
import os, sys, time, random, types
import streamlit as st
sys.path[:0] = [{ui!r}]
from utils import session_wake
import s3b_state as S

def new_handle():
    h = types.SimpleNamespace(done=False, dropped=False)
    h.ready = lambda: h.done and not h.dropped
    return h

with session_wake.running(st):
    h = S.handle
    if h is not None and h.done and not h.dropped:      # what _drain_extras does
        h.dropped = True
        S.drained += 1
    time.sleep(S.script_ms / 1000)
    n = st.number_input("n", key="n", value=0)
    with open(S.log, "a") as f:
        f.write(f"{{int(n)}}\\n")
    w = session_wake.get(st, delay=0.0, retry=0.01)
    if w is not None and not st.session_state.get("armed"):
        st.session_state["armed"] = True
        S.waker = w
        S.new_handle = new_handle
    st.text(f"N={{int(n)}}")
'''


class Client:
    """The browser's end of the session: keeps the number input's widget id."""

    def __init__(self):
        self.msgs, self.wid, self.finished = [], None, 0

    def write_forward_msg(self, msg):
        self.msgs.append(msg)
        kind = msg.WhichOneof("type")
        if kind == "delta" and msg.delta.WhichOneof("type") == "new_element":
            el = msg.delta.new_element
            if el.WhichOneof("type") == "number_input":
                self.wid = el.number_input.id
        if kind == "script_finished":
            self.finished += 1


async def _settle(client, quiet=0.4, limit=20):
    last, t_last, t_end = (client.finished, len(client.msgs)), time.time(), time.time() + limit
    while time.time() < t_end:
        await asyncio.sleep(0.05)
        cur = (client.finished, len(client.msgs))
        if cur != last:
            last, t_last = cur, time.time()
        elif time.time() - t_last > quiet:
            return True
    return False


def _edit(wid, v):
    cs = ClientState()
    w = cs.widget_states.widgets.add()
    w.id, w.int_value = wid, v
    return BackMsg(rerun_script=cs)


async def _trials(tmp, n, naive=False):
    state = types.ModuleType("s3b_state")
    state.log, state.script_ms, state.waker, state.handle, state.drained = os.path.join(tmp, "runs.log"), 20, None, None, 0
    sys.modules["s3b_state"] = state
    path = os.path.join(tmp, "script.py")
    with open(path, "w") as f:
        f.write(SCRIPT.format(ui=UI))
    Runtime._instance = None
    rt = Runtime(RuntimeConfig(script_path=path, command_line=None, media_file_storage=MemoryMediaFileStorage("/media"),
                               uploaded_file_manager=MemoryUploadedFileManager("/up"),
                               cache_storage_manager=MemoryCacheStorageManager(),
                               session_storage=MemorySessionStorage(ttl_seconds=60)))
    await rt.start()
    try:
        client = Client()
        sid = rt.connect_session(client=client, user_info={})
        rt.handle_backmsg(sid, BackMsg(rerun_script=ClientState()))
        await _settle(client)
        assert state.waker is not None, "make_waker found no session"
        if naive:       # control: a rerun that replaces the running one and brings no widget state
            sess = rt._session_mgr.get_active_session_info(sid).session
            loop = asyncio.get_running_loop()
            state.waker.request = lambda: loop.call_soon_threadsafe(sess.request_rerun, None)
        rnd, lost = random.Random(7), []
        for k in range(n):
            v = 1000 + k
            state.script_ms = rnd.choice([5, 20, 60, 120])
            state.handle = state.new_handle()
            state.waker.watch(state.handle)
            delta = rnd.uniform(-0.06, 0.12)            # the edit, relative to the wake-up

            async def push():
                state.handle.done = True
                state.waker.poke()
            if delta >= 0:
                asyncio.ensure_future(push())
                await asyncio.sleep(delta)
                rt.handle_backmsg(sid, _edit(client.wid, v))
            else:
                rt.handle_backmsg(sid, _edit(client.wid, v))
                await asyncio.sleep(-delta)
                await push()
            await _settle(client)
            runs = open(state.log).read().split()
            if not runs or runs[-1] != str(v):
                lost.append((k, v, runs[-4:], round(delta, 3)))
        return lost, state.drained
    finally:
        rt.stop()
        Runtime._instance = None
        sys.modules.pop("s3b_state", None)


def test_a_wake_up_rerun_never_loses_the_visitors_edit(tmp_path):
    """Edits and wake-ups land in every order, within about 0.1 s of each other, while the script
    takes 5 to 120 ms to run. Each edit is the last thing sent: the script's final run must have it,
    and each finished job must have been picked up by a run."""
    lost, drained = asyncio.run(_trials(str(tmp_path), 20))
    assert lost == []
    assert drained == 20


# ---------------------------------------------------------------------------------------------
# A wake-up must never interrupt a run the visitor started. The wake-up request carries no
# widget state, so a run it stops loses the click (or the not-yet-drawn edit) that run holds.
# The ``running`` flag cannot cover this: it is only set inside ``with running(st)``, not in
# module-level code, not while waiting for a lock, and not in a fragment run.

CLICK_SCRIPT = '''
import os, sys, time, types
import streamlit as st
sys.path[:0] = [{ui!r}]
from utils import session_wake
import s3c_state as S

def note(text):
    with open(S.log, "a") as f:
        f.write(text + "\\n")

time.sleep(S.pre_ms / 1000)                     # module-level phase: outside running()
go = st.button("go", key="go")
n = st.number_input("n", key="n", value=0)
if go:
    note("click")
note("n=%d" % int(n))
with session_wake.running(st):
    h = S.handle
    # a run that holds a click leaves the finished job for the wake-up (it must come back for it)
    if h is not None and h.done and not h.dropped and not go:
        h.dropped = True
        S.drained += 1
    w = session_wake.get(st, delay=0.0, retry=0.01)
    if w is not None and not st.session_state.get("armed"):
        st.session_state["armed"] = True
        S.waker = w

@st.fragment
def frag():
    time.sleep(S.frag_ms / 1000)
    if st.button("fb", key="fb"):
        note("fragclick")

frag()
'''


class _Client2(Client):
    def __init__(self):
        super().__init__()
        self.ids, self.frag_id = {}, None

    def write_forward_msg(self, msg):
        super().write_forward_msg(msg)
        if msg.WhichOneof("type") == "delta" and msg.delta.WhichOneof("type") == "new_element":
            el = msg.delta.new_element
            kind = el.WhichOneof("type")
            if kind == "button":
                self.ids[el.button.label] = el.button.id
                if el.button.label == "fb":
                    self.frag_id = msg.delta.fragment_id
            elif kind == "number_input":
                self.ids["n"] = el.number_input.id


def _click(wid, fragment_id=""):
    cs = ClientState()
    w = cs.widget_states.widgets.add()
    w.id, w.trigger_value = wid, True
    if fragment_id:
        cs.fragment_id = fragment_id
    return BackMsg(rerun_script=cs)


async def _with_session(tmp, body):
    state = types.ModuleType("s3c_state")
    state.log, state.pre_ms, state.frag_ms = os.path.join(tmp, "runs.log"), 0, 0
    state.waker, state.handle, state.drained = None, None, 0
    sys.modules["s3c_state"] = state
    path = os.path.join(tmp, "script.py")
    with open(path, "w") as f:
        f.write(CLICK_SCRIPT.format(ui=UI))
    Runtime._instance = None
    rt = Runtime(RuntimeConfig(script_path=path, command_line=None, media_file_storage=MemoryMediaFileStorage("/media"),
                               uploaded_file_manager=MemoryUploadedFileManager("/up"),
                               cache_storage_manager=MemoryCacheStorageManager(),
                               session_storage=MemorySessionStorage(ttl_seconds=60)))
    await rt.start()
    try:
        client = _Client2()
        sid = rt.connect_session(client=client, user_info={})
        rt.handle_backmsg(sid, BackMsg(rerun_script=ClientState()))
        await _settle(client)
        assert state.waker is not None, "make_waker found no session"
        return await body(rt, sid, client, state)
    finally:
        rt.stop()
        Runtime._instance = None
        sys.modules.pop("s3c_state", None)


def _log(state):
    with open(state.log) as f:
        return f.read().split()


def _arm_job(state):
    h = types.SimpleNamespace(done=False, dropped=False)
    h.ready = lambda: h.done and not h.dropped
    state.handle = h
    state.waker.watch(h)
    return h


def test_a_wake_up_does_not_eat_a_click_in_the_module_level_phase(tmp_path):
    """The visitor's click starts a run that spends 300 ms before its first Streamlit call. A job
    finishes during that time. The click must reach the script, and the job must still be picked up
    afterwards by a later run."""
    async def body(rt, sid, client, state):
        lost = []
        for k in range(4):
            before = _log(state).count("click")
            state.pre_ms = 300
            h = _arm_job(state)
            rt.handle_backmsg(sid, _click(client.ids["go"]))
            await asyncio.sleep(0.1)
            h.done = True
            state.waker.poke()                      # delay 0: the wake-up lands mid-phase
            await _settle(client, quiet=0.8)
            state.pre_ms = 0
            if _log(state).count("click") != before + 1:
                lost.append(k)
        return lost, state.drained

    lost, drained = asyncio.run(_with_session(str(tmp_path), body))
    assert lost == []
    assert drained == 4, "the finished jobs must be picked up by the wake-up that comes back"


def test_a_wake_up_does_not_eat_a_click_inside_a_fragment(tmp_path):
    """A button inside an st.fragment starts a fragment run that takes 300 ms. A job finishes
    meanwhile. The fragment's click must be seen, and the job must be picked up afterwards."""
    async def body(rt, sid, client, state):
        assert client.frag_id, "the fragment's id was not seen"
        lost = []
        for k in range(4):
            before = _log(state).count("fragclick")
            state.frag_ms = 300
            h = _arm_job(state)
            rt.handle_backmsg(sid, _click(client.ids["fb"], client.frag_id))
            await asyncio.sleep(0.1)
            h.done = True
            state.waker.poke()
            await _settle(client, quiet=0.8)
            state.frag_ms = 0
            if _log(state).count("fragclick") != before + 1:
                lost.append(k)
        return lost, state.drained

    lost, drained = asyncio.run(_with_session(str(tmp_path), body))
    assert lost == []
    assert drained == 4


def test_a_wake_up_does_not_eat_an_edit_in_the_module_level_phase(tmp_path):
    """Same as the click test, for a number-input edit that the run has not drawn yet."""
    async def body(rt, sid, client, state):
        lost = []
        for k in range(4):
            v = 500 + k
            state.pre_ms = 300
            h = _arm_job(state)
            rt.handle_backmsg(sid, _edit(client.ids["n"], v))
            await asyncio.sleep(0.1)
            h.done = True
            state.waker.poke()
            await _settle(client, quiet=0.8)
            state.pre_ms = 0
            if f"n={v}" not in _log(state):
                lost.append(k)
        return lost

    assert asyncio.run(_with_session(str(tmp_path), body)) == []
