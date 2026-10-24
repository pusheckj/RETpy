"""Section 5: Savings — derived total + auto/custom%/manual allocation modes."""
from __future__ import annotations

try:
    from utils.coerce import safe_int, safe_float, ensure_default
    from utils.formatting import money, money_md
    from utils.derived import (
        KEEP_AMOUNTS_MODE, SAVINGS_MODES, SAVINGS_MODE_LABELS,
        sidebar_savings_budget, custom_pct_defaults, custom_pct_amounts, pct_widget_key,
    )
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money, money_md  # type: ignore
    from ui.utils.derived import (  # type: ignore
        KEEP_AMOUNTS_MODE, SAVINGS_MODES, SAVINGS_MODE_LABELS,
        sidebar_savings_budget, custom_pct_defaults, custom_pct_amounts, pct_widget_key,
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
    ("Your Roth IRA",        "YOUR_BACKDOOR_ROTH",            "#059669"),
    ("Partner Roth IRA",     "PARTNER_ROTH_CONTRIBUTION",     "#f59e0b"),
    ("Your taxable brokerage", "YOUR_BROKERAGE_CONTRIBUTION",   "#475569"),
    ("Partner taxable brokerage", "PARTNER_BROKERAGE_CONTRIBUTION","#94a3b8"),
]


def _has_partner(overrides: dict) -> bool:
    return safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0


def _shown_accounts(overrides: dict) -> list:
    """The contribution rows to show: the partner's only when there is one."""
    return [row for row in _ACCOUNT_LABELS
            if _has_partner(overrides) or not row[1].startswith("PARTNER_")]


def _zero_partner_contributions(st, overrides: dict) -> None:
    if not _has_partner(overrides):
        for _, key, _ in _ACCOUNT_LABELS:
            if key.startswith("PARTNER_"):
                set_override(st, key, 0)


def render_body(st) -> None:
    overrides = st.session_state.get("user_overrides", {}) or {}

    # ---- Top KPI strip ----
    # The tax is the Taxes section's figure: the tax on what you actually put
    # in your 401(k)s and HSA (derived.sidebar_savings_budget), so the two
    # sections show one number. 2x2 like the Taxes section: three columns in
    # the 328px sidebar wrapped "Expenses" mid-word.
    budget = sidebar_savings_budget(st.session_state)
    income, expenses = budget["income"], budget["expenses"]
    taxes, disposable = budget["taxes"]["total"], budget["disposable"]
    row1 = st.columns(2)
    with row1[0]: st.metric("Income", money(income, shorten=True))
    with row1[1]: st.metric("− Taxes", money(taxes, shorten=True),
                            help="This year's tax, after your 401(k) and HSA savings "
                                 "lower it. The same figure as the Taxes section.")
    row2 = st.columns(2)
    with row2[0]: st.metric("− Expenses", money(expenses, shorten=True))
    with row2[1]: st.metric("= Left to save", money(disposable, shorten=True),
                            help="What's left of this year's pay after tax and "
                                 "expenses. With either Auto option the simulation "
                                 "saves all of it; your employer match comes on top.")

    if disposable <= 0:
        st.warning(
            f"Nothing is left to save "
            f"({money_md(income)} − {money_md(taxes)} − {money_md(expenses)}). "
            "Adjust income, expenses, or taxes before setting savings."
        )

    # ---- Mode selector ----
    modes = SAVINGS_MODES
    current_mode = str(get_override(st, "SAVINGS_MODE", modes[0]))
    if current_mode not in modes:
        current_mode = modes[0]
    ensure_default(st, "sv_mode", current_mode)
    mode = st.radio("Allocation strategy", modes, horizontal=False, key="sv_mode",
                    format_func=lambda m: SAVINGS_MODE_LABELS.get(m, m))
    set_override(st, "SAVINGS_MODE", mode)

    _render_employer_match(st, overrides)

    if mode == "Auto-allocate (recommended)":
        _render_auto(st, budget, overrides)
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
    # A couple-only choice: with no partner there is nothing to split.
    if _has_partner(overrides):
        ensure_default(st, "sv_primary_housing",
                       bool(get_override(st, "PRIMARY_PAYS_HOUSING", False)))
        pph = st.toggle(
            "I pay the full mortgage; we split the rest evenly",
            key="sv_primary_housing",
            help="How leftover savings split between your two taxable brokerage accounts. "
                 "Off = split all expenses evenly. On = you cover the whole "
                 "mortgage and the rest splits 50/50, so more leftover lands in "
                 "your taxable brokerage. (Car purchases stay a shared outflow. This only "
                 "re-labels which taxable brokerage gets the savings; both are taxable.)",
        )
        set_override(st, "PRIMARY_PAYS_HOUSING", bool(pph))
    else:
        set_override(st, "PRIMARY_PAYS_HOUSING", False)

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


def _render_auto(st, budget: dict, overrides: dict) -> None:
    """Auto: fill tax-advantaged first, residual to brokerage."""
    disposable = budget["disposable"]
    # The same split savings_budget settled on (its tax is the tax on these
    # 401(k)/HSA amounts); the brokerage share is net of this year's 529 and
    # after-tax 401(k), which the simulation pays first.
    allocation = budget["amounts"]
    set_aside = budget.get("set_aside", {})

    # Push the auto-derived amounts into user_overrides so the simulator picks
    # them up -- except the brokerage. Like "keep my amounts", the simulation
    # invests everything left each year (its brokerage sweep), so the figure
    # shown is this year's sweep, not a minimum to store: stored, the engine
    # enforces it as a floor in EVERY working year and sells investments to
    # fund it whenever a later year leaves less (a new home, children).
    for key, amount in allocation.items():
        set_override(st, key, 0 if "BROKERAGE" in key else int(amount))

    st.caption(
        "Fills accounts in order: **401(k) → HSA → IRA/Roth → Taxable brokerage "
        "residual**, each capped at the 2024 limits (2024 values, in today's dollars). "
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
    for idx, (label, amt) in enumerate(set_aside.items(), start=len(_ACCOUNT_LABELS)):
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
            from utils.plot_theme import style_fig, show_chart
        except ImportError:  # pragma: no cover
            from ui.utils.plot_theme import style_fig, show_chart  # type: ignore
        show_chart(st, fig, "sv_auto_alloc_chart", {"displayModeBar": False})

    # Summary line: every dollar left to save is placed.
    total = sum(allocation.values()) + sum(set_aside.values())
    st.caption(f"**Total allocated**: {money(total, shorten=True)}")


def _render_custom_pct(st, disposable: int, overrides: dict) -> None:
    """Custom %: user provides allocation percentages."""
    st.caption("Set what share of what's left to save goes to each account. "
               "Each gets that share, capped at the 2024 limits (2024 values, in today's dollars).")

    # Defaults (100% either way) and amounts come from utils.derived, which
    # also uses them to work out what's left to save (sidebar_savings_budget).
    defaults = custom_pct_defaults(overrides)
    pcts = {}
    total_pct = 0
    for label, key, _ in _shown_accounts(overrides):
        widget_key = pct_widget_key(key)
        ensure_default(st, widget_key, defaults.get(key, 0))
        v = st.slider(f"{label} %", min_value=0, max_value=100, step=1,
                      key=widget_key)
        pcts[key] = v
        total_pct += v

    for key, amount in custom_pct_amounts(pcts, disposable, overrides).items():
        set_override(st, key, amount)
    _zero_partner_contributions(st, overrides)

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
                f"(over by {total_pct - 100}%). Contributions will exceed what's left to save."
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
    spend invested in a taxable brokerage account. The engine sweeps the un-spent
    residual for any SAVINGS_MODE starting with "Auto"; the brokerage floor is
    set to 0 so it gets exactly what's left."""
    st.caption("Your 401(k), HSA and IRA stay at these amounts. Whatever else you don't "
               "spend is invested in a taxable brokerage account each year.")
    c1, c2 = st.columns(2)
    with c1:
        _manual_amount(st, "sv_manual_your_401k", "YOUR_401K_CONTRIBUTION",
                       "Your 401(k) ($/yr)", _MANUAL_401K_MAX, 500)
        _manual_amount(st, "sv_manual_your_hsa", "YOUR_HSA_CONTRIBUTION",
                       "Your HSA ($/yr)", 10_000, 250)
        _manual_amount(st, "sv_manual_your_roth", "YOUR_BACKDOOR_ROTH",
                       "Your Roth IRA ($/yr)", 10_000, 500)
    with c2:
        if _has_partner(overrides):
            _manual_amount(st, "sv_manual_partner_401k", "PARTNER_401K_CONTRIBUTION",
                           "Partner 401(k) ($/yr)", _MANUAL_401K_MAX, 500)
            _manual_amount(st, "sv_manual_partner_roth", "PARTNER_ROTH_CONTRIBUTION",
                           "Partner Roth IRA ($/yr)", 10_000, 500)
    _zero_partner_contributions(st, overrides)
    set_override(st, "YOUR_BROKERAGE_CONTRIBUTION", 0)
    set_override(st, "PARTNER_BROKERAGE_CONTRIBUTION", 0)


def _render_manual(st, disposable: int, overrides: dict) -> None:
    """Manual: explicit dollar amount per account."""
    st.caption("Enter exact annual dollars per account. Useful when savings "
               "doesn't follow income − tax − expenses (inheritance, side income, etc.).")

    c1, c2 = st.columns(2)
    with c1:
        _manual_amount(st, "sv_manual_your_401k", "YOUR_401K_CONTRIBUTION",
                       "Your 401(k) ($/yr)", _MANUAL_401K_MAX, 500)
        _manual_amount(st, "sv_manual_your_hsa", "YOUR_HSA_CONTRIBUTION",
                       "Your HSA ($/yr)", 10_000, 250)
        _manual_amount(st, "sv_manual_your_roth", "YOUR_BACKDOOR_ROTH",
                       "Your Roth IRA ($/yr)", 10_000, 500)
        _manual_amount(st, "sv_manual_your_brk", "YOUR_BROKERAGE_CONTRIBUTION",
                       "Your taxable brokerage ($/yr)", 500_000, 1_000)

    with c2:
        if _has_partner(overrides):
            _manual_amount(st, "sv_manual_partner_401k", "PARTNER_401K_CONTRIBUTION",
                           "Partner 401(k) ($/yr)", _MANUAL_401K_MAX, 500)
            _manual_amount(st, "sv_manual_partner_roth", "PARTNER_ROTH_CONTRIBUTION",
                           "Partner Roth IRA ($/yr)", 10_000, 500)
            _manual_amount(st, "sv_manual_partner_brk", "PARTNER_BROKERAGE_CONTRIBUTION",
                           "Partner taxable brokerage ($/yr)", 500_000, 1_000)
    _zero_partner_contributions(st, overrides)

    # Sum check
    overrides2 = st.session_state.get("user_overrides", {}) or {}
    manual_total = sum(safe_int(overrides2.get(k, 0), 0) for _, k, _ in _ACCOUNT_LABELS)
    if manual_total > disposable + 1000:
        st.warning(
            f"Manual contributions total **{money_md(manual_total, shorten=True)}** but "
            f"only {money_md(disposable, shorten=True)} is left to save. The simulator "
            f"uses these amounts as set; just note the math only works if you have "
            f"other income sources."
        )
    else:
        st.caption(f"**Manual total**: {money_md(manual_total, shorten=True)} of "
                   f"{money_md(disposable, shorten=True)} left to save")


def render(st) -> None:
    with st.expander("Savings", expanded=False, icon=":material/savings:"):
        render_body(st)
