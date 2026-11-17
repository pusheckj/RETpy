"""Batch b3: UI numbers that must agree with the engine, and input limits that
must not cut a saved plan (return rate, what-if spending slider, today's expense
total with a paid-off mortgage, Debts widget limits, years_text)."""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import debts as dm  # noqa: E402
from components import net_worth_projection_chart as nw  # noqa: E402
from components import whatif_retirement_curve as wf  # noqa: E402
from utils import debt_view as dv  # noqa: E402
from utils import derived  # noqa: E402


# --- return rate: the engine's volatility drag -------------------------------
def _engine_rate(scen, w_s, fee=0.0, drag=True):
    p = cfg.get_return_parameters(scen)
    w_b = 1 - w_s
    rate = w_s * (p["stock_return"] - fee) + w_b * (p["bond_return"] - fee)
    if drag:
        rate -= (w_s ** 2 * p["stock_volatility"] ** 2 + w_b ** 2 * p["bond_volatility"] ** 2
                 + 2 * w_s * w_b * cfg.STOCK_BOND_CORRELATION
                 * p["stock_volatility"] * p["bond_volatility"]) / 2
    return rate


@pytest.mark.parametrize("scen", ["conservative", "historical", "pessimistic"])
def test_investment_return_nets_volatility_drag(scen):
    ov = {"STOCK_ALLOCATION": 0.8, "INVESTMENT_FEE_RATE": 0.0, "APPLY_VOLATILITY_DRAG": True}
    assert nw.investment_real_return(scen, ov) == pytest.approx(_engine_rate(scen, 0.8))
    assert nw._SCENARIO_RETURNS[scen]["investment"] == pytest.approx(
        nw.investment_real_return(scen, {"STOCK_ALLOCATION": cfg.STOCK_ALLOCATION}))


def test_historical_return_is_about_six_and_a_half_not_seven_and_a_half():
    r = nw.investment_real_return("historical", {"STOCK_ALLOCATION": 0.8, "INVESTMENT_FEE_RATE": 0.0,
                                                 "APPLY_VOLATILITY_DRAG": True})
    assert 0.062 < r < 0.067


def test_return_follows_allocation_fee_and_drag_switch():
    base = {"STOCK_ALLOCATION": 1.0, "INVESTMENT_FEE_RATE": 0.0, "APPLY_VOLATILITY_DRAG": True}
    assert nw.investment_real_return("historical", {**base, "APPLY_VOLATILITY_DRAG": False}) == pytest.approx(0.087)
    assert nw.investment_real_return("historical", {**base, "INVESTMENT_FEE_RATE": 0.01}) == pytest.approx(
        _engine_rate("historical", 1.0, fee=0.01))


def test_debt_view_real_return_uses_the_net_rate():
    ov = {"ACTIVE_RETURN_SCENARIO": "historical", "STOCK_ALLOCATION": 0.8,
          "INVESTMENT_FEE_RATE": 0.0, "APPLY_VOLATILITY_DRAG": True}
    assert dv.real_return(ov) == pytest.approx(_engine_rate("historical", 0.8))
    assert dv.real_return(ov) < 0.07


def test_projection_grows_at_the_net_rate():
    ov = {"YOUR_AGE": 40, "PARTNER_AGE": 0, "YOUR_401K": 100_000, "YOUR_401K_CONTRIBUTION": 0,
          "ACTIVE_RETURN_SCENARIO": "historical", "STOCK_ALLOCATION": 0.8,
          "INVESTMENT_FEE_RATE": 0.0, "APPLY_VOLATILITY_DRAG": True}
    assert nw.returns_for(ov)["investment"] == pytest.approx(_engine_rate("historical", 0.8))


# --- what-if spending slider -------------------------------------------------
class _St:
    def __init__(self, **kw):
        self.session_state = kw


def _alt(base, spend):
    return wf._alt_overrides(_St(wifc_spend=spend), base)


def test_slider_100_keeps_the_plan_unchanged():
    base = {"RETIREMENT_SPENDING_MODE": "Absolute amount ($/yr)", "RETIREMENT_SPENDING_ABSOLUTE": 60_000}
    alt = _alt(base, 100.0)
    assert alt["RETIREMENT_SPENDING_MODE"] == "Absolute amount ($/yr)"
    assert alt["RETIREMENT_SPENDING_ABSOLUTE"] == 60_000


def test_slider_is_continuous_for_an_absolute_plan():
    base = {"RETIREMENT_SPENDING_MODE": "Absolute amount ($/yr)", "RETIREMENT_SPENDING_ABSOLUTE": 60_000}
    alt = _alt(base, 99.0)
    assert alt["RETIREMENT_SPENDING_MODE"] == "Absolute amount ($/yr)"
    assert alt["RETIREMENT_SPENDING_ABSOLUTE"] == pytest.approx(59_400)


def test_slider_scales_a_percent_plan_and_a_same_as_today_plan():
    pct = _alt({"RETIREMENT_SPENDING_MODE": "% of today's expenses", "RETIREMENT_SPENDING_PCT": 0.8}, 90.0)
    assert pct["RETIREMENT_SPENDING_PCT"] == pytest.approx(0.72)
    same = _alt({"RETIREMENT_SPENDING_MODE": "Same as today's expenses"}, 90.0)
    assert same["RETIREMENT_SPENDING_MODE"] == "% of today's expenses"
    assert same["RETIREMENT_SPENDING_PCT"] == pytest.approx(0.9)


# --- today's expense total with a paid-off mortgage ---------------------------
def _expenses(**kw):
    return derived.compute_expenses_today(
        {"YOUR_AGE": 40, "PARTNER_AGE": 0, "CHILDREN": [], "PARTNER_OTHER_MONTHLY": 0, **kw})


def test_paid_off_mortgage_costs_only_the_carrying_cost():
    paid_off = _expenses(MORTGAGE_MONTHLY=2_000, MORTGAGE_YEARS_REMAINING=0, HOME_VALUE=500_000)
    outright = _expenses(MORTGAGE_MONTHLY=0, MORTGAGE_YEARS_REMAINING=0, HOME_VALUE=500_000)
    assert paid_off == outright > 0
    assert paid_off == round(500_000 * 0.0135)


def test_running_mortgage_still_counts():
    loan = _expenses(MORTGAGE_MONTHLY=2_000, MORTGAGE_YEARS_REMAINING=20, HOME_VALUE=500_000)
    assert loan == 24_000


# --- Debts widget limits ------------------------------------------------------
def test_debt_widget_limits_match_the_engine():
    assert dv.BALANCE_MAX == int(dm.BALANCE_MAX) and dv.PAYMENT_MAX == int(dm.PAYMENT_MAX)
    assert isinstance(dv.BALANCE_MAX, int) and isinstance(dv.PAYMENT_MAX, int)


def test_large_debt_round_trips_through_the_widgets():
    debt = {"name": "Loan", "kind": "other", "balance": 12_500_000.0, "apr": 0.05, "min_payment": 150_000.0}
    ss = {}
    dv.seed_rows(ss, [debt])
    row = dv.row_from_widgets(ss, 0, dm.normalize_debts([debt])[0])
    assert row["balance"] == 12_500_000.0 and row["min_payment"] == 150_000.0


# --- years_text ---------------------------------------------------------------
def test_years_text_singular():
    assert dv.years_text(11) == "about a year"
    assert dv.years_text(12) == "about a year"
    assert dv.years_text(23) == "about 2 years"
