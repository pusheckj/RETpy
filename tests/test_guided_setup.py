"""Check-up answers carry into the planner, and the guided setup walks a new
planner visitor through the rest (utils/simple_to_full.py,
components/guided_setup.py, app.py routing + the version switch)."""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(_ROOT, "ui")
APP = os.path.join(UI, "app.py")
for _p in (_ROOT, UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import simple_to_full as s2f  # noqa: E402
from utils.derived import KEEP_AMOUNTS_MODE  # noqa: E402
from utils.simple_finance import DEFAULT_INPUTS  # noqa: E402
from components import guided_setup as gs  # noqa: E402

CHECKUP = {**DEFAULT_INPUTS, "gross_salary_annual": 80_000.0, "needs_monthly": 2_600.0,
           "wants_monthly": 900.0, "cash_savings": 5_000.0, "retirement_contrib_pct": 5.0,
           "employer_match_pct": 4.0, "ira_contrib_annual": 1_000.0}


# ---------------------------------------------------------------- the mapping

def test_example_numbers_are_never_copied():
    assert not s2f.used(DEFAULT_INPUTS) and not s2f.used(None) and s2f.used(CHECKUP)


def test_checkup_answers_map_onto_planner_keys():
    ov = s2f.carried(CHECKUP)
    assert ov["YOUR_BASE_SALARY"] == 80_000 and ov["YOUR_CASH"] == 5_000
    assert ov["YOUR_401K_CONTRIBUTION"] == 4_000 and ov["YOUR_401K_MATCH_PCT"] == 0.04
    assert ov["YOUR_BACKDOOR_ROTH"] == 1_000 and ov["YOUR_HSA_CONTRIBUTION"] == 0  # not HSA-eligible
    assert ov["SAVINGS_MODE"] == KEEP_AMOUNTS_MODE and ov["YOUR_BROKERAGE_CONTRIBUTION"] == 0
    # total spending = the check-up's until housing is asked: all needs in Other
    assert ov["SPEND_OTHER_MONTHLY"] == 2_600 and ov["SPEND_DISCRETIONARY_MONTHLY"] == 900
    assert ov["SPEND_RENT_MONTHLY"] == ov["MORTGAGE_MONTHLY"] == ov["HOME_VALUE"] == 0
    assert ov["SPEND_FOOD_MONTHLY"] == ov["SPEND_UTILITIES_MONTHLY"] == 0


def test_housing_comes_out_of_other_and_values_fit_the_inputs():
    assert s2f.spending_split(CHECKUP, 1_400)["SPEND_OTHER_MONTHLY"] == 1_200
    assert s2f.spending_split(CHECKUP, 9_999)["SPEND_OTHER_MONTHLY"] == 0
    huge = s2f.carried({**CHECKUP, "needs_monthly": 900_000.0, "gross_salary_annual": 9e7,
                        "retirement_contrib_pct": 100.0, "hsa_eligible": True,
                        "hsa_contrib_annual": 50_000.0})
    assert huge["SPEND_OTHER_MONTHLY"] == 20_000 and huge["YOUR_BASE_SALARY"] == s2f.SALARY_MAX
    assert huge["YOUR_401K_CONTRIBUTION"] == s2f.CONTRIB_401K_MAX
    assert huge["YOUR_HSA_CONTRIBUTION"] == s2f.CONTRIB_MAX


def test_keep_amounts_mode_gets_the_engines_sweep():
    """account_simulation invests un-spent income for any mode starting "Auto"."""
    assert KEEP_AMOUNTS_MODE.startswith("Auto")
    src = open(os.path.join(_ROOT, "retirement_sim", "account_simulation.py"), encoding="utf-8").read()
    assert 'savings_mode.startswith("Auto")' in src


def test_restore_repairs_saved_state():
    assert gs.restore(None) is None and gs.restore({"status": "nope"}) is None
    r = gs.restore({"status": "active", "step": 99, "seen": ["gs_age", 3], "checkup": "x"})
    assert r == {"status": "active", "step": 0, "seen": ["gs_age"], "checkup": None}


def test_other_state_tax_defaults_to_a_state_rate():
    from retirement_sim import config as cfg
    from utils.widget_sync import DIRECT_MAPPINGS
    assert cfg.YOUR_MARGINAL_TAX_RATE == 0.05
    assert DIRECT_MAPPINGS["st_marginal"][1](None) == 5.0


# ---------------------------------------------------------------- the walkthrough

def _setup_script():
    import os
    import sys
    sys.path[:0] = [os.environ["GS_TEST_UI"], os.path.dirname(os.environ["GS_TEST_UI"])]
    import streamlit as st
    from components import guided_setup
    if not guided_setup.started(st):
        guided_setup.begin(st, st.session_state.get("simple_inputs"))
    if guided_setup.active(st):
        guided_setup.render(st)
    elif guided_setup.skipped(st):
        guided_setup.render_banner(st)


@pytest.fixture
def wizard(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("GS_TEST_UI", UI)

    def make(simple=None, **overrides):
        at = AppTest.from_function(_setup_script, default_timeout=60)
        at.session_state["user_overrides"] = {"YOUR_AGE": 25, "PARTNER_AGE": 25,
                                              "PARTNER_401K": 7_000, "YEARS_UNTIL_FIRST_CHILD": 3,
                                              "FIRST_CHILD_MONTHLY_COST": 2_100, **overrides}
        if simple is not None:
            at.session_state["simple_inputs"] = simple
        return at.run()
    return make


def _next(at):
    at.button(key="gs_next").click().run()
    assert not at.exception, at.exception
    return at.session_state["setup"]


def _walk_to(at, step_title):
    """Answer each step minimally until ``step_title`` is showing."""
    answers = {
        "About you": lambda: (at.number_input(key="gs_age").set_value(31),
                              at.radio(key="gs_household").set_value(gs.JUST_ME)),
        "Children": lambda: (at.number_input(key="gs_kids_have").set_value(0),
                         at.number_input(key="gs_kids_plan").set_value(0)),
        "Where you live": lambda: at.selectbox(key="gs_state").set_value("California"),
        "Your income": lambda: at.number_input(key="gs_salary").set_value(
            at.number_input(key="gs_salary").value or 70_000),
        "Your home": lambda: (at.radio(key="gs_home").set_value(gs.RENT).run(),
                              at.number_input(key="gs_rent").set_value(1_400)),
    }
    for _ in range(len(gs.STEPS)):
        title = gs.STEPS[at.session_state["setup"]["step"]].title
        if title == step_title:
            return
        if title in answers:
            answers[title]()
        _next(at)
    raise AssertionError(f"never reached {step_title}")


def test_required_answers_hold_the_step(wizard):
    at = wizard()
    assert at.session_state["setup"]["checkup"] is None
    assert at.number_input(key="gs_age").value is None            # never the sample's 25
    s = _next(at)
    assert s["step"] == 0 and s["error"] == "Enter your age to continue."
    assert any("Enter your age" in w.value for w in at.warning)


def test_a_value_typed_right_before_next_is_kept(wizard):
    at = wizard()
    at.number_input(key="gs_age").set_value(40)
    at.radio(key="gs_household").set_value(gs.JUST_ME)
    s = _next(at)                                                   # one run: edit + click
    assert s["step"] == 1 and at.session_state["user_overrides"]["YOUR_AGE"] == 40


def test_just_me_clears_the_sample_partner(wizard):
    at = wizard()
    _walk_to(at, "Children")
    ov = at.session_state["user_overrides"]
    assert ov["PARTNER_AGE"] == 0 and ov["PARTNER_401K"] == 0 and ov["FILING_STATUS"] == "Single"


def test_kids_any_number(wizard):
    """One child is one child (the old step stored a phantom second child at
    $0), and three born plus two planned are five."""
    at = wizard()
    _walk_to(at, "Children")
    assert not any("up to two" in c.value for c in at.caption)
    at.number_input(key="gs_kids_have").set_value(1).run()
    at.number_input(key="gs_kid0_age").set_value(6)
    at.number_input(key="gs_kids_plan").set_value(0)
    _next(at)
    kids = at.session_state["user_overrides"]["CHILDREN"]
    assert [(k["years_until_birth"], k["monthly_cost"]) for k in kids] == [(-6, 2_100)]
    at.button(key="gs_back").click().run()
    assert at.number_input(key="gs_kids_have").value == 1                    # answers kept
    assert at.number_input(key="gs_kid0_age").value == 6
    at.number_input(key="gs_kids_have").set_value(3).run()
    at.number_input(key="gs_kid1_age").set_value(2)
    at.number_input(key="gs_kid2_age").set_value(9)
    at.number_input(key="gs_kids_plan").set_value(2).run()
    at.number_input(key="gs_kids_in").set_value(1)
    _next(at)
    kids = at.session_state["user_overrides"]["CHILDREN"]
    assert [k["years_until_birth"] for k in kids] == [-9, -6, -2, 1, 4]       # oldest first
    assert [k["monthly_cost"] for k in kids] == [2_100] + [1_400] * 4


def test_kids_need_every_age_and_at_most_six(wizard):
    at = wizard()
    _walk_to(at, "Children")
    at.number_input(key="gs_kids_have").set_value(2).run()
    at.number_input(key="gs_kid0_age").set_value(4)
    at.number_input(key="gs_kids_plan").set_value(0)
    assert _next(at)["error"] == "Enter each child's age."
    at.number_input(key="gs_kid1_age").set_value(1)
    at.number_input(key="gs_kids_plan").set_value(5).run()
    at.number_input(key="gs_kids_in").set_value(2)
    assert "up to 6" in _next(at)["error"]


def test_checkup_answers_prefill_and_housing_comes_out_of_other(wizard):
    at = wizard(simple=CHECKUP)
    assert at.session_state["setup"]["checkup"]["needs"] == 2_600
    _walk_to(at, "Your income")
    assert at.number_input(key="gs_salary").value == 80_000
    assert at.caption[0].value.startswith("✓ From your check-up.")
    _walk_to(at, "Saving each year")
    assert at.number_input(key="gs_401k_pct").value == 5.0
    assert at.radio(key="gs_invest").value == gs.KEEP
    _walk_to(at, "Monthly spending")
    assert at.session_state["user_overrides"]["SPEND_OTHER_MONTHLY"] == 1_200   # 2,600 - 1,400 rent
    assert any("✓ Matches your check-up" in m.value for m in at.markdown)


def test_finishing_hands_over_to_the_planner(wizard):
    at = wizard(simple=CHECKUP)
    _walk_to(at, "All set")
    assert any("**Income:**" in m.value for m in at.markdown)
    s = _next(at)
    assert s["status"] == "done"
    assert at.session_state["ay_your_age"] == 31                    # side panel synced
    assert at.session_state["sv_mode"] == KEEP_AMOUNTS_MODE
    assert at.session_state["results"] is None and "_autorun_done" not in at.session_state


def test_skip_then_continue(wizard):
    at = wizard()
    at.button(key="gs_skip").click().run()
    assert at.session_state["setup"]["status"] == "skipped"
    assert "gs_resume" in [b.key for b in at.button]
    at.button(key="gs_resume").click().run()
    assert at.session_state["setup"]["status"] == "active"


# ---------------------------------------------------------------- the app

def _app(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.button(key="device_skip").click().run()
    return at


def test_planner_from_the_welcome_screen_starts_the_walkthrough(monkeypatch):
    at = _app(monkeypatch)
    next(b for b in at.button if b.label == "Open the retirement planner").click().run()
    assert not at.exception, at.exception
    assert at.session_state["setup"]["status"] == "active"
    assert at.session_state["setup"]["checkup"] is None
    assert not at.sidebar.children                                  # no side panel yet
    assert at.radio(key="mode_switch_full").value == "Retirement planner"


def test_switching_from_the_checkup_copies_it_and_back_keeps_both(monkeypatch):
    at = _app(monkeypatch)
    next(b for b in at.button if b.label == "Start the money check-up").click().run()
    at.number_input(key="simple_w_gross_salary_annual").set_value(91_000).run()
    at.radio(key="mode_switch_simple").set_value("Retirement planner").run()
    assert not at.exception, at.exception
    assert at.session_state["app_mode"] == "full"
    assert at.session_state["user_overrides"]["YOUR_BASE_SALARY"] == 91_000
    at.number_input(key="gs_age").set_value(29).run()
    at.radio(key="mode_switch_full").set_value("Money check-up").run()
    assert at.session_state["app_mode"] == "simple"
    assert at.number_input(key="simple_w_gross_salary_annual").value == 91_000
    at.radio(key="mode_switch_simple").set_value("Retirement planner").run()
    assert at.number_input(key="gs_age").value == 29                # walkthrough answer kept


def test_step_bar_is_not_a_progress_bar():
    """A progress bar on the page is what animations.js reads as "a simulation
    is running" (it shows the Simulating overlay)."""
    src = open(os.path.join(UI, "components", "guided_setup.py"), encoding="utf-8").read()
    assert "st.progress(" not in src and "mc-setup-bar" in src
    assert ".stProgress" in open(os.path.join(UI, "components", "animations.py"), encoding="utf-8").read()


def test_entered_values_are_labelled_your_plan():
    from components.top_bar import _resolve_names
    assert _resolve_names("Custom (keep current values)") == "Your plan"


def _savings_script():
    import os
    import sys
    sys.path[:0] = [os.environ["GS_TEST_UI"], os.path.dirname(os.environ["GS_TEST_UI"])]
    import streamlit as st
    from components import sec_savings
    sec_savings.render_body(st)


def test_keep_amounts_mode_in_the_savings_section(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("GS_TEST_UI", UI)
    at = AppTest.from_function(_savings_script, default_timeout=60)
    at.session_state["user_overrides"] = {
        "SAVINGS_MODE": KEEP_AMOUNTS_MODE, "PARTNER_AGE": 0, "YOUR_BASE_SALARY": 80_000,
        "YOUR_401K_CONTRIBUTION": 4_000, "YOUR_BROKERAGE_CONTRIBUTION": 9_999,
        "PARTNER_401K_CONTRIBUTION": 5_000}
    at.run()
    assert not at.exception, at.exception
    assert at.radio(key="sv_mode").value == KEEP_AMOUNTS_MODE
    assert at.number_input(key="sv_manual_your_401k").value == 4_000
    assert "sv_manual_your_brk" not in [n.key for n in at.number_input]   # the rest is swept
    ov = at.session_state["user_overrides"]
    assert ov["YOUR_BROKERAGE_CONTRIBUTION"] == 0 and ov["PARTNER_401K_CONTRIBUTION"] == 0


def test_single_parent_files_head_of_household(wizard):
    at = wizard()
    _walk_to(at, "Children")                                      # "Just me" on step one
    at.number_input(key="gs_kids_have").set_value(1).run()
    at.number_input(key="gs_kid0_age").set_value(7)
    at.number_input(key="gs_kids_plan").set_value(0)
    _next(at)
    assert at.session_state["user_overrides"]["FILING_STATUS"] == "Head of household"


def test_an_unanswered_question_opens_blank_after_skip_and_continue(wizard):
    """Skipping step 1 without answering, then "Continue setup", must not show
    the sample household's age as if it were the visitor's."""
    at = wizard()
    assert at.number_input(key="gs_age").value is None
    at.button(key="gs_skip").click().run()
    at.button(key="gs_resume").click().run()
    assert at.number_input(key="gs_age").value is None
    at.number_input(key="gs_age").set_value(41).run()     # an answered one does come back
    at.button(key="gs_skip").click().run()
    at.button(key="gs_resume").click().run()
    assert at.number_input(key="gs_age").value == 41
