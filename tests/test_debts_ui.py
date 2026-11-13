"""Debts in the planner UI: the Debts sidebar section (components/sec_debts.py),
the Debt payoff tile (components/debt_payoff.py), their numbers
(utils/debt_view.py), profiles and widget sync, and how the Money check-up and
the planner share debts (utils/simple_to_full.py, app.py's version switch)."""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import debts as dm  # noqa: E402
from utils import debt_view as dv  # noqa: E402
from utils import derived  # noqa: E402
from utils import simple_to_full as s2f  # noqa: E402
from utils.profile_io import deserialize_overrides, serialize_overrides  # noqa: E402
from utils.simple_finance import DEFAULT_INPUTS, normalize_inputs  # noqa: E402

CARD = {"name": "Visa", "kind": "credit_card", "balance": 6_000.0, "apr": 0.24, "min_payment": 180.0}
SCHOOL = {"name": "School", "kind": "student_loan", "balance": 20_000.0, "apr": 0.05, "min_payment": 212.0}
CAR = {"name": "Car", "kind": "car", "balance": 9_000.0, "apr": 0.069, "min_payment": 300.0}
BASE = {"YOUR_AGE": 35, "PARTNER_AGE": 0, "CHILDREN": [], "SPEND_RENT_MONTHLY": 1_500,
        "HOME_VALUE": 0, "MORTGAGE_MONTHLY": 0, "TARGET_RETIREMENT_AGE": 55}
WITH_DEBTS = {**BASE, "DEBTS": [CARD, SCHOOL], "DEBT_EXTRA_MONTHLY": 100, "DEBT_STRATEGY": "avalanche"}


def _script():
    import os
    import sys
    sys.path[:0] = [os.environ["DT_TEST_UI"], os.path.dirname(os.environ["DT_TEST_UI"])]
    import streamlit as st
    from components import debt_payoff, sec_debts, sec_expenses
    if os.environ.get("DT_TEST_WHAT") != "tile":
        sec_expenses.render(st)
        sec_debts.render(st)
    with st.container(border=True, key="mc-tile-debts"):
        debt_payoff.render(st)


@pytest.fixture
def draw(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("DT_TEST_UI", UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")

    def make(overrides, what="all"):
        monkeypatch.setenv("DT_TEST_WHAT", what)
        at = AppTest.from_function(_script, default_timeout=60)
        at.session_state["user_overrides"] = dict(overrides)
        at.run()
        assert not at.exception, at.exception
        return at
    return make


def _captions(at):
    return [c.value.replace("\\$", "$") for c in at.caption]


def _html(at):
    return "\n".join(m.value for m in at.markdown)


# ---------------------------------------------------------------- sidebar section

def test_add_edit_and_remove_debts(draw):
    at = draw(BASE)
    assert any("mortgage stays in House" in c for c in _captions(at))
    assert at.session_state["user_overrides"]["DEBTS"] == []
    assert not [w for w in at.number_input if w.key == "debt_extra"]          # only with debts
    at.button(key="debt_add").click().run()
    at.text_input(key="debt_0_name").set_value("Visa")
    at.number_input(key="debt_0_balance").set_value(6_000)
    at.number_input(key="debt_0_apr").set_value(24.0)
    at.number_input(key="debt_0_min").set_value(180).run()
    at.button(key="debt_add").click().run()
    at.text_input(key="debt_1_name").set_value("School")
    at.selectbox(key="debt_1_kind").set_value("student_loan")
    at.number_input(key="debt_1_balance").set_value(20_000)
    at.number_input(key="debt_1_apr").set_value(5.0)
    at.number_input(key="debt_1_min").set_value(212)
    at.number_input(key="debt_extra").set_value(100)
    at.radio(key="debt_strategy").set_value("snowball").run()
    assert not at.exception, at.exception
    ov = at.session_state["user_overrides"]
    assert ov["DEBTS"] == [CARD, SCHOOL]
    assert ov["DEBT_EXTRA_MONTHLY"] == 100 and ov["DEBT_STRATEGY"] == "snowball"
    summary = next(c for c in _captions(at) if c.startswith("Owed:"))
    assert "$26,000" in summary and "$492" in summary and "debt-free by" in summary
    # Remove the first: the second moves up, widgets and all.
    at.button(key="debt_rm_0").click().run()
    assert at.session_state["user_overrides"]["DEBTS"] == [SCHOOL]
    assert at.text_input(key="debt_0_name").value == "School"
    assert "debt_1_name" not in at.session_state


def test_expenses_total_counts_the_payments_in_the_same_run(draw):
    at = draw(WITH_DEBTS)
    line = next(c for c in _captions(at) if c.startswith("Per year:"))
    assert "debt payments $5,904 (Debts)" in line                         # (180 + 212 + 100) x 12
    at.number_input(key="debt_extra").set_value(200).run()                 # Expenses draws first
    line = next(c for c in _captions(at) if c.startswith("Per year:"))
    assert "debt payments $7,104 (Debts)" in line


def test_underwater_and_never_paid_off_warnings(draw):
    at = draw({**BASE, "DEBTS": [{"name": "Store card", "balance": 10_000, "apr": 0.30,
                                  "min_payment": 100}]})
    assert any("isn't paid off" in w.value or "aren't paid off" in w.value for w in at.warning)
    assert any("doesn't cover its monthly interest" in c for c in _captions(at))


# ---------------------------------------------------------------- tile

def test_tile_without_debts_prompts_and_teaches(draw):
    at = draw(BASE, what="tile")
    assert "No debts in your plan" in _html(at)
    exp = [e for e in at.get("status") if e.label == "Things to know about debt"]   # an expander with an icon
    assert exp and "Educational information, not financial advice" in " ".join(_captions(at))


def test_tile_numbers_match_the_payoff_math(draw):
    at = draw(WITH_DEBTS, what="tile")
    html = _html(at)
    p = dm.amortize([CARD, SCHOOL], 100, "avalanche")
    s = dv.summary(WITH_DEBTS)
    assert s.months == p.months and abs(s.interest - p.total_interest) < 1e-9
    assert s.debt_free in html and "Interest still to pay" in html
    # status in words, not colour alone
    assert "High interest (8%+)" in html and "Moderate (4–8%)" in html
    assert "Your plan" in html and "Avalanche" in html and "Snowball" in html
    assert "Things to know about debt" in [e.label for e in at.get("status")]


def test_pay_more_moves_the_date(draw):
    at = draw(WITH_DEBTS, what="tile")
    w = dv.what_if(WITH_DEBTS, 100)
    assert w["months_saved"] > 0 and w["interest_saved"] > 0
    assert f"{dv.duration(w['months_saved'])} sooner" in _html(at)
    at.number_input(key="debt_whatif").set_value(400).run()
    w4 = dv.what_if(WITH_DEBTS, 400)
    assert w4["months_saved"] > w["months_saved"]
    assert f"{dv.duration(w4['months_saved'])} sooner" in _html(at)
    assert at.session_state["user_overrides"]["DEBT_EXTRA_MONTHLY"] == 100    # a what-if only


def test_avalanche_and_snowball_differ_when_they_should():
    small_low = {"name": "Small", "balance": 1_500.0, "apr": 0.05, "min_payment": 50.0}
    big_high = {"name": "Big", "balance": 8_000.0, "apr": 0.25, "min_payment": 200.0}
    cmp = dv.compare({"DEBTS": [small_low, big_high], "DEBT_EXTRA_MONTHLY": 300})
    av, sb = cmp["avalanche"], cmp["snowball"]
    assert av["interest"] < sb["interest"]
    assert sb["first_win_months"] < av["first_win_months"] and sb["first_name"] == "Small"
    from components.debt_payoff import plans_html, verdict
    html = plans_html(cmp, "snowball")
    assert html.count("Least interest") == 1 and html.count("Quickest first win") == 1
    assert "saves" in verdict(cmp)


def test_retirement_effect_follows_the_rate():
    """Paying more on a 24% card leaves more at retirement than investing at the
    plan's return; paying more on a 3% loan leaves less."""
    card = {"YOUR_AGE": 35, "DEBTS": [CARD]}
    cheap = {"YOUR_AGE": 35, "DEBTS": [{**SCHOOL, "apr": 0.03}]}
    assert dv.retirement_effect(card, 200, 55) > 0
    assert dv.retirement_effect(cheap, 200, 55) < 0
    assert dv.retirement_effect({"YOUR_AGE": 35}, 200, 55) is None


def test_worked_examples_are_computed():
    from components.debt_payoff import things_to_know_md
    m = dv.minimum_only_example()
    assert 200 < m["months"] < 260 and m["interest"] > dv.EXAMPLE_BALANCE    # ~19.5 years, > $8k
    text = things_to_know_md()
    assert dv.years_text(m["months"]) in text
    for needle in ("APR", "employer", "emergency", "balance transfer", "studentaid.gov",
                   "utilization", "Public Service Loan Forgiveness"):
        assert needle.lower() in text.lower()


# ---------------------------------------------------------------- derived figures

def test_this_years_spending_and_savings_include_the_payments():
    pay = 12 * (180 + 212 + 100)
    assert derived.debt_payments_this_year(WITH_DEBTS) == pay
    assert derived.compute_expenses_today(WITH_DEBTS) - derived.compute_expenses_today(BASE) == pay
    full = {**BASE, "YOUR_BASE_SALARY": 120_000}
    assert (derived.savings_budget(full)["disposable"]
            - derived.savings_budget({**full, **{k: WITH_DEBTS[k] for k in
                                                ("DEBTS", "DEBT_EXTRA_MONTHLY")}})["disposable"]) == pay


def test_spending_chart_and_projection_show_the_debts():
    from components.spending_chart import _debt_payments
    from components.net_worth_projection_chart import _debt_relief
    ages = list(range(35, 45))
    real = _debt_payments(WITH_DEBTS, ages)
    nominal = _debt_payments(WITH_DEBTS, ages, nominal=True)
    assert real[0] == nominal[0] == 12 * 492 and real[1] < nominal[1] and real[-1] == 0.0
    relief = _debt_relief(WITH_DEBTS)
    assert relief[0] == 0.0 and relief[-1] == 12 * 492


def test_net_worth_nets_out_the_debts():
    from utils import sim_runner as sr
    from components.top_bar import _resolve_net_worth
    orig = sr._apply_overrides(sr.build_config_overrides({"DEBTS": []}))
    try:
        before = cfg.TOTAL_NET_WORTH
    finally:
        sr._restore_overrides(orig)
    orig = sr._apply_overrides(sr.build_config_overrides({"DEBTS": [CARD, SCHOOL]}))
    try:
        assert cfg.TOTAL_NET_WORTH == before - 26_000
    finally:
        sr._restore_overrides(orig)
    assert (_resolve_net_worth(None, {"YOUR_CASH": 50_000})
            - _resolve_net_worth(None, {"YOUR_CASH": 50_000, "DEBTS": [CARD]})) == 6_000


# ---------------------------------------------------------------- profiles and widget sync

def test_profile_round_trip_keeps_debts():
    back = deserialize_overrides(serialize_overrides(WITH_DEBTS))
    assert back["DEBTS"] == [CARD, SCHOOL] and back["DEBT_EXTRA_MONTHLY"] == 100
    assert back["DEBT_STRATEGY"] == "avalanche"


def test_loading_a_profile_reseeds_and_clears_the_rows():
    from types import SimpleNamespace
    from utils.widget_sync import reset_input_widget_state, sync_widgets_from_overrides
    st = SimpleNamespace(session_state={"user_overrides": WITH_DEBTS})
    sync_widgets_from_overrides(st)
    ss = st.session_state
    assert ss["debt_0_name"] == "Visa" and ss["debt_0_apr"] == 24.0 and ss["debt_1_min"] == 212
    assert ss["debt_extra"] == 100 and ss["debt_strategy"] == "avalanche"
    # An older profile has no debts: after the reset + sync no row is left.
    ss["debt_whatif"] = 300
    reset_input_widget_state(st)
    ss["user_overrides"] = dict(BASE)
    sync_widgets_from_overrides(st)
    assert not [k for k in ss if str(k).startswith("debt_")]


def test_an_older_profile_without_debts_draws_no_rows(draw):
    at = draw(BASE)
    assert not [w for w in at.text_input if str(w.key).startswith("debt_")]
    assert at.session_state["user_overrides"]["DEBTS"] == []


# ---------------------------------------------------------------- check-up <-> planner

CHECKUP = {**DEFAULT_INPUTS, "gross_salary_annual": 80_000.0, "needs_monthly": 2_600.0,
           "wants_monthly": 900.0, "cash_savings": 5_000.0}


def test_checkup_debts_become_the_planners_without_double_counting():
    ov = s2f.carried(CHECKUP)
    mins = sum(d["min_payment"] for d in DEFAULT_INPUTS["debts"])
    assert len(ov["DEBTS"]) == 3 and ov["DEBT_EXTRA_MONTHLY"] == 150
    assert ov["DEBTS"][1] == {"name": "Car loan", "kind": "car", "balance": 4_200.0,
                              "apr": 0.069, "min_payment": 250.0}
    assert ov["SPEND_OTHER_MONTHLY"] == 2_600 - mins
    # planner spending + this year's debt payments = the check-up's needs + wants + extra
    spend = sum(ov.get(k, 0) for k in ("SPEND_OTHER_MONTHLY", "SPEND_DISCRETIONARY_MONTHLY"))
    assert spend * 12 + derived.debt_payments_this_year(ov) == (2_600 + 900 + 150) * 12


def test_planner_debts_come_back_to_the_checkup():
    planner = {"YOUR_AGE": 30, "PARTNER_AGE": 0, "YOUR_BASE_SALARY": 90_000,
               "SPEND_FOOD_MONTHLY": 600, "SPEND_DISCRETIONARY_MONTHLY": 400,
               "SPEND_RENT_MONTHLY": 1_500, "DEBTS": [CARD, CAR], "DEBT_EXTRA_MONTHLY": 75}
    no_debts = {k: v for k, v in planner.items() if not k.startswith("DEBT")}
    r, base = s2f.from_planner(planner), s2f.from_planner(no_debts)
    assert [d["name"] for d in r["debts"]] == ["Visa", "Car"]
    assert r["debts"][0] == {"name": "Visa", "balance": 6_000.0, "apr_pct": 24.0,
                             "min_payment": 180.0, "kind": "credit_card"}
    assert r["extra_debt_payment_monthly"] == 75
    assert r["needs_monthly"] == pytest.approx(base["needs_monthly"] + 480)   # minimums are needs
    assert r["wants_monthly"] == base["wants_monthly"]
    # and back again: the same debts
    assert s2f.planner_debts(r) == {"DEBTS": [CARD, CAR], "DEBT_EXTRA_MONTHLY": 75}


def test_switching_versions_copies_debts_both_ways():
    simple = normalize_inputs({**CHECKUP, "debts": [], "extra_debt_payment_monthly": 0})
    planner = {"DEBTS": [CARD], "DEBT_EXTRA_MONTHLY": 50}
    new = s2f.debts_to_checkup(simple, planner)
    assert [d["name"] for d in new["debts"]] == ["Visa"]
    assert new["needs_monthly"] == simple["needs_monthly"] + 180
    assert s2f.debts_to_checkup(new, planner) is None                       # nothing to change
    assert s2f.debts_to_planner(new, planner) is None
    edited = normalize_inputs({**new, "debts": new["debts"] + [
        {"name": "Car", "balance": 9_000, "apr_pct": 6.9, "min_payment": 300, "kind": "car"}]})
    assert s2f.debts_to_planner(edited, planner)["DEBTS"] == [CARD, CAR]
    # the example numbers are never copied, and a planner that never had debts leaves them alone
    assert s2f.debts_to_planner(DEFAULT_INPUTS, planner) is None
    assert s2f.debts_to_checkup(DEFAULT_INPUTS, {"DEBTS": []}) is None


def test_the_version_switch_shares_debts(monkeypatch):
    from streamlit.testing.v1 import AppTest, element_tree as et

    def indices(self):                     # AppTest cannot rerun a segmented control otherwise
        values = [self.value] if isinstance(self.value, str) else self.value
        return [self.options.index(self.format_func(v)) for v in values]
    monkeypatch.setattr(et.ButtonGroup, "indices", property(indices))
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    at = AppTest.from_file(os.path.join(UI, "app.py"), default_timeout=120).run()
    at.button(key="device_skip").click().run()
    next(b for b in at.button if b.label == "Open the retirement planner").click().run()
    at.button(key="gs_skip").click().run()
    assert not at.exception, at.exception
    at.session_state["user_overrides"] = {**at.session_state["user_overrides"],
                                          "DEBTS": [CARD], "DEBT_EXTRA_MONTHLY": 50}
    [r for r in at.radio if r.key == "mode_switch_full"][-1].set_value("Money check-up").run()
    assert not at.exception, at.exception
    simple = at.session_state["simple_inputs"]
    assert [d["name"] for d in simple["debts"]] == ["Visa"] and simple["extra_debt_payment_monthly"] == 50
    assert at.text_input(key="simple_w_debt_0_name").value == "Visa"
    at.number_input(key="simple_w_debt_0_balance").set_value(4_000).run()
    at.radio(key="mode_switch_simple").set_value("Retirement planner").run()
    assert not at.exception, at.exception
    assert at.session_state["user_overrides"]["DEBTS"] == [{**CARD, "balance": 4_000.0}]
    assert at.session_state["debt_0_balance"] == 4_000
