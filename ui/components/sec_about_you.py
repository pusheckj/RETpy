"""Section 1: About you — household composition + planning horizon."""
from __future__ import annotations

from datetime import date

try:
    from utils.coerce import safe_int, ensure_default
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, ensure_default  # type: ignore

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore


def render_body(st) -> None:
    current_year = date.today().year

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**You**")
        ensure_default(st, "ay_your_age", safe_int(get_override(st, "YOUR_AGE", 30), 30))
        v = st.number_input("Age", min_value=18, max_value=100, step=1, key="ay_your_age")
        set_override(st, "YOUR_AGE", safe_int(v))

        ensure_default(st, "ay_your_birth_year",
                       safe_int(get_override(st, "YOUR_BIRTH_YEAR", current_year - 30), current_year - 30))
        v = st.number_input("Birth year", min_value=1900, max_value=current_year,
                            step=1, key="ay_your_birth_year",
                            help="Sets your SECURE 2.0 RMD start age (73 or 75).")
        set_override(st, "YOUR_BIRTH_YEAR", safe_int(v))

    with col2:
        st.markdown("**Partner**")
        ensure_default(st, "ay_partner_age", safe_int(get_override(st, "PARTNER_AGE", 0), 0))
        v = st.number_input("Age ", min_value=0, max_value=100, step=1, key="ay_partner_age",
                            help="Set to 0 for a single household.")
        set_override(st, "PARTNER_AGE", safe_int(v))

        ensure_default(st, "ay_partner_birth_year",
                       safe_int(get_override(st, "PARTNER_BIRTH_YEAR", current_year - 30), current_year - 30))
        v = st.number_input("Birth year ", min_value=1900, max_value=current_year,
                            step=1, key="ay_partner_birth_year")
        set_override(st, "PARTNER_BIRTH_YEAR", safe_int(v))

    # Filing status
    options = ["Married filing jointly", "Single", "Head of household"]
    current_filing = str(get_override(st, "FILING_STATUS", "Married filing jointly"))
    if current_filing not in options:
        # Translate from canonical short codes
        canonical_map = {"MFJ": "Married filing jointly", "S": "Single", "HOH": "Head of household"}
        current_filing = canonical_map.get(current_filing, "Married filing jointly")
    ensure_default(st, "ay_filing", current_filing)
    filing = st.radio(
        "Filing status",
        options=options,
        horizontal=True,
        key="ay_filing",
    )
    set_override(st, "FILING_STATUS", filing)
    # Sync YEARS_UNTIL_WEDDING (the engine's marital flag) for every status, so
    # switching MFJ -> Head of household / Single can't leave stale "married"
    # state. Only MFJ is married; Single and Head of household are unmarried.
    if filing == "Married filing jointly":
        set_override(st, "YEARS_UNTIL_WEDDING", 0)
    else:
        set_override(st, "YEARS_UNTIL_WEDDING", 99)

    # Retirement target
    ensure_default(st, "ay_target_age",
                   safe_int(get_override(st, "TARGET_RETIREMENT_AGE", 60), 60))
    target = st.slider("Target retirement age", min_value=25, max_value=75,
                       step=1, key="ay_target_age",
                       help="When you plan to stop working.")
    set_override(st, "TARGET_RETIREMENT_AGE", safe_int(target))
    your_age = safe_int(get_override(st, "YOUR_AGE", 30), 30)
    if target < your_age:
        st.warning(
            f"Target retirement age ({target}) is below your current age ({your_age}). "
            "The simulation won't run until the target age is at least your current age."
        )

    # Partner's own retirement age (only when a partner exists). Independent of
    # yours: the partner can keep working after you retire, or stop earlier. The
    # default is the partner's age in the year YOU retire (i.e. "retire together"),
    # which the engine treats identically to the single-switch default -- so this
    # is a no-op until the user actually moves it apart.
    partner_age = safe_int(get_override(st, "PARTNER_AGE", 0), 0)
    if partner_age > 0:
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
                             help="When your partner plans to stop working (their age). "
                                  "Set it apart from yours to model one retiring first: "
                                  "the working partner keeps earning and saving, and their "
                                  "take-home offsets the other's withdrawals.")
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
                st.caption(f"Partner retires at {p_target} — the same year you do.")
            else:
                when = "after you" if gap_vs_you > 0 else "before you"
                st.caption(f"Partner retires at {p_target} — {abs(gap_vs_you)} year(s) {when}.")
            if p_target < partner_age:
                st.warning(
                    f"Partner's retirement age ({p_target}) is below their current age "
                    f"({partner_age}); the simulator treats them as already retired."
                )
    else:
        # Single household: keep the engine's None default (no partner overlay).
        set_override(st, "PARTNER_RETIREMENT_AGE", None)

    # Plan-until age
    ensure_default(st, "ay_plan_until",
                   safe_int(get_override(st, "PLAN_UNTIL_AGE", 95), 95))
    plan_until = st.slider("Plan until age", min_value=75, max_value=100,
                           step=1, key="ay_plan_until",
                           help="Model finances through this age. ~30-40% of couples have one partner live past 90.")
    set_override(st, "PLAN_UNTIL_AGE", safe_int(plan_until))
    if plan_until <= target:
        st.warning(
            f"Plan-until age ({plan_until}) is not after target retirement age ({target}). "
            "Increase it so the model has a retirement period to simulate."
        )


def render(st) -> None:
    """Standalone expander."""
    with st.expander("About you", expanded=False, icon=":material/person:"):
        render_body(st)
