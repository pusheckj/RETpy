"""Derived quantities computed from user_overrides.

All functions are pure: they take the overrides dict and return a number or
dict. They do NOT mutate state, write to session_state, or call Streamlit.
"""
from __future__ import annotations

from typing import Dict
from utils.coerce import safe_int, safe_float, as_fraction

from retirement_sim import config as cfg


def compute_total_income(overrides: dict) -> int:
    """Return household gross annual income (today's $) from the income breakdown.

    Sum of YOUR_BASE_SALARY + YOUR_BONUS_AMOUNT + YOUR_RSU_AMOUNT + YOUR_OTHER_INCOME
    + same partner fields. Falls back to HOUSEHOLD_INCOME_QUICK if breakdown missing.
    """
    keys = [
        "YOUR_BASE_SALARY", "YOUR_BONUS_AMOUNT", "YOUR_RSU_AMOUNT", "YOUR_OTHER_INCOME",
        "PARTNER_BASE_SALARY", "PARTNER_BONUS_AMOUNT", "PARTNER_RSU_AMOUNT", "PARTNER_OTHER_INCOME",
    ]
    total = sum(safe_int(overrides.get(k, 0), 0) for k in keys)
    if total == 0:
        # Backwards-compat fallback
        total = safe_int(overrides.get("HOUSEHOLD_INCOME_QUICK", 0), 0)
    return total


def compute_taxes(overrides: dict) -> Dict[str, float]:
    """Return a dict with federal, state, fica, total, effective_rate.

    Uses simplified rough calculations:
      - Federal: 2024 MFJ progressive brackets if married, single brackets if not
      - State: depends on STATE_CHOICE override:
          "CA" -> 2024 California brackets
          "No state tax" -> 0
          "Other" -> flat YOUR_MARGINAL_TAX_RATE on taxable income, matching the
                     engine's FlatRateStateTax for this choice
      - FICA: 7.65% of wages up to SS wage base ($168,600 for 2024), then 1.45% above
    """
    income = compute_total_income(overrides)
    if income <= 0:
        return {"federal": 0.0, "state": 0.0, "fica": 0.0, "total": 0.0, "effective_rate": 0.0}

    # Normalize filing status to one of "MFJ" / "S" / "HOH" (matches
    # retirement_sim.config.normalize_filing_status). Default MFJ.
    raw_status = overrides.get("FILING_STATUS", "MFJ")
    s = str(raw_status).strip().lower() if raw_status is not None else "mfj"
    if s in ("hoh", "head of household", "head-of-household") or s.startswith("h"):
        status = "HOH"
    elif s in ("s", "single") or s.startswith("s"):
        status = "S"
    else:
        status = "MFJ"

    # 2024 federal standard deduction by filing status (from retirement_sim.config).
    fed_std_ded = {"MFJ": 29_200, "S": 14_600, "HOH": 21_900}[status]
    taxable = max(0, income - fed_std_ded)

    # 2024 federal ordinary-income brackets by filing status (from retirement_sim.config).
    if status == "MFJ":
        brackets = [
            (23_200,  0.10), (94_300,  0.12), (201_050, 0.22),
            (383_900, 0.24), (487_450, 0.32), (731_200, 0.35), (float("inf"), 0.37),
        ]
    elif status == "HOH":
        brackets = [
            (16_550,  0.10), (63_100,  0.12), (100_500, 0.22),
            (191_950, 0.24), (243_700, 0.32), (609_350, 0.35), (float("inf"), 0.37),
        ]
    else:  # Single
        brackets = [
            (11_600,  0.10), (47_150,  0.12), (100_525, 0.22),
            (191_950, 0.24), (243_725, 0.32), (609_350, 0.35), (float("inf"), 0.37),
        ]

    fed_tax = 0.0
    prev = 0.0
    for cap, rate in brackets:
        if taxable <= prev:
            break
        slab = min(taxable, cap) - prev
        fed_tax += slab * rate
        prev = cap

    # State
    state_choice = str(overrides.get("STATE_CHOICE", "CA"))
    if state_choice == "No state tax" or state_choice == "None":
        state_tax = 0.0
    elif state_choice == "CA":
        # CA treats HoH as unmarried for bracket/deduction purposes here.
        ca_married = (status == "MFJ")
        # 2024 CA standard deduction (from retirement_sim.config: MFJ $11,080).
        # Single/HoH use the unmarried figure ($5,540).
        ca_std_ded = 11_080 if ca_married else 5_540
        ca_taxable = max(0, income - ca_std_ded)
        # 2024 CA brackets (simplified)
        ca_brackets = (
            [(20_824, 0.01), (49_368, 0.02), (77_918, 0.04), (108_162, 0.06),
             (136_700, 0.08), (698_274, 0.093), (837_922, 0.103),
             (1_396_542, 0.113), (float("inf"), 0.123)]
            if ca_married else
            [(10_412, 0.01), (24_684, 0.02), (38_959, 0.04), (54_081, 0.06),
             (68_350, 0.08), (349_137, 0.093), (418_961, 0.103),
             (698_271, 0.113), (float("inf"), 0.123)]
        )
        state_tax = 0.0
        prev = 0.0
        for cap, rate in ca_brackets:
            if ca_taxable <= prev:
                break
            slab = min(ca_taxable, cap) - prev
            state_tax += slab * rate
            prev = cap
    else:
        # "Other": mirror the ENGINE exactly. account_simulation's
        # _select_state_tax_brackets() builds FlatRateStateTax(rate=
        # cfg.YOUR_MARGINAL_TAX_RATE) for this choice, so the sidebar must charge
        # the same rate. It previously hard-coded 5% and ignored the slider, so
        # the reported state tax never moved while the simulated one swung by
        # tens of thousands a year.
        state_tax = taxable * as_fraction(overrides.get("YOUR_MARGINAL_TAX_RATE", 0.05), 0.05)

    # FICA: computed PER EARNER so the SS wage base caps each person's wages
    # independently (a two-earner household gets two SS caps, not one shared
    # cap on combined wages). SS = 6.2% up to the wage base; Medicare = 1.45%
    # uncapped. Sum the two earners.
    SS_WAGE_BASE = 168_600
    SS_RATE = 0.062
    MEDICARE_RATE = 0.0145

    def _fica_for(wage_keys) -> float:
        w = sum(safe_int(overrides.get(k, 0), 0) for k in wage_keys)
        if w <= 0:
            return 0.0
        return min(w, SS_WAGE_BASE) * SS_RATE + w * MEDICARE_RATE

    your_wages = sum(safe_int(overrides.get(k, 0), 0)
                     for k in ("YOUR_BASE_SALARY", "YOUR_BONUS_AMOUNT", "YOUR_RSU_AMOUNT"))
    partner_wages = sum(safe_int(overrides.get(k, 0), 0)
                        for k in ("PARTNER_BASE_SALARY", "PARTNER_BONUS_AMOUNT", "PARTNER_RSU_AMOUNT"))

    if partner_wages > 0:
        fica = (_fica_for(("YOUR_BASE_SALARY", "YOUR_BONUS_AMOUNT", "YOUR_RSU_AMOUNT"))
                + _fica_for(("PARTNER_BASE_SALARY", "PARTNER_BONUS_AMOUNT", "PARTNER_RSU_AMOUNT")))
    else:
        # Single-earner fallback. When no wage keys are set, fall back to the
        # QUICK household-income figure (which stands in for a salary), NOT total
        # income — total income includes *_OTHER_INCOME (pension, rental,
        # interest), which is not subject to payroll tax. The two-earner branch
        # above deliberately excludes those keys, so using `income` here
        # contradicted it and charged FICA on a pure-pension household.
        wages = your_wages if your_wages > 0 else safe_int(
            overrides.get("HOUSEHOLD_INCOME_QUICK", 0), 0)
        fica = min(wages, SS_WAGE_BASE) * SS_RATE + wages * MEDICARE_RATE

    total = fed_tax + state_tax + fica
    effective = total / income if income > 0 else 0.0

    return {
        "federal": float(fed_tax),
        "state": float(state_tax),
        "fica": float(fica),
        "total": float(total),
        "effective_rate": float(effective),
    }


def compute_expenses_today(overrides: dict) -> int:
    """Sum of all monthly spending categories × 12 + housing (mortgage or rent) × 12.

    Categories from spending_inputs: utilities, food, transport, health, discretionary, other.
    Housing auto-derived from MORTGAGE_MONTHLY (if active mortgage years remaining > 0)
    or SPEND_RENT_MONTHLY (if renting).
    """
    cats = [
        "SPEND_UTILITIES_MONTHLY", "SPEND_FOOD_MONTHLY",
        "SPEND_TRANSPORT_MONTHLY", "SPEND_HEALTH_MONTHLY",
        "SPEND_DISCRETIONARY_MONTHLY", "SPEND_OTHER_MONTHLY",
    ]
    monthly = sum(safe_int(overrides.get(k, 0), 0) for k in cats)

    # Partner's personal monthly spending. Must be PARTNER_OTHER_MONTHLY, NOT
    # PARTNER_MONTHLY_SPENDING: config.py documents these as a deliberate
    # footgun pair -- only PARTNER_OTHER_MONTHLY feeds CURRENT_ANNUAL_EXPENSES /
    # granular_nonhousing_annual(), i.e. what the ENGINE actually spends.
    # PARTNER_MONTHLY_SPENDING is the separate savings-math knob. Using it here
    # made this helper disagree with the engine (on a real profile it showed a
    # few thousand dollars a year less than was simulated). The same
    # substitution was already fixed in sim_runner (finding #18d) but not here.
    # Falls back to the legacy key, then to the shared $1,500 default, so a
    # profile that only sets the old key still reads sensibly.
    _partner = overrides.get("PARTNER_OTHER_MONTHLY",
                             overrides.get("PARTNER_MONTHLY_SPENDING", 1_500))
    monthly += safe_int(_partner, 1_500)

    mortgage = safe_int(overrides.get("MORTGAGE_MONTHLY", 0), 0)
    rent = safe_int(overrides.get("SPEND_RENT_MONTHLY", 0), 0)
    home_value = safe_int(overrides.get("HOME_VALUE", 0), 0)

    if mortgage > 0:
        monthly += mortgage
    elif home_value == 0 and rent > 0:
        monthly += rent
    # Owned outright: property tax + insurance are still due. Same rate and
    # toggle as the engine (cfg.home_carrying_cost_annual), so this total and
    # the simulation agree for an owner with no loan.
    carrying = 0.0
    if mortgage <= 0 and home_value > 0 and bool(
            overrides.get("MODEL_HOME_CARRYING_COST_AFTER_PAYOFF", True)):
        pct = safe_float(overrides.get("HOME_CARRYING_COST_PCT",
                                       overrides.get("NEW_HOME_ESCROW_PCT", 0.0135)), 0.0135)
        carrying = home_value * max(0.0, pct)

    # Children living at home today, each at their own monthly cost: the same
    # rule cfg.calculate_child_expenses applies at your current age. (This used
    # to count only the first child, even with two at home.)
    for kid in cfg.children_in(overrides):
        if 0 <= -kid["years_until_birth"] < kid["leaves_home_age"]:
            monthly += safe_int(kid["monthly_cost"], 0)

    annual = monthly * 12 + round(carrying)

    # Extra mortgage principal is REAL CASH the engine charges on top of the
    # scheduled payment (see cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL), so it belongs in
    # "what we spend this year". Added once, here, and only while a loan actually
    # exists -- the mortgage term above already contributes the scheduled payment,
    # so this cannot double-count it. Without this the sidebar total and
    # compute_disposable both ignored it, overstating investable surplus by the
    # prepayment amount.
    if safe_float(overrides.get("MORTGAGE_BALANCE", 0) or 0, 0.0) > 0 or bool(
            overrides.get("HOUSE_MOVE_ENABLED", False)):
        annual += extra_mortgage_for_age(
            overrides, safe_int(overrides.get("YOUR_AGE", 25), 25))

    return int(annual)


def compute_disposable(overrides: dict) -> int:
    """Income - taxes - expenses today (annual)."""
    income = compute_total_income(overrides)
    taxes = compute_taxes(overrides)["total"]
    expenses = compute_expenses_today(overrides)
    return int(max(0, income - taxes - expenses))


# IRS limits (2024)
LIMITS_2024 = {
    "401k_employee": 23_000,
    "401k_catchup_50": 7_500,
    "ira": 7_000,
    "ira_catchup_50": 1_000,
    "hsa_family": 8_300,
    "hsa_individual": 4_150,
    "hsa_catchup_55": 1_000,
}


def get_limit(name: str, age: int = 30, family: bool = True) -> int:
    """Return 2024 IRS limit for a given contribution type."""
    if name == "401k":
        v = LIMITS_2024["401k_employee"]
        if age >= 50:
            v += LIMITS_2024["401k_catchup_50"]
        return v
    if name == "ira":
        v = LIMITS_2024["ira"]
        if age >= 50:
            v += LIMITS_2024["ira_catchup_50"]
        return v
    if name == "hsa":
        v = LIMITS_2024["hsa_family"] if family else LIMITS_2024["hsa_individual"]
        # HSA catch-up starts at 55 (not 50, unlike 401k/IRA). Without this the
        # "max out tax-advantaged" preset and auto_allocate_savings under-filled
        # a 55+ user's HSA by $1,000/yr and routed it to brokerage instead.
        if age >= 55:
            v += LIMITS_2024["hsa_catchup_55"]
        return v
    return 0


# Savings modes (components/sec_savings.py). The engine sweeps un-spent income
# into the brokerage for any mode starting with "Auto"; this one keeps the
# user's own 401(k) / HSA / IRA amounts instead of auto_allocate_savings'.
AUTO_ALLOCATE_MODE = "Auto-allocate (recommended)"
KEEP_AMOUNTS_MODE = "Auto-invest what's left (keep my amounts)"


def auto_allocate_savings(disposable: int, overrides: dict) -> Dict[str, int]:
    """Default allocation rule: max tax-advantaged first, residual to brokerage.

    Order:
      1. Your 401(k) → IRS limit
      2. Partner 401(k) → IRS limit (if partner exists)
      3. Your HSA family → IRS limit (only if HSA-eligible — assume yes if user has any HSA balance)
      4. Your IRA / backdoor Roth → IRS limit
      5. Partner IRA → IRS limit
      6. Your brokerage → fills remainder (split 50/50 with partner if partner exists)

    Returns a dict with keys matching the simulator's contribution config keys:
      YOUR_401K_CONTRIBUTION, PARTNER_401K_CONTRIBUTION, YOUR_HSA_CONTRIBUTION,
      YOUR_BACKDOOR_ROTH, PARTNER_ROTH_CONTRIBUTION,
      YOUR_BROKERAGE_CONTRIBUTION, PARTNER_BROKERAGE_CONTRIBUTION
    """
    your_age = safe_int(overrides.get("YOUR_AGE", 30), 30)
    partner_age = safe_int(overrides.get("PARTNER_AGE", 0), 0)
    has_partner = partner_age > 0

    allocated = {
        "YOUR_401K_CONTRIBUTION": 0,
        "PARTNER_401K_CONTRIBUTION": 0,
        "YOUR_HSA_CONTRIBUTION": 0,
        "YOUR_BACKDOOR_ROTH": 0,
        "PARTNER_ROTH_CONTRIBUTION": 0,
        "YOUR_BROKERAGE_CONTRIBUTION": 0,
        "PARTNER_BROKERAGE_CONTRIBUTION": 0,
    }
    remaining = max(0, int(disposable))

    # 1. Your 401k
    cap = get_limit("401k", your_age)
    fill = min(cap, remaining)
    allocated["YOUR_401K_CONTRIBUTION"] = fill
    remaining -= fill

    # 2. Partner 401k
    if has_partner and remaining > 0:
        cap = get_limit("401k", partner_age)
        fill = min(cap, remaining)
        allocated["PARTNER_401K_CONTRIBUTION"] = fill
        remaining -= fill

    # 3. HSA family (assume eligibility)
    if remaining > 0:
        cap = get_limit("hsa", your_age, family=True)
        fill = min(cap, remaining)
        allocated["YOUR_HSA_CONTRIBUTION"] = fill
        remaining -= fill

    # 4. IRA (your)
    if remaining > 0:
        cap = get_limit("ira", your_age)
        fill = min(cap, remaining)
        allocated["YOUR_BACKDOOR_ROTH"] = fill
        remaining -= fill

    # 5. IRA (partner)
    if has_partner and remaining > 0:
        cap = get_limit("ira", partner_age)
        fill = min(cap, remaining)
        allocated["PARTNER_ROTH_CONTRIBUTION"] = fill
        remaining -= fill

    # 6. Brokerage (residual). The couple SPLITS EXPENSES EVENLY, so each person
    #    covers HALF of household expenses from their own income and banks their
    #    OWN remainder in their OWN brokerage -> the residual lands MOSTLY in the
    #    higher earner's account (entirely, if the other's income only covers their
    #    half), NOT 50/50. Falls back to an even split only when no per-person
    #    income breakdown is available.
    if remaining > 0:
        if has_partner:
            your_gross = sum(safe_int(overrides.get(k, 0), 0) for k in
                             ("YOUR_BASE_SALARY", "YOUR_BONUS_AMOUNT", "YOUR_RSU_AMOUNT", "YOUR_OTHER_INCOME"))
            partner_gross = sum(safe_int(overrides.get(k, 0), 0) for k in
                                ("PARTNER_BASE_SALARY", "PARTNER_BONUS_AMOUNT", "PARTNER_RSU_AMOUNT", "PARTNER_OTHER_INCOME"))
            exp = float(compute_expenses_today(overrides))
            if bool(overrides.get("PRIMARY_PAYS_HOUSING", False)):
                # Primary covers the full mortgage; only the rest is split evenly.
                mortgage = 12.0 * safe_int(overrides.get("MORTGAGE_MONTHLY", 0), 0)
                rest = max(0.0, exp - mortgage)
                your_exp = mortgage + 0.5 * rest
                partner_exp = 0.5 * rest
            else:
                your_exp = partner_exp = 0.5 * exp
            your_left = max(0.0, your_gross - your_exp)
            partner_left = max(0.0, partner_gross - partner_exp)
            leftover_total = your_left + partner_left
            if your_gross + partner_gross <= 0:
                your_amt = remaining // 2            # no breakdown -> keep even split
            elif leftover_total > 0:
                your_amt = int(round(remaining * your_left / leftover_total))
            else:
                your_amt = remaining                 # neither covers their half -> primary banks it
            allocated["YOUR_BROKERAGE_CONTRIBUTION"] = your_amt
            allocated["PARTNER_BROKERAGE_CONTRIBUTION"] = remaining - your_amt
        else:
            allocated["YOUR_BROKERAGE_CONTRIBUTION"] = remaining

    return allocated


# ---------------------------------------------------------------------------
# Mortgage math (house-move planning)
# ---------------------------------------------------------------------------
# The big-purchase section used to take the new loan balance AND the new monthly
# payment as independent free-text inputs alongside the home price. Nothing tied
# them together, so raising "New home value" left the loan and payment untouched
# and the model silently costed the OLD house -- reporting e.g. 80.4% success for
# a $1.6M purchase that actually scores 78.0%, i.e. flipping a "meets your 80%
# target" verdict to a miss. These helpers let the UI derive both from the
# numbers a buyer actually knows: price, down payment, rate, term, escrow.

def mortgage_payment(loan: float, annual_rate: float, years: int) -> float:
    """Level monthly principal + interest for a fully-amortizing loan.

    ``annual_rate`` is a fraction (0.0611 == 6.11%). Falls back to simple
    division at a zero rate so a 0% entry can't divide by zero.
    """
    loan = max(0.0, safe_float(loan, 0.0))
    years = max(1, safe_int(years, 30))
    n = years * 12
    r = safe_float(annual_rate, 0.0) / 12.0
    if loan <= 0:
        return 0.0
    if r <= 0:
        return loan / n
    return loan * r / (1.0 - (1.0 + r) ** -n)


def implied_mortgage_rate(loan: float, pi_payment: float, years: int) -> float:
    """Invert ``mortgage_payment`` — the rate implied by a known P&I payment.

    Used to seed the rate input from a plan that predates the derived fields, so
    an existing saved profile keeps producing its original monthly payment
    instead of silently jumping to a new default rate.
    """
    loan = safe_float(loan, 0.0)
    pi_payment = safe_float(pi_payment, 0.0)
    years = max(1, safe_int(years, 30))
    if loan <= 0 or pi_payment <= 0:
        return 0.0
    if pi_payment * years * 12 <= loan:          # payment can't even cover principal
        return 0.0
    lo, hi = 0.0, 0.50
    for _ in range(60):                          # bisection: monotonic in rate
        mid = (lo + hi) / 2.0
        if mortgage_payment(loan, mid, years) > pi_payment:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def new_home_financing(overrides: dict) -> Dict[str, float]:
    """Derive the new-home loan and all-in monthly payment from the UI inputs.

    Returns ``{loan, principal_interest, escrow, monthly, down_payment}``.
    ``monthly`` is what the engine consumes as ``NEW_MORTGAGE_MONTHLY`` — it is
    all-in (P&I + property tax + insurance), because the engine treats that
    single number as the household's housing outflow.
    """
    price = max(0.0, safe_float(overrides.get("NEW_HOME_VALUE", 0), 0.0))
    down_pct = safe_float(overrides.get("NEW_HOME_DOWN_PCT", 0.20), 0.20)
    down_pct = min(max(down_pct, 0.0), 1.0)
    rate = safe_float(overrides.get("NEW_MORTGAGE_RATE", 0.065), 0.065)
    years = safe_int(overrides.get("NEW_MORTGAGE_YEARS", 30), 30)
    escrow_pct = safe_float(overrides.get("NEW_HOME_ESCROW_PCT", 0.0135), 0.0135)

    down = price * down_pct
    loan = max(0.0, price - down)
    pi = mortgage_payment(loan, rate, years)
    escrow = price * max(0.0, escrow_pct) / 12.0
    return {
        "loan": loan,
        "principal_interest": pi,
        "escrow": escrow,
        "monthly": pi + escrow,
        "down_payment": down,
    }


def advance_mortgage(balance: float, annual_rate: float, pi_payment: float,
                     months: int = 12, extra_annual: float = 0.0) -> float:
    """Amortize ``balance`` forward ``months`` at ``annual_rate``.

    Returns the remaining principal (floored at 0). ``pi_payment`` must be
    PRINCIPAL + INTEREST only — the app's stored monthly figures are all-in
    (they include property tax and insurance), so subtract escrow first or the
    loan appears to pay off far too fast.

    ``extra_annual`` is additional principal for a 12-month year, applied evenly
    per month so it compounds into the interest saving the same way the engine's
    ``_amortize_mortgage_year`` does. Default 0.0 keeps every existing caller
    byte-identical.
    """
    bal = max(0.0, safe_float(balance, 0.0))
    r = max(0.0, safe_float(annual_rate, 0.0)) / 12.0
    pmt = max(0.0, safe_float(pi_payment, 0.0))
    extra_m = max(0.0, safe_float(extra_annual, 0.0)) / 12.0
    for _ in range(max(0, int(months))):
        if bal <= 0:
            return 0.0
        bal = bal * (1.0 + r) - pmt - extra_m
        if bal < 0:
            return 0.0
    # Snap a sub-cent floating-point residual to zero: after exactly `term`
    # payments the balance lands on ~1e-8 rather than 0.0, which would otherwise
    # read as a still-outstanding loan.
    return 0.0 if bal < 0.01 else bal


def advance_mortgage_with_extra(balance: float, annual_rate: float,
                                pi_payment: float, months: int = 12,
                                extra_annual: float = 0.0):
    """Like :func:`advance_mortgage`, but also returns the extra principal
    ACTUALLY consumed by the loan — which is what a caller must charge against
    savings.

    In the payoff year the loan absorbs only part of the intended extra: the
    scheduled payment may retire the balance in, say, month 3, and no further
    payments are made. Charging the full intended ``extra_annual`` anyway
    destroys the difference (measured: ~$30k vanished from net worth in the
    payoff year). Callers should draw only the returned amount, or refund the
    unused remainder.

    Returns ``(remaining_principal, extra_actually_paid)``. With
    ``extra_annual=0`` the balance is identical to :func:`advance_mortgage`.
    """
    bal = max(0.0, safe_float(balance, 0.0))
    r = max(0.0, safe_float(annual_rate, 0.0)) / 12.0
    pmt = max(0.0, safe_float(pi_payment, 0.0))
    extra_m = max(0.0, safe_float(extra_annual, 0.0)) / 12.0
    paid = 0.0
    for _ in range(max(0, int(months))):
        if bal <= 0:
            break
        after_sched = bal * (1.0 + r) - pmt
        if after_sched <= 0:
            bal = 0.0
            break
        take = min(extra_m, after_sched)
        paid += take
        bal = after_sched - take
        if bal < 0.01:
            bal = 0.0
            break
    return (0.0 if bal < 0.01 else bal), paid


def current_mortgage_terms(overrides: dict) -> Dict[str, float]:
    """Infer the CURRENT mortgage's P&I payment and rate from the stored inputs.

    ``MORTGAGE_MONTHLY`` is an all-in figure, so escrow (estimated from
    ``NEW_HOME_ESCROW_PCT`` applied to today's home value) is removed before
    inverting the payment for a rate. Returns ``{balance, pi_payment, rate,
    years}``; a zero balance yields zeros so callers can skip the amortization.
    """
    balance = max(0.0, safe_float(overrides.get("MORTGAGE_BALANCE", 0), 0.0))
    years = safe_int(overrides.get("MORTGAGE_YEARS_REMAINING", 0), 0)
    monthly = max(0.0, safe_float(overrides.get("MORTGAGE_MONTHLY", 0), 0.0))
    if balance <= 0 or years <= 0 or monthly <= 0:
        return {"balance": balance, "pi_payment": 0.0, "rate": 0.0, "years": years}
    home_value = max(0.0, safe_float(overrides.get("HOME_VALUE", 0), 0.0))
    escrow_pct = safe_float(overrides.get("NEW_HOME_ESCROW_PCT", 0.0135), 0.0135)
    pi = max(0.0, monthly - home_value * max(0.0, escrow_pct) / 12.0)
    if pi <= 0:                       # escrow estimate swallowed the payment
        pi = monthly
    return {
        "balance": balance,
        "pi_payment": pi,
        "rate": implied_mortgage_rate(balance, pi, years),
        "years": years,
    }


# ===========================================================================
# Mortgage schedule — SINGLE SOURCE OF TRUTH for the UI
# ===========================================================================
# Several views independently re-derived "is there still a loan, and what does
# housing cost this year": the spending chart (payoff annotation + housing
# bars), the net-worth chart (home equity), and compute_expenses_today (the
# sidebar total + disposable income). Each computed it from TERM LENGTHS, so
# none of them saw extra principal: with $30k/yr extra the sidebar correctly
# said "paid off at 47" while the spending chart still annotated age 51 and
# showed the full payment for four extra years, and never showed the $30k as a
# cost at all.
#
# This mirrors the ENGINE's amortisation exactly -- _level_payment at
# cfg.MORTGAGE_RATE_FOR_PAYOFF, with the lifecycle house move replacing the
# loan at HOUSE_MOVE_AGE -- so a payoff age shown anywhere in the UI matches
# what the simulation actually does. Consumers must take housing cost AND
# balance from here rather than recomputing, so the extra is counted exactly
# once per view.

def _pi_from_all_in(monthly: float, home_value: float, overrides: dict) -> float:
    """Strip the escrow estimate off an all-in monthly payment to get P&I.

    Same convention as :func:`current_mortgage_terms`: the app's stored monthly
    figures include property tax and insurance.
    """
    m = max(0.0, safe_float(monthly, 0.0))
    esc = max(0.0, safe_float(overrides.get("NEW_HOME_ESCROW_PCT", 0.0135), 0.0135))
    pi = m - max(0.0, safe_float(home_value, 0.0)) * esc / 12.0
    return pi if pi > 0 else m       # escrow estimate swallowed the payment


def _balance_from_payment(pi_monthly: float, annual_rate: float, years: int) -> float:
    """Principal implied by a P&I payment stream (present value of an annuity).

    The new mortgage can be specified EITHER by balance or by monthly payment +
    term. Without this, a profile that gives only ``NEW_MORTGAGE_MONTHLY`` had no
    balance to amortize, so the schedule reported no loan at all: zero housing
    cost and no payoff age.
    """
    pmt = max(0.0, safe_float(pi_monthly, 0.0))
    n = max(0, safe_int(years, 0)) * 12
    r = max(0.0, safe_float(annual_rate, 0.0)) / 12.0
    if pmt <= 0 or n <= 0:
        return 0.0
    if r <= 0:
        return pmt * n
    return pmt * (1.0 - (1.0 + r) ** -n) / r


def _payoff_rate(overrides: dict) -> float:
    return safe_float(overrides.get("MORTGAGE_RATE_FOR_PAYOFF", 0.065), 0.065)


def _new_loan_rate(overrides: dict) -> float:
    """The house move's new loan rate; mirrors cfg.new_mortgage_rate()."""
    v = overrides.get("NEW_MORTGAGE_RATE")
    return _payoff_rate(overrides) if v is None else safe_float(v, _payoff_rate(overrides))


def extra_mortgage_for_age(overrides: dict, age) -> float:
    """Extra principal owed at ``age`` (0 when disabled or outside the window).

    UI-side mirror of ``cfg.extra_mortgage_payment_for_age`` that reads the
    overrides dict, so charts don't have to monkeypatch the engine config.
    """
    amt = safe_float(overrides.get("EXTRA_MORTGAGE_PAYMENT_ANNUAL", 0) or 0, 0.0)
    if amt <= 0:
        return 0.0
    start = overrides.get("EXTRA_MORTGAGE_PAYMENT_START_AGE")
    start = safe_int(overrides.get("YOUR_AGE", 25), 25) if start is None else safe_int(start, 0)
    if safe_int(age, 0) < start:
        return 0.0
    stop = overrides.get("EXTRA_MORTGAGE_PAYMENT_STOP_AGE")
    if stop is not None and safe_int(age, 0) >= safe_int(stop, 10 ** 6):
        return 0.0
    return amt


def mortgage_schedule(overrides: dict, ages) -> dict:
    """Per-age loan state, honouring extra principal and the house move.

    Returns ``{"by_age": {age: {"balance", "scheduled", "extra", "housing"}},
    "payoff_age": int|None, "owns": bool}`` where

      * ``scheduled`` is the all-in annual payment (0 once the loan is gone),
      * ``extra``     is the extra principal actually paid that year (never more
                      than the balance left),
      * ``housing``   is scheduled + extra, i.e. the real cash going to housing;
                      for an owner with no loan outstanding (paid off, or never
                      had one) it is the property tax + insurance carrying cost
                      instead -- the engine's ``home_carrying_cost_annual`` rule.

    ``balance`` is the principal at the START of the year.
    """
    ages = [safe_int(a, 0) for a in ages]
    your_age = safe_int(overrides.get("YOUR_AGE", 25), 25)
    rate = max(0.0, _payoff_rate(overrides))
    r = rate / 12.0

    bal = safe_float(overrides.get("MORTGAGE_BALANCE", 0) or 0, 0.0)
    years = safe_int(overrides.get("MORTGAGE_YEARS_REMAINING", 0), 0)
    monthly = safe_float(overrides.get("MORTGAGE_MONTHLY", 0) or 0, 0.0)
    if bal > 0 and years > 0:
        pi = mortgage_payment(bal, rate, years)
    elif monthly > 0 and years > 0:
        # Loan given as payment + term with no balance: recover the principal so
        # there is something to amortize (otherwise this reports no loan at all).
        pi = _pi_from_all_in(monthly, overrides.get("HOME_VALUE", 0), overrides)
        bal = _balance_from_payment(pi, rate, years)
    else:
        pi = 0.0
    scheduled_annual = monthly * 12.0

    move_on = bool(overrides.get("HOUSE_MOVE_ENABLED", False))
    move_age = safe_int(overrides.get("HOUSE_MOVE_AGE", 10 ** 6), 10 ** 6)
    rent_annual = safe_float(overrides.get("SPEND_RENT_MONTHLY", 0) or 0, 0.0) * 12.0
    owns = bal > 0 or monthly > 0 or safe_float(overrides.get("HOME_VALUE", 0) or 0, 0.0) > 0 \
        or move_on
    # Post-payoff carrying cost (mirrors cfg.home_carrying_cost_annual; the pct
    # resolves exactly as config_builder translates it onto the engine).
    carry_on = bool(overrides.get("MODEL_HOME_CARRYING_COST_AFTER_PAYOFF", True))
    carry_pct = safe_float(overrides.get(
        "HOME_CARRYING_COST_PCT", overrides.get("NEW_HOME_ESCROW_PCT", 0.0135)), 0.0135)
    home_value = safe_float(overrides.get("HOME_VALUE", 0) or 0, 0.0)

    by_age, payoff_age = {}, None
    for age in range(min(ages or [your_age]), max(ages or [your_age]) + 1):
        if move_on and age == move_age:
            rate = max(0.0, _new_loan_rate(overrides))      # the new loan's own rate
            r = rate / 12.0
            bal = safe_float(overrides.get("NEW_MORTGAGE_BALANCE", 0) or 0, 0.0)
            _ny = safe_int(overrides.get("NEW_MORTGAGE_YEARS", 30), 30)
            _nm = safe_float(overrides.get("NEW_MORTGAGE_MONTHLY", 0) or 0, 0.0)
            if bal > 0:
                pi = mortgage_payment(bal, rate, _ny)
            else:
                # Specified by payment + term instead of balance: strip escrow
                # off the all-in monthly (same convention as
                # current_mortgage_terms) and invert the annuity for principal.
                _nhv = safe_float(overrides.get("NEW_HOME_VALUE", 0) or 0, 0.0)
                pi = _pi_from_all_in(_nm, _nhv, overrides)
                bal = _balance_from_payment(pi, rate, _ny)
            scheduled_annual = _nm * 12.0
            home_value = safe_float(overrides.get("NEW_HOME_VALUE", 0) or 0, 0.0)
            owns = True

        start_balance = bal
        if bal > 0 and age >= your_age:
            extra = min(extra_mortgage_for_age(overrides, age), bal)
            sched = scheduled_annual
            # Advance 12 months, applying the extra monthly the way the engine
            # does (so it compounds into the interest saving).
            em = extra / 12.0
            for _ in range(12):
                if bal <= 0:
                    break
                bal = bal * (1.0 + r) - pi - em
                if bal < 0:
                    bal = 0.0
                    break
            if bal < 0.01:
                bal = 0.0
                if payoff_age is None:
                    # Paid off DURING this year -> the payment stops next year.
                    payoff_age = age + 1
        else:
            extra, sched = 0.0, (0.0 if owns else rent_annual)
        # Owner with no loan left: property tax + insurance continue.
        carry = (max(0.0, home_value) * carry_pct
                 if (owns and carry_on and start_balance <= 0) else 0.0)

        by_age[age] = {"balance": start_balance, "scheduled": sched,
                       "extra": extra, "housing": sched + extra + carry}

    # A renter never "pays off"; an owner with no loan is already paid off.
    if payoff_age is None and owns and safe_float(
            overrides.get("MORTGAGE_BALANCE", 0) or 0, 0.0) <= 0 and not move_on:
        payoff_age = your_age
    return {"by_age": by_age, "payoff_age": payoff_age, "owns": owns}
