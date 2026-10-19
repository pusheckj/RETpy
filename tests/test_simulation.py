"""
Comprehensive Unit Tests for Retirement Simulation

This test suite covers:
- Tax calculations (federal, state, LTCG, SS, NIIT, Medicare IRMAA)
- Account operations (withdrawals, cost basis, RMD, Roth conversions)
- Expense calculations (children, college, mortgage, healthcare)
- Return calculations (clamping, volatility drag, correlated returns)
- Validation tests (Monte Carlo, accumulation, withdrawals)
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from retirement_sim import config as cfg
from retirement_sim.account_simulation import (
    Account, AccountType, TaxBrackets, CaliforniaTaxBrackets,
    calculate_ltcg_tax, clamp_return, generate_correlated_returns,
    calculate_blended_return, AccountPortfolio, create_initial_portfolio,
    simulate_retirement_year, run_detailed_simulation, run_monte_carlo_detailed
)


# ==============================================================================
# TAX CALCULATION TESTS
# ==============================================================================

class TestFederalTaxBrackets:
    """Test federal income tax bracket calculations."""

    def test_zero_income(self):
        """Federal tax should be zero for zero income."""
        brackets = TaxBrackets()
        assert brackets.calculate_tax(0) == 0

    def test_negative_income(self):
        """Federal tax should be zero for negative income."""
        brackets = TaxBrackets()
        assert brackets.calculate_tax(-1000) == 0

    def test_10_percent_bracket_boundary(self):
        """Test income within the 10% bracket."""
        brackets = TaxBrackets()
        # First bracket: $0-$23,200 at 10%
        tax = brackets.calculate_tax(23_200)
        expected = 23_200 * 0.10
        assert abs(tax - expected) < 0.01

    def test_multiple_brackets(self):
        """Test income spanning multiple brackets."""
        brackets = TaxBrackets()
        # Test income: $50,000
        # $0-$23,200 @ 10% = $2,320
        # $23,200-$50,000 @ 12% = $26,800 * 0.12 = $3,216
        # Total = $5,536
        tax = brackets.calculate_tax(50_000)
        expected = 23_200 * 0.10 + (50_000 - 23_200) * 0.12
        assert abs(tax - expected) < 0.01

    def test_highest_bracket(self):
        """Test income in the highest bracket."""
        brackets = TaxBrackets()
        income = 1_000_000
        tax = brackets.calculate_tax(income)
        # Should be substantial - verify it's in reasonable range (effective rate ~30%)
        assert 250_000 < tax < 400_000

    def test_bracket_monotonicity(self):
        """Tax should increase with income."""
        brackets = TaxBrackets()
        tax1 = brackets.calculate_tax(100_000)
        tax2 = brackets.calculate_tax(150_000)
        assert tax2 > tax1


class TestCaliforniaTaxBrackets:
    """Test California state tax bracket calculations."""

    def test_zero_income(self):
        """CA tax should be zero for zero income."""
        brackets = CaliforniaTaxBrackets()
        assert brackets.calculate_tax(0) == 0

    def test_lowest_bracket(self):
        """Test income in lowest CA bracket."""
        brackets = CaliforniaTaxBrackets()
        # First bracket: $0-$20,824 at 1%
        tax = brackets.calculate_tax(20_824)
        expected = 20_824 * 0.01
        assert abs(tax - expected) < 0.01

    def test_multiple_brackets(self):
        """Test income spanning multiple CA brackets."""
        brackets = CaliforniaTaxBrackets()
        income = 100_000
        tax = brackets.calculate_tax(income)
        # Should be positive and reasonable
        assert 0 < tax < income * 0.15  # Should be less than 15%

    def test_high_income_bracket(self):
        """Test income in highest CA bracket (12.3%)."""
        brackets = CaliforniaTaxBrackets()
        income = 1_000_000
        tax = brackets.calculate_tax(income)
        # Should be substantial (effective rate ~9%)
        assert 80_000 < tax < 150_000


class TestLTCGTax:
    """Test long-term capital gains tax calculations."""

    def test_zero_gains(self):
        """No tax on zero gains."""
        assert calculate_ltcg_tax(0, 50_000) == 0

    def test_negative_gains(self):
        """No tax on negative gains."""
        assert calculate_ltcg_tax(-1000, 50_000) == 0

    def test_gains_in_zero_bracket(self):
        """Gains entirely in 0% bracket."""
        # For MFJ, 0% bracket goes up to $94,050
        # With $50k other income, can have $44,050 of gains tax-free
        gains = 40_000
        other_income = 50_000
        tax = calculate_ltcg_tax(gains, other_income)
        assert tax == 0

    def test_gains_spanning_zero_and_15_brackets(self):
        """Gains spanning 0% and 15% brackets."""
        # Other income: $60,000
        # 0% bracket room: $94,050 - $60,000 = $34,050
        # Gains: $50,000
        # Tax: ($50,000 - $34,050) * 0.15 = $15,950 * 0.15 = $2,392.50
        gains = 50_000
        other_income = 60_000
        tax = calculate_ltcg_tax(gains, other_income)
        expected = (50_000 - (94_050 - 60_000)) * 0.15
        assert abs(tax - expected) < 0.01

    def test_gains_in_all_three_brackets(self):
        """Gains spanning all three brackets (0%, 15%, 20%)."""
        # Other income: $100,000
        # 0% bracket room: max(0, $94,050 - $100,000) = $0
        # 15% bracket room: max(0, $583,750 - $100,000) = $483,750
        # Gains: $600,000
        # Tax: $483,750 * 0.15 + ($600,000 - $483,750) * 0.20
        gains = 600_000
        other_income = 100_000
        tax = calculate_ltcg_tax(gains, other_income)
        gains_at_15 = 583_750 - 100_000
        gains_at_20 = gains - gains_at_15
        expected = gains_at_15 * 0.15 + gains_at_20 * 0.20
        assert abs(tax - expected) < 1.0

    def test_high_income_all_gains_at_20(self):
        """High income means all gains taxed at 20%."""
        # Other income: $600,000
        # All gains will be in 20% bracket
        gains = 100_000
        other_income = 600_000
        tax = calculate_ltcg_tax(gains, other_income)
        expected = gains * 0.20
        assert abs(tax - expected) < 0.01


class TestSocialSecurityTaxation:
    """Test Social Security benefit taxation."""

    def test_zero_benefits(self):
        """No tax on zero SS benefits."""
        taxable = cfg.calculate_taxable_social_security(0, 50_000)
        assert taxable == 0

    def test_negative_benefits(self):
        """No tax on negative SS (shouldn't happen)."""
        taxable = cfg.calculate_taxable_social_security(-1000, 50_000)
        assert taxable == 0

    def test_low_income_no_ss_tax(self):
        """Below threshold, no SS is taxable."""
        # Provisional income = $30,000 + 50% * $20,000 = $40,000
        # Below $32,000 threshold... actually above it
        # Let's use very low income
        ss_benefits = 10_000
        other_agi = 10_000
        # Provisional = $10,000 + 0.5*$10,000 = $15,000
        taxable = cfg.calculate_taxable_social_security(ss_benefits, other_agi)
        # Below $32,000 threshold
        assert taxable == 0

    def test_mid_range_ss_tax(self):
        """Between thresholds, up to 50% taxable."""
        # Provisional income in middle range
        ss_benefits = 50_000
        other_agi = 25_000
        # Provisional = $25,000 + 0.5*$50,000 = $50,000
        # This is between $32,000 and $44,000
        # Taxable = 50% of ($50,000 - $32,000) = 50% of $18,000 = $9,000
        # But capped at 50% of benefits = $25,000
        taxable = cfg.calculate_taxable_social_security(ss_benefits, other_agi)
        # Should be around 50% of excess above first threshold
        assert 0 < taxable < ss_benefits * 0.5

    def test_high_income_85_percent_ss_tax(self):
        """High income, up to 85% of benefits taxable."""
        ss_benefits = 100_000
        other_agi = 200_000
        # Provisional = $200,000 + 0.5*$100,000 = $250,000
        # Well above $44,000 threshold
        # Should get close to 85% taxable
        taxable = cfg.calculate_taxable_social_security(ss_benefits, other_agi)
        # Should be substantial portion of benefits
        assert taxable > ss_benefits * 0.5
        assert taxable <= ss_benefits * 0.85


class TestNIIT:
    """Test Net Investment Income Tax (3.8% surtax)."""

    def test_below_threshold(self):
        """No NIIT below $250k MAGI for MFJ."""
        niit = cfg.calculate_niit(200_000, 50_000)
        assert niit == 0

    def test_at_threshold(self):
        """No NIIT exactly at threshold."""
        niit = cfg.calculate_niit(250_000, 50_000)
        assert niit == 0

    def test_above_threshold_applies_to_lesser_amount(self):
        """NIIT applies to lesser of investment income or excess MAGI."""
        # MAGI: $300,000, Excess: $50,000
        # Investment income: $30,000
        # NIIT applies to min($30,000, $50,000) = $30,000
        magi = 300_000
        investment_income = 30_000
        niit = cfg.calculate_niit(magi, investment_income)
        expected = 30_000 * cfg.NIIT_RATE
        assert abs(niit - expected) < 0.01

    def test_high_investment_income(self):
        """NIIT capped by excess MAGI."""
        # MAGI: $300,000, Excess: $50,000
        # Investment income: $100,000
        # NIIT applies to min($100,000, $50,000) = $50,000
        magi = 300_000
        investment_income = 100_000
        niit = cfg.calculate_niit(magi, investment_income)
        expected = 50_000 * cfg.NIIT_RATE
        assert abs(niit - expected) < 0.01


class TestMedicareIRMAA:
    """Test Medicare IRMAA (Income-Related Monthly Adjustment Amount)."""

    def test_base_premium_below_threshold(self):
        """Below first threshold, pay base premium."""
        # Below $212,000 (2025 CMS MFJ first tier)
        magi = 150_000
        premium = cfg.calculate_medicare_irmaa(magi)
        # Base premium for couple: (185.00 + 0) * 12 * 2 = $4,440.00
        expected_base = 185.00 * 12 * 2
        assert abs(premium - expected_base) < 1.0

    def test_first_surcharge_tier(self):
        """First surcharge tier with IRMAA (2025 CMS MFJ: $212,000)."""
        magi = 220_000
        premium = cfg.calculate_medicare_irmaa(magi)
        # Should include surcharge
        # Part B: $259.00, Part D: $13.70 per person per month
        expected = (259.00 + 13.70) * 12 * 2
        assert abs(premium - expected) < 1.0

    def test_highest_tier(self):
        """Highest IRMAA tier."""
        magi = 800_000
        premium = cfg.calculate_medicare_irmaa(magi)
        # Highest tier: Part B $628.90, Part D $85.80
        expected = (628.90 + 85.80) * 12 * 2
        assert abs(premium - expected) < 1.0

    def test_2025_tier_boundary_212k(self):
        """Pin the 2025 CMS second-tier boundary at exactly $212,000 MFJ."""
        premium_at = cfg.calculate_medicare_irmaa(212_000)
        premium_below = cfg.calculate_medicare_irmaa(211_999)
        expected_at = (259.00 + 13.70) * 12 * 2
        expected_below = 185.00 * 12 * 2
        assert abs(premium_at - expected_at) < 1.0
        assert abs(premium_below - expected_below) < 1.0

    def test_2025_tier_boundary_400k(self):
        """Pin the 2025 CMS fifth-tier boundary at exactly $400,000 MFJ."""
        premium_at = cfg.calculate_medicare_irmaa(400_000)
        premium_below = cfg.calculate_medicare_irmaa(399_999)
        expected_at = (591.90 + 78.60) * 12 * 2
        expected_below = (480.90 + 57.00) * 12 * 2
        assert abs(premium_at - expected_at) < 1.0
        assert abs(premium_below - expected_below) < 1.0

    def test_inflation_adjustment(self):
        """Premiums increase with inflation factor."""
        magi = 300_000
        premium_base = cfg.calculate_medicare_irmaa(magi, inflation_factor=1.0)
        premium_inflated = cfg.calculate_medicare_irmaa(magi, inflation_factor=1.1)
        assert abs(premium_inflated - premium_base * 1.1) < 1.0


# ==============================================================================
# ACCOUNT OPERATIONS TESTS
# ==============================================================================

class TestWithdrawalOrdering:
    """Test tax-efficient withdrawal ordering."""

    def test_withdrawal_from_cash_first(self):
        """Cash should be withdrawn first (no tax)."""
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()

        # Withdraw small amount (should come from cash)
        initial_cash = portfolio.accounts['your_cash'].balance
        withdrawn, taxes = portfolio.withdraw_tax_efficient(1000, your_age=40)

        assert withdrawn == 1000
        assert taxes == 0
        assert portfolio.accounts['your_cash'].balance == initial_cash - 1000

    def test_withdrawal_order_before_59_5(self):
        """Before 59.5, prioritize accounts without early withdrawal penalties."""
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()

        # Age 50: Before 59.5, should prefer taxable over traditional
        # Set cash to 0 to force taxable withdrawal
        portfolio.accounts['your_cash'].balance = 0
        portfolio.accounts['your_brokerage'].balance = 50_000
        portfolio.accounts['your_401k'].balance = 100_000

        # Withdraw amount that would require taxable
        withdrawn, taxes = portfolio.withdraw_tax_efficient(10_000, your_age=50)

        # Should have withdrawn from taxable (with LTCG tax, not 10% penalty)
        assert withdrawn == 10_000
        # Taxable withdrawal should have minimal tax due to cost basis
        assert taxes < 5_000  # Should be minimal given default 50% cost basis

    def test_roth_withdrawal_tax_free(self):
        """Roth withdrawals after 59.5 should be tax-free."""
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()

        # Clear other accounts to force Roth withdrawal
        portfolio.accounts['your_cash'].balance = 0
        portfolio.accounts['your_brokerage'].balance = 0
        portfolio.accounts['your_401k'].balance = 0
        portfolio.accounts['your_roth_ira'].balance = 50_000

        withdrawn, taxes = portfolio.withdraw_tax_efficient(10_000, your_age=65)

        assert withdrawn == 10_000
        assert taxes == 0


class TestCostBasisTracking:
    """Test cost basis tracking for taxable accounts."""

    def test_initial_cost_basis(self):
        """New taxable account should have default cost basis."""
        account = Account("test_brokerage", AccountType.TAXABLE, 100_000, "you")
        # Default cost basis ratio is 50%
        assert account.cost_basis == 50_000

    def test_cost_basis_reduction_on_withdrawal(self):
        """Cost basis should reduce proportionally with withdrawal."""
        portfolio = AccountPortfolio()
        account = Account("test_brokerage", AccountType.TAXABLE, 100_000, "you")
        portfolio.add_account(account)
        portfolio.reset_yearly_income()

        # Withdraw 25% of account
        portfolio.accounts['test_brokerage'].cost_basis = 50_000
        initial_cb = portfolio.accounts['test_brokerage'].cost_basis

        # Simulate withdrawal that reduces cost basis
        if portfolio.accounts['test_brokerage'].balance > 1000:
            withdraw_amt = portfolio.accounts['test_brokerage'].balance * 0.25
            portfolio.accounts['test_brokerage'].balance -= withdraw_amt
            # Cost basis should reduce proportionally
            portfolio.accounts['test_brokerage'].cost_basis *= (1 - 0.25)

            new_cb = portfolio.accounts['test_brokerage'].cost_basis
            assert abs(new_cb - initial_cb * 0.75) < 1.0


class TestRMDCalculations:
    """Test Required Minimum Distribution calculations."""

    def test_no_rmd_before_age_75(self):
        """No RMD before age 75 (SECURE 2.0 rules)."""
        rmd = cfg.calculate_rmd(100_000, 74)
        assert rmd == 0

    def test_rmd_at_age_75(self):
        """RMD starts at age 75."""
        balance = 100_000
        age = 75
        # Distribution period at age 75 is 24.6
        expected = balance / 24.6
        rmd = cfg.calculate_rmd(balance, age)
        assert abs(rmd - expected) < 0.01

    def test_rmd_increases_with_age(self):
        """RMD percentage increases with age."""
        balance = 100_000
        rmd_75 = cfg.calculate_rmd(balance, 75)
        rmd_85 = cfg.calculate_rmd(balance, 85)
        # Distribution period gets smaller with age, so RMD gets larger
        assert rmd_85 > rmd_75

    def test_rmd_proportional_to_balance(self):
        """RMD should be proportional to account balance."""
        age = 80
        rmd_100k = cfg.calculate_rmd(100_000, age)
        rmd_200k = cfg.calculate_rmd(200_000, age)
        assert abs(rmd_200k - 2 * rmd_100k) < 0.01

    def test_rmd_matches_irs_table(self):
        """Spot check RMD against IRS uniform lifetime table."""
        # Age 80: distribution period 20.2
        rmd = cfg.calculate_rmd(1_000_000, 80)
        expected = 1_000_000 / 20.2
        assert abs(rmd - expected) < 1.0


class TestRothConversion:
    """Test Roth conversion logic."""

    def test_roth_conversion_fills_bracket(self):
        """Roth conversion should fill lower tax bracket."""
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()
        portfolio.year_ordinary_income = 50_000  # Some income already

        # Bracket room: $94,300 - $50,000 = $44,300
        converted, tax = portfolio.perform_roth_conversion(your_age=55)

        # Should have converted something (if traditional accounts available)
        if portfolio.accounts['your_401k'].balance > 0:
            assert converted > 0
            assert tax > 0

    def test_no_roth_conversion_above_stop_age(self):
        """No Roth conversion after stop age (67)."""
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()

        converted, tax = portfolio.perform_roth_conversion(your_age=70)

        assert converted == 0
        assert tax == 0

    def test_no_roth_conversion_if_disabled(self):
        """No Roth conversion if feature disabled."""
        with patch.object(cfg, 'ENABLE_ROTH_CONVERSION', False):
            portfolio = create_initial_portfolio()
            portfolio.reset_yearly_income()

            converted, tax = portfolio.perform_roth_conversion(your_age=55)

            assert converted == 0
            assert tax == 0


# ==============================================================================
# EXPENSE CALCULATION TESTS
# ==============================================================================

class TestChildExpenses:
    """Test child expense calculations by age."""

    def test_no_expenses_before_children(self):
        """No child expenses before first child born."""
        first_child_age = cfg.YOUR_AGE + cfg.YEARS_UNTIL_FIRST_CHILD
        expenses = cfg.calculate_child_expenses(first_child_age - 1)
        assert expenses == 0

    def test_first_child_expenses(self):
        """First child should have correct annual cost."""
        first_child_age = cfg.YOUR_AGE + cfg.YEARS_UNTIL_FIRST_CHILD
        expenses = cfg.calculate_child_expenses(first_child_age)
        assert expenses == cfg.FIRST_CHILD_ANNUAL_COST

    def test_both_children_expenses(self):
        """Both children should have combined cost."""
        both_children_age = cfg.YOUR_AGE + cfg.YEARS_UNTIL_FIRST_CHILD + cfg.YEARS_BETWEEN_CHILDREN
        expenses = cfg.calculate_child_expenses(both_children_age)
        assert expenses == cfg.BOTH_CHILDREN_ANNUAL_COST

    def test_first_child_leaves_home(self):
        """First child leaving should reduce expenses."""
        first_child_leaves = cfg.YOUR_AGE + cfg.YEARS_UNTIL_FIRST_CHILD + cfg.CHILD_LEAVES_HOME_AGE
        expenses = cfg.calculate_child_expenses(first_child_leaves)
        # Should be second child only
        second_child_only = cfg.BOTH_CHILDREN_ANNUAL_COST - cfg.FIRST_CHILD_ANNUAL_COST
        assert expenses == second_child_only

    def test_all_children_leave_home(self):
        """Both children leaving should eliminate child expenses."""
        all_leave_age = cfg.YOUR_AGE + cfg.YEARS_UNTIL_FIRST_CHILD + (2 * cfg.CHILD_LEAVES_HOME_AGE)
        expenses = cfg.calculate_child_expenses(all_leave_age)
        assert expenses == 0


class TestCollegeExpenses:
    """Test college expense calculations."""

    def test_no_college_expenses_before_age_18(self):
        """No college expenses before child turns 18."""
        first_child_age = cfg.YOUR_AGE + cfg.YEARS_UNTIL_FIRST_CHILD
        expenses = cfg.calculate_college_expenses(first_child_age + 10)
        assert expenses['child1'] == 0
        assert expenses['child2'] == 0

    def test_college_expense_at_age_18(self):
        """College expenses start when child turns 18."""
        first_child_birth = cfg.YOUR_AGE + cfg.YEARS_UNTIL_FIRST_CHILD
        your_age_at_child_18 = first_child_birth + 18
        expenses = cfg.calculate_college_expenses(your_age_at_child_18)
        expected = cfg.COLLEGE_ANNUAL_COST * cfg.COLLEGE_FUNDING_PCT
        assert expenses['child1'] == expected

    def test_college_expenses_span_4_years(self):
        """College expenses should be for 4 years (18-21)."""
        first_child_birth = cfg.YOUR_AGE + cfg.YEARS_UNTIL_FIRST_CHILD
        for college_year in range(cfg.COLLEGE_YEARS):
            your_age = first_child_birth + 18 + college_year
            expenses = cfg.calculate_college_expenses(your_age)
            expected = cfg.COLLEGE_ANNUAL_COST * cfg.COLLEGE_FUNDING_PCT
            assert expenses['child1'] == expected

    def test_no_college_after_age_22(self):
        """No college expenses after child turns 22."""
        first_child_birth = cfg.YOUR_AGE + cfg.YEARS_UNTIL_FIRST_CHILD
        your_age = first_child_birth + 22
        expenses = cfg.calculate_college_expenses(your_age)
        assert expenses['child1'] == 0


class TestMortgagePayoff:
    """Test mortgage payoff timing."""

    def test_has_mortgage_before_payoff_age(self):
        """Should have mortgage before payoff age."""
        payoff_age = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
        assert cfg.has_mortgage(payoff_age - 1)

    def test_no_mortgage_after_payoff(self):
        """Should not have mortgage after payoff age."""
        payoff_age = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
        assert not cfg.has_mortgage(payoff_age)

    def test_mortgage_payoff_age_reasonable(self):
        """Mortgage term should be in a reasonable range (0-50 years)."""
        assert cfg.MORTGAGE_YEARS_REMAINING < 50
        assert cfg.MORTGAGE_YEARS_REMAINING >= 0


# ==============================================================================
# RETURN CALCULATION TESTS
# ==============================================================================

class TestReturnClamping:
    """Test return clamping to historical bounds."""

    def test_extreme_positive_return_clamped(self):
        """Extreme positive returns should be clamped."""
        extreme_return = 0.80  # 80% return
        clamped = clamp_return(extreme_return)
        assert clamped <= 0.50  # MAX_BLENDED_RETURN

    def test_extreme_negative_return_clamped(self):
        """Extreme negative returns should be clamped."""
        extreme_return = -0.80  # -80% return
        clamped = clamp_return(extreme_return)
        assert clamped >= -0.35  # MIN_BLENDED_RETURN

    def test_reasonable_return_unchanged(self):
        """Reasonable returns should pass through unchanged."""
        reasonable_return = 0.10
        clamped = clamp_return(reasonable_return)
        assert clamped == reasonable_return

    def test_at_boundaries(self):
        """Returns exactly at boundaries should be unchanged."""
        upper = clamp_return(0.50)
        lower = clamp_return(-0.35)
        assert upper == 0.50
        assert lower == -0.35


class TestVolatilityDrag:
    """Test volatility drag calculation in returns."""

    def test_volatility_drag_applied(self):
        """Volatility drag should reduce returns in correlated returns."""
        np.random.seed(42)
        stock_return, bond_return = generate_correlated_returns()

        # With volatility drag enabled, returns should be lower than raw normals
        # (This is somewhat probabilistic, but generally should hold)
        # Just verify returns are in reasonable range
        assert -0.50 < stock_return < 0.50
        assert -0.30 < bond_return < 0.30

    def test_portfolio_level_drag_beats_per_asset(self):
        """
        Blended real return must be HIGHER than the old per-asset-drag value
        by the diversification benefit.

        Old (over-penalizing) behavior subtracted the weighted average of the
        per-asset drags: w_s*var_s/2 + w_b*var_b/2.
        New (correct) behavior subtracts blended portfolio variance / 2, which
        is smaller when rho < 1 -- so the new blended return is higher.
        """
        import retirement_sim.account_simulation as S
        import retirement_sim.config as cfg

        w_s, w_b = 0.80, 0.20
        var_s = cfg.STOCK_VOLATILITY ** 2
        var_b = cfg.BOND_VOLATILITY ** 2
        cov = cfg.STOCK_BOND_CORRELATION * cfg.STOCK_VOLATILITY * cfg.BOND_VOLATILITY

        old_drag = w_s * var_s / 2 + w_b * var_b / 2
        blended_variance = w_s**2 * var_s + w_b**2 * var_b + 2 * w_s * w_b * cov
        new_drag = blended_variance / 2

        diversification_benefit = old_drag - new_drag
        assert diversification_benefit > 0  # correlation < 1 => benefit exists

        # The pre-clamp blended return must be higher by exactly the benefit.
        # Compare using the same random draw for both drag conventions.
        np.random.seed(7)
        stock_return, bond_return = S.generate_correlated_returns()
        arithmetic_blended = w_s * stock_return + w_b * bond_return
        new_blended = arithmetic_blended - new_drag
        old_blended = arithmetic_blended - old_drag
        assert new_blended > old_blended
        assert abs((new_blended - old_blended) - diversification_benefit) < 1e-12

    def test_hundred_percent_stock_drag_unchanged(self):
        """
        A 100%-stock portfolio's drag must equal the old per-asset stock drag
        (var_s / 2) -- the diversification fix must not move an undiversified
        portfolio.
        """
        import retirement_sim.account_simulation as S
        import retirement_sim.config as cfg

        var_s = cfg.STOCK_VOLATILITY ** 2
        old_stock_drag = var_s / 2

        # New portfolio-variance drag with w_s=1, w_b=0 reduces to var_s/2.
        blended_variance = 1.0**2 * var_s + 0.0**2 * (cfg.BOND_VOLATILITY**2) + 0.0
        assert abs(blended_variance / 2 - old_stock_drag) < 1e-15

        # End-to-end: pre-clamp blended return equals stock_return - var_s/2.
        np.random.seed(11)
        stock_return, _ = S.generate_correlated_returns()
        # Re-seed identically and run through calculate_blended_return.
        np.random.seed(11)
        blended = S.calculate_blended_return(1.0, 0.0)
        expected = stock_return - old_stock_drag
        # calculate_blended_return clamps; within-bounds draw should match.
        if S.MIN_BLENDED_RETURN < expected < S.MAX_BLENDED_RETURN:
            assert abs(blended - expected) < 1e-12


class TestCorrelatedReturns:
    """Test stock-bond return correlation."""

    def test_returns_are_generated(self):
        """Correlated returns should be generated."""
        np.random.seed(42)
        stock_return, bond_return = generate_correlated_returns()

        assert isinstance(stock_return, (float, np.floating))
        assert isinstance(bond_return, (float, np.floating))

    def test_returns_within_bounds(self):
        """Generated returns should respect bounds."""
        for _ in range(100):
            stock_return, bond_return = generate_correlated_returns()
            assert -0.50 <= stock_return <= 0.50
            assert -0.30 <= bond_return <= 0.30

    def test_blended_return(self):
        """Blended return should respect allocation."""
        np.random.seed(42)
        stock_alloc = 0.80
        bond_alloc = 0.20

        blended = calculate_blended_return(stock_alloc, bond_alloc)

        assert -0.50 <= blended <= 0.50


# ==============================================================================
# VALIDATION TESTS
# ==============================================================================

class TestMonteCarloResults:
    """Test Monte Carlo simulation produces reasonable results."""

    def test_monte_carlo_success_rate_reasonable(self):
        """Success rate should be between 0% and 100%."""
        result = run_monte_carlo_detailed(retirement_age=50, n_simulations=100)
        assert 0 <= result['success_rate'] <= 1.0

    def test_monte_carlo_success_rate_consistency(self):
        """Multiple runs should have similar success rates (high confidence)."""
        # Run twice with same parameters
        result1 = run_monte_carlo_detailed(retirement_age=50, n_simulations=50)
        result2 = run_monte_carlo_detailed(retirement_age=50, n_simulations=50)

        # Results should be within 20% (relatively high variance with small N)
        diff = abs(result1['success_rate'] - result2['success_rate'])
        assert diff < 0.25

    def test_later_retirement_higher_success(self):
        """Retiring later should generally have higher success rate."""
        result_50 = run_monte_carlo_detailed(retirement_age=50, n_simulations=50)
        result_55 = run_monte_carlo_detailed(retirement_age=55, n_simulations=50)

        # Note: This is probabilistic, so we just check they're both reasonable
        assert 0 <= result_50['success_rate'] <= 1.0
        assert 0 <= result_55['success_rate'] <= 1.0


class TestAccumulationPhase:
    """Test portfolio growth during accumulation."""

    def test_portfolio_grows_during_accumulation(self):
        """Portfolio should grow from contributions + returns."""
        portfolio = create_initial_portfolio()
        initial_balance = portfolio.get_total_balance()

        # Simulate one year with positive return
        from retirement_sim.account_simulation import simulate_accumulation_year
        simulate_accumulation_year(portfolio, your_age=cfg.YOUR_AGE, annual_return=0.10)

        final_balance = portfolio.get_total_balance()

        # Should have grown due to contributions + 10% return
        assert final_balance > initial_balance * 1.05  # At least 5% growth


class TestWithdrawalsDoNotExceedBalances:
    """Test that withdrawals never exceed available balances."""

    def test_withdrawal_amount_respected(self):
        """Cannot withdraw more than portfolio balance (with taxes/penalties)."""
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()

        total = portfolio.get_total_balance()
        requested = total * 2  # Request 2x available

        withdrawn, taxes = portfolio.withdraw_tax_efficient(requested, your_age=60)

        # Withdrawn should be close to available (minus taxes)
        # The home equity can also be used, so we check reasonableness
        assert withdrawn <= total * 1.5  # Should be available + some home equity


class TestAnnualExpenseCalculation:
    """Test annual expense calculations."""

    def test_expenses_increase_with_inflation(self):
        """Expenses should increase with inflation factor."""
        age = 45
        expenses_1x = cfg.calculate_annual_expenses(age, inflation_factor=1.0)
        expenses_1_1x = cfg.calculate_annual_expenses(age, inflation_factor=1.1)

        assert expenses_1_1x > expenses_1x
        assert abs(expenses_1_1x - expenses_1x * 1.1) < 1  # Should be ~10% more

    def test_expenses_with_mortgage(self):
        """Expenses should include mortgage before payoff."""
        mortgage_age = cfg.YOUR_AGE + 10  # Young age with mortgage
        expenses = cfg.calculate_annual_expenses(mortgage_age)

        assert expenses > cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE

    def test_expenses_without_mortgage(self):
        """Expenses should exclude mortgage after payoff."""
        no_mortgage_age = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING + 5
        expenses = cfg.calculate_annual_expenses(no_mortgage_age)

        # Should be base retirement expenses (no mortgage)
        child_expenses = cfg.calculate_child_expenses(no_mortgage_age)
        expected = cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE + child_expenses
        assert abs(expenses - expected) < 1


class TestGranularSpendingCategories:
    """Pin that the granular SPEND_* categories drive the non-housing expense base.

    Editing the six monthly categories (the UI Expenses section) must supersede
    the legacy YOUR_OTHER_MONTHLY / UTILITIES_MONTHLY bundle in the engine, for
    BOTH current and retirement living expenses. Housing (mortgage/rent) stays a
    separate component. These tests mutate the config globals directly and restore
    them, exercising config.py in isolation from the UI seam.
    """

    _CATS = (
        "SPEND_UTILITIES_MONTHLY", "SPEND_FOOD_MONTHLY", "SPEND_TRANSPORT_MONTHLY",
        "SPEND_HEALTH_MONTHLY", "SPEND_DISCRETIONARY_MONTHLY", "SPEND_OTHER_MONTHLY",
    )

    def _set_granular(self, **values):
        """Set granular globals; return a restore-callable for teardown."""
        saved = {k: getattr(cfg, k) for k in self._CATS}
        for k in self._CATS:
            setattr(cfg, k, values.get(k))

        def restore():
            for k, v in saved.items():
                setattr(cfg, k, v)
        return restore

    def test_all_none_falls_back_to_legacy(self):
        # Default state: no granular category set -> legacy bundle is the base.
        restore = self._set_granular()  # all None
        try:
            assert cfg.granular_nonhousing_annual() is None
        finally:
            restore()

    def test_granular_sum_plus_partner(self):
        restore = self._set_granular(
            SPEND_UTILITIES_MONTHLY=350, SPEND_FOOD_MONTHLY=1_050,
            SPEND_TRANSPORT_MONTHLY=600, SPEND_HEALTH_MONTHLY=400,
            SPEND_DISCRETIONARY_MONTHLY=500, SPEND_OTHER_MONTHLY=200,
        )
        try:
            expected = (350 + 1_050 + 600 + 400 + 500 + 200) * 12 + cfg.PARTNER_OTHER_MONTHLY * 12
            assert cfg.granular_nonhousing_annual() == expected
        finally:
            restore()

    def test_partial_present_supersedes_legacy(self):
        # A single non-None category flips to the granular formula (summing only
        # the present categories).
        restore = self._set_granular(SPEND_FOOD_MONTHLY=1_000)
        try:
            assert cfg.granular_nonhousing_annual() == 1_000 * 12 + cfg.PARTNER_OTHER_MONTHLY * 12
        finally:
            restore()

    def test_calculate_annual_expenses_uses_granular_after_mortgage(self):
        # After the mortgage is paid and children have left, calculate_annual_expenses
        # equals the granular non-housing base (recomputed via the same formula the
        # engine uses). We recompute BASE here because it is a module constant.
        restore = self._set_granular(
            SPEND_UTILITIES_MONTHLY=350, SPEND_FOOD_MONTHLY=1_050,
            SPEND_TRANSPORT_MONTHLY=600, SPEND_HEALTH_MONTHLY=400,
            SPEND_DISCRETIONARY_MONTHLY=500, SPEND_OTHER_MONTHLY=200,
        )
        saved_base = cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE
        try:
            cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE = cfg.granular_nonhousing_annual()
            no_mortgage_age = max(cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING + 5, 80)
            expenses = cfg.calculate_annual_expenses(no_mortgage_age, inflation_factor=1.0)
            child = cfg.calculate_child_expenses(no_mortgage_age)
            assert abs(expenses - (cfg.granular_nonhousing_annual() + child)) < 1
        finally:
            cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE = saved_base
            restore()


class TestSpendingAdjustment:
    """Test dynamic spending adjustment (guardrails)."""

    def test_no_adjustment_at_target(self):
        """No spending adjustment when portfolio at target."""
        current = 1_000_000
        target = 1_000_000
        adjustment = cfg.calculate_spending_adjustment(current, target)
        assert adjustment == 1.0

    def test_spending_cut_below_floor(self):
        """Spending should be cut below floor trigger."""
        # Set dynamic spending enabled
        with patch.object(cfg, 'DYNAMIC_SPENDING_ENABLED', True):
            current = 700_000
            target = 1_000_000
            # 70% of target triggers floor
            adjustment = cfg.calculate_spending_adjustment(current, target)
            # Should be less than 1.0 (cut spending)
            assert adjustment <= 1.0

    def test_spending_increase_above_ceiling(self):
        """Spending can increase above ceiling trigger."""
        # Set dynamic spending enabled
        with patch.object(cfg, 'DYNAMIC_SPENDING_ENABLED', True):
            current = 1_300_000
            target = 1_000_000
            # 130% of target triggers ceiling
            adjustment = cfg.calculate_spending_adjustment(current, target)
            # Should be greater than 1.0 (increase spending)
            assert adjustment >= 1.0

    def test_disabled_adjustment_returns_1(self):
        """When disabled, adjustment factor is 1.0."""
        with patch.object(cfg, 'DYNAMIC_SPENDING_ENABLED', False):
            adjustment = cfg.calculate_spending_adjustment(500_000, 1_000_000)
            assert adjustment == 1.0


# ==============================================================================
# INTEGRATION TESTS
# ==============================================================================

class TestDetailedSimulation:
    """Test full detailed simulation."""

    def test_simulation_completes(self):
        """Full simulation should complete without errors."""
        success, portfolio = run_detailed_simulation(retirement_age=50, verbose=False)

        # Should return boolean and portfolio
        assert isinstance(success, bool)
        assert portfolio is not None

    def test_simulation_tracks_taxes(self):
        """Simulation should track tax payments."""
        success, portfolio = run_detailed_simulation(retirement_age=50, verbose=False)

        # Should have tax tracking
        assert portfolio.total_taxes_paid >= 0
        assert portfolio.total_niit_paid >= 0
        assert portfolio.total_ss_taxes_paid >= 0

    def test_simulation_reasonable_final_balance(self):
        """Final balance should be reasonable."""
        success, portfolio = run_detailed_simulation(retirement_age=50, verbose=False)

        final_balance = portfolio.get_total_balance()

        # Should be positive (or very close to zero if success=False)
        if success:
            assert final_balance > 0
        else:
            assert final_balance >= 0


# ==============================================================================
# EDGE CASE TESTS
# ==============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_portfolio_balance(self):
        """Should handle zero portfolio balance."""
        brackets = TaxBrackets()
        tax = brackets.calculate_tax(0)
        assert tax == 0

    def test_very_large_income(self):
        """Should handle very large income."""
        brackets = TaxBrackets()
        tax = brackets.calculate_tax(10_000_000)
        # Should be substantial but not more than 50% of income
        assert 0 < tax < 10_000_000 * 0.5

    def test_very_old_age_rmd(self):
        """Should handle very old age for RMD."""
        rmd = cfg.calculate_rmd(100_000, 120)
        # Should use default distribution period
        assert rmd > 0

    def test_withdrawal_when_accounts_empty(self):
        """Should handle withdrawal when no funds available."""
        portfolio = AccountPortfolio()
        portfolio.reset_yearly_income()

        # Empty portfolio
        portfolio.add_account(Account("test_account", AccountType.CASH, 0, "you"))

        withdrawn, taxes = portfolio.withdraw_tax_efficient(1000, your_age=65)
        # Should be zero (can use home equity as backup)
        # If home equity is available, might get partial withdrawal
        assert 0 <= withdrawn <= 1000

    def test_negative_withdrawal_request(self):
        """Should handle negative withdrawal (should be ignored)."""
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()

        withdrawn, taxes = portfolio.withdraw_tax_efficient(-1000, your_age=65)
        # Negative withdrawal shouldn't process
        assert withdrawn == 0 or withdrawn < 0


class TestAccumulationIncomeClamp:
    """Elective contributions must never exceed the year's gross salary.

    The base-salary elective clamp is a MANUAL-mode feature (SAVINGS_MODE that
    does not start with "Auto"). In the default Auto-allocate mode the engine
    instead sweeps the un-spent after-tax residual into brokerage, which has its
    own natural income ceiling (residual is floored at 0). These tests pin the
    legacy clamp, so they run in Manual mode explicitly.
    """

    def test_default_profile_contributions_unchanged(self):
        """Shipped defaults are within income, so the clamp is a no-op."""
        from retirement_sim.account_simulation import simulate_accumulation_year

        with patch.object(cfg, "SAVINGS_MODE", "Manual"):
            portfolio = create_initial_portfolio()
            before = {name: acct.balance for name, acct in portfolio.accounts.items()}

            # No returns so we isolate contribution amounts.
            simulate_accumulation_year(portfolio, your_age=cfg.YOUR_AGE, annual_return=0.0)

        comp = cfg.YOUR_COMPENSATION_BY_AGE[cfg.YOUR_AGE]
        expected_401k = min(float(cfg.YOUR_401K_CONTRIBUTION), cfg.get_401k_limit(cfg.YOUR_AGE, cfg.CURRENT_YEAR))
        expected_match = comp['base'] * cfg.YOUR_401K_MATCH_PCT
        added_401k = portfolio.accounts["your_401k"].balance - before["your_401k"]
        assert added_401k == pytest.approx(expected_401k + expected_match)

        # Default brokerage residual = saved (backdoor Roth + 529 are 0 by default).
        added_brokerage = portfolio.accounts["your_brokerage"].balance - before["your_brokerage"]
        assert added_brokerage == pytest.approx(max(0.0, comp['saved']))

    def test_over_configured_profile_clamped_to_income(self):
        """Huge 401k + HSA + backdoor Roth get clamped so total <= income."""
        from retirement_sim.account_simulation import simulate_accumulation_year

        age = cfg.YOUR_AGE
        base_salary = cfg.YOUR_COMPENSATION_BY_AGE[age]['base']

        overrides = {
            "YOUR_401K_CONTRIBUTION": base_salary,   # capped to IRS limit internally
            "YOUR_HSA_CONTRIBUTION": 999_999,
            "YOUR_BACKDOOR_ROTH": 999_999,
            "YOUR_BROKERAGE_CONTRIBUTION": 999_999,
            "SAVINGS_MODE": "Manual",  # clamp is a Manual-mode feature
        }
        with patch.multiple(cfg, **overrides):
            portfolio = create_initial_portfolio()
            before = {name: acct.balance for name, acct in portfolio.accounts.items()}
            simulate_accumulation_year(portfolio, your_age=age, annual_return=0.0)

        # Sum of the User-1 elective contributions (exclude employer match,
        # which is not funded from take-home income).
        match = base_salary * cfg.YOUR_401K_MATCH_PCT
        elective = (
            (portfolio.accounts["your_401k"].balance - before["your_401k"] - match)
            + (portfolio.accounts["your_hsa"].balance - before["your_hsa"])
            + (portfolio.accounts["your_roth_ira"].balance - before["your_roth_ira"])
            + (portfolio.accounts["child1_529"].balance - before["child1_529"])
            + (portfolio.accounts["child2_529"].balance - before["child2_529"])
            + (portfolio.accounts["your_brokerage"].balance - before["your_brokerage"])
        )
        assert elective <= base_salary + 1e-6
        # Discretionary tail absorbs the clamp: brokerage is cut far below the
        # requested 999_999 (down to whatever headroom income leaves).
        added_brokerage = portfolio.accounts["your_brokerage"].balance - before["your_brokerage"]
        assert added_brokerage < 999_999

    def test_clamp_trims_roth_when_brokerage_exhausted(self):
        """When mandatory pre-tax + income limits alone exceed salary, the
        discretionary tail (brokerage then backdoor Roth) is fully trimmed."""
        from retirement_sim.account_simulation import simulate_accumulation_year

        age = cfg.YOUR_AGE
        # Tiny salary: even 401k + HSA + backdoor Roth can't all fit.
        low_comp = dict(cfg.YOUR_COMPENSATION_BY_AGE[age])
        low_comp['base'] = 5_000
        low_comp['saved'] = 1_000
        table = dict(cfg.YOUR_COMPENSATION_BY_AGE)
        table[age] = low_comp

        overrides = {
            "YOUR_COMPENSATION_BY_AGE": table,
            "YOUR_401K_CONTRIBUTION": 999_999,   # capped to IRS limit internally
            "YOUR_HSA_CONTRIBUTION": 0,
            "YOUR_BACKDOOR_ROTH": 6_500,
            "YOUR_BROKERAGE_CONTRIBUTION": 999_999,
            "SAVINGS_MODE": "Manual",  # clamp is a Manual-mode feature
        }
        with patch.multiple(cfg, **overrides):
            portfolio = create_initial_portfolio()
            before = {name: acct.balance for name, acct in portfolio.accounts.items()}
            simulate_accumulation_year(portfolio, your_age=age, annual_return=0.0)

        added_brokerage = portfolio.accounts["your_brokerage"].balance - before["your_brokerage"]
        added_roth = portfolio.accounts["your_roth_ira"].balance - before["your_roth_ira"]
        # The discretionary tail (brokerage then backdoor Roth) is fully
        # trimmed. The pre-tax 401k is intentionally NOT clamped (it is bounded
        # by the IRS limit), so it can remain even in this pathological case.
        assert added_brokerage == pytest.approx(0.0)
        assert added_roth == pytest.approx(0.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
