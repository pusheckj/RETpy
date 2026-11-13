"""Consumer-debt payoff math: the one place it lives.

Used by the engine (``config.debt_payment_for_age``), the planner's Debts
section and Debt payoff tile, and the money check-up
(``ui/utils/simple_finance.simulate_payoff``), so all three agree on payoff
months and interest.

A debt is plain data (it travels to the browser in the config snapshot)::

    {"name": "Visa", "kind": "credit_card", "balance": 6500.0,
     "apr": 0.24, "min_payment": 160.0}

``apr`` is a fraction (0.24 = 24%). Balances and payments are nominal dollars,
the way they appear on a statement.

Payoff (``amortize``): month by month with one fixed total payment, the
minimums plus the extra. Each month interest accrues (APR / 12), every debt
gets its minimum, and what is left goes to one target debt: highest APR first
(avalanche) or smallest balance first (snowball). A paid-off debt's minimum
rolls into the next target, so the total stays the same until all are gone.

Real frame (``real_schedule``): the engine works in today's dollars by whole
years. Interest is charged at the nominal APR on the nominal balance, and the
payment is a fixed nominal amount, so in today's dollars the payment shrinks
with inflation. The engine values each plan year's flows at the start of that
year: the payments made in plan year ``y`` (months ``12y+1`` .. ``12y+12``)
count as ``nominal / (1 + inflation) ** y`` today's dollars. That is the same
as a real interest rate of about ``(1 + APR) / (1 + inflation) - 1`` on a real
balance with a real payment that falls by ``1 / (1 + inflation)`` a year.
Payoff dates don't depend on the frame; only the cost in today's dollars does.

Pure Python, no imports from the rest of the package.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

KINDS: Tuple[str, ...] = ("credit_card", "student_loan", "car", "personal", "medical", "other")
KIND_LABELS: Dict[str, str] = {
    "credit_card": "Credit card", "student_loan": "Student loan", "car": "Car loan",
    "personal": "Personal loan", "medical": "Medical", "other": "Other",
}
STRATEGIES: Tuple[str, ...] = ("avalanche", "snowball")
MAX_MONTHS = 600            # 50 years; past this a plan "won't pay off"
MAX_DEBTS = 20
NAME_MAX_LEN = 40
BALANCE_MAX = 100_000_000.0
PAYMENT_MAX = 1_000_000.0
APR_MAX = 1.0               # 100%
PAID_EPS = 0.005            # a balance under half a cent is paid off

# Interest bands, shared with the check-up's "where your next dollar goes"
# ladder: 8%+ before investing past the match; 4-8% a judgment call; under 4%
# no rush.
HIGH_APR = 0.08
MODERATE_APR = 0.04


def clean_amount(value: Any, hi: float) -> float:
    """A finite number in [0, hi]; 0 for anything else. Accepts "$1,200"."""
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, str):
        value = value.strip().replace("$", "").replace(",", "").replace("%", "")
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(out):
        return 0.0
    return max(0.0, min(hi, out))


def guess_kind(name: Any) -> str:
    """A debt type from its name ("Visa card" -> credit_card), else "other"."""
    n = str(name or "").lower()
    for kind, words in (("student_loan", ("student", "college", "school")),
                        ("credit_card", ("card", "visa", "mastercard", "amex", "discover")),
                        ("car", ("car", "auto", "vehicle", "truck")),
                        ("medical", ("medical", "hospital", "doctor", "dental")),
                        ("personal", ("personal", "consolidation"))):
        if any(w in n for w in words):
            return kind
    return "other"


def normalize_debt(raw: Any, index: int = 0) -> Optional[Dict[str, Any]]:
    """A clean debt dict, or None when ``raw`` isn't a dict. Never raises."""
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    name = "" if name is None or isinstance(name, (dict, list)) else str(name).strip()
    name = name[:NAME_MAX_LEN] or f"Debt {index + 1}"
    kind = raw.get("kind")
    kind = kind if kind in KINDS else guess_kind(name)
    return {"name": name, "kind": kind,
            "balance": clean_amount(raw.get("balance"), BALANCE_MAX),
            "apr": clean_amount(raw.get("apr"), APR_MAX),
            "min_payment": clean_amount(raw.get("min_payment"), PAYMENT_MAX)}


def normalize_debts(raw: Any) -> List[Dict[str, Any]]:
    """Clean debt rows (dicts only, at most MAX_DEBTS). Never raises."""
    if not isinstance(raw, (list, tuple)):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        row = normalize_debt(item, len(out))
        if row is not None:
            out.append(row)
        if len(out) >= MAX_DEBTS:
            break
    return out


def normalize_strategy(value: Any) -> str:
    v = str(value or "").strip().lower()
    return v if v in STRATEGIES else "avalanche"


def apr_band(apr: float) -> str:
    """"high" (8%+), "moderate" (4-8%) or "low" (under 4%)."""
    return "high" if apr >= HIGH_APR else "moderate" if apr >= MODERATE_APR else "low"


def total_owed(debts: Any) -> float:
    """What the debts add up to now (0 with none)."""
    return sum(d["balance"] for d in normalize_debts(debts))


def underwater(debts: Sequence[Dict[str, Any]]) -> List[int]:
    """Indexes of debts whose minimum doesn't cover a month's interest."""
    return [k for k, d in enumerate(debts)
            if d["balance"] > PAID_EPS and d["min_payment"] <= d["balance"] * d["apr"] / 12.0 + 1e-9]


@dataclass
class Payoff:
    """One payoff plan. Lists indexed by debt follow the input order of the
    debts that still had a balance (``rows``)."""
    strategy: str
    rows: List[Dict[str, Any]]               # normalized debts with a balance
    paid_off: bool
    months: int                              # months simulated
    monthly_budget: float                    # minimums + extra, held fixed
    total_interest: float
    total_paid: float
    remaining: float                         # owed at the end (0 when paid off)
    payoff_month: List[Optional[int]]        # per row; None = not paid off
    interest_by_debt: List[float]
    focus_order: List[int]                   # where the extra money goes, in order
    balances: List[float] = field(default_factory=list)   # total owed, month 0..months
    payments: List[float] = field(default_factory=list)   # total paid, month 1..months
    underwater: List[int] = field(default_factory=list)

    @property
    def first_win(self) -> Optional[int]:
        """Month the first debt is paid off (None if none is)."""
        done = [m for m in self.payoff_month if m is not None]
        return min(done) if done else None


def amortize(debts: Any, extra_monthly: Any = 0.0, strategy: Any = "avalanche",
             max_months: int = MAX_MONTHS) -> Payoff:
    """Month-by-month payoff with a fixed total payment (see the module doc)."""
    strategy = normalize_strategy(strategy)
    rows = [d for d in normalize_debts(debts) if d["balance"] > PAID_EPS]
    extra = clean_amount(extra_monthly, PAYMENT_MAX)
    budget = sum(r["min_payment"] for r in rows) + extra
    if not rows:
        return Payoff(strategy, [], True, 0, budget, 0.0, 0.0, 0.0, [], [], [], [0.0], [], [])
    if strategy == "snowball":
        order = sorted(range(len(rows)), key=lambda k: (rows[k]["balance"], -rows[k]["apr"], k))
    else:
        order = sorted(range(len(rows)), key=lambda k: (-rows[k]["apr"], rows[k]["balance"], k))

    n = len(rows)
    bal = [r["balance"] for r in rows]
    rate = [r["apr"] / 12.0 for r in rows]
    mins = [r["min_payment"] for r in rows]
    payoff_month: List[Optional[int]] = [None] * n
    interest_by = [0.0] * n
    balances = [sum(bal)]
    payments: List[float] = []
    interest = paid = 0.0
    month = 0
    while month < max_months and any(b > PAID_EPS for b in bal):
        month += 1
        pool = budget
        for k in range(n):
            if bal[k] > PAID_EPS:
                charge = bal[k] * rate[k]
                bal[k] += charge
                interest += charge
                interest_by[k] += charge
        for k in range(n):
            if bal[k] > PAID_EPS:
                pay = min(mins[k], bal[k], pool)
                bal[k] -= pay
                pool -= pay
        for k in order:
            if pool <= 0:
                break
            if bal[k] > PAID_EPS:
                pay = min(pool, bal[k])
                bal[k] -= pay
                pool -= pay
        paid += budget - pool
        payments.append(budget - pool)
        for k in range(n):
            if payoff_month[k] is None and bal[k] <= PAID_EPS:
                bal[k] = 0.0
                payoff_month[k] = month
        balances.append(sum(bal))

    done = all(b <= PAID_EPS for b in bal)
    return Payoff(strategy, rows, done, month, budget, interest, paid,
                  0.0 if done else sum(bal), payoff_month, interest_by, order,
                  balances, payments, underwater(rows))


# ---------------------------------------------------------------------------
# Today's dollars, by plan year (the engine's view)
# ---------------------------------------------------------------------------
@dataclass
class RealSchedule:
    """A payoff plan by plan year. ``payments[y]`` is what is paid in plan year
    ``y`` in today's dollars; ``nominal[y]`` the same in dollars of the day.
    ``balances[y]`` is the total owed at the START of plan year ``y`` in
    today's dollars (``balances[0]`` = owed now)."""
    payments: List[float]
    nominal: List[float]
    balances: List[float]
    payoff: Payoff


def real_schedule(debts: Any, extra_monthly: Any = 0.0, strategy: Any = "avalanche",
                  inflation: float = 0.0, payoff: Optional[Payoff] = None) -> RealSchedule:
    """The plan's yearly payments and balances in today's dollars (module doc)."""
    p = payoff or amortize(debts, extra_monthly, strategy)
    infl = float(inflation or 0.0)
    nominal: List[float] = []
    for m, amount in enumerate(p.payments):
        y = m // 12
        if y == len(nominal):
            nominal.append(0.0)
        nominal[y] += amount
    deflator = [(1.0 + infl) ** y for y in range(len(nominal) + 1)]
    real = [v / deflator[y] for y, v in enumerate(nominal)]
    balances = [p.balances[12 * y] / deflator[y] for y in range(len(nominal) + 1)
                if 12 * y < len(p.balances)]
    return RealSchedule(real, nominal, balances, p)


_CACHE: Dict[Tuple, Tuple[float, ...]] = {}
_CACHE_MAX = 64


def real_payments_by_year(debts: Any, extra_monthly: Any, strategy: Any,
                          inflation: float) -> Tuple[float, ...]:
    """``real_schedule(...).payments`` as a tuple, memoized (the engine asks
    for it once per simulated year)."""
    key = (repr(debts), repr(extra_monthly), repr(strategy), float(inflation or 0.0))
    hit = _CACHE.get(key)
    if hit is None:
        hit = tuple(real_schedule(debts, extra_monthly, strategy, inflation).payments)
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.clear()
        _CACHE[key] = hit
    return hit
