"""EXTRA_ANNUAL_SAVINGS: spend this much less each working year and invest it.

The What-if tile's "Extra annual savings" lever writes it. It must add to the plan in both
savings modes. Before it existed, the lever raised YOUR_BROKERAGE_CONTRIBUTION, which is only a
floor in Auto mode (no effect while the sweep is larger) and a replacement in Manual mode.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim.account_simulation import run_detailed_simulation  # noqa: E402


def _balance_at_retirement(monkeypatch, mode, extra):
    monkeypatch.setattr(cfg, "SAVINGS_MODE", mode)
    monkeypatch.setattr(cfg, "EXTRA_ANNUAL_SAVINGS", extra)
    retire = cfg.YOUR_AGE + 10
    _, portfolio = run_detailed_simulation(retire, random_seed=7)
    row = next(r for r in portfolio.yearly_history if r["age"] == retire)
    return row["total"]


@pytest.mark.parametrize("mode", ["Auto-allocate (recommended)", "Manual"])
def test_extra_savings_raise_the_balance_at_retirement(monkeypatch, mode):
    base = _balance_at_retirement(monkeypatch, mode, 0)
    more = _balance_at_retirement(monkeypatch, mode, 20_000)
    # Ten years of $20k (real) plus growth: at least $200k more.
    assert more - base >= 200_000 * 0.95


def test_default_is_zero():
    assert cfg.EXTRA_ANNUAL_SAVINGS == 0


def _run(monkeypatch, mode, extra):
    monkeypatch.setattr(cfg, "SAVINGS_MODE", mode)
    monkeypatch.setattr(cfg, "EXTRA_ANNUAL_SAVINGS", extra)
    _, portfolio = run_detailed_simulation(cfg.YOUR_AGE + 10, random_seed=7)
    return portfolio


@pytest.mark.parametrize("mode", ["Auto-allocate (recommended)", "Manual"])
def test_the_money_comes_from_lower_working_year_spending(monkeypatch, mode):
    base = _run(monkeypatch, mode, 0)
    more = _run(monkeypatch, mode, 5_000)
    work = [r for r in base.spending_log if r["age"] < cfg.YOUR_AGE + 10]
    work_more = [r for r in more.spending_log if r["age"] < cfg.YOUR_AGE + 10]
    assert work and len(work) == len(work_more)
    for a, b in zip(work, work_more):
        assert a["living"] - b["living"] == pytest.approx(min(5_000, a["living"]))


def test_extra_savings_are_capped_at_spending(monkeypatch):
    mode = "Auto-allocate (recommended)"
    capped = _run(monkeypatch, mode, 10_000_000)
    assert all(r["living"] >= 0 for r in capped.spending_log if r["age"] < cfg.YOUR_AGE + 10)
    spend = sum(r["living"] for r in _run(monkeypatch, mode, 0).spending_log
                if r["age"] < cfg.YOUR_AGE + 10)
    gain = (next(r for r in capped.yearly_history if r["age"] == cfg.YOUR_AGE + 10)["total"]
            - next(r for r in _run(monkeypatch, mode, 0).yearly_history if r["age"] == cfg.YOUR_AGE + 10)["total"])
    # No more than the spending removed, plus growth (well under 2x over 10 years).
    assert 0 < gain < 2 * spend


def test_the_lever_writes_the_new_key_and_leaves_the_brokerage_override_alone():
    from types import SimpleNamespace
    from components import whatif_retirement_curve as w
    ss = {"wifc_scenario": "historical", "wifc_stock": 80, "wifc_spend": 100.0, "wifc_savings": 15_000,
          "wifc_fee": 15, "wifc_infl": 2.75, "wifc_ss": True, "wifc_claim": 67}
    st = SimpleNamespace(session_state=ss)
    base = {"YOUR_BROKERAGE_CONTRIBUTION": 5_000, "EXTRA_ANNUAL_SAVINGS": 1_000}
    alt = w._alt_overrides(st, base)
    assert alt["EXTRA_ANNUAL_SAVINGS"] == 16_000
    assert alt.get("YOUR_BROKERAGE_CONTRIBUTION", 5_000) == 5_000


@pytest.mark.parametrize("extra_spending", [0, 60_000])
def test_the_extra_counts_once_in_surplus_and_deficit_years(monkeypatch, extra_spending):
    """In a deficit year the lower spending first shrinks the draw from the portfolio. Manual
    mode must not also add the full extra to the brokerage (that would count it twice)."""
    real = cfg.calculate_annual_expenses
    monkeypatch.setattr(cfg, "calculate_annual_expenses",
                        lambda *a, **k: real(*a, **k) + extra_spending)

    def gain(mode):
        out = []
        for extra in (0, 20_000):
            monkeypatch.setattr(cfg, "SAVINGS_MODE", mode)
            monkeypatch.setattr(cfg, "EXTRA_ANNUAL_SAVINGS", extra)
            _, p = run_detailed_simulation(cfg.YOUR_AGE + 1, random_seed=3)
            out.append(next(r for r in p.yearly_history if r["age"] == cfg.YOUR_AGE + 1)["total"])
        return out[1] - out[0]

    auto, manual = gain("Auto-allocate (recommended)"), gain("Manual")
    # Each mode gains the extra plus a little tax saved on a smaller draw (the two modes
    # fund a deficit from different accounts, so the tax part differs). Never about 2x.
    for g in (auto, manual):
        assert 20_000 * 0.95 <= g <= 20_000 * 1.4
