"""Phones and tablets: the layout follows the screen width (theme.css media
queries), and the Spending charts that can't reflow are drawn in a regular and
a compact version that CSS switches between.

Regressions these pin, all found on an iPhone (390x664):
  * the sticky top card filled ~70% of the screen and the page scrolled under it
  * its toolbar stacked into four rows: the <=1100px column-stacking rule
    out-ranked the top card's own rules (one extra type selector)
  * the spending donut was squeezed to ~80px by a right-hand legend, and the
    monthly chart's labels (one per month) collided
"""
import os
import re
import sys

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components import spending_dashboard as sd  # noqa: E402

CSS = open(os.path.join(_ROOT, "ui", "styles", "theme.css"), encoding="utf-8").read()


def _media(query: str) -> str:
    """Concatenated bodies of every @media block with exactly this query."""
    blocks = re.findall(r"@media\s*" + re.escape(query) + r"\s*\{(.*?)\n\}", CSS, re.S)
    assert blocks, f"no @media {query} block"
    return "\n".join(blocks)


def test_top_card_scrolls_away_on_phones_and_short_screens():
    body = _media("(max-width: 768px), (max-height: 600px)")
    assert re.search(r"st-key-mc-topbar\)\s*\{\s*position:\s*static", body)


def test_phone_frame_uses_narrow_gutters():
    body = _media("(max-width: 640px)")
    assert "padding: 56px 12px 48px" in body


def test_toolbar_column_rules_outrank_the_tablet_stacking_rule():
    stack = _media("(max-width: 1100px)")
    # the generic stacking rule has a type selector (section[...]) ...
    assert 'section[data-testid="stMain"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]' in stack
    # ... so the top card's exceptions must carry it too, or they lose
    assert re.search(r'section\[data-testid="stMain"\] \.st-key-mc-topbar .*:not\(:first-child\)', stack)
    phone = _media("(max-width: 640px)")
    for n in (2, 3, 4):
        assert re.search(r'section\[data-testid="stMain"\] \.st-key-mc-topbar .*:nth-child\(%d\)' % n, phone)


def test_compact_charts_show_only_on_phones():
    assert re.search(r'stLayoutWrapper"\]:has\(> \[class\*="st-key-mc-narrow-"\]\)\s*\{\s*display:\s*none', CSS)
    phone = _media("(max-width: 640px)")
    assert re.search(r'st-key-mc-wide-"\]\)\s*\{\s*display:\s*none', phone)


def _avg():
    return pd.Series({"Housing": 4000.0, "Utilities": 300.0, "Food & groceries": 800.0})


def test_compact_donut_puts_the_legend_under_the_ring():
    wide, compact = sd.pie_figure(_avg(), dark=False), sd.pie_figure(_avg(), dark=False, compact=True)
    assert wide.layout.legend.orientation in (None, "v") and wide.layout.legend.x == 0.45
    assert compact.layout.legend.orientation == "h" and compact.layout.legend.y < 0.5
    assert list(compact.data[0].domain.x) == [0.12, 0.88]
    assert compact.layout.annotations[0].x == 0.5          # total sits in the ring's hole


def _table():
    months = pd.period_range("2025-01", "2025-12", freq="M")
    return pd.DataFrame({"Housing": [4000.0] * 12, "Net": [4000.0] * 12}, index=months)


def test_compact_monthly_chart_labels_every_third_month():
    assert sd.monthly_figure(_table(), [], False).layout.xaxis.dtick == "M1"
    assert sd.monthly_figure(_table(), [], False, compact=True).layout.xaxis.dtick == "M3"


def test_chart_helper_draws_both_versions_with_stable_keys(monkeypatch):
    calls = []

    class _Ctx:
        def __init__(self, key): calls.append(("container", key))
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _St:
        def container(self, key=None): return _Ctx(key)
        def plotly_chart(self, fig, **kw): calls.append(("chart", kw["key"]))

    built = []
    monkeypatch.setattr(sd, "style_fig", lambda fig, st: fig)   # theme styling needs a live session
    sd._chart(_St(), lambda compact: built.append(compact) or sd.pie_figure(_avg(), False, compact),
              "sp_avg_donut", {})
    assert built == [False, True]
    assert ("container", "mc-wide-sp_avg_donut") in calls and ("container", "mc-narrow-sp_avg_donut") in calls
    assert ("chart", "sp_avg_donut") in calls and ("chart", "sp_avg_donut_compact") in calls


def test_touch_swipes_on_charts_scroll_the_page():
    """Plotly's drag layer captured swipes that began on a chart (the chart
    panned instead of the page scrolling). On touch screens touches pass
    through; desktop (mouse) keeps drag-to-zoom."""
    touch = _media("(hover: none) and (pointer: coarse)")
    assert re.search(r"\.js-plotly-plot \.draglayer \*\s*\{\s*pointer-events:\s*none", touch)


def test_touch_page_scrolls_vertically_only():
    touch = _media("(hover: none) and (pointer: coarse)")
    main = re.search(r'section\[data-testid="stMain"\]\s*\{([^}]*)\}', touch)
    assert main, "no stMain rule for touch screens"
    assert "overflow-x: hidden" in main.group(1)
    assert "touch-action: pan-y pinch-zoom" in main.group(1)
    assert "overscroll-behavior-x: none" in main.group(1)
