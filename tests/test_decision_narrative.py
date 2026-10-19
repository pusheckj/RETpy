"""Decision-narrative pins.

Covers the new pure extractions (bridge_years_gauge.compute_verdict,
first_decade_stress.compute_unlucky_summary) directly, then the narrative
component's clause-by-clause graceful degradation on top of them.

``utils``/``components`` live under ``ui/``; add both roots to sys.path.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components import bridge_years_gauge, first_decade_stress, decision_narrative  # noqa: E402


class _FakeSt:
    """Minimal stand-in for the streamlit module (session_state + no-op UI)."""

    def __init__(self, user_overrides=None, break_even_result=None):
        self.session_state = {"user_overrides": user_overrides or {}}
        if break_even_result is not None:
            self.session_state["break_even_result"] = break_even_result
        self.markdown_calls = []

    def markdown(self, text, **kwargs):
        self.markdown_calls.append(text)


def _accessible_row(age, cash=10_000, taxable=20_000, roth=5_000, burn=15_000, penalty=0.0):
    accessible = cash + taxable + roth
    return {"age": age, "cash": cash, "taxable": taxable, "roth": roth,
            "accessible": accessible, "burn": burn, "penalty": penalty}


def _networth_row(age, p10, p50):
    return {"age": age, "p10": p10, "p50": p50}


# ---------------------------------------------------------------------------
# bridge_years_gauge.compute_verdict
# ---------------------------------------------------------------------------

def test_compute_verdict_none_when_retiring_after_59_5():
    results = {"primary_result": {"accessible_by_year": [_accessible_row(60)]}}
    assert bridge_years_gauge.compute_verdict(results, 60) is None


def test_compute_verdict_none_when_no_accessible_rows():
    results = {"primary_result": {"accessible_by_year": []}}
    assert bridge_years_gauge.compute_verdict(results, 50) is None


def test_compute_verdict_funded():
    rows = [_accessible_row(a, burn=15_000, cash=10_000, taxable=20_000, roth=5_000) for a in range(50, 60)]
    results = {"primary_result": {"accessible_by_year": rows}}
    v = bridge_years_gauge.compute_verdict(results, 50)
    assert v == {"funded": True, "first_short": None, "accessible_at_retire": 35_000.0}


def test_compute_verdict_shortfall():
    rows = [_accessible_row(a, cash=1_000, taxable=1_000, roth=1_000, burn=15_000) for a in range(50, 60)]
    results = {"primary_result": {"accessible_by_year": rows}}
    v = bridge_years_gauge.compute_verdict(results, 50)
    assert v["funded"] is False
    assert v["first_short"] == 50


# ---------------------------------------------------------------------------
# first_decade_stress.compute_unlucky_summary
# ---------------------------------------------------------------------------

def test_compute_unlucky_summary_none_when_insufficient_rows():
    results = {"primary_result": {"networth_by_year": [_networth_row(50, 100, 200)]}}
    assert first_decade_stress.compute_unlucky_summary(results, 50, 90) is None


def test_compute_unlucky_summary_depletes():
    rows = [_networth_row(50, 1_000_000, 1_200_000), _networth_row(55, 10, 900_000),
            _networth_row(60, 0, 800_000)]
    results = {"primary_result": {"networth_by_year": rows,
                                   "withdrawals_by_year": [{"total": 50_000}]}}
    s = first_decade_stress.compute_unlucky_summary(results, 50, 90)
    assert s is not None
    assert s["depletion_age"] == 55
    assert s["draw_pct"] == 0.05


def test_compute_unlucky_summary_survives():
    rows = [_networth_row(50, 1_000_000, 1_200_000), _networth_row(60, 700_000, 1_000_000)]
    results = {"primary_result": {"networth_by_year": rows, "withdrawals_by_year": []}}
    s = first_decade_stress.compute_unlucky_summary(results, 50, 90)
    assert s is not None
    assert s["depletion_age"] is None
    # An empty withdrawals_by_year is falsy, so first_draw defaults to 0.0 (not
    # None) -- draw_pct is then 0.0/start = 0.0, matching the pre-extraction
    # behavior exactly (this test pins that, doesn't change it).
    assert s["draw_pct"] == 0.0


# ---------------------------------------------------------------------------
# decision_narrative.render — clause-by-clause degradation
# ---------------------------------------------------------------------------

def _full_results():
    bridge_rows = [_accessible_row(a) for a in range(50, 60)]
    networth_rows = [_networth_row(a, 1_000_000 - a * 5_000, 1_200_000 - a * 4_000)
                      for a in range(50, 75, 5)]
    return {
        "primary_result": {
            "accessible_by_year": bridge_rows,
            "networth_by_year": networth_rows,
            "withdrawals_by_year": [{"total": 40_000}],
        }
    }


def test_narrative_renders_all_three_clauses():
    st = _FakeSt(
        user_overrides={"TARGET_RETIREMENT_AGE": 50, "PLAN_UNTIL_AGE": 90},
        break_even_result={"label": "Retirement age", "break_even_value": 52,
                            "target_success_rate": 0.8},
    )
    decision_narrative.render(st, results=_full_results())
    joined = " ".join(st.markdown_calls)
    assert "bridge to 59" in joined.lower() or "short starting" in joined.lower()
    assert "biggest risk" in joined.lower()
    assert "lever that moves your plan most" in joined.lower()


def test_narrative_degrades_without_break_even():
    st = _FakeSt(user_overrides={"TARGET_RETIREMENT_AGE": 50, "PLAN_UNTIL_AGE": 90})
    decision_narrative.render(st, results=_full_results())
    joined = " ".join(st.markdown_calls)
    assert "biggest risk" in joined.lower()
    assert "lever that moves" not in joined.lower()


def test_narrative_degrades_when_retiring_after_59_5():
    """No bridge clause, but the unlucky-path clause still renders."""
    results = _full_results()
    st = _FakeSt(user_overrides={"TARGET_RETIREMENT_AGE": 60, "PLAN_UNTIL_AGE": 90})
    decision_narrative.render(st, results=results)
    joined = " ".join(st.markdown_calls)
    assert "bridge" not in joined.lower()
    assert "biggest risk" in joined.lower()


def test_narrative_renders_nothing_when_no_data_available():
    st = _FakeSt(user_overrides={"TARGET_RETIREMENT_AGE": 50, "PLAN_UNTIL_AGE": 90})
    decision_narrative.render(st, results={"primary_result": {}})
    assert st.markdown_calls == []


def test_narrative_noop_without_results():
    st = _FakeSt()
    decision_narrative.render(st, results=None)
    assert st.markdown_calls == []
