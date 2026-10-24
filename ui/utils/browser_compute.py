"""Run simulation batches in the visitor's browser (Pyodide in Web Workers).

The server keeps the quick, detailed part of each analysis and hands the bulk
-- independent, seeded engine calls (``sim_runner.Plan``) -- to the browser
through a hidden component (components/browser_compute/). The browser runs the
same engine source with the same seeds, so its results equal the server's.
Whatever the browser can't do (unsupported, failed, or too slow), the server
runs itself.

Protocol (see components/browser_compute/index.html): the component gets the
pending jobs on every run and posts one message per event, each tagged
``{boot, seq}``; it sends the next only after the server echoes that tag back
as ``ack``, so no message is lost to Streamlit keeping only the latest value.

State lives in ``st.session_state[STATE]``:
``{"status": {...}, "ack": {...} | None, "jobs": {id: job}, "seen": <first render time>}``.
Results from the browser are untrusted input: parsed as JSON only, size-capped
and checked before use; a bad reply just makes the server do that job itself.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    from utils.hosting import is_hosted
except ImportError:  # pragma: no cover
    from ui.utils.hosting import is_hosted  # type: ignore

logger = logging.getLogger(__name__)

STATE = "_bc"
CONTAINER_KEY = "mc-browser-compute"
IFRAME_KEY = "mc-browser-compute-iframe"
COMPONENT_DIR = Path(__file__).resolve().parent.parent / "components" / "browser_compute"
ENGINE_DIR = Path(__file__).resolve().parents[2] / "retirement_sim"
ENGINE_FILES = ("__init__.py", "config.py", "account_simulation.py", "mc_parallel.py",
                "mc_jobs.py", "historical_returns.py", "state_tax_data.py")
DEFAULT_PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/"
MAX_WORKERS = 6
MAX_REPLY_CHARS = 30_000_000
# Seconds to wait for a job before the server takes it over. A job sent while
# the browser is still loading Pyodide (~12 MB on a first visit) gets longer --
# except the main result, which people are waiting on.
DEADLINE_MAIN_READY_S = 60
DEADLINE_MAIN_LOADING_S = 45
# The follow-up analyses only fill in their own sections, and a server takeover
# costs every visitor (one shared CPU), so the browser gets much longer.
DEADLINE_EXTRA_S = 240
# A component that never reports anything in this long isn't running at all.
SILENT_COMPONENT_S = 30

_component_func = None
_engine_cache: Optional[Dict[str, Any]] = None


def enabled() -> bool:
    """On when hosted (shared, small server CPU); off locally unless
    RETIREMENT_SIM_BROWSER_COMPUTE=1. RETIREMENT_SIM_BROWSER_COMPUTE=0 turns it off."""
    flag = os.environ.get("RETIREMENT_SIM_BROWSER_COMPUTE", "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    if flag in ("1", "true", "yes", "on"):
        return True
    return is_hosted()


def pyodide_url() -> str:
    url = os.environ.get("RETIREMENT_SIM_PYODIDE_URL", DEFAULT_PYODIDE_URL).strip()
    return url if url.endswith("/") else url + "/"


def engine() -> Dict[str, Any]:
    """The engine source the browser runs, and its content hash."""
    global _engine_cache
    if _engine_cache is None:
        files = {f"retirement_sim/{name}": (ENGINE_DIR / name).read_text(encoding="utf-8")
                 for name in ENGINE_FILES if (ENGINE_DIR / name).exists()}
        digest = hashlib.sha256("".join(k + v for k, v in sorted(files.items())).encode()).hexdigest()
        _engine_cache = {"hash": digest[:16], "files": files}
    return _engine_cache


def _state(st) -> Dict[str, Any]:
    s = st.session_state.get(STATE)
    if s is None:
        s = st.session_state[STATE] = {"status": {}, "ack": None, "jobs": {}, "seen": None}
    return s


def status(st) -> Dict[str, Any]:
    return _state(st)["status"]


def usable(st) -> bool:
    """Should new work go to the browser? (Not when disabled or known unavailable.)"""
    if not enabled():
        return False
    s = _state(st)
    if s["status"].get("state") == "unavailable":
        return False
    seen = s.get("seen")
    if not s["status"] and seen is not None and time.time() - seen > SILENT_COMPONENT_S:
        return False                                    # never booted: blocked iframe etc.
    return True


def ready(st) -> bool:
    """Workers loaded and waiting: work sent now starts at once. The main
    result goes to the browser only then -- it never waits for a download."""
    return usable(st) and status(st).get("state") == "ready"


def pending(st, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    return [j for j in _state(st)["jobs"].values() if kind is None or j["kind"] == kind]


def cancel(st, kinds: Optional[Iterable[str]] = None) -> None:
    """Drop pending jobs (all, or of ``kinds``); the browser cancels them once
    they leave the job list."""
    jobs = _state(st)["jobs"]
    for jid in [j for j, job in jobs.items() if kinds is None or job["kind"] in set(kinds)]:
        jobs.pop(jid, None)


# ---------------------------------------------------------------------------
# Submitting and finishing
# ---------------------------------------------------------------------------

def submit(st, kind: str, plan, on_done: Callable[[Dict[str, Any]], None],
           run_here: Iterable[int] = (), progress_callback=None) -> None:
    """Run ``plan``: calls in ``run_here`` on the server now, the rest in the
    browser. ``on_done(result)`` runs (in a later script run) when all are in."""
    from retirement_sim import mc_jobs
    from utils import sim_runner as sr
    if plan.result is not None:                     # cached, or nothing to compute
        on_done(plan.result)
        return
    here = list(run_here)
    results: List[Any] = [None] * len(plan.job["calls"])
    for i, r in zip(here, sr.run_plan_calls(plan, here, progress_callback)):
        results[i] = r
    remote = [i for i in range(len(results)) if i not in set(here)]
    job = {"id": uuid.uuid4().hex[:12], "kind": kind, "plan": plan, "remote": remote,
           "results": results, "on_done": on_done, "submitted": time.time(),
           "ready_at_submit": status(st).get("state") == "ready"}
    if not remote:
        _finish(job)
        return
    job["payload"] = mc_jobs.dumps({"base": plan.job["base"], "patches": plan.job["patches"],
                                    "calls": [plan.job["calls"][i] for i in remote]})
    _state(st)["jobs"][job["id"]] = job
    _state(st)["unsent"] = True


def unsent(st) -> bool:
    """A job was submitted after this run drew the component, so the browser
    hasn't been given it: the caller must rerun (nothing else would)."""
    return bool(enabled() and _state(st).get("unsent"))


def _finish(job: Dict[str, Any]) -> None:
    from utils import sim_runner as sr
    job["on_done"](sr.finish_plan(job["plan"], job["results"]))


def _run_here(st, job: Dict[str, Any], why: str) -> None:
    """The server takes over a job's remaining calls."""
    from utils import sim_runner as sr
    _state(st)["jobs"].pop(job["id"], None)
    todo = [i for i in job["remote"] if job["results"][i] is None]
    logger.info("browser compute: server runs %s job (%s)", job["kind"], why)
    for i, r in zip(todo, sr.run_plan_calls(job["plan"], todo)):
        job["results"][i] = r
    _finish(job)


def _accept(job: Dict[str, Any], text: Any) -> bool:
    """Fill a job from the browser's reply; False if the reply isn't usable."""
    from retirement_sim import mc_jobs
    if not isinstance(text, str) or len(text) > MAX_REPLY_CHARS:
        return False
    try:
        values = mc_jobs.loads(text)
    except (ValueError, TypeError, RecursionError):
        return False
    calls = job["plan"].job["calls"]
    if not isinstance(values, list) or len(values) != len(job["remote"]):
        return False
    for i, v in zip(job["remote"], values):
        if not _plausible(calls[i], v):
            return False
    for i, v in zip(job["remote"], values):
        job["results"][i] = v
    return True


def _plausible(call: List[Any], v: Any) -> bool:
    fn, _patch, args = call
    if fn in ("w1", "investable"):
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if not isinstance(v, dict):
        return False
    if fn in ("batch", "scan"):
        n, ok = v.get("n"), v.get("successes")
        if not (isinstance(n, int) and isinstance(ok, int) and 0 <= ok <= n <= int(args[1])):
            return False
        if fn == "batch":
            return isinstance(v.get("finals"), list) and isinstance(v.get("details"), list) \
                and len(v["finals"]) == n
        return v.get("age") == args[0]
    if fn in ("mc", "networth"):
        sr_ = v.get("success_rate")
        return isinstance(sr_, (int, float)) and 0.0 <= sr_ <= 1.0
    return False


# ---------------------------------------------------------------------------
# The component
# ---------------------------------------------------------------------------

def _component():
    global _component_func
    if _component_func is None:
        import streamlit.components.v1 as components
        _component_func = components.declare_component("browser_compute", path=str(COMPONENT_DIR))
    return _component_func


def render(st) -> bool:
    """Draw the hidden component (once per run, at a stable spot, so its
    workers survive reruns) and take in its latest message. True when a job
    finished in this call (its ``on_done`` has run)."""
    if not enabled():
        return False
    s = _state(st)
    if s["seen"] is None:
        s["seen"] = time.time()
    # Take in the browser's latest message BEFORE drawing, so this same run's
    # args acknowledge it -- the component sends its next message only after
    # the ack, and otherwise it would wait for some unrelated rerun.
    finished = _receive(st, st.session_state.get(IFRAME_KEY))
    eng = engine()
    jobs = [{"id": j["id"], "json": j["payload"], "n": len(j["remote"])} for j in s["jobs"].values()]
    s["unsent"] = False
    with st.container(key=CONTAINER_KEY):
        _component()(
            enabled=True, pyodide_url=pyodide_url(), max_workers=MAX_WORKERS,
            # Files go along until the browser reports this engine loaded
            # (its "loading" status, after a remount, asks for them again).
            engine={"hash": eng["hash"],
                    "files": None if (s["status"].get("engine") == eng["hash"]
                                      or s["status"].get("has_files")) else eng["files"]},
            jobs=jobs, ack=s["ack"], key=IFRAME_KEY, default=None, height=0)
    return finished


def _receive(st, value: Any) -> bool:
    s = _state(st)
    if not isinstance(value, dict):
        return False
    tag = {"boot": value.get("boot"), "seq": value.get("seq")}
    if not isinstance(tag["boot"], str) or not isinstance(tag["seq"], int):
        return False
    ack = s["ack"] or {}
    if tag["boot"] == ack.get("boot") and tag["seq"] <= ack.get("seq", 0):
        return False                                    # seen (Streamlit re-delivers the last value)
    s["ack"] = tag
    kind = value.get("type")
    if kind == "status":
        s["status"] = {k: value.get(k) for k in ("state", "workers", "engine", "reason", "has_files")}
        return False
    job = s["jobs"].get(value.get("id")) if isinstance(value.get("id"), str) else None
    if job is None:
        return False                                    # cancelled or already done
    if kind == "result" and _accept(job, value.get("results")):
        s["jobs"].pop(job["id"], None)
        job["browser_ms"] = value.get("ms")
        if os.environ.get("RETIREMENT_SIM_BC_VERIFY") == "1":
            _verify(job, value)
        _finish(job)
        return True
    _run_here(st, job, "browser error: %s" % str(value.get("reason"))[:200]
              if kind == "error" else "unusable reply")
    return True


def _verify(job: Dict[str, Any], value: Dict[str, Any]) -> None:
    """Diagnostics (RETIREMENT_SIM_BC_VERIFY=1): recompute the browser's calls
    here and log whether they match exactly."""
    from utils import sim_runner as sr
    from retirement_sim import mc_jobs
    mine = sr.run_plan_calls(job["plan"], job["remote"])
    theirs = [job["results"][i] for i in job["remote"]]
    same = [mc_jobs.dumps(a) == mc_jobs.dumps(b) for a, b in zip(mine, theirs)]
    worst = max((_rel_diff(a, b) for a, b in zip(mine, theirs)), default=0.0)
    logger.warning("browser compute verify: %s job, %d calls in %s ms on %s workers: %d/%d identical,"
                   " largest relative difference %.3g", job["kind"], len(same), value.get("ms"),
                   value.get("workers"), sum(same), len(same), worst)


def _rel_diff(a: Any, b: Any) -> float:
    """Largest relative difference between two results' numbers (inf: shapes differ)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return 0.0 if a == b else float("inf")
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) / max(abs(a), abs(b), 1e-12) if a != b else 0.0
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        return max((_rel_diff(a[k], b[k]) for k in a), default=0.0)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b):
        return max((_rel_diff(x, y) for x, y in zip(a, b)), default=0.0)
    return 0.0 if a == b else float("inf")


def overdue(st) -> List[Dict[str, Any]]:
    """Pending jobs the server should take over now."""
    jobs = pending(st)
    if not jobs:
        return []
    if not usable(st):
        return jobs
    now = time.time()
    return [j for j in jobs if now - j["submitted"] > _deadline(j)]


def _deadline(job: Dict[str, Any]) -> float:
    if job["kind"] != "main":
        return DEADLINE_EXTRA_S
    return DEADLINE_MAIN_READY_S if job["ready_at_submit"] else DEADLINE_MAIN_LOADING_S


def take_over_one(st) -> bool:
    """Run the oldest overdue job here. True if one ran."""
    jobs = sorted(overdue(st), key=lambda j: j["submitted"])
    if not jobs:
        return False
    _run_here(st, jobs[0], "browser unavailable" if not usable(st) else "deadline")
    return True
