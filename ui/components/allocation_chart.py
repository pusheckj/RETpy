"""Asset allocation glide path chart."""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.plot_theme import PALETTE, PLOTLY_CONFIG, series_color
except ImportError:
    from ui.utils.plot_theme import PALETTE, PLOTLY_CONFIG, series_color  # type: ignore


def render(st, results: dict, chart_key: str = "allocation_main") -> None:
    if not results:
        return
    pr = results.get("primary_result", {}) or {}
    alloc = pr.get("allocation_by_year", []) or []
    if not alloc:
        st.info("Glide path data not available.")
        return

    ages = [row["age"] for row in alloc]
    stocks = [row["stock_pct"] * 100 for row in alloc]
    bonds = [row["bond_pct"] * 100 for row in alloc]
    retire_age = pr.get("retirement_age", None)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ages, y=stocks,
        mode="lines",
        stackgroup="one",
        name="Stocks",
        line=dict(width=0),
        fillcolor=series_color(0, st),
        hovertemplate="Age %{x}<br>Stocks: %{y:.0f}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=ages, y=bonds,
        mode="lines",
        stackgroup="one",
        name="Bonds",
        line=dict(width=0),
        fillcolor=series_color(1, st),
        hovertemplate="Age %{x}<br>Bonds: %{y:.0f}%<extra></extra>",
    ))

    if retire_age is not None:
        fig.add_vline(
            x=retire_age,
            line_dash="dash",
            line_color="#94a3b8",
            annotation_text=f"Retire @ {retire_age}",
            annotation_position="top right",
            annotation_font=dict(size=11, color="#64748b"),
        )

    fig.update_layout(
        title=dict(
            text="<b>Asset allocation</b><br><span style='font-size:13px;color:#64748b;'>Stock/bond mix from today through plan horizon</span>",
            x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
        ),
        height=280,
        margin=dict(l=50, r=30, t=80, b=50),
        xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False, tickfont=dict(color="#64748b")),
        yaxis=dict(title="Allocation (%)", gridcolor="#f1f5f9", zeroline=False, range=[0, 100], tickfont=dict(color="#64748b")),
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        hovermode="x unified",
        dragmode="pan",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0, bgcolor="rgba(0,0,0,0)", font=dict(color="#64748b", size=12)),
    )

    fig.update_xaxes(fixedrange=False)
    fig.update_yaxes(fixedrange=False)

    try:
        from utils.plot_theme import style_fig
    except ImportError:
        from ui.utils.plot_theme import style_fig
    fig = style_fig(fig, st)

    st.plotly_chart(
        fig,
        width="stretch",
        key=chart_key,
        config=PLOTLY_CONFIG,
    )
