"""Numbers for the planner's debt screens (pure: no Streamlit).

The Debts section (components/sec_debts.py) and the Debt payoff tile
(components/debt_payoff.py) read their figures from here. The payoff math is
retirement_sim/debts.py, the same calculation the simulation spends and the
money check-up shows, so every screen agrees.

Plans are in nominal dollars (the way statements read). Effects on retirement
are in today's dollars (``retirement_effect``), like the rest of the planner.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

from retirement_sim import config as cfg
from retirement_sim import debts as dm

try:
    from utils.coerce import safe_float, safe_int
    from utils.simple_finance import month_label
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_float, safe_int  # type: ignore
    from ui.utils.simple_finance import month_label  # type: ignore


# ---------------------------------------------------------------------------
# The Debts section's widgets (components/sec_debts.py)
# ---------------------------------------------------------------------------
PREFIX = "debt_"
FIELDS = ("name", "kind", "balance", "apr", "min")
BALANCE_MAX = 10_000_000
PAYMENT_MAX = 100_000
EXTRA_KEY = "debt_extra"
STRATEGY_KEY = "debt_strategy"


def row_key(i: int, field: str) -> str:
    return f"{PREFIX}{i}_{field}"


def widget_values(d: Dict[str, Any]) -> Dict[str, Any]:
    """A DEBTS row as its widgets' values (APR shown as a percent)."""
    return {"name": d["name"], "kind": d["kind"],
            "balance": min(safe_int(round(d["balance"]), 0), BALANCE_MAX),
            "apr": round(float(d["apr"]) * 100.0, 4),
            "min": min(safe_int(round(d["min_payment"]), 0), PAYMENT_MAX)}


def row_from_widgets(ss, i: int, base: Dict[str, Any]) -> Dict[str, Any]:
    v = {**widget_values(base), **{f: ss[row_key(i, f)] for f in FIELDS if row_key(i, f) in ss}}
    return dm.normalize_debt({"name": v["name"], "kind": v["kind"],
                              "balance": float(safe_int(v["balance"], 0)),
                              "apr": round(safe_float(v["apr"], 0.0) / 100.0, 8),
                              "min_payment": float(safe_int(v["min"], 0))}, i)


def seed_rows(ss, debts: List[Dict[str, Any]], force: bool = False) -> None:
    """Push DEBTS rows into the row widgets (all of them when ``force``; then
    the keys of rows past the end are dropped too)."""
    if force:
        for k in [k for k in list(ss.keys()) if isinstance(k, str) and k.startswith(PREFIX)
                  and k[len(PREFIX):].split("_", 1)[0].isdigit()]:
            del ss[k]
    for i, d in enumerate(dm.normalize_debts(debts)):
        for f, v in widget_values(d).items():
            if force or row_key(i, f) not in ss:
                ss[row_key(i, f)] = v


def reseed_widgets(ss) -> None:
    """Rewrite every Debts widget (rows, extra, order) from the plan's overrides.
    For when the section comes back after a run that did not draw it: Streamlit
    dropped the widgets' values, and reading a key then gives its first seed."""
    ov = ss.get("user_overrides", {}) or {}
    seed_rows(ss, ov.get("DEBTS") or [], force=True)
    ss.pop(EXTRA_KEY, None)
    ss.pop(STRATEGY_KEY, None)


def current_rows(ss) -> List[Dict[str, Any]]:
    """DEBTS as the row widgets hold them on this run."""
    base = dm.normalize_debts((ss.get("user_overrides", {}) or {}).get("DEBTS"))
    return [row_from_widgets(ss, i, d) for i, d in enumerate(base)]


def live(state, overrides: Any = None) -> Dict[str, Any]:
    """``overrides`` (default: user_overrides) with the debt keys as the Debts
    section's widgets hold them on this run, so a section drawn before it
    (Expenses, Taxes) isn't one edit behind."""
    ov = dict(overrides if overrides is not None else (state.get("user_overrides", {}) or {}))
    if not any(isinstance(k, str) and k.startswith(PREFIX) for k in list(state.keys())):
        return ov
    ov["DEBTS"] = current_rows(state)
    if EXTRA_KEY in state:
        ov["DEBT_EXTRA_MONTHLY"] = safe_int(state[EXTRA_KEY], 0)
    if STRATEGY_KEY in state:
        ov["DEBT_STRATEGY"] = dm.normalize_strategy(state[STRATEGY_KEY])
    return ov


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------
def rows(overrides: Any) -> List[Dict[str, Any]]:
    """The plan's debts (DEBTS), cleaned."""
    return dm.normalize_debts((overrides or {}).get("DEBTS"))


def owing(overrides: Any) -> List[Dict[str, Any]]:
    """The debts with a balance."""
    return [d for d in rows(overrides) if d["balance"] > dm.PAID_EPS]


def extra(overrides: Any) -> float:
    return dm.clean_amount((overrides or {}).get("DEBT_EXTRA_MONTHLY"), dm.PAYMENT_MAX)


def strategy(overrides: Any) -> str:
    return dm.normalize_strategy((overrides or {}).get("DEBT_STRATEGY"))


def plan(overrides: Any, more: float = 0.0, strat: Optional[str] = None,
         minimums_only: bool = False) -> dm.Payoff:
    """The payoff plan: the plan's debts, extra (+ ``more``) and strategy."""
    paid_extra = 0.0 if minimums_only else extra(overrides) + max(0.0, float(more or 0.0))
    return dm.amortize(rows(overrides), paid_extra, strat or strategy(overrides))


def duration(months: Optional[int]) -> str:
    """"3 yr 2 mo", "8 mo", "1 yr"."""
    if months is None:
        return "—"
    y, m = divmod(int(months), 12)
    return " ".join(([f"{y} yr"] if y else []) + ([f"{m} mo"] if m or not y else []))


def when(start: date, months: Optional[int]) -> Optional[str]:
    """"Mar 2029" for ``months`` months after ``start``'s month (None stays None)."""
    return None if months is None else month_label(start, int(months))


@dataclass
class Summary:
    owed: float
    monthly: float                 # minimums + extra
    paid_off: bool
    months: int
    debt_free: Optional[str]       # "Mar 2029"
    interest: float                # nominal, over the whole plan
    underwater: List[str]          # names whose minimum doesn't cover the interest
    no_minimum: List[str]          # 0% debts with no minimum payment
    growing: bool                  # a debt is never paid off and keeps growing
    per_debt: List[Dict[str, Any]]  # name, kind, band, balance, apr, min, payoff_month, payoff, interest


def summary(overrides: Any, start: Optional[date] = None) -> Summary:
    start = start or date.today()
    p = plan(overrides)
    per = []
    for k in sorted(range(len(p.rows)), key=lambda k: (p.payoff_month[k] is None,
                                                       p.payoff_month[k] or 0, p.focus_order.index(k))):
        d = p.rows[k]
        per.append({**d, "kind_label": dm.KIND_LABELS[d["kind"]], "band": dm.apr_band(d["apr"]),
                    "payoff_month": p.payoff_month[k], "payoff": when(start, p.payoff_month[k]),
                    "interest": p.interest_by_debt[k]})
    return Summary(sum(d["balance"] for d in p.rows), p.monthly_budget, p.paid_off, p.months,
                   when(start, p.months) if p.paid_off else None, p.total_interest,
                   [p.rows[k]["name"] for k in p.underwater],
                   [p.rows[k]["name"] for k in dm.no_minimum(p.rows)], p.growing, per)


def compare(overrides: Any, start: Optional[date] = None) -> Dict[str, Dict[str, Any]]:
    """Avalanche and snowball with the plan's own debts and payment."""
    start = start or date.today()
    out = {}
    for s in dm.STRATEGIES:
        p = plan(overrides, strat=s)
        first = p.first_win
        first_name = next((p.rows[k]["name"] for k in p.focus_order
                           if first is not None and p.payoff_month[k] == first), None)
        out[s] = {"plan": p, "paid_off": p.paid_off, "months": p.months, "growing": p.growing,
                  "debt_free": when(start, p.months) if p.paid_off else None,
                  "interest": p.total_interest, "first_win": when(start, first),
                  "first_win_months": first, "first_name": first_name,
                  "first_target": p.rows[p.focus_order[0]]["name"] if p.focus_order else None}
    return out


def what_if(overrides: Any, more: float) -> Dict[str, Any]:
    """Paying ``more`` a month on top of the plan: months and interest saved.
    ``None`` savings when either plan never pays off."""
    now, faster = plan(overrides), plan(overrides, more=more)
    both = now.paid_off and faster.paid_off
    return {"now": now, "faster": faster,
            "months_saved": now.months - faster.months if both else None,
            "interest_saved": now.total_interest - faster.total_interest if both else None}


def real_return(overrides: Any) -> float:
    """The expected real return of the plan's return scenario: the same simple
    rate the net-worth projection and Freedom milestones use."""
    try:
        from components.net_worth_projection_chart import _SCENARIO_RETURNS
    except ImportError:  # pragma: no cover
        from ui.components.net_worth_projection_chart import _SCENARIO_RETURNS  # type: ignore
    scen = str((overrides or {}).get("ACTIVE_RETURN_SCENARIO", cfg.ACTIVE_RETURN_SCENARIO)).lower()
    return float(_SCENARIO_RETURNS.get(scen, _SCENARIO_RETURNS["historical"])["investment"])


def inflation(overrides: Any) -> float:
    try:
        return float((overrides or {}).get("EXPECTED_INFLATION", cfg.EXPECTED_INFLATION))
    except (TypeError, ValueError):
        return float(cfg.EXPECTED_INFLATION)


def retirement_effect(overrides: Any, more: float, retire_age: int,
                      rate: Optional[float] = None) -> Optional[float]:
    """Roughly how much more (or less, if negative) the plan has at retirement,
    in today's dollars, when it pays ``more`` a month on its debts.

    A quick estimate, not a simulation: the yearly difference in debt payments
    (today's dollars, the simulation's own schedule) is invested at the plan's
    expected real return. Before retirement a dollar not paid on debt is saved
    that year and grows until retirement (returns, then savings, as in the
    simulation's working years); after it, a dollar not paid is a dollar not
    withdrawn, valued back to the retirement date. None with no debts."""
    if not owing(overrides):
        return None
    r = real_return(overrides) if rate is None else float(rate)
    infl = inflation(overrides)
    now = dm.real_schedule(rows(overrides), extra(overrides), strategy(overrides), infl).payments
    fast = dm.real_schedule(rows(overrides), extra(overrides) + max(0.0, float(more or 0.0)),
                            strategy(overrides), infl).payments
    years = max(0, int(retire_age) - int((overrides or {}).get("YOUR_AGE", cfg.YOUR_AGE)))
    total = 0.0
    for y in range(max(len(now), len(fast))):
        saved = (now[y] if y < len(now) else 0.0) - (fast[y] if y < len(fast) else 0.0)
        total += saved * ((1 + r) ** (years - 1 - y) if y < years else (1 + r) ** -(y - years))
    return total


# ---------------------------------------------------------------------------
# "Things to know": worked examples, computed so the text is always right
# ---------------------------------------------------------------------------
EXAMPLE_BALANCE = 5_000.0
EXAMPLE_APR = 0.24


def fixed_payment_example(payment: float, balance: float = EXAMPLE_BALANCE,
                          apr: float = EXAMPLE_APR) -> dm.Payoff:
    return dm.amortize([{"balance": balance, "apr": apr, "min_payment": payment}])


def minimum_only_example(balance: float = EXAMPLE_BALANCE, apr: float = EXAMPLE_APR,
                         pct: float = 0.01, floor: float = 25.0) -> Dict[str, float]:
    """Paying only a card's minimum when the minimum is the month's interest
    plus ``pct`` of the balance, at least ``floor`` (a common card formula).
    Returns months, interest and total paid."""
    b, r = float(balance), apr / 12.0
    months = 0
    interest = paid = 0.0
    while b > dm.PAID_EPS and months < dm.MAX_MONTHS:
        months += 1
        charge = b * r
        pay = min(b + charge, max(floor, charge + pct * b))
        interest += charge
        paid += pay
        b = b + charge - pay
    return {"months": months, "interest": interest, "paid": paid,
            "first_payment": max(floor, balance * r + pct * balance)}


def years_text(months: int) -> str:
    """"about 19 years" / "about 4 and a half years"."""
    y = months / 12.0
    whole = math.floor(y)
    frac = y - whole
    if frac >= 0.75:
        return f"about {whole + 1} years"
    if frac >= 0.25:
        return f"about {whole} and a half years" if whole else "about half a year"
    return f"about {whole} years" if whole != 1 else "about a year"
