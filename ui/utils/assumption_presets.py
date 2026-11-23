"""Assumption presets: "All typical assumptions" and "All conservative assumptions".

``compute_preset(name, overrides, comp_customized)`` returns ``{config_key: (value, reason)}``
for one of the two presets. The rules are pure. They read only facts about the household
(ages, retirement age, whether there is a loan), never the assumption values already set,
so the same situation always gets the same preset.

The rules follow the research notes in docs/METHODOLOGY.md ("Assumption presets"). The
helpers (``plan_until_age``, ``glide_band``, ``working_stock_pct`` ...) are public so the
tests can pin each rule alone.

The UI half (callbacks that write the values, the Undo snapshot and the status line) sits
at the bottom of this file. It touches ``st.session_state`` only.
"""
from __future__ import annotations

import math
from typing import Dict, Tuple

try:
    from retirement_sim import config as cfg
except ImportError:  # pragma: no cover
    cfg = None

TYPICAL = "typical"
CONSERVATIVE = "conservative"
PRESET_NAMES = (TYPICAL, CONSERVATIVE)
TITLES = {TYPICAL: "Typical", CONSERVATIVE: "Conservative"}

# Every key a preset can write. Singles get no PARTNER_* keys. A hand-edited pay table
# drops YOUR_SALARY_GROWTH_RATE (a partner has no pay table, so that key stays).
PRESET_KEYS = (
    "ACTIVE_RETURN_SCENARIO", "STOCK_ALLOCATION", "INVESTMENT_FEE_RATE", "EXPECTED_INFLATION",
    "GLIDE_PATH_ENABLED", "GLIDE_PATH_SHAPE", "GLIDE_PATH_START_STOCK_PCT",
    "GLIDE_PATH_END_STOCK_PCT", "GLIDE_PATH_TENT_RISE_YEARS",
    "PLAN_UNTIL_AGE", "PARTNER_PLAN_UNTIL_AGE",
    "SS_PAYABLE_FRACTION", "TARGET_SUCCESS_RATE",
    "DYNAMIC_SPENDING_ENABLED", "RETURN_BASED_SPENDING_ENABLED",
    "ACA_ENABLED",
    "LTC_ENABLED", "LTC_START_AGE", "LTC_ANNUAL_COST", "LTC_PROBABILITY",
    "LATE_RETIREMENT_LEISURE_DECREASE", "LATE_RETIREMENT_START_AGE",
    "YOUR_SALARY_GROWTH_RATE", "PARTNER_SALARY_GROWTH_RATE",
    "RULE_OF_55_ENABLED", "ROTH_LADDER_ENABLED",
)

# The two early-access toggles have no entry in widget_sync.DIRECT_MAPPINGS.
EXTRA_WIDGETS = {"RULE_OF_55_ENABLED": "ea_rule55", "ROTH_LADDER_ENABLED": "ea_ladder"}

LTC_COST = {TYPICAL: 115_000, CONSERVATIVE: 130_000}
LTC_YEARS_OF_CARE = {TYPICAL: 1.3, CONSERVATIVE: 2.6}
LTC_START_AGE = 83
FEE = {TYPICAL: 0.0010, CONSERVATIVE: 0.0030}
SS_TYPICAL = 0.78
SS_CONSERVATIVE_CAP = 0.75
SS_TRUSTEES_FALL = 0.145          # drop from 78% over 2033-2100 on the Trustees' path
SS_FROM_YEAR = 2033
SS_PATH_YEARS = 67

# Research G1 glide anchors: (years to retirement, stock %).
_WORK_ANCHORS = ((0, 50), (5, 56), (10, 62), (15, 74), (20, 85), (25, 90))

MISSING = type("Missing", (), {"__repr__": lambda self: "MISSING", "__bool__": lambda self: False})()


def _check(name: str) -> None:
    if name not in PRESET_NAMES:
        raise ValueError(f"unknown preset {name!r}")


def _round5(x: float) -> int:
    """Round to the nearest 5, halves up."""
    return int(math.floor(x / 5.0 + 0.5)) * 5


# ------------------------------------------------------------------ the rules

def plan_until_age(name: str, age: int, couple: bool) -> int:
    """Plan-until age for one person, by their own age."""
    _check(name)
    if name == CONSERVATIVE:
        v = 100
    elif couple:
        v = 100 if age < 50 else (96 if age < 60 else 95)
    else:
        v = 100 if age < 50 else (95 if age < 85 else 100)
    return int(min(100, max(v, 75, age + 1)))


def return_scenario(name: str, years_left: int) -> str:
    """Typical uses the Conservative set for long plans. Historical is never used."""
    _check(name)
    long_plan = years_left > 35
    if name == TYPICAL:
        return "conservative" if long_plan else "forward"
    return "forward" if long_plan else "pessimistic"


def glide_band(name: str, horizon: int) -> Tuple[str, float, float, int]:
    """(shape, stock share at retirement, stock share at the end, years to climb)."""
    _check(name)
    if name == TYPICAL:
        if horizon <= 30:
            return ("down", 0.50, 0.40, 10)
        if horizon <= 40:
            return ("tent", 0.50, 0.60, 10)
        return ("tent", 0.60, 0.70, 10)
    if horizon <= 30:
        return ("tent", 0.40, 0.60, 10)
    if horizon <= 40:
        return ("tent", 0.40, 0.60, 15)
    return ("tent", 0.50, 0.70, 15)


def _anchor_stock(y: float) -> float:
    if y >= _WORK_ANCHORS[-1][0]:
        return float(_WORK_ANCHORS[-1][1])
    for (x0, s0), (x1, s1) in zip(_WORK_ANCHORS, _WORK_ANCHORS[1:]):
        if y <= x1:
            return s0 + (s1 - s0) * (y - x0) / (x1 - x0)
    return float(_WORK_ANCHORS[0][1])


def working_stock_pct(years_to_retire: int, start_pct: int) -> int:
    """The one stock share held while working: the average of the research glide anchors
    over the years left, rounded to 5, never below the share held at retirement."""
    start = int(round(start_pct))
    y = int(years_to_retire)
    if y <= 0:
        return start
    avg = sum(_anchor_stock(i) for i in range(1, y + 1)) / y
    return max(_round5(avg), start)


def ss_payable(name: str, age: int, claim_age: int, plan_end_age: int) -> float:
    """Share of Social Security paid from 2033."""
    _check(name)
    if name == TYPICAL:
        return SS_TYPICAL
    year = int(getattr(cfg, "CURRENT_YEAR", 2026))
    start = max(year + int(claim_age) - int(age), SS_FROM_YEAR)
    end = year + int(plan_end_age) - int(age)
    mid = (start + end) / 2.0
    frac = SS_TYPICAL - SS_TRUSTEES_FALL * max(0.0, mid - SS_FROM_YEAR) / SS_PATH_YEARS
    return float(max(0.50, min(1.0, min(SS_CONSERVATIVE_CAP, round(frac, 2)))))


def ltc_probability(name: str, plan_end_age: int, couple: bool) -> float:
    """Yearly chance of a care bill, so that chance x years of exposure equals the
    expected years of care (1.3 typical, 2.6 when care is used) for each person."""
    _check(name)
    people = 2 if couple else 1
    years = max(1, int(plan_end_age) - LTC_START_AGE + 1)
    raw = 100.0 * LTC_YEARS_OF_CARE[name] * people / years
    return max(5, min(100, _round5(raw))) / 100.0


def success_target(name: str, horizon: int) -> float:
    _check(name)
    if name == TYPICAL:
        return 0.85 if horizon <= 35 else 0.90
    return 0.90 if horizon <= 35 else 0.95


def salary_growth(name: str, age: int) -> float:
    _check(name)
    if name == TYPICAL:
        return 0.015 if age < 35 else (0.010 if age < 45 else (0.005 if age < 55 else 0.0))
    return 0.005 if age < 45 else 0.0


# ------------------------------------------------------------------ facts

def _num(overrides: dict, key: str, default) -> int:
    v = (overrides or {}).get(key)
    if v is None:
        v = getattr(cfg, key, default) if cfg is not None else default
    if v is None:
        v = default
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return int(default)


def facts_of(overrides: dict) -> dict:
    """The facts the rules read (and the Undo note stores), from the overrides."""
    ov = overrides or {}
    A = _num(ov, "YOUR_AGE", 30)
    P = max(0, _num(ov, "PARTNER_AGE", 0))
    R = _num(ov, "TARGET_RETIREMENT_AGE", 60)
    claim = _num(ov, "SS_CLAIM_AGE", 67)
    debts = ov.get("DEBTS", getattr(cfg, "DEBTS", []) if cfg is not None else [])
    has_loan = (_num(ov, "MORTGAGE_BALANCE", 0) > 0 or _num(ov, "MORTGAGE_MONTHLY", 0) > 0
                or bool(debts))
    return {"A": A, "P": P, "R": R, "claim": claim, "has_loan": has_loan}


def situation(overrides: dict, name: str) -> dict:
    """The facts plus the timeline one preset implies (plan end, years left, horizon)."""
    _check(name)
    f = facts_of(overrides)
    A, P, R = f["A"], f["P"], f["R"]
    couple = P > 0
    pu_you = plan_until_age(name, A, couple)
    pu_partner = plan_until_age(name, P, couple) if couple else None
    E = max(pu_you, pu_partner + (A - P)) if couple else pu_you
    return {**f, "couple": couple, "pu_you": pu_you, "pu_partner": pu_partner, "E": E,
            "Y": max(0, R - A), "YL": E - A, "H": E - max(R, A)}


# ------------------------------------------------------------------ the preset

def compute_preset(name: str, overrides: dict, comp_customized: bool = False) -> Dict[str, tuple]:
    """``{config_key: (value, reason)}`` for ``name`` and this household."""
    _check(name)
    s = situation(overrides, name)
    A, P, R, E, H, Y, YL = s["A"], s["P"], s["R"], s["E"], s["H"], s["Y"], s["YL"]
    couple, typical = s["couple"], name == TYPICAL
    out: Dict[str, tuple] = {}

    def put(key, value, reason):
        out[key] = (value, reason)

    # Longevity
    if not typical:
        why = "A cautious plan makes the money last to age 100."
    elif s["pu_you"] == 100 and couple and A < 50:
        why = "For couples under 50, one partner often lives past 95."
    elif s["pu_you"] == 100 and A < 50:
        why = "You are young, so a long life is likely. Planning to 100 keeps a margin."
    elif s["pu_you"] == 100:
        why = "Planning to 100 keeps a margin at your age."
    elif couple:
        why = "Couples your age often have one partner who lives to about 95 or more."
    else:
        why = "Most people your age plan to live to about 95."
    put("PLAN_UNTIL_AGE", s["pu_you"], why)
    if couple:
        put("PARTNER_PLAN_UNTIL_AGE", s["pu_partner"],
            "Same idea for your partner, by their own age.")

    # Returns and mix
    scen = return_scenario(name, YL)
    if scen == "conservative":
        why = "Your plan is long. The Conservative set sits between today's forecasts and long-run history."
    elif scen == "forward":
        why = ("This plan is short enough for 2026 forecasts of lower returns."
               if typical else "Your plan is long, so it uses 2026 forecasts, which are lower than history.")
    else:
        why = "Short plan, so it assumes a weak stretch of markets. Stocks grow about 2.5% a year after inflation."
    put("ACTIVE_RETURN_SCENARIO", scen, why)

    shape, start, end, rise = glide_band(name, H)
    start_pct = int(round(start * 100))
    put("STOCK_ALLOCATION", working_stock_pct(Y, start_pct) / 100.0,
        "The average of a standard glide schedule over your working years, never below your mix at retirement."
        if Y > 0 else "You are retired, so this matches your mix at retirement.")
    put("GLIDE_PATH_ENABLED", True, "Every standard plan lowers stock risk around retirement.")
    put("GLIDE_PATH_SHAPE", shape,
        "A bond tent protects against a crash in the first years of retirement." if shape == "tent"
        else "Your retirement is short, so you ease into bonds as you age.")
    put("GLIDE_PATH_START_STOCK_PCT", start,
        f"Stock share on the day you retire. It is set by a {H}-year retirement.")
    put("GLIDE_PATH_END_STOCK_PCT", end,
        "Stock share once the climb back is done." if shape == "tent"
        else "Stock share at age 75.")
    put("GLIDE_PATH_TENT_RISE_YEARS", rise,
        "Years the bond tent takes to climb back to stocks." if shape == "tent"
        else "Not used with this shape.")
    put("INVESTMENT_FEE_RATE", FEE[name],
        "The usual cost of a low-fee index fund." if typical
        else "The average cost of a target-date fund, rounded up.")

    # Inflation
    if typical:
        infl, why = 0.025, "Long-run US inflation averages about 2.5%."
    elif s["has_loan"]:
        infl, why = 0.025, "You have a loan. Higher inflation would shrink its payments and flatter the plan."
    else:
        infl, why = 0.030, "A cautious plan assumes prices rise a little faster than the long-run 2.5%."
    put("EXPECTED_INFLATION", infl, why)

    # Social Security and the success target
    put("SS_PAYABLE_FRACTION", ss_payable(name, A, s["claim"], E),
        "About 78% of benefits stay payable if Congress does nothing." if typical
        else "Plans for a smaller check. The later your benefit years, the lower the share.")
    put("TARGET_SUCCESS_RATE", success_target(name, H),
        "Your plan is short, so a lower bar is fine because spending guardrails help." if typical and H <= 35
        else "A longer retirement has more room for bad luck, so the bar is higher." if typical
        else "A cautious plan asks for a higher chance of success.")

    # Spending behavior
    put("DYNAMIC_SPENDING_ENABLED", True,
        "People do cut spending after a big drop. Guardrails make that explicit.")
    put("RETURN_BASED_SPENDING_ENABLED", typical,
        "People spend a bit less after bad years." if typical
        else "A cautious plan does not count on cuts after every down year.")
    put("LATE_RETIREMENT_LEISURE_DECREASE", 0.15 if typical else 0.0,
        "Real spending usually falls with age. This keeps a modest 15%." if typical
        else "A cautious plan assumes spending stays flat.")
    put("LATE_RETIREMENT_START_AGE", 75, "The age the app already uses.")

    # Healthcare and long-term care
    put("ACA_ENABLED", True, "Turning this off removes pre-Medicare insurance costs, which flatters the plan.")
    put("LTC_ENABLED", True, "A care bill late in life is a real risk.")
    put("LTC_START_AGE", LTC_START_AGE, "The average nursing-home stay starts around 83.")
    put("LTC_ANNUAL_COST", LTC_COST[name],
        "About the cost of a semi-private nursing-home room today." if typical
        else "About the cost of a private nursing-home room today.")
    put("LTC_PROBABILITY", ltc_probability(name, E, couple),
        ("Sized to the average years of care people use" if typical
         else "Sized to the years of care people use when they need paid care")
        + (", for two people." if couple else "."))

    # Pay growth. Your pay is a table, so a table you edited keeps its own growth. Your
    # partner's pay has no table (the engine grows PARTNER_SALARY by the rate), so that
    # rate is always set.
    if not comp_customized:
        put("YOUR_SALARY_GROWTH_RATE", salary_growth(name, A),
            "Real pay growth slows as people reach their mid-40s.")
    if couple:
        put("PARTNER_SALARY_GROWTH_RATE", salary_growth(name, P),
            "Same rule, by your partner's age.")

    # Early access
    put("ROTH_LADDER_ENABLED", R < 60,
        "You retire before 60, so the 5-year wait on converted money applies. It matters only if you use Roth conversions."
        if R < 60 else "Not needed. Retiring at 60 or later avoids the early-withdrawal rules.")
    put("RULE_OF_55_ENABLED", bool(typical and 55 <= R < 60),
        "You can leave your employer at 55 or later and keep the money in its plan."
        if typical and 55 <= R < 60
        else "A cautious plan does not count on it.")
    return out


# ------------------------------------------------------------------ comparing

def _same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-6
    return a == b


def matches(overrides: dict, plan: Dict[str, tuple]) -> bool:
    """True when every key the preset sets already holds the preset's value."""
    ov = overrides or {}
    return all(k in ov and _same(ov[k], v) for k, (v, _) in plan.items())


# ------------------------------------------------------------------ describing

LABELS = {
    "ACTIVE_RETURN_SCENARIO": "Return scenario",
    "STOCK_ALLOCATION": "Stock allocation",
    "INVESTMENT_FEE_RATE": "Investment fee",
    "EXPECTED_INFLATION": "Expected inflation",
    "GLIDE_PATH_ENABLED": "Glide path",
    "GLIDE_PATH_SHAPE": "Glide path shape",
    "GLIDE_PATH_START_STOCK_PCT": "Stock % at retirement",
    "GLIDE_PATH_END_STOCK_PCT": "Stock % after the glide",
    "GLIDE_PATH_TENT_RISE_YEARS": "Years to climb back",
    "PLAN_UNTIL_AGE": "Plan-until age",
    "PARTNER_PLAN_UNTIL_AGE": "Partner's plan-until age",
    "SS_PAYABLE_FRACTION": "Share of Social Security paid from 2033",
    "TARGET_SUCCESS_RATE": "Success target",
    "DYNAMIC_SPENDING_ENABLED": "Spending guardrails",
    "RETURN_BASED_SPENDING_ENABLED": "Cut spending after down years",
    "ACA_ENABLED": "Pre-Medicare marketplace costs",
    "LTC_ENABLED": "Long-term care costs",
    "LTC_START_AGE": "Care starts around age",
    "LTC_ANNUAL_COST": "Annual care cost",
    "LTC_PROBABILITY": "Chance of needing care each year",
    "LATE_RETIREMENT_LEISURE_DECREASE": "Spend less later",
    "LATE_RETIREMENT_START_AGE": "Spend less from age",
    "YOUR_SALARY_GROWTH_RATE": "Your salary growth",
    "PARTNER_SALARY_GROWTH_RATE": "Partner salary growth",
    "RULE_OF_55_ENABLED": "Rule of 55",
    "ROTH_LADDER_ENABLED": "Roth conversion ladder",
}

_SCENARIO_LABELS = {"conservative": "Conservative", "historical": "Historical",
                    "pessimistic": "Pessimistic", "forward": "Forward-looking"}
_PERCENT = {"STOCK_ALLOCATION", "GLIDE_PATH_START_STOCK_PCT", "GLIDE_PATH_END_STOCK_PCT",
            "SS_PAYABLE_FRACTION", "TARGET_SUCCESS_RATE", "LTC_PROBABILITY",
            "LATE_RETIREMENT_LEISURE_DECREASE"}
_PERCENT_FINE = {"EXPECTED_INFLATION", "YOUR_SALARY_GROWTH_RATE", "PARTNER_SALARY_GROWTH_RATE"}
_TOGGLES = {"GLIDE_PATH_ENABLED", "DYNAMIC_SPENDING_ENABLED", "RETURN_BASED_SPENDING_ENABLED",
            "ACA_ENABLED", "LTC_ENABLED", "RULE_OF_55_ENABLED", "ROTH_LADDER_ENABLED"}


def format_value(key: str, value) -> str:
    """A value the way its widget shows it (units included)."""
    if value is MISSING or value is None:
        return "not set"
    try:
        if key == "ACTIVE_RETURN_SCENARIO":
            return _SCENARIO_LABELS.get(str(value).lower(), str(value))
        if key == "GLIDE_PATH_SHAPE":
            return "Bond tent" if str(value) == "tent" else "Ease into bonds"
        if key in _TOGGLES:
            return "On" if value else "Off"
        if key in _PERCENT:
            return f"{float(value) * 100:.0f}%"
        if key in _PERCENT_FINE:
            return f"{float(value) * 100:.2f}".rstrip("0").rstrip(".") + "%"
        if key == "INVESTMENT_FEE_RATE":
            return f"{float(value) * 10_000:.0f} bps"
        if key == "LTC_ANNUAL_COST":
            return f"${int(round(float(value))):,}"
        if key == "GLIDE_PATH_TENT_RISE_YEARS":
            return f"{int(value)} yrs"
        return f"{int(round(float(value)))}"
    except (TypeError, ValueError):
        return str(value)


COPY = {
    "intro": ("Not sure what numbers to use? Pick one. It sets returns, inflation, lifespan, "
              "Social Security, care costs and more for your age and retirement date."),
    "conservative_help": ("Plans for lower returns, a longer life and smaller Social Security checks. "
                          "Pick this if you want a safety margin."),
    "typical_help": "Uses what most planners assume today, based on 2026 forecasts and long-run history.",
    "long_plan_note": ("For long plans, Typical uses the Conservative return set. "
                       "It sits between today's forecasts and long-run history."),
    "run_note": "Click Run simulation to see results with these numbers.",
    "undone": "Back to your earlier settings.",
    "kept_pay": "Your salary growth: kept, because you edited your pay table",
    "returns_hint": "Not sure what to pick? The Assumptions section can set these for you in one click.",
}


def default_for(key: str):
    """The value the app uses for ``key`` when nothing is set."""
    return getattr(cfg, key, MISSING) if cfg is not None else MISSING


# ------------------------------------------------------------------ session state (UI half)

def _widget_map() -> Dict[str, tuple]:
    try:
        from utils import widget_sync as ws
    except ImportError:  # pragma: no cover
        from ui.utils import widget_sync as ws  # type: ignore
    out: Dict[str, tuple] = {}
    for widget, (key, cast) in ws.DIRECT_MAPPINGS.items():
        if key in PRESET_KEYS and key not in out:
            out[key] = (widget, cast)
    return out


def _forget(st, widget: str) -> None:
    try:
        from utils.slider_input import forget_box
    except ImportError:  # pragma: no cover
        from ui.utils.slider_input import forget_box  # type: ignore
    forget_box(st, widget)


def push_widgets(st, keys, overrides: dict) -> None:
    """Make the widgets for ``keys`` show what ``overrides`` holds. Only these widgets.
    A key that is not in ``overrides`` clears its widget, so it re-seeds from the default."""
    wmap = _widget_map()
    for key in keys:
        if key in wmap:
            widget, cast = wmap[key]
            if key in overrides and overrides[key] is not None:
                try:
                    st.session_state[widget] = cast(overrides[key])
                except Exception:
                    st.session_state.pop(widget, None)
            else:
                st.session_state.pop(widget, None)
            _forget(st, widget)
        elif key in EXTRA_WIDGETS:
            widget = EXTRA_WIDGETS[key]
            if key in overrides and overrides[key] is not None:
                st.session_state[widget] = bool(overrides[key])
            else:
                st.session_state.pop(widget, None)


def _changed(before, after) -> bool:
    if before is MISSING:
        return True
    return not _same(before, after)


def apply_preset(st, name: str) -> None:
    """Callback for a preset button. Runs before the page draws."""
    ss = st.session_state
    ov = ss.setdefault("user_overrides", {})
    plan = compute_preset(name, ov, bool(ss.get("si_comp_customized")))
    facts = facts_of(ov)
    facts["comp_customized"] = bool(ss.get("si_comp_customized"))
    before_all = {k: ov.get(k, MISSING) for k in plan}
    # A missing key that already holds the default is not a change.
    shown_before = {k: (before_all[k] if before_all[k] is not MISSING else default_for(k)) for k in plan}
    changes = [k for k in plan if _changed(shown_before[k], plan[k][0])]
    # A key missing from overrides still needs writing, so the engine sees it.
    after = {k: v for k, (v, _) in plan.items()}
    if not changes:
        # Nothing to change, so the earlier Undo snapshot stays. Keys missing from the
        # overrides still get written (they already hold the default) so the engine sees them.
        for k, v in after.items():
            ov.setdefault(k, v)
        push_widgets(st, [k for k in after if before_all[k] is MISSING], ov)
        ss["assume_noop"] = name
        return
    for k, v in after.items():
        ov[k] = v
    push_widgets(st, list(after), ov)
    ss.pop("assume_noop", None)
    ss["assume_last"] = {
        "name": name, "facts": facts, "before": before_all, "after": after,
        "old": {k: shown_before[k] for k in changes}, "changes": changes,
        "reasons": {k: plan[k][1] for k in plan},
        "scenario": after.get("ACTIVE_RETURN_SCENARIO"),
        "plan_end": situation(ov, name)["E"], "horizon": situation(ov, name)["H"],
    }
    ss.pop("assume_undone", None)


def undo_preset(st) -> None:
    """Callback for Undo: put back exactly what the last click replaced."""
    ss = st.session_state
    last = ss.get("assume_last")
    if not last:
        return
    ov = ss.setdefault("user_overrides", {})
    for k, old in last["before"].items():
        if old is MISSING:
            ov.pop(k, None)
        else:
            ov[k] = old
    push_widgets(st, list(last["before"]), ov)
    ss.pop("assume_last", None)
    ss.pop("assume_noop", None)
    ss["assume_undone"] = True


def undo_available(st) -> bool:
    """Undo shows only while every key still holds the value the click wrote."""
    last = st.session_state.get("assume_last")
    if not last or not last.get("changes"):
        return False
    ov = st.session_state.get("user_overrides") or {}
    return all(k in ov and _same(ov[k], v) for k, v in last["after"].items())


def status(st) -> Tuple[str, str]:
    """(kind, text) for the line under the heading. Needs no saved state: it compares
    the overrides with both presets for the current situation."""
    ss = st.session_state
    ov = ss.get("user_overrides") or {}
    comp = bool(ss.get("si_comp_customized"))
    for name in PRESET_NAMES:
        if matches(ov, compute_preset(name, ov, comp)):
            return name, f"Now using: {TITLES[name]} assumptions."
    last = ss.get("assume_last")
    if last and last.get("after"):
        # Only the keys the preset still sets for this household count. A single no longer
        # has a partner's plan-until age, so a household change is not a user edit.
        now = compute_preset(last["name"], ov, comp) if last.get("name") in PRESET_NAMES else {}
        after = {k: v for k, v in last["after"].items() if k in now}
        off = [k for k, v in after.items() if k not in ov or not _same(ov[k], v)]
        if not off:
            title = TITLES.get(last["name"], "Preset")
            return "outdated", (f"{title}, set for your old plan. Your situation changed. "
                                f"Click {title} again to update.")
        names = [LABELS.get(k, k) for k in off]
        shown = " and ".join(names[:2])
        extra = len(names) - 2
        tail = f" and {extra} more" if extra > 0 else ""
        title = TITLES.get(last["name"], "the preset")
        return "custom", f"Custom: you changed {shown}{tail} after picking {title}."
    return "own", "Now using: your own settings."
