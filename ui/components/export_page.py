"""Export the CURRENTLY RENDERED page as a standalone HTML snapshot.

Different from print_summary.py: that ships a CURATED report (headline,
assumptions, one chart) built from data on the server. This captures
whatever is actually on screen right now -- every chart, every open tab,
however the sidebar is currently configured -- as a static file.

Streamlit is a live single-page app (React + a WebSocket back to this Python
process); there is no "page" to export server-side. This has to run in the
BROWSER: it's injected via components.html (the same 0-height-iframe-reaching-
window.parent pattern app.py already uses for keyboard nav), and the button
itself lives inside that iframe with a plain onclick handler -- a pure
client-side DOM capture + Blob download, no Streamlit rerun needed at all.

WHY A PLAIN cloneNode() ISN'T ENOUGH (found via a real bug report -- the
first version of this file shipped without this and the export rendered
completely unstyled): Streamlit's own layout ("BaseWeb"/Emotion) is CSS-in-JS
that inserts rules via the CSSOM (CSSStyleSheet.insertRule) at runtime rather
than writing CSS text into a <style> tag's DOM children. cloneNode/outerHTML
only serializes DOM TEXT content, so every one of those <style> tags comes
back EMPTY no matter what -- there is no stylesheet to link to or inline;
the rules never existed as text anywhere. The fix used here is the same
technique tools like SingleFile use: walk the live tree with
getComputedStyle() (which resolves the FINAL value regardless of which
mechanism produced it) and bake each element's full computed style onto the
corresponding clone element as an inline `style` attribute. This makes the
export self-consistent even though the CSS-in-JS rules themselves are gone.

Two things it still deliberately does NOT try to reproduce:
  * <script> tags are stripped from the clone. Re-executing Streamlit's app
    bundle in a saved file with no backend connection would just error or
    freeze, not "keep it interactive" -- this is a frozen visual snapshot.
  * Remaining relative resource URLs (favicon, @font-face src) are rewritten
    to ABSOLUTE (this page's origin), not inlined. The saved file renders
    correctly as long as this app is still reachable at that origin; it is
    not a fully self-contained bundle you can email to someone else.
"""
from __future__ import annotations


def render(st) -> None:
    import streamlit.components.v1 as components

    components.html(
        """
        <style>body { margin: 0; }</style>
        <div id="mc-export-wrap" style="font-family: Lora, Georgia, serif;">
          <button id="mc-export-btn" style="
            width: 100%; height: 40px; padding: 0 14px; border-radius: 8px; border: 1px solid #cbd5e1;
            background: #f2ecde; color: #1f2937; font-size: 16px; font-weight: 400;
            cursor: pointer; font-family: inherit; box-sizing: border-box;
          ">Export current page (HTML)</button>
          <div id="mc-export-status" aria-live="polite" style="position: absolute; width: 1px; height: 1px; overflow: hidden;"></div>
        </div>
        <script>
        (function(){
          const P = window.parent;
          const doc = P.document;
          const btn = document.getElementById('mc-export-btn');
          const status = document.getElementById('mc-export-status');
          const LABEL = btn.textContent;
          function say(msg){ status.textContent = msg; btn.textContent = msg || LABEL; }

          // Look like the other Settings buttons (this iframe can't see the page's
          // CSS, so copy the look of a real secondary button next to it).
          try {
            const ref = doc.querySelector('[data-testid="stPopoverBody"] button[data-testid="stBaseButton-secondary"]');
            const cs = P.getComputedStyle(ref || doc.documentElement);
            if (ref) {
              btn.style.background = cs.backgroundColor;
              btn.style.color = cs.color;
              btn.style.border = cs.border;
              btn.style.borderRadius = cs.borderRadius;
              btn.style.fontSize = cs.fontSize;
              btn.style.fontWeight = cs.fontWeight;
            }
            const fam = P.getComputedStyle(doc.body).fontFamily;
            if (fam) { btn.style.fontFamily = fam; btn.parentElement.style.fontFamily = fam; }
          } catch (e) {}

          // ---- style-inliner (extracted by tests/test_export_page.py) ----
          // Baking EVERY computed property onto EVERY element made a 67 MB file.
          // Only the properties that matter are written now:
          //   * inherited ones (colour, font...) only when they differ from the parent,
          //   * the rest only when they differ from the browser default for that tag,
          //   * logical (-block/-inline) duplicates of physical properties never,
          //   * inside a chart's SVG just the handful of painting properties,
          //   * display:none subtrees and the chart toolbar not at all.
          const INHERITED = new Set(['color','cursor','direction','font-family','font-size',
            'font-style','font-variant','font-weight','font-stretch','font-kerning',
            'font-feature-settings','font-variation-settings','line-height','letter-spacing',
            'word-spacing','text-align','text-indent','text-transform','text-shadow',
            'text-rendering','white-space','word-break','overflow-wrap','tab-size','visibility',
            'list-style-type','list-style-position','border-collapse','border-spacing',
            'caption-side','quotes','fill','fill-opacity','fill-rule','stroke','stroke-width',
            'stroke-opacity','stroke-linecap','stroke-linejoin','stroke-dasharray',
            'stroke-dashoffset','stroke-miterlimit','text-anchor','pointer-events',
            'caret-color','color-scheme','-webkit-text-fill-color','-webkit-font-smoothing',
            '-webkit-text-size-adjust','-webkit-text-stroke-color','-webkit-text-stroke-width']);
          const SVG_PAINT = ['fill','fill-opacity','stroke','stroke-width','stroke-opacity',
            'stroke-dasharray','stroke-linecap','stroke-linejoin','opacity','font-family',
            'font-size','font-weight','font-style','text-anchor','letter-spacing','visibility',
            'display','clip-path'];
          const SVG_DEFAULTS = {'opacity':'1','display':'inline','clip-path':'none'};
          const SKIP_NAME = /(^|-)(block|inline)(-|$)|^perspective-origin$/;
          // Written even when they equal the default: rules left in the page's own
          // stylesheet (which match differently on a static copy) must not win.
          const ALWAYS = new Set(['opacity','display','visibility','background-color',
            'background-image','transform','position','overflow-x','overflow-y']);
          const BODY_KEY = '#body';
          const baselines = {};

          function baselineFor(el){
            const key = (el.namespaceURI || '') + ' ' + el.localName;
            if (baselines[key]) return baselines[key];
            const map = {};
            try {
              if (!baselines.frame) {
                const f = doc.createElement('iframe');
                f.style.cssText = 'position:absolute;left:-9999px;top:0;width:300px;height:300px;border:0;visibility:hidden';
                doc.body.appendChild(f);
                baselines.frame = f;
              }
              const fd = baselines.frame.contentDocument;
              const probe = fd.createElementNS(el.namespaceURI || 'http://www.w3.org/1999/xhtml', el.localName);
              fd.body.appendChild(probe);
              const cs = baselines.frame.contentWindow.getComputedStyle(probe);
              for (let i = 0; i < cs.length; i++) map[cs[i]] = cs.getPropertyValue(cs[i]);
              // The page body's own defaults: a tag whose default differs from them
              // (buttons, inputs, headings) does NOT simply inherit the parent's value.
              const bs = baselines.frame.contentWindow.getComputedStyle(fd.body);
              const bodyMap = {};
              for (let i = 0; i < bs.length; i++) bodyMap[bs[i]] = bs.getPropertyValue(bs[i]);
              map[BODY_KEY] = bodyMap;
              fd.body.removeChild(probe);
            } catch (e) {}
            baselines[key] = map;
            return map;
          }

          // Serialize the kept properties of a CSSStyleDeclaration to
          // "prop:value;". `parent` (computed style of the parent, or null) and
          // `base` (browser defaults for the tag) decide what can be left out.
          function styleText(computed, parent, base, only){
            let out = '';
            for (let i = 0; i < computed.length; i++){
              const prop = computed[i];
              if (only && only.indexOf(prop) < 0) continue;
              if (SKIP_NAME.test(prop)) continue;
              const val = computed.getPropertyValue(prop);
              if (!val) continue;
              if (ALWAYS.has(prop)) {
                out += prop + ':' + val + ';';
                continue;
              }
              if (parent && (INHERITED.has(prop) || prop.startsWith('--'))) {
                const bodyDef = base && base[BODY_KEY] ? base[BODY_KEY][prop] : undefined;
                const uaOverrides = bodyDef !== undefined && base[prop] !== undefined && base[prop] !== bodyDef;
                if (uaOverrides ? val === base[prop] : val === parent.getPropertyValue(prop)) continue;
              } else if (base && val === base[prop] &&
                         (!parent || parent.getPropertyValue(prop) === val)) {
                // Browser default AND what the parent has, so it holds whether or
                // not this property happens to inherit.
                continue;
              }
              out += prop + ':' + val + ';';
            }
            return out;
          }

          // Bake every element's COMPUTED style onto the matching clone
          // element, in document order. liveRoot and cloneRoot start
          // IDENTICAL (clone was just taken), so querySelectorAll('*') on
          // each returns the same length in the same order -- do this pass
          // BEFORE removing anything from the clone, or the two lists would
          // drift out of alignment. Elements to drop are collected and removed
          // only after the pass.
          function inlineComputedStyles(liveRoot, cloneRoot){
            const liveEls = liveRoot.querySelectorAll('*');
            const cloneEls = cloneRoot.querySelectorAll('*');
            const dropped = new Set();
            const drop = [];
            cloneRoot.setAttribute('style', styleText(P.getComputedStyle(liveRoot), null, baselineFor(liveRoot), null));
            for (let i = 0; i < liveEls.length; i++){
              const el = liveEls[i];
              const parentEl = el.parentElement;
              if (parentEl && dropped.has(parentEl)) { dropped.add(el); continue; }
              const cs = P.getComputedStyle(el);
              // Typed-in state lives in properties, not attributes: copy it so the
              // saved page's own rules (:checked, a field's value) match the live page.
              if (el.localName === 'input') {
                if (el.checked) cloneEls[i].setAttribute('checked', '');
                else cloneEls[i].removeAttribute('checked');
                if (el.type !== 'checkbox' && el.type !== 'radio') cloneEls[i].setAttribute('value', el.value);
              }
              const inHead = !!el.closest('head');
              const isHtml = el.namespaceURI === 'http://www.w3.org/1999/xhtml';
              // (SVG <defs>, <clipPath>... are display:none by design and must stay.)
              // (<style>/<link> are display:none too but carry the page's CSS.)
              const isSheet = el.localName === 'style' || el.localName === 'link';
              if (isSheet) { continue; }
              if (!inHead && isHtml && (cs.display === 'none' ||
                  (el.classList && el.classList.contains('modebar-container')))) {
                dropped.add(el); drop.push(cloneEls[i]); continue;
              }
              const inSvg = el.namespaceURI === 'http://www.w3.org/2000/svg' && el.localName !== 'svg';
              const parentCs = parentEl ? P.getComputedStyle(parentEl) : null;
              cloneEls[i].setAttribute('style',
                styleText(cs, parentCs, inSvg ? SVG_DEFAULTS : baselineFor(el), inSvg ? SVG_PAINT : null));
            }
            drop.forEach(function(n){ if (n.parentNode) n.parentNode.removeChild(n); });
            if (baselines.frame && baselines.frame.parentNode) baselines.frame.parentNode.removeChild(baselines.frame);
          }
          // ---- end style-inliner ----

          function save(){
            try {
              say('Saving\\u2026');
              const liveRoot = doc.documentElement;
              // Folded section tiles (theme.css, "Collapsible section tiles")
              // open for the capture, so the file shows every section.
              liveRoot.setAttribute('data-mc-exporting', '');
              let clone;
              try {
                clone = liveRoot.cloneNode(true);

                // Streamlit's layout CSS is CSS-in-JS (inserted via the CSSOM,
                // not as <style> text) -- a plain clone captures none of it.
                // Bake in resolved values on every element instead; see the
                // module docstring for why.
                inlineComputedStyles(liveRoot, clone);
              } finally {
                liveRoot.removeAttribute('data-mc-exporting');
              }

              // NOW it's safe to strip <script> (would error/freeze
              // re-executing with no backend) and <iframe> (this exporter,
              // keyboard-nav, the animation layer -- utility-only, no visual
              // content of their own; real charts render as SVG in the main
              // document, not inside an iframe, so they're untouched).
              clone.querySelectorAll('script, iframe').forEach(function(el){ el.remove(); });

              // Remaining relative resource URLs (favicon, @font-face src
              // inside the one stylesheet we're about to keep) resolve
              // against the SAVED FILE's location once downloaded, not this
              // app -- rewrite to absolute so they keep working (as long as
              // this app is still reachable at that origin later).
              const origin = P.location.origin;
              function absolutize(el, attr){
                const v = el.getAttribute(attr);
                if (v && !/^([a-z]+:)?\\/\\//i.test(v) && !v.startsWith('data:')) {
                  const rel = v.startsWith('./') ? v.slice(2) : v;
                  el.setAttribute(attr, origin + (rel.startsWith('/') ? rel : '/' + rel));
                  // A <link crossorigin> stylesheet/font forces a CORS-mode
                  // fetch. This app's dev server sends no
                  // Access-Control-Allow-Origin header, so a saved file://
                  // page would silently fail to load it. We're not reading
                  // it via JS, so the CORS mode was never needed; drop it.
                  el.removeAttribute('crossorigin');
                }
              }
              clone.querySelectorAll('link[href]').forEach(function(el){ absolutize(el, 'href'); });
              clone.querySelectorAll('img[src]').forEach(function(el){ absolutize(el, 'src'); });

              const htmlStr = '<!DOCTYPE html>\\n' + clone.outerHTML;
              const blob = new P.Blob([htmlStr], {type: 'text/html'});
              const url = P.URL.createObjectURL(blob);
              const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
              const a = doc.createElement('a');
              a.href = url;
              a.download = 'retirement_app_snapshot_' + stamp + '.html';
              doc.body.appendChild(a);
              a.click();
              doc.body.removeChild(a);
              P.setTimeout(function(){ P.URL.revokeObjectURL(url); }, 2000);
              say('Saved'); P.setTimeout(function(){ say(''); }, 2500);
            } catch (e) {
              say('Export failed'); status.textContent = 'Export failed: ' + e.message;
              console.error('Page export failed:', e);
            }
          }
          // Let "Saving..." paint before the (synchronous) capture starts.
          btn.addEventListener('click', function(){ say('Saving\\u2026'); P.setTimeout(save, 40); });
        })();
        </script>
        """,
        height=40,
    )
