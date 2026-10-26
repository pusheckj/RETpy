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
    from utils.household import has_partner, plan_end_text
    from utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark
    from utils.sim_runner import run_networth_analysis, _hashable
except ImportError:  # pragma: no cover
    from ui.utils.formatting import money  # type: ignore
    from ui.utils.household import has_partner, plan_end_text  # type: ignore
    from ui.utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark  # type: ignore
    from ui.utils.sim_runner import run_networth_analysis, _hashable  # type: ignore


def _inputs_hash(overrides: dict, n_sims):
    """Stable hash of the inputs that drive the sweep (overrides + sim count),
    so a stored FI result can be detected as stale — and the button as inactive
    — after the user edits the sidebar, switches profiles, or changes the count."""
    try:
        return hash((_hashable(overrides), int(n_sims)))
    except Exception:
        return None


_FRESH_HELP = ("This matches your current inputs. Change a sidebar setting "
               "or the simulation count to recalculate.")


def render(st, results: dict = None) -> None:
    st.markdown('<div class="mc-section">Portfolio needed to retire</div>', unsafe_allow_html=True)
    overrides = st.session_state.get("user_overrides", {}) or {}

    # Household size as the simulation sees it (cfg.has_partner for these inputs).
    couple = has_partner(overrides)
    st.caption(
        "Instead of asking *when* you can retire, this finds the **investable portfolio** you "
        "need to stop working. "
        + ("You both keep" if couple else "You keep")
        + " working and saving until the balance first hits a target, then retire "
        "that year. Your **number** is the smallest target that still meets your success "
        "goal. It leaves out home equity and 529 college funds"
        + (". It assumes you both work until the target and retire together, so your "
           "partner's own retirement age isn't used here." if couple else ".")
    )
    # Orient the reader: three tiles answer the same question three ways, and a
    # first-time user otherwise can't tell which number to trust.
    st.caption(
        "The same plan, three questions. **Retirement** says *when* (earliest age). "
        "This section says *how much* you need. **Safe withdrawal rate** says *how much "
        "you can spend* once you stop. They agree: the earliest age is the year you hit "
        "this number."
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
        prog = st.progress(0.0, text="Testing portfolio targets…")

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
        st.caption("Click **Calculate my number** to test a range of portfolio targets. "
                   "It runs extra simulations, so it takes a few seconds, or up to "
                   "a minute at high simulation counts.")
        return

    # Staleness guard: the result is stored in session state and would otherwise
    # keep showing after the user changes inputs or switches profiles.
    if stale:
        st.warning("Your inputs changed since this was calculated. Click "
                   "**Calculate my number** to update it.")

    _render_result(st, fi, couple)


def _render_result(st, fi: dict, couple: bool = False) -> None:
    num = fi.get("fi_number")
    age = fi.get("fi_median_retire_age")
    lo_age = fi.get("fi_age_low")
    hi_age = fi.get("fi_age_high")
    cur = float(fi.get("current_investable", 0.0))
    target = float(fi.get("target_success", 0.80))
    already = bool(fi.get("already_fi"))
    curve = fi.get("success_by_networth", []) or []
    cap = int(fi.get("max_work_age", 70))

    has_range = (lo_age is not None and hi_age is not None and hi_age > lo_age)
    # No tested target met the goal: say so in words, with the numbers that
    # explain it, instead of "above range" / "—".
    not_reached = (not already) and num is None
    top = max((c["networth"] for c in curve), default=0.0)
    best = max((c["success"] for c in curve), default=0.0)

    cols = st.columns(3)
    with cols[0]:
        if already:
            st.metric("Portfolio needed to retire", money(cur, shorten=True),
                      help=f"Your current investable portfolio ({money(cur, shorten=True)}) "
                           f"already clears the {target:.0%} target. You're at or past "
                           "your number.")
        elif not_reached:
            st.metric("Portfolio needed to retire", f"Over {money(top, shorten=True)}",
                      help=f"No target we tried, up to {money(top, shorten=True)}, "
                           f"reached your {target:.0%} goal.")
        else:
            st.metric("Portfolio needed to retire", money(num, shorten=True),
                      help=f"Smallest investable portfolio with at least a {target:.0%} chance of success, "
                           "if you retire the moment you reach it.")
    with cols[1]:
        if already:
            st.metric("When you could stop", "Now",
                      help="Retiring today already meets your target.")
        elif not_reached:
            st.metric("Best success found", f"{best:.0%}",
                      help="The best chance of success any target we tried reached.")
        else:
            st.metric(
                "Typically reached at age", f"{age:.0f}" if age else "—",
                help=(f"The median age you reach it at today's savings rate"
                      + (f"; most paths land between {lo_age:.0f} and {hi_age:.0f}."
                         if has_range else ".")),
            )
    with cols[2]:
        if already:
            st.metric("Status", "You're there",
                      help=f"Current investable portfolio: {money(cur, shorten=True)}")
        elif not_reached:
            # The sweep never met the success target, even at the top of the range —
            # the household is the FURTHEST from FI, not "there".
            st.metric("Status", "Not reached",
                      help="No target we tried met your success goal.")
        else:
            gap = num - cur
            st.metric(
                "Still to go" if gap > 0 else "Status",
                money(gap, shorten=True) if gap > 0 else "You're there",
                help=f"Current investable portfolio: {money(cur, shorten=True)}",
            )
    if not_reached:
        # Why a bigger target stops helping: the largest targets aren't reached
        # before the work cap, so those runs retire at the cap with less.
        capped = bool(curve) and (curve[-1].get("median_retire_age") or 0) >= cap
        st.info(
            f"No target up to {money(top, shorten=True)} reached your {target:.0%} goal. The "
            f"best was {best:.0%}. "
            + (f"The biggest targets usually aren't reached before age {cap}, the latest "
               "this check lets you work, so those runs retire then with less. "
               if capped else "")
            + "To get there, spend less in retirement, save more now, or lower the "
            "success goal. Then recalculate."
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
                 "<span style='font-size:13px;color:#64748b;'>Retire the moment your portfolio "
                 "hits each target</span>",
            x=0.0, xanchor="left", font=dict(size=16),
        ),
        height=380, margin=dict(l=50, r=40, t=80, b=50),
        xaxis=dict(title="Investable portfolio at retirement", tickformat="$,.2~s",
                   gridcolor="#f1f5f9", zeroline=False, tickfont=dict(color="#64748b")),
        yaxis=dict(title="Success rate (%)", range=[0, 100], gridcolor="#f1f5f9",
                   zeroline=False, tickfont=dict(color="#64748b")),
        showlegend=False, dragmode="pan", uirevision="keep",
    )
    show_chart(st, fig, f"fi_curve_{'dk' if dark else 'lt'}", PLOTLY_CONFIG)

    st.caption(
        "Each point: keep working until the investable portfolio first reaches that target, "
        f"then {'you both retire' if couple else 'retire'} and draw down until "
        f"{plan_end_text(st.session_state.get('user_overrides', {}) or {})}. "
        "You stop when you hit the number, so reaching it **earlier** (in a strong market) means "
        "a longer retirement to fund and a **lower** chance of success than shown here. Reaching it "
        "later is safer. This assumes today's spending, savings rate, and returns. "
        "**Recalculate after you change inputs.**"
    )
