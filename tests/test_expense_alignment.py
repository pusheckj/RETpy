"""Expenses section <-> Spending tab: same categories, and one click makes the
plan's monthly inputs match the statements (synthetic statements only)."""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, UI, os.path.dirname(os.path.abspath(__file__))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from test_spending_dashboard import APPLE_CARD_CSV, FIDELITY_CSV, VENMO_CSV  # noqa: E402


def _script():
    """The Expenses section, then the Spending tab's sync control and table data.
    (AppTest can't rerun the whole tab: its segmented controls break AppTest's
    widget-state replay, so reruns use the tab's own pieces; the full tab is
    drawn once in test_full_tab_shows_the_control.)"""
    import os
    import sys
    sys.path.insert(0, os.environ["SPENDING_TEST_UI_DIR"])
    import streamlit as st
    from components import sec_expenses, spending_dashboard as sd
    with st.sidebar:
        sec_expenses.render_body(st)
    data = sd.statement_data(st)
    if data is not None:
        sd.sync_control(st, data, "sp_use_actual")
        st.session_state["_table"] = sd.plan_vs_actual(st.session_state["user_overrides"],
                                                       sd.session_actual(st, data))


def _full_tab():
    import os
    import sys
    sys.path.insert(0, os.environ["SPENDING_TEST_UI_DIR"])
    import streamlit as st
    from components import sec_expenses, spending_dashboard
    with st.sidebar:
        sec_expenses.render_body(st)
    spending_dashboard.render(st)


@pytest.fixture
def app(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    (tmp_path / "card").mkdir()
    (tmp_path / "card" / "fid.csv").write_text(FIDELITY_CSV, encoding="utf-8")
    (tmp_path / "venmo.csv").write_text(VENMO_CSV, encoding="utf-8")
    (tmp_path / "apple.csv").write_text(APPLE_CARD_CSV, encoding="utf-8")
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    monkeypatch.setenv("SPENDING_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SPENDING_TEST_UI_DIR", UI)

    def make(script=_script, **overrides):
        at = AppTest.from_function(script, default_timeout=60)
        at.session_state["user_overrides"] = dict(overrides)
        return at.run()
    return make


def _captions(at):
    return [c.value for c in at.caption]


def test_partner_spending_has_an_input_with_a_partner(app):
    at = app(PARTNER_AGE=30, PARTNER_OTHER_MONTHLY=1800)
    assert not at.exception, at.exception
    assert at.number_input(key="se_partner").value == 1800
    at.number_input(key="se_partner").set_value(2100).run()
    ov = at.session_state["user_overrides"]
    assert ov["PARTNER_OTHER_MONTHLY"] == 2100 and ov["PARTNER_MONTHLY_SPENDING"] == 2100


def test_single_household_spends_nothing_for_a_partner(app):
    at = app(PARTNER_AGE=0, PARTNER_OTHER_MONTHLY=1500, PARTNER_MONTHLY_SPENDING=1500)
    assert not at.exception, at.exception
    assert "se_partner" not in [n.key for n in at.number_input]
    ov = at.session_state["user_overrides"]
    assert ov["PARTNER_OTHER_MONTHLY"] == 0 and ov["PARTNER_MONTHLY_SPENDING"] == 0


def test_one_click_makes_both_screens_match(app):
    at = app(PARTNER_AGE=30, HOME_VALUE=500_000, MORTGAGE_MONTHLY=1_000,
             SPEND_FOOD_MONTHLY=5, PARTNER_OTHER_MONTHLY=1800)
    assert not at.exception, at.exception
    assert any("differ" in c and "from your statements" in c for c in _captions(at))
    assert not at.button(key="se_use_actual").disabled

    at.button(key="sp_use_actual").click().run()
    assert not at.exception, at.exception
    matched = [c for c in _captions(at) if c.startswith("✓ Matches your statements")]
    assert len(matched) == 2                                 # Expenses section and Spending tab
    assert at.button(key="se_use_actual").disabled and at.button(key="sp_use_actual").disabled
    ov = at.session_state["user_overrides"]
    assert at.number_input(key="se_food").value == ov["SPEND_FOOD_MONTHLY"] != 5
    assert at.number_input(key="se_mortgage_monthly").value == ov["MORTGAGE_MONTHLY"] != 1_000
    assert ov["UTILITIES_MONTHLY"] == ov["SPEND_UTILITIES_MONTHLY"]
    assert ov["PARTNER_OTHER_MONTHLY"] == 1800               # no estimate in these statements
    table = at.session_state["_table"].set_index("Expense category")
    assert table.loc["Partner spending"].isna()["Actual"]
    assert (table.drop(index="Partner spending")["Difference"] == 0).all()


def test_full_tab_shows_the_control(app):
    at = app(_full_tab, PARTNER_AGE=30, HOME_VALUE=500_000, MORTGAGE_MONTHLY=1_000)
    assert not at.exception, at.exception
    assert {"se_use_actual", "sp_use_actual"} <= {b.key for b in at.button}
    table = at.dataframe[0].value.set_index("Expense category")
    assert table.loc["Partner spending", "Actual"] == "—"
    assert table.loc["Housing", "Your plan"] == "$1,000"


def test_editing_an_input_updates_the_status_in_the_same_run(app):
    at = app(PARTNER_AGE=30, HOME_VALUE=500_000, MORTGAGE_MONTHLY=1_000)
    at.button(key="se_use_actual").click().run()
    at.number_input(key="se_food").set_value(at.number_input(key="se_food").value + 50).run()
    assert any(c.startswith("Food & groceries differs from your statements") for c in _captions(at))


def test_without_statements_the_section_points_to_the_spending_tab(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")             # uploads only, none uploaded
    monkeypatch.setenv("SPENDING_TEST_UI_DIR", UI)

    def _sidebar_only():
        import os
        import sys
        sys.path.insert(0, os.environ["SPENDING_TEST_UI_DIR"])
        import streamlit as st
        from components import sec_expenses
        sec_expenses.render_body(st)

    at = AppTest.from_function(_sidebar_only, default_timeout=60).run()
    assert not at.exception, at.exception
    assert any("Add your statements in the Spending tab" in c for c in _captions(at))
    assert "se_use_actual" not in [b.key for b in at.button]
