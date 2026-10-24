"""Savings projection chart — stacked-bar visualization of year-by-year
contributions broken out by destination account, plus a cumulative line
overlay.

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
    from utils.formatting import money
    from utils.plot_theme import is_dark
    from components.savings_rate_inputs import (
        ALLOCATION_ORDER,
        get_allocation_colors,
        year_savings,
    )
except ImportError:  # pragma: no cover
    from ui.utils.coerce import as_fraction  # type: ignore
    from ui.utils.formatting import money  # type: ignore
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
    cols = st.columns(4)
    with cols[0]:
        st.metric("Years saving", f"{years}")
    with cols[1]:
        st.metric("Year 1 savings", money(year_savings(first), shorten=True),
                  help="Everything that goes into your accounts this year, "
                       "employer match included.")
    with cols[2]:
        st.metric("Year 1 savings rate",
                  f"{100.0 * year_savings(first) / gross:.1f}%" if gross > 0 else "—",
                  help="Year 1 savings as a share of pre-tax pay.")
    with cols[3]:
        st.metric("Total contributed", money(cumulative[-1], shorten=True),
                  help=f"In {dollars}.")

    # Stacked bars + cumulative line
    fig = go.Figure()
    allocation_colors = get_allocation_colors(st)
    for label, field, _owner in ALLOCATION_ORDER:
        values = [float(r.get(field, 0.0) or 0.0) * scale(a) for r, a in zip(rows, ages)]
        if not any(v > 0 for v in values):
            continue
        fig.add_trace(go.Bar(
            x=ages,
            y=values,
            name=label,
            marker_color=allocation_colors.get(label, "#94a3b8"),
            hovertemplate=f"{label}<br>Age %{{x}}<br>$%{{y:,.0f}}<extra></extra>",
        ))

    # style_fig() re-themes backgrounds/fonts/axes but never trace colors, so a
    # hardcoded slate-900 dotted line was invisible on the dark card background.
    dark = is_dark(st)
    cum_color = "#e2e8f0" if dark else "#0f172a"

    fig.add_trace(go.Scatter(
        x=ages,
        y=cumulative,
        name="Cumulative total",
        mode="lines",
        line=dict(color=cum_color, width=2.5, dash="dot"),
        hovertemplate="Age %{x}<br>Cumulative: $%{y:,.0f}<extra></extra>",
        yaxis="y2",
    ))

    fig.update_layout(
        barmode="stack",
        title=dict(
            text="<b>Projected savings by account</b><br>"
                 "<span style='font-size:13px;color:#64748b;'>"
                 "Annual contributions stacked by destination · "
                 f"{dollars} · "
                 "<em>before</em> investment returns</span>",
            x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
        ),
        height=420,
        margin=dict(l=50, r=200, t=80, b=50),
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
        yaxis2=dict(
            title="Cumulative",
            overlaying="y",
            side="right",
            gridcolor="rgba(0,0,0,0)",
            tickformat="$,.3~s",
            tickfont=dict(color="#0f172a"),
            showgrid=False,
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
        from utils.plot_theme import style_fig, PLOTLY_CONFIG
    except ImportError:
        from ui.utils.plot_theme import style_fig, PLOTLY_CONFIG
    fig = style_fig(fig, st)

    st.plotly_chart(
        fig,
        width="stretch",
        key=f"{chart_key}_{'dk' if dark else 'lt'}",
        config=PLOTLY_CONFIG,
    )

    st.caption(
        "Stacked bars show **where each year's savings goes**, as the simulation "
        "makes it: your contributions, your employer's match, and everything else "
        "you don't spend invested in a brokerage account. The dotted line is "
        "cumulative contributions (no investment growth yet). Investment returns "
        "compound on top of these contributions in the Monte Carlo simulation."
    )
