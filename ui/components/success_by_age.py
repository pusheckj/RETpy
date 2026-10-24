"""Success rate by retirement age."""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.plot_theme import PLOTLY_CONFIG, active_palette, series_color, is_dark
except ImportError:
    from ui.utils.plot_theme import PLOTLY_CONFIG, active_palette, series_color, is_dark  # type: ignore


def _color(rate: float, target: float, st=None) -> str:
    """Bar color relative to the USER's target success rate.

    Two bugs lived here: the thresholds were hardcoded 0.80/0.60 while the
    dashed reference line uses the user's TARGET_SUCCESS_RATE (a 95%-target
    user saw reassuring "good"-teal bars sitting visibly BELOW their own target
    line), and the colors came from the module-level PALETTE constant, which is
    pinned to Pastel and ignores the palette picker.
    """
    pal = active_palette(st)
    if rate >= target:
        return pal[0]                    # good
    if rate >= 0.75 * target:
        return pal[5 % len(pal)]         # borderline
    return pal[2 % len(pal)]             # at risk


def render(st, results: dict, chart_key: str = "success_by_age_main") -> None:
    if not results:
        return
    by_age = results.get("success_rate_by_age", {}) or {}
    if not by_age:
        st.info("No age-scan data available.")
        return

    ages = sorted(by_age.keys())
    rates = [by_age[a] for a in ages]
    config_snapshot = results.get("config_snapshot", {}) or {}
    target_success_rate = float(config_snapshot.get("TARGET_SUCCESS_RATE", 0.80) or 0.80)
    colors = [_color(r, target_success_rate, st) for r in rates]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=ages,
        y=[r * 100 for r in rates],
        marker_color=colors,
        hovertemplate="Retire at %{x}<br>Success: %{y:.1f}%<extra></extra>",
        showlegend=False,
    ))

    # Target line at the user's configured target success rate
    fig.add_hline(y=target_success_rate * 100, line_dash="dash", line_color="#94a3b8",
                  annotation_text=f"{target_success_rate * 100:.0f}% target", annotation_position="top left",
                  annotation_font=dict(size=11, color="#64748b"),
                  # Opaque chip so the label stays legible where it crosses bars.
                  annotation_bgcolor=("rgba(15,23,42,0.9)" if is_dark(st) else "rgba(255,255,255,0.9)"))

    earliest = results.get("earliest_retirement_age")
    if earliest is not None:
        _earliest_color = series_color(0, st)
        fig.add_vline(x=earliest, line_dash="dash", line_color=_earliest_color,
                      annotation_text=f"Earliest: {earliest}",
                      annotation_position="top left",
                      annotation_font=dict(size=11, color=_earliest_color))

    fig.update_layout(
        title=dict(
            text="<b>When can you retire?</b><br><span style='font-size:13px;color:#64748b;'>Success probability at each retirement age</span>",
            x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
        ),
        height=340,
        margin=dict(l=50, r=30, t=80, b=50),
        xaxis=dict(title="Retirement age", gridcolor="#f1f5f9", zeroline=False, tickfont=dict(color="#64748b")),
        yaxis=dict(title="Success rate (%)", gridcolor="#f1f5f9", zeroline=False, range=[0, 105], tickfont=dict(color="#64748b")),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        bargap=0.3,
    )

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
