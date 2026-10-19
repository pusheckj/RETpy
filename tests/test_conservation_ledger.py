"""
Conservation pins for retirement-year money flow (findings #3 and #4).

These tests assert that dollars are neither created nor destroyed inside the
retirement engine:

#3 ROTH-CONVERSION TAX: perform_roth_conversion books the conversion income tax
   into the running tax totals; that tax must actually LEAVE the portfolio
   (standard "pay conversion tax from outside funds" assumption). Previously the
   total balance was unchanged across a conversion (phantom money).

#4 SURPLUS INCOME: when after-tax SS + RMD proceeds + 529 withdrawals exceed the
   year's spending, the excess is REINVESTED into taxable brokerage, not
   discarded via max(0, ...).

LEDGER IDENTITY (the master conservation check): over one retirement year, taken
BEFORE the end-of-year market return is applied,

    delta(total_balance) == income_in - spending_out - taxes_out

where
    income_in    = Social Security income (external cash into the household),
    spending_out = base expenses + LTC + car + college(529) + ACTUAL health
                   premium (the Pass-2 trued-up premium, captured via the
                   premium running totals), and
    taxes_out    = delta(total_taxes_paid)  (already includes penalties, NIIT,
                   SS tax, RMD tax, Roth-conversion tax and any gross-up tax).

RMDs and the Roth conversion are internal transfers (traditional -> cash /
traditional -> Roth) and so net to zero in the identity except for the tax they
generate, which is captured in taxes_out.
"""

import numpy as np
import pytest

from retirement_sim import config as cfg
from retirement_sim import account_simulation as sim
from retirement_sim.account_simulation import (
    AccountPortfolio,
    Account,
    AccountType,
    simulate_retirement_year,
)


@pytest.fixture(autouse=True)
def _restore_cfg_flags():
    """Snapshot and restore the global cfg toggles these tests mutate, so no
    flag state leaks into other test modules (these are module-level globals)."""
    saved = {
        "ENABLE_ROTH_CONVERSION": cfg.ENABLE_ROTH_CONVERSION,
        "INCLUDE_SOCIAL_SECURITY": cfg.INCLUDE_SOCIAL_SECURITY,
    }
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(cfg, k, v)


def _fresh_portfolio():
    """A large, multi-account portfolio that stays solvent for a full year so the
    conservation identity is exercised on a non-degenerate (non-depleted) path."""
    p = AccountPortfolio()
    p.add_account(Account("your_401k", AccountType.TRADITIONAL_401K, 2_000_000, "you"))
    p.add_account(Account("partner_401k", AccountType.TRADITIONAL_401K, 1_000_000, "partner"))
    p.add_account(Account("your_roth_ira", AccountType.ROTH_IRA, 500_000, "you"))
    p.add_account(Account("your_brokerage", AccountType.TAXABLE, 1_500_000, "you"))
    p.add_account(Account("your_cash", AccountType.CASH, 300_000, "you"))
    return p


def _run_year_reconciled(your_age, seed, expenses, retirement_age=60):
    """Run one retirement year and return (residual, info) for the ledger identity.

    ``residual`` is delta(total_balance, pre-returns) minus
    (income_in - spending_out - taxes_out); it must be ~0 if dollars are
    conserved. The pre-returns balance is captured by spying on
    ``_fund_net_expenses`` (which runs immediately before apply_returns).
    """
    np.random.seed(seed)
    p = _fresh_portfolio()

    state = {}
    orig_fund = sim._fund_net_expenses

    def fund_spy(portfolio, ya, adjusted_expenses, health_insurance, ltc_cost,
                 car_cost, ss_income, ss_tax, rmd_total, rmd_tax,
                 college_529_withdrawn, healthcare_factor,
                 partner_income=0.0, partner_magi=0.0, **kwargs):
        state["adjusted_expenses"] = adjusted_expenses
        state["ltc"] = ltc_cost
        state["car"] = car_cost
        state["ss"] = ss_income
        state["c529"] = college_529_withdrawn
        result = orig_fund(
            portfolio, ya, adjusted_expenses, health_insurance, ltc_cost,
            car_cost, ss_income, ss_tax, rmd_total, rmd_tax,
            college_529_withdrawn, healthcare_factor,
            partner_income=partner_income, partner_magi=partner_magi,
        )
        # Snapshot BEFORE the end-of-year market return is applied.
        state["bal_after_fund"] = portfolio.get_total_balance()
        return result

    sim._fund_net_expenses = fund_spy
    try:
        p.reset_yearly_income()
        taxes_start = p.total_taxes_paid
        aca_start = p.total_aca_premiums
        med_start = p.total_medicare_premiums
        bal_before = p.get_total_balance()
        ok = simulate_retirement_year(
            p, your_age, expenses, 0.0, 1.0, retirement_age, 1.0
        )
        taxes_out = p.total_taxes_paid - taxes_start
        health = (p.total_aca_premiums - aca_start) + (p.total_medicare_premiums - med_start)
    finally:
        sim._fund_net_expenses = orig_fund

    income_in = state["ss"]
    spending_out = (
        state["adjusted_expenses"] + state["ltc"] + state["car"]
        + state["c529"] + health
    )
    expected_delta = income_in - spending_out - taxes_out
    actual_delta = state["bal_after_fund"] - bal_before
    residual = actual_delta - expected_delta
    return residual, {"ok": ok, "portfolio": p, "taxes_out": taxes_out,
                      "income_in": income_in, "spending_out": spending_out}


# ---------------------------------------------------------------------------
# Master ledger conservation identity (covers #3 and #4 jointly)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("your_age,seed,expenses,note", [
    (62, 3, 60_000, "active Roth conversion + ACA premium (fix #3 path)"),
    (80, 5, 20_000, "high RMD + SS, low spend -> surplus reinvested (fix #4 path)"),
    (70, 9, 100_000, "high-spend pre-Medicare drawdown"),
    (67, 11, 90_000, "Medicare-age year"),
])
def test_retirement_year_conserves_dollars(your_age, seed, expenses, note):
    """A retirement year neither creates nor destroys money: the pre-returns
    balance change equals income_in - spending_out - taxes_out to the penny."""
    cfg.ENABLE_ROTH_CONVERSION = True
    cfg.INCLUDE_SOCIAL_SECURITY = True
    residual, info = _run_year_reconciled(your_age, seed, expenses)
    assert info["ok"], f"path should stay solvent for {note}"
    assert abs(residual) < 1e-6, (
        f"conservation broken for {note}: residual=${residual:,.4f} "
        f"(income_in=${info['income_in']:,.2f} "
        f"spending_out=${info['spending_out']:,.2f} "
        f"taxes_out=${info['taxes_out']:,.2f})"
    )


# ---------------------------------------------------------------------------
# #3 Roth-conversion tax must be funded by a REAL withdrawal
# ---------------------------------------------------------------------------

def test_roth_conversion_tax_leaves_the_portfolio():
    """perform_roth_conversion is a pure internal transfer (total unchanged), but
    once its tax is funded (as _fund_net_expenses now does) the total balance must
    drop by exactly the tax when funded from tax-free cash."""
    cfg.ENABLE_ROTH_CONVERSION = True
    np.random.seed(3)
    p = _fresh_portfolio()
    p.reset_yearly_income()
    p.update_ages(62)

    bal_before = p.get_total_balance()
    conv, tax = p.perform_roth_conversion(62)
    assert conv > 0 and tax > 0, "test needs an active conversion"

    # The conversion alone is an internal transfer: total balance is UNCHANGED
    # (this is exactly the phantom-money condition finding #3 flagged).
    assert abs(p.get_total_balance() - bal_before) < 1e-6

    # Funding the tax (what _fund_net_expenses now does) removes real dollars.
    # Here the withdrawal comes from tax-free cash, so the drop equals the tax
    # with no gross-up.
    p.withdraw_tax_efficient(tax, is_medical=False, your_age=62)
    assert abs((bal_before - p.get_total_balance()) - tax) < 1e-6


def test_roth_conversion_year_reduces_balance_by_the_tax():
    """End-to-end: a full retirement year with an active Roth conversion and no
    other tax reduces the pre-returns balance by exactly expenses + conversion
    tax (funded from cash). Guards against the phantom-money regression."""
    cfg.ENABLE_ROTH_CONVERSION = True
    cfg.INCLUDE_SOCIAL_SECURITY = True
    residual, info = _run_year_reconciled(62, 3, 60_000)
    p = info["portfolio"]
    assert p.total_roth_conversions > 0, "test needs an active conversion"
    assert p.roth_conversion_taxes > 0
    # The conversion tax is a real component of taxes_out this year.
    assert info["taxes_out"] >= p.roth_conversion_taxes - 1e-6
    assert abs(residual) < 1e-6


# ---------------------------------------------------------------------------
# #4 Surplus SS/RMD/529 income is reinvested into taxable, not discarded
# ---------------------------------------------------------------------------

def test_surplus_income_is_reinvested_not_destroyed():
    """When forced RMD + SS after-tax proceeds exceed spending, the surplus is
    deposited into taxable brokerage. The taxable balance ends the (pre-returns)
    year ABOVE its post-RMD level rather than the proceeds vanishing."""
    cfg.ENABLE_ROTH_CONVERSION = False  # isolate the surplus path
    cfg.INCLUDE_SOCIAL_SECURITY = True
    np.random.seed(5)
    p = _fresh_portfolio()

    state = {}
    orig_fund = sim._fund_net_expenses

    def fund_spy(portfolio, ya, adjusted_expenses, health_insurance, ltc_cost,
                 car_cost, ss_income, ss_tax, rmd_total, rmd_tax,
                 college_529_withdrawn, healthcare_factor,
                 partner_income=0.0, partner_magi=0.0, **kwargs):
        # Positive surplus means the clamp WOULD have destroyed money.
        total_expenses = adjusted_expenses + health_insurance + ltc_cost + car_cost
        covering = (ss_income - ss_tax) + (rmd_total - rmd_tax) + college_529_withdrawn
        state["surplus"] = covering - total_expenses
        state["brokerage_before"] = portfolio.accounts["your_brokerage"].balance
        result = orig_fund(
            portfolio, ya, adjusted_expenses, health_insurance, ltc_cost,
            car_cost, ss_income, ss_tax, rmd_total, rmd_tax,
            college_529_withdrawn, healthcare_factor,
            partner_income=partner_income, partner_magi=partner_magi,
        )
        state["brokerage_after"] = portfolio.accounts["your_brokerage"].balance
        return result

    sim._fund_net_expenses = fund_spy
    try:
        p.reset_yearly_income()
        # Age 80 -> large mandatory RMD, tiny spending -> guaranteed surplus.
        simulate_retirement_year(p, 80, 20_000, 0.0, 1.0, 60, 1.0)
    finally:
        sim._fund_net_expenses = orig_fund

    assert state["surplus"] > 0, "test needs a genuine surplus year"
    # The surplus was deposited into the taxable brokerage (fix #4), so the
    # brokerage grew by exactly the surplus during the fund step.
    delta_brokerage = state["brokerage_after"] - state["brokerage_before"]
    assert abs(delta_brokerage - state["surplus"]) < 1e-6, (
        f"surplus ${state['surplus']:,.2f} not reinvested; brokerage moved "
        f"${delta_brokerage:,.2f}"
    )
