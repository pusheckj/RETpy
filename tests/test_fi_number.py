"""Tests for the net-worth-trigger ("FI number") simulation and sweep."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg
from retirement_sim.account_simulation import (
    run_detailed_simulation_networth, run_monte_carlo_networth,
    create_initial_portfolio, AccountType,
)
from utils import sim_runner as sr
from utils.config_builder import build_config_overrides
from tests.conftest import load_sample_household


def test_retire_immediately_when_target_below_current():
    # A trivially small target means the household is already past it -> retire now.
    ok, p, retire_age = run_detailed_simulation_networth(1.0, random_seed=1)
    assert retire_age == cfg.YOUR_AGE
    ok2, p2, ra2 = run_detailed_simulation_networth(1e15, max_work_age=70, random_seed=1)
    assert ra2 <= 70  # unreachable target -> retire by the work cap, not forever


def test_higher_target_retires_later_and_succeeds_more():
    lo = run_monte_carlo_networth(3_000_000, n_simulations=150, random_seed=7)
    hi = run_monte_carlo_networth(6_000_000, n_simulations=150, random_seed=7)
    assert hi["median_retire_age"] >= lo["median_retire_age"]  # bigger target -> work longer
    assert hi["success_rate"] >= lo["success_rate"]            # more cushion -> more success


def test_networth_analysis_finds_a_number_with_rising_curve():
    base = load_sample_household()
    sr.clear_cache()
    fi = sr.run_networth_analysis(base, n_simulations=150)
    assert fi["fi_number"] is not None
    assert fi["current_investable"] > 0
    assert fi["fi_number"] > fi["current_investable"]  # not FI yet on this profile
    assert not fi["already_fi"]
    ys = [c["success"] for c in fi["success_by_networth"]]
    assert ys[-1] > ys[0]  # success rises with the net-worth target


def test_investable_balance_excludes_529():
    # 529 college balances are earmarked and never fund retirement, so they must
    # not count toward the net-worth trigger (the "investable only" design).
    p = create_initial_portfolio()
    base_total = p.get_total_balance()
    base_inv = p.get_investable_balance()
    assert abs(base_total - base_inv) < 1e-6  # default has no 529 balance
    p.accounts["child1_529"].balance += 250_000  # fund a 529
    assert p.get_total_balance() == base_total + 250_000
    assert p.get_investable_balance() == base_inv  # investable unchanged
    # ...and the funded account really is a 529.
    assert p.accounts["child1_529"].account_type == AccountType.COLLEGE_529


def test_already_fi_household_reports_current_not_a_floor_artifact():
    # A household already well past FI should be flagged already_fi and report
    # its current balance, not a fabricated grid-floor figure below it.
    rich = load_sample_household()
    rich["YOUR_BROKERAGE"] = 8_000_000
    sr.clear_cache()
    fi = sr.run_networth_analysis(rich, n_simulations=150)
    assert fi["already_fi"] is True
    assert fi["success_by_networth"][0]["success"] >= fi["target_success"]
    # fi_number is the current balance, never below it (the old floor bug).
    assert fi["fi_number"] == fi["current_investable"]

