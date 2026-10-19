"""Tax analysis tab."""
from __future__ import annotations

import plotly.graph_objects as go

from utils.formatting import money, pct


try:
    from utils.plot_theme import assign_colors, PLOTLY_CONFIG
except ImportError:
    from ui.utils.plot_theme import assign_colors, PLOTLY_CONFIG

_SERIES_NAMES = ["Federal", "State (CA)", "LTCG", "NIIT"]
_SERIES = [
    ("Federal", "federal"),
    ("State (CA)", "state"),
    ("LTCG", "ltcg"),
    ("NIIT", "niit"),
]

# Federal MFJ marginal tax bracket rates (2024), shown as horizontal
# reference guides on the "% of income" view.
_FEDERAL_MARGINAL_RATES = [10, 12, 22, 24, 32, 35, 37]


def _effective_rate(total_tax: float, gross_income: float) -> float:
    if gross_income <= 0:
        return 0.0
    return (total_tax / gross_income) * 100.0


def render(st, results: dict, chart_key: str = "tax_tab_main") -> None:
    if not results:
        return
    pr = results.get("primary_result", {}) or {}
    tax_rows = pr.get("taxes_by_year", []) or []
    retirement_age = pr.get("retirement_age", None)
    if not tax_rows:
        st.info("Per-year tax data not available.")
        st.markdown(
            """
            **Tax model summary:**
            - **Federal income tax**: 2024 MFJ brackets (10% - 37%)
            - **California state**: 2024 brackets (1% - 12.3%) — configurable
            - **Federal LTCG**: 0% / 15% / 20% based on taxable income
            - **NIIT**: 3.8% surtax on investment income above $250k MAGI
            - **Medicare IRMAA**: Higher Part B/D premiums based on MAGI tier
            """
        )
        return

    view = st.radio(
        "View",
        options=["Dollar amount", "% of income"],
        horizontal=True,
        key="tax_tab_view",
    )

    # Partition rows into working vs retirement years for KPIs.
    if retirement_age is None:
        working_rows = list(tax_rows)
        ret_rows = []
    else:
        working_rows = [r for r in tax_rows if r.get("age", 0) < retirement_age]
        ret_rows = [r for r in tax_rows if r.get("age", 0) >= retirement_age]

    def _total(rows):
        return sum(
            r.get("federal", 0) + r.get("state", 0) + r.get("ltcg", 0) + r.get("niit", 0)
            for r in rows
        )

    def _gross(rows):
        return sum(r.get("gross_income", 0) for r in rows)

    working_tax = _total(working_rows)
    ret_tax = _total(ret_rows)
    working_gross = _gross(working_rows)
    ret_gross = _gross(ret_rows)

    cols = st.columns(4)
    with cols[0]:
        st.metric("Working-years tax", money(working_tax, shorten=True))
    with cols[1]:
        st.metric("Retirement-years tax", money(ret_tax, shorten=True))
    with cols[2]:
        if working_gross > 0:
            st.metric(
                "Effective working rate",
                f"{_effective_rate(working_tax, working_gross):.1f}%",
            )
        else:
            st.metric("Effective working rate", "—")
    with cols[3]:
        if ret_gross > 0:
            st.metric(
                "Effective retirement rate",
                f"{_effective_rate(ret_tax, ret_gross):.1f}%",
            )
        else:
            st.metric("Effective retirement rate", "—")

    ages = [r.get("age") for r in tax_rows]

    series_colors = assign_colors(_SERIES_NAMES, st)

    fig = go.Figure()
    for label, key in _SERIES:
        color = series_colors[label]
        if view == "Dollar amount":
            values = [r.get(key, 0) for r in tax_rows]
            hover = f"{label}<br>Age %{{x}}<br>$%{{y:,.0f}}<extra></extra>"
        else:
            values = [
                (r.get(key, 0) / r.get("gross_income", 0)) * 100.0
                if r.get("gross_income", 0) > 0
                else 0.0
                for r in tax_rows
            ]
            # Single `%` — Plotly's hovertemplate substitution has no `%%`
            # escape (that's a printf/d3-time-format convention), so `%%`
            # rendered literally as "14.20%%".
            hover = f"{label}<br>Age %{{x}}<br>%{{y:.2f}}%<extra></extra>"
        fig.add_trace(go.Scatter(
            x=ages, y=values, mode="lines",
            stackgroup="one", name=label, line=dict(width=0),
            fillcolor=color,
            hovertemplate=hover,
        ))

    if retirement_age is not None:
        fig.add_vline(
            x=retirement_age,
            line_dash="dash",
            line_color="#94a3b8",
            annotation_text=f"Retire @ {retirement_age}",
            annotation_position="top left",
            annotation_font=dict(size=11, color="#64748b"),
        )

    # On the "% of income" view the y-axis is a rate, so overlay the federal
    # MFJ marginal bracket rates as subtle horizontal reference guides. (On the
    # "Dollar amount" view the y-axis is dollars, so these don't map — skip.)
    if view != "Dollar amount":
        for rate in _FEDERAL_MARGINAL_RATES:
            fig.add_hline(
                y=rate,
                line_dash="dash",
                line_color="rgba(148, 163, 184, 0.45)",
                line_width=1,
                annotation_text=f"{rate}%",
                annotation_position="top right",
                annotation_font=dict(size=9, color="rgba(148, 163, 184, 0.9)"),
            )

    if view == "Dollar amount":
        subtitle = "Annual tax by source"
        yaxis_title = "Annual tax"
        yaxis_tickformat = "$,.3~s"
        yaxis_ticksuffix = ""
    else:
        subtitle = "Effective tax rate by source (share of gross income)"
        yaxis_title = "Effective tax rate"
        yaxis_tickformat = ".1f"
        yaxis_ticksuffix = "%"

    fig.update_layout(
        title=dict(
            text=f"<b>Tax flow over plan horizon</b><br><span style='font-size:13px;color:#64748b;'>{subtitle}</span>",
            x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
        ),
        height=360,
        margin=dict(l=50, r=30, t=80, b=50),
        xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False, tickfont=dict(color="#64748b")),
        yaxis=dict(
            title=yaxis_title,
            gridcolor="#f1f5f9",
            zeroline=False,
            tickformat=yaxis_tickformat,
            ticksuffix=yaxis_ticksuffix,
            tickfont=dict(color="#64748b"),
        ),
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, bgcolor="rgba(0,0,0,0)", font=dict(color="#64748b", size=12)),
    )
    try:
        from utils.plot_theme import style_fig
    except ImportError:
        from ui.utils.plot_theme import style_fig
    fig = style_fig(fig, st)
    st.plotly_chart(
        fig,
        width="stretch",
        config=PLOTLY_CONFIG,
        key=chart_key,
    )

    with st.expander("About these tax categories"):
        st.markdown(
            """
            - **Federal income tax** — 2024 MFJ brackets applied to ordinary income (Traditional 401k/IRA withdrawals, SS up to 85%, wages).
            - **State (CA)** — California income tax, treats all capital gains as ordinary income. Swap for your state in `retirement_sim/config.py`.
            - **LTCG** — Long-term capital gains (0% / 15% / 20%) on taxable brokerage withdrawals.
            - **NIIT** — Net Investment Income Tax: 3.8% surtax on investment income when MAGI > $250k MFJ.
            - **RMDs** — from your RMD start age (72, 73 or 75 depending on birth
              year, per SECURE 2.0; each owner uses their own age, so a younger
              partner starts later) the IRS forces a minimum withdrawal from
              Traditional 401(k)/IRA balances each year. The simulation models
              these: the forced amount is withdrawn, taxed as ordinary income, and
              any part you don't need for spending is reinvested into taxable
              brokerage. The **"Withdrawal rate by source"** chart breaks them out
              as their own amber *RMD (IRS-forced)* band, so you can see how much
              of a year's draw was mandatory rather than chosen — hover it for the
              forced / spent / reinvested split. Roth conversions before that age
              shrink them (often to zero).
            - **IRMAA** (not shown here): higher Medicare premiums in retirement based on MAGI 2 years prior. Captured in retirement expenses.
            """
        )
