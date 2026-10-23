"""Static checks for ui/components/browser_compute (no browser, no network).

Covers the Streamlit component protocol strings, the message shapes posted to
Python, that the iframe's main thread never fetches or runs Python, that the
worker loads Pyodide from the URL it is given and imports the engine from
Pyodide's filesystem, that the engine entry points it calls exist in
retirement_sim.mc_jobs, and (when node is installed) that the JS parses.

The behaviour itself (workers, dedupe, FIFO, acked outbox, cancel, errors,
engine restarts, worker caps) is verified in WebKit against a fake Pyodide by
tests/browser_compute_harness/run_playwright.py; that needs a browser, so it
doesn't run in pytest.
"""
import inspect
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT_DIR = ROOT / "ui" / "components" / "browser_compute"
INDEX = COMPONENT_DIR / "index.html"
WORKER = COMPONENT_DIR / "worker.js"
FAKE_PYODIDE = ROOT / "tests" / "browser_compute_harness" / "fake_pyodide" / "pyodide.js"


def _index() -> str:
    return INDEX.read_text(encoding="utf-8")


def _worker() -> str:
    return WORKER.read_text(encoding="utf-8")


def _index_script() -> str:
    match = re.search(r"<script>(.*)</script>", _index(), re.S)
    assert match, "index.html has no inline <script>"
    return match.group(1)


def test_component_files_exist():
    assert INDEX.is_file() and WORKER.is_file()


def test_index_speaks_the_streamlit_component_protocol():
    html = _index()
    for needle in ("streamlit:componentReady", "apiVersion: 1", "streamlit:render",
                   "streamlit:setComponentValue", 'dataType: "json"', "streamlit:setFrameHeight",
                   "isStreamlitMessage", "event.source !== window.parent", "{ height: 0 }"):
        assert needle in html, needle


def test_index_posts_the_documented_messages():
    js = _index_script()
    for needle in ('type: "status"', '"ready"', '"unavailable"', '"loading"', 'type: "result"',
                   'type: "error"', "inflight.boot = BOOT", "inflight.seq = ++seqNo", "args.ack",
                   "args.jobs", "args.engine", "args.max_workers", "args.pyodide_url", "args.enabled",
                   '"disabled"', 'results: "[" + job.results.join(",") + "]"'):
        assert needle in js, needle


def test_index_main_thread_never_fetches_or_runs_python():
    js = _index_script()
    for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "EventSource", "importScripts",
                   "loadPyodide", "runPython", "eval(", "new Function"):
        assert banned not in js, banned
    assert not re.search(r"https?://", _index())
    assert 'new Worker("worker.js"' in js


def test_worker_loads_pyodide_from_the_given_url_only():
    js = _worker()
    for needle in ('importScripts(indexURL + "pyodide.js")', "loadPyodide({ indexURL: indexURL })",
                   'loadPackage("numpy")'):
        assert needle in js, needle
    assert not re.search(r"https?://", js), "the Pyodide URL must come from the pyodide_url arg"


def test_worker_imports_the_engine_from_pyodide_fs():
    js = _worker()
    for needle in ('const ROOT = "/home/pyodide"', "FS.mkdirTree", "FS.writeFile", "sys.path.insert(0, ",
                   "importlib.invalidate_caches()", 'pyimport("retirement_sim.mc_jobs")'):
        assert needle in js, needle


def test_worker_calls_exist_in_mc_jobs():
    from retirement_sim import mc_jobs

    called = set(re.findall(r"\bmod\.(\w+)", _worker()))
    assert called == {"browser_load", "browser_run"}
    assert list(inspect.signature(mc_jobs.browser_load).parameters) == ["job_id", "job_json"]
    assert list(inspect.signature(mc_jobs.browser_run).parameters) == ["job_id", "index"]


def test_fake_pyodide_mirrors_the_worker_surface():
    fake = FAKE_PYODIDE.read_text(encoding="utf-8")
    for needle in ("self.loadPyodide", "loadPackage", "mkdirTree", "writeFile", "runPython", "pyimport",
                   "browser_load", "browser_run"):
        assert needle in fake, needle


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("name", ["index", "worker", "fake"])
def test_javascript_parses(name, tmp_path):
    if name == "index":
        path = tmp_path / "index_script.js"
        path.write_text(_index_script(), encoding="utf-8")
    else:
        path = WORKER if name == "worker" else FAKE_PYODIDE
    proc = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
