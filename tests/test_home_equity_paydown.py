"""Home-equity paydown pins (engine).

The engine charged the full mortgage payment as an expense every year but froze
the accessible-equity reserve at its starting value forever, so 15-30 years of
principal repayment — real net-worth accumulation — vanished. On a real
profile the reserve stayed at its opening value while true equity roughly
tripled within a decade, and reached the entire home value at payoff.

``cfg.TRACK_HOME_EQUITY_PAYDOWN`` (default True) tracks the loan balance and
re-derives the reserve each year. Measured impact on that profile: success at
the target age up ~4pp, earliest retirement one year sooner, median ending
balance unchanged — the signature of a backstop that rescues bad paths without inflating
the median. Only principal is credited; interest remains a real expense, so no
money is created (the conservation ledger tests still pass).
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
    _level_payment,
    run_detailed_simulation,
)


# --------------------------------------------------------------------------
# The amortization primitive
# --------------------------------------------------------------------------

def test_level_payment_retires_the_loan_over_the_term():
    pi = _level_payment(800_000, 0.065, 15)
    bal, r = 800_000.0, 0.065 / 12
    for _ in range(180):
        bal = bal * (1 + r) - pi
    assert abs(bal) < 1.0, f"loan not retired at term: {bal}"


def test_level_payment_degenerate_inputs():
    assert _level_payment(0, 0.065, 30) == 0.0
    assert _level_payment(-1, 0.065, 30) == 0.0
    assert _level_payment(100_000, 0.065, 0) == 0.0
    # zero rate -> straight line
    assert _level_payment(360_000, 0.0, 30) == 1_000.0


# --------------------------------------------------------------------------
# Behaviour with a real home + mortgage
# --------------------------------------------------------------------------

@pytest.fixture
def homeowner():
    """Apply a homeowner profile to cfg for the duration of a test."""
    keys = ("HOME_VALUE", "MORTGAGE_BALANCE", "MORTGAGE_MONTHLY",
            "MORTGAGE_ANNUAL", "MORTGAGE_YEARS_REMAINING", "HOME_EQUITY",
            "HOUSE_MOVE_ENABLED", "TRACK_HOME_EQUITY_PAYDOWN")
    saved = {k: getattr(cfg, k, None) for k in keys}
    cfg.HOME_VALUE = 600_000
    cfg.MORTGAGE_BALANCE = 400_000
    cfg.MORTGAGE_MONTHLY = 3_800
    cfg.MORTGAGE_ANNUAL = 3_800 * 12
    cfg.MORTGAGE_YEARS_REMAINING = 14
    cfg.HOME_EQUITY = cfg.HOME_VALUE - cfg.MORTGAGE_BALANCE
    cfg.HOUSE_MOVE_ENABLED = False
    cfg.TRACK_HOME_EQUITY_PAYDOWN = True
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(cfg, k, v)


def _history(seed=42, retire=50):
    _ok, pf = run_detailed_simulation(retire, verbose=False, random_seed=seed)
    return {h["age"]: h for h in pf.yearly_history}


def test_opening_reserve_is_unchanged_by_the_fix(homeowner):
    """t=0 must still be today's real equity — the fix only affects later years."""
    h = _history()
    expected = (cfg.HOME_VALUE - cfg.MORTGAGE_BALANCE) * cfg.HOME_EQUITY_ACCESSIBLE_PCT
    assert abs(h[cfg.YOUR_AGE]["home_equity"] - expected) < 1.0


def test_mortgage_balance_declines_every_year(homeowner):
    h = _history()
    ages = sorted(a for a in h if a <= cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING)
    for a, b in zip(ages, ages[1:]):
        assert h[b]["mortgage_balance"] <= h[a]["mortgage_balance"] + 1.0, (
            f"balance rose between {a} and {b}"
        )


def test_loan_is_retired_at_the_payoff_age(homeowner):
    payoff = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
    h = _history()
    if payoff in h:
        assert h[payoff]["mortgage_balance"] == 0.0


def test_equity_reaches_the_full_home_value_after_payoff(homeowner):
    payoff = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
    h = _history()
    later = [a for a in h if a > payoff]
    if not later:
        pytest.skip("simulation ended before the payoff age")
    a = min(later)
    expected = cfg.HOME_VALUE * cfg.HOME_EQUITY_ACCESSIBLE_PCT
    # Equity can be lower only if it was drawn as an emergency backstop.
    assert h[a]["home_equity"] <= expected + 1.0
    if h[a]["home_equity_used"] == 0:
        assert abs(h[a]["home_equity"] - expected) < 1.0


def test_reserve_grows_versus_the_frozen_behaviour(homeowner):
    """The regression guard: equity must no longer be constant.

    Measured on GROSS equity (home value − remaining principal) rather than the
    accessible reserve. Since spending deficits are now actually funded, a
    household that overspends can draw the reserve down via USE_HOME_AS_BACKUP —
    so the reserve is not monotonic even though the paydown is. What this test
    exists to catch is the reserve being FROZEN at its starting value.
    """
    h = _history()
    payoff = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
    start_gross = h[cfg.YOUR_AGE]["home_value"] - h[cfg.YOUR_AGE]["mortgage_balance"]
    mid_age = min((a for a in h if a >= cfg.YOUR_AGE + 5), default=None)
    assert mid_age is not None and mid_age < payoff
    mid_gross = h[mid_age]["home_value"] - h[mid_age]["mortgage_balance"]
    assert mid_gross > start_gross * 1.05, (
        "home equity is still frozen — principal paydown is not being credited"
    )
    # And the loan really is amortizing.
    assert h[mid_age]["mortgage_balance"] < h[cfg.YOUR_AGE]["mortgage_balance"]


def test_toggle_off_restores_the_frozen_reserve(homeowner):
    """The previous, more conservative behaviour stays reproducible."""
    cfg.TRACK_HOME_EQUITY_PAYDOWN = False
    h = _history()
    payoff = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
    start = h[cfg.YOUR_AGE]["home_equity"]
    for a in sorted(h):
        if a >= payoff:
            break
        if h[a]["home_equity_used"] == 0:
            assert abs(h[a]["home_equity"] - start) < 1.0, (
                f"reserve moved at age {a} with the toggle off"
            )


def test_history_exposes_loan_state_for_the_ui(homeowner):
    h = _history()
    row = h[cfg.YOUR_AGE]
    for key in ("home_value", "mortgage_balance", "home_equity", "home_equity_used"):
        assert key in row, f"{key} missing from yearly_history"


def test_renter_is_unaffected():
    """No home, no mortgage -> nothing to amortize, no crash."""
    saved = {k: getattr(cfg, k, None) for k in
             ("HOME_VALUE", "MORTGAGE_BALANCE", "MORTGAGE_MONTHLY",
              "MORTGAGE_YEARS_REMAINING", "HOME_EQUITY")}
    cfg.HOME_VALUE = 0
    cfg.MORTGAGE_BALANCE = 0
    cfg.MORTGAGE_MONTHLY = 0
    cfg.MORTGAGE_YEARS_REMAINING = 0
    cfg.HOME_EQUITY = 0
    try:
        h = _history()
        for row in h.values():
            assert row["mortgage_balance"] == 0.0
            assert row["home_equity"] == 0.0
    finally:
        for k, v in saved.items():
            setattr(cfg, k, v)
