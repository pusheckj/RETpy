"""
Basic Usage Tour

Runs a series of illustrative queries using the default config.
Intended as a smoke test and an introduction to the main API.

Run:
    python -m examples.basic_usage
"""

import numpy as np

try:
    from retirement_sim.account_simulation import (
        run_monte_carlo_detailed, run_detailed_simulation
    )
    from retirement_sim import config as cfg
except ImportError:
    print("ERROR: run from project root, or `pip install -e .` first")
    raise


def _hr(char: str = "=", width: int = 70) -> str:
    return char * width


def _section(title: str) -> None:
    print()
    print(_hr("="))
    print(title)
    print(_hr("="))


def section_1_setup() -> None:
    _section("1. SETUP")
    np.random.seed(42)
    print("  retirement_sim imported successfully")
    print(f"  numpy seed set to 42 for reproducibility")
    print(f"  Active return scenario: {cfg.ACTIVE_RETURN_SCENARIO!r}")
    print(f"  Primary age: {cfg.YOUR_AGE}, Partner age: {cfg.PARTNER_AGE}")
    print(f"  Planning horizon: age {cfg.PLAN_UNTIL_AGE}")


def section_2_financial_summary() -> None:
    _section("2. FINANCIAL SUMMARY (from cfg constants)")
    print("  ASSETS:")
    print(f"    Retirement accounts: ${cfg.TOTAL_RETIREMENT_ACCOUNTS:>12,.0f}")
    print(f"    Taxable investments: ${cfg.TOTAL_TAXABLE:>12,.0f}")
    print(f"    Cash:                ${cfg.TOTAL_CASH:>12,.0f}")
    print(f"    Home equity:         ${cfg.HOME_EQUITY:>12,.0f}")
    print(f"    {'-' * 36}")
    print(f"    NET WORTH:           ${cfg.TOTAL_NET_WORTH:>12,.0f}")

    print("\n  ANNUAL SAVINGS (at current age):")
    try:
        your_savings = cfg.calculate_your_total_savings(cfg.YOUR_AGE)
        partner_savings = cfg.calculate_partner_total_savings(
            cfg.PARTNER_SALARY, 0,
            married=(cfg.normalize_filing_status() == "MFJ" and cfg.has_partner())
        )
        print(f"    Primary:  ${your_savings:>12,.0f}")
        print(f"    Partner:  ${partner_savings:>12,.0f}")
        print(f"    Combined: ${your_savings + partner_savings:>12,.0f}")
    except AttributeError as e:
        print(f"    (savings helpers unavailable: {e})")

    print("\n  CURRENT ANNUAL EXPENSES:")
    print(f"    Total:    ${cfg.CURRENT_ANNUAL_EXPENSES:>12,.0f}")
    try:
        expenses_now = cfg.calculate_annual_expenses(cfg.YOUR_AGE)
        expenses_retired = cfg.calculate_annual_expenses(65)
        print(f"    At age {cfg.YOUR_AGE}: ${expenses_now:>12,.0f}")
        print(f"    At age 65: ${expenses_retired:>12,.0f}")
    except AttributeError as e:
        print(f"    (expense helper unavailable: {e})")


def section_3_single_simulation() -> None:
    _section("3. SINGLE SIMULATION (retire at 50, verbose)")
    try:
        success, portfolio = run_detailed_simulation(
            retirement_age=50, verbose=True, random_seed=42
        )
    except TypeError as e:
        print(f"  API mismatch on run_detailed_simulation: {e}")
        return

    final = portfolio.get_total_balance()
    print(f"\n  Result: {'SUCCESS' if success else 'FAILED'}")
    print(f"  Final portfolio balance: ${final:,.0f}")
    print(f"  Total taxes paid:        ${portfolio.total_taxes_paid:,.0f}")


def section_4_quick_monte_carlo() -> None:
    _section("4. QUICK MONTE CARLO (retire at 55, N=500)")
    try:
        result = run_monte_carlo_detailed(
            retirement_age=55, n_simulations=500, random_seed=42
        )
    except TypeError as e:
        print(f"  API mismatch on run_monte_carlo_detailed: {e}")
        return

    print(f"  Success rate:         {result['success_rate']:.1%}")
    print(f"  Median final balance: ${result['median_final']:>14,.0f}")
    print(f"  10th percentile:      ${result['percentile_10']:>14,.0f}")
    print(f"  90th percentile:      ${result['percentile_90']:>14,.0f}")
    print(f"  Median lifetime tax:  ${result['median_taxes']:>14,.0f}")


def section_5_earliest_age() -> None:
    _section("5. EARLIEST RETIREMENT AGE (N=1000 per age)")
    target = cfg.TARGET_SUCCESS_RATE
    print(f"  Target success rate: {target:.0%}")
    print(f"  Scanning ages {cfg.EARLIEST_RETIREMENT_AGE} -> {cfg.LATEST_RETIREMENT_AGE}\n")
    print(f"    {'Age':<5} {'Success':>8} {'Median Final':>16}")
    print(f"    {'-' * 5} {'-' * 8} {'-' * 16}")

    earliest_hit = None
    # Step by 2 years to keep runtime reasonable for a demo script.
    for age in range(cfg.EARLIEST_RETIREMENT_AGE, cfg.LATEST_RETIREMENT_AGE + 1, 2):
        result = run_monte_carlo_detailed(
            retirement_age=age, n_simulations=1000, random_seed=42
        )
        rate = result['success_rate']
        marker = "  <-- target hit" if (earliest_hit is None and rate >= target) else ""
        print(f"    {age:<5} {rate:>7.1%}  ${result['median_final']:>14,.0f}{marker}")
        if earliest_hit is None and rate >= target:
            earliest_hit = age

    print()
    if earliest_hit is not None:
        print(f"  Earliest age hitting {target:.0%} success: {earliest_hit}")
    else:
        print(f"  No age in the scanned range hit {target:.0%} success.")


def section_6_return_scenarios() -> None:
    _section("6. COMPARE RETURN SCENARIOS (retire at 55, N=500)")
    # NOTE: Setting cfg.ACTIVE_RETURN_SCENARIO alone is not enough because the
    # simulator reads the scalar constants (EXPECTED_STOCK_RETURN, etc.)
    # directly in its inner loop. We overwrite those scalars per-scenario
    # using the values from cfg.RETURN_SCENARIOS, then restore them after.
    scenarios = ['conservative', 'historical', 'pessimistic']
    keys = (
        'EXPECTED_STOCK_RETURN', 'EXPECTED_BOND_RETURN',
        'STOCK_VOLATILITY', 'BOND_VOLATILITY', 'ACTIVE_RETURN_SCENARIO',
    )
    saved = {k: getattr(cfg, k) for k in keys}
    try:
        print(f"  {'Scenario':<14} {'Success':>8} {'Median Final':>16}")
        print(f"  {'-' * 14} {'-' * 8} {'-' * 16}")
        for scenario in scenarios:
            if scenario not in cfg.RETURN_SCENARIOS:
                print(f"  {scenario:<14} (not defined in cfg.RETURN_SCENARIOS)")
                continue
            params = cfg.RETURN_SCENARIOS[scenario]
            cfg.ACTIVE_RETURN_SCENARIO = scenario
            cfg.EXPECTED_STOCK_RETURN = params['stock_return']
            cfg.EXPECTED_BOND_RETURN = params['bond_return']
            cfg.STOCK_VOLATILITY = params['stock_volatility']
            cfg.BOND_VOLATILITY = params['bond_volatility']
            result = run_monte_carlo_detailed(
                retirement_age=55, n_simulations=500, random_seed=42
            )
            print(
                f"  {scenario:<14} {result['success_rate']:>7.1%} "
                f" ${result['median_final']:>14,.0f}"
            )
    finally:
        for k, v in saved.items():
            setattr(cfg, k, v)


def _toggle_run(label: str, retirement_age: int, n: int) -> dict:
    return run_monte_carlo_detailed(
        retirement_age=retirement_age, n_simulations=n, random_seed=42
    )


def section_7_toggle_features() -> None:
    _section("7. TOGGLE FEATURES (retire at 55, N=500)")
    n_sims = 500
    age = 55

    orig_ss = cfg.INCLUDE_SOCIAL_SECURITY
    orig_dyn = cfg.DYNAMIC_SPENDING_ENABLED

    rows = []
    try:
        cfg.INCLUDE_SOCIAL_SECURITY = True
        cfg.DYNAMIC_SPENDING_ENABLED = True
        r = _toggle_run("baseline", age, n_sims)
        rows.append(("SS on,  DynSpend on",  r['success_rate'], r['median_final']))

        cfg.INCLUDE_SOCIAL_SECURITY = False
        cfg.DYNAMIC_SPENDING_ENABLED = True
        r = _toggle_run("no SS", age, n_sims)
        rows.append(("SS off, DynSpend on",  r['success_rate'], r['median_final']))

        cfg.INCLUDE_SOCIAL_SECURITY = True
        cfg.DYNAMIC_SPENDING_ENABLED = False
        r = _toggle_run("no dyn", age, n_sims)
        rows.append(("SS on,  DynSpend off", r['success_rate'], r['median_final']))

        cfg.INCLUDE_SOCIAL_SECURITY = False
        cfg.DYNAMIC_SPENDING_ENABLED = False
        r = _toggle_run("neither", age, n_sims)
        rows.append(("SS off, DynSpend off", r['success_rate'], r['median_final']))
    finally:
        cfg.INCLUDE_SOCIAL_SECURITY = orig_ss
        cfg.DYNAMIC_SPENDING_ENABLED = orig_dyn

    print(f"  {'Config':<22} {'Success':>8} {'Median Final':>16}")
    print(f"  {'-' * 22} {'-' * 8} {'-' * 16}")
    for label, rate, median in rows:
        print(f"  {label:<22} {rate:>7.1%}  ${median:>14,.0f}")


def main() -> None:
    print(_hr("="))
    print("RETIREMENT SIMULATOR - BASIC USAGE TOUR")
    print(_hr("="))

    section_1_setup()
    section_2_financial_summary()
    section_3_single_simulation()
    section_4_quick_monte_carlo()
    section_5_earliest_age()
    section_6_return_scenarios()
    section_7_toggle_features()

    print()
    print(_hr("="))
    print("TOUR COMPLETE")
    print(_hr("="))


if __name__ == "__main__":
    main()
