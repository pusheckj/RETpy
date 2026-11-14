"""Round-2 UI fixes: wording, empty states, honest projection, no silent clamps."""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _read(*parts):
    return open(os.path.join(_ROOT, *parts), encoding="utf-8").read()


class _Rec:
    """A stand-in for ``st`` that records what a chart draws."""
    def __init__(self, overrides=None):
        self.session_state = {"user_overrides": overrides or {}}
        self.calls = []

    def __getattr__(self, name):
        def call(*a, **k):
            self.calls.append((name, a, k))
            return _Ctx() if name == "popover" else None
        return call

    def texts(self, kind):
        return [a[0] for n, a, _ in self.calls if n == kind and a]


# ---- wording ----------------------------------------------------------------

def test_child_tax_credit_is_no_longer_called_unmodeled():
    for path in (("ui", "components", "sec_taxes.py"), ("ui", "components", "faq.py")):
        text = _read(*path)
        assert "tax credits (such as the child tax credit)" not in text
    assert "Not modeled**: tax credits (such as" not in _read("ui", "components", "sec_taxes.py")
    assert "city and county income taxes and the child tax credit" not in _read("README.md").lower()
    assert "No federal tax credits (e.g. the child tax credit)" not in _read("docs", "METHODOLOGY.md")


def test_tax_legend_does_not_say_working_years_only():
    from components.tax_tab import _series
    labels = [name for name, _ in _series({"state_label": "State (CA)"})]
    assert "State (CA)" in labels
    src = _read("ui", "components", "tax_tab.py")
    assert "working years)" not in src


# ---- empty states -----------------------------------------------------------

def test_success_by_age_says_so_when_no_age_works():
    from components import success_by_age
    st = _Rec()
    success_by_age.render(st, {"success_rate_by_age": {30: 0.0, 31: 0.0, 32: 0.001},
                               "config_snapshot": {"TARGET_SUCCESS_RATE": 0.8}})
    assert any("No retirement age" in t for t in st.texts("info"))
    assert not any(n == "plotly_chart" for n, _, _ in st.calls)


def test_first_decade_stress_says_so_when_nothing_is_left():
    from components import first_decade_stress
    rows = [{"age": a, "p10": 0.0, "p50": 0.0} for a in range(50, 60)]
    st = _Rec({"YOUR_AGE": 40, "TARGET_RETIREMENT_AGE": 50})
    first_decade_stress.render(st, {"primary_result": {"networth_by_year": rows}})
    assert any("already gone" in t for t in st.texts("info"))


# ---- the projection pays the deficit ---------------------------------------

def test_projection_takes_overspending_out_of_savings():
    from components.net_worth_projection_chart import project_net_worth
    from tests.test_presets_plausible import as_the_planner_runs_it
    from components.profile_picker import PROFILES
    ov = as_the_planner_runs_it(PROFILES["Median US 25-year-old household"])
    ov.update({"YOUR_BASE_SALARY": 30_000, "PARTNER_AGE": 0, "PARTNER_BASE_SALARY": 0,
               "YOUR_CASH": 20_000, "TARGET_RETIREMENT_AGE": 40})
    proj = project_net_worth(ov)
    totals = [sum(proj["by_account"][k][i] for k in proj["by_account"]) for i in range(len(proj["ages"]))]
    assert proj["deficit"] > 0
    assert totals[-1] < totals[0]          # it used to climb with a stated deficit


def test_projection_has_no_deficit_when_pay_covers_spending():
    from components.net_worth_projection_chart import project_net_worth
    from tests.test_presets_plausible import as_the_planner_runs_it
    from components.profile_picker import PROFILES
    ov = as_the_planner_runs_it(PROFILES["Young professional (28, single)"])
    assert project_net_worth(ov)["deficit"] == 0


# ---- slider floors ----------------------------------------------------------

def test_retirement_sliders_start_at_your_own_age():
    from components.sec_retirement_goals import _retire_floor
    from utils.age_limits import TARGET_MAX, TARGET_MIN
    assert _retire_floor(38) == 38
    assert _retire_floor(20) == TARGET_MIN
    assert _retire_floor(99) == TARGET_MAX - 1          # a slider always has a range


# ---- no silent clamps -------------------------------------------------------

def _boxes():
    import streamlit as st
    from utils import widget_guard
    widget_guard.install(st)
    st.number_input("Salary", min_value=0, max_value=1_000, step=1, key="sal")
    st.number_input("Plain", min_value=0, max_value=10, step=1, key="plain")


def test_a_number_box_says_when_it_moved_a_saved_value():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_boxes, default_timeout=30)
    at.session_state["sal"] = 4_500
    at.run()
    assert not at.exception, at.exception
    assert at.number_input(key="sal").value == 1_000
    notes = [c.value for c in at.caption]
    assert any("4,500" in n and "0 to 1,000" in n and "1,000 is used" in n for n in notes), notes
    assert len(notes) == 1                                    # only the box that moved
    at.run()                                                  # the note stays while the box holds the used value
    assert any("is used" in c.value for c in at.caption)
    at.number_input(key="sal").set_value(500).run()
    assert not at.caption


def test_loaded_values_clamped_by_sync_get_the_same_note():
    from utils.widget_guard import note_text

    class S:
        session_state = {"k": 250_000, "_sync_notes": {"k": (400_000, 250_000)}}
    assert "400,000" in note_text(S, "k", 0, 250_000) and "250,000 is used" in note_text(S, "k", 0, 250_000)
    S.session_state["k"] = 100                                # the user changed it: no note
    assert note_text(S, "k", 0, 250_000) is None


def test_realistic_ceilings_hold_saved_values():
    from utils.widget_sync import DIRECT_MAPPINGS
    def cast(k, v):
        return DIRECT_MAPPINGS[k][1](v)
    assert cast("sa_roth_target", 400_000) == 400_000
    assert cast("si_your_base", 3_000_000) == 3_000_000
    assert cast("si_your_rsu", 6_000_000) == 6_000_000
    assert cast("sa_fee_bps", 0.0125) == 125
    assert cast("sv_match_pct", 0.30) == 30
    assert cast("rg_your_fra", 6_000) == 6_000
    assert cast("sa_roth_stop", 60) == 60


def test_slider_says_when_the_range_moved_under_its_value():
    from streamlit.testing.v1 import AppTest

    def app():
        import os, sys
        sys.path[:0] = [os.environ["F3_UI"]]
        import streamlit as st
        from utils.slider_input import slider_with_box
        lo = st.session_state.get("lo", 25)
        slider_with_box(st, "Target", lo, 99, 1, key="tgt", value=30)
    os.environ["F3_UI"] = _UI
    at = AppTest.from_function(app, default_timeout=30)
    at.run()
    at.session_state["lo"] = 40
    at.run()
    assert at.slider(key="tgt").value == 40
    assert any("30 is outside 40 to 99" in c.value for c in at.caption), [c.value for c in at.caption]


# ---- presets ----------------------------------------------------------------

def test_mid_career_couple_spends_like_a_family():
    from components.profile_picker import PROFILES
    p = PROFILES["Mid-career couple (40, kids)"]
    living = sum(p[k] for k in ("SPEND_UTILITIES_MONTHLY", "SPEND_FOOD_MONTHLY", "SPEND_TRANSPORT_MONTHLY",
                                "SPEND_HEALTH_MONTHLY", "SPEND_DISCRETIONARY_MONTHLY", "SPEND_OTHER_MONTHLY"))
    assert living >= 5_000                                    # a family of four, not the single-person boxes
    assert p["YOUR_401K_CONTRIBUTION"] == 24_500 and p["YOUR_HSA_CONTRIBUTION"] == 8_750


# ---- the top card -----------------------------------------------------------

def test_top_card_marks_a_success_rate_from_old_inputs():
    from components import top_bar
    results = {"primary_result": {"success_rate": 0.93}, "config_snapshot": {"TOTAL_NET_WORTH": 34_000}}
    ov = {"YOUR_401K": 100_000, "YOUR_BASE_SALARY": 90_000, "TARGET_RETIREMENT_AGE": 60}
    for stale, expect in ((False, False), (True, True)):
        st = _Rec()
        slots = [_Ctx(), _Ctx(), _Ctx()]
        top_bar.render(st, results=results, overrides=ov, profile="x", control_slots=slots, stale=stale)
        html = "".join(st.texts("markdown"))
        assert ("old inputs" in html) is expect
        assert ("$100.0K" in html) is stale                  # net worth is live once stale, not the run's snapshot
        assert ("$34.0K" in html) is (not stale)


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False
