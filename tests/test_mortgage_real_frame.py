"""Fixed-rate mortgages in the all-real (today's dollars) frame.

A fixed-rate loan's principal and interest is fixed in NOMINAL dollars, so in
today's dollars it shrinks by 1 / (1 + inflation) a year, while its escrow
(property tax + insurance) tracks prices and stays flat. The balance amortizes
in dollars of the day and is reported deflated. Extra principal is entered in
today's dollars. A purchase's loan is set in dollars of its year. The basis and
the home-sale exclusion are nominal. With EXPECTED_INFLATION = 0 every index is
1 and nothing changes. The UI mirrors (spending chart, net-worth projection,
home-sale path) must agree with the engine to the dollar.
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

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import account_simulation as sim  # noqa: E402
from retirement_sim.account_simulation import AccountPortfolio  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402
from utils.derived import mortgage_schedule  # noqa: E402

INFL = 0.025
PCT = 0.0135

# Fictional owner: 40, $600k home, $400k left on a 25-year loan at 6%.
PI = cfg.level_payment(400_000, 0.06, 25) * 12            # P&I a year
ESCROW = 600_000 * PCT
OWNER = {
    "YOUR_AGE": 40, "PARTNER_AGE": 0, "FILING_STATUS": "Single", "STATE_CHOICE": "TX",
    "YOUR_BASE_SALARY": 150_000, "YOUR_401K": 200_000, "YOUR_BROKERAGE": 300_000,
    "YOUR_CASH": 60_000, "SPEND_FOOD_MONTHLY": 800, "SPEND_OTHER_MONTHLY": 1_000,
    "HOME_VALUE": 600_000, "MORTGAGE_BALANCE": 400_000, "MORTGAGE_YEARS_REMAINING": 25,
    "MORTGAGE_MONTHLY": round((PI + ESCROW) / 12.0, 2), "MORTGAGE_RATE_FOR_PAYOFF": 0.06,
    "HOME_CARRYING_COST_PCT": PCT, "TARGET_RETIREMENT_AGE": 60,
    "EXPECTED_INFLATION": INFL, "ACTIVE_RETURN_SCENARIO": "pessimistic",
}
ALL_IN = OWNER["MORTGAGE_MONTHLY"] * 12
MOVE = {"age": 50, "action": "sell_buy", "price": 800_000, "down_pct": 0.25, "rate": 0.055,
        "years": 30, "costs": 12_000, "selling_cost_pct": 0.06}


@pytest.fixture(autouse=True)
def _restore_cfg(monkeypatch):
    saved = {k: copy.deepcopy(v) for k, v in vars(cfg).items() if k.isupper()}
    monkeypatch.setattr(sr, "_disk", lambda: None)
    sr.clear_cache(include_disk=False)
    yield
    for k, v in saved.items():
        setattr(cfg, k, v)
    sr.clear_cache(include_disk=False)


@contextmanager
def applied(overrides):
    original = sr._apply_overrides(build_config_overrides(overrides))
    try:
        yield
    finally:
        sr._restore_overrides(original)


def _nominal_balances(balance, rate, years, n_years, extra_nominal=lambda y: 0.0):
    """Independent nominal amortization: start-of-year balances, extra monthly."""
    pmt, r, out = cfg.level_payment(balance, rate, years), rate / 12.0, []
    bal = balance
    for y in range(n_years):
        out.append(bal)
        for _ in range(12):
            if bal <= 0:
                break
            after = bal * (1 + r) - pmt
            if after <= 0:
                bal = 0.0
                break
            bal = after - min(extra_nominal(y) / 12.0, after)
            if bal < 0.01:
                bal = 0.0
                break
    return out


def _engine_walk(ages):
    """The engine's housing (config term + timeline swap) and the yearly record,
    walked one plan year at a time the way the simulation crosses years."""
    p = AccountPortfolio()
    p.record_year(cfg.CURRENT_YEAR, cfg.YOUR_AGE)
    housing = {}
    for age in ages:
        p.apply_housing_events(age)
        housing[age] = cfg.housing_annual(age) + sim._housing_swap_delta(p, age)
        p.record_year(cfg.CURRENT_YEAR + age - cfg.YOUR_AGE + 1, age + 1)
    return housing, {row["age"]: row for row in p.yearly_history}


# ------------------------------------------------------------------ helpers


def test_cpi_index_and_payment_deflation():
    with applied(OWNER):
        assert cfg.cpi_index(40) == 1.0 and cfg.cpi_index(39) == 1.0
        assert cfg.cpi_index(50) == pytest.approx(1.025 ** 10)
        assert cfg.cpi_index(50, 45, 0.03) == pytest.approx(1.03 ** 5)
    # A deflator of exactly 1 hands the payment back untouched (bit-exact).
    assert cfg.deflate_loan_payment(12_345, 7_000, 1.0) == 12_345
    assert cfg.deflate_loan_payment(10_000, 4_000, 0.5) == pytest.approx(4_000 + 3_000)
    # Escrow never exceeds the payment.
    assert cfg.mortgage_escrow_annual(5_000, 1_000_000, 0.0135) == 5_000


# ------------------------------------------------------------------ engine


def test_year_k_pi_shrinks_by_inflation_and_escrow_stays_flat():
    with applied(OWNER):
        for k in (0, 1, 5, 24):
            want = ESCROW + (ALL_IN - ESCROW) / 1.025 ** k
            assert cfg.housing_annual(40 + k) == pytest.approx(want, abs=1e-6)
            assert cfg.owner_housing_annual(40 + k) == pytest.approx(want, abs=1e-6)
        # Payoff timing is the term's; afterwards only the flat carrying cost.
        for age in (65, 70, 90):
            assert cfg.housing_annual(age) == pytest.approx(ESCROW)


def test_guardrails_fixed_housing_slice_is_the_deflated_payment():
    with applied(OWNER):
        assert sim._retirement_housing_expense(60, 1.0, None) == pytest.approx(cfg.housing_annual(60))
        assert cfg.housing_annual(60) < ALL_IN


def test_renters_are_unaffected_by_inflation():
    renter = {**OWNER, "HOME_VALUE": 0, "MORTGAGE_BALANCE": 0, "MORTGAGE_MONTHLY": 0,
              "MORTGAGE_YEARS_REMAINING": 0, "SPEND_RENT_MONTHLY": 2_000}
    for infl in (0.0, 0.05):
        with applied({**renter, "EXPECTED_INFLATION": infl}):
            assert [cfg.housing_annual(a) for a in (40, 60, 85)] == [24_000.0] * 3


def test_balance_amortizes_nominally_and_is_reported_deflated():
    with applied(OWNER):
        _, rec = _engine_walk(range(40, 70))
    nominal = _nominal_balances(400_000, 0.06, 25, 30)
    for k in range(30):
        assert rec[40 + k]["mortgage_balance"] == pytest.approx(nominal[k] / 1.025 ** k, abs=0.01)
    assert rec[65]["mortgage_balance"] == 0.0               # term unchanged
    assert rec[50]["home_value"] == 600_000                  # value flat in today's dollars


def test_extra_principal_is_todays_dollars_paid_in_dollars_of_the_year():
    ov = {**OWNER, "EXTRA_MORTGAGE_PAYMENT_ANNUAL": 10_000}
    with applied(ov):
        housing, rec = _engine_walk(range(40, 70))
    nominal = _nominal_balances(400_000, 0.06, 25, 30, lambda y: 10_000 * 1.025 ** y)
    payoff = next(k for k in range(30) if nominal[k] == 0.0)
    for k in range(payoff):
        assert rec[40 + k]["mortgage_balance"] == pytest.approx(nominal[k] / 1.025 ** k, abs=0.01)
    # A year with plenty of loan left costs the deflated schedule + the full
    # today's-dollar extra; after payoff only the carrying cost.
    k = 3
    assert housing[40 + k] == pytest.approx(ESCROW + (ALL_IN - ESCROW) / 1.025 ** k + 10_000, abs=1e-6)
    assert housing[40 + payoff] == pytest.approx(ESCROW)
    # The deterministic payoff projection agrees with the engine.
    with applied(ov):
        assert sim.mortgage_payoff_projection(10_000)["payoff_age"] == 40 + payoff


def test_home_event_loan_is_set_in_dollars_of_its_year():
    ov = {**OWNER, "HOME_EVENTS": [MOVE]}
    with applied(ov):
        housing, rec = _engine_walk(range(40, 85))
        loan_nominal = 600_000 * cfg.cpi_index(50)
    ev_pi = cfg.level_payment(600_000, 0.055, 30) * 12
    ev_escrow = 800_000 * PCT
    for k in (0, 1, 10, 29):
        assert housing[50 + k] == pytest.approx(ev_escrow + ev_pi / 1.025 ** k, rel=1e-9)
    nominal = _nominal_balances(loan_nominal, 0.055, 30, 31)
    for k in (1, 10, 29, 30):
        assert rec[50 + k]["mortgage_balance"] == pytest.approx(
            nominal[k] / 1.025 ** (10 + k), abs=0.01)
    assert housing[80] == pytest.approx(ev_escrow)            # paid off at 80


def test_sale_proceeds_and_gain_tax_use_the_real_balance_and_nominal_basis():
    ov = {**OWNER, "HOME_COST_BASIS": 150_000, "HOME_EVENTS": [MOVE]}
    with applied(ov):
        p = AccountPortfolio()
        p.record_year(cfg.CURRENT_YEAR, 40)
        for age in range(40, 50):
            p.record_year(cfg.CURRENT_YEAR + age - 39, age + 1)
        cpi = cfg.cpi_index(50)
        nominal_left = p.mortgage_balance
        assert p.real_mortgage_balance(50) == pytest.approx(nominal_left / cpi)
        taxed = {}
        p._tax_home_sale_gain = lambda gain: taxed.setdefault("gain", gain) and 0.0
        before = p.get_total_balance()
        p._sell_home(50, 0.06)
        proceeds = p.get_total_balance() - before
    assert proceeds == pytest.approx(600_000 - nominal_left / cpi - 36_000)
    # Basis and the $250k exclusion are nominal, so both shrink in today's dollars.
    assert taxed["gain"] == pytest.approx(600_000 - 36_000 - 150_000 / cpi - 250_000 / cpi)


def test_equity_reserve_uses_the_real_balance():
    with applied(OWNER):
        _, rec = _engine_walk(range(40, 52))
        want = (600_000 - rec[51]["mortgage_balance"]) * cfg.HOME_EQUITY_ACCESSIBLE_PCT
    assert rec[51]["home_equity"] == pytest.approx(want)


# ------------------------------------------------------------------ inflation 0


@pytest.mark.parametrize("extra", [
    {},
    {"EXTRA_MORTGAGE_PAYMENT_ANNUAL": 9_000},
    {"HOME_COST_BASIS": 150_000, "HOME_EVENTS": [MOVE, {"age": 72, "action": "sell_rent",
                                                        "rent": 2_000, "costs": 5_000}]},
])
def test_zero_inflation_reproduces_the_flat_frame_exactly(monkeypatch, extra):
    """With no inflation the conversion is a no-op, bit for bit: the same seeded
    run equals the old flat frame, where the all-in payment is charged as is
    and no amount is converted (every CPI index 1)."""
    ov = {**OWNER, **extra, "EXPECTED_INFLATION": 0.0}

    def run():
        with applied(ov):
            ok, p = sim.run_detailed_simulation(55, random_seed=7)
        return ok, p.yearly_history, p.spending_log, p.withdrawal_log, p.total_taxes_paid

    a = run()
    monkeypatch.setattr(cfg, "cpi_index", lambda *a, **k: 1.0)
    monkeypatch.setattr(cfg, "mortgage_real_annual", lambda all_in, *a, **k: all_in)
    assert run() == a


def test_zero_inflation_keeps_the_all_in_payment_flat():
    with applied({**OWNER, "EXPECTED_INFLATION": 0.0}):
        assert [cfg.housing_annual(a) for a in (40, 50, 64)] == [ALL_IN] * 3


# ------------------------------------------------------------------ UI mirrors


@pytest.mark.parametrize("extra", [
    {},
    {"EXTRA_MORTGAGE_PAYMENT_ANNUAL": 12_000, "EXTRA_MORTGAGE_PAYMENT_STOP_AGE": 48},
    {"HOME_EVENTS": [MOVE, {"age": 75, "action": "sell_rent", "rent": 2_500, "costs": 5_000}]},
    {"EXPECTED_INFLATION": 0.0, "HOME_EVENTS": [MOVE]},
])
def test_spending_chart_housing_matches_the_engine_to_the_dollar(extra):
    from components import spending_chart as sp
    ov = {**OWNER, **extra}
    ages = list(range(40, 91))
    series, _, payoff = sp._compute_housing_series(ov, ages)
    with applied(ov):
        housing, _ = _engine_walk(ages)
    for age, v in zip(ages, series):
        assert v == pytest.approx(housing[age], abs=0.01), age


def test_spending_chart_future_dollars_keeps_pi_flat_in_dollars():
    from components import spending_chart as sp
    ages = list(range(40, 66))
    factors = [1.025 ** (a - 40) for a in ages]
    series, _ = sp.build_category_series(ages, OWNER, {}, 60, inflation_factors=factors)
    housing = next(ys for label, _, ys in series if label.startswith("Housing"))
    for a, v in zip(ages, housing):
        want = (ALL_IN - ESCROW + ESCROW * 1.025 ** (a - 40)) if a < 65 else ESCROW * 1.025 ** (a - 40)
        assert v == pytest.approx(want, abs=0.01)


def test_mortgage_schedule_balance_is_the_engines():
    ov = {**OWNER, "EXTRA_MORTGAGE_PAYMENT_ANNUAL": 6_000, "HOME_EVENTS": [MOVE]}
    ages = list(range(40, 85))
    sched = mortgage_schedule(ov, ages)["by_age"]
    with applied(ov):
        _, rec = _engine_walk(ages)
    for age in ages:
        if age != MOVE["age"]:          # the engine records before that year's move
            assert sched[age]["balance"] == pytest.approx(rec[age]["mortgage_balance"], abs=0.01), age


@pytest.mark.parametrize("extra", [{}, {"EXTRA_MORTGAGE_PAYMENT_ANNUAL": 12_000},
                                   {"HOME_EVENTS": [MOVE]}])
def test_net_worth_projection_home_equity_matches_the_engine(extra):
    from components.net_worth_projection_chart import project_net_worth
    ov = {**OWNER, **extra, "TARGET_RETIREMENT_AGE": 70}      # pessimistic: home value flat
    proj = project_net_worth(ov)
    equity = dict(zip(proj["ages"], proj["by_account"]["Home equity"]))
    with applied(ov):
        _, rec = _engine_walk(range(40, 71))
    for age, v in equity.items():
        if age != 50:
            row = rec[age]
            assert v == pytest.approx(max(0.0, row["home_value"] - row["mortgage_balance"]), abs=0.01), age


def test_home_sale_path_uses_the_real_balance_and_the_engines_housing():
    ov = {**OWNER, "HOME_EVENTS": [MOVE]}
    path = sr.home_sale_path(ov, 70)
    with applied(ov):
        housing, rec = _engine_walk(range(40, 71))
    for age in (45, 49):
        assert path["proceeds"][age] == pytest.approx(
            600_000 - rec[age]["mortgage_balance"] - 36_000, abs=0.01)
    for age in range(40, 71):
        assert path["housing"][age] == pytest.approx(housing[age], abs=0.01), age
