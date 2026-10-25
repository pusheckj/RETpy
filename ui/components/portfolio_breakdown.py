"""Portfolio breakdown with pie charts."""
from __future__ import annotations

import plotly.graph_objects as go

from utils.formatting import money

# #7: shared pastel palette for consistent, softer chart series colors.
try:
    from utils.plot_theme import PALETTE, assign_colors, concept_color, is_dark
except ImportError:
    from ui.utils.plot_theme import PALETTE, assign_colors, concept_color, is_dark


def _get_value(user_overrides: dict, key: str, default: float = 0.0) -> float:
    """Get a numeric value from overrides, falling back to retirement_sim.config."""
    if key in user_overrides and user_overrides[key] is not None:
        try:
            return float(user_overrides[key])
        except (TypeError, ValueError):
            pass
    try:
        from retirement_sim import config as cfg
        return float(getattr(cfg, key, default))
    except Exception:
        return default


def _esc_attr(text: str) -> str:
    """Escape a string for safe use inside an HTML attribute value."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# #5/#14: theme-aware inline <style> for the real hover POPUP (dependency-free).
# The card is a positioned container; .mc-tip is a hidden, absolutely-positioned
# styled popup that becomes visible on hover. The dark palette is applied
# DIRECTLY (keyed on is_dark), not via a `.mc-dark` ancestor class — that class
# is never added to the DOM, so the old scoped rule never fired.
def _tip_style(dark: bool) -> str:
    if dark:
        bg, fg, border, shadow = "#1e293b", "#e2e8f0", "#334155", "0 8px 24px rgba(0, 0, 0, 0.45)"
    else:
        bg, fg, border, shadow = "#ffffff", "#0f172a", "#e5e7eb", "0 8px 24px rgba(15, 23, 42, 0.16)"
    return f'''
<style>
.mc-stat-wrap {{ position: relative; height: 100%; }}
/* Lift the whole card (and its overflowing tooltip) above later sections while
   hovered, so the .mc-tip popup never renders behind the charts below it. */
.mc-stat-wrap:hover {{ z-index: 100; }}
.mc-stat-wrap .mc-tip {{
    position: absolute; left: 0; top: calc(100% + 8px); z-index: 50;
    /* display:none (not just visibility:hidden) while unhovered: a hidden-but-
       laid-out 240px-min-width popup under the RIGHTMOST card pushed
       stMain.scrollWidth ~26-40px past its clientWidth at <=1024px, which is a
       permanent dead horizontal scrollbar on the whole main pane. */
    display: none;
    visibility: hidden; opacity: 0; transition: opacity 0.12s ease-in-out;
    min-width: 240px; max-width: 340px;
    background: {bg}; color: {fg};
    border: 1px solid {border}; border-radius: 10px;
    box-shadow: {shadow};
    padding: 12px 14px; font-size: 12.5px; line-height: 1.5;
    white-space: normal; pointer-events: none;
}}
.mc-stat-wrap .mc-tip .mc-tip-title {{ font-weight: 700; margin-bottom: 4px; }}
.mc-stat-wrap:hover .mc-tip {{ display: block; visibility: visible; opacity: 1; }}
/* Query container for the stat VALUE below, which is sized in cqi (% of this
   card's own width). It used to be sized in vw — viewport-relative, not
   card-relative — so on a narrow/tablet layout the font stayed at its 28px
   floor while the card shrank to ~75px, and the nowrap number painted straight
   across the neighbouring cards. .mc-tip is a SIBLING of .mc-stat-card (inside
   .mc-stat-wrap), so the containment here does not clip the hover popup. */
.mc-stat-wrap .mc-stat-card {{ container-type: inline-size; }}
</style>
'''


def _tip_html(tooltip: str) -> str:
    """Render a breakdown string into a styled .mc-tip popup body.

    The first line becomes a bold title; each subsequent line is its own row.
    """
    lines = [ln for ln in tooltip.split("\n") if ln.strip()]
    if not lines:
        return ""
    title = _esc_attr(lines[0])
    body = "".join(f'<div>{_esc_attr(ln)}</div>' for ln in lines[1:])
    return f'<div class="mc-tip"><div class="mc-tip-title">{title}</div>{body}</div>'


def _delta_badge(delta_val: float) -> str:
    """Render a color-coded "▲/▼ ±$X vs today" pill (⑪ delta-arrow pop).

    Returns "" for a negligible delta so the badge only appears when meaningful.
    """
    if not delta_val or abs(delta_val) < 1:
        return ""
    up = delta_val >= 0
    arrow = "▲" if up else "▼"
    cls = "mc-delta-up" if up else "mc-delta-down"
    sign = "+" if up else "−"
    return (
        f'<div class="mc-delta {cls}">{arrow} {sign}'
        f'{money(abs(delta_val), shorten=True)} vs today</div>'
    )


def _stat_card(label: str, value: str, sublabel: str = "", color: str = "#0f172a", tooltip: str = "", cls: str = "", delta_html: str = "", idx: int = 0, two_line: bool = False) -> str:
    # #5/#14: wrap the card in a positioned container that holds a hidden .mc-tip
    # popup, shown on :hover via CSS (no JS, no native title tooltip).
    # idx drives the ③ cascade stagger so the 4 cards reveal one-by-one.
    tip = _tip_html(tooltip) if tooltip else ""
    cursor = "help" if tooltip else "default"
    return f'''
    <div class="mc-stat-wrap mc-cascade" style="animation-delay:{idx * 90}ms;">
    <div class="mc-stat-card" style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; height: 100%; min-height: 130px; display: flex; flex-direction: column; justify-content: flex-start; cursor: {cursor};">
        <div class="mc-stat-label{' mc-l2' if two_line else ''}" style="font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px;">{label}</div>
        <div class="{cls}" style="font-size: clamp(20px, 17cqi, 52px); font-weight: 700; color: {color}; line-height: 1.1; overflow-wrap: anywhere;">{value}</div>{delta_html}
        <div style="font-size: 12px; color: #94a3b8; margin-top: auto; padding-top: 6px;">{sublabel}</div>
    </div>
    {tip}
    </div>
    '''


def render(st, user_overrides: dict = None, chart_key: str = "portfolio_breakdown_main",
           show_header: bool = True) -> None:
    if user_overrides is None:
        user_overrides = st.session_state.get("user_overrides", {})

    your_age = int(_get_value(user_overrides, "YOUR_AGE", 30))
    ret_age = int(_get_value(user_overrides, "TARGET_RETIREMENT_AGE", 60))

    if show_header:
        st.markdown('<div class="mc-section">Current portfolio</div>', unsafe_allow_html=True)
    else:
        # Nested under a parent section header (e.g. "Retirement"): use a lighter
        # subheader so it doesn't compete with the section title.
        st.markdown(
            '<div style="font-weight:700;font-size:16px;color:#334155;'
            'margin:4px 0 8px 0;">Current portfolio</div>',
            unsafe_allow_html=True,
        )

    # Toggle: today's balances vs a deterministic projection to the retirement
    # date (same engine as the net-worth projection chart). Only offered when
    # retirement is in the future.
    can_project = ret_age > your_age
    if can_project:
        view = st.radio(
            "Portfolio date",
            options=["Today", f"At retirement (age {ret_age})"],
            horizontal=True, key=f"{chart_key}_view", label_visibility="collapsed",
        )
    else:
        view = "Today"
    at_retirement = str(view).startswith("At retirement")

    # Today's balances (from overrides / cfg fallback).
    accounts = {
        "Your 401(k)": _get_value(user_overrides, "YOUR_401K"),
        "Your Roth IRA": _get_value(user_overrides, "YOUR_ROTH_IRA"),
        "Your Traditional IRA": _get_value(user_overrides, "YOUR_TRADITIONAL_IRA"),
        "Your HSA": _get_value(user_overrides, "YOUR_HSA"),
        "Your taxable brokerage": _get_value(user_overrides, "YOUR_BROKERAGE"),
        "Your cash": _get_value(user_overrides, "YOUR_CASH"),
        "Partner 401(k)": _get_value(user_overrides, "PARTNER_401K"),
        "Partner Roth IRA": _get_value(user_overrides, "PARTNER_ROTH_IRA"),
        "Partner taxable brokerage": _get_value(user_overrides, "PARTNER_BROKERAGE"),
        "Partner cash": _get_value(user_overrides, "PARTNER_CASH"),
    }
    home_value = _get_value(user_overrides, "HOME_VALUE")
    mortgage_balance = _get_value(user_overrides, "MORTGAGE_BALANCE")

    # Capture TODAY's category sums before any projection so the "At retirement"
    # view can show each card's growth vs today (⑪ delta-arrow pop).
    _today_home_equity = max(0.0, home_value - mortgage_balance)
    _today_retirement = (
        accounts["Your 401(k)"] + accounts["Your Roth IRA"] + accounts["Your Traditional IRA"]
        + accounts["Your HSA"] + accounts["Partner 401(k)"] + accounts["Partner Roth IRA"]
    )
    _today_nonret = (
        accounts["Your taxable brokerage"] + accounts["Partner taxable brokerage"]
        + accounts["Your cash"] + accounts["Partner cash"]
    )
    _today_net_worth = sum(accounts.values()) + _today_home_equity

    # Project every balance forward to the retirement date if requested. The
    # net-worth projection uses the SAME account labels as ``accounts`` above, so
    # we can swap each balance for its last (= at-retirement) projected value.
    projected = at_retirement
    if projected:
        try:
            try:
                from components.net_worth_projection_chart import project_net_worth
            except ImportError:
                from ui.components.net_worth_projection_chart import project_net_worth  # type: ignore
            proj = project_net_worth(user_overrides)
            by = proj.get("by_account", {}) or {}

            def _last(label: str) -> float:
                seq = by.get(label) or []
                return float(seq[-1]) if seq else 0.0

            accounts = {k: _last(k) for k in accounts}
            # Represent the projected home as pure equity (the projection grows
            # equity; mortgage is assumed retired by the payoff age), so net
            # worth and the tooltips stay internally consistent.
            home_value = _last("Home equity")
            mortgage_balance = 0.0
        except Exception:
            projected = False  # any failure -> fall back to today's values

    home_equity = max(0.0, home_value - mortgage_balance)

    retirement_sum = sum([
        accounts["Your 401(k)"], accounts["Your Roth IRA"], accounts["Your Traditional IRA"], accounts["Your HSA"],
        accounts["Partner 401(k)"], accounts["Partner Roth IRA"],
    ])
    taxable_sum = accounts["Your taxable brokerage"] + accounts["Partner taxable brokerage"]
    cash_sum = accounts["Your cash"] + accounts["Partner cash"]
    net_worth = sum(accounts.values()) + home_equity

    # #5/#14: emit the hover-popup CSS once before the cards (theme-aware).
    dark = is_dark(st)
    st.markdown(_tip_style(dark), unsafe_allow_html=True)

    cols = st.columns(4)

    # #14: build breakdown tooltips (native HTML title) explaining each card.
    net_worth_tip = (
        f"Net worth = assets - debt\n"
        f"Assets {money(sum(accounts.values()) + home_value, shorten=True)} "
        f"minus mortgage {money(mortgage_balance, shorten=True)}"
    )
    retirement_tip = (
        "Retirement = 401(k) + Roth + Traditional IRA + HSA\n"
        f"Your 401(k) {money(accounts['Your 401(k)'], shorten=True)}  |  "
        f"Your Roth IRA {money(accounts['Your Roth IRA'], shorten=True)}  |  "
        f"Your Traditional IRA {money(accounts['Your Traditional IRA'], shorten=True)}  |  "
        f"Your HSA {money(accounts['Your HSA'], shorten=True)}\n"
        f"Partner 401(k) {money(accounts['Partner 401(k)'], shorten=True)}  |  "
        f"Partner Roth IRA {money(accounts['Partner Roth IRA'], shorten=True)}"
    )
    non_retirement_tip = (
        "Non-retirement = taxable brokerage + cash\n"
        f"Taxable brokerage {money(taxable_sum, shorten=True)}  |  "
        f"Cash {money(cash_sum, shorten=True)}"
    )
    home_equity_tip = (
        "Home equity = home value - mortgage balance\n"
        f"Value {money(home_value, shorten=True)} minus mortgage {money(mortgage_balance, shorten=True)}"
    )

    # "vs today" deltas — only in the projected ("At retirement") view.
    if projected:
        d_nw = _delta_badge(net_worth - _today_net_worth)
        d_ret = _delta_badge(retirement_sum - _today_retirement)
        d_nonret = _delta_badge((taxable_sum + cash_sum) - _today_nonret)
        d_home = _delta_badge(home_equity - _today_home_equity)
    else:
        d_nw = d_ret = d_nonret = d_home = ""

    # Phone: cards go two per row; a pair shares its label height (see theme.css).
    l2 = [True, True, False, False]   # "Net worth" | "Retirement accounts" wrap; "Non-retirement" | "Home equity" do not
    with cols[0]: st.markdown(_stat_card("Net worth", money(net_worth, shorten=True), "total assets minus debt", "#0d9488", tooltip=net_worth_tip, cls="mc-teal", delta_html=d_nw, idx=0, two_line=l2[0]), unsafe_allow_html=True)
    with cols[1]: st.markdown(_stat_card("Retirement accounts", money(retirement_sum, shorten=True), "401(k), Roth IRA, Traditional IRA, HSA", tooltip=retirement_tip, delta_html=d_ret, idx=1, two_line=l2[1]), unsafe_allow_html=True)
    with cols[2]: st.markdown(_stat_card("Non&#8209;retirement", money(taxable_sum + cash_sum, shorten=True), "taxable brokerage + cash", tooltip=non_retirement_tip, delta_html=d_nonret, idx=2, two_line=l2[2]), unsafe_allow_html=True)
    with cols[3]: st.markdown(_stat_card("Home equity", money(home_equity, shorten=True), ("projected equity" if projected else f"value {money(home_value, shorten=True)}"), tooltip=home_equity_tip, delta_html=d_home, idx=3, two_line=l2[3]), unsafe_allow_html=True)

    st.markdown('<div style="height: 24px;"></div>', unsafe_allow_html=True)

    # Two pies side-by-side
    pie_cols = st.columns(2)

    with pie_cols[0]:
        # Category pie (KEEP as donut)
        category_labels = ["Retirement", "Taxable brokerage", "Cash", "Home equity"]
        category_values = [retirement_sum, taxable_sum, cash_sum, home_equity]
        # #7: pastel palette, assigned by category name for consistency.
        category_colors = [concept_color(name, st) for name in category_labels]
        fig1 = go.Figure(data=[go.Pie(
            labels=category_labels, values=category_values,
            hole=0.5, marker=dict(colors=category_colors, line=dict(color="#ffffff", width=2)),
            textinfo="none", hovertemplate="<b>%{label}</b><br>%{value:$,.0f}<br>%{percent}<extra></extra>",
            # Full-width donut; legend BELOW so long names never clip on a phone.
            domain=dict(x=[0.0, 1.0], y=[0.26, 1.0]),
        )])
        fig1.update_layout(
            title=dict(text="<b>By category</b>", x=0.0, xanchor="left", y=0.97, yanchor="top", font=dict(size=15)),
            # Fixed height matches the "By account" bar card (340) so the two
            # cards align; the CARD is stretched to the column via theme.css.
            height=340,
            margin=dict(l=10, r=10, t=56, b=18),
            # $ total centered in the donut hole. xanchor=center so x is the text
            # CENTER; x/y = the donut's center (domain x 0-1, y 0.26-1).
            annotations=[dict(text=money(net_worth, shorten=True), x=0.5, xanchor="center", y=0.63, yanchor="middle", font=dict(size=18, family="Inter"), showarrow=False)],
            # Legend vertically centered on the RIGHT.
            legend=dict(orientation="h", yanchor="top", y=0.22, xanchor="center", x=0.5,
                        font=dict(size=12.5), itemsizing="constant"),
            uirevision="keep",
        )
        try:
            from utils.plot_theme import style_fig, show_chart
        except ImportError:
            from ui.utils.plot_theme import style_fig, show_chart
        show_chart(st, fig1, f"{chart_key}_category", {"displayModeBar": False})

    with pie_cols[1]:
        # #17: "By account" as a HORIZONTAL BAR chart, sorted by value descending.
        # #7: pastel palette, assigned by account name for consistency.
        acct_labels, acct_values, acct_colors = [], [], []
        all_names = list(accounts.keys()) + ["Home equity"]
        for name, val in accounts.items():
            if val > 0:
                acct_labels.append(name)
                acct_values.append(val)
                acct_colors.append(concept_color(name, st))
        if home_equity > 0:
            acct_labels.append("Home equity")
            acct_values.append(home_equity)
            acct_colors.append(concept_color("Home equity", st))

        if not acct_values:
            st.info("No account balances to display. Enter your current balances in the sidebar.")
            return

        # Sort descending by value; Plotly draws bars bottom-up, so reverse so the
        # largest value sits at the top of the chart.
        order = sorted(range(len(acct_values)), key=lambda i: acct_values[i])
        bar_labels = [acct_labels[i] for i in order]
        bar_values = [acct_values[i] for i in order]
        bar_colors = [acct_colors[i] for i in order]

        def _wrap_label(name: str, width: int = 16) -> str:
            if len(name) <= width or " " not in name:
                return name
            words = name.split(" ")
            best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
            return " ".join(words[:best]) + "<br>" + " ".join(words[best:])

        def _account_bars(compact: bool) -> go.Figure:
            # Phone: break a long name onto two lines ("Partner taxable<br>brokerage")
            # so the labels stop taking half the plot; the hover keeps the full name.
            ylabels = [_wrap_label(n) for n in bar_labels] if compact else bar_labels
            fig = go.Figure(data=[go.Bar(
                x=bar_values, y=ylabels, orientation="h", customdata=bar_labels,
                marker=dict(color=bar_colors),
                text=[money(v, shorten=True) for v in bar_values],
                textposition="outside", cliponaxis=False,
                textfont=dict(size=12 if compact else 13),
                hovertemplate="<b>%{customdata}</b><br>%{x:$,.0f}<extra></extra>",
            )])
            fig.update_layout(
                title=dict(text="<b>By account</b>", x=0.0, xanchor="left", y=0.97, yanchor="top", font=dict(size=15)),
                height=340, margin=dict(l=20, r=56, t=64, b=30),
                bargap=0.35, showlegend=False,
                uirevision="keep",
            )
            # Headroom on the x-axis so the outside $ labels are not clipped.
            _max = max(bar_values) if bar_values else 0
            fig.update_xaxes(tickformat="$,.3~s", nticks=4, tickangle=0, range=[0, _max * 1.4] if _max else None)
            fig.update_yaxes(tickfont=dict(size=11 if compact else 13), automargin=True)
            if compact:
                # Phone: every bar carries its value, and at ~90 px of plot the
                # axis numbers only ran into each other ("$0$200k$400k").
                fig.update_xaxes(showticklabels=False, showgrid=False)
                fig.update_layout(margin=dict(l=8, r=60, t=56, b=8), height=400)
            return fig

        try:
            from utils.plot_theme import style_fig, show_chart
        except ImportError:
            from ui.utils.plot_theme import style_fig, show_chart
        show_chart(st, _account_bars, f"{chart_key}_account", {"displayModeBar": False})
