"""Derived-state / return-scenario wiring pins (conservation findings #1, #2, #5, #12).

These findings are all the same class: the UI writes a *raw* override onto
``cfg`` but the engine reads a *derived* constant that ``_recompute_derived``
never rebuilt, so the control was inert (or, for #1, actively wrong — a stock
knob without its bond partner made stock+bond sum to 1.2 = 120% invested).

Each test asserts one of:
  * the derived value now recomputes from the raw override, AND
  * ``_restore_overrides`` reverts it (no cross-run cfg state leak), AND/OR
  * the control now MOVES a seeded Monte Carlo run on the packaged profile.

sim_runner imports ``from retirement_sim import config`` and
``from utils.config_builder import build_config_overrides``. ``retirement_sim``
is importable from ROOT; ``utils`` lives under ``ui/``. Add both to sys.path.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import pytest

from retirement_sim import config as cfg
from utils import sim_runner as sr


# All derived keys the four fixes now recompute — used to assert clean restore.
_NEW_DERIVED_KEYS = [
    "BOND_ALLOCATION", "GLIDE_PATH_START_BOND_PCT", "GLIDE_PATH_END_BOND_PCT",
    "EXPECTED_STOCK_RETURN", "EXPECTED_BOND_RETURN",
    "STOCK_VOLATILITY", "BOND_VOLATILITY",
    "FIRST_CHILD_ANNUAL_COST", "BOTH_CHILDREN_ANNUAL_COST",
    "ACA_BASE_ANNUAL_PREMIUM", "MEDICARE_ANNUAL_PREMIUM",
]


def _apply_and_restore(overrides):
    """Apply overrides, snapshot pristine defaults, and return (post, restored, defaults)."""
    defaults = {k: getattr(cfg, k) for k in _NEW_DERIVED_KEYS}
    original = sr._apply_overrides(overrides)
    post = {k: getattr(cfg, k) for k in _NEW_DERIVED_KEYS}
    sr._restore_overrides(original)
    restored = {k: getattr(cfg, k) for k in _NEW_DERIVED_KEYS}
    return post, restored, defaults


# =============================================================================
# Finding #1 — PHANTOM LEVERAGE: bond partners derived from stock knobs.
# =============================================================================

class TestBondPartnerDerivation:
    def test_bond_allocation_is_one_minus_stock(self):
        post, restored, defaults = _apply_and_restore({"STOCK_ALLOCATION": 1.0})
        # STOCK=1.0 -> BOND=0.0 (was silently left at default 0.20 = 120% invested).
        assert post["BOND_ALLOCATION"] == pytest.approx(0.0)
        # No cross-run leak.
        assert restored["BOND_ALLOCATION"] == defaults["BOND_ALLOCATION"]

    def test_glide_path_bond_partners_derived(self):
        post, restored, defaults = _apply_and_restore({
            "GLIDE_PATH_START_STOCK_PCT": 1.0,
            "GLIDE_PATH_END_STOCK_PCT": 0.7,
        })
        assert post["GLIDE_PATH_START_BOND_PCT"] == pytest.approx(0.0)
        assert post["GLIDE_PATH_END_BOND_PCT"] == pytest.approx(0.3)
        assert restored["GLIDE_PATH_START_BOND_PCT"] == defaults["GLIDE_PATH_START_BOND_PCT"]
        assert restored["GLIDE_PATH_END_BOND_PCT"] == defaults["GLIDE_PATH_END_BOND_PCT"]

    def test_stock_plus_bond_always_sums_to_one(self):
        # Sweep several stock knobs; the sleeves must never sum to >1 (no leverage)
        # and never <1 with a valid stock weight (fully invested).
        for stock in (0.0, 0.35, 0.6, 0.8, 1.0):
            post, _, _ = _apply_and_restore({"STOCK_ALLOCATION": stock})
            assert post["BOND_ALLOCATION"] + stock == pytest.approx(1.0)

    def test_stock_knob_clamps_to_unit_interval(self):
        post, _, _ = _apply_and_restore({"STOCK_ALLOCATION": 1.5})
        assert post["BOND_ALLOCATION"] == pytest.approx(0.0)


# =============================================================================
# Finding #2 — RETURN SCENARIO: dropdown copies params into engine globals.
# =============================================================================

class TestReturnScenarioWiring:
    def test_pessimistic_scenario_copies_into_globals(self):
        params = cfg.get_return_parameters("pessimistic")
        post, restored, defaults = _apply_and_restore(
            {"ACTIVE_RETURN_SCENARIO": "pessimistic"}
        )
        assert post["EXPECTED_STOCK_RETURN"] == params["stock_return"]
        assert post["EXPECTED_BOND_RETURN"] == params["bond_return"]
        assert post["STOCK_VOLATILITY"] == params["stock_volatility"]
        assert post["BOND_VOLATILITY"] == params["bond_volatility"]
        # Restore reverts to the module defaults.
        for k in ("EXPECTED_STOCK_RETURN", "EXPECTED_BOND_RETURN",
                  "STOCK_VOLATILITY", "BOND_VOLATILITY"):
            assert restored[k] == defaults[k]

    def test_conservative_and_pessimistic_differ(self):
        cons, _, _ = _apply_and_restore({"ACTIVE_RETURN_SCENARIO": "conservative"})
        pess, _, _ = _apply_and_restore({"ACTIVE_RETURN_SCENARIO": "pessimistic"})
        # The two scenarios must produce different engine globals (proves live).
        assert cons["EXPECTED_STOCK_RETURN"] != pess["EXPECTED_STOCK_RETURN"]
        assert cons["STOCK_VOLATILITY"] != pess["STOCK_VOLATILITY"]


# =============================================================================
# Finding #5 — CHILD COSTS: annual derived from the monthly overrides.
# =============================================================================

class TestChildCostDerivation:
    def test_annual_child_costs_recompute_from_monthly(self):
        post, restored, defaults = _apply_and_restore({
            "FIRST_CHILD_MONTHLY_COST": 5000,
            "BOTH_CHILDREN_MONTHLY_COST": 9000,
        })
        assert post["FIRST_CHILD_ANNUAL_COST"] == 5000 * 12
        assert post["BOTH_CHILDREN_ANNUAL_COST"] == 9000 * 12
        assert restored["FIRST_CHILD_ANNUAL_COST"] == defaults["FIRST_CHILD_ANNUAL_COST"]
        assert restored["BOTH_CHILDREN_ANNUAL_COST"] == defaults["BOTH_CHILDREN_ANNUAL_COST"]

    def test_child_expense_reader_sees_the_override(self):
        # calculate_child_expenses reads the *_ANNUAL_COST derived constants;
        # with both kids at home the override must flow through.
        original = sr._apply_overrides({
            "FIRST_CHILD_MONTHLY_COST": 5000,
            "BOTH_CHILDREN_MONTHLY_COST": 9000,
            # Ensure both children are present at the sampled age.
            "YEARS_UNTIL_FIRST_CHILD": 0,
            "YEARS_BETWEEN_CHILDREN": 1,
        })
        try:
            # A few years out both kids are home -> BOTH_CHILDREN_ANNUAL_COST.
            cost = cfg.calculate_child_expenses(cfg.YOUR_AGE + 3)
            assert cost == pytest.approx(9000 * 12)
        finally:
            sr._restore_overrides(original)


# =============================================================================
# Finding #12 — HEALTH PREMIUMS: annual derived from the monthly/base overrides.
# =============================================================================

class TestHealthPremiumDerivation:
    def test_annual_premiums_recompute_from_monthly(self):
        post, restored, defaults = _apply_and_restore({
            "ACA_BASE_MONTHLY_PREMIUM": 3000,
            "MEDICARE_MONTHLY_PREMIUM": 800,
        })
        assert post["ACA_BASE_ANNUAL_PREMIUM"] == 3000 * 12
        assert post["MEDICARE_ANNUAL_PREMIUM"] == 800 * 12
        assert restored["ACA_BASE_ANNUAL_PREMIUM"] == defaults["ACA_BASE_ANNUAL_PREMIUM"]
        assert restored["MEDICARE_ANNUAL_PREMIUM"] == defaults["MEDICARE_ANNUAL_PREMIUM"]


# =============================================================================
# End-to-end: finding #1 MOVES a full profile's Monte Carlo (the big one).
# =============================================================================

def _profile_overrides():
    from tests.conftest import load_sample_household
    return load_sample_household()


@pytest.mark.slow
def test_phantom_leverage_fix_drops_profile_median():
    """The sample profile sets STOCK_ALLOCATION=1.0 while BOND_ALLOCATION
    defaulted to 0.20 (120% invested = phantom leverage). Removing the leverage
    (BOND = 1 - STOCK = 0.0) must DROP the median end-balance substantially vs a
    run that re-injects the buggy 120% state.
    """
    from utils.sim_runner import run_full_analysis, clear_cache

    p = _profile_overrides()
    ra = int(p["TARGET_RETIREMENT_AGE"])

    # Fixed run (current, correct behavior).
    clear_cache()
    np.random.seed(42)
    fixed = run_full_analysis(
        user_overrides=p, n_simulations=400,
        target_retirement_age=ra, scan_age_range=(ra, ra + 1, 1),
    )["primary_result"]

    # Buggy run: monkeypatch _recompute_derived to skip the bond-partner
    # derivation, restoring the pre-fix 120%-invested leverage.
    real_recompute = sr._recompute_derived

    def _leveraged_recompute(original):
        real_recompute(original)
        # Undo just the bond-partner derivation so stock+bond sums to 1.2 again.
        cfg.BOND_ALLOCATION = 0.20
        cfg.GLIDE_PATH_START_BOND_PCT = 0.20
        cfg.GLIDE_PATH_END_BOND_PCT = 0.40

    sr._recompute_derived = _leveraged_recompute
    try:
        clear_cache()
        np.random.seed(42)
        buggy = run_full_analysis(
            user_overrides=p, n_simulations=400,
            target_retirement_age=ra, scan_age_range=(ra, ra + 1, 1),
        )["primary_result"]
    finally:
        sr._recompute_derived = real_recompute
        clear_cache()

    # The buggy (leveraged) median must be materially higher than the fixed one.
    # The extra 10-20% bond exposure compounds to roughly 1.2-1.3x by the plan
    # horizon, and the exact ratio moves with whichever paths land at the median
    # (observed 1.23x-1.46x across routine edits to a real saved profile), so
    # the bar sits at 1.1x: a real regression collapses it to ~1.0x.
    assert buggy["median_final"] > fixed["median_final"] * 1.1, (
        f"phantom leverage should inflate median: buggy={buggy['median_final']:.0f} "
        f"fixed={fixed['median_final']:.0f}"
    )


@pytest.mark.slow
def test_return_scenario_moves_profile_success():
    """Flipping ACTIVE_RETURN_SCENARIO between conservative and pessimistic must
    now move the seeded Monte Carlo success rate (was byte-identical / inert)."""
    from utils.sim_runner import run_full_analysis, clear_cache

    p = _profile_overrides()
    ra = int(p["TARGET_RETIREMENT_AGE"])

    def _run(scenario):
        q = dict(p)
        q["ACTIVE_RETURN_SCENARIO"] = scenario
        clear_cache()
        np.random.seed(7)
        return run_full_analysis(
            user_overrides=q, n_simulations=400,
            target_retirement_age=ra, scan_age_range=(ra, ra + 1, 1),
        )["primary_result"]["success_rate"]

    cons = _run("conservative")
    pess = _run("pessimistic")
    clear_cache()
    # Pessimistic (5% stock / 22% vol) must be strictly worse than conservative.
    assert pess < cons, f"scenario inert: conservative={cons} pessimistic={pess}"
