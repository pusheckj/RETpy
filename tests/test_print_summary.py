"""One-page printable summary pins.

Ships a self-contained HTML export (no PDF/template dependency exists in
this repo) -- tests exercise the real figure-builder / HTML assembly against
a real (small) simulation run, since the whole point is that the exported
number matches what the live dashboard shows.

``utils``/``components`` live under ``ui/``; add both roots to sys.path.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components import print_summary  # noqa: E402
from utils.formatting import pct  # noqa: E402
from utils.sim_runner import run_full_analysis  # noqa: E402


class _FakeExpander:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeSt:
    def __init__(self, results=None, user_overrides=None):
        self.session_state = {"results": results, "user_overrides": user_overrides or {}}
        self.captions = []
        self.errors = []
        self.download_calls = []

    def expander(self, *a, **k):
        return _FakeExpander()

    def caption(self, text, **k):
        self.captions.append(text)

    def error(self, text, **k):
        self.errors.append(text)

    def download_button(self, label, data, **k):
        self.download_calls.append({"label": label, "data": data, **k})


def _real_results():
    return run_full_analysis(
        {"YOUR_AGE": 30, "TARGET_RETIREMENT_AGE": 50},
        n_simulations=200, target_retirement_age=50, scan_age_range=(45, 55, 1),
    )


def test_noop_without_results():
    st = _FakeSt(results=None)
    print_summary.render(st)
    assert st.download_calls == []
    assert any("first" in c.lower() for c in st.captions)


def test_fan_chart_html_contains_plotly_cdn_and_no_streamlit_calls():
    results = _real_results()
    html = print_summary._build_fan_chart_html(results)
    assert "<script" in html
    assert "cdn.plot.ly" in html
    assert "st.plotly_chart" not in html


def test_render_offers_download_with_headline_number():
    results = _real_results()
    overrides = {"YOUR_AGE": 30, "TARGET_RETIREMENT_AGE": 50}
    st = _FakeSt(results=results, user_overrides=overrides)
    print_summary.render(st)

    assert len(st.download_calls) == 1
    call = st.download_calls[0]
    assert call["mime"] == "text/html"
    html_blob = call["data"]

    primary = results.get("primary_result", {}) or {}
    success_str = pct(primary.get("success_rate"))
    # Formatted via money/pct, not a raw float dumped into the page.
    assert success_str in html_blob
    assert "success_rate" not in html_blob  # no raw dict keys leaking through
    earliest = results.get("earliest_retirement_age")
    if earliest is not None:
        assert str(earliest) in html_blob


def test_render_degrades_on_internal_error(monkeypatch):
    """A broken figure-builder must surface st.error, not crash the app."""
    def _boom(_results):
        raise RuntimeError("boom")

    monkeypatch.setattr(print_summary, "_build_fan_chart_html", _boom)
    st = _FakeSt(results=_real_results(), user_overrides={})
    print_summary.render(st)
    assert st.download_calls == []
    assert any("boom" in e for e in st.errors)
