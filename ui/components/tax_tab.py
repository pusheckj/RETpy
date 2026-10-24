"""Tax analysis tab."""
from __future__ import annotations

import plotly.graph_objects as go

from utils.formatting import money, pct


try:
    from utils.plot_theme import assign_colors, PLOTLY_CONFIG
except ImportError:
    from ui.utils.plot_theme import assign_colors, PLOTLY_CONFIG

# Federal marginal tax bracket rates (2024; the same rates for every filing
# status), shown as horizontal reference guides on the "% of income" view.
_FEDERAL_MARGINAL_RATES = [10, 12, 22, 24, 32, 35, 37]

_FILING_LABELS = {"MFJ": "married filing jointly", "S": "single",
                  "HOH": "head of household"}


def _tax_context(st) -> dict:
    """Active state + filing status, for the labels (from the sidebar inputs)."""
    from retirement_sim import config as cfg
    ov = st.session_state.get("user_overrides", {}) or {}
    code = cfg.resolve_state_code(ov.get("STATE_CHOICE", cfg.STATE_CHOICE))
    status = cfg.normalize_filing_status(ov.get("FILING_STATUS", cfg.FILING_STATUS))
    try:
        partner = int(ov.get("PARTNER_AGE", cfg.PARTNER_AGE) or 0) > 0
    except (TypeError, ValueError):
        partner = False
    if code == cfg.STATE_NONE:
        state_label = "State (none)"
    elif code == cfg.STATE_FLAT:
        state_label = "State (flat rate)"
    else:
        state_label = f"State ({code})"
    return {"state_label": state_label, "state_name": cfg.state_display_name(code),
            "status_label": _FILING_LABELS[status],
            "two_returns": cfg.files_two_returns(status, partner),
            # Markdown-escaped dollar sign.
            "niit": "\\$250k" if status == "MFJ" else "\\$200k"}


def _series(ctx: dict) -> list:
    return [
        ("Federal", "federal"),
        (ctx["state_label"], "state"),
        ("Payroll (FICA)", "fica"),
        ("LTCG", "ltcg"),
        ("NIIT", "niit"),
    ]


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
    ctx = _tax_context(st)
    series = _series(ctx)
    if not tax_rows:
        st.info("Per-year tax data not available.")
        st.markdown(
            f"""
            **Tax model summary:**
            - **Federal income tax**: 2024 brackets for {ctx['status_label']} (10% - 37%)
            - **State ({ctx['state_name']})**: that state's 2024 tax table
            - **Payroll (FICA)**: Social Security and Medicare tax on pay
            - **Federal LTCG**: 0% / 15% / 20% based on taxable income
            - **NIIT**: 3.8% surtax on investment income above {ctx['niit']} MAGI
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
            r.get("federal", 0) + r.get("state", 0) + r.get("fica", 0)
            + r.get("ltcg", 0) + r.get("niit", 0)
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

    series_colors = assign_colors([label for label, _ in series], st)

    fig = go.Figure()
    for label, key in series:
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
    # marginal bracket rates as subtle horizontal reference guides. (On the
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
        from utils.plot_theme import style_fig, show_chart
    except ImportError:
        from ui.utils.plot_theme import style_fig, show_chart
    show_chart(st, fig, chart_key, PLOTLY_CONFIG)

    two_returns = (" You're not married, so each of you files your own return."
                   if ctx["two_returns"] else "")
    with st.expander("About these tax categories"):
        st.markdown(
            f"""
            - **Federal income tax** — 2024 brackets for {ctx['status_label']}, applied to ordinary income (wages, Traditional 401k/IRA withdrawals, Social Security up to 85%).{two_returns}
            - **{ctx['state_label']}** — {ctx['state_name']} income tax from its 2024 tax table (brackets, deductions, and whether it taxes Social Security and retirement income). In retirement years it is included in the Federal band, since the simulation records one combined income-tax figure per year.
            - **Payroll (FICA)** — Social Security and Medicare tax on working-year pay.
            - **LTCG** — Long-term capital gains (0% / 15% / 20%) on taxable brokerage withdrawals.
            - **NIIT** — Net Investment Income Tax: 3.8% surtax on investment income when MAGI > {ctx['niit']}.
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
