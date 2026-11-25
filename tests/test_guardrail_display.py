"""The spending-guardrail display: honest cushion wording (both rules), the
"chance you ever trim spending" stat (engine log -> sim_task -> primary_result ->
hero), and the trim line + table on the portfolio-over-time chart."""
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components import hero_metric, net_worth_box_chart as nwb  # noqa: E402
from components.profile_picker import PROFILES  # noqa: E402
from retirement_sim import account_simulation as sim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import mc_jobs, mc_parallel  # noqa: E402
from utils import goal_levers as gl  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402

COUPLE = PROFILES["Mid-career couple (40, kids)"]
SNAP = {"TARGET_SUCCESS_RATE": 0.80, "YOUR_AGE": 40, "PARTNER_AGE": 38,
        "PLAN_UNTIL_AGE": 95, "PARTNER_PLAN_UNTIL_AGE": 95}
SINGLE = {"YOUR_AGE": 30, "PARTNER_AGE": 0, "FILING_STATUS": "Single", "YOUR_BASE_SALARY": 130_000,
          "YOUR_401K": 40_000, "YOUR_CASH": 20_000, "TARGET_RETIREMENT_AGE": 55,
          "SPEND_RENT_MONTHLY": 500}
# Every year is a "poor" year (return below 1000%), the portfolio rule is off:
# each retirement year trims exactly 10% of the fun-money slice.
ALWAYS_TRIM = {"DYNAMIC_SPENDING_ENABLED": False, "RETURN_BASED_SPENDING_ENABLED": True,
               "RETURN_BASED_SPENDING_RULES": {
                   "excellent_return_threshold": 99.0, "excellent_spending_boost": 0.0,
                   "good_return_threshold": 99.0, "good_spending_boost": 0.0,
                   "poor_return_threshold": 10.0, "poor_spending_cut": 0.10,
                   "bad_return_threshold": -10.0, "bad_spending_cut": 0.20}}
NEVER_TRIM = {"DYNAMIC_SPENDING_ENABLED": False, "RETURN_BASED_SPENDING_ENABLED": False}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(sr, "_disk", lambda: None)
    sr.clear_cache(include_disk=False)
    yield
    sr.clear_cache(include_disk=False)


class _FakeSt:
    def __init__(self, overrides=None):
        self.session_state = {"user_overrides": overrides or {}}
        self.calls = []

    def markdown(self, text, **kwargs):
        self.calls.append(text)


def _plan(**extra):
    return dict(COUPLE, TARGET_RETIREMENT_AGE=48, PARTNER_RETIREMENT_AGE=46, **extra)


def _hero(snap=None, overrides=None, rate=0.737, stats=None, p50=3_000_000.0):
    primary = {"retirement_age": 48, "success_rate": rate, "n_simulations": 1000,
               "networth_by_year": [{"age": 48, "p50": p50}]}
    if stats is not None:
        primary["spending_cut_stats"] = stats
    st = _FakeSt(_plan() if overrides is None else overrides)
    hero_metric.render(st, {"earliest_retirement_age": 50, "primary_result": primary,
                            "config_snapshot": {**SNAP, **(snap or {})}})
    return "\n".join(st.calls)


def _cushion_text(html):
    box = html[html.index('class="mc-cushion"'):]
    return re.sub(r"<[^>]+>", "", box.split("</div>")[0]).replace("&#36;", "$")


def _long_sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) > 20]


# ---------------------------------------------------------------- 1. honest wording

def test_cushion_names_both_rules_when_the_return_rule_is_on():
    text = _cushion_text(_hero())
    assert "The portfolio rule trims fun money by about" in text
    assert "$900,000 (30%) below that" in text
    assert "A year with a loss also trims fun money 10% that year, or 20% with a loss over 10%." in text
    assert "before your spending rule trims" not in text        # the old, one-rule claim
    assert not _long_sentences(text)


def test_return_rule_numbers_come_from_the_config():
    rules = {**cfg.RETURN_BASED_SPENDING_RULES, "poor_spending_cut": 0.05,
             "bad_return_threshold": -0.15, "bad_spending_cut": 0.25}
    text = _cushion_text(_hero(overrides=_plan(RETURN_BASED_SPENDING_RULES=rules)))
    assert "trims fun money 5% that year, or 25% with a loss over 15%." in text


def test_no_loss_sentence_when_the_return_rule_is_off():
    html = _hero(snap={"RETURN_BASED_SPENDING_ENABLED": False},
                 overrides=_plan(RETURN_BASED_SPENDING_ENABLED=False))
    text = _cushion_text(html)
    assert "Your spending rule trims fun money by about" in text and "$900,000 (30%)" in text
    assert "loss" not in text and "portfolio rule" not in text


def test_return_rule_alone_is_not_called_no_adjustment():
    html = _hero(snap={"DYNAMIC_SPENDING_ENABLED": False})
    text = _cushion_text(html)
    assert "Spending never adjusts" not in html
    assert "A year with a loss trims fun money 10% that year, or 20% with a loss over 10%." in text
    assert "$900,000" not in text                              # no portfolio rule to fall below


def test_spending_never_adjusts_only_when_both_rules_are_off():
    html = _hero(snap={"DYNAMIC_SPENDING_ENABLED": False, "RETURN_BASED_SPENDING_ENABLED": False})
    assert "Spending never adjusts." in html and "Your cushion" not in html


def test_cushion_exposes_the_rule_values_for_the_chart():
    c = gl.guardrail_cushion(_plan(), 48)
    assert c["floor_trigger"] == pytest.approx(0.70) and c["cut"] == pytest.approx(0.15)
    assert c["return_rule"] == {"enabled": True, "poor_threshold": 0.0, "poor_cut": 0.10,
                                "bad_threshold": -0.10, "bad_cut": 0.20}
    off = gl.guardrail_cushion(_plan(RETURN_BASED_SPENDING_ENABLED=False), 48)
    assert off["return_rule"]["enabled"] is False


def test_rule_text_quotes_the_engine_rule():
    text = gl.rule_text(gl.guardrail_cushion(_plan(), 48))
    for part in ("compares your portfolio with what you had when you retired",
                 "in today's dollars", "Below 70% of that", "fun money stays at plan", "30% of spending other than housing",
                 "trimmed 15%", "Housing is never cut", "130%", "10% that year", "20%",
                 "never goes below 60%", "140%", "as soon as"):
        assert part in text, part
    assert not _long_sentences(text)
    assert "widow" not in text.lower()


# ---------------------------------------------------------------- 2. the cut stat

def test_spending_log_records_each_years_cut():
    o = sr._apply_overrides(build_config_overrides({**SINGLE, **ALWAYS_TRIM}))
    try:
        ok, p = sim.run_detailed_simulation(55, verbose=False, random_seed=11)
    finally:
        sr._restore_overrides(o)
    retired = [r for r in p.spending_log if r["age"] >= 55]
    assert retired and all(r["cut"] > 0 for r in retired)
    assert all(r["cut"] / (r["living"] + r["cut"]) <= 0.10 * cfg.DISCRETIONARY_EXPENSE_RATIO + 1e-9
               for r in retired)                              # 10% of the fun-money slice, never more
    assert all("cut" not in r for r in p.spending_log if r["age"] < 55)


def test_no_cut_is_recorded_when_both_rules_are_off():
    o = sr._apply_overrides(build_config_overrides({**SINGLE, **NEVER_TRIM}))
    try:
        ok, p = sim.run_detailed_simulation(55, verbose=False, random_seed=11)
    finally:
        sr._restore_overrides(o)
    assert all(r.get("cut", 0.0) == 0.0 for r in p.spending_log)


def test_sim_task_reports_each_runs_cut_years_in_run_order():
    o = sr._apply_overrides(build_config_overrides({**SINGLE, **ALWAYS_TRIM}))
    try:
        out = mc_parallel.sim_task((55, 6, 0, 500))
    finally:
        sr._restore_overrides(o)
    assert len(out["cuts_by_run"]) == out["n"] == 6
    assert all(run and all(c > 0 for c in run) for run in out["cuts_by_run"])
    o = sr._apply_overrides(build_config_overrides({**SINGLE, **NEVER_TRIM}))
    try:
        quiet = mc_parallel.sim_task((55, 6, 0, 500))
    finally:
        sr._restore_overrides(o)
    assert quiet["cuts_by_run"] == [[]] * 6


def test_cut_stats_share_typical_size_and_years():
    runs = [[], [12_000.0, 12_000.0], [6_000.0], []]
    s = sr.spending_cut_stats(runs)
    assert s == {"share": 0.5, "median_monthly": 1_000.0, "median_years": 1.5, "n": 4}
    assert sr.spending_cut_stats([[], []]) == {"share": 0.0, "median_monthly": 0.0,
                                               "median_years": 0.0, "n": 2}
    assert sr.spending_cut_stats([]) is None


def test_primary_result_carries_the_stat_and_the_browser_job_matches_the_server():
    plan = sr.plan_full_analysis({**SINGLE, **ALWAYS_TRIM}, 40, 55, (55, 56, 1))
    first = plan.local[0]
    server = sr.run_plan_calls(plan, [first])[0]
    with mc_jobs.config_state(mc_jobs.snapshot()):            # what the browser's worker does
        mc_jobs.browser_load("g", mc_jobs.dumps(plan.job))
        browser = mc_jobs.loads(mc_jobs.browser_run("g", first))
    assert browser["cuts_by_run"] == server["cuts_by_run"] != []
    stats = sr.execute_plan(sr.plan_full_analysis({**SINGLE, **ALWAYS_TRIM}, 40, 55, (55, 56, 1))
                            )["primary_result"]["spending_cut_stats"]
    assert stats["n"] == 40 and stats["share"] == 1.0
    assert stats["median_monthly"] > 0 and stats["median_years"] >= 1


def test_stat_does_not_depend_on_how_the_run_is_split(monkeypatch):
    got = {}
    for chunks in (2, 5):
        monkeypatch.setattr(sr, "_PRIMARY_CHUNKS", chunks)
        sr.clear_cache(include_disk=False)
        plan = sr.plan_full_analysis({**SINGLE, **ALWAYS_TRIM}, 30, 55, (55, 56, 1))
        got[chunks] = sr.execute_plan(plan)["primary_result"]["spending_cut_stats"]
    assert got[2] == got[5]


# ---------------------------------------------------------------- hero line

STATS = {"share": 0.38, "median_monthly": 450.0, "median_years": 3.0, "n": 1000}


def test_hero_shows_the_chance_you_ever_trim_as_a_small_secondary_line():
    html = _hero(stats=STATS)
    assert 'class="mc-cushion-sub"' in html
    line = re.sub(r"<[^>]+>", "", html[html.index('class="mc-cushion-sub"'):].split("</div>")[0])
    line = line.replace("&#36;", "$")
    assert "Chance you ever trim spending: 38%." in line
    assert "typical trim is about $450 a month for about 3 years" in line
    assert not _long_sentences(line)
    assert html.count("mc-hero-big") == 1                       # one hero: the retirement age


def test_hero_line_wording_for_small_and_zero_chances_and_one_year():
    assert "Chance you ever trim spending: under 1%." in _cushion_text(
        _hero(stats={**STATS, "share": 0.004, "median_years": 1.0}))
    assert "for about 1 year" in _cushion_text(_hero(stats={**STATS, "median_years": 1.0}))
    zero = _cushion_text(_hero(stats={**STATS, "share": 0.0, "median_monthly": 0.0,
                                       "median_years": 0.0}))
    assert "Chance you ever trim spending: 0%." in zero and "typical trim" not in zero


def test_no_stat_line_without_the_stat_or_when_spending_never_adjusts():
    assert "mc-cushion-sub" not in _hero()
    off = {"DYNAMIC_SPENDING_ENABLED": False, "RETURN_BASED_SPENDING_ENABLED": False}
    assert "mc-cushion-sub" not in _hero(snap=off, stats=STATS)


def test_a_perfect_success_rate_is_never_a_promise():
    html = _hero(rate=1.0)
    assert "guarantee" not in html.lower()
    assert "not a promise" in html.lower()
    assert "not a promise" not in _hero(rate=0.93).lower()


# ---------------------------------------------------------------- 3. trim line + table

class _Cols:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _MockSt:
    def __init__(self, overrides, dollars="Today's $", style="Range + milestones"):
        self.session_state = {"user_overrides": overrides, "theme_mode": "Light"}
        self._dollars, self._style = dollars, style
        self.charts, self.captions, self.tables = [], [], []

    def columns(self, n):
        return [_Cols() for _ in range(n)]

    def radio(self, label, options, **k):
        return self._style if label == "Style" else self._dollars

    def plotly_chart(self, fig, **k):
        self.charts.append(fig)

    def caption(self, text, **k):
        self.captions.append(text)

    def dataframe(self, df, **k):
        self.tables.append(df)


def _rows():
    return [{"age": a, "p10": 1e5 * i, "p25": 2e5 * i, "p50": 3e5 * i, "p75": 4e5 * i,
             "p90": 5e5 * i} for i, a in enumerate(range(40, 98), 1)]


def _draw(ov, **kw):
    st = _MockSt(ov, **kw)
    nwb.render(st, results={"primary_result": {"networth_by_year": _rows(), "retirement_age": 48}})
    return st


def _trim_trace(fig):
    return next((t for t in fig.data if t.name == "Spending trim line"), None)


def test_trim_line_is_70_percent_of_the_median_at_retirement_in_retirement_years_only():
    st = _draw(_plan())
    t = _trim_trace(st.charts[0])
    median_48 = next(r["p50"] for r in _rows() if r["age"] == 48)
    assert min(t.x) == 48 and max(t.x) == 97
    assert all(y == pytest.approx(0.70 * median_48) for y in t.y)    # flat in today's dollars
    assert t.line.dash == "dash" and t.line.color.lower() in ("#dc2626", "#f87171")
    label = [a.text for a in st.charts[0].layout.annotations if "Spending trim line" in a.text]
    assert label == [f"Spending trim line ≈ {nwb.money(0.70 * median_48, shorten=True)}"]


def test_trim_line_in_future_dollars_scales_by_the_charts_inflation_factor():
    ov = _plan(EXPECTED_INFLATION=0.03)
    today = _trim_trace(_draw(ov).charts[0])
    future = _trim_trace(_draw(ov, dollars="Future $").charts[0])
    for age, y0, y1 in zip(today.x, today.y, future.y):
        assert y1 == pytest.approx(y0 * 1.03 ** (age - 40))


def test_trim_line_label_matches_the_line_at_retirement():
    ov = _plan(EXPECTED_INFLATION=0.03)
    st = _draw(ov, dollars="Future $")
    t = _trim_trace(st.charts[0])
    label = next(a.text for a in st.charts[0].layout.annotations if "Spending trim line" in a.text)
    assert label == f"Spending trim line ≈ {nwb.money(t.y[0], shorten=True)}"


def test_table_gives_value_at_the_line_distance_and_the_change_it_triggers():
    st = _draw(_plan())
    df = st.tables[0]
    assert list(df.columns) == ["Guardrail", "Portfolio value at the line",
                                "$ distance from the median at retirement", "% distance",
                                "Spending change triggered"]
    median_48 = next(r["p50"] for r in _rows() if r["age"] == 48)
    row = df.iloc[0]
    assert "70%" in row["Guardrail"]
    assert row["Portfolio value at the line"] == nwb.money(0.70 * median_48)
    assert row["$ distance from the median at retirement"] == nwb.money(-0.30 * median_48)
    assert row["% distance"] == "-30%"
    assert row["Spending change triggered"] == (
        f"Fun money trimmed 15%, about {gl.monthly_text(gl.guardrail_cushion(_plan(), 48)['trim_year'])} a month")
    loss = df.iloc[1]
    assert "loss" in loss["Guardrail"] and "10%" in loss["Spending change triggered"]
    assert any("Housing is never cut" in c for c in st.captions)


def test_table_and_line_follow_a_custom_rule():
    rule = {**cfg.SPENDING_GUARDRAILS, "floor_trigger": 0.80, "floor_reduction": 0.10}
    st = _draw(_plan(SPENDING_GUARDRAILS=rule))
    median_48 = next(r["p50"] for r in _rows() if r["age"] == 48)
    assert _trim_trace(st.charts[0]).y[0] == pytest.approx(0.80 * median_48)
    assert st.tables[0].iloc[0]["% distance"] == "-20%"


def test_no_portfolio_line_when_that_rule_is_off_and_no_table_row_for_it():
    st = _draw(_plan(DYNAMIC_SPENDING_ENABLED=False))
    assert _trim_trace(st.charts[0]) is None
    assert len(st.tables[0]) == 1 and "loss" in st.tables[0].iloc[0]["Guardrail"]
    st = _draw(_plan(DYNAMIC_SPENDING_ENABLED=False, RETURN_BASED_SPENDING_ENABLED=False))
    assert _trim_trace(st.charts[0]) is None and not st.tables


def test_the_other_views_keep_their_charts_without_the_line():
    st = _draw(_plan(), style="Box plot")
    assert _trim_trace(st.charts[0]) is None and not st.tables
