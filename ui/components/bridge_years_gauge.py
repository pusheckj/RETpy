"""Bridge-years funding gauge — can you fund retirement to 59½ without penalties?

For the "gap years" between retirement and 59½, stacks the MEDIAN penalty-free
(accessible) balance — cash + taxable brokerage + Roth — as bridge fuel, overlays
the median annual portfolio withdrawal, and gives a verdict plus the first year
(if any) the median path is forced into penalized (traditional/HSA) withdrawals.

Reads ``primary_result['accessible_by_year']`` (per-year median accessible balance
by source, surfaced from the engine's per-account yearly balances) and
``withdrawals_by_year`` (annual draw + source). NOTE: Roth is the full Roth
balance as a proxy for contribution basis (the engine doesn't track basis), so
accessible Roth is slightly overstated by any unrealized growth.
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.coerce import safe_int
    from utils.formatting import money
    from utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark, series_color, concept_color
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int  # type: ignore
    from ui.utils.formatting import money  # type: ignore
    from ui.utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark, series_color, concept_color  # type: ignore

_EARLY_AGE = 59.5


def compute_verdict(results: dict, retire_age: int) -> dict | None:
    """Whether the MEDIAN plan reaches 59½ with penalty-free fuel covering
    each year's withdrawal. Returns ``None`` when there's nothing to verdict:
    retiring at/after 59.5 (no bridge to fund) or no accessible-balance rows
    (older cached result). Shared by the chart (below) and the decision
    narrative, so the two can never disagree.
    """
    if retire_age >= _EARLY_AGE:
        return None
    pr = results.get("primary_result", {}) or {}
    access = pr.get("accessible_by_year", []) or []
    if not access:
        return None

    first_short = None
    for r in access:
        a = int(r["age"])
        acc_v = float(r["accessible"]); burn_v = float(r.get("burn", 0.0))
        if float(r.get("penalty", 0.0)) > 1.0 or (burn_v > 0 and acc_v < burn_v):
            first_short = a
            break
    return {
        "funded": first_short is None,
        "first_short": first_short,
        "accessible_at_retire": float(access[0]["accessible"]) if access else 0.0,
    }


def render(st, results: dict = None, chart_key: str = "bridge_gauge") -> None:
    if not results:
        return
    pr = results.get("primary_result", {}) or {}
    access = pr.get("accessible_by_year", []) or []
    overrides = st.session_state.get("user_overrides", {}) or {}
    retire_age = safe_int(overrides.get("TARGET_RETIREMENT_AGE", 55), 55)

    st.markdown('<div class="mc-section">Bridge to 59½</div>', unsafe_allow_html=True)

    # These two conditions are UNRELATED and must not share one message: `not
    # access` just means the run carried no accessible-balance rows (an older
    # cached result), and telling a 45-year-old their money is penalty-free from
    # day one is the exact opposite of their situation.
    if retire_age >= _EARLY_AGE:
        st.caption(
            "You retire at or after 59½, so every account is penalty-free from day one. "
            "There's no bridge to fund."
        )
        return
    if not access:
        st.caption(
            "Bridge data isn't available for this run. Run the simulation again to see how "
            "the years before 59½ are funded."
        )
        return

    ages = [int(r["age"]) for r in access]
    cash = [float(r["cash"]) for r in access]
    taxable = [float(r["taxable"]) for r in access]
    roth = [float(r["roth"]) for r in access]
    burn = [float(r.get("burn", 0.0)) for r in access]

    verdict = compute_verdict(results, retire_age)
    funded = verdict["funded"]
    first_short = verdict["first_short"]
    accessible_at_retire = verdict["accessible_at_retire"]

    # ---- Verdict tiles ----
    cols = st.columns(3)
    with cols[0]:
        st.metric("Bridge to 59½", "Funded ✓" if funded else "Shortfall",
                  help="Whether the median plan reaches 59½ with penalty-free money covering "
                       "each year's withdrawal. Uses the same median as the chart.")
    with cols[1]:
        st.metric("First shortfall",
                  "None" if funded else f"age {first_short}",
                  help="First year before 59½ that the median plan pays an early-withdrawal penalty "
                       "or runs out of penalty-free money.")
    with cols[2]:
        st.metric("Penalty-free money at retirement", money(accessible_at_retire, shorten=True),
                  help="Median cash + taxable brokerage + Roth balance in your first retirement year.")

    dark = is_dark(st)
    ref_line = "#e2e8f0" if dark else "#0f172a"
    fig = go.Figure()
    # Stacked accessible "fuel" (bottom -> top): cash, taxable, Roth.
    for label, series, color in [
        # Shared concept colors: the same account is the same color in every chart.
        ("Cash", cash, concept_color("Cash", st)),
        ("Taxable brokerage", taxable, concept_color("Taxable brokerage", st)),
        ("Roth (basis, approx.)", roth, concept_color("Roth IRA", st)),
    ]:
        fig.add_trace(go.Scatter(
            x=ages, y=series, mode="lines", line=dict(width=0.5, color=color),
            stackgroup="fuel", name=label, fillcolor=color,
            hovertemplate=f"{label}<br>age %{{x}}: $%{{y:,.0f}}<extra></extra>",
        ))
    # Annual portfolio draw (burn) as an overlaid line.
    fig.add_trace(go.Scatter(
        x=ages, y=burn, mode="lines+markers", line=dict(color=ref_line, width=2.5, dash="dot"),
        marker=dict(size=5), name="Annual withdrawal",
        hovertemplate="age %{x}<br>annual draw $%{y:,.0f}<extra></extra>",
    ))
    fig.add_vline(x=_EARLY_AGE, line_dash="dash", line_color="#94a3b8",
                  annotation_text="59½ · penalties end", annotation_position="top right",
                  annotation_font=dict(size=10, color="#64748b"))
    if not funded:
        fig.add_vline(x=first_short, line_dash="dot", line_color="#dc2626",
                      annotation_text=f"shortfall · age {first_short}",
                      annotation_position="bottom left", annotation_font=dict(size=10, color="#dc2626"))

    fig.update_layout(
        title=dict(
            text="<b>Penalty-free money vs. annual withdrawal</b><br>"
                 "<span style='font-size:13px;color:#64748b;'>Median accessible balance "
                 "(cash + taxable + Roth) until 59½ · today's dollars</span>",
            x=0.0, xanchor="left", font=dict(size=16),
        ),
        height=380, margin=dict(l=50, r=40, t=84, b=50),
        xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False, tickfont=dict(color="#64748b")),
        yaxis=dict(title="Balance / annual draw ($, today)", gridcolor="#f1f5f9", zeroline=False,
                   rangemode="tozero", tickformat="$,.3~s", tickfont=dict(color="#64748b")),
        showlegend=True,
        dragmode="pan", uirevision="keep",
    )
    show_chart(st, fig, f"{chart_key}_{'dk' if dark else 'lt'}", PLOTLY_CONFIG)
    st.caption(
        "The stacked area is your **penalty-free money**: cash, taxable brokerage, and Roth. "
        "You can use these before 59½ without a 10% penalty. The dotted line is the median annual "
        "withdrawal. The bridge is funded as long as that balance stays above the withdrawal line. "
        "If it doesn't, save more in taxable or Roth accounts before you retire. "
        "Roth counts at its full balance, which stands in for what you've put in, so accessible "
        "Roth is slightly overstated."
    )
