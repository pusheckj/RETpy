"""Tests for the separate-partner-retirement-age feature.

The feature lets the partner retire at a different age than the primary. Its
core safety property is that leaving it unused (``PARTNER_RETIREMENT_AGE = None``,
or a value that makes the partner retire the same year the primary does) is
BYTE-IDENTICAL to the pre-feature household-wide single-switch behavior.

Directionally:
  * partner retires EARLIER  -> stops earning/contributing sooner -> less saved
  * partner works LATER      -> keeps earning into the primary's retirement,
                                offsetting withdrawals -> more left / higher success
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import statistics

import pytest

from retirement_sim import config as cfg
from retirement_sim.account_simulation import run_detailed_simulation


@pytest.fixture(autouse=True)
def _restore_partner_ret_age():
    """Always restore the global after each test (engine reads it off cfg)."""
    original = getattr(cfg, "PARTNER_RETIREMENT_AGE", None)
    yield
    cfg.PARTNER_RETIREMENT_AGE = original


def _final(retirement_age, seed):
    ok, portfolio = run_detailed_simulation(retirement_age, random_seed=seed)
    return ok, round(portfolio.get_total_balance(), 2)


def _partner_age_when_primary_retires(retirement_age):
    """Partner's own age in the year the primary reaches ``retirement_age``."""
    return retirement_age - (cfg.YOUR_AGE - cfg.PARTNER_AGE)


# ---------------------------------------------------------------------------
# Byte-identical regression lock (the whole feature's safety guarantee)
# ---------------------------------------------------------------------------

def test_none_is_byte_identical_to_retire_together():
    """None and 'partner retires the same year as the primary' must match to the
    cent across many seeds, both in success flag and final balance."""
    ret = 55
    cfg.PARTNER_RETIREMENT_AGE = None
    baseline = [_final(ret, s) for s in range(12)]

    cfg.PARTNER_RETIREMENT_AGE = _partner_age_when_primary_retires(ret)
    together = [_final(ret, s) for s in range(12)]

    assert baseline == together


def test_no_partner_ignores_the_setting():
    """With no partner (PARTNER_AGE == 0), the setting must have no effect."""
    orig_partner_age = cfg.PARTNER_AGE
    try:
        cfg.PARTNER_AGE = 0
        ret = 55
        cfg.PARTNER_RETIREMENT_AGE = None
        base = [_final(ret, s) for s in range(8)]
        # An early partner-retirement value must be ignored when there's no partner.
        cfg.PARTNER_RETIREMENT_AGE = 45
        forced = [_final(ret, s) for s in range(8)]
        assert base == forced
    finally:
        cfg.PARTNER_AGE = orig_partner_age


# ---------------------------------------------------------------------------
# Directional behavior
# ---------------------------------------------------------------------------

def _mean_balance(ret, seeds=range(24)):
    return statistics.mean(_final(ret, s)[1] for s in seeds)


def test_partner_retiring_earlier_saves_less():
    ret = 55
    together_age = _partner_age_when_primary_retires(ret)
    cfg.PARTNER_RETIREMENT_AGE = None
    baseline = _mean_balance(ret)
    cfg.PARTNER_RETIREMENT_AGE = together_age - 8  # partner stops 8 yrs early
    earlier = _mean_balance(ret)
    assert earlier < baseline


def test_partner_working_later_leaves_more():
    ret = 55
    together_age = _partner_age_when_primary_retires(ret)
    cfg.PARTNER_RETIREMENT_AGE = None
    baseline = _mean_balance(ret)
    cfg.PARTNER_RETIREMENT_AGE = together_age + 8  # partner works 8 yrs into retirement
    later = _mean_balance(ret)
    assert later > baseline


# ---------------------------------------------------------------------------
# UI seam: the override must reach the simulator (NOT a UI-only key)
# ---------------------------------------------------------------------------

def test_partner_retirement_age_passes_through_config_builder():
    from utils.config_builder import build_config_overrides
    out = build_config_overrides({"PARTNER_RETIREMENT_AGE": 63})
    # Unlike TARGET_RETIREMENT_AGE (UI-only), this must survive translation and
    # reach retirement_sim.config so the engine can read it.
    assert out.get("PARTNER_RETIREMENT_AGE") == 63


def test_partner_retirement_age_is_a_real_config_attribute():
    # Must exist as a primitive so sim_runner._apply_overrides' hasattr guard
    # doesn't silently drop it.
    assert hasattr(cfg, "PARTNER_RETIREMENT_AGE")
