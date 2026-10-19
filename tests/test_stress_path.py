"""
Tests for the CLI historical/stress-test path (27-stresspath).

Verifies that the historical-sequence branch of run_detailed_simulation is now
fully stochastic + correlated for bonds:
- the bond sleeve varies across runs (it is no longer pinned to
  EXPECTED_BOND_RETURN), and
- the config crisis sequences (SEQUENCE_TESTS) run to completion (solvent
  enough to reach terminal age or fail gracefully, not crash).
"""

import numpy as np
from retirement_sim import config as cfg
from retirement_sim.account_simulation import (
    generate_correlated_bond_for_stock,
    run_detailed_simulation,
)


def test_correlated_bond_varies_across_draws():
    """Given a fixed stock return, bond draws differ across runs (stochastic)."""
    np.random.seed(0)
    stock_return = -0.30  # a crisis-year real stock shock
    draws = [generate_correlated_bond_for_stock(stock_return) for _ in range(50)]
    assert len(set(round(d, 8) for d in draws)) > 1, "bond draws should vary"
    # No longer pinned to the deterministic expected bond return.
    assert not all(abs(d - cfg.EXPECTED_BOND_RETURN) < 1e-9 for d in draws)


def test_correlated_bond_negative_correlation_on_crash():
    """With rho < 0, a large negative stock shock lifts the mean bond draw
    above its unconditional after-fee mean (flight to safety)."""
    assert cfg.STOCK_BOND_CORRELATION < 0
    np.random.seed(1)
    stock_return = -0.35
    bond_mean_uncond = cfg.EXPECTED_BOND_RETURN - cfg.INVESTMENT_FEE_RATE
    draws = [generate_correlated_bond_for_stock(stock_return) for _ in range(2000)]
    assert np.mean(draws) > bond_mean_uncond


def test_sequence_tests_bonds_vary_and_run_solvent():
    """Every config SEQUENCE_TESTS crisis runs to completion, and repeated
    runs of a stochastic-bond sequence produce differing terminal balances."""
    for seq_name in cfg.SEQUENCE_TESTS:
        # Should not raise; returns (success_bool, portfolio).
        success, portfolio = run_detailed_simulation(
            retirement_age=50, historical_sequence=seq_name, random_seed=7
        )
        assert isinstance(success, bool)
        assert portfolio.get_total_balance() >= 0.0

    # Bonds now vary run-to-run: differing seeds -> differing terminal balances.
    balances = set()
    for seed in range(5):
        _, portfolio = run_detailed_simulation(
            retirement_age=50, historical_sequence='dot_com_crisis', random_seed=seed
        )
        balances.add(round(portfolio.get_total_balance(), 2))
    assert len(balances) > 1, "stochastic bonds should vary terminal balance across seeds"
