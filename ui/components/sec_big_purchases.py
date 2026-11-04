"""Section: Big purchases & goals — car and retirement vacation.

Optional lifecycle events, each OFF by default so the baseline simulation is
unaffected until a user explicitly opts in:
  - Car: one-time purchase and/or recurring replacement (paid cash from
    the portfolio).
  - Retirement vacation: extra early-retirement spending from retirement
    until a chosen slow-down age.
Home moves and extra mortgage payments are in the House section.
"""
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
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore


def _section_label(st, txt):
    st.markdown(f'<div style="font-size: 13px; color: #64748b; text-transform: uppercase; '
                f'letter-spacing: 0.05em; margin: 12px 0 6px 0;">{txt}</div>',
                unsafe_allow_html=True)


def render_body(st) -> None:
    # ===== Car =====
    _section_label(st, "Car")

    ensure_default(st, "bp_car_onetime_enable",
                   bool(get_override(st, "CAR_ONETIME_ENABLED", False)))
    onetime_on = st.toggle("Plan a one-time car purchase",
                             key="bp_car_onetime_enable",
                             help="A one-time cash payment at the age you choose, taken "
                                  "from your portfolio.")
    set_override(st, "CAR_ONETIME_ENABLED", bool(onetime_on))
    if onetime_on:
        c1, c2 = st.columns(2, vertical_alignment="bottom")
        with c1:
            ensure_default(st, "bp_car_onetime_age",
                           safe_int(get_override(st, "CAR_ONETIME_AGE", 40), 40))
            v = st.number_input("Purchase age", min_value=18, max_value=100,
                                step=1, key="bp_car_onetime_age")
            set_override(st, "CAR_ONETIME_AGE", safe_int(v))
        with c2:
            ensure_default(st, "bp_car_onetime_amount",
                           safe_int(get_override(st, "CAR_ONETIME_AMOUNT", 40_000), 40_000))
            v = st.number_input("Purchase amount ($)", min_value=0, max_value=500_000,
                                step=1_000, key="bp_car_onetime_amount")
            set_override(st, "CAR_ONETIME_AMOUNT", safe_int(v))
        st.caption("Paid in cash from your portfolio at this age.")

    ensure_default(st, "bp_car_recurring_enable",
                   bool(get_override(st, "CAR_RECURRING_ENABLED", False)))
    recurring_on = st.toggle("Plan recurring car replacements",
                               key="bp_car_recurring_enable",
                               help="Buys a car in cash every N years, starting at the "
                                    "age you choose.")
    set_override(st, "CAR_RECURRING_ENABLED", bool(recurring_on))
    if recurring_on:
        c3, c4 = st.columns(2, vertical_alignment="bottom")
        with c3:
            ensure_default(st, "bp_car_recurring_start",
                           safe_int(get_override(st, "CAR_RECURRING_START_AGE", 40), 40))
            v = st.number_input("Start age", min_value=18, max_value=100,
                                step=1, key="bp_car_recurring_start")
            set_override(st, "CAR_RECURRING_START_AGE", safe_int(v))
        with c4:
            ensure_default(st, "bp_car_recurring_every",
                           safe_int(get_override(st, "CAR_RECURRING_EVERY_YEARS", 8), 8))
            v = st.number_input("Every N years", min_value=1, max_value=30,
                                step=1, key="bp_car_recurring_every")
            set_override(st, "CAR_RECURRING_EVERY_YEARS", safe_int(v))
        ensure_default(st, "bp_car_recurring_amount",
                       safe_int(get_override(st, "CAR_RECURRING_AMOUNT", 40_000), 40_000))
        v = st.number_input("Amount ($)", min_value=0, max_value=500_000,
                            step=1_000, key="bp_car_recurring_amount")
        set_override(st, "CAR_RECURRING_AMOUNT", safe_int(v))
        st.caption("Paid in cash from your portfolio.")

    st.divider()

    # ===== Retirement vacation =====
    _section_label(st, "Retirement vacation (early years)")

    ensure_default(st, "bp_vacation_enable",
                   bool(get_override(st, "RETIREMENT_VACATION_ENABLED", False)))
    vacation_on = st.toggle("Plan extra travel spending early in retirement",
                              key="bp_vacation_enable",
                              help="Extra yearly spending from retirement until the age "
                                   "you slow down. It comes on top of \"Extra for "
                                   "travel and hobbies\" in Retirement goals.")
    set_override(st, "RETIREMENT_VACATION_ENABLED", bool(vacation_on))
    if vacation_on:
        c8, c9 = st.columns(2, vertical_alignment="bottom")
        with c8:
            ensure_default(st, "bp_vacation_annual",
                           safe_int(get_override(st, "RETIREMENT_VACATION_ANNUAL", 20_000), 20_000))
            v = st.number_input("Annual amount ($)", min_value=0, max_value=200_000,
                                step=1_000, key="bp_vacation_annual")
            set_override(st, "RETIREMENT_VACATION_ANNUAL", safe_int(v))
        with c9:
            ensure_default(st, "bp_vacation_until",
                           safe_int(get_override(st, "RETIREMENT_VACATION_UNTIL_AGE", 75), 75))
            v = st.number_input("Until age (slow-down)", min_value=50, max_value=100,
                                step=1, key="bp_vacation_until")
            set_override(st, "RETIREMENT_VACATION_UNTIL_AGE", safe_int(v))
        st.caption("Extra spending on top of normal expenses, from retirement age "
                   "until the slow-down age.")


def render(st) -> None:
    with section_expander(st, "Big purchases & goals", "shopping_bag"):
        render_body(st)
