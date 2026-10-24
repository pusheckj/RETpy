"""One figure per concept: the numbers different sections show for the same
thing agree (or are labelled as different things).

* Savings vs Taxes: the Savings summary's tax is the Taxes section's tax, which
  is the simulation's first working year (working_year_cashflow), and "left to
  save" is what the simulation saves that year.
"""
import os
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import account_simulation as asim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from utils import derived  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils.profile_io import deserialize_overrides  # noqa: E402

FIXTURES = ["sample_household", "single_renter", "couple_three_kids", "single_parent_hoh"]


def _ui_shaped(name: str) -> dict:
    """A fixture as the sidebar holds it: the Income section rewrites the comp
    table from the income inputs every rerun, with no explicit take-home."""
    with open(os.path.join(_TESTS, "fixtures", name + ".json"), encoding="utf-8") as fh:
        ov = deserialize_overrides(fh.read())
    comp = ov.get("YOUR_COMPENSATION_BY_AGE") or {}
    ov["YOUR_COMPENSATION_BY_AGE"] = {
        age: {k: v for k, v in row.items() if k != "after_tax"} for age, row in comp.items()}
    return ov


def _comp_table(age: int, base: int) -> dict:
    """A one-row comp table, as the Income section writes it for this base pay."""
    return {int(age): {"base": base, "bonus": 0, "rsu_gross": 0, "total_comp": base, "saved": 0}}


def _engine_year_one(ov: dict):
    """(working_year_cashflow at today's age, the savings rows, HSA match)."""
    original = sr._apply_overrides(sr.build_config_overrides(ov))
    try:
        cf = asim.working_year_cashflow(cfg.YOUR_AGE)
        rows = sr._approximate_savings_contributions(int(ov.get("TARGET_RETIREMENT_AGE", 60)))
        hsa_match = float(getattr(cfg, "YOUR_HSA_MATCH", 0) or 0)
        college = float(cfg.calculate_529_contribution(cfg.YOUR_AGE))
    finally:
        sr._restore_overrides(original)
    return cf, rows, hsa_match, college


def _own_savings(row: dict, hsa_match: float) -> float:
    """What the household itself put away that year (employer money excluded)."""
    keys = ("your_401k", "your_hsa", "your_roth", "your_aftertax_roth", "your_brokerage",
            "partner_401k", "partner_roth", "partner_brokerage")
    return sum(float(row[k]) for k in keys) - hsa_match


# ---------------------------------------------------------------------------
# #10 Savings summary vs Taxes section
# ---------------------------------------------------------------------------
class TestSavingsAndTaxesAgree:
    @pytest.mark.parametrize("name", FIXTURES)
    def test_one_tax_figure_and_it_is_the_engines(self, name):
        ov = _ui_shaped(name)
        budget = derived.sidebar_savings_budget({"user_overrides": ov})
        ov.update(budget["amounts"])               # what the Savings section writes
        taxes_section = derived.sidebar_savings_budget({"user_overrides": ov})["taxes"]
        cf, _, _, _ = _engine_year_one(ov)
        assert budget["taxes"]["total"] == pytest.approx(taxes_section["total"], abs=0.01)
        assert budget["taxes"]["total"] == pytest.approx(cf["total_tax"], abs=0.01)
        assert budget["income"] == pytest.approx(cf["gross_income"])

    @pytest.mark.parametrize("name", FIXTURES)
    def test_left_to_save_is_what_the_simulation_saves(self, name):
        ov = _ui_shaped(name)
        if not str(ov.get("SAVINGS_MODE", "")).startswith("Auto"):
            pytest.skip("only the auto modes save everything that's left")
        budget = derived.sidebar_savings_budget({"user_overrides": ov})
        ov.update(budget["amounts"])
        _, rows, hsa_match, college = _engine_year_one(ov)
        saved = _own_savings(rows[0], hsa_match) + college
        if rows[0]["your_brokerage"] + rows[0]["partner_brokerage"] > 0:
            assert saved == pytest.approx(budget["disposable"], abs=1.0)
        else:
            # Kept amounts above what's left: the simulation still makes them
            # and sells investments for the gap, so it saves more than is left.
            assert saved >= budget["disposable"]

    def test_mega_backdoor_and_529_are_paid_before_the_brokerage(self):
        """Auto-allocate's brokerage share must not exceed the simulation's sweep:
        the engine treats it as a floor and would sell investments to fund it."""
        ov = _ui_shaped("single_renter")
        ov.update(SAVINGS_MODE=derived.AUTO_ALLOCATE_MODE, YOUR_BASE_SALARY=200_000,
                  YOUR_AFTER_TAX_401K_PCT=0.10, YOUR_401K_MATCH_PCT=0.05,
                  YOUR_COMPENSATION_BY_AGE=_comp_table(ov["YOUR_AGE"], 200_000))
        budget = derived.savings_budget(ov)
        assert derived.AFTER_TAX_401K_LABEL in budget["set_aside"]
        ov.update(budget["amounts"])
        _, rows, hsa_match, _ = _engine_year_one(ov)
        floor = ov["YOUR_BROKERAGE_CONTRIBUTION"]
        assert rows[0]["your_brokerage"] >= floor - 1
        assert rows[0]["your_aftertax_roth"] == pytest.approx(
            budget["set_aside"][derived.AFTER_TAX_401K_LABEL])
        placed = sum(budget["amounts"].values()) + sum(budget["set_aside"].values())
        assert placed == pytest.approx(budget["disposable"], abs=1.0)

    @pytest.mark.parametrize("mode", [derived.AUTO_ALLOCATE_MODE, derived.CUSTOM_PCT_MODE])
    def test_settles_and_does_not_drift_across_reruns(self, mode):
        ov = _ui_shaped("single_renter")
        ov.update(SAVINGS_MODE=mode, YOUR_BASE_SALARY=60_000,
                  YOUR_COMPENSATION_BY_AGE=_comp_table(ov["YOUR_AGE"], 60_000))
        state = {"user_overrides": ov}
        first = derived.sidebar_savings_budget(state)
        ov.update(first["amounts"])
        second = derived.sidebar_savings_budget(state)
        assert second["disposable"] == first["disposable"]
        assert second["amounts"] == first["amounts"]
        # Pre-tax saving lowered the tax, so more is left than with none.
        no_pretax = derived.compute_taxes({**ov, **{k: 0 for k in derived.PRETAX_KEYS}})
        assert first["taxes"]["total"] < no_pretax["total"]


def _sidebar_script():
    import os
    import sys
    sys.path.insert(0, os.environ["CONSISTENT_TEST_UI_DIR"])
    import streamlit as st
    from components import sec_savings, sec_taxes
    sec_taxes.render_body(st)
    sec_savings.render_body(st)


def test_sidebar_shows_one_tax_figure(monkeypatch):
    """Taxes draws before Savings in the sidebar; both show the same tax."""
    from streamlit.testing.v1 import AppTest
    from utils.formatting import money
    monkeypatch.setenv("CONSISTENT_TEST_UI_DIR", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    ov = _ui_shaped("sample_household")
    at = AppTest.from_function(_sidebar_script, default_timeout=60)
    at.session_state["user_overrides"] = dict(ov)
    at.run()
    assert not at.exception, at.exception
    cf, _, _, _ = _engine_year_one(dict(at.session_state["user_overrides"]))
    shown = money(cf["total_tax"], shorten=True)
    savings_tax = next(m.value for m in at.metric if m.label == "− Taxes")
    assert savings_tax == shown
    assert any(f"Total tax: {shown}" in c.value.replace("\\$", "$") for c in at.caption)
    labels = [m.label for m in at.metric]
    assert "= Left to save" in labels and "= Disposable" not in labels


# ---------------------------------------------------------------------------
# #6 Savings tiles, stacked bars and savings-rate bars: one sum, the engine's
# ---------------------------------------------------------------------------
def _savings_charts_script():
    import os
    import sys
    sys.path.insert(0, os.environ["CONSISTENT_TEST_UI_DIR"])
    import streamlit as st
    from components import savings_projection_chart, savings_rate_chart
    results = st.session_state["_results"]
    savings_projection_chart.render(st, results=results)
    savings_rate_chart.render(st, results=results)


def _chart_spec(element) -> dict:
    import json
    return json.loads(element.proto.spec)


def test_savings_tiles_bars_and_rate_are_one_sum(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from components.savings_rate_inputs import year_savings
    from utils.formatting import money
    monkeypatch.setenv("CONSISTENT_TEST_UI_DIR", _UI)
    ov = _ui_shaped("sample_household")
    ov.update(derived.savings_budget(ov)["amounts"])
    _, rows, _, _ = _engine_year_one(ov)

    at = AppTest.from_function(_savings_charts_script, default_timeout=60)
    at.session_state["_results"] = {"primary_result": {"savings_contributions_by_year": rows}}
    at.session_state["user_overrides"] = dict(ov, SAVINGS_INFLATION_ADJUST=False)
    at.run()
    assert not at.exception, at.exception
    tiles = {m.label: m.value for m in at.metric}
    first_rate = 100.0 * year_savings(rows[0]) / rows[0]["gross_income"]
    assert tiles["Year 1 savings"] == money(year_savings(rows[0]), shorten=True)
    assert tiles["Year 1 savings rate"] == f"{first_rate:.1f}%"
    assert "Mode" not in tiles

    bars, rate = (_chart_spec(c) for c in at.get("plotly_chart"))
    assert rate["data"][0]["y"][0] == pytest.approx(first_rate)
    stacked = {t["name"]: t["y"] for t in bars["data"] if t.get("type") == "bar"}
    assert sum(ys[0] for ys in stacked.values()) == pytest.approx(year_savings(rows[0]))
    # The employer match is the engine's: dollar for dollar up to the match %
    # of base pay (here 5% of $180k), not a share of household income.
    match = min(ov["YOUR_401K_CONTRIBUTION"], ov["YOUR_BASE_SALARY"] * ov["YOUR_401K_MATCH_PCT"])
    assert stacked["Your 401(k) match"][0] == pytest.approx(match)
    assert rows[0]["your_employer_match"] == pytest.approx(match)


def test_savings_charts_wait_for_a_run():
    """Without a run there are no engine contributions to show (no stand-in)."""
    import inspect
    from components import savings_projection_chart
    src = inspect.getsource(savings_projection_chart)
    assert "project_savings" not in src and "user_overrides" in src
    assert savings_projection_chart.savings_rows(None) == []


# ---------------------------------------------------------------------------
# #7 final-balance tiles vs the trajectories table; #16 spending-range counts
# ---------------------------------------------------------------------------
N_RUNS = 200


@pytest.fixture(scope="module")
def sample_run():
    from tests.conftest import load_sample_household
    ov = load_sample_household()
    age = int(ov["TARGET_RETIREMENT_AGE"])
    return ov, sr.run_full_analysis(ov, n_simulations=N_RUNS, target_retirement_age=age,
                                    scan_age_range=(age, age + 1, 1))


def test_primary_result_describes_every_run(sample_run):
    _, res = sample_run
    pr = res["primary_result"]
    assert pr["n_simulations"] == N_RUNS
    assert pr["p10_final"] <= pr["p25_final"] <= pr["median_final"] <= pr["p75_final"] <= pr["p90_final"]
    # The spending range covers every run, not the ~1/3 detail sample.
    assert max(r["n"] for r in pr["spending_by_year"]) == N_RUNS
    assert len(pr["sample_successes"]) == len(pr["sample_paths"])


def _results_script():
    import os
    import sys
    sys.path.insert(0, os.environ["CONSISTENT_TEST_UI_DIR"])
    import streamlit as st
    from components import spending_range_chart, stats_row, trajectories_tab
    results = st.session_state["_results"]
    stats_row.render(st, results=results)
    trajectories_tab.render(st, results=results)
    spending_range_chart.render(st, results=results)


def test_tiles_table_and_counts_agree(sample_run, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from utils.formatting import money
    monkeypatch.setenv("CONSISTENT_TEST_UI_DIR", _UI)
    ov, res = sample_run
    pr = res["primary_result"]
    at = AppTest.from_function(_results_script, default_timeout=60)
    at.session_state["_results"] = res
    at.session_state["user_overrides"] = dict(ov)
    at.run()
    assert not at.exception, at.exception
    html = " ".join(m.value for m in at.markdown)
    table = at.dataframe[0].value
    by_pct = dict(zip(table["Percentile"], table["Final balance"]))
    # The table's median and 10th percentile are the tiles' figures.
    assert by_pct["50th (median)"] == money(pr["median_final"], shorten=True)
    assert by_pct["10th"] == money(pr["p10_final"], shorten=True)
    assert money(pr["median_final"], shorten=True) in html
    assert f"all {N_RUNS:,} simulations" in html
    assert f"out of {N_RUNS:,} simulations" in html
    tiles = {m.label: m.value for m in at.metric}
    n_out = pr["sample_successes"].count(False)
    assert tiles["Ran out of money (in this sample)"] == f"{n_out} of {len(pr['sample_paths'])}"
    assert "Median final (this sample)" not in tiles
    captions = " ".join(c.value for c in at.caption)
    assert f"Based on all {N_RUNS:,} simulated runs" in captions


def test_a_sample_path_that_ran_out_is_drawn_red():
    from components.trajectories_tab import sample_outcomes
    pr = {"sample_paths": [[(60, 5e5), (61, 4e4)], [(60, 5e5), (61, 6e5)]],
          "sample_successes": [False, True]}
    # The failed path's last recorded balance is $40k, not $0: the flag decides.
    assert [bad for _, bad in sample_outcomes(pr)] == [True, False]
