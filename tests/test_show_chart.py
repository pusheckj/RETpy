"""show_chart: one chart per screen once the phone/desktop answer is known, a
styled-figure memo, and the old two-copy fallback while it is not.

The answer is st.session_state["_viewport_narrow"] (True phone, False desktop,
absent or None = not known yet, e.g. AppTest or the first run).
"""
import os
import sys

import plotly.graph_objects as go
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import plot_theme as pt  # noqa: E402


class _Ctx:
    def __init__(self, log, key):
        self.log, self.key = log, key

    def __enter__(self):
        self.log.append(("container", self.key))
        return self

    def __exit__(self, *a):
        return False


class _St:
    def __init__(self, narrow="unset", **state):
        self.session_state = dict(state)
        if narrow != "unset":
            self.session_state["_viewport_narrow"] = narrow
        self.log = []
        self.figs = {}

    def container(self, key=None):
        return _Ctx(self.log, key)

    def plotly_chart(self, fig, **kw):
        self.log.append(("chart", kw["key"]))
        self.figs[kw["key"]] = fig


def _fig():
    f = go.Figure(go.Bar(x=[1, 2, 3], y=[3, 1, 2], name="a"))
    f.update_layout(title="A long enough title to wrap on a phone, for sure yes", height=300)
    return f


@pytest.fixture
def styled(monkeypatch):
    """Count style_fig calls."""
    calls = []
    real = pt.style_fig

    def counting(fig, st, compact=False):
        calls.append(compact)
        return real(fig, st, compact=compact)

    monkeypatch.setattr(pt, "style_fig", counting)
    return calls


def _containers(st):
    return [k for kind, k in st.log if kind == "container"]


def test_unknown_viewport_keeps_two_copies(styled):
    for st in (_St(), _St(narrow=None)):
        styled.clear()
        pt.show_chart(st, _fig(), "k")
        assert _containers(st) == ["mc-wide-k", "mc-narrow-k"]
        assert [k for kind, k in st.log if kind == "chart"] == ["k", "k_compact"]
        assert styled == [False, True]


def test_phone_draws_one_compact_chart(styled):
    st = _St(narrow=True)
    pt.show_chart(st, _fig(), "k")
    assert _containers(st) == ["mc-chart-k"]
    assert [k for kind, k in st.log if kind == "chart"] == ["k"]
    assert styled == [True]
    # Compact layout: one legend column / wrapped title, tight side margins.
    assert st.figs["k"]["layout"]["margin"]["r"] == 24


def test_desktop_draws_one_wide_chart(styled):
    st = _St(narrow=False)
    pt.show_chart(st, _fig(), "k")
    assert _containers(st) == ["mc-chart-k"]
    assert styled == [False]
    assert st.figs["k"]["layout"]["margin"]["r"] != 24


def test_builder_is_called_once_with_the_viewport(styled):
    seen = []

    def build(compact):
        seen.append(compact)
        return _fig()

    for narrow in (True, False):
        seen.clear()
        pt.show_chart(_St(narrow=narrow), build, "k")
        assert seen == [narrow]


def test_same_figure_and_theme_skips_style_fig(styled):
    st = _St(narrow=False)
    pt.show_chart(st, _fig(), "k")
    first = st.figs["k"]
    pt.show_chart(st, _fig(), "k")
    assert styled == [False]                    # second call served from the memo
    assert st.figs["k"] == first


def test_theme_palette_font_viewport_and_figure_change_miss_the_memo(styled):
    st = _St(narrow=False)
    pt.show_chart(st, _fig(), "k")
    for change in ({"theme_mode": "Dark"}, {"palette_choice": "Vibrant"}, {"font_choice": "Poppins"}):
        n = len(styled)
        st.session_state.update(change)
        pt.show_chart(st, _fig(), "k")
        assert len(styled) == n + 1, change
    n = len(styled)
    other = _fig()
    other.data[0].y = (9, 9, 9)
    pt.show_chart(st, other, "k")
    assert len(styled) == n + 1
    n = len(styled)
    st.session_state["_viewport_narrow"] = True
    pt.show_chart(st, _fig(), "k")
    assert len(styled) == n + 1


def test_memo_is_bounded(styled):
    st = _St(narrow=False)
    for i in range(70):
        f = _fig()
        f.data[0].y = (i, 1, 2)
        pt.show_chart(st, f, f"k{i}")
    assert len(st.session_state["_fig_cache"]) == 64


def test_the_callers_figure_is_not_changed_by_styling(styled):
    f = _fig()
    before = f.to_json()
    pt.show_chart(_St(narrow=True), f, "k")
    assert f.to_json() == before and styled == [True]


def test_stub_st_without_container_draws_the_wide_chart_only(styled):
    class Plain:
        session_state = {}

        def plotly_chart(self, fig, **kw):
            self.key = kw["key"]

    p = Plain()
    pt.show_chart(p, _fig(), "k")
    assert p.key == "k" and styled == [False]


def test_single_chart_wrapper_keeps_the_donut_card_styling():
    """The "By category" donut card is styled through the wrapper key. The single-copy
    wrapper (mc-chart-) must get the same rules as mc-wide-/mc-narrow-."""
    css = open(os.path.join(_ROOT, "ui", "styles", "theme.css"), encoding="utf-8").read()
    assert 'st-key-mc-chart-"][class*="_category"]' in css
    # and the wrapper is never hidden by the two-copy rules
    assert "st-key-mc-chart-\"]) { display: none" not in css
