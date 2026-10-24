"""Animation & interaction layer for the app (performance-optimized).

Two parts, injected once per run after the theme CSS:

1. CSS (via st.markdown, into the app document) — pure-CSS effects: hover lifts,
   chart glow, sidebar pill slide, count-up flash + pulse ring, button ripple
   shell, sliding segmented indicator, slider/toggle polish, tooltip + toast
   slide, spinner/skeleton, celebration glow, and the one-time .mc-entrance.
2. JS engine (via components.html, reaching window.parent.document) — behavior
   that must react to reruns.

PERFORMANCE DESIGN (after profiling stutter):
- Count-up uses ONE shared requestAnimationFrame ticker for all metrics, and
  writes the value via the text node's nodeValue (a characterData change) rather
  than textContent (a childList change) — so it does NOT trigger the page's
  MutationObservers every frame. Values are keyed by label so a metric only
  animates on first appearance or when it actually CHANGES.
- Entrance runs ONCE per session on the section tiles (staggered). The old broad
  CSS entrance replayed on ~59 elements every rerun; that is gone.
- The segmented-control indicator is CHANGE-DETECTED (only writes styles when the
  active segment moves) and repositioned via a ResizeObserver + click handler —
  no polling interval, so it adds ~zero idle work.
- No permanent will-change (it was leaking 34 compositor layers).
- Confetti has a cooldown + cleans up any prior canvas.
- Honors prefers-reduced-motion (values snap, no entrance/confetti/ripple).
"""
from __future__ import annotations

_ANIM_CSS = """
<style id="mc-anim-css">
/* ---------------- Hover & press (⑤⑦⑧) ----------------
   GPU-friendly: transform lift + a one-shot border-color tint for focus (a
   border repaint on ONE hovered element is cheap; the box-shadow SPREAD that
   caused stutter stays off). */
[data-testid="stPlotlyChart"]{ transition: transform .18s ease, border-color .25s ease, box-shadow .3s ease; }
[data-testid="stPlotlyChart"]:hover{ transform: translateY(-2px); border-color: rgba(13,148,136,.45) !important;
  box-shadow: 0 16px 34px rgba(15,118,110,.20), 0 0 0 4px rgba(94,234,212,.16) !important; }
.mc-stat-card{ transition: transform .18s ease; position: relative; }
/* cursor-following sheen (⑤) — shown while tilting; --mx/--my set by the tilt handler */
.mc-stat-card::after{ content:""; position:absolute; inset:0; border-radius:16px; pointer-events:none; opacity:0;
  background: radial-gradient(200px 160px at var(--mx,50%) var(--my,0%), rgba(94,234,212,.30), transparent 70%);
  transition: opacity .35s ease-out; z-index:0; }
.mc-stat-card.mc-tilting::after{ opacity:1; }
.mc-stat-card > *{ position: relative; z-index:1; }
section[data-testid="stSidebar"] [data-testid="stExpander"]{ transition: transform .15s ease; }
@media (hover: hover){ section[data-testid="stSidebar"] [data-testid="stExpander"]:hover{ transform: translateX(4px); } }
section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderIcon"]{ transition: transform .3s cubic-bezier(.22,1,.36,1); }
@media (hover: hover){ section[data-testid="stSidebar"] [data-testid="stExpander"]:hover [data-testid="stExpanderIcon"]{ transform: scale(1.14); } }

/* Primary / Run button (⑥): play-icon + label nudge on hover, gentle press on
   active — transform only. */
.stButton > button[kind="primary"] > *, [data-testid="stFormSubmitButton"] > button > *{
  transition: transform .3s cubic-bezier(.22,1,.36,1); }
.stButton > button[kind="primary"]:hover > *, [data-testid="stFormSubmitButton"] > button:hover > *{
  transform: translateX(3px); }
.stButton > button:active{ transform: translateY(1px) scale(.985); }

/* Delta-arrow pop (⑪): small scale-overshoot when a metric delta renders — on
   native st.metric deltas AND our custom "vs today" badge (.mc-delta). */
[data-testid="stMetricDelta"], .mc-delta{ animation: mcDeltaPop .45s cubic-bezier(.34,1.56,.64,1) both; transform-origin: left center; }
@keyframes mcDeltaPop{ 0%{opacity:0; transform:scale(.6) translateY(3px)} 60%{opacity:1} 100%{opacity:1; transform:none} }
/* "vs today" delta badge: pill under a stat card value, colored by direction. */
.mc-delta{ display:inline-flex; align-items:center; gap:3px; margin-top:6px;
  font-size:12.5px; font-weight:700; line-height:1; padding:3px 8px; border-radius:999px; }
.mc-delta.mc-delta-up{ color:#0f766e; background:rgba(13,148,136,.12); }
.mc-delta.mc-delta-down{ color:#b91c1c; background:rgba(220,38,38,.10); }

/* ③ Cascading rows: KPI stat cards reveal one-by-one (per-card animation-delay
   set inline in the component). Fires on render — page load and view toggle.
   fill=backwards (NOT both): holds the hidden start state during the stagger
   delay, then reverts to base after — so NO identity-transform lingers to
   create a stacking context that would trap the cards' hover tooltips. */
.mc-cascade{ animation: mcCascadeIn .5s cubic-bezier(.22,.61,.36,1) backwards; }
@keyframes mcCascadeIn{ 0%{ opacity:0; transform: translateY(12px); } 100%{ opacity:1; transform:none; } }

/* Progress bar (⑲): smooth eased width fill (in addition to the moving stripes). */
.stProgress > div > div > div{ transition: width .35s cubic-bezier(.22,.61,.36,1); }

/* ---------------- Count-up flash + pulse ring (⑨⑩⑫㉕) ---------------- */
.mc-flash{ animation: mcFlash .8s ease-out; border-radius:8px; }
@keyframes mcFlash{ 0%{background:rgba(13,148,136,.18)} 100%{background:transparent} }
.mc-pulse{ position:relative; }
/* transform+opacity ring (compositor) instead of an animated box-shadow spread */
.mc-pulse::after{ content:""; position:absolute; inset:0; border-radius:16px; pointer-events:none;
  border:2px solid rgba(13,148,136,.5); opacity:0; animation: mcPulseRing .8s ease-out; }
@keyframes mcPulseRing{ 0%{opacity:.7; transform:scale(1)} 100%{opacity:0; transform:scale(1.05)} }

/* ---------------- Button ripple (⑥) ---------------- */
.stButton > button, [data-testid="stFormSubmitButton"] > button, button[kind]{ position: relative; overflow: hidden; }
.mc-ripple{ position:absolute; border-radius:50%; background:rgba(255,255,255,.45);
  transform:scale(0); animation: mcRipple .6s ease-out; pointer-events:none; z-index:0; }
@keyframes mcRipple{ to{ transform:scale(3.2); opacity:0; } }

/* ---------------- Sliding segmented indicator (㉑) ---------------- */
[role="radiogroup"].mc-seg{ position: relative; }
/* top/height are driven from the ACTIVE LABEL by segPos(), not pinned to the
   group: a group that WRAPS to two rows (e.g. the 3-option "Return scenario" in
   the narrow sidebar) previously got a full-height pill spanning both rows, so
   it highlighted the wrong option. */
.mc-seg-indicator{ position:absolute; top:4px; height:0; left:0; width:0; border-radius:9px;
  background: rgba(13,148,136,.14); opacity:0; z-index:0;
  transition: left .3s cubic-bezier(.22,.61,.36,1), width .3s cubic-bezier(.22,.61,.36,1),
              top .3s cubic-bezier(.22,.61,.36,1), height .3s cubic-bezier(.22,.61,.36,1); }
[role="radiogroup"].mc-seg label{ position: relative; z-index:1; }
[role="radiogroup"].mc-seg label:has(input:checked){ background: transparent !important; }

/* ---------------- Slider / toggle / checkbox (㉒㉓㉔) ---------------- */
[data-testid="stSliderThumbValue"]{ transition: transform .15s ease; }
[data-baseweb="slider"]:hover [data-testid="stSliderThumbValue"],
[data-baseweb="slider"]:active [data-testid="stSliderThumbValue"]{ transform: scale(1.12); }
[data-baseweb="slider"] [role="slider"]{ transition: box-shadow .15s ease, scale .12s ease; }
/* NOTE: use the standalone `scale` property, NOT `transform: scale(...)`.
   BaseWeb positions the thumb with an INLINE `transform: translate(...)`, and an
   inline style always beats a stylesheet rule — so a transform-based press
   effect here silently never rendered. `scale` composes with the inline
   translate instead of fighting it. */
[data-baseweb="slider"] [role="slider"]:active{ scale: 1.15; }
[data-baseweb="checkbox"]{ transition: transform .12s ease; }
[data-baseweb="checkbox"]:active{ transform: scale(.94); }
[data-baseweb="checkbox"] input:checked ~ div{ animation: mcCheckPop .28s cubic-bezier(.22,.61,.36,1); }
@keyframes mcCheckPop{ 0%{transform:scale(.7)} 60%{transform:scale(1.12)} 100%{transform:scale(1)} }

/* ---------------- Tooltip / toast (㉘㉗) ---------------- */
/* Animate the INNER content only: [data-baseweb="tooltip"] is positioned by
   popper via an inline transform, and a fill-forwards `transform: none`
   keyframe on it overrides that and pins the tooltip to the page's top-left. */
[data-testid="stTooltipContent"]{
  animation: mcTipIn .16s ease-out both; transform-origin: top center; }
@keyframes mcTipIn{ 0%{opacity:0;transform:scale(.92) translateY(-2px)} 100%{opacity:1;transform:none} }
[data-testid="stToast"]{ animation: mcToastIn .38s cubic-bezier(.22,.61,.36,1) both; }
@keyframes mcToastIn{ 0%{opacity:0;transform:translateX(34px) scale(.96)} 100%{opacity:1;transform:none} }

/* ---------------- Chart draw-in (⑬⑭⑮⑯) — per Plotly trace type ----------------
   One-time reveal when a chart first appears (hidden on insert, revealed once the
   SVG is drawn, class removed after). round-16px keeps the card corners; the class
   is removed on animationend so the elevated box-shadow returns. */
[data-testid="stPlotlyChart"].mc-predraw{ opacity:0 !important; }
[data-testid="stPlotlyChart"].mc-draw-line{ animation: mcDrawLine .9s cubic-bezier(.22,.61,.36,1); }
@keyframes mcDrawLine{ 0%{ clip-path: inset(0 100% 0 0 round 16px); } 100%{ clip-path: inset(0 0 0 0 round 16px); } }
[data-testid="stPlotlyChart"].mc-draw-bar{ animation: mcDrawBar .8s cubic-bezier(.22,.61,.36,1); }
@keyframes mcDrawBar{ 0%{ clip-path: inset(100% 0 0 0 round 16px); } 100%{ clip-path: inset(0 0 0 0 round 16px); } }
/* Pie reveal by clip-path, NOT transform: Streamlit measures the chart while it
   animates, and a scale(.72) made it re-derive a taller height (440px -> 584px),
   overflowing the card — the "donut overflow race". clip-path doesn't change
   the measured box. */
[data-testid="stPlotlyChart"].mc-draw-pie{ animation: mcDrawPie .7s cubic-bezier(.22,.61,.36,1); }
@keyframes mcDrawPie{ 0%{ opacity:0; clip-path: circle(0% at 50% 50%); } 100%{ opacity:1; clip-path: circle(75% at 50% 50%); } }
/* ⑯ Outcome band rise-in: box/range charts (distribution bands) rise from the
   baseline with a soft fade — distinct from a bar's hard bottom-wipe. */
[data-testid="stPlotlyChart"].mc-draw-band{ animation: mcDrawBand .9s cubic-bezier(.22,.61,.36,1); }
@keyframes mcDrawBand{ 0%{ clip-path: inset(100% 0 0 0 round 16px); opacity:.45; } 100%{ clip-path: inset(0 0 0 0 round 16px); opacity:1; } }
@media (prefers-reduced-motion: reduce){
  [data-testid="stPlotlyChart"].mc-predraw{ opacity:1 !important; }
  [data-testid="stPlotlyChart"][class*="mc-draw-"]{ animation:none !important; }
}

/* ---------------- Spinner + skeleton (⑱⑳) ---------------- */
[data-testid="stSpinner"] i, [data-testid="stSpinner"] svg{ color:#0d9488 !important; border-top-color:#0d9488 !important; }
.mc-skeleton{ background: linear-gradient(90deg, rgba(120,96,52,.06) 25%, rgba(120,96,52,.12) 37%, rgba(120,96,52,.06) 63%);
  background-size: 400% 100%; animation: mcShimmer 1.4s ease-in-out infinite; border-radius:10px; }
@keyframes mcShimmer{ 0%{background-position:100% 0} 100%{background-position:-100% 0} }

/* ---------------- Lazy-section placeholder + hidden trigger (progressive render) ---------------- */
.mc-lazy{ border-radius:16px; margin:6px 0 14px;
  background: linear-gradient(90deg, rgba(120,96,52,.05) 25%, rgba(120,96,52,.11) 37%, rgba(120,96,52,.05) 63%);
  background-size: 400% 100%; animation: mcShimmer 1.4s ease-in-out infinite; }
/* the JS-clicked "load" buttons stay in the DOM (clickable) but invisible */
[class*="st-key-_lzb_"]{ height:0 !important; min-height:0 !important; overflow:hidden !important;
  margin:0 !important; padding:0 !important; opacity:0 !important; pointer-events:none !important; }
@media (prefers-reduced-motion: reduce){ .mc-lazy{ animation:none; } }

/* KPI card pointer-tilt (⑤): 3D tilt follows the cursor (transform only). */
.mc-stat-card.mc-tilting{ transition: transform .06s linear !important; will-change: transform; }

/* ⑫ Odometer digit-roll (replaces the count-up on metric values). Each numeral
   is a 1em-tall window onto a stacked 0-9 strip; the strip translateY-rolls to
   its target digit. Non-digit glyphs ($ . , K M %) stay static. */
.mc-odo{ display:inline-flex; align-items:baseline; font-variant-numeric: tabular-nums;
  font-feature-settings:"tnum" 1; }
.mc-odo-d{ display:inline-block; overflow:hidden; height:1em; line-height:1; vertical-align:baseline; }
.mc-odo-col{ display:flex; flex-direction:column; transform:translateY(0); }
.mc-odo-col.mc-odo-anim{ transition: transform .85s cubic-bezier(.22,.61,.36,1); will-change: transform; }
.mc-odo-col > span{ display:block; height:1em; line-height:1; }
.mc-odo-sep{ display:inline-block; }
/* The metric's own value nodes stay in the DOM (React keeps updating THEM on
   every rerun) but are hidden; the odometer in front reads them. Removing them
   froze every st.metric at its first value. */
.mc-odo-host > :not(.mc-odo):not(.mc-topbar-metric-hint){ display:none !important; }

@media (prefers-reduced-motion: reduce){
  .mc-flash, .mc-pulse::after, [data-testid="stToast"], .mc-entrance, .mc-cascade,
  [data-testid="stMetricDelta"], .mc-delta{ animation: none !important; }
  .mc-stat-card.mc-tilting{ transform: none !important; }
  .mc-odo-col{ transition: none !important; }
}
</style>
"""

_ANIM_JS = """
<script>
(function(){
  var P = window.parent, D = P.document;
  var reduce = false;
  try { reduce = P.matchMedia && P.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch(e){}
  if (!P.__mcSeen) P.__mcSeen = {};
  // Animation "epoch": bumped by the app when the user switches to a different
  // set of inputs (profile change). Our celebration/last-seen state lives on
  // window.parent and survives every rerun for the life of the TAB, so without
  // this a profile at 85% success would suppress the confetti for a DIFFERENT
  // profile at 90% (its "previous" value is still >= 80). Reset on change.
  var EPOCH = '__MC_EPOCH__';
  if (P.__mcEpoch !== EPOCH) {
    P.__mcEpoch = EPOCH;
    P.__mcLastSuccess = undefined;
    P.__mcSeen = {};
  }

  // ---------- number parse / format ----------
  // Only plain amounts roll ($1.9M, 87%, +2.4%, $9,147). Text that merely
  // contains a number (a household named "Median US 25-year-old household")
  // is left alone: rolling it char by char dropped its spaces.
  function parseNum(t){
    var m = /^\\s*(\\+?\\$?)(-?[\\d,]*\\.?\\d+)\\s*(%|[KMB]|pp)?\\s*$/.exec(t || '');
    if(!m) return null;
    var raw = m[2].replace(/,/g,''); var num = parseFloat(raw);
    if(isNaN(num)) return null;
    return { pre:m[1], num:num, suf:m[3]||'', comma:m[2].indexOf(',')>=0, dec:(raw.split('.')[1]||'').length };
  }
  // Return the DISPLAYED value text of a metric node. Once we replace the node's
  // content with an odometer, node.textContent is the stacked 0-9 strip glyphs,
  // so the real value is stashed on __mcOdoTxt.
  function dispText(node){ return node.__mcOdoTxt != null ? node.__mcOdoTxt : node.textContent; }
  function labelFor(node){
    var m = node.closest && node.closest('[data-testid="stMetric"]');
    if(m){ var l=m.querySelector('[data-testid="stMetricLabel"]'); return 'M|'+(l?l.textContent.trim():'?'); }
    if(node.classList.contains('mc-topbar-metric-value')){
      var lab = node.parentElement && node.parentElement.querySelector('.mc-topbar-metric-label');
      return 'T|'+(lab?lab.textContent.trim():'?'); }
    if(node.classList.contains('mc-stat-value')){
      var c = node.closest('.mc-stat-card'); return 'S|'+(c?c.textContent.slice(0,24):node.textContent); }
    return 'X|'+(node.textContent||'').slice(0,24);
  }
  function isSuccessLabel(node){ return /success/i.test(labelFor(node)); }
  function inView(node){
    try{ var r=node.getBoundingClientRect();
      return r.width>0 && r.bottom>0 && r.top < (P.innerHeight||800); }catch(e){ return true; }
  }

  // ---------- ⑫ odometer digit-roll (build) ----------
  // A metric value becomes an .mc-odo wrapper: each digit is a 1em window onto a
  // stacked 0-9 strip that CSS-transitions (GPU, no per-frame JS) to its target;
  // separators are static. Digits are staggered L->R so the roll cascades.
  function digitCol(d){
    var col = D.createElement('span'); col.className = 'mc-odo-col';
    for(var n=0;n<=9;n++){ var s=D.createElement('span'); s.textContent=n; col.appendChild(s); }
    col.__d = d; return col;
  }
  function buildOdo(node, valTxt, animate){
    var old = node.querySelector(':scope > .mc-odo'); if(old) node.removeChild(old);
    // Bare text (our own HTML metrics) moves into a hidden span; framework-owned
    // element children are left exactly where they are and hidden by CSS.
    Array.prototype.slice.call(node.childNodes).forEach(function(cn){
      if(cn.nodeType===3 && cn.nodeValue.trim()){
        var src=D.createElement('span'); src.className='mc-odo-src';
        node.replaceChild(src, cn); src.appendChild(cn); }
    });
    node.classList.add('mc-odo-host');
    var wrap = D.createElement('span'); wrap.className='mc-odo'; var cols=[];
    for(var i=0;i<valTxt.length;i++){
      var ch = valTxt.charAt(i);
      if(ch>='0' && ch<='9'){ var box=D.createElement('span'); box.className='mc-odo-d';
        var col=digitCol(+ch); box.appendChild(col); wrap.appendChild(box); cols.push(col); }
      else { var sep=D.createElement('span'); sep.className='mc-odo-sep'; sep.textContent=ch; wrap.appendChild(sep); }
    }
    node.insertBefore(wrap, node.firstChild);
    node.__mcOdoTxt = valTxt;
    if(!animate){ cols.forEach(function(c){ c.style.transform='translateY(-'+c.__d+'em)'; }); return; }
    // start at 0 (the strip's default), then roll to target next frame.
    P.requestAnimationFrame(function(){
      cols.forEach(function(c, k){
        c.classList.add('mc-odo-anim'); c.style.transitionDelay=(k*55)+'ms';
        c.style.transform='translateY(-'+c.__d+'em)';
        var clear = function(){ c.classList.remove('mc-odo-anim'); c.style.transitionDelay='';
          c.removeEventListener('transitionend', clear); };
        c.addEventListener('transitionend', clear);
        // Fallback: a digit whose target is 0 doesn't move, so `transitionend`
        // never fires — clear it (and its will-change) on a timer regardless.
        P.setTimeout(clear, 900 + k*55 + 120);
      });
    });
  }

  var _lastFlash = new WeakMap();
  function flash(node){
    var now = P.performance ? P.performance.now() : 0;
    if(_lastFlash.get(node) && (now - _lastFlash.get(node)) < 850) return;   // debounce
    _lastFlash.set(node, now);
    node.classList.remove('mc-flash'); void node.offsetWidth; node.classList.add('mc-flash');
    var tile = node.closest && node.closest('.mc-stat-card, [data-testid="stMetric"], [class*="st-key-mc-tile"]');
    if(tile){ tile.classList.remove('mc-pulse'); void tile.offsetWidth; tile.classList.add('mc-pulse'); }
  }
  function odometer(){
    var nodes = D.querySelectorAll('[data-testid="stMetricValue"], .mc-topbar-metric-value, .mc-stat-value');
    nodes.forEach(function(node){
      // The value node may carry a trailing hint span (top-bar metrics). Split it
      // off so the odometer covers only the numeric value; re-attach it after.
      var hint = node.querySelector && node.querySelector('.mc-topbar-metric-hint');
      var built = !!(node.firstChild && node.firstChild.nodeType===1 &&
                     node.firstChild.classList && node.firstChild.classList.contains('mc-odo'));
      var valTxt;
      if(built){
        // Already an odometer. Streamlit rewrites the TEXT of this node when the
        // value changes but leaves our wrapper in place, so we must compare the
        // live text against what the odometer currently displays -- an
        // "is it built?" check alone would freeze the digits at their first
        // value (showing a stale/mismatched number until a full re-render).
        var live = '';
        for(var i=0;i<node.childNodes.length;i++){
          var cn = node.childNodes[i];
          if(cn.nodeType===3) live += cn.nodeValue;                       // bare text
          else if(cn.nodeType===1 && !cn.classList.contains('mc-topbar-metric-hint')
                  && !cn.classList.contains('mc-odo')) live += cn.textContent;
        }
        live = live.trim();
        // No stray text alongside the wrapper -> nothing changed; leave it be.
        if(!live) return;
        if(live === node.__mcOdoTxt) return;
        valTxt = live;
      } else {
        valTxt = (node.firstChild && node.firstChild.nodeType===3)
          ? node.firstChild.nodeValue.trim() : (node.textContent||'').trim();
      }
      var info = parseNum(valTxt);
      if(!info){                                          // non-numeric (names, "—")
        // A value that WAS a number and now isn't: drop the odometer so the
        // framework's own text ("—") shows instead of the stale digits.
        if(built){ var w = node.querySelector(':scope > .mc-odo'); if(w) node.removeChild(w);
                   node.classList.remove('mc-odo-host'); node.__mcOdoTxt = null; }
        return;
      }
      var key = labelFor(node), prev = P.__mcSeen[key];
      var changed = (prev !== undefined && Math.abs(prev-info.num) > 1e-9);
      // Off-screen or reduced-motion: build statically at the target (no roll).
      if(reduce || !inView(node)){ buildOdo(node, valTxt, false); P.__mcSeen[key]=info.num; return; }
      buildOdo(node, valTxt, (prev===undefined) || changed);
      if(changed) flash(node);                            // keep ⑩ flash + ㉕ pulse on a real change
      P.__mcSeen[key]=info.num;
    });
  }

  // ---------- one-time entrance (section tiles, staggered) ----------
  function entrance(){
    if(P.__mcEntranceDone || reduce) return;
    P.__mcEntranceDone = true;
    var els = D.querySelectorAll('.st-key-mc-topbar, [class*="st-key-mc-tile"]');
    els.forEach(function(el, i){
      el.style.animationDelay = (i*70)+'ms'; el.classList.add('mc-entrance');
      P.setTimeout(function(){ el.classList.remove('mc-entrance'); el.style.animationDelay=''; }, 900 + i*70);
    });
  }

  // ---------- sliding segmented indicator (change-detected) ----------
  function segPos(g){
    var ind = g.querySelector(':scope > .mc-seg-indicator');
    if(!ind){ ind = D.createElement('div'); ind.className='mc-seg-indicator'; g.insertBefore(ind, g.firstChild); }
    var lab = g.querySelector('label:has(input:checked)') || g.querySelector('label');
    if(!lab) return;
    // Track the active label's BOX (not just x/width) so a wrapped, multi-row
    // group highlights only the selected row.
    var L=lab.offsetLeft, W=lab.offsetWidth, T=lab.offsetTop, H=lab.offsetHeight;
    if(ind.__L===L && ind.__W===W && ind.__T===T && ind.__H===H) return;  // no move -> no write (no idle churn)
    ind.__L=L; ind.__W=W; ind.__T=T; ind.__H=H;
    ind.style.left=L+'px'; ind.style.width=W+'px';
    ind.style.top=T+'px'; ind.style.height=H+'px'; ind.style.opacity='1';
  }
  function segAll(){ D.querySelectorAll('[role="radiogroup"].mc-seg').forEach(segPos); }

  // ---------- celebration confetti (cooldown + cleanup) ----------
  function confetti(){
    if(reduce) return;
    var old = D.getElementById('mc-confetti'); if(old) old.remove();
    var c = D.createElement('canvas'); c.id='mc-confetti'; var W=P.innerWidth, H=P.innerHeight;
    c.width=W; c.height=H; c.style.cssText='position:fixed;inset:0;pointer-events:none;z-index:2147483000';
    D.body.appendChild(c); var ctx=c.getContext('2d');
    var cols=['#0d9488','#22c55e','#5eead4','#f59e0b','#0f766e'], parts=[];
    for(var i=0;i<80;i++){ parts.push({ x:W/2+(Math.random()-.5)*W*0.4, y:H*0.22,
      vx:(Math.random()-.5)*11, vy:Math.random()*-11-4, g:0.32+Math.random()*0.2,
      s:5+Math.random()*6, col:cols[i%cols.length], rot:Math.random()*6, vr:(Math.random()-.5)*0.4 }); }
    var t0=null, DUR=1400;
    function frame(ts){ if(t0===null)t0=ts; var el=ts-t0; ctx.clearRect(0,0,W,H); var alive=false;
      parts.forEach(function(p){ p.vy+=p.g; p.x+=p.vx; p.y+=p.vy; p.rot+=p.vr;
        var a=Math.max(0,1-el/DUR); if(p.y<H+20 && a>0){ alive=true;
          ctx.save(); ctx.globalAlpha=a; ctx.translate(p.x,p.y); ctx.rotate(p.rot);
          ctx.fillStyle=p.col; ctx.fillRect(-p.s/2,-p.s/2,p.s,p.s*0.6); ctx.restore(); } });
      if(alive && el<DUR){ P.requestAnimationFrame(frame); } else { c.remove(); }
    }
    P.requestAnimationFrame(frame);
  }
  function checkCelebrate(){
    D.querySelectorAll('.mc-topbar-metric-value').forEach(function(node){
      if(!isSuccessLabel(node)) return;
      var info = parseNum(dispText(node)); if(!info) return;
      var cur = Math.round(info.num), prev = P.__mcLastSuccess;
      if(cur >= 80 && (prev === undefined || prev < 80)){
        var now = P.performance ? P.performance.now() : 0;
        if(!P.__mcCelebT || (now - P.__mcCelebT) > 2500){
          P.__mcCelebT = now;
          // Fire AFTER the results paint settles. Running confetti during
          // Streamlit's heavy results render (20 Plotly charts, ~600ms
          // synchronous frame) made it crawl. requestIdleCallback waits for a
          // free main thread; setTimeout is the fallback.
          if(P.requestIdleCallback){ P.requestIdleCallback(function(){ confetti(); }, {timeout:1400}); }
          else { P.setTimeout(function(){ confetti(); }, 650); }
        }
      }
      P.__mcLastSuccess = cur;
    });
  }

  // ---------- click handlers (installed once) ----------
  if(!D.__mcClick){
    D.__mcClick = true;
    D.addEventListener('click', function(ev){
      try{
        var t0 = ev.target.closest ? ev.target : null;
        var jump = t0 && t0.closest('[data-mc-jump]');
        if(jump){ ev.preventDefault(); mcJump(jump.getAttribute('data-mc-jump')); return; }
        var show = t0 && t0.closest('[data-mc-show-results]');
        if(show){ ev.preventDefault(); mcShowResults(); return; }
        var fold = t0 && t0.closest('[data-mc-clamp]');
        if(fold){ if(fold.hasAttribute('data-mc-open')) fold.removeAttribute('data-mc-open');
                  else fold.setAttribute('data-mc-open', ''); }
        // ripple
        var btn = ev.target.closest && ev.target.closest('.stButton > button, [data-testid="stFormSubmitButton"] > button, button[kind]');
        if(btn && !reduce){
          var r=btn.getBoundingClientRect(), sz=Math.max(r.width,r.height);
          var s=D.createElement('span'); s.className='mc-ripple'; s.style.width=s.style.height=sz+'px';
          s.style.left=(ev.clientX-r.left-sz/2)+'px'; s.style.top=(ev.clientY-r.top-sz/2)+'px';
          btn.appendChild(s); P.setTimeout(function(){ s.remove(); }, 640);
        }
        // segmented: slide the indicator immediately
        var lab = ev.target.closest && ev.target.closest('[role="radiogroup"].mc-seg label');
        if(lab){ var g=lab.closest('[role="radiogroup"].mc-seg'); var ind=g && g.querySelector(':scope > .mc-seg-indicator');
          if(ind){ var L=lab.offsetLeft, W=lab.offsetWidth, T=lab.offsetTop, H=lab.offsetHeight;
            ind.__L=L; ind.__W=W; ind.__T=T; ind.__H=H;
            ind.style.left=L+'px'; ind.style.width=W+'px';
            ind.style.top=T+'px'; ind.style.height=H+'px'; ind.style.opacity='1'; } }
      }catch(e){}
    }, true);

    // ---------- KPI card pointer-tilt (⑤) ----------
    // Rect cached on enter (no per-move layout reads); transform written on move
    // (GPU). A transient .mc-tilting class makes it follow instantly, then it
    // eases back on leave.
    if(!reduce){
      var _tEl = null, _tR = null, _TMAX = 5;
      D.addEventListener('pointerover', function(e){
        var card = e.target.closest && e.target.closest('.mc-stat-card');
        if(card && card !== _tEl){ _tEl = card; _tR = card.getBoundingClientRect(); card.classList.add('mc-tilting'); }
      }, true);
      D.addEventListener('pointermove', function(e){
        if(!_tEl || !_tR) return;
        var px=(e.clientX-_tR.left)/_tR.width, py=(e.clientY-_tR.top)/_tR.height;
        if(px<-0.05||px>1.05||py<-0.05||py>1.05) return;
        _tEl.style.setProperty('--mx', (px*100).toFixed(1)+'%');
        _tEl.style.setProperty('--my', (py*100).toFixed(1)+'%');
        _tEl.style.transform='perspective(700px) rotateX('+((0.5-py)*2*_TMAX).toFixed(2)+'deg) rotateY('+((px-0.5)*2*_TMAX).toFixed(2)+'deg) translateY(-4px)';
      }, true);
      D.addEventListener('pointerout', function(e){
        var card = e.target.closest && e.target.closest('.mc-stat-card');
        if(card && (!e.relatedTarget || !card.contains(e.relatedTarget))){
          card.classList.remove('mc-tilting'); card.style.transform='';
          if(_tEl===card){ _tEl=null; _tR=null; }
        }
      }, true);
    }
  }

  // ---------- lazy-section loader ----------
  // Result sections render a <div data-lazy="KEY"> placeholder + a hidden "load"
  // button. When the placeholder nears the viewport we click the button, which
  // reruns ONLY that section's fragment to render its real charts — so the
  // ~20-chart burst is spread out and off-screen charts never render until
  // needed. We use a scroll + getBoundingClientRect check (NOT an
  // IntersectionObserver): the observer is created in this component's iframe
  // realm and does not reliably intersect against the PARENT viewport, whereas a
  // parent-element rect vs P.innerHeight is exact cross-realm.
  function checkLazy(){
    var vh = P.innerHeight || 800;
    D.querySelectorAll('[data-lazy]').forEach(function(ph){
      var key = ph.getAttribute('data-lazy'); if(!key) return;
      if(ph.offsetParent === null) return;               // hidden (collapsed expander / display:none) — don't load yet
      var r = ph.getBoundingClientRect();
      if(r.width === 0 && r.height === 0) return;
      // Near the viewport, OR already requested once: a section the user has
      // scrolled PAST sits above the window (bottom < -400) and would otherwise
      // stop retrying while still showing a skeleton.
      var near = (r.top < vh + 900 && r.bottom > -400);
      if(!near && !ph.__lzTries) return;
      // The click triggers a fragment rerun that REPLACES this placeholder with
      // the real charts. That rerun can silently not take (Streamlit drops it if
      // another rerun is already in flight — very reproducible right after a
      // run, when many fragments reset at once). A one-shot latch left the
      // section shimmering forever with no recovery, so re-arm on a timer and
      // stop only once the placeholder is actually gone from the DOM.
      var now = P.performance ? P.performance.now() : 0;
      if(ph.__lzAt && (now - ph.__lzAt) < 700) return;    // a click is still in flight
      if(ph.__lzTries >= 12) return;                       // give up rather than spin forever
      ph.__lzTries = (ph.__lzTries || 0) + 1;
      ph.__lzAt = now;
      var btn = D.querySelector('.st-key-_lzb_' + key + ' button');
      if(btn){ try{ btn.click(); }catch(err){} }
    });
  }
  var _lzPend = false;
  function scheduleLazy(){ if(_lzPend) return; _lzPend = true;
    P.requestAnimationFrame(function(){ _lzPend = false; try{ checkLazy(); }catch(e){} }); }
  // Re-install the scroll/resize listeners each iframe load (removing the stale
  // ones from a prior, now-dead realm — same lesson as the tagger).
  if(P.__mcLazyFn){ try{ P.document.removeEventListener('scroll', P.__mcLazyFn, true);
    P.removeEventListener('resize', P.__mcLazyFn); }catch(e){} }
  P.__mcLazyFn = scheduleLazy;
  try{ P.document.addEventListener('scroll', P.__mcLazyFn, true); }catch(e){}   // capture: catches inner-container scroll
  try{ P.addEventListener('resize', P.__mcLazyFn); }catch(e){}
  // Reliable fallback: a light poll that loads near-viewport sections and
  // SELF-TERMINATES once no placeholders remain (rect reads only, no writes/
  // mutations). Guarantees lazy sections load even if a scroll event is missed.
  if(P.__mcLazyPoll){ try{ P.clearInterval(P.__mcLazyPoll); }catch(e){} }
  P.__mcLazyPoll = P.setInterval(function(){
    try{ checkLazy(); if(!D.querySelector('[data-lazy]')){ P.clearInterval(P.__mcLazyPoll); P.__mcLazyPoll = null; } }catch(e){}
  }, 350);

  // ---------- chart draw-in (per Plotly trace type) ----------
  function drawScan(){
    if(reduce) return;
    D.querySelectorAll('[data-testid="stPlotlyChart"]:not([data-mc-draw])').forEach(function(c){
      c.setAttribute('data-mc-draw', 'pending');
      c.classList.add('mc-predraw');
      var tries = 0;
      (function waitSvg(){
        tries++;
        var svg = c.querySelector('svg.main-svg');
        if(svg){
          var type = 'line';
          if(c.querySelector('.pielayer path, .pielayer .slice')) type = 'pie';
          else if(c.querySelector('.boxlayer, .trace.boxes, g.box')) type = 'band';   // ⑯ box/range distribution
          else if(c.querySelector('.barlayer .point, .trace.bars, .bars .point')) type = 'bar';
          c.classList.remove('mc-predraw');
          var cls = 'mc-draw-' + type;
          c.setAttribute('data-mc-type', type);   // persistent marker (survives class removal)
          c.classList.add(cls);
          c.setAttribute('data-mc-draw', 'done');
          var done = function(){ c.classList.remove(cls); c.removeEventListener('animationend', done); };
          c.addEventListener('animationend', done);
          P.setTimeout(done, 1300);
        } else if(tries < 9){ P.setTimeout(waitSvg, 80); }
        else { c.classList.remove('mc-predraw'); c.setAttribute('data-mc-draw', 'done'); }
      })();
    });
  }

  // ---------- Monte Carlo paths fan during a run (⑰) ----------
  // Shown while a run progress bar is present (Python computes server-side, so
  // the browser is free to animate). Self-removes when the run finishes. The
  // caption's simulation count is injected from the real n_simulations setting.
  function runFan(){
    var running = !!D.querySelector('.stProgress');
    var fan = D.getElementById('mc-fan');
    if(running && !fan && !reduce){
      var W=520, H=150;
      fan = D.createElement('div'); fan.id='mc-fan';
      fan.style.cssText='position:fixed;top:44%;left:50%;transform:translate(-50%,-50%);z-index:2147482000;'
        +'pointer-events:none;background:rgba(255,255,255,.95);border-radius:18px;'
        +'box-shadow:0 16px 44px rgba(120,96,52,.20);padding:10px 16px 6px;';
      var cv=D.createElement('canvas'); cv.width=W*2; cv.height=H*2;
      cv.style.width=W+'px'; cv.style.height=H+'px'; cv.style.display='block';
      fan.appendChild(cv); D.body.appendChild(fan);
      var ctx=cv.getContext('2d'); ctx.scale(2,2);
      var cols=['#0d9488','#22c55e','#5eead4','#0f766e'], N=28, paths=[];
      for(var i=0;i<N;i++){ paths.push({ amp:(i/N-0.5), wob:Math.random()*6, col:cols[i%cols.length] }); }
      var t0=null;
      function frame(ts){
        if(D.getElementById('mc-fan')!==fan || !D.querySelector('.stProgress')){
          if(P.__mcFanReq){ P.cancelAnimationFrame(P.__mcFanReq); P.__mcFanReq=null; } if(fan.parentNode) fan.remove(); return; }
        if(t0===null) t0=ts; var el=(ts-t0)/1000; ctx.clearRect(0,0,W,H);
        var prog=(el%2.6)/2.6, ox=24, oy=H*0.52, reach=(W-48)*prog;
        for(var i=0;i<paths.length;i++){ var pth=paths[i]; ctx.beginPath(); ctx.moveTo(ox,oy);
          for(var x=0;x<=reach;x+=6){ var f=x/(W-48);
            var y=oy - pth.amp*H*0.46*f - Math.sin(f*6+pth.wob+el*1.4)*(3+7*f); ctx.lineTo(ox+x,y); }
          ctx.strokeStyle=pth.col; ctx.globalAlpha=0.12+0.18*Math.abs(pth.amp); ctx.lineWidth=1.5; ctx.stroke(); }
        ctx.beginPath(); ctx.arc(ox,oy,3.5,0,6.29); ctx.fillStyle='#0d9488'; ctx.globalAlpha=1; ctx.fill();
        ctx.fillStyle='#0d9488'; ctx.font='600 13.5px Inter,system-ui,sans-serif'; ctx.textAlign='center';
        ctx.fillText('__MC_SIM_LABEL__', W/2, H-2);
        P.__mcFanReq=P.requestAnimationFrame(frame);
      }
      P.__mcFanReq=P.requestAnimationFrame(frame);
    } else if(!running && fan){
      if(P.__mcFanReq){ P.cancelAnimationFrame(P.__mcFanReq); P.__mcFanReq=null; } fan.remove();
    }
  }

  // ---------- phones: section bar, Show results, folded explanations ----------
  function mainEl(){ return D.querySelector('section[data-testid="stMain"]'); }
  function isPhone(){ return P.matchMedia && P.matchMedia('(max-width: 640px)').matches; }
  // Scroll a section to just under the sticky bar. Sections passed on the way
  // load their charts lazily and grow, moving the target, so keep correcting
  // (instantly) until it holds still; any touch or wheel by the user stops it.
  function mcJump(name){
    var main = mainEl(); if(!main) return;
    var tries = 0, calm = 0, stopped = false;
    var stop = function(){ stopped = true; };
    main.addEventListener('touchstart', stop, {once: true, passive: true});
    main.addEventListener('wheel', stop, {once: true, passive: true});
    var step = function(){
      if(stopped) return;
      var t = D.querySelector('.st-key-mc-tile-' + name); if(!t) return;
      var bar = D.querySelector('.mc-phonebar');
      var off = (bar ? bar.getBoundingClientRect().height : 0) + 8;
      var delta = t.getBoundingClientRect().top - off;
      if(Math.abs(delta) <= 4){ if(++calm >= 3) return; }
      else { calm = 0; main.scrollTo({top: main.scrollTop + delta, behavior: (tries === 0 && !reduce) ? 'smooth' : 'auto'}); }
      if(++tries < 14) P.setTimeout(step, tries === 1 ? 650 : 300);
    };
    step();
  }
  // Close the full-screen inputs panel; if the inputs changed, start the run.
  function mcShowResults(){
    var run = D.querySelector('.st-key-topbar_run_button button');
    var close = D.querySelector('[data-testid="stSidebarCollapseButton"] button');
    if(close) close.click();
    var main = mainEl(); if(main) main.scrollTo({top: 0, behavior: 'auto'});
    if(run && !run.disabled) P.setTimeout(function(){ run.click(); }, 60);
  }
  function showResultsLabel(){
    var a = D.querySelector('[data-mc-show-results]'); if(!a) return;
    var run = D.querySelector('.st-key-topbar_run_button button');
    var want = (run && !run.disabled) ? 'Run & show results' : 'Show results';
    if(a.textContent !== want) a.textContent = want;
  }
  function phoneBar(){
    var bar = D.querySelector('.mc-phonebar'); if(!bar || !isPhone()) return;
    bar.querySelectorAll('[data-mc-jump]').forEach(function(a){   // only sections on the page
      a.hidden = !D.querySelector('.st-key-mc-tile-' + a.getAttribute('data-mc-jump')); });
    var main = mainEl(), card = D.querySelector('.st-key-mc-topbar');
    if(!main || !card || !P.IntersectionObserver) return;
    // "stuck" (top card scrolled away): show the headline result in the bar.
    bar.classList.toggle('mc-stuck', card.getBoundingClientRect().bottom <= 0);
    if(P.__mcBarCard !== card){
      if(P.__mcBarIO){ try{ P.__mcBarIO.disconnect(); }catch(e){} }
      P.__mcBarCard = card;
      P.__mcBarIO = new P.IntersectionObserver(function(es){
        var b = D.querySelector('.mc-phonebar'); if(b) b.classList.toggle('mc-stuck', !es[0].isIntersecting);
      }, {root: main, threshold: 0});
      P.__mcBarIO.observe(card);
    }
    // Highlight the section under a fixed line 40% down the screen (checked on
    // scroll, once per frame) and keep its chip in view in the chip row.
    markActive();
    if(P.__mcBarMain !== main){
      P.__mcBarMain = main;
      var queued = false;
      main.addEventListener('scroll', function(){
        if(queued) return; queued = true;
        P.requestAnimationFrame(function(){ queued = false; markActive(); });
      }, {passive: true});
    }
  }
  function markActive(){
    var b = D.querySelector('.mc-phonebar'); if(!b || !isPhone()) return;
    var y = P.innerHeight * 0.4, cur = null;
    D.querySelectorAll('[class*="st-key-mc-tile-"]').forEach(function(t){
      var r = t.getBoundingClientRect();
      if(r.top <= y && r.bottom > y){ var m = /st-key-mc-tile-([a-z]+)/.exec(t.className || ''); if(m) cur = m[1]; }
    });
    b.querySelectorAll('[data-mc-jump]').forEach(function(a){
      var on = a.getAttribute('data-mc-jump') === cur;
      if(on && a.getAttribute('aria-current') !== 'true'){
        a.setAttribute('aria-current', 'true');
        var nav = a.parentElement;   // position within the chip row, not the bar
        var x = nav.scrollLeft + a.getBoundingClientRect().left - nav.getBoundingClientRect().left - 12;
        nav.scrollTo({left: Math.max(0, x), behavior: reduce ? 'auto' : 'smooth'});
      } else if(!on && a.hasAttribute('aria-current')){ a.removeAttribute('aria-current'); }
    });
  }
  // Fold long explanations to three lines on phones; a tap opens/closes them.
  // Marked with a data attribute (not a class) so React re-renders don't drop it.
  function foldText(){
    if(!isPhone()) return;
    D.querySelectorAll('[class*="st-key-mc-tile"] [data-testid="stCaptionContainer"] p, ' +
                       '[class*="st-key-mc-tile"] [data-testid="stMarkdownContainer"] > p').forEach(function(el){
      if(el.hasAttribute('data-mc-clamp') || el.__mcFoldChecked) return;
      el.__mcFoldChecked = true;
      if(el.closest('[data-testid="stExpander"]')) return;
      if((el.textContent || '').length > 220) el.setAttribute('data-mc-clamp', '');
    });
  }

  // ---------- scan (debounced, on real DOM changes only) ----------
  function scan(){ try{ odometer(); entrance(); segAll(); checkCelebrate(); checkLazy(); drawScan(); runFan();
                         phoneBar(); showResultsLabel(); foldText(); }catch(e){} }
  scan();
  if(P.__mcAnimObs){ try{ P.__mcAnimObs.disconnect(); }catch(e){} }
  if(P.__mcAnimTimer){ try{ P.clearInterval(P.__mcAnimTimer); }catch(e){} P.__mcAnimTimer=null; }
  var pend=false;
  P.__mcAnimObs = new P.MutationObserver(function(muts){
    // Plotly emits a stream of DOM mutations on every hover/relayout; those must
    // NOT trigger our scan (offset reads / reflows) or interacting with charts
    // would stutter. Ignore mutations that originate inside a chart or our own
    // confetti canvas; only real content changes (reruns) drive a scan.
    var relevant = false;
    for(var i=0;i<muts.length;i++){
      var t = muts[i].target;
      if(t && t.closest){
        if(t.closest('[data-testid="stPlotlyChart"]') || t.closest('#mc-confetti')) continue;
      }
      relevant = true; break;
    }
    if(!relevant) return;
    if(pend) return; pend=true;
    P.setTimeout(function(){ pend=false; scan(); }, 90);
  });
  try{ P.__mcAnimObs.observe(D.body, {childList:true, subtree:true}); }catch(e){}
  // reposition the segmented indicator on layout changes (no polling interval)
  if(P.ResizeObserver){
    if(P.__mcSegRO){ try{ P.__mcSegRO.disconnect(); }catch(e){} }
    P.__mcSegRO = new P.ResizeObserver(function(){ try{ segAll(); }catch(e){} });
    try{ D.querySelectorAll('[role="radiogroup"].mc-seg').forEach(function(g){ P.__mcSegRO.observe(g); }); }catch(e){}
  }
})();
</script>
"""


def inject_animations(st) -> None:
    """Inject the animation CSS (app doc) + JS engine (parent doc via a 0-height
    component). Call once per run, after the theme CSS."""
    st.markdown(_ANIM_CSS, unsafe_allow_html=True)
    # Label the Monte Carlo "paths fan" overlay with the ACTUAL simulation count
    # the user selected (n_simulations; default 1000) rather than a fixed 10,000,
    # so the wording matches what's really being computed.
    try:
        n_sims = int(st.session_state.get("n_simulations", 1000))
    except Exception:
        n_sims = 1000
    label = f"Simulating {n_sims:,} futures…"
    # Epoch token: lets the JS detect "the user switched to a different set of
    # inputs" and reset its window.parent-scoped celebration/last-value state.
    try:
        epoch = str(st.session_state.get("_anim_epoch", 0))
    except Exception:
        epoch = "0"
    js = _ANIM_JS.replace("__MC_SIM_LABEL__", label).replace("__MC_EPOCH__", epoch)
    try:
        import streamlit.components.v1 as components
        components.html(js, height=0)
    except Exception:
        pass
