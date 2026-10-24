"""Spending guardrails hold housing fixed (MODEL_GUARDRAILS_EXCLUDE_HOUSING).

Housing can't be cut in a downturn, yet the guardrail used to treat a flat
DISCRETIONARY_EXPENSE_RATIO of TOTAL expenses -- housing included -- as
cuttable. The rule pinned here:

  * toggle on  -> discretionary = ratio x (expenses - housing_this_year), where
                  housing_this_year is the exact housing term inside
                  ``expenses`` (mortgage while owed, post-payoff carrying cost,
                  rent; config path or engine house-move path);
  * toggle off -> byte-identical to the pre-fix guardrail;
  * the combined multiplier is clamped to
    [GUARDRAIL_MIN_DISCRETIONARY_FACTOR, GUARDRAIL_MAX_DISCRETIONARY_FACTOR].
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


def _owner(home=1_000_000, monthly=10_000, years=10, balance=900_000):
    cfg.HOME_VALUE = home
    cfg.MORTGAGE_BALANCE = balance
    cfg.MORTGAGE_MONTHLY = monthly
    cfg.MORTGAGE_ANNUAL = monthly * 12
    cfg.MORTGAGE_YEARS_REMAINING = years
    cfg.HOUSE_MOVE_ENABLED = False
    cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL = 0.0
    cfg.HOME_CARRYING_COST_PCT = PCT
    cfg.MODEL_HOME_CARRYING_COST_AFTER_PAYOFF = True


def _renter(rent_monthly=3_000):
    _owner(home=0, monthly=0, years=0, balance=0)
    cfg.SPEND_RENT_MONTHLY = rent_monthly


def _house_move():
    """Old loan off at YOUR_AGE+3; move at +6 to a 900k home, new loan off at +10."""
    _owner(home=600_000, monthly=2_000, years=3, balance=60_000)
    cfg.HOUSE_MOVE_ENABLED = True
    cfg.HOUSE_MOVE_AGE = cfg.YOUR_AGE + 6
    cfg.NEW_HOME_VALUE = 900_000
    cfg.NEW_MORTGAGE_BALANCE = 150_000
    cfg.NEW_MORTGAGE_MONTHLY = 3_500
    cfg.NEW_MORTGAGE_YEARS = 4


def _force_adjustment(portfolio_factor, return_factor=1.0):
    """Pin the guardrail multipliers so the expected split is exact."""
    cfg.calculate_spending_adjustment = lambda cur, tgt: portfolio_factor
    cfg.calculate_return_based_spending_adjustment = lambda r: return_factor


_STUB = types.SimpleNamespace(get_total_balance=lambda: 1.0,
                              target_portfolio_inflation_adjusted=1.0)


def _old_guardrails(portfolio, expenses, annual_return, *_ignored):
    """The pre-fix ``_apply_spending_guardrails``, verbatim."""
    discretionary_ratio = cfg.DISCRETIONARY_EXPENSE_RATIO
    fixed_expenses = expenses * (1 - discretionary_ratio)
    discretionary_expenses = expenses * discretionary_ratio
    portfolio_adjustment = cfg.calculate_spending_adjustment(
        portfolio.get_total_balance(),
        portfolio.target_portfolio_inflation_adjusted
    )
    return_adjustment = cfg.calculate_return_based_spending_adjustment(annual_return)
    combined_discretionary_adjustment = portfolio_adjustment * return_adjustment
    combined_discretionary_adjustment = max(0.60, min(1.40, combined_discretionary_adjustment))
    adjusted_discretionary = discretionary_expenses * combined_discretionary_adjustment
    return fixed_expenses + adjusted_discretionary


def _guard(expenses, age, portfolio=_STUB):
    return sim._apply_spending_guardrails(portfolio, expenses, 0.0, age, 1.0)


def test_defaults():
    assert cfg.MODEL_GUARDRAILS_EXCLUDE_HOUSING is True
    assert cfg.GUARDRAIL_MIN_DISCRETIONARY_FACTOR == 0.60
    assert cfg.GUARDRAIL_MAX_DISCRETIONARY_FACTOR == 1.40


# --------------------------------------------------------------------------
# housing_this_year is exactly the housing term inside ``expenses``
# --------------------------------------------------------------------------

def _non_housing(age, portfolio=None):
    return (sim.calculate_retirement_expenses(age, IF, age, portfolio=portfolio)
            - sim._retirement_housing_expense(age, 1.0, portfolio))


def test_housing_helper_matches_expense_total_config_path():
    """expenses - housing == the same expenses with every housing input zeroed,
    across mortgage years, payoff, and the 75+ late-retirement scaling."""
    _owner(years=20)
    ages = range(cfg.YOUR_AGE + 15, 95)
    with_housing = {a: _non_housing(a) for a in ages}
    cfg.MORTGAGE_ANNUAL = 0
    cfg.MODEL_HOME_CARRYING_COST_AFTER_PAYOFF = False
    for a in ages:
        assert sim._retirement_housing_expense(a) == 0.0
        assert with_housing[a] == pytest.approx(
            sim.calculate_retirement_expenses(a, IF, a), abs=1e-6), a


def test_housing_helper_matches_expense_total_engine_path():
    """After a house move the engine swap is part of housing: non-housing is the
    same whether or not the engine's loan state is consulted."""
    _house_move()
    p = sim.create_initial_portfolio()
    for age in range(cfg.YOUR_AGE, cfg.YOUR_AGE + 15):
        p.maybe_execute_house_move(age)
        assert sim._mortgage_swap_active(p)
        assert sim._retirement_housing_expense(age, 1.0, p) == pytest.approx(
            p.housing_expense_for_age(age))
        assert _non_housing(age, p) == pytest.approx(_non_housing(age), abs=1e-6), age


# --------------------------------------------------------------------------
# the guardrail split
# --------------------------------------------------------------------------

def test_big_mortgage_year_cuts_only_nonhousing():
    _owner()
    _force_adjustment(0.80)
    age = cfg.YOUR_AGE + 5                     # mortgage still owed
    expenses = sim.calculate_retirement_expenses(age, IF, age)
    housing = sim._retirement_housing_expense(age)
    assert housing == cfg.MORTGAGE_ANNUAL == 120_000
    ratio = cfg.DISCRETIONARY_EXPENSE_RATIO
    cut = expenses - _guard(expenses, age)
    assert cut == pytest.approx(0.20 * ratio * (expenses - housing))
    # ...strictly less than the old ratio-of-total cut.
    assert cut < 0.20 * ratio * expenses


def test_after_payoff_carrying_cost_is_fixed():
    _owner(years=5)
    _force_adjustment(0.80)
    for age in (cfg.YOUR_AGE + 5, cfg.YOUR_AGE + 30, 80):   # 80: later years
        expenses = sim.calculate_retirement_expenses(age, IF, age)
        housing = sim._retirement_housing_expense(age)
        # The later-years drop used to scale housing by 0.85 too; property tax
        # and insurance don't fall because you travel less, so it no longer does.
        assert housing == pytest.approx(1_000_000 * PCT)  # _owner's home
        cut = expenses - _guard(expenses, age)
        assert cut == pytest.approx(
            0.20 * cfg.DISCRETIONARY_EXPENSE_RATIO * (expenses - housing))


def test_renter_rent_is_fixed():
    _renter(3_000)
    _force_adjustment(0.80)
    age = cfg.YOUR_AGE + 20
    expenses = sim.calculate_retirement_expenses(age, IF, age)
    assert sim._retirement_housing_expense(age) == 36_000
    cut = expenses - _guard(expenses, age)
    assert cut == pytest.approx(0.20 * cfg.DISCRETIONARY_EXPENSE_RATIO * (expenses - 36_000))


def test_house_move_engine_housing_is_fixed():
    _house_move()
    _force_adjustment(0.80)
    p = sim.create_initial_portfolio()
    p.set_retirement_baseline()
    age = cfg.HOUSE_MOVE_AGE + 1                # new 3,500/mo loan owed
    p.maybe_execute_house_move(cfg.HOUSE_MOVE_AGE)
    expenses = sim.calculate_retirement_expenses(age, IF, age, portfolio=p)
    assert sim._retirement_housing_expense(age, 1.0, p) == pytest.approx(42_000)
    cut = expenses - _guard(expenses, age, p)
    assert cut == pytest.approx(0.20 * cfg.DISCRETIONARY_EXPENSE_RATIO * (expenses - 42_000))


def test_simulate_retirement_year_passes_age_through():
    """End-to-end wiring: the recorded guardrail-adjusted living spend uses the
    housing-excluded split inside simulate_retirement_year."""
    _owner()
    _force_adjustment(0.80)
    age = cfg.YOUR_AGE + 5
    expenses = sim.calculate_retirement_expenses(age, IF, age)
    p = sim.create_initial_portfolio()
    p.set_retirement_baseline()
    sim.simulate_retirement_year(p, age, expenses, 0.0, 1.0, age)
    expected = expenses - 0.20 * cfg.DISCRETIONARY_EXPENSE_RATIO * (expenses - 120_000)
    assert p.spending_log[-1]["living"] == pytest.approx(expected)


def test_housing_capped_at_expenses_for_direct_callers():
    _owner()
    _force_adjustment(0.50)
    age = cfg.YOUR_AGE + 5
    assert _guard(50_000.0, age) == 50_000.0     # all fixed, nothing to cut


# --------------------------------------------------------------------------
# toggle off == pre-fix behaviour
# --------------------------------------------------------------------------

@pytest.mark.parametrize("factor", [0.30, 0.80, 0.95, 1.20, 2.00])
def test_toggle_off_matches_old_formula_exactly(factor):
    _owner()
    _force_adjustment(factor)
    cfg.MODEL_GUARDRAILS_EXCLUDE_HOUSING = False
    for age in (cfg.YOUR_AGE + 5, cfg.YOUR_AGE + 30, 80):
        expenses = sim.calculate_retirement_expenses(age, IF, age)
        assert _guard(expenses, age) == _old_guardrails(_STUB, expenses, 0.0)


def test_toggle_on_without_housing_matches_old_formula_exactly():
    _renter(0)
    _force_adjustment(0.80)
    age = cfg.YOUR_AGE + 20
    expenses = sim.calculate_retirement_expenses(age, IF, age)
    assert _guard(expenses, age) == _old_guardrails(_STUB, expenses, 0.0)


@pytest.fixture(params=[True, False], ids=["house_move", "config_mortgage"])
def mortgage_in_retirement(request):
    """The sample household retiring at 42 with a mortgage still owed: via the
    engine house-move path (moves at 36, 15-year loan) or the original config
    loan (15 years left at 34)."""
    from tests.conftest import load_sample_household
    from utils.config_builder import build_config_overrides
    from utils.sim_runner import _apply_overrides, _restore_overrides
    ov = load_sample_household()
    ov["HOUSE_MOVE_ENABLED"] = request.param
    original = _apply_overrides(build_config_overrides(ov))
    try:
        assert cfg.has_mortgage(42) or request.param
        yield 42
    finally:
        _restore_overrides(original)


def _paths(retire, seeds=range(6)):
    out = []
    for s in seeds:
        ok, p = sim.run_detailed_simulation(retire, random_seed=s)
        out.append((ok, p.yearly_history, p.spending_log, p.withdrawal_log))
    return out


def test_toggle_off_full_run_is_byte_identical(mortgage_in_retirement, monkeypatch):
    cfg.MODEL_GUARDRAILS_EXCLUDE_HOUSING = False
    # _old_guardrails hardcodes the pre-fix 0.60/1.40 clamp; the profile may set its own.
    monkeypatch.setattr(cfg, "GUARDRAIL_MIN_DISCRETIONARY_FACTOR", 0.60)
    monkeypatch.setattr(cfg, "GUARDRAIL_MAX_DISCRETIONARY_FACTOR", 1.40)
    new = _paths(mortgage_in_retirement)
    monkeypatch.setattr(sim, "_apply_spending_guardrails", _old_guardrails)
    old = _paths(mortgage_in_retirement)
    assert new == old


def test_toggle_on_changes_a_mortgage_heavy_run(mortgage_in_retirement):
    """The toggle reaches the engine: guardrails bind on some path, fewer
    dollars get cut, so the paired-seed trajectories differ."""
    runs = {}
    for on in (True, False):
        cfg.MODEL_GUARDRAILS_EXCLUDE_HOUSING = on
        runs[on] = _paths(mortgage_in_retirement)
    assert runs[True] != runs[False]


# --------------------------------------------------------------------------
# clamp bounds are config
# --------------------------------------------------------------------------

@pytest.mark.parametrize("exclude", [True, False])
def test_clamp_params_respected(exclude):
    _owner()
    cfg.MODEL_GUARDRAILS_EXCLUDE_HOUSING = exclude
    age = cfg.YOUR_AGE + 5
    expenses = sim.calculate_retirement_expenses(age, IF, age)
    housing = sim._retirement_housing_expense(age) if exclude else 0.0
    disc = cfg.DISCRETIONARY_EXPENSE_RATIO * (expenses - housing)

    def adjusted(factor):
        return expenses - disc + disc * factor

    _force_adjustment(0.30)                                   # below default floor
    assert _guard(expenses, age) == pytest.approx(adjusted(0.60))
    cfg.GUARDRAIL_MIN_DISCRETIONARY_FACTOR = 0.50
    assert _guard(expenses, age) == pytest.approx(adjusted(0.50))
    cfg.GUARDRAIL_MIN_DISCRETIONARY_FACTOR = 0.0
    assert _guard(expenses, age) == pytest.approx(adjusted(0.30))

    _force_adjustment(2.00)                                   # above default cap
    assert _guard(expenses, age) == pytest.approx(adjusted(1.40))
    cfg.GUARDRAIL_MAX_DISCRETIONARY_FACTOR = 1.10
    assert _guard(expenses, age) == pytest.approx(adjusted(1.10))


# --------------------------------------------------------------------------
# UI override path reaches the engine
# --------------------------------------------------------------------------

def test_ui_overrides_reach_cfg_and_restore():
    from utils.config_builder import build_config_overrides
    from utils.sim_runner import _apply_overrides, _restore_overrides, audit_override_keys
    ui = {"MODEL_GUARDRAILS_EXCLUDE_HOUSING": False,
          "GUARDRAIL_MIN_DISCRETIONARY_FACTOR": 0.70,
          "GUARDRAIL_MAX_DISCRETIONARY_FACTOR": 1.10}
    built = build_config_overrides(ui)
    for k, v in ui.items():
        assert built[k] == v
    assert audit_override_keys(built) == []
    original = _apply_overrides(built)
    try:
        for k, v in ui.items():
            assert getattr(cfg, k) == v
    finally:
        _restore_overrides(original)
    assert cfg.MODEL_GUARDRAILS_EXCLUDE_HOUSING is True
    assert cfg.GUARDRAIL_MIN_DISCRETIONARY_FACTOR == 0.60
    assert cfg.GUARDRAIL_MAX_DISCRETIONARY_FACTOR == 1.40
