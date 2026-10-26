"""Life-expectancy section — an actuarial age-at-death DISTRIBUTION based on the
user's personal risk factors, and how it compares to the plan's horizon.

Pure actuarial math (utils.mortality) — instant, so it updates live as the user
changes risk factors (no Run button). Independent of the Monte Carlo, so it
renders before/without a simulation.
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.coerce import safe_int
    from utils.formatting import metric_row
    from utils.household import plan_end_ages
    from utils.mortality import life_distribution, RISK_FACTORS, CONDITIONS
    from utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int  # type: ignore
    from ui.utils.formatting import metric_row  # type: ignore
    from ui.utils.household import plan_end_ages  # type: ignore
    from ui.utils.mortality import life_distribution, RISK_FACTORS, CONDITIONS  # type: ignore
    from ui.utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark  # type: ignore


def render(st) -> None:
    st.markdown('<div class="mc-section">Your life expectancy</div>', unsafe_allow_html=True)
    overrides = st.session_state.get("user_overrides", {}) or {}
    st.caption(
        "A range of likely lifespans, adjusted for your own risk factors (not your "
        "partner's). It sets how long your money needs to last. Plan for a high percentile, "
        "not the average. This is an educational estimate (Gompertz mortality with "
        "relative-risk multipliers from public studies), **not medical advice**."
    )

    # ---- Inputs ----
    top = st.columns([1, 1])
    with top[0]:
        sex = st.selectbox("Sex at birth", ["Male", "Female"], key="le_sex",
                           help="Baseline mortality differs by sex. This sets the starting curve.")
    with top[1]:
        default_age = safe_int(overrides.get("YOUR_AGE", 40), 40)
        st.session_state.setdefault("le_age", default_age)
        current_age = st.number_input("Your current age", min_value=18, max_value=100, step=1,
                                      key="le_age", help="Life expectancy is worked out assuming "
                                      "you are alive at this age.")

    keys = list(RISK_FACTORS.keys())
    fcols = st.columns(3)
    selections = {}
    for i, key in enumerate(keys):
        spec = RISK_FACTORS[key]
        opts = list(spec["options"].keys())
        wkey = f"le_{key}"
        st.session_state.setdefault(wkey, spec["default"])
        with fcols[i % 3]:
            selections[key] = st.selectbox(spec["label"], opts, key=wkey, help=spec.get("help"))

    conditions = st.multiselect(
        "Diagnosed conditions", list(CONDITIONS.keys()), key="le_conditions",
        help="Each condition you pick raises your risk of dying earlier. Leave empty if none apply.",
    )

    # ---- Compute (instant) ----
    dist = life_distribution(int(current_age), sex, selections, conditions)
    # Your age when the plan ends -- the horizon every screen shows
    # (cfg.plan_end_age: with a younger partner it runs past your own plan-until age).
    plan_until = plan_end_ages(overrides)[0]
    reach_plan = float(dist["reach_fn"].get(plan_until, 0.0)) if plan_until > current_age else 1.0

    # ---- Headline metrics ----
    metric_row(st, [
        ("Median lifespan", f"{dist['median']}",
         dict(help="Half of people with your profile live past this age.")),
        ("Life expectancy", f"{dist['mean']:.0f}",
         dict(help="The average age at death.")),
        ("1-in-10 reach", f"{dist['p90']}",
         dict(help="The age 1 in 10 people with your profile live past. A "
                   "sensible planning horizon.")),
        ("Outlive your plan", f"{reach_plan:.0%}",
         dict(delta="risk" if reach_plan >= 0.25 else "low",
              delta_color=("inverse" if reach_plan >= 0.25 else "normal"),
              delta_arrow=("up" if reach_plan >= 0.25 else "down"),
              help=f"Chance you're still alive when the plan ends (you're {plan_until}). "
                   "If it's high, your plan could end while you're still spending.")),
    ])

    # ---- Distribution plot ----
    dark = is_dark(st)
    fill = "rgba(45,212,191,0.28)" if dark else "rgba(13,148,136,0.20)"
    line = "#2dd4bf" if dark else "#0d9488"
    ages = dist["ages"]
    pdf = dist["death_pdf"]
    # Trim the long thin tail for readability (show through ~105 or last age with mass).
    hi = max([a for a, d in zip(ages, pdf) if d >= 0.001] + [current_age + 1])
    hi = min(max(hi + 2, 100), ages[-1])
    xa = [a for a in ages if a <= hi]
    ya = [pdf[i] * 100 for i, a in enumerate(ages) if a <= hi]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xa, y=ya, mode="lines", fill="tozeroy", line=dict(color=line, width=2), fillcolor=fill,
        name="Age at death", hovertemplate="Age %{x}<br>%{y:.2f}% of outcomes<extra></extra>",
    ))
    fig.add_vline(x=dist["median"], line_dash="dash", line_color=line,
                  annotation_text=f"median {dist['median']}", annotation_position="top left",
                  annotation_font=dict(size=11, color=line))
    fig.add_vline(x=dist["p90"], line_dash="dot", line_color="#d97706" if not dark else "#fbbf24",
                  annotation_text=f"1-in-10 reach {dist['p90']}", annotation_position="top right",
                  annotation_font=dict(size=10, color="#d97706" if not dark else "#fbbf24"),
                  # Opaque chip: the "plan ends" line sits just right of this
                  # label and used to strike through the text.
                  annotation_bgcolor=("rgba(15,23,42,0.92)" if dark else "rgba(255,255,255,0.92)"))
    if current_age < plan_until <= hi:
        fig.add_vline(x=plan_until, line_dash="dash", line_color="#64748b",
                      annotation_text=f"plan ends {plan_until}",
                      # Label on the side AWAY from the nearby 1-in-10 line, which
                      # otherwise strikes through it.
                      annotation_position=("bottom left" if plan_until < dist["p90"] else "bottom right"),
                      annotation_font=dict(size=10, color="#64748b"))
    fig.update_layout(
        title=dict(
            text="<b>Your projected age at death</b><br><span style='font-size:13px;color:#64748b;'>"
                 "How likely each age at death is, given your risk factors</span>",
            x=0.0, xanchor="left", font=dict(size=16),
        ),
        height=360, margin=dict(l=50, r=40, t=80, b=50),
        xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False, tickfont=dict(color="#64748b")),
        yaxis=dict(title="% of outcomes", gridcolor="#f1f5f9", zeroline=False, rangemode="tozero",
                   tickfont=dict(color="#64748b")),
        showlegend=False, dragmode="pan", uirevision="keep",
    )
    def _build(compact):
        f = go.Figure(fig)
        if compact:  # "plan ends" sat past the right edge of a phone-width plot
            for a in f.layout.annotations:
                if str(a.text).startswith("plan ends"):
                    a.update(xanchor="right")
        return f

    show_chart(st, _build, f"life_dist_{'dk' if dark else 'lt'}", PLOTLY_CONFIG)

    # ---- Plan tie-in ----
    reach90 = dist["reach"][90]
    lead = (f"There's a **{reach_plan:.0%}** chance you're still alive when the plan ends "
            f"(you're **{plan_until}**). ") if plan_until > current_age else ""
    if plan_until > current_age and reach_plan >= 0.25:
        lead += (f"That's a real risk of outliving your plan. Consider extending it toward your "
                 f"1-in-10 age (**{dist['p90']}**) so the money lasts as long as you do.")
    elif plan_until > current_age and plan_until >= dist["p90"]:
        lead += "Your plan already covers a long life, which gives you a good buffer."
    else:
        lead += f"About **{reach90:.0%}** of people with your profile reach age 90."
    st.markdown(lead)
    st.caption(
        "The shaded curve shows the chance of dying at each age. Living *longer* than planned is "
        "what drains a portfolio, so retirement plans usually fund to around the 90th-percentile "
        "age, not the average. "
        f"Your profile's risk multiplier is **{dist['hazard_ratio']:.2f}×** the reference."
    )
