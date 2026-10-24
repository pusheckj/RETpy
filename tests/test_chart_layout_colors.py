"""Shared chart layout + color-map invariants (finding #11/#12/#17/#18)."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import plotly.graph_objects as go
from utils import plot_theme as pt


class _St:
    session_state = {}


def test_same_concept_same_color_across_charts():
    st = _St()
    # Home equity and brokerage are one color regardless of chart/owner wording.
    assert pt.concept_color("Home equity", st) == pt.concept_color("Home equity", st)
    assert pt.concept_color("Taxable brokerage", st) == pt.concept_color("Taxable brokerage", st)
    assert pt.concept_of("Your taxable brokerage") == pt.concept_of("Taxable brokerage") == "Taxable brokerage"
    assert pt.concept_of("Traditional 401(k)/IRA") == "401(k)"
    # Partner variant is the same hue, lightened (not identical).
    assert pt.concept_color("Partner 401(k)", st) != pt.concept_color("Your 401(k)", st)


def test_income_series_salary_and_hsa_are_distinct():
    st = _St()
    assert pt.concept_color("Your base salary", st) != pt.concept_color("HSA", st)


def test_all_palettes_give_distinct_colors_to_concepts_in_one_chart():
    for name in pt.PALETTES:
        st = _St()
        st.session_state = {"palette_choice": name}
        income = ["Your base salary", "Social Security", "Traditional 401(k)/IRA",
                  "Roth", "Taxable brokerage", "HSA"]
        assert len({pt.concept_color(n, st) for n in income}) == len(income)


def test_legend_is_container_anchored_with_bottom_margin():
    fig = go.Figure([go.Bar(x=[1], y=[1], name=n) for n in "abcde"])
    fig.update_layout(height=400, margin=dict(b=50), xaxis_title="Age")
    pt.style_fig(fig, _St())
    assert fig.layout.legend.yref == "container" and fig.layout.legend.y == 0
    assert fig.layout.margin.b >= 64 + 3 * 20  # axis + ceil(5/2) legend rows
    assert fig.layout.height > 400              # plot area keeps its size


def test_long_title_is_wrapped_and_top_margin_grows():
    fig = go.Figure(go.Bar(x=[1], y=[1]))
    fig.update_layout(title=dict(text="<b>" + "Word " * 12 + "</b><br><span>" + "sub " * 30 + "</span>"),
                      height=400, margin=dict(t=80))
    pt.style_fig(fig, _St())
    assert fig.layout.title.text.count("<br>") >= 3
    assert fig.layout.margin.t > 80
