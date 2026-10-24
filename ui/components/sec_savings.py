"""Section 5: Savings — derived total + auto/custom%/manual allocation modes."""
from __future__ import annotations

try:
    from utils.coerce import safe_int, safe_float, ensure_default
    from utils.formatting import money, money_md
    from utils.derived import (
        compute_total_income, compute_taxes, compute_expenses_today,
        compute_disposable, auto_allocate_savings, get_limit, KEEP_AMOUNTS_MODE,
    )
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money, money_md  # type: ignore
    from ui.utils.derived import (  # type: ignore
        compute_total_income, compute_taxes, compute_expenses_today,
        compute_disposable, auto_allocate_savings, get_limit, KEEP_AMOUNTS_MODE,
    )

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore

try:
    from utils.plot_theme import series_color
except ImportError:  # pragma: no cover
    from ui.utils.plot_theme import series_color  # type: ignore


_ACCOUNT_LABELS = [
    ("Your 401(k)",          "YOUR_401K_CONTRIBUTION",        "#0d9488"),
    ("Partner 401(k)",       "PARTNER_401K_CONTRIBUTION",     "#d97706"),
    ("Your HSA",             "YOUR_HSA_CONTRIBUTION",         "#7c3aed"),
    ("Your Roth (backdoor)", "YOUR_BACKDOOR_ROTH",            "#059669"),
    ("Partner Roth IRA",     "PARTNER_ROTH_CONTRIBUTION",     "#f59e0b"),
    ("Your brokerage",       "YOUR_BROKERAGE_CONTRIBUTION",   "#475569"),
    ("Partner brokerage",    "PARTNER_BROKERAGE_CONTRIBUTION","#94a3b8"),
]


def render_body(st) -> None:
    overrides = st.session_state.get("user_overrides", {}) or {}

    income = compute_total_income(overrides)
    # Before pre-tax savings, matching compute_disposable (the pool split below).
    taxes = compute_taxes(overrides, pretax_savings=False)["total"]
    expenses = compute_expenses_today(overrides)
    disposable = compute_disposable(overrides)

    # ---- Top KPI strip ----
    # Stacked (not 4 cramped columns) so labels/values never truncate in the
    # narrow sidebar; income/taxes/expenses on one row, disposable on its own.
    row1 = st.columns(3)
    with row1[0]: st.metric("Income", money(income, shorten=True))
    with row1[1]: st.metric("− Taxes", money(taxes, shorten=True),
                            help="Before your 401(k)/HSA savings lower it. The Taxes "
                                 "section shows the tax after them.")
    with row1[2]: st.metric("− Expenses", money(expenses, shorten=True))
    st.metric("= Disposable", money(disposable, shorten=True))

    if disposable <= 0:
        st.warning(
            f"Disposable income is ≤ \\$0 "
            f"({money_md(income)} − {money_md(taxes)} − {money_md(expenses)}). "
            "Adjust income, expenses, or taxes before setting savings."
        )

    # ---- Mode selector ----
    modes = ["Auto-allocate (recommended)", KEEP_AMOUNTS_MODE, "Custom %", "Manual amounts"]
    current_mode = str(get_override(st, "SAVINGS_MODE", modes[0]))
    if current_mode not in modes:
        current_mode = modes[0]
    ensure_default(st, "sv_mode", current_mode)
    mode = st.radio("Allocation strategy", modes, horizontal=False, key="sv_mode")
    set_override(st, "SAVINGS_MODE", mode)

    _render_employer_match(st, overrides)

    if mode == "Auto-allocate (recommended)":
        _render_auto(st, disposable, overrides)
    elif mode == KEEP_AMOUNTS_MODE:
        _render_keep_amounts(st, overrides)
    elif mode == "Custom %":
        _render_custom_pct(st, disposable, overrides)
    else:
        _render_manual(st, disposable, overrides)

    # ---- Inflation toggle ----
    # HONEST SCOPE: the engine does not read SAVINGS_INFLATION_ADJUST at all
    # (grep retirement_sim/ — only config.py's unused declaration). It holds
    # each cfg.*_CONTRIBUTION flat per year, which in the model's real-dollar
    # frame already IS "inflation-indexed". So this toggle only changes the
    # savings-projection chart's nominal display; the old help text promised a
    # change to the plan that never happened.
    ensure_default(st, "sv_inflation_adjust",
                   bool(get_override(st, "SAVINGS_INFLATION_ADJUST", True)))
    v = st.toggle(
        "Show contributions in future (nominal) dollars",
        key="sv_inflation_adjust",
        help="Display option for the savings-projection chart only: scales each "
             "year's contribution up by ~2.75%/yr so you see nominal dollars. "
             "The Monte Carlo always holds contributions constant in today's "
             "dollars (which already keeps real purchasing power constant), so "
             "this does not move your success rate.",
    )
    set_override(st, "SAVINGS_INFLATION_ADJUST", bool(v))

    # ---- Expense-sharing (brokerage attribution) ----
    ensure_default(st, "sv_primary_housing",
                   bool(get_override(st, "PRIMARY_PAYS_HOUSING", False)))
    pph = st.toggle(
        "I (primary) pay the full mortgage; split the rest evenly",
        key="sv_primary_housing",
        help="How leftover savings split between the two brokerage accounts. "
             "Off = split all expenses evenly. On = the primary earner covers "
             "the whole mortgage and the rest splits 50/50, so more leftover "
             "lands in the primary's brokerage. (Car purchases stay a shared "
             "outflow. This only re-labels which brokerage gets the savings; "
             "both are taxable.)",
    )
    set_override(st, "PRIMARY_PAYS_HOUSING", bool(pph))

    # ---- Mega backdoor Roth (after-tax 401(k) -> in-plan Roth conversion) ----
    ensure_default(st, "sv_after_tax_401k",
                   safe_float(get_override(st, "YOUR_AFTER_TAX_401K_PCT", 0.0), 0.0) * 100)
    atp = st.slider(
        "After-tax 401(k) → Roth · mega backdoor (% of base pay)",
        min_value=0.0, max_value=20.0, step=0.5, key="sv_after_tax_401k",
        help="Extra after-tax 401(k) contributions converted in-plan to Roth. The engine "
             "fills the total 401(k) limit (employee + employer) left after your regular "
             "deferral and match, funds it from take-home, and grows it tax-free — moving "
             "savings from your taxable brokerage into Roth. Set 0 if your plan lacks "
             "after-tax contributions + in-plan Roth conversion.",
    )
    set_override(st, "YOUR_AFTER_TAX_401K_PCT", atp / 100.0)
    if atp > 0:
        # Same room as the engine (working_year_cashflow): the 415(c) total
        # limit minus your deferral and the match it earns.
        from retirement_sim import config as cfg
        age = safe_int(get_override(st, "YOUR_AGE", 30), 30)
        total_limit = int(cfg.get_401k_total_limit(age, cfg.CURRENT_YEAR))
        base_sal = safe_int(get_override(st, "YOUR_BASE_SALARY", 0), 0)
        deferral = min(safe_int(get_override(st, "YOUR_401K_CONTRIBUTION", 0), 0),
                       int(cfg.get_401k_limit(age, cfg.CURRENT_YEAR)), base_sal)
        match_pct = safe_float(get_override(st, "YOUR_401K_MATCH_PCT", 0.0), 0.0)
        match = min(deferral, int(match_pct * base_sal))
        room = max(0, total_limit - deferral - match)
        est = min(int(atp / 100.0 * base_sal), room)
        est_s = money(est, shorten=True).replace("$", "\\$")
        room_s = money(room, shorten=True).replace("$", "\\$")
        limit_s = money(total_limit, shorten=True).replace("$", "\\$")
        st.caption(
            f"≈ {est_s}/yr into Roth (capped at ~{room_s}: the {limit_s} total 401(k) "
            "limit minus your contribution and match). Redirects that much from "
            "taxable brokerage."
        )


def _render_employer_match(st, overrides: dict) -> None:
    """Employer 401(k) match inputs (yours, and your partner's if any)."""
    ensure_default(st, "sv_match_pct",
                   safe_float(get_override(st, "YOUR_401K_MATCH_PCT", 0.0), 0.0) * 100)
    v = st.number_input(
        "Your employer's 401(k) match (% of pay)", min_value=0.0, max_value=25.0,
        step=0.5, format="%.1f", key="sv_match_pct",
        help="The most your employer adds, as in \"we match up to 4%\". They match "
             "what you put in, so contributing less than this gets less match.",
    )
    set_override(st, "YOUR_401K_MATCH_PCT", float(v) / 100.0)
    if safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0:
        ensure_default(st, "sv_partner_match_pct",
                       safe_float(get_override(st, "PARTNER_401K_MATCH_PCT", 0.0), 0.0) * 100)
        v = st.number_input(
            "Partner's employer 401(k) match (% of pay)", min_value=0.0, max_value=25.0,
            step=0.5, format="%.1f", key="sv_partner_match_pct",
        )
        set_override(st, "PARTNER_401K_MATCH_PCT", float(v) / 100.0)


def _render_auto(st, disposable: int, overrides: dict) -> None:
    """Auto: fill tax-advantaged first, residual to brokerage."""
    allocation = auto_allocate_savings(disposable, overrides)

    # Push the auto-derived amounts into user_overrides so the simulator picks them up.
    for key, amount in allocation.items():
        set_override(st, key, int(amount))

    st.caption(
        "Fills accounts in order: **401(k) → HSA → IRA/Roth → Brokerage "
        "residual**, each capped at 2024 IRS limits. "
        "Switch to Custom % or Manual for different splits."
    )

    # Visualization: stacked horizontal bar
    import plotly.graph_objects as go
    labels = []
    values = []
    colors = []
    for idx, (label, key, _color) in enumerate(_ACCOUNT_LABELS):
        amt = allocation.get(key, 0)
        if amt > 0:
            labels.append(label)
            values.append(amt)
            colors.append(series_color(idx, st))

    if values:
        fig = go.Figure()
        cumulative = 0
        for label, val, color in zip(labels, values, colors):
            fig.add_trace(go.Bar(
                x=[val], y=["Allocation"],
                orientation="h",
                name=label,
                marker_color=color,
                hovertemplate=f"{label}<br>$%{{x:,.0f}}<extra></extra>",
                text=label if val > disposable * 0.05 else "",
                textposition="inside",
                textfont=dict(color="white", size=10),
            ))
            cumulative += val

        fig.update_layout(
            barmode="stack",
            height=104,
            margin=dict(l=0, r=10, t=6, b=28),
            xaxis=dict(showgrid=False, zeroline=False, tickformat="$,.3~s"),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            showlegend=False,
        )
        try:
            from utils.plot_theme import style_fig
        except ImportError:  # pragma: no cover
            from ui.utils.plot_theme import style_fig  # type: ignore
        fig = style_fig(fig, st)
        st.plotly_chart(fig, width="stretch",
                        config={"displayModeBar": False},
                        key="sv_auto_alloc_chart")

    # Summary line
    total = sum(allocation.values())
    st.caption(f"**Total allocated**: {money(total, shorten=True)}")


def _render_custom_pct(st, disposable: int, overrides: dict) -> None:
    """Custom %: user provides allocation percentages."""
    st.caption("Set what fraction of disposable income goes to each account. "
               "Each gets `pct × disposable`, capped at 2024 IRS limits.")

    # Default split if no values yet: roughly mirror auto
    defaults = {
        "YOUR_401K_CONTRIBUTION": 30,
        "PARTNER_401K_CONTRIBUTION": 20,
        "YOUR_HSA_CONTRIBUTION": 8,
        "YOUR_BACKDOOR_ROTH": 7,
        "PARTNER_ROTH_CONTRIBUTION": 5,
        "YOUR_BROKERAGE_CONTRIBUTION": 15,
        "PARTNER_BROKERAGE_CONTRIBUTION": 15,
    }
    pcts = {}
    total_pct = 0
    for label, key, _ in _ACCOUNT_LABELS:
        widget_key = f"sv_pct_{key.lower()}"
        ensure_default(st, widget_key, defaults.get(key, 0))
        v = st.slider(f"{label} %", min_value=0, max_value=100, step=1,
                      key=widget_key)
        pcts[key] = v
        total_pct += v

    # Compute amounts
    your_age = safe_int(overrides.get("YOUR_AGE", 30), 30)
    partner_age = safe_int(overrides.get("PARTNER_AGE", 0), 0)
    caps = {
        "YOUR_401K_CONTRIBUTION": get_limit("401k", your_age),
        "PARTNER_401K_CONTRIBUTION": get_limit("401k", partner_age) if partner_age > 0 else 0,
        "YOUR_HSA_CONTRIBUTION": get_limit("hsa", your_age, family=True),
        "YOUR_BACKDOOR_ROTH": get_limit("ira", your_age),
        "PARTNER_ROTH_CONTRIBUTION": get_limit("ira", partner_age) if partner_age > 0 else 0,
        "YOUR_BROKERAGE_CONTRIBUTION": 10_000_000,
        "PARTNER_BROKERAGE_CONTRIBUTION": 10_000_000,
    }
    for key, pct_val in pcts.items():
        amount = int(disposable * pct_val / 100)
        cap = caps.get(key, 10_000_000)
        amount = min(amount, cap)
        set_override(st, key, amount)

    # Sum check
    if total_pct != 100:
        if total_pct < 100:
            st.warning(
                f"Percentages sum to **{total_pct}%** "
                f"({100 - total_pct}% unallocated — that money sits unused). "
                "Adjust sliders to total 100%."
            )
        else:
            st.warning(
                f"Percentages sum to **{total_pct}%** "
                f"(over by {total_pct - 100}%). Contributions will exceed disposable income."
            )


def _manual_amount(st, widget_key: str, cfg_key: str, label: str,
                   max_value: int, step: int) -> None:
    """Render one manual-dollars number_input, seeded from the current override.

    The seed MUST be clamped to ``max_value``: Auto / Custom-% modes write
    IRS-limit amounts into user_overrides (e.g. the age-50+ 401(k) catch-up
    limit of \\$30,500), and ``ensure_default`` does not clamp. Seeding an
    out-of-range value made ``st.number_input`` raise
    ``StreamlitValueAboveMaxError``, which ``app.py::_safe_render`` swallowed —
    replacing the WHOLE Savings section (mode radio included) with a
    placeholder, so the user could not even switch back to Auto.
    """
    ensure_default(st, widget_key,
                   min(max_value, safe_int(get_override(st, cfg_key, 0), 0)))
    v = st.number_input(label, min_value=0, max_value=max_value, step=step,
                        key=widget_key)
    set_override(st, cfg_key, safe_int(v))


# 401(k) employee-deferral ceiling for the manual inputs. Must clear the
# age-50+ catch-up limit ($23,000 + $7,500 = $30,500); kept a fixed generous
# bound rather than an age-derived one so an age edit can never push an already
# stored widget value above the max (which would crash the section).
_MANUAL_401K_MAX = 40_000


def _render_keep_amounts(st, overrides: dict) -> None:
    """Your own 401(k) / HSA / IRA amounts, and everything else you don't
    spend invested in a brokerage account. The engine sweeps the un-spent
    residual for any SAVINGS_MODE starting with "Auto"; the brokerage floor is
    set to 0 so it gets exactly what's left."""
    st.caption("Your 401(k), HSA and IRA stay at these amounts. Whatever else you don't "
               "spend is invested in a regular brokerage account each year.")
    has_partner = safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0
    c1, c2 = st.columns(2)
    with c1:
        _manual_amount(st, "sv_manual_your_401k", "YOUR_401K_CONTRIBUTION",
                       "Your 401(k) ($/yr)", _MANUAL_401K_MAX, 500)
        _manual_amount(st, "sv_manual_your_hsa", "YOUR_HSA_CONTRIBUTION",
                       "Your HSA ($/yr)", 10_000, 250)
        _manual_amount(st, "sv_manual_your_roth", "YOUR_BACKDOOR_ROTH",
                       "Your Roth IRA / backdoor ($/yr)", 10_000, 500)
    with c2:
        if has_partner:
            _manual_amount(st, "sv_manual_partner_401k", "PARTNER_401K_CONTRIBUTION",
                           "Partner 401(k) ($/yr)", _MANUAL_401K_MAX, 500)
            _manual_amount(st, "sv_manual_partner_roth", "PARTNER_ROTH_CONTRIBUTION",
                           "Partner Roth IRA ($/yr)", 10_000, 500)
    if not has_partner:
        set_override(st, "PARTNER_401K_CONTRIBUTION", 0)
        set_override(st, "PARTNER_ROTH_CONTRIBUTION", 0)
    set_override(st, "YOUR_BROKERAGE_CONTRIBUTION", 0)
    set_override(st, "PARTNER_BROKERAGE_CONTRIBUTION", 0)


def _render_manual(st, disposable: int, overrides: dict) -> None:
    """Manual: explicit dollar amount per account."""
    st.caption("Enter exact annual dollars per account. Useful when savings "
               "doesn't follow income − expenses (inheritance, side income, etc.).")

    c1, c2 = st.columns(2)
    with c1:
        _manual_amount(st, "sv_manual_your_401k", "YOUR_401K_CONTRIBUTION",
                       "Your 401(k) ($/yr)", _MANUAL_401K_MAX, 500)
        _manual_amount(st, "sv_manual_your_hsa", "YOUR_HSA_CONTRIBUTION",
                       "Your HSA ($/yr)", 10_000, 250)
        _manual_amount(st, "sv_manual_your_roth", "YOUR_BACKDOOR_ROTH",
                       "Your Roth IRA / backdoor ($/yr)", 10_000, 500)
        _manual_amount(st, "sv_manual_your_brk", "YOUR_BROKERAGE_CONTRIBUTION",
                       "Your brokerage ($/yr)", 500_000, 1_000)

    with c2:
        _manual_amount(st, "sv_manual_partner_401k", "PARTNER_401K_CONTRIBUTION",
                       "Partner 401(k) ($/yr)", _MANUAL_401K_MAX, 500)
        _manual_amount(st, "sv_manual_partner_roth", "PARTNER_ROTH_CONTRIBUTION",
                       "Partner Roth IRA ($/yr)", 10_000, 500)
        _manual_amount(st, "sv_manual_partner_brk", "PARTNER_BROKERAGE_CONTRIBUTION",
                       "Partner brokerage ($/yr)", 500_000, 1_000)

    # Sum check
    overrides2 = st.session_state.get("user_overrides", {}) or {}
    manual_total = sum(safe_int(overrides2.get(k, 0), 0) for _, k, _ in _ACCOUNT_LABELS)
    if manual_total > disposable + 1000:
        st.warning(
            f"Manual contributions total **{money_md(manual_total, shorten=True)}** but "
            f"disposable is only {money_md(disposable, shorten=True)}. The simulator "
            f"uses these amounts as set; just note the math only works if you have "
            f"other income sources."
        )
    else:
        st.caption(f"**Manual total**: {money_md(manual_total, shorten=True)} of "
                   f"{money_md(disposable, shorten=True)} disposable")


def render(st) -> None:
    with st.expander("Savings", expanded=False, icon=":material/savings:"):
        render_body(st)
