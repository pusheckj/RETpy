"""UI smoke test — import every component and verify sim pipeline.

Run from project root:
    python ui/_smoke_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path
import traceback

UI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = UI_DIR.parent
for p in (PROJECT_ROOT, UI_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


class MockSt:
    """Tolerant mock for `st` that accepts anything without crashing."""
    def __init__(self, name="st"):
        self.name = name
        self.session_state = {"user_overrides": {}, "results": None, "profile": "Median US 25-year-old household"}
    def __getattr__(self, attr):
        def _catchall(*args, **kwargs):
            return MockSt(f"{self.name}.{attr}(...)")
        return _catchall
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def columns(self, n):
        return [MockSt(f"col{i}") for i in range(n if isinstance(n, int) else len(n))]
    def tabs(self, names): return [MockSt(f"tab:{n}") for n in names]
    def expander(self, *a, **k): return self


def test_imports():
    print("\n== Import check ==")
    modules = [
        "components.profile_picker",
        "components.account_inputs",
        "components.hero_metric", "components.stats_row", "components.scenario_compare",
        "components.decision_narrative",
        "components.what_if_pane",
        "components.success_by_age", "components.allocation_chart",
        "components.income_sources_chart", "components.portfolio_breakdown",
        "components.withdrawal_drawdown_chart",
        "components.savings_rate_inputs",
        "components.savings_projection_chart",
        "components.net_worth_projection_chart",
        "components.spending_inputs",
        "components.spending_chart",
        "components.income_over_time",
        "components.trajectories_tab", "components.tax_tab", "components.withdrawal_tab",
        "components.sensitivity_tab",
        "components.stress_presets",
        "components.mortgage_paydown_tab",
        "components.print_summary",
        "components.export_page",
        "components.cache_panel",
        "utils.disk_cache",
        "components.faq",
        "components.theme_toggle",
        "components.sec_about_you",
        "components.sec_income",
        "components.sec_taxes",
        "components.sec_expenses",
        "components.sec_big_purchases",
        "components.sec_savings",
        "components.sec_retirement_goals",
        "components.sec_assumptions",
        "utils.derived",
        "utils.formatting", "utils.sim_runner", "utils.config_builder",
    ]
    errors = []
    for m in modules:
        try:
            __import__(m)
            print(f"  OK   {m}")
        except Exception as e:
            print(f"  FAIL {m}: {type(e).__name__}: {e}")
            errors.append((m, e))
    return errors


def test_sim_pipeline():
    print("\n== Simulation pipeline (fast: 200 sims) ==")
    try:
        from utils.sim_runner import run_full_analysis
        result = run_full_analysis(user_overrides={}, n_simulations=200, target_retirement_age=55)
        assert result is not None
        pr = result.get("primary_result", {}) or {}
        print(f"  OK   success_rate={pr.get('success_rate', 0):.1%}, earliest={result.get('earliest_retirement_age')}")
        return None
    except Exception as e:
        traceback.print_exc()
        return e


if __name__ == "__main__":
    import_errors = test_imports()
    sim_error = test_sim_pipeline()
    print("\n== Summary ==")
    if not import_errors and sim_error is None:
        print("  ✔ All smoke tests passed.")
        sys.exit(0)
    else:
        print(f"  ✘ {len(import_errors)} import errors, sim_error={sim_error}")
        sys.exit(1)
