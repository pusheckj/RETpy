"""Charts and number formatting (QA round, fixer G3).

The Spending chart equals what the engine spends (partner line, health
insurance), the 4% rule line cannot flatten the bars, axes say "B" not "G",
numbers near a unit boundary pick the right unit, and a plan that fails in
year one still charts the whole horizon.
"""
import os
import sys

import plotly.graph_objects as go
import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components import spending_chart as sc  # noqa: E402
from retirement_sim.account_simulation import run_detailed_simulation  # noqa: E402
from utils import milestones, sim_runner as sr  # noqa: E402
from utils.formatting import money, money_precise, months_text  # noqa: E402
from utils.plot_theme import style_fig  # noqa: E402


# ---- number formatting ----------------------------------------------------

@pytest.mark.parametrize("value, text", [
    (999_999, "$1.0M"), (999_950, "$1.0M"), (999_499, "$999.5K"),
    (999_999_999, "$1.0B"), (1_234_567, "$1.2M"), (950, "$950"), (-999_999, "-$1.0M"),
])
def test_money_picks_the_unit_after_rounding(value, text):
    assert money(value, shorten=True) == text


def test_money_precise_never_says_1000k_or_1000m():
    assert money_precise(999_999) == "$1.0M"
    assert money_precise(999_999_999) == "$1.00B"


@pytest.mark.parametrize("value, text", [
    (999_600, "$1M"), (999_999_999, "$1B"), (-999_600, "-$1M"), (99_950, "$100K"),
    (999_499, "$999K"), (250_000, "$250K"), (1_500_000, "$1.5M"),
])
def test_short_money_picks_the_unit_after_rounding(value, text):
    assert milestones.short_money(value) == text


def test_months_text_reads_as_a_sentence():
    assert months_text(5.34) == "5.3 months"
    assert months_text(1.0) == "1 month"
    assert months_text(71.8) == "71.8 months"
    assert months_text(1_000_000.0) == "over 100 years"


def test_emergency_marker_names_the_goal_not_a_fraction():
    src = open(os.path.join(_UI, "utils", "milestones.py"), encoding="utf-8").read()
    assert "of {months} months" not in src
    assert "(goal: {months})" in src


# ---- axes -----------------------------------------------------------------

def test_billions_are_b_on_every_si_axis():
    fig = go.Figure(go.Scatter(x=[1, 2e9], y=[1, 2e9]))
    fig.update_yaxes(tickformat="$,.3~s")
    fig.update_xaxes(tickformat="~s", tickprefix="$")
    style_fig(fig, None)
    for ax in (fig.layout.yaxis, fig.layout.xaxis):
        assert not ax.tickformat
        assert ax.exponentformat == "B"
        assert ax.tickprefix == "$"


def test_stacked_bars_that_add_up_to_billions_count():
    fig = go.Figure([go.Bar(x=[1], y=[6e8]), go.Bar(x=[1], y=[6e8])])
    fig.update_layout(barmode="stack")
    fig.update_yaxes(tickformat="$,.3~s")
    style_fig(fig, None)
    assert fig.layout.yaxis.exponentformat == "B"


def test_axes_in_thousands_and_millions_keep_the_si_format():
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1e3, 5e8]))
    fig.update_yaxes(tickformat="$,.3~s")
    style_fig(fig, None)
    assert fig.layout.yaxis.tickformat == "$,.3~s"


def test_a_sub_dollar_axis_does_not_read_milli_dollars():
    fig = go.Figure(go.Scatter(x=[1, 2], y=[0.0, 0.0]))
    fig.update_yaxes(tickformat="$,.3~s")
    style_fig(fig, None)
    assert fig.layout.yaxis.exponentformat == "B"


def test_a_figure_without_si_axes_is_left_alone():
    fig = go.Figure(go.Bar(x=[1], y=[2]))
    fig.update_yaxes(tickformat="$,.0f")
    style_fig(fig, None)
    assert fig.layout.yaxis.tickformat == "$,.0f"
    assert fig.layout.yaxis.exponentformat is None


# ---- spending chart -------------------------------------------------------

_OV = {"YOUR_AGE": 38, "PARTNER_AGE": 36, "SPEND_FOOD_MONTHLY": 900, "SPEND_UTILITIES_MONTHLY": 200,
       "SPEND_RENT_MONTHLY": 2_000, "PARTNER_OTHER_MONTHLY": 1_500}


def _by_label(series):
    return {label: ys for label, _c, ys in series}


def test_partner_spending_is_its_own_band():
    ages = list(range(38, 60))
    series, _ = sc.build_category_series(ages, _OV, {}, 55)
    assert _by_label(series)["Partner's spending"] == [18_000.0] * len(ages)
    series, _ = sc.build_category_series(ages, {**_OV, "PARTNER_OTHER_MONTHLY": 0}, {}, 55)
    assert "Partner's spending" not in _by_label(series)


def test_working_years_total_matches_the_engine():
    # The chart's first year equals the household total the engine spends: housing,
    # the six categories and the partner's line (the QA persona's $18k a year).
    from utils.derived import compute_expenses_today
    ov = {**_OV, "SPEND_TRANSPORT_MONTHLY": 400, "SPEND_HEALTH_MONTHLY": 300,
          "SPEND_DISCRETIONARY_MONTHLY": 600, "SPEND_OTHER_MONTHLY": 250}
    series, _ = sc.build_category_series([38, 39], ov, {}, 55)
    assert sum(ys[0] for _l, _c, ys in series) == pytest.approx(compute_expenses_today(ov), rel=1e-9)


def test_health_insurance_band_comes_from_the_engines_premium():
    ages = list(range(58, 70))
    health = {a: (30_000.0 if a < 65 else 9_000.0) for a in ages}
    series, _ = sc.build_category_series(ages, {**_OV, "YOUR_AGE": 58}, {}, 58, health_by_age=health)
    ys = _by_label(series)["Health insurance (ACA, Medicare)"]
    assert ys[0] == 30_000.0 and ys[-1] == 9_000.0
    series, _ = sc.build_category_series(ages, {**_OV, "YOUR_AGE": 58}, {}, 58)
    assert "Health insurance (ACA, Medicare)" not in _by_label(series)


def test_engine_logs_the_premium_it_pays():
    _, p = run_detailed_simulation(45, random_seed=3)
    rows = {r["age"]: r for r in p.spending_log}
    assert all("health" in r for r in rows.values() if r["age"] >= 45)
    assert rows[45]["health"] > 0           # ACA before Medicare


def test_housing_label_fits_the_home():
    ages = list(range(68, 80))
    paid_off = {"YOUR_AGE": 68, "HOME_VALUE": 800_000, "MORTGAGE_BALANCE": 0, "MORTGAGE_MONTHLY": 0,
                "SPEND_FOOD_MONTHLY": 500}
    series, _ = sc.build_category_series(ages, paid_off, {}, 68)
    assert series[0][0] == "Housing (property tax, insurance)"
    loan = {**paid_off, "MORTGAGE_BALANCE": 200_000, "MORTGAGE_MONTHLY": 2_000, "MORTGAGE_YEARS_REMAINING": 10}
    series, _ = sc.build_category_series(ages, loan, {}, 68)
    assert series[0][0] == "Housing (mortgage)"


def test_retired_extra_is_not_called_early():
    ov = {"YOUR_AGE": 68, "PARTNER_AGE": 0, "SPEND_FOOD_MONTHLY": 500}
    series, _ = sc.build_category_series(list(range(68, 80)), ov, {}, 68)
    assert "Travel and hobbies extra" in _by_label(series)
    ov = {"YOUR_AGE": 50, "PARTNER_AGE": 0, "SPEND_FOOD_MONTHLY": 500}
    series, _ = sc.build_category_series(list(range(50, 80)), ov, {}, 60)
    assert "Early-retirement extra" in _by_label(series)


def _fig(four_pct):
    ages = list(range(50, 60))
    ov = {"YOUR_AGE": 50, "PARTNER_AGE": 0, "SPEND_FOOD_MONTHLY": 5_000, "SPEND_RENT_MONTHLY": 3_000}
    return sc._build_figure(ages, ov, {}, 50, 55, 59, "Flat (no change)",
                            four_pct_series=four_pct, title="t", subtitle="s", yaxis_title="y")


def test_a_huge_4pct_line_does_not_stretch_the_axis():
    fig = _fig([400_000.0] * 10)
    top = max(sum(t.y[i] for t in fig.data if t.type == "bar") for i in range(10))
    assert fig.layout.yaxis.range[1] == pytest.approx(1.6 * top)
    assert any("4% rule line runs off the top" in a.text for a in fig.layout.annotations)


def test_a_4pct_line_near_the_bars_keeps_the_auto_axis():
    fig = _fig([90_000.0] * 10)
    assert fig.layout.yaxis.range is None


# ---- failing plans --------------------------------------------------------

def test_percentile_charts_run_to_the_plan_end_even_when_all_runs_fail_early():
    ages = sr._horizon_ages([25, 26])
    assert ages[0] == 25 and ages[-1] >= 90
    med, p10, p90 = sr._percentile_trajectories([[(25, 500.0)], [(25, 800.0)]])
    assert med[0][0] == 25 and med[-1][0] == ages[-1] and med[-1][1] == 0.0
    assert len(sr._networth_percentiles([[(25, 500.0)]])) == len(ages)


# ---- account caps ---------------------------------------------------------

def test_account_balances_take_more_than_10m():
    src = open(os.path.join(_UI, "components", "account_inputs.py"), encoding="utf-8").read()
    assert "max_value=100_000_000" in src and "10_000_000" not in src
    assert "10_000_000" not in open(os.path.join(_UI, "utils", "widget_sync.py"), encoding="utf-8").read()
