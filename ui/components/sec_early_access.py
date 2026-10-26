"""Section: Early-retirement access strategies.

Ways to reach retirement money before the normal 59.5 penalty age. Each is OFF
by default so the baseline plan is unchanged and each can be A/B tested on its
own, then layered.

Strategy 1 of the five — using a taxable brokerage as the bridge — needs no
toggle: the engine already draws taxable first (after cash) before 59.5, taxed at
long-term capital-gains rates with no penalty. It is surfaced here as a read-only
status line so the set of five reads as a complete menu rather than four.
"""
from __future__ import annotations

try:
    from utils.section_icon import section_expander
except ImportError:  # pragma: no cover
    from ui.utils.section_icon import section_expander  # type: ignore

try:
    from utils.coerce import safe_int, safe_float, ensure_default
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore

try:
    from utils.formatting import money
except ImportError:  # pragma: no cover
    from ui.utils.formatting import money  # type: ignore


def _md(text) -> str:
    """Escape "$" for Streamlit markdown.

    Streamlit renders $...$ as LaTeX, so two dollar amounts in one caption get
    swallowed into a math span (e.g. "$535K carve-out pays $30K/yr" rendered as
    "535.0K**carve-outpaysabout**30.0K"). Every interpolated money() value must go
    through this.
    """
    return str(text).replace("$", "\\$")


def _section_label(st, txt):
    st.markdown(f'<div style="font-size: 13px; font-weight: 700; color: var(--mc-ink); '
                f'text-transform: uppercase; letter-spacing: 0.05em; margin: 12px 0 6px 0;">{txt}</div>',
                unsafe_allow_html=True)


def _render_body(st) -> None:
    overrides = st.session_state.get("user_overrides", {}) or {}
    retire_age = safe_int(get_override(st, "TARGET_RETIREMENT_AGE", 60), 60)

    st.caption(
        "Retirement accounts normally charge a 10% penalty before age 59.5. "
        "These are the standard ways around it — turn them on one at a time to "
        "see what each is worth, then layer them."
    )

    # --- 1. Taxable brokerage (always on) -----------------------------------
    _section_label(st, "1 · Taxable brokerage bridge")
    taxable = (safe_float(get_override(st, "YOUR_BROKERAGE", 0), 0.0)
               + safe_float(get_override(st, "PARTNER_BROKERAGE", 0), 0.0)
               + safe_float(get_override(st, "YOUR_CASH", 0), 0.0)
               + safe_float(get_override(st, "PARTNER_CASH", 0), 0.0))
    st.caption(
        f":gray[Always active — no age limit and no penalty, just long-term "
        f"capital-gains tax. You currently hold **{_md(money(taxable, shorten=True))}** "
        f"in taxable + cash, which is what funds the years before any of the "
        f"strategies below are needed.]"
    )

    # --- 2. Rule of 55 -------------------------------------------------------
    _section_label(st, "2 · Rule of 55")
    ensure_default(st, "ea_rule55", bool(get_override(st, "RULE_OF_55_ENABLED", False)))
    v = st.toggle(
        "Use the Rule of 55", key="ea_rule55",
        help="Leave your employer during or after the year you turn 55 and that "
             "employer's 401(k) becomes penalty-free. IRAs do NOT qualify, and "
             "rolling the 401(k) into an IRA forfeits it.",
    )
    set_override(st, "RULE_OF_55_ENABLED", bool(v))
    if v:
        if retire_age >= 55:
            st.caption(f":gray[Retiring at {retire_age} — qualifies. Your 401(k) is "
                       f"penalty-free from {retire_age} instead of 59.5.]")
        else:
            st.warning(
                f"You're targeting retirement at **{retire_age}**, before 55, so this "
                f"does nothing — the exception needs you to leave the employer at 55+. "
                f"It applies only if you push retirement to 55 or later."
            )

    # --- 3. 72(t) SEPP -------------------------------------------------------
    _section_label(st, "3 · 72(t) SEPP")
    ensure_default(st, "ea_sepp", bool(get_override(st, "SEPP_72T_ENABLED", False)))
    v = st.toggle(
        "Take 72(t) equal periodic payments", key="ea_sepp",
        help="Fixed annual withdrawals from retirement accounts, penalty-free at "
             "any age. Once started they must continue for the longer of 5 years "
             "or until 59.5 — breaking the schedule retroactively penalizes every "
             "payment taken.",
    )
    set_override(st, "SEPP_72T_ENABLED", bool(v))
    if v:
        c1, c2 = st.columns(2)
        with c1:
            ensure_default(st, "ea_sepp_age",
                           safe_int(get_override(st, "SEPP_72T_START_AGE", retire_age), retire_age))
            a = st.number_input("Start age", min_value=25, max_value=70, step=1,
                                key="ea_sepp_age")
            set_override(st, "SEPP_72T_START_AGE", safe_int(a))
        with c2:
            ensure_default(st, "ea_sepp_rate",
                           safe_float(get_override(st, "SEPP_72T_RATE", 0.05), 0.05) * 100)
            r = st.number_input("Rate (%)", min_value=0.0, max_value=10.0, step=0.25,
                                key="ea_sepp_rate",
                                help="IRS allows the greater of 5% or 120% of the "
                                     "mid-term AFR for the amortization method.")
            set_override(st, "SEPP_72T_RATE", r / 100)
        start = safe_int(get_override(st, "SEPP_72T_START_AGE", retire_age), retire_age)
        rate = safe_float(get_override(st, "SEPP_72T_RATE", 0.05), 0.05)

        # Carve-out: the balance DESIGNATED for the schedule. Splitting a
        # sub-account off is the standard way to right-size a 72(t) — applying it
        # to the whole traditional balance forces a much larger mandatory draw and
        # crowds out voluntary Roth conversions using the same low brackets.
        ensure_default(st, "ea_sepp_carveout",
                       safe_int(get_override(st, "SEPP_72T_CARVEOUT", 0), 0))
        co = st.number_input(
            "Designated balance ($, 0 = entire traditional)",
            min_value=0, max_value=20_000_000, step=25_000, key="ea_sepp_carveout",
            help="Split this much of your traditional savings into a separate IRA "
                 "for the 72(t). The payment is computed only on this amount, and "
                 "the rest stays outside the schedule — no 5-year lock-in and "
                 "still available for Roth conversions.",
        )
        set_override(st, "SEPP_72T_CARVEOUT", safe_int(co))

        try:
            from retirement_sim import config as _cfg
            if co > 0:
                pay = _cfg.sepp_72t_annual_amount(co, start, rate)
                st.caption(
                    f":gray[A **{_md(money(co, shorten=True))}** carve-out pays about "
                    f"**{_md(money(pay, shorten=True))}/yr** from age {start}. "
                    f"Rule of thumb: about "
                    f"**{_md(money(_cfg.sepp_72t_balance_for_payment(50_000, start, rate), shorten=True))}** "
                    f"designated per \\$50k/yr of bridge income you need.]"
                )
            else:
                st.warning(
                    "**0 designates your whole traditional balance** — an all-or-nothing "
                    "72(t). That forces the largest possible mandatory draw and "
                    "competes with your Roth conversions for the same low tax "
                    "brackets. Enter only the amount you actually need to bridge."
                )
        except Exception:
            pass

        locked_until = max(start + 5, 60)
        st.caption(f":gray[Locked in until about age {locked_until} "
                   f"(the longer of 5 years or 59.5). The annual amount is fixed "
                   f"at the start age from the designated balance — it does not "
                   f"flex if markets move.]")

    # --- 4. Roth conversion ladder ------------------------------------------
    _section_label(st, "4 · Roth conversion ladder")
    ensure_default(st, "ea_ladder", bool(get_override(st, "ROTH_LADDER_ENABLED", False)))
    v = st.toggle(
        "Enforce the 5-year conversion ladder", key="ea_ladder",
        help="Converted principal becomes withdrawable tax- and penalty-free 5 "
             "years after each conversion. Turning this ON makes the model track "
             "conversions as dated cohorts and enforce that waiting period — "
             "stricter, and more realistic, than assuming Roth money is always "
             "reachable.",
    )
    set_override(st, "ROTH_LADDER_ENABLED", bool(v))
    conversions_on = bool(get_override(st, "ENABLE_ROTH_CONVERSION", True))
    if v and not conversions_on:
        st.warning(
            "The ladder has nothing to climb: **Roth conversion** is switched off "
            "under Assumptions → Roth conversion. Turn it on to actually build the "
            "rungs."
        )
    elif v:
        st.caption(":gray[Each year's conversion unlocks 5 years later, so the "
                   "first rung needs to be built 5 years before you retire.]")

    # --- 5. Coast FIRE -------------------------------------------------------
    _section_label(st, "5 · Coast FIRE")
    ensure_default(st, "ea_coast", bool(get_override(st, "COAST_FIRE_ENABLED", False)))
    v = st.toggle(
        "Coast from a chosen age", key="ea_coast",
        help="Stop saving but keep working enough to cover expenses. The portfolio "
             "compounds untouched — no new contributions, no withdrawals — until "
             "your real retirement age.",
    )
    set_override(st, "COAST_FIRE_ENABLED", bool(v))
    if v:
        # Default to a coast age that actually DOES something for this household:
        # midway between today and retirement. A fixed default (45) silently
        # landed past an early retirement target, so the control opened on a
        # guaranteed no-op.
        your_age = safe_int(get_override(st, "YOUR_AGE", 30), 30)
        suggested = max(your_age + 1, retire_age - max(2, (retire_age - your_age) // 2))
        ensure_default(st, "ea_coast_age",
                       safe_int(get_override(st, "COAST_FIRE_AGE", suggested), suggested))
        a = st.number_input("Coast from age", min_value=25, max_value=70, step=1,
                            key="ea_coast_age")
        set_override(st, "COAST_FIRE_AGE", safe_int(a))
        coast_age = safe_int(a)
        if coast_age >= retire_age:
            st.caption(f":gray[Coasting from {coast_age} has no effect — you already "
                       f"retire at {retire_age}.]")
        else:
            st.caption(f":gray[Saving stops at {coast_age}; you keep covering "
                       f"expenses until {retire_age}, so the portfolio grows on "
                       f"compounding alone for {retire_age - coast_age} years.]")


def render(st) -> None:
    with section_expander(st, "Early retirement access", "lock_open"):
        _render_body(st)
