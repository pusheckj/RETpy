"""
Example Profile: Mid-Career Couple With Kids (Ages 40 and 38)

Alex and Riley are a dual-income couple with one child age 5 and planning a
second. Typical scenario: high-income tech + product management, home with
mortgage, mid-career savings.

- Alex: $180k base, $25k bonus, $40k RSUs
- Riley: $120k base, no bonus
- One child (age 5), second planned next year
- Home: $700k value, $350k mortgage (10 years left)
- Target retirement: age 55

NOTE: Alex and Riley are FICTITIOUS names used for this illustrative example.
All numbers are representative and not tailored to any real household. Replace
with your own values before using for personal planning. This is not financial
advice.

Run with::

    python -m examples.mid_career_couple

Or programmatically::

    import examples.mid_career_couple as cfg
    # pass cfg to the simulator in place of retirement_sim.config
"""

# -----------------------------------------------------------------------------
# IMPLEMENTATION NOTE
# -----------------------------------------------------------------------------
# This profile starts from the package defaults and overrides only the
# Alex/Riley-specific values. Pulling the base in via spec_from_file_location
# avoids triggering package __init__ imports and works whether the package is
# installed or the examples folder is run in-place.
import importlib.util as _ilu
import os as _os
_cfg_path = _os.path.join(_os.path.dirname(__file__), '..', 'retirement_sim', 'config.py')
_spec = _ilu.spec_from_file_location('retirement_sim_config_base', _cfg_path)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)
# Re-export every public attribute (constants + helper functions) from the base
# config. Profile-specific overrides follow below.
globals().update({k: v for k, v in vars(_base).items() if not k.startswith('_')})

# -----------------------------------------------------------------------------
# PERSONAL INFORMATION
# -----------------------------------------------------------------------------
YOUR_AGE = 40       # Alex (primary user)
PARTNER_AGE = 38    # Riley (partner)
CURRENT_YEAR = 2026
PLAN_UNTIL_AGE = 95
YEARS_UNTIL_WEDDING = 0  # Already married ~10 years

YOUR_BIRTH_YEAR = 1986   # Alex
PARTNER_BIRTH_YEAR = 1988  # Riley

# -----------------------------------------------------------------------------
# CURRENT ASSETS
# -----------------------------------------------------------------------------
# Alex
YOUR_401K = 350_000
YOUR_ROTH_IRA = 95_000
YOUR_TRADITIONAL_IRA = 20_000
YOUR_HSA = 25_000
YOUR_BROKERAGE = 180_000
YOUR_CASH = 40_000

# Riley
PARTNER_401K = 180_000
PARTNER_ROTH_IRA = 55_000
PARTNER_BROKERAGE = 30_000
PARTNER_CASH = 25_000

# Primary residence
HOME_VALUE = 700_000
MORTGAGE_BALANCE = 350_000
HOME_EQUITY = HOME_VALUE - MORTGAGE_BALANCE

# -----------------------------------------------------------------------------
# ALEX'S COMPENSATION (AGES 40 -> 55)
# -----------------------------------------------------------------------------
# Base grows ~3%/yr, bonus ~14% of base, RSUs ~22% of base.
# after_tax and saved are rough estimates for a high-earner MFJ in a high-tax
# state, after 401k/HSA contributions and typical household spending.
YOUR_COMPENSATION_BY_AGE = {
    40: {"base": 180_000, "bonus": 25_000, "rsu_gross": 40_000, "total_comp": 245_000, "after_tax": 158_000, "saved": 50_000},
    41: {"base": 185_400, "bonus": 26_000, "rsu_gross": 42_000, "total_comp": 253_400, "after_tax": 163_000, "saved": 52_000},
    42: {"base": 191_000, "bonus": 27_000, "rsu_gross": 44_000, "total_comp": 262_000, "after_tax": 168_000, "saved": 54_000},
    43: {"base": 196_700, "bonus": 28_000, "rsu_gross": 46_000, "total_comp": 270_700, "after_tax": 173_000, "saved": 56_000},
    44: {"base": 202_600, "bonus": 29_000, "rsu_gross": 48_000, "total_comp": 279_600, "after_tax": 178_000, "saved": 58_000},
    45: {"base": 208_700, "bonus": 30_000, "rsu_gross": 50_000, "total_comp": 288_700, "after_tax": 184_000, "saved": 60_000},
    46: {"base": 215_000, "bonus": 31_000, "rsu_gross": 52_000, "total_comp": 298_000, "after_tax": 189_000, "saved": 62_000},
    47: {"base": 221_500, "bonus": 32_000, "rsu_gross": 54_000, "total_comp": 307_500, "after_tax": 195_000, "saved": 64_000},
    48: {"base": 228_100, "bonus": 33_000, "rsu_gross": 56_000, "total_comp": 317_100, "after_tax": 201_000, "saved": 66_000},
    49: {"base": 235_000, "bonus": 34_000, "rsu_gross": 58_000, "total_comp": 327_000, "after_tax": 207_000, "saved": 68_000},
    50: {"base": 242_000, "bonus": 35_000, "rsu_gross": 60_000, "total_comp": 337_000, "after_tax": 213_000, "saved": 70_000},
    51: {"base": 249_300, "bonus": 36_000, "rsu_gross": 62_000, "total_comp": 347_300, "after_tax": 219_000, "saved": 72_000},
    52: {"base": 256_800, "bonus": 37_000, "rsu_gross": 64_000, "total_comp": 357_800, "after_tax": 225_000, "saved": 74_000},
    53: {"base": 264_500, "bonus": 38_000, "rsu_gross": 66_000, "total_comp": 368_500, "after_tax": 231_000, "saved": 76_000},
    54: {"base": 272_400, "bonus": 39_000, "rsu_gross": 68_000, "total_comp": 379_400, "after_tax": 237_000, "saved": 78_000},
    55: {"base": 280_600, "bonus": 40_000, "rsu_gross": 70_000, "total_comp": 390_600, "after_tax": 243_000, "saved": 80_000},
}
YOUR_SALARY_GROWTH_RATE = 0.03
YOUR_BONUS_PCT = 0.14
YOUR_RSU_PCT = 0.22
YOUR_MARGINAL_TAX_RATE = 0.32

# Alex's contribution rates (defaults from base config are fine for 401k/HSA)
YOUR_401K_MATCH_PCT = 0.06  # Employer matches up to 6% of base

# -----------------------------------------------------------------------------
# RILEY (PARTNER) INCOME
# -----------------------------------------------------------------------------
PARTNER_SALARY = 120_000
PARTNER_SALARY_GROWTH_RATE = 0.03
PARTNER_401K_CONTRIBUTION = 23_000
PARTNER_MONTHLY_SPENDING = 2_500
PARTNER_ANNUAL_SPENDING = PARTNER_MONTHLY_SPENDING * 12
PARTNER_ESTIMATED_TAX_RATE = 0.27

# -----------------------------------------------------------------------------
# EXPENSES
# -----------------------------------------------------------------------------
MORTGAGE_MONTHLY = 2_800
MORTGAGE_ANNUAL = MORTGAGE_MONTHLY * 12
MORTGAGE_YEARS_REMAINING = 10  # Mortgage paid off at Alex's age 50

UTILITIES_MONTHLY = 175
UTILITIES_ANNUAL = UTILITIES_MONTHLY * 12

YOUR_OTHER_MONTHLY = 3_000  # Alex / household
YOUR_OTHER_ANNUAL = YOUR_OTHER_MONTHLY * 12

PARTNER_OTHER_MONTHLY = 2_500  # Riley personal

CURRENT_ANNUAL_EXPENSES = (MORTGAGE_ANNUAL + UTILITIES_ANNUAL
                           + YOUR_OTHER_ANNUAL + PARTNER_OTHER_MONTHLY * 12)
BASE_RETIREMENT_EXPENSES_NO_MORTGAGE = (YOUR_OTHER_ANNUAL + UTILITIES_ANNUAL
                                        + PARTNER_OTHER_MONTHLY * 12)
RETIREMENT_ANNUAL_EXPENSES = BASE_RETIREMENT_EXPENSES_NO_MORTGAGE

# -----------------------------------------------------------------------------
# CHILDREN
# -----------------------------------------------------------------------------
# First child is already 5 -> YEARS_UNTIL_FIRST_CHILD = -5 places the birth
# 5 years ago relative to YOUR_AGE. Second child planned in 1 year ->
# YEARS_BETWEEN_CHILDREN = 6. The base calculate_child_expenses handles
# negative offsets correctly because it derives the birth age from
# YOUR_AGE + YEARS_UNTIL_FIRST_CHILD, which remains valid for any integer.
YEARS_UNTIL_FIRST_CHILD = -5
YEARS_BETWEEN_CHILDREN = 6
FIRST_CHILD_MONTHLY_COST = 1_800
FIRST_CHILD_ANNUAL_COST = FIRST_CHILD_MONTHLY_COST * 12
BOTH_CHILDREN_MONTHLY_COST = 3_400
BOTH_CHILDREN_ANNUAL_COST = BOTH_CHILDREN_MONTHLY_COST * 12

# -----------------------------------------------------------------------------
# COLLEGE / 529
# -----------------------------------------------------------------------------
COLLEGE_FUNDING_PCT = 0.50  # Target covering ~50% of in-state 4-year cost
COLLEGE_ANNUAL_COST = 40_000
COLLEGE_TARGET_PER_CHILD = COLLEGE_ANNUAL_COST * 4 * COLLEGE_FUNDING_PCT
SAVINGS_529_PER_CHILD_ANNUAL = COLLEGE_TARGET_PER_CHILD / 18

# -----------------------------------------------------------------------------
# ASSET ALLOCATION / RETURNS
# -----------------------------------------------------------------------------
STOCK_ALLOCATION = 0.85
BOND_ALLOCATION = 0.15
ACTIVE_RETURN_SCENARIO = 'historical'

# -----------------------------------------------------------------------------
# SOCIAL SECURITY
# -----------------------------------------------------------------------------
YOUR_SS_MONTHLY_FRA = 3_200       # Alex estimate at FRA (67)
PARTNER_SS_MONTHLY_FRA = 2_400    # Riley estimate at FRA (67)
SS_CLAIM_AGE = 67

# -----------------------------------------------------------------------------
# ACA / HEALTHCARE
# -----------------------------------------------------------------------------
# Family of 4 premium is higher than the default (family of 3/4 mid-tier plan).
ACA_BASE_MONTHLY_PREMIUM = 1_700
ACA_BASE_ANNUAL_PREMIUM = ACA_BASE_MONTHLY_PREMIUM * 12

# -----------------------------------------------------------------------------
# SIMULATION
# -----------------------------------------------------------------------------
EARLIEST_RETIREMENT_AGE = 50
LATEST_RETIREMENT_AGE = 65
TARGET_SUCCESS_RATE = 0.80

# -----------------------------------------------------------------------------
# RECOMPUTE DERIVED VALUES
# -----------------------------------------------------------------------------
# Base config computed RMD_START_AGE, HOME_EQUITY, totals etc. from its own
# defaults; recompute them here using the overridden values.
RMD_START_AGE = _base.get_rmd_start_age(YOUR_BIRTH_YEAR)

TOTAL_RETIREMENT_ACCOUNTS = (YOUR_401K + YOUR_ROTH_IRA + YOUR_TRADITIONAL_IRA
                             + YOUR_HSA + PARTNER_401K + PARTNER_ROTH_IRA)
TOTAL_TAXABLE = YOUR_BROKERAGE + PARTNER_BROKERAGE
TOTAL_CASH = YOUR_CASH + PARTNER_CASH
TOTAL_INVESTMENTS = TOTAL_RETIREMENT_ACCOUNTS + TOTAL_TAXABLE + TOTAL_CASH
TOTAL_NET_WORTH = TOTAL_INVESTMENTS + HOME_EQUITY


# -----------------------------------------------------------------------------
# PROFILE-AWARE HELPER FUNCTIONS
# -----------------------------------------------------------------------------
# The base helpers close over the base module's YOUR_AGE / balances etc. at
# import time, so we redefine the ones whose behavior depends on values this
# profile overrides (YOUR_AGE, child timing, partner income, compensation).

def calculate_your_total_savings(age):
    if age in YOUR_COMPENSATION_BY_AGE:
        c = YOUR_COMPENSATION_BY_AGE[age]
        return (c['saved'] + _base.YOUR_401K_CONTRIBUTION
                + c['base'] * YOUR_401K_MATCH_PCT + _base.YOUR_HSA_TOTAL)
    last = max(YOUR_COMPENSATION_BY_AGE.keys())
    return calculate_your_total_savings(last) * ((1 + YOUR_SALARY_GROWTH_RATE) ** (age - last))


def calculate_partner_total_savings(salary, years_from_now, married=False):
    after_tax = (salary - PARTNER_401K_CONTRIBUTION) * (1 - PARTNER_ESTIMATED_TAX_RATE)
    roth = 0 if married else _base.PARTNER_ROTH_CONTRIBUTION
    to_brokerage = max(0, after_tax - roth - PARTNER_ANNUAL_SPENDING)
    return PARTNER_401K_CONTRIBUTION + roth + to_brokerage


def calculate_child_expenses(your_age):
    first_birth = YOUR_AGE + YEARS_UNTIL_FIRST_CHILD
    second_birth = first_birth + YEARS_BETWEEN_CHILDREN
    first_leaves = first_birth + _base.CHILD_LEAVES_HOME_AGE
    second_leaves = second_birth + _base.CHILD_LEAVES_HOME_AGE
    if your_age < first_birth:
        return 0
    if your_age < second_birth:
        return FIRST_CHILD_ANNUAL_COST if your_age < first_leaves else 0
    if your_age < first_leaves:
        return BOTH_CHILDREN_ANNUAL_COST
    if your_age < second_leaves:
        return BOTH_CHILDREN_ANNUAL_COST - FIRST_CHILD_ANNUAL_COST
    return 0


def calculate_529_contribution(your_age):
    first_birth = YOUR_AGE + YEARS_UNTIL_FIRST_CHILD
    second_birth = first_birth + YEARS_BETWEEN_CHILDREN
    total = 0
    if 0 <= (your_age - first_birth) < 18:
        total += SAVINGS_529_PER_CHILD_ANNUAL
    if 0 <= (your_age - second_birth) < 18:
        total += SAVINGS_529_PER_CHILD_ANNUAL
    return total


def calculate_college_expenses(your_age):
    first_birth = YOUR_AGE + YEARS_UNTIL_FIRST_CHILD
    second_birth = first_birth + YEARS_BETWEEN_CHILDREN
    out = {'child1': 0, 'child2': 0, 'total': 0}
    if 18 <= (your_age - first_birth) < 18 + _base.COLLEGE_YEARS:
        out['child1'] = COLLEGE_ANNUAL_COST * COLLEGE_FUNDING_PCT
    if 18 <= (your_age - second_birth) < 18 + _base.COLLEGE_YEARS:
        out['child2'] = COLLEGE_ANNUAL_COST * COLLEGE_FUNDING_PCT
    out['total'] = out['child1'] + out['child2']
    return out


def has_mortgage(your_age):
    return your_age < YOUR_AGE + MORTGAGE_YEARS_REMAINING


def calculate_annual_expenses(your_age, inflation_factor=1.0):
    base = BASE_RETIREMENT_EXPENSES_NO_MORTGAGE
    if has_mortgage(your_age):
        base += MORTGAGE_ANNUAL
    base += calculate_child_expenses(your_age)
    return base * inflation_factor


def calculate_social_security(your_age, claim_age=67):
    # Inline the base helper's math using the overridden FRA amounts.
    total = 0
    start = _base.SOCIAL_SECURITY_START_AGE
    def _adj(monthly, ca):
        if ca < start:
            m_early = (start - ca) * 12
            r1 = min(m_early, 36) * (5 / 9) * 0.01
            r2 = max(0, m_early - 36) * (5 / 12) * 0.01
            return monthly * (1 - r1 - r2)
        if ca > start:
            return monthly * (1 + 0.08 * min(ca - start, 3))
        return monthly
    if your_age >= claim_age:
        total += _adj(YOUR_SS_MONTHLY_FRA, claim_age) * 12
    partner_age = your_age - (YOUR_AGE - PARTNER_AGE)
    if partner_age >= claim_age:
        total += _adj(PARTNER_SS_MONTHLY_FRA, claim_age) * 12
    return total


if __name__ == "__main__":
    print("=" * 70)
    print("MID-CAREER COUPLE WITH KIDS - ALEX (40) & RILEY (38)")
    print("Fictitious example profile. Not financial advice.")
    print("=" * 70)
    print("\nASSETS:")
    print(f"  Retirement Accounts:  ${TOTAL_RETIREMENT_ACCOUNTS:>12,.0f}")
    print(f"  Taxable Investments:  ${TOTAL_TAXABLE:>12,.0f}")
    print(f"  Cash:                 ${TOTAL_CASH:>12,.0f}")
    print(f"  Total Investments:    ${TOTAL_INVESTMENTS:>12,.0f}")
    print(f"  Home Equity:          ${HOME_EQUITY:>12,.0f}")
    print(f"  {'-' * 40}")
    print(f"  TOTAL NET WORTH:      ${TOTAL_NET_WORTH:>12,.0f}")

    print("\nPERSONAL INFO:")
    print(f"  Alex (primary): {YOUR_AGE}, Riley (partner): {PARTNER_AGE}")
    print(f"  Married at simulation start")
    print(f"  Mortgage paid off at Alex's age {YOUR_AGE + MORTGAGE_YEARS_REMAINING}")
    print(f"  Target retirement age: {EARLIEST_RETIREMENT_AGE}+")

    first_birth = YOUR_AGE + YEARS_UNTIL_FIRST_CHILD
    second_birth = first_birth + YEARS_BETWEEN_CHILDREN
    print("\nCHILDREN:")
    print(f"  First child currently age {YOUR_AGE - first_birth} (born when Alex was {first_birth})")
    print(f"  Second child born when Alex is {second_birth} (in {second_birth - YOUR_AGE} year)")

    your_total = calculate_your_total_savings(YOUR_AGE)
    partner_total = calculate_partner_total_savings(PARTNER_SALARY, 0, married=(YEARS_UNTIL_WEDDING == 0))
    print("\nANNUAL SAVINGS:")
    print(f"  Alex:                 ${your_total:>12,.0f}")
    print(f"  Riley:                ${partner_total:>12,.0f}")
    print(f"  {'-' * 40}")
    print(f"  COMBINED:             ${your_total + partner_total:>12,.0f}")

    print("\nCURRENT EXPENSES:")
    print(f"  Mortgage:             ${MORTGAGE_ANNUAL:>12,.0f}")
    print(f"  Utilities:            ${UTILITIES_ANNUAL:>12,.0f}")
    print(f"  Alex other:           ${YOUR_OTHER_ANNUAL:>12,.0f}")
    print(f"  Riley other:          ${PARTNER_ANNUAL_SPENDING:>12,.0f}")
    print(f"  Children (current):   ${calculate_child_expenses(YOUR_AGE):>12,.0f}")
    print(f"  {'-' * 40}")
    print(f"  TOTAL (ex-kids):      ${CURRENT_ANNUAL_EXPENSES:>12,.0f}")

    print("\nEXPENSE TIMELINE:")
    for age in [YOUR_AGE, 45, 50, 55, 65, 75]:
        child_exp = calculate_child_expenses(age)
        status = "w/mortgage" if has_mortgage(age) else "no mortgage"
        total = calculate_annual_expenses(age)
        print(f"  Age {age}: Children ${child_exp:>6,.0f}/yr, Total ${total:>7,.0f}/yr ({status})")
