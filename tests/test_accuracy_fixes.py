"""
Pinning tests for discrete accuracy fixes identified in the model audit.

Each test below corresponds to a specific ranked finding in
tasks/audit_findings.json and pins the corrected behavior so a future
regression is caught by `pytest tests/`.
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from retirement_sim import config as cfg
from retirement_sim.account_simulation import (
    AccountPortfolio,
    CaliforniaTaxBrackets,
    NoStateTax,
    FlatRateStateTax,
    calculate_ltcg_tax,
    simulate_retirement_year,
    _true_up_social_security_tax,
    Account,
    AccountType,
    GROSSUP_TOLERANCE,
)


# ==============================================================================
# Rank #22: CA MFJ standard deduction corrected from stale $10,726 (2023 value)
# to $11,080 (2024 FTB value), de-duplicated into a single named constant.
# ==============================================================================

class TestCaliforniaStandardDeductionFix:
    def test_constant_value_matches_2024_ftb_figure(self):
        """The named constant must hold the correct 2024 CA MFJ standard deduction."""
        assert cfg.CA_STANDARD_DEDUCTION_MFJ_2024 == 11_080

    def test_marginal_tax_on_income_uses_named_constant(self):
        """
        calculate_marginal_tax_on_income() computes CA tax using the CA standard
        deduction internally. Verify the CA portion of the result matches a
        hand-computed value using CA_STANDARD_DEDUCTION_MFJ_2024, not the old
        stale $10,726 figure.
        """
        portfolio = AccountPortfolio()
        portfolio.year_ordinary_income = 0.0

        income = 50_000.0
        marginal_tax = portfolio.calculate_marginal_tax_on_income(income)

        # Reconstruct the expected federal + CA tax using the corrected constant.
        std_deduction = portfolio.get_standard_deduction()
        taxable_before = max(0, 0.0 - std_deduction)
        taxable_after = max(0, 0.0 + income - std_deduction)
        federal_tax = (
            portfolio.federal_tax_brackets.calculate_tax(taxable_after)
            - portfolio.federal_tax_brackets.calculate_tax(taxable_before)
        )

        ca_brackets = CaliforniaTaxBrackets()
        ca_std_deduction = cfg.CA_STANDARD_DEDUCTION_MFJ_2024
        ca_taxable_before = max(0, 0.0 - ca_std_deduction)
        ca_taxable_after = max(0, 0.0 + income - ca_std_deduction)
        expected_ca_tax = (
            ca_brackets.calculate_tax(ca_taxable_after)
            - ca_brackets.calculate_tax(ca_taxable_before)
        )

        expected_total = federal_tax + expected_ca_tax
        assert marginal_tax == expected_total

        # Confirm this differs from the stale 2023 value, i.e. the fix is live.
        stale_ca_std_deduction = 10_726
        stale_ca_taxable_before = max(0, 0.0 - stale_ca_std_deduction)
        stale_ca_taxable_after = max(0, 0.0 + income - stale_ca_std_deduction)
        stale_ca_tax = (
            ca_brackets.calculate_tax(stale_ca_taxable_after)
            - ca_brackets.calculate_tax(stale_ca_taxable_before)
        )
        assert expected_ca_tax != stale_ca_tax

    def test_no_duplicated_literal_remains_in_source(self):
        """The stale hardcoded 10_726 literal must no longer appear in the engine."""
        import inspect
        from retirement_sim import account_simulation as sim_module

        source = inspect.getsource(sim_module)
        assert "10_726" not in source
        assert "10726" not in source


# ==============================================================================
# Rank #20: calculate_rmd() must honor the caller-resolved per-owner RMD start
# age instead of re-gating on the single module-global RMD_START_AGE.
# ==============================================================================

class TestRmdPerOwnerStartAge:
    def test_default_matches_module_global(self):
        """
        With no start_age argument, calculate_rmd falls back to RMD_START_AGE,
        preserving legacy (equal-birth-year) behavior exactly.
        """
        balance = 100_000.0
        just_below = cfg.RMD_START_AGE - 1
        at_start = cfg.RMD_START_AGE

        # Below the global start age: no RMD.
        assert cfg.calculate_rmd(balance, just_below) == 0
        # At the global start age: an RMD is due.
        assert cfg.calculate_rmd(balance, at_start) > 0
        # Explicitly passing the global start age is identical to the default.
        assert (
            cfg.calculate_rmd(balance, at_start)
            == cfg.calculate_rmd(balance, at_start, cfg.RMD_START_AGE)
        )

    def test_earlier_owner_start_age_triggers_rmd(self):
        """
        A partner born 1958 has an RMD start age of 73 (get_rmd_start_age).
        At age 73 an RMD must be due when the resolved start_age is passed,
        even though the module-global RMD_START_AGE (75, from YOUR_BIRTH_YEAR
        2001) would otherwise suppress it.
        """
        balance = 100_000.0
        older_start = cfg.get_rmd_start_age(1958)
        assert older_start == 73
        # The default profile's global start age is later than this owner's.
        assert cfg.RMD_START_AGE > older_start

        # With the resolved start age, the RMD is honored at 73/74.
        rmd_at_73 = cfg.calculate_rmd(balance, 73, older_start)
        assert rmd_at_73 == balance / cfg.RMD_TABLE[73]
        assert rmd_at_73 > 0
        assert cfg.calculate_rmd(balance, 74, older_start) > 0

        # The old buggy behavior (global gate) would have returned 0 at 73/74.
        assert cfg.calculate_rmd(balance, 73, cfg.RMD_START_AGE) == 0

    def test_later_owner_start_age_suppresses_rmd(self):
        """
        An owner whose resolved start age is later than their current age must
        get no RMD, regardless of the global RMD_START_AGE.
        """
        balance = 100_000.0
        later_start = 75
        assert cfg.calculate_rmd(balance, 73, later_start) == 0
        assert cfg.calculate_rmd(balance, 74, later_start) == 0
        assert cfg.calculate_rmd(balance, 75, later_start) > 0


# ==============================================================================
# Rank #7: Federal LTCG must stack gains on TAXABLE ordinary income (gross minus
# the standard deduction), per the IRS Qualified Dividends & Capital Gain
# worksheet, not on gross ordinary income.
# ==============================================================================

class TestLtcgStacksOnTaxableIncome:
    def test_gains_fit_in_zero_bracket_after_deduction(self):
        """
        Finding scenario: $25k ordinary income, $80k gains, $29,200 deduction.
        Taxable ordinary income is max(0, 25k - 29.2k) = 0, so all $80k of gains
        fit under the $94,050 0% LTCG bracket -> $0 federal LTCG. Stacking on
        gross ($25k) would have pushed part of the gains into the 15% bracket.
        """
        gross_ordinary = 25_000.0
        gains = 80_000.0
        std_deduction = 29_200.0
        taxable_ordinary = max(0, gross_ordinary - std_deduction)

        # Corrected base: gains stack on $0 taxable ordinary income -> all in 0%.
        assert calculate_ltcg_tax(gains, taxable_ordinary) == 0

        # The old (buggy) gross-income base would have taxed some gains at 15%.
        assert calculate_ltcg_tax(gains, gross_ordinary) > 0

    def test_withdraw_tax_efficient_uses_post_deduction_base(self):
        """
        End-to-end: the LTCG withdrawal path must compute federal LTCG using
        (year_ordinary_income - standard_deduction) as the stacking base.
        """
        portfolio = AccountPortfolio()
        # Force ages so the standard deduction is the base $29,200 (no age add-on).
        portfolio.current_your_age = 45
        portfolio.current_partner_age = 45
        std_deduction = portfolio.get_standard_deduction()

        # Ordinary income below the standard deduction => taxable ordinary is 0.
        portfolio.year_ordinary_income = 25_000.0
        assert max(0, portfolio.year_ordinary_income - std_deduction) == 0

        # Replace accounts with a single all-gains taxable brokerage account.
        # Account.__post_init__ resets cost_basis for TAXABLE accounts, so we
        # zero it AFTER construction => every withdrawn dollar is a realized gain.
        gains = 80_000.0
        brokerage = Account(
            name="brokerage",
            account_type=AccountType.TAXABLE,
            balance=gains,
            owner="you",
        )
        brokerage.cost_basis = 0.0
        portfolio.accounts = {"brokerage": brokerage}
        portfolio.total_niit_paid = 0.0

        withdrawn, taxes = portfolio.withdraw_tax_efficient(gains, your_age=65)

        # Federal LTCG with the corrected base is 0 (gains fit in 0% bracket after
        # the standard deduction). CA still taxes gains as ordinary income, so
        # `taxes` reflects only CA tax + NIIT here.
        fed_ltcg = calculate_ltcg_tax(gains, max(0, portfolio.year_ordinary_income - std_deduction))
        assert fed_ltcg == 0

        # Compare against what the buggy gross-stacking base would have produced.
        stale_fed_ltcg = calculate_ltcg_tax(gains, 25_000.0)
        assert stale_fed_ltcg > 0

        # Reconstruct the CA + NIIT components the engine also charges on the gains
        # so we can isolate the federal LTCG contribution to `taxes`.
        ca_brackets = CaliforniaTaxBrackets()
        ca_std = cfg.CA_STANDARD_DEDUCTION_MFJ_2024
        ca_before = max(0, 25_000.0 - ca_std)
        ca_after = max(0, 25_000.0 + gains - ca_std)
        ca_tax = ca_brackets.calculate_tax(ca_after) - ca_brackets.calculate_tax(ca_before)
        niit = cfg.calculate_niit(25_000.0 + gains, gains)

        # Total taxes == CA + NIIT + federal LTCG(0). It must exclude the stale
        # gross-stacked federal LTCG amount.
        assert abs(taxes - (ca_tax + niit)) < 1e-6
        assert withdrawn == gains


# ==============================================================================
# Rank #6: Glide path start allocation corrected from 90/10 to 80/20 so it
# matches the accumulation-phase STOCK_ALLOCATION/BOND_ALLOCATION and de-risks
# monotonically through the retirement transition instead of stepping equity
# exposure UP right as withdrawals begin.
# ==============================================================================

class TestGlidePathStartsAtAccumulationAllocation:
    def test_glide_path_start_constants_match_accumulation_allocation(self):
        """The glide path's starting mix must equal the accumulation-phase mix."""
        assert cfg.GLIDE_PATH_START_STOCK_PCT == cfg.STOCK_ALLOCATION == 0.80
        assert cfg.GLIDE_PATH_START_BOND_PCT == cfg.BOND_ALLOCATION == 0.20

    def test_allocation_at_retirement_transition_is_80_20(self):
        """
        calculate_asset_allocation() evaluated exactly at the retirement age
        (the first year of withdrawals) must return ~80/20, not 90/10.
        """
        retirement_age = 50
        stock_alloc, bond_alloc = cfg.calculate_asset_allocation(
            age=retirement_age, retirement_age=retirement_age
        )
        assert abs(stock_alloc - 0.80) < 1e-9
        assert abs(bond_alloc - 0.20) < 1e-9

    def test_allocation_is_continuous_across_the_transition(self):
        """
        The allocation the year before retirement (accumulation mix) and the
        allocation the year retirement starts must match exactly, so equity
        exposure never steps UP at the worst possible moment (right as
        withdrawals begin).
        """
        retirement_age = 50
        pre_retirement_stock, pre_retirement_bond = cfg.calculate_asset_allocation(
            age=retirement_age - 1, retirement_age=retirement_age
        )
        at_retirement_stock, at_retirement_bond = cfg.calculate_asset_allocation(
            age=retirement_age, retirement_age=retirement_age
        )
        assert pre_retirement_stock == at_retirement_stock == cfg.STOCK_ALLOCATION
        assert pre_retirement_bond == at_retirement_bond == cfg.BOND_ALLOCATION

    def test_glide_path_deriks_monotonically_after_retirement(self):
        """
        Stock allocation must be non-increasing (bond allocation non-decreasing)
        as age advances from retirement to the glide path end age.
        """
        retirement_age = 50
        ages = range(retirement_age, cfg.GLIDE_PATH_END_AGE + 1)
        stock_pcts = [
            cfg.calculate_asset_allocation(age=a, retirement_age=retirement_age)[0]
            for a in ages
        ]
        assert all(
            stock_pcts[i] >= stock_pcts[i + 1] for i in range(len(stock_pcts) - 1)
        )


# ==============================================================================
# Rank #5: STATE_CHOICE is wired into the engine. AccountPortfolio selects its
# state-tax model from cfg.STATE_CHOICE: "CA" (default, unchanged) ->
# CaliforniaTaxBrackets, "No state tax" -> NoStateTax (zero), "Other" ->
# FlatRateStateTax at cfg.YOUR_MARGINAL_TAX_RATE.
# ==============================================================================

class TestStateChoiceWiring:
    def _restore(self, choice, rate):
        cfg.STATE_CHOICE = choice
        cfg.YOUR_MARGINAL_TAX_RATE = rate

    def test_default_is_california_unchanged(self):
        orig_choice, orig_rate = cfg.STATE_CHOICE, cfg.YOUR_MARGINAL_TAX_RATE
        try:
            cfg.STATE_CHOICE = "CA"
            p = AccountPortfolio()
            assert isinstance(p.ca_tax_brackets, CaliforniaTaxBrackets)
            # CA progressive tax on $100k taxable income is a positive amount.
            assert p.ca_tax_brackets.calculate_tax(100_000) > 0
        finally:
            self._restore(orig_choice, orig_rate)

    def test_no_state_tax_is_zero(self):
        orig_choice, orig_rate = cfg.STATE_CHOICE, cfg.YOUR_MARGINAL_TAX_RATE
        try:
            cfg.STATE_CHOICE = "No state tax"
            p = AccountPortfolio()
            assert isinstance(p.ca_tax_brackets, NoStateTax)
            assert p.ca_tax_brackets.calculate_tax(100_000) == 0.0
            assert p.ca_tax_brackets.calculate_tax(1_000_000) == 0.0
        finally:
            self._restore(orig_choice, orig_rate)

    def test_other_applies_flat_marginal_rate(self):
        orig_choice, orig_rate = cfg.STATE_CHOICE, cfg.YOUR_MARGINAL_TAX_RATE
        try:
            cfg.STATE_CHOICE = "Other"
            cfg.YOUR_MARGINAL_TAX_RATE = 0.09
            p = AccountPortfolio()
            assert isinstance(p.ca_tax_brackets, FlatRateStateTax)
            # Flat 9% of $100k taxable income == $9,000.
            assert p.ca_tax_brackets.calculate_tax(100_000) == 9_000.0
            # No tax on zero / negative income.
            assert p.ca_tax_brackets.calculate_tax(0) == 0.0
        finally:
            self._restore(orig_choice, orig_rate)

    def test_unknown_choice_falls_back_to_california(self):
        orig_choice, orig_rate = cfg.STATE_CHOICE, cfg.YOUR_MARGINAL_TAX_RATE
        try:
            cfg.STATE_CHOICE = "Narnia"
            p = AccountPortfolio()
            assert isinstance(p.ca_tax_brackets, CaliforniaTaxBrackets)
        finally:
            self._restore(orig_choice, orig_rate)


class TestCaliforniaSocialSecurityExemption:
    """California does not tax Social Security at the state level. Booked SS
    tax under CA must be lower than the pre-fix calculation; the exemption
    must NOT leak into 'Other'/'No state tax', which don't model this."""

    def _restore(self, choice, exempt_flag, include_ss):
        cfg.STATE_CHOICE = choice
        cfg.MODEL_CA_EXEMPTS_SOCIAL_SECURITY = exempt_flag
        cfg.INCLUDE_SOCIAL_SECURITY = include_ss

    def _book_ss(self, your_age=70, other_agi=80_000.0):
        p = AccountPortfolio()
        p.reset_yearly_income()
        p.update_ages(your_age)
        p.year_ordinary_income = other_agi
        ss_income = cfg.calculate_social_security(your_age, cfg.SS_CLAIM_AGE)
        ss_tax = _true_up_social_security_tax(p, ss_income, 0.0)
        return ss_tax, p

    def test_ca_booked_ss_tax_is_lower_with_exemption_on(self):
        orig = (cfg.STATE_CHOICE, cfg.MODEL_CA_EXEMPTS_SOCIAL_SECURITY, cfg.INCLUDE_SOCIAL_SECURITY)
        try:
            cfg.STATE_CHOICE = "CA"
            cfg.INCLUDE_SOCIAL_SECURITY = True

            cfg.MODEL_CA_EXEMPTS_SOCIAL_SECURITY = False
            old_tax, _ = self._book_ss()

            cfg.MODEL_CA_EXEMPTS_SOCIAL_SECURITY = True
            new_tax, _ = self._book_ss()

            assert new_tax < old_tax
        finally:
            self._restore(*orig)

    def test_other_and_no_state_tax_are_byte_identical_regardless_of_toggle(self):
        """The exemption is a CA-specific rule; a flat-rate 'Other' stand-in or
        an explicit no-state-tax choice must be unaffected either way."""
        orig = (cfg.STATE_CHOICE, cfg.MODEL_CA_EXEMPTS_SOCIAL_SECURITY, cfg.INCLUDE_SOCIAL_SECURITY)
        try:
            cfg.INCLUDE_SOCIAL_SECURITY = True
            for choice in ("Other", "No state tax"):
                cfg.STATE_CHOICE = choice

                cfg.MODEL_CA_EXEMPTS_SOCIAL_SECURITY = False
                tax_off, _ = self._book_ss()

                cfg.MODEL_CA_EXEMPTS_SOCIAL_SECURITY = True
                tax_on, _ = self._book_ss()

                assert tax_off == pytest.approx(tax_on), choice
        finally:
            self._restore(*orig)


# ==============================================================================
# Rank #3: ACA/Medicare MAGI must be built from ACTUAL realized income
# (year_ordinary_income + year_investment_income) AFTER expense withdrawals
# realize capital gains and after Roth conversions add ordinary income --
# not from the pre-withdrawal `year_ordinary_income + adjusted_expenses*0.5`
# proxy. The circularity (premium is itself an expense that drives the
# withdrawals that realize the income) is resolved with a two-pass estimate:
# a provisional side-effect-free quote sizes the withdrawals, then the premium
# is recomputed from true MAGI, recorded once, and any shortfall funded.
# ==============================================================================

class TestHealthInsuranceMagiTiming:
    def _make_brokerage_only_portfolio(self, brokerage_balance):
        """
        A retiree whose only asset is a large all-gains taxable brokerage
        account. Every withdrawn dollar is a realized long-term capital gain,
        so it flows into year_investment_income (MAGI) -- exactly the income
        the old proxy AGI omitted.
        """
        p = AccountPortfolio()
        p.accounts = {}
        brokerage = Account(
            name="brokerage",
            account_type=AccountType.TAXABLE,
            balance=brokerage_balance,
            owner="you",
        )
        brokerage.cost_basis = 0.0  # all gains
        p.add_account(brokerage)
        # Neutralize confounders so the premium change is attributable to MAGI.
        p.set_retirement_baseline(1.0)
        p.ltc_needs_by_age = {}
        return p

    def test_quote_is_side_effect_free(self):
        """
        quote_health_insurance_cost must NOT mutate the running premium totals,
        so it can be called for the provisional (pass 1) estimate without
        double-counting when the true premium is recorded in pass 2.
        """
        p = AccountPortfolio()
        before_aca = p.total_aca_premiums
        before_medicare = p.total_medicare_premiums
        # Pre-65 -> ACA path; post-65 -> Medicare path.
        assert p.quote_health_insurance_cost(50, 40_000.0) >= 0
        assert p.quote_health_insurance_cost(70, 500_000.0) >= 0
        assert p.total_aca_premiums == before_aca
        assert p.total_medicare_premiums == before_medicare

    def test_brokerage_funded_year_records_higher_aca_premium(self, monkeypatch):
        """
        Scenario (finding): a pre-65 retiree funds a large year almost entirely
        from taxable brokerage LTCG. Realized gains push MAGI above 400% FPL, so
        the recorded ACA premium jumps to the full un-subsidized base premium --
        strictly HIGHER than the old proxy-AGI premium, which saw ~zero MAGI
        (no ordinary income + a small expenses*0.5 proxy) and got a fat subsidy.
        """
        assert cfg.ACA_ENABLED
        # Pins the legacy flat-band quote (calculate_aca_premium); the age-rated
        # path has its own coverage in test_aca_marketplace.py.
        monkeypatch.setattr(cfg, "MODEL_ACA_AGE_RATED", False)

        your_age = 55  # pre-Medicare -> ACA
        # A big expense funded from all-gains brokerage. Withdrawing to cover it
        # realizes >400% FPL of LTCG, so MAGI lands above the subsidy cliff.
        expenses = 130_000.0
        p = self._make_brokerage_only_portfolio(brokerage_balance=2_000_000.0)

        # Old-proxy premium the buggy code would have recorded: MAGI proxy is
        # year_ordinary_income(0) + adjusted_expenses*0.5. With no dynamic-spend
        # movement adjusted_expenses ~= expenses, so proxy ~= expenses/2.
        # Regardless of the exact adjusted value, the proxy MAGI is far below the
        # realized-gains MAGI, so it earned a subsidy.
        old_proxy_premium = cfg.calculate_aca_premium(expenses * 0.5)

        success = simulate_retirement_year(
            p, your_age=your_age, expenses=expenses,
            annual_return=0.0, inflation_factor=1.0, retirement_age=55,
        )
        assert success

        recorded = p.total_aca_premiums
        # The corrected premium is based on true MAGI (realized gains), which is
        # above the 400% FPL cliff -> full base premium.
        assert recorded == cfg.ACA_BASE_ANNUAL_PREMIUM
        # And it is strictly higher than the old proxy-AGI premium (the bug).
        assert recorded > old_proxy_premium

    def test_low_income_roth_free_year_unchanged_from_true_magi(self, monkeypatch):
        """
        Sanity floor: when there is NO realized gain and NO conversion income
        (a pure cash-funded year), true MAGI == 0-ish and the recorded premium
        equals the ACA quote at that MAGI -- i.e. the two-pass true-up does not
        inflate premiums when there is genuinely no extra income to recognize.

        Asserts a PREMIUM equality, so the all-in healthcare floor is switched
        off: at ~zero MAGI the subsidised premium is far below the $24k
        early-retirement band, and the floor would otherwise clamp the recorded
        figure to the band and mask the MAGI-timing behaviour under test. The
        floor has its own coverage in TestHealthcareCostFloor.
        """
        monkeypatch.setattr(cfg, "MODEL_ACA_AGE_RATED", False)  # legacy flat-band quote
        _saved_floor = getattr(cfg, "MODEL_HEALTHCARE_COST_FLOOR", True)
        cfg.MODEL_HEALTHCARE_COST_FLOOR = False
        try:
            your_age = 55
            expenses = 40_000.0
            p = AccountPortfolio()
            p.accounts = {}
            # Fund entirely from cash (no gains, no ordinary income realized).
            cash = Account(
                name="cash", account_type=AccountType.CASH, balance=1_000_000.0, owner="you",
            )
            p.add_account(cash)
            p.set_retirement_baseline(1.0)
            p.ltc_needs_by_age = {}

            success = simulate_retirement_year(
                p, your_age=your_age, expenses=expenses,
                annual_return=0.0, inflation_factor=1.0, retirement_age=55,
            )
            assert success
            # No ordinary income and no investment income were realized this year.
            assert p.year_investment_income == 0.0
            # Premium recorded equals the ACA quote at true MAGI (== realized income,
            # which is ~0 here), NOT some inflated figure.
            expected = cfg.calculate_aca_premium(
                p.year_ordinary_income + p.year_investment_income
            )
            assert abs(p.total_aca_premiums - expected) < 1e-6
        finally:
            cfg.MODEL_HEALTHCARE_COST_FLOOR = _saved_floor


# ==============================================================================
# Rank #2: withdraw_tax_efficient() must FUND the income tax and early-withdrawal
# penalties out of additional withdrawals (gross-up), so the cash left after
# taxes/penalties equals the NET need. Previously it withdrew only the net need,
# computed the tax, recorded it, but never removed that tax cash from any
# account -- so portfolios lasted longer than reality and success was
# optimistically biased. Because the tax on the gross-up is itself taxable, the
# required gross is an iterative fixed point.
#
# These tests do NOT pin old success values (the fix changes every number).
# They assert invariants:
#   (a) gross withdrawn exceeds the net need by ~ the computed tax+penalty, and
#       the account balances drop by the full gross (taxes are truly funded);
#   (b) a hand-computed single-scenario example matches within tolerance.
# ==============================================================================

class TestWithdrawalGrossUpFundsTaxes:
    def test_traditional_pre_59_5_grosses_up_for_tax_and_penalty(self):
        """
        (a)+(b): A pre-59.5 retiree needs $100k NET from a traditional IRA
        (income tax + 10% early-withdrawal penalty). The model must withdraw a
        GROSS amount such that gross - tax - penalty == the $100k net need, and
        the traditional balance must fall by the full gross (the tax cash is
        genuinely removed from the account, not paid "for free").
        """
        p = AccountPortfolio()
        p.current_your_age = 50
        p.current_partner_age = 50
        p.year_ordinary_income = 0.0

        trad = Account(
            name="trad",
            account_type=AccountType.TRADITIONAL_IRA,
            balance=5_000_000.0,   # ample: never depletes, so gross-up converges
            owner="you",
        )
        p.accounts = {"trad": trad}
        p.total_early_withdrawal_penalties = 0.0

        net_need = 100_000.0
        start_balance = trad.balance

        withdrawn, cost = p.withdraw_tax_efficient(
            net_need, is_medical=False, your_age=50
        )
        net_delivered = withdrawn - cost

        # The cash left after taxes/penalties covers the net need (fixed point).
        assert abs(net_delivered - net_need) <= GROSSUP_TOLERANCE + 1e-6

        # Gross must strictly exceed the net need -- taxes are funded, not free.
        assert withdrawn > net_need

        # Invariant (a): gross exceeds the net need by ~ the computed tax+penalty.
        assert abs(withdrawn - (net_need + cost)) <= GROSSUP_TOLERANCE + 1e-6

        # The tax cash is genuinely removed: balance drops by the FULL gross.
        assert abs((start_balance - trad.balance) - withdrawn) < 1e-6

        # (b) Hand-computed: with $0 prior ordinary income and no state tax on the
        # gross via the CA/federal marginal calc, recompute the tax+penalty that
        # the engine charges on the gross and confirm it matches `cost` exactly.
        # (calculate_marginal_tax_on_income mutates year_ordinary_income, so use a
        # fresh portfolio to reproduce the marginal tax on `withdrawn`.)
        ref = AccountPortfolio()
        ref.current_your_age = 50
        ref.current_partner_age = 50
        ref.year_ordinary_income = 0.0
        expected_income_tax = ref.calculate_marginal_tax_on_income(withdrawn)
        expected_penalty = cfg.calculate_early_withdrawal_penalty(
            withdrawn, AccountType.TRADITIONAL_IRA.value, 50
        )
        assert abs(cost - (expected_income_tax + expected_penalty)) < 1e-6

    def test_taxable_ltcg_grosses_up_for_capital_gains_tax(self):
        """
        (a): A retiree needs $80k NET from an all-gains taxable brokerage account.
        LTCG (CA + NIIT here; federal LTCG may be 0 in the 0% bracket) must be
        funded by extra withdrawals, so the gross exceeds the net need by ~ the
        computed tax and the balance drops by the full gross.
        """
        p = AccountPortfolio()
        p.current_your_age = 65
        p.current_partner_age = 65
        p.year_ordinary_income = 0.0
        p.total_niit_paid = 0.0

        brokerage = Account(
            name="brokerage",
            account_type=AccountType.TAXABLE,
            balance=5_000_000.0,
            owner="you",
        )
        brokerage.cost_basis = 0.0  # every withdrawn dollar is a realized gain
        p.accounts = {"brokerage": brokerage}

        net_need = 80_000.0
        start_balance = brokerage.balance

        withdrawn, cost = p.withdraw_tax_efficient(
            net_need, is_medical=False, your_age=65
        )
        net_delivered = withdrawn - cost

        # There IS a positive tax on these gains (CA taxes LTCG as ordinary
        # income), so a real gross-up must have happened.
        assert cost > 0
        assert withdrawn > net_need

        # Invariant (a): net delivered covers the need; gross ~= net + tax.
        assert abs(net_delivered - net_need) <= GROSSUP_TOLERANCE + 1e-6
        assert abs(withdrawn - (net_need + cost)) <= GROSSUP_TOLERANCE + 1e-6

        # Balance falls by the full gross -- the tax cash left the account.
        assert abs((start_balance - brokerage.balance) - withdrawn) < 1e-6

    def test_zero_tax_path_needs_no_gross_up(self):
        """
        Sanity floor: a pure cash withdrawal incurs no tax/penalty, so the gross
        equals the net need exactly (the gross-up loop terminates immediately).
        """
        p = AccountPortfolio()
        p.accounts = {}
        cash = Account(
            name="cash", account_type=AccountType.CASH, balance=1_000_000.0, owner="you",
        )
        p.add_account(cash)

        net_need = 40_000.0
        withdrawn, cost = p.withdraw_tax_efficient(
            net_need, is_medical=False, your_age=50
        )
        assert cost == 0.0
        assert abs(withdrawn - net_need) < 1e-6

    def test_grossed_up_withdrawal_drains_more_than_the_old_net_only_behavior(self):
        """
        Regression guard for the core bug: the grossed-up gross withdrawal must be
        strictly larger than the (old-behavior) net-only withdrawal amount, i.e.
        the portfolio is drained by the taxes it owes rather than paying them for
        free. Verified via the balance delta exceeding the net need.
        """
        p = AccountPortfolio()
        p.current_your_age = 50
        p.current_partner_age = 50
        p.year_ordinary_income = 0.0
        trad = Account(
            name="trad",
            account_type=AccountType.TRADITIONAL_IRA,
            balance=5_000_000.0,
            owner="you",
        )
        p.accounts = {"trad": trad}
        start_balance = trad.balance

        net_need = 100_000.0
        p.withdraw_tax_efficient(net_need, is_medical=False, your_age=50)
        balance_drop = start_balance - trad.balance

        # The account was drained by MORE than the net need (the extra is the
        # tax+penalty the old code never removed).
        assert balance_drop > net_need


# ==============================================================================
# Rank #10 (engine): the per-year retirement withdrawal_log record additively
# logs the real taxes paid that year, so the chart layer can plot actual taxes
# instead of hardcoded constants. Keys are ADDITIVE; existing keys unchanged.
# ==============================================================================
class TestWithdrawalLogLogsPerYearTaxes:
    def _make_traditional_only_portfolio(self, balance):
        """A retiree whose only asset is a large traditional IRA, so every
        withdrawal is fully taxable as ordinary income (guaranteeing taxes > 0)."""
        p = AccountPortfolio()
        p.accounts = {}
        trad = Account(
            name="trad",
            account_type=AccountType.TRADITIONAL_IRA,
            balance=balance,
            owner="you",
        )
        p.add_account(trad)
        p.set_retirement_baseline(1.0)
        p.ltc_needs_by_age = {}
        return p

    def test_retirement_year_logs_nonnegative_taxes_matching_engine_delta(self):
        """
        A post-59.5 retiree funds a year entirely from a traditional IRA (fully
        taxable). The withdrawal_log entry for that year must:
          1. contain the additive tax keys (backward-compatible with old keys),
          2. log total_taxes >= 0, and
          3. equal the taxes the engine actually attributed to that year
             (delta of the cumulative total_taxes_paid, minus penalties).
        """
        your_age = 65  # post-59.5 -> ordinary income tax, no early-withdrawal penalty
        expenses = 120_000.0
        p = self._make_traditional_only_portfolio(balance=3_000_000.0)

        taxes_before = p.total_taxes_paid
        penalties_before = p.total_early_withdrawal_penalties

        success = simulate_retirement_year(
            p, your_age=your_age, expenses=expenses,
            annual_return=0.0, inflation_factor=1.0, retirement_age=55,
        )
        assert success
        assert len(p.withdrawal_log) == 1
        entry = p.withdrawal_log[0]

        # (0) Existing keys are all still present (backward compatibility).
        for key in ('age', 'cash', 'taxable', 'traditional', 'roth', 'hsa',
                    'total', 'portfolio_value', 'withdrawal_pct'):
            assert key in entry

        # (1) New additive keys present.
        for key in ('total_taxes', 'ss_tax', 'niit', 'penalties'):
            assert key in entry

        # (2) Non-negative, and this scenario actually incurs income tax.
        assert entry['total_taxes'] >= 0.0
        assert entry['total_taxes'] > 0.0

        # (3) Logged total equals the engine's per-year tax delta (running total
        #     rolls in penalties, so subtract the penalty delta -> pure taxes).
        engine_penalties = p.total_early_withdrawal_penalties - penalties_before
        engine_taxes = (p.total_taxes_paid - taxes_before) - engine_penalties
        assert abs(entry['total_taxes'] - engine_taxes) < 1e-6
        assert abs(entry['penalties'] - engine_penalties) < 1e-6


# ==============================================================================
# inflation-slider: EXPECTED_INFLATION (the UI slider) is now the single source
# of truth for general CPI. config.INFLATION_RATES['general'] is derived from it,
# and the sim_runner override path propagates a slider change into the built dict.
# The all-real frame pins the general growth factor at 1.0 (liabilities do not
# rescale), but the slider DOES drive healthcare/childcare real-excess growth
# (= category nominal literal - general) and the historical-path single-year
# deflation. At the default slider value the model number is unchanged.
# ==============================================================================
class TestInflationSliderIsLive:
    def test_default_general_equals_expected_inflation_and_prior_literal(self):
        # Default preserves the prior hardcoded general rate 0.0275.
        assert cfg.EXPECTED_INFLATION == 0.0275
        assert cfg.INFLATION_RATES['general'] == cfg.EXPECTED_INFLATION == 0.0275

    def test_healthcare_childcare_stay_own_nominal_literals(self):
        assert cfg.INFLATION_RATES['healthcare'] == 0.045
        assert cfg.INFLATION_RATES['childcare'] == 0.04

    def test_general_factor_stays_pinned_at_one_regardless_of_slider(self):
        from retirement_sim.account_simulation import update_inflation_factors
        factors = {'general': 1.0, 'healthcare': 1.0, 'childcare': 1.0}
        update_inflation_factors(factors)
        assert factors['general'] == 1.0

    def test_slider_moves_healthcare_real_excess_growth(self):
        # Real-excess = healthcare_nominal - general. Zero volatility isolates the mean.
        from retirement_sim import account_simulation as S
        orig_general = cfg.INFLATION_RATES['general']
        orig_vol = cfg.INFLATION_VOLATILITY
        try:
            cfg.INFLATION_VOLATILITY = 0.0
            # Low general -> larger real-excess -> faster healthcare growth.
            cfg.INFLATION_RATES['general'] = 0.02
            low = {'healthcare': 1.0}
            S.update_inflation_factors(low)
            # High general -> smaller real-excess -> slower healthcare growth.
            cfg.INFLATION_RATES['general'] = 0.04
            high = {'healthcare': 1.0}
            S.update_inflation_factors(high)
            # 0.045 - 0.02 = 0.025 vs 0.045 - 0.04 = 0.005
            assert low['healthcare'] == 1.0 + (0.045 - 0.02)
            assert high['healthcare'] == 1.0 + (0.045 - 0.04)
            assert low['healthcare'] > high['healthcare']
        finally:
            cfg.INFLATION_RATES['general'] = orig_general
            cfg.INFLATION_VOLATILITY = orig_vol

    def test_sim_runner_override_propagates_and_restores(self):
        import importlib
        ui_utils = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ui"))
        if ui_utils not in sys.path:
            sys.path.insert(0, ui_utils)
        sim_runner = importlib.import_module("utils.sim_runner")
        before = cfg.INFLATION_RATES['general']
        original = sim_runner._apply_overrides({"EXPECTED_INFLATION": 0.05})
        try:
            # Slider override propagated into the already-built dict.
            assert cfg.INFLATION_RATES['general'] == 0.05
        finally:
            sim_runner._restore_overrides(original)
        # Nested dict value restored, not left mutated.
        assert cfg.INFLATION_RATES['general'] == before
