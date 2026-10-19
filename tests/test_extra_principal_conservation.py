"""Extra mortgage principal must conserve dollars everywhere it is modeled.

Prepaying principal is a TRANSFER (savings -> home equity), net-worth-neutral on
the day it is made; it only pays off later through avoided interest. Every bug
these tests pin was a place where that transfer leaked:

  * ``max(0.0, cash - outlay)`` floors silently discarded whatever cash could
    not cover, CREATING ~$16.9k of net worth in the first prepayment year.
  * the house move read a STALE equity snapshot, DESTROYING the final year of
    extra principal (~$30k) -- charged to cash, never credited to sale proceeds.
  * the payoff year billed a full year of extra that the loan only partly
    absorbed, on both the chart and the engine side.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ui"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from components.net_worth_projection_chart import project_net_worth  # noqa: E402
from utils.derived import (advance_mortgage, advance_mortgage_with_extra,  # noqa: E402
                           mortgage_schedule)

BASE = {
    "YOUR_AGE": 32,
    "HOME_VALUE": 800_000,
    "MORTGAGE_BALANCE": 500_000,
    "MORTGAGE_RATE": 0.0625,
    "MORTGAGE_YEARS_REMAINING": 25,
    "YOUR_BROKERAGE": 400_000,
    "YOUR_CASH": 40_000,
    "TARGET_RETIREMENT_AGE": 55,
}
EXTRA = 30_000


def _total(proj, age):
    i = proj["ages"].index(age)
    return sum(proj["by_account"][label][i] for label in proj["by_account"])


class TestAdvanceMortgageWithExtra:
    def test_matches_scheduled_only_when_no_extra(self):
        """The new variant must not move the default path."""
        for bal in (500_000.0, 25_000.0, 1_200.0):
            expected = advance_mortgage(bal, 0.0625, 3_300.0, months=12)
            got, paid = advance_mortgage_with_extra(bal, 0.0625, 3_300.0, months=12)
            assert got == pytest.approx(expected)
            assert paid == 0.0

    def test_reports_full_extra_on_a_healthy_loan(self):
        _, paid = advance_mortgage_with_extra(500_000.0, 0.0625, 3_300.0,
                                              extra_annual=EXTRA)
        assert paid == pytest.approx(EXTRA)

    def test_payoff_year_only_charges_what_the_loan_absorbs(self):
        """Scheduled payments alone nearly retire this loan -- the extra must not
        be billed in full against principal that is already gone."""
        bal, paid = advance_mortgage_with_extra(20_000.0, 0.0625, 3_300.0,
                                                extra_annual=EXTRA)
        assert bal == 0.0
        assert paid < EXTRA
        # Cash paid can never exceed the principal that existed to retire.
        assert paid <= 20_000.0

    def test_never_charges_on_an_already_paid_loan(self):
        bal, paid = advance_mortgage_with_extra(0.0, 0.0625, 3_300.0,
                                                extra_annual=EXTRA)
        assert (bal, paid) == (0.0, 0.0)


class TestNetWorthProjectionConserves:
    def test_first_year_delta_is_only_avoided_interest(self):
        """A $30k prepayment moves cash into equity, so net worth in the
        following year may differ only by second-order amounts: avoided interest
        (a gain) net of the forgone return on the cash that left (a cost). Both
        are a few hundred dollars. The discarding floors used to INVENT $16.9k
        here -- 56% of the payment -- so a 10% band catches that decisively in
        either direction.
        """
        base = project_net_worth(BASE)
        xtra = project_net_worth({**BASE,
                                  "EXTRA_MORTGAGE_PAYMENT_ANNUAL": EXTRA,
                                  "EXTRA_MORTGAGE_PAYMENT_START_AGE": 32})
        age = BASE["YOUR_AGE"] + 1
        delta = _total(xtra, age) - _total(base, age)
        assert abs(delta) < 0.10 * EXTRA, (
            f"first-year net-worth delta {delta:,.0f} is too large to be "
            f"avoided interest -- the transfer is leaking"
        )

    def test_no_discontinuity_at_a_house_move(self):
        """The move converts equity to sale proceeds. Reading a stale equity
        snapshot destroyed the final year's prepayment; the delta must stay
        smooth across the move instead of stepping by ~one year's extra.
        """
        ov = {**BASE, "HOUSE_MOVE_ENABLED": True, "HOUSE_MOVE_AGE": 36,
              "NEW_HOME_VALUE": 1_000_000, "NEW_MORTGAGE_BALANCE": 800_000,
              "NEW_MORTGAGE_RATE": 0.065, "NEW_MORTGAGE_YEARS": 15}
        base = project_net_worth(ov)
        xtra = project_net_worth({**ov,
                                  "EXTRA_MORTGAGE_PAYMENT_ANNUAL": EXTRA,
                                  "EXTRA_MORTGAGE_PAYMENT_START_AGE": 32})
        d_before = _total(xtra, 35) - _total(base, 35)
        d_after = _total(xtra, 36) - _total(base, 36)
        assert abs(d_after - d_before) < 0.25 * EXTRA, (
            f"net worth jumped {d_after - d_before:,.0f} across the move"
        )

    def test_paying_extra_never_increases_liquid_assets(self):
        """Sanity floor: the money has to come from somewhere every single year."""
        base = project_net_worth(BASE)
        xtra = project_net_worth({**BASE,
                                  "EXTRA_MORTGAGE_PAYMENT_ANNUAL": EXTRA,
                                  "EXTRA_MORTGAGE_PAYMENT_START_AGE": 32})
        liquid = [l for l in base["by_account"] if l != "Home equity"]
        payoff = mortgage_schedule(
            {**BASE, "EXTRA_MORTGAGE_PAYMENT_ANNUAL": EXTRA,
             "EXTRA_MORTGAGE_PAYMENT_START_AGE": 32}, base["ages"])["payoff_age"]
        for i, age in enumerate(base["ages"]):
            if payoff is not None and age > payoff:
                break       # after payoff the prepayer rebuilds savings
            b = sum(base["by_account"][l][i] for l in liquid)
            x = sum(xtra["by_account"][l][i] for l in liquid)
            assert x <= b + 1.0, f"age {age}: prepaying grew liquid assets"


class TestEngineChargesOnlyAbsorbedPrincipal:
    """The engine's payoff year had the same overcharge as the chart."""

    def test_capped_loop_matches_scheduled_only_with_no_extra(self):
        from retirement_sim.account_simulation import AccountPortfolio
        p = AccountPortfolio()
        p.mortgage_balance = 400_000.0
        p._mortgage_pi = 2_800.0
        before = p.mortgage_balance
        end, applied = p._amortize_year_capped(0.0)
        assert applied == 0.0
        assert end < before
        assert p.mortgage_balance == before      # pure: no mutation

    def test_extra_capped_in_the_payoff_year(self):
        from retirement_sim.account_simulation import AccountPortfolio
        p = AccountPortfolio()
        p.mortgage_balance = 15_000.0
        p._mortgage_pi = 2_800.0
        end, applied = p._amortize_year_capped(EXTRA)
        assert end == 0.0
        assert applied < EXTRA
        assert applied <= 15_000.0
