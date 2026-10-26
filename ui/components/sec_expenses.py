"""Section 4: Expenses — housing, categories, kids, lifecycle."""
from __future__ import annotations

try:
    from utils.section_icon import section_expander
except ImportError:  # pragma: no cover
    from ui.utils.section_icon import section_expander  # type: ignore

try:
    from utils.coerce import safe_int, safe_float, ensure_default
    from utils.formatting import money, money_md
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money, money_md  # type: ignore

try:
    from utils.overrides import get_override, set_override
    from utils.expense_categories import CATEGORIES
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore
    from ui.utils.expense_categories import CATEGORIES  # type: ignore

from retirement_sim import config as cfg

# Children: one row per child, up to MAX_CHILDREN. Every row widget's key starts
# with "se_kid" (utils/widget_sync fills and clears them as a family).
MAX_CHILDREN = 6
_NEW_CHILD_COST = (2_100, 1_400)   # a first child, and each one after (the defaults)


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


def _clamped(v, lo, hi):
    return max(lo, min(hi, safe_int(v, lo)))


def _kid_number(st, key, label, seed, lo, hi, step, help_text=None) -> int:
    ensure_default(st, key, _clamped(seed, lo, hi))
    return safe_int(st.number_input(label, min_value=lo, max_value=hi, step=step, key=key,
                                    help=help_text))


def _new_child(earlier: list) -> dict:
    """A row added by raising the number of children: born 3 years after the
    previous child (or in a year), at the default cost."""
    yub = earlier[-1]["years_until_birth"] + 3 if earlier else 1
    return {**cfg.CHILD_DEFAULTS, "years_until_birth": max(1, yub),
            "monthly_cost": _NEW_CHILD_COST[1 if earlier else 0]}


def _child_row(st, i: int, kid: dict) -> dict:
    """One child's inputs; returns the child's CHILDREN entry."""
    p = f"se_kid{i}_"
    yub = int(kid["years_until_birth"])
    st.markdown(f"**Child {i + 1}**")
    ensure_default(st, p + "born", yub <= 0)
    born = st.toggle("Already born", key=p + "born")
    c1, c2 = st.columns(2, vertical_alignment="bottom")
    with c1:
        if born:
            yub = -_kid_number(st, p + "age", "Age today", -yub if yub <= 0 else 0, 0, 30, 1)
        else:
            yub = _kid_number(st, p + "in", "Born in (years)", yub if yub > 0 else 1, 1, 30, 1)
    with c2:
        cost = _kid_number(st, p + "cost", "Monthly cost ($)", kid["monthly_cost"], 0, 10_000, 100,
                           "Childcare, food, clothes and activities while they live with you, "
                           "in today's dollars.")
    c3, c4 = st.columns(2, vertical_alignment="bottom")
    with c3:
        leaves = _kid_number(st, p + "leaves", "Leaves home at", kid["leaves_home_age"], 16, 30, 1,
                             "Their costs stop at this age.")
    with c4:
        pct = _kid_number(st, p + "college", "College you pay (%)",
                          round(100 * float(kid["college_funding_pct"])), 0, 100, 5,
                          "Share of college you plan to pay. It's saved in a 529 from birth "
                          "and paid out at college. 0 means none.")
    return {**kid, "years_until_birth": yub, "monthly_cost": cost, "leaves_home_age": leaves,
            "college_funding_pct": pct / 100.0}


def _children(st) -> list:
    """The Children inputs: how many, then one row each. Writes CHILDREN."""
    kids = cfg.children_in(st.session_state.get("user_overrides", {}) or {})
    ensure_default(st, "se_kids_n", min(len(kids), MAX_CHILDREN))
    n = st.number_input("Number of children", min_value=0, max_value=MAX_CHILDREN, step=1,
                        key="se_kids_n", help="Children you have now or plan to have.")
    out: list = []
    for i in range(safe_int(n)):
        out.append(_child_row(st, i, kids[i] if i < len(kids) else _new_child(out)))
    if any(c["college_funding_pct"] > 0 for c in out):
        # College prices: one pair for every child.
        first = next(c for c in out if c["college_funding_pct"] > 0)
        c1, c2 = st.columns(2, vertical_alignment="bottom")
        with c1:
            fee = _kid_number(st, "se_kid_college_cost", "A year of college ($)",
                              first["college_annual_cost"], 0, 200_000, 1_000,
                              "Tuition, housing and fees for one year, in today's dollars.")
        with c2:
            years = _kid_number(st, "se_kid_college_years", "Years of college",
                                first["college_years"], 1, 8, 1)
        out = [{**c, "college_annual_cost": fee, "college_years": years} for c in out]
    set_override(st, "CHILDREN", out)
    return out


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
            st.caption("Add your statements in the Spending tab to fill these in "
                       "from what you actually spend.")
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
        c1, c2 = st.columns(2, vertical_alignment="bottom")
        with c1:
            _money_input(st, "Home value", "se_home_value", "HOME_VALUE",
                         800_000, 10_000_000, 10_000)
        with c2:
            _money_input(st, "Monthly mortgage payment", "se_mortgage_monthly",
                         "MORTGAGE_MONTHLY", 3_000, 20_000, 100)
        c1, c2 = st.columns(2, vertical_alignment="bottom")
        with c1:
            _money_input(st, "Mortgage balance", "se_mortgage_balance",
                         "MORTGAGE_BALANCE", 500_000, 5_000_000, 10_000)
        with c2:
            yrs_default = max(0, min(40, safe_int(get_override(st, "MORTGAGE_YEARS_REMAINING", 28), 28)))
            ensure_default(st, "se_mortgage_years", yrs_default)
            v = st.slider("Years remaining on mortgage", min_value=0, max_value=40,
                          step=1, key="se_mortgage_years")
            set_override(st, "MORTGAGE_YEARS_REMAINING", safe_int(v))
        if safe_int(get_override(st, "MORTGAGE_BALANCE", 0), 0) > 0:
            ensure_default(st, "se_mortgage_rate",
                           safe_float(get_override(st, "MORTGAGE_RATE_FOR_PAYOFF", 0.065), 0.065) * 100)
            v = st.number_input("Mortgage interest rate (%)", min_value=0.0, max_value=20.0,
                                step=0.25, format="%.2f", key="se_mortgage_rate",
                                help="On your mortgage statement. Sets how fast you pay down "
                                     "the loan, so how much you'd keep if you sold.")
            set_override(st, "MORTGAGE_RATE_FOR_PAYOFF", round(v / 100, 6))
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
    for r in range(0, len(shown), 2):
        for col, c in zip(st.columns(2, vertical_alignment="bottom"), shown[r:r + 2]):
            with col:
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
    kids = _children(st)

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
        "Flat (no change)": "Flat (no preset change)",
    }
    preset = st.selectbox("How does spending evolve?", presets, key="se_lifecycle",
        format_func=lambda p: _preset_short.get(p, p),
        help="Flat: no change (the extra early in retirement and the later drop "
             "in Retirement goals still apply). Travel boom: discretionary +50% early "
             "in retirement, -20% later. Conservative senior: discretionary -30% later. "
             "Empty-nest: food and discretionary +30% while any child is at home, "
             "-25% once all have left. Early and later years are set in "
             "Retirement goals.")
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
    changes = (["children"] if kids else []) + (
        ["your planned moves"] if (overrides.get("HOME_EVENTS") or overrides.get("HOUSE_MOVE_ENABLED"))
        else []) + ["healthcare in retirement"]
    st.caption("Per year: " + " · ".join(parts)
               + ". This is what the plan spends today. It changes with "
               + (", ".join(changes[:-1]) + " and " if len(changes) > 1 else "")
               + changes[-1] + ".")


def render(st) -> None:
    with section_expander(st, "Expenses", "shopping_cart"):
        render_body(st)
