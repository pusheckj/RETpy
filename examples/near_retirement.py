"""
Example Profile: Near Retirement (Ages 55 and 53)

Jordan and Taylor are a dual-income empty-nester couple 5 years from their
target retirement age. Typical scenario: high-income late-career, low
remaining mortgage, two grown kids already launched.

- Jordan: $220k base, $35k bonus (legal)
- Taylor: $130k (teacher -- note: pension not modeled, see limitations)
- Two grown kids (no child expenses)
- Home: $850k value, $120k mortgage (7 years left)
- Target retirement: age 60

Run with:
    python -m examples.near_retirement

LIMITATIONS
-----------
- Taylor's teacher pension is NOT modeled by the simulator. In reality it
  would provide meaningful guaranteed retirement income and materially change
  the probability-of-success numbers. Treat results as a conservative lower
  bound until the pension is added as a custom income stream.
- State tax brackets default to California in account_simulation.py. Replace
  them if the household lives elsewhere.

This file pulls shared infrastructure (tax tables, contribution limits, RMD
table, IRMAA brackets, historical returns, and helper functions) from
retirement_sim.config via a direct file load, then overrides the
household-specific values. The direct load bypasses the package __init__ so
this example remains import-safe even if upstream re-exports drift.
"""

import importlib.util as _importlib_util
import os as _os

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_CONFIG_PATH = _os.path.normpath(_os.path.join(_HERE, "..", "retirement_sim", "config.py"))
_spec = _importlib_util.spec_from_file_location("_retirement_sim_config", _CONFIG_PATH)
_cfg = _importlib_util.module_from_spec(_spec)
_spec.loader.exec_module(_cfg)

# Re-export every public symbol from the reference config. Household-specific
# values below override the relevant subset.
for _k in dir(_cfg):
    if not _k.startswith("_"):
        globals()[_k] = getattr(_cfg, _k)
del _k

# === PERSONAL INFORMATION ===
YOUR_AGE = 55           # Jordan
PARTNER_AGE = 53        # Taylor
CURRENT_YEAR = 2026
YOUR_BIRTH_YEAR = 1971
PARTNER_BIRTH_YEAR = 1973
PLAN_UNTIL_AGE = 95
YEARS_UNTIL_WEDDING = 0    # long-married

# === CURRENT ASSETS -- mature balances after 30+ years of saving ===
# Jordan
YOUR_401K = 1_200_000
YOUR_ROTH_IRA = 300_000
YOUR_TRADITIONAL_IRA = 150_000
YOUR_HSA = 80_000
YOUR_BROKERAGE = 600_000
YOUR_CASH = 75_000

# Taylor (no Traditional IRA, no HSA)
PARTNER_401K = 450_000
PARTNER_ROTH_IRA = 180_000
PARTNER_TRADITIONAL_IRA = 0
PARTNER_HSA = 0
PARTNER_BROKERAGE = 100_000
PARTNER_CASH = 60_000

# Primary residence -- mostly paid down
HOME_VALUE = 850_000
MORTGAGE_BALANCE = 120_000
HOME_EQUITY = HOME_VALUE - MORTGAGE_BALANCE
HOME_EQUITY_ACCESSIBLE_PCT = 0.85

# === PRIMARY USER INCOME -- ages 55-60 (Jordan retires at 60) ===
# Legal / consulting career. No RSUs.
YOUR_COMPENSATION_BY_AGE = {
    55: {"base": 220_000, "bonus": 35_000, "rsu_gross": 0, "total_comp": 255_000, "after_tax": 175_000, "saved": 55_000},
    56: {"base": 226_000, "bonus": 36_000, "rsu_gross": 0, "total_comp": 262_000, "after_tax": 180_000, "saved": 58_000},
    57: {"base": 233_000, "bonus": 37_000, "rsu_gross": 0, "total_comp": 270_000, "after_tax": 185_000, "saved": 60_000},
    58: {"base": 240_000, "bonus": 38_000, "rsu_gross": 0, "total_comp": 278_000, "after_tax": 190_000, "saved": 62_000},
    59: {"base": 247_000, "bonus": 39_000, "rsu_gross": 0, "total_comp": 286_000, "after_tax": 196_000, "saved": 64_000},
    60: {"base": 255_000, "bonus": 40_000, "rsu_gross": 0, "total_comp": 295_000, "after_tax": 202_000, "saved": 66_000},
}

# After retirement: zero growth, no RSUs.
YOUR_SALARY_GROWTH_RATE = 0.00
YOUR_BONUS_PCT = 0.16
YOUR_RSU_PCT = 0.00

# Contribution rates (age 50+ catch-up; age 55+ HSA catch-up)
YOUR_401K_CONTRIBUTION = 30_500          # $23k + $7.5k catch-up
YOUR_401K_MATCH_PCT = 0.05
YOUR_HSA_CONTRIBUTION = 8_550            # family + $1k catch-up
YOUR_HSA_MATCH = 0
YOUR_HSA_TOTAL = YOUR_HSA_CONTRIBUTION + YOUR_HSA_MATCH
YOUR_BACKDOOR_ROTH = 8_000
YOUR_ESPP_PCT = 0.00                     # no ESPP at a law firm
YOUR_ESPP_DISCOUNT = 0.00
YOUR_MARGINAL_TAX_RATE = 0.32

def calculate_your_total_savings(age: int) -> float:
    """Jordan's TOTAL annual savings. Zero once retired."""
    if age in YOUR_COMPENSATION_BY_AGE:
        comp = YOUR_COMPENSATION_BY_AGE[age]
        return (comp['saved'] + YOUR_401K_CONTRIBUTION
                + comp['base'] * YOUR_401K_MATCH_PCT + YOUR_HSA_TOTAL)
    return 0.0

# === PARTNER INCOME (Taylor -- teacher; PENSION NOT MODELED) ===
PARTNER_SALARY = 130_000
PARTNER_SALARY_GROWTH_RATE = 0.02        # step/lane increases
PARTNER_401K_CONTRIBUTION = 30_500       # 403(b) + catch-up
PARTNER_401K_MATCH = 0
PARTNER_ROTH_CONTRIBUTION = 8_000        # IRA max + catch-up (backdoor if needed)
PARTNER_MONTHLY_SPENDING = 3_000
PARTNER_ANNUAL_SPENDING = PARTNER_MONTHLY_SPENDING * 12
PARTNER_ESTIMATED_TAX_RATE = 0.28

def calculate_partner_total_savings(salary: float, years_from_now: int, married: bool = False) -> float:
    """Taylor's total savings. Drops to zero once she retires at age 58."""
    if PARTNER_AGE + years_from_now >= 58:
        return 0.0
    savings_401k = PARTNER_401K_CONTRIBUTION
    taxable_income = salary - PARTNER_401K_CONTRIBUTION
    after_tax = taxable_income * (1 - PARTNER_ESTIMATED_TAX_RATE)
    roth = 0 if married else PARTNER_ROTH_CONTRIBUTION
    to_brokerage = max(0, after_tax - roth - PARTNER_ANNUAL_SPENDING)
    return savings_401k + roth + to_brokerage

# === EXPENSE MODELING ===
MORTGAGE_MONTHLY = 1_750                 # $120k @ ~6% over 7 years
MORTGAGE_ANNUAL = MORTGAGE_MONTHLY * 12
MORTGAGE_YEARS_REMAINING = 7             # paid off at Jordan age 62

UTILITIES_MONTHLY = 350                  # larger, established home
UTILITIES_ANNUAL = UTILITIES_MONTHLY * 12

YOUR_OTHER_MONTHLY = 3_500
YOUR_OTHER_ANNUAL = YOUR_OTHER_MONTHLY * 12
PARTNER_OTHER_MONTHLY = 3_000

CURRENT_ANNUAL_EXPENSES = (
    MORTGAGE_ANNUAL + UTILITIES_ANNUAL + YOUR_OTHER_ANNUAL + PARTNER_OTHER_MONTHLY * 12
)

# Children already grown and launched. Large-negative YEARS_UNTIL_FIRST_CHILD
# pushes computed "child age" well past CHILD_LEAVES_HOME_AGE so any
# downstream calc correctly yields zero.
YEARS_UNTIL_FIRST_CHILD = -25
YEARS_BETWEEN_CHILDREN = 3
FIRST_CHILD_MONTHLY_COST = 0
FIRST_CHILD_ANNUAL_COST = 0
BOTH_CHILDREN_MONTHLY_COST = 0
BOTH_CHILDREN_ANNUAL_COST = 0
CHILD_LEAVES_HOME_AGE = 18

# 529 -- not applicable
COLLEGE_FUNDING_PCT = 0.00
COLLEGE_ANNUAL_COST = 40_000
COLLEGE_YEARS = 4
COLLEGE_TARGET_PER_CHILD = 0
SAVINGS_529_PER_CHILD_ANNUAL = 0

def calculate_child_expenses(your_age: int) -> float:
    return 0.0

def calculate_529_contribution(your_age: int) -> float:
    return 0.0

def calculate_college_expenses(your_age: int) -> dict:
    return {'child1': 0, 'child2': 0, 'total': 0}

def has_mortgage(your_age: int) -> bool:
    return your_age < (YOUR_AGE + MORTGAGE_YEARS_REMAINING)

# === RETIREMENT EXPENSE MODEL ===
BASE_RETIREMENT_EXPENSES_NO_MORTGAGE = (
    YOUR_OTHER_ANNUAL + UTILITIES_ANNUAL + PARTNER_OTHER_MONTHLY * 12
)
HEALTHCARE_INCREASE_ANNUAL = 12_000
MEDICARE_AGE = 65
HEALTHCARE_INCREASE_PRE_MEDICARE = 15_000
EARLY_RETIREMENT_LEISURE_INCREASE = 12_000
LATE_RETIREMENT_LEISURE_DECREASE = 0.15
LATE_RETIREMENT_EXPENSE_REDUCTION = LATE_RETIREMENT_LEISURE_DECREASE
RETIREMENT_ANNUAL_EXPENSES = BASE_RETIREMENT_EXPENSES_NO_MORTGAGE

def calculate_annual_expenses(your_age: int, inflation_factor: float = 1.0) -> float:
    base = BASE_RETIREMENT_EXPENSES_NO_MORTGAGE
    if has_mortgage(your_age):
        base += MORTGAGE_ANNUAL
    return base * inflation_factor

# === DYNAMIC / RETURN-BASED SPENDING GUARDRAILS ===
DYNAMIC_SPENDING_ENABLED = True
SPENDING_GUARDRAILS = {
    'floor_trigger': 0.75, 'floor_reduction': 0.15,
    'ceiling_trigger': 1.30, 'ceiling_increase': 0.00,
}
DISCRETIONARY_EXPENSE_RATIO = 0.30

RETURN_BASED_SPENDING_ENABLED = True
RETURN_BASED_SPENDING_RULES = {
    'excellent_return_threshold': 0.15, 'excellent_spending_boost': 0.00,
    'good_return_threshold': 0.08,      'good_spending_boost': 0.00,
    'poor_return_threshold': 0.00,      'poor_spending_cut': 0.10,
    'bad_return_threshold': -0.10,      'bad_spending_cut': 0.20,
}

# Reuse the reference spending-adjustment helpers (they read the module-level
# constants above by name, so our overrides take effect).
calculate_spending_adjustment = _cfg.calculate_spending_adjustment
calculate_return_based_spending_adjustment = _cfg.calculate_return_based_spending_adjustment

# === INVESTMENT ASSUMPTIONS -- de-risked for near retirement ===
STOCK_ALLOCATION = 0.65
BOND_ALLOCATION = 0.35

RETURN_SCENARIOS = {
    'conservative': {'name': 'Conservative', 'description': 'Below-historical returns',
                     'stock_return': 0.07, 'bond_return': 0.02,
                     'stock_volatility': 0.19, 'bond_volatility': 0.08},
    'historical':   {'name': 'Historical Average', 'description': '1926-2024 data',
                     'stock_return': 0.087, 'bond_return': 0.031,
                     'stock_volatility': 0.20, 'bond_volatility': 0.087},
    'pessimistic':  {'name': 'Pessimistic', 'description': 'Stress test',
                     'stock_return': 0.05, 'bond_return': 0.01,
                     'stock_volatility': 0.22, 'bond_volatility': 0.10},
}
ACTIVE_RETURN_SCENARIO = 'conservative'

def get_return_parameters(scenario: str = None) -> dict:
    if scenario is None:
        scenario = ACTIVE_RETURN_SCENARIO
    if scenario not in RETURN_SCENARIOS:
        scenario = 'conservative'
    return RETURN_SCENARIOS[scenario]

EXPECTED_STOCK_RETURN = 0.07
EXPECTED_BOND_RETURN = 0.02
STOCK_VOLATILITY = 0.19
BOND_VOLATILITY = 0.08
STOCK_BOND_CORRELATION = -0.20
INVESTMENT_FEE_RATE = 0.0015
APPLY_VOLATILITY_DRAG = True
EXPECTED_INFLATION = 0.0275
INFLATION_VOLATILITY = 0.015
INFLATION_RATES = {'general': 0.0275, 'healthcare': 0.045, 'childcare': 0.04}

# === SOCIAL SECURITY ===
YOUR_SS_MONTHLY_FRA = 3_900         # Jordan
PARTNER_SS_MONTHLY_FRA = 2_300      # Taylor (WEP reduction NOT modeled)
INCLUDE_SOCIAL_SECURITY = True
SS_CLAIM_AGE = 67

def calculate_social_security(your_age: int, claim_age: int = 67) -> float:
    """Household SS in today's dollars. See retirement_sim.config for formula."""
    annual = 0.0

    def _adjust(monthly: float, claim: int) -> float:
        if claim < SOCIAL_SECURITY_START_AGE:
            months_early = (SOCIAL_SECURITY_START_AGE - claim) * 12
            first_36 = min(months_early, 36) * (5 / 9) * 0.01
            beyond_36 = max(0, months_early - 36) * (5 / 12) * 0.01
            return monthly * (1 - (first_36 + beyond_36))
        if claim > SOCIAL_SECURITY_START_AGE:
            return monthly * (1 + 0.08 * min(claim - SOCIAL_SECURITY_START_AGE, 3))
        return monthly

    if your_age >= claim_age:
        annual += _adjust(YOUR_SS_MONTHLY_FRA, claim_age) * 12
    partner_current_age = your_age - (YOUR_AGE - PARTNER_AGE)
    if partner_current_age >= claim_age:
        annual += _adjust(PARTNER_SS_MONTHLY_FRA, claim_age) * 12
    return annual

# === RMDs (Jordan born 1971 -> SECURE 2.0 start age 75) ===
RMD_START_AGE = get_rmd_start_age(YOUR_BIRTH_YEAR)

# === ROTH CONVERSION STRATEGY ===
# Especially valuable: big traditional balances plus a 7-year low-income
# window (retire at 60, SS at 67) to convert at 12%.
ENABLE_ROTH_CONVERSION = True
ROTH_CONVERSION_TARGET_BRACKET = 94_300
ROTH_CONVERSION_MAX_ANNUAL = 100_000
ROTH_CONVERSION_STOP_AGE = 67

# === ACA HEALTH INSURANCE (pre-Medicare bridge: ages 60-65) ===
ACA_ENABLED = True
ACA_BASE_MONTHLY_PREMIUM = 2_000        # older couple -- higher premiums
ACA_BASE_ANNUAL_PREMIUM = ACA_BASE_MONTHLY_PREMIUM * 12
ACA_SUBSIDY_CLIFF = FPL_FAMILY_OF_4 * ACA_SUBSIDY_CLIFF_PCT

MEDICARE_MONTHLY_PREMIUM = 450
MEDICARE_ANNUAL_PREMIUM = MEDICARE_MONTHLY_PREMIUM * 12

HEALTHCARE_COSTS_BY_AGE = {
    'pre_retirement': 8_000,
    'early_retirement': 28_000,         # older couple on ACA
    'medicare_base': 9_000,
    'medicare_mid': 13_000,
    'medicare_late': 20_000,
}
HEALTHCARE_INFLATION_RATE = 0.045

# Reuse the reference healthcare and ACA helpers -- they read module-level
# constants by name, so our overrides flow through.
calculate_healthcare_cost = _cfg.calculate_healthcare_cost
calculate_aca_premium = _cfg.calculate_aca_premium

# === LONG-TERM CARE -- enabled: real risk over 40-year horizon ===
LTC_ENABLED = True
LTC_START_AGE = 85
LTC_PROBABILITY = 0.50
LTC_DURATION_YEARS = 3
LTC_ANNUAL_COST = 110_000
LTC_INFLATION_RATE = 0.04
calculate_ltc_cost = _cfg.calculate_ltc_cost

# === ASSET ALLOCATION GLIDE PATH ===
GLIDE_PATH_ENABLED = True
GLIDE_PATH_START_STOCK_PCT = 0.65
GLIDE_PATH_START_BOND_PCT = 0.35
GLIDE_PATH_END_AGE = 75
GLIDE_PATH_END_STOCK_PCT = 0.45
GLIDE_PATH_END_BOND_PCT = 0.55
GLIDE_PATH_HOLD_AFTER = True
calculate_asset_allocation = _cfg.calculate_asset_allocation

# === SIMULATION SETTINGS ===
NUM_SIMULATIONS = 10_000
EARLIEST_RETIREMENT_AGE = 55
LATEST_RETIREMENT_AGE = 67
TARGET_SUCCESS_RATE = 0.80
USE_HOME_AS_BACKUP = True

# === COMPUTED TOTALS ===
TOTAL_RETIREMENT_ACCOUNTS = (
    YOUR_401K + YOUR_ROTH_IRA + YOUR_TRADITIONAL_IRA + YOUR_HSA
    + PARTNER_401K + PARTNER_ROTH_IRA + PARTNER_TRADITIONAL_IRA + PARTNER_HSA
)
TOTAL_TAXABLE = YOUR_BROKERAGE + PARTNER_BROKERAGE
TOTAL_CASH = YOUR_CASH + PARTNER_CASH
TOTAL_INVESTMENTS = TOTAL_RETIREMENT_ACCOUNTS + TOTAL_TAXABLE + TOTAL_CASH
TOTAL_NET_WORTH = TOTAL_INVESTMENTS + HOME_EQUITY

if __name__ == "__main__":
    hdr = "=" * 70
    print(f"{hdr}\nNEAR-RETIREMENT PROFILE: Jordan (55) & Taylor (53)\n{hdr}")
    print("\nASSETS:")
    print(f"  Retirement Accounts:  ${TOTAL_RETIREMENT_ACCOUNTS:>12,.0f}")
    print(f"  Taxable Investments:  ${TOTAL_TAXABLE:>12,.0f}")
    print(f"  Cash:                 ${TOTAL_CASH:>12,.0f}")
    print(f"  Total Investments:    ${TOTAL_INVESTMENTS:>12,.0f}")
    print(f"  Home Equity:          ${HOME_EQUITY:>12,.0f}")
    print(f"  {'-' * 40}")
    print(f"  TOTAL NET WORTH:      ${TOTAL_NET_WORTH:>12,.0f}")

    print(f"\nPERSONAL: Jordan {YOUR_AGE} / Taylor {PARTNER_AGE}. Retire @60/58.")
    print(f"  Mortgage paid off at Jordan age {YOUR_AGE + MORTGAGE_YEARS_REMAINING}")
    print(f"  Return scenario: {ACTIVE_RETURN_SCENARIO}  "
          f"Stock/Bond: {int(STOCK_ALLOCATION*100)}/{int(BOND_ALLOCATION*100)}")

    your_total = calculate_your_total_savings(YOUR_AGE)
    partner_total = calculate_partner_total_savings(PARTNER_SALARY, 0, married=True)
    print("\nANNUAL SAVINGS (current year):")
    print(f"  Jordan:  ${your_total:>10,.0f}   Taylor:  ${partner_total:>10,.0f}   "
          f"Combined: ${your_total + partner_total:,.0f}")

    print("\nCURRENT EXPENSES:")
    print(f"  Mortgage ${MORTGAGE_ANNUAL:,.0f} + Utilities ${UTILITIES_ANNUAL:,.0f} + "
          f"Jordan ${YOUR_OTHER_ANNUAL:,.0f} + Taylor ${PARTNER_ANNUAL_SPENDING:,.0f}"
          f"  =  ${CURRENT_ANNUAL_EXPENSES:,.0f}")

    print("\nNOTES:")
    print("  - Taylor's teacher pension is NOT modeled -- treat success as a floor.")
    print("  - Kids are grown; no child or college expenses.")
    print("  - Roth conversions enabled during the 60-66 low-income window.")
    print("  - LTC modeling enabled (50% probability at age 85+).")
