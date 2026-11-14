"""A withdrawal need under $100 must not fail a plan over the gross-up's cents.

The gross-up solver (withdraw_tax_efficient) stops once less than
GROSSUP_TOLERANCE ($1) of net need is left. The solvency checks used only the
1% rule, so a need under $100 could fail on that leftover. In the Mid-career
preset a working year short by $52.51 delivered $51.96 net and failed a $2.25M
household. Every path has the same small deficit, so a quarter of all paths
failed at once: success fell from 61.7% to 37.3% for $200 more spending a year,
then came back at the next $200.
"""
import os
import sys
from contextlib import contextmanager

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import account_simulation as asim  # noqa: E402
from components.profile_picker import PROFILES  # noqa: E402
from utils import sim_runner as sr  # noqa: E402


@contextmanager
def applied(ov: dict):
    original = sr._apply_overrides(sr.build_config_overrides(ov))
    try:
        yield
    finally:
        sr._restore_overrides(original)


@pytest.mark.parametrize("need", [100.0, 250.0, 1_000.0, 52_510.0, 1e6])
def test_needs_of_100_or_more_keep_the_99_percent_rule(need):
    for frac in (0.0, 0.5, 0.98, 0.989, 0.99, 0.991, 1.0):
        net = need * frac
        assert asim._fell_short(net, need) == (net < need * asim.WITHDRAWAL_SHORTFALL_TOLERANCE)


def test_small_needs_allow_the_solvers_slack_but_not_a_real_shortfall():
    assert not asim._fell_short(51.96, 52.51)       # 55 cents left: the solver's own slack
    assert not asim._fell_short(0.0, 0.80)          # under $1 never fails
    assert asim._fell_short(50.0, 52.51)            # $2.51 short: real
    assert asim._fell_short(0.0, 52.51)             # nothing left to draw: real


def _bare_preset(extra_spending: int) -> dict:
    """The Mid-career preset as a plain dict, before the side panel adds the pay
    table: the engine pays the default $70k, so every working year until about
    50 is short by the same deterministic amount and the last ones are tiny."""
    ov = dict(PROFILES["Mid-career couple (40, kids)"])
    ov["SPEND_OTHER_MONTHLY"] = ov["SPEND_OTHER_MONTHLY"] + extra_spending / 12.0
    return ov


def test_success_is_monotone_in_spending_with_common_random_numbers(monkeypatch):
    draws = []                                  # (need, your_age) of every gross-up
    real = asim.AccountPortfolio.withdraw_tax_efficient

    def spy(self, amount_needed, *a, **kw):
        draws.append((amount_needed, kw.get("your_age")))
        return real(self, amount_needed, *a, **kw)

    monkeypatch.setattr(asim.AccountPortfolio, "withdraw_tax_efficient", spy)
    levels = [2_800, 3_000, 3_200, 3_400, 3_600]
    n, age = 200, 55
    rates = []
    for extra in levels:
        wins = 0
        draws.clear()
        with applied(_bare_preset(extra)):
            for i in range(n):
                ok, pf = asim.run_detailed_simulation(age, random_seed=1000 + i)
                wins += ok
                # A plan with millions invested never fails while still working.
                assert ok or pf.yearly_history[-1]["age"] >= age, (extra, i)
        rates.append(wins / n)
        if extra == 3_200:
            # The case the bug needed: a working year a few dollars short.
            assert any(1 < need < 100 and your_age < age for need, your_age in draws)
    # More spending never raises success by more than noise, nor drops it off a cliff.
    for lo, hi in zip(rates, rates[1:]):
        assert hi <= lo + 0.02, rates
        assert lo - hi <= 0.03, rates
