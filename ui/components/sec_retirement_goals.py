"""Section 6: Retirement goals — spending, SS, success threshold."""
from __future__ import annotations

try:
    from retirement_sim import config as cfg
except ImportError:  # pragma: no cover
    cfg = None  # type: ignore

try:
    from utils.coerce import safe_int, safe_float, ensure_default
    from utils.formatting import money, money_md, pct
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money, money_md, pct  # type: ignore

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore


def _section_label(st, txt):
    st.markdown(f'<div style="font-size: 13px; color: #64748b; text-transform: uppercase; '
                f'letter-spacing: 0.05em; margin: 12px 0 6px 0;">{txt}</div>',
                unsafe_allow_html=True)


def _ss_factor(claim_age: int) -> float:
    """Factor applied to FRA monthly benefit for early/delayed claiming."""
    if claim_age >= 70:
        return 1.24
    if claim_age >= 67:
        return 1.0 + 0.08 * (claim_age - 67)
    if claim_age == 62:
        return 0.70
    # Linear interp 62-67
    return 0.70 + (1.0 - 0.70) * (claim_age - 62) / 5.0


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
    claim_age = st.slider("Claim age", min_value=62, max_value=70, step=1,
                          key="rg_ss_claim",
                          help="62 = early (30% reduction). 67 = full retirement age. "
                               "70 = delayed (+24% credit).")
    set_override(st, "SS_CLAIM_AGE", safe_int(claim_age))

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

    # Live preview of household SS at claim age
    factor = _ss_factor(claim_age)
    your_fra = safe_int(get_override(st, "YOUR_SS_MONTHLY_FRA", 2_000), 2_000)
    partner_fra = safe_int(get_override(st, "PARTNER_SS_MONTHLY_FRA", 0), 0) if has_partner else 0
    annual_ss = (your_fra + partner_fra) * 12 * factor
    if include and annual_ss > 0:
        st.caption(
            f"At age {claim_age} (**{factor:.0%}** of FRA): "
            f"household SS ≈ {money_md(annual_ss, shorten=True)}/yr "
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
        plan_until = safe_int(get_override(st, "PLAN_UNTIL_AGE", 90), 90)
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
