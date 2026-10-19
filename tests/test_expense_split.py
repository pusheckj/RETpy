"""Tests for the PRIMARY_PAYS_HOUSING expense-sharing toggle (brokerage attribution).

Default (False) = split all living expenses evenly. True = the primary covers the
full mortgage and only the rest is split evenly, so the partner (relieved of half
the mortgage) keeps MORE and the primary keeps less -- while the residual still
lands mostly in the primary's account. Both destinations are taxable, so the
total is conserved; only the per-account attribution changes.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg
from utils.derived import auto_allocate_savings, compute_disposable
from tests.conftest import load_sample_household


def test_default_is_even_split():
    assert getattr(cfg, "PRIMARY_PAYS_HOUSING", None) is False


def test_primary_pays_housing_shifts_partner_up_and_conserves():
    base = load_sample_household()
    disp = compute_disposable(base)

    even = auto_allocate_savings(disp, {**base, "PRIMARY_PAYS_HOUSING": False})
    ph = auto_allocate_savings(disp, {**base, "PRIMARY_PAYS_HOUSING": True})

    # Partner is relieved of half the mortgage -> keeps more in their brokerage;
    # primary shoulders the mortgage -> keeps less. Still mostly the primary's.
    assert ph["PARTNER_BROKERAGE_CONTRIBUTION"] > even["PARTNER_BROKERAGE_CONTRIBUTION"]
    assert ph["YOUR_BROKERAGE_CONTRIBUTION"] < even["YOUR_BROKERAGE_CONTRIBUTION"]
    assert ph["YOUR_BROKERAGE_CONTRIBUTION"] > ph["PARTNER_BROKERAGE_CONTRIBUTION"]

    # Dollar-conserving: same total brokerage either way (±1 for int rounding).
    even_tot = even["YOUR_BROKERAGE_CONTRIBUTION"] + even["PARTNER_BROKERAGE_CONTRIBUTION"]
    ph_tot = ph["YOUR_BROKERAGE_CONTRIBUTION"] + ph["PARTNER_BROKERAGE_CONTRIBUTION"]
    assert abs(even_tot - ph_tot) <= 1
