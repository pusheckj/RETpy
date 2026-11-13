"""Debt payoff: the planner's results view for the Debts section.

Instant (no simulation): every figure comes from utils/debt_view.py, which runs
the same payoff math the simulation spends (retirement_sim/debts.py). Shows
when you're debt-free and what it costs, avalanche vs snowball, what paying
more each month saves, a rough effect on retirement, and "Things to know".

Styling: the .debt-* classes inside the "mc-tile-debts" tile (styles/theme.css,
"Debt payoff"; dark values in components/theme_toggle.py). Status is never
colour alone: every chip carries words.
"""
from __future__ import annotations

import html
from datetime import date
from typing import Any, Dict, List, Optional

import plotly.graph_objects as go

try:
    from utils import debt_view as dv
    from utils.coerce import safe_int
    from utils.formatting import money, money_md
    from utils.plot_theme import PLOTLY_CONFIG, is_dark, show_chart
    from utils.simple_finance import month_date
except ImportError:  # pragma: no cover
    from ui.utils import debt_view as dv  # type: ignore
    from ui.utils.coerce import safe_int  # type: ignore
    from ui.utils.formatting import money, money_md  # type: ignore
    from ui.utils.plot_theme import PLOTLY_CONFIG, is_dark, show_chart  # type: ignore
    from ui.utils.simple_finance import month_date  # type: ignore

from retirement_sim import debts as dm

WHATIF_KEY = "debt_whatif"
WHATIF_DEFAULT = 100
WHATIF_MAX = 100_000
BAND_CHIPS = {"high": ("High interest (8%+)", "high"), "moderate": ("Moderate (4–8%)", "moderate"),
              "low": ("Low rate (under 4%)", "low")}
STRATEGY_NAMES = {"avalanche": ("Avalanche", "Highest rate first"),
                  "snowball": ("Snowball", "Smallest balance first")}


def _h(text: Any) -> str:
    """HTML-escape, and keep ``$`` away from Streamlit's markdown math."""
    return html.escape(str(text)).replace("$", "&#36;")


def _m(value: float) -> str:
    return _h(money(value))


def _chip(text: str, tone: str = "") -> str:
    return f'<span class="debt-chip{" debt-chip--" + tone if tone else ""}">{_h(text)}</span>'


# ---------------------------------------------------------------------------
# Pieces (each returns HTML, so tests can read them without Streamlit)
# ---------------------------------------------------------------------------
def stats_html(s: dv.Summary, extra: float) -> str:
    if s.paid_off:
        free, free_sub = _h(s.debt_free), f"in {_h(dv.duration(s.months))}"
    else:
        free, free_sub = "Not within 50 years", "at these payments"
    mins = s.monthly - extra
    if s.growing:      # a compounded 50-year figure would be millions: say what is wrong
        interest, int_sub = "Keeps growing", "payments don't cover the interest"
    else:
        interest, int_sub = _m(s.interest), "under this plan" if s.paid_off else "in 50 years"
    cards = [("Debt-free", free, free_sub),
             ("Interest still to pay", interest, int_sub),
             ("Paying each month", _m(s.monthly),
              f"{_m(mins)} minimums + {_m(extra)} extra" if extra > 0 else "minimums only"),
             ("Owed now", _m(s.owed), f"{len(s.per_debt)} debt{'s' if len(s.per_debt) != 1 else ''}")]
    return '<div class="debt-stats">' + "".join(
        f'<div class="debt-stat"><div class="debt-stat-label">{label}</div>'
        f'<div class="debt-stat-value">{value}</div><div class="debt-stat-sub">{sub}</div></div>'
        for label, value, sub in cards) + "</div>"


def debts_html(s: dv.Summary) -> str:
    items = []
    for n, d in enumerate(s.per_debt, 1):
        label, tone = BAND_CHIPS[d["band"]]
        when = (f"Paid off <b>{_h(d['payoff'])}</b> · {_m(d['interest'])} interest" if d["payoff"]
                else "<b>Not paid off</b> in 50 years")
        items.append(
            f'<div class="debt-item" role="listitem"><div class="debt-item-head"><span class="debt-item-num">{n}</span>'
            f'<span class="debt-item-name">{_h(d["name"])}</span>{_chip(d["kind_label"])}'
            f'{_chip(label, tone)}</div>'
            f'<div class="debt-item-body">{_m(d["balance"])} at {d["apr"] * 100:.2f}% · '
            f'{_m(d["min_payment"])}/mo minimum</div>'
            f'<div class="debt-item-body">{when}</div></div>')
    # Divs, not <ol>/<li>: Streamlit's markdown styles lists (markers, indents).
    return f'<div class="debt-list" role="list">{"".join(items)}</div>'


def plans_html(cmp: Dict[str, Dict[str, Any]], current: str) -> str:
    av, sb = cmp["avalanche"], cmp["snowball"]
    both = av["paid_off"] and sb["paid_off"]
    cheaper = None
    if both and abs(av["interest"] - sb["interest"]) >= 0.5:
        cheaper = "avalanche" if av["interest"] < sb["interest"] else "snowball"
    quicker = None
    if av["first_win_months"] and sb["first_win_months"] and av["first_win_months"] != sb["first_win_months"]:
        quicker = "avalanche" if av["first_win_months"] < sb["first_win_months"] else "snowball"
    cards = []
    for key in ("avalanche", "snowball"):
        p = cmp[key]
        name, sub = STRATEGY_NAMES[key]
        chips = (_chip("Your plan", "plan") if key == current else "") + \
                (_chip("Least interest", "good") if key == cheaper else "") + \
                (_chip("Quickest first win", "good") if key == quicker else "")
        rows = [("Debt-free", _h(p["debt_free"]) if p["paid_off"] else "Not within 50 years"),
                ("Interest", "Keeps growing" if p["growing"] else _m(p["interest"])),
                ("First debt gone", f'{_h(p["first_win"])} ({_h(p["first_name"])})' if p["first_win"] else "—")]
        body = "".join(f'<div class="debt-plan-row"><span>{a}</span><b>{b}</b></div>' for a, b in rows)
        target = f'<div class="debt-plan-sub">{_h(sub)}: extra goes to {_h(p["first_target"])} first</div>' \
            if p["first_target"] else f'<div class="debt-plan-sub">{_h(sub)}</div>'
        cards.append(f'<div class="debt-plan{" debt-plan--current" if key == current else ""}">'
                     f'<div class="debt-plan-head"><span class="debt-plan-name">{name}</span>{chips}</div>'
                     f'{target}{body}</div>')
    return f'<div class="debt-plans">{"".join(cards)}</div>'


def verdict(cmp: Dict[str, Dict[str, Any]]) -> str:
    av, sb = cmp["avalanche"], cmp["snowball"]
    if not (av["paid_off"] and sb["paid_off"]):
        return "Neither order pays the debts off at these payments. Pay more each month first."
    gap = sb["interest"] - av["interest"]
    if gap >= 0.5:
        return (f"Highest rate first saves {money_md(gap)} in interest. Smallest balance first clears "
                "a debt sooner, which keeps some people going. Either beats paying only the minimums.")
    return "Both orders cost about the same here, so pick the one you'll stick with."


def balance_figure(now: dm.Payoff, faster: dm.Payoff, mins: dm.Payoff, more: float,
                   start: date, dark: bool, compact: bool = False) -> go.Figure:
    """Total owed over time: minimums only, your plan, and paying ``more``."""
    horizon = max(now.months, faster.months, 1)
    mins_end = mins.months if mins.paid_off else dm.MAX_MONTHS
    cap = max(horizon, min(mins_end, max(2 * horizon, 24)))
    # A balance that keeps growing would stretch the axis to millions: stop its
    # line once it passes twice what is owed (the caption under the chart says so).
    series = [dm.until_runaway(p.balances[:cap + 1]) for p in (mins, now, faster)]
    cap = max(len(ys) for ys in series) - 1
    teal = "#2dd4bf" if dark else "#0d9488"
    amber = "#fbbf24" if dark else "#b45309"
    slate = "#94a3b8" if dark else "#64748b"
    fig = go.Figure()
    mins_name = ("Minimums only" if mins.paid_off else "Minimums only (keeps growing)" if mins.growing
                 else "Minimums only (not paid off in 50 yrs)")
    for ys, (p, name, color, dash, width) in zip(series, (
            (mins, mins_name, slate, "dot", 2),
            (now, "Your plan", teal, "solid", 3),
            (faster, f"Paying {money(more)} more", amber, "dash", 2.5))):
        xs = [month_date(start, k).isoformat() for k in range(len(ys))]
        fig.add_trace(go.Scatter(x=xs, y=ys, name=name, mode="lines",
                                 line=dict(color=color, width=width, dash=dash),
                                 hovertemplate=f"{name}: $%{{y:,.0f}}<extra></extra>"))
    fig.update_layout(height=280 if compact else 320, margin=dict(l=8, r=16, t=8, b=8),
                      hovermode="x unified", dragmode=False, showlegend=True,
                      legend=dict(orientation="h", yanchor="top", y=-0.12, x=0, xanchor="left"))
    fig.update_xaxes(fixedrange=True, hoverformat="%b %Y", showspikes=True, spikethickness=1,
                     spikedash="dot", spikecolor="#94a3b8", spikemode="across")
    fig.update_yaxes(fixedrange=True, tickprefix="$", tickformat="~s", rangemode="tozero",
                     title_text=None, showspikes=False)
    return fig


def things_to_know_md() -> str:
    """The "Things to know" text. The worked examples are computed, so they are
    always right for the stated numbers."""
    b, apr = dv.EXAMPLE_BALANCE, dv.EXAMPLE_APR
    m = dv.minimum_only_example(b, apr)
    p150, p300 = dv.fixed_payment_example(150, b, apr), dv.fixed_payment_example(300, b, apr)
    hi, mid = f"{dm.HIGH_APR * 100:g}%", f"{dm.MODERATE_APR * 100:g}%"
    return "\n\n".join([
        "**Interest adds up fast.** Card interest is charged on what you owe each month, and "
        "unpaid interest is added to the balance, so you then pay interest on the interest. "
        f"Say you owe {money_md(b)} on a card at {apr * 100:g}% APR. If the minimum is that "
        f"month's interest plus 1% of the balance (a common formula, at least \\$25), paying "
        f"only the minimum takes {dv.years_text(m['months'])} and costs about "
        f"{money_md(m['interest'])} in interest: {money_md(m['paid'])} to repay "
        f"{money_md(b)}. A fixed {money_md(150)} a month clears it in "
        f"{dv.duration(p150.months)} ({money_md(p150.total_interest)} of interest); "
        f"{money_md(300)} a month, in {dv.duration(p300.months)} "
        f"({money_md(p300.total_interest)}).",
        "**APR vs. interest rate.** APR is the yearly cost of borrowing as a percentage. On a "
        "credit card it is the interest rate (charged monthly or daily at a twelfth or a "
        "365th of it). On a loan, the APR also counts some fees, such as an origination "
        "fee, so it can be higher than the interest rate. Compare loans by APR.",
        "**Paying off debt is a sure return.** Each dollar you pay off saves that debt's APR, "
        "with no risk and no tax. Paying off a 22% card is like earning 22%. Stocks have "
        "returned about 10% a year over the long run (about 7% after inflation), with big ups "
        "and downs and no guarantee.",
        f"**Low-rate debt can wait.** Debt under about {mid} costs less than investing has "
        "usually earned, so keeping it on its normal payments while you invest is reasonable. "
        f"Between {mid} and {hi} is a judgment call; many people split extra money between the "
        f"two. At {hi} or more, paying it off usually comes first. (The same rule of thumb as "
        "the Money check-up.)",
        "**Avalanche or snowball.** Paying the highest rate first (avalanche) costs the least "
        "interest. Paying the smallest balance first (snowball) clears a debt sooner, and that "
        "quick win keeps some people going. The best plan is the one you stick with.",
        "**Take the employer match first.** Before paying extra on debt, put in enough to get "
        "your full 401(k) match. A match is often an instant 50% or 100% on what you put in, "
        "more than any debt costs.",
        "**Keep a cash cushion.** Hold a small emergency fund (often \\$1,000 or a month of "
        "costs) before paying debt down hard, so a surprise bill doesn't land back on a card. "
        "Then build toward 3 to 6 months of essentials.",
        "**Balance transfers, refinancing and consolidation.** A 0% balance transfer can save "
        "a lot, but there is usually a fee of about 3% to 5% of the amount moved, and the rate "
        "jumps when the offer ends. Have a plan to pay it off before then. A consolidation "
        "loan only helps if its rate is lower and the cards stay paid off. Moving federal "
        "student loans to a private lender gives up federal options for good.",
        "**Student loans.** Federal loans offer things private loans don't: income-driven "
        "repayment plans that set the payment from your income, deferment and forbearance, "
        "and forgiveness programs such as Public Service Loan Forgiveness. The rules change "
        "often and qualifying takes care, so check studentaid.gov for what applies to you, "
        "and don't count on forgiveness. Private loan terms are set by the lender. Up to "
        "\\$2,500 of student loan interest a year may be tax-deductible, under income limits "
        "(the planner doesn't model this).",
        "**Your credit score.** Paying on time, every time, matters most. Next is how much of "
        "your card limits you use (utilization): keeping balances well under your limits, "
        "under 30% and lower is better, helps. Paying a card off doesn't hurt your score; "
        "closing an old card can raise your utilization.",
        "**In this planner.** Payments are fixed in dollars, so inflation makes later payments "
        "a little cheaper in today's dollars. The simulation pays your debts from your income "
        "while you work (the extra comes out of savings) and from your savings once you've "
        "retired.",
    ])


def _things_to_know(st) -> None:
    with st.expander("Things to know about debt", expanded=False, icon=":material/school:"):
        st.markdown(things_to_know_md())
        st.caption("Educational information, not financial advice. Rates, rules and programs "
                   "change; check with your lender or a qualified professional for your situation.")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def _whatif(st, ov: Dict[str, Any], start: date) -> None:
    st.markdown('<div class="debt-subhead">Pay more each month</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
    with c1:
        # An explicit value=, not a value seeded into session state: this tile is drawn
        # lazily, and a box that mounts again (after Run simulation) starts from what the
        # element carries. Seeded through session state, that was 0 while the text used 100.
        more = safe_int(st.number_input("Try paying this much more ($/mo)", min_value=0,
                                        max_value=WHATIF_MAX, step=25, value=WHATIF_DEFAULT,
                                        key=WHATIF_KEY,
                                        help="A what-if only: it doesn't change your plan. "
                                             "To keep it, raise Extra each month in Debts."), 0)
    w = dv.what_if(ov, more)
    with c2:
        if more <= 0:
            line = "Enter an amount to see what paying more saves."
        elif w["months_saved"] is None:
            line = (f"Paying {_m(more)} more a month: debt-free in "
                    f"{_h(dv.duration(w['faster'].months))}." if w["faster"].paid_off else
                    ("Even that doesn't cover the interest, so what you owe keeps growing."
                     if w["faster"].growing else "Even that doesn't pay the debts off within 50 years."))
        else:
            line = (f"Paying {_m(more)} more a month makes you debt-free "
                    f"<b>{_h(dv.duration(w['months_saved']))} sooner</b> and saves "
                    f"<b>{_m(w['interest_saved'])}</b> in interest.")
        st.markdown(f'<div class="debt-whatif-line">{line}</div>', unsafe_allow_html=True)
    mins = dv.plan(ov, minimums_only=True)
    dark = is_dark(st)
    show_chart(st, lambda compact: balance_figure(w["now"], w["faster"], mins, more, start, dark, compact),
               f"debt_balance_{'dk' if dark else 'lt'}", {**PLOTLY_CONFIG, "displayModeBar": False})
    if any(p.growing for p in (mins, w["now"], w["faster"])):
        st.caption("A line that stops is a balance that keeps growing: the payments don't cover "
                   "the interest. It is cut off once it passes twice what you owe.")
    _retirement_line(st, ov, more)


def _retirement_line(st, ov: Dict[str, Any], more: float) -> None:
    infl = dv.inflation(ov)
    real = dm.real_schedule(dv.rows(ov), dv.extra(ov), dv.strategy(ov), infl)
    total = sum(real.payments)
    age = safe_int(ov.get("TARGET_RETIREMENT_AGE", 55), 55)
    text = (f"Your simulation already pays these debts: about {money_md(total)} in today's "
            f"dollars over {dv.duration(real.payoff.months)}"
            + ("." if real.payoff.paid_off else ", and they are still not paid off."))
    if more > 0 and not real.payoff.paid_off:
        # The comparison counts payments over 50 years only, so with debts that are
        # never paid off it would price the benefit of paying more at nothing.
        text += (" At these payments the debts are never paid off, so there is no fair "
                 "comparison with investing the money yet. Raise Extra each month first.")
    elif more > 0:
        effect = dv.retirement_effect(ov, more, age)
        rate = dv.real_return(ov)
        if effect is not None:
            if abs(effect) < 50:
                change = "about the same amount"
            else:
                change = f"about {money_md(abs(effect))} {'more' if effect > 0 else 'less'}"
            text += (f" Paying {money_md(more)} more a month would leave {change} at {age} "
                     f"(today's dollars) than investing it at about {rate * 100:.1f}% a year "
                     "after inflation. A quick estimate, not a simulation: debt above that rate "
                     "is worth paying off first, and payoff is a sure thing while market "
                     "returns are not.")
    st.caption(text)


def render(st, results: Optional[dict] = None) -> None:
    ov = st.session_state.get("user_overrides", {}) or {}
    today = date.today()
    if not dv.owing(ov):
        st.markdown('<div class="debt-empty">No debts in your plan. Add credit cards, student '
                    'loans and other debts in the <b>Debts</b> section of the side panel to see '
                    'when you&#39;ll be debt-free and what paying faster saves.</div>',
                    unsafe_allow_html=True)
        _things_to_know(st)
        return
    s = dv.summary(ov, today)
    st.markdown(stats_html(s, dv.extra(ov)), unsafe_allow_html=True)
    if not s.paid_off:
        st.warning("At these payments your debts aren't paid off within 50 years"
                   + (": the interest is more than the payments, so what you owe keeps growing. "
                      if s.growing else ". ")
                   + "Raise Extra each month in the Debts section.")
    if s.underwater:
        st.warning(f"The minimum on **{', '.join(s.underwater)}** doesn't cover its monthly "
                   "interest, so on its own that balance never shrinks.")
    if s.no_minimum:
        st.caption(f"**{', '.join(s.no_minimum)}** has no minimum payment and no interest, so only "
                   "extra money (or a minimum rolled over from another debt) pays it down.")

    st.markdown('<div class="debt-subhead">When each debt is paid off</div>', unsafe_allow_html=True)
    st.markdown(debts_html(s), unsafe_allow_html=True)

    st.markdown('<div class="debt-subhead">Avalanche or snowball</div>', unsafe_allow_html=True)
    cmp = dv.compare(ov, today)
    st.markdown(plans_html(cmp, dv.strategy(ov)), unsafe_allow_html=True)
    st.caption(verdict(cmp) + " Both pay the same each month; a paid-off debt's minimum rolls "
               "into the next one. Change the order in the Debts section.")

    _whatif(st, ov, today)
    _things_to_know(st)
