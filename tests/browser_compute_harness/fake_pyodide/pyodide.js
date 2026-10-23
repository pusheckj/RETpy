/*
 * FAKE Pyodide for tests/browser_compute_harness only (the real one can't be
 * downloaded here). Same surface the component's worker.js uses:
 * loadPyodide({indexURL}) -> {loadPackage, FS.mkdirTree/writeFile, runPython,
 * pyimport("retirement_sim.mc_jobs") -> {browser_load, browser_run}}.
 *
 * It checks what a real interpreter would need (engine files at
 * /home/pyodide/retirement_sim/..., /home/pyodide on sys.path, numpy loaded)
 * and reports activity on BroadcastChannel("fake-pyodide") so the harness page
 * can see boots, loads, runs and heartbeats (a terminated worker goes quiet).
 *
 * Failure switches:
 *   job json "fail_index": i   browser_run(i) raises ValueError (PythonError)
 *   job json "fatal_index": i  browser_run(i) throws a non-Python RangeError
 *   job json not JSON          browser_load raises JSONDecodeError
 *   "FAKE_IMPORT_ERROR" in mc_jobs.py           import fails in every worker
 *   "FAKE_FAIL_WORKERS=bc-1,bc-2" in mc_jobs.py  import fails in those workers
 * browser_run returns JSON.stringify({i, id, w, pid, eng}) after busy-waiting
 * job json "delays"[i] or "delay_ms" (default 5-25 ms random). eng = ENGINE_TAG=<x>
 * in mc_jobs.py.
 */
(function () {
  "use strict";
  const PID = Math.random().toString(36).slice(2, 10);
  const NAME = self.name || "?";
  const channel = typeof BroadcastChannel === "function" ? new BroadcastChannel("fake-pyodide") : null;

  function say(ev, extra) {
    if (channel) {
      channel.postMessage(Object.assign(
        { ev: ev, pid: PID, name: NAME, t: performance.timeOrigin + performance.now() }, extra || {}));
    }
  }

  function pyErr(type, message) {
    const e = new Error("Traceback (most recent call last):\n  File \"<fake>\", line 1\n" + type + ": " + message);
    e.name = "PythonError";
    e.type = type;
    return e;
  }

  function busy(ms) {
    const end = performance.now() + ms;
    while (performance.now() < end) { /* burn CPU like a real call */ }
  }

  self.loadPyodide = async function (opts) {
    const indexURL = opts && opts.indexURL;
    if (typeof indexURL !== "string" || !indexURL.endsWith("/")) throw new Error("fake: indexURL must end with '/'");
    say("boot", { indexURL: indexURL });
    await new Promise((r) => setTimeout(r, 80));            // "download + compile"
    setInterval(() => say("alive"), 100);

    const dirs = new Set(["/", "/home", "/home/pyodide"]);
    const files = new Map();
    const jobs = new Map();
    let numpy = false;
    let onPath = false;
    const MC = "/home/pyodide/retirement_sim/mc_jobs.py";

    const mcJobs = {
      browser_load(id, json) {
        let job;
        try { job = JSON.parse(json); } catch (e) { throw pyErr("JSONDecodeError", String(e.message)); }
        if (!job || !Array.isArray(job.calls)) throw pyErr("KeyError", "'calls'");
        jobs.set(id, job);
        while (jobs.size > 4) jobs.delete(jobs.keys().next().value);   // like mc_jobs._JOBS
        say("load", { id: id });
        return job.calls.length;
      },
      browser_run(id, index) {
        const job = jobs.get(id);
        if (!job) throw pyErr("KeyError", JSON.stringify(id));
        say("run", { id: id, i: index });
        if (job.fail_index === index) throw pyErr("ValueError", "boom at call " + index);
        if (job.fatal_index === index) throw new RangeError("fake fatal: memory access out of bounds");
        busy(Array.isArray(job.delays) ? Number(job.delays[index])
             : job.delay_ms != null ? Number(job.delay_ms) : 5 + Math.random() * 20);
        const tag = /ENGINE_TAG=(\w+)/.exec(files.get(MC) || "");
        say("ran", { id: id, i: index });
        return JSON.stringify({ i: index, id: id, w: NAME, pid: PID, eng: tag ? tag[1] : null });
      },
    };

    return {
      FS: {
        mkdirTree(path) {
          let cur = "";
          for (const part of String(path).split("/").filter(Boolean)) { cur += "/" + part; dirs.add(cur); }
        },
        writeFile(path, data) {
          const dir = path.slice(0, path.lastIndexOf("/")) || "/";
          if (!dirs.has(dir)) throw new Error("fake FS: no such directory " + dir);
          files.set(path, String(data));
        },
      },
      async loadPackage(name) {
        await new Promise((r) => setTimeout(r, 20));
        if (name === "numpy") numpy = true;
      },
      runPython(code) {
        if (/^\s*import numpy\s*$/.test(code)) {
          if (!numpy) throw pyErr("ModuleNotFoundError", "No module named 'numpy'");
          return undefined;
        }
        if (code.includes("sys.path") && code.includes('"/home/pyodide"')) onPath = true;
        return undefined;
      },
      pyimport(name) {
        if (name !== "retirement_sim.mc_jobs") throw pyErr("ModuleNotFoundError", "No module named '" + name + "'");
        if (!onPath) throw pyErr("ModuleNotFoundError", "No module named 'retirement_sim' (/home/pyodide not on sys.path)");
        if (!files.has("/home/pyodide/retirement_sim/__init__.py") || !files.has(MC)) {
          throw pyErr("ModuleNotFoundError", "No module named 'retirement_sim.mc_jobs'");
        }
        if (!numpy) throw pyErr("ModuleNotFoundError", "No module named 'numpy'");
        const src = files.get(MC);
        if (src.includes("FAKE_IMPORT_ERROR")) throw pyErr("ImportError", "FAKE_IMPORT_ERROR in engine");
        const failing = /FAKE_FAIL_WORKERS=([\w,-]+)/.exec(src);
        if (failing && failing[1].split(",").includes(NAME)) throw pyErr("MemoryError", "FAKE_FAIL_WORKERS hit " + NAME);
        say("import", { eng: (/ENGINE_TAG=(\w+)/.exec(src) || [])[1] || null });
        return mcJobs;
      },
    };
  };
})();
