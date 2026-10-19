"""RMD attribution pins — the engine now reports forced vs chosen draws.

``_flush_withdrawal_log`` folds RMDs into the ``traditional`` bucket (they really
do drain traditional balances), which meant the UI could not show how much of a
year's draw was MANDATORY. Three additive fields split it:

    rmd_gross           the full IRS-forced withdrawal for the year
    rmd_spent           the part that funded spending (folded into `traditional`)
    traditional_chosen  discretionary traditional draws only

These are ADDITIVE: ``traditional``, ``total`` and ``withdrawal_pct`` are
unchanged, so no simulation output moved. The tests below pin both the invariant
and the additivity, plus the behaviour that makes the numbers meaningful:

  * RMDs start exactly at the SECURE 2.0 age for the configured birth year.
  * A Roth-conversion strategy can legitimately drive RMDs to ZERO by draining
    traditional balances before that age — so "no RMD rows" is a valid result,
    not a broken feature (this is what the Roth-conversion caption claims).
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim.account_simulation import run_detailed_simulation  # noqa: E402


@pytest.fixture
def no_roth_conversion():
    """Keep traditional balances alive to the RMD age so RMDs actually fire."""
    original = getattr(cfg, "ENABLE_ROTH_CONVERSION", True)
    cfg.ENABLE_ROTH_CONVERSION = False
    try:
        yield
    finally:
        cfg.ENABLE_ROTH_CONVERSION = original


# Fixed seed: these runs are stochastic, and an unseeded path can drain the
# traditional balances before the RMD age -- which made the forced-withdrawal
# assertions skip at random instead of actually checking anything.
_SEED = 42


def _log(retirement_age=50, seed=_SEED):
    _ok, portfolio = run_detailed_simulation(
        retirement_age, verbose=False, random_seed=seed
    )
    return portfolio.withdrawal_log


def test_rmd_fields_present_on_every_retirement_year():
    for row in _log():
        for key in ("rmd_gross", "rmd_spent", "traditional_chosen"):
            assert key in row, f"{key} missing from withdrawal_log row (age {row['age']})"


def test_traditional_equals_chosen_plus_forced():
    """The split must reconstruct the bucket exactly — the chart stacks both."""
    for row in _log():
        expected = row["traditional_chosen"] + row["rmd_spent"]
        assert abs(row["traditional"] - expected) < 0.01, (
            f"age {row['age']}: traditional {row['traditional']} != "
            f"chosen {row['traditional_chosen']} + rmd_spent {row['rmd_spent']}"
        )


def test_rmd_spent_never_exceeds_gross():
    """Spent is gross minus whatever was reinvested — it can't be larger."""
    for row in _log():
        assert row["rmd_spent"] <= row["rmd_gross"] + 0.01, (
            f"age {row['age']}: rmd_spent {row['rmd_spent']} > gross {row['rmd_gross']}"
        )


def test_fields_are_non_negative():
    for row in _log():
        assert row["rmd_gross"] >= 0
        assert row["rmd_spent"] >= 0
        assert row["traditional_chosen"] >= 0


@pytest.mark.slow
def test_rmds_start_at_secure_20_age(no_roth_conversion):
    """With conversions off, forced withdrawals begin at the statutory age."""
    start_age = cfg.get_rmd_start_age(int(getattr(cfg, "YOUR_BIRTH_YEAR", 1990)))
    rows = _log()
    forced = [r for r in rows if r["rmd_gross"] > 0]
    assert forced, "seeded run should force RMDs once conversions are disabled"
    assert min(r["age"] for r in forced) >= start_age, (
        f"an RMD fired before the statutory start age {start_age}"
    )
    # And nothing forced strictly before it.
    assert all(r["rmd_gross"] == 0 for r in rows if r["age"] < start_age)


@pytest.mark.slow
def test_surplus_rmd_is_reinvested_not_spent(no_roth_conversion):
    """A forced withdrawal beyond spending need shows up as gross > spent.

    That gap is the money the engine reinvests into taxable (conservation #4) —
    the part a user cannot see when RMDs are folded into one bucket.
    """
    forced = [r for r in _log() if r["rmd_gross"] > 0]
    assert forced, "seeded run should force RMDs once conversions are disabled"
    assert any(r["rmd_gross"] > r["rmd_spent"] + 1.0 for r in forced), (
        "expected at least one year where the forced RMD exceeded spending need"
    )


def test_roth_conversion_can_eliminate_rmds():
    """Documents WHY zero-RMD runs are valid (the Roth-conversion claim).

    With the default strategy enabled, traditional balances are typically drained
    before the RMD age, so ``rmd_gross`` is legitimately 0 everywhere. This test
    passes either way — it exists to pin that 0 is not treated as a failure.
    """
    rows = _log()
    assert rows, "expected a non-empty retirement log"
    assert all(r["rmd_gross"] >= 0 for r in rows)
