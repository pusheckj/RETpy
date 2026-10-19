"""What-if: two "when can you retire?" curves — baseline vs. an alternate
scenario whose parameters are tweaked HERE (locally), without touching the
sidebar / main run.

The baseline curve is the household's current inputs; the alternate re-runs the
age-scan with a handful of high-impact levers (returns, allocation, fees,
inflation, Social Security, retirement spending) overlaid on top of the base
overrides. Both success-vs-age curves are drawn on one chart so you can see how
the changes move your earliest retirement age.

Behind a button because each curve is a full age-scan (many simulations).
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.sim_runner import run_full_analysis, _hashable
    from utils.plot_theme import style_fig, PLOTLY_CONFIG, is_dark
    from utils.coerce import safe_int, safe_float
except ImportError:  # pragma: no cover
    from ui.utils.sim_runner import run_full_analysis, _hashable  # type: ignore
    from ui.utils.plot_theme import style_fig, PLOTLY_CONFIG, is_dark  # type: ignore
    from ui.utils.coerce import safe_int, safe_float  # type: ignore

_SCENARIOS = ["conservative", "historical", "pessimistic"]
_SCAN_RANGE = (25, 76, 1)


def _base_default(overrides: dict, key: str, cfg_default):
    """Baseline value for a lever: the user's override if set, else the config default."""
    if key in overrides and overrides[key] is not None:
        return overrides[key]
    try:
        from retirement_sim import config as cfg
        return getattr(cfg, key, cfg_default)
    except Exception:
        return cfg_default


def _alt_overrides(st, base: dict) -> dict:
    """Read the what-if controls and layer them on top of the base overrides."""
    scen = str(st.session_state.get("wifc_scenario", "historical"))
    alloc = safe_float(st.session_state.get("wifc_stock", 80.0), 80.0) / 100.0
    fee_bps = safe_float(st.session_state.get("wifc_fee", 0.0), 0.0)
    infl = safe_float(st.session_state.get("wifc_infl", 2.75), 2.75) / 100.0
    include_ss = bool(st.session_state.get("wifc_ss", True))
    ss_claim = safe_int(st.session_state.get("wifc_ss_claim", 67), 67)
    spend_pct = safe_float(st.session_state.get("wifc_spend", 100.0), 100.0) / 100.0
    extra_savings = safe_int(st.session_state.get("wifc_savings", 0), 0)

    alt = dict(base)
    alt["ACTIVE_RETURN_SCENARIO"] = scen
    alt["STOCK_ALLOCATION"] = alloc
    alt["INVESTMENT_FEE_RATE"] = fee_bps / 10_000.0
    alt["EXPECTED_INFLATION"] = infl
    alt["INCLUDE_SOCIAL_SECURITY"] = include_ss
    if include_ss:
        alt["SS_CLAIM_AGE"] = ss_claim
    # Retirement spending as a % of today's expenses (100% = same as today).
    if abs(spend_pct - 1.0) > 1e-6:
        alt["RETIREMENT_SPENDING_MODE"] = "% of today's expenses"
        alt["RETIREMENT_SPENDING_PCT"] = spend_pct
    # Extra annual savings routed to the taxable brokerage on top of the plan.
    if extra_savings:
        cur_brk = safe_int(base.get("YOUR_BROKERAGE_CONTRIBUTION", 0), 0)
        alt["YOUR_BROKERAGE_CONTRIBUTION"] = cur_brk + extra_savings
    return alt


def _inputs_hash(alt: dict, n_sims):
    try:
        return hash((_hashable(alt), int(n_sims)))
    except Exception:
        return None


def _curve_earliest(by_age: dict, target: float):
    """Earliest age whose success rate clears the target."""
    for age in sorted(by_age):
        if by_age[age] >= target:
            return age
    return None


def render(st, results: dict = None) -> None:
    st.markdown('<div class="mc-section">What-if: when can you retire?</div>', unsafe_allow_html=True)
    overrides = st.session_state.get("user_overrides", {}) or {}
    st.caption(
        "Compare your **current plan** against an **alternate scenario** you tweak right here. "
        "The changes below apply only to this comparison — your sidebar inputs and the main "
        "results are untouched. Each line shows your success probability at every retirement age."
    )

    # ---- Alternate-scenario controls (default to your current settings) ----
    base_scen = str(_base_default(overrides, "ACTIVE_RETURN_SCENARIO", "historical")).lower()
    if base_scen not in _SCENARIOS:
        base_scen = "historical"
    st.session_state.setdefault("wifc_scenario", base_scen)
    st.session_state.setdefault("wifc_stock", float(_base_default(overrides, "STOCK_ALLOCATION", 0.80)) * 100)
    st.session_state.setdefault("wifc_fee", float(_base_default(overrides, "INVESTMENT_FEE_RATE", 0.0)) * 10_000)
    st.session_state.setdefault("wifc_infl", float(_base_default(overrides, "EXPECTED_INFLATION", 0.0275)) * 100)
    st.session_state.setdefault("wifc_ss", bool(_base_default(overrides, "INCLUDE_SOCIAL_SECURITY", True)))
    st.session_state.setdefault("wifc_ss_claim", int(_base_default(overrides, "SS_CLAIM_AGE", 67)))
    st.session_state.setdefault("wifc_spend", 100.0)
    st.session_state.setdefault("wifc_savings", 0)

    c1, c2 = st.columns(2)
    with c1:
        st.selectbox("Return scenario", _SCENARIOS, key="wifc_scenario",
                     format_func=lambda s: s.capitalize(),
                     help="Market assumptions for the alternate scenario.")
        st.slider("Stock allocation (%)", 0, 100, key="wifc_stock", step=5,
                  help="Higher stock = higher expected return and volatility.")
        st.slider("Retirement spending (% of today's)", 40, 150, key="wifc_spend", step=5,
                  help="Scale retirement living expenses vs. today. 100% = unchanged.")
        st.number_input("Extra annual savings ($/yr)", min_value=0, max_value=200_000,
                        step=1_000, key="wifc_savings",
                        help="Additional yearly savings into your taxable brokerage.")
    with c2:
        st.slider("Investment fees (bps)", 0, 150, key="wifc_fee", step=5,
                  help="Annual expense ratio in basis points (100 bps = 1%).")
        st.slider("Expected inflation (%)", 0.0, 6.0, key="wifc_infl", step=0.25,
                  help="Long-run inflation assumption for the alternate scenario.")
        st.toggle("Include Social Security", key="wifc_ss",
                  help="Whether the alternate scenario counts Social Security income.")
        if st.session_state.get("wifc_ss", True):
            st.slider("SS claim age", 62, 70, key="wifc_ss_claim", step=1,
                      help="Age Social Security benefits begin in the alternate scenario.")

    n_sims = int(st.session_state.get("n_simulations", 1000))
    target = int(overrides.get("TARGET_RETIREMENT_AGE", 55))
    alt = _alt_overrides(st, overrides)
    cur_hash = _inputs_hash(alt, n_sims)
    stored = st.session_state.get("wifc_result")
    fresh = bool(stored) and stored.get("_hash") is not None and cur_hash is not None and stored.get("_hash") == cur_hash

    if st.button("✓ Comparison up to date" if fresh else "Compare scenarios",
                 key="wifc_btn", type="primary", disabled=fresh,
                 help="Re-runs both age-scans. Change a lever above to re-enable." if fresh else None):
        prog = st.progress(0.0, text="Running both scenarios…")

        def _cb(frac, msg):
            try:
                prog.progress(min(1.0, max(0.0, float(frac))), text=str(msg))
            except Exception:
                pass

        # Baseline: current inputs (cached from the main run when unchanged).
        base_res = run_full_analysis(user_overrides=overrides, n_simulations=n_sims,
                                     target_retirement_age=target, scan_age_range=_SCAN_RANGE,
                                     progress_callback=lambda f, m: _cb(f * 0.5, m))
        alt_res = run_full_analysis(user_overrides=alt, n_simulations=n_sims,
                                    target_retirement_age=target, scan_age_range=_SCAN_RANGE,
                                    progress_callback=lambda f, m: _cb(0.5 + f * 0.5, m))
        st.session_state["wifc_result"] = {
            "_hash": cur_hash,
            "base": base_res.get("success_rate_by_age", {}) or {},
            "alt": alt_res.get("success_rate_by_age", {}) or {},
            "target_success": float((base_res.get("config_snapshot", {}) or {}).get("TARGET_SUCCESS_RATE", 0.80)),
        }
        prog.empty()
        # NOTE: no st.rerun() here — this section lives inside the What-if
        # expander, which would collapse on a rerun and hide the result. Render
        # it inline instead (the button relabels to "up to date" on the next
        # natural rerun).

    stored = st.session_state.get("wifc_result")
    if not stored:
        st.caption("Set the alternate scenario above, then click **Compare scenarios**.")
        return

    _render_plot(st, stored)


def _render_plot(st, stored: dict) -> None:
    base = stored.get("base", {}) or {}
    alt = stored.get("alt", {}) or {}
    tgt = float(stored.get("target_success", 0.80))
    if not base and not alt:
        st.info("No age-scan data to compare.")
        return

    dark = is_dark(st)
    base_col = "#0d9488" if not dark else "#2dd4bf"   # teal — current plan
    alt_col = "#d97706" if not dark else "#fbbf24"    # amber — alternate
    ref = "#e2e8f0" if dark else "#94a3b8"

    base_ages = sorted(base)
    alt_ages = sorted(alt)
    base_e = _curve_earliest(base, tgt)
    alt_e = _curve_earliest(alt, tgt)

    # ---- headline verdict ----
    cols = st.columns(3)
    with cols[0]:
        st.metric("Current plan — retire by", f"age {base_e}" if base_e else "beyond range",
                  help=f"Earliest age clearing the {tgt:.0%} success target on your current inputs.")
    with cols[1]:
        st.metric("Alternate — retire by", f"age {alt_e}" if alt_e else "beyond range",
                  help="Earliest age clearing the target under the tweaked scenario.")
    with cols[2]:
        if base_e is not None and alt_e is not None:
            d = base_e - alt_e
            st.metric("Difference", f"{abs(d)} yr {'earlier' if d > 0 else ('later' if d < 0 else 'same')}",
                      delta=("earlier" if d > 0 else ("later" if d < 0 else None)),
                      delta_color=("normal" if d > 0 else ("inverse" if d < 0 else "off")),
                      help="How much sooner (or later) the alternate scenario lets you retire.")
        else:
            st.metric("Difference", "—")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=base_ages, y=[base[a] * 100 for a in base_ages], mode="lines+markers",
        name="Current plan", line=dict(color=base_col, width=2.5), marker=dict(size=5, color=base_col),
        hovertemplate="Current · retire %{x}<br>success %{y:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=alt_ages, y=[alt[a] * 100 for a in alt_ages], mode="lines+markers",
        name="Alternate", line=dict(color=alt_col, width=2.5, dash="dot"), marker=dict(size=5, color=alt_col),
        hovertemplate="Alternate · retire %{x}<br>success %{y:.1f}%<extra></extra>",
    ))
    fig.add_hline(y=tgt * 100, line_dash="dash", line_color=ref,
                  annotation_text=f"{tgt:.0%} target", annotation_position="bottom right",
                  annotation_font=dict(size=11, color="#64748b"))
    if base_e is not None:
        fig.add_vline(x=base_e, line_dash="dot", line_color=base_col,
                      annotation_text=f"current: {base_e}", annotation_position="top left",
                      annotation_font=dict(size=10, color=base_col))
    if alt_e is not None and alt_e != base_e:
        fig.add_vline(x=alt_e, line_dash="dot", line_color=alt_col,
                      annotation_text=f"alt: {alt_e}", annotation_position="bottom left",
                      annotation_font=dict(size=10, color=alt_col))
    fig.update_layout(
        title=dict(
            text="<b>When can you retire? — current vs. alternate</b><br>"
                 "<span style='font-size:13px;color:#64748b;'>Success probability at each retirement age</span>",
            x=0.0, xanchor="left", font=dict(size=16),
        ),
        height=380, margin=dict(l=50, r=40, t=80, b=50),
        xaxis=dict(title="Retirement age", gridcolor="#f1f5f9", zeroline=False, tickfont=dict(color="#64748b")),
        yaxis=dict(title="Success rate (%)", range=[0, 105], gridcolor="#f1f5f9", zeroline=False,
                   tickfont=dict(color="#64748b")),
        showlegend=True, dragmode="pan", uirevision="keep",
    )
    fig = style_fig(fig, st)
    st.plotly_chart(fig, width="stretch", key=f"wifc_curve_{'dk' if dark else 'lt'}", config=PLOTLY_CONFIG)
    st.caption(
        "The dotted **Alternate** line reflects the levers above; the solid **Current plan** line is your "
        "sidebar inputs. Where a line first crosses the target, that's the earliest age you could retire under "
        "that scenario."
    )
