// Visual audit, run in the page: (opts) => report. opts: {root: css selector or null, dark: bool}
(opts) => {
  const root = opts.root ? document.querySelector(opts.root) : document.querySelector('[data-testid="stApp"]');
  if (!root) return {error: 'no root ' + opts.root};
  const out = {overflow: [], clipped: [], overlap: [], contrast: [], lightbg: [], rows: [], controls: {}, charts: [], imgs: [], docOverflow: null};
  const W = window.innerWidth;
  out.docOverflow = {doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    main: (() => { const m = document.querySelector('[data-testid="stMain"]'); return m ? m.scrollWidth - m.clientWidth : 0; })(),
    body: document.body.scrollWidth - document.body.clientWidth};
  const cs = (e) => getComputedStyle(e);
  const keyOf = (e) => { for (let n = e; n && n !== document.body; n = n.parentElement) {
      for (const c of n.classList || []) if (c.startsWith('st-key-')) return c; } return ''; };
  const tidOf = (e) => { for (let n = e; n && n !== document.body; n = n.parentElement) {
      const t = n.getAttribute && n.getAttribute('data-testid'); if (t) return t; } return ''; };
  const desc = (e) => {
    const cls = [...(e.classList || [])].filter(c => !c.startsWith('st-emotion') && !c.startsWith('e1')).slice(0, 2).join('.');
    const txt = (e.innerText || e.textContent || e.value || '').trim().replace(/\s+/g, ' ').slice(0, 45);
    return `${e.tagName.toLowerCase()}${cls ? '.' + cls : ''} <${tidOf(e)}> {${keyOf(e)}} "${txt}"`;
  };
  const parse = (s) => {
    if (!s || s === 'transparent') return [0, 0, 0, 0];
    let m = s.match(/rgba?\(([^)]+)\)/);
    if (m) { const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; }
    m = s.match(/color\(srgb ([^)]+)\)/);
    if (m) { const p = m[1].split(/[ \/]+/).filter(Boolean).map(Number); return [p[0] * 255, p[1] * 255, p[2] * 255, p.length > 3 ? p[3] : 1]; }
    return null;
  };
  const over = (top, bot) => { // top RGBA over bot RGB(A)
    const a = top[3] + bot[3] * (1 - top[3]);
    if (a === 0) return [0, 0, 0, 0];
    return [0, 1, 2].map(i => (top[i] * top[3] + bot[i] * bot[3] * (1 - top[3])) / a).concat([a]);
  };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
  const pageBg = parse(cs(document.querySelector('[data-testid="stApp"]') || document.body).backgroundColor);
  const bgOf = (e) => { // effective opaque background; unknown flag if gradient image met
    let stack = [], unknown = false;
    for (let n = e; n && n.nodeType === 1; n = n.parentElement) {
      const s = cs(n); const c = parse(s.backgroundColor);
      if (s.backgroundImage && s.backgroundImage !== 'none' && !s.backgroundImage.startsWith('url')) unknown = true;
      if (c && c[3] > 0) { stack.push(c); if (c[3] >= 0.999) break; }
    }
    let base = (pageBg && pageBg[3] > 0.5) ? pageBg : [255, 255, 255, 1];
    for (let i = stack.length - 1; i >= 0; i--) base = over(stack[i], base);
    return {c: base, unknown};
  };
  const opacityOf = (e) => { let o = 1; for (let n = e; n && n.nodeType === 1; n = n.parentElement) o *= parseFloat(cs(n).opacity || 1); return o; };
  const visible = (e) => { const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false;
    if (e.closest('.mc-odo, .mc-odo-sep, [class*="odo"]')) return false;
    for (let d = e.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) { { const sm = e.closest('summary'); if (!d.open && !(sm && sm.parentElement === d)) return false; } }
    for (let n = e; n && n.nodeType === 1; n = n.parentElement) { const s = cs(n);
      if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0) return false;
      if ((s.overflow === 'hidden' || s.overflow === 'clip') && n !== e) { const pr = n.getBoundingClientRect(); if (pr.height < 2 || pr.width < 2) return false; } }
    return true; };
  const inChart = (e) => !!e.closest('.js-plotly-plot, canvas, [data-testid="stDataFrame"], [data-testid="stDataEditor"], .vega-embed');
  const all = [...root.querySelectorAll('*')].filter(e => !['SCRIPT', 'STYLE', 'PATH', 'DEFS', 'G', 'CLIPPATH'].includes(e.tagName.toUpperCase()));
  const vis = new Map(); const isVis = (e) => { if (!vis.has(e)) vis.set(e, visible(e)); return vis.get(e); };
  const textBearing = (e) => { for (const n of e.childNodes) if (n.nodeType === 3 && n.textContent.trim().length) return true; return false; };
  const tile = (e) => e.closest('[class*="st-key-mc-tile"], [data-testid="stSidebarContent"]') || document.querySelector('[data-testid="stMain"]');
  const seen = new Set();
  const add = (list, key, item) => { if (seen.has(key)) return; seen.add(key); list.push(item); };

  for (const e of all) {
    if (!isVis(e)) continue;
    const s = cs(e), r = e.getBoundingClientRect();
    const isSvg = e instanceof SVGElement;
    // --- overflow vs viewport / tile
    if (!isSvg && !e.closest('.js-plotly-plot')) {
      let clipper = null;
      for (let n = e.parentElement; n && n !== document.body; n = n.parentElement) { const ps = cs(n);
        if (ps.overflowX !== 'visible') { clipper = n; break; } }
      const cr = clipper ? clipper.getBoundingClientRect() : {left: 0, right: W};
      const cx = clipper ? cs(clipper).overflowX : 'visible';
      const beyondV = r.right > W + 1.5 || r.left < -1.5;
      if (beyondV && !(clipper && (cr.right <= W + 1.5) && (r.left >= cr.left - 1.5 && r.right <= cr.right + 1.5)) ) {
        if (!(clipper && (cx === 'auto' || cx === 'scroll'))) add(out.overflow, 'v' + desc(e), {kind: 'viewport', w: Math.round(r.width), l: Math.round(r.left), r: Math.round(r.right), d: desc(e)});
      } else if (clipper && cx !== 'auto' && cx !== 'scroll' && !['stSidebarContent'].includes(tidOf(clipper))) {
        if ((r.right > cr.right + 1.5 || r.left < cr.left - 1.5) && textBearing(e) && s.position !== 'absolute' && s.position !== 'fixed')
          add(out.overflow, 'c' + desc(e), {kind: 'clipped-by-ancestor', ov: Math.round(Math.max(r.right - cr.right, cr.left - r.left)), d: desc(e), by: desc(clipper)});
      }
      const t = tile(e);
      if (t && s.position !== 'absolute' && s.position !== 'fixed' && s.position !== 'sticky') {
        const tr = t.getBoundingClientRect();
        if ((r.right > tr.right + 1.5 || r.left < tr.left - 1.5) && !clipper) add(out.overflow, 't' + desc(e), {kind: 'beyond-tile', ov: Math.round(Math.max(r.right - tr.right, tr.left - r.left)), d: desc(e)});
      }
    }
    // --- clipped text
    if ((textBearing(e) || e.tagName === 'INPUT' || e.tagName === 'TEXTAREA') && !isSvg) {
      const hiddenX = s.overflowX !== 'visible' && s.overflowX !== 'auto' && s.overflowX !== 'scroll';
      if (e.scrollWidth > e.clientWidth + 1 && (hiddenX || s.textOverflow === 'ellipsis' || e.tagName === 'INPUT') && e.clientWidth > 0)
        add(out.clipped, 'x' + desc(e), {kind: s.textOverflow === 'ellipsis' ? 'ellipsis' : 'clip-x', sw: e.scrollWidth, cw: e.clientWidth, d: desc(e)});
      const hiddenY = s.overflowY === 'hidden' || s.overflowY === 'clip';
      if (e.scrollHeight > e.clientHeight + 2 && hiddenY && e.clientHeight > 0 && !e.closest('[data-mc-clamp]'))
        add(out.clipped, 'y' + desc(e), {kind: 'clip-y', sh: e.scrollHeight, ch: e.clientHeight, d: desc(e)});
      // text wider than its own line box inside nowrap
      if (s.whiteSpace === 'nowrap' && e.scrollWidth > e.clientWidth + 1 && !hiddenX && e.parentElement && e.parentElement.scrollWidth > e.parentElement.clientWidth + 1)
        add(out.clipped, 'n' + desc(e), {kind: 'nowrap-spill', d: desc(e)});
    }
    // --- contrast
    if (textBearing(e) && !e.disabled && !e.closest('[disabled], [aria-disabled="true"]')) {
      const col = parse(isSvg ? s.fill : s.color); if (!col) continue;
      const op = opacityOf(e);
      let {c: bg, unknown} = bgOf(isSvg ? (e.closest('svg') || e).parentElement : e);
      let gradStops = null;
      if (unknown) { for (let n = e; n && n.nodeType === 1; n = n.parentElement) { const bi = cs(n).backgroundImage; if (bi && /gradient/.test(bi)) { const st = (bi.match(/rgba?\([^)]+\)/g) || []).map(parse).filter(x => x && x[3] > 0.9); if (st.length) { gradStops = st; break; } } } }
      const fg = over([col[0], col[1], col[2], col[3] * op], bg);
      const fs = parseFloat(s.fontSize), fw = parseInt(s.fontWeight) || 400;
      const large = fs >= 24 || (fs >= 18.66 && fw >= 700);
      const need = large ? 3 : 4.5; let cr = ratio(fg, bg);
      if (gradStops) cr = Math.min(...gradStops.map(g => ratio(fg, g)));
      if (cr < need) add(out.contrast, 'c' + desc(e) + Math.round(cr * 10), {cr: +cr.toFixed(2), need, fs, fg: fg.slice(0, 3).map(Math.round).join(','), bg: bg.slice(0, 3).map(Math.round).join(','), unk: unknown, svg: isSvg, d: desc(e)});
    }
    // --- hard-coded light bg in dark
    if (opts.dark && !isSvg && !inChart(e) && !['IMG', 'VIDEO'].includes(e.tagName)) {
      const c = parse(s.backgroundColor);
      if (c && c[3] > 0.5 && r.width * r.height > 150 && lum(c) > 0.45 && !(c[1] - c[0] > 100)) add(out.lightbg, 'l' + desc(e), {bg: c.slice(0, 3).map(Math.round).join(','), a: +c[3].toFixed(2), d: desc(e)});
      if (s.backgroundImage && /gradient/.test(s.backgroundImage) && r.width * r.height > 150) {
        const cols = (s.backgroundImage.match(/rgba?\([^)]+\)/g) || []).map(parse).filter(x => x && x[3] > 0.5 && lum(x) > 0.6);
        if (cols.length) add(out.lightbg, 'g' + desc(e), {bg: 'gradient ' + s.backgroundImage.slice(0, 80), d: desc(e)});
      }
    }
    if (e.tagName === 'IMG' && r.width > 40) out.imgs.push({w: Math.round(r.width), h: Math.round(r.height), src: (e.src || '').slice(0, 50), d: desc(e)});
  }
  // --- plotly chart colours (text vs the tile it sits on, plot backgrounds)
  for (const p of root.querySelectorAll('.js-plotly-plot')) {
    if (!isVis(p)) continue;
    const {c: bg} = bgOf(p);
    for (const t of p.querySelectorAll('text')) {
      const col = parse(cs(t).fill); if (!col) continue;
      const st = cs(t); if (st.visibility === 'hidden' || parseFloat(st.opacity) === 0) continue;
      const cr = ratio(over([col[0], col[1], col[2], col[3] * (parseFloat(st.opacity) || 1)], bg), bg);
      if (cr < 4.5 && (t.textContent || '').trim()) add(out.charts, 'ct' + (t.textContent || '').slice(0, 20) + keyOf(p), {cr: +cr.toFixed(2), txt: (t.textContent || '').slice(0, 25), fill: st.fill, bg: bg.slice(0, 3).map(Math.round).join(','), d: desc(p)});
    }
    for (const b of p.querySelectorAll('.main-svg, rect.bg, .legend .bg, .hoverlayer .bg')) {
      const f = b.tagName === 'rect' ? cs(b).fill : cs(b).backgroundColor; const c = parse(f);
      if (opts.dark && c && c[3] > 0.4 && lum(c) > 0.4) add(out.charts, 'cb' + keyOf(p) + f, {bgfill: f, d: desc(p) + ' / ' + b.getAttribute('class')});
    }
  }
  // --- rows: controls with different height / misaligned
  const ctrl = (c) => [...c.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([role=slider]), [data-baseweb="select"], button[data-testid^="stBaseButton"]')].filter(x => isVis(x) && x.getBoundingClientRect().height >= 28 && !x.closest('[data-baseweb="select"] input'));
  for (const row of root.querySelectorAll('[data-testid="stHorizontalBlock"], [class*="st-key-"]')) {
    if (!isVis(row)) continue; const s = cs(row);
    if (!(s.display === 'flex' && s.flexDirection === 'row') || s.flexWrap === 'wrap' && false) continue;
    const kids = [...row.children].filter(isVis); if (kids.length < 2) continue;
    const tops = kids.map(k => k.getBoundingClientRect().top);
    const lefts = kids.map(k => k.getBoundingClientRect().left); if (Math.max(...lefts) - Math.min(...lefts) < 10) continue; // stacked
    if (Math.max(...tops) - Math.min(...tops) > 400) continue; // wrapped / stacked
    const items = kids.map(k => { const cc = ctrl(k)[0]; if (!cc) return null; const rr = (cc.closest('[data-baseweb="input"], [data-baseweb="select"]') || cc).getBoundingClientRect(); return {h: rr.height, t: rr.top, b: rr.bottom, w: rr.width}; }).filter(Boolean);
    if (items.length < 2) continue;
    const hs = items.map(i => i.h), ts = items.map(i => i.t), bs = items.map(i => i.b);
    const dh = Math.max(...hs) - Math.min(...hs), dt = Math.max(...ts) - Math.min(...ts), db = Math.max(...bs) - Math.min(...bs);
    if (dh > 2 || (dt > 3 && db > 3)) add(out.rows, 'r' + desc(row), {dh: Math.round(dh), dt: Math.round(dt), db: Math.round(db), hs: hs.map(Math.round), d: desc(row)});
  }
  // --- overlapping text leaves
  const leaves = all.filter(e => isVis(e) && textBearing(e) && !(e instanceof SVGElement) && !inChart(e) && cs(e).display !== 'inline' && !e.closest('[data-testid="stSidebarCollapseButton"], .mc-show-results'));
  const rects = leaves.map(e => e.getBoundingClientRect());
  for (let i = 0; i < leaves.length; i++) for (let j = i + 1; j < leaves.length; j++) {
    const a = rects[i], b = rects[j];
    const iw = Math.min(a.right, b.right) - Math.max(a.left, b.left), ih = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (iw > 3 && ih > 3 && !leaves[i].contains(leaves[j]) && !leaves[j].contains(leaves[i])) {
      // ignore if one is a pseudo/abs overlay by design: report only when both in normal flow
      const pa = cs(leaves[i]).position, pb = cs(leaves[j]).position;
      add(out.overlap, 'o' + desc(leaves[i]) + desc(leaves[j]), {iw: Math.round(iw), ih: Math.round(ih), a: desc(leaves[i]), b: desc(leaves[j]), pos: pa + '/' + pb});
    }
  }
  // --- typed box beside a slider must show the slider's value
  out.boxes = [];
  for (const c of root.querySelectorAll('[class*="st-key-sbx-"]')) {
    if (!isVis(c)) continue;
    const tv = c.querySelector('[data-testid="stSliderThumbValue"]'), inp = c.querySelector('input[type=number], input[inputmode]');
    if (!tv || !inp) continue;
    const a = parseFloat(tv.innerText.replace(/[^0-9.\-]/g, '')), b2 = parseFloat(inp.value);
    if (Math.abs(a - b2) > 1e-6) out.boxes.push({k: keyOf(c), slider: tv.innerText, box: inp.value});
  }
  // --- control sizing inventory
  for (const [sel, kind] of [['[data-baseweb="input"]', 'input'], ['[data-baseweb="select"] > div', 'select'], ['button[data-testid="stBaseButton-secondary"]', 'btn-secondary'], ['button[data-testid="stBaseButton-primary"]', 'btn-primary'], ['button[data-testid="stBaseButton-tertiary"]', 'btn-tertiary'], ['button[data-testid^="stBaseButton-segmented"], [data-testid="stPills"] button, [data-testid="stSegmentedControl"] button', 'pill']]) {
    for (const e of root.querySelectorAll(sel)) { if (!isVis(e)) continue; const r = e.getBoundingClientRect(), s = cs(e);
      const k = `${kind} h=${Math.round(r.height)} r=${s.borderTopLeftRadius}`; (out.controls[k] = out.controls[k] || []).push(keyOf(e) || tidOf(e)); }
  }
  for (const e of root.querySelectorAll('[class*="st-key-mc-tile"], [data-testid="stVerticalBlockBorderWrapper"]')) {
    if (!isVis(e)) continue; const s = cs(e); if (s.borderTopLeftRadius === '0px') continue;
    const k = `${e.className.includes('mc-tile') ? 'tile' : 'card'} r=${s.borderTopLeftRadius}`; (out.controls[k] = out.controls[k] || []).push(keyOf(e));
  }
  for (const k in out.controls) { const arr = out.controls[k]; out.controls[k] = {n: arr.length, ex: [...new Set(arr)].slice(0, 4)}; }
  return out;
}
