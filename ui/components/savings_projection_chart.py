"""Savings projection chart — stacked-bar visualization of year-by-year
contributions broken out by destination account (the running total is in the hover).

Reads ``results['primary_result']['savings_contributions_by_year']``: the
simulation's own contributions each working year (deferrals, employer match,
Roth, and the brokerage sweep), the same rows the savings-rate chart below
divides by income. Accounts and their sum come from ``savings_rate_inputs``,
so "Year 1 savings" here is the numerator of that chart's first bar.
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.coerce import as_fraction
    from utils.formatting import metric_row, money
    from utils.plot_theme import is_dark
    from components.savings_rate_inputs import (
        ALLOCATION_ORDER,
        get_allocation_colors,
        year_savings,
    )
except ImportError:  # pragma: no cover
    from ui.utils.coerce import as_fraction  # type: ignore
    from ui.utils.formatting import metric_row, money  # type: ignore
    from ui.utils.plot_theme import is_dark  # type: ignore
    from ui.components.savings_rate_inputs import (  # type: ignore
        ALLOCATION_ORDER,
        get_allocation_colors,
        year_savings,
    )


def savings_rows(results: dict) -> list:
    """The simulation's per-year contributions (working years only)."""
    return list(((results or {}).get("primary_result", {}) or {})
                .get("savings_contributions_by_year", []) or [])


def render(st, results: dict = None, chart_key: str = "savings_projection_main") -> None:
    rows = savings_rows(results)
    if not rows:
        st.info("No working years before the target retirement age, so there are "
                "no contributions to show.")
        return
    overrides = st.session_state.get("user_overrides", {}) or {}

    # Display option only (sec_savings "Show contributions in future dollars"):
    # the simulation works in today's dollars.
    nominal = bool(overrides.get("SAVINGS_INFLATION_ADJUST", True))
    inflation = as_fraction(overrides.get("EXPECTED_INFLATION", 0.0275), 0.0275)
    first_age = int(rows[0]["age"])

    def scale(age: int) -> float:
        return (1.0 + inflation) ** (age - first_age) if nominal else 1.0

    dollars = "future dollars" if nominal else "today's dollars"
    ages = [int(r["age"]) for r in rows]
    totals = [year_savings(r) * scale(a) for r, a in zip(rows, ages)]
    cumulative, running = [], 0.0
    for t in totals:
        running += t
        cumulative.append(running)
    years = len(rows)

    # KPI strip. "Year 1 savings rate" is the savings-rate chart's first bar.
    first = rows[0]
    gross = float(first.get("gross_income", 0.0) or 0.0)
    metric_row(st, [
        ("Years saving", f"{years}", {}),
        ("Year 1 savings", money(year_savings(first), shorten=True),
         dict(help="Everything that goes into your accounts this year, "
                   "employer match included.")),
        ("Year 1 savings rate",
         f"{100.0 * year_savings(first) / gross:.1f}%" if gross > 0 else "—",
         dict(help="Year 1 savings as a share of pre-tax pay.")),
        ("Total contributed", money(cumulative[-1], shorten=True),
         dict(help=f"In {dollars}.")),
    ])

    # Stacked bars. The running total rides along as customdata on the top bar of
    # the stack, so the unified hover ends with "Cumulative: $X" (one y-axis only).
    fig = go.Figure()
    allocation_colors = get_allocation_colors(st)
    traces = []
    for label, field, _owner in ALLOCATION_ORDER:
        values = [float(r.get(field, 0.0) or 0.0) * scale(a) for r, a in zip(rows, ages)]
        if any(v > 0 for v in values):
            traces.append((label, values))
    for k, (label, values) in enumerate(traces):
        last = k == len(traces) - 1
        fig.add_trace(go.Bar(
            x=ages,
            y=values,
            name=label,
            marker_color=allocation_colors.get(label, "#94a3b8"),
            customdata=cumulative if last else None,
            hovertemplate=f"{label}<br>Age %{{x}}<br>$%{{y:,.0f}}"
                          + ("<br>Cumulative: $%{customdata:,.0f}" if last else "")
                          + "<extra></extra>",
        ))
    dark = is_dark(st)

    fig.update_layout(
        barmode="stack",
        title=dict(
            text="<b>Projected savings by account</b><br>"
                 "<span style='font-size:13px;color:#64748b;'>"
                 "Annual contributions by destination · "
                 f"{money(cumulative[-1], shorten=True)} total by age {ages[-1]} · "
                 f"{dollars}, <em>before</em> returns</span>",
            x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
        ),
        height=420,
        margin=dict(l=50, r=30, t=80, b=50),
        xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False,
                   tickfont=dict(color="#64748b"), fixedrange=False),
        yaxis=dict(
            title="Annual contribution",
            gridcolor="#f1f5f9",
            zeroline=False,
            tickformat="$,.3~s",
            tickfont=dict(color="#64748b"),
            side="left",
        ),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        hovermode="x unified",
        dragmode="pan",
        bargap=0.25,
        legend=dict(orientation="v", yanchor="top", y=1.0,
                    xanchor="left", x=1.14, bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#64748b", size=11)),
        uirevision="keep",
    )

    try:
        from utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG
    except ImportError:
        from ui.utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG

    show_chart(st, fig, f"{chart_key}_{'dk' if dark else 'lt'}", PLOTLY_CONFIG)

    st.caption(
        "Stacked bars show **where each year's savings goes**, as the simulation "
        "makes it: your contributions, your employer's match, and everything else "
        "you don't spend invested in a taxable brokerage account. Hover a bar to see "
        "the running total (no investment growth yet). Investment returns "
        "compound on top of these contributions in the Monte Carlo simulation."
    )
