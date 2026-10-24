"""First-decade stress test — median vs 10th-percentile net-worth trajectory,
with the sequence-of-returns gap shaded and quantified for the first 10
retirement years.

An early retiree's fragility is dominated by a bad first decade (sequence risk).
This localizes the median-vs-downside gap to that danger window. Reads the same
``primary_result['networth_by_year']`` percentile rows the net-worth box chart
uses, so the two views stay consistent (total investable balance, excl. home
equity, today's dollars).
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.coerce import safe_int
    from utils.household import plan_end_ages
    from utils.formatting import money
    from utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int  # type: ignore
    from ui.utils.household import plan_end_ages  # type: ignore
    from ui.utils.formatting import money  # type: ignore
    from ui.utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark  # type: ignore


def compute_unlucky_summary(results: dict, retire_age: int, plan_until: int) -> dict | None:
    """Quantify WHY the 10th-percentile (unlucky) trajectory ends up lowest,
    from the same p10/p50 series the chart draws plus the median first-year
    withdrawal. Returns ``None`` when there isn't enough retirement-horizon
    data (< 2 rows at/after ``retire_age``). Shared by the chart's optional
    breakdown (below) and the decision narrative.
    """
    rows = (results.get("primary_result", {}) or {}).get("networth_by_year", []) or []
    ret_rows = [r for r in rows if int(r["age"]) >= retire_age]
    if len(ret_rows) < 2:
        return None

    ages = [int(r["age"]) for r in ret_rows]
    p10 = {int(r["age"]): float(r["p10"]) for r in ret_rows}
    p50 = {int(r["age"]): float(r["p50"]) for r in ret_rows}

    start = p10[ages[0]]
    trough_age = min(ages, key=lambda a: p10[a])
    trough = p10[trough_age]
    dep_thresh = max(1.0, 0.02 * start)
    depletion_age = next((a for a in ages if p10[a] <= dep_thresh), None)
    p10_5 = p10.get(retire_age + 5)
    p10_10 = p10.get(retire_age + 10)
    med_10 = p50.get(retire_age + 10)
    end_age = ages[-1]
    end_p10 = p10[end_age]

    wd = (results.get("primary_result", {}) or {}).get("withdrawals_by_year", []) or []
    first_draw = float(wd[0].get("total", 0.0)) if wd else 0.0
    draw_pct = (first_draw / start) if start > 0 else None
    early_drop_pct = ((start - p10_5) / start) if (p10_5 is not None and start > 0) else None

    return {
        "start": start, "trough_age": trough_age, "trough": trough,
        "depletion_age": depletion_age, "end_age": end_age, "end_p10": end_p10,
        "first_draw": first_draw, "draw_pct": draw_pct,
        "early_drop_pct": early_drop_pct, "p10_10": p10_10, "med_10": med_10,
    }


def render(st, results: dict = None, chart_key: str = "first_decade_stress") -> None:
    if not results:
        return
    rows = (results.get("primary_result", {}) or {}).get("networth_by_year", []) or []
    if not rows:
        return

    overrides = st.session_state.get("user_overrides", {}) or {}
    current_age = safe_int(overrides.get("YOUR_AGE", 25), 25)
    retire_age = safe_int(overrides.get("TARGET_RETIREMENT_AGE", 55), 55)
    plan_until = plan_end_ages(overrides)[0]  # when the plan ends (cfg.plan_end_age)

    by_age = {int(r["age"]): r for r in rows}
    # Retirement horizon only (the sequence-risk story starts at retirement).
    ret_rows = [r for r in rows if int(r["age"]) >= retire_age]
    if len(ret_rows) < 2:
        return

    ages = [int(r["age"]) for r in ret_rows]
    p50 = [float(r["p50"]) for r in ret_rows]
    p10 = [float(r["p10"]) for r in ret_rows]

    dark = is_dark(st)
    med_color = "#14b8a6" if dark else "#0d9488"
    low_color = "#f87171" if dark else "#dc2626"
    gap_fill = "rgba(248,113,113,0.16)" if dark else "rgba(220,38,38,0.12)"

    fig = go.Figure()
    # Median first, then p10 with fill='tonexty' so the wedge BETWEEN them shades.
    fig.add_trace(go.Scatter(
        x=ages, y=p50, mode="lines", line=dict(color=med_color, width=2.5),
        name="Median", hovertemplate="Age %{x}<br>median $%{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=ages, y=p10, mode="lines", line=dict(color=low_color, width=2, dash="dot"),
        fill="tonexty", fillcolor=gap_fill,
        name="10th pct (unlucky)",
        hovertemplate="Age %{x}<br>10th pct $%{y:,.0f}<extra></extra>",
    ))
    # Retirement + end-of-first-decade markers.
    if current_age <= retire_age <= plan_until:
        fig.add_vline(x=retire_age, line_dash="dash", line_color="#94a3b8",
                      annotation_text=f"Retire (age {retire_age})",
                      annotation_position="top left", annotation_font=dict(size=10, color="#64748b"))
    decade_age = retire_age + 10
    if decade_age <= plan_until:
        fig.add_vline(x=decade_age, line_dash="dot", line_color="#94a3b8",
                      annotation_text="+10 yrs", annotation_position="top right",
                      annotation_font=dict(size=10, color="#64748b"))

    fig.update_layout(
        title=dict(
            # Long subtitle: style_fig wraps title lines at a safe width (Plotly
            # never wraps titles; one long span used to clip mid-word).
            text="<b>First-decade stress: median vs unlucky path</b><br>"
                 "<span style='font-size:13px;color:#64748b;'>The shaded wedge is your "
                 "sequence-of-returns risk — "
                 "how far a bad early market pulls you below the median "
                 "(today's dollars)</span>",
            x=0.0, xanchor="left", font=dict(size=16),
        ),
        height=400, margin=dict(l=50, r=40, t=100, b=50),
        xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False, tickfont=dict(color="#64748b")),
        yaxis=dict(title="Investable net worth ($, today)", gridcolor="#f1f5f9", zeroline=False,
                   rangemode="tozero", tickformat="$,.3~s", tickfont=dict(color="#64748b")),
        showlegend=True,
        dragmode="pan", uirevision="keep",
    )
    show_chart(st, fig, f"{chart_key}_{'dk' if dark else 'lt'}", PLOTLY_CONFIG)

    # Divergence table for the first-decade milestones.
    import pandas as pd
    table = []
    for yr in (5, 10):
        row = by_age.get(retire_age + yr)
        if not row:
            continue
        med = float(row["p50"]); low = float(row["p10"])
        gap = med - low
        gap_pct = (gap / med) if med > 0 else None
        table.append({
            # All-text columns: a numeric int column right-aligns while the
            # money strings left-align, which mixed alignment across the table.
            "Retirement year": f"Year {yr}",
            "Age": str(retire_age + yr),
            "Median": money(med, shorten=True),
            "Unlucky (P10)": money(low, shorten=True),
            "Gap": money(gap, shorten=True),
            "Gap %": f"{gap_pct:.0%}" if gap_pct is not None else "—",
        })
    if table:
        st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)
    st.caption(
        "Solid line is a typical market; dotted line is a poor-luck (10th-percentile) path. "
        "The gap widens fastest in the **first decade**, when a bad return sequence does the "
        "most damage. A wide early gap argues for a cash/bond buffer, more guardrail "
        "flexibility, or one more year of work; a narrow one means your plan handles a rough "
        "start. Depleted paths count as $0, so the 10th percentile can fall to zero."
    )

    # ---- Optional: why is the unlucky path the low performer? ----
    if st.toggle("Analyze the unlucky path", key=f"{chart_key}_why",
                 help="Break down the circumstances behind the 10th-percentile outcome — "
                      "the sequence-of-returns story."):
        _render_unlucky_analysis(st, retire_age, plan_until, results)


def _render_unlucky_analysis(st, retire_age: int, plan_until: int, results: dict) -> None:
    """Explain WHY the 10th-percentile (unlucky) trajectory ends up lowest,
    quantified from the same p10/p50 series the chart draws plus the median
    first-year withdrawal."""
    summary = compute_unlucky_summary(results, retire_age, plan_until)
    if summary is None:
        return
    start = summary["start"]
    trough_age = summary["trough_age"]
    depletion_age = summary["depletion_age"]
    end_age = summary["end_age"]
    end_p10 = summary["end_p10"]
    first_draw = summary["first_draw"]
    draw_pct = summary["draw_pct"]
    early_drop_pct = summary["early_drop_pct"]
    p10_10 = summary["p10_10"]
    med_10 = summary["med_10"]

    cols = st.columns(3)
    with cols[0]:
        st.metric("Unlucky at retirement", money(start, shorten=True),
                  help="10th-percentile investable balance in year 1 of retirement.")
    with cols[1]:
        if depletion_age is not None:
            st.metric("Runs dry by", f"age {depletion_age}",
                      help="First age the unlucky path is effectively exhausted (≤2% of its start).")
        else:
            st.metric("Unlucky ending", money(end_p10, shorten=True),
                      help=f"10th-percentile balance at the plan-end age ({end_age}).")
    with cols[2]:
        st.metric("First-year draw", f"{draw_pct:.1%}" if draw_pct else "—",
                  help="Median year-1 withdrawal ÷ the unlucky path's starting balance — the "
                       "spending pressure a weak early market has to absorb.")

    # Prose: tailor to whether the unlucky path depletes or merely lags.
    parts = []
    if early_drop_pct is not None and early_drop_pct > 0.02:
        parts.append(
            f"The damage is **front-loaded**: the unlucky path falls about **{early_drop_pct:.0%}** "
            f"in the first five retirement years"
        )
    else:
        parts.append(
            "The unlucky path is held back by a **weak early market** — flat-to-negative returns "
            "in the first retirement years"
        )
    if draw_pct is not None:
        parts.append(
            f" while you keep withdrawing ~**{money(first_draw, shorten=True)}/yr** (≈{draw_pct:.1%} of the "
            f"balance). Selling assets *after* they've dropped — **sequence-of-returns risk** — locks in "
            f"the loss, so each later year compounds off a smaller base."
        )
    else:
        parts.append(
            ". Withdrawing through that early dip — **sequence-of-returns risk** — sells assets while "
            "they're down, so the portfolio compounds off a smaller base."
        )
    if depletion_age is not None:
        parts.append(
            f" It never recovers: the balance bottoms out around age **{trough_age}** and is exhausted by "
            f"age **{depletion_age}**."
        )
    elif med_10 is not None and p10_10 is not None and med_10 > 0:
        gap10 = (med_10 - p10_10) / med_10
        parts.append(
            f" It survives, but by the end of the first decade the unlucky path sits about "
            f"**{gap10:.0%} below the median** — that persistent gap is the sequence-risk drag."
        )
    parts.append(
        " The fix for a fragile early decade: hold a **cash/bond buffer** to avoid selling stocks in a "
        "downturn, lean on **spending guardrails**, or **work one more year** to shrink the draw rate."
    )
    st.markdown("".join(parts))

