"""Drive ui/components/browser_compute in WebKit against the fake Pyodide (test-only).

    python3 tests/browser_compute_harness/run_playwright.py

Serves the repo files on a fake origin through Playwright request routing
(serve.lookup; no socket), opens harness.html (which plays the Streamlit host
+ a minimal server) and checks the component's behaviour:
warm-up, dedupe, FIFO, result order, acked outbox, cancel, errors,
unavailable paths, engine restarts and worker-count capping. Prints one
PASS/FAIL line per check; exit code 1 if any check fails.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import serve  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

BASE = "http://bc-harness.test"      # fake origin, answered by _serve
CHECKS: list[tuple[str, bool]] = []


def check(name: str, ok, detail="") -> None:
    CHECKS.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok or detail == "" else f"   -> {detail}"), flush=True)


def engine(tag: str, extra: str = "") -> dict:
    return {"hash": tag, "files": {"retirement_sim/__init__.py": "# fake engine package\n",
                                   "retirement_sim/mc_jobs.py": f"# ENGINE_TAG={tag}\n{extra}\n"}}


def job(jid: str, n: int, calls: int | None = None, **kw) -> dict:
    body = {"base": {}, "patches": [], "calls": [["mc", -1, [i]] for i in range(n if calls is None else calls)]}
    body.update(kw)
    return {"id": jid, "json": json.dumps(body), "n": n}


def init_script(hwc=None, touch=None, screen=None, uad_mobile=False, no_worker=False) -> str:
    js = []
    if hwc is not None:
        js.append(f"Object.defineProperty(Navigator.prototype,'hardwareConcurrency',{{get:()=>{hwc},configurable:true}});")
    if touch is not None:
        js.append(f"Object.defineProperty(Navigator.prototype,'maxTouchPoints',{{get:()=>{touch},configurable:true}});")
    if screen is not None:
        js.append(f"Object.defineProperty(Screen.prototype,'width',{{get:()=>{screen[0]},configurable:true}});"
                  f"Object.defineProperty(Screen.prototype,'height',{{get:()=>{screen[1]},configurable:true}});")
    if uad_mobile:
        js.append("Object.defineProperty(Navigator.prototype,'userAgentData',{get:()=>({mobile:true}),configurable:true});")
    if no_worker:
        js.append("if(location.pathname.endsWith('/browser_compute/index.html'))"
                  "Object.defineProperty(window,'Worker',{value:undefined,configurable:true,writable:true});")
    return "(function(){" + "".join(js) + "})();"


class Session:
    def __init__(self, browser, base: str, **overrides):
        self.ctx = browser.new_context()
        self.ctx.route(base + "/**", _serve)
        self.ctx.add_init_script(init_script(**overrides))
        self.page = self.ctx.new_page()
        self.errors: list[str] = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto(base + serve.HARNESS_PATH)

    def start(self, **args) -> None:
        self.js("a => H.start(a)", args)

    def js(self, expr: str, arg=None):
        return self.page.evaluate(expr, arg)

    def wait(self, expr: str, arg=None, timeout: int = 8000) -> None:
        self.page.wait_for_function(expr, arg=arg, timeout=timeout)

    def set_jobs(self, jobs: list) -> None:
        self.js("j => { H.args.jobs = j; H.render(); }", jobs)

    def wait_read(self, vtype: str, key: str, timeout: int = 8000) -> dict:
        """Wait until the server read a value of type vtype for job id / status state `key`."""
        expr = "([t, k]) => H.read.some(v => v.type === t && (v.id === k || v.state === k))"
        self.wait(expr, [vtype, key], timeout)
        return [v for v in self.js("() => H.read") if v["type"] == vtype and key in (v.get("id"), v.get("state"))][-1]

    def values(self) -> list:
        return self.js("() => H.values")

    def events(self, ev: str) -> list:
        return self.js("e => H.ev(e)", ev)

    def now(self) -> float:
        return self.js("() => performance.timeOrigin + performance.now()")

    def close(self, label: str) -> None:
        check(f"{label}: no uncaught page errors", not self.errors, self.errors)
        self.ctx.close()


def _serve(route) -> None:
    found = serve.lookup(route.request.url)
    if found is None:
        route.fulfill(status=404, content_type="text/plain", body="not found")
    else:
        route.fulfill(status=200, content_type=found[1], body=found[0].read_bytes(),
                      headers={"Cache-Control": "no-store"})


def results_ok(value: dict, jid: str, n: int, eng: str | None = None) -> bool:
    arr = json.loads(value["results"])
    return (len(arr) == n and [r["i"] for r in arr] == list(range(n)) and all(r["id"] == jid for r in arr)
            and (eng is None or all(r["eng"] == eng for r in arr)))


# ---------------------------------------------------------------------------

def scenario_core(browser, base):
    s = Session(browser, base, hwc=5)                        # 5 cores - 1 = 4, max_workers 3 -> 3
    s.start(max_workers=3, engine=engine("H1"), jobs=[])
    ready = s.wait_read("status", "ready")
    check("core: warm-up -> 'loading' then 'ready' before any job, workers=3, engine=H1",
          ready["workers"] == 3 and ready["engine"] == "H1"
          and [v["state"] for v in s.values()] == ["loading", "ready"], ready)
    s.wait("() => H.ev('import').length === 3")
    boots = s.events("boot")
    t0 = next(b["t"] for b in boots if b["name"] == "bc-0")
    rest = [round(b["t"] - t0) for b in boots if b["name"] != "bc-0"]
    check("core: 3 workers booted, bc-0 first, others after it loaded Pyodide (staggered)",
          sorted(b["name"] for b in boots) == ["bc-0", "bc-1", "bc-2"] and all(d >= 60 for d in rest), rest)
    check("core: componentReady once, frame height always 0",
          s.js("() => H.componentReady === 1 && H.heights.length > 0 && H.heights.every(h => h === 0)"))
    check("core: server stopped sending engine files after reading 'ready'", s.js("() => H.args.engine.files === null"))

    # Two jobs, listed together and re-rendered constantly (dedupe), on a server
    # that reads only the latest value per rerun (loss would show as a hang).
    s.js("j => { H.args.jobs = j; for (let i = 0; i < 5; i++) H.render(); H.spam = setInterval(H.render, 25); }",
         [job("A", 12, delays=[60, 10, 10] * 4), job("B", 6, delays=[40, 10, 10] * 2)])  # finish out of order
    a = s.wait_read("result", "A", 10000)
    b = s.wait_read("result", "B", 10000)
    s.js("() => clearInterval(H.spam)")
    time.sleep(0.3)
    vals = s.values()
    runs = s.events("run")
    check("core: exactly one result per job id",
          sum(v.get("id") == "A" for v in vals) == 1 and sum(v.get("id") == "B" for v in vals) == 1)
    per_call = {}
    for r in runs:
        per_call[(r["id"], r["i"])] = per_call.get((r["id"], r["i"]), 0) + 1
    check("core: dedupe -> every call ran exactly once despite repeated renders",
          sorted(per_call) == sorted([("A", i) for i in range(12)] + [("B", i) for i in range(6)])
          and set(per_call.values()) == {1}, per_call)
    loads = [(e["pid"], e["id"]) for e in s.events("load")]
    check("core: browser_load once per worker and job", len(loads) == len(set(loads)), loads)
    a_starts = [r["t"] for r in runs if r["id"] == "A"]
    b_starts = [r["t"] for r in runs if r["id"] == "B"]
    order = {("A", i): i for i in range(12)} | {("B", i): 12 + i for i in range(6)}
    per_worker = {}
    for r in sorted(runs, key=lambda r: r["t"]):              # same clock within one worker
        per_worker.setdefault(r["pid"], []).append(order[(r["id"], r["i"])])
    check("core: FIFO -> each worker took calls in queue order (A0..A11 then B0..B5)",
          all(seq == sorted(seq) for seq in per_worker.values()), per_worker)
    # Cross-worker timestamps can differ by a fraction of a millisecond: 2 ms slack.
    check("core: FIFO -> every call of A started before the first call of B",
          max(a_starts) <= min(b_starts) + 2, round(max(a_starts) - min(b_starts), 3))
    done = [(r["id"], r["i"]) for r in sorted(s.events("ran"), key=lambda r: r["t"])]
    check("core: calls completed out of index order (so the next check means something)",
          done[:12] != [("A", i) for i in range(12)], done[:6])
    check("core: results arrays in call-index order, ids match",
          results_ok(a, "A", 12, "H1") and results_ok(b, "B", 6, "H1"))
    check("core: results report workers=3 and ms>0", a["workers"] == b["workers"] == 3 and a["ms"] > 0 and b["ms"] > 0,
          (a["workers"], b["workers"], a["ms"], b["ms"]))
    check("core: calls spread over 3 distinct workers", len({r["pid"] for r in runs}) == 3)
    seqs = [v["seq"] for v in vals]
    read_seqs = [v["seq"] for v in s.js("() => H.read")]
    check("core: seqs 1..k, one boot, and the latest-wins server read every value (nothing lost)",
          seqs == list(range(1, len(vals) + 1)) and sorted(read_seqs) == seqs and len({v["boot"] for v in vals}) == 1,
          (seqs, read_seqs))
    s.close("core")


def scenario_outbox(browser, base):
    s = Session(browser, base, hwc=3)                         # -> 2 workers
    s.js("() => { H.auto = false; }")
    s.start(max_workers=4, engine=engine("H1"))
    s.wait("() => H.values.length === 1")
    first = s.values()[0]
    check("outbox: first value is status loading (alive, has the files)",
          first["state"] == "loading" and first.get("has_files") is True, first)
    s.js("() => H.rerun()")                                   # server reads + acks 'loading'
    s.wait("() => H.values.length === 2")
    check("outbox: then status ready", s.values()[1]["state"] == "ready")
    s.js("() => H.rerun()")                                   # server reads + acks 'ready'
    s.set_jobs([job("C", 1, delay_ms=5), job("D", 1, delay_ms=5)])
    s.wait("() => H.ev('ran').filter(e => e.id === 'C' || e.id === 'D').length === 2")
    time.sleep(0.3)
    vals = s.values()
    check("outbox: two jobs finish back-to-back -> only one value posted before the ack",
          len(vals) == 3 and vals[2]["type"] == "result", [v.get("id") for v in vals])
    s.js("() => H.render()")
    time.sleep(0.3)
    check("outbox: a render without a new ack posts nothing", len(s.values()) == 3)
    s.js("() => { H.args.ack = {boot: 'someone-else', seq: 99}; H.render(); }")   # foreign ack
    s.wait("() => H.values.length === 4")
    v = s.values()
    check("outbox: ack from another boot -> unacknowledged value resent with the same seq",
          v[3]["seq"] == v[2]["seq"] and v[3]["id"] == v[2]["id"], (v[2]["seq"], v[3]["seq"]))
    s.js("() => H.render()")
    time.sleep(0.3)
    check("outbox: no further resend while that ack is unchanged (no rerun storm)", len(s.values()) == 4)
    s.js("() => { H.args.ack = null; H.rerun(); }")           # fresh server reads it, acks
    s.wait("() => H.values.length === 5")
    s.js("() => H.rerun()")
    got = sorted(v["id"] for v in s.js("() => H.read") if v["type"] == "result")
    check("outbox: next value sent only after the ack; server read both results", got == ["C", "D"], got)

    # Auto reruns, latest-wins server, several jobs finishing at once: nothing lost.
    s.js("() => { H.auto = true; H.rerunDelay = 1; }")
    s.set_jobs([job(f"F{i}", 1, delay_ms=1) for i in range(5)])
    s.wait("() => ['F0','F1','F2','F3','F4'].every(k => H.read.some(v => v.id === k))", timeout=8000)
    check("outbox: 5 jobs finishing together, server sees only the latest value -> all 5 read", True)
    s.close("outbox")


def scenario_cancel(browser, base):
    s = Session(browser, base, hwc=3)                         # -> 2 workers
    s.start(max_workers=4, engine=engine("H1"))
    s.wait_read("status", "ready")
    s.set_jobs([job("X", 8, delay_ms=150)])
    s.wait("() => H.ev('run').filter(e => e.id === 'X').length === 2")
    s.set_jobs([])                                            # server drops X
    time.sleep(0.8)
    runs_x = [r for r in s.events("run") if r["id"] == "X"]
    check("cancel: removed job -> no further calls (only the 2 running ones ran)", len(runs_x) == 2, len(runs_x))
    check("cancel: nothing posted for the cancelled job", not any(v.get("id") == "X" for v in s.values()))
    s.set_jobs([job("Y", 4, delay_ms=10)])
    y = s.wait_read("result", "Y")
    check("cancel: next job runs normally on both workers", results_ok(y, "Y", 4) and y["workers"] == 2)
    s.set_jobs([job("X", 8, delay_ms=5)])                     # listed again after the cancel
    x = s.wait_read("result", "X")
    check("cancel: a cancelled id listed again starts over and completes", results_ok(x, "X", 8))
    s.close("cancel")


def scenario_errors(browser, base):
    s = Session(browser, base, hwc=3)                         # -> 2 workers
    s.start(max_workers=4, engine=engine("H1"))
    s.wait_read("status", "ready")
    s.set_jobs([job("E1", 6, delay_ms=40, fail_index=1)])
    e1 = s.wait_read("error", "E1")
    time.sleep(0.3)
    runs = [r for r in s.events("run") if r["id"] == "E1"]
    check("errors: Python exception -> one 'error' with the exception text",
          "ValueError: boom at call 1" in e1["reason"] and sum(v.get("id") == "E1" for v in s.values()) == 1, e1)
    check("errors: remaining calls of the failed job dropped", len(runs) <= 2, len(runs))
    s.set_jobs([{"id": "E2", "json": "not json", "n": 2}])
    e2 = s.wait_read("error", "E2")
    check("errors: browser_load failure -> error", "JSONDecodeError" in e2["reason"], e2)
    s.set_jobs([job("E6", 5, calls=3)])
    e6 = s.wait_read("error", "E6")
    check("errors: n disagrees with the job's call count -> error", "3 calls, expected 5" in e6["reason"], e6)
    s.set_jobs([job("E3", 4)])
    e3 = s.wait_read("result", "E3")
    check("errors: Python errors don't cost workers (next job: workers=2)", results_ok(e3, "E3", 4) and e3["workers"] == 2)
    s.set_jobs([job("E4", 4, fatal_index=0, delay_ms=20)])
    e4 = s.wait_read("error", "E4")
    dead = next(r["pid"] for r in s.events("run") if r["id"] == "E4" and r["i"] == 0)
    t_err = s.now()
    time.sleep(0.5)
    late = [e for e in s.events("alive") if e["pid"] == dead and e["t"] > t_err + 150]
    check("errors: non-Python (fatal) error -> error posted and that worker terminated",
          "fake fatal" in e4["reason"] and not late, (e4["reason"][:80], len(late)))
    s.set_jobs([job("E5", 4)])
    e5 = s.wait_read("result", "E5")
    pids = {r["pid"] for r in s.events("run") if r["id"] == "E5"}
    check("errors: survivors carry on (workers=1, killed worker unused)",
          results_ok(e5, "E5", 4) and e5["workers"] == 1 and dead not in pids, (e5["workers"], pids))
    s.close("errors")


def scenario_unavailable(browser, base):
    s = Session(browser, base, hwc=3)
    s.start(enabled=False, engine=engine("H1"))
    s.wait("() => H.values.length === 1")
    for _ in range(3):
        s.js("() => H.render()")
    time.sleep(0.4)
    v = s.values()
    check("unavailable: disabled -> one status unavailable/disabled across renders, no workers",
          len(v) == 1 and v[0]["state"] == "unavailable" and v[0]["reason"] == "disabled" and not s.events("boot"), v)
    s.set_jobs([job("J", 2)])
    j = s.wait_read("error", "J")
    check("unavailable: job listed while disabled -> error", "disabled" in j["reason"], j)
    s.js("() => { H.args.enabled = true; H.render(); }")
    s.wait_read("status", "ready")
    check("unavailable: enabling later boots workers and reports ready", len(s.events("boot")) >= 1)
    s.close("unavailable/disabled")

    s = Session(browser, base, hwc=3, no_worker=True)
    s.start(engine=engine("H1"))
    s.wait("() => H.values.length >= 1")
    v = s.values()[0]
    check("unavailable: no Web Worker support -> unavailable", v["state"] == "unavailable" and "Web Worker" in v["reason"], v)
    s.close("unavailable/no-worker")

    s = Session(browser, base, hwc=4)                         # -> 3 workers, all fail to load Pyodide
    s.start(engine=engine("H1"), jobs=[job("K", 2)],
            pyodide_url=base + "/tests/browser_compute_harness/nonexistent/")
    s.wait_read("error", "K")
    v = s.values()
    check("unavailable: Pyodide unreachable -> loading, unavailable once (with error text), then error for the pending job",
          [x.get("state", x["type"]) for x in v] == ["loading", "unavailable", "error"]
          and "Pyodide failed to load" in v[1]["reason"] and not s.events("boot"), v)
    s.close("unavailable/network")

    s = Session(browser, base, hwc=4)
    s.start(engine=engine("H1", "FAKE_IMPORT_ERROR"))
    s.wait("() => H.values.some(x => x.state === 'unavailable')")
    v = [x for x in s.values() if x.get("state") == "unavailable"][0]
    check("unavailable: engine import fails in every worker -> unavailable with the Python error",
          v["state"] == "unavailable" and "FAKE_IMPORT_ERROR" in v["reason"] and len(s.events("boot")) == 3, v)
    s.close("unavailable/import")

    s = Session(browser, base, hwc=4)                         # 3 workers, bc-1 fails
    s.start(engine=engine("H1", "FAKE_FAIL_WORKERS=bc-1"))
    s.wait_read("status", "ready")
    s.wait("() => H.ev('import').length === 2")              # bc-0 and bc-2 loaded the engine
    time.sleep(0.2)
    s.set_jobs([job("P", 9, delay_ms=10)])
    p = s.wait_read("result", "P")
    names = {r["name"] for r in s.events("run") if r["id"] == "P"}
    check("unavailable: one worker fails to init -> continue with the others",
          results_ok(p, "P", 9) and p["workers"] == 2 and names <= {"bc-0", "bc-2"}, (p["workers"], names))
    s.close("unavailable/partial")


def scenario_engine(browser, base):
    s = Session(browser, base, hwc=3)                         # -> 2 workers
    s.start(engine=engine("H1"))
    s.wait_read("status", "ready")
    s.set_jobs([job("P1", 4)])
    p1 = s.wait_read("result", "P1")
    old = {e["pid"] for e in s.events("boot")}
    s.set_jobs([job("P2", 10, delay_ms=60)])
    s.wait("() => H.ev('run').filter(e => e.id === 'P2').length >= 2")
    t_switch = s.now()
    s.js("e => { H.args.engine = e; H.render(); }", engine("H2"))
    p2 = s.wait_read("result", "P2", 10000)
    time.sleep(0.4)
    vals = s.values()
    order = [(v["type"], v.get("engine") or v.get("id")) for v in vals]
    check("engine: hash change -> 'ready' for H2, before the restarted job's result",
          order.index(("status", "H2")) < order.index(("result", "P2")), order)
    check("engine: job running at the switch restarts on the new engine (all results from H2, in order)",
          results_ok(p1, "P1", 4, "H1") and results_ok(p2, "P2", 10, "H2"))
    late = [e for e in s.events("alive") if e["pid"] in old and e["t"] > t_switch + 250]
    new = {e["pid"] for e in s.events("boot")} - old
    check("engine: old workers terminated, 2 fresh ones booted", not late and len(new) == 2, (len(late), len(new)))
    s.close("engine/change")

    s = Session(browser, base, hwc=3)
    files = engine("H1")["files"]
    s.start(engine={"hash": "H1", "files": None})
    st = s.wait_read("status", "loading")
    s.wait("() => H.ev('boot').length >= 1")
    check("engine: hash without files -> status 'loading' (engine null); Pyodide warms up meanwhile",
          st["engine"] is None and st["workers"] == 2, st)
    s.js("f => { H.args.engine.files = f; H.render(); }", files)
    s.wait_read("status", "ready")
    check("engine: files arrive -> ready", s.js("() => H.args.engine.files === null"))
    s.js("f => { H.args.engine.files = f; H.render(); }", files)   # server lost the 'ready'
    s.wait("() => H.values.filter(v => v.state === 'ready').length === 2")
    s.js("() => H.render()")
    time.sleep(0.4)
    check("engine: server re-sends files after reading 'ready' -> 'ready' repeated exactly once",
          sum(v.get("state") == "ready" for v in s.values()) == 2)
    s.close("engine/loading")


def scenario_capping(browser, base):
    cases = [
        ("8 cores, max_workers 3", dict(hwc=8), 3, 3),
        ("8 cores, max_workers 16", dict(hwc=8), 16, 7),
        ("phone (touch, 390x844)", dict(hwc=8, touch=5, screen=(390, 844)), 16, 2),
        ("userAgentData.mobile", dict(hwc=8, uad_mobile=True), 16, 2),
        ("touch but large screen", dict(hwc=8, touch=5, screen=(1024, 1366)), 16, 7),
        ("1 core", dict(hwc=1), 16, 1),
        ("hardwareConcurrency unknown", dict(hwc=0), 16, 1),
    ]
    for label, ov, max_workers, want in cases:
        s = Session(browser, base, **ov)
        s.start(max_workers=max_workers, engine=engine("H1"))
        ready = s.wait_read("status", "ready")
        s.wait("n => H.ev('import').length >= n", want)
        time.sleep(0.3)
        boots = len(s.events("boot"))
        check(f"capping: {label} -> {want} worker(s)", ready["workers"] == want and boots == want,
              (ready["workers"], boots))
        s.ctx.close()


def main() -> int:
    with sync_playwright() as pw:
        browser = pw.webkit.launch()
        print(f"WebKit {browser.version}, origin {BASE} (routed)", flush=True)
        for scenario in (scenario_core, scenario_outbox, scenario_cancel, scenario_errors,
                         scenario_unavailable, scenario_engine, scenario_capping):
            try:
                scenario(browser, BASE)
            except Exception as exc:  # noqa: BLE001 - report and continue with the next scenario
                check(f"{scenario.__name__} raised", False, repr(exc)[:400])
        browser.close()
    failed = [n for n, ok in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
