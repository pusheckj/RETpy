"""EXTRA_ANNUAL_SAVINGS: extra money invested in the taxable brokerage each working year.

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


def test_default_is_zero_and_plain_data():
    assert cfg.EXTRA_ANNUAL_SAVINGS == 0


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
