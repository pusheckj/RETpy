"""
Tests for the ACCUMULATION savings-sweep behavior in
``simulate_accumulation_year``.

In the default Auto-allocate mode every working year now invests ALL un-spent
after-tax income into the taxable brokerage:

    residual = household_after_tax - living_expenses - after_tax_electives

where ``living_expenses`` comes from ``cfg.calculate_annual_expenses`` and
``after_tax_electives`` are the take-home-funded electives (backdoor Roth +
529s + partner direct Roth). The flat *_BROKERAGE_CONTRIBUTION knobs act only as
a FLOOR. In Manual mode the legacy flat-override behavior is preserved exactly.
"""

import pytest
from unittest.mock import patch

from retirement_sim import config as cfg
from retirement_sim.account_simulation import (
    create_initial_portfolio,
    simulate_accumulation_year,
    working_year_cashflow,
)


def _added(portfolio, before, name):
    return portfolio.accounts[name].balance - before[name]


def _snapshot(portfolio):
    return {name: acct.balance for name, acct in portfolio.accounts.items()}


class TestAutoSweepGrowsBrokerageByResidual:
    """(a) income > living + electives -> full residual lands in brokerage."""

    def test_full_residual_swept_into_brokerage_with_zero_return(self):
        age = cfg.YOUR_AGE
        # Isolate the your-side sweep: no partner income, no electives, no
        # per-person brokerage floors, and no children (so childcare = 0). Give
        # a high after-tax income so a clear surplus exists over living.
        big_comp = dict(cfg.YOUR_COMPENSATION_BY_AGE[age])
        big_comp["after_tax"] = 200_000
        table = dict(cfg.YOUR_COMPENSATION_BY_AGE)
        table[age] = big_comp
        overrides = {
            "SAVINGS_MODE": "Auto-allocate (recommended)",
            "YOUR_COMPENSATION_BY_AGE": table,
            "PARTNER_SALARY": 0.0,
            "PARTNER_401K_CONTRIBUTION": 0.0,
            "PARTNER_ROTH_CONTRIBUTION": 0.0,
            "PARTNER_BROKERAGE_CONTRIBUTION": 0,
            "YOUR_BACKDOOR_ROTH": 0,
            "YOUR_HSA_CONTRIBUTION": 0,
            "YOUR_BROKERAGE_CONTRIBUTION": 0,
            "CHILDREN": [],                   # no kids -> no 529, no childcare
            "HOUSE_MOVE_ENABLED": False,
            "CAR_ONETIME_ENABLED": False,
            "CAR_RECURRING_ENABLED": False,
        }
        with patch.multiple(cfg, **overrides):
            your_after_tax = float(cfg.YOUR_COMPENSATION_BY_AGE[age]["after_tax"])
            living = cfg.calculate_annual_expenses(age, 1.0, childcare_factor=1.0)
            expected_residual = max(0.0, your_after_tax - living)  # no electives
            assert expected_residual > 0  # sanity: this profile has a surplus

            portfolio = create_initial_portfolio()
            before = _snapshot(portfolio)
            simulate_accumulation_year(portfolio, your_age=age, annual_return=0.0)

            added_brokerage = _added(portfolio, before, "your_brokerage")
            added_partner_brokerage = _added(portfolio, before, "partner_brokerage")

        # Partner has no income/capacity -> everything routes to your_brokerage.
        assert added_partner_brokerage == pytest.approx(0.0)
        assert added_brokerage == pytest.approx(expected_residual)
        assert portfolio.overspent_years == 0


class TestAutoSweepOverspend:
    """(b) residual <= 0 invests 0, flags the year, AND funds the shortfall.

    The deficit used to be floored at zero and silently discarded — the household
    spent money that was never funded, inflating both the ending balance and the
    reported success rate. It is now drawn from the portfolio, so an overspent
    year still invests nothing but the portfolio SHRINKS by the shortfall.
    """

    def test_overspend_invests_zero_and_sets_flag(self):
        age = cfg.YOUR_AGE
        # Force living >> income by inflating the granular household base while
        # zeroing income sources. No brokerage floors so nothing is invested.
        tiny_comp = dict(cfg.YOUR_COMPENSATION_BY_AGE[age])
        tiny_comp["after_tax"] = 1_000
        table = dict(cfg.YOUR_COMPENSATION_BY_AGE)
        table[age] = tiny_comp
        overrides = {
            "SAVINGS_MODE": "Auto-allocate (recommended)",
            "YOUR_COMPENSATION_BY_AGE": table,
            "PARTNER_SALARY": 0.0,
            "PARTNER_401K_CONTRIBUTION": 0.0,
            "PARTNER_ROTH_CONTRIBUTION": 0.0,
            "PARTNER_BROKERAGE_CONTRIBUTION": 0,
            "YOUR_BACKDOOR_ROTH": 0,
            "YOUR_HSA_CONTRIBUTION": 0,
            "YOUR_BROKERAGE_CONTRIBUTION": 0,
            # Blow up living expenses well past the $1,000 after-tax income.
            "SPEND_FOOD_MONTHLY": 20_000,
            "SPEND_UTILITIES_MONTHLY": 0,
            "SPEND_TRANSPORT_MONTHLY": 0,
            "SPEND_HEALTH_MONTHLY": 0,
            "SPEND_DISCRETIONARY_MONTHLY": 0,
            "SPEND_OTHER_MONTHLY": 0,
            "HOUSE_MOVE_ENABLED": False,
            "CAR_ONETIME_ENABLED": False,
            "CAR_RECURRING_ENABLED": False,
        }
        with patch.multiple(cfg, **overrides):
            portfolio = create_initial_portfolio()
            before = _snapshot(portfolio)
            simulate_accumulation_year(portfolio, your_age=age, annual_return=0.0)

            added_brokerage = _added(portfolio, before, "your_brokerage")
            added_partner_brokerage = _added(portfolio, before, "partner_brokerage")

        # Nothing is INVESTED on an overspent year. The balances can go DOWN,
        # because the shortfall is now funded by a withdrawal (brokerage is the
        # first non-cash source), so assert "did not grow" rather than "== 0".
        assert added_brokerage <= 0.0
        assert added_partner_brokerage <= 0.0
        assert portfolio.overspent_years == 1
        # The shortfall must actually be funded, not discarded: total portfolio
        # dollars have to fall (previously this year left the balance untouched).
        after_total = sum(a.balance for a in portfolio.accounts.values())
        before_total = sum(before[name] for name in before)
        assert after_total < before_total, (
            "an overspent year left the portfolio untouched — the deficit was "
            "discarded instead of funded"
        )


class TestFullProfileNoLeak:
    """(c) A full saved profile no longer leaks after-tax income.

    Uses the committed sample household (tests/fixtures/sample_household.json):
    married, two kids, comp table through the retirement age, mega-backdoor,
    ESPP and backdoor Roth all on.

    Each working year the total money that lands in the portfolio (contributions
    net of the employer match, which is not funded from take-home, and net of
    lifecycle lump sums) must equal household after-tax income minus household
    living expenses -- i.e. nothing leaks away.
    """

    def _ui_dir(self):
        import os

        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui"
        )

    def _load_profile_overrides(self):
        from tests.conftest import load_sample_household

        return load_sample_household()

    def test_no_leak_each_working_year(self):
        import sys

        ui_dir = self._ui_dir()
        if ui_dir not in sys.path:
            sys.path.insert(0, ui_dir)
        overrides = self._load_profile_overrides()
        from utils.sim_runner import _apply_overrides, _restore_overrides, build_config_overrides  # type: ignore

        # Disable lifecycle lump sums so the accounting is a clean
        # income - living identity (house move / car are separate outflows that
        # legitimately reduce the portfolio and are NOT living expenses).
        overrides = {
            **overrides,
            "HOUSE_MOVE_ENABLED": False,
            "CAR_ONETIME_ENABLED": False,
            "CAR_RECURRING_ENABLED": False,
        }
        original = _apply_overrides(build_config_overrides(overrides))
        try:
            retire_age = int(overrides.get("TARGET_RETIREMENT_AGE", cfg.YOUR_AGE + 7))
            # Accounts funded from AFTER-TAX take-home income. Their combined
            # growth each year must equal household_after_tax - living (the
            # residual sweep + the after-tax electives it nets against). Pre-tax
            # and employer money (401k employee + match, HSA + match) funds the
            # retirement accounts and is intentionally excluded from this
            # income identity.
            after_tax_funded = (
                "your_brokerage",
                "partner_brokerage",
                "your_roth_ira",
                "partner_roth_ira",
                "child1_529",
                "child2_529",
            )
            for age in range(cfg.YOUR_AGE, retire_age):
                portfolio = create_initial_portfolio()
                before = _snapshot(portfolio)
                simulate_accumulation_year(portfolio, your_age=age, annual_return=0.0)
                contributed_from_income = sum(
                    _added(portfolio, before, name) for name in after_tax_funded
                )

                # Take-home now comes from ONE function (real tax rules,
                # replacing the old comp after_tax + flat partner rate); the
                # sweep must conserve exactly what it reports.
                cf = working_year_cashflow(age)
                household_after_tax = cf["your_take_home"] + cf["partner_take_home"]
                living = cfg.calculate_annual_expenses(age, 1.0, childcare_factor=1.0)

                expected = max(0.0, household_after_tax - living)
                assert contributed_from_income == pytest.approx(expected, rel=1e-6), (
                    f"age {age}: leaked "
                    f"{expected - contributed_from_income:.0f} "
                    f"(expected {expected:.0f}, got {contributed_from_income:.0f})"
                )
        finally:
            _restore_overrides(original)


class TestManualModePreservesFlatBehavior:
    """(d) Manual mode keeps the legacy flat-override behavior exactly."""

    def test_manual_mode_uses_flat_overrides(self):
        age = cfg.YOUR_AGE
        overrides = {
            "SAVINGS_MODE": "Manual",
            "YOUR_BROKERAGE_CONTRIBUTION": 12_345,
            "PARTNER_BROKERAGE_CONTRIBUTION": 6_789,
            "YOUR_BACKDOOR_ROTH": 0,
            "PARTNER_ROTH_CONTRIBUTION": 0,
            "HOUSE_MOVE_ENABLED": False,
            "CAR_ONETIME_ENABLED": False,
            "CAR_RECURRING_ENABLED": False,
        }
        with patch.multiple(cfg, **overrides):
            portfolio = create_initial_portfolio()
            before = _snapshot(portfolio)
            simulate_accumulation_year(portfolio, your_age=age, annual_return=0.0)

            added_brokerage = _added(portfolio, before, "your_brokerage")
            added_partner_brokerage = _added(portfolio, before, "partner_brokerage")

        # Flat overrides are honored verbatim (they are within income here), and
        # no residual sweep occurs, so brokerage grows by exactly the overrides.
        assert added_brokerage == pytest.approx(12_345)
        assert added_partner_brokerage == pytest.approx(6_789)
        # Manual mode never touches the overspent counter.
        assert portfolio.overspent_years == 0


# ==========================================================================
# A brokerage-contribution FLOOR above the year's surplus must be FUNDED
# ==========================================================================
# The AUTO sweep does `total_brokerage = max(residual, floors)` and then
# contribute()s that amount. Before this fix there was no offsetting
# withdrawal, so any floor exceeding income CREATED money from nothing.
#
# Distinct from the raw_residual < 0 deficit case already covered above: here
# the residual can be comfortably POSITIVE and still short of the floor.
# Measured on a real profile, a floor about 9% above the year's surplus
# inflated success by ~7pp.

class TestFloorAboveSurplusIsFunded:
    # These tests rewrite cfg globals (comp table, savings mode, contribution
    # floors...). Without restoring them the mutations leak into every later
    # test file -- which is exactly what happened on the first run here: four
    # unrelated tests in other modules started failing while still passing in
    # isolation.
    _KEYS = ("YOUR_COMPENSATION_BY_AGE", "PARTNER_SALARY", "YOUR_401K_CONTRIBUTION",
             "YOUR_401K_MATCH_PCT", "YOUR_HSA_CONTRIBUTION", "YOUR_BACKDOOR_ROTH",
             "PARTNER_401K_CONTRIBUTION", "PARTNER_ROTH_CONTRIBUTION",
             "YOUR_AFTER_TAX_401K_PCT", "CHILDREN",
             "SAVINGS_MODE", "HOUSE_MOVE_ENABLED", "CAR_ONETIME_ENABLED",
             "CAR_RECURRING_ENABLED", "YOUR_BROKERAGE_CONTRIBUTION",
             "PARTNER_BROKERAGE_CONTRIBUTION")

    @pytest.fixture(autouse=True)
    def _isolate_cfg(self):
        saved = {k: getattr(cfg, k) for k in self._KEYS if hasattr(cfg, k)}
        try:
            yield
        finally:
            for k, v in saved.items():
                setattr(cfg, k, v)

    def _one_year(self, floor, brokerage_start=0.0):
        import retirement_sim.account_simulation as A
        cfg.YOUR_COMPENSATION_BY_AGE = {40: {
            "base": 200_000, "bonus": 0, "rsu_gross": 0, "total_comp": 200_000,
            "after_tax": 150_000, "saved": 0.0}}
        cfg.PARTNER_SALARY = 0.0
        for k in ("YOUR_401K_CONTRIBUTION", "YOUR_401K_MATCH_PCT",
                  "YOUR_HSA_CONTRIBUTION", "YOUR_BACKDOOR_ROTH",
                  "PARTNER_401K_CONTRIBUTION", "PARTNER_ROTH_CONTRIBUTION",
                  "YOUR_AFTER_TAX_401K_PCT"):
            setattr(cfg, k, 0.0)
        cfg.CHILDREN = [{**c, "college_funding_pct": 0.0} for c in cfg.CHILDREN]  # no 529
        cfg.SAVINGS_MODE = "Auto-allocate (recommended)"
        cfg.HOUSE_MOVE_ENABLED = False
        cfg.CAR_ONETIME_ENABLED = False
        cfg.CAR_RECURRING_ENABLED = False
        cfg.YOUR_BROKERAGE_CONTRIBUTION = floor
        cfg.PARTNER_BROKERAGE_CONTRIBUTION = 0

        p = A.AccountPortfolio()
        p.accounts = {}
        p.add_account(A.Account("your_brokerage", A.AccountType.TAXABLE,
                                brokerage_start, "you"))
        p.add_account(A.Account("partner_brokerage", A.AccountType.TAXABLE, 0.0, "partner"))
        p.add_account(A.Account("your_401k", A.AccountType.TRADITIONAL_401K,
                                2_000_000.0, "you"))
        before = p.get_total_balance()
        A.simulate_accumulation_year(p, your_age=40, annual_return=0.0)
        return before, p.get_total_balance()

    def test_floor_above_surplus_cannot_create_money(self):
        """The headline invariant: a huge floor must not grow total wealth by
        more than the year's real surplus."""
        _b0, a0 = self._one_year(0)
        _b1, a1 = self._one_year(400_000)
        assert a1 <= a0 + 1.0, (
            f"a $400k floor created money: total {a1:,.0f} vs {a0:,.0f} without"
        )

    def test_growth_is_capped_by_real_income(self):
        before, after = self._one_year(400_000)
        living = cfg.calculate_annual_expenses(40, 1.0, childcare_factor=1.0)
        surplus = 150_000 - living
        assert (after - before) <= surplus + 1.0

    def test_floor_below_surplus_is_unaffected(self):
        """The common case must be untouched: when income covers the floor,
        the sweep banks the full residual exactly as before."""
        before, after = self._one_year(10_000)
        living = cfg.calculate_annual_expenses(40, 1.0, childcare_factor=1.0)
        surplus = 150_000 - living
        assert (after - before) == pytest.approx(surplus, rel=1e-6)

    def test_a_real_withdrawal_is_issued_for_the_gap(self):
        """Not just conserved on net -- an actual funding withdrawal must occur."""
        import retirement_sim.account_simulation as A
        calls = []
        real = A.AccountPortfolio.withdraw_tax_efficient

        def spy(self, amount, **kw):
            calls.append(amount)
            return real(self, amount, **kw)

        A.AccountPortfolio.withdraw_tax_efficient = spy
        try:
            self._one_year(400_000)
        finally:
            A.AccountPortfolio.withdraw_tax_efficient = real
        assert calls, "no withdrawal was issued to fund the floor excess"
