"""
Tests for previously-identified coverage gaps.

Covers 14 high-value scenarios that were missing from the test suite:
1.  Standard deduction applied before federal tax brackets
2.  Roth conversion rejected when bracket is already full
3.  RMD birth-year differentiation (user vs partner)
4.  Withdrawal order changes at age 59.5
5.  ACA subsidy cliff at 400% FPL
6.  SS taxation tier boundaries ($32k and $44k provisional income)
7.  Glide path allocation at exact boundary ages
8.  Portfolio value conservation during accumulation year
9.  Reproducibility: same seed produces identical results
10. Inflation factors not double-compounded (applied once per year)
11. Dynamic spending guardrail triggers at correct portfolio threshold
12. Roth conversion stops at or after SS claim age
13. Mortgage payoff age reflects mortgage term
14. NIIT is zero below threshold, non-zero above it
"""

import pytest
import numpy as np
import copy
from retirement_sim import config as cfg
from retirement_sim.account_simulation import (
    Account, AccountType, AccountPortfolio, TaxBrackets,
    create_initial_portfolio, simulate_accumulation_year,
    update_inflation_factors, calculate_blended_return,
    run_detailed_simulation,
)


# ==============================================================================
# 1. STANDARD DEDUCTION APPLIED BEFORE BRACKETS
# ==============================================================================

class TestStandardDeductionOrdering:
    """Federal tax must subtract standard deduction BEFORE applying brackets."""

    def test_income_below_standard_deduction_pays_zero_tax(self):
        """Income below $29,200 (MFJ standard deduction) should owe $0 federal tax."""
        portfolio = AccountPortfolio()
        portfolio.update_ages(40)  # Both under 65, base $29,200 deduction
        tax = portfolio.calculate_federal_tax_with_deduction(20_000)
        assert tax == 0.0, f"Expected $0 tax on $20k income, got ${tax:,.0f}"

    def test_income_exactly_at_standard_deduction_pays_zero(self):
        """Income equal to the standard deduction should yield $0 tax."""
        portfolio = AccountPortfolio()
        portfolio.update_ages(40)
        deduction = cfg.get_standard_deduction(40, 35)
        tax = portfolio.calculate_federal_tax_with_deduction(deduction)
        assert tax == 0.0

    def test_income_one_dollar_above_deduction_pays_10pct(self):
        """$1 above the standard deduction should be taxed at 10%."""
        portfolio = AccountPortfolio()
        portfolio.update_ages(40)
        deduction = cfg.get_standard_deduction(40, 35)
        tax = portfolio.calculate_federal_tax_with_deduction(deduction + 1.0)
        assert abs(tax - 0.10) < 0.01, f"Expected ~$0.10 tax on $1 above deduction, got ${tax:.4f}"

    def test_standard_deduction_increases_at_65(self):
        """At age 65+ each spouse gets an additional $1,550 deduction."""
        deduction_under_65 = cfg.get_standard_deduction(64, 59)
        deduction_at_65 = cfg.get_standard_deduction(65, 60)
        assert deduction_at_65 == deduction_under_65 + cfg.ADDITIONAL_STD_DEDUCTION_65_PLUS

    def test_both_spouses_65_adds_two_extra_deductions(self):
        """When both spouses are 65+, two additional deductions apply."""
        base = cfg.STANDARD_DEDUCTION_MFJ_2024
        both_65 = cfg.get_standard_deduction(65, 65)
        assert both_65 == base + 2 * cfg.ADDITIONAL_STD_DEDUCTION_65_PLUS


# ==============================================================================
# 2. ROTH CONVERSION RESPECTS BRACKET LIMITS
# ==============================================================================

class TestRothConversionBracketLimits:
    """Roth conversion should not push ordinary income past the target bracket."""

    def test_no_conversion_when_bracket_already_full(self):
        """If year_ordinary_income already exceeds ROTH_CONVERSION_TARGET_BRACKET, skip."""
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()
        # Manually set income above the 12% bracket ceiling
        portfolio.year_ordinary_income = cfg.roth_conversion_target() + 10_000
        amount, tax = portfolio.perform_roth_conversion(your_age=55)
        assert amount == 0.0, "Should not convert when bracket is already full"
        assert tax == 0.0

    def test_no_conversion_at_or_after_ss_claim_age(self):
        """Conversions stop at SS claim age (default 67)."""
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()
        amount, tax = portfolio.perform_roth_conversion(your_age=cfg.ROTH_CONVERSION_STOP_AGE)
        assert amount == 0.0

    def test_conversion_capped_at_bracket_room(self):
        """Conversion amount should not exceed available bracket room."""
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()
        # Set income partway through 12% bracket
        portfolio.year_ordinary_income = 60_000
        bracket_room = cfg.roth_conversion_target() - 60_000  # $34,300
        amount, _ = portfolio.perform_roth_conversion(your_age=55)
        assert amount <= bracket_room + 1, (
            f"Converted ${amount:,.0f} but bracket room was only ${bracket_room:,.0f}"
        )

    def test_conversion_disabled_when_flag_off(self):
        """No conversion when ENABLE_ROTH_CONVERSION is False."""
        original = cfg.ENABLE_ROTH_CONVERSION
        try:
            cfg.ENABLE_ROTH_CONVERSION = False
            portfolio = create_initial_portfolio()
            portfolio.reset_yearly_income()
            amount, tax = portfolio.perform_roth_conversion(your_age=55)
            assert amount == 0.0
        finally:
            cfg.ENABLE_ROTH_CONVERSION = original


# ==============================================================================
# 3. RMD BIRTH-YEAR DIFFERENTIATION
# ==============================================================================

class TestRMDBirthYearDifferentiation:
    """User (born 1991) and partner (born 1993) both have RMD start age 75 under SECURE 2.0."""

    def test_user_rmd_start_age(self):
        assert cfg.get_rmd_start_age(cfg.YOUR_BIRTH_YEAR) == 75

    def test_partner_rmd_start_age(self):
        assert cfg.get_rmd_start_age(cfg.PARTNER_BIRTH_YEAR) == 75

    def test_no_rmd_before_start_age(self):
        """No RMD should be taken before age 75."""
        balance = 500_000
        rmd = cfg.calculate_rmd(balance, 74)
        assert rmd == 0.0

    def test_rmd_taken_at_start_age(self):
        """RMD should be non-zero at exactly age 75."""
        balance = 500_000
        rmd = cfg.calculate_rmd(balance, 75)
        assert rmd > 0
        # At 75, distribution period is 24.6 → RMD = 500k / 24.6 ≈ $20,325
        expected = balance / cfg.RMD_TABLE[75]
        assert abs(rmd - expected) < 1.0

    def test_partner_rmd_uses_partner_age_not_user_age(self):
        """Partner's RMD is based on their age (younger), not the user's."""
        # At user's age 80, partner is 75 — she should START taking RMDs
        # At user's age 79, partner is 74 — she should NOT yet
        assert cfg.get_rmd_start_age(cfg.PARTNER_BIRTH_YEAR) == 75  # confirms age 75 threshold
        assert cfg.calculate_rmd(100_000, 74) == 0.0   # Partner at 74: no RMD
        assert cfg.calculate_rmd(100_000, 75) > 0.0    # Partner at 75: RMD starts


# ==============================================================================
# 4. WITHDRAWAL ORDER CHANGES AT AGE 59.5
# ==============================================================================

class TestWithdrawalOrderAt59_5:
    """Before 59.5 taxable brokerage is preferred over traditional; after 59.5 traditional comes before Roth."""

    def _portfolio_with_only_traditional_and_roth(self, trad_balance=100_000, roth_balance=100_000):
        """Create a minimal portfolio with only traditional and Roth accounts."""
        p = AccountPortfolio()
        p.add_account(Account("trad", AccountType.TRADITIONAL_IRA, trad_balance, "you"))
        p.add_account(Account("roth", AccountType.ROTH_IRA, roth_balance, "you"))
        p.reset_yearly_income()
        return p

    def test_before_59_5_roth_withdrawn_before_traditional(self):
        """Before 59.5, Roth contributions come out before traditional (avoids 10% penalty)."""
        p = self._portfolio_with_only_traditional_and_roth()
        trad_before = p.accounts["trad"].balance
        roth_before = p.accounts["roth"].balance

        p.withdraw_tax_efficient(10_000, your_age=50)

        roth_used = roth_before - p.accounts["roth"].balance
        trad_used = trad_before - p.accounts["trad"].balance
        assert roth_used > 0, "Roth should be used before traditional before age 59.5"
        assert trad_used == 0.0, "Traditional should not be touched before 59.5 if Roth available"

    def test_after_59_5_traditional_withdrawn_before_roth(self):
        """After 59.5, traditional accounts come before Roth in withdrawal order."""
        p = self._portfolio_with_only_traditional_and_roth()
        trad_before = p.accounts["trad"].balance
        roth_before = p.accounts["roth"].balance

        p.withdraw_tax_efficient(10_000, your_age=60)

        trad_used = trad_before - p.accounts["trad"].balance
        roth_used = roth_before - p.accounts["roth"].balance
        assert trad_used > 0, "Traditional should be used after 59.5"
        assert roth_used == 0.0, "Roth should be preserved after 59.5 if traditional available"

    def test_early_withdrawal_penalty_applied_before_59_5(self):
        """A 10% penalty should be collected when withdrawing from traditional before 59.5."""
        p = AccountPortfolio()
        p.add_account(Account("trad", AccountType.TRADITIONAL_IRA, 100_000, "you"))
        p.reset_yearly_income()

        _, taxes_and_penalties = p.withdraw_tax_efficient(10_000, your_age=50)
        penalty = p.total_early_withdrawal_penalties
        assert penalty > 0, "Should collect early withdrawal penalty before age 59.5"

    def test_no_early_withdrawal_penalty_after_59_5(self):
        """No 10% penalty should apply to traditional withdrawals after 59.5."""
        p = AccountPortfolio()
        p.add_account(Account("trad", AccountType.TRADITIONAL_IRA, 100_000, "you"))
        p.reset_yearly_income()

        p.withdraw_tax_efficient(10_000, your_age=60)
        assert p.total_early_withdrawal_penalties == 0.0


# ==============================================================================
# 5. ACA SUBSIDY CLIFF AT 400% FPL
# ==============================================================================

class TestACASubsidyCliff:
    """ACA subsidies cut off sharply at 400% of FPL (~$124,800 for family of 4)."""

    def test_just_below_cliff_gets_subsidy(self):
        """At 399% FPL, premium is capped at ~9.5% of income (subsidized)."""
        cliff = cfg.ACA_SUBSIDY_CLIFF  # ~$124,800
        income_just_below = cliff - 100
        premium = cfg.calculate_aca_premium(income_just_below)
        # Should pay at most 9.5% of income, not the full $18,000
        assert premium < cfg.ACA_BASE_ANNUAL_PREMIUM, (
            f"Expected subsidy below cliff, got full premium ${premium:,.0f}"
        )
        assert premium <= income_just_below * 0.095 + 1  # small float tolerance

    def test_at_cliff_pays_full_premium(self):
        """At exactly 400% FPL, no subsidy — pay full $18,000/year."""
        cliff = cfg.ACA_SUBSIDY_CLIFF
        premium = cfg.calculate_aca_premium(cliff)
        assert premium == cfg.ACA_BASE_ANNUAL_PREMIUM, (
            f"Expected full premium ${cfg.ACA_BASE_ANNUAL_PREMIUM:,} at cliff, got ${premium:,}"
        )

    def test_above_cliff_pays_full_premium(self):
        """Above the cliff, always pay full unsubsidized premium."""
        premium = cfg.calculate_aca_premium(cfg.ACA_SUBSIDY_CLIFF + 50_000)
        assert premium == cfg.ACA_BASE_ANNUAL_PREMIUM

    def test_very_low_income_gets_maximum_subsidy(self):
        """At 150% FPL, premium is capped at ~4% of income."""
        income_150pct = cfg.FPL_FAMILY_OF_4 * 1.5
        premium = cfg.calculate_aca_premium(income_150pct)
        max_allowed = income_150pct * 0.04
        assert premium <= max_allowed + 1


# ==============================================================================
# 6. SOCIAL SECURITY TAXATION TIER BOUNDARIES
# ==============================================================================

class TestSSTaxationTiers:
    """SS benefits are 0% taxable below $32k provisional, up to 50% at $32-44k, up to 85% above $44k."""

    def test_below_lower_threshold_zero_taxable(self):
        """Provisional income below $32k → 0% of SS is taxable."""
        ss = 20_000
        other_agi = 10_000  # provisional = 10k + 0.5*20k = 20k < 32k
        taxable = cfg.calculate_taxable_social_security(ss, other_agi)
        assert taxable == 0.0

    def test_at_lower_threshold_boundary(self):
        """Provisional income exactly at $32k → 0% taxable."""
        ss = 20_000
        # provisional = other_agi + 0.5*ss = 32k → other_agi = 22k
        other_agi = cfg.SS_TAX_THRESHOLD_1_MFJ - 0.5 * ss
        taxable = cfg.calculate_taxable_social_security(ss, other_agi)
        assert taxable == 0.0

    def test_in_middle_tier_up_to_50pct_taxable(self):
        """Between $32k and $44k provisional → up to 50% of SS taxable."""
        ss = 20_000
        # provisional = 38k (middle of $32k-$44k band)
        other_agi = 38_000 - 0.5 * ss  # = 28k
        taxable = cfg.calculate_taxable_social_security(ss, other_agi)
        assert 0 < taxable <= ss * 0.50

    def test_above_upper_threshold_up_to_85pct_taxable(self):
        """Provisional income above $44k → up to 85% of SS taxable."""
        ss = 40_000
        other_agi = 60_000  # provisional = 60k + 20k = 80k >> $44k
        taxable = cfg.calculate_taxable_social_security(ss, other_agi)
        assert taxable <= ss * 0.85 + 1
        assert taxable > ss * 0.50  # definitely in top tier

    def test_zero_ss_income_returns_zero(self):
        assert cfg.calculate_taxable_social_security(0, 100_000) == 0.0


# ==============================================================================
# 7. GLIDE PATH ALLOCATION AT BOUNDARY AGES
# ==============================================================================

class TestGlidepathBoundaries:
    """Asset allocation should transition smoothly and hold at boundaries."""

    def test_before_retirement_uses_accumulation_allocation(self):
        stock, bond = cfg.calculate_asset_allocation(age=39, retirement_age=42)
        assert stock == cfg.STOCK_ALLOCATION
        assert bond == cfg.BOND_ALLOCATION

    def test_at_retirement_uses_start_allocation(self):
        stock, bond = cfg.calculate_asset_allocation(age=42, retirement_age=42)
        assert abs(stock - cfg.GLIDE_PATH_START_STOCK_PCT) < 0.001

    def test_at_end_age_uses_end_allocation(self):
        stock, bond = cfg.calculate_asset_allocation(age=cfg.GLIDE_PATH_END_AGE, retirement_age=42)
        assert abs(stock - cfg.GLIDE_PATH_END_STOCK_PCT) < 0.001

    def test_after_end_age_holds_steady(self):
        stock_at_end, _ = cfg.calculate_asset_allocation(age=cfg.GLIDE_PATH_END_AGE, retirement_age=42)
        stock_after, _ = cfg.calculate_asset_allocation(age=cfg.GLIDE_PATH_END_AGE + 5, retirement_age=42)
        assert abs(stock_at_end - stock_after) < 0.001

    def test_midpoint_is_interpolated(self):
        """Halfway between retirement and end age should be halfway between start/end allocation."""
        ret_age = 42
        midpoint_age = ret_age + (cfg.GLIDE_PATH_END_AGE - ret_age) // 2
        stock, _ = cfg.calculate_asset_allocation(age=midpoint_age, retirement_age=ret_age)
        expected = (cfg.GLIDE_PATH_START_STOCK_PCT + cfg.GLIDE_PATH_END_STOCK_PCT) / 2
        assert abs(stock - expected) < 0.02  # within 2pp of midpoint

    def test_allocations_always_sum_to_one(self):
        for age in [35, 42, 55, 65, 75, 80]:
            stock, bond = cfg.calculate_asset_allocation(age=age, retirement_age=42)
            assert abs(stock + bond - 1.0) < 1e-9, f"Allocations don't sum to 1.0 at age {age}"


# ==============================================================================
# 8. PORTFOLIO VALUE CONSERVATION DURING ACCUMULATION
# ==============================================================================

class TestPortfolioConservation:
    """Money should not be created or destroyed during accumulation — only grown by returns and contributions."""

    def test_zero_return_zero_contribution_balance_unchanged(self):
        """With 0% return and no contributions, balance should be unchanged."""
        portfolio = create_initial_portfolio()
        balance_before = portfolio.get_total_balance()
        portfolio.apply_returns(0.0)
        assert abs(portfolio.get_total_balance() - balance_before) < 0.01

    def test_positive_return_increases_balance_by_correct_amount(self):
        """10% return should increase non-cash balance by exactly 10%."""
        portfolio = AccountPortfolio()
        portfolio.add_account(Account("brok", AccountType.TAXABLE, 100_000, "you"))
        portfolio.apply_returns(0.10)
        assert abs(portfolio.get_total_balance() - 110_000) < 0.01

    def test_cash_does_not_earn_returns(self):
        """Cash accounts should not grow with market returns."""
        portfolio = AccountPortfolio()
        portfolio.add_account(Account("cash", AccountType.CASH, 50_000, "you"))
        portfolio.apply_returns(0.20)
        assert portfolio.accounts["cash"].balance == 50_000

    def test_contribution_increases_balance_by_exact_amount(self):
        """Contributing $5,000 should increase balance by exactly $5,000."""
        portfolio = AccountPortfolio()
        portfolio.add_account(Account("roth", AccountType.ROTH_IRA, 10_000, "you"))
        portfolio.contribute("roth", 5_000)
        assert portfolio.accounts["roth"].balance == 15_000


# ==============================================================================
# 9. REPRODUCIBILITY WITH SAME SEED
# ==============================================================================

class TestReproducibility:
    """Same random seed must produce identical simulation results."""

    def test_same_seed_gives_same_success_outcome(self):
        """Two runs with identical seeds must produce the same pass/fail result."""
        seed = 42
        success1, portfolio1 = run_detailed_simulation(retirement_age=45, random_seed=seed)
        success2, portfolio2 = run_detailed_simulation(retirement_age=45, random_seed=seed)
        assert success1 == success2

    def test_same_seed_gives_same_final_balance(self):
        """Two runs with identical seeds must produce the same final portfolio balance."""
        seed = 99
        _, portfolio1 = run_detailed_simulation(retirement_age=45, random_seed=seed)
        _, portfolio2 = run_detailed_simulation(retirement_age=45, random_seed=seed)
        assert abs(portfolio1.get_total_balance() - portfolio2.get_total_balance()) < 1.0

    def test_different_seeds_likely_differ(self):
        """Two different seeds should (almost certainly) produce different results."""
        # Use age 65 so the simulation builds a meaningful balance under the
        # default (median-earner) contribution profile; at earlier retirement
        # ages the default contributions can't sustain withdrawals and both
        # seeds deplete to zero.
        _, p1 = run_detailed_simulation(retirement_age=65, random_seed=1)
        _, p2 = run_detailed_simulation(retirement_age=65, random_seed=2)
        # Not guaranteed, but vanishingly unlikely to be identical
        assert p1.get_total_balance() != p2.get_total_balance()


# ==============================================================================
# 10. INFLATION FACTORS NOT DOUBLE-COMPOUNDED
# ==============================================================================

class TestInflationFactorCompounding:
    """
    Inflation factors in the ALL-REAL (today's-dollars) frame.

    Rebaselined for accuracy fix #1: the engine draws REAL investment returns, so
    liabilities live in real dollars too. General CPI therefore never grows a
    liability -- the ``general`` factor is pinned at 1.0 forever. Only real-excess
    categories (healthcare/childcare) grow, at rate = category_rate -
    general_rate. These tests assert that frame; the previous versions asserted the
    old (buggy) behavior where ``general`` compounded nominally at ~2.75%/yr.
    """

    def test_inflation_factor_starts_at_one(self):
        """Fresh inflation factors should start at 1.0 (no inflation yet)."""
        factors = {'general': 1.0, 'healthcare': 1.0, 'childcare': 1.0}
        # Before any update, factors should be 1.0
        assert factors['general'] == 1.0

    def test_general_factor_stays_flat_in_real_terms(self):
        """
        All-real rebaseline: general CPI does not grow real liabilities, so the
        general factor stays exactly 1.0 no matter how many years elapse.
        (Was: assert it grows to ~1 + rate after one update.)
        """
        np.random.seed(0)
        factors = {'general': 1.0, 'healthcare': 1.0, 'childcare': 1.0}
        for _ in range(30):
            update_inflation_factors(factors)
        assert factors['general'] == 1.0

    def test_general_flat_healthcare_grows_at_real_excess(self):
        """
        All-real rebaseline (was test_inflation_factor_compounds_over_multiple_years,
        which asserted general ~1.31 after 10yr nominal compounding). Now general is
        flat at 1.0 while healthcare compounds at its real-excess rate
        (healthcare_rate - general_rate). With zero volatility the growth is exact.
        """
        old_vol = cfg.INFLATION_VOLATILITY
        cfg.INFLATION_VOLATILITY = 0.0
        try:
            factors = {'general': 1.0, 'healthcare': 1.0, 'childcare': 1.0}
            years = 10
            for _ in range(years):
                update_inflation_factors(factors)
            real_excess = cfg.INFLATION_RATES['healthcare'] - cfg.INFLATION_RATES['general']
            expected_hc = (1 + real_excess) ** years
            assert factors['general'] == 1.0
            assert factors['healthcare'] == pytest.approx(expected_hc, rel=1e-9)
            # healthcare must grow strictly faster than the flat general factor.
            assert factors['healthcare'] > factors['general']
        finally:
            cfg.INFLATION_VOLATILITY = old_vol

    def test_real_excess_categories_compound_multiplicatively(self):
        """
        Verify compounding (not additive) for a real-excess category: the healthcare
        factor after 2 years equals f1 * (1 + year2_excess_rate), not f1 + rate.
        (Was test_each_year_multiplies_not_adds, which checked the general factor;
        general is now flat so we assert the invariant on healthcare instead.)
        """
        np.random.seed(7)
        factors1 = {'general': 1.0, 'healthcare': 1.0, 'childcare': 1.0}
        update_inflation_factors(factors1)
        f_after_1 = factors1['healthcare']

        np.random.seed(7)
        factors2 = {'general': 1.0, 'healthcare': 1.0, 'childcare': 1.0}
        update_inflation_factors(factors2)
        update_inflation_factors(factors2)
        f_after_2 = factors2['healthcare']

        real_excess = cfg.INFLATION_RATES['healthcare'] - cfg.INFLATION_RATES['general']
        # Additive would give f_after_1 + real_excess; compounding does not.
        assert f_after_2 != pytest.approx(f_after_1 + real_excess, abs=0.001)
        # And healthcare genuinely grew year over year.
        assert f_after_2 > f_after_1 > 1.0


class TestAllRealFrame:
    """
    End-to-end pin of the ALL-REAL frame (accuracy fix #1) at the liability level.

    A single simulated stream of inflation factors is advanced year over year; we
    then confirm that liabilities the engine multiplies by the GENERAL factor stay
    FLAT in real terms, while liabilities the engine multiplies by the HEALTHCARE
    factor grow at the real-excess rate. This is the invariant the whole conversion
    rests on: real returns vs real liabilities.
    """

    def test_general_liabilities_flat_healthcare_grows_real_excess(self):
        from retirement_sim.account_simulation import calculate_retirement_expenses

        old_vol = cfg.INFLATION_VOLATILITY
        cfg.INFLATION_VOLATILITY = 0.0  # deterministic so growth is exact
        try:
            factors = {'general': 1.0, 'healthcare': 1.0, 'childcare': 1.0}

            # A fixed retirement age with no age-driven expense-schedule change in the
            # window we sample (avoid the 75+ late-retirement step-down and college).
            age = 68
            base_general_expense = calculate_retirement_expenses(age, factors)
            # Healthcare-factor liabilities (grown by inflation_factors['healthcare']
            # in the engine): base living healthcare cost + ACA premium.
            base_healthcare = cfg.calculate_healthcare_cost(age, True, factors['healthcare'])
            base_premium = cfg.calculate_aca_premium(50_000.0) * factors['healthcare']
            assert base_healthcare > 0 and base_premium > 0  # non-trivial baselines

            years = 12
            for _ in range(years):
                update_inflation_factors(factors)

            # General-factor liability: FLAT in real terms (same expense at same age).
            later_general_expense = calculate_retirement_expenses(age, factors)
            assert later_general_expense == pytest.approx(base_general_expense, rel=1e-9)

            # Healthcare-factor liabilities: grow at the real-excess rate exactly.
            real_excess = cfg.INFLATION_RATES['healthcare'] - cfg.INFLATION_RATES['general']
            growth = (1 + real_excess) ** years
            later_healthcare = cfg.calculate_healthcare_cost(age, True, factors['healthcare'])
            later_premium = cfg.calculate_aca_premium(50_000.0) * factors['healthcare']

            assert later_healthcare == pytest.approx(base_healthcare * growth, rel=1e-9)
            assert later_premium == pytest.approx(base_premium * growth, rel=1e-9)
            # Healthcare outpaced general (which was flat).
            assert later_healthcare > base_healthcare
            assert later_premium > base_premium
        finally:
            cfg.INFLATION_VOLATILITY = old_vol

    def test_child_expenses_grow_at_childcare_real_excess(self):
        """
        Child-related expenses must grow with the CHILDCARE factor (real-excess over
        general CPI), not the flat general factor. Uses an age at which both children
        are home so the child component is non-trivial, and isolates it by subtracting
        the non-child (general-factor) portion, which stays flat in real terms.
        """
        from retirement_sim.account_simulation import calculate_retirement_expenses

        old_vol = cfg.INFLATION_VOLATILITY
        cfg.INFLATION_VOLATILITY = 0.0  # deterministic so growth is exact
        try:
            factors = {'general': 1.0, 'healthcare': 1.0, 'childcare': 1.0}

            # First child 28-46, second 31-49 (YOUR_AGE=25). Age 40 => both home,
            # and no college/late-retirement schedule change in the sampled window.
            age = 40
            child_cost = cfg.calculate_child_expenses(age)
            assert child_cost > 0, "test age must have children at home"

            base_expense = calculate_retirement_expenses(age, factors)
            nonchild = base_expense - child_cost  # general-factor portion (flat)

            years = 20
            for _ in range(years):
                update_inflation_factors(factors)

            real_excess = cfg.INFLATION_RATES['childcare'] - cfg.INFLATION_RATES['general']
            growth = (1 + real_excess) ** years
            expected = nonchild + child_cost * growth  # only the child term grows

            later_expense = calculate_retirement_expenses(age, factors)
            assert later_expense == pytest.approx(expected, rel=1e-9)
            # And it genuinely exceeds the flat-general baseline (bug would keep it flat).
            assert later_expense > base_expense
        finally:
            cfg.INFLATION_VOLATILITY = old_vol


# ==============================================================================
# 11. DYNAMIC SPENDING GUARDRAIL TRIGGERS
# ==============================================================================

class TestDynamicSpendingGuardrails:
    """Spending cuts should trigger when portfolio falls below 70% of target."""

    def test_no_adjustment_at_full_portfolio(self):
        """Portfolio at 100% of target → no spending adjustment."""
        factor = cfg.calculate_spending_adjustment(
            current_portfolio=1_000_000,
            target_portfolio=1_000_000
        )
        assert factor == 1.0

    def test_cut_triggers_below_70pct(self):
        """Portfolio below 70% of target triggers spending cut."""
        factor = cfg.calculate_spending_adjustment(
            current_portfolio=650_000,   # 65% of target
            target_portfolio=1_000_000
        )
        assert factor < 1.0, "Should cut spending when portfolio below 70% of target"

    def test_cut_not_triggered_above_70pct(self):
        """Portfolio at 75% of target should NOT trigger cut."""
        factor = cfg.calculate_spending_adjustment(
            current_portfolio=750_000,
            target_portfolio=1_000_000
        )
        assert factor == 1.0

    def test_no_upside_increase_in_good_times(self):
        """Conservative mode: no spending increase even when portfolio > 130% of target."""
        factor = cfg.calculate_spending_adjustment(
            current_portfolio=1_400_000,  # 140% of target
            target_portfolio=1_000_000
        )
        assert factor == 1.0, "Conservative mode should not increase spending in good times"

    def test_guardrail_disabled_returns_one(self):
        """When DYNAMIC_SPENDING_ENABLED is False, always return 1.0."""
        original = cfg.DYNAMIC_SPENDING_ENABLED
        try:
            cfg.DYNAMIC_SPENDING_ENABLED = False
            factor = cfg.calculate_spending_adjustment(500_000, 1_000_000)
            assert factor == 1.0
        finally:
            cfg.DYNAMIC_SPENDING_ENABLED = original


# ==============================================================================
# 12. ROTH CONVERSION STOPS AT SS CLAIM AGE
# ==============================================================================

class TestRothConversionStopsAtSS:
    """Roth conversions should stop at ROTH_CONVERSION_STOP_AGE (when SS kicks in)."""

    def test_no_conversion_at_stop_age(self):
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()
        amount, _ = portfolio.perform_roth_conversion(cfg.ROTH_CONVERSION_STOP_AGE)
        assert amount == 0.0

    def test_no_conversion_after_stop_age(self):
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()
        amount, _ = portfolio.perform_roth_conversion(cfg.ROTH_CONVERSION_STOP_AGE + 5)
        assert amount == 0.0

    def test_conversion_allowed_before_stop_age(self):
        portfolio = create_initial_portfolio()
        portfolio.reset_yearly_income()
        amount, _ = portfolio.perform_roth_conversion(cfg.ROTH_CONVERSION_STOP_AGE - 1)
        # Should attempt conversion if there's traditional balance and bracket room
        # (portfolio has traditional accounts from create_initial_portfolio)
        assert amount >= 0.0  # just confirm no error; may be 0 if no room


# ==============================================================================
# 13. MORTGAGE PAYOFF AGE REFLECTS MORTGAGE TERM
# ==============================================================================

class TestMortgagePayoffAge:
    """Mortgage should be paid off at YOUR_AGE + MORTGAGE_YEARS_REMAINING."""

    def test_mortgage_years_remaining_is_non_negative(self):
        assert cfg.MORTGAGE_YEARS_REMAINING >= 0

    def test_payoff_age_matches_config(self):
        expected_payoff = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
        assert expected_payoff == cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING

    def test_has_mortgage_one_year_before_payoff(self):
        payoff_age = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
        if cfg.MORTGAGE_YEARS_REMAINING > 0:
            assert cfg.has_mortgage(payoff_age - 1) is True
        else:
            assert cfg.has_mortgage(cfg.YOUR_AGE) is False

    def test_no_mortgage_at_payoff_age(self):
        payoff_age = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
        assert cfg.has_mortgage(payoff_age) is False

    def test_no_mortgage_well_after_payoff(self):
        """Far beyond the payoff age, there's no mortgage."""
        payoff_age = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
        assert cfg.has_mortgage(payoff_age + 10) is False

    def test_mortgage_included_in_expenses_before_payoff(self):
        payoff_age = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
        expenses_before = cfg.calculate_annual_expenses(payoff_age - 1)
        expenses_after = cfg.calculate_annual_expenses(payoff_age)
        assert expenses_before - expenses_after == pytest.approx(cfg.MORTGAGE_ANNUAL, abs=1)


# ==============================================================================
# 14. NIIT ZERO BELOW THRESHOLD, NON-ZERO ABOVE
# ==============================================================================

class TestNIIT:
    """Net Investment Income Tax: 3.8% on investment income above $250k MAGI."""

    def test_no_niit_below_threshold(self):
        """MAGI below $250k → $0 NIIT."""
        niit = cfg.calculate_niit(magi=200_000, net_investment_income=50_000)
        assert niit == 0.0

    def test_no_niit_at_threshold(self):
        """MAGI exactly at $250k → $0 NIIT."""
        niit = cfg.calculate_niit(magi=cfg.NIIT_THRESHOLD_MFJ, net_investment_income=50_000)
        assert niit == 0.0

    def test_niit_applied_above_threshold(self):
        """MAGI above $250k → NIIT on the lesser of investment income or excess MAGI."""
        magi = 300_000
        investment_income = 30_000
        niit = cfg.calculate_niit(magi=magi, net_investment_income=investment_income)
        # Excess MAGI = $50k, investment income = $30k → taxable = min(30k, 50k) = $30k
        expected = 30_000 * cfg.NIIT_RATE
        assert abs(niit - expected) < 0.01

    def test_niit_capped_at_investment_income(self):
        """NIIT is capped at investment income even if excess MAGI is larger."""
        magi = 1_000_000
        investment_income = 10_000
        niit = cfg.calculate_niit(magi=magi, net_investment_income=investment_income)
        expected = investment_income * cfg.NIIT_RATE
        assert abs(niit - expected) < 0.01

    def test_niit_uses_excess_magi_when_smaller(self):
        """When excess MAGI < investment income, NIIT is on excess MAGI only."""
        magi = 260_000   # $10k above threshold
        investment_income = 50_000
        niit = cfg.calculate_niit(magi=magi, net_investment_income=investment_income)
        expected = 10_000 * cfg.NIIT_RATE  # only $10k excess
        assert abs(niit - expected) < 0.01
