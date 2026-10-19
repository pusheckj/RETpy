"""
Pinning tests for rank #18 lower-$ latent defects:

(a) SS taxable-portion TIMING (#18a): the taxable portion of Social Security is
    driven by the year's provisional income. It must reflect the income realized
    by the year's expense withdrawals + Roth conversion, not just the RMD income
    known before withdrawals. The engine now QUOTES a provisional SS tax to size
    withdrawals and RECOMPUTES + books the real SS tax after withdrawals +
    conversion. When later realized income is higher, the trued-up taxable SS (and
    its tax) must be >= the pre-withdrawal estimate.

(b) Roth-conversion OWNER co-mingling (#18b): converted dollars must be credited
    to the SAME owner's Roth IRA, not always dumped into your_roth_ira. Draining a
    partner's traditional balance must credit the partner's Roth.

(c) ESPP dead inputs (#18c): YOUR_ESPP_PCT * YOUR_ESPP_DISCOUNT * base_salary is
    now deposited into taxable brokerage during accumulation. A non-zero discount
    must MOVE net worth; a zero discount must be a no-op.

(d) Partner-spending formula (#18d): the sim_runner legacy expense fallback must
    use PARTNER_OTHER_MONTHLY (the household-expense knob the engine actually
    consumes), not the stale PARTNER_MONTHLY_SPENDING savings-math knob.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ui")))

from retirement_sim import config as cfg
from retirement_sim import account_simulation as sim
from retirement_sim.account_simulation import (
    AccountPortfolio,
    Account,
    AccountType,
    simulate_accumulation_year,
    _collect_social_security,
    _true_up_social_security_tax,
)


@pytest.fixture(autouse=True)
def _restore_cfg_flags():
    saved = {
        "ENABLE_ROTH_CONVERSION": cfg.ENABLE_ROTH_CONVERSION,
        "INCLUDE_SOCIAL_SECURITY": cfg.INCLUDE_SOCIAL_SECURITY,
        "YOUR_ESPP_PCT": getattr(cfg, "YOUR_ESPP_PCT", 0.0),
        "YOUR_ESPP_DISCOUNT": getattr(cfg, "YOUR_ESPP_DISCOUNT", 0.0),
        "STATE_CHOICE": getattr(cfg, "STATE_CHOICE", "CA"),
        "MODEL_CA_EXEMPTS_SOCIAL_SECURITY": getattr(cfg, "MODEL_CA_EXEMPTS_SOCIAL_SECURITY", True),
    }
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(cfg, k, v)


# ---------------------------------------------------------------------------
# (a) SS taxable-portion timing
# ---------------------------------------------------------------------------

def test_ss_provisional_quote_is_side_effect_free():
    """_collect_social_security only QUOTES the SS tax: it must not mutate
    year_ordinary_income or the running tax totals (those are booked later)."""
    cfg.INCLUDE_SOCIAL_SECURITY = True
    p = AccountPortfolio()
    p.reset_yearly_income()
    p.update_ages(70)
    p.year_ordinary_income = 40_000.0  # some RMD income realized so far

    oi_before = p.year_ordinary_income
    ss_tax_start = p.total_ss_taxes_paid
    tax_start = p.total_taxes_paid

    ss_income, provisional_tax = _collect_social_security(p, 70, 1.0)

    assert ss_income > 0
    assert provisional_tax > 0
    # Side-effect-free: nothing recognized, nothing booked.
    assert p.year_ordinary_income == oi_before
    assert p.total_ss_taxes_paid == ss_tax_start
    assert p.total_taxes_paid == tax_start


def test_ss_trueup_taxes_more_when_realized_income_is_higher():
    """The bug: taxable SS computed from RMD-only income UNDERSTATES it. With more
    ordinary income realized (as expense withdrawals + Roth conversion do), the
    trued-up taxable SS and its tax must be strictly higher than the low-income
    provisional estimate."""
    cfg.INCLUDE_SOCIAL_SECURITY = True

    # Low-income provisional pass (only a little RMD income known).
    p_low = AccountPortfolio()
    p_low.reset_yearly_income()
    p_low.update_ages(70)
    p_low.year_ordinary_income = 20_000.0
    ss_income, provisional_tax = _collect_social_security(p_low, 70, 1.0)

    # Now the year realizes MORE ordinary income (withdrawals + conversion).
    p_high = AccountPortfolio()
    p_high.reset_yearly_income()
    p_high.update_ages(70)
    p_high.year_ordinary_income = 120_000.0
    real_tax = _true_up_social_security_tax(p_high, ss_income, provisional_tax)

    # Higher provisional income -> more of SS is taxable -> higher SS tax booked.
    assert real_tax > provisional_tax
    # And the real tax was actually booked into the running totals.
    assert p_high.total_ss_taxes_paid == pytest.approx(real_tax)
    assert p_high.total_taxes_paid == pytest.approx(real_tax)


def test_ss_trueup_uses_full_ordinary_income_as_provisional_base():
    """The trued-up taxable SS must equal calculate_taxable_social_security applied
    to the FINAL ordinary income (other AGI excludes SS itself), pinning the
    #3-consistent 'recompute from realized income' behavior.

    ``is_state_taxable=False`` on the expected-tax quote mirrors what
    _true_up_social_security_tax itself now passes -- CA exempts Social
    Security from state tax (see MODEL_CA_EXEMPTS_SOCIAL_SECURITY)."""
    cfg.INCLUDE_SOCIAL_SECURITY = True
    p = AccountPortfolio()
    p.reset_yearly_income()
    p.update_ages(70)
    p.year_ordinary_income = 80_000.0

    ss_income = cfg.calculate_social_security(70, cfg.SS_CLAIM_AGE)
    expected_taxable = cfg.calculate_taxable_social_security(ss_income, 80_000.0)
    expected_tax = p.quote_marginal_tax_on_income(expected_taxable, is_state_taxable=False)

    real_tax = _true_up_social_security_tax(p, ss_income, 0.0)
    assert real_tax == pytest.approx(expected_tax)


def test_true_up_social_security_is_ca_exempt():
    """After SS is trued up, its taxable amount must not inflate the CA base
    used by a LATER same-year withdrawal -- the bug: CA tax on a
    subsequent-in-year withdrawal (SS-tax shortfall, premium true-up, a car/
    house draw) was computed off a base that had already absorbed the
    taxable SS amount, which CA does not tax at all."""
    cfg.INCLUDE_SOCIAL_SECURITY = True
    cfg.STATE_CHOICE = "CA"
    cfg.MODEL_CA_EXEMPTS_SOCIAL_SECURITY = True
    p = AccountPortfolio()
    p.reset_yearly_income()
    p.update_ages(70)
    p.year_ordinary_income = 80_000.0

    ss_income = cfg.calculate_social_security(70, cfg.SS_CLAIM_AGE)
    _true_up_social_security_tax(p, ss_income, 0.0)

    taxable_ss = p.year_ordinary_income - 80_000.0
    assert taxable_ss > 0, "fixture must produce some taxable SS to be a real test"
    # The STATE base must exclude the taxable SS just recognized.
    assert p._state_taxable_base() == pytest.approx(80_000.0)

    # A subsequent withdrawal's CA tax must be computed off that $80k base,
    # not off year_ordinary_income (which now includes the taxable SS).
    ca_std_ded = cfg.CA_STANDARD_DEDUCTION_MFJ_2024
    expected_ca_tax = (
        p.ca_tax_brackets.calculate_tax(80_000.0 + 50_000.0 - ca_std_ded)
        - p.ca_tax_brackets.calculate_tax(80_000.0 - ca_std_ded)
    )
    base_before_withdrawal = p.year_ordinary_income
    fed_std_ded = p.get_standard_deduction()
    expected_fed_tax = (
        p.federal_tax_brackets.calculate_tax(base_before_withdrawal + 50_000.0 - fed_std_ded)
        - p.federal_tax_brackets.calculate_tax(base_before_withdrawal - fed_std_ded)
    )

    real_total_tax = p.calculate_marginal_tax_on_income(50_000.0)
    assert real_total_tax == pytest.approx(expected_fed_tax + expected_ca_tax)


def test_ca_ss_exemption_toggle_reproduces_old_behaviour():
    """MODEL_CA_EXEMPTS_SOCIAL_SECURITY=False must reproduce the pre-fix
    behaviour: taxable SS taxed by CA like any other ordinary income."""
    cfg.INCLUDE_SOCIAL_SECURITY = True
    cfg.STATE_CHOICE = "CA"

    def _run(exempt_flag):
        cfg.MODEL_CA_EXEMPTS_SOCIAL_SECURITY = exempt_flag
        p = AccountPortfolio()
        p.reset_yearly_income()
        p.update_ages(70)
        p.year_ordinary_income = 80_000.0
        ss_income = cfg.calculate_social_security(70, cfg.SS_CLAIM_AGE)
        ss_tax = _true_up_social_security_tax(p, ss_income, 0.0)
        return ss_tax, p

    exempt_tax, p_exempt = _run(True)
    old_tax, p_old = _run(False)

    assert exempt_tax < old_tax, "exempting SS from CA tax must lower the booked SS tax"
    assert p_old.year_state_exempt_income == 0.0, "toggle off must never populate the exemption ledger"
    assert p_exempt.year_state_exempt_income > 0.0


# ---------------------------------------------------------------------------
# (b) Roth-conversion owner co-mingling
# ---------------------------------------------------------------------------

def test_roth_conversion_credits_partner_roth_when_partner_trad_drained():
    """A conversion that drains ONLY the partner's traditional 401k must credit the
    PARTNER's Roth IRA, not your_roth_ira (the old always-your_roth bug)."""
    cfg.ENABLE_ROTH_CONVERSION = True
    p = AccountPortfolio()
    # Only the partner has a traditional balance to convert.
    p.add_account(Account("partner_401k", AccountType.TRADITIONAL_401K, 500_000, "partner"))
    p.add_account(Account("your_roth_ira", AccountType.ROTH_IRA, 0.0, "you"))
    p.add_account(Account("partner_roth_ira", AccountType.ROTH_IRA, 0.0, "partner"))
    p.add_account(Account("your_cash", AccountType.CASH, 100_000, "you"))
    p.reset_yearly_income()
    p.update_ages(62)

    your_roth_before = p.accounts["your_roth_ira"].balance
    conv, tax = p.perform_roth_conversion(62)
    assert conv > 0, "test needs an active conversion"

    # The converted dollars landed in the PARTNER's Roth (same owner), and NOT in
    # your Roth.
    assert p.accounts["partner_roth_ira"].balance == pytest.approx(conv)
    assert p.accounts["your_roth_ira"].balance == pytest.approx(your_roth_before)


def test_roth_conversion_routes_per_owner_when_both_have_traditional():
    """When both owners' traditional balances are drained, each owner's Roth gets
    exactly what was pulled from that owner's traditional (and the totals conserve)."""
    cfg.ENABLE_ROTH_CONVERSION = True
    # Force a large conversion cap so it spans both owners' small trad balances.
    p = AccountPortfolio()
    # Small balances so the whole conversion pulls from both.
    p.add_account(Account("your_401k", AccountType.TRADITIONAL_401K, 3_000, "you"))
    p.add_account(Account("partner_401k", AccountType.TRADITIONAL_401K, 4_000, "partner"))
    p.add_account(Account("your_roth_ira", AccountType.ROTH_IRA, 0.0, "you"))
    p.add_account(Account("partner_roth_ira", AccountType.ROTH_IRA, 0.0, "partner"))
    p.add_account(Account("your_cash", AccountType.CASH, 100_000, "you"))
    p.reset_yearly_income()
    p.update_ages(62)

    trad_before = 3_000 + 4_000
    conv, _ = p.perform_roth_conversion(62)
    assert conv > 0

    roth_total = p.accounts["your_roth_ira"].balance + p.accounts["partner_roth_ira"].balance
    trad_after = p.accounts["your_401k"].balance + p.accounts["partner_401k"].balance
    # Conservation: what left traditional equals what entered Roth.
    assert roth_total == pytest.approx(trad_before - trad_after)
    assert roth_total == pytest.approx(conv)
    # No owner's Roth received dollars pulled from the OTHER owner: each Roth gain
    # cannot exceed that owner's own traditional drawdown.
    your_drawn = 3_000 - p.accounts["your_401k"].balance
    partner_drawn = 4_000 - p.accounts["partner_401k"].balance
    assert p.accounts["your_roth_ira"].balance == pytest.approx(your_drawn)
    assert p.accounts["partner_roth_ira"].balance == pytest.approx(partner_drawn)


# ---------------------------------------------------------------------------
# (c) ESPP discount benefit
# ---------------------------------------------------------------------------

def _accum_your_brokerage_after_one_year(espp_pct, espp_discount, age=30):
    cfg.YOUR_ESPP_PCT = espp_pct
    cfg.YOUR_ESPP_DISCOUNT = espp_discount
    np.random.seed(7)
    p = AccountPortfolio()
    p.add_account(Account("your_401k", AccountType.TRADITIONAL_401K, 0.0, "you"))
    p.add_account(Account("your_roth_ira", AccountType.ROTH_IRA, 0.0, "you"))
    p.add_account(Account("your_hsa", AccountType.HSA, 0.0, "you"))
    p.add_account(Account("your_brokerage", AccountType.TAXABLE, 0.0, "you"))
    p.add_account(Account("your_cash", AccountType.CASH, 0.0, "you"))
    p.add_account(Account("partner_401k", AccountType.TRADITIONAL_401K, 0.0, "partner"))
    p.add_account(Account("partner_roth_ira", AccountType.ROTH_IRA, 0.0, "partner"))
    p.add_account(Account("partner_brokerage", AccountType.TAXABLE, 0.0, "partner"))
    p.add_account(Account("child1_529", AccountType.COLLEGE_529, 0.0, "child1"))
    p.add_account(Account("child2_529", AccountType.COLLEGE_529, 0.0, "child2"))
    simulate_accumulation_year(p, age, 0.0)  # 0% return isolates contributions
    return p.accounts["your_brokerage"].balance


def test_espp_discount_moves_net_worth():
    """A non-zero ESPP discount must ADD dollars to taxable brokerage vs the
    zero-discount baseline; the delta equals base_salary * pct * discount."""
    base = _accum_your_brokerage_after_one_year(espp_pct=0.10, espp_discount=0.0)
    with_espp = _accum_your_brokerage_after_one_year(espp_pct=0.10, espp_discount=0.15)

    # base_salary at age 30 in the default comp table is $52,200.
    base_salary = cfg.YOUR_COMPENSATION_BY_AGE[30]["base"]
    expected_benefit = base_salary * 0.10 * 0.15
    assert expected_benefit > 0
    assert (with_espp - base) == pytest.approx(expected_benefit)


def test_espp_zero_discount_is_noop():
    """Zero discount (the default profile) must not change any balance -- the fix
    is feature-OFF safe."""
    a = _accum_your_brokerage_after_one_year(espp_pct=0.10, espp_discount=0.0)
    b = _accum_your_brokerage_after_one_year(espp_pct=0.0, espp_discount=0.0)
    assert a == pytest.approx(b)


# ---------------------------------------------------------------------------
# (d) Partner-spending formula reconciliation (sim_runner legacy fallback)
# ---------------------------------------------------------------------------

def test_sim_runner_legacy_fallback_uses_partner_other_monthly():
    """When the granular SPEND_* source is unavailable, the sim_runner recompute
    must derive household expense totals from PARTNER_OTHER_MONTHLY (the engine's
    expense knob), NOT the stale PARTNER_MONTHLY_SPENDING savings knob."""
    import utils.sim_runner as sr

    saved = {
        "PARTNER_OTHER_MONTHLY": cfg.PARTNER_OTHER_MONTHLY,
        "PARTNER_MONTHLY_SPENDING": cfg.PARTNER_MONTHLY_SPENDING,
        "granular_nonhousing_annual": cfg.granular_nonhousing_annual,
        "CURRENT_ANNUAL_EXPENSES": getattr(cfg, "CURRENT_ANNUAL_EXPENSES", None),
        "BASE_RETIREMENT_EXPENSES_NO_MORTGAGE": getattr(
            cfg, "BASE_RETIREMENT_EXPENSES_NO_MORTGAGE", None
        ),
    }
    try:
        # Force the legacy fallback branch by removing the granular helper.
        del cfg.granular_nonhousing_annual
        # Diverge the two knobs so the wrong source would be detectable.
        cfg.PARTNER_OTHER_MONTHLY = 5_000   # expense knob (correct source)
        cfg.PARTNER_MONTHLY_SPENDING = 1_500  # stale savings knob (wrong source)

        sr._recompute_derived({})

        expected_current = (
            cfg.MORTGAGE_ANNUAL + cfg.UTILITIES_ANNUAL + cfg.YOUR_OTHER_ANNUAL
            + cfg.PARTNER_OTHER_MONTHLY * 12
        )
        expected_base_ret = (
            cfg.YOUR_OTHER_ANNUAL + cfg.UTILITIES_ANNUAL + cfg.PARTNER_OTHER_MONTHLY * 12
        )
        assert cfg.CURRENT_ANNUAL_EXPENSES == pytest.approx(expected_current)
        assert cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE == pytest.approx(expected_base_ret)
        # And it must NOT match the stale PARTNER_MONTHLY_SPENDING derivation.
        stale_current = (
            cfg.MORTGAGE_ANNUAL + cfg.UTILITIES_ANNUAL + cfg.YOUR_OTHER_ANNUAL
            + cfg.PARTNER_MONTHLY_SPENDING * 12
        )
        assert cfg.CURRENT_ANNUAL_EXPENSES != pytest.approx(stale_current)
    finally:
        cfg.granular_nonhousing_annual = saved.pop("granular_nonhousing_annual")
        for k, v in saved.items():
            if v is not None:
                setattr(cfg, k, v)
