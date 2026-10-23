/*
 * Web Worker for ui/components/browser_compute/index.html (classic worker,
 * plain JS, no build step). Hosts one Pyodide interpreter with the engine
 * package `retirement_sim` and runs engine calls in it, so Python never runs
 * on the page's main thread.
 *
 * Messages in (handled strictly one after another):
 *   {type:"init", indexURL}               load Pyodide + numpy from indexURL
 *   {type:"engine", hash, files}          write the engine sources, import mc_jobs
 *   {type:"run", key, id, index, json?}   browser_load(id, json) if json is given,
 *                                         then browser_run(id, index)
 * Messages out:
 *   {type:"booted"}                       Pyodide + numpy loaded
 *   {type:"engine_ready", hash}
 *   {type:"init_error", error}            this worker can't run anything
 *   {type:"done", key, index, ok:true, text, count?}
 *   {type:"done", key, index, ok:false, error, fatal}
 *
 * mc_jobs keeps only the 4 most recent jobs per worker. That is enough: the
 * page hands out calls first-in first-out, so a worker never goes back to an
 * older job once it has started a newer one.
 */
"use strict";

const ROOT = "/home/pyodide";
const ERROR_MAX = 4000;
const SAFE_PATH = /^[A-Za-z0-9_.-]+(\/[A-Za-z0-9_.-]+)*$/;

let pyodide = null;
let loadJob = null;   // retirement_sim.mc_jobs.browser_load
let runCall = null;   // retirement_sim.mc_jobs.browser_run
let broken = null;    // why this worker can't run, once known
let chain = Promise.resolve();

self.onmessage = function (event) {
  const msg = event.data || {};
  chain = chain.then(() => handle(msg)).catch((e) => {
    self.postMessage({ type: "init_error", error: "worker failure: " + text(e) });
  });
};

function text(e) {
  const s = String((e && (e.message || e.name)) || e || "unknown error");
  return s.length > ERROR_MAX ? "…" + s.slice(-ERROR_MAX) : s;   // a traceback ends with the error
}

function handle(msg) {
  if (msg.type === "init") return init(msg.indexURL);
  if (msg.type === "engine") return engine(msg.hash, msg.files);
  if (msg.type === "run") return run(msg);
  return undefined;
}

async function init(indexURL) {
  try {
    importScripts(indexURL + "pyodide.js");
    pyodide = await self.loadPyodide({ indexURL: indexURL });
    await pyodide.loadPackage("numpy");
    pyodide.runPython("import numpy");
    self.postMessage({ type: "booted" });
  } catch (e) {
    pyodide = null;
    broken = "Pyodide failed to load from " + indexURL + ": " + text(e);
    self.postMessage({ type: "init_error", error: broken });
  }
}

function engine(hash, files) {
  if (!pyodide || runCall) return;      // init failure already reported / engine already loaded
  try {
    for (const rel of Object.keys(files || {})) {
      if (typeof files[rel] !== "string" || !SAFE_PATH.test(rel)
          || rel.split("/").some((part) => part === "." || part === "..")) {
        throw new Error("bad engine file entry: " + rel);
      }
      const path = ROOT + "/" + rel;
      pyodide.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
      pyodide.FS.writeFile(path, files[rel]);
    }
    pyodide.runPython([
      "import importlib, sys",
      "if " + JSON.stringify(ROOT) + " not in sys.path:",
      "    sys.path.insert(0, " + JSON.stringify(ROOT) + ")",
      "importlib.invalidate_caches()",
    ].join("\n"));
    const mod = pyodide.pyimport("retirement_sim.mc_jobs");
    loadJob = mod.browser_load;           // keep the proxies: one each, not one per call
    runCall = mod.browser_run;
    self.postMessage({ type: "engine_ready", hash: hash });
  } catch (e) {
    loadJob = runCall = null;
    broken = "engine failed to load: " + text(e);
    self.postMessage({ type: "init_error", error: broken });
  }
}

function isPythonError(e) {
  // Pyodide's PythonError carries the Python exception class name in .type.
  return !!e && (e.name === "PythonError" || typeof e.type === "string");
}

function run(msg) {
  const reply = { type: "done", key: msg.key, index: msg.index };
  try {
    if (!runCall) throw new Error(broken || "engine not loaded");
    if (typeof msg.json === "string") reply.count = Number(loadJob(msg.id, msg.json));
    reply.text = String(runCall(msg.id, msg.index));
    reply.ok = true;
  } catch (e) {
    reply.ok = false;
    reply.error = text(e);
    // A Python exception leaves the interpreter usable; anything else (out of
    // memory, a WebAssembly trap, "Pyodide already fatally failed") does not.
    reply.fatal = !isPythonError(e);
  }
  self.postMessage(reply);
}
