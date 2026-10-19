"""Scenario Delta Report pins.

Pinned scenarios now snapshot the full ``user_overrides`` dict alongside the
output summary, so two pins can be diffed by INPUT, not just by output. The
"Compare inputs" section's per-row impact computation is lazy (only fires on
that row's button click) since the differing-key set is unbounded.

``utils``/``components`` live under ``ui/``; add both roots to sys.path.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components import scenario_compare  # noqa: E402


class _FakeCtx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeSt:
    """Minimal stand-in for the streamlit module, covering the widgets
    scenario_compare.py actually calls."""

    def __init__(self, submit_pin=False, pin_name="Scenario 1",
                 clicked_buttons=None, selectbox_values=None):
        self.session_state = {}
        self._submit_pin = submit_pin
        self._pin_name = pin_name
        self._clicked_buttons = set(clicked_buttons or [])
        self._selectbox_values = selectbox_values or {}
        self.markdown_calls = []
        self.caption_calls = []
        self.dataframe_calls = []

    def markdown(self, text, **k):
        self.markdown_calls.append(text)

    def caption(self, text, **k):
        self.caption_calls.append(text)

    def dataframe(self, df, **k):
        self.dataframe_calls.append(df)

    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [_FakeCtx() for _ in range(n)]

    def form(self, key, **k):
        return _FakeCtx()

    def text_input(self, label, value="", **k):
        return self._pin_name

    def form_submit_button(self, *a, **k):
        return self._submit_pin

    def button(self, label, key=None, **k):
        return key in self._clicked_buttons

    def selectbox(self, label, options, index=0, key=None, **k):
        if key in self._selectbox_values:
            return self._selectbox_values[key]
        return options[index] if options else None


def _results(earliest=45, success=0.85, median=1_000_000, p10=500_000):
    return {
        "earliest_retirement_age": earliest,
        "primary_result": {
            "retirement_age": earliest,
            "success_rate": success,
            "median_final": median,
            "p10_final": p10,
        },
    }


# ---------------------------------------------------------------------------
# diff_overrides — pure function
# ---------------------------------------------------------------------------

def test_diff_excludes_identical_keys():
    a = {"YOUR_AGE": 30, "STATE_CHOICE": "CA"}
    b = {"YOUR_AGE": 30, "STATE_CHOICE": "CA"}
    assert scenario_compare.diff_overrides(a, b) == []


def test_diff_includes_differing_values():
    a = {"YOUR_AGE": 30}
    b = {"YOUR_AGE": 35}
    diffs = scenario_compare.diff_overrides(a, b)
    assert diffs == [("YOUR_AGE", 30, 35)]


def test_diff_treats_one_sided_key_as_vs_default():
    a = {"LTC_ENABLED": True}
    b = {}
    diffs = scenario_compare.diff_overrides(a, b)
    assert diffs == [("LTC_ENABLED", True, scenario_compare._NO_VALUE)]


# ---------------------------------------------------------------------------
# Pin action — new {summary, overrides} shape
# ---------------------------------------------------------------------------

def test_pin_action_stores_summary_and_overrides():
    st = _FakeSt(submit_pin=True, pin_name="Baseline")
    st.session_state["user_overrides"] = {"YOUR_AGE": 30, "TARGET_RETIREMENT_AGE": 50}
    scenario_compare.render(st, results=_results())

    pinned = st.session_state["pinned_scenarios"]
    assert "Baseline" in pinned
    entry = pinned["Baseline"]
    assert entry["overrides"] == {"YOUR_AGE": 30, "TARGET_RETIREMENT_AGE": 50}
    assert entry["summary"]["earliest_retirement_age"] == 45
    assert entry["summary"]["success_rate"] == 0.85


def test_render_reads_legacy_flat_shape_without_crashing():
    """A pin written before this change (flat summary dict, no 'overrides' key)
    must still render via the defensive entry.get('summary', entry) fallback."""
    st = _FakeSt()
    st.session_state["pinned_scenarios"] = {
        "Old pin": scenario_compare._extract_summary(_results(earliest=50)),
    }
    # render() early-returns before the card loop when results is falsy
    # (pre-existing behavior, unrelated to the shape being tested here) --
    # pass a valid results dict so we reach the loop.
    scenario_compare.render(st, results=_results(earliest=99))
    # No exception, and the OLD pin's earliest age (50, not the new run's 99)
    # made it into the card markup.
    assert any("50" in text for text in st.markdown_calls)


# ---------------------------------------------------------------------------
# Compare-inputs impact computation — lazy, only on button click
# ---------------------------------------------------------------------------

def _two_pins():
    return {
        "A": {
            "summary": {"earliest_retirement_age": 45, "success_rate": 0.85},
            "overrides": {
                "YOUR_AGE": 30, "TARGET_RETIREMENT_AGE": 50,
                "YOUR_BASE_SALARY": 100_000, "YOUR_401K_CONTRIBUTION": 5_000,
            },
        },
        "B": {
            "summary": {"earliest_retirement_age": 47, "success_rate": 0.80},
            "overrides": {
                "YOUR_AGE": 30, "TARGET_RETIREMENT_AGE": 50,
                "YOUR_BASE_SALARY": 100_000, "YOUR_401K_CONTRIBUTION": 20_000,
            },
        },
    }


def test_impact_not_computed_without_button_click():
    st = _FakeSt(selectbox_values={"scenario_compare_a": "A", "scenario_compare_b": "B"})
    scenario_compare._render_compare_inputs(st, _two_pins())
    assert st.session_state.get("scenario_compare_impacts", {}) == {}


def test_impact_computed_only_for_clicked_row():
    impact_key = "cmp_impact_A|B|YOUR_401K_CONTRIBUTION"
    st = _FakeSt(
        selectbox_values={"scenario_compare_a": "A", "scenario_compare_b": "B"},
        clicked_buttons={impact_key},
    )
    scenario_compare._render_compare_inputs(st, _two_pins())
    impacts = st.session_state.get("scenario_compare_impacts", {})
    assert "A|B|YOUR_401K_CONTRIBUTION" in impacts
    entry = impacts["A|B|YOUR_401K_CONTRIBUTION"]
    assert "earliest_retirement_age" in entry
    assert "success_rate" in entry


def test_same_scenario_both_sides_shows_caption_not_table():
    st = _FakeSt(selectbox_values={"scenario_compare_a": "A", "scenario_compare_b": "A"})
    scenario_compare._render_compare_inputs(st, _two_pins())
    assert st.dataframe_calls == []
    assert any("different scenarios" in c for c in st.caption_calls)
