"""Spending chart — stacked bars of annual spending by category over plan horizon.

Reads the spending-category inputs and lifecycle preset from
``st.session_state.user_overrides`` (written by
``components.spending_inputs``). Purely visual — does not depend on sim
results, though the ``results`` arg is accepted for signature consistency
with the other chart components.
"""
from __future__ import annotations

import contextlib

import plotly.graph_objects as go

try:
    from retirement_sim import config as cfg
except ImportError:  # pragma: no cover
    cfg = None  # type: ignore

try:
    from utils.coerce import safe_int, safe_float, as_fraction  # noqa: F401
    from components.spending_inputs import (
        SPENDING_CATEGORIES,
        compute_lifecycle_multipliers,
        first_child_window,
    )
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, as_fraction  # noqa: F401
    from ui.components.spending_inputs import (
        SPENDING_CATEGORIES,
        compute_lifecycle_multipliers,
        first_child_window,
    )

try:
    from utils.plot_theme import style_fig, show_chart, assign_colors, series_color, PLOTLY_CONFIG, is_dark
except ImportError:  # pragma: no cover
    from ui.utils.plot_theme import style_fig, show_chart, assign_colors, series_color, PLOTLY_CONFIG, is_dark


# Category keys in stacking order (housing first, then declared spending
# categories). Colors are assigned from the shared palette (at render time,
# inside ``build_category_series``, so they follow the runtime picker) so both
# the today's-dollars and future-dollars charts match.
_CATEGORY_KEYS = [
    "_AUTO_HOUSING",
    "SPEND_UTILITIES_MONTHLY",
    "SPEND_FOOD_MONTHLY",
    "SPEND_TRANSPORT_MONTHLY",
    "SPEND_HEALTH_MONTHLY",
    "SPEND_DISCRETIONARY_MONTHLY",
    "SPEND_OTHER_MONTHLY",
]


# --- Big-purchase / goal event helpers -------------------------------------
# Read the toggle + values from ``user_overrides`` (fallback: engine cfg
# defaults) and REUSE the engine cfg helpers for car / vacation so the event
# math matches the Monte Carlo engine. The cfg helpers read module-level
# globals, so we temporarily patch them for the call and restore afterwards.

_CAR_CFG_KEYS = (
    "CAR_ONETIME_ENABLED", "CAR_ONETIME_AGE", "CAR_ONETIME_AMOUNT",
    "CAR_RECURRING_ENABLED", "CAR_RECURRING_START_AGE",
    "CAR_RECURRING_EVERY_YEARS", "CAR_RECURRING_AMOUNT",
)
_VACATION_CFG_KEYS = (
    "RETIREMENT_VACATION_ENABLED", "RETIREMENT_VACATION_ANNUAL",
    "RETIREMENT_VACATION_UNTIL_AGE",
)


@contextlib.contextmanager
def _cfg_patched(overrides: dict, keys):
    """Temporarily set the given cfg globals from ``overrides`` (fallback: the
    existing cfg value) so the engine helpers see the user's live inputs."""
    if cfg is None:  # pragma: no cover
        yield
        return
    saved = {}
    try:
        for k in keys:
            saved[k] = getattr(cfg, k, None)
            if k in overrides:
                setattr(cfg, k, overrides[k])
        yield
    finally:
        for k, v in saved.items():
            setattr(cfg, k, v)


def _car_outlay(overrides: dict, age: int) -> float:
    """Car cash outlay in ``age``'s year via cfg.calculate_car_purchase."""
    if cfg is None:  # pragma: no cover
        return 0.0
    if not (bool(overrides.get("CAR_ONETIME_ENABLED", getattr(cfg, "CAR_ONETIME_ENABLED", False)))
            or bool(overrides.get("CAR_RECURRING_ENABLED", getattr(cfg, "CAR_RECURRING_ENABLED", False)))):
        return 0.0
    with _cfg_patched(overrides, _CAR_CFG_KEYS):
        return float(cfg.calculate_car_purchase(age))


def _vacation_outlay(overrides: dict, age: int, retirement_age: int) -> float:
    """Retirement-vacation spend via cfg.calculate_retirement_vacation."""
    if cfg is None:  # pragma: no cover
        return 0.0
    if not bool(overrides.get("RETIREMENT_VACATION_ENABLED",
                              getattr(cfg, "RETIREMENT_VACATION_ENABLED", False))):
        return 0.0
    with _cfg_patched(overrides, _VACATION_CFG_KEYS):
        return float(cfg.calculate_retirement_vacation(age, retirement_age))


_CHILD_CFG_KEYS = ("YOUR_AGE", "CHILDREN")


# Retirement lifestyle ages the lifecycle preset is placed by.
_LIFESTYLE_CFG_KEYS = (
    "EARLY_RETIREMENT_LEISURE_UNTIL_AGE", "RETIREMENT_LEISURE_MIN_YEARS",
    "LATE_RETIREMENT_START_AGE", "LATE_RETIREMENT_MIN_YEARS",
)


def _go_go_extra(overrides: dict, age: int, retirement_age: int) -> float:
    """The engine's extra early-retirement spending at ``age`` (travel and
    hobbies, Retirement goals), from cfg's own helpers."""
    if cfg is None or age < int(retirement_age):  # pragma: no cover
        return 0.0
    with _cfg_patched(overrides, _LIFESTYLE_CFG_KEYS + ("EARLY_RETIREMENT_LEISURE_INCREASE",
                                                       "PARTNER_AGE")):
        if age >= cfg.retirement_leisure_end_age(int(retirement_age)):
            return 0.0
        return float(cfg.retirement_leisure_increase())


def _child_expense(overrides: dict, age: int) -> float:
    """Annual child-related expense at ``age`` via ``cfg.calculate_child_expenses``.

    Reuses the ENGINE's child-cost function (config.calculate_child_expenses),
    so the chart shows the same child spending the Monte Carlo simulation
    applies. Returns 0 when there are no children or after every child has
    left home.
    """
    if cfg is None:  # pragma: no cover
        return 0.0
    calc = getattr(cfg, "calculate_child_expenses", None)
    if calc is None:
        return 0.0
    with _cfg_patched({**overrides, "CHILDREN": cfg.children_in(overrides)}, _CHILD_CFG_KEYS):
        try:
            return float(calc(int(age)))
        except Exception:
            return 0.0


def _cfg_default(key, fallback):
    return getattr(cfg, key, fallback) if cfg is not None else fallback


# Long-term care config keys read by cfg.calculate_ltc_cost (module globals).
_LTC_CFG_KEYS = ("LTC_ENABLED", "LTC_START_AGE", "LTC_ANNUAL_COST")


def _ltc_expected(overrides: dict, age: int) -> float:
    """Expected annual long-term-care cost at ``age`` (today's dollars).

    LTC is STOCHASTIC in the engine: each year from LTC_START_AGE there's an
    ``LTC_PROBABILITY`` chance of incurring the age-scaled ``LTC_ANNUAL_COST``.
    For this deterministic by-category chart we show the EXPECTED value =
    probability × the if-needed cost, reusing ``cfg.calculate_ltc_cost`` (with
    inflation_factor=1.0 so it's in today's dollars) so the age-scaling (1.15×
    at 87+, 1.25× at 90+) matches the Monte Carlo engine exactly. Returns 0 when
    LTC modeling is off or before the start age.
    """
    if cfg is None:  # pragma: no cover
        return 0.0
    if not bool(overrides.get("LTC_ENABLED", getattr(cfg, "LTC_ENABLED", False))):
        return 0.0
    calc = getattr(cfg, "calculate_ltc_cost", None)
    if calc is None:  # pragma: no cover
        return 0.0
    prob = safe_float(overrides.get("LTC_PROBABILITY",
                                    getattr(cfg, "LTC_PROBABILITY", 0.0)), 0.0)
    prob = max(0.0, min(1.0, prob))
    with _cfg_patched(overrides, _LTC_CFG_KEYS):
        try:
            full = float(calc(int(age), 1.0, True))
        except Exception:  # pragma: no cover - defensive
            return 0.0
    return full * prob


def _any_category_set(overrides: dict) -> bool:
    """True if the user has set at least one spending category explicitly,
    OR set a mortgage / rent."""
    for _, okey, _, _ in SPENDING_CATEGORIES:
        if okey in overrides:
            return True
    if safe_int(overrides.get("MORTGAGE_MONTHLY", 0), 0) > 0:
        return True
    if safe_int(overrides.get("SPEND_RENT_MONTHLY", 0), 0) > 0:
        return True
    return False


def _compute_housing_series(overrides: dict, ages: list) -> tuple:
    """Return (annual_housing_per_age_list, owns_now: bool, mortgage_payoff_age: int|None).

    Delegates entirely to ``utils.derived.mortgage_schedule``, which mirrors the
    ENGINE's amortisation (level payment at MORTGAGE_RATE_FOR_PAYOFF, the housing
    timeline's purchases and sales) and honours EXTRA principal.

    This used to compute the payoff from TERM LENGTHS alone
    (``HOUSE_MOVE_AGE + NEW_MORTGAGE_YEARS``), which had two consequences once
    extra principal existed: the "Mortgage paid off" annotation and the housing
    bars ran to the SCHEDULED payoff (age 51 on the packaged profile) while the
    sidebar correctly reported 47, and the extra payment -- real cash the engine
    charges -- never appeared as spending at all.

    ``housing`` from the schedule is scheduled payment + extra principal, so the
    extra is counted exactly once here. Nothing else in this chart adds it (the
    other series come from the SPEND_* keys), so there is no double count.
    """
    try:
        from utils.derived import mortgage_schedule
    except ImportError:  # pragma: no cover
        from ui.utils.derived import mortgage_schedule  # type: ignore

    sched = mortgage_schedule(overrides, ages)
    by_age = sched["by_age"]
    out = [by_age.get(safe_int(a, 0), {}).get("housing", 0.0) for a in ages]
    return out, sched["owns"], sched["payoff_age"]


def _owns_by_age(overrides: dict, ages: list) -> list:
    """Whether a home is owned in each year (rent before a planned purchase,
    after a sale to rent), from the same schedule as the housing series."""
    try:
        from utils.derived import mortgage_schedule
    except ImportError:  # pragma: no cover
        from ui.utils.derived import mortgage_schedule  # type: ignore
    by_age = mortgage_schedule(overrides, ages)["by_age"]
    return [bool(by_age.get(safe_int(a, 0), {}).get("owns", False)) for a in ages]


def build_category_series(ages, overrides, multipliers, retirement_age,
                          *, inflation_factors=None, st=None):
    """Ordered ``[(label, color, values-per-age)]`` for the spending stack over
    ``ages``: auto-derived housing, each declared category, retirement vacation,
    and car purchases (in stacking order, bottom → top). Values are today's
    dollars unless ``inflation_factors`` (one factor per age) scales them to
    nominal. Also returns the mortgage payoff age (or ``None``).

    Shared by ``_build_figure`` here and ``components.spending_destination_chart``
    so both charts stay consistent.
    """
    # Assigned at call time (not module import) so the palette follows the
    # runtime color picker.
    category_colors = assign_colors(_CATEGORY_KEYS, st)

    def _apply(ys):
        if inflation_factors is None:
            return ys
        return [v * f for v, f in zip(ys, inflation_factors)]

    series = []
    housing_series, _, payoff_age = _compute_housing_series(overrides, ages)
    owns = _owns_by_age(overrides, ages)
    # A fixed-rate mortgage is a FIXED NOMINAL payment, so it must NOT be
    # inflated in the future-dollars view — it stays flat in nominal terms year
    # to year. Rent, by contrast, is a real cost that rises with inflation, so
    # it IS scaled. (In today's-dollars mode ``_apply`` is a no-op for both.)
    # A housing timeline can mix the two (rent, then a purchase), so per year.
    scaled = _apply(housing_series)
    housing_series = [v if o else sv for v, sv, o in zip(housing_series, scaled, owns)]
    if any(v > 0 for v in housing_series):
        housing_label = ("Housing (mortgage)" if all(owns) else
                         "Housing (rent)" if not any(owns) else "Housing")
        series.append((housing_label, category_colors["_AUTO_HOUSING"], housing_series))

    for _, okey, label, default in SPENDING_CATEGORIES:
        monthly = safe_int(overrides.get(okey, default), default)
        annual_today = monthly * 12
        cat_mults = multipliers.get(okey, {})
        ys = _apply([annual_today * cat_mults.get(a, 1.0) for a in ages])
        series.append((label, category_colors.get(okey, "#94a3b8"), ys))

    # Children — annual child-rearing cost from the engine's own function
    # (ramps up as kids are born, drops as each leaves home). Only shown when
    # kids are planned (non-zero in some year). Palette-series colors start
    # past the category keys (indices 0..len-1) so they don't collide.
    child_series = _apply([_child_expense(overrides, a) for a in ages])
    if any(v > 0 for v in child_series):
        series.append(("Children", series_color(len(_CATEGORY_KEYS), st), child_series))

    vac_series = _apply([_vacation_outlay(overrides, a, retirement_age) for a in ages])
    if any(v > 0 for v in vac_series):
        series.append(("Retirement vacation", series_color(len(_CATEGORY_KEYS) + 1, st), vac_series))

    gogo_series = _apply([_go_go_extra(overrides, a, retirement_age) for a in ages])
    if any(v > 0 for v in gogo_series):
        series.append(("Early-retirement extra", series_color(len(_CATEGORY_KEYS) + 4, st), gogo_series))

    car_series = _apply([_car_outlay(overrides, a) for a in ages])
    if any(v > 0 for v in car_series):
        series.append(("Car purchase", series_color(len(_CATEGORY_KEYS) + 2, st), car_series))

    # Long-term care — EXPECTED annual cost (probability-weighted) from the
    # engine's own age-scaled formula. Only shown when LTC modeling is on and
    # non-zero in some year (i.e. from the start age onward).
    ltc_series = _apply([_ltc_expected(overrides, a) for a in ages])
    if any(v > 0 for v in ltc_series):
        series.append(("Long-term care (expected)", series_color(len(_CATEGORY_KEYS) + 3, st), ltc_series))

    return series, payoff_age


def _vline_label_side(x, ages: list) -> str:
    """Plotly ``annotation_position`` for a vertical reference line at ``x``.

    Plotly anchors a "top left" label to the LEFT of the line, so a fixed side
    clips the text against the plot edge whenever the line sits near that edge
    (at tablet width the spending chart's plot area is ~215px, and
    "Retirement (age 40)" on a 30-90 age axis rendered as "etirement (age 40)").
    Point the label into the wider half instead.
    """
    try:
        lo, hi = float(min(ages)), float(max(ages))
        if hi <= lo:
            return "top right"
        return "top right" if (float(x) - lo) / (hi - lo) < 0.5 else "top left"
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return "top right"


def _build_figure(
    ages: list,
    overrides: dict,
    multipliers: dict,
    current_age: int,
    retirement_age: int,
    plan_until: int,
    preset: str,
    *,
    inflation_factors: list | None = None,
    four_pct_series: list | None = None,
    four_pct_color: str = "#0f172a",
    mortgage_color: str = "#1d4ed8",
    title: str,
    subtitle: str,
    yaxis_title: str,
    st=None,
) -> go.Figure:
    """Build the stacked-area spending figure.

    If ``inflation_factors`` is provided (one multiplier per entry in
    ``ages``), each category's today's-dollars series is scaled by the
    matching factor to produce nominal (future) dollars. Otherwise the
    series are left in today's dollars.
    """
    fig = go.Figure()

    # Stacked bars per category (housing, declared categories, vacation, car),
    # matching the other charts. Series are built once via the shared helper.
    series, payoff_age = build_category_series(
        ages, overrides, multipliers, retirement_age,
        inflation_factors=inflation_factors, st=st,
    )
    for label, color, ys in series:
        fig.add_trace(go.Bar(
            x=ages,
            y=ys,
            name=label,
            marker_color=color,
            marker_line_width=0,
            hovertemplate=f"{label}: $%{{y:,.0f}}/yr<extra></extra>",
        ))

    # "4% rule" overlay: 4% of the projected portfolio each year = a per-year
    # gauge of how much you could theoretically spend. Values arrive in today's
    # dollars and are inflated to match the chart's dollar mode. Drawn on the
    # SAME y-axis as the category bars so it's directly comparable (the axis
    # expands to fit it).
    has_4pct = four_pct_series is not None and any(v is not None for v in four_pct_series)
    if has_4pct:
        if inflation_factors is not None:
            fp = [None if v is None else v * f for v, f in zip(four_pct_series, inflation_factors)]
        else:
            fp = list(four_pct_series)
        fig.add_trace(go.Scatter(
            x=ages, y=fp, name="4% rule (safe spend)",
            mode="lines", connectgaps=False,
            line=dict(color=four_pct_color, width=2, dash="dot"),
            hovertemplate="4% rule safe spend: $%{y:,.0f}/yr<extra></extra>",
        ))
    if current_age <= retirement_age <= plan_until:
        fig.add_vline(
            x=retirement_age,
            line_dash="dash",
            line_color="#94a3b8",
            annotation_text=f"Retirement (age {retirement_age})",
            # Anchor toward whichever side of the line has room. A fixed
            # "top left" clipped the label against the plot's left edge
            # ("etirement (age 40)") whenever retirement sat early in the age
            # range — which is the common case for an early-retirement plan.
            annotation_position=_vline_label_side(retirement_age, ages),
            annotation_font=dict(size=10, color="#64748b"),
        )

    # Vertical reference line at mortgage payoff age (auto-housing drop).
    if payoff_age is not None and current_age < payoff_age <= plan_until:
        fig.add_vline(
            x=payoff_age,
            line_dash="dot",
            line_color=mortgage_color,
            annotation_text=f"Mortgage paid off (age {payoff_age})",
            annotation_position=_vline_label_side(payoff_age, ages),
            # Dropped one line below the retirement label: both annotations sit
            # on the top row, and on a narrow plot they overlapped each other
            # into unreadable text.
            annotation_yshift=-15,
            annotation_font=dict(size=10, color=mortgage_color),
        )

    fig.update_layout(
        barmode="stack",
        bargap=0.15,
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
        yaxis=dict(title=yaxis_title, gridcolor="#f1f5f9",
                   zeroline=False, tickfont=dict(color="#64748b"),
                   rangemode="tozero", tickformat="$,.3~s"),
        hovermode="x unified", dragmode="pan",
        legend=dict(orientation="v", yanchor="top", y=1.0, xanchor="left",
                    x=1.02, bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#64748b", size=12)),
        uirevision="keep",
    )

    return fig


def render(st, results: dict = None, chart_key: str = "spending_main") -> None:
    overrides = st.session_state.get("user_overrides", {}) or {}

    if not _any_category_set(overrides):
        st.info("Set spending patterns in the sidebar to see projected expenses.")
        return

    current_age = safe_int(overrides.get("YOUR_AGE", 25), 25)
    retirement_age = safe_int(overrides.get("TARGET_RETIREMENT_AGE", 55), 55)
    plan_until = cfg.plan_end_age(overrides) if cfg is not None else safe_int(
        overrides.get("PLAN_UNTIL_AGE", 90), 90)
    yufc, leave_age = first_child_window(
        cfg.children_in(overrides) if cfg is not None else [])
    preset = str(overrides.get("SPEND_LIFECYCLE_PRESET", "Flat (no change)"))
    inflation_rate = as_fraction(overrides.get("EXPECTED_INFLATION", 0.0275), 0.0275)

    ages = list(range(current_age, plan_until + 1))
    if not ages:
        st.info("No plan horizon to display (check current age and plan end age).")
        return

    # The engine's own preset mapping, with this plan's children and lifestyle
    # ages patched on (empty-nest follows every child at home).
    with _cfg_patched(overrides, _CHILD_CFG_KEYS + _LIFESTYLE_CFG_KEYS):
        multipliers = compute_lifecycle_multipliers(
            preset=preset,
            current_age=current_age,
            retirement_age=retirement_age,
            plan_until_age=plan_until,
            years_until_first_child=yufc,
            child_leaves_home_age=leave_age,
        )

    # 4% rule overlay (BOTH charts): 4% of the MEDIAN projected portfolio each
    # year (median_trajectory now spans the full horizon) = a per-year gauge of
    # how much you could theoretically spend. Drawn on its own labeled right
    # axis so a large safe-spend figure doesn't squash the category bars.
    four_pct_today = None
    if results:
        pr = results.get("primary_result", {}) or {}
        median_by_age = {}
        for a, bal in (pr.get("median_trajectory") or []):
            try:
                median_by_age[int(a)] = float(bal)
            except (TypeError, ValueError):
                continue
        if median_by_age:
            four_pct_today = [
                0.04 * median_by_age[a] if a in median_by_age else None
                for a in ages
            ]

    inflation_factors = [(1.0 + inflation_rate) ** (age - current_age) for age in ages]

    # Single chart with a Today's / Future-dollars toggle (wrapped in a fragment
    # so flipping it reruns only this chart, not the whole app).
    def _render_body() -> None:
        # 4% line color: dark on the light theme, light on the dark theme (a
        # near-black dotted line is invisible on the dark background). Computed
        # HERE (inside the fragment) so it always reflects the current theme.
        four_pct_color = "#e2e8f0" if is_dark(st) else "#0f172a"
        mortgage_color = "#60a5fa" if is_dark(st) else "#1d4ed8"
        mode = st.radio(
            "Dollars",
            options=["Today's $", "Future $"],
            horizontal=True, key=f"{chart_key}_dollars_mode",
            label_visibility="collapsed",
        )
        future = str(mode).startswith("Future")

        if future:
            fig = _build_figure(
                ages, overrides, multipliers, current_age, retirement_age, plan_until, preset,
                inflation_factors=inflation_factors,
                four_pct_series=four_pct_today, four_pct_color=four_pct_color,
                mortgage_color=mortgage_color,
                title="Projected annual spending by category (future dollars)",
                subtitle=(f"Nominal dollars · inflated at {inflation_rate * 100:.2f}%/yr · "
                          f"lifecycle: {preset}"),
                yaxis_title="Annual spending ($, nominal)",
                st=st,
            )
        else:
            fig = _build_figure(
                ages, overrides, multipliers, current_age, retirement_age, plan_until, preset,
                four_pct_series=four_pct_today, four_pct_color=four_pct_color,
                mortgage_color=mortgage_color,
                title="Projected annual spending by category",
                subtitle=f"Today's dollars · lifecycle: {preset}",
                yaxis_title="Annual spending ($, today)",
                st=st,
            )
        show_chart(st, fig, f"{chart_key}_{'nominal' if future else 'today'}_{'dk' if is_dark(st) else 'lt'}", PLOTLY_CONFIG)

        base_caption = (
            "Stacked bars show each category's annual spending, including "
            "**children** (rises as kids are born, drops as each leaves home) "
            "and, when enabled, **long-term care** as the *expected* yearly cost "
            "(probability × age-scaled care cost — the cost if care is needed is "
            "much larger). "
            "**Housing is auto-derived** from your mortgage / rent inputs; the "
            "mortgage bar drops to $0 at payoff. The sidebar lifecycle preset "
            "scales the other categories at key ages. The dotted **4% rule** line "
            "(shown after you run the simulation) is 4% of your median projected "
            "portfolio **each year** — a gauge of safe annual spending, on the "
            "same axis as the bars."
        )
        if future:
            st.caption(
                base_caption + " In **future (nominal) dollars** — each year is "
                "grown by inflation, so totals look larger even though real "
                "purchasing power is unchanged."
            )
        else:
            st.caption(
                base_caption + " In **today's dollars** (constant purchasing "
                "power)."
            )

    # Rendered directly (not in an st.fragment): a fragment isolates the toggle
    # rerun but its execution context doesn't see the session theme, so is_dark()
    # / style_fig() would render the chart in light colors even in dark mode.
    _render_body()
