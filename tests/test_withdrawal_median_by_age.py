"""The per-year withdrawal / income / tax charts show a cross-run statistic,
not one representative run.

They used to plot the withdrawal_log of the single surviving run whose FINAL
balance was nearest the median. That run's one-off years (a long-term-care
year, a giant forced RMD on a lucky high-return path) were then drawn as if
they were the typical plan: bars of $300k-$750k late in retirement on top of a
steady ~$100-150k pattern. Each age now shows the MEDIAN draw across the runs
that last the plan, split by source in those runs' average mix.
See ui/utils/sim_runner.py::_median_withdrawal_log_from_data.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import pytest

from utils import sim_runner as sr

_RET, _END = 65, 90
_STEADY = 100_000.0


def _row(age, *, cash=0.0, taxable=0.0, chosen=0.0, rmd=0.0, roth=0.0, hsa=0.0,
         pv=2_000_000.0, taxes=10_000.0, niit=0.0, rmd_gross=None, conv=0.0):
    total = cash + taxable + chosen + rmd + roth + hsa
    return {
        "age": age, "cash": cash, "taxable": taxable, "traditional": chosen + rmd,
        "traditional_chosen": chosen, "rmd_spent": rmd,
        "rmd_gross": rmd if rmd_gross is None else rmd_gross,
        "roth": roth, "hsa": hsa, "total": total, "portfolio_value": pv,
        "withdrawal_pct": total / pv, "total_taxes": taxes, "ss_tax": 0.0,
        "niit": niit, "penalties": 0.0, "roth_conversion": conv,
        "roth_conversion_tax": 0.0,
    }


def _steady_log():
    return [_row(a, chosen=_STEADY) for a in range(_RET, _END + 1)]


def _spiky_paths():
    """Five surviving runs drawing a steady $100k of traditional money; run 2
    has long-term-care years (LTC bill paid from taxable + traditional, with
    the tax on it) at 85 and 88. Run 2 also has the MEDIAN final balance, so
    the old closest-to-median-final selection picked exactly that run."""
    logs = [_steady_log() for _ in range(5)]
    for age in (85, 88):
        logs[2][age - _RET] = _row(age, taxable=300_000.0, chosen=300_000.0,
                                   taxes=170_000.0)
    finals = [1.0e6, 2.0e6, 3.0e6, 4.0e6, 5.0e6]
    paths = [[(_RET, 2.0e6), (_END, f)] for f in finals]
    return paths, logs, [True] * 5


def test_one_runs_ltc_years_are_not_shown_as_the_typical_plan():
    paths, logs, ok = _spiky_paths()
    rows = sr._median_withdrawal_log_from_data(paths, logs, ok)
    by_age = {r["age"]: r for r in rows}
    assert sorted(by_age) == list(range(_RET, _END + 1))
    for age in (85, 88):
        assert by_age[age]["total"] == pytest.approx(_STEADY)
        assert by_age[age]["total_taxes"] == pytest.approx(10_000.0)
    assert max(r["total"] for r in rows) == pytest.approx(_STEADY)


def test_income_and_tax_rows_built_from_it_carry_no_spike():
    paths, logs, ok = _spiky_paths()
    rows = sr._median_withdrawal_log_from_data(paths, logs, ok)
    income = sr._approximate_income_sources(rows, _RET)
    draws = [r["traditional"] + r["roth"] + r["taxable"] + r["hsa"] for r in income]
    assert max(draws) == pytest.approx(_STEADY)
    taxes = {r["age"]: r for r in sr._approximate_taxes(rows, _RET)}
    assert taxes[85]["federal"] == pytest.approx(10_000.0)


def test_total_is_the_per_age_median_and_the_buckets_add_up():
    rng = np.random.default_rng(3)
    logs = []
    for _ in range(7):
        log = []
        for a in range(_RET, _END + 1):
            log.append(_row(a, taxable=float(rng.uniform(0, 60e3)),
                            chosen=float(rng.uniform(0, 60e3)),
                            rmd=float(rng.uniform(0, 30e3)) if a >= 75 else 0.0,
                            roth=float(rng.uniform(0, 20e3)),
                            pv=float(rng.uniform(5e5, 3e6)),
                            taxes=float(rng.uniform(0, 40e3)),
                            conv=float(rng.uniform(0, 50e3))))
        logs.append(log)
    paths = [[(_RET, 1.0), (_END, float(i))] for i in range(7)]
    rows = sr._median_withdrawal_log_from_data(paths, logs, [True] * 7)
    for r in rows:
        k = r["age"] - _RET
        col = lambda f: [lg[k][f] for lg in logs]  # noqa: E731
        assert r["total"] == pytest.approx(float(np.median(col("total"))))
        assert r["portfolio_value"] == pytest.approx(float(np.median(col("portfolio_value"))))
        assert r["total_taxes"] == pytest.approx(float(np.median(col("total_taxes"))))
        assert r["roth_conversion"] == pytest.approx(float(np.median(col("roth_conversion"))))
        parts = r["cash"] + r["taxable"] + r["traditional"] + r["roth"] + r["hsa"]
        assert parts == pytest.approx(r["total"])
        assert r["traditional"] == pytest.approx(r["traditional_chosen"] + r["rmd_spent"])
        assert r["rmd_gross"] >= r["rmd_spent"] - 1e-6
        assert r["withdrawal_pct"] == pytest.approx(r["total"] / r["portfolio_value"])
        assert r["n_paths"] == 7


def test_split_is_the_runs_average_mix_when_sources_differ_by_run():
    # The year taxable money runs out differs by run: at 70, three runs still
    # draw taxable and two have moved to traditional. Per-source medians would
    # show taxable only; the average mix keeps both, scaled to the median total.
    logs = [_steady_log() for _ in range(5)]
    for i in range(3):
        logs[i][70 - _RET] = _row(70, taxable=_STEADY)
    paths = [[(_RET, 1.0), (_END, float(i))] for i in range(5)]
    row = {r["age"]: r for r in sr._median_withdrawal_log_from_data(paths, logs, [True] * 5)}[70]
    assert row["taxable"] == pytest.approx(0.6 * _STEADY)
    assert row["traditional"] == pytest.approx(0.4 * _STEADY)


def test_assembled_primary_result_uses_the_median_and_says_so():
    paths, logs, ok = _spiky_paths()
    chunk = {
        "finals": [p[-1][1] for p in paths], "successes": 5, "n": 5,
        "details": [{"trajectory": p, "success": s, "withdrawal_log": lg, "bytype": []}
                    for p, s, lg in zip(paths, ok, logs)],
        "spending_by_age": {},
    }
    pr = sr._assemble_primary_from_chunks(_RET, [chunk])
    assert max(r["total"] for r in pr["withdrawals_by_year"]) == pytest.approx(_STEADY)
    inc = pr["income_sources_by_year"]
    assert max(r["traditional"] + r["taxable"] for r in inc) == pytest.approx(_STEADY)
    assert pr["withdrawals_basis"] == {"n_runs": 5, "survivors_only": True}


def test_survivors_are_preferred_and_depleted_runs_fall_back():
    paths, logs, _ = _spiky_paths()
    # A failed run with huge draws must not move the survivors' median.
    logs.append([_row(a, taxable=900_000.0) for a in range(_RET, 70)])
    paths.append([(_RET, 1.0), (69, 0.0)])
    ok = [True] * 5 + [False]
    rows = sr._median_withdrawal_log_from_data(paths, logs, ok)
    assert rows[0]["total"] == pytest.approx(_STEADY)
    assert rows[0]["n_paths"] == 5
    # With no survivors at all, every run counts (ages each run reached).
    rows = sr._median_withdrawal_log_from_data(paths, logs, [False] * 6)
    assert rows[0]["n_paths"] == 6
    assert rows[-1]["age"] == _END


def test_withdrawals_basis_reports_fallback():
    assert sr._withdrawals_basis([True, False]) == {"n_runs": 1, "survivors_only": True}
    assert sr._withdrawals_basis([False, False]) == {"n_runs": 2, "survivors_only": False}


def test_income_chart_labels_and_caption():
    from components import income_over_time as iot
    assert "Partner base salary" in iot._WORKING_LABELS
    assert "Partner base" not in iot._WORKING_LABELS
    cap = iot.retirement_caption(
        {"primary_result": {"withdrawals_basis": {"n_runs": 250, "survivors_only": True}}})
    assert "median year across the 250 simulated runs that last the whole plan" in cap
    cap = iot.retirement_caption(
        {"primary_result": {"withdrawals_basis": {"n_runs": 40, "survivors_only": False}}})
    assert "all 40 simulated runs" in cap
    assert "Run the simulation" in iot.retirement_caption(None)


def test_income_chart_series_follow_the_median_rows():
    from components import income_over_time as iot
    paths, logs, ok = _spiky_paths()
    rows = sr._median_withdrawal_log_from_data(paths, logs, ok)
    results = {"primary_result": {"income_sources_by_year": sr._approximate_income_sources(rows, _RET)}}
    ages, series = iot.build_income_series({"YOUR_AGE": 60, "PARTNER_AGE": 0,
                                            "INCLUDE_SOCIAL_SECURITY": False},
                                           results, 60, _RET, _END)
    draws = [v for k, v in series.items() if k != "Social Security"]
    stacked = [sum(v[i] for v in draws) for i in range(len(ages))]
    assert max(stacked[ages.index(_RET):]) == pytest.approx(_STEADY)
