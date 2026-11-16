"""A withdrawal need under $100 must not fail a plan over the gross-up's cents.

The gross-up solver (withdraw_tax_efficient) stops once less than
GROSSUP_TOLERANCE ($1) of net need is left. The solvency checks used only the
1% rule, so a need under $100 could fail on that leftover. In the Mid-career
preset a working year short by $52.51 delivered $51.96 net and failed a $2.25M
household. Every path has the same small deficit, so a quarter of all paths
failed at once: success fell from 61.7% to 37.3% for $200 more spending a year,
then came back at the next $200.
"""
import copy
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
    """The Mid-career preset on the config's sample pay table (about $70k at 40):
    every working year until about 50 is short by the same deterministic amount
    and the last ones are tiny. This is what the preset used to simulate as a
    plain dict; its own salary now builds its table (config_builder), so the
    sample table is set explicitly to keep the case."""
    ov = dict(PROFILES["Mid-career couple (40, kids)"])
    ov["YOUR_COMPENSATION_BY_AGE"] = copy.deepcopy(asim.cfg.YOUR_COMPENSATION_BY_AGE)
    # ... with the contributions the preset used to state (stated, Auto-allocate leaves them
    # alone; its own would fill the IRAs too and remove the deficit).
    lim = asim.cfg.CONTRIBUTION_LIMITS_2026
    ov.update({"YOUR_401K_CONTRIBUTION": lim["401k"], "YOUR_HSA_CONTRIBUTION": lim["hsa_family"]})
    ov["SPEND_OTHER_MONTHLY"] = ov["SPEND_OTHER_MONTHLY"] + extra_spending / 12.0
    return ov


def test_success_is_monotone_in_spending_with_common_random_numbers(monkeypatch):
    draws = []                                  # (need, your_age) of every gross-up
    real = asim.AccountPortfolio.withdraw_tax_efficient

    def spy(self, amount_needed, *a, **kw):
        draws.append((amount_needed, kw.get("your_age")))
        return real(self, amount_needed, *a, **kw)

    monkeypatch.setattr(asim.AccountPortfolio, "withdraw_tax_efficient", spy)
    n, age = 200, 55
    # Find the spending level whose working year is a few dollars short (it moves
    # whenever a tax figure changes), then sweep $200 steps around it.
    edge = None
    for extra in range(1_600, 4_400, 20):
        draws.clear()
        with applied(_bare_preset(extra)):
            asim.run_detailed_simulation(age, random_seed=1000)
        if any(1 < need < 100 and your_age < age for need, your_age in draws):
            edge = extra
            break
    assert edge is not None, "no spending level gives a tiny working-year shortfall"
    levels = [edge - 400, edge - 200, edge, edge + 200, edge + 400]
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
        if extra == edge:
            # The case the bug needed: a working year a few dollars short.
            assert any(1 < need < 100 and your_age < age for need, your_age in draws)
    # More spending never raises success by more than noise, nor drops it off a cliff.
    for lo, hi in zip(rates, rates[1:]):
        assert hi <= lo + 0.02, rates
        assert lo - hi <= 0.03, rates
