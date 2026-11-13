"""Retirement — when you retire, spending, Social Security, long-term care, success target,
and early retirement access (Rule of 55, 72(t), Roth ladder, Coast FIRE) at the end."""
from __future__ import annotations

try:
    from utils.section_icon import section_expander
except ImportError:  # pragma: no cover
    from ui.utils.section_icon import section_expander  # type: ignore

try:
    from retirement_sim import config as cfg
except ImportError:  # pragma: no cover
    cfg = None  # type: ignore

try:
    from utils.coerce import safe_int, safe_float, ensure_default
    from utils.formatting import money, money_md, pct
    from utils.household import plan_end_ages
    from utils.derived import RETIREMENT_SPENDING_MODES
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money, money_md, pct  # type: ignore
    from ui.utils.household import plan_end_ages  # type: ignore
    from ui.utils.derived import RETIREMENT_SPENDING_MODES  # type: ignore

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore

try:
    from utils.age_limits import AGE_MIN, AGE_MAX, TARGET_MIN, TARGET_MAX, PLAN_UNTIL_MIN, PLAN_UNTIL_MAX
except ImportError:  # pragma: no cover
    from ui.utils.age_limits import (AGE_MIN, AGE_MAX, TARGET_MIN, TARGET_MAX,  # type: ignore
                                     PLAN_UNTIL_MIN, PLAN_UNTIL_MAX)

try:
    from utils.slider_input import slider_with_box, forget_box
except ImportError:  # pragma: no cover
    from ui.utils.slider_input import slider_with_box, forget_box  # type: ignore

LATER_NOTE = "ay_partner_later__note"      # (age used, sentence) after a typed gap was moved into range


def _move_partner_retirement(st, target: int, age_gap: int) -> None:
    """Number-box callback: the partner retires ``ay_partner_later`` years after you,
    which moves their own-age slider (the engine stores their age, not the gap)."""
    ss = st.session_state
    n = int(ss.get("ay_partner_later", 0) or 0)
    want = target - age_gap + n
    age = max(TARGET_MIN, min(TARGET_MAX, want))       # the same range as the slider
    ss["ay_partner_target_age"] = age
    ss.pop(LATER_NOTE, None)
    if age != want:
        ss[LATER_NOTE] = (age, f"A retirement age can only be {TARGET_MIN} to {TARGET_MAX}, "
                               f"so {age} was used.")
    forget_box(st, "ay_partner_target_age")


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
    """Early-retirement extra and the later-years drop (cfg.EARLY_RETIREMENT_LEISURE_*,
    LATE_RETIREMENT_*). The extra follows household size until you change it."""
    _section_label(st, "Early and later retirement")
    adults = 2 if safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0 else 1
    auto = int(round(cfg.default_retirement_leisure(adults))) if cfg else 10_000
    if get_override(st, "EARLY_RETIREMENT_LEISURE_INCREASE", None) is None:
        st.session_state["rg_leisure_amount"] = auto       # not chosen yet: follow the household

    def _chosen():
        set_override(st, "EARLY_RETIREMENT_LEISURE_INCREASE",
                     safe_int(st.session_state.get("rg_leisure_amount"), auto))

    c1, c2 = st.columns(2, vertical_alignment="bottom")
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
    ensure_default(st, "rg_late_pct", int(round(safe_float(
        get_override(st, "LATE_RETIREMENT_LEISURE_DECREASE", 0.15), 0.15) * 100)))
    v = slider_with_box(st, "Spend less later (%)", 0, 50, 5, key="rg_late_pct", unit="%",
                        help="Day-to-day spending usually falls as you age. Housing "
                             "costs stay the same.")
    set_override(st, "LATE_RETIREMENT_LEISURE_DECREASE", v / 100)
    ensure_default(st, "rg_late_from",
                   safe_int(get_override(st, "LATE_RETIREMENT_START_AGE", 75), 75))
    v = st.number_input("Spend less from age", min_value=55, max_value=100, step=1,
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


def render_retirement_ages(st) -> None:
    """Your target retirement age and, when there is a partner, theirs (moved here
    from About you). Same widget keys as before, so saved profiles load unchanged."""
    your_age = safe_int(get_override(st, "YOUR_AGE", 30), 30)
    has_partner = safe_int(get_override(st, "PARTNER_AGE", 0), 0) > 0
    ensure_default(st, "ay_target_age",
                   safe_int(get_override(st, "TARGET_RETIREMENT_AGE", 60), 60))
    target = slider_with_box(st, "Target retirement age", TARGET_MIN, TARGET_MAX,
                       1, key="ay_target_age",
                       help="When you plan to stop working.")
    set_override(st, "TARGET_RETIREMENT_AGE", safe_int(target))
    if target < your_age:
        st.warning(
            f"Your target retirement age ({target}) is below your current age ({your_age}). "
            "Raise it to at least your age to run the plan."
        )

    # Partner's own retirement age (only when a partner exists). Independent of
    # yours: the partner can keep working after you retire, or stop earlier. The
    # default is the partner's age in the year YOU retire (i.e. "retire together"),
    # which the engine treats identically to the single-switch default -- so this
    # is a no-op until the user actually moves it apart.
    partner_age = safe_int(get_override(st, "PARTNER_AGE", 0), 0)
    if has_partner:
        age_gap = your_age - partner_age  # your_age - partner_age
        # "Retire together" = the partner's age in the year YOU retire. When that
        # lands outside the slider's range (a large age gap), it can't be
        # represented on the slider, so we KEEP the byte-identical None default
        # (retire together) until the user deliberately moves the slider -- rather
        # than storing the clamped value, which would wrongly retire the partner
        # early/late and diverge from the "retire together" intent.
        together_raw = target - age_gap
        together_in_range = TARGET_MIN <= together_raw <= TARGET_MAX
        slider_default = max(TARGET_MIN, min(TARGET_MAX, together_raw))
        ensure_default(st, "ay_partner_target_age",
                       safe_int(get_override(st, "PARTNER_RETIREMENT_AGE", None) or slider_default,
                                slider_default))
        p_target = slider_with_box(st, "Partner's retirement age", TARGET_MIN, TARGET_MAX,
                             1, key="ay_partner_target_age",
                             help="Your partner's age when they stop working. Set it apart "
                                  "from yours if one of you retires first. The other keeps "
                                  "earning and saving, and their take-home pay offsets "
                                  "withdrawals.")
        keep_none = not together_in_range and p_target == slider_default
        # "N years after you" is how people think of it; the slider is in their own age.
        st.session_state["ay_partner_later"] = 0 if keep_none else safe_int(p_target) + age_gap - target
        # No min/max on the box: Streamlit would refuse a typed value past them without
        # a word. The callback moves it into the slider's range and says so.
        st.number_input("Partner retires this many years after you", step=1, key="ay_partner_later",
                        help="0 means the same year as you. A negative number means they "
                             "retire first. It moves the partner's retirement age above.",
                        on_change=_move_partner_retirement, args=(st, target, age_gap))
        note = st.session_state.get(LATER_NOTE)
        if note and note[0] == p_target:
            st.caption(note[1])
        if keep_none:
            # "Retire together" isn't representable on the slider and the user
            # hasn't moved it -> keep None so results match the retire-together default.
            set_override(st, "PARTNER_RETIREMENT_AGE", None)
            st.caption("Partner retires the same year you do.")
        else:
            set_override(st, "PARTNER_RETIREMENT_AGE", safe_int(p_target))
            # Translate the partner's retirement age into "N years before/after you"
            # by comparing the years each retires (partner reaches p_target when
            # your age is p_target + age_gap).
            your_year_partner_retires = p_target + age_gap
            gap_vs_you = your_year_partner_retires - target
            if gap_vs_you == 0:
                st.caption(f"Partner retires at {p_target}, the same year you do.")
            else:
                when = "after you" if gap_vs_you > 0 else "before you"
                n = abs(gap_vs_you)
                st.caption(f"Partner retires at {p_target}, {n} year{'' if n == 1 else 's'} {when}.")
            if p_target < partner_age:
                st.warning(
                    f"Partner's retirement age ({p_target}) is below their current age "
                    f"({partner_age}), so they count as already retired."
                )


def render_body(st) -> None:
    # ----- When you retire -----
    _section_label(st, "When you retire")
    render_retirement_ages(st)
    overrides = st.session_state.get("user_overrides", {}) or {}

    # ----- Retirement spending -----
    _section_label(st, "Retirement spending")
    modes = RETIREMENT_SPENDING_MODES
    current_mode = str(get_override(st, "RETIREMENT_SPENDING_MODE", modes[0]))
    if current_mode not in modes:
        current_mode = modes[0]
    ensure_default(st, "rg_spend_mode", current_mode)
    mode = st.radio("How much will you spend in retirement?", modes, key="rg_spend_mode",
                    help="Most retirees spend about 70-100% of what they spent while "
                         "working. Healthcare costs rise and work costs fall.")
    set_override(st, "RETIREMENT_SPENDING_MODE", mode)

    if mode == "% of today's expenses":
        ensure_default(st, "rg_spend_pct",
                       safe_float(get_override(st, "RETIREMENT_SPENDING_PCT", 0.80), 0.80) * 100)
        v = slider_with_box(st, "Retirement spending (% of today's)", 50.0, 150.0, 5.0,
                            key="rg_spend_pct", unit="%",
                            help="What you plan to spend each year in retirement, as a share "
                                 "of what you spend today. 100% means the same.")
        set_override(st, "RETIREMENT_SPENDING_PCT", v / 100)
        st.caption(f"= {v:.0f}% of your current yearly expenses, rising with inflation.")
    elif mode == "Absolute amount ($/yr)":
        ensure_default(st, "rg_spend_abs",
                       safe_int(get_override(st, "RETIREMENT_SPENDING_ABSOLUTE", 60_000), 60_000))
        v = st.number_input("Annual retirement spending ($)", min_value=0,
                            max_value=1_000_000, step=1_000, key="rg_spend_abs")
        set_override(st, "RETIREMENT_SPENDING_ABSOLUTE", safe_int(v))
        st.caption(f"= {money(safe_int(v), shorten=True)}/yr in today's dollars, "
                   f"rising with inflation each year.")
    else:
        st.caption("Same as today's expenses, rising with inflation each year.")

    _lifestyle(st, overrides)

    # ----- Social Security -----
    _section_label(st, "Social Security")
    has_partner = safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0

    ensure_default(st, "rg_ss_include",
                   bool(get_override(st, "INCLUDE_SOCIAL_SECURITY", True)))
    include = st.toggle("Include Social Security",
                          key="rg_ss_include",
                          help="Turn off to see your plan without Social Security.")
    set_override(st, "INCLUDE_SOCIAL_SECURITY", bool(include))

    ensure_default(st, "rg_ss_claim",
                   safe_int(get_override(st, "SS_CLAIM_AGE", 67), 67))
    claim_age = slider_with_box(st, "Your claim age" if has_partner else "Claim age",
                          62, 70, 1,
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
        partner_claim = slider_with_box(st, "Partner's claim age", 62, 70, 1,
                                  key="rg_partner_ss_claim",
                                  help="The age your partner starts claiming.")
        set_override(st, "PARTNER_SS_CLAIM_AGE", safe_int(partner_claim))
    else:
        set_override(st, "PARTNER_SS_CLAIM_AGE", None)

    c1, c2 = st.columns(2, vertical_alignment="bottom")
    with c1:
        ensure_default(st, "rg_your_fra",
                       safe_int(get_override(st, "YOUR_SS_MONTHLY_FRA", 2_000), 2_000))
        v = st.number_input("Your monthly benefit ($)",
                            min_value=0, max_value=5_000, step=50,
                            key="rg_your_fra",
                            help="Your monthly benefit at full retirement age. Find yours at "
                                 "https://www.ssa.gov/myaccount. The average is about $1,900/mo.")
        set_override(st, "YOUR_SS_MONTHLY_FRA", safe_int(v))
    with c2:
        if has_partner:
            ensure_default(st, "rg_partner_fra",
                           safe_int(get_override(st, "PARTNER_SS_MONTHLY_FRA", 1_800), 1_800))
            v = st.number_input("Partner's monthly benefit ($)",
                                help="Their monthly benefit at full retirement age.",
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
            (f"At age {claim_age} (**{factor:.0%}** of your full-age benefit): " if not has_partner else
             "Once you've both claimed: ")
            + f"your Social Security ≈ {money_md(annual_ss, shorten=True)}/yr "
            f"({money_md(annual_ss / 12, shorten=True)}/mo{' combined' if has_partner else ''})."
        )
    if include:
        st.caption(
            "Full retirement age is 67 for everyone, which is right if you were born in 1960 or later. "
            "The model does not pay a survivor benefit. It assumes both of you live to the end of the plan. "
            "If you are a widow or widower, enter the benefit you get now as your own full-age amount."
            if has_partner else
            "Full retirement age is 67, which is right if you were born in 1960 or later. "
            "If you are a widow or widower, enter the benefit you get now as your full-age amount. "
            "The model does not change it."
        )

    # ----- Long-term care -----
    _section_label(st, "Long-term care")
    ensure_default(st, "rg_ltc_enabled",
                   bool(get_override(st, "LTC_ENABLED",
                                     getattr(cfg, "LTC_ENABLED", True) if cfg else True)))
    ltc_on = st.toggle(
        "Model long-term care costs",
        key="rg_ltc_enabled",
        help="Adds the risk of a big care bill late in life (nursing home or in-home "
             "care). From the start age, each year has a set chance of the annual cost, "
             "which grows with inflation and is ~15% higher at 87+ and ~25% higher at "
             "90+. Turn off if you have LTC insurance or expect family care.",
    )
    set_override(st, "LTC_ENABLED", bool(ltc_on))
    if ltc_on:
        ensure_default(st, "rg_ltc_start",
                       safe_int(get_override(st, "LTC_START_AGE",
                                             getattr(cfg, "LTC_START_AGE", 83) if cfg else 83), 83))
        start = slider_with_box(st, "Care starts around age", 70, 95, 1,
                                key="rg_ltc_start",
                                help="The age from which each year carries a chance of a care bill.")
        set_override(st, "LTC_START_AGE", safe_int(start))

        ensure_default(st, "rg_ltc_cost",
                       safe_int(get_override(st, "LTC_ANNUAL_COST",
                                             getattr(cfg, "LTC_ANNUAL_COST", 120_000) if cfg else 120_000),
                                120_000))
        cost = st.number_input("Annual care cost ($, today's dollars)", min_value=0,
                               step=5_000, key="rg_ltc_cost",
                               help="Nursing-home care costs about $105k-120k/yr today "
                                    "(Genworth median). The plan raises it with inflation "
                                    "to the year care is needed.")
        set_override(st, "LTC_ANNUAL_COST", safe_int(cost))

        ensure_default(st, "rg_ltc_prob",
                       max(0, min(100, int(round(
                           safe_float(get_override(st, "LTC_PROBABILITY",
                                                   getattr(cfg, "LTC_PROBABILITY", 0.20) if cfg else 0.20),
                                      0.20) * 100)))))
        prob = slider_with_box(st, "Chance of needing care each year (%)", 0, 100,
                         5, key="rg_ltc_prob", unit="%",
                         help="Chance of paying the cost in any one year from the start "
                              "age. Lower it if you have LTC insurance or expect "
                              "family care.")
        set_override(st, "LTC_PROBABILITY", prob / 100)

        # Rough exposure preview (before inflation / age scaling).
        plan_until = plan_end_ages(st.session_state.get("user_overrides", {}) or {})[0]
        exp_years = max(0, plan_until - safe_int(start) + 1) * (prob / 100)
        st.caption(
            f"About **{exp_years:.1f}** expected years of care at "
            f"{money_md(safe_int(cost), shorten=True)}/yr, roughly "
            f"{money_md(exp_years * safe_int(cost), shorten=True)} total before "
            f"inflation and age increases."
        )

    # ----- Success threshold -----
    _section_label(st, "Success target")
    current_thr = safe_float(get_override(st, "TARGET_SUCCESS_RATE", 0.80), 0.80)
    ensure_default(st, "rg_target_success",
                   max(70, min(95, int(round(current_thr * 100)))))
    v = slider_with_box(st, "Success target (%)", 70, 95, 1,
                  key="rg_target_success", unit="%",
                  help="Your plan counts as a success if the money lasts in at least this "
                       "share of simulated futures. 80% is a common default; "
                       "early retirees often aim for 90-95%.")
    set_override(st, "TARGET_SUCCESS_RATE", v / 100)

    # ----- Early retirement access -----
    # Last on purpose: it reads the retirement age and the balances and savings
    # drawn above it this run.
    try:
        from components import sec_early_access
    except ImportError:  # pragma: no cover
        from ui.components import sec_early_access  # type: ignore
    st.divider()
    _section_label(st, "Early retirement access")
    sec_early_access.render_body(st)


def render(st) -> None:
    with section_expander(st, "Retirement", "flag"):
        render_body(st)
