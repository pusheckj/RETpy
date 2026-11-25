"""Test the net-worth box-plot percentile pipeline (sim_runner._networth_percentiles)."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import sim_runner as sr
from utils.plot_theme import beeswarm_xy


def test_networth_percentiles_monotone_full_axis_and_depletion():
    paths = [
        [(40, 100.0), (41, 110.0), (42, 120.0)],
        [(40, 100.0), (41, 90.0)],            # depletes after 41 -> age 42 counts as $0
        [(40, 100.0), (41, 200.0), (42, 300.0)],
        [(40, 100.0), (41, 150.0), (42, 90.0)],
    ]
    out = sr._networth_percentiles(paths)
    # Full, contiguous age axis (union), sorted, running on to the plan's last
    # year (every path is $0 after its data ends).
    ages = [r["age"] for r in out]
    assert ages[:3] == [40, 41, 42] and ages == list(range(40, ages[-1] + 1)) and ages[-1] >= 90
    assert out[-1]["p90"] == 0.0
    # Percentiles are monotone within each age.
    for r in out:
        assert r["p10"] <= r["p25"] <= r["p50"] <= r["p75"] <= r["p90"]
    # Age 40: all paths identical -> zero spread. Age 42: spread exists, and the
    # depleted path drags the low end down (below the min surviving balance 90).
    assert out[0]["p90"] - out[0]["p10"] == 0.0
    assert out[2]["p90"] - out[2]["p10"] > 0.0
    assert out[2]["p10"] < 90.0
    assert sr._networth_percentiles([]) == []


def test_networth_rows_carry_samples():
    paths = [[(40, float(100 + i))] for i in range(200)]  # >80 -> sampled/capped
    out = sr._networth_percentiles(paths)
    assert "samples" in out[0]
    assert 1 <= len(out[0]["samples"]) <= 80  # capped for the point-cloud view


def test_beeswarm_packs_symmetrically_within_half_width():
    # A dense cluster + a sparse one -> fullest bin spans ~2*half_width (violin),
    # points stay within +/- half_width of the center, sparse bin is narrower.
    xs, ys = beeswarm_xy([10.0] * 40 + [20.0] * 4, x_center=50.0, half_width=0.42)
    assert len(xs) == 44
    assert max(abs(x - 50.0) for x in xs) <= 0.42 + 1e-9
    dense_spread = max(x for x, y in zip(xs, ys) if y == 10.0) - min(x for x, y in zip(xs, ys) if y == 10.0)
    sparse_spread = max(x for x, y in zip(xs, ys) if y == 20.0) - min(x for x, y in zip(xs, ys) if y == 20.0)
    assert dense_spread > sparse_spread  # density -> width (the violin shape)
    assert beeswarm_xy([], 1.0) == ([], [])
    assert beeswarm_xy([5.0, 5.0, 5.0], 3.0)[0] == [3.0, 3.0, 3.0]  # identical -> single column


# ------------------------------------------------------------ Range + milestones view

from components import net_worth_box_chart as nwb
from components.profile_picker import PROFILES


def _couple(**extra):
    return dict(PROFILES["Mid-career couple (40, kids)"], TARGET_RETIREMENT_AGE=48, **extra)


def _labels(ov, plan_until=97):
    return [m["label"] for m in nwb.milestones(ov, int(ov["YOUR_AGE"]), plan_until)]


def test_milestones_from_the_couples_inputs():
    ms = nwb.milestones(_couple(), 40, 97)
    labels = [m["label"] for m in ms]
    assert labels == ["Both retire", "Mortgage paid off", "Kids in college", "59½: penalty-free",
                      "Your Social Security", "Partner's Social Security", "RMDs start", "Plan ends"]
    ages = [m["age"] for m in ms]
    assert ages == sorted(ages) and all(40 < a <= 97 for a in ages)
    college = next(m for m in ms if m["label"] == "Kids in college")
    assert college["end"] > college["age"]          # a shaded span
    assert all(m["detail"] and m["short"] for m in ms)


def test_partner_retiring_on_their_own_and_claiming_with_you():
    ov = _couple(PARTNER_RETIREMENT_AGE=50, PARTNER_SS_CLAIM_AGE=65)   # partner is 2 years younger
    labels = _labels(ov)
    assert "You retire" in labels and "Partner retires" in labels and "Both retire" not in labels
    assert "Social Security (both)" in labels


def test_single_no_social_security_and_debts():
    ov = dict(PROFILES["Young professional (28, single)"], TARGET_RETIREMENT_AGE=50,
              INCLUDE_SOCIAL_SECURITY=False,
              DEBTS=[{"name": "Card", "kind": "credit_card", "balance": 6_000, "apr": 0.2,
                      "min_payment": 300}])
    labels = _labels(ov, 90)
    assert "You retire" in labels and not any("Social Security" in l or "Partner" in l
                                              for l in labels)
    debt = next(m for m in nwb.milestones(ov, 28, 90) if m["label"] == "Debts paid off")
    assert 28 < debt["age"] < 32


def _intervals(items, layout, lo, hi, px, key):
    span = hi - lo
    out = []
    for m, (row, anchor) in zip(items, layout):
        w = (len(m[key]) * nwb._CHAR_PX + 12) / px * span
        out.append((row, (m["age"], m["age"] + w) if anchor == "left" else (m["age"] - w, m["age"])))
    return out


def test_labels_stagger_into_rows_without_overlap():
    for compact in (False, True):
        key = "short" if compact else "label"
        items = nwb.milestones(_couple(PARTNER_RETIREMENT_AGE=47), 40, 97)
        layout = nwb.stagger(items, 39, 98, nwb._PLOT_PX[compact], key)
        iv = _intervals(items, layout, 39, 98, nwb._PLOT_PX[compact], key)
        for i, (r1, a) in enumerate(iv):
            assert a[1] <= 98 + 1e-9 or layout[i][1] == "left"
            for r2, b in iv[i + 1:]:
                if r1 == r2:
                    assert a[1] < b[0] or b[1] < a[0]
        assert layout[-1][1] == "right"                  # "Plan ends" sits left of its line
    many = [{"age": 50.0, "label": "A long milestone label", "short": "A"} for _ in range(3)]
    assert [r for r, _ in nwb.stagger(many, 40, 98, 700)] == [0, 1, 2]


def test_milestone_figure_uses_one_label_size_and_the_apps_title_sizes():
    ages = list(range(40, 98))
    p50 = [1e6 + 5e4 * i for i in range(len(ages))]
    p = {k: [v * f for v in p50] for k, f in (("p10", .4), ("p25", .7), ("p75", 1.4), ("p90", 2.0))}
    items = nwb.milestones(_couple(), 40, 97)
    for compact in (False, True):
        fig = nwb._milestone_figure(ages, p["p10"], p["p25"], p50, p["p75"], p["p90"], items,
                                    dark=False, compact=compact, mode_label="today's dollars",
                                    unit="$, today")
        anns = fig.layout.annotations
        assert len(anns) == len(items)
        assert {a.font.size for a in anns} == {nwb.LABEL_SIZE}
        assert all(a.hovertext and a.yref == "paper" for a in anns)
        assert fig.layout.title.font.size == 16 and "font-size:13px" in fig.layout.title.text
        assert fig.layout.yaxis.range[1] > nwb.axis_top(p["p75"], p["p90"])[0]
        assert [t.name for t in fig.data][:3] == ["Middle 80% of paths", "Middle 50% of paths",
                                                  "Median"]


def test_axis_stops_when_a_few_lucky_paths_run_away():
    assert nwb.axis_top([1, 2, 4], [2, 4, 6]) == (6, False)
    top, clipped = nwb.axis_top([1, 2, 10], [2, 4, 60])
    assert clipped and top == 16


class _Cols:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _MockSt:
    def __init__(self, overrides, style):
        self.session_state = {"user_overrides": overrides, "theme_mode": "Light"}
        self._style = style
        self.charts = []
        self.captions = []

    def columns(self, n):
        return [_Cols() for _ in range(n)]

    def radio(self, label, options, **k):
        return self._style if label == "Style" else options[0]

    def plotly_chart(self, fig, **k):
        self.charts.append(fig)

    def caption(self, text, **k):
        self.captions.append(text)

    def dataframe(self, df, **k):
        pass


def test_render_range_and_milestones_in_both_dollar_modes():
    rows = [{"age": a, "p10": 1e5 * i, "p25": 2e5 * i, "p50": 3e5 * i, "p75": 4e5 * i,
             "p90": 5e5 * i} for i, a in enumerate(range(40, 98), 1)]
    st = _MockSt(_couple(), "Range + milestones")
    nwb.render(st, results={"primary_result": {"networth_by_year": rows}})
    assert len(st.charts) == 1 and "middle 50%" in st.captions[0]
    fig = st.charts[0]
    assert any(a.text == "Both retire" for a in fig.layout.annotations)
    st_box = _MockSt(_couple(), "Box plot")
    nwb.render(st_box, results={"primary_result": {"networth_by_year": rows}})
    assert st_box.charts[0].data[0].type == "box"           # the default view is unchanged


def test_range_and_milestones_is_the_default_view():
    import inspect
    from components import net_worth_box_chart as nwb
    src = inspect.getsource(nwb)
    assert 'index=STYLES.index("Range + milestones")' in src
