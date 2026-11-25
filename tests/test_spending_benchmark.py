"""Spending tab: "Your spending vs similar households".

The numbers come from utils/budget_compare.py (see tests/test_budget_compare.py); these tests
cover what the page shows: the table, the pickers, the credit, and that it needs no statements.
"""
import os
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_UI = os.path.join(os.path.dirname(_TESTS), "ui")
for _p in (os.path.dirname(_TESTS), _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import budget_compare as bc  # noqa: E402
from components import spending_benchmark as sb  # noqa: E402

from .test_budget_compare import FAMILY, SD  # noqa: E402
from .test_spending_upload import UPLOADS  # noqa: E402,F401


def _script():
    import os
    import sys
    sys.path[:0] = [os.environ["SB_TEST_UI"], os.path.dirname(os.environ["SB_TEST_UI"])]
    import streamlit as st
    from components import spending_benchmark
    spending_benchmark.render(st)


@pytest.fixture
def draw(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SB_TEST_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")

    def make(overrides):
        at = AppTest.from_function(_script, default_timeout=60)
        at.session_state["user_overrides"] = dict(overrides)
        at.run()
        assert not at.exception, at.exception
        return at
    return make


def _captions(at):
    return " ".join(c.value.replace("\\$", "$") for c in at.caption)


def _table(at):
    return at.dataframe[0].value


def test_the_table_has_a_row_per_group_and_a_total(draw):
    at = draw({**FAMILY, "BENCH_AREA": SD})
    df = _table(at)
    assert list(df["Category"]) == ["Housing and utilities", "Food & groceries", "Transportation",
                                    "Healthcare premiums", "Fun and discretionary", "Other", "Total"]
    assert list(df.columns) == ["Category", "You, a month", "Typical, a month", "Typical range", "You are"]
    rows, _ = bc.spending_rows({**FAMILY, "BENCH_AREA": SD})
    assert df["Typical, a month"][6] == f"${rows[-1].typical:,.0f}"
    assert df["You, a month"][0] == "$3,250"                          # rent 3,000 plus utilities 250
    assert df["You are"][0] == "Typical"                              # within 10% of a 1-bedroom rent x 1.25 for 2 adults
    assert df["You are"][0] == sb.VERDICT[rows[0].verdict]
    assert " to " in df["Typical range"][0]


def test_a_row_with_no_figure_shows_a_dash_not_a_verdict(draw):
    at = draw({**FAMILY, "BENCH_AREA": SD, "SPEND_FOOD_MONTHLY": 0})
    df = _table(at)
    food = df[df["Category"] == "Food & groceries"].iloc[0]
    assert food["You, a month"] == "–" and food["You are"] == "–"
    assert df[df["Category"] == "Transportation"].iloc[0]["You are"] in ("Below typical", "Typical", "Above typical")


def test_the_page_names_the_household_the_group_and_the_place(draw):
    at = draw({**FAMILY, "BENCH_AREA": SD})
    text = _captions(at)
    assert f"Households with 2 adults, you aged 38, in the fourth 20% income group, near {SD}" in text
    at = draw(FAMILY)
    assert "near California. Your figures" in _captions(at)


def test_it_is_labelled_a_statistical_average_and_credits_its_sources(draw):
    text = _captions(draw(FAMILY))
    assert "This is a statistical average of what similar households spend. It is not a target and not advice" in text
    for credit in ("BiggerPockets Money", "BLS Consumer Expenditure Survey 2025", "BEA Regional Price Parities",
                   "HUD Fair Market Rents"):
        assert credit in text
    assert "docs/DATA_SOURCES.md" not in text            # a plain source line, not a file path
    assert "10% either side" in text


def test_every_sentence_of_the_page_copy_is_short(draw):
    import re
    for line in re.split(r"(?<=[.!?])\s+", _captions(draw({**FAMILY, "BENCH_AREA": SD}))):
        assert len(line.split()) <= 20, line


def test_it_says_what_is_left_out_and_what_was_folded_in(draw):
    text = _captions(draw(FAMILY))
    assert "retirement contribution and payroll tax line is not compared" in text
    assert "Includes the survey's clothing line" in text            # apparel folded into Fun
    assert "Includes your partner's own spending" in text
    assert "children's costs are not compared" in text
    assert "(the CE" not in text and "CE " not in text.replace("BLS Consumer Expenditure", "")


def test_the_income_group_defaults_to_your_pay_and_can_be_changed(draw):
    at = draw(FAMILY)
    pick = at.selectbox(key="sb_income")
    assert pick.value == "auto"
    before = _table(at)["Typical, a month"][6]
    pick.select("Q5").run()
    assert not at.exception, at.exception
    assert "top 20% income group" in _captions(at)
    assert _table(at)["Typical, a month"][6] != before
    assert at.session_state["user_overrides"]["BENCH_INCOME_GROUP"] == "Q5"   # saved with the plan
    at.selectbox(key="sb_income").select("auto").run()
    assert "BENCH_INCOME_GROUP" not in at.session_state["user_overrides"]


def test_a_saved_income_group_is_shown_on_load(draw):
    at = draw({**FAMILY, "BENCH_INCOME_GROUP": "Q2"})
    assert at.selectbox(key="sb_income").value == "Q2"
    assert "second 20% income group" in _captions(at)


def _both():
    import os
    import sys
    sys.path[:0] = [os.environ["SB_TEST_UI"], os.path.dirname(os.environ["SB_TEST_UI"])]
    import streamlit as st
    from components import sec_family, spending_benchmark
    sec_family.render_body(st)
    spending_benchmark.render(st)


def test_the_area_pickers_in_family_and_here_share_one_saved_area(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SB_TEST_UI", _UI)
    at = AppTest.from_function(_both, default_timeout=60)
    at.session_state["user_overrides"] = {**FAMILY, "CHILDREN": [{"years_until_birth": -1}]}
    at.run()
    assert not at.exception, at.exception
    assert at.selectbox(key="se_kid_area").value == "California (statewide average)"
    at.selectbox(key="se_kid_area_spend").select(SD).run()
    assert not at.exception, at.exception
    assert at.session_state["user_overrides"]["BENCH_AREA"] == SD
    assert at.selectbox(key="se_kid_area").value == SD               # Family follows
    at.selectbox(key="se_kid_area").select("California (statewide average)").run()
    assert "BENCH_AREA" not in at.session_state["user_overrides"]
    assert at.selectbox(key="se_kid_area_spend").value == "California (statewide average)"


def test_no_state_means_the_us_average_and_still_renders(draw):
    at = draw({**FAMILY, "STATE_CHOICE": "Other"})
    assert "near the US" in _captions(at)
    assert at.selectbox(key="se_kid_area_spend").value == "US average"


def test_statement_figures_replace_the_plan_in_the_comparison():
    rows_plan, _ = bc.spending_rows(FAMILY)
    actual = {"SPEND_FOOD_MONTHLY": 2_500, "SPEND_RENT_MONTHLY": 3_300}
    yours = sb.yours_from_actual(actual)
    assert yours == {"Food & groceries": 2_500.0, "Housing": 3_300.0}
    rows, _ = bc.spending_rows(FAMILY, yours=yours)
    assert rows[1].you == 2_500 and rows[0].you == 3_300 + 250
    assert rows[2].you == rows_plan[2].you                            # the rest stay the plan's
    assert sb.yours_from_actual(None) == {}


def test_the_spending_tab_shows_it_before_any_statements_are_loaded(monkeypatch, tmp_path):
    from components import spending_dashboard as sd
    from .test_spending_upload import _app
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    monkeypatch.setattr(sd, "SETTINGS_PATH", str(tmp_path / "none.json"))
    monkeypatch.delenv("SPENDING_DATA_DIR", raising=False)
    monkeypatch.setenv("SPENDING_TEST_UI_DIR", os.path.abspath(_UI))
    at = _app()
    assert not at.exception, at.exception
    assert any("Your spending vs similar households" in m.value for m in at.markdown)
    assert at.dataframe and "Typical, a month" in at.dataframe[0].value.columns


def test_the_spending_tab_compares_statement_averages_when_statements_are_loaded(monkeypatch):
    from .test_spending_upload import _app
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    monkeypatch.setenv("SPENDING_TEST_UI_DIR", os.path.abspath(_UI))
    at = _app(UPLOADS)
    assert not at.exception, at.exception
    assert any("Your spending vs similar households" in m.value for m in at.markdown)
    assert "your statements where they have the category" in _captions(at)


def test_the_money_checkup_shows_one_short_comparison_line():
    from streamlit.testing.v1 import AppTest

    def _script():
        import os
        import sys
        sys.path[:0] = [os.environ["SB_TEST_UI"], os.path.dirname(os.environ["SB_TEST_UI"])]
        import streamlit as st
        from components import simple_mode
        simple_mode.render(st)

    os.environ["SB_TEST_UI"] = _UI
    at = AppTest.from_function(_script, default_timeout=60)
    at.session_state["simple_inputs"] = {"gross_salary_annual": 65_000, "age": 30}
    at.run()
    assert not at.exception, at.exception
    text = _captions(at)
    assert "For comparison, households your age in the middle 20% income group typically spend about" in text
    assert "This is a statistical average, not advice" in text and "BiggerPockets Money" in text
    assert "BLS Consumer Expenditure Survey" in text and "CE" not in text.replace("Expenditure", "")
    import re
    assert all(len(s.split()) <= 20 for s in re.split(r"(?<=[.!?])\s+", text))
    at.session_state["simple_inputs"] = {"gross_salary_annual": 0, "age": 30}
    at.run()
    assert "For comparison, households your age" not in _captions(at)
