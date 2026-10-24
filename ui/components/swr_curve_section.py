"""Safe withdrawal rate (SWR) section — the personalized version of the 4% rule.

Sweeps the initial retirement spending (~3%–6% of investable assets at
retirement) via ``sim_runner.run_swr_analysis`` and plots success rate vs the
realized initial withdrawal rate, marking the user's actual planned rate and the
rate that meets the success target. Behind a button because the sweep runs many
extra simulations.
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.formatting import money
    from utils.sim_runner import run_swr_analysis, _hashable
    from utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark
except ImportError:  # pragma: no cover
    from ui.utils.formatting import money  # type: ignore
    from ui.utils.sim_runner import run_swr_analysis, _hashable  # type: ignore
    from ui.utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark  # type: ignore


def _inputs_hash(overrides: dict, n_sims):
    """Stable hash of the sweep inputs (overrides + sim count) — used to detect a
    stored SWR result as stale and to keep the button inactive until inputs change."""
    try:
        return hash((_hashable(overrides), int(n_sims)))
    except Exception:
        return None


_FRESH_HELP = ("Already reflects your current inputs. Change a sidebar "
               "parameter or the simulation count to recalculate.")


def render(st, results: dict = None) -> None:
    st.markdown('<div class="mc-section">Safe withdrawal rate</div>', unsafe_allow_html=True)
    overrides = st.session_state.get("user_overrides", {}) or {}

    st.caption(
        "Your personalized 4% rule. It sweeps how much you draw in year 1 "
        "(as a % of investable assets at retirement), runs the full Monte Carlo "
        "at each level, and finds the **highest rate that still meets your success "
        "target** — factoring in your taxes, Social Security, guardrails, and a "
        "40+ year horizon that the generic 4% rule ignores."
    )
    st.caption(
        "Third view of the same plan: **Retirement** gives the earliest age, "
        "**Net worth to retire** gives the portfolio you need, and this gives the "
        "spending that portfolio supports.]"
    )

    n_sims = int(st.session_state.get("n_simulations", 1000))
    target_age = int(overrides.get("TARGET_RETIREMENT_AGE", 55))
    swr = st.session_state.get("swr_result")
    cur_hash = _inputs_hash(overrides, n_sims)
    _sh = swr.get("_inputs_hash") if swr else None
    fresh = _sh is not None and cur_hash is not None and _sh == cur_hash
    stale = bool(swr) and _sh is not None and cur_hash is not None and _sh != cur_hash

    if st.button("✓ Rate up to date" if fresh else "Find my safe withdrawal rate",
                 key="swr_calc_btn", type="primary", disabled=fresh,
                 help=_FRESH_HELP if fresh else None):
        try:
            from utils.validation import validate_run_inputs
        except ImportError:  # pragma: no cover
            from ui.utils.validation import validate_run_inputs  # type: ignore
        _errs = validate_run_inputs(overrides, target_age)
        if _errs:
            for _e in _errs:
                st.error(_e)
            return
        prog = st.progress(0.0, text="Sweeping withdrawal rates…")

        def _cb(frac, msg):
            try:
                prog.progress(min(1.0, max(0.0, float(frac))), text=str(msg))
            except Exception:
                pass

        res = run_swr_analysis(overrides, n_simulations=n_sims,
                               target_retirement_age=target_age, progress_callback=_cb)
        res["_inputs_hash"] = cur_hash
        st.session_state["swr_result"] = res
        prog.empty()
        st.rerun()  # re-render so the button immediately goes inactive

    if not swr:
        st.caption("Click **Find my safe withdrawal rate** to run the sweep "
                   "(extra simulations — a few seconds).")
        return
    if swr.get("error"):
        st.info("Couldn't estimate a withdrawal rate — no investable balance at retirement "
                "for these inputs. Check your accounts / retirement age.")
        return

    if stale:
        st.warning("Your inputs changed since this was calculated — click "
                   "**Find my safe withdrawal rate** to refresh.")

    _render_result(st, swr, results)


def _render_result(st, swr: dict, results: dict = None) -> None:
    curve = swr.get("success_by_rate", []) or []
    swr_rate = swr.get("swr_rate")
    target = float(swr.get("target_success", 0.80))
    inv0 = float(swr.get("investable_at_retirement", 0.0) or 0.0)

    # The user's actual planned year-1 withdrawal rate. Prefer the value the
    # sweep computed at baseline; fall back to the last main run's withdrawals.
    actual_rate = swr.get("actual_rate")
    if actual_rate is None and results and inv0 > 0:
        wd = (results.get("primary_result", {}) or {}).get("withdrawals_by_year", []) or []
        if wd:
            actual_rate = float(wd[0].get("total", 0.0) or 0.0) / inv0

    cols = st.columns(3)
    with cols[0]:
        st.metric("Your withdrawal rate", f"{actual_rate:.1%}" if actual_rate else "run sim",
                  help="Year-1 portfolio draw ÷ investable balance at retirement, from your last run.")
    with cols[1]:
        st.metric("Safe rate at target",
                  f"{swr_rate:.1%}" if swr_rate else "none",
                  help=f"Highest initial withdrawal rate that still clears ≥{target:.0%} success.")
    with cols[2]:
        gap = (swr_rate - actual_rate) if (swr_rate and actual_rate is not None) else None
        st.metric("Headroom", f"{gap:+.1%}" if gap is not None else "—",
                  delta=("cushion" if (gap or 0) >= 0 else "overspending") if gap is not None else None,
                  delta_color=("normal" if (gap or 0) >= 0 else "inverse"),
                  delta_arrow=("up" if (gap or 0) >= 0 else "down"),
                  help="Safe rate minus your rate. Positive = room to spend more; negative = at risk.")

    if swr_rate is None:
        st.info(
            "No withdrawal rate in the tested range meets your success target — even a sharply "
            "lower first-year spend falls short at this retirement age. Consider retiring later, "
            "saving more, or lowering the target success rate."
        )

    xs = [c["realized_rate"] * 100 for c in curve]
    ys = [c["success"] * 100 for c in curve]
    dark = is_dark(st)
    line = "#14b8a6" if dark else "#0d9488"
    ref = "#e2e8f0" if dark else "#0f172a"
    you = "#fbbf24" if dark else "#d97706"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines+markers", line=dict(color=line, width=2.5),
        marker=dict(size=6, color=line), name="success",
        hovertemplate="Withdrawal %{x:.1f}%<br>success %{y:.0f}%<extra></extra>",
    ))
    fig.add_hline(y=target * 100, line_dash="dash", line_color=ref,
                  annotation_text=f"target {target:.0%}", annotation_position="bottom right",
                  annotation_font=dict(size=11, color=ref))
    if swr_rate:
        fig.add_vline(x=swr_rate * 100, line_dash="dot", line_color=line,
                      annotation_text=f"safe ≈ {swr_rate:.1%}", annotation_position="top left",
                      annotation_font=dict(size=11, color=line))
    if actual_rate is not None:
        fig.add_vline(x=actual_rate * 100, line_dash="solid", line_color=you,
                      annotation_text=f"your plan ≈ {actual_rate:.1%}", annotation_position="top right",
                      annotation_font=dict(size=11, color=you))
    fig.update_layout(
        title=dict(
            text="<b>Success rate vs. initial withdrawal rate</b><br>"
                 "<span style='font-size:13px;color:#64748b;'>Higher spending → lower success; "
                 "your safe rate is where the curve crosses your target</span>",
            x=0.0, xanchor="left", font=dict(size=16),
        ),
        height=380, margin=dict(l=50, r=40, t=80, b=50),
        xaxis=dict(title="Initial withdrawal rate (% of investable)", ticksuffix="%",
                   gridcolor="#f1f5f9", zeroline=False, tickfont=dict(color="#64748b")),
        yaxis=dict(title="Success rate (%)", range=[0, 100], gridcolor="#f1f5f9",
                   zeroline=False, tickfont=dict(color="#64748b")),
        showlegend=False, dragmode="pan", uirevision="keep",
    )
    show_chart(st, fig, f"swr_curve_{'dk' if dark else 'lt'}", PLOTLY_CONFIG)
    st.caption(
        "Each point re-runs the full Monte Carlo at a different year-1 spending level. The rate is the "
        "**realized total** first-year draw ÷ investable balance at retirement, directly comparable "
        "to your plan's rate. Based on today's inputs — **recalculate after changing them**."
    )
