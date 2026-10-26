"""Retirement income sources stacked bar."""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.plot_theme import concept_color, PLOTLY_CONFIG
except ImportError:
    from ui.utils.plot_theme import concept_color, PLOTLY_CONFIG


def render(st, results: dict, chart_key: str = "income_sources_main") -> None:
    if not results:
        return
    pr = results.get("primary_result", {}) or {}
    rows = pr.get("income_sources_by_year", []) or []
    if not rows:
        st.info("No income-source breakdown for this simulation.")
        return

    ages = [r["age"] for r in rows]
    ss = [r.get("ss", 0) for r in rows]
    trad = [r.get("traditional", 0) for r in rows]
    roth = [r.get("roth", 0) for r in rows]
    taxable = [r.get("taxable", 0) for r in rows]
    hsa = [r.get("hsa", 0) for r in rows]
    # finding #14 — Roth CONVERSION is a traditional->Roth transfer, not
    # spending/income, so it is plotted as a separate dashed line overlay
    # (not stacked with the withdrawal/income bars) to avoid reading as
    # consumption.
    roth_conversion = [r.get("roth_conversion", 0) for r in rows]

    labels = ["Social Security", "Traditional 401(k)/IRA", "Roth", "Taxable brokerage", "HSA"]
    series_colors = {l: concept_color(l, st) for l in labels}

    fig = go.Figure()
    for label, values in [
        ("Social Security", ss),
        ("Traditional 401(k)/IRA", trad),
        ("Roth", roth),
        ("Taxable brokerage", taxable),
        ("HSA", hsa),
    ]:
        color = series_colors[label]
        fig.add_trace(go.Bar(
            x=ages, y=values, name=label, marker_color=color,
            hovertemplate=f"{label}<br>Age %{{x}}<br>$%{{y:,.0f}}<extra></extra>",
        ))

    if any(roth_conversion):
        fig.add_trace(go.Scatter(
            x=ages, y=roth_conversion, name="Roth conversion (transfer)",
            mode="lines+markers", line=dict(color="#7c3aed", dash="dot", width=2),
            marker=dict(size=5, symbol="diamond"),
            hovertemplate="Roth conversion (transfer)<br>Age %{x}<br>$%{y:,.0f}<extra></extra>",
        ))

    fig.update_layout(
        barmode="stack",
        title=dict(
            text="<b>Retirement income composition</b><br><span style='font-size:13px;color:#64748b;'>Yearly withdrawals by source (median at each age, across runs that last the whole plan)</span>",
            x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
        ),
        height=360,
        margin=dict(l=50, r=30, t=80, b=50),
        xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False, tickfont=dict(color="#64748b")),
        yaxis=dict(title="Annual income", gridcolor="#f1f5f9", zeroline=False, tickformat="$,.3~s", tickfont=dict(color="#64748b")),
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, bgcolor="rgba(0,0,0,0)", font=dict(color="#64748b", size=12)),
    )

    try:
        from utils.plot_theme import style_fig, show_chart
    except ImportError:
        from ui.utils.plot_theme import style_fig, show_chart

    show_chart(st, fig, chart_key, PLOTLY_CONFIG)
