"""Section 7: Assumptions (advanced) — returns, inflation, strategies, healthcare."""
from __future__ import annotations

import copy

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


def _section_label(st, txt):
    st.markdown(f'<div style="font-size: 13px; color: #64748b; text-transform: uppercase; '
                f'letter-spacing: 0.05em; margin: 14px 0 6px 0;">{txt}</div>',
                unsafe_allow_html=True)


def _get_hc(overrides: dict) -> dict:
    """Return the HEALTHCARE_COSTS_BY_AGE dict (override > cfg default)."""
    o = overrides.get("HEALTHCARE_COSTS_BY_AGE")
    if isinstance(o, dict):
        return dict(o)
    if cfg is not None:
        return dict(getattr(cfg, "HEALTHCARE_COSTS_BY_AGE", {}))
    return {}


def render_body(st) -> None:
    overrides = st.session_state.get("user_overrides", {}) or {}

    # ===== Returns =====
    _section_label(st, "Returns")
    scen_options = ["Conservative", "Historical", "Pessimistic"]
    current_scen = str(get_override(st, "ACTIVE_RETURN_SCENARIO", "historical")).lower()
    scen_map = {"conservative": "Conservative", "historical": "Historical", "pessimistic": "Pessimistic"}
    current_label = scen_map.get(current_scen, "Historical")
    ensure_default(st, "sa_scenario", current_label)
    scen = st.radio("Return scenario", scen_options, horizontal=True, key="sa_scenario",
                    help="Real stock/bond returns — Conservative: 7%/2%. Historical: 8.7%/3.1%. Pessimistic: 5%/1%.")
    set_override(st, "ACTIVE_RETURN_SCENARIO", scen.lower())

    c1, c2 = st.columns(2)
    with c1:
        cur_stock_pct = max(0.0, min(100.0, as_fraction(get_override(st, "STOCK_ALLOCATION", 0.80), 0.80) * 100))
        ensure_default(st, "sa_stock_alloc", cur_stock_pct)
        v = st.slider("Stock allocation (%)", min_value=0, max_value=100, step=5,
                      key="sa_stock_alloc")
        set_override(st, "STOCK_ALLOCATION", v / 100)
    with c2:
        bond_pct = 100 - st.session_state.get("sa_stock_alloc", 80)
        st.metric("Bond allocation", f"{bond_pct:.0f}%")

    # Interpret INVESTMENT_FEE_RATE as fraction. bps = fee_rate * 10_000.
    cur_fee_bps = max(0, min(100, int(round(safe_float(get_override(st, "INVESTMENT_FEE_RATE", 0.0), 0.0) * 10_000))))
    ensure_default(st, "sa_fee_bps", cur_fee_bps)
    v = st.slider("Investment fee (basis points)", min_value=0, max_value=100,
                  step=5, key="sa_fee_bps",
                  help="100 bps = 1% expense ratio. Index ETFs ≈ 3-15 bps; active funds ≈ 50-100 bps.")
    set_override(st, "INVESTMENT_FEE_RATE", v / 10_000)

    ensure_default(st, "sa_vol_drag", bool(get_override(st, "APPLY_VOLATILITY_DRAG", True)))
    v = st.toggle("Apply volatility drag (geometric vs arithmetic mean)",
                    key="sa_vol_drag")
    set_override(st, "APPLY_VOLATILITY_DRAG", bool(v))

    st.divider()

    # ===== Inflation =====
    _section_label(st, "Inflation")
    cur_infl = max(0.0, min(10.0, as_fraction(get_override(st, "EXPECTED_INFLATION", 0.0275), 0.0275) * 100))
    ensure_default(st, "sa_inflation", cur_infl)
    v = st.slider("Expected inflation (%/yr)", min_value=0.0, max_value=10.0,
                  step=0.25, key="sa_inflation",
                  help="Long-term US CPI averages 2.5-3%; the Fed targets 2%.")
    set_override(st, "EXPECTED_INFLATION", v / 100)

    st.divider()

    # ===== Glide path =====
    _section_label(st, "Glide path")
    ensure_default(st, "sa_glide_enable", bool(get_override(st, "GLIDE_PATH_ENABLED", True)))
    v = st.toggle("Enable glide path (shift bonds-heavier with age)",
                    key="sa_glide_enable")
    set_override(st, "GLIDE_PATH_ENABLED", bool(v))
    if st.session_state.get("sa_glide_enable", True):
        c3, c4 = st.columns(2)
        with c3:
            cur_start = max(50.0, min(100.0, as_fraction(get_override(st, "GLIDE_PATH_START_STOCK_PCT", 0.90), 0.90) * 100))
            ensure_default(st, "sa_glide_start", cur_start)
            v = st.slider("Stock % at retirement", min_value=50, max_value=100,
                          step=5, key="sa_glide_start")
            set_override(st, "GLIDE_PATH_START_STOCK_PCT", v / 100)
        with c4:
            cur_end = max(20.0, min(80.0, as_fraction(get_override(st, "GLIDE_PATH_END_STOCK_PCT", 0.60), 0.60) * 100))
            ensure_default(st, "sa_glide_end", cur_end)
            v = st.slider("Stock % at age 75", min_value=20, max_value=80,
                          step=5, key="sa_glide_end")
            set_override(st, "GLIDE_PATH_END_STOCK_PCT", v / 100)

    st.divider()

    # ===== Roth conversion =====
    _section_label(st, "Roth conversion")
    # Surface the user's ACTUAL RMD start age here: RMDs are the whole reason
    # this strategy exists, but they're otherwise invisible in the UI (the
    # engine models them, then folds them into the Traditional bucket).
    try:
        from retirement_sim import config as _cfg
        _age = safe_int(get_override(st, "YOUR_AGE", _cfg.YOUR_AGE), _cfg.YOUR_AGE)
        _year = safe_int(get_override(st, "CURRENT_YEAR", _cfg.CURRENT_YEAR), _cfg.CURRENT_YEAR)
        _rmd_age = _cfg.get_rmd_start_age(_year - _age)   # birth year follows from age
        st.caption(
            f"From age **{_rmd_age}** (your SECURE 2.0 RMD start age) the IRS forces "
            "minimum withdrawals from Traditional balances, taxed as income. "
            "Converting to Roth before then shrinks those forced withdrawals."
        )
    except Exception:
        pass
    ensure_default(st, "sa_roth_enable", bool(get_override(st, "ENABLE_ROTH_CONVERSION", True)))
    v = st.toggle("Enable Roth conversion strategy", key="sa_roth_enable",
                    help="Convert Traditional to Roth during low-income early retirement years.")
    set_override(st, "ENABLE_ROTH_CONVERSION", bool(v))
    if st.session_state.get("sa_roth_enable", True):
        c5, c6 = st.columns(2)
        with c5:
            ensure_default(st, "sa_roth_target",
                           safe_int(get_override(st, "ROTH_CONVERSION_TARGET_BRACKET", 94_300), 94_300))
            v = st.number_input("Fill up to bracket ($)", min_value=0, max_value=250_000,
                                step=5_000, key="sa_roth_target",
                                help="$94,300 = top of 12% MFJ bracket.")
            set_override(st, "ROTH_CONVERSION_TARGET_BRACKET", safe_int(v))
            ensure_default(st, "sa_roth_max",
                           safe_int(get_override(st, "ROTH_CONVERSION_MAX_ANNUAL", 100_000), 100_000))
            v = st.number_input("Max annual conversion ($)", min_value=0,
                                max_value=500_000, step=10_000, key="sa_roth_max")
            set_override(st, "ROTH_CONVERSION_MAX_ANNUAL", safe_int(v))
        with c6:
            ensure_default(st, "sa_roth_stop",
                           safe_int(get_override(st, "ROTH_CONVERSION_STOP_AGE", 67), 67))
            v = st.slider("Stop conversions at age", min_value=62, max_value=75,
                          step=1, key="sa_roth_stop")
            set_override(st, "ROTH_CONVERSION_STOP_AGE", safe_int(v))

    st.divider()

    # ===== Dynamic spending =====
    _section_label(st, "Dynamic spending")
    ensure_default(st, "sa_dyn_enable", bool(get_override(st, "DYNAMIC_SPENDING_ENABLED", True)))
    # Describe the ACTUAL settings (a profile can calibrate them), not the defaults.
    _g = {**cfg.SPENDING_GUARDRAILS, **(overrides.get("SPENDING_GUARDRAILS") or {})}
    _cut = float(_g["floor_reduction"]); _drop = 1 - float(_g["floor_trigger"])
    _share = float(overrides.get("DISCRETIONARY_EXPENSE_RATIO", cfg.DISCRETIONARY_EXPENSE_RATIO))
    v = st.toggle(f"Enable spending guardrails (cut {_cut:.0%} of the cuttable {_share:.0%} of "
                  f"non-housing spending if the portfolio drops {_drop:.0%})",
                    key="sa_dyn_enable")
    set_override(st, "DYNAMIC_SPENDING_ENABLED", bool(v))

    ensure_default(st, "sa_ret_spend", bool(get_override(st, "RETURN_BASED_SPENDING_ENABLED", True)))
    v = st.toggle("Enable return-based spending (cut in down years)",
                    key="sa_ret_spend")
    set_override(st, "RETURN_BASED_SPENDING_ENABLED", bool(v))

    st.divider()

    # ===== Healthcare / LTC =====
    _section_label(st, "Healthcare / LTC")
    ensure_default(st, "sa_aca", bool(get_override(st, "ACA_ENABLED", True)))
    v = st.toggle("ACA subsidy modeling (pre-Medicare years)", key="sa_aca")
    set_override(st, "ACA_ENABLED", bool(v))

    hc = _get_hc(overrides)
    ensure_default(st, "sa_hc_early", safe_int(hc.get("early_retirement", 24_000), 24_000))
    v = st.number_input("Pre-Medicare healthcare cost ($/yr)",
                        min_value=0, max_value=50_000, step=500, key="sa_hc_early")
    new_hc = copy.deepcopy(hc) if hc else {}
    new_hc["early_retirement"] = safe_int(v)
    set_override(st, "HEALTHCARE_COSTS_BY_AGE", new_hc)

    # Long-term care lives in the "Retirement goals" section (single source of
    # truth — enable + start age + annual cost + per-year probability). It was
    # previously duplicated here, and because this section renders AFTER
    # Retirement goals its checkbox silently overrode that one. Removed to avoid
    # the conflict.


def render(st) -> None:
    with st.expander("Assumptions (advanced)", expanded=False, icon=":material/tune:"):
        render_body(st)
