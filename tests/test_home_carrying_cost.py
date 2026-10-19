"""Post-payoff home carrying cost (property tax + homeowners insurance).

MORTGAGE_MONTHLY / NEW_MORTGAGE_MONTHLY are ALL-IN payments (they bundle
escrow). The engine used to drop the whole payment at payoff, so housing fell to
$0 even though tax + insurance continue for life -- and an owner with no loan at
all paid nothing. The rule pinned here:

  * while a mortgage payment is owed  -> unchanged (escrow already included);
  * owner, no payment                 -> + home_value * HOME_CARRYING_COST_PCT,
                                         home_value = HOME_VALUE before a house
                                         move, NEW_HOME_VALUE after it;
  * renter                            -> unchanged;
  * MODEL_HOME_CARRYING_COST_AFTER_PAYOFF False -> exactly the pre-fix numbers.

The UI's derived.mortgage_schedule must report the same per-age housing.
"""
import os
import sys
import types

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import account_simulation as sim  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402
from utils.derived import mortgage_schedule  # noqa: E402

PCT = 0.0135
IF = {"general": 1.0, "healthcare": 1.0, "childcare": 1.0}


@pytest.fixture(autouse=True)
def _restore_cfg():
    """Snapshot EVERY cfg global and restore it, so no mutation leaks."""
    saved = {k: v for k, v in vars(cfg).items()
             if not k.startswith("__") and not isinstance(v, types.ModuleType)}
    try:
        yield
    finally:
        for k in [k for k in vars(cfg) if not k.startswith("__") and k not in saved]:
            delattr(cfg, k)
        for k, v in saved.items():
            setattr(cfg, k, v)


def _owner(home=600_000, monthly=3_000, years=5, balance=250_000):
    cfg.HOME_VALUE = home
    cfg.MORTGAGE_BALANCE = balance
    cfg.MORTGAGE_MONTHLY = monthly
    cfg.MORTGAGE_ANNUAL = monthly * 12
    cfg.MORTGAGE_YEARS_REMAINING = years
    cfg.HOUSE_MOVE_ENABLED = False
    cfg.HOME_CARRYING_COST_PCT = PCT


def _expenses(age, on):
    cfg.MODEL_HOME_CARRYING_COST_AFTER_PAYOFF = on
    return cfg.calculate_annual_expenses(age, 1.0, childcare_factor=1.0)


def test_defaults():
    assert cfg.HOME_CARRYING_COST_PCT == PCT
    assert cfg.MODEL_HOME_CARRYING_COST_AFTER_PAYOFF is True


# --------------------------------------------------------------------------
# config path
# --------------------------------------------------------------------------

def test_active_mortgage_is_unchanged():
    _owner()
    for age in range(cfg.YOUR_AGE, cfg.YOUR_AGE + 5):
        assert cfg.has_mortgage(age)
        assert _expenses(age, True) == _expenses(age, False)
        assert cfg.owner_housing_annual(age) == cfg.MORTGAGE_ANNUAL


def test_after_payoff_adds_value_times_pct_exactly():
    _owner()
    payoff = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
    for age in (payoff, payoff + 10, 90):
        assert _expenses(age, True) - _expenses(age, False) == pytest.approx(600_000 * PCT)
        cfg.MODEL_HOME_CARRYING_COST_AFTER_PAYOFF = True
        assert cfg.owner_housing_annual(age) == pytest.approx(600_000 * PCT)


def test_owner_without_mortgage_pays_from_day_one():
    _owner(monthly=0, years=0, balance=0)
    assert not cfg.is_renter()
    assert _expenses(cfg.YOUR_AGE, True) - _expenses(cfg.YOUR_AGE, False) \
        == pytest.approx(600_000 * PCT)


def test_renter_unchanged():
    _owner(home=0, monthly=0, years=0, balance=0)
    cfg.SPEND_RENT_MONTHLY = 2_000
    assert cfg.is_renter()
    assert cfg.home_carrying_cost_annual(cfg.HOME_VALUE) == 0.0
    for age in (cfg.YOUR_AGE, 60, 90):
        assert _expenses(age, True) == _expenses(age, False)


def test_pct_is_live():
    _owner(monthly=0, years=0, balance=0)
    cfg.HOME_CARRYING_COST_PCT = 0.02
    assert cfg.home_carrying_cost_annual(cfg.HOME_VALUE) == pytest.approx(12_000)


# --------------------------------------------------------------------------
# engine path (house move) -- accumulation, PRIMARY_PAYS_HOUSING, retirement
# --------------------------------------------------------------------------

def _house_move():
    """Old loan paid off at YOUR_AGE+3; move at +6; new 4-yr loan off at +10."""
    _owner(home=600_000, monthly=2_000, years=3, balance=60_000)
    cfg.HOUSE_MOVE_ENABLED = True
    cfg.HOUSE_MOVE_AGE = cfg.YOUR_AGE + 6
    cfg.NEW_HOME_VALUE = 900_000
    cfg.NEW_MORTGAGE_BALANCE = 150_000
    cfg.NEW_MORTGAGE_MONTHLY = 3_500
    cfg.NEW_MORTGAGE_YEARS = 4


def _expected_carry(age):
    a0 = cfg.YOUR_AGE
    if a0 + 3 <= age < a0 + 6:
        return 600_000 * PCT          # old home, paid off, not yet moved
    if age >= a0 + 10:
        return 900_000 * PCT          # new home, paid off
    return 0.0                        # a payment is owed


def test_engine_housing_after_house_move_uses_new_home_value():
    _house_move()
    p = sim.create_initial_portfolio()
    for age in range(cfg.YOUR_AGE, cfg.YOUR_AGE + 15):
        p.maybe_execute_house_move(age)
        owed = p.mortgage_expense_for_age(age)
        assert p.housing_expense_for_age(age) == pytest.approx(owed + _expected_carry(age))
    assert p.home_value == 900_000


def test_accumulation_living_delta_on_every_engine_path():
    """Working-year living (accumulation swap) gains exactly the carry."""
    _house_move()
    logs = {}
    for on in (True, False):
        cfg.MODEL_HOME_CARRYING_COST_AFTER_PAYOFF = on
        _, p = sim.run_detailed_simulation(cfg.YOUR_AGE + 14, random_seed=11)
        logs[on] = {r["age"]: r["living"] for r in p.spending_log
                    if r["age"] < cfg.YOUR_AGE + 14}
    assert len(logs[True]) == 14 and sorted(logs[True]) == sorted(logs[False])
    for age, living in logs[True].items():
        assert living - logs[False][age] == pytest.approx(_expected_carry(age)), age


def test_retirement_expenses_delta_after_house_move():
    _house_move()
    p = sim.create_initial_portfolio()
    p.maybe_execute_house_move(cfg.HOUSE_MOVE_AGE)
    age = cfg.YOUR_AGE + 20
    out = {}
    for on in (True, False):
        cfg.MODEL_HOME_CARRYING_COST_AFTER_PAYOFF = on
        out[on] = sim.calculate_retirement_expenses(age, IF, age, portfolio=p)
    assert out[True] - out[False] == pytest.approx(900_000 * PCT)


def test_primary_pays_housing_assigns_carry_to_primary():
    """Owner, no loan: the carry is housing, so the primary covers all of it --
    partner's brokerage is untouched, the primary's drops by the full amount."""
    _owner(home=500_000, monthly=0, years=0, balance=0)
    cfg.PRIMARY_PAYS_HOUSING = True
    deltas = {}
    for on in (True, False):
        cfg.MODEL_HOME_CARRYING_COST_AFTER_PAYOFF = on
        p = sim.create_initial_portfolio()
        y0 = p.accounts["your_brokerage"].balance
        q0 = p.accounts["partner_brokerage"].balance
        sim.simulate_accumulation_year(p, cfg.YOUR_AGE, 0.0)
        deltas[on] = (p.accounts["your_brokerage"].balance - y0,
                      p.accounts["partner_brokerage"].balance - q0)
    assert deltas[False][0] - deltas[True][0] == pytest.approx(500_000 * PCT)
    assert deltas[True][1] == pytest.approx(deltas[False][1])


# --------------------------------------------------------------------------
# toggle off == pre-fix behaviour
# --------------------------------------------------------------------------

def test_toggle_off_reduces_to_prefix_expressions():
    _house_move()
    cfg.MODEL_HOME_CARRYING_COST_AFTER_PAYOFF = False
    p = sim.create_initial_portfolio()
    for age in range(cfg.YOUR_AGE, 95):
        p.maybe_execute_house_move(age)
        assert cfg.owner_housing_annual(age) == (
            cfg.MORTGAGE_ANNUAL if cfg.has_mortgage(age) else 0.0)
        assert p.housing_expense_for_age(age) == p.mortgage_expense_for_age(age)


def test_toggle_off_full_run_ignores_pct():
    """With the toggle off the rate cannot reach any number the sim produces."""
    _house_move()
    cfg.MODEL_HOME_CARRYING_COST_AFTER_PAYOFF = False
    runs = []
    for pct in (0.0, 0.05):
        cfg.HOME_CARRYING_COST_PCT = pct
        ok, p = sim.run_detailed_simulation(cfg.YOUR_AGE + 20, random_seed=7)
        runs.append((ok, p.yearly_history, p.spending_log))
    assert runs[0] == runs[1]


# --------------------------------------------------------------------------
# UI single source of truth agrees with the engine
# --------------------------------------------------------------------------

def test_config_builder_translates_escrow_pct():
    assert build_config_overrides({"NEW_HOME_ESCROW_PCT": 0.02})["HOME_CARRYING_COST_PCT"] == 0.02
    # An explicit engine key wins over the UI convenience key.
    out = build_config_overrides({"NEW_HOME_ESCROW_PCT": 0.02, "HOME_CARRYING_COST_PCT": 0.01})
    assert out["HOME_CARRYING_COST_PCT"] == 0.01
    assert "HOME_CARRYING_COST_PCT" not in build_config_overrides({})


def _engine_housing_by_age(overrides, ages):
    from utils.sim_runner import _apply_overrides, _restore_overrides
    original = _apply_overrides(build_config_overrides(overrides))
    try:
        p = sim.create_initial_portfolio()
        out = {}
        for age in ages:
            p.maybe_execute_house_move(age)
            if sim._mortgage_swap_active(p):
                out[age] = p.housing_expense_for_age(age)
            else:
                out[age] = cfg.owner_housing_annual(age)
        return out
    finally:
        _restore_overrides(original)


def _assert_schedule_matches_engine(overrides):
    ages = list(range(int(overrides["YOUR_AGE"]), 91))
    engine = _engine_housing_by_age(overrides, ages)
    ui = mortgage_schedule(overrides, ages)["by_age"]
    for age in ages:
        assert ui[age]["housing"] == pytest.approx(engine[age], abs=0.01), age
    return ui


def test_mortgage_schedule_matches_engine_on_sample_household():
    from tests.conftest import load_sample_household
    prof = load_sample_household()
    ui = _assert_schedule_matches_engine(prof)
    # Spot-check the payoff boundary: new home carried after the new loan.
    payoff = prof["HOUSE_MOVE_AGE"] + prof["NEW_MORTGAGE_YEARS"]
    assert ui[payoff - 1]["housing"] == pytest.approx(prof["NEW_MORTGAGE_MONTHLY"] * 12)
    assert ui[payoff]["housing"] == pytest.approx(prof["NEW_HOME_VALUE"] * PCT)


@pytest.mark.parametrize("extra", [
    {},                                                         # loan, no move
    {"MORTGAGE_BALANCE": 0, "MORTGAGE_MONTHLY": 0,
     "MORTGAGE_YEARS_REMAINING": 0},                            # owner, no loan
    {"NEW_HOME_ESCROW_PCT": 0.02},                              # one input, both sides
    {"MODEL_HOME_CARRYING_COST_AFTER_PAYOFF": False},           # toggle off
])
def test_mortgage_schedule_matches_engine_synthetic(extra):
    o = {"YOUR_AGE": 40, "HOME_VALUE": 700_000, "MORTGAGE_BALANCE": 300_000,
         "MORTGAGE_MONTHLY": 3_200, "MORTGAGE_YEARS_REMAINING": 12,
         "HOUSE_MOVE_ENABLED": False}
    o.update(extra)
    _assert_schedule_matches_engine(o)
