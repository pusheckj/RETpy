"""Section: Expenses — monthly spending categories, the lifecycle pattern, and
big purchases & goals (car, retirement vacation) at the end.

Housing is in the House section and children in Family; both render first, so
the live total below reads their finished inputs. The big-purchase inputs are
drawn after the total and nothing above them reads their values."""
from __future__ import annotations

try:
    from utils.section_icon import section_expander
except ImportError:  # pragma: no cover
    from ui.utils.section_icon import section_expander  # type: ignore

try:
    from utils.coerce import safe_int, ensure_default
    from utils.formatting import money, money_md
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, ensure_default  # type: ignore
    from ui.utils.formatting import money, money_md  # type: ignore

try:
    from utils.overrides import get_override, set_override
    from utils.expense_categories import CATEGORIES
    from utils.derived import LIFECYCLE_PRESETS
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore
    from ui.utils.expense_categories import CATEGORIES  # type: ignore
    from ui.utils.derived import LIFECYCLE_PRESETS  # type: ignore

from retirement_sim import config as cfg


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
            st.caption("Add your statements in the Spending tab to fill these in "
                       "from what you actually spend.")
        else:
            sync_control(st, data, "se_use_actual")


def render_body(st) -> None:
    sync_slot = st.container()

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

    # ----- Lifecycle preset -----
    _section_label(st, "Lifecycle pattern")
    presets = LIFECYCLE_PRESETS
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
             "in Retirement still apply). Travel boom: discretionary +50% early "
             "in retirement, -20% later. Conservative senior: discretionary -30% later. "
             "Empty-nest: food and discretionary +30% while any child is at home, "
             "-25% once all have left. Early and later years are set in "
             "Retirement.")
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
    # Rent or own is the House section's radio, drawn earlier this run.
    rent_own = st.session_state.get("se_rent_own")
    owns = (rent_own == "Own home" if rent_own
            else safe_int(overrides.get("HOME_VALUE", 0), 0) > 0)
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
    changes = (["children"] if cfg.children_in(overrides) else []) + (
        ["your planned moves"] if (overrides.get("HOME_EVENTS") or overrides.get("HOUSE_MOVE_ENABLED"))
        else []) + ["healthcare in retirement"]
    st.caption("Per year: " + " · ".join(parts)
               + ". This is what the plan spends today. It changes with "
               + (", ".join(changes[:-1]) + " and " if len(changes) > 1 else "")
               + changes[-1] + ".")

    # ----- Big purchases & goals (car, retirement vacation) -----
    # Drawn last: the total above does not include them (they are one-off or
    # early-retirement extras the engine adds separately).
    try:
        from components import sec_big_purchases
    except ImportError:  # pragma: no cover
        from ui.components import sec_big_purchases  # type: ignore
    st.divider()
    sec_big_purchases.render_body(st)


def render(st) -> None:
    with section_expander(st, "Expenses", "shopping_cart"):
        render_body(st)
