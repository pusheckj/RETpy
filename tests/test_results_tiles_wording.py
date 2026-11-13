"""Results tiles: the verdict words follow the numbers (QA G4).

Failing plans must not get upbeat text, markers must say what they mean, the
withdrawal-rate and portfolio-needed sweeps must reach their answer, and singles
must not see partner wording.
"""
import os
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components import bridge_years_gauge, decision_narrative  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from tests.conftest import load_sample_household  # noqa: E402
from utils import milestones as ms  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils.formatting import pct  # noqa: E402


# --------------------------------------------------------------------------- percent

def test_pct_never_rounds_up_to_100():
    assert pct(0.9996, 0) == ">99%"
    assert pct(0.9996) == "99.9%"
    assert pct(0.998) == "99.8%"
    assert pct(1.0) == "100.0%" and pct(1.0, 0) == "100%"
    assert pct(0.994, 0) == "99%"


# --------------------------------------------------------------------------- bridge verdict

def _row(age, cash=0.0, taxable=0.0, roth=0.0, burn=0.0, penalty=0.0, penalized=0.0, rule55=0.0, sepp=0.0):
    return {"age": age, "cash": cash, "taxable": taxable, "roth": roth, "rule55": rule55, "sepp": sepp,
            "accessible": cash + taxable + roth + rule55 + sepp, "burn": burn, "penalty": penalty,
            "penalized": penalized}


def test_bridge_with_no_money_is_not_funded():
    """A failing plan has $0 and burns $0: that is "out of money", not "Funded"."""
    results = {"primary_result": {"accessible_by_year": [_row(a) for a in range(30, 60)]}}
    v = bridge_years_gauge.compute_verdict(results, 30)
    assert v["funded"] is False and v["ran_out"] is True and v["first_short"] == 30


def test_bridge_funded_only_by_traditional_money_is_a_shortfall_not_out_of_money():
    rows = [_row(a, cash=0, burn=50_000, penalty=5_000, penalized=400_000) for a in range(50, 60)]
    v = bridge_years_gauge.compute_verdict({"primary_result": {"accessible_by_year": rows}}, 50)
    assert v["funded"] is False and v["ran_out"] is False and v["first_short"] == 50


def test_narrative_does_not_call_a_failed_bridge_covered():
    class St:
        session_state = {"user_overrides": {"TARGET_RETIREMENT_AGE": 30, "YOUR_AGE": 25}}
        out = []

        def markdown(self, text, **kw):
            self.out.append(text)

        def warning(self, text):
            self.out.append(text)

    st = St()
    results = {"primary_result": {"accessible_by_year": [_row(a) for a in range(30, 60)],
                                  "success_rate": 0.0}, "config_snapshot": {"TARGET_SUCCESS_RATE": 0.8}}
    decision_narrative.render(st, results)
    text = " ".join(st.out)
    assert "cover the bridge" not in text and "is gone by age 30" in text


def test_accessible_rows_count_rule_of_55_401k(monkeypatch):
    monkeypatch.setattr(cfg, "RULE_OF_55_ENABLED", True)
    monkeypatch.setattr(cfg, "SEPP_72T_ENABLED", False)
    bt = [[{"age": a, "cash": 10_000, "taxable": 20_000, "roth_ira": 5_000, "roth_401k": 0,
            "traditional_401k": 600_000, "traditional_ira": 50_000, "hsa": 0} for a in range(56, 62)]]
    wd = [[{"age": a, "total": 40_000, "penalties": 0.0} for a in range(56, 62)]]
    rows = sr._accessible_percentiles(bt, wd, 56)
    assert rows[0]["rule55"] == 600_000
    assert rows[0]["accessible"] == 10_000 + 20_000 + 5_000 + 600_000
    assert bridge_years_gauge.compute_verdict({"primary_result": {"accessible_by_year": rows}}, 56)["funded"]
    # Retiring before 55: nothing is freed.
    monkeypatch.setattr(cfg, "YOUR_AGE", 50, raising=False)
    bt2 = [[{**r, "age": r["age"] - 8} for r in bt[0]]]
    wd2 = [[{**r, "age": r["age"] - 8} for r in wd[0]]]
    assert sr._accessible_percentiles(bt2, wd2, 48)[0]["rule55"] == 0.0


def test_accessible_rows_count_a_72t_payment(monkeypatch):
    monkeypatch.setattr(cfg, "RULE_OF_55_ENABLED", False)
    monkeypatch.setattr(cfg, "SEPP_72T_ENABLED", True)
    monkeypatch.setattr(cfg, "SEPP_72T_START_AGE", 50)
    monkeypatch.setattr(cfg, "SEPP_72T_CARVEOUT", 0.0)
    bt = [[{"age": a, "cash": 0, "taxable": 0, "roth_ira": 0, "roth_401k": 0,
            "traditional_401k": 500_000, "traditional_ira": 0, "hsa": 0} for a in range(50, 62)]]
    wd = [[{"age": a, "total": 30_000, "penalties": 0.0} for a in range(50, 62)]]
    rows = sr._accessible_percentiles(bt, wd, 50)
    assert rows[0]["sepp"] == pytest.approx(cfg.sepp_72t_annual_amount(500_000, 50)) and rows[0]["sepp"] > 0
    assert rows[-1]["sepp"] == 0.0  # the schedule is over after 59.5


# --------------------------------------------------------------------------- spending above income

def test_overspend_gap_reports_the_cause_and_skips_retirees():
    ov = {"YOUR_AGE": 25, "TARGET_RETIREMENT_AGE": 55, "YOUR_BASE_SALARY": 40_000,
          "SPEND_FOOD_MONTHLY": 5_000, "PARTNER_AGE": 0}
    gap = decision_narrative.overspend_gap({"user_overrides": ov})
    assert gap is not None and gap["gap"] > 30_000
    assert decision_narrative.overspend_gap({"user_overrides": {**ov, "TARGET_RETIREMENT_AGE": 25}}) is None
    assert decision_narrative.overspend_gap({"user_overrides": {**ov, "SPEND_FOOD_MONTHLY": 300}}) is None


# --------------------------------------------------------------------------- milestones

def _inputs(**kw):
    base = dict(your_age=35, retire_age=55, year=2026, ages=list(range(35, 96)),
                invested=[100_000.0 * (1.0 if a < 55 else 0.97 ** (a - 55)) for a in range(35, 96)],
                home=[0.0] * 61, spend_core=60_000, living_base=30_000, health=5_000, today_spend=70_000,
                discretionary_ratio=0.3, rate=0.04, real_return=0.05, cash=5_000, barista_income=20_000,
                mortgage_years=0, places=(), cost=ms.CostBasis())
    base.update(kw)
    return ms.Inputs(**base)


def test_marker_reached_only_after_retirement_is_flagged():
    invested = [100_000.0 + 10_000 * i for i in range(61)]
    inp = _inputs(invested=invested, retire_age=40)       # FIRE (~1.6M) arrives at 35 + 150 -> never; use a low target
    inp = _inputs(invested=invested, retire_age=40, spend_core=20_000, living_base=10_000, health=0, barista_income=0)
    rep = ms.build(inp)
    late = [m for m in rep.markers if m.status == ms.PROGRESS and m.age and m.age > 40]
    assert late and all(m.after_retire for m in late)
    # A marker reached before retirement is not flagged, and a flagged one is never "next up".
    assert rep.next_up is None or not rep.next_up.after_retire


def test_net_worth_subtracts_debt():
    inp = _inputs(invested=[50_000.0] * 61, debt=[30_000.0] * 61)
    rep = ms.build(inp)
    # $20K of net worth: the $10K rung is passed, $25K is not.
    labels = {m.label: m.status for m in rep.networth}
    assert labels["$25K net worth"] != ms.REACHED and labels["$10K net worth"] == ms.REACHED


def test_cash_months_wording_has_no_odd_fraction_of_a_goal():
    rep = ms.build(_inputs(cash=2_500_000))
    detail = next(m.detail for m in rep.markers if m.key == "emergency:6")
    assert "of 6 months" not in detail and "The goal is 6" in detail


# --------------------------------------------------------------------------- sweeps

def test_swr_sweep_finds_the_crossing_for_a_rich_household():
    """A plan drawing well under 1% used to get the grid's top (1.6x its own rate)."""
    ov = load_sample_household()
    ov.update(YOUR_BROKERAGE=15_000_000, YOUR_401K=2_000_000, PARTNER_AGE=0, PARTNER_SALARY=0,
              TARGET_RETIREMENT_AGE=45, YOUR_AGE=40)
    sr.clear_cache()
    res = sr.run_swr_analysis(ov, 120, 45)
    assert not res.get("error")
    assert res["actual_rate"] < 0.02
    if res["swr_is_lower_bound"]:
        pytest.fail("the sweep should reach a failing rate")
    assert res["swr_rate"] > 2 * res["actual_rate"]
    assert max(c["realized_rate"] for c in res["success_by_rate"]) >= 0.08


def test_swr_crossing_helper_marks_a_top_of_grid_pass():
    curve = [{"realized_rate": r, "success": 1.0} for r in (0.01, 0.05, 0.1)]
    assert sr._swr_crossing(curve, 0.8) == 0.1


def test_fi_number_already_fi_flag_and_grid_reach():
    ov = load_sample_household()
    ov.update(YOUR_BROKERAGE=30_000_000)
    sr.clear_cache()
    fi = sr.run_networth_analysis(ov, 90)
    assert fi["already_fi"] is True and fi["already_retired"] is False
    assert len(fi["success_by_networth"]) <= 4
    ov2 = load_sample_household()
    sr.clear_cache()
    fi2 = sr.run_networth_analysis(ov2, 90)
    top = max(c["networth"] for c in fi2["success_by_networth"])
    assert top >= 1.1 * fi2["current_investable"]


# --------------------------------------------------------------------------- singles

def test_single_income_has_no_partner_card():
    from streamlit.testing.v1 import AppTest

    def script():
        import os
        import sys
        sys.path[:0] = [os.environ["T_UI"], os.path.dirname(os.environ["T_UI"])]
        import streamlit as st
        from components import sec_income
        sec_income.render_body(st) if hasattr(sec_income, "render_body") else sec_income.render(st)

    os.environ["T_UI"] = _UI
    at = AppTest.from_function(script, default_timeout=60)
    ov = load_sample_household()
    ov["PARTNER_AGE"] = 0
    at.session_state["user_overrides"] = ov
    at.run()
    assert not at.exception, at.exception
    labels = [m.label for m in at.metric]
    assert "Partner" not in labels and "Your income" in labels


# --------------------------------------------------------------------------- tiles drawn with AppTest

def _at(script, monkeypatch, state):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("T_UI", _UI)
    at = AppTest.from_function(script, default_timeout=120)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, at.exception
    return at


def _text(at):
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption]
                     + [i.value for i in at.info] + [str(m.value) for m in at.metric])


def _life_script():
    import os
    import sys
    sys.path[:0] = [os.environ["T_UI"], os.path.dirname(os.environ["T_UI"])]
    import streamlit as st
    from components import life_expectancy_section
    life_expectancy_section.render(st, show_header=False)


def test_life_expectancy_does_not_reassure_a_failing_plan(monkeypatch):
    ov = {"YOUR_AGE": 25, "PLAN_UNTIL_AGE": 95, "PARTNER_AGE": 0}
    bad = _text(_at(_life_script, monkeypatch, {
        "user_overrides": ov, "results": {"primary_result": {"success_rate": 0.0},
                                          "config_snapshot": {"TARGET_SUCCESS_RATE": 0.8}}}))
    assert "good buffer" not in bad and "below your 80% target" in bad
    good = _text(_at(_life_script, monkeypatch, {
        "user_overrides": ov, "results": {"primary_result": {"success_rate": 0.95},
                                          "config_snapshot": {"TARGET_SUCCESS_RATE": 0.8}}}))
    assert "good buffer" in good


def _fi_script():
    import os
    import sys
    sys.path[:0] = [os.environ["T_UI"], os.path.dirname(os.environ["T_UI"])]
    import streamlit as st
    from components import fi_number_section
    fi_number_section._render_result(st, st.session_state["fi"], False)


def _fi(**kw):
    base = {"fi_number": 1_400_000.0, "fi_median_retire_age": 68.0, "fi_age_low": 68.0, "fi_age_high": 68.0,
            "already_fi": True, "already_retired": True, "target_success": 0.8,
            "current_investable": 1_400_000.0, "max_work_age": 70,
            "success_by_networth": [{"networth": 1_400_000.0, "success": 1.0, "median_retire_age": 68.0}]}
    base.update(kw)
    return base


def test_fi_number_does_not_echo_the_balance_as_the_need(monkeypatch):
    text = _text(_at(_fi_script, monkeypatch, {"fi": _fi()}))
    assert "At most $1.4M" in text and "Already retired" in text and "meets your target" in text
    working = _text(_at(_fi_script, monkeypatch, {"fi": _fi(already_retired=False)}))
    assert "Now" in working and "somewhere below today's balance" in working


def _ms_script():
    import os
    import sys
    sys.path[:0] = [os.environ["T_UI"], os.path.dirname(os.environ["T_UI"])]
    import streamlit as st
    from components import freedom_milestones
    freedom_milestones.render(st, st.session_state.get("results"))


def test_milestones_say_through_the_plan_end_for_a_failed_plan(monkeypatch):
    ov = load_sample_household()
    results = {"earliest_retirement_age": None,
               "primary_result": {"median_trajectory": [(34, 1_000.0)], "retirement_age": 55}}
    at = _at(_ms_script, monkeypatch, {"user_overrides": ov, "results": results, "n_simulations": 100})
    text = _text(at)
    from utils.household import plan_end_ages
    end = plan_end_ages(ov)[0]
    assert f"(through {end})" in text and "(through 34)" not in text
    assert "is not a chance of success" in text


def test_renter_place_card_does_not_say_keeps_your_home(monkeypatch):
    ov = load_sample_household()
    ov.update(HOME_VALUE=0, MORTGAGE_BALANCE=0, MORTGAGE_MONTHLY=0, MORTGAGE_YEARS_REMAINING=0,
              SPEND_RENT_MONTHLY=2_000)
    text = _text(_at(_ms_script, monkeypatch, {"user_overrides": ov, "n_simulations": 100}))
    assert "Keeps your home" not in text and "Your plan&#x27;s housing" in "\n".join(
        m.value for m in _at(_ms_script, monkeypatch, {"user_overrides": ov, "n_simulations": 100}).markdown)


def _swr_script():
    import os
    import sys
    sys.path[:0] = [os.environ["T_UI"], os.path.dirname(os.environ["T_UI"])]
    import streamlit as st
    from components import swr_curve_section
    swr_curve_section._render_result(st, st.session_state["swr"], None)


def _swr(rate, lower, top_success):
    curve = [{"realized_rate": r, "success": s, "spending": 0.0}
             for r, s in ((0.003, 1.0), (0.05, 1.0), (0.10, top_success))]
    return {"success_by_rate": curve, "swr_rate": rate, "swr_is_lower_bound": lower, "actual_rate": 0.003,
            "target_success": 0.8, "investable_at_retirement": 1_400_000.0, "retirement_age": 68}


def test_swr_tile_says_above_not_none_when_the_top_of_the_sweep_passes(monkeypatch):
    text = _text(_at(_swr_script, monkeypatch, {"swr": _swr(0.10, True, 1.0)}))
    assert "Above 10.0%" in text and "None found" not in text
    assert "not limited by how fast you draw" in text
    found = _text(_at(_swr_script, monkeypatch, {"swr": _swr(0.06, False, 0.3)}))
    assert "6.0%" in found and "Above" not in found
    none = _text(_at(_swr_script, monkeypatch, {"swr": _swr(None, False, 0.0) | {"success_by_rate": [
        {"realized_rate": 0.01, "success": 0.1, "spending": 0.0}]}}))
    assert "None found" in none and "even the lowest, 1.0%" in none


def test_short_money_picks_the_unit_after_rounding():
    assert ms.short_money(999_600) == "$1M"
    assert ms.short_money(999_999_999) == "$1B"
    assert ms.short_money(1_500_000) == "$1.5M"
