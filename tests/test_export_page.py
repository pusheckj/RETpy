"""Export-current-page pin.

Unlike the other new components, this one is almost entirely a JS injection
(there's no server-side data to assert on) — the test captures what actually
gets passed to ``streamlit.components.v1.html`` and checks the essential
pieces are present, so a future edit can't silently drop the strip-scripts
step, the URL-absolutizing step, or the download trigger.

``utils``/``components`` live under ``ui/``; add both roots to sys.path.
"""
import os
import sys
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components import export_page  # noqa: E402


def _render_and_capture():
    with patch("streamlit.components.v1.html") as mock_html:
        export_page.render(object())
    args, kwargs = mock_html.call_args
    return args[0] if args else kwargs["html"]


def test_strips_scripts_and_iframes_from_the_clone():
    html = _render_and_capture()
    assert "querySelectorAll('script, iframe')" in html


def test_absolutizes_relative_resource_urls():
    html = _render_and_capture()
    assert "location.origin" in html
    assert "link[href]" in html
    assert "img[src]" in html


def test_strips_crossorigin_so_file_url_pages_can_load_the_css():
    """Regression for the reported bug: a rewritten <link crossorigin> forces
    a CORS-mode fetch, and this app's dev server sends no
    Access-Control-Allow-Origin header -- so a saved file:// page silently
    failed to load Streamlit's own stylesheet, rendering completely
    unstyled ("exploded"). removeAttribute('crossorigin') is the fix."""
    html = _render_and_capture()
    assert "removeAttribute('crossorigin')" in html


def test_strips_leading_dot_slash_before_absolutizing():
    """Streamlit's own asset links use './static/...' -- strip the leading
    './' explicitly rather than relying on the browser to normalize the
    resulting '/./' dot-segment."""
    html = _render_and_capture()
    assert "v.startsWith('./')" in html


def test_bakes_in_computed_styles_before_stripping_anything():
    """Root-cause regression: Streamlit's own layout CSS ("BaseWeb"/Emotion)
    is CSS-in-JS inserted via the CSSOM (CSSStyleSheet.insertRule), not
    written as text into a <style> tag. cloneNode/outerHTML only serializes
    DOM TEXT, so those rules -- which is most of Streamlit's actual layout,
    not just this app's own theme.css -- never come along, no matter how the
    resource URLs are fixed up. That's why the first two fixes (this file's
    git history) didn't resolve the reported "exploded" export: they fixed
    the wrong layer. The real fix bakes every element's resolved
    getComputedStyle() onto the clone as an inline `style` attribute, which
    resolves correctly regardless of which mechanism produced the value.
    Must happen BEFORE script/iframe stripping so the live/clone element
    lists returned by querySelectorAll('*') stay index-aligned."""
    html = _render_and_capture()
    assert "getComputedStyle" in html
    assert "inlineComputedStyles" in html
    assert html.index("inlineComputedStyles(liveRoot, clone)") < \
        html.index("querySelectorAll('script, iframe')")


def test_computed_style_inlining_survives_cssom_only_rules_and_stays_aligned():
    """Faithful DOM-level proof (not just a string check): build a real page
    where ALL styling comes from CSSStyleSheet.insertRule (exactly how
    Streamlit's Emotion behaves -- never written as literal <style> text),
    at multiple tree depths with siblings, and confirm each clone element
    ends up with ITS OWN live element's resolved style, not a neighbor's
    (which would indicate the live/clone element lists drifted out of
    alignment during the parallel walk).

    Requires Node + jsdom; skips gracefully if either is unavailable rather
    than installing anything (tests shouldn't have network side effects) --
    the string-level test above still pins the essential behavior either way.
    """
    import re
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node")
    if not node:
        return
    probe = subprocess.run([node, "-e", "require.resolve('jsdom')"], capture_output=True, text=True)
    if probe.returncode != 0:
        return  # jsdom not installed in this environment; skip rather than install it

    html = _render_and_capture()
    style_text_fn = re.search(r"function styleText\(computed\)\{(.*?)\n          \}", html, re.DOTALL).group(1)
    inline_fn = re.search(r"function inlineComputedStyles\(liveRoot, cloneRoot\)\{(.*?)\n          \}", html, re.DOTALL).group(1)

    script = f"""
    const {{ JSDOM }} = require('jsdom');
    const dom = new JSDOM(`
      <html><head><style id="s"></style></head>
      <body>
        <div id="a" class="box" data-n="0">
          <div class="box" data-n="1">
            <span id="target" data-n="2">deep</span>
          </div>
          <div class="box" data-n="3"></div>
        </div>
      </body></html>
    `, {{ pretendToBeVisual: true }});
    const doc = dom.window.document;
    const sheet = doc.getElementById('s').sheet;
    sheet.insertRule('[data-n="0"] {{ background-color: rgb(1, 1, 1); }}', 0);
    sheet.insertRule('[data-n="1"] {{ background-color: rgb(2, 2, 2); }}', 1);
    sheet.insertRule('[data-n="2"] {{ background-color: rgb(3, 3, 3); }}', 2);
    sheet.insertRule('[data-n="3"] {{ background-color: rgb(4, 4, 4); }}', 3);

    const P = dom.window;
    function styleText(computed){{{style_text_fn}}}
    function inlineComputedStyles(liveRoot, cloneRoot){{{inline_fn}}}

    const liveRoot = doc.documentElement;
    const clone = liveRoot.cloneNode(true);
    inlineComputedStyles(liveRoot, clone);

    for (const n of ['0','1','2','3']) {{
      const style = clone.querySelector('[data-n="' + n + '"]').getAttribute('style');
      const expected = 'rgb(' + (parseInt(n)+1) + ', ' + (parseInt(n)+1) + ', ' + (parseInt(n)+1) + ')';
      if (!style || !style.includes(expected)) {{
        console.error('MISALIGNED at data-n=' + n + ': ' + style);
        process.exit(1);
      }}
    }}
    console.log('all aligned');
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        result = subprocess.run([node, path], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "all aligned" in result.stdout
    finally:
        os.unlink(path)


def test_triggers_a_download_not_a_navigation():
    html = _render_and_capture()
    assert "a.download" in html
    assert "createObjectURL" in html
    assert "a.click()" in html


def test_button_and_status_element_present():
    html = _render_and_capture()
    assert 'id="mc-export-btn"' in html
    assert 'id="mc-export-status"' in html


def test_embedded_js_is_syntactically_valid():
    """Regex-extract the <script> block from the RUNTIME string (not the .py
    source text, which still has Python's escaping) and hand it to node
    --check, if node is available."""
    import re
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node")
    if not node:
        return  # environment without node; the other tests still cover intent

    html = _render_and_capture()
    m = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert m, "no <script> block found"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(m.group(1))
        path = f.name
    try:
        result = subprocess.run([node, "--check", path], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    finally:
        os.unlink(path)
