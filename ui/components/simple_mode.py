"""Simple mode: "Money check-up", a phone-first everyday-money page.

No Monte Carlo and no engine calls: everything comes from
``utils.simple_finance`` and renders instantly.

Contract
--------
``render(st)`` reads and writes ``st.session_state["simple_inputs"]``, always a
``simple_finance.normalize_inputs`` dict, so the caller can persist it and
restore it. If the caller replaces that dict between runs (for example after
reading it back from the browser), the widgets reseed from it on the next run.

Styling: the page uses the app's tiles (``mc-tile-simple-*``) and
``.mc-section`` headings and the ``simple-*`` classes, all in ``styles/theme.css``.
"""
from __future__ import annotations

import copy
import html
from datetime import date
from typing import Any, Dict, List

import plotly.graph_objects as go

try:
    from utils import simple_finance as sf
    from utils.formatting import money, money_md
    from utils.plot_theme import is_dark, style_fig
except ImportError:  # pragma: no cover
    from ui.utils import simple_finance as sf  # type: ignore
    from ui.utils.formatting import money, money_md  # type: ignore
    from ui.utils.plot_theme import is_dark, style_fig  # type: ignore

STATE_KEY = "simple_inputs"
_SYNC_KEY = "_simple_inputs_synced"   # copy of what this page last wrote
_W = "simple_w_"                      # widget-key prefix
_SCALARS = [k for k in sf.DEFAULT_INPUTS if k != "debts"]
_DOLLAR = ":material/attach_money:"
_PCT = ":material/percent:"
_TEAL, _SLATE = "#0d9488", "#7a8db3"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _h(text: Any) -> str:
    """HTML-escape, and keep ``$`` away from Streamlit's markdown math."""
    return html.escape(str(text)).replace("$", "&#36;")


def _m(value: float) -> str:
    return _h(money(value))


def _duration(months: int) -> str:
    y, m = divmod(int(months), 12)
    parts = ([f"{y} yr"] if y else []) + ([f"{m} mo"] if m or not y else [])
    return " ".join(parts)


def _section(st, title: str, sub: str = "") -> None:
    st.markdown(f'<div class="mc-section">{_h(title)}</div>', unsafe_allow_html=True)
    if sub:
        st.markdown(f'<div class="simple-sub">{_h(sub)}</div>', unsafe_allow_html=True)


def _group(st, title: str) -> None:
    st.markdown(f'<div class="simple-group">{_h(title)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Widget state <-> inputs dict
# ---------------------------------------------------------------------------
def _debt_key(i: int, field: str) -> str:
    return f"{_W}debt_{i}_{field}"


def _seed(ss, inputs: Dict[str, Any], force: bool) -> None:
    """Push inputs into widget keys (all of them when ``force``, else only missing ones)."""
    for f in _SCALARS:
        if force or _W + f not in ss:
            ss[_W + f] = inputs[f]
    for i, row in enumerate(inputs["debts"]):
        for f in sf.DEBT_FIELDS:
            if force or _debt_key(i, f) not in ss:
                ss[_debt_key(i, f)] = row[f]


def _collect(ss, base: Dict[str, Any]) -> Dict[str, Any]:
    """Current widget values layered over ``base``, normalised."""
    d = dict(base)
    for f in _SCALARS:
        if _W + f in ss:
            d[f] = ss[_W + f]
    debts = []
    for i, row in enumerate(base["debts"]):
        r = dict(row)
        for f in sf.DEBT_FIELDS:
            if _debt_key(i, f) in ss:
                r[f] = ss[_debt_key(i, f)]
        debts.append(r)
    d["debts"] = debts
    return sf.normalize_inputs(d)


def _add_debt(ss) -> None:
    inputs = _collect(ss, sf.normalize_inputs(ss.get(STATE_KEY)))
    if len(inputs["debts"]) < sf.MAX_DEBTS:
        inputs["debts"].append({"name": f"Debt {len(inputs['debts']) + 1}",
                                "balance": 0.0, "apr_pct": 0.0, "min_payment": 0.0})
    ss[STATE_KEY] = sf.normalize_inputs(inputs)
    ss[_SYNC_KEY] = None                       # reseed every widget next run


def _remove_debt(ss, index: int) -> None:
    inputs = _collect(ss, sf.normalize_inputs(ss.get(STATE_KEY)))
    if 0 <= index < len(inputs["debts"]):
        del inputs["debts"][index]
    ss[STATE_KEY] = sf.normalize_inputs(inputs)
    ss[_SYNC_KEY] = None


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def _money_input(st, field: str, label: str, help_text: str, step: float = 50.0,
                 hi: float = sf.MONTHLY_MAX) -> None:
    st.number_input(label, min_value=0.0, max_value=hi, step=step, format="%.0f",
                    key=_W + field, help=help_text, icon=_DOLLAR)


def _pct_input(st, field: str, label: str, help_text: str) -> None:
    st.number_input(label, min_value=0.0, max_value=sf.PCT_MAX, step=0.5, format="%.1f",
                    key=_W + field, help=help_text, icon=_PCT)


def _render_inputs(st, inputs: Dict[str, Any]) -> None:
    ss = st.session_state
    _section(st, "Your numbers", "Rough numbers are fine. Everything updates as you type.")

    _group(st, "Each month")
    c1, c2 = st.columns(2)
    with c1:
        _money_input(st, "take_home_monthly", "Take-home pay",
                     "What lands in your bank account each month, after taxes and "
                     "paycheck deductions.")
        _money_input(st, "needs_monthly", "Needs",
                     "Must-pay bills: rent or mortgage, utilities, groceries, insurance, "
                     "getting to work, and your minimum debt payments.")
    with c2:
        _money_input(st, "wants_monthly", "Wants",
                     "Optional spending: eating out, shopping, subscriptions, travel, hobbies.")
        _money_input(st, "extra_debt_payment_monthly", "Extra paid on debt",
                     "Anything you pay on debts above the minimums each month.")

    _group(st, "Savings")
    c1, c2 = st.columns(2)
    with c1:
        _money_input(st, "cash_savings", "Cash savings",
                     "Money in checking and savings you could get to quickly. "
                     "Not investments or retirement accounts.", step=500.0, hi=sf.BALANCE_MAX)
    with c2:
        st.select_slider("Emergency fund goal", options=list(range(sf.EMERGENCY_MIN_MONTHS,
                                                                   sf.EMERGENCY_MAX_MONTHS + 1)),
                         format_func=lambda m: f"{m} months", key=_W + "emergency_target_months",
                         help="How many months of needs to keep in cash. 3 if your income is "
                              "steady; closer to 6 if it's irregular or others rely on you.")

    _group(st, "Work and retirement")
    c1, c2, c3 = st.columns(3)
    with c1:
        _money_input(st, "gross_salary_annual", "Yearly salary (before tax)",
                     "Used to work out your 401(k) match and limits.", step=1000.0,
                     hi=sf.BALANCE_MAX)
    with c2:
        _pct_input(st, "retirement_contrib_pct", "You put in (% of pay)",
                   "The percent of each paycheck going into your 401(k) or 403(b).")
    with c3:
        _pct_input(st, "employer_match_pct", "Employer matches up to (%)",
                   "Your employer adds money when you contribute, up to this percent of "
                   "your pay. Check your benefits site. 0 if there's no match.")
    c1, c2 = st.columns(2)
    with c1:
        _money_input(st, "ira_contrib_annual", "Put into an IRA this year",
                     "Roth or traditional IRA contributions so far this year.", step=100.0,
                     hi=sf.BALANCE_MAX)
    with c2:
        st.toggle("Your health plan is HSA-eligible", key=_W + "hsa_eligible",
                  help="Health Savings Accounts are only for high-deductible health plans. "
                       "Your plan documents say if it's HSA-eligible.")
        if ss.get(_W + "hsa_eligible"):
            st.toggle("Family coverage", key=_W + "hsa_family",
                      help="Family coverage has a higher yearly HSA limit.")
    if ss.get(_W + "hsa_eligible"):
        _money_input(st, "hsa_contrib_annual", "Put into your HSA this year",
                     "Your HSA contributions so far this year, including any from your employer.",
                     step=100.0, hi=sf.BALANCE_MAX)

    _group(st, "Debts")
    st.caption("Credit cards, car loans, student loans, personal loans. "
               "Leave out your mortgage.")
    for i in range(len(inputs["debts"])):
        with st.container(border=True, key=f"simple-debt-{i}"):
            n1, n2 = st.columns([4, 1], vertical_alignment="bottom")
            n1.text_input("Name", key=_debt_key(i, "name"), max_chars=sf.DEBT_NAME_MAX_LEN)
            n2.button("Remove", key=f"simple_debt_rm_{i}", on_click=_remove_debt,
                      args=(ss, i), help="Remove this debt", width="stretch")
            b, a, m = st.columns(3)
            b.number_input("Balance", min_value=0.0, max_value=sf.BALANCE_MAX, step=100.0,
                           format="%.0f", key=_debt_key(i, "balance"),
                           help="How much you owe now.", icon=_DOLLAR)
            a.number_input("APR", min_value=0.0, max_value=sf.PCT_MAX, step=0.25,
                           format="%.2f", key=_debt_key(i, "apr_pct"),
                           help="The yearly interest rate on your statement.", icon=_PCT)
            m.number_input("Min payment", min_value=0.0, max_value=sf.MONTHLY_MAX, step=10.0,
                           format="%.0f", key=_debt_key(i, "min_payment"),
                           help="The minimum payment due each month.", icon=_DOLLAR)
    if len(inputs["debts"]) < sf.MAX_DEBTS:
        st.button("Add a debt", key="simple_debt_add", icon=":material/add:",
                  on_click=_add_debt, args=(ss,))


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
_RATE_CHIP = {"strong": ("Strong", "good"), "healthy": ("Healthy", "good"),
              "low": ("Room to grow", "warn"), "negative": ("Spending > income", "warn"),
              "unknown": ("Add take-home pay", "")}
_FUND_CHIP = {"plenty": ("More than 6 months", "good"), "ok": ("In the 3-6 month range", "good"),
              "building": ("Building", "warn"), "none": ("Not started", "warn"),
              "unknown": ("Add your needs", "")}


def _chip(text: str, tone: str = "") -> str:
    cls = f"simple-chip simple-chip--{tone}" if tone else "simple-chip"
    return f'<span class="{cls}">{_h(text)}</span>'


def _render_headline(st, rate: sf.SavingsRate, fund: sf.EmergencyFund) -> None:
    c1, c2 = st.columns(2)
    with c1, st.container(border=True, key="mc-tile-simple-rate"):
        value = "—" if rate.rate is None else f"{rate.rate:.0%}"
        label, tone = _RATE_CHIP[rate.band]
        kept = (f'<div class="simple-note">You keep <b>{_m(max(0.0, rate.monthly_savings))}</b> '
                f'a month.</div>') if rate.rate is not None else ""
        fill = 0 if rate.rate is None else max(0.0, min(rate.rate / 0.30, 1.0)) * 100
        st.markdown(
            f'<div class="mc-stat-label">Savings rate</div>'
            f'<div class="simple-kpi-value">{value}</div>{_chip(label, tone)}'
            f'<div class="simple-meter"><div class="simple-meter-fill" style="width:{fill:.1f}%"></div>'
            f'<div class="simple-meter-tick" style="left:33.3%"><span>10%</span></div>'
            f'<div class="simple-meter-tick" style="left:66.7%"><span>20%</span></div></div>'
            f'{kept}<div class="simple-note">{_h(rate.message)}</div>',
            unsafe_allow_html=True)
    with c2, st.container(border=True, key="mc-tile-simple-fund"):
        value = "—" if fund.months is None else f"{fund.months:.1f} months"
        label, tone = _FUND_CHIP[fund.status]
        fill = 0 if fund.months is None else min(fund.months / sf.EMERGENCY_MAX_MONTHS, 1.0) * 100
        gaps = ""
        if fund.months is not None and fund.gap_to_max > 0:
            bits = []
            if fund.gap_to_min > 0:
                bits.append(f"<b>{_m(fund.gap_to_min)}</b> more reaches 3 months")
            bits.append(f"<b>{_m(fund.gap_to_max)}</b> reaches 6")
            gaps = f'<div class="simple-note">{"; ".join(bits)}.</div>'
        st.markdown(
            f'<div class="mc-stat-label">Emergency fund</div>'
            f'<div class="simple-kpi-value">{value}</div>{_chip(label, tone)}'
            f'<div class="simple-meter"><div class="simple-meter-fill" style="width:{fill:.1f}%"></div>'
            f'<div class="simple-meter-tick" style="left:50%"><span>3 mo</span></div>'
            f'<div class="simple-meter-tick simple-meter-tick--end" style="left:99.5%">'
            f'<span>6 mo</span></div></div>'
            f'<div class="simple-note">Months of needs ({_m(fund.essentials_monthly)}/mo) your '
            f'cash covers.</div>{gaps}<div class="simple-note">{_h(fund.message)}</div>',
            unsafe_allow_html=True)


def _render_ladder(st, steps: List[sf.LadderStep]) -> None:
    with st.container(border=True, key="mc-tile-simple-ladder"):
        _section(st, "Where your next dollar goes",
                 "Work down the list. The highlighted step is where your next spare dollar "
                 "does the most good.")
        cards = []
        for s in steps:
            tone = {"current": "current", "done": "good"}.get(s.status, "")
            label = sf.STATUS_LABELS[s.status]
            num = "✓" if s.status == "done" else str(s.number)
            detail = f'<div class="simple-step-detail">{_h(s.detail)}</div>' if s.detail else ""
            target = ("" if s.status == "skip" else
                      f'<div><span class="simple-step-target">Aim for: {_h(s.target_label)}</span></div>')
            cards.append(
                f'<div class="simple-step simple-step--{s.status}">'
                f'<div class="simple-step-head"><span class="simple-step-num">{num}</span>'
                f'<span class="simple-step-title">{_h(s.title)}</span>{_chip(label, tone)}</div>'
                f'<div class="simple-step-body">{target}<div>{_h(s.why)}</div>{detail}</div></div>')
        st.markdown(f'<div class="simple-steps">{"".join(cards)}</div>', unsafe_allow_html=True)
        st.caption("Rules of thumb, not personal advice. Contribution limits are yearly "
                   "and don't include age-50+ catch-up amounts.")


def _plan_card(res: sf.PayoffResult, name: str, sub: str, best: bool, badge: str) -> str:
    if res.focus_order:
        sub = f"{sub}: extra goes to {res.focus_order[0]} first"
    if res.paid_off:
        big = f"Debt-free by {_h(res.debt_free_date)}"
        meta = f"{_h(_duration(res.months))} &middot; {_m(res.total_interest)} in interest"
        rows = "".join(f'<li><span>{i + 1}. {_h(r["name"])}</span>'
                       f'<span>paid off {_h(r["payoff_date"])}</span></li>'
                       for i, r in enumerate(res.order))
    else:
        big = "Won't pay off at these payments"
        meta = (f"After {sf.MAX_PAYOFF_MONTHS // 12} years you'd still owe "
                f"{_m(res.remaining_balance)}. Pay extra each month or raise "
                f"the payments.")
        rows = "".join(f'<li><span>{_h(r["name"])}</span><span>'
                       f'{"paid off " + _h(r["payoff_date"]) if r["payoff_date"] else "not paid off"}'
                       f'</span></li>' for r in res.order)
    chip = _chip(badge, "good") if badge else ""
    return (f'<div class="simple-plan{" simple-plan--best" if best else ""}">'
            f'<div class="simple-plan-head"><span class="simple-plan-name">{_h(name)}</span>{chip}</div>'
            f'<div class="simple-plan-sub">{_h(sub)}</div>'
            f'<div class="simple-plan-big">{big}</div><div class="simple-plan-meta">{meta}</div>'
            f'<div class="simple-plan-list-title">When each debt is paid off</div>'
            f'<ul class="simple-plan-order">{rows}</ul></div>')


def _payoff_chart(st, av: sf.PayoffResult, sb: sf.PayoffResult, start: date) -> None:
    fig = go.Figure()
    for res, name, color, dash in ((av, "Avalanche", _TEAL, "solid"),
                                   (sb, "Snowball", _SLATE, "dash")):
        xs = [sf.month_date(start, k).isoformat() for k in range(len(res.balances))]
        fig.add_trace(go.Scatter(
            x=xs, y=res.balances, name=name, mode="lines",
            line=dict(color=color, width=3, dash=dash),
            hovertemplate=f"{name}: $%{{y:,.0f}}<extra></extra>"))
    fig.update_layout(height=300, margin=dict(l=8, r=8, t=8, b=40), dragmode=False,
                      hovermode="x unified")
    style_fig(fig, st)
    # Readable at tablet width, one font, a neutral hover label and a thin guide.
    fig.update_layout(font=dict(size=12), legend=dict(font=dict(size=12)),
                      hoverlabel=dict(font=dict(size=12),
                                      **(dict(bgcolor="#37343f", bordercolor="#47434f")
                                         if is_dark(st) else {})))
    fig.update_xaxes(fixedrange=True, hoverformat="%b %Y", showspikes=True,
                     spikethickness=1, spikedash="dot", spikecolor="#94a3b8",
                     spikemode="across")
    fig.update_yaxes(showspikes=False)
    fig.update_yaxes(fixedrange=True, tickprefix="$", tickformat="~s", rangemode="tozero",
                     title_text=None)
    st.plotly_chart(fig, width="stretch",
                    config={"displayModeBar": False, "scrollZoom": False, "displaylogo": False})


def _render_payoff(st, payoff: Dict[str, Any], inputs: Dict[str, Any], start: date) -> None:
    av: sf.PayoffResult = payoff["avalanche"]
    sb: sf.PayoffResult = payoff["snowball"]
    with st.container(border=True, key="mc-tile-simple-debt"):
        _section(st, "Pay off debt: two ways",
                 "Both plans pay the same total each month. When a debt is paid off, its "
                 "minimum rolls into the next one.")
        if not av.order:
            st.markdown('<div class="simple-note">No debts entered. If you have any, add them '
                        'under <b>Debts</b> above to see a payoff plan.</div>',
                        unsafe_allow_html=True)
            return
        extra = inputs["extra_debt_payment_monthly"]
        st.markdown(
            f'<div class="simple-note">Paying <b>{_m(av.monthly_payment)}</b> a month: '
            f'{_m(av.monthly_payment - extra)} in minimums + {_m(extra)} extra.</div>',
            unsafe_allow_html=True)
        if av.underwater:
            names = ", ".join(av.underwater)
            st.warning(f"The minimum on **{names}** doesn't cover its monthly interest, so on "
                       "its own that balance never shrinks. Paying extra fixes this.")
        saved = payoff["interest_saved"]
        av_best = av.paid_off and (not sb.paid_off or av.total_interest <= sb.total_interest)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(_plan_card(av, "Avalanche", "Highest interest rate first",
                                   av_best, "Saves the most" if av_best and saved else ""),
                        unsafe_allow_html=True)
        with c2:
            sb_first = (sb.order[0]["payoff_month"] if sb.order and sb.order[0]["payoff_month"]
                        else None)
            av_first = (av.order[0]["payoff_month"] if av.order and av.order[0]["payoff_month"]
                        else None)
            quick = bool(sb_first and av_first and sb_first < av_first)
            st.markdown(_plan_card(sb, "Snowball", "Smallest balance first", False,
                                   "Quickest first win" if quick else ""),
                        unsafe_allow_html=True)
        if saved is not None:
            if saved > 0.5:
                verdict = (f"Avalanche saves **{money_md(saved)}** in interest. Snowball "
                           "clears a debt sooner, which keeps some people motivated. "
                           "Either beats paying only the minimums.")
            else:
                verdict = "Both plans cost about the same here, so pick the one you'll stick with."
            st.markdown(verdict)
        _payoff_chart(st, av, sb, start)


def _render_budget(st, buckets: List[sf.BudgetBucket]) -> None:
    with st.container(border=True, key="mc-tile-simple-budget"):
        _section(st, "The 50/30/20 check",
                 "A popular guide for take-home pay: about 50% on needs, 30% on wants, and "
                 "20% on savings and extra debt payments.")
        rows = []
        for b in buckets:
            share = b.share
            width = 0.0 if share is None else max(0.0, min(share, 1.0)) * 100
            pct = "—" if share is None else f"{share:.0%}"
            rows.append(
                f'<div class="simple-bar-row"><div class="simple-bar-head">'
                f'<span>{_h(b.label)}</span><span><b>{pct}</b> &middot; {_m(b.amount)}</span></div>'
                f'<div class="simple-bar"><div class="simple-bar-fill simple-fill--{b.status}" '
                f'style="width:{width:.1f}%"></div><div class="simple-bar-target" '
                f'style="left:{b.target * 100:.0f}%" title="{b.target:.0%} guide"></div></div>'
                f'<div class="simple-bar-note">{_h(b.message)}</div></div>')
        st.markdown("".join(rows), unsafe_allow_html=True)
        st.caption("The tick on each bar marks the guide. Minimum debt payments count as "
                   "needs; extra debt payments count as savings.")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def render(st) -> None:
    """Draw the page. Reads/writes ``st.session_state["simple_inputs"]``."""
    ss = st.session_state
    inputs = sf.normalize_inputs(ss.get(STATE_KEY))
    _seed(ss, inputs, force=ss.get(_SYNC_KEY) != inputs)

    st.markdown('<div class="mc-section">Money check-up</div>', unsafe_allow_html=True)
    st.markdown('<div class="simple-sub">Five quick checks: your savings rate, your emergency '
                'fund, where your next dollar goes, paying off debt, and the '
                '50/30/20 budget.</div>', unsafe_allow_html=True)

    with st.container(border=True, key="mc-tile-simple-inputs"):
        _render_inputs(st, inputs)

    inputs = _collect(ss, inputs)
    ss[STATE_KEY] = inputs
    ss[_SYNC_KEY] = copy.deepcopy(inputs)

    today = date.today()
    res = sf.analyze(inputs, today)
    for w in res["warnings"]:
        st.info(w.replace("$", "\\$"))
    _render_headline(st, res["savings_rate"], res["emergency_fund"])
    _render_ladder(st, res["ladder"])
    _render_payoff(st, res["payoff"], inputs, today)
    _render_budget(st, res["budget"])
