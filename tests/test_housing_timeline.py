"""Housing timeline (HOME_EVENTS): buy, sell and buy, sell and rent.

Today's home is HOME_VALUE / MORTGAGE_* (rate MORTGAGE_RATE_FOR_PAYOFF) or
SPEND_RENT_MONTHLY; cfg.housing_events() adds the dated events, with the old
single house move (HOUSE_MOVE_*) converted into one more event.

Fixtures (fictional): ``renter_buyer.json`` (couple renting at $2,000/mo who buy
a $450k home at 30) and ``downsizer.json`` (single owner of a paid-off $650k
home, bought for $200k, who sells and rents at 72).
"""
import copy
import os
import sys
from contextlib import contextmanager

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import account_simulation as sim  # noqa: E402
from retirement_sim.account_simulation import Account, AccountPortfolio, AccountType  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402
from utils.derived import housing_timeline, mortgage_schedule  # noqa: E402
from utils.profile_io import deserialize_overrides  # noqa: E402
from tests.conftest import load_sample_household  # noqa: E402

PCT = 0.0135


def _fixture(name):
    with open(os.path.join(_TESTS, "fixtures", f"{name}.json"), encoding="utf-8") as fh:
        return deserialize_overrides(fh.read())


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


def _run(overrides, retirement_age, seed=11):
    with applied(overrides):
        ok, p = sim.run_detailed_simulation(retirement_age, random_seed=seed)
    return ok, p


def _fingerprint(p):
    return (p.yearly_history, p.spending_log, p.withdrawal_log, p.total_taxes_paid,
            p.total_aca_premiums, p.total_medicare_premiums)


def _living(p):
    return {row["age"]: row["living"] for row in p.spending_log}


def _as_events(overrides):
    """The same plan with its legacy house move written as HOME_EVENTS."""
    out = {k: v for k, v in overrides.items()
           if k not in ("HOUSE_MOVE_AGE", "NEW_HOME_VALUE", "NEW_MORTGAGE_BALANCE",
                        "NEW_MORTGAGE_MONTHLY", "NEW_MORTGAGE_YEARS", "NEW_MORTGAGE_RATE")}
    out["HOUSE_MOVE_ENABLED"] = False
    out["HOME_EVENTS"] = housing_timeline({**overrides, "HOME_EVENTS": []})
    return out


# ---------------------------------------------------------------------------
# 1. Old saved plans: legacy keys == the equivalent timeline, bit for bit
# ---------------------------------------------------------------------------

def test_legacy_owner_move_equals_its_timeline():
    """An owner with one planned move (the sample household): the old keys and
    the same move as a HOME_EVENTS entry give identical simulations."""
    legacy = load_sample_household()
    assert legacy["HOUSE_MOVE_ENABLED"] is True
    timeline = _as_events(legacy)
    assert len(timeline["HOME_EVENTS"]) == 1
    assert timeline["HOME_EVENTS"][0]["action"] == cfg.HOME_SELL_BUY
    ra = int(legacy["TARGET_RETIREMENT_AGE"])
    a, b = _run(legacy, ra), _run(timeline, ra)
    assert a[0] == b[0] and _fingerprint(a[1]) == _fingerprint(b[1])


def test_legacy_renter_move_equals_its_timeline():
    """A renter with the old house move becomes a plain purchase (rent stops)."""
    legacy = {**_fixture("renter_buyer"), "HOME_EVENTS": [],
              "HOUSE_MOVE_ENABLED": True, "HOUSE_MOVE_AGE": 30, "NEW_HOME_VALUE": 450_000,
              "NEW_MORTGAGE_BALANCE": 360_000, "NEW_MORTGAGE_MONTHLY": 2_782,
              "NEW_MORTGAGE_YEARS": 30, "NEW_MORTGAGE_RATE": 0.065}
    timeline = _as_events(legacy)
    assert timeline["HOME_EVENTS"][0]["action"] == cfg.HOME_BUY
    a, b = _run(legacy, 60), _run(timeline, 60)
    assert _fingerprint(a[1]) == _fingerprint(b[1])


def test_legacy_shim_event_fields():
    with applied(load_sample_household()):
        (e,) = cfg.housing_events()
        assert e == {"age": cfg.HOUSE_MOVE_AGE, "action": cfg.HOME_SELL_BUY,
                     "costs": cfg.HOUSE_MOVING_COSTS,
                     "selling_cost_pct": cfg.HOME_SELLING_COST_PCT,
                     "price": cfg.NEW_HOME_VALUE, "loan": cfg.NEW_MORTGAGE_BALANCE,
                     "rate": cfg.new_mortgage_rate(), "years": cfg.NEW_MORTGAGE_YEARS,
                     "monthly": cfg.NEW_MORTGAGE_MONTHLY}


@pytest.mark.parametrize("plan", [
    {"SPEND_RENT_MONTHLY": 1_800},                                   # renter, no move
    {"HOME_VALUE": 500_000, "MORTGAGE_BALANCE": 300_000,             # owner, no move
     "MORTGAGE_MONTHLY": 2_400, "MORTGAGE_YEARS_REMAINING": 25},
], ids=["renter", "owner"])
def test_no_events_is_the_untouched_path(plan):
    """Without a timeline the engine never consults its own home state: an
    empty HOME_EVENTS is the same plan as no key at all."""
    a, b = _run(plan, 55), _run({**plan, "HOME_EVENTS": []}, 55)
    assert _fingerprint(a[1]) == _fingerprint(b[1])
    with applied(plan):
        assert cfg.housing_events() == [] and not sim._housing_timeline_on()


def test_malformed_events_are_skipped():
    cfg.HOME_EVENTS = [{"action": "buy"}, {"age": "x", "action": "buy"},
                       {"age": 40, "action": "teleport"}, "nonsense",
                       {"age": 40, "action": "sell_rent", "rent": 1_000}]
    assert [e["action"] for e in cfg.housing_events()] == [cfg.HOME_SELL_RENT]


# ---------------------------------------------------------------------------
# 2. A renter who buys stops paying rent (finding R6)
# ---------------------------------------------------------------------------

def test_renter_who_buys_at_30_stops_paying_rent():
    ov = _fixture("renter_buyer")
    ok, p = _run(ov, 60)
    living = _living(p)
    with applied(ov):
        (e,) = cfg.housing_events()
    # Same base both years; only housing changes: $24k rent -> the all-in payment.
    # (The bug kept the rent: the step was the whole payment.)
    assert living[30] - living[29] == pytest.approx(e["monthly"] * 12 - 24_000)
    # In retirement, after the 30-year loan: the home's tax + insurance, no rent.
    with applied(ov):
        q = sim.create_initial_portfolio()
        for age in range(27, 66):
            q.apply_housing_events(age)
        assert q.housing_expense_for_age(65) == pytest.approx(450_000 * PCT)
        assert sim._retirement_housing_expense(65, 1.0, q) == pytest.approx(450_000 * PCT)


def test_ui_schedule_mirrors_engine_for_renter_who_buys():
    ov = _fixture("renter_buyer")
    ages = list(range(27, 93))
    ui = mortgage_schedule(ov, ages)["by_age"]
    with applied(ov):
        p = sim.create_initial_portfolio()
        for age in ages:
            p.apply_housing_events(age)
            assert ui[age]["housing"] == pytest.approx(p.housing_expense_for_age(age), abs=0.01), age
            assert ui[age]["owns"] is p.owns_home()
    # Renting until 30 (used to be treated as an owner from day 1, with no rent).
    assert ui[29]["housing"] == 24_000 and ui[29]["owns"] is False


# ---------------------------------------------------------------------------
# 3. An owner who downsizes to renting at 72
# ---------------------------------------------------------------------------

def test_downsizer_sells_and_rents_at_72():
    ov = _fixture("downsizer")
    with applied(ov):
        p = sim.create_initial_portfolio()
        p.update_ages(72)
        assert p.housing_expense_for_age(71) == pytest.approx(650_000 * PCT)
        before = p.get_total_balance()
        assert p.apply_housing_events(72) is True
        # Gain 650k - 39k selling - 200k basis = 411k; a single owner excludes
        # 250k, so 161k is a taxed long-term gain.
        assert p.total_taxes_paid > 0
        proceeds = p.get_total_balance() - before + 5_000          # + moving costs
        assert 650_000 * 0.94 - 161_000 * 0.25 < proceeds < 650_000 * 0.94
        assert not p.owns_home() and p.home_equity == 0
        assert p.housing_expense_for_age(73) == 30_000
        # The later-years drop (from 75) leaves the rent alone.
        assert sim._retirement_housing_expense(80, 1.0, p) == 30_000
    ui = mortgage_schedule(ov, range(58, 96))["by_age"]
    assert ui[71]["housing"] == pytest.approx(650_000 * PCT) and ui[71]["owns"]
    assert ui[72]["housing"] == 30_000 and not ui[72]["owns"]


def test_downsizer_full_run_completes():
    ok, p = _run(_fixture("downsizer"), 63)
    assert p.yearly_history[-1]["age"] == 95 or not ok
    row72 = next(r for r in p.yearly_history if r["age"] == 73)
    assert row72["home_value"] == 0 and row72["mortgage_balance"] == 0


# ---------------------------------------------------------------------------
# 4. Two moves
# ---------------------------------------------------------------------------

def test_two_moves_switch_loans_and_payoff():
    ov = {**_fixture("renter_buyer"), "HOME_EVENTS": [
        {"age": 30, "action": "buy", "price": 450_000, "down_pct": 0.2, "rate": 0.065,
         "years": 30, "costs": 10_000},
        {"age": 45, "action": "sell_buy", "price": 800_000, "down_pct": 0.25, "rate": 0.055,
         "years": 15, "costs": 15_000, "selling_cost_pct": 0.05},
    ]}
    with applied(ov):
        p = sim.create_initial_portfolio()
        for age in range(27, 46):
            p.record_year(2026 + age - 27, age)        # closes last year: amortizes
            p.apply_housing_events(age)
        assert p.home_value == 800_000 and p.mortgage_balance == 600_000
        assert p.mortgage_payoff_age == 60 and p._mortgage_rate == 0.055
        assert sim.mortgage_payoff_projection()["payoff_age"] == 60
    ui = mortgage_schedule(ov, range(27, 93))
    assert ui["payoff_age"] == 60
    assert ui["by_age"][44]["scheduled"] != ui["by_age"][45]["scheduled"]


# ---------------------------------------------------------------------------
# 5. Home-sale exclusion by filing status
# ---------------------------------------------------------------------------

def _sale_tax(filing, partner_age):
    cfg.FILING_STATUS, cfg.PARTNER_AGE = filing, partner_age
    p = AccountPortfolio()
    p.add_account(Account("your_cash", AccountType.CASH, 0.0, "you"))
    p.update_ages(70)
    p.home_value, p.home_cost_basis = 900_000.0, 300_000.0
    p._sell_home(70, 0.06)
    return p.total_taxes_paid, p.get_total_balance()


def test_sale_exclusion_single_vs_married():
    single_tax, single_cash = _sale_tax("Single", 0)
    mfj_tax, mfj_cash = _sale_tax("Married filing jointly", 68)
    partners_tax, _ = _sale_tax("Single", 68)        # unmarried co-owners
    # Gain 900k - 54k - 300k = 546k: single taxes 296k, married 46k.
    assert single_tax > mfj_tax > 0
    assert partners_tax == pytest.approx(mfj_tax, rel=0.5)
    assert single_cash == pytest.approx(900_000 * 0.94 - single_tax)
    assert mfj_cash == pytest.approx(900_000 * 0.94 - mfj_tax)
    cfg.PARTNER_AGE = 0
    assert cfg.home_sale_exclusion() == 250_000
    cfg.PARTNER_AGE, cfg.FILING_STATUS = 68, "Married filing jointly"
    assert cfg.home_sale_exclusion() == 500_000


def test_unknown_basis_means_no_tax():
    p = AccountPortfolio()
    p.add_account(Account("your_cash", AccountType.CASH, 0.0, "you"))
    p.home_value, p.home_cost_basis = 2_000_000.0, None
    p._sell_home(70, 0.06)
    assert p.total_taxes_paid == 0 and p.get_total_balance() == pytest.approx(1_880_000)


# ---------------------------------------------------------------------------
# 6. The current loan's rate drives equity paydown
# ---------------------------------------------------------------------------

def test_current_loan_rate_affects_paydown():
    owner = {"YOUR_AGE": 40, "HOME_VALUE": 600_000, "MORTGAGE_BALANCE": 400_000,
             "MORTGAGE_MONTHLY": 3_000, "MORTGAGE_YEARS_REMAINING": 25}
    balances = {}
    for rate in (0.03, 0.07):
        with applied({**owner, "MORTGAGE_RATE_FOR_PAYOFF": rate}):
            p = sim.create_initial_portfolio()
            for age in range(40, 46):
                p.record_year(2026 + age - 40, age)
            balances[rate] = p.mortgage_balance
    assert balances[0.03] < balances[0.07] < 400_000
    # The UI's current-loan terms use the entered rate too.
    from utils.derived import current_mortgage_terms
    assert current_mortgage_terms({**owner, "MORTGAGE_RATE_FOR_PAYOFF": 0.03})["rate"] == 0.03


# ---------------------------------------------------------------------------
# 7. The mortgage-paydown sweep understands the timeline
# ---------------------------------------------------------------------------

def test_paydown_sweep_runs_for_a_renter_planning_to_buy():
    plan = sr.plan_mortgage_paydown(_fixture("renter_buyer"), 30, 60, extra_grid=[0, 12_000])
    assert plan.result is None                     # a real sweep, not the no-loan stub
    result = sr.execute_plan(plan)
    assert not result.get("no_mortgage") and len(result["curve"]) == 2
    # Extra principal from today only starts once there is a loan (age 30).
    assert result["curve"][1]["payoff_age"] < result["curve"][0]["payoff_age"]


def test_paydown_sweep_skipped_for_a_lifelong_renter():
    ov = {**_fixture("renter_buyer"), "HOME_EVENTS": []}
    plan = sr.plan_mortgage_paydown(ov, 30, 60)
    assert plan.result is not None and plan.result["no_mortgage"]
    cash_buy = {**ov, "HOME_EVENTS": [{"age": 30, "action": "buy", "price": 400_000,
                                       "down_pct": 1.0, "years": 30}]}
    assert sr.plan_mortgage_paydown(cash_buy, 30, 60).result["no_mortgage"]


def test_whatif_baseline_drops_planned_moves():
    ov = _fixture("renter_buyer")
    assert "HOME_EVENTS" in sr.active_lifecycle_toggles(ov)
    assert sr.whatif_baseline_overrides(ov)["HOME_EVENTS"] == []
