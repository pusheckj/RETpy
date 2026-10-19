"""
Tests for Monte Carlo statistical transparency (SE / 95% CI).

These verify the additive standard-error and confidence-interval keys on
run_monte_carlo_detailed and run_monte_carlo_with_scenario without changing
any existing outputs.
"""

import numpy as np
import pytest

from retirement_sim.account_simulation import (
    run_monte_carlo_detailed,
    run_monte_carlo_with_scenario,
)


def _expected_se(p, n):
    return np.sqrt(p * (1 - p) / n)


class TestMonteCarloStatistics:
    """SE/CI math and preservation of existing keys."""

    def test_detailed_se_and_ci_math(self):
        result = run_monte_carlo_detailed(retirement_age=50, n_simulations=200,
                                          random_seed=42)
        p = result['success_rate']
        se = result['success_rate_se']

        assert se == pytest.approx(_expected_se(p, 200))
        lo, hi = result['success_rate_ci95']
        assert lo == pytest.approx(p - 1.96 * se)
        assert hi == pytest.approx(p + 1.96 * se)

    def test_scenario_se_and_ci_math(self):
        result = run_monte_carlo_with_scenario(retirement_age=50,
                                               scenario='conservative',
                                               n_simulations=200,
                                               random_seed=42)
        p = result['success_rate']
        se = result['success_rate_se']

        assert se == pytest.approx(_expected_se(p, 200))
        lo, hi = result['success_rate_ci95']
        assert lo == pytest.approx(p - 1.96 * se)
        assert hi == pytest.approx(p + 1.96 * se)

    def test_detailed_existing_keys_present(self):
        result = run_monte_carlo_detailed(retirement_age=50, n_simulations=50,
                                          random_seed=1)
        for key in ('retirement_age', 'success_rate', 'median_final',
                    'percentile_10', 'percentile_90', 'median_taxes',
                    'median_roth_conversions', 'median_health_premiums',
                    'median_early_penalties', 'median_niit', 'median_ss_taxes',
                    'median_ltc_costs'):
            assert key in result

    def test_scenario_existing_keys_present(self):
        result = run_monte_carlo_with_scenario(retirement_age=50,
                                               scenario='conservative',
                                               n_simulations=50, random_seed=1)
        for key in ('retirement_age', 'scenario', 'scenario_name',
                    'success_rate', 'median_final', 'percentile_10',
                    'percentile_90', 'median_taxes', 'median_roth_conversions',
                    'median_health_premiums', 'median_early_penalties'):
            assert key in result

    def test_scenario_random_seed_reproducible(self):
        r1 = run_monte_carlo_with_scenario(retirement_age=50, n_simulations=100,
                                           random_seed=7)
        r2 = run_monte_carlo_with_scenario(retirement_age=50, n_simulations=100,
                                           random_seed=7)
        assert r1['success_rate'] == r2['success_rate']
