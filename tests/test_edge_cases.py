#!/usr/bin/env python3
"""
Expense Edge Case & Stress Testing
===================================
Test extreme scenarios and edge cases to ensure robust behavior.
"""

from retirement_sim import config as cfg


def test_extreme_ages():
    """Test expense calculations at extreme ages."""
    print("=" * 70)
    print("EDGE CASE TEST: Extreme Ages")
    print("=" * 70)

    extreme_ages = [
        (20, "Below current age (should work)"),
        (cfg.YOUR_AGE, "Current age (baseline)"),
        (90, "Planning horizon limit"),
        (95, "Beyond planning horizon"),
        (100, "Very old age"),
    ]

    print(f"\n{'Age':<5} {'Scenario':<35} {'Child Exp':>12} {'Status':>10}")
    print("-" * 70)

    for age, scenario in extreme_ages:
        child_exp = cfg.calculate_child_expenses(age)
        college_exp = cfg.calculate_college_expenses(age)
        healthcare = cfg.calculate_healthcare_cost(age, is_retired=True, inflation_factor=1.0)

        # All should be >= 0
        assert child_exp >= 0, f"Child expense negative at age {age}"
        assert college_exp['total'] >= 0, f"College expense negative at age {age}"
        assert healthcare >= 0, f"Healthcare negative at age {age}"

        print(f"{age:<5} {scenario:<35} ${child_exp:>9,.0f} {'OK':>10}")

    print(f"\nAll extreme age cases handled correctly")


def test_inflation_extremes():
    """Test with extreme inflation rates."""
    print("\n" + "=" * 70)
    print("STRESS TEST: Extreme Inflation Scenarios")
    print("=" * 70)

    base_expense = cfg.calculate_annual_expenses(50, inflation_factor=1.0)

    test_scenarios = [
        (0.5, "50% deflation (extreme recession)"),
        (0.9, "10% deflation"),
        (1.0, "No inflation (baseline)"),
        (2.0, "100% inflation (double prices)"),
        (5.0, "400% inflation (hyperinflation)"),
        (10.0, "900% inflation (extreme)"),
    ]

    print(f"\nBase expense (age 50, no inflation): ${base_expense:,.0f}")
    print(f"\n{'Inflation':>10} {'Scenario':<40} {'Expense':>15} {'Status':>10}")
    print("-" * 80)

    for inflation_factor, scenario in test_scenarios:
        expense = cfg.calculate_annual_expenses(50, inflation_factor=inflation_factor)

        # Verify expense makes mathematical sense
        expected = base_expense * inflation_factor
        assert abs(expense - expected) <= 1, (  # Allow 1 dollar rounding error
            f"Inflation {inflation_factor}: Expected ${expected:,.0f}, got ${expense:,.0f}"
        )

        assert expense >= 0, f"Expense negative with inflation {inflation_factor}"

        print(f"{inflation_factor:>10.1f}x {scenario:<40} ${expense:>12,.0f} {'OK':>10}")

    print(f"\nAll inflation extremes handled correctly")


def test_mortgage_edge_cases():
    """Test mortgage logic at boundary conditions."""
    print("\n" + "=" * 70)
    print("EDGE CASE TEST: Mortgage Boundary Conditions")
    print("=" * 70)

    mortgage_payoff_age = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING

    test_cases = [
        (mortgage_payoff_age - 2, True, "2 years before payoff"),
        (mortgage_payoff_age - 1, True, "1 year before payoff"),
        (mortgage_payoff_age, False, "Exact payoff age"),
        (mortgage_payoff_age + 1, False, "1 year after payoff"),
    ]

    print(f"\nMortgage payoff age: {mortgage_payoff_age}")
    print(f"\n{'Age':<5} {'Expected':>10} {'Actual':>10} {'Scenario':<30} {'Status':>10}")
    print("-" * 70)

    for age, expected, scenario in test_cases:
        actual = cfg.has_mortgage(age)
        match = actual == expected

        status = "OK" if match else "FAIL"
        print(f"{age:<5} {str(expected):>10} {str(actual):>10} {scenario:<30} {status:>10}")

        assert match, f"Age {age}: Expected {expected}, got {actual}"

    print(f"\nMortgage boundary conditions handled correctly")


def test_child_expense_transitions():
    """Test child expense logic at all transition points."""
    print("\n" + "=" * 70)
    print("EDGE CASE TEST: Child Expense Transitions")
    print("=" * 70)

    first_child_birth = cfg.YOUR_AGE + cfg.YEARS_UNTIL_FIRST_CHILD
    second_child_birth = first_child_birth + cfg.YEARS_BETWEEN_CHILDREN
    first_child_leaves = first_child_birth + cfg.CHILD_LEAVES_HOME_AGE
    second_child_leaves = second_child_birth + cfg.CHILD_LEAVES_HOME_AGE

    transitions = [
        (first_child_birth - 1, 0, "Day before first child born"),
        (first_child_birth, cfg.FIRST_CHILD_ANNUAL_COST, "First child born"),
        (second_child_birth - 1, cfg.FIRST_CHILD_ANNUAL_COST, "Day before second born"),
        (second_child_birth, cfg.BOTH_CHILDREN_ANNUAL_COST, "Second child born"),
        (first_child_leaves - 1, cfg.BOTH_CHILDREN_ANNUAL_COST, "Day before first leaves"),
        (first_child_leaves, cfg.BOTH_CHILDREN_ANNUAL_COST - cfg.FIRST_CHILD_ANNUAL_COST, "First child leaves"),
        (second_child_leaves - 1, cfg.BOTH_CHILDREN_ANNUAL_COST - cfg.FIRST_CHILD_ANNUAL_COST, "Day before second leaves"),
        (second_child_leaves, 0, "Second child leaves"),
    ]

    print(f"\n{'Age':<5} {'Expected':>12} {'Actual':>12} {'Scenario':<30} {'Status':>10}")
    print("-" * 75)

    for age, expected, scenario in transitions:
        actual = cfg.calculate_child_expenses(age)
        match = actual == expected

        status = "OK" if match else "FAIL"
        print(f"{age:<5} ${expected:>9,.0f} ${actual:>9,.0f} {scenario:<30} {status:>10}")

        assert match, f"Age {age} ({scenario}): Expected ${expected:,.0f}, got ${actual:,.0f}"

    print(f"\nAll child expense transitions handled correctly")


def test_healthcare_age_boundaries():
    """Test healthcare cost boundaries between age bands."""
    print("\n" + "=" * 70)
    print("EDGE CASE TEST: Healthcare Age Band Boundaries")
    print("=" * 70)

    boundaries = [
        (49, True, cfg.HEALTHCARE_COSTS_BY_AGE['early_retirement'], "Last year of early retirement rate"),
        (50, True, cfg.HEALTHCARE_COSTS_BY_AGE['early_retirement'], "First year of early retirement"),
        (64, True, cfg.HEALTHCARE_COSTS_BY_AGE['early_retirement'], "Last year before Medicare"),
        (65, True, cfg.HEALTHCARE_COSTS_BY_AGE['medicare_base'], "First year of Medicare"),
        (74, True, cfg.HEALTHCARE_COSTS_BY_AGE['medicare_base'], "Last year of Medicare base"),
        (75, True, cfg.HEALTHCARE_COSTS_BY_AGE['medicare_mid'], "First year of Medicare mid"),
        (84, True, cfg.HEALTHCARE_COSTS_BY_AGE['medicare_mid'], "Last year of Medicare mid"),
        (85, True, cfg.HEALTHCARE_COSTS_BY_AGE['medicare_late'], "First year of Medicare late"),
    ]

    print(f"\n{'Age':<5} {'Retired':<8} {'Expected':>12} {'Actual':>12} {'Scenario':<35} {'Status':>10}")
    print("-" * 90)

    for age, retired, expected, scenario in boundaries:
        actual = cfg.calculate_healthcare_cost(age, retired, inflation_factor=1.0)
        match = actual == expected

        status = "OK" if match else "FAIL"
        print(f"{age:<5} {str(retired):<8} ${expected:>9,.0f} ${actual:>9,.0f} {scenario:<35} {status:>10}")

        assert match, f"Age {age} (retired={retired}, {scenario}): Expected ${expected:,.0f}, got ${actual:,.0f}"

    print(f"\nAll healthcare age boundaries handled correctly")


def test_college_timing_precision():
    """Test college expense timing at exact ages."""
    print("\n" + "=" * 70)
    print("EDGE CASE TEST: College Timing Precision")
    print("=" * 70)

    first_child_birth = cfg.YOUR_AGE + cfg.YEARS_UNTIL_FIRST_CHILD
    second_child_birth = first_child_birth + cfg.YEARS_BETWEEN_CHILDREN

    college_cost = cfg.COLLEGE_ANNUAL_COST * cfg.COLLEGE_FUNDING_PCT

    transitions = [
        (first_child_birth + 17, 0, 0, "First child age 17 (before college)"),
        (first_child_birth + 18, college_cost, 0, "First child starts college"),
        (first_child_birth + 21, college_cost, 0, "First child last year"),
        (first_child_birth + 22, 0, 0, "First child graduates"),
        (second_child_birth + 18, 0, college_cost, "Second child starts"),
        (second_child_birth + 21, 0, college_cost, "Second child last year"),
        (second_child_birth + 22, 0, 0, "Second child graduates"),
    ]

    print(f"\n{'Age':<5} {'Child1':>10} {'Child2':>10} {'Scenario':<35} {'Status':>10}")
    print("-" * 75)

    for age, expected1, expected2, scenario in transitions:
        result = cfg.calculate_college_expenses(age)
        match = (result['child1'] == expected1 and result['child2'] == expected2)

        status = "OK" if match else "FAIL"
        print(f"{age:<5} ${result['child1']:>7,.0f} ${result['child2']:>7,.0f} {scenario:<35} {status:>10}")

        assert match, (f"Age {age} ({scenario}): Expected child1=${expected1:.0f}, child2=${expected2:.0f}, "
                        f"got child1=${result['child1']:.0f}, child2=${result['child2']:.0f}")

    print(f"\nCollege timing handled correctly")


def run_all_edge_case_tests():
    """Run all edge case and stress tests."""
    print("\n" + "=" * 70)
    print("EDGE CASE & STRESS TEST SUITE")
    print("=" * 70)
    print("\nTesting boundary conditions and extreme scenarios...")

    tests = [
        ("Extreme Ages", test_extreme_ages),
        ("Inflation Extremes", test_inflation_extremes),
        ("Mortgage Boundaries", test_mortgage_edge_cases),
        ("Child Transitions", test_child_expense_transitions),
        ("Healthcare Boundaries", test_healthcare_age_boundaries),
        ("College Timing", test_college_timing_precision),
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            test_func()
            results[test_name] = True
        except Exception as e:
            print(f"\nTEST FAILED: {test_name}")
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = False

    # Summary
    print("\n" + "=" * 70)
    print("EDGE CASE TEST SUMMARY")
    print("=" * 70)

    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test_name:<30} {status}")

    all_passed = all(results.values())

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL EDGE CASE TESTS PASSED")
        print("Expense modeling is robust against boundary conditions!")
    else:
        print("SOME EDGE CASE TESTS FAILED")
        print("Review the errors above.")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    run_all_edge_case_tests()
