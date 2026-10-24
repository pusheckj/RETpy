"""Tests for the always-on 'Income over time' chart (components.income_over_time).

The chart reads directly from ``user_overrides`` for the working years
(deterministic gross salary by source) and enriches retirement years from Monte
Carlo results when available. These tests assert:
  (a) working-years source traces exist and sum to gross household income in a
      sample year,
  (b) the future-dollars mode yields strictly larger values than today's-dollars
      in a later year (inflation applied),
  (c) render() does not raise with results=None or with a results dict.

The chart module lives under ``ui/``; add both ROOT and ROOT/ui to sys.path so
its internal ``from components...`` / ``from utils...`` imports resolve.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components import income_over_time as iot


# ---------------------------------------------------------------------------
# Shared overrides: a two-earner household with bonus + RSU + other income, so
# every working-source trace is exercised.
#
# In the real app, editing the flat income fields ALSO writes
# ``YOUR_COMPENSATION_BY_AGE`` (see components.sec_income.render_body), so the
# comp table is the primary source. We include one here derived from the flat
# inputs so the chart's comp-table path is exercised the way the UI drives it.
# ---------------------------------------------------------------------------
def _comp_table(base, bonus, rsu, start_age, end_age, growth) -> dict:
    table = {}
    for offset in range(end_age - start_age + 1):
        age = start_age + offset
        scale = (1 + growth) ** offset
        table[age] = {
            "base": int(round(base * scale)),
            "bonus": int(round(bonus * scale)),
            "rsu_gross": int(round(rsu * scale)),
        }
    return table


def _overrides() -> dict:
    return {
        "YOUR_AGE": 30,
        "TARGET_RETIREMENT_AGE": 55,
        "PLAN_UNTIL_AGE": 90,
        "PARTNER_AGE": 30,
        "EXPECTED_INFLATION": 0.0275,
        # Flat income inputs (kept for the comp-table-absent fallback test).
        "YOUR_BASE_SALARY": 120_000,
        "YOUR_BONUS_AMOUNT": 20_000,
        "YOUR_RSU_AMOUNT": 40_000,
        "YOUR_OTHER_INCOME": 5_000,
        "YOUR_SALARY_GROWTH_RATE": 0.03,
        # Comp table the UI would have written from the flat inputs above.
        "YOUR_COMPENSATION_BY_AGE": _comp_table(120_000, 20_000, 40_000, 30, 55, 0.03),
        "PARTNER_BASE_SALARY": 90_000,
        "PARTNER_BONUS_AMOUNT": 10_000,
        "PARTNER_RSU_AMOUNT": 15_000,
        "PARTNER_OTHER_INCOME": 2_000,
        "PARTNER_SALARY_GROWTH_RATE": 0.02,
    }


def _sample_results() -> dict:
    """Minimal results dict with a couple of retirement income-source rows."""
    return {
        "primary_result": {
            "income_sources_by_year": [
                {"age": 55, "ss": 0, "traditional": 40_000, "roth": 10_000,
                 "taxable": 20_000, "hsa": 0},
                {"age": 67, "ss": 45_000, "traditional": 30_000, "roth": 5_000,
                 "taxable": 10_000, "hsa": 2_000},
            ],
        },
    }


# ===========================================================================
# (a) Working-years traces exist and sum to gross income in a sample year.
# ===========================================================================
def test_working_year_sources_sum_to_gross_income():
    ov = _overrides()
    ages, series = iot.build_income_series(
        ov, None, current_age=30, retirement_age=55, plan_until=90,
        future_dollars=False, inflation_rate=0.0275,
    )
    assert ages[0] == 30 and ages[-1] == 90

    # Every working source is present (all non-zero in this scenario).
    for label in iot._WORKING_LABELS:
        assert label in series, f"missing working source: {label}"

    # In the FIRST working year (age 30, no growth applied yet), the stacked
    # sources must sum to the household gross income entered.
    i0 = ages.index(30)
    stacked = sum(series[label][i0] for label in iot._WORKING_LABELS)
    you = 120_000 + 20_000 + 40_000 + 5_000
    partner = 90_000 + 10_000 + 15_000 + 2_000
    assert abs(stacked - (you + partner)) < 1e-6

    # A later working year (age 40) must be larger due to salary growth.
    i10 = ages.index(40)
    later_stacked = sum(series[label][i10] for label in iot._WORKING_LABELS)
    assert later_stacked > stacked


def test_comp_table_int_and_str_keys_both_work():
    """Comp table keyed by int OR str must both resolve for the same year."""
    row = {"base": 100_000, "bonus": 5_000, "rsu_gross": 25_000}
    int_keyed = {32: row}
    str_keyed = {"32": row}
    b1, bo1, r1, _ = iot._your_income_for_age({"YOUR_OTHER_INCOME": 0}, int_keyed, 32, 0.03)
    b2, bo2, r2, _ = iot._your_income_for_age({"YOUR_OTHER_INCOME": 0}, str_keyed, 32, 0.03)
    assert (b1, bo1, r1) == (100_000, 5_000, 25_000)
    assert (b2, bo2, r2) == (100_000, 5_000, 25_000)


def test_flat_input_fallback_when_no_comp_table():
    """With the comp table explicitly absent, the flat YOUR_* inputs drive the
    primary user's income (grown from current age)."""
    ov = _overrides()
    ov["YOUR_COMPENSATION_BY_AGE"] = {}  # force flat-input fallback
    ages, series = iot.build_income_series(
        ov, None, 30, 55, 90, future_dollars=False)
    i0 = ages.index(30)
    assert series["Your base salary"][i0] == 120_000
    assert series["Your bonus"][i0] == 20_000
    assert series["Your RSU"][i0] == 40_000
    # Grows with YOUR_SALARY_GROWTH_RATE (3%) one year later.
    i1 = ages.index(31)
    assert abs(series["Your base salary"][i1] - 120_000 * 1.03) < 1e-6


# ===========================================================================
# (b) Future-dollars mode > today's-dollars in a later year.
# ===========================================================================
def test_future_dollars_larger_than_today_in_later_year():
    ov = _overrides()
    _, real = iot.build_income_series(
        ov, None, 30, 55, 90, future_dollars=False, inflation_rate=0.0275)
    ages, nominal = iot.build_income_series(
        ov, None, 30, 55, 90, future_dollars=True, inflation_rate=0.0275)

    i_later = ages.index(50)  # 20 years out — inflation factor clearly > 1
    real_total = sum(real[label][i_later] for label in real)
    nominal_total = sum(nominal[label][i_later] for label in nominal)
    assert nominal_total > real_total

    # And in the very first year the two are equal (factor == 1).
    i0 = ages.index(30)
    assert abs(sum(real[l][i0] for l in real) - sum(nominal[l][i0] for l in nominal)) < 1e-6


# ===========================================================================
# Retirement enrichment from results.
# ===========================================================================
def test_retirement_sources_from_results():
    ov = _overrides()
    ages, series = iot.build_income_series(
        ov, _sample_results(), 30, 55, 90, future_dollars=False)
    # Retirement sources present because results supplied them.
    assert "Traditional 401(k)/IRA" in series
    i55 = ages.index(55)
    assert series["Traditional 401(k)/IRA"][i55] == 40_000
    assert series["Roth"][i55] == 10_000
    i67 = ages.index(67)
    assert series["Social Security"][i67] == 45_000


# ===========================================================================
# (c) render() works with results=None and with a results dict.
# ===========================================================================
class _MockSt:
    """Tolerant mock for `st` — mirrors ui/_smoke_test.py's MockSt, but returns
    a controllable value from radio() so the dollars-mode toggle resolves."""

    def __init__(self, overrides, radio_value="Today's dollars"):
        self.session_state = {"user_overrides": overrides, "theme_mode": "Light"}
        self._radio_value = radio_value
        self.plotly_calls = 0

    def radio(self, *a, **k):
        return self._radio_value

    def plotly_chart(self, *a, **k):
        self.plotly_calls += 1

    def info(self, *a, **k):
        pass

    def caption(self, *a, **k):
        pass


def test_render_without_results_does_not_raise():
    st = _MockSt(_overrides())
    iot.render(st, results=None, chart_key="iot_test_none")
    assert st.plotly_calls == 1  # rendered the chart


def test_render_with_results_does_not_raise():
    st = _MockSt(_overrides(), radio_value="Future (nominal) dollars")
    iot.render(st, results=_sample_results(), chart_key="iot_test_results")
    assert st.plotly_calls == 1


def test_render_no_ages_shows_info():
    """current_age > plan_until => friendly info, no chart."""
    ov = _overrides()
    ov["YOUR_AGE"] = 95
    ov["PLAN_UNTIL_AGE"] = 90
    # No partner: a younger partner extends the plan to their own plan-until age.
    ov["PARTNER_AGE"] = 0
    st = _MockSt(ov)
    iot.render(st, results=None, chart_key="iot_test_noages")
    assert st.plotly_calls == 0


def test_all_income_types_grow_at_the_rate():
    """Every income type (base, bonus, RSU, AND other income) grows at the
    salary growth rate — not just base/bonus/RSU. Pins the fix that previously
    left 'other income' flat while the rest compounded."""
    ov = {"YOUR_AGE": 32, "YOUR_OTHER_INCOME": 10_000, "PARTNER_OTHER_INCOME": 5_000}
    g = 0.08
    # You: no comp table -> flat inputs grown from current age.
    _b0, _bo0, _r0, o0 = iot._your_income_for_age(ov, {}, 32, g)
    _b8, _bo8, _r8, o8 = iot._your_income_for_age(ov, {}, 40, g)
    assert abs(o0 - 10_000) < 1e-6
    assert abs(o8 - 10_000 * (1 + g) ** 8) < 1.0  # ~18,509, grew with the rate
    # Partner other income grows too.
    p0 = iot._partner_income_for_age(ov, 32, 32, g)
    p8 = iot._partner_income_for_age(ov, 40, 32, g)
    assert abs(p8[3] - 5_000 * (1 + g) ** 8) < 1.0
