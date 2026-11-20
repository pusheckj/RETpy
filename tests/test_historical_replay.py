"""Historical replay: "If you had retired in a real year" (Deep dives -> Stress tests).

Engine: run_detailed_simulation(historical_start_year=Y) replays real stock and
bond returns from historical_returns.py (all real, like the engine). Plan:
sim_runner.plan_historical_backtest, which must run the same in a fresh
interpreter (the browser). UI: components/historical_backtest.py.
"""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import account_simulation as sim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import historical_returns as hist  # noqa: E402
from retirement_sim import mc_jobs  # noqa: E402
from utils import browser_compute as bc  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from components import historical_backtest as hb  # noqa: E402

SINGLE = {"YOUR_AGE": 30, "PARTNER_AGE": 0, "FILING_STATUS": "Single", "YOUR_BASE_SALARY": 130_000,
          "YOUR_401K": 40_000, "YOUR_CASH": 20_000, "TARGET_RETIREMENT_AGE": 55,
          "SPEND_RENT_MONTHLY": 500}


@pytest.fixture(autouse=True)
def _no_disk_cache(monkeypatch):
    monkeypatch.setattr(sr, "_disk", lambda: None)
    sr.clear_cache(include_disk=False)
    yield
    sr.clear_cache(include_disk=False)


@pytest.fixture
def single_cfg():
    orig = sr._apply_overrides(sr.build_config_overrides(SINGLE))
    try:
        yield
    finally:
        sr._restore_overrides(orig)


# ---------------------------------------------------------------- engine

def test_years_map_working_years_before_and_retirement_from_the_start_year(single_cfg):
    years = sim.historical_replay_years(55, 1966)
    assert len(years) == cfg.plan_end_age() - cfg.YOUR_AGE
    assert years[0] == 1966 - 25                      # 25 working years before
    assert years[25] == 1966                          # first retirement year (age 55)
    assert years == list(range(years[0], years[0] + len(years)))
    # Retiring "before today" is retiring now: the first year is the start year.
    assert sim.historical_replay_years(20, 1966)[0] == 1966


def test_return_is_the_real_data_at_the_plan_mix_and_expected_outside(single_cfg, monkeypatch):
    monkeypatch.setattr(cfg, "INVESTMENT_FEE_RATE", 0.002)
    s, b = cfg.calculate_asset_allocation(60, 55)
    stock, bond = hist.HISTORICAL_RETURNS[1931]
    got = sim.historical_replay_return(1931, 60, 55)
    assert got == pytest.approx(s * (stock - 0.002) + b * (bond - 0.002))
    # Past the data: the deterministic expected median (geometric) return.
    want = cfg.geometric_portfolio_return(s, cfg.EXPECTED_STOCK_RETURN, cfg.EXPECTED_BOND_RETURN,
                                          cfg.STOCK_VOLATILITY, cfg.BOND_VOLATILITY,
                                          cfg.STOCK_BOND_CORRELATION, 0.002)
    assert sim.historical_replay_return(sim.HISTORICAL_LAST_YEAR + 1, 60, 55) == pytest.approx(want)
    assert sim.historical_replay_return(1900, 60, 55) == pytest.approx(want)


def test_replay_is_deterministic_and_draws_no_market_returns(single_cfg, monkeypatch):
    def totals(year):
        ok, pf = sim.run_detailed_simulation(55, random_seed=7, historical_start_year=year)
        return ok, [round(r["total"], 6) for r in pf.yearly_history]

    a = totals(1966)
    assert totals(1966) == a                                    # same seed, same answer
    assert totals(1982) != a                                    # the markets matter

    def boom(*_a, **_k):
        raise AssertionError("a replay must not draw market returns")
    monkeypatch.setattr(sim, "generate_correlated_returns", boom)
    monkeypatch.setattr(sim, "generate_correlated_bond_for_stock", boom)
    assert totals(1966) == a


def test_existing_historical_sequence_api_is_unchanged(single_cfg, monkeypatch):
    with pytest.raises(ValueError):
        sim.run_detailed_simulation(55, historical_sequence="dot_com_crisis", historical_start_year=1966)
    ok1, pf1 = sim.run_detailed_simulation(55, historical_sequence="dot_com_crisis", random_seed=3)
    # It still reads the config's nominal table (and a replay doesn't).
    replay = sim.run_detailed_simulation(55, random_seed=3, historical_start_year=1966)[1]
    monkeypatch.setitem(cfg.HISTORICAL_RETURNS, 2000, -0.40)
    ok2, pf2 = sim.run_detailed_simulation(55, historical_sequence="dot_com_crisis", random_seed=3)
    assert pf2.get_total_balance() < pf1.get_total_balance()
    again = sim.run_detailed_simulation(55, random_seed=3, historical_start_year=1966)[1]
    assert again.get_total_balance() == replay.get_total_balance()


def test_replay_call_reports_run_out_age_and_balances(single_cfg):
    years = [1951, 1966, 1973]                      # whole plan inside 1926-2024
    rows = mc_jobs.replay(55, years, mc_jobs.PATH_SEED)
    assert [r["year"] for r in rows] == years
    for r in rows:
        ok, pf = sim.run_detailed_simulation(55, random_seed=mc_jobs.PATH_SEED,
                                             historical_start_year=r["year"])
        assert r["ok"] == ok
        if ok:
            assert r["out_age"] is None and r["end"] == pytest.approx(pf.get_total_balance())
        else:
            assert r["end"] == 0.0 and 55 <= r["out_age"] < cfg.plan_end_age()
        assert r["outside_data"] == 0


# ---------------------------------------------------------------- plan

def test_start_years_cover_only_full_data_when_possible(single_cfg):
    years, full = sr.backtest_start_years(55)
    assert full
    assert years[0] == sim.HISTORICAL_FIRST_YEAR + 25
    assert years[-1] == sim.HISTORICAL_LAST_YEAR - (cfg.plan_end_age() - 55) + 1
    for y in (years[0], years[-1]):
        data = sim.historical_replay_years(55, y)
        assert sim.HISTORICAL_FIRST_YEAR <= min(data) and max(data) <= sim.HISTORICAL_LAST_YEAR


def test_a_very_long_plan_widens_past_the_data_and_says_so():
    # 42 working years + 50 retired = 92 > the 99 data years minus 9.
    ov = {**SINGLE, "YOUR_AGE": 18, "TARGET_RETIREMENT_AGE": 60, "PLAN_UNTIL_AGE": 110}
    res = sr.run_historical_backtest(ov, 60)
    assert not res["full_data"]
    assert len(res["runs"]) >= sr.BACKTEST_MIN_YEARS
    assert res["runs"][0]["year"] == sim.HISTORICAL_FIRST_YEAR
    assert any(r["outside_data"] > 0 for r in res["runs"])


def test_backtest_plan_matches_in_a_fresh_interpreter():
    """What the browser does: config defaults + the job's plain-data snapshot."""
    plan = sr.plan_historical_backtest(SINGLE, 55)
    assert all(c[0] == "replay" for c in plan.job["calls"]) and plan.job["patches"] == []
    server = [mc_jobs.dumps(r) for r in sr.run_plan_calls(plan)]
    child = ("import sys, json\nsys.path.insert(0, sys.argv[1])\nfrom retirement_sim import mc_jobs\n"
             "n = mc_jobs.browser_load('j', sys.stdin.read())\n"
             "print(json.dumps([mc_jobs.browser_run('j', i) for i in range(n)]))\n")
    out = subprocess.run([sys.executable, "-c", child, _ROOT], input=mc_jobs.dumps(plan.job),
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == server
    res = sr.finish_plan(plan, [mc_jobs.loads(t) for t in server])
    years = [r["year"] for r in res["runs"]]
    assert years == sorted(years) and res["full_data"] and res["errors"] == 0


def test_browser_replies_are_checked():
    call = ["replay", -1, [55, [1966, 1967], 1000]]
    good = [{"year": 1966, "ok": True}, {"year": 1967, "ok": False}]
    assert bc._plausible(call, good)
    assert not bc._plausible(call, good[:1])
    assert not bc._plausible(call, [{"year": 1999}, {"year": 1967}])
    assert not bc._plausible(call, {"year": 1966})


# ---------------------------------------------------------------- summary + grid

def _runs():
    out = []
    for y in range(1934, 1977):
        bad = y in (1937, 1938) or 1965 <= y <= 1974
        out.append({"year": y, "ok": not bad, "out_age": (70 + (y % 7)) if bad else None,
                    "end": 0.0 if bad else 1e6 + y})
    out[-10]["out_age"] = 66                      # 1967 runs out soonest
    return out


def test_hardest_starts_come_from_the_results():
    hs = hb.hardest_starts(_runs())
    assert hs["head"] == "Hardest starts: 1937–1938 and 1965–1974."
    assert "age 66" in hs["detail"] and "1967" in hs["detail"]
    ok = [dict(r, ok=True, out_age=None, end=2e6) for r in _runs()]
    ok[5]["end"] = 10.0
    hs = hb.hardest_starts(ok)
    assert hs["head"] == "Every start year lasted to the end."
    assert str(ok[5]["year"]) in hs["detail"]


def test_grid_has_a_labelled_cell_per_year_and_decade_rows():
    runs = _runs()
    g = hb.grid_html(runs)
    for d in (1930, 1940, 1950, 1960, 1970):
        assert f'<div class="mc-bt-dec">{d}s</div>' in g
    assert g.count('role="listitem"') == len(runs)
    assert g.count("is-empty") == 4 + 3                 # 1930-33 and 1977-79
    assert 'aria-label="Retire in 1967: money runs out at age 66"' in g
    assert f"lasted; {hb.money(runs[0]['end'], 0, shorten=True)} left at the end" in g
    assert g.count("✕") == 12 and g.count("✓") == len(runs) - 12   # never color alone


# ---------------------------------------------------------------- UI

def _script():
    import os
    import sys
    sys.path[:0] = [os.environ["BT_TEST_UI"], os.path.dirname(os.environ["BT_TEST_UI"])]
    import streamlit as st
    from components import historical_backtest
    historical_backtest.render(st, results=st.session_state["results"])


def test_button_runs_the_replay_and_draws_summary_grid_and_table(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("BT_TEST_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    at = AppTest.from_function(_script, default_timeout=120)
    at.session_state["user_overrides"] = dict(SINGLE)
    at.session_state["results"] = {"primary_result": {"success_rate": 0.81, "retirement_age": 55}}
    at.run()
    assert not at.exception, at.exception
    btn = at.button(key="backtest_btn")
    assert btn.label == "Replay my plan through history"
    btn.click().run()
    assert not at.exception, at.exception
    assert at.button(key="backtest_btn").label == "✓ Replay up to date"
    assert at.button(key="backtest_btn").disabled
    md = " ".join(m.value for m in at.markdown)
    res = at.session_state["backtest_result"]
    n_ok = sum(r["ok"] for r in res["runs"])
    assert f"{n_ok} of {len(res['runs'])}" in md and "81%" in md and "the simulation's answer" in md
    assert "mc-bt-grid" in md and ("Hardest starts" in md or "Every start year lasted" in md)
    assert any(e.label == "Show as a table" for e in at.expander)
    assert len(at.dataframe) == 1 and len(at.dataframe[0].value) == len(res["runs"])
    cap = " ".join(c.value for c in at.caption)
    assert "1926" in cap and "2024" in cap and "don't set the limits for the future" in cap
