"""Spending-range boxplot — the distribution of annual spending across all Monte
Carlo runs, per age. Shows how much year-to-year spending varies because market
outcomes flex the spending guardrails.

Reads ``results['primary_result']['spending_by_year']`` = per-age percentiles
(p10/p25/p50/p75/p90) of the GUARDRAIL-ADJUSTED living spending, collected from
``portfolio.spending_log`` across every Monte Carlo run. Pre-retirement
spending is deterministic (the guardrails act only in retirement), so those
boxes are flat; the retirement boxes fan out with the market/guardrail spread.
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.coerce import safe_int, as_fraction
    from utils.household import plan_end_ages
    from utils.plot_theme import style_fig, PLOTLY_CONFIG, is_dark, beeswarm_xy
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, as_fraction  # type: ignore
    from ui.utils.household import plan_end_ages  # type: ignore
    from ui.utils.plot_theme import style_fig, PLOTLY_CONFIG, is_dark, beeswarm_xy  # type: ignore


def render(st, results: dict = None, chart_key: str = "spending_range_main") -> None:
    if not results:
        return
    rows = (results.get("primary_result", {}) or {}).get("spending_by_year", []) or []
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
                "Dollars", options=["Today's dollars", "Future (nominal) dollars"],
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
            # Density-packed point cloud (violin-shaped beeswarm) from the raw
            # per-path samples, plus a median line for reference.
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
                name="median", hovertemplate="Age %{x}<br>median $%{y:,.0f}/yr<extra></extra>",
            ))
        else:
            fig.add_trace(go.Box(
                x=ages, q1=p25, median=p50, q3=p75, lowerfence=p10, upperfence=p90,
                name="Annual spending", boxpoints=False,
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
        # Zoom the y-axis onto the data. From $0 the boxes were a few pixels tall
        # (spending barely moves between runs next to its own level), so frame the
        # p10-p90 spread with 10% padding and at least a quarter of the top value
        # as span, so a tiny spread isn't blown up into a dramatic one.
        hi_v = max([v for v in p90 if v] or [1.0])
        lo_v = min(p10) if p10 else 0.0
        span = max(hi_v - lo_v, 0.25 * hi_v)
        mid = (hi_v + lo_v) / 2.0
        y_lo = max(0.0, mid - span / 2.0 - 0.1 * span)
        y_hi = mid + span / 2.0 + 0.1 * span
        fig.update_layout(
            title=dict(
                text="<b>Spending range across market scenarios</b><br>"
                     f"<span style='font-size:13px;color:#64748b;'>Distribution of guardrail-adjusted "
                     f"annual living spending across Monte Carlo runs · {mode_label}</span>",
                x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
            ),
            height=420, margin=dict(l=50, r=40, t=80, b=50),
            xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False,
                       tickfont=dict(color="#64748b"), fixedrange=False),
            yaxis=dict(title=f"Annual spending ({unit})", gridcolor="#f1f5f9", zeroline=False,
                       tickformat="$,.3~s", tickfont=dict(color="#64748b"),
                       range=[y_lo, y_hi]),
            showlegend=False, dragmode="pan", boxgap=0.2,
            transition=(dict(duration=0) if points_mode
                        else dict(duration=350, easing="cubic-in-out")),
            uirevision="keep",
        )
        fig = style_fig(fig, st)
        st.plotly_chart(
            fig, width="stretch",
            key=f"{chart_key}_{'nom' if future else 'tod'}_{'pts' if points_mode else 'box'}_{'dk' if dark else 'lt'}",
            config=PLOTLY_CONFIG,
        )

        # MAX over ages, not rows[-1]: a depleted path's spending_log stops at
        # failure, so the last row is the plan-end age where n == the number of
        # SURVIVING paths (the minimum n on the chart). rows[-1] reported "~800
        # simulated paths" for a 1,000-sim run at 80% success.
        n = max((r.get("n", 0) or 0 for r in rows), default=0) if rows else 0
        runs = int((results.get("primary_result", {}) or {}).get("n_simulations") or n)
        based_on = (f"Based on all {n:,} simulated runs (the same runs as the success rate)"
                    if n >= runs else f"Based on {n:,} of the {runs:,} simulated runs")
        st.caption(
            "Each box is the spread of **annual spending across all simulated market paths** at that age: "
            "the box spans the middle 50% (25th–75th percentile), the whiskers reach the 10th–90th, and the "
            "line is the median. Spending is flat while you're working, then **fans out in retirement** as the "
            "**spending guardrails** raise or cut discretionary spending in response to how markets treated the "
            f"portfolio. {based_on} · guardrail-adjusted living spending "
            "(healthcare and long-term care are modeled separately and excluded here). "
            "The vertical axis is zoomed to the spending range, so it does not start at $0."
        )

    # Rendered directly (not in st.fragment) so is_dark()/style_fig() see the theme.
    _body()
