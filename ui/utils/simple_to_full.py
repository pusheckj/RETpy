"""Carry the money check-up's answers into the retirement planner.

The check-up (utils/simple_finance.py) and the planner (config keys in
``st.session_state.user_overrides``) describe the same person in different
terms. ``carried`` maps the check-up's answers onto planner keys; the guided
setup (components/guided_setup.py) applies it once, when someone who used the
check-up starts the planner. ``spending_split`` re-splits the check-up's
spending once the setup knows the housing payment. Pure: no Streamlit.

Debts are the one thing the two versions share all along: the check-up's
debts are the planner's DEBTS (``planner_debts`` / ``checkup_debts``), and
switching versions copies them across (``debts_to_checkup`` /
``debts_to_planner``, called by app.py's version switch). The check-up counts
the minimum payments in its needs; the planner keeps them out of its spending
categories (the Debts section pays them), so moving debts across moves the
minimums out of, or into, the needs.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from retirement_sim import config as cfg

from retirement_sim import debts as dm

try:
    from utils.age_limits import AGE_MIN, AGE_MAX
except ImportError:  # pragma: no cover
    from ui.utils.age_limits import AGE_MIN, AGE_MAX  # type: ignore

try:
    from utils.simple_finance import DEFAULT_INPUTS, contribution_limits, normalize_inputs, to_engine_debts
    from utils.derived import KEEP_AMOUNTS_MODE, PRETAX_KEYS, debt_payments_this_year, savings_budget
    from utils.expense_categories import CATEGORIES, INPUTS
except ImportError:  # pragma: no cover
    from ui.utils.simple_finance import (  # type: ignore
        DEFAULT_INPUTS, contribution_limits, normalize_inputs, to_engine_debts)
    from ui.utils.derived import (  # type: ignore
        KEEP_AMOUNTS_MODE, PRETAX_KEYS, debt_payments_this_year, savings_budget)
    from ui.utils.expense_categories import CATEGORIES, INPUTS  # type: ignore

# The planner inputs' upper bounds (a number_input errors on a larger value).
SALARY_MAX = 2_000_000          # components/sec_income.py
BALANCE_MAX = 100_000_000       # components/account_inputs.py
CONTRIB_401K_MAX = 40_000       # components/sec_savings.py _MANUAL_401K_MAX
CONTRIB_MAX = 10_000            # HSA / IRA inputs


def _cap(value: float, hi: int) -> int:
    return int(min(max(round(value), 0), hi))


def used(simple: Any) -> bool:
    """Did the visitor enter anything? The check-up opens on example numbers;
    those are never copied as if they were someone's own."""
    return isinstance(simple, dict) and normalize_inputs(simple) != normalize_inputs(DEFAULT_INPUTS)


def debt_minimums(simple: Any) -> float:
    """The minimums still being paid: a paid-off row (balance 0) owes none, and the
    planner never pays it either."""
    return float(sum(d["min_payment"] for d in normalize_inputs(simple)["debts"]
                     if d["balance"] > dm.PAID_EPS))


def contribution_401k(salary: float, pct: float, limit: Optional[int] = None) -> int:
    """$/yr into a 401(k) at ``pct`` percent of pay, within the yearly limit."""
    return _cap(salary * pct / 100.0, min(limit or CONTRIB_401K_MAX, CONTRIB_401K_MAX))


def spending_split(simple: Any, housing_monthly: float = 0.0,
                   debt_monthly: Optional[float] = None) -> Dict[str, int]:
    """The check-up's monthly spending as the planner's categories.

    Wants -> Entertainment / discretionary. Needs include rent or mortgage and
    the minimum debt payments; less ``housing_monthly`` (the planner's own
    housing input) and ``debt_monthly`` (the minimums, which the planner's
    Debts section pays; default: the check-up's own debts' minimums), the rest
    goes to Other / miscellaneous. The check-up doesn't split needs further, so
    the other categories start at 0 for the visitor to fill in.
    """
    s = normalize_inputs(simple)
    debt = debt_minimums(s) if debt_monthly is None else max(0.0, float(debt_monthly))
    out = {c.key: 0 for c in CATEGORIES if not c.partner_only}
    out["SPEND_DISCRETIONARY_MONTHLY"] = _cap(s["wants_monthly"], INPUTS["SPEND_DISCRETIONARY_MONTHLY"][1])
    out["SPEND_OTHER_MONTHLY"] = _cap(s["needs_monthly"] - housing_monthly - debt,
                                      INPUTS["SPEND_OTHER_MONTHLY"][1])
    out["UTILITIES_MONTHLY"] = 0          # SPEND_UTILITIES_MONTHLY's mirror
    return out


def planner_debts(simple: Any) -> Dict[str, Any]:
    """The check-up's debts as the planner's DEBTS and DEBT_EXTRA_MONTHLY."""
    s = normalize_inputs(simple)
    rows = [{**d, "apr": round(d["apr"], 8)} for d in to_engine_debts(s["debts"])]
    return {"DEBTS": rows, "DEBT_EXTRA_MONTHLY": round(s["extra_debt_payment_monthly"], 2)}


def checkup_debts(overrides: Any) -> Dict[str, Any]:
    """The planner's DEBTS and extra payment as the check-up's ``debts`` and
    ``extra_debt_payment_monthly`` (APR as a percent)."""
    ov = dict(overrides or {})
    rows = [{"name": d["name"], "balance": d["balance"], "apr_pct": round(d["apr"] * 100.0, 6),
             "min_payment": d["min_payment"], "kind": d["kind"]}
            for d in dm.normalize_debts(ov.get("DEBTS"))]
    extra = dm.clean_amount(ov.get("DEBT_EXTRA_MONTHLY"), dm.PAYMENT_MAX)
    return {"debts": rows, "extra_debt_payment_monthly": extra}


def debts_to_checkup(simple: Any, overrides: Any) -> Optional[Dict[str, Any]]:
    """Check-up answers with the planner's debts, or None when nothing changes.

    Only once the planner has debts or the check-up has been used: the example
    numbers keep their example debts. Needs move by the change in minimums, so
    they keep including the minimum payments."""
    ov = dict(overrides or {})
    if "DEBTS" not in ov or not (dm.normalize_debts(ov.get("DEBTS")) or used(simple)):
        return None
    s = normalize_inputs(simple)
    new = normalize_inputs({**s, **checkup_debts(ov)})
    if (new["debts"], new["extra_debt_payment_monthly"]) == (s["debts"], s["extra_debt_payment_monthly"]):
        return None
    new["needs_monthly"] = max(0.0, s["needs_monthly"] + debt_minimums(new) - debt_minimums(s))
    return normalize_inputs(new)


def debts_to_planner(simple: Any, overrides: Any) -> Optional[Dict[str, Any]]:
    """The planner overrides to change so its debts are the check-up's, or None
    when nothing changes (or the check-up was never used)."""
    if not used(simple):
        return None
    ov = dict(overrides or {})
    new = planner_debts(simple)
    old = {"DEBTS": dm.normalize_debts(ov.get("DEBTS")),
           "DEBT_EXTRA_MONTHLY": dm.clean_amount(ov.get("DEBT_EXTRA_MONTHLY"), dm.PAYMENT_MAX)}
    same = (len(new["DEBTS"]) == len(old["DEBTS"])
            and abs(new["DEBT_EXTRA_MONTHLY"] - old["DEBT_EXTRA_MONTHLY"]) < 0.005
            and all(a["name"] == b["name"] and a["kind"] == b["kind"]
                    and abs(a["balance"] - b["balance"]) < 0.005
                    and abs(a["apr"] - b["apr"]) < 1e-7
                    and abs(a["min_payment"] - b["min_payment"]) < 0.005
                    for a, b in zip(new["DEBTS"], old["DEBTS"])))
    return None if same else new


def carried(simple: Any) -> Dict[str, Any]:
    """Planner overrides from the check-up's answers.

    Saving keeps the visitor's own 401(k) / HSA / IRA amounts and invests the
    rest (KEEP_AMOUNTS_MODE). ``married`` and ``partner_salary_annual`` are
    check-up only (they set the Roth IRA income limit), so they are left out here
    (``partner_answers`` hands them to the setup's questions).
    The debts become the planner's DEBTS (``planner_debts``), so their minimums
    leave the needs. Housing starts at 0, with the rest of the check-up's needs
    (rent included) in Other, so total spending plus the debt payments equals
    the check-up's until the setup asks about housing and calls
    ``spending_split`` again.
    """
    s = normalize_inputs(simple)
    salary = s["gross_salary_annual"]
    out: Dict[str, Any] = {
        "YOUR_CASH": _cap(s["cash_savings"], BALANCE_MAX),
        # at most this year's limit (Max out rounds the percent up, so pay x percent can
        # pass it by a few dollars)
        "YOUR_401K_CONTRIBUTION": contribution_401k(
            salary, s["retirement_contrib_pct"], contribution_limits(False, None, s["age"])["401k"]),
        "YOUR_401K_MATCH_PCT": s["employer_match_pct"] / 100.0,
        "YOUR_HSA_CONTRIBUTION": _cap(s["hsa_contrib_annual"], CONTRIB_MAX) if s["hsa_eligible"] else 0,
        "YOUR_BACKDOOR_ROTH": _cap(s["ira_contrib_annual"], CONTRIB_MAX),
        "SAVINGS_MODE": KEEP_AMOUNTS_MODE,
        "YOUR_BROKERAGE_CONTRIBUTION": 0,
        "PARTNER_BROKERAGE_CONTRIBUTION": 0,
        "HOME_VALUE": 0, "MORTGAGE_BALANCE": 0, "MORTGAGE_MONTHLY": 0,
        "MORTGAGE_YEARS_REMAINING": 0, "SPEND_RENT_MONTHLY": 0,
        **spending_split(s, 0.0),
        **planner_debts(s),
    }
    if salary > 0:
        out["YOUR_BASE_SALARY"] = _cap(salary, SALARY_MAX)
    if AGE_MIN <= s["age"] <= AGE_MAX:           # 0 = not given
        out["YOUR_AGE"] = int(s["age"])
    return out


def summary(simple: Any) -> Dict[str, float]:
    """The check-up figures the setup quotes back in its guidance."""
    s = normalize_inputs(simple)
    return {"needs": s["needs_monthly"], "wants": s["wants_monthly"],
            "debt_min": debt_minimums(s), "ira_so_far": s["ira_contrib_annual"],
            "salary": s["gross_salary_annual"],
            "pct_401k": s["retirement_contrib_pct"], "hsa_eligible": bool(s["hsa_eligible"]),
            "age": int(s["age"]) if AGE_MIN <= s["age"] <= AGE_MAX else 0}


def partner_answers(simple: Any) -> Dict[str, Any]:
    """What the check-up said about a spouse. Not carried into the plan (the
    setup asks about the partner itself), but the setup opens its "who is this
    plan for" and partner-pay questions on it."""
    s = normalize_inputs(simple)
    return {"married": bool(s["married"]),
            "partner_salary": s["partner_salary_annual"] if s["married"] else 0.0}


def from_planner(overrides: Any) -> Dict[str, Any]:
    """Check-up answers from a planner that is already filled in (the reverse of
    ``carried``), so the check-up opens on the owner's own numbers.

    Cash flow is the household's (take-home pay, needs, wants, cash), the same
    figures the planner's Investments section (Saving each year) uses. Pay, 401(k), match, HSA and IRA
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
    debts = checkup_debts(ov)
    minimums = sum(d["min_payment"] for d in debts["debts"] if d["balance"] > 0)
    # The planner's expenses include this year's debt payments; the check-up
    # splits them into needs (minimums) and savings (the extra).
    spend = (budget["expenses"] - debt_payments_this_year(ov)) / 12.0
    partner = num("PARTNER_OTHER_MONTHLY") if num("PARTNER_AGE") > 0 else 0.0
    wants = min(num("SPEND_DISCRETIONARY_MONTHLY") + partner, spend)
    salary = num("YOUR_BASE_SALARY") + num("YOUR_BONUS_AMOUNT")
    married = num("PARTNER_AGE") > 0 and cfg.normalize_filing_status(ov.get("FILING_STATUS")) == "MFJ"
    hsa = saved("YOUR_HSA_CONTRIBUTION")
    out: Dict[str, Any] = {
        "take_home_monthly": max(take_home, 0.0),
        "needs_monthly": max(spend - wants, 0.0) + minimums,
        "wants_monthly": wants,
        "cash_savings": num("YOUR_CASH") + num("PARTNER_CASH"),
        "gross_salary_annual": salary,
        "retirement_contrib_pct": (100.0 * saved("YOUR_401K_CONTRIBUTION") / salary) if salary > 0 else 0.0,
        "employer_match_pct": 100.0 * num("YOUR_401K_MATCH_PCT"),
        "hsa_eligible": hsa > 0,
        "hsa_family": num("PARTNER_AGE") > 0 or bool(ov.get("CHILDREN")),
        "hsa_contrib_annual": hsa,
        "ira_contrib_annual": saved("YOUR_BACKDOOR_ROTH"),
        "married": married,
        "partner_salary_annual": num("PARTNER_BASE_SALARY") + num("PARTNER_BONUS_AMOUNT"),
        **debts,
    }
    return normalize_inputs({**DEFAULT_INPUTS, **out})
