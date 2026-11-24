"""Follow-up analyses in a background process pool (sim_runner.submit_plan_bg).

After a run, the ways-to-reach-your-goal, net-worth (FI), safe-withdrawal and
mortgage sweeps used to run one per script run on the script thread, so every
click waited behind a sweep. They now go to a process pool. When results are
ready, ``utils/session_wake.py`` asks Streamlit to rerun the session once (no
timer polling from the browser) and the rerun stores what finished."""
import concurrent.futures as cf
import os
import sys
import threading
import time

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import mc_jobs  # noqa: E402
from utils import sim_runner as sr  # noqa: E402

APP = os.path.join(_ROOT, "ui", "app.py")

SINGLE = {"YOUR_AGE": 30, "PARTNER_AGE": 0, "FILING_STATUS": "Single", "YOUR_BASE_SALARY": 130_000,
          "YOUR_401K": 40_000, "YOUR_CASH": 20_000, "TARGET_RETIREMENT_AGE": 55,
          "SPEND_RENT_MONTHLY": 500}


@pytest.fixture(autouse=True)
def _no_disk_cache(monkeypatch):
    monkeypatch.setattr(sr, "_disk", lambda: None)
    sr.clear_cache(include_disk=False)
    yield
    sr.clear_cache(include_disk=False)


class InlineExecutor:
    """Runs each task at once in this process; records what it was given."""

    def __init__(self, probe=None, fail=False):
        self.tasks, self.probe, self.fail = [], probe, fail

    def submit(self, fn, *args):
        self.tasks.append((fn, args))
        fut = cf.Future()
        if self.fail:
            fut.set_exception(RuntimeError("pool is gone"))
            return fut
        if self.probe:
            self.probe()
        fut.set_result(fn(*args))
        return fut


class ManualExecutor:
    """Holds each task until ``release`` -- a pool whose workers are still busy."""

    def __init__(self):
        self.pending = []

    def submit(self, fn, *args):
        fut = cf.Future()
        self.pending.append((fut, fn, args))
        return fut

    def release(self):
        for fut, fn, args in self.pending:
            if fut.set_running_or_notify_cancel():
                fut.set_result(fn(*args))
        self.pending = []


def _fi():
    return sr.plan_networth_analysis(SINGLE, n_simulations=60)


def _swr():
    return sr.plan_swr_analysis(SINGLE, 60, 55)


# ---------------------------------------------------------------- same numbers as the server

@pytest.mark.parametrize("make", [_fi, _swr], ids=["fi", "swr"])
def test_background_result_equals_the_server_result(make):
    whole = sr.execute_plan(make())
    sr.clear_cache(include_disk=False)                       # a fresh plan, not a cache hit
    plan = make()
    assert plan.result is None
    ex = InlineExecutor()
    handle = sr.submit_plan_bg(plan, generation=1, executor=ex)
    assert len(ex.tasks) >= 1
    assert all(fn is mc_jobs.run_local for fn, _a in ex.tasks)
    # Every call is sent once, whatever the chunking.
    sent = sorted(i for _fn, (_job, idx) in ex.tasks for i in idx)
    assert sent == list(range(len(plan.job["calls"])))
    sr.clear_cache(include_disk=False)
    assert sr.collect_bg(handle) == whole


def test_collect_waits_until_every_chunk_is_done():
    ex = ManualExecutor()
    handle = sr.submit_plan_bg(_fi(), generation=1, executor=ex)
    assert not handle.ready()
    assert sr.collect_bg(handle) is None
    ex.release()
    assert handle.ready()
    assert isinstance(sr.collect_bg(handle), dict)


def test_done_callback_runs_for_every_chunk_and_ready_needs_them_all():
    ex = ManualExecutor()
    calls = []
    handle = sr.submit_plan_bg(_fi(), generation=1, executor=ex, on_done=lambda: calls.append(1))
    n = len(handle.futures)
    assert calls == []
    ex.release()
    assert len(calls) == n and handle.ready()


# ---------------------------------------------------------------- late results

def test_a_newer_generation_drops_the_late_result():
    ex = ManualExecutor()
    handle = sr.submit_plan_bg(_fi(), generation=3, executor=ex)
    ex.release()
    assert sr.collect_bg(handle, generation=4) is None       # the session moved on
    assert handle.dropped
    assert sr.collect_bg(handle, generation=4) is None
    handle2 = sr.submit_plan_bg(_fi(), generation=4, executor=InlineExecutor())
    assert sr.collect_bg(handle2, generation=4) is not None


def test_cancel_stops_chunks_that_have_not_started():
    ex = ManualExecutor()
    handle = sr.submit_plan_bg(_fi(), generation=1, executor=ex)
    sr.cancel_bg(handle)
    assert all(f.cancelled() for f, _fn, _a in ex.pending)
    assert handle.dropped and not handle.ready()


def test_drain_splits_ready_stale_and_waiting_entries():
    done = sr.submit_plan_bg(_fi(), generation=2, executor=InlineExecutor())
    stale = sr.submit_plan_bg(_swr(), generation=1, executor=InlineExecutor())
    waiting = sr.submit_plan_bg(_fi(), generation=2, executor=ManualExecutor())
    entries = [("fi", done, "store-fi"), ("swr", stale, "store-swr"), ("again", waiting, "store-x")]
    arrived, remaining = sr.drain_bg(entries, generation=2)
    assert [(k, s) for k, s, _r in arrived] == [("fi", "store-fi")]
    assert isinstance(arrived[0][2], dict)
    assert remaining == [("again", waiting, "store-x")]
    assert stale.dropped


# ---------------------------------------------------------------- failures

def test_pool_failure_falls_back_to_running_it_here():
    whole = sr.execute_plan(_fi())
    sr.clear_cache(include_disk=False)
    handle = sr.submit_plan_bg(_fi(), generation=1, executor=InlineExecutor(fail=True))
    assert sr.collect_bg(handle) == whole


def test_submit_failure_is_raised_for_the_caller_to_fall_back():
    class Broken:
        def submit(self, *_a):
            raise RuntimeError("cannot start")

    with pytest.raises(RuntimeError):
        sr.submit_plan_bg(_fi(), generation=1, executor=Broken())


# ---------------------------------------------------------------- the config lock

def test_no_config_lock_is_held_while_the_pool_computes():
    held = []

    def probe():
        def other_thread():
            got = sr.CONFIG_LOCK.acquire(blocking=False)
            if got:
                sr.CONFIG_LOCK.release()
            held.append(not got)

        t = threading.Thread(target=other_thread)
        t.start()
        t.join()

    handle = sr.submit_plan_bg(_fi(), generation=1, executor=InlineExecutor(probe=probe))
    assert held and not any(held)
    assert sr.collect_bg(handle) is not None


# ---------------------------------------------------------------- the real pool

def test_real_pool_matches_the_server():
    whole = sr.execute_plan(_fi())
    sr.clear_cache(include_disk=False)
    woke = threading.Event()
    handle = sr.submit_plan_bg(_fi(), generation=1, on_done=woke.set)
    assert woke.wait(180), "the pool never finished"
    deadline = time.time() + 30
    result = None
    while result is None and time.time() < deadline:
        result = sr.collect_bg(handle)
        time.sleep(0.05)
    assert result == whole


def test_flag_turns_it_off(monkeypatch):
    monkeypatch.setenv("RETIREMENT_SIM_BG_EXTRAS", "0")
    assert not sr.bg_extras_enabled()
    monkeypatch.delenv("RETIREMENT_SIM_BG_EXTRAS")
    monkeypatch.setenv("RETIREMENT_SIM_MAX_WORKERS", "1")
    assert not sr.bg_extras_enabled()                         # 1 = never start worker processes
    monkeypatch.setenv("RETIREMENT_SIM_MAX_WORKERS", "4")
    assert sr.bg_extras_enabled()


def test_workers_do_not_re_import_the_main_script(monkeypatch):
    """Under ``streamlit run`` the main file is app.py. Spawned workers would import
    all of it: the file is hidden while they start, and put back after."""
    main = sys.modules["__main__"]
    monkeypatch.setattr(main, "__file__", "/some/app.py", raising=False)
    seen = []

    class Spy(InlineExecutor):
        def submit(self, fn, *args):
            seen.append(hasattr(main, "__file__"))
            return super().submit(fn, *args)

    sr.submit_plan_bg(_fi(), generation=1, executor=Spy())
    assert seen and not any(seen)
    assert main.__file__ == "/some/app.py"


# ---------------------------------------------------------------- waking the session

from utils import session_wake  # noqa: E402


class _Handle:
    """Stands in for a BgHandle: ready when ``done`` and not dropped."""

    def __init__(self, done=True):
        self.done, self.dropped = done, False

    def ready(self):
        return self.done and not self.dropped


def _waker(**kw):
    fired = []
    kw.setdefault("delay", 0.05)
    kw.setdefault("retry", 0.05)
    return session_wake.Waker(lambda: fired.append(time.time()), **kw), fired


def _until(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def test_several_results_close_together_wake_the_session_once():
    w, fired = _waker(delay=0.2)
    w.watch(_Handle())
    for _ in range(6):
        w.poke()
        time.sleep(0.01)
    assert _until(lambda: len(fired) == 1)
    time.sleep(0.4)
    assert len(fired) == 1


def test_the_rerun_waits_for_the_other_results():
    """Each rerun redraws the whole page: four results that trickle in must not cost four
    reruns. The waker waits until every watched job is ready."""
    w, fired = _waker(max_wait=30)
    first, second, third = _Handle(), _Handle(done=False), _Handle(done=False)
    for h in (first, second, third):
        w.watch(h)
    w.poke()
    time.sleep(0.3)
    assert fired == []                                    # two are still computing
    second.done = True
    w.poke()
    time.sleep(0.3)
    assert fired == []
    third.done = True
    w.poke()
    assert _until(lambda: len(fired) == 1)
    time.sleep(0.3)
    assert len(fired) == 1


def test_a_ready_result_does_not_wait_for_a_slow_one_for_ever():
    w, fired = _waker(max_wait=0.3)
    w.watch(_Handle())
    w.watch(_Handle(done=False))                          # never finishes
    w.poke()
    time.sleep(0.15)
    assert fired == []
    assert _until(lambda: len(fired) == 1)


def test_a_result_the_visitors_own_rerun_took_does_not_hold_the_others_back():
    w, fired = _waker(max_wait=30)
    taken, ready = _Handle(), _Handle()
    waiting = _Handle(done=False)
    for h in (taken, ready, waiting):
        w.watch(h)
    w.poke()
    time.sleep(0.2)
    taken.dropped = ready.dropped = True                  # a rerun of theirs stored both
    waiting.done = True
    w.poke()
    assert _until(lambda: len(fired) == 1)


def test_a_running_script_is_not_interrupted():
    """A user's run (Run, a sensitivity sweep) must finish first: the rerun that
    shows the results waits until the script is idle."""
    w, fired = _waker()
    w.watch(_Handle())
    w.running = True
    w.poke()
    time.sleep(0.4)
    assert fired == []
    w.running = False
    assert _until(lambda: len(fired) == 1)


def test_nothing_ready_means_no_rerun():
    w, fired = _waker()
    gone, waiting = _Handle(), _Handle(done=False)
    w.watch(gone)
    w.watch(waiting)
    gone.dropped = True                       # a new run or a profile switch cancelled it
    w.poke()
    time.sleep(0.3)
    assert fired == []


def test_a_stopped_waker_never_fires():
    w, fired = _waker(delay=0.2)
    w.watch(_Handle())
    w.poke()
    w.stop()
    time.sleep(0.4)
    assert fired == []


def test_rerun_request_keeps_the_pending_widget_values():
    """The rerun carries no widget state of its own. A pending edit of the visitor's must
    survive: hand the request to the running runner first (it merges), and start a new
    runner only when there is none to take it."""
    class Runner:
        def __init__(self, accepts):
            self.accepts, self.got = accepts, []

        def request_rerun(self, data):
            self.got.append(data)
            return self.accepts

    class Session:
        def __init__(self, runner):
            self._scriptrunner, self.created = runner, []

        def _create_scriptrunner(self, data):
            self.created.append(data)

    data = session_wake.rerun_data(query_string="a=1", page_script_hash="h", cached_message_hashes={"m"},
                                   context_info=None)
    assert data.widget_states is None and not data.fragment_id_queue
    assert data.cached_message_hashes == {"m"} and data.query_string == "a=1"
    live = Session(Runner(True))
    session_wake.request_rerun(live, data)
    assert live._scriptrunner.got == [data] and live.created == []
    idle = Session(Runner(False))
    session_wake.request_rerun(idle, data)
    assert idle.created == [data]
    none_yet = Session(None)
    session_wake.request_rerun(none_yet, data)
    assert none_yet.created == [data]


def test_outside_a_streamlit_session_there_is_no_waker():
    assert session_wake.make_waker() is None


# ---------------------------------------------------------------- the planner

@pytest.fixture(autouse=True)
def _planner_can_rerun(monkeypatch):
    """AppTest reads a segmented control's single choice as a list (see
    test_mode_switch_sidebar); teach it that so the planner can be rerun."""
    from streamlit.testing.v1 import element_tree as et

    def indices(self):
        values = [self.value] if isinstance(self.value, str) else self.value
        return [self.options.index(self.format_func(v)) for v in values]
    monkeypatch.setattr(et.ButtonGroup, "indices", property(indices))


def _planner(monkeypatch):
    """The hosted planner past its walkthrough, first run done (500 simulations)."""
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    monkeypatch.setenv("RETIREMENT_SIM_BG_EXTRAS", "0")
    at = AppTest.from_file(APP, default_timeout=300).run()
    at.button(key="device_skip").click().run()
    next(b for b in at.button if b.label == "Open the retirement planner").click().run()
    at.button(key="gs_skip").click().run()
    assert not at.exception, at.exception
    assert at.session_state["results"] is not None
    return at


class FakeWaker:
    """What app.py needs from a waker, recording what it is told."""

    def __init__(self):
        self.watched, self.pokes, self.running, self.stopped = [], 0, False, False

    def watch(self, handle):
        self.watched.append(handle)

    def poke(self):
        self.pokes += 1

    def stop(self):
        self.stopped = True


def test_a_run_queues_the_follow_ups_in_the_pool_and_a_rerun_shows_them(monkeypatch):
    """After Run the page comes back without computing the follow-ups on the script
    thread. When the pool has finished, the next rerun (the one the waker asks for)
    stores them -- no second trigger and no poll."""
    at = _planner(monkeypatch)
    ex = ManualExecutor()
    waker = FakeWaker()
    monkeypatch.setenv("RETIREMENT_SIM_BG_EXTRAS", "1")
    monkeypatch.setenv("RETIREMENT_SIM_BROWSER_COMPUTE", "0")        # no browser workers: the server's pool
    monkeypatch.setattr(sr, "_bg_executor", lambda: ex)
    monkeypatch.setattr(session_wake, "make_waker", lambda: waker)
    ov = dict(at.session_state["user_overrides"])
    ov["YOUR_AGE"] += 1                                               # an edit: the results go stale
    at.session_state["user_overrides"] = ov
    at.run()
    for key in ("fi_result", "swr_result", "goal_levers_result", "mortgage_paydown_result"):
        if key in at.session_state:                                   # the first run's, computed inline
            del at.session_state[key]
    at.button(key="topbar_run_button").click().run()
    assert not at.exception, at.exception
    ss = at.session_state
    kinds = [k for k, _h, _s in ss["_extras_bg"]]
    assert kinds[:1] == ["levers"] and {"fi", "swr"} <= set(kinds)
    assert ss["results"] is not None and not ss["_extras_pending"]
    assert "fi_result" not in ss and "swr_result" not in ss          # nothing ran on this thread
    assert len(waker.watched) == len(kinds)
    ex.release()                                                      # the pool finishes
    at.run()                                                          # the rerun the waker asks for
    assert not at.exception, at.exception
    ss = at.session_state
    assert not ss["_extras_bg"]
    assert isinstance(ss["fi_result"], dict) and isinstance(ss["swr_result"], dict)


def test_switching_profile_with_a_job_pending_leaves_no_results(monkeypatch):
    """Profile A's late results (pool or browser) must not land under profile B. A switch
    clears results, cancels both kinds of job and waits for an explicit Run."""
    at = _planner(monkeypatch)
    ex = ManualExecutor()
    handle = sr.submit_plan_bg(_fi(), generation=0, executor=ex)
    stored = []
    ss = at.session_state
    ss["_extras_bg"] = [("fi", handle, lambda res: stored.append(res))]
    ss["_extras_gen"] = 0
    ss["_main_pending"] = True
    job = {"id": "j1", "kind": "main", "plan": None, "remote": [0], "results": [None],
           "on_done": lambda res: stored.append(res), "submitted": time.time(), "ready_at_submit": True,
           "payload": "{}"}
    ss["_bc"] = {"status": {"state": "ready", "workers": 4, "engine": "x"}, "ack": {"boot": "b", "seq": 3},
                 "jobs": {"j1": job}, "seen": time.time()}
    at.selectbox(key="profile_selectbox").set_value("Near retirement (55)").run()
    assert not at.exception, at.exception
    ss = at.session_state
    assert ss["profile"] == "Near retirement (55)"
    assert ss["results"] is None and ss["whatif_results"] is None
    assert not ss.filtered_state.get("_extras_bg")
    assert handle.dropped                                              # the pool job is cancelled
    assert "_main_pending" not in ss
    assert ss["_bc"]["jobs"] == {}                                     # the browser job is dropped ...
    assert ss["_bc"]["status"]["state"] == "ready" and ss["_bc"]["ack"] == {"boot": "b", "seq": 3}   # ... its status kept
    ex.release()                                                       # the old job finishes late
    at.run()
    assert not at.exception, at.exception
    ss = at.session_state
    assert stored == []
    assert ss["results"] is None
    for key in ("last_run_inputs_hash", "mortgage_paydown_result", "fi_result", "swr_result"):
        assert ss.filtered_state.get(key) is None, key


def test_the_walkthrough_hands_over_a_selectbox_that_matches_the_profile():
    """_sync_planner sets profile to "Custom" for the visitor's own answers. A profile
    drop-down still holding a sample's name would apply that sample over them."""
    import types
    from components import guided_setup
    st = types.SimpleNamespace(session_state={"user_overrides": {"YOUR_AGE": 29}, "profile": "Near retirement (55)",
                                              "profile_selectbox": "Near retirement (55)"})
    guided_setup._sync_planner(st)
    assert st.session_state["profile"] == "Custom (keep current values)"
    assert st.session_state["profile_selectbox"] == st.session_state["profile"]
