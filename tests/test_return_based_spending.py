#!/usr/bin/env python3
"""
Test the impact of return-based spending adjustments on retirement success rates.

This is a script-style exploration, not a pytest test suite. Run directly:
    python -m tests.test_return_based_spending
"""

import numpy as np
from retirement_sim import config as cfg
from retirement_sim.account_simulation import run_monte_carlo_detailed


def main():
    print("=" * 80)
    print("RETURN-BASED SPENDING ADJUSTMENT TEST")
    print("=" * 80)

    print("""
This test compares retirement success rates WITH and WITHOUT the
return-based spending adjustment feature.

The feature adjusts discretionary spending based on annual market returns:
  - Excellent returns (>=15%): +20% discretionary spending
  - Good returns (>=8%):       +10% discretionary spending
  - Poor returns (<0%):        -10% discretionary spending
  - Bad returns (<-10%):       -20% discretionary spending

Only discretionary expenses (30% of total) are affected.
Fixed expenses (mortgage, healthcare, utilities) remain unchanged.
""")

    # Test parameters
    test_ages = [41, 42, 43, 44, 45]
    n_simulations = 1000

    # Store results
    results_without = {}
    results_with = {}

    # Test WITHOUT return-based spending
    print("\nRunning simulations WITHOUT return-based spending...")
    print("-" * 60)

    original_setting = cfg.RETURN_BASED_SPENDING_ENABLED
    try:
        cfg.RETURN_BASED_SPENDING_ENABLED = False

        for age in test_ages:
            np.random.seed(42)  # Same seed for fair comparison
            result = run_monte_carlo_detailed(age, n_simulations=n_simulations)
            results_without[age] = result['success_rate']
            print(f"  Age {age}: {result['success_rate']:.1%} success rate")

        # Test WITH return-based spending
        print("\nRunning simulations WITH return-based spending...")
        print("-" * 60)

        cfg.RETURN_BASED_SPENDING_ENABLED = True

        for age in test_ages:
            np.random.seed(42)  # Same seed for fair comparison
            result = run_monte_carlo_detailed(age, n_simulations=n_simulations)
            results_with[age] = result['success_rate']
            print(f"  Age {age}: {result['success_rate']:.1%} success rate")
    finally:
        cfg.RETURN_BASED_SPENDING_ENABLED = original_setting

    # Summary comparison
    print("\n" + "=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)

    print(f"\n{'Retirement Age':<18} {'Without Feature':>18} {'With Feature':>18} {'Improvement':>15}")
    print("-" * 70)

    for age in test_ages:
        without = results_without[age]
        with_feat = results_with[age]
        improvement = (with_feat - without) * 100
        sign = "+" if improvement >= 0 else ""
        print(f"Age {age:<14} {without:>17.1%} {with_feat:>17.1%} {sign}{improvement:>13.1f}%")

    # Find threshold ages
    print("\n" + "-" * 70)
    print("\nTHRESHOLD ANALYSIS:")

    def find_threshold(results, target):
        for age in sorted(results.keys()):
            if results[age] >= target:
                return age
        return None

    thresh_80_without = find_threshold(results_without, 0.80)
    thresh_80_with = find_threshold(results_with, 0.80)
    thresh_90_without = find_threshold(results_without, 0.90)
    thresh_90_with = find_threshold(results_with, 0.90)

    print(f"\n80% Success Rate Threshold:")
    print(f"  Without feature: Age {thresh_80_without}")
    print(f"  With feature:    Age {thresh_80_with}")
    if thresh_80_without and thresh_80_with:
        diff = thresh_80_without - thresh_80_with
        if diff > 0:
            print(f"  --> Retire {diff} year(s) EARLIER with feature!")
        elif diff < 0:
            print(f"  --> Retire {-diff} year(s) later with feature")
        else:
            print(f"  --> No change in retirement age")

    print(f"\n90% Success Rate Threshold:")
    print(f"  Without feature: Age {thresh_90_without}")
    print(f"  With feature:    Age {thresh_90_with}")
    if thresh_90_without and thresh_90_with:
        diff = thresh_90_without - thresh_90_with
        if diff > 0:
            print(f"  --> Retire {diff} year(s) EARLIER with feature!")
        elif diff < 0:
            print(f"  --> Retire {-diff} year(s) later with feature")
        else:
            print(f"  --> No change in retirement age")

    print("""
================================================================================
CONCLUSION
================================================================================
The return-based spending adjustment feature allows you to:
  - Increase travel/entertainment spending in good market years
  - Reduce discretionary spending in bad market years

This behavioral flexibility should improve retirement outcomes by preserving
portfolio value during market downturns when it matters most (sequence risk).
""")


if __name__ == "__main__":
    main()
