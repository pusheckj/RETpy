"""Income over time — full-horizon stacked chart of GROSS household income
broken out by source, across age.

Two phases share a single age axis:

  * WORKING YEARS (current_age .. retirement_age-1): deterministic from the
    sidebar inputs in ``st.session_state.user_overrides`` — your + partner
    base / bonus / RSU / other income. Uses ``YOUR_COMPENSATION_BY_AGE`` when
    present (projected past the last table age with ``YOUR_SALARY_GROWTH_RATE``),
    else falls back to the flat ``YOUR_BASE_SALARY``/``YOUR_BONUS_AMOUNT``/
    ``YOUR_RSU_AMOUNT`` grown by the same rate. Partner from the flat
    ``PARTNER_*`` fields grown by ``PARTNER_SALARY_GROWTH_RATE``. This mirrors
    ``utils.sim_runner._approximate_savings_contributions`` so the two agree,
    and auto-updates from the sidebar (no Run required).

  * RETIREMENT YEARS (retirement_age .. plan_until): enriched from Monte Carlo
    results when available — ``results['primary_result']['income_sources_by_year']``
    (Social Security + portfolio drawdown by source: each age's MEDIAN draw
    across the runs that last the plan, split in their average source mix --
    see ``utils.sim_runner._median_withdrawal_log_from_data``; the caption from
    ``retirement_caption`` says so). With no results, Social
    Security is still shown deterministically via
    ``cfg.calculate_social_security`` (guarded), and a caption invites the user
    to run the sim for the full drawdown breakdown.

A "Today's dollars" vs "Future (nominal) dollars" toggle inflates every year's
values by ``(1 + EXPECTED_INFLATION) ** (age - current_age)`` when future mode
is selected — the same real-vs-nominal pattern as ``components.spending_chart``.
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from retirement_sim import config as cfg
except ImportError:  # pragma: no cover
    cfg = None  # type: ignore

try:
    from utils.coerce import safe_int, safe_float, as_fraction
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, as_fraction

try:
    from utils.plot_theme import style_fig, show_chart, concept_color, PLOTLY_CONFIG
except ImportError:  # pragma: no cover
    from ui.utils.plot_theme import style_fig, show_chart, concept_color, PLOTLY_CONFIG


# --- Ordered source labels (stacking order, bottom -> top). Working-years
# sources first, then retirement-years sources. Colors are assigned over this
# FULL list so every source keeps a consistent color across both phases and
# both dollar modes. --------------------------------------------------------
_WORKING_LABELS = [
    "Your base salary",
    "Your bonus",
    "Your RSU",
    "Your other income",
    "Partner base salary",
    "Partner bonus",
    "Partner RSU",
    "Partner other",
]
_RETIREMENT_LABELS = [
    "Social Security",
    "Traditional 401(k)/IRA",
    "Roth",
    "Taxable brokerage",
    "HSA",
]
_ALL_LABELS = _WORKING_LABELS + _RETIREMENT_LABELS


def _comp_lookup(comp_by_age: dict, age: int):
    """Return the comp row for ``age`` from ``comp_by_age`` handling int OR str
    keys (the table may be keyed either way depending on its source)."""
    if not comp_by_age:
        return None
    if age in comp_by_age:
        return comp_by_age[age]
    if str(age) in comp_by_age:
        return comp_by_age[str(age)]
    return None


def _comp_ages(comp_by_age: dict) -> list:
    """Numeric ages present in ``comp_by_age`` (keys may be int or str)."""
    ages = []
    for k in comp_by_age.keys():
        ages.append(safe_int(k, None) if not isinstance(k, int) else k)
    return [a for a in ages if a is not None]


def _your_income_for_age(overrides: dict, comp_by_age: dict, age: int,
                         growth: float) -> tuple:
    """(base, bonus, rsu, other) for the primary user in ``age``'s year.

    Prefer the compensation table (base/bonus/rsu_gross by age), projecting
    past the last table age with ``growth``. If the table is absent, fall back
    to the flat YOUR_BASE_SALARY/BONUS/RSU inputs grown by ``growth`` from
    current age. ``other`` always comes from the flat YOUR_OTHER_INCOME.
    """
    # "Other income" grows at the same salary growth rate as every other
    # income type (from the current age), so ALL income types compound at the
    # listed rate — not just base/bonus/RSU.
    current_age = safe_int(overrides.get("YOUR_AGE",
                                         getattr(cfg, "YOUR_AGE", 25) if cfg else 25), 25)
    other_factor = (1.0 + growth) ** max(0, age - current_age)
    other = safe_float(overrides.get("YOUR_OTHER_INCOME",
                                     getattr(cfg, "YOUR_OTHER_INCOME", 0) if cfg else 0), 0.0) * other_factor

    comp_ages = _comp_ages(comp_by_age)
    if comp_ages:
        row = _comp_lookup(comp_by_age, age)
        if row is not None:
            base = safe_float(row.get("base", 0), 0.0)
            bonus = safe_float(row.get("bonus", 0), 0.0)
            rsu = safe_float(row.get("rsu_gross", 0), 0.0)
            return base, bonus, rsu, other
        # Beyond the table: project the last known row forward by growth.
        last_age = max(comp_ages)
        last_row = _comp_lookup(comp_by_age, last_age) or {}
        factor = (1.0 + growth) ** max(0, age - last_age)
        base = safe_float(last_row.get("base", 0), 0.0) * factor
        bonus = safe_float(last_row.get("bonus", 0), 0.0) * factor
        rsu = safe_float(last_row.get("rsu_gross", 0), 0.0) * factor
        return base, bonus, rsu, other

    # No comp table — flat inputs grown from current age.
    current_age = safe_int(overrides.get("YOUR_AGE",
                                         getattr(cfg, "YOUR_AGE", 25) if cfg else 25), 25)
    factor = (1.0 + growth) ** max(0, age - current_age)
    base = safe_float(overrides.get("YOUR_BASE_SALARY",
                                    getattr(cfg, "YOUR_BASE_SALARY", 0) if cfg else 0), 0.0) * factor
    bonus = safe_float(overrides.get("YOUR_BONUS_AMOUNT",
                                     getattr(cfg, "YOUR_BONUS_AMOUNT", 0) if cfg else 0), 0.0) * factor
    rsu = safe_float(overrides.get("YOUR_RSU_AMOUNT",
                                   getattr(cfg, "YOUR_RSU_AMOUNT", 0) if cfg else 0), 0.0) * factor
    return base, bonus, rsu, other


def _partner_income_for_age(overrides: dict, age: int, current_age: int,
                            growth: float) -> tuple:
    """(base, bonus, rsu, other) for the partner in ``age``'s year — flat
    inputs grown by ``growth`` from current age."""
    factor = (1.0 + growth) ** max(0, age - current_age)
    base = safe_float(overrides.get("PARTNER_BASE_SALARY",
                                    getattr(cfg, "PARTNER_BASE_SALARY", 0) if cfg else 0), 0.0) * factor
    bonus = safe_float(overrides.get("PARTNER_BONUS_AMOUNT",
                                     getattr(cfg, "PARTNER_BONUS_AMOUNT", 0) if cfg else 0), 0.0) * factor
    rsu = safe_float(overrides.get("PARTNER_RSU_AMOUNT",
                                   getattr(cfg, "PARTNER_RSU_AMOUNT", 0) if cfg else 0), 0.0) * factor
    other = safe_float(overrides.get("PARTNER_OTHER_INCOME",
                                     getattr(cfg, "PARTNER_OTHER_INCOME", 0) if cfg else 0), 0.0) * factor
    return base, bonus, rsu, other


def _retirement_ss_for_age(age: int, ss_claim_age: int,
                           overrides: dict | None = None) -> float:
    """Deterministic household Social Security for ``age`` (today's dollars),
    via cfg.calculate_social_security. Guarded — returns 0 on any issue.

    The INCLUDE_SOCIAL_SECURITY toggle must be read from ``overrides`` FIRST
    (cfg's module default is True and sim_runner restores it after every run),
    otherwise unchecking "Include Social Security" in the sidebar left this
    chart still stacking an SS band from the claim age onward.
    """
    if cfg is None:
        return 0.0
    _ov = overrides or {}
    include_ss = _ov.get("INCLUDE_SOCIAL_SECURITY",
                         getattr(cfg, "INCLUDE_SOCIAL_SECURITY", False))
    if not bool(include_ss):
        return 0.0
    # (No claim-age gate: the partner may claim at their own age, and
    # calculate_social_security is already 0 before anyone has claimed.)
    calc = getattr(cfg, "calculate_social_security", None)
    if calc is None:
        return 0.0
    try:
        return float(calc(age, ss_claim_age))
    except Exception:  # pragma: no cover - defensive
        return 0.0


def build_income_series(
    overrides: dict,
    results: dict | None,
    current_age: int,
    retirement_age: int,
    plan_until: int,
    *,
    future_dollars: bool = False,
    inflation_rate: float = 0.0275,
) -> tuple:
    """Build the per-source income series across the full horizon.

    Returns ``(ages, series)`` where ``ages`` is the ordered age axis and
    ``series`` maps each source label (subset of ``_ALL_LABELS``, in stacking
    order) to a per-age list of dollar values. Values are in today's dollars
    unless ``future_dollars`` is True, in which case each year's value is
    scaled by ``(1 + inflation_rate) ** (age - current_age)``.

    Only sources that are non-zero in at least one year are included.
    """
    ages = list(range(current_age, plan_until + 1))
    if not ages:
        return [], {}

    # Seed every possible label with zeros so the stacking order is stable.
    series = {label: [0.0] * len(ages) for label in _ALL_LABELS}

    comp_by_age = overrides.get("YOUR_COMPENSATION_BY_AGE",
                                getattr(cfg, "YOUR_COMPENSATION_BY_AGE", {}) if cfg else {}) or {}
    your_growth = as_fraction(overrides.get("YOUR_SALARY_GROWTH_RATE",
                              getattr(cfg, "YOUR_SALARY_GROWTH_RATE", 0.02) if cfg else 0.02), 0.02)
    partner_growth = as_fraction(overrides.get("PARTNER_SALARY_GROWTH_RATE",
                                 getattr(cfg, "PARTNER_SALARY_GROWTH_RATE", 0.02) if cfg else 0.02), 0.02)
    ss_claim_age = safe_int(overrides.get("SS_CLAIM_AGE",
                            getattr(cfg, "SS_CLAIM_AGE", 67) if cfg else 67), 67)

    # Partner's own working boundary (separate-partner-retirement-age feature).
    # ``x`` here is the PRIMARY's age; the partner's age that year is offset by
    # the fixed starting age gap. PARTNER_RETIREMENT_AGE is expressed in the
    # partner's own age. When it's unset (None), the partner works exactly while
    # the primary does -> identical to before. No partner, no partner income.
    _pra_raw = overrides.get("PARTNER_RETIREMENT_AGE",
                             getattr(cfg, "PARTNER_RETIREMENT_AGE", None) if cfg else None)
    _partner_age0 = safe_int(overrides.get("PARTNER_AGE",
                             getattr(cfg, "PARTNER_AGE", 0) if cfg else 0), 0)
    _has_partner = _partner_age0 > 0
    _age_gap = current_age - _partner_age0  # primary_age - partner_age

    def _partner_working(primary_age: int) -> bool:
        if not _has_partner:
            return False
        if _pra_raw is None:
            return primary_age < retirement_age
        return (primary_age - _age_gap) < safe_int(_pra_raw, retirement_age)

    # Retirement-year income sources from Monte Carlo results, keyed by age.
    ret_rows = {}
    if results:
        pr = results.get("primary_result", {}) or {}
        for row in (pr.get("income_sources_by_year", []) or []):
            try:
                ret_rows[int(row.get("age"))] = row
            except (TypeError, ValueError):
                continue

    for i, age in enumerate(ages):
        # --- Primary working income (deterministic) ---
        if age < retirement_age:
            yb, ybo, yr, yo = _your_income_for_age(overrides, comp_by_age, age, your_growth)
            series["Your base salary"][i] = yb
            series["Your bonus"][i] = ybo
            series["Your RSU"][i] = yr
            series["Your other income"][i] = yo

        # --- Partner working income (their OWN retirement boundary) ---
        # Runs independently of the primary's phase so a partner who keeps
        # working after the primary retires still shows earned income, and one
        # who retires first drops to zero on time.
        if _partner_working(age):
            pb, pbo, pr_, po = _partner_income_for_age(overrides, age, current_age, partner_growth)
            series["Partner base salary"][i] = pb
            series["Partner bonus"][i] = pbo
            series["Partner RSU"][i] = pr_
            series["Partner other"][i] = po

        # --- Retirement drawdown + SS once the PRIMARY has retired ---
        if age >= retirement_age:
            row = ret_rows.get(age)
            if row is not None:
                series["Social Security"][i] = safe_float(row.get("ss", 0), 0.0)
                series["Traditional 401(k)/IRA"][i] = safe_float(row.get("traditional", 0), 0.0)
                series["Roth"][i] = safe_float(row.get("roth", 0), 0.0)
                series["Taxable brokerage"][i] = safe_float(row.get("taxable", 0), 0.0)
                series["HSA"][i] = safe_float(row.get("hsa", 0), 0.0)
            else:
                # No sim results (or this age not covered): show SS only.
                series["Social Security"][i] = _retirement_ss_for_age(
                    age, ss_claim_age, overrides)

    # Apply inflation (future/nominal dollars) if requested.
    if future_dollars:
        factors = [(1.0 + inflation_rate) ** (age - current_age) for age in ages]
        for label in series:
            series[label] = [v * f for v, f in zip(series[label], factors)]

    # Drop all-zero sources, preserving stacking order.
    ordered = {
        label: series[label]
        for label in _ALL_LABELS
        if any(v > 0 for v in series[label])
    }
    return ages, ordered


def build_figure(
    ages: list,
    series: dict,
    current_age: int,
    retirement_age: int,
    plan_until: int,
    *,
    title: str,
    subtitle: str,
    yaxis_title: str,
    colors: dict,
    roth_conversion: list | None = None,
) -> go.Figure:
    """Assemble the stacked bar figure from a prebuilt ``series`` dict."""
    fig = go.Figure()
    for label, values in series.items():
        fig.add_trace(go.Bar(
            x=ages,
            y=values,
            name=label,
            marker_color=colors.get(label, "#94a3b8"),
            hovertemplate=f"{label}: $%{{y:,.0f}}<extra></extra>",
        ))

    # Roth conversions are traditional->Roth TRANSFERS, not income/drawdown, so
    # they're drawn as a dashed overlay line (not a stacked bar) to avoid reading
    # as household income.
    if roth_conversion is not None and any((v or 0) > 0 for v in roth_conversion):
        fig.add_trace(go.Scatter(
            x=ages, y=roth_conversion,
            name="Roth conversion (transfer)",
            mode="lines+markers",
            line=dict(color="#7c3aed", dash="dot", width=2),
            marker=dict(size=5, symbol="diamond", color="#7c3aed"),
            hovertemplate="Roth conversion (transfer): $%{y:,.0f}<extra></extra>",
        ))

    # Retirement reference line so the two phases read as one continuous axis.
    if current_age <= retirement_age <= plan_until:
        fig.add_vline(
            x=retirement_age,
            line_dash="dash",
            line_color="#94a3b8",
            annotation_text=f"Retirement (age {retirement_age})",
            annotation_position="top left",
            annotation_font=dict(size=10, color="#64748b"),
        )

    fig.update_layout(
        barmode="stack",
        title=dict(
            text=(
                f"<b>{title}</b><br>"
                f"<span style='font-size:13px;color:#64748b;'>{subtitle}</span>"
            ),
            x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
        ),
        height=420,
        margin=dict(l=50, r=170, t=70, b=50),
        xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False,
                   tickfont=dict(color="#64748b"), fixedrange=False),
        yaxis=dict(title=yaxis_title, gridcolor="#f1f5f9", zeroline=False,
                   tickfont=dict(color="#64748b"), rangemode="tozero",
                   tickformat="$,.3~s"),
        hovermode="x unified", dragmode="pan",
        legend=dict(orientation="v", yanchor="top", y=1.0, xanchor="left",
                    x=1.02, bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#64748b", size=12)),
        uirevision="keep",
    )
    return fig


def retirement_caption(results: dict | None) -> str:
    """What the retirement-year bars are: each age's median draw across runs,
    not one run's (whose long-term-care years or giant forced RMDs would read
    as the typical plan)."""
    if not results:
        return "Run the simulation to see retirement portfolio drawdown by source."
    basis = (results.get("primary_result", {}) or {}).get("withdrawals_basis") or {}
    n = safe_int(basis.get("n_runs"), 0)
    runs = f"{n:,} simulated runs" if n else "simulated runs"
    who = (f"the {runs} that last the whole plan" if basis.get("survivors_only", True)
           else f"all {runs} (none last the whole plan)")
    return (f"Retirement years show the median year across {who}, split by source "
            "in their average mix. Costs that hit only some runs, such as a year of "
            "long-term care or a large required minimum distribution, count toward "
            "the success rate but aren't drawn as the typical year.")


def render(st, results: dict = None, chart_key: str = "income_over_time_main") -> None:
    overrides = st.session_state.get("user_overrides", {}) or {}

    current_age = safe_int(overrides.get("YOUR_AGE",
                           getattr(cfg, "YOUR_AGE", 25) if cfg else 25), 25)
    retirement_age = safe_int(overrides.get("TARGET_RETIREMENT_AGE",
                              getattr(cfg, "TARGET_RETIREMENT_AGE", 55) if cfg else 55), 55)
    plan_until = (cfg.plan_end_age(overrides) if cfg else
                  safe_int(overrides.get("PLAN_UNTIL_AGE", 90), 90))
    inflation_rate = as_fraction(overrides.get("EXPECTED_INFLATION", 0.0275), 0.0275)

    # Assign palette colors at render time so they follow the runtime palette.
    colors = {l: concept_color(l, st) for l in _ALL_LABELS}

    ages = list(range(current_age, plan_until + 1))
    if not ages:
        st.info("Set your current age and plan end age in the sidebar to see income over time.")
        return

    def _render_body() -> None:
        # Dollars-mode toggle (real vs nominal), keyed uniquely per chart instance.
        mode = st.radio(
            "Dollars",
            options=["Today's $", "Future $"],
            horizontal=True,
            key=f"{chart_key}_dollars_mode",
            label_visibility="collapsed",
        )
        future_dollars = str(mode).startswith("Future")

        series_ages, series = build_income_series(
            overrides, results, current_age, retirement_age, plan_until,
            future_dollars=future_dollars, inflation_rate=inflation_rate,
        )

        # Roth-conversion (transfer) overlay, aligned to the same age axis and
        # dollar mode as the bars. Sourced from the sim's income_sources_by_year.
        roth_conversion = None
        if results:
            conv_by_age = {}
            for row in ((results.get("primary_result", {}) or {}).get("income_sources_by_year", []) or []):
                try:
                    conv_by_age[int(row.get("age"))] = safe_float(row.get("roth_conversion", 0), 0.0)
                except (TypeError, ValueError):
                    continue
            if any(v > 0 for v in conv_by_age.values()):
                factors = ([(1.0 + inflation_rate) ** (a - current_age) for a in series_ages]
                           if future_dollars else [1.0] * len(series_ages))
                roth_conversion = [conv_by_age.get(a, 0.0) * f for a, f in zip(series_ages, factors)]

        if not series:
            st.info(
                "Set your income in the sidebar (base salary, bonus, RSU) to see "
                "your household income projected over time."
            )
            return

        if future_dollars:
            subtitle = (
                f"Gross household income by source · future (nominal) dollars · "
                f"inflated at {inflation_rate * 100:.2f}%/yr"
            )
            yaxis_title = "Annual gross income ($, nominal)"
        else:
            subtitle = "Gross household income by source · today's dollars"
            yaxis_title = "Annual gross income ($, today)"

        fig = build_figure(
            series_ages, series, current_age, retirement_age, plan_until,
            title="Income over time",
            subtitle=subtitle,
            yaxis_title=yaxis_title,
            colors=colors,
            roth_conversion=roth_conversion,
        )

        show_chart(st, fig, chart_key, PLOTLY_CONFIG)

        st.caption(retirement_caption(results))

    # Isolate the dollars toggle in a fragment so switching modes reruns only
    # this chart, not the whole app. Fall back to an inline call if the running
    # Streamlit build doesn't expose st.fragment.
    fragment = getattr(st, "fragment", None)
    if fragment is not None:
        try:
            _render_body = fragment(_render_body)
        except Exception:  # pragma: no cover - defensive
            pass
    _render_body()
