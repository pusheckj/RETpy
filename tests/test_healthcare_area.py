"""Healthcare by area, in the engine: plain config values from an area, the single price
formula, the 2027 credit table, 6% premium growth, the cliff record, and the wiring from the
side panel's setting to the simulation (a dead-input guard).

No area set means today's behaviour exactly: tests/test_aca_marketplace.py pins that.
"""
import copy
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
from retirement_sim import healthcare_data as hd  # noqa: E402
from retirement_sim import mc_jobs  # noqa: E402
from retirement_sim.account_simulation import (  # noqa: E402
    Account, AccountPortfolio, AccountType, simulate_retirement_year,
)
from utils import sim_runner as sr  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_cfg():
    saved = {k: copy.deepcopy(v) for k, v in vars(cfg).items() if k.isupper()}
    yield
    for k, v in saved.items():
        setattr(cfg, k, v)


def _area(key="AL:1", plan="silver", **kw):
    for k, v in hd.area_overrides(key, plan, **kw).items():
        setattr(cfg, k, v)
    cfg.SPEND_HEALTH_MONTHLY = None


def _family_portfolio(adults=(35, 35), kids=(5, 3)):
    """A household whose primary is ``adults[0]`` and whose children are ``kids`` today."""
    cfg.MODEL_ACA_AGE_RATED = True
    cfg.ACA_ENABLED = True
    cfg.YOUR_AGE = adults[0]
    cfg.PARTNER_AGE = adults[1]
    cfg.FILING_STATUS = "Married filing jointly"
    cfg.CHILDREN = [{"years_until_birth": -k, "monthly_cost": 1_000, "leaves_home_age": 21}
                    for k in kids]
    p = AccountPortfolio()
    p.update_ages(adults[0])
    return p


# ---------------------------------------------------------------------------
# The Alabama fixture, from the engine
# ---------------------------------------------------------------------------

def test_alabama_case_reproduces_from_the_engine():
    _area("AL:1", "silver")
    bench, plan = cfg.aca_household_prices_annual([35, 35], [5, 3])
    assert bench / 12 == pytest.approx(2134.11, abs=0.005) and plan == bench
    pct = cfg.aca_applicable_pct(80_000 / cfg.aca_fpl(4))
    assert cfg.aca_fpl(4) == 33_000 and pct == pytest.approx(0.08375, abs=1e-5)
    assert bench - 80_000 * pct == pytest.approx(18_909.16, abs=0.01)         # the credit
    assert cfg.aca_oop_annual(4, 1.0, 1.0, member_ages=[35, 35, 5, 3]) == pytest.approx(3_200)

    _area("AL:1", "bronze")
    bench2, bronze = cfg.aca_household_prices_annual([35, 35], [5, 3])
    assert bench2 == pytest.approx(bench)                 # the credit still follows Silver
    assert bronze / 12 == pytest.approx(1287.61, abs=0.005)
    assert cfg.aca_oop_annual(4, 1.0, 1.0, member_ages=[35, 35, 5, 3]) == pytest.approx(4_160)


def test_alabama_case_through_the_portfolio():
    _area("AL:1", "silver")
    p = _family_portfolio()
    magi = 80_000.0
    premium, oop = p.quote_marketplace_cost(35, [35, 35], magi, 1.0)
    pct = hd.applicable_pct(magi / 33_000)
    assert premium == pytest.approx(magi * pct)           # Silver: you pay your share of income
    assert oop == pytest.approx(3_200)
    above = p.quote_marketplace_cost(35, [35, 35], 10_000_000.0, 1.0)[0]
    assert above == pytest.approx(12 * 2134.11, abs=0.1)  # no credit above 400% FPL


def test_bronze_pays_the_bronze_price_less_the_silver_based_credit():
    _area("AL:1", "bronze")
    p = _family_portfolio()
    low = p.quote_marketplace_cost(35, [35, 35], 50_000.0, 1.0)[0]
    assert low == 0.0                                      # the credit is bigger than the bronze price
    mid = p.quote_marketplace_cost(35, [35, 35], 110_000.0, 1.0)[0]
    pct = hd.applicable_pct(110_000 / 33_000)
    bench = 12 * 2134.11
    assert mid == pytest.approx(12 * 1287.61 - (bench - 110_000 * pct), abs=0.2)
    assert p.quote_marketplace_cost(35, [35, 35], 10_000_000.0, 1.0)[0] == pytest.approx(12 * 1287.61, abs=0.1)


def test_new_york_is_priced_by_family_tier():
    _area("NY:avg", "silver")
    bench, _ = cfg.aca_household_prices_annual([40, 40], [5, 12])
    assert bench == pytest.approx(12 * 1041 * 2.85)
    assert cfg.aca_household_prices_annual([62], [])[0] == pytest.approx(12 * 1041)


def test_only_the_three_oldest_children_under_21_are_charged_in_an_area():
    _area("TX:1")
    three = cfg.aca_household_prices_annual([40, 40], [15, 12, 9])[0]
    assert cfg.aca_household_prices_annual([40, 40], [15, 12, 9, 2])[0] == pytest.approx(three)


# ---------------------------------------------------------------------------
# Premium growth: 6.0% a year nominal for pre-Medicare premiums only
# ---------------------------------------------------------------------------

def test_premiums_grow_at_6_percent_nominal_when_an_area_is_set():
    _area("AL:1")
    ex_h = cfg.INFLATION_REAL_EXCESS["healthcare"]
    assert ex_h == pytest.approx(0.0175)                   # unchanged: Medicare, care, out-of-pocket
    base = cfg.aca_marketplace_premium(10_000_000, [35, 35], [5, 3], 4)
    grown = cfg.aca_marketplace_premium(10_000_000, [35, 35], [5, 3], 4,
                                        factor=(1 + ex_h) ** 10, years=10)
    # 6.0% nominal less 2.75% CPI = 3.25% a year in the engine's all-real frame.
    assert grown / base == pytest.approx(1.0325 ** 10)


def test_the_credit_does_not_grow_with_prices_in_an_area():
    """The required contribution is a share of income. Prices rise, income does not, so the
    credit gets bigger and the household's bill below the cliff stays put."""
    _area("AL:1")
    now = cfg.aca_marketplace_premium(80_000, [35, 35], [5, 3], 4)
    later = cfg.aca_marketplace_premium(80_000, [35, 35], [5, 3], 4,
                                        factor=1.0175 ** 10, years=10)
    assert later == pytest.approx(now)


def test_without_an_area_growth_and_prices_are_todays():
    assert cfg.ACA_AREA_SILVER_MONTHLY is None and cfg.ACA_PREMIUM_GROWTH_NOMINAL is None
    assert cfg.aca_premium_extra(30) == 1.0
    bench, plan = cfg.aca_household_prices_annual([55, 50], [10])
    expect = (cfg.aca_member_full_price_annual(55) + cfg.aca_member_full_price_annual(50)
              + cfg.aca_member_full_price_annual(10))
    assert bench == plan == pytest.approx(expect)
    assert cfg.ACA_COVERAGE_YEAR == 2026


def test_medicare_and_care_growth_are_not_touched_by_an_area():
    before = cfg.calculate_medicare_irmaa(90_000, 1.3, enrollees=2)
    ltc = cfg.calculate_ltc_cost(86, 1.3, True)
    _area("AL:1")
    assert cfg.calculate_medicare_irmaa(90_000, 1.3, enrollees=2) == before
    assert cfg.calculate_ltc_cost(86, 1.3, True) == ltc
    assert cfg.INFLATION_RATES["healthcare"] == 0.045


# ---------------------------------------------------------------------------
# One price formula for the engine and the Freedom-milestones quote
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("area_key", [None, "AL:1", "NY:avg", "CA:19"])
@pytest.mark.parametrize("magi", [20_000.0, 90_000.0, 400_000.0])
def test_milestone_quote_equals_the_engine_quote(area_key, magi):
    if area_key:
        _area(area_key, "bronze")
    p = _family_portfolio()
    cfg.SPEND_HEALTH_MONTHLY = 150
    prem, oop = p.quote_marketplace_cost(35, [35, 35], magi, 1.1)
    quote = cfg.pre_medicare_health_quote(magi, [35, 35], [5, 3], 1.1)
    assert quote == pytest.approx(prem + oop)


def test_milestone_quote_reads_the_area_from_a_saved_source_after_overrides_are_gone():
    defaults = {k: copy.deepcopy(getattr(cfg, k)) for k in hd.area_overrides("AL:1")}
    _area("AL:1")
    source = {k: getattr(cfg, k) for k in defaults}
    source.update({"ACA_ENABLED": True, "MODEL_ACA_AGE_RATED": True, "MEDICARE_AGE": 65,
                   "ACA_BENCHMARK_MONTHLY_AT_40": 625.0, "ACA_CHILD_MONTHLY": 390.0,
                   "ACA_OOP_PER_PERSON_ANNUAL": 1_500.0, "SPEND_HEALTH_MONTHLY": 0.0,
                   "INFLATION_REAL_EXCESS": cfg.INFLATION_REAL_EXCESS})
    live = cfg.pre_medicare_health_quote(80_000, [35, 35], [5, 3], 1.0, years=3)
    for k, v in defaults.items():             # the plan's overrides are put back
        setattr(cfg, k, v)
    assert cfg.ACA_AREA_SILVER_MONTHLY is None
    assert cfg.pre_medicare_health_quote(80_000, [35, 35], [5, 3], 1.0, source=source,
                                         years=3) == pytest.approx(live)


def test_milestone_quote_grows_with_the_premium_factor():
    _area("AL:1")
    a = cfg.pre_medicare_health_quote(10_000_000, [35, 35], [5, 3], 1.0)
    b = cfg.pre_medicare_health_quote(10_000_000, [35, 35], [5, 3], 1.0, years=10)
    assert b > a


# ---------------------------------------------------------------------------
# The cliff, from the engine's own MAGI
# ---------------------------------------------------------------------------

def test_cliff_helper_names_the_subsidy_lost_at_400_percent_fpl():
    _area("AL:1")
    edge = 4 * cfg.aca_fpl(4)
    bench = 12 * 2134.11
    top = 0.1022
    assert cfg.aca_marketplace_cliff(edge - 1, [35, 35], [5, 3], 4) == (False, 0.0)
    over, lost = cfg.aca_marketplace_cliff(edge, [35, 35], [5, 3], 4)
    assert over is True
    assert lost == pytest.approx(bench - edge * top, abs=0.2)


def test_cliff_helper_without_an_area_uses_the_2026_table():
    cliff = 4 * cfg.aca_fpl(2)
    over, lost = cfg.aca_marketplace_cliff(cliff + 5_000, [55, 55], [], 2)
    bench = cfg.aca_household_prices_annual([55, 55], [])[0]
    assert over and lost == pytest.approx(bench - cliff * 0.0996)


def test_a_simulated_year_records_whether_income_cleared_the_cliff():
    _area("AL:1")
    cfg.ENABLE_ROTH_CONVERSION = False        # a conversion would add income of its own

    def year(withdraw):
        p = _family_portfolio((55, 55), ())
        cfg.CHILDREN = []
        p.accounts = {}
        p.add_account(Account(name="ira", account_type=AccountType.TRADITIONAL_IRA,
                              balance=5_000_000.0, owner="you"))
        p.set_retirement_baseline(1.0)
        p.ltc_needs_by_age = {}
        assert simulate_retirement_year(p, your_age=55, expenses=withdraw, annual_return=0.0,
                                        inflation_factor=1.0, retirement_age=55)
        return p.spending_log[-1]

    low = year(30_000.0)
    assert low["aca_over"] is False and low["aca_lost"] == 0.0
    high = year(200_000.0)                  # a $200k IRA draw is income: far over 400% FPL
    assert high["aca_over"] is True and high["aca_lost"] > 0
    assert high["magi"] > 4 * cfg.aca_fpl(2)


def test_cliff_summary_names_the_first_year_most_runs_cross():
    from utils import health_cliff as hc
    by_age = {55: [None] * 10, 56: [None] * 6 + [9_000.0] * 4,
              57: [8_000.0] * 6 + [None] * 4, 58: [8_000.0] * 10}
    summary = hc.compact(by_age)
    assert summary[57] == {"n": 10, "over": 6, "lost": 8_000.0}
    out = hc.first_crossing(summary, your_age=50, current_year=2026)
    assert out["age"] == 57 and out["year"] == 2033
    assert out["lost"] == pytest.approx(8_000)
    assert out["share"] == pytest.approx(0.6)
    assert hc.first_crossing(hc.compact({55: [None] * 5}), 50, 2026) is None
    assert hc.first_crossing({}, 50, 2026) is None


# ---------------------------------------------------------------------------
# From the side panel's setting to the simulation
# ---------------------------------------------------------------------------

def test_the_area_becomes_plain_config_values_and_never_the_zip():
    built = build_config_overrides({"HEALTH_AREA": "AL:3", "HEALTH_PLAN": "bronze"})
    assert built["ACA_AREA_KEY"] == "AL:3" and len(built["ACA_AREA_SILVER_MONTHLY"]) == 65
    assert 0 < built["ACA_AREA_PLAN_RATIO"] < 1
    assert "HEALTH_AREA" not in built and "HEALTH_PLAN" not in built
    json.dumps(mc_jobs.encode(built))                  # plain data: the browser can take it
    assert not any(k.startswith("ACA_AREA") for k in build_config_overrides({}))
    assert not any(k.startswith("ACA_AREA") for k in build_config_overrides({"HEALTH_AREA": "ZZ:9"}))


def test_the_two_price_boxes_rescale_the_area_prices():
    ref = hd.reference_prices("AL:3")
    same = build_config_overrides({"HEALTH_AREA": "AL:3", "ACA_BENCHMARK_MONTHLY_AT_40": round(ref["benchmark_at_40"]),
                                   "ACA_CHILD_MONTHLY": round(ref["child"])})
    plain = build_config_overrides({"HEALTH_AREA": "AL:3"})
    assert same["ACA_AREA_SILVER_MONTHLY"] == plain["ACA_AREA_SILVER_MONTHLY"]
    double = build_config_overrides({"HEALTH_AREA": "AL:3",
                                     "ACA_BENCHMARK_MONTHLY_AT_40": 2 * round(ref["benchmark_at_40"])})
    t, d = plain["ACA_AREA_SILVER_MONTHLY"], double["ACA_AREA_SILVER_MONTHLY"]
    assert d[40] == pytest.approx(2 * t[40], rel=0.01) and d[30] > 1.9 * t[30]
    assert d[5] == t[5]                                # the child price box is separate


MEDIAN = {"YOUR_AGE": 30, "PARTNER_AGE": 28, "FILING_STATUS": "Married filing jointly",
          "YOUR_BASE_SALARY": 150_000, "PARTNER_BASE_SALARY": 60_000, "YOUR_401K": 120_000,
          "YOUR_CASH": 30_000, "YOUR_BROKERAGE": 80_000, "TARGET_RETIREMENT_AGE": 45,
          "PARTNER_RETIREMENT_AGE": 45, "SPEND_RENT_MONTHLY": 1_500}


@pytest.fixture
def full_run(monkeypatch):
    monkeypatch.setattr(sr, "_disk", lambda: None)

    def run(overrides):
        sr.clear_cache(include_disk=False)
        return sr.run_full_analysis(dict(overrides), n_simulations=60, target_retirement_age=45,
                                    scan_age_range=(44, 47, 3))["primary_result"]

    yield run
    sr.clear_cache(include_disk=False)


def _health(result):
    return {r["age"]: r["p50"] for r in result["health_by_year"]}


def test_the_area_reaches_the_simulation(full_run):
    """Dead-input guard: setting the area (or its plan type, or a price box) must move what the
    simulation pays for health insurance before 65."""
    none = _health(full_run(MEDIAN))
    al = _health(full_run({**MEDIAN, "HEALTH_AREA": "AL:1"}))
    ca = _health(full_run({**MEDIAN, "HEALTH_AREA": "CA:19"}))
    bronze = _health(full_run({**MEDIAN, "HEALTH_AREA": "AL:1", "HEALTH_PLAN": "bronze"}))
    typed = _health(full_run({**MEDIAN, "HEALTH_AREA": "AL:1", "ACA_BENCHMARK_MONTHLY_AT_40": 1_500}))
    age = 55
    assert len({round(v[age], 2) for v in (none, al, ca, bronze, typed)}) == 5
    assert typed[age] != al[age]


def test_no_area_leaves_existing_plans_as_they_were(full_run):
    a = full_run(MEDIAN)
    b = full_run({**MEDIAN, "HEALTH_AREA": None, "HEALTH_PLAN": "bronze"})
    assert _health(a) == _health(b)


def test_a_run_reports_when_income_crosses_the_cliff(full_run):
    r = full_run({**MEDIAN, "HEALTH_AREA": "AL:1"})
    assert "aca_cliff_by_year" in r and isinstance(r["aca_cliff_by_year"], dict)


# ---------------------------------------------------------------------------
# The browser gets the same answer
# ---------------------------------------------------------------------------

_CHILD = r'''
import sys, json
sys.path.insert(0, sys.argv[1])
from retirement_sim import mc_jobs
job = sys.stdin.read()
n = mc_jobs.browser_load("j", job)
print(json.dumps([mc_jobs.browser_run("j", i) for i in range(n)]))
'''


def test_a_fresh_interpreter_matches_the_server_with_an_area(monkeypatch):
    monkeypatch.setattr(sr, "_disk", lambda: None)
    sr.clear_cache(include_disk=False)
    ov = {**MEDIAN, "HEALTH_AREA": "NY:avg", "HEALTH_PLAN": "bronze"}
    plan = sr.plan_full_analysis(ov, 60, 45, (44, 47, 3))
    assert plan.job["base"]["ACA_AREA_TIERS"]["fam"] == 2.85
    server = [mc_jobs.dumps(r) for r in sr.run_plan_calls(plan)]
    out = subprocess.run([sys.executable, "-c", _CHILD, _ROOT], input=mc_jobs.dumps(plan.job),
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == server
    sr.clear_cache(include_disk=False)
