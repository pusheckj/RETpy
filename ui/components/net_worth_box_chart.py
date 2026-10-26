"""Investable-net-worth box plot over time — the distribution of projected
investable balance across all Monte Carlo runs, per age.

EXCLUDES home equity: the underlying rows are portfolio balance paths, the same
rows first_decade_stress.py reads. The top bar and portfolio_breakdown's
"Net worth" card DO include home equity, so this chart must not reuse that
label or the two disagree on screen with no explanation.

Reads ``results['primary_result']['networth_by_year']`` = per-age percentiles
(p10/p25/p50/p75/p90) of total portfolio balance, aligned on the full horizon
(a depleted path counts as $0 in later years). Shows how the outcome fans out
as market returns compound over decades.
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.coerce import safe_int, as_fraction
    from utils.household import plan_end_ages
    from utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark, beeswarm_xy
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, as_fraction  # type: ignore
    from ui.utils.household import plan_end_ages  # type: ignore
    from ui.utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark, beeswarm_xy  # type: ignore


def render(st, results: dict = None, chart_key: str = "net_worth_box_main") -> None:
    if not results:
        return
    rows = (results.get("primary_result", {}) or {}).get("networth_by_year", []) or []
    if not rows:
        return

    overrides = st.session_state.get("user_overrides", {}) or {}
    current_age = safe_int(overrides.get("YOUR_AGE", 25), 25)
    retirement_age = safe_int(overrides.get("TARGET_RETIREMENT_AGE", 55), 55)
    plan_until = plan_end_ages(overrides)[0]  # when the plan ends (cfg.plan_end_age)
    inflation_rate = as_fraction(overrides.get("EXPECTED_INFLATION", 0.0275), 0.0275)

    def _body() -> None:
        c1, c2 = st.columns(2)
        with c1:
            mode = st.radio(
                "Dollars", options=["Today's $", "Future $"],
                horizontal=True, key=f"{chart_key}_dollars", label_visibility="collapsed",
            )
        with c2:
            style = st.radio(
                "Style", options=["Box plot", "Point cloud (violin)"],
                horizontal=True, key=f"{chart_key}_style", label_visibility="collapsed",
            )
        future = str(mode).startswith("Future")
        points_mode = "Point cloud" in str(style)

        def infl(a: int) -> float:
            return (1.0 + inflation_rate) ** (a - current_age) if future else 1.0

        ages = [int(r["age"]) for r in rows]
        p10 = [float(r["p10"]) * infl(int(r["age"])) for r in rows]
        p25 = [float(r["p25"]) * infl(int(r["age"])) for r in rows]
        p50 = [float(r["p50"]) * infl(int(r["age"])) for r in rows]
        p75 = [float(r["p75"]) * infl(int(r["age"])) for r in rows]
        p90 = [float(r["p90"]) * infl(int(r["age"])) for r in rows]

        dark = is_dark(st)
        box_color = "#14b8a6" if dark else "#0d9488"
        fill = "rgba(20,184,166,0.35)" if dark else "rgba(13,148,136,0.30)"
        ref_line = "#e2e8f0" if dark else "#0f172a"

        fig = go.Figure()
        if points_mode:
            allx, ally = [], []
            for r in rows:
                a = int(r["age"]); f = infl(a)
                xs, ys = beeswarm_xy([float(s) * f for s in r.get("samples", [])], a)
                allx += xs; ally += ys
            fig.add_trace(go.Scatter(
                x=allx, y=ally, mode="markers",
                marker=dict(size=3, color=box_color, opacity=0.45),
                hoverinfo="skip", showlegend=False, name="paths",
            ))
            fig.add_trace(go.Scatter(
                x=ages, y=p50, mode="lines", line=dict(color=ref_line, width=2),
                name="median", hovertemplate="Age %{x}<br>median $%{y:,.0f}<extra></extra>",
            ))
        else:
            fig.add_trace(go.Box(
                x=ages, q1=p25, median=p50, q3=p75, lowerfence=p10, upperfence=p90,
                name="Investable portfolio", boxpoints=False,
                marker_color=box_color, line=dict(color=box_color, width=1.2),
                fillcolor=fill,
                customdata=list(zip(p10, p25, p50, p75, p90)),
                hovertemplate=(
                    "Age %{x}<br>90th $%{customdata[4]:,.0f}<br>75th $%{customdata[3]:,.0f}<br>"
                    "median $%{customdata[2]:,.0f}<br>25th $%{customdata[1]:,.0f}<br>"
                    "10th $%{customdata[0]:,.0f}<extra></extra>"
                ),
            ))
        if current_age <= retirement_age <= plan_until:
            fig.add_vline(
                x=retirement_age, line_dash="dash", line_color="#94a3b8",
                annotation_text=f"Retirement (age {retirement_age})",
                annotation_position="top left", annotation_font=dict(size=10, color="#64748b"),
            )

        mode_label = "future (nominal) dollars" if future else "today's dollars"
        unit = "$, nominal" if future else "$, today"
        # In point-cloud mode a few lucky paths can be orders of magnitude above
        # p90 (e.g. historical returns compounding to $1B+), which would flatten
        # the whole cloud. Clip the axis to the same p90-based range the box plot
        # uses so the violin body stays readable (extreme outliers are suppressed).
        y_cap = 1.15 * max([v for v in p90 if v] or [1.0]) if points_mode else None
        fig.update_layout(
            title=dict(
                text="<b>Investable portfolio range over time</b><br>"
                     f"<span style='font-size:13px;color:#64748b;'>Projected investable "
                     f"balance across Monte Carlo runs · {mode_label}</span>",
                x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
            ),
            height=420, margin=dict(l=50, r=40, t=80, b=50),
            # Clamp to the data: on narrow charts Plotly autoranged the box
            # axis down to age 0 (a big empty left third on a phone).
            xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False,
                       tickfont=dict(color="#64748b"), fixedrange=False,
                       range=[min(ages) - 1, max(ages) + 1]),
            yaxis=dict(title=f"Investable portfolio ({unit})", gridcolor="#f1f5f9", zeroline=False,
                       rangemode="tozero", tickformat="$,.3~s", tickfont=dict(color="#64748b"),
                       range=([0, y_cap] if points_mode else None)),
            showlegend=False, dragmode="pan", boxgap=0.2,
            transition=(dict(duration=0) if points_mode
                        else dict(duration=350, easing="cubic-in-out")),
            uirevision="keep",
        )
        show_chart(st, fig, f"{chart_key}_{'nom' if future else 'tod'}_{'pts' if points_mode else 'box'}_{'dk' if dark else 'lt'}", PLOTLY_CONFIG)
        st.caption(
            "Each box shows the spread of **investable net worth across all simulated market "
            "paths** at that age. It leaves out home equity, unlike the \"Net worth\" figures "
            "elsewhere. The box covers the middle 50% (25th to 75th percentile), the whiskers "
            "reach the 10th and 90th, and the line is the median. The range widens over time as "
            "returns compound. Runs that run out of money count as $0, which pulls the lower "
            "percentiles toward zero in later years."
        )

    _body()
