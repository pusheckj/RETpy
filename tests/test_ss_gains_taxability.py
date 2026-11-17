"""Social Security taxability counts realized capital gains (provisional income)."""

import pytest

from retirement_sim import config as cfg
from retirement_sim import account_simulation as sim
from retirement_sim.account_simulation import Account, AccountPortfolio, AccountType


@pytest.fixture(autouse=True)
def _restore_ss_flag():
    saved = cfg.INCLUDE_SOCIAL_SECURITY
    try:
        yield
    finally:
        cfg.INCLUDE_SOCIAL_SECURITY = saved


def _portfolio_with_gains(gains):
    p = AccountPortfolio()
    p.add_account(Account("your_brokerage", AccountType.TAXABLE, 1_000_000, "you"))
    p.reset_yearly_income()
    p.year_investment_income = gains
    return p


def test_formula_40k_ss_plus_60k_gains_mfj():
    """Provisional income 60k + 20k = 80k -> the 85% cap binds: 34,000 taxable."""
    assert cfg.calculate_taxable_social_security(40_000, 60_000, status="MFJ") == pytest.approx(34_000)


def test_true_up_passes_gains_as_other_agi(monkeypatch):
    cfg.INCLUDE_SOCIAL_SECURITY = True
    seen = []
    orig = cfg.calculate_taxable_social_security

    def spy(ss, other_agi, *a, **k):
        seen.append(other_agi)
        return orig(ss, other_agi, *a, **k)

    monkeypatch.setattr(cfg, "calculate_taxable_social_security", spy)
    p = _portfolio_with_gains(60_000)
    sim._true_up_social_security_tax(p, 40_000, 0.0)
    assert seen and seen[0] == pytest.approx(60_000)
    assert p.total_ss_taxes_paid > 0


def test_provisional_quote_passes_gains_as_other_agi(monkeypatch):
    cfg.INCLUDE_SOCIAL_SECURITY = True
    monkeypatch.setattr(sim, "social_security_for_year", lambda *a, **k: {"total": 40_000})
    seen = []
    orig = cfg.calculate_taxable_social_security

    def spy(ss, other_agi, *a, **k):
        seen.append(other_agi)
        return orig(ss, other_agi, *a, **k)

    monkeypatch.setattr(cfg, "calculate_taxable_social_security", spy)
    p = _portfolio_with_gains(60_000)
    sim._collect_social_security(p, cfg.YOUR_AGE + 30, 1.0)
    assert seen and seen[0] == pytest.approx(60_000)
