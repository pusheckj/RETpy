"""Savings projection chart — stacked-bar visualization of year-by-year
contributions broken out by destination account, plus a cumulative line
overlay. Reads directly from st.session_state.user_overrides via the
``project_savings`` helper.
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.coerce import safe_int
    from utils.formatting import money
    from utils.plot_theme import is_dark
    from components.savings_rate_inputs import (
        project_savings,
        ALLOCATION_ORDER,
        get_allocation_colors,
    )
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int  # type: ignore
    from ui.utils.formatting import money  # type: ignore
    from ui.utils.plot_theme import is_dark  # type: ignore
    from ui.components.savings_rate_inputs import (  # type: ignore
        project_savings,
        ALLOCATION_ORDER,
        get_allocation_colors,
    )


def render(st, results: dict = None, chart_key: str = "savings_projection_main") -> None:
    overrides = st.session_state.get("user_overrides", {}) or {}
    start_age = safe_int(overrides.get("YOUR_AGE", 25), 25)
    retirement_age = safe_int(overrides.get("TARGET_RETIREMENT_AGE", 60), 60)

    if retirement_age <= start_age:
        st.info(
            "Set your target retirement age above your current age in the Quick inputs "
            "to see a savings projection."
        )
        return

    rows = project_savings(overrides, start_age, retirement_age)
    if not rows:
        return

    ages = [r["age"] for r in rows]
    cumulative = [r["cumulative"] for r in rows]
    total_at_retire = cumulative[-1]
    years = len(rows)

    # Account categories: order matters for the stack. Labels must match
    # _allocation_for_year() output keys EXACTLY (this list was previously
    # stale — "Brokerage (residual)" was a leftover from an older model and
    # caused brokerage contributions to silently drop from the stacked bars
    # while still appearing in the cumulative line).
    account_keys = [
        "Your 401(k)",
        "Your 401(k) match",
        "Your HSA",
        "Your Roth (backdoor)",
        "Your brokerage",
        "Partner 401(k)",
        "Partner Roth IRA",
        "Partner brokerage",
    ]

    # KPI strip
    cols = st.columns(4)
    first_breakdown = rows[0]["by_account"]
    today_total = sum(first_breakdown.values())
    today_tax_adv = sum(
        v for k, v in first_breakdown.items()
        if k not in ("Your brokerage", "Partner brokerage", "Your 401(k) match")
    )
    with cols[0]:
        st.metric("Mode", str(overrides.get("SAVINGS_RATE_MODE", "percent")).title())
    with cols[1]:
        st.metric("Years saving", f"{years}")
    with cols[2]:
        st.metric("Year 1 savings", money(today_total, shorten=True))
    with cols[3]:
        st.metric("Total contributed", money(total_at_retire, shorten=True))

    # Stacked bars + cumulative line
    fig = go.Figure()
    allocation_colors = get_allocation_colors(st)
    for label in account_keys:
        values = [r["by_account"].get(label, 0.0) for r in rows]
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
        name="Cumulative (no growth)",
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
        "Stacked bars show **where each year's savings goes**. The dotted line is "
        "cumulative contributions (no investment growth yet). Investment returns "
        "compound on top of these contributions in the Monte Carlo simulation."
    )
