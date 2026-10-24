"""Net-worth-to-retire ("FI number") section.

Answers "what investable portfolio lets us stop working?" rather than "at what
age?". Runs ``sim_runner.run_networth_analysis`` — retire the moment the
investable balance first hits a target; sweep targets to find the smallest that
meets the plan's success threshold. Behind a button because the sweep runs many
extra simulations.
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.formatting import money
    from utils.plot_theme import style_fig, PLOTLY_CONFIG, is_dark
    from utils.sim_runner import run_networth_analysis, _hashable
except ImportError:  # pragma: no cover
    from ui.utils.formatting import money  # type: ignore
    from ui.utils.plot_theme import style_fig, PLOTLY_CONFIG, is_dark  # type: ignore
    from ui.utils.sim_runner import run_networth_analysis, _hashable  # type: ignore


def _inputs_hash(overrides: dict, n_sims):
    """Stable hash of the inputs that drive the sweep (overrides + sim count),
    so a stored FI result can be detected as stale — and the button as inactive
    — after the user edits the sidebar, switches profiles, or changes the count."""
    try:
        return hash((_hashable(overrides), int(n_sims)))
    except Exception:
        return None


_FRESH_HELP = ("This number reflects your current inputs. Change a sidebar "
               "parameter (or the simulation count) to recalculate.")


def render(st, results: dict = None) -> None:
    st.markdown('<div class="mc-section">Net worth to retire</div>', unsafe_allow_html=True)
    overrides = st.session_state.get("user_overrides", {}) or {}

    couple = int(overrides.get("PARTNER_AGE", 0) or 0) > 0
    st.caption(
        "Instead of *when* you can retire, this finds the **investable portfolio** that "
        "lets you stop. "
        + ("Both of you keep" if couple else "You keep")
        + " working and contributing until the balance first hits a target, then retire "
        "that year. Your **number** is the smallest target that still meets your success "
        "threshold. Excludes home equity and earmarked 529 college funds"
        + ("; assumes both partners work until the target (no separate partner retirement "
           "age)." if couple else ".")
    )
    # Orient the reader: three tiles answer the same question three ways, and a
    # first-time user otherwise can't tell which number to trust.
    st.caption(
        ":gray[The same plan, asked three ways — **Retirement** answers *when* "
        "(earliest age), this section answers *how much* (the portfolio you need), "
        "and **Safe withdrawal rate** answers *how much can I spend* once you stop. "
        "They're consistent: hit this number and the earliest age is the year you hit it.]"
    )

    n_sims = int(st.session_state.get("n_simulations", 1000))
    fi = st.session_state.get("fi_result")
    cur_hash = _inputs_hash(overrides, n_sims)
    _fih = fi.get("_inputs_hash") if fi else None
    fresh = _fih is not None and cur_hash is not None and _fih == cur_hash
    stale = bool(fi) and _fih is not None and cur_hash is not None and _fih != cur_hash

    if st.button("✓ Number up to date" if fresh else "Calculate my number",
                 key="fi_calc_btn", type="primary", disabled=fresh,
                 help=_FRESH_HELP if fresh else None):
        # This sweep EARNS the retirement age (retires when the portfolio hits a
        # target), so it only needs a valid planning horizon — pass target_age=None.
        try:
            from utils.validation import validate_run_inputs
        except ImportError:  # pragma: no cover
            from ui.utils.validation import validate_run_inputs  # type: ignore
        _errs = validate_run_inputs(overrides, None)
        if _errs:
            for _e in _errs:
                st.error(_e)
            return
        prog = st.progress(0.0, text="Sweeping net-worth targets…")

        def _cb(frac, msg):
            try:
                prog.progress(min(1.0, max(0.0, float(frac))), text=str(msg))
            except Exception:
                pass

        res = run_networth_analysis(overrides, n_simulations=n_sims, progress_callback=_cb)
        res["_inputs_hash"] = cur_hash
        st.session_state["fi_result"] = res
        prog.empty()
        st.rerun()  # re-render so the button immediately goes inactive

    if not fi:
        st.caption("Click **Calculate my number** to run the net-worth sweep "
                   "(extra simulations — a few seconds, up to ~a minute at high "
                   "sim counts).")
        return

    # Staleness guard: the result is stored in session state and would otherwise
    # keep showing after the user changes inputs or switches profiles.
    if stale:
        st.warning("Your inputs changed since this was calculated — click "
                   "**Calculate my number** to refresh.")

    _render_result(st, fi)


def _render_result(st, fi: dict) -> None:
    num = fi.get("fi_number")
    age = fi.get("fi_median_retire_age")
    lo_age = fi.get("fi_age_low")
    hi_age = fi.get("fi_age_high")
    cur = float(fi.get("current_investable", 0.0))
    target = float(fi.get("target_success", 0.80))
    already = bool(fi.get("already_fi"))
    curve = fi.get("success_by_networth", []) or []

    has_range = (lo_age is not None and hi_age is not None and hi_age > lo_age)

    cols = st.columns(3)
    with cols[0]:
        st.metric(
            "Net worth to retire",
            money(cur, shorten=True) if already else (money(num, shorten=True) if num else "above range"),
            help=(f"Your current investable portfolio ({money(cur, shorten=True)}) already "
                  f"clears the {target:.0%} target — you're at or past your number."
                  if already else
                  f"Smallest investable portfolio with ≥{target:.0%} success, retiring "
                  "the moment you reach it."),
        )
    with cols[1]:
        if already:
            st.metric("When you could stop", "Now",
                      help="Retiring today already meets your success target.")
        else:
            st.metric(
                "Typically reached at age", f"{age:.0f}" if age else "—",
                help=(f"Median age you reach that number at today's savings rate"
                      + (f"; most paths land between {lo_age:.0f} and {hi_age:.0f}." if has_range else ".")),
            )
    with cols[2]:
        if already:
            st.metric("Status", "You're there",
                      help=f"Current investable portfolio: {money(cur, shorten=True)}")
        elif num is None:
            # The sweep never met the success target, even at the top of the range —
            # the household is the FURTHEST from FI, not "there". Don't collapse this
            # into the gap<=0 "You're there" case.
            st.metric("Status", "Above range",
                      help="No swept net-worth target met your success threshold. Your "
                           "number is beyond the tested range — lower spending, raise "
                           "savings, or extend the work-cap age, then recalculate.")
        else:
            gap = num - cur
            st.metric(
                "Still to go" if gap > 0 else "Status",
                money(gap, shorten=True) if gap > 0 else "You're there",
                help=f"Current investable portfolio: {money(cur, shorten=True)}",
            )

    xs = [c["networth"] for c in curve]
    ys = [c["success"] * 100 for c in curve]
    dark = is_dark(st)
    line = "#14b8a6" if dark else "#0d9488"
    ref = "#e2e8f0" if dark else "#0f172a"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines+markers",
        line=dict(color=line, width=2.5), marker=dict(size=6, color=line),
        name="success",
        hovertemplate="Net worth $%{x:,.0f}<br>success %{y:.0f}%<extra></extra>",
    ))
    fig.add_hline(y=target * 100, line_dash="dash", line_color=ref,
                  annotation_text=f"target {target:.0%}", annotation_position="bottom right",
                  annotation_font=dict(size=11, color=ref))
    vline_x = cur if already else num
    if vline_x:
        fig.add_vline(x=vline_x, line_dash="dot", line_color=line,
                      annotation_text=("you're here ≈ " if already else "your number ≈ ") + money(vline_x, shorten=True),
                      annotation_position="top left", annotation_font=dict(size=11, color=line))
    fig.update_layout(
        title=dict(
            text="<b>Success rate vs. net worth at retirement</b><br>"
                 "<span style='font-size:13px;color:#64748b;'>Retire the moment the portfolio "
                 "hits each target</span>",
            x=0.0, xanchor="left", font=dict(size=16),
        ),
        height=380, margin=dict(l=50, r=40, t=80, b=50),
        xaxis=dict(title="Investable net worth at retirement", tickformat="$,.2~s",
                   gridcolor="#f1f5f9", zeroline=False, tickfont=dict(color="#64748b")),
        yaxis=dict(title="Success rate (%)", range=[0, 100], gridcolor="#f1f5f9",
                   zeroline=False, tickfont=dict(color="#64748b")),
        showlegend=False, dragmode="pan", uirevision="keep",
    )
    fig = style_fig(fig, st)
    st.plotly_chart(fig, width="stretch", key=f"fi_curve_{'dk' if dark else 'lt'}", config=PLOTLY_CONFIG)

    st.caption(
        "Each point: keep working until the investable portfolio first reaches that target, "
        "then both retire and draw down to the plan-end age. Because retirement age is *earned* "
        "(you stop when you hit the number), reaching it **earlier** — in a strong market — means "
        "a longer retirement to fund and a **lower** success rate than this headline; reaching it "
        "later is safer. Assumes today's spending, savings rate, and returns — "
        "**recalculate after changing inputs**."
    )
