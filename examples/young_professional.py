"""
Example Profile: Young Professional (Single, Age 28)

Sarah is a 28-year-old software engineer planning her retirement.
- $135k base, 10% bonus, $30k RSUs
- Single, no kids, renting
- Modest savings from 5 years of maxing 401k/Roth/HSA

NOTE: Sarah is a fictitious example profile. All numbers are illustrative.

LIMITATIONS OF THIS PROFILE
---------------------------
- The base simulator assumes Married Filing Jointly (MFJ) tax brackets,
  standard deduction, SS provisional-income thresholds, NIIT thresholds,
  and IRMAA brackets. Modeling a single filer here is an APPROXIMATION --
  results will be slightly optimistic on tax-favored withdrawals. To model
  a single filer accurately, edit the tax dataclasses in
  ``retirement_sim/account_simulation.py``.
- Student loans are NOT modeled by the base package. Sarah has ~$35k in
  federal loans at 5% (not reflected in this config). Consider adding the
  monthly payment to YOUR_OTHER_MONTHLY until payoff.
- ``PARTNER_AGE = 0`` makes this a single household: no partner accounts,
  pay, contributions or Social Security. Filing status is Single.

Run with::

    python -m examples.young_professional

Or programmatically::

    import examples.young_professional as cfg
    # pass cfg to the simulator in place of retirement_sim.config
"""

# -----------------------------------------------------------------------------
# IMPLEMENTATION NOTE
# -----------------------------------------------------------------------------
# This profile starts from the package defaults via ``from ... import *`` and
# then overrides the Sarah-specific values. This keeps the profile short and
# automatically picks up future package additions (new helper functions, new
# constants). If you want a fully self-contained profile, copy the entire
# contents of ``retirement_sim/config.py`` into this file and edit in place.

# Import from the config submodule directly (avoids triggering package
# __init__ imports that are unrelated to configuration, and works whether
# the package is installed or the examples folder is run in-place).
import importlib.util as _ilu
import os as _os
_cfg_path = _os.path.join(_os.path.dirname(__file__), '..', 'retirement_sim', 'config.py')
_spec = _ilu.spec_from_file_location('retirement_sim_config_base', _cfg_path)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)
# Re-export every public attribute (constants + helper functions) from base.
globals().update({k: v for k, v in vars(_base).items() if not k.startswith('_')})

# -----------------------------------------------------------------------------
# PERSONAL INFORMATION
# -----------------------------------------------------------------------------
YOUR_AGE = 28
PARTNER_AGE = 0           # 0 = no partner (single household)
CURRENT_YEAR = 2026
PLAN_UNTIL_AGE = 95

FILING_STATUS = "Single"
MARRIED = False

# -----------------------------------------------------------------------------
# CURRENT ASSETS
# -----------------------------------------------------------------------------
YOUR_401K = 50_000
YOUR_ROTH_IRA = 25_000    # Backdoor Roth
YOUR_TRADITIONAL_IRA = 0
YOUR_HSA = 8_000
YOUR_BROKERAGE = 30_000
YOUR_CASH = 25_000        # Emergency fund

PARTNER_401K = 0
PARTNER_ROTH_IRA = 0
PARTNER_BROKERAGE = 0
PARTNER_CASH = 0

HOME_VALUE = 0
MORTGAGE_BALANCE = 0
HOME_EQUITY = 0
HOME_EQUITY_ACCESSIBLE_PCT = 0.85  # Unused (HOME_EQUITY == 0)

# -----------------------------------------------------------------------------
# PRIMARY USER INCOME
# -----------------------------------------------------------------------------
# Sarah's compensation ages 28-40. Base grows ~4%/yr; RSUs grow modestly.
# ``after_tax`` and ``saved`` are estimates for a single filer in a moderate
# tax state, net of federal/state/payroll taxes and living expenses.
YOUR_COMPENSATION_BY_AGE = {
    28: {"base": 135_000, "bonus": 13_500, "rsu_gross": 30_000, "total_comp": 178_500, "after_tax": 120_000, "saved": 20_000},
    29: {"base": 140_000, "bonus": 14_000, "rsu_gross": 32_000, "total_comp": 186_000, "after_tax": 125_000, "saved": 22_000},
    30: {"base": 146_000, "bonus": 14_600, "rsu_gross": 35_000, "total_comp": 195_600, "after_tax": 130_000, "saved": 24_000},
    31: {"base": 152_000, "bonus": 15_200, "rsu_gross": 38_000, "total_comp": 205_200, "after_tax": 135_000, "saved": 26_000},
    32: {"base": 158_000, "bonus": 15_800, "rsu_gross": 40_000, "total_comp": 213_800, "after_tax": 140_000, "saved": 28_000},
    33: {"base": 165_000, "bonus": 16_500, "rsu_gross": 42_000, "total_comp": 223_500, "after_tax": 145_000, "saved": 30_000},
    34: {"base": 172_000, "bonus": 17_200, "rsu_gross": 45_000, "total_comp": 234_200, "after_tax": 151_000, "saved": 32_000},
    35: {"base": 179_000, "bonus": 17_900, "rsu_gross": 48_000, "total_comp": 244_900, "after_tax": 157_000, "saved": 34_000},
    36: {"base": 186_000, "bonus": 18_600, "rsu_gross": 50_000, "total_comp": 254_600, "after_tax": 163_000, "saved": 36_000},
    37: {"base": 194_000, "bonus": 19_400, "rsu_gross": 52_000, "total_comp": 265_400, "after_tax": 169_000, "saved": 38_000},
    38: {"base": 202_000, "bonus": 20_200, "rsu_gross": 55_000, "total_comp": 277_200, "after_tax": 176_000, "saved": 40_000},
    39: {"base": 210_000, "bonus": 21_000, "rsu_gross": 58_000, "total_comp": 289_000, "after_tax": 183_000, "saved": 42_000},
    40: {"base": 218_000, "bonus": 21_800, "rsu_gross": 60_000, "total_comp": 299_800, "after_tax": 189_000, "saved": 44_000},
}

YOUR_SALARY_GROWTH_RATE = 0.04
YOUR_BONUS_PCT = 0.10
YOUR_RSU_PCT = 0.28

YOUR_401K_CONTRIBUTION = 23_000
YOUR_401K_MATCH_PCT = 0.05
YOUR_HSA_CONTRIBUTION = 3_550         # Individual HDHP
YOUR_HSA_MATCH = 600
YOUR_HSA_TOTAL = YOUR_HSA_CONTRIBUTION + YOUR_HSA_MATCH
YOUR_BACKDOOR_ROTH = 7_000
YOUR_ESPP_PCT = 0.10
YOUR_ESPP_DISCOUNT = 0.15

YOUR_MARGINAL_TAX_RATE = 0.32

# -----------------------------------------------------------------------------
# PARTNER INCOME (single household -> zero)
# -----------------------------------------------------------------------------
PARTNER_SALARY = 0
PARTNER_SALARY_GROWTH_RATE = 0.0
PARTNER_401K_CONTRIBUTION = 0
PARTNER_401K_MATCH = 0
PARTNER_ROTH_CONTRIBUTION = 0
PARTNER_MONTHLY_SPENDING = 0
PARTNER_ANNUAL_SPENDING = 0
PARTNER_ESTIMATED_TAX_RATE = 0.25     # Unused but kept for engine compatibility

# -----------------------------------------------------------------------------
# EXPENSES - Sarah rents (no mortgage); rent bundled into YOUR_OTHER_MONTHLY.
# -----------------------------------------------------------------------------
MORTGAGE_MONTHLY = 0
MORTGAGE_ANNUAL = 0
MORTGAGE_YEARS_REMAINING = 0

UTILITIES_MONTHLY = 100
UTILITIES_ANNUAL = UTILITIES_MONTHLY * 12

YOUR_OTHER_MONTHLY = 3_500            # Rent + food + transport + lifestyle
YOUR_OTHER_ANNUAL = YOUR_OTHER_MONTHLY * 12

PARTNER_OTHER_MONTHLY = 0

CURRENT_ANNUAL_EXPENSES = (
    MORTGAGE_ANNUAL + UTILITIES_ANNUAL + YOUR_OTHER_ANNUAL
    + (PARTNER_OTHER_MONTHLY * 12)
)

# -----------------------------------------------------------------------------
# LIFE EVENTS - no children (so no 529 or college costs either)
# -----------------------------------------------------------------------------
CHILDREN = []

# -----------------------------------------------------------------------------
# Overrides for helper functions that hardcode module-level references
# -----------------------------------------------------------------------------
# The package helpers close over module-level globals (YOUR_AGE, mortgage
# fields, etc.). Re-defining them here makes them use THIS module's values.

def has_mortgage(your_age: int) -> bool:
    return False


def calculate_child_expenses(your_age: int) -> float:
    return 0.0


def calculate_529_contribution(your_age: int) -> float:
    return 0.0


def calculate_college_expenses(your_age: int) -> dict:
    return {'total': 0}


def calculate_your_total_savings(age: int) -> float:
    if age in YOUR_COMPENSATION_BY_AGE:
        comp = YOUR_COMPENSATION_BY_AGE[age]
        return (
            comp['saved']
            + YOUR_401K_CONTRIBUTION
            + comp['base'] * YOUR_401K_MATCH_PCT
            + YOUR_HSA_TOTAL
        )
    last_known_age = max(YOUR_COMPENSATION_BY_AGE.keys())
    last_known = calculate_your_total_savings(last_known_age)
    return last_known * ((1 + YOUR_SALARY_GROWTH_RATE) ** (age - last_known_age))


def calculate_partner_total_savings(salary: float, years_from_now: int, married: bool = False) -> float:
    return 0.0


def calculate_annual_expenses(your_age: int, inflation_factor: float = 1.0) -> float:
    base = BASE_RETIREMENT_EXPENSES_NO_MORTGAGE  # defined below
    if has_mortgage(your_age):
        base += MORTGAGE_ANNUAL
    base += calculate_child_expenses(your_age)
    return base * inflation_factor


# -----------------------------------------------------------------------------
# RETIREMENT EXPENSE MODELING
# -----------------------------------------------------------------------------
BASE_RETIREMENT_EXPENSES_NO_MORTGAGE = (
    YOUR_OTHER_ANNUAL + UTILITIES_ANNUAL + PARTNER_OTHER_MONTHLY * 12
)
RETIREMENT_ANNUAL_EXPENSES = BASE_RETIREMENT_EXPENSES_NO_MORTGAGE

HEALTHCARE_INCREASE_ANNUAL = 6_000            # Single filer
HEALTHCARE_INCREASE_PRE_MEDICARE = 8_000
EARLY_RETIREMENT_LEISURE_INCREASE = 8_000

# -----------------------------------------------------------------------------
# INVESTMENT / ALLOCATION - aggressive glide for 28-year-old
# -----------------------------------------------------------------------------
STOCK_ALLOCATION = 0.90
BOND_ALLOCATION = 0.10
ACTIVE_RETURN_SCENARIO = 'historical'
DISCRETIONARY_EXPENSE_RATIO = 0.35

# -----------------------------------------------------------------------------
# SOCIAL SECURITY - single filer (no partner benefit)
# -----------------------------------------------------------------------------
INCLUDE_SOCIAL_SECURITY = True
SS_CLAIM_AGE = 67
YOUR_SS_MONTHLY_FRA = 2_800
PARTNER_SS_MONTHLY_FRA = 0


def calculate_social_security(your_age: int, claim_age: int = 67) -> float:
    """Single-filer SS - no partner benefit."""
    if your_age < claim_age:
        return 0.0
    monthly = YOUR_SS_MONTHLY_FRA
    if claim_age < SOCIAL_SECURITY_START_AGE:
        months_early = (SOCIAL_SECURITY_START_AGE - claim_age) * 12
        first_36 = min(months_early, 36) * (5 / 9) * 0.01
        beyond_36 = max(0, months_early - 36) * (5 / 12) * 0.01
        monthly *= (1 - (first_36 + beyond_36))
    elif claim_age > SOCIAL_SECURITY_START_AGE:
        years_delayed = min(claim_age - SOCIAL_SECURITY_START_AGE, 3)
        monthly *= (1 + 0.08 * years_delayed)
    return monthly * 12


# -----------------------------------------------------------------------------
# MEDICARE - single filer (not a couple, so half the premium)
# -----------------------------------------------------------------------------
MEDICARE_MONTHLY_PREMIUM = 200
MEDICARE_ANNUAL_PREMIUM = MEDICARE_MONTHLY_PREMIUM * 12


def calculate_medicare_irmaa(magi: float, inflation_factor: float = 1.0) -> float:
    """Single-filer IRMAA (one person, not a couple)."""
    part_b = MEDICARE_IRMAA_BRACKETS_MFJ[0][1]
    part_d = MEDICARE_IRMAA_BRACKETS_MFJ[0][2]
    for threshold, b, d in MEDICARE_IRMAA_BRACKETS_MFJ:
        if magi >= threshold:
            part_b, part_d = b, d
        else:
            break
    return (part_b + part_d) * 12 * 1 * inflation_factor


# -----------------------------------------------------------------------------
# ACA - individual plan
# -----------------------------------------------------------------------------
ACA_BASE_MONTHLY_PREMIUM = 600
ACA_BASE_ANNUAL_PREMIUM = ACA_BASE_MONTHLY_PREMIUM * 12

HEALTHCARE_COSTS_BY_AGE = {
    'pre_retirement': 3_000,
    'early_retirement': 12_000,
    'medicare_base': 4_000,
    'medicare_mid': 6_000,
    'medicare_late': 9_000,
}

# -----------------------------------------------------------------------------
# BIRTH YEARS / RMD
# -----------------------------------------------------------------------------
YOUR_BIRTH_YEAR = CURRENT_YEAR - YOUR_AGE        # derived from age
PARTNER_BIRTH_YEAR = CURRENT_YEAR - PARTNER_AGE
RMD_START_AGE = get_rmd_start_age(YOUR_BIRTH_YEAR)  # 75

# -----------------------------------------------------------------------------
# SIMULATION SETTINGS
# -----------------------------------------------------------------------------
NUM_SIMULATIONS = 10_000
EARLIEST_RETIREMENT_AGE = 50
LATEST_RETIREMENT_AGE = 65
TARGET_SUCCESS_RATE = 0.80
TARGET_RETIREMENT_AGE = 55

USE_HOME_AS_BACKUP = False  # No home

# -----------------------------------------------------------------------------
# COMPUTED TOTALS
# -----------------------------------------------------------------------------
TOTAL_RETIREMENT_ACCOUNTS = (YOUR_401K + YOUR_ROTH_IRA + YOUR_TRADITIONAL_IRA
                             + YOUR_HSA + PARTNER_401K + PARTNER_ROTH_IRA)
TOTAL_TAXABLE = YOUR_BROKERAGE + PARTNER_BROKERAGE
TOTAL_CASH = YOUR_CASH + PARTNER_CASH
TOTAL_INVESTMENTS = TOTAL_RETIREMENT_ACCOUNTS + TOTAL_TAXABLE + TOTAL_CASH
TOTAL_NET_WORTH = TOTAL_INVESTMENTS + HOME_EQUITY


if __name__ == "__main__":
    print("=" * 70)
    print("FINANCIAL SUMMARY - Young Professional Example (Sarah, age 28)")
    print("=" * 70)

    print("\nASSETS:")
    print(f"  401(k):               ${YOUR_401K:>12,.0f}")
    print(f"  Roth IRA:             ${YOUR_ROTH_IRA:>12,.0f}")
    print(f"  HSA:                  ${YOUR_HSA:>12,.0f}")
    print(f"  Brokerage:            ${YOUR_BROKERAGE:>12,.0f}")
    print(f"  Cash (emergency):     ${YOUR_CASH:>12,.0f}")
    print(f"  {'-' * 40}")
    print(f"  TOTAL NET WORTH:      ${TOTAL_NET_WORTH:>12,.0f}")

    print("\nPERSONAL INFO:")
    print(f"  Age: {YOUR_AGE}  (single, renting, no kids planned)")
    print(f"  Birth year: {YOUR_BIRTH_YEAR}, current year: {CURRENT_YEAR}")
    print(f"  Target retirement age: {TARGET_RETIREMENT_AGE}")
    print(f"  Plan until age: {PLAN_UNTIL_AGE}")

    print("\nANNUAL SAVINGS (age 28):")
    your_total = calculate_your_total_savings(YOUR_AGE)
    print(f"  Total (401k + match + HSA + taxable):  ${your_total:>12,.0f}")

    print("\nCURRENT EXPENSES:")
    print(f"  Rent + lifestyle:     ${YOUR_OTHER_ANNUAL:>12,.0f}")
    print(f"  Utilities:            ${UTILITIES_ANNUAL:>12,.0f}")
    print(f"  {'-' * 40}")
    print(f"  TOTAL:                ${CURRENT_ANNUAL_EXPENSES:>12,.0f}")

    print("\nCOMPENSATION PROJECTION:")
    for age in [28, 32, 36, 40]:
        comp = YOUR_COMPENSATION_BY_AGE.get(age)
        if comp:
            print(f"  Age {age}: base ${comp['base']:,} + bonus ${comp['bonus']:,} "
                  f"+ RSU ${comp['rsu_gross']:,} = ${comp['total_comp']:,}")

    print("\nRETIREMENT SETTINGS:")
    print(f"  Return scenario:      {ACTIVE_RETURN_SCENARIO}")
    print(f"  Stock/bond at start:  {int(STOCK_ALLOCATION * 100)}/{int(BOND_ALLOCATION * 100)}")
    print(f"  SS included:          {INCLUDE_SOCIAL_SECURITY} (claim age {SS_CLAIM_AGE})")
    print(f"  SS FRA monthly:       ${YOUR_SS_MONTHLY_FRA:,}")
    print(f"  Roth conversions:     {ENABLE_ROTH_CONVERSION}")

    print("\nNOTE: This config re-uses the package's MFJ tax tables for engine")
    print("compatibility. A true single filer would face higher marginal rates")
    print("and lower SS/NIIT/IRMAA thresholds. Student loans not modeled.")
