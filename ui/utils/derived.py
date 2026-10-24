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


def _working_tax_inputs(overrides: dict, pretax_savings: bool = True) -> dict:
    """Keyword arguments for cfg.working_year_taxes from the sidebar inputs.

    Missing keys count as 0 / not set, like the rest of this module. A partner
    is present when PARTNER_AGE > 0 (or, without an age, when they have income).
    Deferrals are capped at this year's IRS limits, as the simulation caps them.
    """
    from retirement_sim import config as cfg

    def _sum(keys):
        return sum(max(0, safe_int(overrides.get(k, 0), 0)) for k in keys)

    your_wages = _sum(("YOUR_BASE_SALARY", "YOUR_BONUS_AMOUNT", "YOUR_RSU_AMOUNT"))
    partner_wages = _sum(("PARTNER_BASE_SALARY", "PARTNER_BONUS_AMOUNT", "PARTNER_RSU_AMOUNT"))
    your_other = _sum(("YOUR_OTHER_INCOME",))
    partner_other = _sum(("PARTNER_OTHER_INCOME",))
    if your_wages + partner_wages + your_other + partner_other == 0:
        # Only a quick household figure: it stands in for one salary.
        your_wages = max(0, safe_int(overrides.get("HOUSEHOLD_INCOME_QUICK", 0), 0))

    your_age = safe_int(overrides.get("YOUR_AGE", 30), 30)
    if "PARTNER_AGE" in overrides:
        partner_age = safe_int(overrides.get("PARTNER_AGE", 0), 0)
        partner = partner_age > 0
    else:
        partner = (partner_wages + partner_other) > 0
        partner_age = your_age if partner else 0

    raw_status = overrides.get("FILING_STATUS")
    status = cfg.normalize_filing_status("MFJ" if raw_status is None else raw_status)

    k401 = hsa = p401 = 0.0
    if pretax_savings:
        year = cfg.CURRENT_YEAR
        k401 = min(max(0, safe_int(overrides.get("YOUR_401K_CONTRIBUTION", 0), 0)),
                   cfg.get_401k_limit(your_age, year))
        hsa = min(max(0, safe_int(overrides.get("YOUR_HSA_CONTRIBUTION", 0), 0)),
                  cfg.get_hsa_limit(your_age, year, is_family=True))
        if partner:
            p401 = min(max(0, safe_int(overrides.get("PARTNER_401K_CONTRIBUTION", 0), 0)),
                       cfg.get_401k_limit(partner_age, year))

    return dict(
        your_wages=your_wages, partner_wages=partner_wages,
        your_other=your_other, partner_other=partner_other,
        your_401k=k401, partner_401k=p401, your_hsa=hsa,
        your_age=your_age, partner_age=partner_age, status=status, partner=partner,
        state=overrides.get("STATE_CHOICE", "CA"),
        flat_rate=as_fraction(overrides.get("YOUR_MARGINAL_TAX_RATE", 0.05), 0.05),
    )


def compute_taxes(overrides: dict, pretax_savings: bool = True) -> Dict[str, float]:
    """Return a dict with federal, state, fica, total, effective_rate.

    This year's tax on the household's pay, from the SAME function the
    simulation uses for every working year (cfg.working_year_taxes): federal
    brackets and standard deduction by filing status (two returns for an
    unmarried couple), the chosen state's table (STATE_CHOICE; "Other" = flat
    YOUR_MARGINAL_TAX_RATE above the federal standard deduction), and FICA per
    earner with the Social Security wage base and the Additional Medicare Tax.
    "state" includes state payroll tax (California SDI).

    ``pretax_savings`` (default True) lowers taxable income by the 401(k)/HSA
    contributions in ``overrides``, as the simulation does. (savings_budget
    works out those contributions and this tax together.)
    """
    income = compute_total_income(overrides)
    if income <= 0:
        return {"federal": 0.0, "state": 0.0, "fica": 0.0, "total": 0.0, "effective_rate": 0.0}

    from retirement_sim import config as cfg

    t = cfg.working_year_taxes(**_working_tax_inputs(overrides, pretax_savings))
    total = t["federal"] + t["state"] + t["fica"]
    return {
        "federal": float(t["federal"]),
        "state": float(t["state"]),
        "fica": float(t["fica"]),
        "total": float(total),
        "effective_rate": float(total / income) if income > 0 else 0.0,
    }


def files_two_returns(overrides: dict) -> bool:
    """Whether the sidebar inputs describe an unmarried couple (two returns)."""
    from retirement_sim import config as cfg

    kw = _working_tax_inputs(overrides, pretax_savings=False)
    return cfg.files_two_returns(kw["status"], kw["partner"])


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
    # exists this year (the schedule knows; a renter planning to buy has none
    # yet) -- the mortgage term above already contributes the scheduled payment,
    # so this cannot double-count it. Without this the sidebar total and
    # compute_disposable both ignored it, overstating investable surplus by the
    # prepayment amount.
    if extra_mortgage_for_age(overrides, safe_int(overrides.get("YOUR_AGE", 25), 25)) > 0:
        today = safe_int(overrides.get("YOUR_AGE", 25), 25)
        annual += mortgage_schedule(overrides, [today])["by_age"][today]["extra"]

    return int(annual)


def compute_disposable(overrides: dict) -> int:
    """Income - taxes - expenses today (annual): what's left to save.

    The tax is the tax on the 401(k)/HSA amounts actually saved, as in the
    Taxes section and the simulation's first working year. See savings_budget.
    """
    return savings_budget(overrides)["disposable"]


# Pre-tax payroll savings: they lower this year's income tax (_working_tax_inputs).
PRETAX_KEYS = ("YOUR_401K_CONTRIBUTION", "YOUR_HSA_CONTRIBUTION", "PARTNER_401K_CONTRIBUTION")

COLLEGE_529_LABEL = "529 college savings"
AFTER_TAX_401K_LABEL = "After-tax 401(k) → Roth"


def college_saving_this_year(overrides: dict) -> float:
    """This year's 529 saving across the children, as the simulation has it
    (cfg.calculate_529_contribution at your current age): each child's college
    target spread evenly from birth until COLLEGE_START_AGE."""
    start = safe_int(overrides.get("COLLEGE_START_AGE", cfg.COLLEGE_START_AGE),
                     cfg.COLLEGE_START_AGE)
    if start <= 0:
        return 0.0
    return float(sum(cfg.college_target(kid) / start for kid in cfg.children_in(overrides)
                     if 0 <= -cfg._child(kid, "years_until_birth") < start))


def after_tax_401k_this_year(overrides: dict, deferral: float) -> float:
    """This year's after-tax 401(k) -> Roth (mega backdoor), sized as the
    simulation sizes it (account_simulation.working_year_cashflow):
    YOUR_AFTER_TAX_401K_PCT of base pay, up to the total 401(k) limit left
    after your own ``deferral`` and the match it earns."""
    pct = as_fraction(overrides.get("YOUR_AFTER_TAX_401K_PCT", 0.0), 0.0)
    if pct <= 0:
        return 0.0
    age = safe_int(overrides.get("YOUR_AGE", 30), 30)
    year = cfg.CURRENT_YEAR
    base = max(0, safe_int(overrides.get("YOUR_BASE_SALARY", 0), 0))
    wages = base + sum(max(0, safe_int(overrides.get(k, 0), 0))
                       for k in ("YOUR_BONUS_AMOUNT", "YOUR_RSU_AMOUNT"))
    deferral = max(0.0, min(float(deferral), cfg.get_401k_limit(age, year), wages))
    match = min(deferral, base * as_fraction(overrides.get("YOUR_401K_MATCH_PCT", 0.0), 0.0))
    room = max(0.0, cfg.get_401k_total_limit(age, year) - deferral - match)
    return float(min(pct * base, room))


def savings_budget(overrides: dict, custom_pcts: Dict[str, float] = None) -> Dict[str, object]:
    """This year's income, tax, expenses and what's left to save.

    The tax is the tax on what's actually put into the 401(k)s and HSA, so it
    is the Taxes section's figure and the simulation's (cfg.working_year_taxes).
    Those amounts can depend on what's left: Auto-allocate fills the 401(k)s
    and HSA from it and Custom % takes shares of it, and pre-tax saving lowers
    the tax, which leaves more. So this solves
        left = income - tax(amounts(left)) - expenses
    in whole dollars, starting from the tax with no pre-tax saving. Each pass
    can only raise ``left`` (more pre-tax saving, less tax), by less than the
    change before it, so it settles in a few passes and gives the same answer
    on every rerun (it never feeds back across reruns).

    Amounts by SAVINGS_MODE: Auto-allocate -> auto_allocate_savings(left);
    Custom % with ``custom_pcts`` -> custom_pct_amounts(custom_pcts, left);
    otherwise the amounts already in ``overrides`` (they don't depend on left).

    ``set_aside``: this year's 529 saving and after-tax 401(k). The simulation
    pays them from take-home ahead of its brokerage sweep, so Auto-allocate's
    brokerage share is what's left after them -- never more than the
    simulation's own sweep (a larger brokerage figure would act as a floor
    the simulation has to fund by selling investments).

    Returns {"income", "taxes" (a compute_taxes dict), "expenses",
    "disposable" (int), "amounts", "set_aside" ({label: dollars})}.
    ``amounts`` are this year's contributions as the simulation makes them:
    in the two auto modes the brokerage keys are its sweep of everything left
    (not a floor to store -- see sec_savings._render_auto).
    """
    income = compute_total_income(overrides)
    expenses = compute_expenses_today(overrides)
    college = college_saving_this_year(overrides)
    mode = str(overrides.get("SAVINGS_MODE", AUTO_ALLOCATE_MODE))
    if mode == AUTO_ALLOCATE_MODE:
        def amounts_for(left: int) -> Dict[str, int]:
            first = auto_allocate_savings(left, overrides)
            extra = college + after_tax_401k_this_year(
                overrides, first["YOUR_401K_CONTRIBUTION"])
            # set_aside only trims the brokerage share; the 401(k)/HSA/IRA
            # amounts (and so the tax) are the same as in ``first``.
            return auto_allocate_savings(left, overrides, set_aside=extra)
    elif mode == CUSTOM_PCT_MODE and custom_pcts is not None:
        def amounts_for(left: int) -> Dict[str, int]:
            return custom_pct_amounts(custom_pcts, left, overrides)
    else:
        fixed = {k: max(0, safe_int(overrides.get(k, 0), 0)) for k in PRETAX_KEYS}

        def amounts_for(left: int) -> Dict[str, int]:
            return fixed

    def solve(amounts: Dict[str, int]):
        taxes = compute_taxes({**overrides, **{k: amounts.get(k, 0) for k in PRETAX_KEYS}})
        return taxes, int(max(0.0, income - taxes["total"] - expenses))

    amounts: Dict[str, int] = {}
    taxes, left = solve(amounts)
    for _ in range(200):
        amounts = amounts_for(left)
        taxes, new_left = solve(amounts)
        if new_left == left:
            break
        left = new_left
    deferral = amounts.get("YOUR_401K_CONTRIBUTION", overrides.get("YOUR_401K_CONTRIBUTION", 0))
    set_aside = {COLLEGE_529_LABEL: college,
                 AFTER_TAX_401K_LABEL: after_tax_401k_this_year(overrides, safe_int(deferral, 0))}
    set_aside = {k: v for k, v in set_aside.items() if v > 0}
    if mode == KEEP_AMOUNTS_MODE:
        # Your amounts stay; the simulation invests the rest in the brokerage.
        kept = {k: max(0, safe_int(overrides.get(k, 0), 0)) for k in CONTRIBUTION_KEYS
                if "BROKERAGE" not in k}
        if safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0:
            kept["PARTNER_ROTH_CONTRIBUTION"] = int(min(
                kept["PARTNER_ROTH_CONTRIBUTION"], partner_roth_allowed(overrides, kept)))
        else:
            kept["PARTNER_401K_CONTRIBUTION"] = kept["PARTNER_ROTH_CONTRIBUTION"] = 0
        sweep = int(max(0.0, left - sum(kept.values()) - sum(set_aside.values())))
        amounts = {**kept, **split_brokerage(sweep, overrides, kept, sum(set_aside.values()))}
    return {"income": income, "taxes": taxes, "expenses": expenses,
            "disposable": left, "amounts": amounts, "set_aside": set_aside}


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
CUSTOM_PCT_MODE = "Custom %"
MANUAL_MODE = "Manual amounts"
SAVINGS_MODES = [AUTO_ALLOCATE_MODE, KEEP_AMOUNTS_MODE, CUSTOM_PCT_MODE, MANUAL_MODE]

# Contribution keys in the Savings section's order, and the Savings widgets
# that hold them a rerun before user_overrides does.
CONTRIBUTION_KEYS = (
    "YOUR_401K_CONTRIBUTION", "PARTNER_401K_CONTRIBUTION", "YOUR_HSA_CONTRIBUTION",
    "YOUR_BACKDOOR_ROTH", "PARTNER_ROTH_CONTRIBUTION",
    "YOUR_BROKERAGE_CONTRIBUTION", "PARTNER_BROKERAGE_CONTRIBUTION",
)
_MANUAL_WIDGETS = {
    "YOUR_401K_CONTRIBUTION": "sv_manual_your_401k",
    "YOUR_HSA_CONTRIBUTION": "sv_manual_your_hsa",
    "PARTNER_401K_CONTRIBUTION": "sv_manual_partner_401k",
    "YOUR_BACKDOOR_ROTH": "sv_manual_your_roth",
    "PARTNER_ROTH_CONTRIBUTION": "sv_manual_partner_roth",
}


def pct_widget_key(key: str) -> str:
    """The Custom % slider for a contribution key."""
    return f"sv_pct_{key.lower()}"


def custom_pct_defaults(overrides: dict) -> Dict[str, int]:
    """Starting Custom % split (sums to 100), over the accounts shown."""
    if safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0:
        return {"YOUR_401K_CONTRIBUTION": 30, "PARTNER_401K_CONTRIBUTION": 20,
                "YOUR_HSA_CONTRIBUTION": 8, "YOUR_BACKDOOR_ROTH": 7,
                "PARTNER_ROTH_CONTRIBUTION": 5, "YOUR_BROKERAGE_CONTRIBUTION": 15,
                "PARTNER_BROKERAGE_CONTRIBUTION": 15}
    return {"YOUR_401K_CONTRIBUTION": 50, "YOUR_HSA_CONTRIBUTION": 8,
            "YOUR_BACKDOOR_ROTH": 12, "YOUR_BROKERAGE_CONTRIBUTION": 30}


def custom_pct_amounts(pcts: Dict[str, float], disposable: int, overrides: dict) -> Dict[str, int]:
    """Custom %: each account gets pct x disposable, capped at its IRS limit."""
    your_age = safe_int(overrides.get("YOUR_AGE", 30), 30)
    partner_age = safe_int(overrides.get("PARTNER_AGE", 0), 0)
    caps = {
        "YOUR_401K_CONTRIBUTION": get_limit("401k", your_age),
        "PARTNER_401K_CONTRIBUTION": get_limit("401k", partner_age) if partner_age > 0 else 0,
        "YOUR_HSA_CONTRIBUTION": get_limit("hsa", your_age, family=True),
        "YOUR_BACKDOOR_ROTH": get_limit("ira", your_age),
        "PARTNER_ROTH_CONTRIBUTION": get_limit("ira", partner_age) if partner_age > 0 else 0,
    }
    return {key: min(int(disposable * float(pct) / 100), caps.get(key, 10_000_000))
            for key, pct in pcts.items()}


def sidebar_savings_budget(state) -> Dict[str, object]:
    """savings_budget for the sidebar as it stands this rerun.

    ``state`` is st.session_state: user_overrides plus the Savings widgets
    (mode, Custom % sliders, manual 401(k)/HSA amounts), which hold this
    rerun's values before the Savings section writes them to user_overrides.
    The Taxes section and the Savings section both call this, so they show
    one tax figure even when the Taxes section draws first.
    """
    overrides = dict(state.get("user_overrides", {}) or {})
    mode = state.get("sv_mode")
    if mode in SAVINGS_MODES:
        overrides["SAVINGS_MODE"] = mode
    mode = str(overrides.get("SAVINGS_MODE", AUTO_ALLOCATE_MODE))
    pcts = None
    if mode == CUSTOM_PCT_MODE:
        pcts = {k: state.get(pct_widget_key(k), d)
                for k, d in custom_pct_defaults(overrides).items()}
    elif mode != AUTO_ALLOCATE_MODE:
        for key, widget in _MANUAL_WIDGETS.items():
            if widget in state:
                overrides[key] = state[widget]
    # Percent widgets stored as fractions.
    for key, widget in (("YOUR_AFTER_TAX_401K_PCT", "sv_after_tax_401k"),
                        ("YOUR_401K_MATCH_PCT", "sv_match_pct")):
        if state.get(widget) is not None:
            overrides[key] = safe_float(state[widget], 0.0) / 100.0
    return savings_budget(overrides, custom_pcts=pcts)


def partner_roth_allowed(overrides: dict, amounts: dict) -> float:
    """Your partner's direct Roth IRA this year, as the simulation allows it
    (account_simulation.working_year_cashflow): the IRA limit, reduced by the
    Roth income phase-out of the return their income is on (MAGI after the
    401(k)/HSA ``amounts``), and no more than the earned income behind it."""
    partner_age = safe_int(overrides.get("PARTNER_AGE", 0), 0)
    kw = _working_tax_inputs({**overrides, **amounts})
    t = cfg.working_year_taxes(**kw)
    two = t["two_returns"]
    magi = t["partner"]["agi"] + (0.0 if two else t["you"]["agi"])
    joint = (not two) and kw["status"] == cfg.normalize_filing_status("MFJ")
    your_roth = float(amounts.get("YOUR_BACKDOOR_ROTH", 0) or 0)
    earned = kw["partner_wages"] + (max(0.0, kw["your_wages"] - your_roth) if joint else 0.0)
    allowed = cfg.roth_ira_allowed(get_limit("ira", partner_age), magi,
                                   cfg.return_status("partner", kw["status"], kw["partner"]))
    return max(0.0, min(allowed, earned))


def split_brokerage(remaining: int, overrides: dict, allocated: dict,
                    set_aside: float = 0) -> Dict[str, int]:
    """Split ``remaining`` between your and your partner's brokerage.

    The couple SPLITS EXPENSES EVENLY, so each person covers HALF of household
    expenses from their own take-home and banks their OWN remainder in their
    OWN brokerage -> the residual lands MOSTLY in the higher earner's account
    (entirely, if the other's take-home only covers their half), NOT 50/50.
    The same split as the simulation's sweep
    (account_simulation.simulate_accumulation_year): each person's take-home
    after the 401(k)/HSA in ``allocated`` and their own Roth (and, for you,
    the 529 and after-tax 401(k) in ``set_aside``). Falls back to an even
    split only when no per-person income breakdown is available.
    """
    has_partner = safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0
    out = {"YOUR_BROKERAGE_CONTRIBUTION": 0, "PARTNER_BROKERAGE_CONTRIBUTION": 0}
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
            pay = cfg.working_year_taxes(**_working_tax_inputs({**overrides, **allocated}))
            your_cap = max(0.0, pay["you"]["take_home"]
                           - float(allocated.get("YOUR_BACKDOOR_ROTH", 0)) - float(set_aside))
            partner_cap = max(0.0, pay["partner"]["take_home"]
                              - float(allocated.get("PARTNER_ROTH_CONTRIBUTION", 0)))
            your_left = max(0.0, your_cap - your_exp)
            partner_left = max(0.0, partner_cap - partner_exp)
            leftover_total = your_left + partner_left
            if your_gross + partner_gross <= 0:
                your_amt = remaining // 2            # no breakdown -> keep even split
            elif leftover_total > 0:
                your_amt = int(round(remaining * your_left / leftover_total))
            else:
                your_amt = remaining                 # neither covers their half -> primary banks it
            out["YOUR_BROKERAGE_CONTRIBUTION"] = your_amt
            out["PARTNER_BROKERAGE_CONTRIBUTION"] = remaining - your_amt
        else:
            out["YOUR_BROKERAGE_CONTRIBUTION"] = remaining
    return out


def auto_allocate_savings(disposable: int, overrides: dict, set_aside: float = 0) -> Dict[str, int]:
    """Default allocation rule: max tax-advantaged first, residual to brokerage.

    ``set_aside`` is paid from what's left before the brokerage gets the rest:
    this year's 529 saving and after-tax 401(k), which the simulation also
    funds ahead of its brokerage sweep (see savings_budget).

    Order:
      1. Your 401(k) → IRS limit
      2. Partner 401(k) → IRS limit (if partner exists)
      3. Your HSA family → IRS limit (only if HSA-eligible — assume yes if user has any HSA balance)
      4. Your IRA / backdoor Roth → IRS limit
      5. Partner IRA → IRS limit, less any Roth income phase-out
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

    # 5. IRA (partner): a direct Roth, so only what the simulation allows at
    #    this income (the rest goes to the brokerage, as it does there).
    if has_partner and remaining > 0:
        cap = int(partner_roth_allowed(overrides, allocated))
        fill = min(cap, remaining)
        allocated["PARTNER_ROTH_CONTRIBUTION"] = fill
        remaining -= fill

    remaining = max(0, remaining - int(round(set_aside)))

    # 6. Brokerage (residual), split between you as the simulation splits it.
    if remaining > 0:
        allocated.update(split_brokerage(remaining, overrides, allocated, set_aside))

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
    inverting the payment for a rate. When the loan's rate was entered
    (``MORTGAGE_RATE_FOR_PAYOFF``) it is used instead, with the engine's level
    payment for the balance and term. Returns ``{balance, pi_payment, rate,
    years}``; a zero balance yields zeros so callers can skip the amortization.
    """
    balance = max(0.0, safe_float(overrides.get("MORTGAGE_BALANCE", 0), 0.0))
    years = safe_int(overrides.get("MORTGAGE_YEARS_REMAINING", 0), 0)
    monthly = max(0.0, safe_float(overrides.get("MORTGAGE_MONTHLY", 0), 0.0))
    if balance <= 0 or years <= 0 or monthly <= 0:
        return {"balance": balance, "pi_payment": 0.0, "rate": 0.0, "years": years}
    if overrides.get("MORTGAGE_RATE_FOR_PAYOFF") is not None:
        rate = max(0.0, _payoff_rate(overrides))
        return {"balance": balance, "pi_payment": mortgage_payment(balance, rate, years),
                "rate": rate, "years": years}
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


def housing_timeline(overrides: dict) -> list:
    """The plan's housing events (buy / sell and buy / sell and rent), resolved
    exactly as the engine resolves them (``cfg.housing_events``, legacy house
    move included) from ``overrides`` over the config defaults. The escrow %
    follows the one input config_builder maps onto HOME_CARRYING_COST_PCT."""
    from retirement_sim import config as cfg
    src = dict(overrides or {})
    if src.get("HOME_CARRYING_COST_PCT") is None and src.get("NEW_HOME_ESCROW_PCT") is not None:
        src["HOME_CARRYING_COST_PCT"] = src["NEW_HOME_ESCROW_PCT"]
    return cfg.housing_events(src)


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
    """Per-age housing state, honouring extra principal and the housing timeline.

    Returns ``{"by_age": {age: {"balance", "scheduled", "extra", "housing",
    "owns"}}, "payoff_age": int|None, "owns": bool}`` where

      * ``scheduled`` is the all-in annual payment (0 once the loan is gone),
        or the year's rent while renting,
      * ``extra``     is the extra principal actually paid that year (never more
                      than the balance left),
      * ``housing``   is scheduled + extra, i.e. the real cash going to housing;
                      for an owner with no loan outstanding (paid off, or never
                      had one) it is the property tax + insurance carrying cost
                      instead -- the engine's ``home_carrying_cost_annual`` rule,
      * ``owns``      is whether a home is owned that year.

    ``balance`` is the principal at the START of the year. Events apply at the
    start of their year, like the engine (``AccountPortfolio.apply_housing_events``):
    a renter pays rent until a purchase and the owner's costs after it; a sale
    to rent switches to the new rent. The top-level ``owns`` is True if a home
    is owned in any year.
    """
    ages = [safe_int(a, 0) for a in ages]
    your_age = safe_int(overrides.get("YOUR_AGE", 25), 25)
    rate = max(0.0, _payoff_rate(overrides))
    r = rate / 12.0

    bal = safe_float(overrides.get("MORTGAGE_BALANCE", 0) or 0, 0.0)
    years = safe_int(overrides.get("MORTGAGE_YEARS_REMAINING", 0), 0)
    monthly = safe_float(overrides.get("MORTGAGE_MONTHLY", 0) or 0, 0.0)
    home_value = safe_float(overrides.get("HOME_VALUE", 0) or 0, 0.0)
    if bal > 0 and years > 0:
        pi = mortgage_payment(bal, rate, years)
    elif monthly > 0 and years > 0:
        # Loan given as payment + term with no balance: recover the principal so
        # there is something to amortize (otherwise this reports no loan at all).
        pi = _pi_from_all_in(monthly, home_value, overrides)
        bal = _balance_from_payment(pi, rate, years)
    else:
        pi = 0.0
    scheduled_annual = monthly * 12.0
    rent_annual = safe_float(overrides.get("SPEND_RENT_MONTHLY", 0) or 0, 0.0) * 12.0
    owns = bal > 0 or monthly > 0 or home_value > 0      # the engine's is_renter rule
    events = housing_timeline(overrides)
    purchases = [e["age"] for e in events if e["action"] != "sell_rent"]
    # Post-payoff carrying cost (mirrors cfg.home_carrying_cost_annual; the pct
    # resolves exactly as config_builder translates it onto the engine).
    carry_on = bool(overrides.get("MODEL_HOME_CARRYING_COST_AFTER_PAYOFF", True))
    carry_pct = safe_float(overrides.get(
        "HOME_CARRYING_COST_PCT", overrides.get("NEW_HOME_ESCROW_PCT", 0.0135)), 0.0135)

    by_age, payoff_age, ever_owns = {}, None, owns
    for age in range(min(ages or [your_age]), max(ages or [your_age]) + 1):
        for e in events:
            if e["age"] != age:
                continue
            if e["action"] == "sell_rent":
                if owns and bal > 0 and not any(a > age for a in purchases):
                    payoff_age = age                         # repaid from the sale
                owns, bal, pi, scheduled_annual, home_value = False, 0.0, 0.0, 0.0, 0.0
                rent_annual = e["rent"] * 12.0
                continue
            rate = e["rate"]                                 # the new loan's own rate
            r = rate / 12.0
            bal = e["loan"]
            if bal > 0:
                pi = mortgage_payment(bal, rate, e["years"])
            else:
                # Specified by payment + term instead of balance: strip escrow
                # off the all-in monthly (same convention as
                # current_mortgage_terms) and invert the annuity for principal.
                pi = _pi_from_all_in(e["monthly"], e["price"], overrides)
                bal = _balance_from_payment(pi, rate, e["years"])
            scheduled_annual = e["monthly"] * 12.0
            home_value = e["price"]
            owns = ever_owns = True
            payoff_age = None                                # a new loan to retire

        start_balance = bal
        if owns and bal > 0 and age >= your_age:
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
                       "extra": extra, "housing": sched + extra + carry, "owns": owns}

    # A renter never "pays off"; an owner with no loan (and no purchase ahead)
    # is already paid off.
    if payoff_age is None and owns and not events and safe_float(
            overrides.get("MORTGAGE_BALANCE", 0) or 0, 0.0) <= 0:
        payoff_age = your_age
    return {"by_age": by_age, "payoff_age": payoff_age, "owns": ever_owns}
