"""The Income tile's "Where this year's pay goes" Sankey.

* sim_runner.working_year_flows: every dollar of pay lands in exactly one place
  (taxes, pre-tax savings, take-home), take-home (plus any shortfall) is all spent
  or saved, and the spending is the engine's own figure for that year.
* income_flow_chart: nodes and streams for single people, couples on two returns,
  the after-tax 401(k), a fixed take-home comp row and a shortfall; employer money
  is a note, never a stream; the pinned layout never stacks nodes on each other.
* The tile's plot-type switch draws the chart (AppTest).
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components.profile_picker import PROFILES
from components import income_flow_chart as ifc
from retirement_sim import account_simulation as sim
from retirement_sim import config as cfg
from utils import sim_runner as sr


def _couple(**extra):
    return dict(PROFILES["Mid-career couple (40, kids)"], TARGET_RETIREMENT_AGE=48, **extra)


def _single(**extra):
    return dict(PROFILES["Young professional (28, single)"], TARGET_RETIREMENT_AGE=60, **extra)


def _balanced(f):
    pay = f["you"] + f["partner"] + f["social_security"]
    split = (f["you_tax"] + f["partner_tax"] + f["your_401k"] + f["partner_401k"]
             + f["your_hsa"] + f["take_home"])
    used = (f["spending_total"] + f["roth"] + f["after_tax_401k"] + f["plan_529"]
            + f["brokerage"] + f["left_over"])
    assert pay == pytest.approx(split, abs=1.0)
    assert f["take_home"] + f["shortfall"] == pytest.approx(used, abs=1.0)
    assert f["federal"] + f["state"] + f["fica"] == pytest.approx(
        f["you_tax"] + f["partner_tax"], abs=1.0)
    assert sum(f["spending"].values()) == pytest.approx(f["spending_total"], abs=0.01)
    assert min([f["brokerage"], f["shortfall"], f["left_over"], *f["spending"].values()]) >= 0


@pytest.mark.parametrize("ov, age", [(_couple(), 40), (_couple(), 45), (_single(), 30)])
def test_every_dollar_lands_once(ov, age):
    f = sr.working_year_flows(ov, age, ov["TARGET_RETIREMENT_AGE"])
    _balanced(f)
    assert f["age"] == age and f["gross"] > 0


def test_pay_and_taxes_are_the_engines_working_year_cashflow():
    ov = _couple()
    f = sr.working_year_flows(ov, 42, 48)
    original = sr._apply_overrides(sr.build_config_overrides(ov))
    try:
        cf = sim.working_year_cashflow(42, partner_working=True)
    finally:
        sr._restore_overrides(original)
    assert f["federal"] == pytest.approx(cf["federal"])
    assert f["take_home"] == pytest.approx(cf["your_take_home"] + cf["partner_take_home"])
    assert f["gross"] == pytest.approx(cf["gross_income"])


def test_spending_is_the_engines_spending_log():
    """The year's spending equals what simulate_accumulation_year logs for it."""
    ov = _couple()
    f = sr.working_year_flows(ov, 43, 48)
    original = sr._apply_overrides(sr.build_config_overrides(ov))
    try:
        ok, portfolio = sim.run_detailed_simulation(48, random_seed=7)
        logged = next(r["living"] for r in portfolio.spending_log if r["age"] == 43)
    finally:
        sr._restore_overrides(original)
    assert f["spending_total"] == pytest.approx(logged, rel=1e-9)
    # Split into the app's expense categories plus housing and children.
    assert {"Mortgage", "Children", "Food & groceries", "Utilities"} <= set(f["spending"])


def test_config_is_left_as_it_was():
    before = (cfg.YOUR_AGE, cfg.CURRENT_ANNUAL_EXPENSES, cfg.PARTNER_AGE)
    sr.working_year_flows(_single(), 31, 60)
    assert (cfg.YOUR_AGE, cfg.CURRENT_ANNUAL_EXPENSES, cfg.PARTNER_AGE) == before


def _graph(f, compact=False):
    nodes, links = ifc.flow_graph(f, compact)
    return {k: name for k, name, _ in nodes}, links


def test_single_person_has_no_partner_node_and_no_empty_nodes():
    f = sr.working_year_flows(_single(), 28, 60)
    names, links = _graph(f)
    assert names["you"] == "Your pay" and "partner" not in names
    assert names["roth"] == "Roth IRA" and names["k401"] == "401(k)"
    for key in ("p529", "at401k", "short", "left", "ss"):     # zero this year
        assert key not in names
    assert all(v > 0.5 for _, _, v in links)


def test_employer_money_is_a_note_not_a_stream():
    f = sr.working_year_flows(_couple(), 40, 48)
    names, links = _graph(f)
    assert f["employer"]["401(k) match"] > 0
    assert not any("match" in n.lower() or "employer" in n.lower() for n in names.values())
    pay_out = sum(v for a, _, v in links if a in ("you", "partner", "ss"))
    assert pay_out == pytest.approx(f["gross"], abs=1.0)        # match not in pay
    text = ifc.caption(f)
    assert "employers add" in text and "401(k) match and HSA deposit" in text


def test_shortfall_is_a_source_not_a_negative_brokerage():
    ov = dict(PROFILES["Median US 25-year-old household"], TARGET_RETIREMENT_AGE=60)
    f = sr.working_year_flows(ov, 28, 60)
    assert f["shortfall"] > 0 and f["brokerage"] == 0
    _balanced(f)
    names, links = _graph(f)
    assert names["short"] == "Shortfall from savings" and "brk" not in names
    assert ("short", "spend", pytest.approx(f["shortfall"])) in [(a, b, v) for a, b, v in links]
    assert "draws it from savings" in ifc.caption(f)


def test_two_returns_and_after_tax_401k():
    ov = _couple(YOUR_AFTER_TAX_401K_PCT=0.10, FILING_STATUS="Single")
    f = sr.working_year_flows(ov, 41, 48)
    assert f["two_returns"] and f["after_tax_401k"] > 0
    _balanced(f)
    names, _ = _graph(f)
    assert names["at401k"] == "After-tax 401(k)" and names["partner"] == "Partner"


def test_fixed_take_home_comp_row():
    table = {a: {"base": 200_000, "bonus": 30_000, "rsu_gross": 15_000, "after_tax": 150_000}
             for a in range(40, 48)}
    f = sr.working_year_flows(_couple(YOUR_COMPENSATION_BY_AGE=table), 40, 48)
    assert f["your_take_home"] == pytest.approx(150_000)
    _balanced(f)


def test_phone_version_is_pay_to_taxes_saving_spending():
    f = sr.working_year_flows(_couple(), 40, 48)
    names, links = _graph(f, compact=True)
    assert set(names) == {"pay", "taxes", "saving", "spend"}
    assert sum(v for _, _, v in links) == pytest.approx(f["gross"], abs=1.0)


def test_pinned_layout_never_overlaps():
    f = sr.working_year_flows(_couple(), 40, 48)
    fig = ifc.build_figure(f)
    node = fig.data[0].node
    height = ifc._HEIGHT[False] - ifc._MARGIN["t"] - ifc._MARGIN["b"]
    nodes, links = ifc.flow_graph(f)
    value = {k: 0.0 for k, _, _ in nodes}
    for a, b, v in links:
        value[b] += v
    for k in value:
        value[k] = max(value[k], sum(v for a, _, v in links if a == k))
    scale = None
    by_col = {}
    for (k, _, _), x, y in zip(nodes, node.x, node.y):
        by_col.setdefault(x, []).append((y, value[k]))
    cols = list(by_col.values())
    scale = min((height - ifc._PAD[False] * (len(c) - 1)) / sum(v for _, v in c) for c in cols)
    for col in cols:
        col.sort()
        for (y0, v0), (y1, v1) in zip(col, col[1:]):
            gap = (y1 - y0) * height - (v0 + v1) * scale / 2
            assert gap >= ifc._PAD[False] - 0.5
        for y, v in col:
            assert 0 <= y * height - v * scale / 2 and y * height + v * scale / 2 <= height + 0.5


def test_hover_shows_dollars_and_share_of_gross_and_text_is_theme_colored():
    f = sr.working_year_flows(_couple(), 40, 48)
    for dark in (False, True):
        tr = ifc.build_figure(f, dark=dark).data[0]
        assert "of gross pay" in tr.link.hovertemplate and "$%{value:,.0f}" in tr.link.hovertemplate
        assert tr.textfont.color == ifc._TEXT[dark]
        assert set(tr.node.color) <= set(ifc.KIND_COLORS[dark].values())


# ------------------------------------------------------------------ the tile (AppTest)

def _script():
    import os
    import sys
    sys.path[:0] = [os.environ["IFC_TEST_UI"], os.path.dirname(os.environ["IFC_TEST_UI"])]
    import streamlit as st
    from components import income_over_time
    income_over_time.render(st, results=None)


def test_both_income_charts_show_and_the_age_picker_moves_the_sankey(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("IFC_TEST_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    at = AppTest.from_function(_script, default_timeout=90)
    at.session_state["user_overrides"] = _couple()
    at.run()
    assert not at.exception, at.exception
    assert not [r for r in at.radio if r.key == "income_over_time_main_plot_type"]   # no switch now
    assert [r for r in at.radio if r.key == "income_over_time_main_dollars_mode"]     # over-time chart
    age = at.slider(key="income_over_time_main_flow_age")                             # and the Sankey
    assert (age.min, age.max, age.value) == (40, 47, 40)
    age.set_value(45).run()
    assert not at.exception, at.exception
    assert any("You save" in c.value for c in at.caption)
