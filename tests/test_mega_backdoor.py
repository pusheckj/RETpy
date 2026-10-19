"""Tests for the mega backdoor Roth (after-tax 401(k) -> in-plan Roth conversion).

The engine contributes an after-tax 401(k) amount (up to the 415(c) total-
additions room) to the Roth bucket, funded from take-home, when
YOUR_AFTER_TAX_401K_PCT > 0. These pin:
1. get_401k_total_limit returns the 415(c) limit (69k base, +catchup at 50+).
2. 0% is a no-op (byte-identical to the pre-feature behavior).
3. A positive % reallocates take-home from taxable brokerage into Roth, and
   terminal wealth does not fall (Roth grows tax-free vs the taxable drag).
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest

from retirement_sim import config as cfg
from retirement_sim.account_simulation import run_detailed_simulation


@pytest.fixture(autouse=True)
def _restore():
    orig = getattr(cfg, "YOUR_AFTER_TAX_401K_PCT", 0.0)
    yield
    cfg.YOUR_AFTER_TAX_401K_PCT = orig


def test_415c_total_limit_helper():
    assert cfg.get_401k_total_limit(40, 2024) == 69_000        # base 415(c)
    assert cfg.get_401k_total_limit(55, 2024) == 69_000 + 7_500  # +catch-up at 50+


def _balances(seed):
    ok, p = run_detailed_simulation(50, random_seed=seed)
    roth = sum(a.balance for n, a in p.accounts.items() if "roth" in n)
    brk = sum(a.balance for n, a in p.accounts.items() if "brokerage" in n)
    return roth, brk, p.get_total_balance()


def _roth_funded(seed):
    """Cumulative dollars CONTRIBUTED to Roth (incl. the mega-backdoor).

    Measured instead of the ending Roth balance because the mega backdoor is an
    ACCUMULATION-phase reallocation, while the ending balance is read at age 95
    after decades of drawdown -- on a profile that can deplete, both arms read
    $0 and the comparison silently tests nothing. ``roth_contribution_basis`` is
    increment-only (never drawn down; ``_roth_basis_drawn`` tracks draws
    separately), so it isolates the contribution effect under test.
    """
    ok, p = run_detailed_simulation(50, random_seed=seed)
    return p.roth_contribution_basis


def test_zero_pct_is_noop():
    cfg.YOUR_AFTER_TAX_401K_PCT = 0.0
    a = [round(_balances(s)[2], 2) for s in range(5)]
    # Removing the attribute entirely (pre-feature) must match 0.0 exactly.
    del cfg.YOUR_AFTER_TAX_401K_PCT
    b = [round(_balances(s)[2], 2) for s in range(5)]
    cfg.YOUR_AFTER_TAX_401K_PCT = 0.0
    assert a == b


def test_positive_pct_shifts_brokerage_to_roth():
    cfg.YOUR_AFTER_TAX_401K_PCT = 0.0
    roth0 = _roth_funded(42)
    tot0 = _balances(42)[2]
    cfg.YOUR_AFTER_TAX_401K_PCT = 0.16
    roth1 = _roth_funded(42)
    tot1 = _balances(42)[2]
    assert roth1 > roth0          # more was contributed to Roth
    assert tot1 >= tot0 * 0.999   # terminal wealth not reduced (tax-free growth)


def test_manual_mode_conserves_dollars():
    """MANUAL savings mode must NOT phantom-create wealth: with take-home savings
    large enough to fund all electives, enabling the mega backdoor just moves
    dollars from brokerage into Roth, so ONE contribution year with zero returns
    adds the SAME total regardless of the split. (Regression for the adversarial-
    review finding that the engine's MANUAL branch failed to subtract the after-
    tax 401k from the brokerage.)"""
    import retirement_sim.account_simulation as sim
    saved = dict(
        SAVINGS_MODE=getattr(cfg, "SAVINGS_MODE", "Auto"),
        brk=getattr(cfg, "YOUR_BROKERAGE_CONTRIBUTION", None),
        comp=cfg.YOUR_COMPENSATION_BY_AGE,
        k=getattr(cfg, "YOUR_401K_CONTRIBUTION", None),
        match=cfg.YOUR_401K_MATCH_PCT,
        backdoor=getattr(cfg, "YOUR_BACKDOOR_ROTH", None),
    )
    try:
        age = int(cfg.YOUR_AGE)
        # take-home 'saved' (100k) comfortably exceeds all electives, so the split
        # is the ONLY thing that changes between the two runs.
        cfg.SAVINGS_MODE = "Manual"
        cfg.YOUR_BROKERAGE_CONTRIBUTION = None       # use the saved-based formula
        cfg.YOUR_401K_MATCH_PCT = 0.0
        cfg.YOUR_401K_CONTRIBUTION = 23000
        cfg.YOUR_BACKDOOR_ROTH = 0
        cfg.YOUR_COMPENSATION_BY_AGE = {
            age: {"base": 300_000, "bonus": 0, "rsu_gross": 0,
                  "total_comp": 300_000, "after_tax": 210_000, "saved": 100_000},
        }

        def one_year_total(pct):
            cfg.YOUR_AFTER_TAX_401K_PCT = pct
            p = sim.create_initial_portfolio()
            start = p.get_total_balance()
            sim.simulate_accumulation_year(p, age, 0.0)  # zero return isolates contributions
            return p.get_total_balance() - start

        base_total = one_year_total(0.0)
        mega_total = one_year_total(0.10)   # ~30k after-tax 401k, well under saved=100k
        assert abs(mega_total - base_total) <= max(1.0, base_total * 1e-6), (
            f"MANUAL mode leaked money: base={base_total:,.2f} mega={mega_total:,.2f}"
        )
    finally:
        cfg.SAVINGS_MODE = saved["SAVINGS_MODE"]
        cfg.YOUR_BROKERAGE_CONTRIBUTION = saved["brk"]
        cfg.YOUR_COMPENSATION_BY_AGE = saved["comp"]
        cfg.YOUR_401K_CONTRIBUTION = saved["k"]
        cfg.YOUR_401K_MATCH_PCT = saved["match"]
        cfg.YOUR_BACKDOOR_ROTH = saved["backdoor"]
