"""Ask Streamlit to rerun one visitor's script when background work has finished.

The follow-up analyses run in a process pool (``sim_runner.submit_plan_bg``). The
page needs one more rerun when they are done, so it can draw them. A timer in the
browser could ask for that rerun, but every tick is a full rerun request (the whole
widget state, about 13 KB) and a script run, many times per analysis. Here the
server asks for the rerun itself, once, when something is ready.

The request is the same one ``st.rerun()`` makes: no widget state of its own. It goes
to the session's running script runner when there is one, which merges it with any
edit of the visitor's that is still waiting, so no edit is lost. It starts a new
runner only when the script is idle.

This uses Streamlit's session object, which has no public handle. When it cannot be
reached (another Streamlit version, a test), ``make_waker`` returns None and the app
runs the follow-ups on the script thread as before.
"""
from __future__ import annotations

import contextlib
import dataclasses
import logging
import threading
import time
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)

KEY = "_wake"
WAKE_DELAY_S = 1.0     # results that arrive within this long of each other share one rerun
MAX_WAIT_S = 20.0      # a result waits for the others at most this long
RETRY_S = 1.0          # a script that is still running is asked again after this long


class Waker:
    """Wakes the session once for any number of finished jobs.

    ``poke()`` may be called from any thread (a pool callback). Every rerun redraws the
    whole page, so the waker asks for one when everything it watches is ready, or when
    the first ready job has waited ``max_wait`` seconds for the rest. It asks at least
    ``delay`` seconds after the poke. It calls ``request()``, and waits while ``running``
    is set: the visitor's own run is not interrupted, and that run's own start picks up
    whatever is ready."""

    def __init__(self, request: Callable[[], None], delay: float = WAKE_DELAY_S, retry: float = RETRY_S,
                 max_wait: float = MAX_WAIT_S):
        self.request = request
        self.delay, self.retry, self.max_wait = delay, retry, max_wait
        self._first_ready: Optional[float] = None
        self.running = False
        self._handles: List[Any] = []
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._stopped = False

    def watch(self, handle) -> None:
        with self._lock:
            self._handles.append(handle)

    def poke(self) -> None:
        with self._lock:
            if self._timer is None and not self._stopped:
                self._arm(self.delay)

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _arm(self, seconds: float) -> None:
        timer = threading.Timer(seconds, self._fire)
        timer.daemon = True
        self._timer = timer
        timer.start()

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
            if self._stopped:
                return
            self._handles = [h for h in self._handles if not h.dropped]
            ready = [h for h in self._handles if h.ready()]
            if not ready:
                self._first_ready = None                # cancelled, or already taken
                return
            now = time.monotonic()
            if self._first_ready is None:
                self._first_ready = now
            if len(ready) < len(self._handles) and now - self._first_ready < self.max_wait:
                self._arm(self.delay)                   # the rest are coming: check again
                return
            if self.running:
                self._arm(self.retry)
                return
            self._first_ready = None
        try:
            self.request()
        except Exception:
            logger.exception("Could not ask for a rerun")


def rerun_data(*, query_string: str = "", page_script_hash: str = "",
               cached_message_hashes=None, context_info=None):
    """The rerun ``st.rerun()`` would ask for: whole app, no widget state of its own."""
    from streamlit.runtime.scriptrunner import RerunData
    wanted = {"query_string": query_string, "page_script_hash": page_script_hash,
              "cached_message_hashes": set(cached_message_hashes or ()), "context_info": context_info}
    have = {f.name for f in dataclasses.fields(RerunData)}
    return RerunData(**{k: v for k, v in wanted.items() if k in have})


def request_rerun(session, data) -> None:
    """Hand ``data`` to ``session`` (on its event loop). The running runner gets it first:
    it merges the request with a pending one and keeps that one's widget values. A new
    runner is started only when there is none that can take it."""
    state = getattr(session, "_state", None)
    if getattr(state, "name", None) == "SHUTDOWN_REQUESTED":
        return
    runner = getattr(session, "_scriptrunner", None)
    if runner is not None and runner.request_rerun(data):
        return
    session._create_scriptrunner(data)


class _LiveRequest:
    """The request for one live session: what to send, and where."""

    def __init__(self, session, loop, ctx):
        self.session, self.loop = session, loop
        self.bind(ctx)

    def bind(self, ctx) -> None:
        """Take the client's message-cache list from the newest run. The wake-up rerun
        then sends a cached message as a reference only if the browser has it."""
        self._fields = dict(query_string=getattr(ctx, "query_string", "") or "",
                            page_script_hash=getattr(ctx, "page_script_hash", "") or "",
                            cached_message_hashes=set(getattr(ctx, "cached_message_hashes", ()) or ()),
                            context_info=getattr(ctx, "context_info", None))

    def __call__(self) -> None:
        data = rerun_data(**self._fields)
        self.loop.call_soon_threadsafe(request_rerun, self.session, data)


def make_waker(**kw) -> Optional[Waker]:
    """A waker for the session this script run belongs to (call it on the script thread),
    or None when Streamlit's session cannot be reached."""
    try:
        from streamlit.runtime import Runtime
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx(suppress_warning=True)
        if ctx is None or not Runtime.exists():
            return None
        info = Runtime.instance()._session_mgr.get_active_session_info(ctx.session_id)
        session = info.session
        loop = session._event_loop
        if not (hasattr(session, "_create_scriptrunner") and hasattr(session, "_scriptrunner")):
            return None
        return Waker(_LiveRequest(session, loop, ctx), **kw)
    except Exception:
        logger.info("Cannot reach the Streamlit session; follow-ups run on the script thread", exc_info=True)
        return None


def get(st, **kw) -> Optional[Waker]:
    """This session's waker (made on first use), marked as running: call it from a script run."""
    waker = st.session_state.get(KEY)
    if waker is None:
        waker = make_waker(**kw)
        if waker is None:
            return None
        st.session_state[KEY] = waker
    waker.running = True
    return waker


@contextlib.contextmanager
def running(st):
    """Wrap a script run. While it lasts the waker does not interrupt it; at the start it
    takes the browser's newest message-cache list, and at the end it may ask for a rerun."""
    waker = st.session_state.get(KEY)
    if waker is not None:
        waker.running = True
        bind = getattr(getattr(waker, "request", None), "bind", None)
        if bind is not None:
            try:
                from streamlit.runtime.scriptrunner import get_script_run_ctx
                bind(get_script_run_ctx(suppress_warning=True))
            except Exception:
                pass
    try:
        yield
    finally:
        try:
            waker = st.session_state.get(KEY)
        except Exception:
            waker = None
        if waker is not None:
            waker.running = False
            waker.poke()                                # anything that finished during the run
