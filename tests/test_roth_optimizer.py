"""Roth conversion optimizer (Deep dives -> Roth conversions) and the sidebar's
"Fill up to income of" caption.

The engine fills income up to ROTH_CONVERSION_TARGET_BRACKET measured BEFORE the
standard deduction, so "fill the X% bracket" = bracket top + standard deduction
(utils/roth_brackets.py). The sweep is sim_runner.plan_roth_sweep.
"""
import json
import os
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import account_simulation as sim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import mc_jobs  # noqa: E402
from utils import browser_compute as bc  # noqa: E402
from utils import roth_brackets as rb  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from components import roth_optimizer_tab as rt  # noqa: E402

SINGLE = {"YOUR_AGE": 30, "PARTNER_AGE": 0, "FILING_STATUS": "Single", "YOUR_BASE_SALARY": 130_000,
          "YOUR_401K": 40_000, "YOUR_CASH": 20_000, "TARGET_RETIREMENT_AGE": 55,
          "SPEND_RENT_MONTHLY": 500}


@pytest.fixture(autouse=True)
def _no_disk_cache(monkeypatch):
    monkeypatch.setattr(sr, "_disk", lambda: None)
    sr.clear_cache(include_disk=False)
    yield
    sr.clear_cache(include_disk=False)


# ---------------------------------------------------------------- bracket math

@pytest.mark.parametrize("status", ["MFJ", "S", "HOH"])
def test_fill_targets_are_bracket_top_plus_standard_deduction(status):
    brackets = cfg.FEDERAL_BRACKETS_BY_STATUS[status]
    std = cfg.STANDARD_DEDUCTION_BY_STATUS[status]
    for rate, target in rb.sweep_targets(status):
        top = next(t for t, r in brackets if r == rate)
        assert target == top + std
    if status == "MFJ":                               # the 2026 figures, for the record
        assert rb.sweep_targets(status) == [(0.12, 133_000), (0.22, 243_600), (0.24, 435_750)]


def test_engine_compares_the_target_with_income_before_the_deduction():
    """With no other income, a target of X converts X (not X minus the deduction)."""
    with mc_jobs.config_state({"ENABLE_ROTH_CONVERSION": True, "ROTH_CONVERSION_TARGET_BRACKET": 60_000,
                               "ROTH_CONVERSION_MAX_ANNUAL": 1_000_000, "ROTH_CONVERSION_STOP_AGE": 99}):
        pf = sim.create_initial_portfolio()
        pf.accounts["your_401k"].balance = 1_000_000.0
        pf.year_ordinary_income = 0.0
        converted, _tax = pf.perform_roth_conversion(60)
    assert converted == pytest.approx(60_000)


def test_bracket_note_names_the_bracket_reached():
    assert rb.bracket_note(100_800, "MFJ") == "partway into the 12% bracket"   # the default
    assert rb.bracket_note(133_000, "MFJ") == "≈ top of the 12% bracket"
    assert rb.bracket_note(243_600, "MFJ") == "≈ top of the 22% bracket"
    assert rb.bracket_note(66_500, "S") == "≈ top of the 12% bracket"
    assert "standard deduction" in rb.bracket_note(20_000, "MFJ")


# ---------------------------------------------------------------- the sweep

def test_paired_standard_error_uses_the_path_by_path_difference():
    assert sr._paired_se("1111", "1111") == 0.0
    assert sr._paired_se("1-10", "1010") == pytest.approx(0.0)        # '-' paths skipped
    assert sr._paired_se("1100", "0000") > 0


def test_sweep_cells_best_and_current_match_the_main_run():
    res = sr.run_roth_sweep(SINGLE, 300, 55)
    cells = res["cells"]
    grid = [f"{r['rate']:.2f}|{c}" for r in res["rows"] for c in res["caps"]]
    assert set(cells) == {"off", "current", *grid}                     # default target isn't on the grid
    assert res["current_key"] == "current" and res["n_simulations"] == 300
    assert [r["target"] for r in res["rows"]] == [t for _r, t in rb.sweep_targets("S")]
    best = cells[res["best_key"]]
    assert res["best_key"] != "current"
    assert all(best["success"] >= c["success"] for k, c in cells.items() if k != "current")
    assert not best["within_noise"]
    for c in cells.values():
        assert c["n"] == 300 and 0.0 <= c["success"] <= 1.0 and c["median_taxes"] >= 0.0
        if c["within_noise"]:
            assert best["success"] - c["success"] <= 2 * c["diff_se"] + 1e-12
    # Same seeds as the main run: your setting's success IS the plan's success.
    main = sr.run_full_analysis(SINGLE, n_simulations=300, target_retirement_age=55)
    assert cells["current"]["success"] == main["primary_result"]["success_rate"]


def test_a_current_setting_on_the_grid_is_not_run_twice():
    ov = {**SINGLE, "ROTH_CONVERSION_TARGET_BRACKET": rb.fill_target(0.22, "S"),
          "ROTH_CONVERSION_MAX_ANNUAL": 100_000}
    plan = sr.plan_roth_sweep(ov, 300, 55)
    assert all(c[1] != -1 for c in plan.job["calls"])                    # no base-config cell
    assert len(plan.job["patches"]) == 10
    off = sr.plan_roth_sweep({**SINGLE, "ENABLE_ROTH_CONVERSION": False}, 300, 55)
    assert len(off.job["patches"]) == 10


def test_sweep_job_matches_in_a_fresh_interpreter():
    plan = sr.plan_roth_sweep(SINGLE, 300, 55)
    small = dict(plan.job, calls=[[fn, p, [a[0], 6, a[2]]] for fn, p, a in plan.job["calls"][::4]])
    mini = sr.Plan("roth", plan.key, plan.overrides, small, plan.finish)
    server = [mc_jobs.dumps(r) for r in sr.run_plan_calls(mini)]
    child = ("import sys, json\nsys.path.insert(0, sys.argv[1])\nfrom retirement_sim import mc_jobs\n"
             "n = mc_jobs.browser_load('j', sys.stdin.read())\n"
             "print(json.dumps([mc_jobs.browser_run('j', i) for i in range(n)]))\n")
    out = subprocess.run([sys.executable, "-c", child, _ROOT], input=mc_jobs.dumps(small),
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == server


def test_browser_outcome_replies_are_checked():
    call = ["outcomes", 0, [55, 4, 1000]]
    assert bc._plausible(call, {"bits": "10-1", "finals": [1.0, 0.0, 2.0], "taxes": [0.0, 0.0, 1.0]})
    assert not bc._plausible(call, {"bits": "101", "finals": [1.0, 0.0, 2.0], "taxes": [0, 0, 0]})
    assert not bc._plausible(call, {"bits": "10x1", "finals": [1.0] * 4, "taxes": [0.0] * 4})
    assert not bc._plausible(call, {"bits": "1011", "finals": [1.0], "taxes": [0.0]})


# ---------------------------------------------------------------- colors

def test_ramp_is_one_teal_hue_light_to_dark_with_readable_text():
    lo_fill, lo_ink = rt.cell_colors(0.70, 0.70, 0.80, dark=False)
    hi_fill, hi_ink = rt.cell_colors(0.80, 0.70, 0.80, dark=False)
    assert rt._luminance(rt._hex(lo_fill)) > rt._luminance(rt._hex(hi_fill))
    assert lo_ink == "#0f172a" and hi_ink == "#ffffff"
    d_lo, d_lo_ink = rt.cell_colors(0.70, 0.70, 0.80, dark=True)
    d_hi, d_hi_ink = rt.cell_colors(0.80, 0.70, 0.80, dark=True)
    assert rt._luminance(rt._hex(d_lo)) < rt._luminance(rt._hex(d_hi))   # dark mode: brighter = more
    assert d_lo_ink == "#ffffff" and d_hi_ink == "#0f172a"


# ---------------------------------------------------------------- UI

def _script():
    import os
    import sys
    sys.path[:0] = [os.environ["ROTH_TEST_UI"], os.path.dirname(os.environ["ROTH_TEST_UI"])]
    import streamlit as st
    from components import roth_optimizer_tab
    roth_optimizer_tab.render(st, results=st.session_state["results"])


def test_find_best_then_use_best_then_undo(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("ROTH_TEST_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    at = AppTest.from_function(_script, default_timeout=240)
    at.session_state["user_overrides"] = dict(SINGLE)
    at.session_state["n_simulations"] = 300
    at.session_state["results"] = {"primary_result": {"success_rate": 0.5, "retirement_age": 55,
                                                      "median_final": 1.0, "p10_final": 0.0},
                                   "earliest_retirement_age": 60}
    at.run()
    assert not at.exception, at.exception
    assert at.button(key="roth_sweep_btn").label == "Find my best Roth conversion plan"
    at.button(key="roth_sweep_btn").click().run()
    assert not at.exception, at.exception
    assert at.button(key="roth_sweep_btn").disabled                       # up to date
    md = " ".join(m.value for m in at.markdown)
    assert "mc-roth-grid" in md and "Fill the 12% bracket" in md and "Up to $200K/yr" in md
    res = at.session_state["roth_sweep_result"]
    assert ("BEST" in md)
    assert "No conversions" in md and "Your current setting" in md
    assert any(e.label == "Show as a table" for e in at.expander)
    table = at.dataframe[0].value
    assert "Median taxes in retirement" in table.columns and len(table) == 11

    best = res["cells"][res["best_key"]]
    use = at.button(key="roth_use_best")
    assert use.label.startswith("Use best: ")
    use.click().run()
    assert not at.exception, at.exception
    ov = at.session_state["user_overrides"]
    assert ov["ENABLE_ROTH_CONVERSION"] == bool(best["enabled"])
    if best["enabled"]:
        assert ov["ROTH_CONVERSION_TARGET_BRACKET"] == best["target"]
        assert ov["ROTH_CONVERSION_MAX_ANNUAL"] == best["cap"]
        assert at.session_state["sa_roth_target"] == best["target"]       # widgets synced
    assert at.button(key="roth_use_best").disabled
    assert any("Now using" in s.value for s in at.success)
    at.button(key="roth_undo").click().run()
    assert not at.exception, at.exception
    ov = at.session_state["user_overrides"]
    for k in ("ENABLE_ROTH_CONVERSION", "ROTH_CONVERSION_TARGET_BRACKET", "ROTH_CONVERSION_MAX_ANNUAL"):
        assert ov.get(k, "absent") == SINGLE.get(k, "absent")


def test_preview_pins_best_and_current_in_scenario_compare(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("ROTH_TEST_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    res = sr.run_roth_sweep(SINGLE, 300, 55)
    at = AppTest.from_function(_script, default_timeout=240)
    at.session_state["user_overrides"] = dict(SINGLE)
    at.session_state["n_simulations"] = 300
    at.session_state["results"] = {"primary_result": {"success_rate": 0.5, "retirement_age": 55}}
    at.session_state["roth_sweep_result"] = dict(res)                       # (stale hash: still drawn)
    at.run()
    assert not at.exception, at.exception
    at.button(key="roth_preview_best").click().run()
    assert not at.exception, at.exception
    pinned = at.session_state["pinned_scenarios"]
    names = list(pinned)
    assert names[0] == "Current plan" and names[1].startswith("Best Roth plan: ")
    best = res["cells"][res["best_key"]]
    assert pinned[names[1]]["summary"]["success_rate"] == pytest.approx(best["success"])
    assert pinned[names[1]]["overrides"]["ENABLE_ROTH_CONVERSION"] == bool(best["enabled"])


def _side_script():
    import os
    import sys
    sys.path[:0] = [os.environ["ROTH_TEST_UI"], os.path.dirname(os.environ["ROTH_TEST_UI"])]
    import streamlit as st
    from components import sec_assumptions
    sec_assumptions.render_investing_body(st)


def test_sidebar_caption_says_income_before_deduction_and_the_bracket(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("ROTH_TEST_UI", _UI)
    at = AppTest.from_function(_side_script, default_timeout=60)
    at.session_state["user_overrides"] = {"FILING_STATUS": "Married filing jointly"}
    at.run()
    assert not at.exception, at.exception
    cap = " ".join(c.value for c in at.caption)
    assert "Income before the \\$32,200 standard deduction. \\$100,800: partway into the 12% bracket." in cap
    at.number_input(key="sa_roth_target").set_value(133_000).run()
    cap = " ".join(c.value for c in at.caption)
    assert "\\$133,000: ≈ top of the 12% bracket." in cap
    assert at.session_state["user_overrides"]["ROTH_CONVERSION_TARGET_BRACKET"] == 133_000
