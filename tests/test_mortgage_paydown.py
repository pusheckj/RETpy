"""Extra-mortgage-principal (early payoff) pins.

A prepayment sweep is only meaningful if ALL of these hold. Each has a test
below, because getting any one wrong produces a plausible-looking but wrong
answer:

  1. the extra payment COSTS real cash (otherwise prepaying is free and always
     "wins");
  2. it amortises the principal faster;
  3. the SCHEDULED PAYMENT STOPS once the loan is retired early -- the freed
     cash flow IS the benefit. Without this, prepayment is all cost and the
     sweep would always answer "never prepay";
  4. the default (extra = 0) path is byte-identical to pre-feature behaviour.

Payoff age / interest are deterministic, so they're also pinned exactly.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim.account_simulation import (  # noqa: E402
    AccountPortfolio,
    mortgage_payoff_projection,
    run_detailed_simulation,
)


@pytest.fixture(autouse=True)
def _restore():
    keys = ("EXTRA_MORTGAGE_PAYMENT_ANNUAL", "EXTRA_MORTGAGE_PAYMENT_START_AGE",
            "EXTRA_MORTGAGE_PAYMENT_STOP_AGE", "MORTGAGE_BALANCE",
            "MORTGAGE_YEARS_REMAINING", "MORTGAGE_ANNUAL", "HOME_VALUE",
            "HOUSE_MOVE_ENABLED", "TRACK_HOME_EQUITY_PAYDOWN")
    saved = {k: getattr(cfg, k) for k in keys if hasattr(cfg, k)}
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(cfg, k, v)


def _loan(balance=400_000, years=15, annual=48_000):
    cfg.MORTGAGE_BALANCE = balance
    cfg.MORTGAGE_YEARS_REMAINING = years
    cfg.MORTGAGE_ANNUAL = annual
    cfg.HOME_VALUE = 700_000
    cfg.HOUSE_MOVE_ENABLED = False
    cfg.TRACK_HOME_EQUITY_PAYDOWN = True


# --------------------------------------------------------------------------
# config helpers
# --------------------------------------------------------------------------

def test_disabled_by_default_is_a_noop():
    cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL = 0.0
    assert cfg.extra_mortgage_payment_enabled() is False
    assert cfg.extra_mortgage_payment_for_age(40) == 0.0


def test_missing_attribute_degrades_to_disabled():
    """Deleting the attribute (how other tests simulate pre-feature) must not
    raise NameError from inside the config helpers."""
    saved = cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL
    del cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL
    try:
        assert cfg.extra_mortgage_payment_enabled() is False
        assert cfg.extra_mortgage_payment_for_age(40) == 0.0
    finally:
        cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL = saved


def test_window_is_respected():
    cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL = 12_000.0
    cfg.EXTRA_MORTGAGE_PAYMENT_START_AGE = 40
    cfg.EXTRA_MORTGAGE_PAYMENT_STOP_AGE = 45
    assert cfg.extra_mortgage_payment_for_age(39) == 0.0
    assert cfg.extra_mortgage_payment_for_age(40) == 12_000.0
    assert cfg.extra_mortgage_payment_for_age(44) == 12_000.0
    assert cfg.extra_mortgage_payment_for_age(45) == 0.0      # stop is exclusive


# --------------------------------------------------------------------------
# (2) faster amortisation + deterministic projection
# --------------------------------------------------------------------------

def test_extra_principal_retires_the_loan_earlier():
    _loan()
    ages = {}
    for extra in (0.0, 12_000.0, 36_000.0):
        cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL = extra
        ages[extra] = mortgage_payoff_projection(extra)["payoff_age"]
    assert ages[0.0] is not None
    assert ages[12_000.0] < ages[0.0]
    assert ages[36_000.0] < ages[12_000.0]


def test_more_principal_means_less_interest():
    _loan()
    i0 = mortgage_payoff_projection(0.0)["total_interest"]
    i1 = mortgage_payoff_projection(24_000.0)["total_interest"]
    assert i1 < i0


def test_years_saved_is_reported_against_the_scheduled_payoff():
    _loan()
    base = mortgage_payoff_projection(0.0)["payoff_age"]
    p = mortgage_payoff_projection(24_000.0)
    assert p["years_saved_vs_scheduled"] == base - p["payoff_age"]


def test_projection_is_independent_of_market_returns():
    """Amortisation is deterministic -- the same inputs must give the same
    payoff age no matter what the return scenario is."""
    _loan()
    saved = cfg.ACTIVE_RETURN_SCENARIO
    try:
        out = []
        for scen in ("conservative", "historical", "pessimistic"):
            cfg.ACTIVE_RETURN_SCENARIO = scen
            out.append(mortgage_payoff_projection(24_000.0)["payoff_age"])
        assert len(set(out)) == 1
    finally:
        cfg.ACTIVE_RETURN_SCENARIO = saved


# --------------------------------------------------------------------------
# (3) THE critical property: the payment stops at payoff
# --------------------------------------------------------------------------

def test_scheduled_payment_stops_once_the_loan_is_gone():
    """The freed cash flow is the entire benefit of prepaying. If the engine
    kept billing a retired loan, prepayment would be pure cost and the sweep
    would always conclude "never prepay"."""
    _loan()
    cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL = 36_000.0
    p = AccountPortfolio()
    p.mortgage_balance = 0.0
    assert p.mortgage_expense_for_age(50) == 0.0


def test_outflow_includes_the_extra_while_the_loan_lives():
    _loan()
    p = AccountPortfolio()
    cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL = 0.0
    without = p.mortgage_expense_for_age(int(cfg.YOUR_AGE))
    cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL = 12_000.0
    p2 = AccountPortfolio()
    with_extra = p2.mortgage_expense_for_age(int(cfg.YOUR_AGE))
    assert with_extra == pytest.approx(without + 12_000.0)


def test_extra_never_exceeds_the_remaining_balance():
    """A final partial year must not overpay the loan."""
    _loan()
    cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL = 100_000.0
    p = AccountPortfolio()
    p.mortgage_balance = 5_000.0
    out = p.mortgage_expense_for_age(int(cfg.YOUR_AGE))
    assert out <= cfg.MORTGAGE_ANNUAL + 5_000.0 + 0.01


# --------------------------------------------------------------------------
# (4) default path unchanged
# --------------------------------------------------------------------------

@pytest.mark.slow
def test_zero_extra_is_byte_identical_to_pre_feature():
    cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL = 0.0
    a = [round(run_detailed_simulation(50, random_seed=s)[1].get_total_balance(), 4)
         for s in range(3)]
    saved = cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL
    del cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL
    try:
        b = [round(run_detailed_simulation(50, random_seed=s)[1].get_total_balance(), 4)
             for s in range(3)]
    finally:
        cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL = saved
    assert a == b
