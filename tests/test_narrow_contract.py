"""The single-chart path (show_chart with a known viewport) can not be swapped by
CSS, so every theme.css rule that shows the compact "mc-narrow-" chart must fire
only on screens the narrow definition covers (plot_theme.NARROW_VIEWPORT_QUERY,
the query the browser evaluates for st.session_state["_viewport_narrow"]).

Found in review: the tablet rule (641-1130px with the side panel open) showed the
compact chart, but the narrow query stopped at 640px, so iPad-width screens got
the wide chart in a ~600px pane and its titles ran past the card.
"""
import itertools
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import plot_theme as pt  # noqa: E402

CSS = open(os.path.join(_ROOT, "ui", "styles", "theme.css"), encoding="utf-8").read()


def _matches(query: str, w: int, h: int, touch: bool) -> bool:
    """Evaluate a media query (comma list of 'and' lists) for one screen."""
    def feature(f: str) -> bool:
        name, _, val = (x.strip() for x in f.strip("() ").partition(":"))
        if name == "min-width": return w >= int(val[:-2])
        if name == "max-width": return w <= int(val[:-2])
        if name == "min-height": return h >= int(val[:-2])
        if name == "max-height": return h <= int(val[:-2])
        if name == "hover": return touch if val == "none" else not touch
        if name == "pointer": return touch if val == "coarse" else not touch
        raise AssertionError(f"media feature not handled by the test: {f}")
    return any(all(feature(f) for f in alt.split(" and ")) for alt in query.split(","))


def _blocks(css: str):
    """(media query or None, selector, body) for each rule; @media is not nested."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, i, media, depth_media = [], 0, None, 0
    pos = 0
    while pos < len(css):
        m = re.compile(r"\s*([^{}]+)\{").match(css, pos)
        if m is None:
            close = css.find("}", pos)
            if close < 0: break
            if media is not None: media = None
            pos = close + 1
            continue
        head = m.group(1).strip()
        if head.startswith("@media"):
            media, pos = head[len("@media"):].strip(), m.end()
            continue
        end = css.find("}", m.end())
        if head.startswith("@"):   # @keyframes etc.: skip the whole nested body
            depth, j = 1, m.end()
            while depth and j < len(css):
                depth += {"{": 1, "}": -1}.get(css[j], 0); j += 1
            pos = j
            continue
        out.append((media, head, css[m.end():end]))
        pos = end + 1
    return out


def _swaps_to_narrow():
    return [(media, sel) for media, sel, body in _blocks(CSS)
            if "st-key-mc-narrow-" in sel and re.search(r"display:\s*block", body)
            and ":has(> [class*=\"st-key-mc-narrow-\"])" in sel]


def test_the_test_finds_the_swap_rules():
    swaps = _swaps_to_narrow()
    assert len(swaps) >= 3 and all(media for media, _ in swaps), swaps
    assert any("min-width: 641px" in media for media, _ in swaps)


def test_every_css_swap_to_the_compact_chart_is_covered_by_the_narrow_definition():
    bad = []
    widths = sorted(set(range(280, 1700, 10)) | {640, 641, 960, 961, 1130, 1131})
    heights = (390, 430, 500, 501, 768, 1000)
    for media, sel in _swaps_to_narrow():
        for w, h, touch in itertools.product(widths, heights, (False, True)):
            if _matches(media, w, h, touch) and not _matches(pt.NARROW_VIEWPORT_QUERY, w, h, touch):
                bad.append((media, w, h, touch))
                break
    assert not bad, f"CSS shows the compact chart where _viewport_narrow is False: {bad}"


def test_the_browser_query_in_device_store_matches_the_constant():
    path = os.path.join(_ROOT, "ui", "components", "device_store", "index.html")
    m = re.search(r'NARROW_QUERY\s*=\s*"([^"]*)"', open(path, encoding="utf-8").read())
    if m is None:
        import pytest
        pytest.skip("device_store does not measure the viewport yet (P1 is not merged)")
    assert m.group(1) == pt.NARROW_VIEWPORT_QUERY
