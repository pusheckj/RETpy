#!/usr/bin/env python3
"""
Test various reasonable adjustments to find earliest realistic retirement age.

This is a script-style exploration, not a pytest test suite. Run directly:
    python -m tests.test_scenarios
"""

import numpy as np
from retirement_sim import config as cfg
from retirement_sim.account_simulation import run_monte_carlo_detailed


def _run_scenario(name, changes, target_ages=range(42, 50)):
    """Run a scenario with given config changes and return threshold ages."""
    # Save originals
    originals = {}
    for k, v in changes.items():
        originals[k] = getattr(cfg, k)
        setattr(cfg, k, v)

    results = []
    for age in target_ages:
        result = run_monte_carlo_detailed(age, n_simulations=1000, random_seed=123)
        results.append((age, result['success_rate']))

    # Restore
    for k, v in originals.items():
        setattr(cfg, k, v)

    # Find 80% and 90% thresholds
    threshold_80 = None
    threshold_90 = None
    for age, rate in results:
        if threshold_80 is None and rate >= 0.80:
            threshold_80 = age
        if threshold_90 is None and rate >= 0.90:
            threshold_90 = age

    return name, results, threshold_80, threshold_90


def main():
    print("=" * 80)
    print("TESTING REASONABLE MODEL ADJUSTMENTS")
    print("=" * 80)

    # BASELINE
    print("\n" + "=" * 80)
    print("1. BASELINE")
    print("=" * 80)
    name, results, t80, t90 = _run_scenario("Baseline", {})
    print(f"\n{'Age':<6} {'Success':>10}")
    print("-" * 20)
    for age, rate in results:
        print(f"{age:<6} {rate:>9.1%}")
    print(f"\n  80% threshold: Age {t80}")
    print(f"  90% threshold: Age {t90}")

    # Plan to age 90
    print("\n" + "=" * 80)
    print("2. Plan to age 90 (instead of 95)")
    print("=" * 80)
    print("   Rationale: Life expectancy at 65 is ~85 years. Planning to 90 is still conservative.")
    name, results, t80, t90 = _run_scenario("Plan to 90", {"PLAN_UNTIL_AGE": 90})
    print(f"\n{'Age':<6} {'Success':>10}")
    print("-" * 20)
    for age, rate in results:
        print(f"{age:<6} {rate:>9.1%}")
    print(f"\n  80% threshold: Age {t80}")
    print(f"  90% threshold: Age {t90}")

    # Reduce LTC probability from 50% to 30%
    print("\n" + "=" * 80)
    print("3. Reduce LTC probability from 50% to 30%")
    print("=" * 80)
    print("   Rationale: 50% is the high end. 30-40% is more typical for healthy individuals.")
    name, results, t80, t90 = _run_scenario("LTC 30%", {"LTC_PROBABILITY": 0.30})
    print(f"\n{'Age':<6} {'Success':>10}")
    print("-" * 20)
    for age, rate in results:
        print(f"{age:<6} {rate:>9.1%}")
    print(f"\n  80% threshold: Age {t80}")
    print(f"  90% threshold: Age {t90}")

    # Disable LTC modeling entirely
    print("\n" + "=" * 80)
    print("4. Disable LTC modeling (assume LTC insurance or family care)")
    print("=" * 80)
    print("   Rationale: If you buy LTC insurance or plan for family care, this risk is mitigated.")
    name, results, t80, t90 = _run_scenario("No LTC", {"LTC_ENABLED": False})
    print(f"\n{'Age':<6} {'Success':>10}")
    print("-" * 20)
    for age, rate in results:
        print(f"{age:<6} {rate:>9.1%}")
    print(f"\n  80% threshold: Age {t80}")
    print(f"  90% threshold: Age {t90}")

    # Historical returns
    print("\n" + "=" * 80)
    print("5. Historical returns (8.7% stocks instead of 7%)")
    print("=" * 80)
    print("   Rationale: Long-term historical average is 8.7% real. 7% is already conservative.")
    name, results, t80, t90 = _run_scenario("Historical", {"EXPECTED_STOCK_RETURN": 0.087})
    print(f"\n{'Age':<6} {'Success':>10}")
    print("-" * 20)
    for age, rate in results:
        print(f"{age:<6} {rate:>9.1%}")
    print(f"\n  80% threshold: Age {t80}")
    print(f"  90% threshold: Age {t90}")

    # Combined reasonable adjustments
    print("\n" + "=" * 80)
    print("6. COMBINED: Plan to 90 + LTC 30% + Historical returns")
    print("=" * 80)
    print("   This represents a more optimistic but still reasonable scenario.")
    combined_changes = {
        "PLAN_UNTIL_AGE": 90,
        "LTC_PROBABILITY": 0.30,
        "EXPECTED_STOCK_RETURN": 0.087,
    }
    name, results, t80, t90 = _run_scenario("Combined", combined_changes, target_ages=range(40, 48))
    print(f"\n{'Age':<6} {'Success':>10}")
    print("-" * 20)
    for age, rate in results:
        print(f"{age:<6} {rate:>9.1%}")
    print(f"\n  80% threshold: Age {t80}")
    print(f"  90% threshold: Age {t90}")

    # Moderate optimism
    print("\n" + "=" * 80)
    print("7. Moderate: Plan to 90 + No LTC modeling")
    print("=" * 80)
    moderate_changes = {
        "PLAN_UNTIL_AGE": 90,
        "LTC_ENABLED": False,
    }
    name, results, t80, t90 = _run_scenario("Moderate", moderate_changes, target_ages=range(40, 48))
    print(f"\n{'Age':<6} {'Success':>10}")
    print("-" * 20)
    for age, rate in results:
        print(f"{age:<6} {rate:>9.1%}")
    print(f"\n  80% threshold: Age {t80}")
    print(f"  90% threshold: Age {t90}")

    # Summary table
    print("\n" + "=" * 80)
    print("SUMMARY: EARLIEST RETIREMENT AGES BY SCENARIO")
    print("=" * 80)

    scenarios_to_run = [
        ("Baseline", {}),
        ("Plan to 90", {"PLAN_UNTIL_AGE": 90}),
        ("LTC 30% probability", {"LTC_PROBABILITY": 0.30}),
        ("No LTC modeling", {"LTC_ENABLED": False}),
        ("Historical returns (8.7%)", {"EXPECTED_STOCK_RETURN": 0.087}),
        ("Plan 90 + LTC 30%", {"PLAN_UNTIL_AGE": 90, "LTC_PROBABILITY": 0.30}),
        ("Plan 90 + No LTC", {"PLAN_UNTIL_AGE": 90, "LTC_ENABLED": False}),
        ("Plan 90 + No LTC + 8.7% returns", {"PLAN_UNTIL_AGE": 90, "LTC_ENABLED": False, "EXPECTED_STOCK_RETURN": 0.087}),
    ]

    print(f"\n{'Scenario':<35} {'80% Success':>12} {'90% Success':>12}")
    print("-" * 62)

    for name, changes in scenarios_to_run:
        _, results, t80, t90 = _run_scenario(name, changes, target_ages=range(40, 52))
        t80_str = f"Age {t80}" if t80 else "N/A"
        t90_str = f"Age {t90}" if t90 else "N/A"
        print(f"{name:<35} {t80_str:>12} {t90_str:>12}")

    print("\n" + "=" * 80)
    print("CONCLUSION")
    print("=" * 80)
    print("""
With the conservative baseline, earlier retirement requires a later retirement age.

With reasonable optimistic adjustments (Plan to 90, no LTC modeling),
80-90% success can be achieved earlier.

The key drivers of the conservative result:
  1. Planning to age 95 (50-year retirement horizon)
  2. 50% LTC probability at age 85+
  3. 7% stock returns (vs 8.7% historical)

For a healthy individual with LTC insurance or family support,
earlier retirement with 80-90% success is reasonable.
""")


if __name__ == "__main__":
    main()
