"""Section 6: Retirement goals — spending, SS, success threshold."""
from __future__ import annotations

try:
    from retirement_sim import config as cfg
except ImportError:  # pragma: no cover
    cfg = None  # type: ignore

try:
    from utils.coerce import safe_int, safe_float, ensure_default
    from utils.formatting import money, money_md, pct
    from utils.household import plan_end_ages
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money, money_md, pct  # type: ignore
    from ui.utils.household import plan_end_ages  # type: ignore

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore


def _section_label(st, txt):
    st.markdown(f'<div style="font-size: 13px; color: #64748b; text-transform: uppercase; '
                f'letter-spacing: 0.05em; margin: 12px 0 6px 0;">{txt}</div>',
                unsafe_allow_html=True)


def _ss_factor(claim_age: int) -> float:
    """Factor applied to FRA monthly benefit for early/delayed claiming (the
    engine's own rule, cfg.ss_claim_factor)."""
    if cfg is not None:
        return float(cfg.ss_claim_factor(claim_age))
    if claim_age >= 70:  # pragma: no cover - engine not importable
        return 1.24
    if claim_age >= 67:  # pragma: no cover
        return 1.0 + 0.08 * (claim_age - 67)
    return 0.70 + (1.0 - 0.70) * (claim_age - 62) / 5.0  # pragma: no cover


def _lifestyle(st, overrides: dict) -> None:
    """Go-go years extra and the later-years drop (cfg.EARLY_RETIREMENT_LEISURE_*,
    LATE_RETIREMENT_*). The extra follows household size until you change it."""
    _section_label(st, "Early and later retirement")
    adults = 2 if safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0 else 1
    auto = int(round(cfg.default_retirement_leisure(adults))) if cfg else 10_000
    if get_override(st, "EARLY_RETIREMENT_LEISURE_INCREASE", None) is None:
        st.session_state["rg_leisure_amount"] = auto       # not chosen yet: follow the household

    def _chosen():
        set_override(st, "EARLY_RETIREMENT_LEISURE_INCREASE",
                     safe_int(st.session_state.get("rg_leisure_amount"), auto))

    c1, c2 = st.columns(2)
    with c1:
        st.number_input("Extra for travel and hobbies ($/yr)", min_value=0, max_value=200_000,
                        step=1_000, key="rg_leisure_amount", on_change=_chosen,
                        help="Most people spend more in the first years of retirement. "
                             "Starts at about $10,000 a year for a couple, two-thirds of "
                             "that for one person.")
    with c2:
        ensure_default(st, "rg_leisure_until",
                       safe_int(get_override(st, "EARLY_RETIREMENT_LEISURE_UNTIL_AGE", 70), 70))
        v = st.number_input("Until age", min_value=50, max_value=100, step=1,
                            key="rg_leisure_until")
        set_override(st, "EARLY_RETIREMENT_LEISURE_UNTIL_AGE", safe_int(v))
    c3, c4 = st.columns(2)
    with c3:
        ensure_default(st, "rg_late_pct", int(round(safe_float(
            get_override(st, "LATE_RETIREMENT_LEISURE_DECREASE", 0.15), 0.15) * 100)))
        v = st.slider("Spend less later (%)", min_value=0, max_value=50, step=5,
                      key="rg_late_pct",
                      help="Day-to-day spending usually falls as you age. Housing "
                           "costs stay the same.")
        set_override(st, "LATE_RETIREMENT_LEISURE_DECREASE", v / 100)
    with c4:
        ensure_default(st, "rg_late_from",
                       safe_int(get_override(st, "LATE_RETIREMENT_START_AGE", 75), 75))
        v = st.number_input("From age", min_value=55, max_value=100, step=1,
                            key="rg_late_from")
        set_override(st, "LATE_RETIREMENT_START_AGE", safe_int(v))

    # The ages the engine will actually use for the retirement age you're planning.
    ret = safe_int(get_override(st, "TARGET_RETIREMENT_AGE", 60), 60)
    amount = get_override(st, "EARLY_RETIREMENT_LEISURE_INCREASE", None)
    amount = auto if amount is None else safe_int(amount)
    end = max(safe_int(get_override(st, "EARLY_RETIREMENT_LEISURE_UNTIL_AGE", 70), 70),
              ret + safe_int(getattr(cfg, "RETIREMENT_LEISURE_MIN_YEARS", 5), 5))
    late = max(safe_int(get_override(st, "LATE_RETIREMENT_START_AGE", 75), 75),
               ret + safe_int(getattr(cfg, "LATE_RETIREMENT_MIN_YEARS", 10), 10))
    pct_less = safe_float(get_override(st, "LATE_RETIREMENT_LEISURE_DECREASE", 0.15), 0.15)
    extra = (f"extra {money_md(amount)}/yr until {end}" if amount > 0 and end > ret
             else "no extra spending")
    st.caption(f"Retiring at {ret}: {extra}, then {pct_less:.0%} less from {late} "
               "(housing excluded). A late retirement still gets 5 years of extra, "
               "and the drop waits until 10 years after you retire.")


def render_body(st) -> None:
    overrides = st.session_state.get("user_overrides", {}) or {}

    # ----- Retirement spending -----
    _section_label(st, "Retirement spending")
    modes = ["Same as today's expenses", "% of today's expenses", "Absolute amount ($/yr)"]
    current_mode = str(get_override(st, "RETIREMENT_SPENDING_MODE", modes[0]))
    if current_mode not in modes:
        current_mode = modes[0]
    ensure_default(st, "rg_spend_mode", current_mode)
    mode = st.radio("How much will you spend in retirement?", modes, key="rg_spend_mode",
                    help="Most retirees spend ~70-100% of pre-retirement expenses: "
                         "healthcare rises, commute/work costs fall.")
    set_override(st, "RETIREMENT_SPENDING_MODE", mode)

    if mode == "% of today's expenses":
        ensure_default(st, "rg_spend_pct",
                       safe_float(get_override(st, "RETIREMENT_SPENDING_PCT", 0.80), 0.80) * 100)
        v = st.slider("Retirement spending (% of today's)", min_value=50.0,
                      max_value=150.0, step=5.0, key="rg_spend_pct")
        set_override(st, "RETIREMENT_SPENDING_PCT", v / 100)
        st.caption(f"= {v:.0f}% of current annual expenses, inflated each year.")
    elif mode == "Absolute amount ($/yr)":
        ensure_default(st, "rg_spend_abs",
                       safe_int(get_override(st, "RETIREMENT_SPENDING_ABSOLUTE", 60_000), 60_000))
        v = st.number_input("Annual retirement spending ($)", min_value=0,
                            max_value=1_000_000, step=1_000, key="rg_spend_abs")
        set_override(st, "RETIREMENT_SPENDING_ABSOLUTE", safe_int(v))
        st.caption(f"= {money(safe_int(v), shorten=True)}/yr in today's dollars, "
                   f"inflated each year.")
    else:
        st.caption("Same as today's expenses, inflation-adjusted each year.")

    _lifestyle(st, overrides)

    # ----- Social Security -----
    _section_label(st, "Social Security")
    has_partner = safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0

    ensure_default(st, "rg_ss_include",
                   bool(get_override(st, "INCLUDE_SOCIAL_SECURITY", True)))
    include = st.toggle("Include Social Security",
                          key="rg_ss_include",
                          help="Stress-test what happens if SS is reduced or eliminated.")
    set_override(st, "INCLUDE_SOCIAL_SECURITY", bool(include))

    ensure_default(st, "rg_ss_claim",
                   safe_int(get_override(st, "SS_CLAIM_AGE", 67), 67))
    claim_age = st.slider("Your claim age" if has_partner else "Claim age",
                          min_value=62, max_value=70, step=1,
                          key="rg_ss_claim",
                          help="62 = earliest (about 30% less if your full retirement age is 67). "
                               "67 = full retirement age. "
                               "70 = delayed (+24% credit).")
    set_override(st, "SS_CLAIM_AGE", safe_int(claim_age))
    partner_claim = claim_age
    if has_partner:
        ensure_default(st, "rg_partner_ss_claim",
                       safe_int(get_override(st, "PARTNER_SS_CLAIM_AGE", None) or claim_age,
                                claim_age))
        partner_claim = st.slider("Partner's claim age", min_value=62, max_value=70, step=1,
                                  key="rg_partner_ss_claim",
                                  help="When your partner starts, in their own age.")
        set_override(st, "PARTNER_SS_CLAIM_AGE", safe_int(partner_claim))
    else:
        set_override(st, "PARTNER_SS_CLAIM_AGE", None)

    c1, c2 = st.columns(2)
    with c1:
        ensure_default(st, "rg_your_fra",
                       safe_int(get_override(st, "YOUR_SS_MONTHLY_FRA", 2_000), 2_000))
        v = st.number_input("Your monthly benefit at FRA ($)",
                            min_value=0, max_value=5_000, step=50,
                            key="rg_your_fra",
                            help="Find yours at https://www.ssa.gov/myaccount. "
                                 "Average retired-worker benefit is ~$1,900/mo.")
        set_override(st, "YOUR_SS_MONTHLY_FRA", safe_int(v))
    with c2:
        if has_partner:
            ensure_default(st, "rg_partner_fra",
                           safe_int(get_override(st, "PARTNER_SS_MONTHLY_FRA", 1_800), 1_800))
            v = st.number_input("Partner monthly at FRA ($)",
                                min_value=0, max_value=5_000, step=50,
                                key="rg_partner_fra")
            set_override(st, "PARTNER_SS_MONTHLY_FRA", safe_int(v))
        else:
            set_override(st, "PARTNER_SS_MONTHLY_FRA", 0)

    # Live preview of household SS once each person has claimed
    factor = _ss_factor(claim_age)
    your_fra = safe_int(get_override(st, "YOUR_SS_MONTHLY_FRA", 2_000), 2_000)
    partner_fra = safe_int(get_override(st, "PARTNER_SS_MONTHLY_FRA", 0), 0) if has_partner else 0
    annual_ss = (your_fra * factor + partner_fra * _ss_factor(partner_claim)) * 12
    if has_partner and cfg is not None and str(get_override(st, "FILING_STATUS", "")) in (
            "Married filing jointly", "MFJ"):
        # Spousal top-up once both have claimed (full rule: cfg.calculate_social_security).
        annual_ss += 12 * (max(0, your_fra / 2 - partner_fra) * cfg.ss_spousal_factor(partner_claim)
                           + max(0, partner_fra / 2 - your_fra) * cfg.ss_spousal_factor(claim_age))
    if include and annual_ss > 0:
        st.caption(
            (f"At age {claim_age} (**{factor:.0%}** of FRA): " if not has_partner else
             "Once you've both claimed: ")
            + f"household SS ≈ {money_md(annual_ss, shorten=True)}/yr "
            f"({money_md(annual_ss / 12, shorten=True)}/mo combined)."
        )

    # ----- Long-term care -----
    _section_label(st, "Long-term care")
    ensure_default(st, "rg_ltc_enabled",
                   bool(get_override(st, "LTC_ENABLED",
                                     getattr(cfg, "LTC_ENABLED", True) if cfg else True)))
    ltc_on = st.toggle(
        "Model long-term care costs",
        key="rg_ltc_enabled",
        help="Adds the risk of large end-of-life care costs (nursing home / in-home "
             "care) at advanced ages. Each year from the start age has a set chance of "
             "incurring the annual cost, drawn independently per year in the Monte "
             "Carlo, inflated over time and scaled up ~15% at 87+ and ~25% at 90+. On "
             "by default; uncheck if you have LTC insurance or expect family care.",
    )
    set_override(st, "LTC_ENABLED", bool(ltc_on))
    if ltc_on:
        ensure_default(st, "rg_ltc_start",
                       safe_int(get_override(st, "LTC_START_AGE",
                                             getattr(cfg, "LTC_START_AGE", 83) if cfg else 83), 83))
        start = st.slider("Care starts around age", min_value=70, max_value=95, step=1,
                          key="rg_ltc_start")
        set_override(st, "LTC_START_AGE", safe_int(start))

        ensure_default(st, "rg_ltc_cost",
                       safe_int(get_override(st, "LTC_ANNUAL_COST",
                                             getattr(cfg, "LTC_ANNUAL_COST", 120_000) if cfg else 120_000),
                                120_000))
        cost = st.number_input("Annual care cost ($, today's dollars)", min_value=0,
                               step=5_000, key="rg_ltc_cost",
                               help="Median U.S. nursing-home care runs ~$105k-120k/yr today "
                                    "(Genworth). The engine inflates this to the year care is "
                                    "actually incurred, so the modeled cost reflects real "
                                    "future prices.")
        set_override(st, "LTC_ANNUAL_COST", safe_int(cost))

        ensure_default(st, "rg_ltc_prob",
                       max(0, min(100, int(round(
                           safe_float(get_override(st, "LTC_PROBABILITY",
                                                   getattr(cfg, "LTC_PROBABILITY", 0.20) if cfg else 0.20),
                                      0.20) * 100)))))
        prob = st.slider("Chance of needing care each year (%)", min_value=0, max_value=100,
                         step=5, key="rg_ltc_prob",
                         help="Chance of incurring the cost in any year from the start "
                              "age (independent per year). Lower it if you have LTC "
                              "insurance or expect family care.")
        set_override(st, "LTC_PROBABILITY", prob / 100)

        # Rough exposure preview (before inflation / age scaling).
        plan_until = plan_end_ages(st.session_state.get("user_overrides", {}) or {})[0]
        exp_years = max(0, plan_until - safe_int(start) + 1) * (prob / 100)
        st.caption(
            f"≈ **{exp_years:.1f}** expected care-years over the plan at "
            f"{money_md(safe_int(cost), shorten=True)}/yr "
            f"(≈ {money_md(exp_years * safe_int(cost), shorten=True)} total, before "
            f"inflation & age scaling)."
        )

    # ----- Success threshold -----
    _section_label(st, "Plan success threshold")
    current_thr = safe_float(get_override(st, "TARGET_SUCCESS_RATE", 0.80), 0.80)
    ensure_default(st, "rg_target_success",
                   max(70, min(95, int(round(current_thr * 100)))))
    v = st.slider("Target success rate (%)", min_value=70, max_value=95, step=1,
                  key="rg_target_success",
                  help="Plan succeeds if this fraction of Monte Carlo simulations "
                       "don't run out of money. 80% is a common default; FIRE often "
                       "targets 90-95%.")
    set_override(st, "TARGET_SUCCESS_RATE", v / 100)


def render(st) -> None:
    with st.expander("Retirement goals", expanded=False, icon=":material/flag:"):
        render_body(st)
