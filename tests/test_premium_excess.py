"""Excess provisional health premium: only cash Pass 1 really delivered goes
back to the portfolio (conservation), and the withdrawal log stays consistent."""

import pytest

from retirement_sim import config as cfg
from retirement_sim import account_simulation as sim
from retirement_sim.account_simulation import Account, AccountPortfolio, AccountType


@pytest.fixture(autouse=True)
def _no_ss():
    saved = cfg.INCLUDE_SOCIAL_SECURITY
    cfg.INCLUDE_SOCIAL_SECURITY = False
    try:
        yield
    finally:
        cfg.INCLUDE_SOCIAL_SECURITY = saved


def _run(monkeypatch, cash, brokerage=0.0, true_premium=8_000.0,
         expenses=50_000.0, provisional=20_000.0):
    p = AccountPortfolio()
    p.add_account(Account("your_cash", AccountType.CASH, cash, "you"))
    if brokerage:
        p.add_account(Account("your_brokerage", AccountType.TAXABLE, brokerage, "you"))
    p.reset_yearly_income()
    p._current_year_withdrawals = {k: 0.0 for k in p._current_year_withdrawals}
    monkeypatch.setattr(p, "quote_health_insurance_cost", lambda *a, **k: true_premium)
    before = p.get_total_balance()
    taxes_before = p.total_taxes_paid
    ok, rmd, surplus = sim._fund_net_expenses(
        p, 55, expenses, provisional, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    taxes = p.total_taxes_paid - taxes_before
    return p, ok, rmd, surplus, before, taxes


def test_fully_funded_excess_is_returned(monkeypatch):
    # Pass 1 delivered the full provisional 70,000; true need 58,000.
    p, ok, _rmd, surplus, before, taxes = _run(monkeypatch, cash=500_000)
    assert ok
    assert surplus == pytest.approx(12_000.0)
    assert before - p.get_total_balance() == pytest.approx(58_000.0 + taxes, abs=1e-6)
    # Log: only the 58,000 actually consumed stays in the withdrawals.
    assert sum(p._current_year_withdrawals.values()) == pytest.approx(58_000.0, abs=1e-6)
    assert p._premium_excess_returned == pytest.approx(12_000.0)


def test_pass1_short_creates_no_money(monkeypatch):
    # Cash 56,000, need 70,000: Pass 1 delivers 56,000 only; true need 58,000.
    # Case from the review: the portfolio must end at 0, not 12,000.
    p, ok, _rmd, surplus, before, taxes = _run(monkeypatch, cash=56_000)
    assert surplus == pytest.approx(0.0)
    assert p.get_total_balance() == pytest.approx(0.0, abs=1e-6)
    assert p._premium_excess_returned == 0.0
    # 56,000 is within the 1% tolerance? No: 56,000 < 58,000 * 0.99, so it fails.
    assert not ok


def test_partly_short_returns_only_the_delivered_part(monkeypatch):
    # Cash 66,000, need 70,000 (short 4,000), true need 58,000: 8,000 comes back.
    p, ok, _rmd, surplus, before, taxes = _run(monkeypatch, cash=66_000)
    assert ok
    assert surplus == pytest.approx(8_000.0)
    assert p.get_total_balance() == pytest.approx(8_000.0, abs=1e-6)


def test_depleted_portfolio_ends_at_zero(monkeypatch):
    # Whole portfolio (cash + brokerage with no gain) is 56,000: nothing returned.
    p, ok, _rmd, surplus, _b, _t = _run(monkeypatch, cash=20_000, brokerage=36_000)
    assert surplus == pytest.approx(0.0)
    assert p.get_total_balance() <= 1e-6


def test_zero_excess_changes_nothing(monkeypatch):
    p, ok, _rmd, surplus, before, taxes = _run(monkeypatch, cash=500_000, true_premium=20_000.0)
    assert ok
    assert surplus == 0.0
    assert p._premium_excess_returned == 0.0
    assert before - p.get_total_balance() == pytest.approx(70_000.0 + taxes, abs=1e-6)
    assert sum(p._current_year_withdrawals.values()) == pytest.approx(70_000.0, abs=1e-6)


def test_excess_does_not_shrink_rmd_in_log(monkeypatch):
    p, ok, rmd, surplus, before, _t = _run(monkeypatch, cash=500_000)
    p.withdrawal_log = []
    sim._flush_withdrawal_log(p, 75, 30_000.0, before, 0.0, 0.0, 0.0, 0.0,
                              reinvested_surplus=surplus)
    row = p.withdrawal_log[-1]
    assert row["rmd_spent"] == pytest.approx(30_000.0)
