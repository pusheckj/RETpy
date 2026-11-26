// Runs ui/components/file_reader/index.html's script against a tiny fake DOM and
// prints what it posted to its parent as JSON. Usage: node run.js <index.html> <scenario.json>
//
// scenario: {args: {...render args}, steps: [ {pick: {name, size, text}} | {drop: {...}} | {clear: true}
//            | {render: {...args}} | {fail_read: true, pick: {...}} ]}
// output:   {posted: [msg...], ui: {id: {hidden, text}}}
"use strict";
const fs = require("fs");

const [htmlPath, scenarioPath] = process.argv.slice(2);
const html = fs.readFileSync(htmlPath, "utf8");
const scenario = JSON.parse(fs.readFileSync(scenarioPath, "utf8"));
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];

const posted = [];
const winListeners = {};
const elements = {};

function makeEl(id) {
  const listeners = {};
  const el = {
    id, hidden: false, textContent: "", title: "", value: "", files: null, attrs: {},
    classList: { add() {}, remove() {} },
    style: { setProperty() {} },
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(name, fn) { (listeners[name] = listeners[name] || []).push(fn); },
    fire(name, ev) { (listeners[name] || []).forEach((fn) => fn(ev || {})); },
    getBoundingClientRect() { return { height: 100 }; },
  };
  return el;
}
const document = {
  getElementById(id) { return (elements[id] = elements[id] || makeEl(id)); },
  documentElement: { style: { setProperty() {} } },
  body: {},
};

let readerFails = false;
class FileReader {
  readAsText(file) {
    setImmediate(() => {
      if (readerFails) { this.onerror && this.onerror(new Error("boom")); }
      else { this.result = file.text; this.onload && this.onload(); }
    });
  }
}

const parent = { postMessage(msg) { posted.push(msg); } };
const window = {
  location: { origin: "http://localhost:8501" },
  parent,
  matchMedia() { return { matches: false }; },
  getComputedStyle() { return { getPropertyValue() { return ""; }, fontFamily: "" }; },
  addEventListener(name, fn) { (winListeners[name] = winListeners[name] || []).push(fn); },
};
parent.document = document;

async function main() {
  new Function("window", "document", "FileReader", "Date", script)(window, document, FileReader, Date);
  const send = (args) => (winListeners.message || []).forEach((fn) =>
    fn({ source: parent, origin: "http://localhost:8501", data: { type: "streamlit:render", args } }));
  send(scenario.args || {});
  const tick = () => new Promise((r) => setTimeout(r, 5));
  for (const step of scenario.steps || []) {
    if (step.render) send(step.render);
    if (step.fail_read) readerFails = true;
    if (step.pick) {
      const f = step.pick;
      elements.f.files = [{ name: f.name, size: f.size, text: f.text }];
      elements.f.fire("change");
      await tick();
    }
    if (step.drop) {
      const f = step.drop;
      elements.box.fire("drop", { preventDefault() {}, dataTransfer: { files: [{ name: f.name, size: f.size, text: f.text }] } });
      await tick();
    }
    if (step.clear) elements.clear.fire("click");
    if (step.fail_read) readerFails = false;
  }
  const ui = {};
  for (const id of ["file", "hint", "choose", "name", "size", "err", "label"]) {
    const e = elements[id];
    if (e) ui[id] = { hidden: !!e.hidden, text: e.textContent };
  }
  ui.inputValue = elements.f ? elements.f.value : null;
  ui.accept = elements.f ? elements.f.attrs.accept : null;
  process.stdout.write(JSON.stringify({ posted, ui }));
}
main().catch((e) => { console.error(e); process.exit(1); });
