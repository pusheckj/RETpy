// Run BiggerPockets Money's BPMTaxEngine.compute on a list of fixtures.
//
// Usage: node bpm_runner.mjs <calc_tax.html> <fixtures.json> <results.json>
//
//   <calc_tax.html>  the BPM Income Tax Projection Calculator page (v1.11.2); read only.
//   <fixtures.json>  [{ "id": "...", "bpm": { ...BPMTaxEngine.compute input... },
//                       "marginals": false }, ...]
//   <results.json>   written: [{ "id", "ok", "result" | "error" }, ...]
//
// The engine is a pure IIFE (`const BPMTaxEngine = (function(){...})();`). It is cut out
// of the page by brace matching and run in a vm sandbox with no DOM, the same method as
// the extractor that ships with the BPM raw-data folder. Nothing is written next to the
// page. Dev tool only: it is not part of the app.
import fs from 'node:fs';
import vm from 'node:vm';

const [, , SRC, FIXTURES, OUT] = process.argv;
if (!SRC || !FIXTURES || !OUT) {
  console.error('usage: node bpm_runner.mjs <calc_tax.html> <fixtures.json> <results.json>');
  process.exit(2);
}

const html = fs.readFileSync(SRC, 'utf8');
const script = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));

function matchBraces(src, startIdx) {
  let depth = 0, inS = null, esc = false, lineC = false, blockC = false;
  for (let i = startIdx; i < src.length; i++) {
    const c = src[i], n = src[i + 1];
    if (lineC) { if (c === '\n') lineC = false; continue; }
    if (blockC) { if (c === '*' && n === '/') { blockC = false; i++; } continue; }
    if (inS) {
      if (esc) { esc = false; continue; }
      if (c === '\\') { esc = true; continue; }
      if (c === inS) inS = null;
      continue;
    }
    if (c === '/' && n === '/') { lineC = true; continue; }
    if (c === '/' && n === '*') { blockC = true; continue; }
    if (c === "'" || c === '"' || c === '`') { inS = c; continue; }
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return i; }
  }
  return -1;
}

const start = script.indexOf('const BPMTaxEngine = (function(){');
if (start < 0) throw new Error('BPMTaxEngine IIFE not found: is this the BPM tax calculator page?');
const open = script.indexOf('{', script.indexOf('(function()', start));
const close = matchBraces(script, open);
if (close < 0) throw new Error('could not match the engine braces');
const end = script.indexOf(')();', close) + 4;
const ctx = vm.createContext({ console });
vm.runInContext(script.slice(start, end) + '\n;globalThis.__E = BPMTaxEngine;', ctx, { timeout: 10000 });
const E = ctx.__E;

const fixtures = JSON.parse(fs.readFileSync(FIXTURES, 'utf8'));
const out = fixtures.map((fx) => {
  try {
    const r = E.compute(fx.bpm, { skipMarginal: !fx.marginals });
    // Plain copy (the vm's objects are from another realm).
    return { id: fx.id, ok: true, result: JSON.parse(JSON.stringify(r)) };
  } catch (e) {
    return { id: fx.id, ok: false, error: String(e && e.stack || e) };
  }
});
fs.writeFileSync(OUT, JSON.stringify(out));
console.log(`bpm_runner: ${out.filter((o) => o.ok).length}/${out.length} fixtures computed`);
