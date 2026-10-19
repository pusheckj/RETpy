"""Tests for the always-on deterministic charts reacting to the Big-purchases /
goals toggles (Stage 2 #1A).

The two charts (net_worth_projection_chart, spending_chart) read directly from
``user_overrides`` and must:
  1. Be identical to the baseline when all toggles are OFF.
  2. Bend visibly when a car / house-move / vacation toggle is turned ON, reusing
     the engine cfg helpers so the math matches the Monte Carlo engine.
  3. Recompute the mortgage-payoff age from the NEW loan after a house move
     (the specific reported bug: move at 34 with a 30yr loan => paid off at 64,
     NOT the old value).

The chart modules live under ``ui/``; add both ROOT and ROOT/ui to sys.path so
their internal ``from components...`` / ``from utils...`` imports resolve.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components import net_worth_projection_chart as nw
from components import spending_chart as sp


# ---------------------------------------------------------------------------
# Shared baseline overrides (owner with a mortgage + some savings).
# ---------------------------------------------------------------------------
def _base_overrides() -> dict:
    return {
        "YOUR_AGE": 34,
        "TARGET_RETIREMENT_AGE": 55,
        "PLAN_UNTIL_AGE": 90,
        "ACTIVE_RETURN_SCENARIO": "historical",
        "HOME_VALUE": 600_000,
        "MORTGAGE_BALANCE": 300_000,
        "MORTGAGE_MONTHLY": 2_000,
        "MORTGAGE_YEARS_REMAINING": 12,   # old payoff would be 34 + 12 = 46
        "YOUR_BROKERAGE": 200_000,
        "YOUR_BROKERAGE_CONTRIBUTION": 20_000,
        "YOUR_CASH": 100_000,
        "SPEND_FOOD_MONTHLY": 1_000,
    }


# ===========================================================================
# NET WORTH PROJECTION CHART
# ===========================================================================
def test_net_worth_baseline_when_all_off():
    """All toggles OFF => projection is unchanged."""
    ov = _base_overrides()
    proj = nw.project_net_worth(ov)
    assert proj["ages"][0] == 34
    # Home equity starts at value - mortgage and never gets rewritten.
    assert proj["by_account"]["Home equity"][0] == 300_000.0


def test_net_worth_car_purchase_bends_projection():
    ov = _base_overrides()
    on = dict(ov)
    on["CAR_ONETIME_ENABLED"] = True
    on["CAR_ONETIME_AGE"] = 40
    on["CAR_ONETIME_AMOUNT"] = 50_000

    base = nw.project_net_worth(ov)
    car = nw.project_net_worth(on)

    def total_at(proj, age):
        i = proj["ages"].index(age)
        return sum(proj["by_account"][lbl][i] for lbl, *_ in nw.ACCOUNTS)

    # Before the purchase age, totals match; from the purchase age on, the car
    # scenario is lower (a $50k outlay compounds away).
    assert total_at(base, 39) == total_at(car, 39)
    assert total_at(car, 40) < total_at(base, 40)


def test_net_worth_house_move_switches_equity_and_nets_cash():
    ov = _base_overrides()
    on = dict(ov)
    on["HOUSE_MOVE_ENABLED"] = True
    on["HOUSE_MOVE_AGE"] = 40
    on["NEW_HOME_VALUE"] = 1_000_000
    on["NEW_MORTGAGE_BALANCE"] = 800_000   # new equity 200k (< old 300k)
    on["HOME_SELLING_COST_PCT"] = 0.06
    on["HOUSE_MOVING_COSTS"] = 10_000

    proj = nw.project_net_worth(on)
    i = proj["ages"].index(40)
    # Home equity switches to the NEW home's equity at the move age.
    assert proj["by_account"]["Home equity"][i] == 200_000.0
    # Before the move it is still the (compounded) OLD equity, not the new one.
    assert proj["by_account"]["Home equity"][proj["ages"].index(39)] != 200_000.0
    assert proj["by_account"]["Home equity"][proj["ages"].index(39)] >= 300_000.0


def test_net_worth_vacation_bends_only_in_retirement():
    ov = dict(_base_overrides())
    ov["TARGET_RETIREMENT_AGE"] = 45   # keep horizon short so vacation years appear
    on = dict(ov)
    on["RETIREMENT_VACATION_ENABLED"] = True
    on["RETIREMENT_VACATION_ANNUAL"] = 30_000
    on["RETIREMENT_VACATION_UNTIL_AGE"] = 75

    base = nw.project_net_worth(ov)
    vac = nw.project_net_worth(on)

    def total_at(proj, age):
        i = proj["ages"].index(age)
        return sum(proj["by_account"][lbl][i] for lbl, *_ in nw.ACCOUNTS)

    # At retirement age the vacation outlay starts draining the portfolio.
    assert total_at(vac, 45) < total_at(base, 45)


def test_net_worth_cfg_globals_restored():
    """The context-manager patch must restore cfg globals after use."""
    from retirement_sim import config as cfg
    before = cfg.CAR_ONETIME_ENABLED
    ov = dict(_base_overrides())
    ov["CAR_ONETIME_ENABLED"] = not before
    ov["CAR_ONETIME_AGE"] = 40
    nw.project_net_worth(ov)
    assert cfg.CAR_ONETIME_ENABLED == before


# ===========================================================================
# SPENDING CHART — housing series + payoff age
# ===========================================================================
def test_spending_housing_baseline_payoff_age():
    ov = _base_overrides()
    ages = list(range(34, 91))
    series, owns_now, payoff = sp._compute_housing_series(ov, ages)
    assert owns_now is True
    assert payoff == 46          # 34 + 12
    # Mortgage active through 45; from 46 on only property tax + insurance
    # (HOME_CARRYING_COST_PCT of the home's value) remain.
    assert series[ages.index(45)] == 2_000 * 12
    assert series[ages.index(46)] == 600_000 * 0.0135


def test_spending_house_move_recomputes_payoff_age_bug():
    """The reported bug: move at 34 with a 30yr loan => paid off at 64, not 46."""
    ov = dict(_base_overrides())
    ov["HOUSE_MOVE_ENABLED"] = True
    ov["HOUSE_MOVE_AGE"] = 34
    ov["NEW_MORTGAGE_MONTHLY"] = 4_500
    ov["NEW_MORTGAGE_YEARS"] = 30

    ages = list(range(34, 91))
    series, owns_now, payoff = sp._compute_housing_series(ov, ages)
    assert payoff == 64          # 34 + 30, NOT the old 46
    # New mortgage payment used from the move age onward.
    assert series[ages.index(34)] == 4_500 * 12
    assert series[ages.index(63)] == 4_500 * 12
    assert series[ages.index(64)] == 0


def test_spending_house_move_switches_payment_midstream():
    ov = dict(_base_overrides())
    ov["HOUSE_MOVE_ENABLED"] = True
    ov["HOUSE_MOVE_AGE"] = 40
    ov["NEW_MORTGAGE_MONTHLY"] = 4_500
    ov["NEW_MORTGAGE_YEARS"] = 30

    ages = list(range(34, 91))
    series, _, payoff = sp._compute_housing_series(ov, ages)
    # Old payment before move, new payment after.
    assert series[ages.index(39)] == 2_000 * 12
    assert series[ages.index(40)] == 4_500 * 12
    assert payoff == 70          # 40 + 30


def test_spending_car_outlay_matches_engine_helper():
    ov = dict(_base_overrides())
    ov["CAR_ONETIME_ENABLED"] = True
    ov["CAR_ONETIME_AGE"] = 40
    ov["CAR_ONETIME_AMOUNT"] = 45_000
    assert sp._car_outlay(ov, 40) == 45_000
    assert sp._car_outlay(ov, 41) == 0


def test_spending_vacation_outlay_matches_engine_helper():
    ov = dict(_base_overrides())
    ov["RETIREMENT_VACATION_ENABLED"] = True
    ov["RETIREMENT_VACATION_ANNUAL"] = 25_000
    ov["RETIREMENT_VACATION_UNTIL_AGE"] = 75
    retire = 55
    assert sp._vacation_outlay(ov, 54, retire) == 0        # not retired yet
    assert sp._vacation_outlay(ov, 55, retire) == 25_000   # go-go years
    assert sp._vacation_outlay(ov, 75, retire) == 0        # slowed down


def test_spending_render_smoke_all_off_and_on():
    """Render must not raise with a stub st, toggles OFF and ON."""
    ov = _base_overrides()

    class _StubFig:
        pass

    class _StubSt:
        session_state = {}
        def __init__(self, overrides):
            self.session_state = {"user_overrides": overrides}
        def info(self, *a, **k):
            pass
        def caption(self, *a, **k):
            pass
        def radio(self, label, options, **k):
            # Combined spending chart has a Today's/Future dollars toggle.
            return options[0] if options else None
        def plotly_chart(self, *a, **k):
            pass

    # OFF
    sp.render(_StubSt(dict(ov)))
    # ON (all three)
    on = dict(ov)
    on.update({
        "CAR_ONETIME_ENABLED": True, "CAR_ONETIME_AGE": 40, "CAR_ONETIME_AMOUNT": 45_000,
        "HOUSE_MOVE_ENABLED": True, "HOUSE_MOVE_AGE": 40,
        "NEW_MORTGAGE_MONTHLY": 4_500, "NEW_MORTGAGE_YEARS": 30,
        "RETIREMENT_VACATION_ENABLED": True, "RETIREMENT_VACATION_ANNUAL": 25_000,
        "RETIREMENT_VACATION_UNTIL_AGE": 75,
    })
    sp.render(_StubSt(on))
