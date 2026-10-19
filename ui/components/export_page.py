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
        <div id="mc-export-wrap" style="font-family: Inter, -apple-system, sans-serif;">
          <button id="mc-export-btn" style="
            width: 100%; padding: 8px 14px; border-radius: 8px; border: 1px solid #0d9488;
            background: #0d9488; color: #ffffff; font-size: 14px; font-weight: 600;
            cursor: pointer; font-family: inherit;
          ">Export current page (HTML)</button>
          <div id="mc-export-status" style="font-size: 12px; color: #64748b; margin-top: 6px;"></div>
        </div>
        <script>
        (function(){
          const P = window.parent;
          const doc = P.document;
          const btn = document.getElementById('mc-export-btn');
          const status = document.getElementById('mc-export-status');

          // Serialize a CSSStyleDeclaration to a "prop:value;" string,
          // skipping properties whose value is empty (some CSS custom
          // properties/experimental props report as such).
          function styleText(computed){
            let out = '';
            for (let i = 0; i < computed.length; i++){
              const prop = computed[i];
              const val = computed.getPropertyValue(prop);
              if (val) out += prop + ':' + val + ';';
            }
            return out;
          }

          // Bake every element's COMPUTED style onto the matching clone
          // element, in document order. liveRoot and cloneRoot start
          // IDENTICAL (clone was just taken), so querySelectorAll('*') on
          // each returns the same length in the same order -- do this pass
          // BEFORE removing anything from the clone, or the two lists would
          // drift out of alignment.
          function inlineComputedStyles(liveRoot, cloneRoot){
            const liveEls = liveRoot.querySelectorAll('*');
            const cloneEls = cloneRoot.querySelectorAll('*');
            cloneRoot.setAttribute('style', styleText(P.getComputedStyle(liveRoot)));
            for (let i = 0; i < liveEls.length; i++){
              cloneEls[i].setAttribute('style', styleText(P.getComputedStyle(liveEls[i])));
            }
          }

          btn.addEventListener('click', function(){
            try {
              status.textContent = 'Capturing styles\\u2026';
              const liveRoot = doc.documentElement;
              const clone = liveRoot.cloneNode(true);

              // Streamlit's layout CSS is CSS-in-JS (inserted via the CSSOM,
              // not as <style> text) -- a plain clone captures none of it.
              // Bake in resolved values on every element instead; see the
              // module docstring for why.
              inlineComputedStyles(liveRoot, clone);

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
              status.textContent = 'Saved.';
            } catch (e) {
              status.textContent = 'Export failed: ' + e.message;
              console.error('Page export failed:', e);
            }
          });
        })();
        </script>
        """,
        height=68,
    )
