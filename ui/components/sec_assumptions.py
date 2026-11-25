"""Section 7: Assumptions — one-click presets, spending rules and pre-Medicare healthcare.

The investing assumptions (returns, inflation, glide path, Roth conversion) are
drawn by ``render_investing_body`` inside the Investments section
(components/sec_investments.py); this section keeps the rest.
"""
from __future__ import annotations

try:
    from utils.section_icon import section_expander
except ImportError:  # pragma: no cover
    from ui.utils.section_icon import section_expander  # type: ignore

try:
    from utils.coerce import safe_int, safe_float, as_fraction, ensure_default
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, as_fraction, ensure_default  # type: ignore

try:
    from retirement_sim import config as cfg
except ImportError:  # pragma: no cover
    cfg = None

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore


try:
    from utils.slider_input import slider_with_box
except ImportError:  # pragma: no cover
    from ui.utils.slider_input import slider_with_box  # type: ignore

try:
    from utils import health_area
except ImportError:  # pragma: no cover
    from ui.utils import health_area  # type: ignore

try:
    from retirement_sim import healthcare_data as hd
except ImportError:  # pragma: no cover
    hd = None


def _section_label(st, txt):
    st.markdown(f'<div style="font-size: 13px; color: #64748b; text-transform: uppercase; '
                f'letter-spacing: 0.05em; margin: 14px 0 6px 0;">{txt}</div>',
                unsafe_allow_html=True)


def render_investing_body(st) -> None:
    """Returns, inflation, glide path and Roth conversion (shown in Investments)."""
    # ===== Returns =====
    _section_label(st, "Returns")
    scen_options = ["Conservative", "Historical", "Pessimistic", "Forward-looking"]
    current_scen = str(get_override(st, "ACTIVE_RETURN_SCENARIO", "historical")).lower()
    scen_map = {"conservative": "Conservative", "historical": "Historical", "pessimistic": "Pessimistic",
                "forward": "Forward-looking"}
    current_label = scen_map.get(current_scen, "Historical")
    ensure_default(st, "sa_scenario", current_label)
    scen = st.radio("Return scenario", scen_options, horizontal=True, key="sa_scenario",
                    help="Average real (after-inflation) yearly stock/bond returns. Conservative: 7%/2%. Historical: 8.7%/3.1%. Pessimistic: 5%/1%. "
                         "Forward-looking: firms' 2026 forecasts for the next 10-15 years, about 5.1%/2.4% "
                         "(stocks grow about 3.9% a year after the ups and downs). "
                         "Ups and downs make money grow a little slower than the average (about 6.3% a year for 80/20 Historical). "
                         "The simulation includes that. "
                         "Historical is the default and the most optimistic; Conservative is closer to typical planner assumptions. "
                         "Forward-looking is lower because stock prices are high today compared with company earnings.")
    set_override(st, "ACTIVE_RETURN_SCENARIO", {v: k for k, v in scen_map.items()}.get(scen or current_label, "historical"))

    cur_stock_pct = max(0.0, min(100.0, as_fraction(get_override(st, "STOCK_ALLOCATION", 0.80), 0.80) * 100))
    ensure_default(st, "sa_stock_alloc", cur_stock_pct)
    v = slider_with_box(st, "Stock allocation (%)", 0, 100, 5, key="sa_stock_alloc", unit="%",
                        help="The share of your investments held in stocks. The rest is bonds. "
                             "More stock means higher expected returns and bigger swings.")
    set_override(st, "STOCK_ALLOCATION", v / 100)
    # Bonds are derived (100 - stocks), so they are a read-only line, not an input.
    st.caption(f"Bond allocation: **{100 - st.session_state.get('sa_stock_alloc', 80):.0f}%** "
               "(100 minus stocks)")

    # Interpret INVESTMENT_FEE_RATE as fraction. bps = fee_rate * 10_000.
    cur_fee_bps = max(0, min(200, int(round(safe_float(get_override(st, "INVESTMENT_FEE_RATE", 0.0), 0.0) * 10_000))))
    ensure_default(st, "sa_fee_bps", cur_fee_bps)
    v = slider_with_box(st, "Investment fee (bps)", 0, 200,
                  5, key="sa_fee_bps", unit=" bps",
                  help="What your funds charge each year. 100 basis points (bps) = 1%. "
                       "Index ETFs run about 3-15 bps, active funds 50-100.")
    set_override(st, "INVESTMENT_FEE_RATE", v / 10_000)

    st.divider()

    # ===== Inflation =====
    _section_label(st, "Inflation")
    cur_infl = max(0.0, min(10.0, as_fraction(get_override(st, "EXPECTED_INFLATION", 0.0275), 0.0275) * 100))
    ensure_default(st, "sa_inflation", cur_infl)
    v = slider_with_box(st, "Expected inflation (%/yr)", 0.0, 10.0,
                  0.25, key="sa_inflation", unit="%",
                  help="Long-term US CPI averages 2.5-3%; the Fed targets 2%.")
    set_override(st, "EXPECTED_INFLATION", v / 100)

    st.divider()

    # ===== Glide path =====
    _section_label(st, "Glide path")
    ensure_default(st, "sa_glide_enable", bool(get_override(st, "GLIDE_PATH_ENABLED", True)))
    v = st.toggle("Change the stock/bond mix around retirement (glide path)",
                    key="sa_glide_enable")
    set_override(st, "GLIDE_PATH_ENABLED", bool(v))
    if st.session_state.get("sa_glide_enable", True):
        shape_labels = {"down": "Ease into bonds", "tent": "Bond tent"}
        cur_shape = shape_labels.get(str(get_override(st, "GLIDE_PATH_SHAPE", "down")), "Ease into bonds")
        ensure_default(st, "sa_glide_shape", cur_shape)
        shape = st.radio("Shape", list(shape_labels.values()), horizontal=True, key="sa_glide_shape",
                         help="Ease into bonds: hold your mix while working, then shift toward bonds as you age. "
                              "Bond tent: hold the most bonds in the years around retirement, when a market "
                              "crash would hurt most, then move back into stocks. Your stocks step down over "
                              "the 5 years before you retire and climb back over the years you choose.")
        tent = shape == "Bond tent"
        set_override(st, "GLIDE_PATH_SHAPE", "tent" if tent else "down")
        cur_start = max(30.0, min(100.0, as_fraction(get_override(st, "GLIDE_PATH_START_STOCK_PCT", cfg.GLIDE_PATH_START_STOCK_PCT), cfg.GLIDE_PATH_START_STOCK_PCT) * 100))
        ensure_default(st, "sa_glide_start", cur_start)
        v = slider_with_box(st, "Stock % at retirement", 30, 100, 5, key="sa_glide_start", unit="%",
                            help=("Your lowest stock share: the day you retire." if tent
                                  else "Your stock share on the day you retire."))
        set_override(st, "GLIDE_PATH_START_STOCK_PCT", v / 100)
        cur_end = max(20.0, min(100.0, as_fraction(get_override(st, "GLIDE_PATH_END_STOCK_PCT", cfg.GLIDE_PATH_END_STOCK_PCT), cfg.GLIDE_PATH_END_STOCK_PCT) * 100))
        ensure_default(st, "sa_glide_end", cur_end)
        if tent:
            v = slider_with_box(st, "Stock % after the climb", 20, 100, 5, key="sa_glide_end", unit="%",
                                help="Your stock share once the climb back is done. It stays there.")
        else:
            v = slider_with_box(st, "Stock % at age 75", 20, 100, 5, key="sa_glide_end", unit="%",
                                help="Your stock share at age 75. It slides from the retirement "
                                     "share to this one as you age.")
        set_override(st, "GLIDE_PATH_END_STOCK_PCT", v / 100)
        if tent:
            cur_rise = max(3, min(25, safe_int(get_override(st, "GLIDE_PATH_TENT_RISE_YEARS", cfg.GLIDE_PATH_TENT_RISE_YEARS), 10)))
            ensure_default(st, "sa_tent_years", cur_rise)
            v = slider_with_box(st, "Years to climb back", 3, 25, 1, key="sa_tent_years", unit=" yrs",
                                help="How many years after you retire your stocks take to climb back. "
                                     "About 10 covers the years when a crash hurts most.")
            set_override(st, "GLIDE_PATH_TENT_RISE_YEARS", int(v))

    st.divider()

    # ===== Roth conversion =====
    _section_label(st, "Roth conversion")
    # Surface the user's ACTUAL RMD start age here: RMDs are the whole reason
    # this strategy exists, but they're otherwise invisible in the UI (the
    # engine models them, then folds them into the Traditional bucket).
    try:
        from retirement_sim import config as _cfg
        _age = safe_int(get_override(st, "YOUR_AGE", _cfg.YOUR_AGE), _cfg.YOUR_AGE)
        _rmd_age = _cfg.get_rmd_start_age(_cfg.CURRENT_YEAR - _age)   # birth year follows from age
        st.caption(
            f"From age **{_rmd_age}**, the IRS requires minimum withdrawals (RMDs) from "
            "traditional accounts, taxed as income. Converting to Roth before then "
            "shrinks them."
        )
    except Exception:
        pass
    ensure_default(st, "sa_roth_enable", bool(get_override(st, "ENABLE_ROTH_CONVERSION", True)))
    v = st.toggle("Enable Roth conversion strategy", key="sa_roth_enable",
                    help="Move money from traditional to Roth in low-income early "
                          "retirement years. You pay the tax now, and later "
                          "withdrawals are tax-free.")
    set_override(st, "ENABLE_ROTH_CONVERSION", bool(v))
    if st.session_state.get("sa_roth_enable", True):
        c5, c6 = st.columns(2, vertical_alignment="bottom")
        with c5:
            # Default = the top of the 12% bracket for YOUR filing status, kept
            # as None ("follow the status") until you type another amount; any
            # status default left in the box re-follows a status change.
            from retirement_sim import config as _cfg
            _status = _cfg.normalize_filing_status(
                get_override(st, "FILING_STATUS", "Married filing jointly"))
            _auto = int(_cfg.ROTH_CONVERSION_TARGET_BY_STATUS[_status])
            try:
                from utils.config_builder import LEGACY_ROTH_TARGETS
            except ImportError:  # pragma: no cover
                from ui.utils.config_builder import LEGACY_ROTH_TARGETS  # type: ignore
            # The current defaults and the old 2024/2025 ones a saved profile may hold.
            _defaults = ({int(x) for x in _cfg.ROTH_CONVERSION_TARGET_BY_STATUS.values()}
                         | set(LEGACY_ROTH_TARGETS))
            _stored = get_override(st, "ROTH_CONVERSION_TARGET_BRACKET", None)
            if _stored is None or safe_int(_stored, _auto) in _defaults:
                _stored = None
                if safe_int(st.session_state.get("sa_roth_target"), _auto) in _defaults:
                    st.session_state["sa_roth_target"] = _auto
            ensure_default(st, "sa_roth_target", _auto if _stored is None else safe_int(_stored, _auto))
            v = st.number_input("Fill up to income of ($)", min_value=0, max_value=750_000,
                                step=5_000, key="sa_roth_target",
                                help=f"Each year, convert until your income reaches this amount. "
                                     f"This is income BEFORE the standard deduction "
                                     f"(\\${int(_cfg.STANDARD_DEDUCTION_BY_STATUS[_status]):,}), "
                                     f"so the default, \\${_auto:,}, stops short of the top of "
                                     f"the 12% bracket. To fill a bracket, add the deduction "
                                     f"to its top. Deep dives → Roth conversions compares plans.")
            set_override(st, "ROTH_CONVERSION_TARGET_BRACKET",
                         None if safe_int(v) == _auto else safe_int(v))
        with c6:
            ensure_default(st, "sa_roth_max",
                           safe_int(get_override(st, "ROTH_CONVERSION_MAX_ANNUAL", 100_000), 100_000))
            v = st.number_input("Max annual conversion ($)", min_value=0,
                                max_value=500_000, step=10_000, key="sa_roth_max")
            set_override(st, "ROTH_CONVERSION_MAX_ANNUAL", safe_int(v))
        # Which bracket the fill reaches: the box is easy to read as taxable income.
        try:
            from utils.roth_brackets import bracket_note
        except ImportError:  # pragma: no cover
            from ui.utils.roth_brackets import bracket_note  # type: ignore
        _fill = safe_int(st.session_state.get("sa_roth_target"), _auto)
        _note = bracket_note(_fill, _status)
        if _note:
            st.caption(f"Income before the \\${int(_cfg.STANDARD_DEDUCTION_BY_STATUS[_status]):,} "
                       f"standard deduction. \\${_fill:,}: {_note}.")
        ensure_default(st, "sa_roth_stop",
                       safe_int(get_override(st, "ROTH_CONVERSION_STOP_AGE", 67), 67))
        v = slider_with_box(st, "Stop conversions at age", 50, 80, 1, key="sa_roth_stop",
                            help="No Roth conversions after this age.")
        set_override(st, "ROTH_CONVERSION_STOP_AGE", safe_int(v))


def _render_healthcare_area(st) -> None:
    """Healthcare by area: a ZIP code or the state's average sets local marketplace prices (2027
    plan year). Only the resolved area is kept, never the ZIP. See utils/health_area.py."""
    overrides = st.session_state.get("user_overrides", {}) or {}
    area = health_area.area_key(overrides)
    st.text_input("ZIP code (optional)", key=health_area.ZIP_KEY, max_chars=5,
                  help="Looks up your marketplace rating area to price health insurance before 65 "
                       "where you live. The ZIP code is used once and is not saved. Only the area "
                       "it falls in is kept with your plan.")
    state = health_area.state_choice_code(overrides)
    b1, b2 = st.columns(2)
    with b1:
        st.button("Use this ZIP code's prices", key="sa_health_zip_btn",
                  on_click=health_area.apply_zip, args=(st,))
    with b2:
        st.button(f"Use {hd.state_names()[state]} average" if state else "Use my state's average",
                  key="sa_health_state_btn", on_click=health_area.apply_state, args=(st,),
                  disabled=state is None,
                  help="Uses the state chosen under Taxes." if state else
                       "Choose a state under Taxes first. No-state-tax and flat-rate choices have no area.")
    msg = st.session_state.get(health_area.MSG_KEY)
    if msg:
        st.caption(msg)
    if area:
        ref = hd.reference_prices(area)
        st.caption(f"Pricing from {hd.area_label(area)}, {health_area.year_phrase(overrides)}: "
                   f"benchmark Silver is \\${ref['benchmark_at_40']:,.0f} a month at 40 and "
                   f"\\${ref['child']:,.0f} a month for a child, before credits. Premiums grow 6% a year "
                   "before 65. Credits use the 2027 table and the income your plan earns each year.")
        labels = list(health_area.PLAN_LABELS.values())
        current = health_area.PLAN_LABELS.get(str(overrides.get("HEALTH_PLAN", "silver")), labels[0])
        ensure_default(st, health_area.PLAN_KEY, current)
        pick = st.radio("Plan you buy", labels, horizontal=True, key=health_area.PLAN_KEY,
                        help="Benchmark Silver is the second-cheapest Silver plan, and it sets your credit. "
                             "Lowest-cost Bronze costs less each month but carries 30% more out-of-pocket "
                             "cost. The credit is the same.")
        set_override(st, "HEALTH_PLAN", "bronze" if pick == labels[1] else "silver")
        st.button("Back to the national figures", key="sa_health_clear_btn",
                  on_click=health_area.clear_area, args=(st,))


def render_body(st) -> None:
    try:
        from components import assumption_presets
    except ImportError:  # pragma: no cover
        from ui.components import assumption_presets  # type: ignore
    assumption_presets.render(st)        # "All conservative / typical assumptions" + What changed + Undo
    st.divider()

    overrides = st.session_state.get("user_overrides", {}) or {}

    # ===== Dynamic spending =====
    _section_label(st, "Dynamic spending")
    ensure_default(st, "sa_dyn_enable", bool(get_override(st, "DYNAMIC_SPENDING_ENABLED", True)))
    # Describe the ACTUAL settings (a profile can calibrate them), not the defaults.
    _g = {**cfg.SPENDING_GUARDRAILS, **(overrides.get("SPENDING_GUARDRAILS") or {})}
    _cut = float(_g["floor_reduction"]); _drop = 1 - float(_g["floor_trigger"])
    _share = float(overrides.get("DISCRETIONARY_EXPENSE_RATIO", cfg.DISCRETIONARY_EXPENSE_RATIO))
    v = st.toggle(f"Guardrails: cut {_cut:.0%} of discretionary spending when the portfolio "
                  f"is {_drop:.0%} below target",
                    key="sa_dyn_enable",
                    help=f"Discretionary is about {_share:.0%} of non-housing spending; "
                         "housing is never cut.")
    set_override(st, "DYNAMIC_SPENDING_ENABLED", bool(v))

    ensure_default(st, "sa_ret_spend", bool(get_override(st, "RETURN_BASED_SPENDING_ENABLED", True)))
    v = st.toggle("Cut spending after down years",
                    key="sa_ret_spend")
    set_override(st, "RETURN_BASED_SPENDING_ENABLED", bool(v))

    st.divider()

    # ===== Healthcare / LTC =====
    _section_label(st, "Healthcare (before Medicare)")
    ensure_default(st, "sa_aca", bool(get_override(st, "ACA_ENABLED", True)))
    v = st.toggle("Include ACA subsidies before Medicare", key="sa_aca")
    set_override(st, "ACA_ENABLED", bool(v))

    _render_healthcare_area(st)

    # Marketplace prices before age 65. These replace a "Pre-Medicare healthcare
    # cost" box that fed a flat band the default age-rated model never reads. With an area
    # set they hold that area's prices; type your own quote over them and the area's prices
    # scale to it.
    overrides = st.session_state.get("user_overrides", {}) or {}
    area = health_area.area_key(overrides)
    ref = hd.reference_prices(area) if area else None
    year = health_area.year_phrase(overrides)
    c7, c8 = st.columns(2, vertical_alignment="bottom")
    with c7:
        ensure_default(st, "sa_aca_benchmark",
                       safe_int(get_override(st, "ACA_BENCHMARK_MONTHLY_AT_40",
                                             round(ref["benchmark_at_40"]) if ref
                                             else getattr(cfg, "ACA_BENCHMARK_MONTHLY_AT_40", 625)), 625))
        v = st.number_input(f"Marketplace plan, age 40 (\\$/mo, {year})", min_value=0, max_value=5_000,
                            step=25, key="sa_aca_benchmark",
                            help="Before 65, without a work plan, you buy insurance on the "
                                 "marketplace. Enter the price of the second-cheapest Silver "
                                 "plan for a 40-year-old in your area, before subsidies "
                                 "(healthcare.gov, by ZIP code). The plan prices other ages "
                                 "from it and works out subsidies itself. With a ZIP code or "
                                 "state above, this shows that area's price. Type your own "
                                 "quote to scale the area's prices to it.")
        set_override(st, "ACA_BENCHMARK_MONTHLY_AT_40", safe_int(v))
    with c8:
        ensure_default(st, "sa_aca_child",
                       safe_int(get_override(st, "ACA_CHILD_MONTHLY",
                                             round(ref["child"]) if ref
                                             else getattr(cfg, "ACA_CHILD_MONTHLY", 390)), 390))
        v = st.number_input(f"Same plan, per child (\\$/mo, {year})", min_value=0, max_value=3_000,
                            step=25, key="sa_aca_child")
        set_override(st, "ACA_CHILD_MONTHLY", safe_int(v))
    if area:
        st.caption(hd.SOURCE_LINE)
    else:
        st.caption("Flat national figures for the 2026 plan year (KFF). Enter a ZIP code or use your "
                   "state above for local prices.")

    # Long-term care lives in the "Retirement" section (single source of
    # truth — enable + start age + annual cost + per-year probability). It was
    # previously duplicated here, and because this section renders AFTER
    # Retirement its checkbox silently overrode that one. Removed to avoid
    # the conflict.


def render(st) -> None:
    with section_expander(st, "Assumptions", "tune"):
        render_body(st)
