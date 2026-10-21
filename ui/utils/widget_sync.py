"""Mapping between UI widget keys and config override keys.

When inputs are restored from a saved JSON (or a profile preset is chosen), we
need to push the restored values into the individual widget keys that Streamlit
uses for each `st.number_input` / `st.slider` / etc. Without this step, the
widgets keep displaying whatever they showed before because their own
session_state entries take precedence over the `value=` default.

``sync_widgets_from_overrides(st)`` reads ``st.session_state.user_overrides``
and writes every widget key to the corresponding value (performing unit
conversion where needed).
"""
from __future__ import annotations

from typing import Any, Dict


# Each entry maps a widget-key (as used by the component's render()) to a
# rule for deriving the widget's value from ``user_overrides``:
#   - override_key: the key in user_overrides (or None if derived specially)
#   - cast: callable applied to the override value before storing
#   - default: value to use if the override key is absent
#
# Unit conversions are explicit. For example, YOUR_401K_MATCH_PCT is stored
# as a fraction (0.04) but the slider displays whole percent (4.0), so the
# cast multiplies by 100.


def _clamp(v, lo, hi):
    """Clamp v into [lo, hi], tolerating either bound being None (unbounded)."""
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def _as_int(default: int, lo: int = None, hi: int = None):
    def cast(v):
        try:
            result = int(float(v))
        except (TypeError, ValueError):
            result = int(default)
        return _clamp(result, lo, hi)
    return cast


def _as_float(default: float, lo: float = None, hi: float = None):
    def cast(v):
        try:
            result = float(v)
        except (TypeError, ValueError):
            result = float(default)
        return _clamp(result, lo, hi)
    return cast


def _as_pct(default_pct: float, lo: float = None, hi: float = None):
    """Cast fraction 0.04 → whole percent 4.0 (clamped)."""
    def cast(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return _clamp(default_pct, lo, hi)
        result = float(f * 100) if f <= 1.5 else float(f)  # tolerate either form
        return _clamp(result, lo, hi)
    return cast


def _as_bps(default_bps: int, lo: int = None, hi: int = None):
    """Cast fee rate 0.0015 → 15 bps (clamped)."""
    def cast(v):
        try:
            result = int(round(float(v) * 10_000))
        except (TypeError, ValueError):
            result = default_bps
        return _clamp(result, lo, hi)
    return cast


def _as_pct_int(default_int: int, lo: int = None, hi: int = None):
    """Cast a fraction (0.80) or whole-percent (80) value to a whole-percent int."""
    def cast(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return _clamp(int(default_int), lo, hi)
        result = int(round(f * 100)) if f <= 1.5 else int(round(f))
        return _clamp(result, lo, hi)
    return cast


def _state_code_to_label(v):
    code = str(v) if v else "CA"
    return {
        "CA": "California",
        "California": "California",
        "No state tax": "No state income tax",
        "No state income tax": "No state income tax",
        "Other": "Other (use marginal rate)",
        "Other (use marginal rate)": "Other (use marginal rate)",
    }.get(code, "California")


def _scenario_cast(v):
    s = str(v).strip().lower()
    return {
        "conservative": "Conservative",
        "historical": "Historical",
        "pessimistic": "Pessimistic",
    }.get(s, "Historical")


# Simple direct mappings: widget_key -> (override_key, cast)
# Values pulled from ui/components/*.py "key=..." declarations.
DIRECT_MAPPINGS: Dict[str, tuple] = {
    # account_inputs
    "ai_your_401k":       ("YOUR_401K", _as_int(10_000, 0, 10_000_000)),
    "ai_your_roth":       ("YOUR_ROTH_IRA", _as_int(3_500, 0, 10_000_000)),
    "ai_your_trad":       ("YOUR_TRADITIONAL_IRA", _as_int(0, 0, 10_000_000)),
    "ai_your_hsa":        ("YOUR_HSA", _as_int(500, 0, 10_000_000)),
    "ai_your_brk":        ("YOUR_BROKERAGE", _as_int(2_500, 0, 10_000_000)),
    "ai_your_cash":       ("YOUR_CASH", _as_int(4_000, 0, 10_000_000)),
    "ai_partner_401k":    ("PARTNER_401K", _as_int(7_000, 0, 10_000_000)),
    "ai_partner_roth":    ("PARTNER_ROTH_IRA", _as_int(2_500, 0, 10_000_000)),
    "ai_partner_brk":     ("PARTNER_BROKERAGE", _as_int(1_000, 0, 10_000_000)),
    "ai_partner_cash":    ("PARTNER_CASH", _as_int(3_000, 0, 10_000_000)),

    # spending_inputs — category breakdown + lifecycle preset
    # (Housing is now auto-derived from mortgage/rent — no sp_housing here.)
    "sp_utilities":       ("SPEND_UTILITIES_MONTHLY", _as_int(200, 0, 50_000)),
    "sp_food":            ("SPEND_FOOD_MONTHLY", _as_int(900, 0, 50_000)),
    "sp_transport":       ("SPEND_TRANSPORT_MONTHLY", _as_int(500, 0, 50_000)),
    "sp_health":          ("SPEND_HEALTH_MONTHLY", _as_int(400, 0, 50_000)),
    "sp_discretionary":   ("SPEND_DISCRETIONARY_MONTHLY", _as_int(600, 0, 50_000)),
    "sp_other":           ("SPEND_OTHER_MONTHLY", _as_int(300, 0, 50_000)),
    "sp_lifecycle":       ("SPEND_LIFECYCLE_PRESET", lambda v: str(v)),

    # savings — direct annual contribution amounts per account (both partners)
    "sr_inflation_adjust":("SAVINGS_INFLATION_ADJUST", lambda v: bool(v)),
    "sr_your_401k":       ("YOUR_401K_CONTRIBUTION", _as_int(2_700, 0, 30_000)),
    "sr_your_hsa":        ("YOUR_HSA_CONTRIBUTION", _as_int(0, 0, 10_000)),
    "sr_your_roth":       ("YOUR_BACKDOOR_ROTH", _as_int(0, 0, 10_000)),
    "sr_your_brk":        ("YOUR_BROKERAGE_CONTRIBUTION", _as_int(0, 0, 500_000)),
    "sr_partner_401k":    ("PARTNER_401K_CONTRIBUTION", _as_int(2_500, 0, 30_000)),
    "sr_partner_roth":    ("PARTNER_ROTH_CONTRIBUTION", _as_int(0, 0, 10_000)),
    "sr_partner_brk":     ("PARTNER_BROKERAGE_CONTRIBUTION", _as_int(0, 0, 500_000)),

    # ===== New sidebar sections (sec_*.py) =====

    # sec_about_you.py
    "ay_your_age":        ("YOUR_AGE", _as_int(25, 18, 100)),
    "ay_partner_age":     ("PARTNER_AGE", _as_int(25, 0, 100)),
    "ay_filing":          ("FILING_STATUS", lambda v: str(v)),
    "ay_target_age":      ("TARGET_RETIREMENT_AGE", _as_int(60, 25, 75)),
    "ay_partner_target_age": ("PARTNER_RETIREMENT_AGE", _as_int(60, 25, 75)),
    "ay_plan_until":      ("PLAN_UNTIL_AGE", _as_int(90, 75, 100)),

    # sec_income.py
    "si_your_base":       ("YOUR_BASE_SALARY", _as_int(70_000, 0, 2_000_000)),
    "si_your_bonus":      ("YOUR_BONUS_AMOUNT", _as_int(0, 0, 1_000_000)),
    "si_your_rsu":        ("YOUR_RSU_AMOUNT", _as_int(0, 0, 5_000_000)),
    "si_your_other":      ("YOUR_OTHER_INCOME", _as_int(0, 0, 1_000_000)),
    "si_your_growth":     ("YOUR_SALARY_GROWTH_RATE", _as_pct(2.0, 0.0, 10.0)),
    "si_partner_base":    ("PARTNER_BASE_SALARY", _as_int(42_000, 0, 2_000_000)),
    "si_partner_bonus":   ("PARTNER_BONUS_AMOUNT", _as_int(0, 0, 1_000_000)),
    "si_partner_rsu":     ("PARTNER_RSU_AMOUNT", _as_int(0, 0, 5_000_000)),
    "si_partner_other":   ("PARTNER_OTHER_INCOME", _as_int(0, 0, 1_000_000)),
    "si_partner_growth":  ("PARTNER_SALARY_GROWTH_RATE", _as_pct(2.0, 0.0, 10.0)),

    # sec_taxes.py
    "st_state":           ("STATE_CHOICE", _state_code_to_label),
    "st_marginal":        ("YOUR_MARGINAL_TAX_RATE", _as_pct(22.0, 0.0, 50.0)),

    # sec_expenses.py
    "se_home_value":      ("HOME_VALUE", _as_int(0, 0, 10_000_000)),
    "se_mortgage_balance":("MORTGAGE_BALANCE", _as_int(0, 0, 5_000_000)),
    "se_mortgage_monthly":("MORTGAGE_MONTHLY", _as_int(0, 0, 20_000)),
    "se_mortgage_years":  ("MORTGAGE_YEARS_REMAINING", _as_int(0, 0, 40)),
    "se_rent_monthly":    ("SPEND_RENT_MONTHLY", _as_int(1_500, 0, 20_000)),
    "se_utilities":       ("SPEND_UTILITIES_MONTHLY", _as_int(200, 0, 2_000)),
    "se_food":            ("SPEND_FOOD_MONTHLY", _as_int(900, 0, 10_000)),
    "se_transport":       ("SPEND_TRANSPORT_MONTHLY", _as_int(500, 0, 5_000)),
    "se_health":          ("SPEND_HEALTH_MONTHLY", _as_int(400, 0, 5_000)),
    "se_discretionary":   ("SPEND_DISCRETIONARY_MONTHLY", _as_int(600, 0, 10_000)),
    "se_other":           ("SPEND_OTHER_MONTHLY", _as_int(300, 0, 5_000)),
    "se_yufc":            ("YEARS_UNTIL_FIRST_CHILD", _as_int(3, -25, 20)),
    "se_ybc":             ("YEARS_BETWEEN_CHILDREN", _as_int(3, 1, 10)),
    "se_fcmc":            ("FIRST_CHILD_MONTHLY_COST", _as_int(2_100, 0, 10_000)),
    "se_bcmc":            ("BOTH_CHILDREN_MONTHLY_COST", _as_int(3_500, 0, 15_000)),
    "se_leave_age":       ("CHILD_LEAVES_HOME_AGE", _as_int(18, 16, 25)),
    "se_lifecycle":       ("SPEND_LIFECYCLE_PRESET", lambda v: str(v)),

    # sec_savings.py
    "sv_mode":               ("SAVINGS_MODE", lambda v: str(v)),
    "sv_inflation_adjust":   ("SAVINGS_INFLATION_ADJUST", lambda v: bool(v)),
    "sv_primary_housing":    ("PRIMARY_PAYS_HOUSING", lambda v: bool(v)),
    "sv_after_tax_401k":     ("YOUR_AFTER_TAX_401K_PCT", _as_pct(0.0, 0.0, 20.0)),
    "sv_manual_your_401k":   ("YOUR_401K_CONTRIBUTION", _as_int(2_700, 0, 30_000)),
    "sv_manual_your_hsa":    ("YOUR_HSA_CONTRIBUTION", _as_int(0, 0, 10_000)),
    "sv_manual_your_roth":   ("YOUR_BACKDOOR_ROTH", _as_int(0, 0, 10_000)),
    "sv_manual_your_brk":    ("YOUR_BROKERAGE_CONTRIBUTION", _as_int(0, 0, 500_000)),
    "sv_manual_partner_401k":("PARTNER_401K_CONTRIBUTION", _as_int(2_500, 0, 30_000)),
    "sv_manual_partner_roth":("PARTNER_ROTH_CONTRIBUTION", _as_int(0, 0, 10_000)),
    "sv_manual_partner_brk": ("PARTNER_BROKERAGE_CONTRIBUTION", _as_int(0, 0, 500_000)),

    # sec_big_purchases.py — car / house move / retirement vacation. These MUST
    # be listed so a profile switch or JSON load clears them (else a big-purchase
    # plan opted into on one profile bleeds into the next).
    "bp_car_onetime_enable":   ("CAR_ONETIME_ENABLED", lambda v: bool(v)),
    "bp_car_onetime_age":      ("CAR_ONETIME_AGE", _as_int(40, 18, 100)),
    "bp_car_onetime_amount":   ("CAR_ONETIME_AMOUNT", _as_int(40_000, 0, 500_000)),
    "bp_car_recurring_enable": ("CAR_RECURRING_ENABLED", lambda v: bool(v)),
    "bp_car_recurring_start":  ("CAR_RECURRING_START_AGE", _as_int(40, 18, 100)),
    "bp_car_recurring_every":  ("CAR_RECURRING_EVERY_YEARS", _as_int(8, 1, 30)),
    "bp_car_recurring_amount": ("CAR_RECURRING_AMOUNT", _as_int(40_000, 0, 500_000)),
    "bp_house_move_enable":    ("HOUSE_MOVE_ENABLED", lambda v: bool(v)),
    "bp_house_move_age":       ("HOUSE_MOVE_AGE", _as_int(45, 18, 100)),
    "bp_new_home_value":       ("NEW_HOME_VALUE", _as_int(1_000_000, 0, 20_000_000)),
    "bp_new_mortgage_balance": ("NEW_MORTGAGE_BALANCE", _as_int(700_000, 0, 20_000_000)),
    "bp_new_mortgage_monthly": ("NEW_MORTGAGE_MONTHLY", _as_int(4_500, 0, 100_000)),
    "bp_new_mortgage_years":   ("NEW_MORTGAGE_YEARS", _as_int(30, 1, 40)),
    "bp_home_selling_cost_pct":("HOME_SELLING_COST_PCT", _as_pct(6.0, 0.0, 20.0)),
    "bp_house_moving_costs":   ("HOUSE_MOVING_COSTS", _as_int(10_000, 0, 200_000)),
    # Extra mortgage principal (early payoff). Mapped so a profile switch or
    # JSON load resets the widget instead of leaving the previous plan's
    # prepayment amount stuck on the new profile.
    "bp_extra_mortgage":       ("EXTRA_MORTGAGE_PAYMENT_ANNUAL", _as_int(0, 0, 300_000)),
    "bp_vacation_enable":      ("RETIREMENT_VACATION_ENABLED", lambda v: bool(v)),
    "bp_vacation_annual":      ("RETIREMENT_VACATION_ANNUAL", _as_int(20_000, 0, 200_000)),
    "bp_vacation_until":       ("RETIREMENT_VACATION_UNTIL_AGE", _as_int(75, 50, 100)),

    # sec_retirement_goals.py
    "rg_spend_mode":      ("RETIREMENT_SPENDING_MODE", lambda v: str(v)),    "rg_spend_pct":       ("RETIREMENT_SPENDING_PCT", _as_pct(80.0, 50.0, 150.0)),
    "rg_spend_abs":       ("RETIREMENT_SPENDING_ABSOLUTE", _as_int(0, 0, 1_000_000)),
    "rg_ss_include":      ("INCLUDE_SOCIAL_SECURITY", lambda v: bool(v)),
    "rg_ss_claim":        ("SS_CLAIM_AGE", _as_int(67, 62, 70)),
    "rg_your_fra":        ("YOUR_SS_MONTHLY_FRA", _as_int(2_000, 0, 5_000)),
    "rg_partner_fra":     ("PARTNER_SS_MONTHLY_FRA", _as_int(1_800, 0, 5_000)),
    "rg_target_success":  ("TARGET_SUCCESS_RATE", _as_pct_int(80, 70, 95)),

    # sec_assumptions.py
    "sa_scenario":        ("ACTIVE_RETURN_SCENARIO", _scenario_cast),
    "sa_stock_alloc":     ("STOCK_ALLOCATION", _as_pct(80.0, 0.0, 100.0)),
    "sa_inflation":       ("EXPECTED_INFLATION", _as_pct(2.75, 0.0, 10.0)),
    "sa_fee_bps":         ("INVESTMENT_FEE_RATE", _as_bps(15, 0, 100)),
    "sa_vol_drag":        ("APPLY_VOLATILITY_DRAG", lambda v: bool(v)),
    "sa_glide_enable":    ("GLIDE_PATH_ENABLED", lambda v: bool(v)),
    "sa_glide_start":     ("GLIDE_PATH_START_STOCK_PCT", _as_pct(90.0, 50.0, 100.0)),
    "sa_glide_end":       ("GLIDE_PATH_END_STOCK_PCT", _as_pct(60.0, 20.0, 80.0)),
    "sa_roth_enable":     ("ENABLE_ROTH_CONVERSION", lambda v: bool(v)),
    "sa_roth_target":     ("ROTH_CONVERSION_TARGET_BRACKET", _as_int(94_300, 0, 250_000)),
    "sa_roth_max":        ("ROTH_CONVERSION_MAX_ANNUAL", _as_int(100_000, 0, 500_000)),
    "sa_roth_stop":       ("ROTH_CONVERSION_STOP_AGE", _as_int(67, 62, 75)),
    "sa_dyn_enable":      ("DYNAMIC_SPENDING_ENABLED", lambda v: bool(v)),
    "sa_ret_spend":       ("RETURN_BASED_SPENDING_ENABLED", lambda v: bool(v)),
    "sa_aca":             ("ACA_ENABLED", lambda v: bool(v)),
    # Long-term care widgets live in sec_retirement_goals (rg_ltc_*). The
    # probability is stored as a fraction (0-1) but the slider shows a percent.
    "rg_ltc_enabled":     ("LTC_ENABLED", lambda v: bool(v)),
    "rg_ltc_start":       ("LTC_START_AGE", _as_int(83, 70, 95)),
    "rg_ltc_cost":        ("LTC_ANNUAL_COST", _as_int(120_000, 0, 1_000_000)),
    "rg_ltc_prob":        ("LTC_PROBABILITY", lambda v: max(0, min(100, int(round(float(v) * 100))))),
}


def _derive_marital(overrides: dict) -> str:
    yuw = overrides.get("YEARS_UNTIL_WEDDING")
    try:
        yuw = int(yuw)
    except (TypeError, ValueError):
        return "Married"
    if yuw == 0:
        return "Married"
    if yuw >= 99:
        return "Single (no wedding planned)"
    return "Getting married"


def _derive_kids(overrides: dict) -> str:
    yufc = overrides.get("YEARS_UNTIL_FIRST_CHILD")
    fcmc = overrides.get("FIRST_CHILD_MONTHLY_COST")
    try:
        yufc = int(yufc) if yufc is not None else None
        fcmc = int(fcmc) if fcmc is not None else None
    except (TypeError, ValueError):
        return "No kids planned"
    if (yufc is not None and yufc >= 99) or fcmc == 0:
        return "No kids planned"
    return "Kids planned / already born"


def _derive_rent_own(overrides: dict) -> str:
    hv = overrides.get("HOME_VALUE", 0)
    try:
        return "Own home" if int(hv) > 0 else "Renting"
    except (TypeError, ValueError):
        return "Renting"


def _derive_scenario(overrides: dict) -> str:
    scen = overrides.get("ACTIVE_RETURN_SCENARIO", "historical")
    scen = str(scen).strip().lower()
    mapping = {
        "conservative": "Conservative",
        "historical": "Historical",
        "pessimistic": "Pessimistic",
    }
    return mapping.get(scen, "Historical")


def _derive_spending_guardrail_trigger(overrides: dict) -> float:
    """SPENDING_GUARDRAILS['floor_trigger'] is a fraction (0.70) → slider shows 70.0."""
    g = overrides.get("SPENDING_GUARDRAILS")
    if isinstance(g, dict):
        ft = g.get("floor_trigger", 0.70)
    else:
        ft = 0.70
    try:
        ft = float(ft)
    except (TypeError, ValueError):
        ft = 0.70
    return float(ft * 100) if ft <= 1.5 else float(ft)


def _derive_spending_guardrail_reduction(overrides: dict) -> float:
    g = overrides.get("SPENDING_GUARDRAILS")
    if isinstance(g, dict):
        fr = g.get("floor_reduction", 0.15)
    else:
        fr = 0.15
    try:
        fr = float(fr)
    except (TypeError, ValueError):
        fr = 0.15
    return float(fr * 100) if fr <= 1.5 else float(fr)


def _derive_hc_early(overrides: dict) -> int:
    hc = overrides.get("HEALTHCARE_COSTS_BY_AGE")
    if isinstance(hc, dict):
        v = hc.get("early_retirement", 24_000)
    else:
        v = 24_000
    try:
        return int(v)
    except (TypeError, ValueError):
        return 24_000


# Widget keys whose values depend on one or more overrides and require
# custom derivation logic (marital status, kids, rent/own, etc.)
DERIVED_MAPPINGS: Dict[str, Any] = {
    "fam_marital": _derive_marital,
    "fam_kids":    _derive_kids,
    "hi_rent_own": _derive_rent_own,
    "ri_scenario": _derive_scenario,
    "si_floor_trigger":   _derive_spending_guardrail_trigger,
    "si_floor_reduction": _derive_spending_guardrail_reduction,
    "si_hc_early":        _derive_hc_early,
    # New sec_*.py derived widgets
    "se_rent_own": _derive_rent_own,
    "se_kids":     _derive_kids,
    "sa_hc_early": _derive_hc_early,
}


# Radio/selectbox widgets use the option's full label as their session-state
# value (not its index). This map keeps the profile-picker consistent:
# widget_key "profile_selectbox" -> st.session_state["profile"] passthrough.


# Widget keys that hold user input but are NOT in DIRECT_MAPPINGS /
# DERIVED_MAPPINGS, so `sync_widgets_from_overrides` can't repopulate them.
# They must still be cleared when the user switches to a different set of
# inputs, or they stay "sticky" to the previous profile's values.
#
#   si_comp_editor      the compensation st.data_editor. Once touched it owns
#                       its own session_state and is written straight back into
#                       YOUR_COMPENSATION_BY_AGE on every rerun -- i.e. a stale
#                       one silently feeds the OLD profile's income to the sim.
#   si_comp_customized  the "user edited the comp table" flag. Must be cleared
#                       WITH the editor, otherwise the new profile's table is
#                       treated as hand-customized and never re-derives from
#                       that profile's own base/bonus/RSU inputs.
#   le_age              life-expectancy card's age (seeded from YOUR_AGE).
_EXTRA_INPUT_KEYS = ("si_comp_editor", "si_comp_customized", "le_age")

# Prefixes for widget families that are NOT (fully) enumerated above: either
# dynamically keyed (count varies at runtime) or whole sections whose widgets
# write straight back into ``user_overrides`` on every rerun. Clearing by prefix
# means a newly added widget inside one of these sections is covered by default
# instead of silently becoming sticky across a profile / JSON switch.
#
#   sv_pct_   sec_savings' per-account percentage sliders (dynamic count).
#   ea_       sec_early_access (Rule of 55 / 72(t) / Roth ladder / Coast FIRE).
#             Every one of these is pushed to cfg via set_override each rerun,
#             so a stale toggle re-enables a strategy the loaded plan disabled.
#   bp_       sec_big_purchases. The down-payment %, rate and escrow % are not
#             in DIRECT_MAPPINGS and the engine-facing NEW_MORTGAGE_BALANCE /
#             NEW_MORTGAGE_MONTHLY are re-derived FROM them, so a stale pair
#             silently rewrites the loaded profile's loan and payment.
#   wifc_     the what-if levers (plus the cached ``wifc_result`` plot data,
#             which is stale the moment the inputs change).
#   le_       life-expectancy card inputs (age / sex / conditions).
_EXTRA_INPUT_PREFIXES = ("sv_pct_", "ea_", "bp_", "wifc_", "le_")


def reset_input_widget_state(st) -> None:
    """Clear every input-widget key so a new set of overrides can repopulate.

    Used by BOTH ways of switching inputs -- the profile dropdown and the
    Save/Load JSON upload. They previously cleared *different* key sets, so a
    JSON load left widgets (notably the compensation editor) holding the
    previous profile's values.
    """
    for key in set(DIRECT_MAPPINGS) | set(DERIVED_MAPPINGS) | set(_EXTRA_INPUT_KEYS):
        try:
            if key in st.session_state:
                del st.session_state[key]
        except (KeyError, AttributeError):
            pass
    try:
        for key in [k for k in list(st.session_state.keys())
                    if isinstance(k, str) and k.startswith(_EXTRA_INPUT_PREFIXES)]:
            del st.session_state[key]
    except (KeyError, AttributeError):
        pass


def sync_widgets_from_overrides(st) -> None:
    """Write every known widget key from the current user_overrides.

    Call this after setting ``st.session_state.user_overrides`` (e.g., on
    profile load or JSON upload) and before the next ``st.rerun()``. Widgets
    that don't have an entry here are silently left alone — their existing
    session_state value persists.
    """
    overrides = st.session_state.get("user_overrides", {}) or {}

    for widget_key, (override_key, cast) in DIRECT_MAPPINGS.items():
        if override_key in overrides and overrides[override_key] is not None:
            try:
                st.session_state[widget_key] = cast(overrides[override_key])
            except Exception:
                pass

    for widget_key, derive_fn in DERIVED_MAPPINGS.items():
        try:
            st.session_state[widget_key] = derive_fn(overrides)
        except Exception:
            pass
