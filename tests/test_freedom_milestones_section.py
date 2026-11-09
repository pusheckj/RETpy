"""The Freedom milestones section, drawn with Streamlit's AppTest.

Covers drawing with and without a run, the edge cases (no partner, no balances),
the place editor, custom places, the saved settings, stale-check detection and the
Confirm button. The rules themselves are tested in test_milestones.py.
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

from tests.conftest import load_sample_household  # noqa: E402
from utils import places as pl  # noqa: E402


def _script():
    import os
    import sys
    sys.path[:0] = [os.environ["MS_TEST_UI"], os.path.dirname(os.environ["MS_TEST_UI"])]
    import streamlit as st
    from components import freedom_milestones
    freedom_milestones.render(st, st.session_state.get("results"))


def _draw(monkeypatch, overrides, results=None, n_sims=200):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("MS_TEST_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    at = AppTest.from_function(_script, default_timeout=120)
    at.session_state["user_overrides"] = dict(overrides)
    at.session_state["results"] = results
    at.session_state["n_simulations"] = n_sims
    at.run()
    assert not at.exception, at.exception
    return at


def _md(at):
    return "\n".join(m.value for m in at.markdown)


def _fake_results(ages, values):
    return {"earliest_retirement_age": 46,
            "primary_result": {"median_trajectory": list(zip(ages, values)), "retirement_age": 45}}


def test_draws_without_a_run(monkeypatch):
    at = _draw(monkeypatch, load_sample_household())
    text = _md(at)
    assert "Freedom milestones" in text and "of " in text and "reached" in text
    assert "Coast FIRE" in text and "Freedom by place" in text and "Other markers" in text
    confirms = [b.key for b in at.button if b.key and b.key.startswith("ms_confirm_")]
    assert len(confirms) == len(pl.BUILT_IN)
    assert any("simple projection" in c.value for c in at.caption)
    assert not at.error


def test_draws_with_a_run_and_says_so(monkeypatch):
    ages = list(range(34, 96))
    vals = [840_000 * 1.06 ** i for i in range(len(ages))]
    at = _draw(monkeypatch, load_sample_household(), _fake_results(ages, vals))
    assert any("median path" in c.value for c in at.caption)


@pytest.mark.parametrize("name,patch", [
    ("no partner", {"PARTNER_AGE": 0, "PARTNER_CASH": 0}),
    ("no balances", {k: 0 for k in ("YOUR_401K", "YOUR_ROTH_IRA", "YOUR_TRADITIONAL_IRA", "YOUR_HSA",
                                    "YOUR_BROKERAGE", "YOUR_CASH", "PARTNER_401K", "PARTNER_ROTH_IRA",
                                    "PARTNER_BROKERAGE", "PARTNER_CASH", "HOME_VALUE", "MORTGAGE_BALANCE")}),
    ("retirement age passed", {"TARGET_RETIREMENT_AGE": 30}),
    ("rich", {"YOUR_BROKERAGE": 400_000_000}),
    ("empty profile", None),
])
def test_edge_cases_draw(monkeypatch, name, patch):
    ov = {} if patch is None else {**load_sample_household(), **patch}
    at = _draw(monkeypatch, ov)
    assert not at.exception
    assert "Freedom milestones" in _md(at)


def test_results_missing_ages_are_handled(monkeypatch):
    at = _draw(monkeypatch, load_sample_household(), {"primary_result": {}})
    assert not at.exception


def test_rate_setting_is_saved_with_the_profile(monkeypatch):
    at = _draw(monkeypatch, load_sample_household())
    at.number_input(key="ms_rate").set_value(3.5).run()
    assert not at.exception
    state = pl.get_state(at.session_state["user_overrides"])
    assert state["settings"]["rate"] == pytest.approx(0.035)
    assert "3.50%" in _md(at) or at.number_input(key="ms_rate").value == 3.5
    at.number_input(key="ms_rate").set_value(4.0).run()                 # back to the default
    assert pl.KEY not in at.session_state["user_overrides"]


def test_editing_a_place_changes_its_fire_number_and_is_saved(monkeypatch):
    at = _draw(monkeypatch, load_sample_household())
    before = _md(at)
    at.selectbox(key="ms_edit_pick").select("midwest").run()
    at.number_input(key="ms_edit_factor_midwest").set_value(0.5)
    at.button(key="FormSubmitter:ms_edit_form_midwest-Save place").click().run()
    assert not at.exception
    ov = at.session_state["user_overrides"]
    assert pl.get_state(ov)["edits"]["midwest"]["factor"] == 0.5
    assert "0.50&times; costs" in _md(at) and "0.50&times; costs" not in before
    assert [b for b in at.button if b.key == "ms_reset_midwest"]        # reset appears once edited
    at.button(key="ms_reset_midwest").click().run()
    assert pl.KEY not in at.session_state["user_overrides"]


def test_add_and_remove_a_custom_place(monkeypatch):
    at = _draw(monkeypatch, load_sample_household())
    at.text_input(key="ms_new_name").set_value("Lisbon <b>")
    at.number_input(key="ms_new_factor").set_value(0.7)
    at.selectbox(key="ms_new_tax").select(pl.TAX_NONE)
    at.button(key="FormSubmitter:ms_new_form-Add place").click().run()
    assert not at.exception
    state = pl.get_state(at.session_state["user_overrides"])
    assert [c["name"] for c in state["custom"]] == ["Lisbon <b>"]
    assert any(b.key == "ms_confirm_c1" for b in at.button)
    text = _md(at)
    assert "Lisbon &lt;b&gt;" in text and "Lisbon <b>" not in text       # names are escaped
    at.button(key="ms_remove_c1").click().run()
    assert pl.get_state(at.session_state["user_overrides"])["custom"] == []


def test_adding_with_no_name_asks_for_one(monkeypatch):
    at = _draw(monkeypatch, load_sample_household())
    at.button(key="FormSubmitter:ms_new_form-Add place").click().run()
    assert not at.exception
    assert pl.KEY not in at.session_state["user_overrides"]
    assert any("Enter a name" in c.value for c in at.caption)


def test_removed_built_in_place_disappears_and_comes_back(monkeypatch):
    at = _draw(monkeypatch, load_sample_household())
    at.selectbox(key="ms_edit_pick").select("thailand").run()
    at.button(key="ms_remove_thailand").click().run()
    assert not any(b.key == "ms_confirm_thailand" for b in at.button)
    at.button(key="ms_restore").click().run()
    assert any(b.key == "ms_confirm_thailand" for b in at.button)


def test_confirm_runs_the_simulation_and_goes_stale_when_the_place_changes(monkeypatch):
    at = _draw(monkeypatch, load_sample_household(), n_sims=200)
    at.button(key="ms_confirm_here").click().run()
    assert not at.exception, at.exception
    res = at.session_state["ms_res_here"]
    assert 0.0 <= res["success_at_target"] <= 1.0 and "earliest_retirement_age" in res
    assert "Simulation check" in _md(at) and "Out of date" not in _md(at)
    btn = at.button(key="ms_confirm_here")
    assert btn.disabled and "Confirmed" in btn.label
    # Change the place: the old check no longer matches.
    at.selectbox(key="ms_edit_pick").select("here").run()
    at.number_input(key="ms_edit_factor_here").set_value(0.5)
    at.button(key="FormSubmitter:ms_edit_form_here-Save place").click().run()
    assert "Out of date" in _md(at)
    assert not at.button(key="ms_confirm_here").disabled


def test_editing_a_place_does_not_make_the_main_run_look_stale(monkeypatch):
    from utils import sim_runner as sr
    at = _draw(monkeypatch, load_sample_household())
    before = sr._hashable(at.session_state["user_overrides"])
    at.selectbox(key="ms_edit_pick").select("texas").run()
    at.number_input(key="ms_edit_factor_texas").set_value(0.6)
    at.button(key="FormSubmitter:ms_edit_form_texas-Save place").click().run()
    assert sr._hashable(at.session_state["user_overrides"]) == before


def test_loading_another_profile_clears_the_section_widgets():
    from utils.widget_sync import reset_input_widget_state

    class _St:
        session_state = {"ms_rate": 3.0, "ms_res_here": {}, "ms_edit_pick": "texas", "keep_me": 1}

    reset_input_widget_state(_St)
    assert _St.session_state == {"keep_me": 1}


def test_confirm_goes_to_the_browser_when_its_workers_are_ready(monkeypatch):
    """With browser workers ready the place check is handed over as a plan of plain
    calls, and the stored result is the same as the server's would be."""
    from utils import browser_compute as bc
    from utils import sim_runner as sr
    sent = {}

    def fake_submit(st, kind, plan, on_done, run_here=(), progress_callback=None):
        sent["kind"], sent["plan"], sent["done"] = kind, plan, on_done
        # Run it the way the browser would: the calls here, then the plan's finish.
        on_done(sr.finish_plan(plan, sr.run_plan_calls(plan)))

    monkeypatch.setattr(bc, "ready", lambda st: True)
    monkeypatch.setattr(bc, "submit", fake_submit)
    at = _draw(monkeypatch, load_sample_household(), n_sims=200)
    at.button(key="ms_confirm_midwest").click().run()
    assert not at.exception, at.exception
    assert sent["kind"] == "place:midwest"
    assert {c[0] for c in sent["plan"].job["calls"]} == {"scan", "batch"}
    assert sent["plan"].job["base"]["RETIREMENT_STATE_CHOICE"] == "OH"
    assert "ms_res_midwest" in at.session_state
    assert "Simulation check" in _md(at)
