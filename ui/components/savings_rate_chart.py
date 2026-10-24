"""Savings-rate chart — household savings as a % of income, per working year,
with a pre-tax (% of gross income) vs post-tax (% of take-home) toggle.

Reads ``results['primary_result']['savings_contributions_by_year']``, which
carries both the year's contributions (numerator) AND that year's gross +
after-tax household income (denominator) from the same engine-consistent source
(``sim_runner._approximate_savings_contributions``). Sourcing both from one place
keeps this rate internally consistent with the "Projected savings by account"
chart's contributions and honors the engine's Auto residual-sweep behavior.
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark
    from components.savings_rate_inputs import year_savings
except ImportError:  # pragma: no cover
    from ui.utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark
    from ui.components.savings_rate_inputs import year_savings  # type: ignore


def _rate_series(rows: list, post_tax: bool) -> tuple:
    """(ages, rates%) for each working year with positive income. The numerator
    is savings_rate_inputs.year_savings -- the same sum as the "Projected
    savings by account" bars and its "Year 1 savings" tile (employer match
    included, the standard "total savings rate")."""
    ages, rates = [], []
    for r in rows:
        denom = float(r.get("after_tax_income" if post_tax else "gross_income", 0.0))
        if denom <= 0:
            continue
        ages.append(int(r["age"]))
        rates.append(100.0 * year_savings(r) / denom)
    return ages, rates


def render(st, results: dict = None, chart_key: str = "savings_rate_main") -> None:
    if not results:
        return
    rows = (results.get("primary_result", {}) or {}).get("savings_contributions_by_year", []) or []
    if not rows:
        return

    mode = st.radio(
        "Savings-rate basis",
        options=["% of pre-tax income", "% of take-home (post-tax)"],
        horizontal=True,
        key=f"{chart_key}_basis",
        label_visibility="collapsed",
    )
    post_tax = "take-home" in str(mode)

    ages, rates = _rate_series(rows, post_tax)
    if not ages:
        st.info("No working-year income available to compute a savings rate.")
        return

    avg = sum(rates) / len(rates)
    bar_color = "#14b8a6" if is_dark(st) else "#0d9488"
    ref_color = "#e2e8f0" if is_dark(st) else "#0f172a"
    basis_label = "take-home (after-tax)" if post_tax else "pre-tax (gross)"

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=ages, y=rates, name="Savings rate",
        marker_color=bar_color, marker_line_width=0,
        hovertemplate="Age %{x}<br>Saving %{y:.1f}% of " + basis_label + " income<extra></extra>",
    ))
    fig.add_hline(
        y=avg, line_dash="dash", line_color=ref_color,
        annotation_text=f"Avg {avg:.1f}%", annotation_position="top left",
        annotation_font=dict(size=11, color=ref_color),
    )
    fig.update_layout(
        title=dict(
            text="<b>Savings rate</b><br><span style='font-size:13px;color:#64748b;'>"
                 f"Household contributions (incl. employer match) as a % of {basis_label} "
                 "income, per working year</span>",
            x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
        ),
        height=380,
        margin=dict(l=50, r=40, t=80, b=50),
        xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False,
                   tickfont=dict(color="#64748b"), fixedrange=False),
        yaxis=dict(title="Savings rate (%)", gridcolor="#f1f5f9", zeroline=False,
                   rangemode="tozero", ticksuffix="%", tickfont=dict(color="#64748b")),
        showlegend=False, hovermode="x unified", dragmode="pan", bargap=0.2,
        uirevision="keep",
    )
    show_chart(st, fig, chart_key, PLOTLY_CONFIG)

    tail = (
        "take-home (after-tax) income. This runs higher than the pre-tax view because "
        "pre-tax 401(k)/HSA dollars are saved before they'd ever show up in take-home pay."
        if post_tax else
        "gross (pre-tax) income."
    )
    st.caption(
        "Share of household income saved each working year — the same savings as the "
        "bars above: 401(k) (incl. employer match), HSA, Roth, and taxable-brokerage "
        "contributions, divided by " + tail
        + " The dashed line is the working-years average."
    )
