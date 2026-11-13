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


try:
    from utils.slider_input import slider_with_box
except ImportError:  # pragma: no cover
    from ui.utils.slider_input import slider_with_box  # type: ignore


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
        if filing == SINGLE and household == JUST_ME:
            try:
                from utils.derived import children_at_home_now
            except ImportError:  # pragma: no cover
                from ui.utils.derived import children_at_home_now  # type: ignore
            if children_at_home_now(st.session_state.get("user_overrides", {}) or {}):
                st.caption("You have children at home. If you pay most of their costs, Head of "
                           "household usually means a lower tax bill.")

    # The retirement-age sliders live in Retirement (drawn later this run).
    # Their widget values are already current, so apply the target age now:
    # sections drawn before Retirement then see this run's value, not last run's.
    if "ay_target_age" in st.session_state:
        set_override(st, "TARGET_RETIREMENT_AGE", safe_int(st.session_state["ay_target_age"]))

    # Plan-until age: each person's own. The plan runs until the later of the
    # two, so a younger partner is covered to their own plan-until age.
    ensure_default(st, "ay_plan_until",
                   safe_int(get_override(st, "PLAN_UNTIL_AGE", 95), 95))
    plan_until = slider_with_box(st, "Plan-until age", 75, 100,
                           1, key="ay_plan_until",
                           help="Your money needs to last through this age."
                                + ("" if household == JUST_ME else
                                   " About 30-40% of couples have one partner live past 90."))
    set_override(st, "PLAN_UNTIL_AGE", safe_int(plan_until))
    if household != JUST_ME:
        ensure_default(st, "ay_partner_plan_until",
                       safe_int(get_override(st, "PARTNER_PLAN_UNTIL_AGE", None) or plan_until,
                                plan_until))
        p_until = slider_with_box(st, "Partner's plan-until age", 75, 100, 1,
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
    target = safe_int(get_override(st, "TARGET_RETIREMENT_AGE", 60), 60)
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
