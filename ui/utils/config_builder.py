"""Convert UI user_overrides dict -> retirement_sim.config overrides."""
from __future__ import annotations

from typing import Dict, Any


# Keys that live only in UI state and need translation / dropping.
# This is the single source of truth for "legitimately UI-only" override keys:
# each is consumed/translated inside build_config_overrides below and never
# maps onto a retirement_sim.config attribute. sim_runner.UI_ONLY_KEYS is seeded
# from this set so its override-wiring guard does not flag them as inert.
_UI_ONLY_KEYS = {
    "HOUSEHOLD_INCOME_QUICK", "TOTAL_SAVINGS_QUICK", "TARGET_RETIREMENT_AGE",
    # House-move financing inputs. These DERIVE NEW_MORTGAGE_BALANCE and
    # NEW_MORTGAGE_MONTHLY (the real config keys the engine reads) in
    # components/sec_big_purchases.py via utils.derived.new_home_financing, so
    # they must not be pushed onto cfg themselves. (NEW_MORTGAGE_RATE is a real
    # cfg key: the engine amortizes the new loan at it.)
    "NEW_HOME_DOWN_PCT", "NEW_HOME_ESCROW_PCT",
}

# Derived on every run: birth years from age (sim_runner._recompute_derived),
# the current year from the clock. Older saved profiles may still carry them;
# they're ignored so they can't contradict age or the calendar.
_DERIVED_KEYS = {"YOUR_BIRTH_YEAR", "PARTNER_BIRTH_YEAR", "CURRENT_YEAR"}

# Retired engine knobs older saved profiles may still carry. Dropped quietly:
#   PARTNER_ESTIMATED_TAX_RATE  flat partner tax rate -> real tax rules
#                               (cfg.working_year_taxes)
#   PARTNER_401K_MATCH          never read -> PARTNER_401K_MATCH_PCT
_RETIRED_KEYS = {"PARTNER_ESTIMATED_TAX_RATE", "PARTNER_401K_MATCH"}

# The take-home the Income section used to write into every comp-table row
# (70% of total comp). A row carrying exactly that value is treated as not set,
# so the engine computes the real take-home; any other after_tax is an explicit
# override and is kept.
LEGACY_AUTO_AFTER_TAX_RATE = 0.70

# The Roth-conversion target the UI used to store for everyone (the top of the
# 12% bracket for a JOINT return). For other filing statuses it means "the
# default", which now follows the filing status.
LEGACY_ROTH_TARGET_MFJ = 94_300

# Quick-income assumptions (used when the user hasn't entered a detailed
# income breakdown and only supplies a single household income number).
QUICK_INCOME_PRIMARY_SHARE = 0.55  # primary/partner household income split (55/45)
QUICK_INCOME_SYNTHETIC_GROWTH = 0.02  # annual real growth rate for the synthesized comp table
QUICK_INCOME_SAVINGS_RATE = 0.07  # Manual-mode "saved" per comp row, as a fraction of gross comp

# Default proportions for allocating a single "total savings" number across
# typical account types (roughly mirrors median US household allocation).
_DEFAULT_SAVINGS_ALLOCATION = {
    "YOUR_401K":              0.30,
    "YOUR_ROTH_IRA":          0.10,
    "YOUR_TRADITIONAL_IRA":   0.00,
    "YOUR_HSA":               0.02,
    "YOUR_BROKERAGE":         0.08,
    "YOUR_CASH":              0.12,
    "PARTNER_401K":           0.20,
    "PARTNER_ROTH_IRA":       0.07,
    "PARTNER_BROKERAGE":      0.03,
    "PARTNER_CASH":           0.08,
}


def build_config_overrides(user_overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Transform UI state into a dict of retirement_sim.config attribute overrides.

    Args:
        user_overrides: The dict held in st.session_state.user_overrides.

    Returns:
        A dict where every key is a valid attribute on retirement_sim.config.
    """
    out: Dict[str, Any] = {}

    # 1. Copy direct config keys.
    #    STATE_CHOICE and YOUR_MARGINAL_TAX_RATE are real config attributes (not
    #    UI-only), so they flow straight through here to reach cfg and drive the
    #    engine's state-tax selection (CA / No state tax / Other flat rate).
    for k, v in user_overrides.items():
        if k in _UI_ONLY_KEYS or k in _DERIVED_KEYS or k in _RETIRED_KEYS:
            continue
        out[k] = v

    # 1b. Legacy values that meant "the default" (see the constants above).
    comp = out.get("YOUR_COMPENSATION_BY_AGE")
    if isinstance(comp, dict) and comp:
        out["YOUR_COMPENSATION_BY_AGE"] = _strip_auto_after_tax(comp)
    status = str(out.get("FILING_STATUS", "Married filing jointly")).strip().lower()
    if (out.get("ROTH_CONVERSION_TARGET_BRACKET") == LEGACY_ROTH_TARGET_MFJ
            and not (status.startswith("m") or status == "mfj")):
        out["ROTH_CONVERSION_TARGET_BRACKET"] = None

    # 2. Translate HOUSEHOLD_INCOME_QUICK -> PARTNER_SALARY + default comp table
    #    (only if the user hasn't explicitly set a compensation table)
    income = user_overrides.get("HOUSEHOLD_INCOME_QUICK")
    if income is not None:
        income = max(0, income)
        has_comp_table = "YOUR_COMPENSATION_BY_AGE" in user_overrides and user_overrides["YOUR_COMPENSATION_BY_AGE"]
        has_partner_salary = "PARTNER_SALARY" in user_overrides
        # Split 50/50 if neither has been manually edited
        # The quick figure is the WHOLE household income, so the split rows
        # stand in for every income line: zero the separate other/bonus/RSU
        # lines they replace, or the engine would add them a second time.
        if not has_comp_table:
            primary = int(income * QUICK_INCOME_PRIMARY_SHARE)  # slight skew to primary
            out["YOUR_COMPENSATION_BY_AGE"] = _synthesize_comp_table(
                primary_salary=primary,
                start_age=int(user_overrides.get("YOUR_AGE", 25)),
                n_rows=15,
                growth=QUICK_INCOME_SYNTHETIC_GROWTH,
            )
            out["YOUR_OTHER_INCOME"] = 0
        if not has_partner_salary:
            out["PARTNER_SALARY"] = int(income - int(income * QUICK_INCOME_PRIMARY_SHARE))
            for k in ("PARTNER_BONUS_AMOUNT", "PARTNER_RSU_AMOUNT", "PARTNER_OTHER_INCOME"):
                out[k] = 0

    # 3. Translate TOTAL_SAVINGS_QUICK -> allocation across accounts
    #    (only if none of the individual account keys were set by the user)
    total_savings = user_overrides.get("TOTAL_SAVINGS_QUICK")
    if total_savings is not None:
        total_savings = max(0, total_savings)
        user_touched_accounts = any(k in user_overrides for k in _DEFAULT_SAVINGS_ALLOCATION)
        if not user_touched_accounts:
            for key, pct in _DEFAULT_SAVINGS_ALLOCATION.items():
                out[key] = int(total_savings * pct)

    # 4. NEW_HOME_ESCROW_PCT (UI-only) also drives the engine's post-payoff
    #    property tax + insurance rate, so one input sets both (unless the user
    #    set HOME_CARRYING_COST_PCT directly).
    escrow_pct = user_overrides.get("NEW_HOME_ESCROW_PCT")
    if escrow_pct is not None and "HOME_CARRYING_COST_PCT" not in user_overrides:
        out["HOME_CARRYING_COST_PCT"] = escrow_pct

    return out


def _synthesize_comp_table(primary_salary: int, start_age: int, n_rows: int, growth: float) -> dict:
    """Build a YOUR_COMPENSATION_BY_AGE dict from a single starting salary."""
    table = {}
    for offset in range(n_rows):
        age = start_age + offset
        base = int(primary_salary * ((1 + growth) ** offset))
        total = base
        table[age] = {
            "base": base,
            "bonus": 0,
            "rsu_gross": 0,
            "total_comp": total,
            "saved": int(total * QUICK_INCOME_SAVINGS_RATE),
        }
    return table


def _strip_auto_after_tax(comp: dict) -> dict:
    """Copy of a comp table without the legacy auto-written 70% take-home."""
    out = {}
    for age, row in comp.items():
        if isinstance(row, dict) and "after_tax" in row:
            try:
                total = row.get("total_comp", row.get("base", 0))
                auto = int(int(total) * LEGACY_AUTO_AFTER_TAX_RATE) == int(row["after_tax"])
            except (TypeError, ValueError):
                auto = False
            if auto:
                row = {k: v for k, v in row.items() if k != "after_tax"}
        out[age] = row
    return out
