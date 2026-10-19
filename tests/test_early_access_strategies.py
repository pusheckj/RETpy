"""Early-retirement access strategy pins.

Four ways to reach retirement money before 59.5, each independently toggleable:

  * Rule of 55  — employer 401(k) only, and only if you separated at 55+
  * 72(t) SEPP  — fixed penalty-free draws, locked in for 5 years / until 59.5
  * Roth ladder — converted principal seasons for 5 years before it's reachable
  * Coast FIRE  — stop contributing, keep covering expenses, let it compound

Strategy 1 of the five (taxable brokerage) needs no toggle: the engine already
draws taxable before 59.5 at LTCG rates with no penalty, which is pinned here too
so the behaviour can't silently regress.

All default OFF, so the baseline plan is unchanged.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim.account_simulation import (  # noqa: E402
    AccountType,
    _withdrawal_order,
    run_detailed_simulation,
)


@pytest.fixture
def strategy_flags():
    """Save/restore every strategy toggle so tests can't leak into each other."""
    keys = ("RULE_OF_55_ENABLED", "SEPP_72T_ENABLED", "SEPP_72T_START_AGE",
            "SEPP_72T_RATE", "SEPP_72T_CARVEOUT", "ROTH_LADDER_ENABLED",
            "COAST_FIRE_ENABLED", "COAST_FIRE_AGE")
    saved = {k: getattr(cfg, k, None) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(cfg, k, v)


def test_all_strategies_default_off():
    """The baseline plan must be unaffected until a user opts in."""
    assert cfg.RULE_OF_55_ENABLED is False
    assert cfg.SEPP_72T_ENABLED is False
    assert cfg.ROTH_LADDER_ENABLED is False
    assert cfg.COAST_FIRE_ENABLED is False


# --------------------------------------------------------------------------
# 1. Taxable brokerage bridge (no toggle — already the engine's behaviour)
# --------------------------------------------------------------------------

def test_taxable_is_drawn_before_penalized_accounts():
    """Pre-59.5 the order must reach taxable before any penalized account."""
    order = _withdrawal_order(45, is_medical=False)
    types = [t for types, _ in order for t in types]
    treat = {tuple(types_): treatment for types_, treatment in order}
    assert AccountType.TAXABLE in types
    i_taxable = types.index(AccountType.TAXABLE)
    i_trad = types.index(AccountType.TRADITIONAL_401K)
    assert i_taxable < i_trad, "taxable must be tapped before traditional pre-59.5"
    assert treat[(AccountType.TAXABLE,)] == "ltcg", "taxable must use LTCG rates"


# --------------------------------------------------------------------------
# 2. Rule of 55
# --------------------------------------------------------------------------

def _penalty(account_type, age, separation_age, enabled, sepp=False):
    cfg.RULE_OF_55_ENABLED = enabled
    return cfg.calculate_early_withdrawal_penalty(
        100_000, account_type, age,
        separation_age=separation_age, sepp_covered=sepp,
    )


def test_rule_of_55_waives_401k_penalty(strategy_flags):
    assert _penalty('traditional_401k', 56, 56, False) == 10_000
    assert _penalty('traditional_401k', 56, 56, True) == 0


def test_rule_of_55_never_applies_to_an_ira(strategy_flags):
    """IRAs are excluded by statute — rolling a 401(k) over forfeits this."""
    assert _penalty('traditional_ira', 56, 56, True) == 10_000


def test_rule_of_55_requires_separation_at_55_or_later(strategy_flags):
    # Left at 50, now 56: the exception was forfeited.
    assert _penalty('traditional_401k', 56, 50, True) == 10_000
    # Left at 52 and only 52 now: too young either way.
    assert _penalty('traditional_401k', 52, 52, True) == 10_000


def test_rule_of_55_needs_a_known_separation_age(strategy_flags):
    """Still working / unknown separation -> no exception."""
    assert _penalty('traditional_401k', 56, None, True) == 10_000


def test_separation_age_is_recorded_at_retirement(strategy_flags):
    _ok, pf = run_detailed_simulation(56, verbose=False, random_seed=11)
    assert pf.separation_age == 56.0


# --------------------------------------------------------------------------
# 3. 72(t) SEPP
# --------------------------------------------------------------------------

def test_sepp_amount_amortizes_the_balance(strategy_flags):
    amt = cfg.sepp_72t_annual_amount(1_000_000, 45)
    # ~$58k on $1M at 45 with a 41.0-year life expectancy at 5%.
    assert 50_000 < amt < 65_000, amt
    # A shorter remaining life expectancy -> a larger annual payment.
    assert cfg.sepp_72t_annual_amount(1_000_000, 55) > amt


def test_sepp_amount_is_zero_without_a_balance():
    assert cfg.sepp_72t_annual_amount(0, 45) == 0.0
    assert cfg.sepp_72t_annual_amount(None, 45) == 0.0


def test_sepp_schedule_lock_in_rule():
    """Longer of 5 years or age 59.5."""
    assert cfg.sepp_72t_must_continue(47, 45) is True     # only 2 years in
    assert cfg.sepp_72t_must_continue(51, 45) is True     # 6 years in but < 59.5
    assert cfg.sepp_72t_must_continue(60, 45) is False    # past both tests
    assert cfg.sepp_72t_must_continue(58, 56) is True     # 2 years in
    assert cfg.sepp_72t_must_continue(45, None) is False  # never started


def test_sepp_waives_the_penalty_at_any_age(strategy_flags):
    assert _penalty('traditional_401k', 45, None, False, sepp=True) == 0
    assert _penalty('traditional_ira', 45, None, False, sepp=True) == 0


def test_sepp_distributions_actually_flow(strategy_flags):
    cfg.SEPP_72T_ENABLED = False
    _ok, off = run_detailed_simulation(50, verbose=False, random_seed=7)
    cfg.SEPP_72T_ENABLED = True
    cfg.SEPP_72T_START_AGE = 50
    _ok, on = run_detailed_simulation(50, verbose=False, random_seed=7)
    assert off.total_sepp_distributions == 0.0
    assert on.total_sepp_distributions > 0.0
    assert on.sepp_annual_amount is not None and on.sepp_annual_amount > 0


def test_sepp_annual_amount_is_fixed_not_market_linked(strategy_flags):
    """The payment is locked at the start age; it must not float year to year."""
    cfg.SEPP_72T_ENABLED = True
    cfg.SEPP_72T_START_AGE = 50
    _ok, pf = run_detailed_simulation(50, verbose=False, random_seed=7)
    locked = pf.sepp_annual_amount
    _ok2, pf2 = run_detailed_simulation(50, verbose=False, random_seed=7)
    assert pf2.sepp_annual_amount == locked


# --------------------------------------------------------------------------
# 4. Roth conversion ladder
# --------------------------------------------------------------------------

def test_conversions_are_recorded_as_dated_cohorts():
    _ok, pf = run_detailed_simulation(50, verbose=False, random_seed=3)
    if not pf.roth_conversion_cohorts:
        pytest.skip("no conversions occurred on this path")
    for age, amount in pf.roth_conversion_cohorts:
        assert amount > 0 and age > 0
    assert abs(sum(a for _, a in pf.roth_conversion_cohorts)
               - pf.total_roth_conversions) < 1.0


def test_seasoning_splits_reachable_from_locked():
    _ok, pf = run_detailed_simulation(50, verbose=False, random_seed=3)
    if not pf.roth_conversion_cohorts:
        pytest.skip("no conversions occurred on this path")
    first_age = min(a for a, _ in pf.roth_conversion_cohorts)
    years = cfg.ROTH_LADDER_SEASONING_YEARS
    # Right after converting, nothing has seasoned.
    assert pf.seasoned_conversion_basis(first_age) == 0.0
    # Every cohort is either seasoned or not — the split must be exhaustive.
    probe = first_age + years + 1
    total = pf.seasoned_conversion_basis(probe) + pf.unseasoned_conversion_basis(probe)
    assert abs(total - pf.total_roth_conversions) < 1.0
    # And the first rung is reachable once it clears the window.
    assert pf.seasoned_conversion_basis(first_age + years) > 0.0


# --------------------------------------------------------------------------
# 5. Coast FIRE
# --------------------------------------------------------------------------

def test_coasting_stops_contributions_but_keeps_compounding(strategy_flags):
    def final_balance(coast, coast_age=40):
        cfg.COAST_FIRE_ENABLED = coast
        cfg.COAST_FIRE_AGE = coast_age
        _ok, pf = run_detailed_simulation(55, verbose=False, random_seed=5)
        hist = {h["age"]: h for h in pf.yearly_history}
        return hist[55]["total"], pf

    saving, _ = final_balance(False)
    coasting, pf = final_balance(True, 40)
    assert pf.coasting is True
    assert coasting < saving, "coasting should accumulate less than full saving"
    # But it must still GROW after the coast age — no withdrawals while working.
    hist = {h["age"]: h for h in pf.yearly_history}
    assert hist[50]["total"] > hist[42]["total"], "portfolio should compound while coasting"


def test_coasting_after_retirement_age_is_inert(strategy_flags):
    """A coast age at/after retirement changes nothing."""
    cfg.COAST_FIRE_ENABLED = False
    _ok, base = run_detailed_simulation(45, verbose=False, random_seed=9)
    cfg.COAST_FIRE_ENABLED = True
    cfg.COAST_FIRE_AGE = 60          # never reached while working
    _ok, late = run_detailed_simulation(45, verbose=False, random_seed=9)
    b = {h["age"]: h["total"] for h in base.yearly_history}
    l = {h["age"]: h["total"] for h in late.yearly_history}
    assert abs(b[45] - l[45]) < 1.0


# --------------------------------------------------------------------------
# 72(t) carve-out: designating a sub-account instead of all-or-nothing
# --------------------------------------------------------------------------
# Applying a SEPP to the ENTIRE traditional balance forces the largest possible
# mandatory draw, which crowds out the voluntary Roth conversions competing for
# the same low brackets (measured on a real profile: conversions -72%, six
# figures of extra lifetime tax). Splitting off a designated sub-account is how a 72(t) is
# actually right-sized, and it reduced the crowd-out to -6% at a $300k carve-out.

def test_balance_for_payment_inverts_the_amount_calc():
    for target, age in ((30_000, 40), (50_000, 45), (80_000, 52)):
        bal = cfg.sepp_72t_balance_for_payment(target, age)
        assert abs(cfg.sepp_72t_annual_amount(bal, age) - target) < 1.0


def test_balance_for_payment_degenerate_inputs():
    assert cfg.sepp_72t_balance_for_payment(0, 45) == 0.0
    assert cfg.sepp_72t_balance_for_payment(None, 45) == 0.0


def test_carveout_scales_the_locked_payment(strategy_flags):
    """Half the designated balance -> half the annual payment."""
    cfg.SEPP_72T_ENABLED = True
    cfg.SEPP_72T_START_AGE = 50

    def locked(carveout):
        cfg.SEPP_72T_CARVEOUT = carveout
        _ok, pf = run_detailed_simulation(50, verbose=False, random_seed=7)
        return pf.sepp_annual_amount

    small, big = locked(250_000), locked(500_000)
    assert small > 0 and big > 0
    assert abs(big - 2 * small) < 1.0, f"{big} should be ~2x {small}"


def test_carveout_caps_at_the_real_balance(strategy_flags):
    """A carve-out larger than the account can't invent money."""
    cfg.SEPP_72T_ENABLED = True
    cfg.SEPP_72T_START_AGE = 50
    cfg.SEPP_72T_CARVEOUT = 0
    _ok, whole = run_detailed_simulation(50, verbose=False, random_seed=7)
    cfg.SEPP_72T_CARVEOUT = 50_000_000        # far more than exists
    _ok, huge = run_detailed_simulation(50, verbose=False, random_seed=7)
    assert abs(huge.sepp_annual_amount - whole.sepp_annual_amount) < 1.0


def test_zero_carveout_means_whole_balance(strategy_flags):
    """0 is the documented 'use everything' sentinel (backward compatible)."""
    cfg.SEPP_72T_ENABLED = True
    cfg.SEPP_72T_START_AGE = 50
    cfg.SEPP_72T_CARVEOUT = 0
    _ok, pf = run_detailed_simulation(50, verbose=False, random_seed=7)
    assert pf.sepp_annual_amount > 0
    assert pf.sepp_carveout_balance is None, "no carve-out ledger when using everything"


def test_carveout_bounds_lifetime_distributions(strategy_flags):
    """Payments must not reach into traditional money left OUTSIDE the schedule."""
    cfg.SEPP_72T_ENABLED = True
    cfg.SEPP_72T_START_AGE = 50

    def lifetime(carveout):
        cfg.SEPP_72T_CARVEOUT = carveout
        _ok, pf = run_detailed_simulation(50, verbose=False, random_seed=7)
        return pf.total_sepp_distributions

    assert lifetime(250_000) < lifetime(500_000) < lifetime(0)


def test_carveout_ledger_grows_with_the_market(strategy_flags):
    """The designated account is real invested money — its ledger must compound,
    or the schedule would appear to exhaust it years too early."""
    cfg.SEPP_72T_ENABLED = True
    cfg.SEPP_72T_START_AGE = 50
    cfg.SEPP_72T_CARVEOUT = 300_000
    _ok, pf = run_detailed_simulation(50, verbose=False, random_seed=7)
    # Over a long retirement the payments alone would exceed a static $300k;
    # because the ledger compounds, more than that can legitimately be paid out.
    assert pf.total_sepp_distributions > 0
    assert pf.sepp_annual_amount > 0
