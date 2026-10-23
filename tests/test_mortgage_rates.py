"""The current loan and the house move's new loan each amortize at their own
rate (MORTGAGE_RATE_FOR_PAYOFF and NEW_MORTGAGE_RATE). The new loan used to
reuse the current loan's rate, and the app's new-loan rate input never reached
the engine."""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import account_simulation as sim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402
from utils.sim_runner import _apply_overrides, _restore_overrides  # noqa: E402

MOVE = {"YOUR_AGE": 40, "HOME_VALUE": 700_000, "MORTGAGE_BALANCE": 400_000, "MORTGAGE_MONTHLY": 3_800,
        "MORTGAGE_YEARS_REMAINING": 14, "HOUSE_MOVE_ENABLED": True, "HOUSE_MOVE_AGE": 42,
        "NEW_HOME_VALUE": 1_000_000, "NEW_MORTGAGE_BALANCE": 800_000, "NEW_MORTGAGE_MONTHLY": 7_900,
        "NEW_MORTGAGE_YEARS": 15}


def _with(overrides, fn):
    original = _apply_overrides(build_config_overrides(overrides))
    try:
        return fn()
    finally:
        _restore_overrides(original)


def _after_move(overrides):
    def run():
        p = sim.AccountPortfolio()
        rate_before = p._mortgage_rate
        p.maybe_execute_house_move(cfg.HOUSE_MOVE_AGE)
        return rate_before, p._mortgage_rate, p._mortgage_pi
    return _with(overrides, run)


def test_new_loan_amortizes_at_its_own_rate():
    before, after, pi = _after_move({**MOVE, "MORTGAGE_RATE_FOR_PAYOFF": 0.0575, "NEW_MORTGAGE_RATE": 0.07})
    assert (before, after) == (0.0575, 0.07)
    assert pi == pytest.approx(sim._level_payment(800_000, 0.07, 15))


def test_new_rate_falls_back_to_the_current_loan():
    assert cfg.NEW_MORTGAGE_RATE is None
    _, after, _ = _after_move({**MOVE, "MORTGAGE_RATE_FOR_PAYOFF": 0.0575})
    assert after == 0.0575


def test_payoff_projection_switches_rate_at_the_move():
    proj = lambda new: _with({**MOVE, "MORTGAGE_RATE_FOR_PAYOFF": 0.0575, "NEW_MORTGAGE_RATE": new},
                             lambda: sim.mortgage_payoff_projection(0.0)["total_interest"])
    assert proj(0.08) > proj(0.05)     # the new loan's rate drives interest after the move


def test_app_schedule_matches_engine_when_rates_differ():
    from tests.test_home_carrying_cost import _assert_schedule_matches_engine
    _assert_schedule_matches_engine({**MOVE, "MORTGAGE_RATE_FOR_PAYOFF": 0.0575, "NEW_MORTGAGE_RATE": 0.07})
