"""Section 4: Expenses — housing, categories, kids, lifecycle."""
from __future__ import annotations

try:
    from utils.coerce import safe_int, ensure_default
    from utils.formatting import money, money_md
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, ensure_default  # type: ignore
    from ui.utils.formatting import money, money_md  # type: ignore

try:
    from utils.overrides import get_override, set_override
    from utils.expense_categories import CATEGORIES
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore
    from ui.utils.expense_categories import CATEGORIES  # type: ignore


def _section_label(st, txt):
    st.markdown(f'<div style="font-size: 13px; color: #64748b; text-transform: uppercase; '
                f'letter-spacing: 0.05em; margin: 12px 0 6px 0;">{txt}</div>',
                unsafe_allow_html=True)


def _money_input(st, label, widget_key, override_key, default, max_value, step,
                  help_text="", mirror_key=None):
    ensure_default(st, widget_key, safe_int(get_override(st, override_key, default), default))
    display_label = f"{label}($)" if label.endswith(" ") else f"{label} ($)"
    v = st.number_input(display_label, min_value=0, max_value=max_value, step=step,
                        key=widget_key, help=help_text or None)
    set_override(st, override_key, safe_int(v))
    if mirror_key:
        set_override(st, mirror_key, safe_int(v))
    return safe_int(v)


def _statement_sync(st, slot) -> None:
    """Do the monthly inputs match your statements? Drawn into ``slot`` at the
    top of the section, but only after the inputs below have stored this run's
    values, so the answer is never one edit behind."""
    try:
        from components.spending_dashboard import statement_data, sync_control
    except ImportError:  # pragma: no cover
        from ui.components.spending_dashboard import statement_data, sync_control  # type: ignore
    data = statement_data(st)
    with slot:
        if data is None:
            st.caption("Add your statements in the Spending tab to fill these in from "
                       "what you actually spend.")
        else:
            sync_control(st, data, "se_use_actual")


def render_body(st) -> None:
    sync_slot = st.container()

    # ----- Housing -----
    _section_label(st, "Housing")
    owns_default = safe_int(get_override(st, "HOME_VALUE", 0), 0) > 0
    ensure_default(st, "se_rent_own", "Own home" if owns_default else "Renting")
    status = st.radio("Rent or own?", ["Renting", "Own home"], horizontal=True, key="se_rent_own")
    owns = status == "Own home"

    if owns:
        c1, c2 = st.columns(2)
        with c1:
            _money_input(st, "Home value", "se_home_value", "HOME_VALUE",
                         800_000, 10_000_000, 10_000)
            _money_input(st, "Mortgage balance", "se_mortgage_balance",
                         "MORTGAGE_BALANCE", 500_000, 5_000_000, 10_000)
        with c2:
            _money_input(st, "Monthly mortgage payment", "se_mortgage_monthly",
                         "MORTGAGE_MONTHLY", 3_000, 20_000, 100)
            yrs_default = max(0, min(40, safe_int(get_override(st, "MORTGAGE_YEARS_REMAINING", 28), 28)))
            ensure_default(st, "se_mortgage_years", yrs_default)
            v = st.slider("Years remaining on mortgage", min_value=0, max_value=40,
                          step=1, key="se_mortgage_years")
            set_override(st, "MORTGAGE_YEARS_REMAINING", safe_int(v))
        # Clear rent if owning
        set_override(st, "SPEND_RENT_MONTHLY", 0)
    else:
        for k in ("HOME_VALUE", "MORTGAGE_BALANCE", "MORTGAGE_MONTHLY", "MORTGAGE_YEARS_REMAINING"):
            set_override(st, k, 0)
        _money_input(st, "Monthly rent", "se_rent_monthly", "SPEND_RENT_MONTHLY",
                     1_500, 20_000, 50)

    # ----- Spending categories -----
    # One input per category in utils/expense_categories.py -- the same list
    # the Spending tab groups your statements by.
    _section_label(st, "Monthly spending")
    has_partner = safe_int(get_override(st, "PARTNER_AGE", 0), 0) > 0
    shown = [c for c in CATEGORIES if has_partner or not c.partner_only]
    half = (len(shown) + 1) // 2
    for col, cats in zip(st.columns(2), (shown[:half], shown[half:])):
        with col:
            for c in cats:
                _money_input(st, c.label, c.widget, c.key, c.default, c.max_value, c.step,
                             help_text=c.help, mirror_key=c.mirror or None)
    if not has_partner:
        # Single household: no partner spending. The engine adds this key to
        # every year's expenses, so leaving its $1,500 default would spend
        # money for a partner who doesn't exist.
        for c in CATEGORIES:
            if c.partner_only:
                for key in filter(None, (c.key, c.mirror)):
                    set_override(st, key, 0)
    _statement_sync(st, sync_slot)

    # ----- Children -----
    _section_label(st, "Children")
    yufc_current = safe_int(get_override(st, "YEARS_UNTIL_FIRST_CHILD", 99), 99)
    fcmc_current = safe_int(get_override(st, "FIRST_CHILD_MONTHLY_COST", 0), 0)
    has_kids_default = "Kids planned / already born" if (yufc_current < 99 and fcmc_current > 0) else "No kids planned"
    ensure_default(st, "se_kids", has_kids_default)
    kids_status = st.radio("Have / planning kids?",
                            ["No kids planned", "Kids planned / already born"],
                            horizontal=True, key="se_kids")
    if kids_status == "Kids planned / already born":
        c5, c6 = st.columns(2)
        with c5:
            ensure_default(st, "se_yufc", yufc_current if yufc_current < 99 else 3)
            v = st.number_input("Years until first child", min_value=-25, max_value=20,
                                step=1, key="se_yufc",
                                help="Negative = already born that many years ago")
            set_override(st, "YEARS_UNTIL_FIRST_CHILD", safe_int(v))
            ensure_default(st, "se_ybc", safe_int(get_override(st, "YEARS_BETWEEN_CHILDREN", 3), 3))
            v = st.number_input("Years between children", min_value=1, max_value=10,
                                step=1, key="se_ybc")
            set_override(st, "YEARS_BETWEEN_CHILDREN", safe_int(v))
        with c6:
            _money_input(st, "Monthly cost (one child)", "se_fcmc",
                          "FIRST_CHILD_MONTHLY_COST", 2_100, 10_000, 100)
            _money_input(st, "Monthly cost (both children)", "se_bcmc",
                          "BOTH_CHILDREN_MONTHLY_COST", 3_500, 15_000, 100)

        ensure_default(st, "se_leave_age",
                       safe_int(get_override(st, "CHILD_LEAVES_HOME_AGE", 18), 18))
        v = st.slider("Child leaves home age", min_value=16, max_value=25,
                      step=1, key="se_leave_age")
        set_override(st, "CHILD_LEAVES_HOME_AGE", safe_int(v))
    else:
        set_override(st, "YEARS_UNTIL_FIRST_CHILD", 99)
        set_override(st, "FIRST_CHILD_MONTHLY_COST", 0)
        set_override(st, "BOTH_CHILDREN_MONTHLY_COST", 0)

    # ----- Lifecycle preset -----
    _section_label(st, "Lifecycle pattern")
    presets = [
        "Flat (no change)",
        "Early-retirement travel boom, quieter later",
        "Conservative senior years",
        "Children then empty-nest",
    ]
    current_preset = str(get_override(st, "SPEND_LIFECYCLE_PRESET", presets[0]))
    if current_preset not in presets:
        current_preset = presets[0]
    ensure_default(st, "se_lifecycle", current_preset)
    # Shorter DISPLAY labels only — the stored values must keep their long form
    # because spending_inputs.apply_lifecycle_preset and the saved profile JSONs
    # match on them. The 328px sidebar's selectbox clips its selected value at
    # ~168px, so "Children then empty-nest" rendered as "Children then empty…".
    _preset_short = {
        "Early-retirement travel boom, quieter later": "Travel boom, quieter later",
        "Children then empty-nest": "Kids then empty-nest",
    }
    preset = st.selectbox("How does spending evolve?", presets, key="se_lifecycle",
        format_func=lambda p: _preset_short.get(p, p),
        help="Flat: inflation only. Travel boom: discretionary +50% ages 55–70, "
             "-20% after 75. Conservative senior: discretionary -30% after 75. "
             "Empty-nest: food/discretionary +30% while kids at home, -25% after.")
    set_override(st, "SPEND_LIFECYCLE_PRESET", preset)

    # ----- Live total -----
    # Uses utils.derived.compute_expenses_today, which is the SAME figure the
    # engine spends (verified equal to cfg.calculate_annual_expenses). The
    # previous hand-rolled sum here silently omitted the partner's personal
    # spending, so it under-reported the household total by that amount
    # (about a sixth of the simulated total on a real profile) -- the
    # number people sanity-check their budget against was the one number on the
    # page that didn't feed the simulation.
    overrides = st.session_state.get("user_overrides", {}) or {}
    try:
        from utils.derived import compute_expenses_today
    except ImportError:  # pragma: no cover
        from ui.utils.derived import compute_expenses_today  # type: ignore

    total_annual = int(compute_expenses_today(overrides))
    total_monthly = total_annual / 12.0

    # Breakdown, so the total is auditable rather than a mystery figure.
    monthly_categories = sum(safe_int(overrides.get(c.key, 0), 0)
                             for c in CATEGORIES if not c.partner_only)
    monthly_housing = (safe_int(overrides.get("MORTGAGE_MONTHLY", 0), 0)
                       if owns else safe_int(overrides.get("SPEND_RENT_MONTHLY", 0), 0))
    monthly_partner = safe_int(
        overrides.get("PARTNER_OTHER_MONTHLY",
                      overrides.get("PARTNER_MONTHLY_SPENDING", 1_500)), 1_500)
    monthly_kids = max(0.0, total_monthly - monthly_categories
                       - monthly_housing - monthly_partner)

    st.markdown(
        '<hr style="margin: 14px 0 8px 0; border: 0; border-top: 1px solid #e5e7eb;">',
        unsafe_allow_html=True,
    )
    _section_label(st, "Current spending")
    cols = st.columns(2)
    with cols[0]:
        # Full precision, not shortened: "$139,104" is checkable against a
        # budget; "$139K" is not.
        st.metric("Total per year", f"${total_annual:,.0f}")
    with cols[1]:
        st.metric("Total per month", f"${total_monthly:,.0f}")

    parts = [f"housing {money_md(monthly_housing * 12)}",
             f"living {money_md(monthly_categories * 12)}"]
    if monthly_partner > 0:
        parts.append(f"partner {money_md(monthly_partner * 12)}")
    if monthly_kids > 1:
        parts.append(f"children {money_md(monthly_kids * 12)}")
    st.caption("Per year: " + " · ".join(parts)
               + ".  This is the figure the simulation spends today; it grows "
                 "with children, the house move, and healthcare in retirement.")


def render(st) -> None:
    with st.expander("Expenses", expanded=False, icon=":material/shopping_cart:"):
        render_body(st)
