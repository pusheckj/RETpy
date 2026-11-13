"""Everyday money math for the simple "Money check-up" page.

Pure functions only (no Streamlit), so everything here is unit-testable and
instant. Four checks:

1. Savings rate and emergency fund (``savings_rate``, ``emergency_fund``).
2. "Where your next dollar goes": a personalised priority ladder (``priority_ladder``).
3. Debt payoff, avalanche vs snowball (``simulate_payoff``, ``compare_payoff``).
4. The 50/30/20 budget check (``budget_503020``).

``analyze(inputs)`` runs all four on one inputs dict. Inputs are a flat,
JSON-serialisable dict (``DEFAULT_INPUTS``); ``debts`` is the only nested
value, a list of small ``{name, balance, apr_pct, min_payment, kind}`` dicts
(``kind``, the planner's debt type, is not asked here; it is guessed from the
name when missing).
``normalize_inputs`` repairs anything (old, partial or garbage dicts restored
from a browser) into that shape without raising.

All money amounts are monthly unless the name says ``_annual``.
"""
from __future__ import annotations

import calendar
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from retirement_sim import config as cfg
from retirement_sim import debts as debt_math

try:
    from utils.formatting import money
except ImportError:  # pragma: no cover
    from ui.utils.formatting import money  # type: ignore


# ---------------------------------------------------------------------------
# Thresholds (rules of thumb, kept in one place)
# ---------------------------------------------------------------------------
SAVINGS_RATE_LOW = 0.10        # under 10%: a common first goal
SAVINGS_RATE_STRONG = 0.20     # 20%+ is a strong rate
EMERGENCY_MIN_MONTHS = 3
EMERGENCY_MAX_MONTHS = 6
DEFAULT_EMERGENCY_MONTHS = 4
STARTER_EMERGENCY_FLOOR = 1_000.0
# The interest bands and payoff limits are the planner's too (retirement_sim/debts.py).
HIGH_APR_PCT = debt_math.HIGH_APR * 100          # 8%+: pay off before investing past the match
MODERATE_APR_PCT = debt_math.MODERATE_APR * 100  # 4-8%: judgment call; below 4%: no rush
MAX_PAYOFF_MONTHS = debt_math.MAX_MONTHS         # 50 years; past this we report "won't pay off"
MAX_DEBTS = debt_math.MAX_DEBTS
DEBT_NAME_MAX_LEN = debt_math.NAME_MAX_LEN
BUDGET_TARGETS = {"needs": 0.50, "wants": 0.30, "savings": 0.20}
BUDGET_SLACK = 0.05            # within 5 points of a target counts as "close"
_PAID_EPS = 0.005              # a balance under half a cent is paid off

# Upper bounds used both by normalize_inputs and by the page's widgets.
MONTHLY_MAX = 1_000_000.0
BALANCE_MAX = 100_000_000.0
PCT_MAX = 100.0

DEBT_FIELDS = ("name", "balance", "apr_pct", "min_payment")   # the page's inputs per debt

# A generic young-professional example. Fictional; not anyone's real data.
DEFAULT_INPUTS: Dict[str, Any] = {
    "take_home_monthly": 4_200.0,
    "needs_monthly": 2_300.0,         # includes the debt minimums below ($600)
    "wants_monthly": 1_000.0,
    "cash_savings": 3_500.0,
    "gross_salary_annual": 65_000.0,
    "retirement_contrib_pct": 3.0,    # % of gross pay into the 401(k)
    "employer_match_pct": 4.0,        # employer matches up to this % of pay
    "hsa_eligible": False,
    "hsa_family": False,              # family coverage has the higher HSA limit
    "hsa_contrib_annual": 0.0,
    "ira_contrib_annual": 0.0,
    "age": 0,                         # 0 = not given: no age 50+ catch-up amounts in the limits
    "married": False,                 # married filing jointly (sets the Roth IRA income limit)
    "partner_salary_annual": 0.0,     # partner's yearly pay; only counts when married
    "emergency_target_months": DEFAULT_EMERGENCY_MONTHS,
    "debts": [
        {"name": "Credit card", "balance": 6_500.0, "apr_pct": 24.0, "min_payment": 160.0,
         "kind": "credit_card"},
        {"name": "Car loan", "balance": 4_200.0, "apr_pct": 6.9, "min_payment": 250.0,
         "kind": "car"},
        {"name": "Student loan", "balance": 18_000.0, "apr_pct": 4.5, "min_payment": 190.0,
         "kind": "student_loan"},
    ],
    "extra_debt_payment_monthly": 150.0,
}

# kind, low, high for every scalar field
_FIELD_SPECS: Dict[str, tuple] = {
    "take_home_monthly": ("money", 0.0, MONTHLY_MAX),
    "needs_monthly": ("money", 0.0, MONTHLY_MAX),
    "wants_monthly": ("money", 0.0, MONTHLY_MAX),
    "cash_savings": ("money", 0.0, BALANCE_MAX),
    "gross_salary_annual": ("money", 0.0, BALANCE_MAX),
    "retirement_contrib_pct": ("money", 0.0, PCT_MAX),
    "employer_match_pct": ("money", 0.0, PCT_MAX),
    "hsa_eligible": ("bool", None, None),
    "hsa_family": ("bool", None, None),
    "hsa_contrib_annual": ("money", 0.0, BALANCE_MAX),
    "ira_contrib_annual": ("money", 0.0, BALANCE_MAX),
    "age": ("int", 0, 100),
    "married": ("bool", None, None),
    "partner_salary_annual": ("money", 0.0, BALANCE_MAX),
    "emergency_target_months": ("int", EMERGENCY_MIN_MONTHS, EMERGENCY_MAX_MONTHS),
    "extra_debt_payment_monthly": ("money", 0.0, MONTHLY_MAX),
}


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------
def _to_float(value: Any) -> Optional[float]:
    """Finite float or None. Accepts "$4,200"-style strings; rejects bools."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace("$", "").replace(",", "").replace("%", "")
        if not value:
            return None
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return out if math.isfinite(out) else None


def _to_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value) if math.isfinite(value) else None
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "y", "1", "on"):
            return True
        if v in ("false", "no", "n", "0", "off", ""):
            return False
    return None


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _normalize_debt(raw: Any, index: int) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    name = "" if name is None or isinstance(name, (dict, list)) else str(name).strip()
    name = name[:DEBT_NAME_MAX_LEN] or f"Debt {index + 1}"

    def num(key: str, hi: float) -> float:
        v = _to_float(raw.get(key))
        return 0.0 if v is None else _clamp(v, 0.0, hi)

    kind = raw.get("kind")
    return {
        "name": name,
        "balance": num("balance", BALANCE_MAX),
        "apr_pct": num("apr_pct", PCT_MAX),
        "min_payment": num("min_payment", MONTHLY_MAX),
        # Not asked on this page (it has no type picker); kept so a debt brought
        # over from the planner keeps its type on the way back.
        "kind": kind if kind in debt_math.KINDS else debt_math.guess_kind(name),
    }


def normalize_inputs(d: Any) -> Dict[str, Any]:
    """Return a clean inputs dict. Never raises.

    Missing keys (and keys whose value is the wrong type) get the default;
    unknown keys are dropped; numbers are coerced and clamped (negatives -> 0);
    ``debts`` keeps only dict rows, at most ``MAX_DEBTS``. Idempotent.
    """
    src = d if isinstance(d, dict) else {}
    out: Dict[str, Any] = {}
    for key, default in DEFAULT_INPUTS.items():
        if key == "debts":
            continue
        kind, lo, hi = _FIELD_SPECS[key]
        raw = src.get(key, default)
        if kind == "bool":
            b = _to_bool(raw)
            out[key] = default if b is None else b
        elif kind == "int":
            v = _to_float(raw)
            out[key] = default if v is None else int(_clamp(round(v), lo, hi))
        else:
            v = _to_float(raw)
            out[key] = float(default) if v is None else float(_clamp(v, lo, hi))

    raw_debts = src.get("debts", DEFAULT_INPUTS["debts"])
    if not isinstance(raw_debts, (list, tuple)):
        raw_debts = DEFAULT_INPUTS["debts"]
    debts: List[Dict[str, Any]] = []
    for item in raw_debts:
        row = _normalize_debt(item, len(debts))
        if row is not None:
            debts.append(row)
        if len(debts) >= MAX_DEBTS:
            break
    out["debts"] = debts
    # Keep DEFAULT_INPUTS key order (stable JSON / easy diffing).
    return {k: out[k] for k in DEFAULT_INPUTS}


# ---------------------------------------------------------------------------
# Contribution limits (single source of truth: retirement_sim.config)
# ---------------------------------------------------------------------------
# IRS limits in actual dollars for the year shown to the visitor. (The retirement
# engine keeps its limits in constant 2024 dollars, which is right for its
# all-real projection but reads as out of date on a "what to do this year" page.)
# 2026: IRS Notice 2025-67 (401(k) $24,500, IRA $7,500); Rev. Proc. 2025-19
# (HSA $4,400 self-only / $8,750 family). Later years use the latest known year.
IRS_LIMITS = {
    2026: {"401k": 24_500, "ira": 7_500, "hsa_individual": 4_400, "hsa_family": 8_750,
           # Age catch-ups, added on top (same notices): 401(k) at 50+, replaced by the
           # larger "super" amount at ages 60-63; IRA at 50+; HSA at 55+.
           "401k_catchup": 8_000, "401k_super_catchup": 11_250, "ira_catchup": 1_100,
           "hsa_catchup": 1_000},
}
SUPER_CATCHUP_AGES = (60, 63)       # inclusive


def contribution_limits(hsa_family: bool = False, today: Optional[date] = None,
                        age: int = 0) -> Dict[str, float]:
    """This year's employee limits for 401(k), IRA and HSA.

    ``age`` (0 = unknown) adds the catch-ups: 401(k) and IRA from 50, HSA from 55,
    and the larger 401(k) amount at 60-63. Years before the table fall back to
    ``retirement_sim.config``'s 2024 base (and its catch-ups)."""
    year = (today or date.today()).year
    known = [y for y in IRS_LIMITS if y <= year]
    hsa_key = "hsa_family" if hsa_family else "hsa_individual"
    age = int(age or 0)
    if known:
        t = IRS_LIMITS[max(known)]
        out = {"401k": float(t["401k"]), "ira": float(t["ira"]), "hsa": float(t[hsa_key])}
        c401 = t["401k_super_catchup"] if SUPER_CATCHUP_AGES[0] <= age <= SUPER_CATCHUP_AGES[1] \
            else t["401k_catchup"]
        extra = {"401k": c401, "ira": t["ira_catchup"], "hsa": t["hsa_catchup"]}
    else:
        out = {
            "401k": float(cfg.get_inflation_adjusted_limit("401k", 0)),
            "ira": float(cfg.get_inflation_adjusted_limit("ira", 0)),
            "hsa": float(cfg.get_inflation_adjusted_limit(hsa_key, 0)),
        }
        extra = {k: cfg.get_inflation_adjusted_limit(f"{k}_catchup", 0) for k in ("401k", "ira", "hsa")}
    for k, from_age in (("401k", 50), ("ira", 50), ("hsa", 55)):
        if age >= from_age:
            out[k] += float(extra[k])
    return out


# Roth IRA income phase-out (modified AGI), IRS Notice 2025-67, same notice as
# the limits above: (low, high) for "single" (also head of household) and
# "joint" (married filing jointly). Direct contributions shrink from the full
# IRA limit at ``low`` to zero at ``high``. Years before the table fall back to
# the engine's 2024 ranges (retirement_sim.config.ROTH_IRA_PHASEOUT_BY_STATUS).
ROTH_PHASEOUT = {
    2026: {"single": (153_000, 168_000), "joint": (242_000, 252_000)},
}


def roth_phaseout(married: bool = False, today: Optional[date] = None) -> tuple:
    """``(low, high)`` MAGI range for the year shown to the visitor."""
    year = (today or date.today()).year
    known = [y for y in ROTH_PHASEOUT if y <= year]
    if known:
        lo, hi = ROTH_PHASEOUT[max(known)]["joint" if married else "single"]
        return float(lo), float(hi)
    lo, hi = cfg.ROTH_IRA_PHASEOUT_BY_STATUS[
        cfg.normalize_filing_status("Married filing jointly" if married else "Single")]
    return float(lo), float(hi)


def roth_direct_limit(magi: float, married: bool = False, today: Optional[date] = None,
                      age: int = 0) -> float:
    """What you can put into a Roth IRA directly at ``magi``, in whole dollars:
    the full IRA limit at or below the range, zero at or above it, and a straight
    line between (same shape as the engine's ``roth_ira_allowed``)."""
    limit = contribution_limits(False, today, age)["ira"]
    lo, hi = roth_phaseout(married, today)
    if magi <= lo:
        return limit
    if magi >= hi:
        return 0.0
    return float(math.floor(limit * (hi - magi) / (hi - lo) + 1e-9))


@dataclass
class RothCheck:
    case: str               # direct | reduced | backdoor
    magi: float             # estimate; see roth_magi
    low: float
    high: float
    direct_limit: float     # whole dollars you can put in a Roth directly
    ira_limit: float
    note: str               # one line saying which case applies


def roth_magi(inputs: Dict[str, Any], today: Optional[date] = None) -> float:
    """Estimated MAGI for the Roth test: your pay, plus your partner's when
    married, less your 401(k) deferral and your HSA contribution. An estimate:
    the partner's own deferrals and other adjustments aren't known."""
    i = normalize_inputs(inputs)
    limits = contribution_limits(i["hsa_family"], today, i["age"])
    deferral = min(i["gross_salary_annual"] * i["retirement_contrib_pct"] / 100.0, limits["401k"])
    hsa = i["hsa_contrib_annual"] if i["hsa_eligible"] else 0.0
    partner = i["partner_salary_annual"] if i["married"] else 0.0
    return max(0.0, i["gross_salary_annual"] + partner - deferral - hsa)


def roth_check(inputs: Dict[str, Any], today: Optional[date] = None) -> RothCheck:
    i = normalize_inputs(inputs)
    magi = roth_magi(i, today)
    lo, hi = roth_phaseout(i["married"], today)
    ira = contribution_limits(False, today, i["age"])["ira"]
    direct = roth_direct_limit(magi, i["married"], today, i["age"])
    if magi <= lo:
        case = "direct"
        note = f"Your income is under the Roth limit, so you can put in the full {money(ira)} directly."
    elif direct > 0:
        case = "reduced"
        note = (f"Your income cuts the direct Roth limit to {money(direct)}. "
                f"The rest can go through a backdoor Roth.")
    else:
        case = "backdoor"
        note = "You earn too much for a direct Roth. A backdoor Roth is the way in."
    return RothCheck(case, magi, lo, hi, direct, ira, note)


def max_401k_pct(salary: float, today: Optional[date] = None, age: int = 0) -> Optional[float]:
    """The ``retirement_contrib_pct`` that puts in this year's 401(k) limit, capped
    at 100 and rounded up to 2 decimals so the contribution is never a few dollars
    short of the limit. ``None`` when there is no salary."""
    if salary <= 0:
        return None
    limit = contribution_limits(False, today, age)["401k"]
    return min(PCT_MAX, math.ceil(round(limit / salary * 10_000, 6)) / 100.0)


# ---------------------------------------------------------------------------
# 1. Savings rate and emergency fund
# ---------------------------------------------------------------------------
@dataclass
class SavingsRate:
    rate: Optional[float]          # None when take-home is 0
    monthly_savings: float         # take-home - needs - wants (can be negative)
    band: str                      # unknown | negative | low | healthy | strong
    message: str


def savings_rate(take_home: float, needs: float, wants: float) -> SavingsRate:
    saved = take_home - needs - wants
    if take_home <= 0:
        return SavingsRate(None, saved, "unknown",
                           "Add your monthly take-home pay to see your savings rate.")
    rate = saved / take_home
    if rate < 0:
        band, msg = "negative", ("You're spending more than you bring in each month. "
                                 "Closing that gap comes before everything else.")
    elif rate < SAVINGS_RATE_LOW:
        band, msg = "low", ("Under 10%. A common first goal is 10%; "
                            "even a small step up adds up over time.")
    elif rate < SAVINGS_RATE_STRONG:
        band, msg = "healthy", ("10-20% is a healthy range. Reaching 20% "
                                "speeds up every goal below.")
    else:
        band, msg = "strong", "20% or more is a strong rate. Keep it going."
    return SavingsRate(rate, saved, band, msg)


@dataclass
class EmergencyFund:
    months: Optional[float]        # None when essentials are 0
    essentials_monthly: float
    cash: float
    gap_to_min: float              # dollars to reach 3 months
    gap_to_max: float              # dollars to reach 6 months
    target_months: int
    gap_to_target: float
    status: str                    # unknown | none | building | ok | plenty
    message: str


def emergency_fund(cash: float, essentials: float,
                   target_months: int = DEFAULT_EMERGENCY_MONTHS) -> EmergencyFund:
    cash = max(0.0, cash)
    essentials = max(0.0, essentials)
    target_months = int(_clamp(target_months, EMERGENCY_MIN_MONTHS, EMERGENCY_MAX_MONTHS))
    if essentials <= 0:
        return EmergencyFund(None, essentials, cash, 0.0, 0.0, target_months, 0.0, "unknown",
                             "Add your monthly essentials to see how long your cash would last.")
    months = cash / essentials
    gap = lambda m: max(0.0, m * essentials - cash)  # noqa: E731
    if cash <= 0:
        status, msg = "none", "No cash cushion yet. Start with a small one, then build to 3-6 months."
    elif months < EMERGENCY_MIN_MONTHS:
        status, msg = "building", "Under 3 months. Keep building toward the 3-6 month range."
    elif months <= EMERGENCY_MAX_MONTHS:
        status, msg = "ok", "Inside the 3-6 month range most planners suggest."
    else:
        status, msg = "plenty", ("More than 6 months. Cash beyond your goal "
                                 "could be invested instead.")
    return EmergencyFund(months, essentials, cash, gap(EMERGENCY_MIN_MONTHS),
                         gap(EMERGENCY_MAX_MONTHS), target_months, gap(target_months),
                         status, msg)


# ---------------------------------------------------------------------------
# 2. Where my next dollar goes
# ---------------------------------------------------------------------------
STATUS_LABELS = {
    "done": "Done",
    "current": "Do this now",
    "next": "Up next",
    "later": "Later",
    "skip": "Doesn't apply",
}


@dataclass
class LadderStep:
    number: int
    key: str
    title: str
    status: str                    # done | current | next | later | skip
    target: Optional[float]        # dollar amount to aim for (None: open-ended)
    target_label: str
    why: str
    detail: str = ""
    have: Optional[float] = None   # what you have/put in now, toward the target


def _sorted_debts(debts: List[Dict[str, Any]], lo: float, hi: float) -> List[Dict[str, Any]]:
    rows = [d for d in debts if d["balance"] > _PAID_EPS and lo <= d["apr_pct"] < hi]
    return sorted(rows, key=lambda d: (-d["apr_pct"], d["balance"]))


def _debt_list(rows: List[Dict[str, Any]]) -> str:
    return ", ".join(f"{d['name']} ({d['apr_pct']:g}%)" for d in rows)


def priority_ladder(inputs: Dict[str, Any], today: Optional[date] = None) -> List[LadderStep]:
    """The nine-step order for the next dollar, with each step's status.

    A step is ``done`` when its goal is met and ``skip`` when it doesn't apply.
    Of the rest, the first is ``current``, the second ``next``, the others
    ``later``. Step 9 is open-ended, so there is always a current step.
    """
    i = normalize_inputs(inputs)
    essentials = i["needs_monthly"]
    cash = i["cash_savings"]
    salary = i["gross_salary_annual"]
    contrib_pct = i["retirement_contrib_pct"]
    match_pct = i["employer_match_pct"]
    limits = contribution_limits(i["hsa_family"], today, i["age"])
    steps: List[LadderStep] = []

    # 1. Starter emergency fund
    starter = max(STARTER_EMERGENCY_FLOOR, essentials)
    steps.append(LadderStep(
        1, "starter_emergency", "Starter emergency fund",
        "done" if cash >= starter else "pending", starter, f"{money(starter)} in cash",
        "A small cushion keeps a surprise bill from landing on a credit card.",
        f"You have {money(cash)}." if cash < starter else "", cash))

    # 2. Employer 401(k) match
    contrib_annual = salary * contrib_pct / 100.0
    if salary <= 0:
        st2, detail2 = "skip", "Add your yearly salary to check this step."
    elif match_pct <= 0:
        st2, detail2 = "skip", "No employer match entered."
    elif contrib_pct + 1e-9 >= match_pct:
        st2, detail2 = "done", "You're getting the full match."
    else:
        left = salary * (match_pct - contrib_pct) / 100.0
        st2 = "pending"
        detail2 = (f"You put in {contrib_pct:g}%. Raising it to {match_pct:g}% gets about "
                   f"{money(left)}/yr in free match money you're missing.")
    match_target = salary * match_pct / 100.0
    steps.append(LadderStep(
        2, "employer_match", "Get your full 401(k) match", st2, match_target,
        f"{money(match_target)}/yr ({match_pct:g}% of pay)",
        "It's free money. No investment is a surer return. "
        "Assumes your employer matches dollar for dollar.",
        detail2, contrib_annual))

    # 3. High-interest debt
    high = _sorted_debts(i["debts"], HIGH_APR_PCT, math.inf)
    high_total = sum(d["balance"] for d in high)
    steps.append(LadderStep(
        3, "high_interest_debt", f"Pay off high-interest debt ({HIGH_APR_PCT:g}%+)",
        "pending" if high else "done", high_total,
        f"{money(high_total)} to pay off" if high else "$0 owed",
        "Paying off debt at 8% or more is a guaranteed return at that rate. "
        "Go highest rate first.",
        f"In order: {_debt_list(high)}." if high else "No debt at 8% or more."))

    # 4. Full emergency fund
    months = i["emergency_target_months"]
    full = max(starter, months * essentials)
    steps.append(LadderStep(
        4, "full_emergency", f"Full emergency fund ({months} months)",
        "done" if cash >= full else "pending", full, f"{money(full)} in cash",
        "Covers essentials if you lose your job or face a big surprise. "
        "Pick 3 months if income is steady, closer to 6 if not.",
        f"You have {money(cash)}; {money(max(0.0, full - cash))} to go." if cash < full else "",
        cash))

    # 5. HSA
    hsa_have = i["hsa_contrib_annual"]
    if not i["hsa_eligible"]:
        st5, detail5 = "skip", "Only for HSA-eligible (high-deductible) health plans."
    else:
        st5 = "done" if hsa_have >= limits["hsa"] else "pending"
        detail5 = f"You put in {money(hsa_have)} this year." if st5 == "pending" else ""
    steps.append(LadderStep(
        5, "hsa", "Max out your HSA", st5, limits["hsa"],
        f"{money(limits['hsa'])}/yr ({'family' if i['hsa_family'] else 'self-only'})",
        "Triple tax break: tax-free in, tax-free growth, tax-free out for medical costs.",
        detail5, hsa_have))

    # 6. Roth IRA (the income limit decides: direct, reduced, or backdoor only)
    ira_have = i["ira_contrib_annual"]
    roth = roth_check(i, today)
    title6 = "Max out a Roth IRA"
    why6 = ("Grows tax-free, and you can take out what you put in at any time. "
            "Earn too much for a Roth? High earners use a \"backdoor Roth\".")
    goal6, detail_lead = limits["ira"], ""
    if roth.case == "reduced":
        goal6 = roth.direct_limit
        why6 = "Grows tax-free, and you can take out what you put in at any time."
        detail_lead = roth.note + " "
    elif roth.case == "backdoor":
        title6 = "Max out a backdoor Roth IRA"
        why6 = ("You earn too much to put money in a Roth directly. A backdoor Roth gets "
                "around that: put it in a traditional IRA, then convert it to Roth right away. "
                "Caution: if you hold other traditional IRA money, the conversion is "
                "partly taxable (the pro-rata rule).")
    st6 = "done" if ira_have >= goal6 else "pending"
    steps.append(LadderStep(
        6, "roth_ira", title6, st6, goal6, f"{money(goal6)}/yr", why6,
        (detail_lead + (f"You put in {money(ira_have)} this year." if st6 == "pending" else "")).strip(),
        ira_have))

    # 7. 401(k) to the limit
    if salary <= 0:
        st7, detail7 = "skip", "Add your yearly salary to check this step."
    else:
        st7 = "done" if contrib_annual >= limits["401k"] else "pending"
        detail7 = (f"You put in about {money(contrib_annual)}/yr "
                   f"({contrib_pct:g}% of pay)." if st7 == "pending" else "")
    steps.append(LadderStep(
        7, "max_401k", "Max out your 401(k)", st7, limits["401k"], f"{money(limits['401k'])}/yr",
        "More tax-advantaged saving for retirement. Your employer's match "
        "doesn't count toward this limit.",
        detail7, contrib_annual))

    # 8. Moderate-interest debt
    moderate = _sorted_debts(i["debts"], MODERATE_APR_PCT, HIGH_APR_PCT)
    mod_total = sum(d["balance"] for d in moderate)
    steps.append(LadderStep(
        8, "moderate_debt", f"Moderate-interest debt ({MODERATE_APR_PCT:g}\u2011{HIGH_APR_PCT:g}%)",
        "pending" if moderate else "done", mod_total,
        f"{money(mod_total)} to pay off" if moderate else "$0 owed",
        "A judgment call: paying it off is a sure return at that rate, investing may "
        "earn more. Many people split extra money between the two.",
        f"Your debts here: {_debt_list(moderate)}." if moderate else "No debt between 4% and 8%."))

    # 9. Everything else (open-ended)
    low = _sorted_debts(i["debts"], 0.0, MODERATE_APR_PCT)
    steps.append(LadderStep(
        9, "invest_and_goals", "Invest and save for other goals", "pending", None,
        "Whatever's left",
        "A regular brokerage account, a home down payment, travel. "
        "Debt under 4% can stay on its normal payments; no rush.",
        f"Low-rate debt on normal payments: {_debt_list(low)}." if low else ""))

    open_steps = [s for s in steps if s.status == "pending"]
    for n, s in enumerate(open_steps):
        s.status = "current" if n == 0 else "next" if n == 1 else "later"
    return steps


# ---------------------------------------------------------------------------
# 3. Debt payoff
# ---------------------------------------------------------------------------
@dataclass
class PayoffResult:
    strategy: str                  # avalanche | snowball
    paid_off: bool
    months: int                    # months simulated (MAX_PAYOFF_MONTHS if not paid off)
    debt_free_date: Optional[str]  # "Mar 2029"; None if no debt or never
    total_interest: float
    total_paid: float
    monthly_payment: float         # minimums + extra, held fixed (freed minimums roll over)
    remaining_balance: float
    order: List[Dict[str, Any]] = field(default_factory=list)   # payoff order
    balances: List[float] = field(default_factory=list)         # total owed, month 0..months
    underwater: List[str] = field(default_factory=list)         # minimum <= interest
    focus_order: List[str] = field(default_factory=list)        # where extra money goes, in order


def month_label(start: date, months_ahead: int) -> str:
    """'Mon YYYY' for ``months_ahead`` months after ``start``'s month."""
    idx = start.month - 1 + months_ahead
    return f"{calendar.month_abbr[idx % 12 + 1]} {start.year + idx // 12}"


def month_date(start: date, months_ahead: int) -> date:
    idx = start.month - 1 + months_ahead
    return date(start.year + idx // 12, idx % 12 + 1, 1)


def underwater_debts(debts: List[Dict[str, Any]]) -> List[str]:
    """Names of debts whose minimum payment doesn't cover the monthly interest."""
    return [d["name"] for d in debts
            if d["balance"] > _PAID_EPS and d["apr_pct"] > 0
            and d["min_payment"] <= d["balance"] * d["apr_pct"] / 1200.0 + 1e-9]


def to_engine_debts(debts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Check-up debt rows (``apr_pct``) as the planner's DEBTS rows (``apr``)."""
    out = []
    for n, d in enumerate(debts or []):
        r = _normalize_debt(d, n)
        if r is not None:
            out.append({"name": r["name"], "kind": r["kind"], "balance": r["balance"],
                        "apr": r["apr_pct"] / 100.0, "min_payment": r["min_payment"]})
    return out


def simulate_payoff(debts: List[Dict[str, Any]], extra_monthly: float = 0.0,
                    strategy: str = "avalanche", start: Optional[date] = None,
                    max_months: int = MAX_PAYOFF_MONTHS) -> PayoffResult:
    """Month-by-month payoff with a fixed total payment.

    Each month: interest accrues (APR/12), every debt gets its minimum, and the
    rest of the budget (extra + minimums freed by paid-off debts) goes to the
    target: highest APR first (avalanche) or smallest balance first (snowball).
    The math is the planner's and the simulation's (retirement_sim/debts.py).
    """
    start = start or date.today()
    extra = max(0.0, _to_float(extra_monthly) or 0.0)
    p = debt_math.amortize(to_engine_debts(debts), extra, strategy, max_months)
    rows = p.rows
    if not rows:
        return PayoffResult(strategy, True, 0, None, 0.0, 0.0, p.monthly_budget, 0.0, [], [0.0], [], [])
    order = p.focus_order
    payoff_rows = []
    for k in sorted(range(len(rows)), key=lambda k: (p.payoff_month[k] is None, p.payoff_month[k] or 0,
                                                     order.index(k))):
        m = p.payoff_month[k]
        payoff_rows.append({
            "name": rows[k]["name"], "apr_pct": rows[k]["apr"] * 100.0, "balance": rows[k]["balance"],
            "payoff_month": m, "payoff_date": month_label(start, m) if m is not None else None,
        })
    return PayoffResult(
        strategy, p.paid_off, p.months, month_label(start, p.months) if p.paid_off else None,
        p.total_interest, p.total_paid, p.monthly_budget, p.remaining, payoff_rows, p.balances,
        [rows[k]["name"] for k in p.underwater], [rows[k]["name"] for k in order])


def compare_payoff(debts: List[Dict[str, Any]], extra_monthly: float = 0.0,
                   start: Optional[date] = None) -> Dict[str, Any]:
    """Run both strategies; report the interest saved by avalanche."""
    av = simulate_payoff(debts, extra_monthly, "avalanche", start)
    sb = simulate_payoff(debts, extra_monthly, "snowball", start)
    both = av.paid_off and sb.paid_off
    return {
        "avalanche": av,
        "snowball": sb,
        "interest_saved": (sb.total_interest - av.total_interest) if both else None,
        "months_saved": (sb.months - av.months) if both else None,
    }


# ---------------------------------------------------------------------------
# 4. 50/30/20
# ---------------------------------------------------------------------------
@dataclass
class BudgetBucket:
    key: str                       # needs | wants | savings
    label: str
    amount: float
    share: Optional[float]         # of take-home; None when take-home is 0
    target: float
    status: str                    # unknown | on_track | close | off
    message: str


def budget_503020(take_home: float, needs: float, wants: float) -> List[BudgetBucket]:
    """Needs / wants / savings as shares of take-home vs 50/30/20.

    Savings = take-home - needs - wants, so extra debt payments (anything above
    the minimums) count as savings and minimums count as needs.
    """
    saved = take_home - needs - wants
    out: List[BudgetBucket] = []
    for key, label, amount in (("needs", "Needs", needs), ("wants", "Wants", wants),
                               ("savings", "Savings & extra debt payments", saved)):
        target = BUDGET_TARGETS[key]
        if take_home <= 0:
            out.append(BudgetBucket(key, label, amount, None, target, "unknown",
                                    "Add your take-home pay to see this."))
            continue
        share = amount / take_home
        pct, tgt = f"{share:.0%}", f"{target:.0%}"
        if key == "savings":
            gap = target - share
            if gap <= 0:
                status, msg = "on_track", f"{pct} saved: at or above the {tgt} guide."
            elif gap <= BUDGET_SLACK:
                status, msg = "close", f"{pct} saved: just under the {tgt} guide."
            else:
                status, msg = "off", (f"{pct} saved, under the {tgt} guide. Trimming needs "
                                      "or wants frees up money here.")
        else:
            over = share - target
            if over <= 0:
                status, msg = "on_track", f"{pct} of take-home: within the {tgt} guide."
            elif over <= BUDGET_SLACK:
                status, msg = "close", f"{pct} of take-home: a little over the {tgt} guide."
            elif key == "needs":
                status, msg = "off", (f"{pct} of take-home, over the {tgt} guide. Housing and "
                                      "car costs are usually the biggest levers.")
            else:
                status, msg = "off", (f"{pct} of take-home, over the {tgt} guide. This is "
                                      "often the easiest bucket to trim.")
        out.append(BudgetBucket(key, label, amount, share, target, status, msg))
    return out


# ---------------------------------------------------------------------------
# Everything at once
# ---------------------------------------------------------------------------
def analyze(inputs: Any, today: Optional[date] = None) -> Dict[str, Any]:
    """Run every check on (normalised) inputs. Fast: no engine calls."""
    i = normalize_inputs(inputs)
    today = today or date.today()
    warnings: List[str] = []
    mins = sum(d["min_payment"] for d in i["debts"] if d["balance"] > _PAID_EPS)
    if mins > i["needs_monthly"] + 0.5:
        warnings.append(f"Your needs ({money(i['needs_monthly'])}) are less than your minimum "
                        f"debt payments ({money(mins)}). Needs should include those minimums.")
    left = i["take_home_monthly"] - i["needs_monthly"] - i["wants_monthly"]
    if i["extra_debt_payment_monthly"] > max(0.0, left) + 0.5:
        warnings.append(f"Your extra debt payment ({money(i['extra_debt_payment_monthly'])}) is "
                        f"more than what's left after needs and wants ({money(max(0.0, left))}).")
    return {
        "inputs": i,
        "savings_rate": savings_rate(i["take_home_monthly"], i["needs_monthly"], i["wants_monthly"]),
        "emergency_fund": emergency_fund(i["cash_savings"], i["needs_monthly"],
                                         i["emergency_target_months"]),
        "ladder": priority_ladder(i, today),
        "payoff": compare_payoff(i["debts"], i["extra_debt_payment_monthly"], today),
        "budget": budget_503020(i["take_home_monthly"], i["needs_monthly"], i["wants_monthly"]),
        "limits": contribution_limits(i["hsa_family"], today, i["age"]),
        "warnings": warnings,
    }
