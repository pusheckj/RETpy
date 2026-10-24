"""Mortgage-paydown effectiveness tab.

Answers "is putting extra money against the mortgage worth it?" by sweeping the
extra annual principal and reporting what each level buys: success rate,
the age the house is owned outright, years shaved off the loan, and lifetime
interest avoided.

Why the sweep is a fair test rather than a rigged one (see
``cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL``): the extra payment is charged as real
cash, so it genuinely competes with investing the same dollars; the loan
amortises faster; and once the balance hits zero the scheduled payment STOPS,
which is the entire benefit of prepaying. Without that last piece prepayment
would look like pure cost and the answer would always be "no".

Payoff age / interest are DETERMINISTIC (amortisation doesn't depend on market
returns), so they're computed in closed form rather than sampled -- they carry
no Monte Carlo error at all. Only the success column does, and its noise floor
is shown explicitly so a difference inside the error bars isn't read as signal.

No Run button by design: warmed centrally with the rest of the page.
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.formatting import money, pct
    from utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark
except ImportError:  # pragma: no cover
    from ui.utils.formatting import money, pct  # type: ignore
    from ui.utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark  # type: ignore

STATE_KEY = "mortgage_paydown_result"


def render(st, results: dict = None, chart_key: str = "mortgage_paydown") -> None:
    res = st.session_state.get(STATE_KEY)
    if not res or not res.get("curve"):
        st.caption(
            "The mortgage-paydown sweep runs with the rest of the page. "
            "If it hasn't finished yet, give it a moment or press Run."
        )
        return

    curve = res["curve"]
    noise = float(res.get("noise_floor_pp", 0.0))
    base = next((c for c in curve if c["extra"] == 0.0), curve[0])

    # ---- Verdict ----------------------------------------------------------
    best = max(curve, key=lambda c: c["success_rate"])
    sig = [c for c in curve if c.get("significant") and c["delta_success"] > 0]
    cheapest_sig = min(sig, key=lambda c: c["extra"]) if sig else None

    if not res.get("helps_significantly"):
        st.info(
            f"**Prepaying doesn't clearly help this plan.** No extra-payment level "
            f"beat the baseline by more than the ±{noise:.1f}pp noise floor at "
            f"{res.get('n_simulations', 0):,} simulations. The dollars do just as "
            f"much good invested."
        )
    else:
        st.success(
            f"**Prepaying helps.** {money(best['extra'])}/yr extra raises success "
            f"from {pct(base['success_rate'])} to {pct(best['success_rate'])} "
            f"(**{best['delta_success'] * 100:+.1f}pp**) and owns the house outright "
            f"at **{best['payoff_age']}** instead of {base['payoff_age']} — "
            f"{best.get('years_saved') or 0} years earlier, avoiding "
            f"{money((base.get('total_interest') or 0) - (best.get('total_interest') or 0))} "
            f"of interest."
        )
        if cheapest_sig is not None and cheapest_sig["extra"] != best["extra"]:
            st.caption(
                f"Smallest amount that still clears the noise floor: "
                f"**{money(cheapest_sig['extra'])}/yr** "
                f"({cheapest_sig['delta_success'] * 100:+.1f}pp)."
            )

    # ---- Chart: success vs extra payment, with the noise band -------------
    dark = is_dark(st)
    xs = [c["extra"] for c in curve]
    ys = [c["success_rate"] * 100 for c in curve]
    b = base["success_rate"] * 100

    fig = go.Figure()
    # Shade the "indistinguishable from baseline" band so the eye doesn't read
    # every wiggle as a real effect.
    fig.add_hrect(y0=b - noise, y1=b + noise,
                  fillcolor="rgba(148,163,184,0.18)", line_width=0,
                  annotation_text="same as baseline (within noise)",
                  annotation_position="top left",
                  annotation_font=dict(size=10, color="#64748b"))
    fig.add_hline(y=b, line_dash="dash", line_color="#94a3b8")
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines+markers",
        line=dict(color="#0d9488" if not dark else "#14b8a6", width=2.5),
        marker=dict(size=9),
        customdata=[[c.get("payoff_age"), c.get("years_saved") or 0] for c in curve],
        hovertemplate=("Extra $%{x:,.0f}/yr<br>success %{y:.1f}%"
                       "<br>paid off at age %{customdata[0]}"
                       "<br>%{customdata[1]} yrs earlier<extra></extra>"),
        name="Success rate",
    ))
    fig.update_layout(
        title=dict(
            text="<b>Does prepaying the mortgage improve the plan?</b><br>"
                 "<span style='font-size:13px;color:#64748b;'>Success rate vs "
                 "extra principal per year · today's dollars</span>",
            x=0.0, xanchor="left", font=dict(size=16),
        ),
        height=380, margin=dict(l=55, r=30, t=86, b=55),
        xaxis=dict(title="Extra principal ($/yr)", gridcolor="#f1f5f9",
                   zeroline=False, tickformat="$,.0f"),
        yaxis=dict(title="Success rate (%)", gridcolor="#f1f5f9", zeroline=False),
        showlegend=False, dragmode="pan", uirevision="keep",
    )
    show_chart(st, fig, f"{chart_key}_{'dk' if dark else 'lt'}", PLOTLY_CONFIG)

    # ---- Table -----------------------------------------------------------
    import pandas as pd
    rows = []
    for c in curve:
        d = c["delta_success"] * 100
        rows.append({
            "Extra / yr": money(c["extra"]),
            "Success": pct(c["success_rate"]),
            "vs baseline": "—" if c["extra"] == 0 else (
                f"{d:+.1f}pp" + ("" if c.get("significant") else " (noise)")
            ),
            "Owned outright at": c.get("payoff_age") or "—",
            "Years earlier": c.get("years_saved") or "—",
            "Lifetime interest": money(c.get("total_interest") or 0),
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.caption(
        f"Success is a Monte Carlo estimate at {res.get('n_simulations', 0):,} runs, "
        f"so differences under ±{noise:.1f}pp are not meaningful — those are marked "
        "*(noise)*. Payoff age and interest are exact: amortisation doesn't depend "
        "on market returns. The extra payment is charged as real cash, so this is a "
        "genuine contest between prepaying and investing the same dollars, and the "
        "scheduled payment correctly stops once the loan is gone."
    )
