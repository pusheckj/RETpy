"""Tests for the spending-range boxplot data pipeline.

The engine records per-year household spending in ``portfolio.spending_log``
(added additively — must not change results), and sim_runner aggregates it into
per-age percentiles (``spending_by_year``) that drive the boxplot. These pin:
1. spending_log is populated across accumulation + retirement with age/living/total.
2. _spending_percentiles yields monotone per-age percentiles.
3. accumulation spending has NO cross-scenario spread; retirement DOES (guardrails).
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from retirement_sim.account_simulation import run_detailed_simulation
from utils import sim_runner as sr


def test_spending_log_is_populated():
    _, portfolio = run_detailed_simulation(50, random_seed=1)
    log = portfolio.spending_log
    assert log, "spending_log should be recorded"
    row = log[-1]
    assert {"age", "living", "total"} <= set(row)
    assert row["total"] >= row["living"] >= 0  # total adds healthcare/LTC/car
    ages = [r["age"] for r in log]
    assert min(ages) < 50 <= max(ages)  # spans accumulation + retirement


def test_spending_percentiles_monotone_and_flat_vs_fanned():
    # Collect several paths' logs and aggregate.
    logs = []
    for s in range(30):
        _, p = run_detailed_simulation(50, random_seed=s)
        logs.append([dict(r) for r in p.spending_log])
    pct = sr._spending_percentiles(logs)  # field='living'
    assert pct, "should produce per-age percentiles"
    for r in pct:
        assert r["p10"] <= r["p25"] <= r["p50"] <= r["p75"] <= r["p90"]
        assert r["n"] >= 1
    by_age = {r["age"]: r for r in pct}
    # Accumulation years (deterministic): zero spread.
    acc = [r for a, r in by_age.items() if a < 50]
    assert acc and all((r["p90"] - r["p10"]) == 0 for r in acc)
    # Retirement years: guardrails create a spread in at least some years.
    ret = [r for a, r in by_age.items() if a >= 50]
    assert any((r["p90"] - r["p10"]) > 0 for r in ret)
