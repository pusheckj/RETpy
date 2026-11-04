"""Carry the money check-up's answers into the retirement planner.

The check-up (utils/simple_finance.py) and the planner (config keys in
``st.session_state.user_overrides``) describe the same person in different
terms. ``carried`` maps the check-up's answers onto planner keys; the guided
setup (components/guided_setup.py) applies it once, when someone who used the
check-up starts the planner. ``spending_split`` re-splits the check-up's
spending once the setup knows the housing payment. Pure: no Streamlit.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from utils.simple_finance import DEFAULT_INPUTS, normalize_inputs
    from utils.derived import KEEP_AMOUNTS_MODE, PRETAX_KEYS, savings_budget
    from utils.expense_categories import CATEGORIES, INPUTS
except ImportError:  # pragma: no cover
    from ui.utils.simple_finance import DEFAULT_INPUTS, normalize_inputs  # type: ignore
    from ui.utils.derived import (  # type: ignore
        KEEP_AMOUNTS_MODE, PRETAX_KEYS, savings_budget)
    from ui.utils.expense_categories import CATEGORIES, INPUTS  # type: ignore

# The planner inputs' upper bounds (a number_input errors on a larger value).
SALARY_MAX = 2_000_000          # components/sec_income.py
BALANCE_MAX = 10_000_000        # components/account_inputs.py
CONTRIB_401K_MAX = 40_000       # components/sec_savings.py _MANUAL_401K_MAX
CONTRIB_MAX = 10_000            # HSA / IRA inputs


def _cap(value: float, hi: int) -> int:
    return int(min(max(round(value), 0), hi))


def used(simple: Any) -> bool:
    """Did the visitor enter anything? The check-up opens on example numbers;
    those are never copied as if they were someone's own."""
    return isinstance(simple, dict) and normalize_inputs(simple) != normalize_inputs(DEFAULT_INPUTS)


def debt_minimums(simple: Any) -> float:
    return float(sum(d["min_payment"] for d in normalize_inputs(simple)["debts"]))


def contribution_401k(salary: float, pct: float, limit: Optional[int] = None) -> int:
    """$/yr into a 401(k) at ``pct`` percent of pay, within the yearly limit."""
    return _cap(salary * pct / 100.0, min(limit or CONTRIB_401K_MAX, CONTRIB_401K_MAX))


def spending_split(simple: Any, housing_monthly: float = 0.0) -> Dict[str, int]:
    """The check-up's monthly spending as the planner's categories.

    Wants -> Entertainment / discretionary. Needs include rent or mortgage and
    the minimum debt payments; less ``housing_monthly`` (the planner's own
    housing input), the rest goes to Other / miscellaneous, debt payments
    included: the planner doesn't model these debts, so their payments stay as
    spending. The check-up doesn't split needs further, so the other categories
    start at 0 for the visitor to fill in.
    """
    s = normalize_inputs(simple)
    out = {c.key: 0 for c in CATEGORIES if not c.partner_only}
    out["SPEND_DISCRETIONARY_MONTHLY"] = _cap(s["wants_monthly"], INPUTS["SPEND_DISCRETIONARY_MONTHLY"][1])
    out["SPEND_OTHER_MONTHLY"] = _cap(s["needs_monthly"] - housing_monthly,
                                      INPUTS["SPEND_OTHER_MONTHLY"][1])
    out["UTILITIES_MONTHLY"] = 0          # SPEND_UTILITIES_MONTHLY's mirror
    return out


def carried(simple: Any) -> Dict[str, Any]:
    """Planner overrides from the check-up's answers.

    Saving keeps the visitor's own 401(k) / HSA / IRA amounts and invests the
    rest (KEEP_AMOUNTS_MODE). Housing starts at 0, with all of the check-up's
    needs (rent included) in Other, so total spending equals the check-up's
    until the setup asks about housing and calls ``spending_split`` again.
    """
    s = normalize_inputs(simple)
    salary = s["gross_salary_annual"]
    out: Dict[str, Any] = {
        "YOUR_CASH": _cap(s["cash_savings"], BALANCE_MAX),
        "YOUR_401K_CONTRIBUTION": contribution_401k(salary, s["retirement_contrib_pct"]),
        "YOUR_401K_MATCH_PCT": s["employer_match_pct"] / 100.0,
        "YOUR_HSA_CONTRIBUTION": _cap(s["hsa_contrib_annual"], CONTRIB_MAX) if s["hsa_eligible"] else 0,
        "YOUR_BACKDOOR_ROTH": _cap(s["ira_contrib_annual"], CONTRIB_MAX),
        "SAVINGS_MODE": KEEP_AMOUNTS_MODE,
        "YOUR_BROKERAGE_CONTRIBUTION": 0,
        "PARTNER_BROKERAGE_CONTRIBUTION": 0,
        "HOME_VALUE": 0, "MORTGAGE_BALANCE": 0, "MORTGAGE_MONTHLY": 0,
        "MORTGAGE_YEARS_REMAINING": 0, "SPEND_RENT_MONTHLY": 0,
        **spending_split(s, 0.0),
    }
    if salary > 0:
        out["YOUR_BASE_SALARY"] = _cap(salary, SALARY_MAX)
    return out


def summary(simple: Any) -> Dict[str, float]:
    """The check-up figures the setup quotes back in its guidance."""
    s = normalize_inputs(simple)
    return {"needs": s["needs_monthly"], "wants": s["wants_monthly"],
            "debt_min": debt_minimums(s), "ira_so_far": s["ira_contrib_annual"],
            "salary": s["gross_salary_annual"],
            "pct_401k": s["retirement_contrib_pct"], "hsa_eligible": bool(s["hsa_eligible"])}


def from_planner(overrides: Any) -> Dict[str, Any]:
    """Check-up answers from a planner that is already filled in (the reverse of
    ``carried``), so the check-up opens on the owner's own numbers.

    Cash flow is the household's (take-home pay, needs, wants, cash), the same
    figures the planner's Savings section uses. Pay, 401(k), match, HSA and IRA
    are yours. Wants are discretionary spending plus the partner's own spending;
    needs are everything else the planner spends. The planner has no consumer
    debts, so the check-up starts with none (a mortgage is not a debt here).
    """
    ov = dict(overrides or {})

    def num(key: str) -> float:
        try:
            return float(ov.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    # The planner's own budget for this year, in whatever savings mode it is in
    # (Auto-allocate works out the 401(k)/HSA/IRA amounts; the keys may be stale).
    budget = savings_budget(ov)
    amounts = budget["amounts"]

    def saved(key: str) -> float:
        return float(amounts.get(key, ov.get(key) or 0) or 0)

    take_home = (budget["income"] - budget["taxes"]["total"] - sum(saved(k) for k in PRETAX_KEYS)) / 12.0
    spend = budget["expenses"] / 12.0
    partner = num("PARTNER_OTHER_MONTHLY") if num("PARTNER_AGE") > 0 else 0.0
    wants = min(num("SPEND_DISCRETIONARY_MONTHLY") + partner, spend)
    salary = num("YOUR_BASE_SALARY") + num("YOUR_BONUS_AMOUNT")
    hsa = saved("YOUR_HSA_CONTRIBUTION")
    out: Dict[str, Any] = {
        "take_home_monthly": max(take_home, 0.0),
        "needs_monthly": max(spend - wants, 0.0),
        "wants_monthly": wants,
        "cash_savings": num("YOUR_CASH") + num("PARTNER_CASH"),
        "gross_salary_annual": salary,
        "retirement_contrib_pct": (100.0 * saved("YOUR_401K_CONTRIBUTION") / salary) if salary > 0 else 0.0,
        "employer_match_pct": 100.0 * num("YOUR_401K_MATCH_PCT"),
        "hsa_eligible": hsa > 0,
        "hsa_family": num("PARTNER_AGE") > 0 or bool(ov.get("CHILDREN")),
        "hsa_contrib_annual": hsa,
        "ira_contrib_annual": saved("YOUR_BACKDOOR_ROTH"),
        "debts": [],
    }
    return normalize_inputs({**DEFAULT_INPUTS, **out})
