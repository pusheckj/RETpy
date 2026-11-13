"""Consumer debts: the shared payoff math (retirement_sim/debts.py), its
today's-dollars treatment, and how the engine spends the payments
(config.debt_payment_for_age, account_simulation)."""
import hashlib
import json
import os
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import account_simulation as sim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import debts as dm  # noqa: E402
from retirement_sim import mc_jobs, mc_parallel  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils import simple_finance as sf  # noqa: E402

CARD = {"name": "Visa", "kind": "credit_card", "balance": 6_000.0, "apr": 0.24, "min_payment": 180.0}
CAR = {"name": "Car", "kind": "car", "balance": 9_000.0, "apr": 0.069, "min_payment": 300.0}
SCHOOL = {"name": "School", "kind": "student_loan", "balance": 20_000.0, "apr": 0.05, "min_payment": 212.0}
THREE = [CARD, CAR, SCHOOL]
# A single earner on $150k a year (the comp table is what the engine pays).
EARNER = {"YOUR_AGE": 30, "PARTNER_AGE": 0, "FILING_STATUS": "Single",
          "YOUR_COMPENSATION_BY_AGE": {30: {"base": 150_000, "bonus": 0, "rsu_gross": 0,
                                            "total_comp": 150_000, "saved": 0}}}


def _level(balance, apr, months):
    r = apr / 12
    return balance * r / (1 - (1 + r) ** -months)


@pytest.fixture
def applied():
    """Apply overrides to cfg the way the app does; undo after. The debt keys
    are always included, so a test may set them on cfg directly."""
    undo = []

    def apply(overrides):
        ov = {"DEBTS": [], "DEBT_EXTRA_MONTHLY": 0, "DEBT_STRATEGY": "avalanche", **overrides}
        undo.append(sr._apply_overrides(sr.build_config_overrides(ov)))
    yield apply
    while undo:
        sr._restore_overrides(undo.pop())


# ---------------------------------------------------------------- payoff math

def test_one_loan_at_its_level_payment_pays_off_on_schedule():
    pay = _level(10_000, 0.06, 36)
    p = dm.amortize([{"balance": 10_000, "apr": 0.06, "min_payment": pay}])
    assert p.paid_off and p.months == 36 and p.payoff_month == [36]
    assert p.total_interest == pytest.approx(pay * 36 - 10_000, abs=0.01)
    assert p.total_paid == pytest.approx(pay * 36, abs=0.01)


def test_hand_checked_card():
    """$6,000 at 24% paying $180 a month: n = -ln(1 - rB/P) / ln(1 + r)."""
    import math
    r = 0.02
    n = -math.log(1 - r * 6_000 / 180) / math.log(1 + r)       # 55.48 months
    p = dm.amortize([CARD])
    assert p.months == math.ceil(n) == 56
    assert p.total_interest == pytest.approx(p.total_paid - 6_000, abs=1e-6)
    assert 3_900 < p.total_interest < 4_100


def test_rollover_keeps_the_total_payment_until_the_end():
    p = dm.amortize(THREE, 100)
    budget = 180 + 300 + 212 + 100
    assert p.monthly_budget == budget
    assert all(x == pytest.approx(budget) for x in p.payments[:-1])   # freed minimums roll on
    assert p.payments[-1] <= budget + 1e-9
    assert sorted(m for m in p.payoff_month) == sorted(p.payoff_month) and p.paid_off


def test_avalanche_saves_interest_and_snowball_wins_first():
    small_low = {"name": "Small", "balance": 1_500.0, "apr": 0.05, "min_payment": 50.0}
    big_high = {"name": "Big", "balance": 8_000.0, "apr": 0.25, "min_payment": 200.0}
    av = dm.amortize([small_low, big_high], 300, "avalanche")
    sb = dm.amortize([small_low, big_high], 300, "snowball")
    assert av.focus_order == [1, 0] and sb.focus_order == [0, 1]
    assert av.total_interest < sb.total_interest
    assert sb.first_win < av.first_win
    assert av.months <= sb.months


def test_underwater_minimum_is_flagged_and_never_pays_off():
    p = dm.amortize([{"balance": 10_000, "apr": 0.24, "min_payment": 150}])   # interest $200/mo
    assert p.underwater == [0] and not p.paid_off and p.months == dm.MAX_MONTHS
    assert dm.amortize([{"balance": 10_000, "apr": 0.24, "min_payment": 150}], 200).paid_off


def test_normalize_repairs_garbage():
    rows = dm.normalize_debts([{"name": "  my visa card ", "balance": "$1,200", "apr": -1,
                                "min_payment": None, "kind": "boat"}, "x", None])
    assert rows == [{"name": "my visa card", "kind": "credit_card", "balance": 1_200.0,
                     "apr": 0.0, "min_payment": 0.0}]
    assert dm.normalize_debts("nope") == [] and dm.normalize_strategy("SNOWBALL") == "snowball"
    assert dm.normalize_strategy(None) == "avalanche"
    assert dm.apr_band(0.08) == "high" and dm.apr_band(0.05) == "moderate" and dm.apr_band(0.03) == "low"


def test_checkup_and_planner_share_the_math():
    """The money check-up's simulate_payoff is the same calculation."""
    rows = [{"name": d["name"], "balance": d["balance"], "apr_pct": d["apr"] * 100,
             "min_payment": d["min_payment"]} for d in THREE]
    for strategy in dm.STRATEGIES:
        a = sf.simulate_payoff(rows, 150, strategy)
        b = dm.amortize(THREE, 150, strategy)
        assert (a.months, a.total_interest, a.balances) == (b.months, b.total_interest, b.balances)
    assert sf.HIGH_APR_PCT == dm.HIGH_APR * 100 and sf.MODERATE_APR_PCT == dm.MODERATE_APR * 100


# ---------------------------------------------------------------- today's dollars

def test_no_inflation_means_real_equals_nominal():
    s = dm.real_schedule(THREE, 100, "avalanche", 0.0)
    assert s.payments == s.nominal
    assert sum(s.payments) == pytest.approx(s.payoff.total_paid)


def test_each_year_is_deflated_to_todays_dollars():
    s = dm.real_schedule(THREE, 100, "avalanche", 0.03)
    for y, (real, nominal) in enumerate(zip(s.payments, s.nominal)):
        assert real == pytest.approx(nominal / 1.03 ** y, rel=1e-12)
    assert s.payments[0] == s.nominal[0] == pytest.approx(12 * (180 + 300 + 212 + 100))
    assert sum(s.payments) < s.payoff.total_paid                  # inflation erodes a fixed payment
    assert s.balances[0] == pytest.approx(35_000)


def test_real_rate_is_apr_over_inflation():
    """A balance left to grow: in today's dollars it grows by (1 + APR) / (1 + inflation)
    a year (APR compounded monthly)."""
    s = dm.real_schedule([{"balance": 1_000, "apr": 0.12, "min_payment": 0}], 0, "avalanche", 0.04)
    yearly = (1 + 0.12 / 12) ** 12
    for y in range(1, 5):
        assert s.balances[y] / s.balances[y - 1] == pytest.approx(yearly / 1.04, rel=1e-12)


def test_payoff_dates_do_not_depend_on_inflation():
    a = dm.real_schedule(THREE, 50, "snowball", 0.0).payoff
    b = dm.real_schedule(THREE, 50, "snowball", 0.06).payoff
    assert a.payoff_month == b.payoff_month


# ---------------------------------------------------------------- engine

def test_debt_payment_for_age_follows_the_schedule(applied):
    applied({"YOUR_AGE": 30, "DEBTS": [CARD], "DEBT_EXTRA_MONTHLY": 0, "EXPECTED_INFLATION": 0.025})
    s = dm.real_schedule([CARD], 0, "avalanche", 0.025)
    assert cfg.debt_payment_for_age(30) == pytest.approx(180 * 12)
    assert cfg.debt_payment_for_age(31) == pytest.approx(s.payments[1])
    assert cfg.debt_payment_for_age(31) == pytest.approx(180 * 12 / 1.025)
    assert cfg.debt_payment_for_age(30 + len(s.payments)) == 0.0          # paid off
    assert cfg.debt_payment_for_age(29) == 0.0


def test_no_debts_means_no_payment(applied):
    assert cfg.DEBTS == [] and cfg.debt_payment_for_age(cfg.YOUR_AGE) == 0.0
    applied({"DEBT_EXTRA_MONTHLY": 500})           # an extra amount with nothing to pay
    assert cfg.debt_payment_for_age(cfg.YOUR_AGE) == 0.0


def _working_year(debts, extra=0):
    cfg.DEBTS, cfg.DEBT_EXTRA_MONTHLY = debts, extra
    p = sim.create_initial_portfolio()
    sim.simulate_accumulation_year(p, cfg.YOUR_AGE, 0.0, partner_working=False)   # single
    return p


def test_working_year_payments_come_out_of_savings(applied):
    applied({**EARNER, "SAVINGS_MODE": "Auto-allocate (recommended)"})
    without = _working_year([])
    with_debts = _working_year(THREE, 100)
    pay = 12 * (180 + 300 + 212 + 100)
    assert without.get_total_balance() - with_debts.get_total_balance() == pytest.approx(pay)
    assert with_debts.spending_log[-1]["living"] - without.spending_log[-1]["living"] == pytest.approx(pay)


def test_payments_stop_and_return_to_savings_after_payoff(applied):
    applied({"YOUR_AGE": 30, "PARTNER_AGE": 0, "FILING_STATUS": "Single", "YOUR_BASE_SALARY": 150_000,
             "DEBTS": [CARD]})
    years = len(dm.real_schedule([CARD], 0, "avalanche", cfg.EXPECTED_INFLATION).payments)
    after = cfg.YOUR_AGE + years
    assert cfg.debt_payment_for_age(after - 1) > 0 and cfg.debt_payment_for_age(after) == 0.0


def test_retirement_year_withdraws_the_payment_untrimmed(applied):
    applied({"YOUR_AGE": 60, "PARTNER_AGE": 0, "FILING_STATUS": "Single", "YOUR_401K": 2_000_000,
             "DYNAMIC_SPENDING_ENABLED": True, "RETURN_BASED_SPENDING_ENABLED": True})

    def year(debts):
        cfg.DEBTS = debts
        p = sim.create_initial_portfolio()
        p.set_retirement_baseline(1.0)
        sim.simulate_retirement_year(p, 60, 50_000, -0.25, 1.0, 60)     # bad year: guardrails cut
        return p

    plain, owing = year([]), year([SCHOOL])
    gap = owing.spending_log[-1]["living"] - plain.spending_log[-1]["living"]
    assert gap == pytest.approx(12 * 212)                                 # not scaled by guardrails
    assert owing.get_total_balance() < plain.get_total_balance() - 12 * 212


def _digest(n_seeds=2):
    h = hashlib.sha256()
    for seed in range(1, n_seeds + 1):
        for age in (45, 58):
            ok, p = sim.run_detailed_simulation(age, random_seed=seed)
            h.update(repr((ok, [(r["age"], r["total"]) for r in p.yearly_history],
                           p.withdrawal_log, p.spending_log)).encode())
    return h.hexdigest()


@pytest.mark.parametrize("preset", [None, "Mid-career couple (40, kids)", "Young professional (28, single)"])
def test_no_debts_leaves_the_simulation_bit_for_bit_unchanged(applied, preset, monkeypatch):
    from components.profile_picker import PROFILES
    applied(dict(PROFILES[preset]) if preset else {})
    empty = _digest()
    cfg.DEBTS = [{"name": "Paid", "balance": 0, "apr": 0.2, "min_payment": 100}]
    paid_off_already = _digest()
    cfg.DEBTS, cfg.DEBT_EXTRA_MONTHLY = [], 400
    extra_but_nothing_owed = _digest()
    cfg.DEBT_EXTRA_MONTHLY = 0
    monkeypatch.setattr(cfg, "debt_payment_for_age", lambda age: 0.0)     # as if the hook weren't there
    no_hook = _digest()
    assert empty == paid_off_already == extra_but_nothing_owed == no_hook


def test_debts_cost_the_plan_money(applied):
    applied(EARNER)
    _, base = sim.run_detailed_simulation(55, random_seed=3)
    cfg.DEBTS = THREE
    _, owing = sim.run_detailed_simulation(55, random_seed=3)
    at55 = lambda p: next(r["total"] for r in p.yearly_history if r["age"] == 55)  # noqa: E731
    assert at55(owing) < at55(base)
    # Paying the same debts off faster costs less in all: more is left at 55.
    cfg.DEBT_EXTRA_MONTHLY = 500
    _, faster = sim.run_detailed_simulation(55, random_seed=3)
    assert at55(owing) < at55(faster) < at55(base)


# ---------------------------------------------------------------- browser compute

def test_debts_are_plain_data_in_the_snapshot(applied):
    applied({"DEBTS": THREE, "DEBT_EXTRA_MONTHLY": 150, "DEBT_STRATEGY": "snowball"})
    snap = mc_parallel.cfg_snapshot()
    assert snap["DEBTS"] == THREE and snap["DEBT_EXTRA_MONTHLY"] == 150
    assert snap["DEBT_STRATEGY"] == "snowball"
    assert mc_jobs.loads(mc_jobs.dumps(snap))["DEBTS"] == THREE
    assert not any(k.startswith("_") and isinstance(v, dict) and k != "__builtins__"
                   for k, v in snap.items() if "debt" in k.lower())


_CHILD = r'''
import sys, json
sys.path.insert(0, sys.argv[1])
from retirement_sim import mc_jobs
job = sys.stdin.read()
n = mc_jobs.browser_load("j", job)
print(json.dumps([mc_jobs.browser_run("j", i) for i in range(n)]))
'''


def test_a_fresh_interpreter_matches_the_server_with_debts(monkeypatch):
    """What the browser does: config defaults + the job's plain-data snapshot."""
    monkeypatch.setattr(sr, "_disk", lambda: None)
    sr.clear_cache(include_disk=False)
    ov = {"YOUR_AGE": 30, "PARTNER_AGE": 0, "FILING_STATUS": "Single", "YOUR_BASE_SALARY": 90_000,
          "YOUR_401K": 40_000, "YOUR_CASH": 20_000, "TARGET_RETIREMENT_AGE": 55,
          "HOME_VALUE": 400_000, "MORTGAGE_BALANCE": 250_000, "MORTGAGE_MONTHLY": 2_000,
          "MORTGAGE_YEARS_REMAINING": 25, "DEBTS": THREE, "DEBT_EXTRA_MONTHLY": 120,
          "DEBT_STRATEGY": "snowball"}
    plan = sr.plan_mortgage_paydown(ov, 40, 55, extra_grid=[0, 12_000])
    assert plan.job["base"]["DEBTS"] == THREE
    server = [mc_jobs.dumps(r) for r in sr.run_plan_calls(plan)]
    out = subprocess.run([sys.executable, "-c", _CHILD, _ROOT], input=mc_jobs.dumps(plan.job),
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == server
    sr.clear_cache(include_disk=False)


def test_engine_bundle_ships_the_debt_module():
    from utils import browser_compute as bc
    assert "retirement_sim/debts.py" in bc.engine()["files"]
