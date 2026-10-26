"""Section 1: About you — household composition + planning horizon."""
from __future__ import annotations

try:
    from utils.section_icon import section_expander
except ImportError:  # pragma: no cover
    from ui.utils.section_icon import section_expander  # type: ignore

try:
    from utils.coerce import safe_int, ensure_default
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, ensure_default  # type: ignore

try:
    from utils.overrides import get_override, set_override
    from utils.household import (HOUSEHOLDS, JUST_ME, SPOUSE, MFJ, SINGLE, HOH,
                                 UNMARRIED_FILING, household_of, clear_partner)
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore
    from ui.utils.household import (HOUSEHOLDS, JUST_ME, SPOUSE, MFJ, SINGLE, HOH,  # type: ignore
                                    UNMARRIED_FILING, household_of, clear_partner)

try:
    from utils.household import plan_end_ages, plan_end_text
except ImportError:  # pragma: no cover
    from ui.utils.household import plan_end_ages, plan_end_text  # type: ignore

from retirement_sim.config import plan_end_age


def render_body(st) -> None:
    ensure_default(st, "ay_your_age", safe_int(get_override(st, "YOUR_AGE", 30), 30))
    v = st.number_input("Your age", min_value=18, max_value=100, step=1, key="ay_your_age")
    set_override(st, "YOUR_AGE", safe_int(v))
    your_age = safe_int(v)

    # Who the plan is for. Expressed through the existing keys only: a partner
    # is PARTNER_AGE > 0, and a married couple files jointly (utils/household).
    ensure_default(st, "ay_household", household_of(st.session_state.get("user_overrides", {}) or {}))
    household = st.radio("Who is this plan for?", HOUSEHOLDS, key="ay_household",
                         help="Pick spouse or partner if you share bills and savings.")
    if household == JUST_ME:
        clear_partner(st.session_state.setdefault("user_overrides", {}))
    else:
        # A partner age left at 0 by a single plan would sit below the input's
        # minimum; start it at your own age instead.
        if safe_int(st.session_state.get("ay_partner_age", 0), 0) < 18:
            st.session_state["ay_partner_age"] = max(
                18, safe_int(get_override(st, "PARTNER_AGE", 0), 0) or your_age)
        v = st.number_input("Partner's age", min_value=18, max_value=100, step=1,
                            key="ay_partner_age")
        set_override(st, "PARTNER_AGE", safe_int(v))

    # Filing status follows from the household: married couples file jointly;
    # anyone unmarried (single or with a partner) files Single or Head of household.
    if household == SPOUSE:
        set_override(st, "FILING_STATUS", MFJ)
    else:
        if st.session_state.get("ay_filing") not in UNMARRIED_FILING:
            current = str(get_override(st, "FILING_STATUS", SINGLE))
            st.session_state["ay_filing"] = HOH if current in (HOH, "HOH") else SINGLE
        filing = st.radio("Your tax filing status", UNMARRIED_FILING, horizontal=True,
                          key="ay_filing",
                          help="Head of household: you're unmarried and pay more than half "
                               "the cost of a home for a child or another dependent.")
        set_override(st, "FILING_STATUS", filing)

    # Retirement target
    ensure_default(st, "ay_target_age",
                   safe_int(get_override(st, "TARGET_RETIREMENT_AGE", 60), 60))
    target = st.slider("Target retirement age", min_value=25, max_value=75,
                       step=1, key="ay_target_age",
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
    if household != JUST_ME:
        age_gap = your_age - partner_age  # your_age - partner_age
        # "Retire together" = the partner's age in the year YOU retire. When that
        # lands outside the slider's 25-75 range (a large age gap), it can't be
        # represented on the slider, so we KEEP the byte-identical None default
        # (retire together) until the user deliberately moves the slider -- rather
        # than storing the clamped value, which would wrongly retire the partner
        # early/late and diverge from the "retire together" intent.
        together_raw = target - age_gap
        together_in_range = 25 <= together_raw <= 75
        slider_default = max(25, min(75, together_raw))
        ensure_default(st, "ay_partner_target_age",
                       safe_int(get_override(st, "PARTNER_RETIREMENT_AGE", None) or slider_default,
                                slider_default))
        p_target = st.slider("Partner's retirement age", min_value=25, max_value=75,
                             step=1, key="ay_partner_target_age",
                             help="Your partner's age when they stop working. Set it apart "
                                  "from yours if one of you retires first. The other keeps "
                                  "earning and saving, and their take-home pay offsets "
                                  "withdrawals.")
        if not together_in_range and p_target == slider_default:
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

    # Plan-until age: each person's own. The plan runs until the later of the
    # two, so a younger partner is covered to their own plan-until age.
    ensure_default(st, "ay_plan_until",
                   safe_int(get_override(st, "PLAN_UNTIL_AGE", 95), 95))
    plan_until = st.slider("Plan-until age", min_value=75, max_value=100,
                           step=1, key="ay_plan_until",
                           help="Your money needs to last through this age."
                                + ("" if household == JUST_ME else
                                   " About 30-40% of couples have one partner live past 90."))
    set_override(st, "PLAN_UNTIL_AGE", safe_int(plan_until))
    if household != JUST_ME:
        ensure_default(st, "ay_partner_plan_until",
                       safe_int(get_override(st, "PARTNER_PLAN_UNTIL_AGE", None) or plan_until,
                                plan_until))
        p_until = st.slider("Partner's plan-until age", min_value=75, max_value=100, step=1,
                            key="ay_partner_plan_until", help="Same idea, using your partner's age.")
        set_override(st, "PARTNER_PLAN_UNTIL_AGE", safe_int(p_until))
        # Whoever is covered longer sets the end; every result uses this horizon.
        values = st.session_state.get("user_overrides", {}) or {}
        end_you, end_partner = plan_end_ages(values)
        diff = abs(end_you - end_partner) if end_partner is not None else 0
        if diff:
            who = "younger" if end_partner < end_you else "older"
            st.caption(f"The plan runs until {plan_end_text(values)}. Your partner is {diff} "
                       f"year{'' if diff == 1 else 's'} {who}, so it uses the later "
                       f"of your two plan-until ages.")
        else:
            st.caption(f"The plan runs until {plan_end_text(values)}.")
    end = plan_end_age(st.session_state.get("user_overrides", {}) or {})
    if end <= target:
        st.warning(
            f"The plan ends when you're {end}, which isn't after your target retirement "
            f"age ({target}). Raise the plan-until age."
        )


def render(st) -> None:
    """Standalone expander."""
    with section_expander(st, "About you", "person"):
        render_body(st)
