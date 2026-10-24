"""
=============================================================================
RETIREMENT MONTE CARLO SIMULATOR - CONFIGURATION
=============================================================================

License: MIT (see LICENSE at project root)

PURPOSE
-------
This module holds every financial assumption and user-specific parameter used
by the retirement Monte Carlo simulator. All account balances, income
projections, contribution rates, tax tables, inflation assumptions, healthcare
models, Social Security estimates, and simulation toggles live here.

Keeping configuration in one place means that running the simulator for a
different household is a matter of editing this file (or copying it into your
own profile under ``examples/`` and pointing the simulator at it) — the core
simulation engine in ``account_simulation.py`` should not need changes.

HOW TO USE
----------
1. Copy this file (or one of the ready-made profiles under ``examples/``) and
   edit the values to match your household.
2. Update ages, balances, income projections, and toggles.
3. Replace the Social Security, marginal-rate, and state-tax defaults with
   your own estimates.
4. Run ``python -m retirement_sim.account_simulation`` or invoke the
   Monte Carlo helpers programmatically.

For a parameter-by-parameter walkthrough see ``docs/CONFIGURATION.md``. For
ready-made household profiles (single earner, dual-income, near-retirement,
FIRE scenarios, etc.) see the files under ``examples/``.

DISCLAIMER
----------
The default values in this file represent a **median US household headed by
25-year-olds** (approximate figures from the Federal Reserve Survey of
Consumer Finances 2022, BLS Current Population Survey, US Census, and
Vanguard's "How America Saves" report):

- Household income ~$85,000 combined ($45k + $42k)
- Household net worth ~$35,000 (mostly cash + starter 401k balances)
- Renters (no home or mortgage at simulation start)
- Modest employer 401k match (4%), no HSA / ESPP / RSUs

They are **not** tailored to any real person and they are **not** financial,
tax, or legal advice. Always validate the assumptions against your own
situation and consult a qualified professional before making retirement
decisions. See ``examples/`` for other profiles (mid-career couple,
near-retirement, young high-earning professional).

TAX YEAR
--------
Federal contribution limits, standard deduction, IRMAA brackets, SS taxation
thresholds, NIIT threshold, and state bracket values use **tax year 2024** as
the reference. The simulator inflates limits forward from 2024 using the
``CONTRIBUTION_LIMIT_INFLATION_RATE`` rate.

NAMING CONVENTION
-----------------
``YOUR_*``     refers to the primary user (user 1 / higher earner by default).
``PARTNER_*``  refers to the secondary user (user 2 / spouse or partner).
Set ``PARTNER_AGE = 0`` for a single household: the engine then leaves out every
partner account, paycheck, contribution and Social Security benefit (see
``has_partner``). ``FILING_STATUS`` says whether a couple is married.
"""

# -----------------------------------------------------------------------------
# PERSONAL INFORMATION
# -----------------------------------------------------------------------------
# Defaults represent a median US household headed by 25-year-olds.
YOUR_AGE = 25
PARTNER_AGE = 25
CURRENT_YEAR = 2026

# Planning horizon - model until this age. Each person has one: PLAN_UNTIL_AGE
# is yours, PARTNER_PLAN_UNTIL_AGE your partner's (None = the same age), and the
# plan runs until the LATER of the two (plan_end_age), so a younger partner is
# covered to their own plan-until age.
# Rationale: ~30-40% chance one partner in a couple lives past 90, so plan long.
# LIMITATION (fixed-horizon / no-mortality model): the simulation assumes BOTH
# spouses survive continuously through the plan. There is no stochastic
# mortality, no survivor Social Security benefit, no filing-status change at
# first death, and no widowhood expense reduction. Plan-until-age is used only
# as a fixed simulation-length cutoff, not as a mortality assumption.
PLAN_UNTIL_AGE = 95
PARTNER_PLAN_UNTIL_AGE = None

# Partner's own retirement age (independent of the primary user's, which arrives
# as the ``retirement_age`` argument to the engine). ``None`` means "the partner
# retires the same year the primary does" -- i.e. the household-wide single switch
# used everywhere before this feature existed, so leaving it None reproduces the
# original results byte-for-byte. Set it (via the UI slider or an override) to let
# the partner keep earning + contributing after the primary retires, or stop
# earning before the primary retires. Expressed in the PARTNER's own age.
PARTNER_RETIREMENT_AGE = None

# While the partner keeps working after the primary retires, the household is on
# the partner's employer health plan: no marketplace premium or out-of-pocket is
# charged. The payroll premium belongs in the living-expense base (e.g. the
# partner's own spending line). Medicare for a 65+ primary is unaffected.
PARTNER_EMPLOYER_HEALTH_COVERAGE = True

# -----------------------------------------------------------------------------
# CURRENT ASSETS
# -----------------------------------------------------------------------------
# Defaults: median US 25-year-old household. Sources: Federal Reserve SCF 2022
# (median net worth under 35: ~$39k), Vanguard "How America Saves" (median
# 401k balance age 25-34: ~$14k), BLS Consumer Expenditure Survey.
# Combined household net worth at simulation start: ~$35,000.

# Primary user's accounts
YOUR_401K = 10_000
YOUR_ROTH_IRA = 3_500
YOUR_TRADITIONAL_IRA = 0
YOUR_HSA = 500
YOUR_BROKERAGE = 2_500
YOUR_CASH = 4_000

# Partner's accounts
PARTNER_401K = 7_000
PARTNER_ROTH_IRA = 2_500
PARTNER_BROKERAGE = 1_000
PARTNER_CASH = 3_000

# Primary residence — default is RENTER (most 25-year-olds rent; homeownership
# rate under 25 is ~35%). Set HOME_VALUE and MORTGAGE_BALANCE to nonzero
# values if the household owns.
HOME_VALUE = 0
MORTGAGE_BALANCE = 0
HOME_EQUITY = HOME_VALUE - MORTGAGE_BALANCE

# What % of home equity is accessible in an emergency (net of selling costs,
# capital-gains tax on the gain over the $500k MFJ exclusion, moving costs,
# etc.). 85% is a reasonable default.
HOME_EQUITY_ACCESSIBLE_PCT = 0.85

# -----------------------------------------------------------------------------
# PRIMARY USER INCOME - DETAILED PROJECTIONS
# -----------------------------------------------------------------------------
# Defaults: median US worker starting at $45k at age 25, growing at ~3%/year
# (BLS Current Population Survey: median weekly earnings age 25-34 ≈ $1,046,
# rising to ~$1,250 at age 45-54). No bonuses or RSUs by default (these
# appear in a minority of jobs).
#
# Format per age: {base, bonus, rsu_gross, total_comp, after_tax, saved}
#   - base       : W-2 base salary
#   - bonus      : annual cash bonus
#   - rsu_gross  : gross value of vesting RSUs
#   - total_comp : sum of the three (for reference)
#   - after_tax  : take-home pay after federal + state + payroll taxes
#   - saved      : portion of after_tax that is saved (brokerage + ESPP +
#                  backdoor Roth). Excludes 401k and HSA (those are pre-tax).
YOUR_COMPENSATION_BY_AGE = {
    25: {"base": 45_000, "bonus": 0, "rsu_gross": 0, "total_comp": 45_000, "after_tax": 36_000, "saved": 2_000},
    26: {"base": 46_400, "bonus": 0, "rsu_gross": 0, "total_comp": 46_400, "after_tax": 37_100, "saved": 2_200},
    27: {"base": 47_800, "bonus": 0, "rsu_gross": 0, "total_comp": 47_800, "after_tax": 38_200, "saved": 2_400},
    28: {"base": 49_200, "bonus": 0, "rsu_gross": 0, "total_comp": 49_200, "after_tax": 39_300, "saved": 2_600},
    29: {"base": 50_700, "bonus": 0, "rsu_gross": 0, "total_comp": 50_700, "after_tax": 40_500, "saved": 2_800},
    30: {"base": 52_200, "bonus": 0, "rsu_gross": 0, "total_comp": 52_200, "after_tax": 41_700, "saved": 3_000},
    32: {"base": 55_400, "bonus": 0, "rsu_gross": 0, "total_comp": 55_400, "after_tax": 44_200, "saved": 3_400},
    35: {"base": 60_500, "bonus": 0, "rsu_gross": 0, "total_comp": 60_500, "after_tax": 48_200, "saved": 4_000},
    38: {"base": 66_100, "bonus": 0, "rsu_gross": 0, "total_comp": 66_100, "after_tax": 52_600, "saved": 4_500},
    40: {"base": 70_100, "bonus": 0, "rsu_gross": 0, "total_comp": 70_100, "after_tax": 55_700, "saved": 4_800},
}

# Beyond the last age in the table, project forward with these growth rates.
YOUR_SALARY_GROWTH_RATE = 0.02  # 2% real growth (modest for median worker)
YOUR_BONUS_PCT = 0.00           # Most median jobs don't pay bonuses
YOUR_RSU_PCT = 0.00             # RSUs are concentrated in tech/executive roles

# Primary user's contribution rates
# Median 401k participant contributes ~6-7% of salary per Vanguard data.
# At $45k salary, 6% = $2,700. Employer match median ~4%.
YOUR_401K_CONTRIBUTION = 2_700  # ~6% of starting salary (typical median)
YOUR_401K_MATCH_PCT = 0.04       # Employer matches 100% up to this % of base
# HSA - most workers don't have / fund an HSA; defaults are 0.
YOUR_HSA_CONTRIBUTION = 0
YOUR_HSA_MATCH = 0
YOUR_HSA_TOTAL = YOUR_HSA_CONTRIBUTION + YOUR_HSA_MATCH
YOUR_BACKDOOR_ROTH = 0           # Not needed at this income level
YOUR_BROKERAGE_CONTRIBUTION = 0  # Annual after-tax savings to taxable brokerage
# Mega backdoor Roth: fraction of BASE salary contributed as after-tax 401(k),
# then converted in-plan to Roth (tax-free growth). The engine caps it at the
# 415(c) total-additions room (after employee deferral + employer match) and
# funds it from take-home, reallocating savings from taxable brokerage into Roth.
# 0.0 = off (no after-tax 401k) -> byte-identical to pre-feature behavior.
YOUR_AFTER_TAX_401K_PCT = 0.0

# Expense-sharing for brokerage attribution (results-neutral except a small LTCG
# timing effect). False (default) = the couple splits ALL living expenses evenly,
# each banking their own remainder in their own brokerage. True = the PRIMARY
# covers the full mortgage/housing and only the REST is split evenly (car
# purchases are a separate household lump-sum outflow, unaffected either way).
PRIMARY_PAYS_HOUSING = False
# Income breakdown (today's $ — UI Income Summary fields)
YOUR_BASE_SALARY = 45_000  # matches YOUR_COMPENSATION_BY_AGE[25]['base'] (median-worker persona)
YOUR_BONUS_AMOUNT = 0
YOUR_RSU_AMOUNT = 0
YOUR_OTHER_INCOME = 0
YOUR_ESPP_PCT = 0.00             # ESPP is rare outside public tech companies
YOUR_ESPP_DISCOUNT = 0.00

# -----------------------------------------------------------------------------
# INFLATION-ADJUSTED CONTRIBUTION LIMITS
# -----------------------------------------------------------------------------
# Base year limits (2024) - these get adjusted for inflation over time.
CONTRIBUTION_LIMITS_2024 = {
    '401k': 23_000,
    '401k_total': 69_000,   # 415(c) total additions limit: employee + employer + after-tax
    '401k_catchup': 7_500,  # Additional for age 50+
    'ira': 7_000,
    'ira_catchup': 1_000,   # Additional for age 50+
    'hsa_family': 8_300,
    'hsa_individual': 4_150,
    'hsa_catchup': 1_000,   # Additional for age 55+
}

# IRS typically adjusts limits in ~$500 increments for inflation. In the model's
# ALL-REAL (today's-dollars) frame, general inflation does not grow any nominal
# quantity, and IRS limits are indexed to CPI -- so in real terms they are held
# constant at their 2024 values (real-excess growth of contribution limits is ~0).
CONTRIBUTION_LIMIT_INFLATION_RATE = 0.0

def get_inflation_adjusted_limit(limit_type: str, years_from_2024: int) -> float:
    """
    Calculate inflation-adjusted contribution limit.

    Args:
        limit_type: Type of limit ('401k', 'ira', 'hsa_family', etc.)
        years_from_2024: Number of years from 2024

    Returns:
        Inflation-adjusted limit rounded to nearest $500 (like IRS does)

    """
    if limit_type not in CONTRIBUTION_LIMITS_2024:
        return 0

    base_limit = CONTRIBUTION_LIMITS_2024[limit_type]

    # No adjustment to make -> return the statutory base UNROUNDED. Rounding an
    # unadjusted limit corrupts the two that aren't $500 multiples (hsa_family
    # 8,300 -> 8,500, letting a family HSA be funded $200/yr over the legal max;
    # hsa_individual 4,150 -> 4,000, truncating a legal contribution).
    if years_from_2024 == 0 or CONTRIBUTION_LIMIT_INFLATION_RATE == 0:
        return base_limit

    adjusted = base_limit * ((1 + CONTRIBUTION_LIMIT_INFLATION_RATE) ** years_from_2024)

    # Round to nearest $500 (IRS convention)
    return round(adjusted / 500) * 500

def get_401k_limit(your_age: int, year: int) -> float:
    """Get 401k contribution limit for a given year and age."""
    years_from_2024 = year - 2024
    base_limit = get_inflation_adjusted_limit('401k', years_from_2024)
    if your_age >= 50:
        base_limit += get_inflation_adjusted_limit('401k_catchup', years_from_2024)
    return base_limit

def get_ira_limit(your_age: int, year: int) -> float:
    """Get IRA contribution limit for a given year and age."""
    years_from_2024 = year - 2024
    base_limit = get_inflation_adjusted_limit('ira', years_from_2024)
    if your_age >= 50:
        base_limit += get_inflation_adjusted_limit('ira_catchup', years_from_2024)
    return base_limit


def get_401k_total_limit(your_age: int, year: int) -> float:
    """415(c) total 401(k) additions limit (employee deferral + employer match +
    after-tax) for a given year/age. The 'mega backdoor Roth' after-tax room is
    this limit minus the employee deferral and the employer match."""
    years_from_2024 = year - 2024
    base_limit = get_inflation_adjusted_limit('401k_total', years_from_2024)
    if your_age >= 50:
        base_limit += get_inflation_adjusted_limit('401k_catchup', years_from_2024)
    return base_limit

def get_hsa_limit(your_age: int, year: int, is_family: bool = True) -> float:
    """Get HSA contribution limit for a given year and age."""
    years_from_2024 = year - 2024
    limit_type = 'hsa_family' if is_family else 'hsa_individual'
    base_limit = get_inflation_adjusted_limit(limit_type, years_from_2024)
    if your_age >= 55:
        base_limit += get_inflation_adjusted_limit('hsa_catchup', years_from_2024)
    return base_limit

# Flat STATE income tax rate for STATE_CHOICE "Other" -- its only use (the
# engine's FlatRateStateTax and derived.compute_taxes). It used to default to
# 0.22, a federal + state + FICA "next dollar" estimate, which charged every
# "Other" state a 22% state income tax.
YOUR_MARGINAL_TAX_RATE = 0.05

# State of residence for state income tax modeling. One of:
#   "CA"           -> California 2024 progressive brackets (CaliforniaTaxBrackets)
#   "No state tax" -> no state income tax (e.g. TX, FL) -> NoStateTax
#   "Other"        -> flat rate applied at YOUR_MARGINAL_TAX_RATE (FlatRateStateTax)
STATE_CHOICE = "CA"

# -----------------------------------------------------------------------------
# COMPLETE SAVINGS CALCULATION
# -----------------------------------------------------------------------------
# Primary user's total annual savings includes:
# - 401k contribution + employer match
# - HSA contribution + employer match
# - Backdoor Roth
# - ESPP
# - Remaining to brokerage (from "saved after living expenses")

def calculate_your_total_savings(age: int) -> float:
    """Calculate primary user's TOTAL savings including all tax-advantaged accounts."""
    if age in YOUR_COMPENSATION_BY_AGE:
        comp = YOUR_COMPENSATION_BY_AGE[age]
        base_salary = comp['base']
        saved_to_taxable = comp['saved']  # After-tax savings to brokerage/ESPP/Roth

        # Add pre-tax savings that aren't in the "saved" number
        total = (
            saved_to_taxable +           # Brokerage, ESPP, Backdoor Roth
            YOUR_401K_CONTRIBUTION +      # Your 401k
            base_salary * YOUR_401K_MATCH_PCT +  # 401k match
            YOUR_HSA_TOTAL                # HSA (you + employer)
        )
        return total
    else:
        # Beyond the table, project forward with salary growth rate.
        last_known_age = max(YOUR_COMPENSATION_BY_AGE.keys())
        last_known = calculate_your_total_savings(last_known_age)
        years_beyond = age - last_known_age
        return last_known * ((1 + YOUR_SALARY_GROWTH_RATE) ** years_beyond)

# -----------------------------------------------------------------------------
# PARTNER INCOME
# -----------------------------------------------------------------------------
# Default: median US 25-year-old individual income ~$42,000 (slightly below
# primary user to reflect typical spread in partner earnings).
PARTNER_SALARY = 42_000
PARTNER_SALARY_GROWTH_RATE = 0.02  # Modest real wage growth

# Partner's contributions
PARTNER_401K_CONTRIBUTION = 2_500  # ~6% of salary (median contribution)
PARTNER_401K_MATCH = 0             # Many jobs have no match
PARTNER_ROTH_CONTRIBUTION = 2_000  # Direct Roth (income below MFJ phase-out)
PARTNER_BROKERAGE_CONTRIBUTION = 0 # Annual partner after-tax savings to brokerage

# -----------------------------------------------------------------------------
# SAVINGS ALLOCATION MODE
# -----------------------------------------------------------------------------
# Controls how each working year's after-tax income is invested. These are
# REAL module attributes (not just UI keys) so UI overrides reach the engine
# via sim_runner._apply_overrides (which only sets attrs that already exist on
# the config module).
#   - "Auto-allocate (recommended)"  (SAVINGS_MODE.startswith("Auto")): each
#     working year sweeps ALL un-spent after-tax income into the taxable
#     brokerage (household after-tax income - living expenses - after-tax
#     electives). The flat *_BROKERAGE_CONTRIBUTION knobs act as a FLOOR.
#   - Any other value ("Manual", etc.): keep the legacy flat-override behavior
#     (invest exactly YOUR/PARTNER_BROKERAGE_CONTRIBUTION, no surplus sweep).
SAVINGS_MODE = "Auto-allocate (recommended)"
# In the all-real (today's-dollars) auto sweep this flag is inherently
# subsumed: income already grows in real terms via YOUR_COMPENSATION_BY_AGE and
# the partner salary growth rate, so the swept residual scales up on its own.
# Kept as a real attribute only so the UI override plumbs through cleanly.
SAVINGS_INFLATION_ADJUST = True
# Partner income breakdown (today's $)
PARTNER_BASE_SALARY = 42_000
PARTNER_BONUS_AMOUNT = 0
PARTNER_RSU_AMOUNT = 0
PARTNER_OTHER_INCOME = 0

# Partner's spending and taxes
# FOOTGUN: there are TWO independent partner-spend knobs in this file that are
# NOT wired together - changing one does not change the other:
#   - PARTNER_MONTHLY_SPENDING (below): consumed only by
#     calculate_partner_total_savings() to net partner's own savings/brokerage
#     contribution (partner's personal budget math).
#   - PARTNER_OTHER_MONTHLY (below, in DETAILED EXPENSE MODELING): consumed by
#     granular_nonhousing_annual() / CURRENT_ANNUAL_EXPENSES /
#     BASE_RETIREMENT_EXPENSES_NO_MORTGAGE to add partner's spending into the
#     household expense totals the engine actually simulates against.
# If you intend to change "how much the partner spends," you likely need to
# update BOTH constants to keep them consistent.
PARTNER_MONTHLY_SPENDING = 1_500
PARTNER_ANNUAL_SPENDING = PARTNER_MONTHLY_SPENDING * 12
PARTNER_ESTIMATED_TAX_RATE = 0.20  # Effective rate for median income single/MFJ

def calculate_partner_total_savings(salary: float, years_from_now: int, married: bool = False) -> float:
    """
    Calculate partner's TOTAL annual savings including 401k.

    Partner's Roth contribution drops to 0 once married due to joint-income
    MAGI limits (assumes the couple is over the phase-out); override by
    adjusting PARTNER_ROTH_CONTRIBUTION or the backdoor-Roth logic.
    """
    # 401k is always contributed (pre-tax)
    savings_401k = PARTNER_401K_CONTRIBUTION

    # Calculate after-tax savings
    taxable_income = salary - PARTNER_401K_CONTRIBUTION
    taxes = taxable_income * PARTNER_ESTIMATED_TAX_RATE
    after_tax = taxable_income - taxes

    # Roth contribution (only before marriage in this example model)
    roth = 0 if married else PARTNER_ROTH_CONTRIBUTION

    # What goes to brokerage after spending
    to_brokerage = max(0, after_tax - roth - PARTNER_ANNUAL_SPENDING)

    # Total savings = 401k + Roth + brokerage
    return savings_401k + roth + to_brokerage

# -----------------------------------------------------------------------------
# DETAILED EXPENSE MODELING
# -----------------------------------------------------------------------------

# Current monthly expenses (defaults: median 25-year-old renter household)
# Median asking rent for a 1-bedroom in the US: ~$1,500/mo. Split between two
# earners in shared living. No mortgage at simulation start (most 25yos rent).
MORTGAGE_MONTHLY = 0
MORTGAGE_ANNUAL = MORTGAGE_MONTHLY * 12
MORTGAGE_YEARS_REMAINING = 0  # No mortgage at start

UTILITIES_MONTHLY = 150
UTILITIES_ANNUAL = UTILITIES_MONTHLY * 12

# Monthly rent for RENTERS (no home, no mortgage). Layered into living expenses
# by ``rent_annual()`` / ``calculate_annual_expenses`` so a renter's housing cost
# is not silently dropped. Owners (HOME_VALUE > 0 or MORTGAGE_MONTHLY > 0) use the
# mortgage term instead and this is ignored. Real cfg attribute (finding #6) so
# the UI's "Monthly rent" slider reaches the engine instead of being dropped by
# the hasattr() gate in sim_runner._apply_overrides.
SPEND_RENT_MONTHLY = 0

# Property tax + homeowners insurance, as an annual fraction of the CURRENT
# home's value (HOME_VALUE; NEW_HOME_VALUE after a house move). MORTGAGE_MONTHLY
# and NEW_MORTGAGE_MONTHLY are ALL-IN payments that already bundle this escrow,
# so it is charged ONLY in years the household owns a home but makes no mortgage
# payment (loan paid off, or never had one). Left out, housing fell to $0 at
# payoff although tax + insurance continue for life. Flat in real (today's)
# dollars like the rest of the housing term. Same 1.35% default as the UI's
# NEW_HOME_ESCROW_PCT, which config_builder translates onto this key so one
# input drives both. Renters are unaffected (home value 0).
# Set MODEL_HOME_CARRYING_COST_AFTER_PAYOFF False to reproduce the pre-fix
# behaviour.
HOME_CARRYING_COST_PCT = 0.0135
MODEL_HOME_CARRYING_COST_AFTER_PAYOFF = True

# Primary user's share of household living expenses (rent, food, lifestyle).
# ~$900 half-share of rent + ~$500 food + ~$600 other = ~$2,000/mo.
YOUR_OTHER_MONTHLY = 2_000
YOUR_OTHER_ANNUAL = YOUR_OTHER_MONTHLY * 12

# FOOTGUN: this is the OTHER independent partner-spend knob (see
# PARTNER_MONTHLY_SPENDING above for the full explanation). This one - not
# PARTNER_MONTHLY_SPENDING - is what actually feeds CURRENT_ANNUAL_EXPENSES,
# BASE_RETIREMENT_EXPENSES_NO_MORTGAGE, and granular_nonhousing_annual(), i.e.
# the household expense totals the simulation engine consumes.
PARTNER_OTHER_MONTHLY = 1_500
# Note: Partner's personal spending is already captured in the partner savings
# calculation above, so it contributes to CURRENT_ANNUAL_EXPENSES only once.

# -----------------------------------------------------------------------------
# GRANULAR NON-HOUSING SPENDING CATEGORIES (preferred source of truth)
# -----------------------------------------------------------------------------
# These six monthly categories are what the UI's Expenses section lets the user
# edit directly. When ANY of them is set (non-None), the engine derives BOTH the
# current and retirement non-housing living-expense totals from their sum
# (x12) + partner spending, superseding the legacy YOUR_OTHER_MONTHLY /
# UTILITIES_MONTHLY bundle. When they are all left at None the engine falls back
# to the legacy keys so nothing else breaks.
#
# Housing (mortgage / rent) is handled separately and is NOT part of this base.
SPEND_UTILITIES_MONTHLY = None
SPEND_FOOD_MONTHLY = None
SPEND_TRANSPORT_MONTHLY = None
SPEND_HEALTH_MONTHLY = None
SPEND_DISCRETIONARY_MONTHLY = None
SPEND_OTHER_MONTHLY = None

# Order matters only for readability; membership drives the "present" check.
_GRANULAR_SPEND_KEYS = (
    "SPEND_UTILITIES_MONTHLY",
    "SPEND_FOOD_MONTHLY",
    "SPEND_TRANSPORT_MONTHLY",
    "SPEND_HEALTH_MONTHLY",
    "SPEND_DISCRETIONARY_MONTHLY",
    "SPEND_OTHER_MONTHLY",
)


def granular_nonhousing_annual():
    """Return the annual non-housing living-expense base from the granular
    SPEND_* categories, or ``None`` when no granular category is present.

    Base = sum(six SPEND_* monthly categories) * 12 + partner spending * 12.

    Housing (mortgage/rent) is intentionally excluded; it is layered on
    separately by ``calculate_annual_expenses`` and CURRENT_ANNUAL_EXPENSES.
    Partner spending mirrors the legacy formula's PARTNER_OTHER_MONTHLY term so
    the household total stays complete. Returns ``None`` when every granular
    category is unset (None) so callers can fall back to the legacy keys.
    """
    present = [globals().get(k) for k in _GRANULAR_SPEND_KEYS]
    if all(v is None for v in present):
        return None
    monthly = sum(float(v) for v in present if v is not None)
    return monthly * 12 + PARTNER_OTHER_MONTHLY * 12


# Total current expenses (includes partner's personal spending so the
# household total is complete). Prefers the granular SPEND_* categories when
# present; falls back to the legacy YOUR_OTHER / UTILITIES bundle otherwise.
_granular_current = granular_nonhousing_annual()
CURRENT_ANNUAL_EXPENSES = (
    MORTGAGE_ANNUAL + _granular_current
    if _granular_current is not None
    else (
        MORTGAGE_ANNUAL
        + UTILITIES_ANNUAL
        + YOUR_OTHER_ANNUAL
        + (PARTNER_OTHER_MONTHLY * 12)
    )
)

# -----------------------------------------------------------------------------
# LIFE EVENTS - CHILDREN
# -----------------------------------------------------------------------------
# One entry per child; an empty list is a child-free household. Each child:
#   years_until_birth    years from now until the child is born; negative =
#                        already born (-5 is a 5-year-old today)
#   monthly_cost         what the child costs each month while living at home
#                        (today's dollars; grows with the childcare factor)
#   leaves_home_age      the child's age when those costs stop
#   college_annual_cost  one year of college (today's dollars)
#   college_years        years of college, starting at COLLEGE_START_AGE
#   college_funding_pct  share of college you pay (0-1), saved in the child's own
#                        529 from birth and then spent from it. 0 = none.
# A field left out takes its CHILD_DEFAULTS value. Defaults: two children, born
# in 3 and 6 years (median age at first birth in the US is ~27-28), $2,100/mo
# for the first and $1,400/mo more for the second, no college funding.
CHILD_DEFAULTS = {
    "years_until_birth": 0,
    "monthly_cost": 0,
    "leaves_home_age": 18,
    "college_annual_cost": 40_000,
    "college_years": 4,
    "college_funding_pct": 0.0,
}
CHILDREN = [
    {"years_until_birth": 3, "monthly_cost": 2_100, "leaves_home_age": 18,
     "college_annual_cost": 40_000, "college_years": 4, "college_funding_pct": 0.0},
    {"years_until_birth": 6, "monthly_cost": 1_400, "leaves_home_age": 18,
     "college_annual_cost": 40_000, "college_years": 4, "college_funding_pct": 0.0},
]

# College starts at this age for every child; 529 saving runs from birth to it.
COLLEGE_START_AGE = 18


def _child(child: dict, field: str):
    """One field of a child entry, CHILD_DEFAULTS filling any gap."""
    value = child.get(field)
    return CHILD_DEFAULTS[field] if value is None else value


def child_birth_ages() -> list:
    """Each child's birth age, in the PRIMARY's age terms (CHILDREN order)."""
    return [YOUR_AGE + _child(c, "years_until_birth") for c in CHILDREN]


def children_at_home_ages(your_age: int) -> list:
    """Ages of the children living at home when the primary is ``your_age``.

    Same rule calculate_child_expenses encodes: each child is in the household
    from birth until their leaves_home_age. Empty for a child-free household
    and after every child has left.
    """
    years = your_age - YOUR_AGE
    ages = []
    for c in CHILDREN:
        age = years - _child(c, "years_until_birth")
        if 0 <= age < _child(c, "leaves_home_age"):
            ages.append(age)
    return ages


def calculate_child_expenses(your_age: int) -> float:
    """Annual cost of the children living at home when the primary is
    ``your_age``: each child's monthly_cost x 12, from birth until they leave."""
    years = your_age - YOUR_AGE
    total = 0.0
    for c in CHILDREN:
        age = years - _child(c, "years_until_birth")
        if 0 <= age < _child(c, "leaves_home_age"):
            total += _child(c, "monthly_cost") * 12
    return total


def normalize_children(raw) -> list:
    """A clean copy of a children list: dict entries only, every field present."""
    if not isinstance(raw, (list, tuple)):
        return []
    return [{k: _child(c, k) for k in CHILD_DEFAULTS} for c in raw if isinstance(c, dict)]


# Older profiles described at most two children with the keys below (values =
# what the old config defaulted to). legacy_children() turns them into the
# equivalent CHILDREN list -- the second child costs what "both children" added
# over the first -- so an old profile gives the same results as before.
LEGACY_CHILD_KEYS = {
    "YEARS_UNTIL_FIRST_CHILD": 3,
    "YEARS_BETWEEN_CHILDREN": 3,
    "FIRST_CHILD_MONTHLY_COST": 2_100,
    "BOTH_CHILDREN_MONTHLY_COST": 3_500,
    "CHILD_LEAVES_HOME_AGE": 18,
    "COLLEGE_FUNDING_PCT": 0.0,
    "COLLEGE_ANNUAL_COST": 40_000,
    "COLLEGE_YEARS": 4,
}
# Old keys that were derived from the ones above (always recomputed, so a stored
# value never mattered), and the old "years until first child" that meant none.
_LEGACY_CHILD_DERIVED = ("FIRST_CHILD_ANNUAL_COST", "BOTH_CHILDREN_ANNUAL_COST",
                         "COLLEGE_TARGET_PER_CHILD", "SAVINGS_529_PER_CHILD_ANNUAL")
_LEGACY_NO_CHILDREN = 99


def legacy_children(values: dict) -> list:
    """The CHILDREN list equivalent to the old two-child keys in ``values``."""
    v = {k: (d if values.get(k) is None else values[k]) for k, d in LEGACY_CHILD_KEYS.items()}
    first = v["YEARS_UNTIL_FIRST_CHILD"]
    if first >= _LEGACY_NO_CHILDREN:
        return []
    shared = {"leaves_home_age": v["CHILD_LEAVES_HOME_AGE"],
              "college_annual_cost": v["COLLEGE_ANNUAL_COST"],
              "college_years": v["COLLEGE_YEARS"],
              "college_funding_pct": v["COLLEGE_FUNDING_PCT"]}
    one, both = v["FIRST_CHILD_MONTHLY_COST"], v["BOTH_CHILDREN_MONTHLY_COST"]
    return [
        {"years_until_birth": first, "monthly_cost": one, **shared},
        {"years_until_birth": first + v["YEARS_BETWEEN_CHILDREN"],
         "monthly_cost": max(0, both - one), **shared},
    ]


def children_in(values: dict) -> list:
    """The children an overrides dict describes: its CHILDREN, else its old
    two-child keys, else this config's CHILDREN. Always a fresh, clean list."""
    if values.get("CHILDREN") is not None:
        return normalize_children(values["CHILDREN"])
    if any(k in values for k in LEGACY_CHILD_KEYS):
        return legacy_children(values)
    return normalize_children(CHILDREN)


def migrate_legacy_overrides(values: dict) -> dict:
    """``values`` updated to today's keys, so an old saved profile still loads
    and gives the same results: the two-child keys become CHILDREN (a CHILDREN
    entry already there wins) and the retired wedding flag is dropped. Returns
    ``values`` itself when there is nothing to change."""
    stale = [k for k in (*LEGACY_CHILD_KEYS, *_LEGACY_CHILD_DERIVED, "YEARS_UNTIL_WEDDING")
             if k in values]
    if not stale:
        return values
    out = {k: v for k, v in values.items() if k not in stale}
    if "CHILDREN" not in out and any(k in values for k in (*LEGACY_CHILD_KEYS,
                                                           *_LEGACY_CHILD_DERIVED)):
        out["CHILDREN"] = legacy_children(values)
    return out

# -----------------------------------------------------------------------------
# 529 COLLEGE SAVINGS
# -----------------------------------------------------------------------------
# Per child, opt-in through college_funding_pct: the household saves that share
# of college_annual_cost x college_years into the child's own 529, spread evenly
# from birth to COLLEGE_START_AGE, then pays that share of each college year from
# it (the household budget covers anything the 529 can't).


def college_target(child: dict) -> float:
    """The part of this child's college the household pays (today's dollars)."""
    return (_child(child, "college_annual_cost") * _child(child, "college_years")
            * _child(child, "college_funding_pct"))


def child_529_contributions(your_age: int) -> list:
    """This year's 529 saving for each child (CHILDREN order): the child's
    college_target spread evenly from birth until COLLEGE_START_AGE."""
    years = your_age - YOUR_AGE
    return [college_target(c) / COLLEGE_START_AGE
            if 0 <= years - _child(c, "years_until_birth") < COLLEGE_START_AGE else 0.0
            for c in CHILDREN]


def calculate_529_contribution(your_age: int) -> float:
    """Total 529 saving this year, across all children."""
    return sum(child_529_contributions(your_age))


def calculate_college_expenses(your_age: int) -> dict:
    """This year's college bill the household pays, per child.

    Returns ``{'child1': ..., 'child2': ..., 'total': ...}``: one key per child in
    CHILDREN order (matching the engine's ``childN_529`` accounts) plus the sum.
    College runs from COLLEGE_START_AGE for the child's college_years.
    """
    years = your_age - YOUR_AGE
    expenses = {}
    for i, c in enumerate(CHILDREN, 1):
        age = years - _child(c, "years_until_birth")
        cost = 0.0
        if COLLEGE_START_AGE <= age < COLLEGE_START_AGE + _child(c, "college_years"):
            cost = _child(c, "college_annual_cost") * _child(c, "college_funding_pct")
        expenses[f"child{i}"] = cost
    expenses["total"] = sum(expenses.values())
    return expenses

def has_mortgage(your_age: int) -> bool:
    """Check if mortgage is still being paid."""
    mortgage_payoff_age = YOUR_AGE + MORTGAGE_YEARS_REMAINING
    return your_age < mortgage_payoff_age


def is_renter() -> bool:
    """True when the household rents (no home value AND no mortgage payment).

    Renters have no mortgage term in the expense model, so their housing cost
    (SPEND_RENT_MONTHLY) must be layered on separately — otherwise it is
    silently dropped (finding #6). Owners are modeled via the mortgage term.
    """
    home_value = float(globals().get("HOME_VALUE", 0) or 0)
    return home_value == 0 and MORTGAGE_MONTHLY == 0


def rent_annual(your_age: int) -> float:
    """Annual rent for a renter, else 0.

    Rent is a constant (today's-dollars) living cost that runs for the whole
    horizon (renters do not "pay off" housing the way owners retire a mortgage).
    Owners return 0 here because their housing is the mortgage term. A planned
    purchase (HOME_EVENTS) ends it: the engine then swaps this whole housing
    term for its own (``AccountPortfolio.housing_expense_for_age``).
    """
    if is_renter():
        return SPEND_RENT_MONTHLY * 12
    return 0.0


def home_carrying_cost_annual(home_value: float) -> float:
    """Annual property tax + insurance on an owned home worth ``home_value``.

    Callers charge this only for years with NO mortgage payment (the all-in
    payment already includes escrow). 0 for renters (value 0) and when
    MODEL_HOME_CARRYING_COST_AFTER_PAYOFF is off.
    """
    if not globals().get("MODEL_HOME_CARRYING_COST_AFTER_PAYOFF", False):
        return 0.0
    return max(0.0, float(home_value or 0)) * HOME_CARRYING_COST_PCT


def owner_housing_annual(your_age: int) -> float:
    """Config-path owner housing at ``your_age``: the all-in mortgage while it is
    being paid, else the carrying cost of HOME_VALUE (no rent).
    """
    if has_mortgage(your_age):
        return MORTGAGE_ANNUAL
    return home_carrying_cost_annual(globals().get("HOME_VALUE", 0))


def housing_annual(your_age: int) -> float:
    """Config-path housing term ``calculate_annual_expenses`` adds at ``your_age``
    (today's dollars): the all-in mortgage while it is being paid, else rent
    (renters) plus the owner's post-payoff carrying cost. Single source for both
    the expense total and the guardrails' fixed housing slice. It describes
    today's home for the whole plan; with a housing timeline the engine replaces
    it year by year with ``AccountPortfolio.housing_expense_for_age``.
    """
    if has_mortgage(your_age):
        return MORTGAGE_ANNUAL
    return rent_annual(your_age) + home_carrying_cost_annual(globals().get("HOME_VALUE", 0))


# -----------------------------------------------------------------------------
# RETIREMENT EXPENSE MODELING
# -----------------------------------------------------------------------------

# Base retirement expenses (today's dollars, EXCLUDING mortgage).
# This is combined "other" spending + utilities for the household. Prefers the
# granular SPEND_* categories when present (so editing them in the UI flows into
# retirement spending); falls back to the legacy YOUR_OTHER / UTILITIES bundle.
BASE_RETIREMENT_EXPENSES_NO_MORTGAGE = (
    granular_nonhousing_annual()
    if granular_nonhousing_annual() is not None
    else (
        YOUR_OTHER_ANNUAL +
        UTILITIES_ANNUAL +
        PARTNER_OTHER_MONTHLY * 12
    )
)

# Healthcare increase in retirement (estimate, used by simple expense model).
HEALTHCARE_INCREASE_ANNUAL = 12_000
MEDICARE_AGE = 65
HEALTHCARE_INCREASE_PRE_MEDICARE = 15_000

# Retirement lifestyle: extra travel/hobby spending in the first years of
# retirement ("go-go years"), then lower day-to-day spending in later years.
# The app's Retirement goals section sets all of these.
#
# Extra $/yr (today's dollars). None = by household size: $10,000 for two
# adults, two-thirds of that for one (shared costs like lodging don't halve).
EARLY_RETIREMENT_LEISURE_INCREASE = None
# The extra lasts from retirement until this age, and at least
# RETIREMENT_LEISURE_MIN_YEARS when you retire late.
EARLY_RETIREMENT_LEISURE_UNTIL_AGE = 70
RETIREMENT_LEISURE_MIN_YEARS = 5
# From this age (at least LATE_RETIREMENT_MIN_YEARS after retiring) living
# spending is LATE_RETIREMENT_LEISURE_DECREASE lower. Housing is not reduced:
# a mortgage or rent doesn't shrink because you travel less.
LATE_RETIREMENT_LEISURE_DECREASE = 0.15
LATE_RETIREMENT_START_AGE = 75
LATE_RETIREMENT_MIN_YEARS = 10
_LEISURE_TWO_ADULTS = 10_000
_LEISURE_ONE_ADULT_SHARE = 2.0 / 3.0

# Legacy name for notebook compatibility
LATE_RETIREMENT_EXPENSE_REDUCTION = LATE_RETIREMENT_LEISURE_DECREASE


def default_retirement_leisure(adults: int) -> float:
    """The go-go extra used when none is set, for a household of ``adults``."""
    return _LEISURE_TWO_ADULTS * (1.0 if adults >= 2 else _LEISURE_ONE_ADULT_SHARE)


def retirement_leisure_increase() -> float:
    """Extra early-retirement spending per year (today's dollars)."""
    if EARLY_RETIREMENT_LEISURE_INCREASE is not None:
        return float(EARLY_RETIREMENT_LEISURE_INCREASE)
    return default_retirement_leisure(2 if has_partner() else 1)


def retirement_leisure_end_age(retirement_age=None) -> int:
    """First age WITHOUT the go-go extra. ``None`` = the plain age rule."""
    end = int(EARLY_RETIREMENT_LEISURE_UNTIL_AGE)
    if retirement_age is not None:
        end = max(end, int(retirement_age) + int(RETIREMENT_LEISURE_MIN_YEARS))
    return end


def late_retirement_start_age(retirement_age=None) -> int:
    """First age with the later-years spending reduction."""
    start = int(LATE_RETIREMENT_START_AGE)
    if retirement_age is not None:
        start = max(start, int(retirement_age) + int(LATE_RETIREMENT_MIN_YEARS))
    return start

# -----------------------------------------------------------------------------
# DYNAMIC SPENDING ADJUSTMENT (Guardrails)
# -----------------------------------------------------------------------------
# In reality, people adjust spending based on portfolio performance.
# This models "guardrails" - reducing discretionary spending when portfolio
# drops, optionally increasing it when the portfolio is well above target.

DYNAMIC_SPENDING_ENABLED = True

# Spending adjustment thresholds (based on portfolio performance vs target).
# Target = initial retirement portfolio adjusted for inflation.
# CONSERVATIVE DEFAULT: Cut when down, NO increase when up.
SPENDING_GUARDRAILS = {
    'floor_trigger': 0.70,      # If portfolio < 70% of target, cut spending
    'floor_reduction': 0.15,    # Cut discretionary by 15%
    'ceiling_trigger': 1.30,    # If portfolio > 130% of target, could spend more
    'ceiling_increase': 0.00,   # NO increase - stay at baseline (conservative)
}

# What portion of NON-HOUSING spending is "discretionary" (can be cut).
# Non-discretionary: utilities, healthcare, basic food (and all housing, below).
# Discretionary: travel, entertainment, dining out, hobbies.
DISCRETIONARY_EXPENSE_RATIO = 0.30

# Housing (mortgage while owed, post-payoff property tax + insurance, or rent)
# can't be cut in a downturn, so it is always in the FIXED part of spending and
# the guardrails only flex DISCRETIONARY_EXPENSE_RATIO x (expenses - housing).
# A single ratio of TOTAL spending over-states the cuttable slice in big-mortgage
# years and under-states it after payoff. Set False to reproduce the pre-fix
# behaviour (ratio applied to total expenses, housing included).
MODEL_GUARDRAILS_EXCLUDE_HOUSING = True

# Bounds on the combined (portfolio x return-based) multiplier applied to the
# discretionary slice: it never falls below MIN or rises above MAX of baseline
# discretionary spending.
GUARDRAIL_MIN_DISCRETIONARY_FACTOR = 0.60
GUARDRAIL_MAX_DISCRETIONARY_FACTOR = 1.40

# -----------------------------------------------------------------------------
# RETURN-BASED SPENDING ADJUSTMENT
# -----------------------------------------------------------------------------
# Adjust discretionary spending based on current year's market returns.
# Good years = spend more on travel/entertainment.
# Bad years = cut back on discretionary spending.
# Applied IN ADDITION to the portfolio-based guardrails above.

RETURN_BASED_SPENDING_ENABLED = True

# Return thresholds and spending adjustments.
# CONSERVATIVE DEFAULT: Cut in down years, NO increase in up years.
RETURN_BASED_SPENDING_RULES = {
    'excellent_return_threshold': 0.15,   # Returns >= 15%
    'excellent_spending_boost': 0.00,     # NO boost - stay at baseline

    'good_return_threshold': 0.08,        # Returns >= 8%
    'good_spending_boost': 0.00,          # NO boost - stay at baseline

    'poor_return_threshold': 0.00,        # Returns < 0%
    'poor_spending_cut': 0.10,            # Cut discretionary by 10%

    'bad_return_threshold': -0.10,        # Returns < -10%
    'bad_spending_cut': 0.20,             # Cut discretionary by 20%
}

def calculate_return_based_spending_adjustment(annual_return: float) -> float:
    """
    Calculate spending adjustment based on current year's market return.

    This allows for lifestyle flexibility:
    - Great market year? Take that extra vacation.
    - Bad market year? Stay home, cook more, skip the big trip.

    Args:
        annual_return: This year's portfolio return (e.g., 0.12 for 12%)

    Returns:
        Multiplier for discretionary expenses (e.g., 1.20 for +20%, 0.80 for -20%)
    """
    if not RETURN_BASED_SPENDING_ENABLED:
        return 1.0

    rules = RETURN_BASED_SPENDING_RULES

    # Check thresholds from best to worst
    if annual_return >= rules['excellent_return_threshold']:
        adjustment = 1.0 + rules['excellent_spending_boost']
    elif annual_return >= rules['good_return_threshold']:
        adjustment = 1.0 + rules['good_spending_boost']
    elif annual_return < rules['bad_return_threshold']:
        adjustment = 1.0 - rules['bad_spending_cut']
    elif annual_return < rules['poor_return_threshold']:
        adjustment = 1.0 - rules['poor_spending_cut']
    else:
        # Normal year - no adjustment
        adjustment = 1.0

    return adjustment

def calculate_spending_adjustment(current_portfolio: float, target_portfolio: float) -> float:
    """
    Calculate spending adjustment factor based on portfolio performance.

    Returns a multiplier (e.g., 0.95 = reduce spending by 5%).

    """
    if not DYNAMIC_SPENDING_ENABLED or target_portfolio <= 0:
        return 1.0

    ratio = current_portfolio / target_portfolio

    if ratio < SPENDING_GUARDRAILS['floor_trigger']:
        # Portfolio is down significantly - cut discretionary spending
        # Pure discretionary multiplier — the caller (_apply_spending_guardrails)
        # applies this to the DISCRETIONARY SLICE only, so scaling by
        # DISCRETIONARY_EXPENSE_RATIO here applied it twice (a configured 15% cut
        # landed as 1.35% of total spending instead of 4.5%).
        reduction = SPENDING_GUARDRAILS['floor_reduction']
        return 1.0 - reduction

    elif ratio > SPENDING_GUARDRAILS['ceiling_trigger']:
        # Portfolio is up significantly - can spend a bit more
        increase = SPENDING_GUARDRAILS['ceiling_increase']
        return 1.0 + increase

    return 1.0  # No adjustment needed

# Simplified retirement expense constant for basic notebook (uses detailed calc in account_simulation)
RETIREMENT_ANNUAL_EXPENSES = BASE_RETIREMENT_EXPENSES_NO_MORTGAGE

# -----------------------------------------------------------------------------
# RETIREMENT SPENDING MODE (finding #7)
# -----------------------------------------------------------------------------
# How the retirement living base is derived from today's living base:
#   "Same as today's expenses"  -> base unchanged (default; prior behavior)
#   "% of today's expenses"     -> base * RETIREMENT_SPENDING_PCT
#   "Absolute amount ($/yr)"    -> RETIREMENT_SPENDING_ABSOLUTE (overrides base)
# Only the non-housing, non-child LIVING base is affected — mortgage/rent,
# child costs, healthcare and the go-go-years vacation are layered on top as
# before. Real cfg attributes so the UI radio reaches the engine (was dropped
# by the hasattr() gate in sim_runner._apply_overrides).
RETIREMENT_SPENDING_MODE = "Same as today's expenses"
RETIREMENT_SPENDING_PCT = 0.80          # used when mode == "% of today's expenses"
RETIREMENT_SPENDING_ABSOLUTE = 0        # used when mode == "Absolute amount ($/yr)"


def retirement_living_base() -> float:
    """Return the retirement non-housing living base under RETIREMENT_SPENDING_MODE.

    Starts from BASE_RETIREMENT_EXPENSES_NO_MORTGAGE (today's living base) and:
      * "% of today's expenses"  -> scales it by RETIREMENT_SPENDING_PCT
      * "Absolute amount ($/yr)" -> replaces it with RETIREMENT_SPENDING_ABSOLUTE
      * anything else            -> leaves it unchanged ("same as today").
    Housing / child / healthcare / vacation are NOT part of this base; they are
    added separately by ``calculate_annual_expenses`` / the retirement path.
    """
    base = BASE_RETIREMENT_EXPENSES_NO_MORTGAGE
    mode = str(RETIREMENT_SPENDING_MODE)
    if mode.startswith("%"):
        return base * float(RETIREMENT_SPENDING_PCT)
    if mode.startswith("Absolute"):
        return float(RETIREMENT_SPENDING_ABSOLUTE)
    return base


# -----------------------------------------------------------------------------
# SPENDING LIFECYCLE PRESET (finding #11)
# -----------------------------------------------------------------------------
# The UI "lifecycle pattern" preset moves food / discretionary spending by age:
#   travel boom      discretionary +50% from retirement until the go-go years
#                    end (retirement_leisure_end_age), -20% from the later-years
#                    age (late_retirement_start_age);
#   conservative     discretionary -30% from the later-years age;
#   empty-nest       food + discretionary +30% while any child is at home, -25%
#                    once the last one has left (SPEND_EMPTY_NEST_AGE).
# The engine reads the preset NAME and computes the multiplier per year
# (lifecycle_multiplier), because the retirement-relative ages depend on the
# retirement age being simulated. The spending chart uses the same function.
# SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE ({category: {age: multiplier}}) is an
# explicit override for direct engine use; when non-empty it replaces the
# preset. sim_runner clears it so a stale dict in an old profile can't win.
SPEND_LIFECYCLE_PRESET = "Flat (no change)"
SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE = {}

LIFECYCLE_TRAVEL_BOOM = "Early-retirement travel boom, quieter later"
LIFECYCLE_SENIOR = "Conservative senior years"
LIFECYCLE_EMPTY_NEST = "Children then empty-nest"
_LIFECYCLE_CATEGORIES = ("SPEND_FOOD_MONTHLY", "SPEND_DISCRETIONARY_MONTHLY")


def empty_nest_age(start_age=None, end_age=None):
    """First age (yours) after the last child has left home, or None without
    children. Children who left before today count, so a household whose kids
    are grown is an empty nest from the start."""
    start = int(YOUR_AGE if start_age is None else start_age)
    end = int(PLAN_UNTIL_AGE if end_age is None else end_age)
    last = None
    for age in range(start - 60, end + 1):
        if children_at_home_ages(age):
            last = age
    return None if last is None else last + 1


# Derived from the children inputs (sim_runner._recompute_derived recomputes it).
SPEND_EMPTY_NEST_AGE = empty_nest_age()


def lifecycle_multiplier(category: str, your_age: int, retirement_age=None,
                         preset=None, retired: bool = True, kids_at_home=None,
                         empty_nest_from=...) -> float:
    """Multiplier the lifecycle ``preset`` applies to ``category`` at ``your_age``.

    ``retirement_age`` None = unknown: the go-go window then needs ``retired``
    and the later-years age falls back to the plain age rule. ``kids_at_home``
    and ``empty_nest_from`` default to children_at_home_ages / SPEND_EMPTY_NEST_AGE.
    """
    preset = SPEND_LIFECYCLE_PRESET if preset is None else preset
    if preset == LIFECYCLE_EMPTY_NEST:
        if category not in _LIFECYCLE_CATEGORIES:
            return 1.0
        if kids_at_home is None:
            kids_at_home = bool(children_at_home_ages(your_age))
        if kids_at_home:
            return 1.30
        nest = SPEND_EMPTY_NEST_AGE if empty_nest_from is ... else empty_nest_from
        return 0.75 if nest is not None and your_age >= nest else 1.0
    if category != "SPEND_DISCRETIONARY_MONTHLY":
        return 1.0
    later = your_age >= late_retirement_start_age(retirement_age)
    if preset == LIFECYCLE_TRAVEL_BOOM:
        go_go = (retired and your_age < retirement_leisure_end_age(retirement_age)
                 and (retirement_age is None or your_age >= retirement_age))
        return 1.50 if go_go else (0.80 if later else 1.0)
    if preset == LIFECYCLE_SENIOR:
        return 0.70 if later else 1.0
    return 1.0


def lifecycle_spend_delta_annual(your_age: int, inflation_factor: float = 1.0,
                                 retirement_age=None, retired: bool = True) -> float:
    """Annual living-expense delta from the lifecycle preset at ``your_age``.

    For each category the preset touches (food / discretionary), the dollar
    change relative to today's spending:
        sum over categories of  monthly*12 * (multiplier(age) - 1.0)
    A non-empty SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE supplies the multipliers
    instead (missing ages = 1.0). Every other category and the partner base are
    untouched. Scaled by ``inflation_factor`` so it grows in step with the base
    it adjusts.
    """
    mults = SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE
    delta = 0.0
    if mults:
        for category, by_age in mults.items():
            if not by_age:
                continue
            monthly = globals().get(category)
            if monthly is None:
                continue
            multiplier = by_age.get(your_age, by_age.get(int(your_age), 1.0))
            delta += float(monthly) * 12.0 * (float(multiplier) - 1.0)
        return delta * inflation_factor
    preset = SPEND_LIFECYCLE_PRESET
    if preset not in (LIFECYCLE_TRAVEL_BOOM, LIFECYCLE_SENIOR, LIFECYCLE_EMPTY_NEST):
        return 0.0
    kids = bool(children_at_home_ages(your_age)) if preset == LIFECYCLE_EMPTY_NEST else None
    for category in _LIFECYCLE_CATEGORIES:
        monthly = globals().get(category)
        if monthly is None:
            continue
        multiplier = lifecycle_multiplier(category, your_age, retirement_age, preset,
                                          retired, kids_at_home=kids)
        if multiplier != 1.0:
            delta += float(monthly) * 12.0 * (multiplier - 1.0)
    return delta * inflation_factor


def calculate_annual_expenses(
    your_age: int,
    inflation_factor: float = 1.0,
    childcare_factor: float = None,
    retirement: bool = False,
    retirement_age: int = None,
) -> float:
    """
    Calculate total annual expenses for a given age, accounting for:
    - Mortgage (until paid off) or rent (renters)
    - Children (while they're home)
    - Retirement spending mode (retirement years only)
    - Spending lifecycle preset (food/discretionary multipliers by age)
    - Healthcare increases (handled by the simulator, not here)
    - Lifestyle changes in retirement (handled by the simulator)

    General (non-child) expenses are adjusted by ``inflation_factor``. Child-related
    expenses are adjusted by ``childcare_factor`` instead, because childcare outpaces
    general CPI (see INFLATION_RATES / the all-real real-excess convention). When
    ``childcare_factor`` is None it defaults to ``inflation_factor`` so callers that
    only pass one factor keep their previous behavior.

    ``retirement`` selects the retirement living base (RETIREMENT_SPENDING_MODE:
    same / % of today / absolute). Working years pass retirement=False and keep
    today's living base unchanged. ``retirement_age`` places the lifecycle
    preset's retirement-relative ages (None = the plain age rule).
    """
    if childcare_factor is None:
        childcare_factor = inflation_factor

    # Base living expenses (household spending + utilities). In retirement the
    # base is transformed by RETIREMENT_SPENDING_MODE (% / absolute / same).
    base = retirement_living_base() if retirement else BASE_RETIREMENT_EXPENSES_NO_MORTGAGE

    # Housing: mortgage while owning-and-paying, else rent for renters, else
    # (owner, no payment) property tax + insurance. All are today's-dollars
    # terms grown by the general factor alongside ``base``.
    base += housing_annual(your_age)

    # General (non-child) expenses grow with the general factor; child expenses grow
    # with the childcare factor (real-excess over general CPI in the all-real frame).
    total = base * inflation_factor + calculate_child_expenses(your_age) * childcare_factor

    # Spending lifecycle preset: food/discretionary +/- by age (finding #11).
    # Applied as a real dollar delta on the general (inflation-adjusted) side so
    # the engine matches the pattern the spending chart already shows.
    total += lifecycle_spend_delta_annual(your_age, inflation_factor, retirement_age, retirement)

    return total


# -----------------------------------------------------------------------------
# INVESTMENT ASSUMPTIONS
# -----------------------------------------------------------------------------

# Asset allocation - age-appropriate default for a mid-career couple with
# a long accumulation horizon ahead.
STOCK_ALLOCATION = 0.80
BOND_ALLOCATION = 0.20

# -----------------------------------------------------------------------------
# RETURN SCENARIOS
# -----------------------------------------------------------------------------
# Three pre-built return scenarios. Switch between them by setting
# ACTIVE_RETURN_SCENARIO or pass a scenario name into get_return_parameters().

RETURN_SCENARIOS = {
    'conservative': {
        'name': 'Conservative',
        'description': 'Below-historical returns for prudent planning',
        'stock_return': 0.07,   # 7% real
        'bond_return': 0.02,    # 2% real
        'stock_volatility': 0.19,
        'bond_volatility': 0.08,
    },
    'historical': {
        'name': 'Historical Average',
        'description': 'Based on 1926-2024 actual market data',
        'stock_return': 0.087,  # 8.7% real (historical mean)
        'bond_return': 0.031,   # 3.1% real (historical mean)
        'stock_volatility': 0.20,
        'bond_volatility': 0.087,
    },
    'pessimistic': {
        'name': 'Pessimistic',
        'description': 'Lower returns for stress testing',
        'stock_return': 0.05,   # 5% real
        'bond_return': 0.01,    # 1% real
        'stock_volatility': 0.22,
        'bond_volatility': 0.10,
    },
}

# Default scenario for the simulation
ACTIVE_RETURN_SCENARIO = 'historical'

def get_return_parameters(scenario: str = None) -> dict:
    """
    Get return parameters for a given scenario.

    Args:
        scenario: One of 'conservative', 'historical', 'pessimistic'.
                  If None, uses ACTIVE_RETURN_SCENARIO.

    Returns:
        Dict with stock_return, bond_return, stock_volatility, bond_volatility
    """
    if scenario is None:
        scenario = ACTIVE_RETURN_SCENARIO
    if scenario not in RETURN_SCENARIOS:
        scenario = 'conservative'
    return RETURN_SCENARIOS[scenario]

# Expected returns (real, after inflation).
# Using HISTORICAL averages (1926-2024): Stocks 8.7%, Bonds 3.1%.
# The simulation applies a volatility drag adjustment to convert to effective
# geometric returns for compounding.
EXPECTED_STOCK_RETURN = 0.087  # 8.7% real (historical arithmetic mean)
EXPECTED_BOND_RETURN = 0.031   # 3.1% real (historical arithmetic mean)

# Volatility (standard deviation of annual returns).
# Historical (1926-2024): Stocks ~20%, Bonds ~8.7%.
STOCK_VOLATILITY = 0.19
BOND_VOLATILITY = 0.08

# Stock-Bond Correlation.
# Historically ranges from -0.2 to +0.3, averaging around 0.0 to +0.1.
# During crises, correlation often goes negative (flight to safety).
# The modern era (2000-present) has averaged around -0.20 to -0.30.
STOCK_BOND_CORRELATION = -0.20

# Investment fees (annual expense ratio).
# Typical range: 0.03% (broad-index funds) to 0.50% (active 401k funds).
# Default 0% (no fee drag); adjust via the assumptions panel if desired.
INVESTMENT_FEE_RATE = 0.0

# Volatility drag adjustment.
# Geometric return = Arithmetic return - (volatility^2 / 2).
# Applied in the simulation to account for compounding effects.
APPLY_VOLATILITY_DRAG = True

# Inflation - category-specific rates.
EXPECTED_INFLATION = 0.0275
INFLATION_VOLATILITY = 0.015

# Category-specific inflation rates (moderate assumptions).
# Split the difference between conservative (3%/5%) and recent (2.5%/4%).
# Slider semantics: 'general' is the single source of truth for general CPI and is
# derived from EXPECTED_INFLATION (the UI slider), so moving the slider moves it.
# The engine is all-real: the general inflation factor is pinned to 1.0 for liability
# growth, so the slider does NOT rescale liabilities directly. Instead it drives
# (a) healthcare/childcare real-excess growth (= category nominal literal - general),
# and (b) the historical-path single-year deflation. healthcare/childcare stay their
# own nominal literals so raising the slider shrinks their real-excess, lowering it
# widens the gap. Default EXPECTED_INFLATION (0.0275) equals the prior hardcoded
# general rate, so defaults are preserved.
INFLATION_RATES = {
    'general': EXPECTED_INFLATION,  # Slider-driven general CPI (single source of truth)
    'healthcare': 0.045,  # Healthcare-specific inflation
    'childcare': 0.04,    # Childcare costs
    # NOTE: 'housing' was removed. Its nominal rate equaled 'general' (2.75%), so its
    # real-excess rate is 0 and it never grows a liability in the all-real frame. It
    # was never wired into the engine's inflation_factors dicts either. If housing is
    # ever meant to outpace general CPI, add it back here AND thread a housing_factor
    # through calculate_annual_expenses to the base/mortgage component.
}

# -----------------------------------------------------------------------------
# SOCIAL SECURITY
# -----------------------------------------------------------------------------
# Estimated benefits are in TODAY'S dollars (Social Security is inflation-
# adjusted via the COLA, so real benefits remain roughly constant).

SOCIAL_SECURITY_START_AGE = 67      # Full retirement age for those born 1960+
EARLY_SS_AGE = 62                   # Can claim early with ~30% reduction
DELAYED_SS_AGE = 70                 # Maximum delay with ~24% increase

# Estimated monthly benefits at full retirement age (67).
# Defaults: median US career-earner benefits at FRA. The SSA average monthly
# retired-worker benefit is ~$1,900 (2024). Replace with YOUR estimates from
# https://ssa.gov (create a "my Social Security" account for a personalized
# projection based on your actual earnings history).
YOUR_SS_MONTHLY_FRA = 2_000         # Median earner lifetime projection
PARTNER_SS_MONTHLY_FRA = 1_800      # Slightly lower for partner

# If claiming early (age 62): ~70% of FRA amount.
# If claiming late (age 70): ~124% of FRA amount.

def ss_claim_factor(claim_age: int) -> float:
    """Share of the full-retirement-age benefit paid when claiming at
    ``claim_age`` (per SSA rules).

    Early claiming reduction:
    - Months 1-36 early: 5/9 of 1% per month = 6.67% per year
    - Months 37-60 early: 5/12 of 1% per month = 5% per year
    So if claiming at 62 (5 years = 60 months early):
    - First 36 months: 36 * 5/9 * 1% = 20%
    - Next 24 months: 24 * 5/12 * 1% = 10%
    - Total reduction: 30%

    Delayed claiming credit:
    - 8% per year increase for each year delayed past FRA (up to age 70)
    """
    if claim_age < SOCIAL_SECURITY_START_AGE:
        months_early = (SOCIAL_SECURITY_START_AGE - claim_age) * 12
        first_36_reduction = min(months_early, 36) * (5/9) * 0.01
        beyond_36_reduction = max(0, months_early - 36) * (5/12) * 0.01
        return 1 - first_36_reduction - beyond_36_reduction
    if claim_age > SOCIAL_SECURITY_START_AGE:
        return 1 + 0.08 * min(claim_age - SOCIAL_SECURITY_START_AGE, 3)
    return 1.0


def ss_spousal_factor(start_age: float) -> float:
    """Share of the full spousal benefit paid when it starts at ``start_age``:
    25/36 of 1% less per month early for 36 months, 5/12 of 1% beyond, and
    no credit for waiting past full retirement age."""
    months_early = max(0.0, (SOCIAL_SECURITY_START_AGE - start_age) * 12)
    return 1 - min(months_early, 36) * (25/36) * 0.01 - max(0.0, months_early - 36) * (5/12) * 0.01


def calculate_social_security(your_age: int, claim_age: int = 67) -> float:
    """
    Calculate annual Social Security income in today's dollars.

    Args:
        your_age: Current age of primary user in simulation
        claim_age: Age when the PRIMARY's benefit starts (62-70). The partner
            claims at PARTNER_SS_CLAIM_AGE in their own age (None = claim_age).

    Returns:
        Annual SS income for both the primary user and partner (if eligible):
        each person's own benefit (ss_claim_factor) plus, for a MARRIED couple
        (MODEL_SPOUSAL_SS_BENEFIT), the spousal top-up -- a spouse whose own
        benefit is under half of the other's gets the difference once both
        have claimed (ss_spousal_factor; no delayed credit on it).

    LIMITATION: both spouses are assumed alive for the full planning horizon
    (see PLAN_UNTIL_AGE). This function does not model survivor benefits
    (the higher of the two SS benefits continuing alone after a spouse's
    death) because there is no stochastic mortality in this model. Benefits
    are the FRA amounts you enter; they do not change with when you stop work.
    """
    annual_income = 0

    # Primary user's SS
    if your_age >= claim_age:
        annual_income += YOUR_SS_MONTHLY_FRA * ss_claim_factor(claim_age) * 12

    if not has_partner():
        return annual_income

    # Partner's SS (accounting for age difference), at their own claim age
    age_gap = YOUR_AGE - PARTNER_AGE
    partner_age = your_age - age_gap
    partner_claim_age = globals().get("PARTNER_SS_CLAIM_AGE") or claim_age
    partner_monthly_fra = globals().get("PARTNER_SS_MONTHLY_FRA", 0) or 0
    if partner_monthly_fra > 0 and partner_age >= partner_claim_age:
        annual_income += partner_monthly_fra * ss_claim_factor(partner_claim_age) * 12

    # Spousal top-up: married couples only, once BOTH have claimed. It starts
    # when the second of the two files, at the receiving spouse's age then.
    if (globals().get("MODEL_SPOUSAL_SS_BENEFIT", False)
            and normalize_filing_status() == _FILING_MFJ
            and your_age >= claim_age and partner_age >= partner_claim_age):
        partner_top_up = max(0.0, 0.5 * YOUR_SS_MONTHLY_FRA - partner_monthly_fra)
        your_top_up = max(0.0, 0.5 * partner_monthly_fra - YOUR_SS_MONTHLY_FRA)
        annual_income += 12 * (
            partner_top_up * ss_spousal_factor(max(partner_claim_age, claim_age - age_gap))
            + your_top_up * ss_spousal_factor(max(claim_age, partner_claim_age + age_gap)))

    return annual_income

# Toggle Social Security on/off for scenario comparison
INCLUDE_SOCIAL_SECURITY = True
SS_CLAIM_AGE = 67  # When you start claiming (62-70)
PARTNER_SS_CLAIM_AGE = None  # When your partner starts, in their own age (None = same as yours)
# Spousal benefit for married couples (calculate_social_security). False
# reproduces the earlier results, which paid each person only their own benefit.
MODEL_SPOUSAL_SS_BENEFIT = True

# -----------------------------------------------------------------------------
# SOCIAL SECURITY TAXATION
# -----------------------------------------------------------------------------
# Up to 85% of Social Security benefits are taxable based on "provisional income"
# Provisional Income = AGI + 50% of SS benefits + tax-exempt interest
#
# Thresholds for Married Filing Jointly (2024):
#   - Below $32,000: 0% taxable
#   - $32,000 - $44,000: Up to 50% taxable
#   - Above $44,000: Up to 85% taxable

# Model the REAL-TERMS DECAY of tax thresholds that Congress never indexed.
#
# This engine runs in an ALL-REAL (today's-dollars) frame — see
# update_inflation_factors. Holding a NOMINAL threshold constant inside a real
# frame is arithmetically identical to assuming it IS inflation-indexed. Two of
# them are not, by statute:
#   * NIIT $250k MFJ — fixed since 2013, never indexed
#   * Social Security taxability $32k/$44k — fixed since 1993, never indexed
# (Medicare IRMAA IS indexed, since 2020, so holding it flat in real terms is
# already correct and it is deliberately NOT decayed here.)
#
# Left un-decayed, the model under-taxes later life badly: over a 60-year plan at
# 2.75% inflation the NIIT threshold is really worth ~$49k in today's dollars, and
# the SS 85% tier ~$8.6k — i.e. essentially every retiree crosses both.
# Set False to reproduce the pre-2026-08-23 behaviour.
MODEL_UNINDEXED_THRESHOLD_DECAY = True


def real_frozen_threshold(nominal_threshold: float, years_from_start: float) -> float:
    """Today's-dollars value of a threshold frozen in NOMINAL terms.

    A statute-fixed dollar threshold loses real value at general CPI every year.
    Returns the threshold unchanged when the decay model is switched off, or when
    ``years_from_start`` is non-positive.
    """
    if not MODEL_UNINDEXED_THRESHOLD_DECAY:
        return nominal_threshold
    try:
        yrs = float(years_from_start or 0.0)
    except (TypeError, ValueError):
        return nominal_threshold
    if yrs <= 0:
        return nominal_threshold
    return nominal_threshold / ((1.0 + EXPECTED_INFLATION) ** yrs)


# California fully exempts Social Security benefits from STATE income tax
# (federal taxability is unaffected either way -- see SS_TAX_THRESHOLD_*
# below). Left False, the model reproduces the pre-fix behaviour: taxable SS
# ran through the CA brackets like any other ordinary income, overstating CA
# tax owed (and, via the shared year_ordinary_income total, overstating CA
# tax on any withdrawal recognized later in the same year too). Only takes
# effect when STATE_CHOICE selects real CA brackets -- "Other" is a rough
# flat-rate stand-in for an unmodeled state and does not inherit this.
MODEL_CA_EXEMPTS_SOCIAL_SECURITY = True


SS_TAX_THRESHOLD_1_MFJ = 32_000     # Below this: 0% taxable
SS_TAX_THRESHOLD_2_MFJ = 44_000     # Above this: up to 85% taxable
SS_TAX_RATE_TIER_1 = 0.50           # Max 50% taxable in middle tier
SS_TAX_RATE_TIER_2 = 0.85           # Max 85% taxable in top tier

def calculate_taxable_social_security(ss_benefits: float, other_agi: float,
                                      years_from_start: float = 0.0) -> float:
    """
    Calculate the taxable portion of Social Security benefits.

    Uses IRS provisional income formula:
    Provisional Income = AGI (excluding SS) + 50% of SS benefits + tax-exempt interest

    For MFJ:
    - Provisional < $32,000: 0% taxable
    - $32,000 <= Provisional <= $44,000: 50% of (Provisional - $32,000) is taxable
    - Provisional > $44,000: 85% taxable (with formula adjustment)

    Args:
        ss_benefits: Total Social Security benefits received
        other_agi: AGI excluding Social Security

    Returns:
        Taxable portion of Social Security benefits
    """
    if ss_benefits <= 0:
        return 0

    # Calculate provisional income
    provisional_income = other_agi + (0.5 * ss_benefits)

    # These two thresholds have been frozen in NOMINAL dollars since 1993, so in
    # this real-dollar frame they lose value every year (see
    # real_frozen_threshold). Holding them constant would model them as indexed.
    thresh_1 = real_frozen_threshold(SS_TAX_THRESHOLD_1_MFJ, years_from_start)
    thresh_2 = real_frozen_threshold(SS_TAX_THRESHOLD_2_MFJ, years_from_start)

    if provisional_income <= thresh_1:
        # Below first threshold: nothing taxable
        return 0

    elif provisional_income <= thresh_2:
        # Between thresholds: up to 50% taxable
        taxable = 0.5 * (provisional_income - thresh_1)
        return min(taxable, ss_benefits * SS_TAX_RATE_TIER_1)

    else:
        # Above second threshold: up to 85% taxable
        # Formula: Lesser of:
        #   1) 85% of SS benefits
        #   2) Sum of:
        #      a) 85% of (provisional - threshold 2)
        #      b) Lesser of the tier-1 span or 50% of SS benefits
        amount_above_threshold_2 = provisional_income - thresh_2
        tier_1_amount = min(
            0.5 * (thresh_2 - thresh_1),
            ss_benefits * 0.50
        )
        tier_2_amount = 0.85 * amount_above_threshold_2

        combined = tier_1_amount + tier_2_amount
        max_taxable = ss_benefits * SS_TAX_RATE_TIER_2

        return min(combined, max_taxable)

# -----------------------------------------------------------------------------
# FEDERAL TAX CONFIGURATION (2024 MFJ)
# -----------------------------------------------------------------------------
# Note: the progressive federal / California / LTCG bracket tables are defined
# as dataclasses inside account_simulation.py. Edit those there if you want to
# model a different state's brackets or a single-filer scenario.

# =============================================================================
# EXAMPLE STATE: California brackets are used as the default state tax model
# (see account_simulation.py). Users in other states should replace those
# brackets with their state's brackets, or set them to all zeros to model a
# no-income-tax state (AK, FL, NV, SD, TN, TX, WA, WY).
# =============================================================================

# -----------------------------------------------------------------------------
# FILING STATUS (finding #8)
# -----------------------------------------------------------------------------
# The UI filing-status selector (Married filing jointly / Single / Head of
# household) must actually select the federal bracket table + standard
# deduction the engine uses — otherwise every non-MFJ user is taxed as MFJ,
# understating tax and inflating success. Real cfg attribute so the selector
# reaches the engine (was dropped by the hasattr() gate in
# sim_runner._apply_overrides).
#
# WIRED: federal brackets (get_federal_brackets) + federal standard deduction
# (get_standard_deduction) branch on FILING_STATUS. These are the dominant
# dollar effects (single vs MFJ federal tax differs by ~$2.8k @ $70k, ~$5.9k @
# $150k, ~$17.3k @ $300k).
# DOCUMENTED LIMITATION (not yet filing-aware — still uses MFJ figures):
# California brackets + CA standard deduction, NIIT threshold, Social-Security
# provisional-income thresholds, LTCG brackets, and Medicare IRMAA brackets all
# remain MFJ. For a Single/HOH filer these are roughly the MFJ thresholds and
# therefore CONSERVATIVE (they understate CA tax / NIIT / IRMAA and overstate
# the SS-taxable ceiling for a single filer). Wiring them fully would require a
# Single/HOH table for each; left as a bounded follow-up.
FILING_STATUS = "Married filing jointly"

# Canonical short codes -> the strings the UI emits, so callers can compare
# loosely. normalize_filing_status() collapses either form to "MFJ"/"S"/"HOH".
_FILING_MFJ = "MFJ"
_FILING_SINGLE = "S"
_FILING_HOH = "HOH"


def has_partner() -> bool:
    """Is there a second adult in the plan? (PARTNER_AGE 0 = single household.)
    The one place this rule lives: partner accounts, income, contributions,
    spending, Social Security and healthcare all key off it."""
    try:
        return int(globals().get("PARTNER_AGE", 0) or 0) > 0
    except (TypeError, ValueError):
        return False


def plan_end_age(values: dict = None) -> int:
    """The primary's age when the plan ends: the later of you reaching
    PLAN_UNTIL_AGE and your partner reaching PARTNER_PLAN_UNTIL_AGE (None = the
    same age), so a younger partner is covered to their own plan-until age.
    Simulations run the years before this age. ``values`` (a UI overrides
    dict) supplies any of the four ages in place of this config's."""
    def get(key):
        if values is not None and values.get(key) is not None:
            return values[key]
        return globals().get(key)
    end = int(get("PLAN_UNTIL_AGE"))
    partner_age = int(get("PARTNER_AGE") or 0)
    if partner_age > 0:                     # has_partner(), for these values
        partner_until = int(get("PARTNER_PLAN_UNTIL_AGE") or end)
        end = max(end, partner_until + int(get("YOUR_AGE")) - partner_age)
    return end


def normalize_filing_status(status=None) -> str:
    """Collapse a filing-status string to one of "MFJ", "S", "HOH".

    Accepts either the UI label ("Married filing jointly" / "Single" /
    "Head of household") or the short code. Unknown values fall back to MFJ so
    existing results are unchanged.
    """
    if status is None:
        status = FILING_STATUS
    s = str(status).strip().lower()
    if s in ("mfj", "married filing jointly", "married", "m"):
        return _FILING_MFJ
    if s in ("s", "single"):
        return _FILING_SINGLE
    if s in ("hoh", "head of household", "head-of-household"):
        return _FILING_HOH
    # First-letter heuristic keeps "married..." -> MFJ etc. for odd variants.
    if s.startswith("m"):
        return _FILING_MFJ
    if s.startswith("h"):
        return _FILING_HOH
    if s.startswith("s"):
        return _FILING_SINGLE
    return _FILING_MFJ


# 2024 federal ordinary-income brackets as (upper_threshold, marginal_rate).
# MFJ mirrors the TaxBrackets dataclass default in account_simulation.py;
# Single and HOH are the official 2024 IRS schedules.
FEDERAL_BRACKETS_BY_STATUS = {
    _FILING_MFJ: [
        (23_200, 0.10), (94_300, 0.12), (201_050, 0.22),
        (383_900, 0.24), (487_450, 0.32), (731_200, 0.35),
        (float('inf'), 0.37),
    ],
    _FILING_SINGLE: [
        (11_600, 0.10), (47_150, 0.12), (100_525, 0.22),
        (191_950, 0.24), (243_725, 0.32), (609_350, 0.35),
        (float('inf'), 0.37),
    ],
    _FILING_HOH: [
        (16_550, 0.10), (63_100, 0.12), (100_500, 0.22),
        (191_950, 0.24), (243_700, 0.32), (609_350, 0.35),
        (float('inf'), 0.37),
    ],
}


def get_federal_brackets(status=None):
    """Return the 2024 federal bracket list for the given (or active) filing status."""
    return FEDERAL_BRACKETS_BY_STATUS[normalize_filing_status(status)]


# Standard deduction for Married Filing Jointly (2024).
# Applied before calculating federal income tax.
STANDARD_DEDUCTION_MFJ_2024 = 29_200
# 2024 federal standard deduction for Single and Head of household filers.
STANDARD_DEDUCTION_SINGLE_2024 = 14_600
STANDARD_DEDUCTION_HOH_2024 = 21_900

STANDARD_DEDUCTION_BY_STATUS = {
    _FILING_MFJ: STANDARD_DEDUCTION_MFJ_2024,
    _FILING_SINGLE: STANDARD_DEDUCTION_SINGLE_2024,
    _FILING_HOH: STANDARD_DEDUCTION_HOH_2024,
}

# Additional standard deduction for age 65+ (each spouse).
ADDITIONAL_STD_DEDUCTION_65_PLUS = 1_550
# For Single/HOH the age-65+ additional deduction is larger (per-filer, 2024).
ADDITIONAL_STD_DEDUCTION_65_PLUS_SINGLE = 1_950

# California standard deduction for Married Filing Jointly (2024 tax year).
# Source: CA Franchise Tax Board, 2024 California Standard Deduction Worksheet
# (FTB Form 540 instructions, 2024), published 2024.
CA_STANDARD_DEDUCTION_MFJ_2024 = 11_080

def get_standard_deduction(your_age: int, partner_age: int) -> float:
    """
    Calculate the FEDERAL standard deduction based on ages and FILING_STATUS.

    2024 base deduction: MFJ $29,200 / Single $14,600 / HOH $21,900.
    Age-65+ add-on: $1,550 per spouse for MFJ; $1,950 for Single/HOH (per filer).
    For non-MFJ filers only the primary filer's age is considered (there is no
    second filer), matching the single-return schedule.
    """
    status = normalize_filing_status()
    deduction = STANDARD_DEDUCTION_BY_STATUS[status]

    if status == _FILING_MFJ:
        if your_age >= 65:
            deduction += ADDITIONAL_STD_DEDUCTION_65_PLUS
        if partner_age >= 65:
            deduction += ADDITIONAL_STD_DEDUCTION_65_PLUS
    else:
        if your_age >= 65:
            deduction += ADDITIONAL_STD_DEDUCTION_65_PLUS_SINGLE

    return deduction

# -----------------------------------------------------------------------------
# EARLY WITHDRAWAL PENALTIES
# -----------------------------------------------------------------------------
# IRS penalties for withdrawing from retirement accounts before qualified age.

EARLY_WITHDRAWAL_AGE_401K_IRA = 59.5  # Age for penalty-free 401k/IRA withdrawals
EARLY_WITHDRAWAL_AGE_HSA = 65         # Age for penalty-free HSA non-medical withdrawals

EARLY_WITHDRAWAL_PENALTY_401K_IRA = 0.10  # 10% penalty
EARLY_WITHDRAWAL_PENALTY_HSA = 0.20       # 20% penalty for non-medical

# Note: Roth contributions can be withdrawn tax/penalty-free anytime.
# Roth EARNINGS face 10% penalty before 59.5 (and 5-year rule).
# For simplicity, the simulator assumes Roth is withdrawn last when age >= 59.5.

def calculate_early_withdrawal_penalty(amount: float, account_type: str,
                                       age: float, is_medical: bool = False,
                                       separation_age: float = None,
                                       sepp_covered: bool = False) -> float:
    """
    Calculate early withdrawal penalty for retirement account withdrawals.

    Args:
        amount: Withdrawal amount
        account_type: One of 'traditional_401k', 'traditional_ira', 'hsa', 'roth'
        age: Current age of account owner
        is_medical: Whether HSA withdrawal is for qualified medical expenses
        separation_age: Age the owner left their employer. With
            RULE_OF_55_ENABLED, separating at/after 55 makes the CURRENT
            EMPLOYER's 401(k) penalty-free — IRAs never qualify.
        sepp_covered: True when this withdrawal is part of an active 72(t)
            SEPP schedule, which is a statutory penalty exception.

    Returns:
        Penalty amount (0 if no penalty applies)
    """
    if amount <= 0:
        return 0

    if account_type in ['traditional_401k', 'traditional_ira']:
        if age < EARLY_WITHDRAWAL_AGE_401K_IRA:
            # 72(t) SEPP: penalty-free regardless of account type.
            if sepp_covered:
                return 0
            # Rule of 55: employer plan only, and only if the separation from
            # service happened during/after the year you turned 55.
            if (RULE_OF_55_ENABLED
                    and account_type == 'traditional_401k'
                    and separation_age is not None
                    and separation_age >= RULE_OF_55_MIN_SEPARATION_AGE
                    and age >= RULE_OF_55_MIN_SEPARATION_AGE):
                return 0
            return amount * EARLY_WITHDRAWAL_PENALTY_401K_IRA

    elif account_type == 'hsa':
        # HSA: No penalty if for medical expenses, 20% penalty otherwise before 65
        if not is_medical and age < EARLY_WITHDRAWAL_AGE_HSA:
            return amount * EARLY_WITHDRAWAL_PENALTY_HSA

    # Roth contributions: no penalty (simplification - we withdraw contributions first)
    # Cash/Taxable: no penalty

    return 0

# -----------------------------------------------------------------------------
# NET INVESTMENT INCOME TAX (NIIT)
# -----------------------------------------------------------------------------
# 3.8% additional tax on net investment income for high earners.
# Applies to interest, dividends, capital gains, rental income, etc.

NIIT_THRESHOLD_MFJ = 250_000  # MAGI threshold for MFJ
NIIT_RATE = 0.038             # 3.8% surtax

def calculate_niit(magi: float, net_investment_income: float,
                   years_from_start: float = 0.0) -> float:
    """
    Calculate Net Investment Income Tax (3.8% surtax).

    Args:
        magi: Modified Adjusted Gross Income
        net_investment_income: Investment income (interest, dividends, capital gains)

    Returns:
        NIIT tax amount
    """
    # $250k MFJ has been frozen in NOMINAL dollars since 2013 -> it decays in real
    # terms (see real_frozen_threshold).
    niit_threshold = real_frozen_threshold(NIIT_THRESHOLD_MFJ, years_from_start)
    if magi <= niit_threshold:
        return 0

    # NIIT applies to the LESSER of:
    # 1) Net investment income
    # 2) Amount by which MAGI exceeds threshold
    excess_magi = magi - niit_threshold
    taxable_amount = min(net_investment_income, excess_magi)

    return taxable_amount * NIIT_RATE

# -----------------------------------------------------------------------------
# MEDICARE IRMAA (Income-Related Monthly Adjustment Amount)
# -----------------------------------------------------------------------------
# Higher-income beneficiaries pay more for Medicare Parts B and D.
# Based on MAGI from 2 years prior (e.g., 2024 income affects 2026 premiums).

# 2025 IRMAA thresholds and monthly surcharges (MFJ), per official CMS figures.
# NOTE: Thresholds are held FROZEN in nominal dollars (not inflated year-over-year)
# because this engine operates in an all-real frame. This is a known, documented
# limitation: in reality IRMAA thresholds are inflation-adjusted annually, so this
# will overstate IRMAA exposure for future years modeled far past 2025.
# Format: (income_threshold, monthly_part_b_premium, monthly_part_d_surcharge)
MEDICARE_IRMAA_BRACKETS_MFJ = [
    (0,        185.00,  0.00),      # Base premium (no surcharge)
    (212_000,  259.00,  13.70),     # First surcharge tier
    (266_000,  370.00,  35.30),
    (334_000,  480.90,  57.00),
    (400_000,  591.90,  78.60),
    (750_000,  628.90,  85.80),     # Maximum tier
]

def calculate_medicare_irmaa(magi: float, inflation_factor: float = 1.0,
                             enrollees: int = 2) -> float:
    """
    Calculate annual Medicare premiums including IRMAA surcharges.

    Uses MAGI from 2 years prior to determine premium tier.

    Args:
        magi: Modified AGI (typically from 2 years prior)
        inflation_factor: Inflation adjustment for future years
        enrollees: How many people are actually enrolled in Medicare. Defaults to
            2 (a couple, both age 65+) which is the historical behavior. Pass 1
            for a single filer, or for an age-gapped couple in the years when
            only one spouse has reached MEDICARE_AGE -- billing two premiums for
            a household with one eligible person overstated the cost.

    Returns:
        Annual Medicare premium (Part B + Part D) for ``enrollees`` people
    """
    # Find the applicable bracket
    part_b_monthly = MEDICARE_IRMAA_BRACKETS_MFJ[0][1]  # Base
    part_d_monthly = MEDICARE_IRMAA_BRACKETS_MFJ[0][2]  # Base

    for threshold, part_b, part_d in MEDICARE_IRMAA_BRACKETS_MFJ:
        if magi >= threshold:
            part_b_monthly = part_b
            part_d_monthly = part_d
        else:
            break

    # Calculate annual premium, one Part B + Part D per enrolled person
    annual_premium = (part_b_monthly + part_d_monthly) * 12 * max(0, int(enrollees))

    # Apply inflation adjustment
    return annual_premium * inflation_factor

# -----------------------------------------------------------------------------
# REQUIRED MINIMUM DISTRIBUTIONS (RMDs)
# -----------------------------------------------------------------------------
# SECURE 2.0 Act: RMDs start at age 73 (for those born 1951-1959).
# For those born 1960+: RMDs start at age 75 (effective 2033).

def get_rmd_start_age(birth_year: int) -> int:
    """
    Calculate RMD start age based on SECURE 2.0 Act rules.

    - Born 1950 or earlier: Age 72
    - Born 1951-1959: Age 73
    - Born 1960 or later: Age 75
    """
    if birth_year <= 1950:
        return 72
    elif birth_year <= 1959:
        return 73
    else:
        return 75

# Birth years for the RMD start age, DERIVED from age (age is the input; a
# separate birth year could only disagree with it). Someone right at the
# 1959/1960 cutoff could land a year off, depending on their birthday.
YOUR_BIRTH_YEAR = CURRENT_YEAR - YOUR_AGE
PARTNER_BIRTH_YEAR = CURRENT_YEAR - PARTNER_AGE

RMD_START_AGE = get_rmd_start_age(YOUR_BIRTH_YEAR)  # 75 (for those born 1960+)

# IRS Uniform Lifetime Table (for calculating RMDs).
# Extended to age 120 for edge case handling.
RMD_TABLE = {
    72: 27.4,  # For those born 1950 or earlier (backward compatibility)
    73: 26.5,  74: 25.5,  75: 24.6,  76: 23.7,  77: 22.9,
    78: 22.0,  79: 21.1,  80: 20.2,  81: 19.4,  82: 18.5,
    83: 17.7,  84: 16.8,  85: 16.0,  86: 15.2,  87: 14.4,
    88: 13.7,  89: 12.9,  90: 12.2,  91: 11.5,  92: 10.8,
    93: 10.1,  94: 9.5,   95: 8.9,   96: 8.4,   97: 7.8,
    98: 7.3,   99: 6.8,   100: 6.4,  101: 6.0,  102: 5.6,
    103: 5.2,  104: 4.9,  105: 4.6,  106: 4.3,  107: 4.1,
    108: 3.9,  109: 3.7,  110: 3.5,  111: 3.4,  112: 3.3,
    113: 3.1,  114: 3.0,  115: 2.9,  116: 2.8,  117: 2.7,
    118: 2.5,  119: 2.3,  120: 2.0,
}

# Default distribution period for ages beyond the table
DEFAULT_RMD_DISTRIBUTION_PERIOD = 2.0

def calculate_rmd(account_balance: float, age: int, start_age: int = RMD_START_AGE) -> float:
    """
    Calculate Required Minimum Distribution for a traditional account.

    Args:
        account_balance: Balance as of Dec 31 of prior year
        age: Account owner's age
        start_age: Owner's RMD start age (from their birth year). Defaults to the
            module-global RMD_START_AGE for backward compatibility.

    Returns:
        Required minimum distribution amount
    """
    if age < start_age or account_balance <= 0:
        return 0

    # Get distribution period from table, use default for ages beyond table
    distribution_period = RMD_TABLE.get(age, DEFAULT_RMD_DISTRIBUTION_PERIOD)

    # Guard against division by zero (should never happen with valid table)
    if distribution_period <= 0:
        distribution_period = DEFAULT_RMD_DISTRIBUTION_PERIOD

    return account_balance / distribution_period

# -----------------------------------------------------------------------------
# ROTH CONVERSION STRATEGY
# -----------------------------------------------------------------------------
# Convert Traditional 401k/IRA to Roth during low-income early retirement years
# (before Social Security kicks in at 67). The optimal strategy is to "fill up"
# lower tax brackets with conversions.

ENABLE_ROTH_CONVERSION = True  # Toggle Roth conversion strategy on/off

# Target tax brackets to fill (2024 MFJ brackets):
# 10% bracket: $0 - $23,200
# 12% bracket: $23,200 - $94,300
# 22% bracket: $94,300 - $201,050
# Strategy: Fill up to the top of the 12% bracket for optimal tax arbitrage.
ROTH_CONVERSION_TARGET_BRACKET = 94_300  # Fill up to top of 12% bracket

# Maximum conversion per year (can set lower if desired).
ROTH_CONVERSION_MAX_ANNUAL = 100_000

# Stop conversions once SS starts (income becomes higher).
ROTH_CONVERSION_STOP_AGE = 67

# -----------------------------------------------------------------------------
# ACA HEALTH INSURANCE (Before Medicare at 65)
# -----------------------------------------------------------------------------
# Marketplace insurance costs for early retirees (before Medicare eligibility).

ACA_ENABLED = True  # Enable ACA health insurance modeling

# Base unsubsidized premium (family coverage, mid-tier Silver plan).
# RAISED 2026-09-21 from $1,500/mo ($18k/yr), which was well below market: an
# unsubsidized Silver plan for a family of four runs roughly $25k-$30k/yr in
# 2026 (CA on the higher end). $2,000/mo ($24k/yr) is the conservative end of
# that range and is deliberately consistent with
# HEALTHCARE_COSTS_BY_AGE['early_retirement']. This is the CEILING the subsidy
# calculation caps against, so it only bites once MAGI clears the 400%-FPL
# cliff -- which a household running large Roth conversions does immediately.
# Raise toward $2,500/mo for a less optimistic plan.
ACA_BASE_MONTHLY_PREMIUM = 2_000
ACA_BASE_ANNUAL_PREMIUM = ACA_BASE_MONTHLY_PREMIUM * 12

# Federal Poverty Level (FPL) for family of 4 (2024).
FPL_FAMILY_OF_4 = 31_200

# ACA subsidy cliff - subsidies phase out above 400% FPL.
# Note: American Rescue Plan temporarily removed the cliff through 2025.
# This models the permanent structure where subsidies phase out.
ACA_SUBSIDY_CLIFF_PCT = 4.0
ACA_SUBSIDY_CLIFF = FPL_FAMILY_OF_4 * ACA_SUBSIDY_CLIFF_PCT

# Below 400% FPL, max premium is capped at % of income (sliding scale):
# At 150% FPL: ~4% of income
# At 200% FPL: ~6.5% of income
# At 300% FPL: ~9.5% of income
# At 400% FPL: ~9.5% of income (then cliff)
ACA_MAX_PREMIUM_PCT_BY_FPL = {
    1.5: 0.04,   # 150% FPL: max 4% of income
    2.0: 0.065,  # 200% FPL: max 6.5% of income
    3.0: 0.095,  # 300% FPL: max 9.5% of income
    4.0: 0.095,  # 400% FPL: max 9.5% of income
}

# Medicare (age 65+)
MEDICARE_MONTHLY_PREMIUM = 400  # Combined Part B + supplemental for couple
MEDICARE_ANNUAL_PREMIUM = MEDICARE_MONTHLY_PREMIUM * 12


# =============================================================================
# HEALTHCARE COST MODEL BY AGE
# =============================================================================
# Age-based healthcare cost model for more realistic modeling.
# All values in today's dollars for a couple (HEALTHCARE_BAND_ADULTS people);
# the engine charges each covered adult their share by their OWN age
# (healthcare_cost_per_adult), so one person pays half a band.

HEALTHCARE_COSTS_BY_AGE = {
    'pre_retirement': 6_000,      # Employer-subsidized (pre-retirement)
    'early_retirement': 24_000,   # ACA marketplace (retired, pre-65) - big jump
    'medicare_base': 8_000,       # Medicare base (ages 65-74)
    'medicare_mid': 12_000,       # Medicare (ages 75-84)
    'medicare_late': 18_000,      # Medicare + more care (ages 85+)
}
HEALTHCARE_BAND_ADULTS = 2

# WIRED 2026-09-21 (was a DEAD INPUT for the whole life of the project).
#
# Nothing in the engine ever called calculate_healthcare_cost(), so the UI's
# healthcare editor changed the displayed assumptions and nothing else. It
# escaped the inert-control audit because the attribute DOES exist on cfg; it
# was simply never read.
#
# The two bands mean DIFFERENT things, so they are wired differently:
#
#   * 'early_retirement' describes a FULL-PRICE ACA premium -- the same quantity
#     as the unsubsidized ceiling. It therefore drives that ceiling
#     (calculate_aca_premium caps against it) rather than acting as a floor.
#     Flooring here would be wrong: it would force the full $24k onto a
#     low-income early retiree whose subsidy correctly puts them at ~$1.6k.
#
#   * 'medicare_*' describe premium PLUS care ("Medicare + more care" at 85+),
#     i.e. out-of-pocket on top of premiums -- deductibles, copays, dental,
#     vision, drugs, rising utilisation. Out-of-pocket is charged nowhere else
#     in the engine, so for 65+ the band acts as an ALL-IN FLOOR. Taking the max
#     (not the sum) keeps it from double-counting the premium portion, and the
#     richer MAGI-driven model still wins where IRMAA pushes premiums above the
#     band.
#
# Set MODEL_HEALTHCARE_COST_FLOOR False to reproduce the pre-fix behaviour.
#
# NOTE: the 'pre_retirement' band is deliberately NOT charged. Working-year
# healthcare is employer-payroll-deducted and is already reflected inside
# YOUR_COMPENSATION_BY_AGE[...]['after_tax']; charging it again would
# double-count. Only retirement years are affected.
MODEL_HEALTHCARE_COST_FLOOR = True


def full_price_aca_annual() -> float:
    """Unsubsidized ACA premium ceiling (today's dollars, whole household).

    Prefers HEALTHCARE_COSTS_BY_AGE['early_retirement'] so the UI's healthcare
    editor actually reaches the engine; falls back to ACA_BASE_ANNUAL_PREMIUM.
    Legacy flat-band path only: with MODEL_ACA_AGE_RATED on, the engine prices
    the marketplace per member by age instead (calculate_aca_premium_age_rated).
    """
    band = (HEALTHCARE_COSTS_BY_AGE or {}).get('early_retirement')
    try:
        band = float(band)
    except (TypeError, ValueError):
        band = 0.0
    return band if band > 0 else float(ACA_BASE_ANNUAL_PREMIUM)

def calculate_healthcare_cost(your_age: int, is_retired: bool, inflation_factor: float = 1.0) -> float:
    """
    Calculate healthcare costs based on age and retirement status.

    Healthcare costs rise significantly in early retirement (ACA) and again in
    late life as medical needs increase with age.

    Args:
        your_age: Current age
        is_retired: Whether person is retired
        inflation_factor: Inflation adjustment factor

    Returns:
        Annual healthcare cost in inflated dollars
    """
    if not is_retired:
        # Pre-retirement: employer-subsidized
        base_cost = HEALTHCARE_COSTS_BY_AGE['pre_retirement']
    elif your_age < 65:
        # Early retirement: ACA marketplace, no subsidies if high income
        base_cost = HEALTHCARE_COSTS_BY_AGE['early_retirement']
    elif your_age < 75:
        # Medicare ages 65-74: base Medicare + supplemental
        base_cost = HEALTHCARE_COSTS_BY_AGE['medicare_base']
    elif your_age < 85:
        # Ages 75-84: higher healthcare utilization
        base_cost = HEALTHCARE_COSTS_BY_AGE['medicare_mid']
    else:
        # Ages 85+: significant medical needs
        base_cost = HEALTHCARE_COSTS_BY_AGE['medicare_late']

    return base_cost * inflation_factor


def healthcare_cost_per_adult(age: int, inflation_factor: float = 1.0) -> float:
    """One retired adult's share of the couple band for their own ``age``."""
    return calculate_healthcare_cost(age, True, inflation_factor) / HEALTHCARE_BAND_ADULTS

# =============================================================================
# LONG-TERM CARE (LTC) MODELING
# =============================================================================
# Long-term care is a major, commonly-underplanned retirement risk. Enabled by
# default with reasonable, conservative estimates; turn it off (or lower the
# probability) if you have LTC insurance or expect family care.
#
# Cost basis: LTC_ANNUAL_COST is in TODAY'S dollars; the engine inflates it by
# the healthcare-cost factor to the year care is actually incurred, so the
# modeled FUTURE cost reflects real (higher) future prices. $120k/yr ≈ the 2024
# national median for a private nursing-home room (Genworth Cost of Care ~$116k
# in 2023), nudged to current dollars; assisted living / in-home care run less,
# a dedicated memory-care facility more, so this is a reasonable middle-high.

LTC_ENABLED = True  # On by default (a major retirement risk worth planning for)
LTC_START_AGE = 83  # Care typically begins early-to-mid 80s (avg NH entry ~83)
# Per-YEAR probability of incurring care from the start age (drawn independently
# each year in the Monte Carlo). 20%/yr over ~83-95 ≈ 2-3 expected care-years,
# matching typical paid-LTC duration. (Prior 50%/yr was the high end.)
LTC_PROBABILITY = 0.20
LTC_DURATION_YEARS = 3  # Average duration of LTC need (reference; draw is per-year)
LTC_ANNUAL_COST = 120_000  # $/year in today's dollars (facility + care); inflated to future cost by the engine

def calculate_ltc_cost(your_age: int, inflation_factor: float, needs_ltc: bool) -> float:
    """
    Calculate annual long-term care cost if needed at this age.

    LTC becomes a consideration starting at age 85. This function calculates
    the annual cost based on:
    - Whether the person actually needs LTC (stochastic draw)
    - Their age (affects intensity of care needed)
    - Inflation adjustments

    Args:
        your_age: Current age
        inflation_factor: Inflation adjustment factor for healthcare
        needs_ltc: Whether the person needs LTC this year (pre-determined draw)

    Returns:
        Annual LTC cost in inflated dollars (0 if no LTC needed)
    """
    if not LTC_ENABLED or your_age < LTC_START_AGE or not needs_ltc:
        return 0.0

    # Adjust for age (higher care intensity at older ages)
    age_factor = 1.0
    if your_age >= 90:
        age_factor = 1.25  # 25% higher costs at 90+
    elif your_age >= 87:
        age_factor = 1.15  # 15% higher at 87-89

    return LTC_ANNUAL_COST * inflation_factor * age_factor


def calculate_aca_premium(modified_agi: float, family_size: int = 4) -> float:
    """
    Calculate ACA health insurance premium based on Modified AGI.

    Args:
        modified_agi: Modified Adjusted Gross Income for ACA purposes
        family_size: Number of people in household (default 4)

    Returns:
        Annual health insurance premium after subsidies
    """
    if not ACA_ENABLED:
        return 0

    # Calculate FPL percentage
    fpl = FPL_FAMILY_OF_4  # Simplified for family of 4
    fpl_pct = modified_agi / fpl

    # If above 400% FPL, no subsidy - pay full premium
    if fpl_pct >= ACA_SUBSIDY_CLIFF_PCT:
        return full_price_aca_annual()

    # Below 400% FPL, premium is capped at a percentage of income.
    # Interpolate the max premium percentage.
    if fpl_pct <= 1.5:
        max_pct = 0.04
    elif fpl_pct <= 2.0:
        max_pct = 0.04 + (fpl_pct - 1.5) / 0.5 * (0.065 - 0.04)
    elif fpl_pct <= 3.0:
        max_pct = 0.065 + (fpl_pct - 2.0) / 1.0 * (0.095 - 0.065)
    else:  # 3.0 to 4.0
        max_pct = 0.095

    # Calculate subsidized premium
    max_premium = modified_agi * max_pct

    # Return the lesser of subsidized premium or base premium
    return min(max_premium, full_price_aca_annual())


# -----------------------------------------------------------------------------
# AGE-RATED MARKETPLACE ("fair marketplace assumptions", Covered California,
# San Diego, plan year 2026)
# -----------------------------------------------------------------------------
# The legacy model above prices every pre-65 year at ONE flat household figure
# (HEALTHCARE_COSTS_BY_AGE['early_retirement'], $24k) against a fixed
# family-of-4 FPL, regardless of ages or who is actually in the household. Real
# marketplace premiums are rated per member by age (3:1 band, 64-year-old pays
# 3x a 21-year-old), subsidies are sized by household size, and marketplace
# members also carry out-of-pocket costs (deductibles/copays).
#
# MODEL_ACA_AGE_RATED = True (used by AccountPortfolio.quote_health_insurance_cost):
#   * Full price = sum over marketplace members of their own benchmark-silver
#     rate: adults ACA_BENCHMARK_MONTHLY_AT_40 x curve(age)/curve(40) x 12;
#     members under ACA_CHILD_RATE_UNDER_AGE at ACA_CHILD_MONTHLY x 12. Members
#     = pre-Medicare adults + children at home (children_at_home_ages).
#     HEALTHCARE_COSTS_BY_AGE['early_retirement'] is NOT used as the ceiling in
#     this mode -- the age-rated figure replaces the flat band (the band, and
#     ACA_BASE_MONTHLY_PREMIUM, only drive the legacy path).
#   * Subsidy: FPL by household size (2025 HHS guideline, which sets 2026
#     credits); household = adults in the tax household + children at home.
#     Cliff at 400% FPL (enhanced credits expired end-2025). Premium =
#     min(MAGI x applicable %, full price), applicable % per the 2026 table.
#   * Out-of-pocket: ACA_OOP_PER_PERSON_ANNUAL per marketplace member, net of
#     the living base's SPEND_HEALTH_MONTHLY line for the marketplace share so
#     the same dollars are not charged twice.
# False -> the legacy flat-band path above, byte-identical to before.
MODEL_ACA_AGE_RATED = True

# Benchmark (second-lowest-cost Silver) premiums before subsidy, today's $/mo.
# The app's Assumptions panel sets both. 650 is the 2026 figure for San Diego,
# close to the 2026 US average for a 40-year-old (about $625); prices vary a lot
# by region, so look yours up by ZIP code at healthcare.gov.
ACA_BENCHMARK_MONTHLY_AT_40 = 650   # one 40-year-old; other ages via ACA_AGE_CURVE
ACA_CHILD_MONTHLY = 390             # per child under ACA_CHILD_RATE_UNDER_AGE
ACA_CHILD_RATE_UNDER_AGE = 21       # federal curve rates members under 21 at the child rate
ACA_OOP_PER_PERSON_ANNUAL = 1_500   # deductibles/copays per marketplace member, today's $

# 2025 HHS poverty guideline (48 states + DC); used for 2026 coverage.
ACA_FPL_FIRST_PERSON = 15_650
ACA_FPL_PER_ADDITIONAL_PERSON = 5_500

# Federal default ACA age-rating curve (CMS). Ages below 21 never reach this
# table (child rate); 64+ is capped at 3.000.
ACA_AGE_CURVE = {
    21: 1.000, 22: 1.000, 23: 1.000, 24: 1.000, 25: 1.004, 26: 1.024,
    27: 1.048, 28: 1.087, 29: 1.119, 30: 1.135, 31: 1.159, 32: 1.183,
    33: 1.198, 34: 1.214, 35: 1.222, 36: 1.230, 37: 1.238, 38: 1.246,
    39: 1.262, 40: 1.278, 41: 1.302, 42: 1.325, 43: 1.357, 44: 1.397,
    45: 1.444, 46: 1.500, 47: 1.563, 48: 1.635, 49: 1.706, 50: 1.786,
    51: 1.865, 52: 1.952, 53: 2.040, 54: 2.135, 55: 2.230, 56: 2.333,
    57: 2.437, 58: 2.548, 59: 2.603, 60: 2.714, 61: 2.810, 62: 2.873,
    63: 2.952, 64: 3.000,
}

# 2026 applicable percentage (share of MAGI expected toward the benchmark),
# linear between points; flat 2.10% at/below 133% and 9.96% from 300-400% FPL.
ACA_APPLICABLE_PCT_POINTS = (
    (1.33, 0.0210),
    (1.50, 0.0419),
    (2.00, 0.0660),
    (2.50, 0.0844),
    (3.00, 0.0996),
    (4.00, 0.0996),
)


def aca_member_full_price_annual(age: int) -> float:
    """Unsubsidized benchmark-silver premium for ONE member (today's $/yr)."""
    if age < ACA_CHILD_RATE_UNDER_AGE:
        return float(ACA_CHILD_MONTHLY) * 12.0
    factor = ACA_AGE_CURVE[min(int(age), 64)]
    return float(ACA_BENCHMARK_MONTHLY_AT_40) * factor / ACA_AGE_CURVE[40] * 12.0


def aca_fpl(household_size: int) -> float:
    """Federal poverty level for a household of ``household_size`` people."""
    n = max(1, int(household_size))
    return float(ACA_FPL_FIRST_PERSON + ACA_FPL_PER_ADDITIONAL_PERSON * (n - 1))


def aca_applicable_pct(fpl_ratio: float) -> float:
    """2026 applicable percentage at ``fpl_ratio`` (1.5 = 150% FPL)."""
    pts = ACA_APPLICABLE_PCT_POINTS
    if fpl_ratio <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if fpl_ratio <= x1:
            return y0 + (fpl_ratio - x0) / (x1 - x0) * (y1 - y0)
    return pts[-1][1]


def calculate_aca_premium_age_rated(modified_agi: float, member_ages,
                                    household_size: int) -> float:
    """Annual marketplace premium after subsidy for the given members (today's $).

    ``member_ages`` are the people actually ON the marketplace (pre-Medicare
    adults + children at home); ``household_size`` is the tax household that
    sets the FPL. Above ACA_SUBSIDY_CLIFF_PCT (400%) FPL there is no credit and
    the full age-rated price is due; below it the household pays
    min(MAGI x applicable %, full price).
    """
    if not ACA_ENABLED or not member_ages:
        return 0.0
    full_price = sum(aca_member_full_price_annual(a) for a in member_ages)
    fpl_ratio = modified_agi / aca_fpl(household_size)
    if fpl_ratio >= ACA_SUBSIDY_CLIFF_PCT:
        return full_price
    return min(max(0.0, modified_agi) * aca_applicable_pct(fpl_ratio), full_price)


def aca_oop_annual(n_members: int, marketplace_share: float,
                   healthcare_factor: float = 1.0) -> float:
    """Marketplace out-of-pocket NOT already in the living base.

    ACA_OOP_PER_PERSON_ANNUAL x members (grown by the healthcare factor, like
    premiums) minus the marketplace share of the living base's real-flat
    SPEND_HEALTH_MONTHLY x 12 line, floored at 0 -- so health dollars the base
    already funds are not charged twice.
    """
    gross = float(ACA_OOP_PER_PERSON_ANNUAL) * n_members * healthcare_factor
    in_base = float(SPEND_HEALTH_MONTHLY or 0) * 12.0 * marketplace_share
    return max(0.0, gross - in_base)

# -----------------------------------------------------------------------------
# ASSET ALLOCATION GLIDE PATH
# -----------------------------------------------------------------------------
# Instead of a fixed stock/bond split, gradually shift to a more conservative
# allocation as retirement progresses.

GLIDE_PATH_ENABLED = True

# Starting allocation at retirement (must match accumulation-phase
# STOCK_ALLOCATION/BOND_ALLOCATION so the glide path de-risks
# monotonically instead of stepping equity up at the retirement transition)
GLIDE_PATH_START_STOCK_PCT = 0.80  # 80% stocks at retirement
GLIDE_PATH_START_BOND_PCT = 0.20   # 20% bonds at retirement

# Target allocation by age 75
GLIDE_PATH_END_AGE = 75
GLIDE_PATH_END_STOCK_PCT = 0.60    # 60% stocks by age 75
GLIDE_PATH_END_BOND_PCT = 0.40     # 40% bonds by age 75

# Hold steady after target age
GLIDE_PATH_HOLD_AFTER = True

def calculate_asset_allocation(age: int, retirement_age: int) -> tuple:
    """
    Calculate stock/bond allocation based on age and glide path.

    Args:
        age: Current age
        retirement_age: Age when retirement started

    Returns:
        (stock_allocation, bond_allocation) as tuple of floats
    """
    if not GLIDE_PATH_ENABLED:
        return (STOCK_ALLOCATION, BOND_ALLOCATION)

    # Before retirement, use the starting allocation
    if age < retirement_age:
        return (STOCK_ALLOCATION, BOND_ALLOCATION)

    # After target age, use end allocation
    if age >= GLIDE_PATH_END_AGE:
        return (GLIDE_PATH_END_STOCK_PCT, GLIDE_PATH_END_BOND_PCT)

    # Linear interpolation between retirement age and target age
    years_in_retirement = age - retirement_age
    years_to_target = GLIDE_PATH_END_AGE - retirement_age

    if years_to_target <= 0:
        return (GLIDE_PATH_END_STOCK_PCT, GLIDE_PATH_END_BOND_PCT)

    progress = min(1.0, years_in_retirement / years_to_target)

    stock_pct = GLIDE_PATH_START_STOCK_PCT - progress * (GLIDE_PATH_START_STOCK_PCT - GLIDE_PATH_END_STOCK_PCT)
    bond_pct = GLIDE_PATH_START_BOND_PCT + progress * (GLIDE_PATH_END_BOND_PCT - GLIDE_PATH_START_BOND_PCT)

    return (stock_pct, bond_pct)

# -----------------------------------------------------------------------------
# SEQUENCE OF RETURNS RISK ANALYSIS
# -----------------------------------------------------------------------------
# Historical market return sequences for stress testing.

# Historical annual S&P 500 returns (nominal, including dividends).
# Source: various historical data compilations.
HISTORICAL_RETURNS = {
    2000: -0.091,  # Dot-com crash begins
    2001: -0.119,  # Recession
    2002: -0.221,  # Bear market bottom
    2003: 0.287,   # Recovery begins
    2004: 0.109,
    2005: 0.049,
    2006: 0.158,
    2007: 0.055,   # Pre-financial crisis
    2008: -0.370,  # Financial crisis
    2009: 0.265,   # Recovery
    2010: 0.151,
    2011: 0.021,
    2012: 0.160,
    2013: 0.324,
    2014: 0.137,
    2015: 0.014,
    2016: 0.120,
    2017: 0.218,
    2018: -0.044,
    2019: 0.314,
    2020: 0.184,   # COVID crash and recovery
    2021: 0.287,
    2022: -0.182,  # Bear market
    2023: 0.262,
    2024: 0.250,   # Estimated
}

# Pre-defined stress test sequences.
SEQUENCE_TESTS = {
    'dot_com_crisis': {
        'name': 'Dot-Com + Financial Crisis (2000-2010)',
        'years': list(range(2000, 2011)),
        'description': 'Two major bear markets back-to-back'
    },
    'financial_crisis': {
        'name': 'Financial Crisis (2007-2012)',
        'years': list(range(2007, 2013)),
        'description': 'Worst 5-year period in recent history'
    },
    'lost_decade': {
        'name': 'Lost Decade (2000-2009)',
        'years': list(range(2000, 2010)),
        'description': 'Decade with near-zero returns'
    },
    'covid_recovery': {
        'name': 'COVID Crash & Recovery (2018-2023)',
        'years': list(range(2018, 2024)),
        'description': 'Recent market volatility'
    },
}

def get_historical_returns_for_sequence(sequence_name: str) -> list:
    """
    Get the actual historical returns for a named sequence.

    Args:
        sequence_name: Name of the sequence test

    Returns:
        List of annual returns for the sequence
    """
    if sequence_name not in SEQUENCE_TESTS:
        return []

    years = SEQUENCE_TESTS[sequence_name]['years']
    returns = [HISTORICAL_RETURNS.get(year, 0.07) for year in years]
    return returns

# =============================================================================
# LIFECYCLE BIG PURCHASES
# =============================================================================
# Optional big-ticket lifecycle events: a car purchase (one-time and/or
# recurring replacement), a full house move, and extra "go-go years" vacation
# spending in early retirement. ALL DISABLED BY DEFAULT so the baseline
# simulation is unaffected. Stage 2 wires these into the engine; for now
# these are pure config + pure helper functions with no side effects on the
# simulation.

# --- Car purchase(s), paid cash from the portfolio -------------------------
# One-time car purchase at a specific age.
CAR_ONETIME_ENABLED = False
CAR_ONETIME_AGE = 40
CAR_ONETIME_AMOUNT = 40_000

# Recurring car replacement every N years starting at a given age.
CAR_RECURRING_ENABLED = False
CAR_RECURRING_START_AGE = 40
CAR_RECURRING_EVERY_YEARS = 8
CAR_RECURRING_AMOUNT = 40_000

def calculate_car_purchase(age: int) -> float:
    """
    One-time $ cash outlay for car purchase(s) occurring in a given year.

    Combines (if enabled):
    - A single one-time purchase at CAR_ONETIME_AGE.
    - A recurring replacement every CAR_RECURRING_EVERY_YEARS years, starting
      at CAR_RECURRING_START_AGE.

    Args:
        age: Current age (accumulation or retirement).

    Returns:
        Total car-related cash outlay for this year (0 if none / disabled).
    """
    total = 0.0

    if CAR_ONETIME_ENABLED and age == CAR_ONETIME_AGE:
        total += CAR_ONETIME_AMOUNT

    if CAR_RECURRING_ENABLED and age >= CAR_RECURRING_START_AGE:
        years_since_start = age - CAR_RECURRING_START_AGE
        if CAR_RECURRING_EVERY_YEARS > 0 and years_since_start % CAR_RECURRING_EVERY_YEARS == 0:
            total += CAR_RECURRING_AMOUNT

    return total

# --- Housing timeline: buy, move, downsize ----------------------------------
# Today's home is described above: HOME_VALUE / MORTGAGE_* for an owner (rate:
# MORTGAGE_RATE_FOR_PAYOFF), SPEND_RENT_MONTHLY for a renter. HOME_EVENTS lists
# what changes later, each at an age of yours. Empty list = stay put. The
# household holds one home at a time.
#   {"age": 30, "action": "buy", "price": 450_000, "down_pct": 0.20,
#    "rate": 0.065, "years": 30, "costs": 10_000}
#       buy a home (sells the current one first if you own then);
#   {"age": 45, "action": "sell_buy", ...same fields as buy...,
#    "selling_cost_pct": 0.06}
#       sell the home you own and buy another (move, upgrade, downsize);
#   {"age": 72, "action": "sell_rent", "rent": 2_500, "costs": 5_000}
#       sell the home and rent from then on (rent is monthly, today's dollars).
# Optional on a purchase: "loan" (instead of down_pct) and "monthly" (the
# all-in payment; derived from loan, rate, term and HOME_CARRYING_COST_PCT when
# left out). Missing costs / selling_cost_pct use HOUSE_MOVING_COSTS /
# HOME_SELLING_COST_PCT. Normalized by housing_events().
HOME_EVENTS = []

# What you paid for today's home (plus improvements), for tax on its sale.
# None = its current value, i.e. no taxable gain (the prior assumption). The
# gain above the exclusion (home_sale_exclusion) is taxed as a long-term gain.
# A home bought through HOME_EVENTS has its price as basis; the engine holds
# home values flat in today's dollars, so those sales have no real gain.
HOME_COST_BASIS = None
HOME_SALE_EXCLUSION_SINGLE = 250_000   # per owner (IRC 121)
HOME_SALE_EXCLUSION_MFJ = 500_000      # married filing jointly

# Legacy single house move (plans saved before HOME_EVENTS). Still honoured:
# housing_events() turns it into one more event, so old plans keep their results.
HOUSE_MOVE_ENABLED = False
HOUSE_MOVE_AGE = 45
NEW_HOME_VALUE = 1_000_000
NEW_MORTGAGE_BALANCE = 700_000
NEW_MORTGAGE_MONTHLY = 4_500
NEW_MORTGAGE_YEARS = 30
HOME_SELLING_COST_PCT = 0.06  # Realtor fees + closing costs on the sale
HOUSE_MOVING_COSTS = 10_000   # Movers, buy-side closing costs, etc.

# The CURRENT loan's fixed rate (the app's "Mortgage interest rate" input).
# The engine amortizes the balance you entered at this rate, so it drives how
# fast equity builds and what is left to repay when you sell. When paydown
# tracking is off it is also the rate used to rebuild the remaining principal
# from the payment (estimate_remaining_mortgage_principal). 6.5% is a
# reasonable multi-decade average for a 30-year fixed mortgage.
MORTGAGE_RATE_FOR_PAYOFF = 0.065

# Rate on the NEW loan taken out at HOUSE_MOVE_AGE (lifecycle house move);
# None = same as the current loan. The two rarely match, and the engine
# amortizes the new loan at this rate from the move on.
NEW_MORTGAGE_RATE = None


def new_mortgage_rate() -> float:
    """The new loan's rate (falls back to the current loan's)."""
    return MORTGAGE_RATE_FOR_PAYOFF if NEW_MORTGAGE_RATE is None else float(NEW_MORTGAGE_RATE)


HOME_BUY = "buy"
HOME_SELL_BUY = "sell_buy"
HOME_SELL_RENT = "sell_rent"
_HOME_ACTIONS = (HOME_BUY, HOME_SELL_BUY, HOME_SELL_RENT)


def _num(value, default: float) -> float:
    try:
        return default if value is None else float(value)
    except (TypeError, ValueError):
        return default


def level_payment(balance: float, annual_rate: float, years: int) -> float:
    """Level monthly principal + interest retiring ``balance`` over ``years``."""
    balance, years = max(0.0, _num(balance, 0.0)), int(_num(years, 0))
    if balance <= 0 or years <= 0:
        return 0.0
    r = max(0.0, _num(annual_rate, 0.0)) / 12.0
    n = years * 12
    return balance / n if r <= 0 else balance * r / (1.0 - (1.0 + r) ** -n)


def housing_events(source=None) -> list:
    """HOME_EVENTS plus the legacy single house move, normalized and sorted by age.

    Each event comes back with every field resolved: age, action, costs,
    selling_cost_pct, and either rent (sell_rent) or price / loan / rate /
    years / monthly (a purchase; monthly is the all-in payment). Malformed
    entries are skipped. ``source`` is an optional mapping read before this
    module's globals, so the UI can resolve a plan from its overrides without
    touching config.
    """
    if source is None:
        get = globals().get
    else:
        def get(key, default=None):
            value = source.get(key)
            return globals().get(key, default) if value is None else value
    raw = list(get("HOME_EVENTS", None) or [])
    if get("HOUSE_MOVE_ENABLED", False):
        owns = (_num(get("HOME_VALUE", 0), 0.0) > 0
                or _num(get("MORTGAGE_MONTHLY", 0), 0.0) > 0)
        rate = get("NEW_MORTGAGE_RATE", None)
        raw.append({
            "age": get("HOUSE_MOVE_AGE", 45),
            "action": HOME_SELL_BUY if owns else HOME_BUY,
            "price": get("NEW_HOME_VALUE", 0), "loan": get("NEW_MORTGAGE_BALANCE", 0),
            "rate": get("MORTGAGE_RATE_FOR_PAYOFF", 0.065) if rate is None else rate,
            "years": get("NEW_MORTGAGE_YEARS", 30),
            "monthly": get("NEW_MORTGAGE_MONTHLY", 0),
        })
    out = []
    for e in raw:
        if not isinstance(e, dict) or str(e.get("action")) not in _HOME_ACTIONS:
            continue
        try:
            age = int(e["age"])
        except (KeyError, TypeError, ValueError):
            continue
        ev = {
            "age": age, "action": str(e["action"]),
            "costs": max(0.0, _num(e.get("costs"), _num(get("HOUSE_MOVING_COSTS", 0), 0.0))),
            "selling_cost_pct": max(0.0, _num(e.get("selling_cost_pct"),
                                              _num(get("HOME_SELLING_COST_PCT", 0.06), 0.06))),
        }
        if ev["action"] == HOME_SELL_RENT:
            ev["rent"] = max(0.0, _num(e.get("rent"), 0.0))
        else:
            price = max(0.0, _num(e.get("price"), 0.0))
            rate = max(0.0, _num(e.get("rate"), _num(get("MORTGAGE_RATE_FOR_PAYOFF", 0.065), 0.065)))
            years = max(0, int(_num(e.get("years"), 30)))
            if e.get("loan") is None:
                down = min(max(_num(e.get("down_pct"), 0.20), 0.0), 1.0)
                loan = price * (1.0 - down)
            else:
                loan = max(0.0, _num(e.get("loan"), 0.0))
            monthly = e.get("monthly")
            if monthly is None:
                escrow = price * max(0.0, _num(get("HOME_CARRYING_COST_PCT", 0.0135), 0.0135)) / 12.0
                monthly = level_payment(loan, rate, years) + escrow
            ev.update(price=price, loan=loan, rate=rate, years=years,
                      monthly=max(0.0, _num(monthly, 0.0)))
        out.append(ev)
    out.sort(key=lambda ev: ev["age"])
    return out


def home_sale_exclusion() -> float:
    """Gain on selling your main home that escapes tax: $500k married filing
    jointly, $250k for one owner. Unmarried partners are taken to own the home
    together, so each excludes $250k of their half."""
    if not has_partner():
        return float(HOME_SALE_EXCLUSION_SINGLE)
    if normalize_filing_status() == _FILING_MFJ:
        return float(HOME_SALE_EXCLUSION_MFJ)
    return 2.0 * float(HOME_SALE_EXCLUSION_SINGLE)

# -----------------------------------------------------------------------------
# EXTRA MORTGAGE PRINCIPAL (early payoff)
# -----------------------------------------------------------------------------
# Additional principal paid each year on top of the scheduled payment, in
# today's dollars. 0.0 (the default) is a no-op, so the baseline plan is
# byte-identical.
#
# For a sweep of this to mean anything, all four of these must hold, and the
# engine is wired so they do:
#   1. the extra payment COSTS real cash (it is added to the housing outflow);
#   2. it reduces the tracked principal faster (_amortize_mortgage_year);
#   3. when the loan is retired early the SCHEDULED PAYMENT STOPS -- that freed
#      cash flow is the entire benefit, and without it prepaying would look
#      strictly harmful (all cost, no upside);
#   4. home equity follows, since refresh_home_equity() derives it from the
#      principal.
# Point 3 is the subtle one: mortgage_expense_for_age() otherwise decides "is
# there still a loan?" from the CONFIG schedule (an age), which cannot know the
# balance hit zero early.
EXTRA_MORTGAGE_PAYMENT_ANNUAL = 0.0
# Window for the extra payment. None start -> begin immediately (YOUR_AGE);
# None stop -> keep paying until the loan is gone.
EXTRA_MORTGAGE_PAYMENT_START_AGE = None
EXTRA_MORTGAGE_PAYMENT_STOP_AGE = None


def extra_mortgage_payment_enabled() -> bool:
    """True when a non-zero extra principal payment is configured.

    Reads via ``globals().get`` so deleting the attribute entirely (how the
    tests simulate pre-feature behaviour) degrades to "disabled" instead of
    raising NameError.
    """
    try:
        return float(globals().get("EXTRA_MORTGAGE_PAYMENT_ANNUAL", 0.0) or 0.0) > 0.0
    except (TypeError, ValueError):
        return False


def extra_mortgage_payment_for_age(your_age: float) -> float:
    """Extra principal owed at ``your_age`` (today's dollars, 0 outside the window)."""
    if not extra_mortgage_payment_enabled():
        return 0.0
    try:
        age = float(your_age)
    except (TypeError, ValueError):
        return 0.0
    start = globals().get("EXTRA_MORTGAGE_PAYMENT_START_AGE")
    start = float(YOUR_AGE) if start is None else float(start)
    if age < start:
        return 0.0
    stop = globals().get("EXTRA_MORTGAGE_PAYMENT_STOP_AGE")
    if stop is not None and age >= float(stop):
        return 0.0
    return float(globals().get("EXTRA_MORTGAGE_PAYMENT_ANNUAL", 0.0) or 0.0)


def estimate_remaining_mortgage_principal(
    monthly_payment: float,
    months_remaining: int,
    annual_rate: float = MORTGAGE_RATE_FOR_PAYOFF,
) -> float:
    """
    Approximate the outstanding principal of a fixed-rate mortgage.

    APPROXIMATION: the simulation engine does not track a mortgage amortization
    schedule; it only knows the level monthly payment and the payoff age. We
    therefore reconstruct the remaining principal as the present value of the
    remaining level payments:

        principal = P * (1 - (1 + r)^-n) / r         (r > 0)
        principal = P * n                            (r == 0)

    where P is the monthly payment, r is the monthly rate (annual_rate / 12),
    and n is the number of remaining monthly payments. For a genuine
    fully-amortizing fixed-rate loan this equals the exact outstanding balance;
    for other loan shapes it is a reasonable estimate given only (payment,
    term-remaining).

    Args:
        monthly_payment: Level monthly principal + interest payment.
        months_remaining: Number of payments left before payoff.
        annual_rate: Assumed nominal annual interest rate.

    Returns:
        Estimated remaining principal (0 if no payment or no months remain).
    """
    if monthly_payment <= 0 or months_remaining <= 0:
        return 0.0

    monthly_rate = annual_rate / 12.0
    if monthly_rate <= 0:
        return monthly_payment * months_remaining

    return monthly_payment * (1.0 - (1.0 + monthly_rate) ** (-months_remaining)) / monthly_rate

# --- Retirement vacation ("go-go years") extra spending ---------------------
RETIREMENT_VACATION_ENABLED = False
RETIREMENT_VACATION_ANNUAL = 20_000
RETIREMENT_VACATION_UNTIL_AGE = 75

def calculate_retirement_vacation(age: int, retirement_age: int) -> float:
    """
    Extra annual "go-go years" vacation spending in early retirement.

    Args:
        age: Current age.
        retirement_age: Age at which retirement begins.

    Returns:
        RETIREMENT_VACATION_ANNUAL if enabled and the person is retired and
        younger than RETIREMENT_VACATION_UNTIL_AGE, else 0.
    """
    if not RETIREMENT_VACATION_ENABLED:
        return 0.0

    if retirement_age <= age < RETIREMENT_VACATION_UNTIL_AGE:
        return RETIREMENT_VACATION_ANNUAL

    return 0.0

# -----------------------------------------------------------------------------
# SIMULATION SETTINGS
# -----------------------------------------------------------------------------
NUM_SIMULATIONS = 10_000
EARLIEST_RETIREMENT_AGE = 25
LATEST_RETIREMENT_AGE = 75
TARGET_SUCCESS_RATE = 0.80

# Use home as backup for long-term care / emergency
USE_HOME_AS_BACKUP = True

# Credit mortgage PRINCIPAL REPAYMENT to home equity as the loan amortizes.
#
# The engine charges the full mortgage payment as an expense every year, but the
# accessible-equity reserve used to be frozen at its starting value forever — so
# 15-30 years of principal repayment (real net-worth accumulation) simply
# vanished. On a real profile the reserve stayed at its opening value while true
# equity roughly tripled by the early 40s, and reached the whole home value at
# payoff.
#
# Enabling this tracks the loan balance and recomputes the reserve each year, so
# paying down a mortgage builds the backstop it actually builds. It makes results
# slightly MORE optimistic (the old behavior was conservative, not wrong in the
# user's favour). Set False to reproduce the pre-2026-08-20 behavior.
TRACK_HOME_EQUITY_PAYDOWN = True

# =============================================================================
# EARLY-RETIREMENT ACCESS STRATEGIES
# =============================================================================
# Ways to reach retirement money before the normal 59.5 penalty age. All default
# OFF so the baseline is unchanged and each can be A/B tested on its own.
#
# Strategy 1 (taxable brokerage) needs no toggle — it is already the engine's
# first non-cash source before 59.5, taxed at LTCG rates with no penalty.

# --- Rule of 55 -------------------------------------------------------------
# Separate from service during or after the year you turn 55 and your CURRENT
# EMPLOYER's 401(k) becomes penalty-free (IRAs do NOT qualify, and rolling the
# 401(k) to an IRA forfeits it). Modeled as: no 10% penalty on 401(k)
# withdrawals when retirement age >= 55.
RULE_OF_55_ENABLED = False
RULE_OF_55_MIN_SEPARATION_AGE = 55

# --- 72(t) Substantially Equal Periodic Payments -----------------------------
# Penalty-free fixed annual distributions from traditional accounts. Once begun
# they must continue for the LONGER of 5 years or until age 59.5; breaking the
# schedule retroactively penalizes every distribution taken.
SEPP_72T_ENABLED = False
SEPP_72T_START_AGE = 45
# Interest rate for the fixed-amortization method (IRS caps it at 5% or 120% of
# the mid-term AFR, whichever is greater).
SEPP_72T_RATE = 0.05
SEPP_72T_MIN_YEARS = 5
# Dollar amount of traditional assets DESIGNATED for the SEPP — i.e. split off
# into a separate IRA that the schedule acts on. This is the standard way to
# right-size a 72(t): the payment is computed only on the designated balance, and
# the rest of your traditional money stays outside the schedule, free of the
# 5-year lock-in and still available for Roth conversions.
#
# 0 means "use the entire traditional balance" (the all-or-nothing case). That is
# rarely what anyone wants: on a real profile, applying the SEPP to the whole
# traditional balance forced a mandatory draw that crowded out most of the
# voluntary Roth conversions and cost six figures in extra lifetime tax.
SEPP_72T_CARVEOUT = 0.0

# --- Roth conversion ladder --------------------------------------------------
# Converted principal becomes withdrawable tax- and penalty-free 5 years after
# each conversion. Enabling this makes the model track conversions as dated
# cohorts and ENFORCE the seasoning rule, so unseasoned money is penalized —
# stricter (and more realistic) than the default "Roth is always accessible"
# simplification. Pair with ENABLE_ROTH_CONVERSION to actually build the ladder.
ROTH_LADDER_ENABLED = False
ROTH_LADDER_SEASONING_YEARS = 5

# --- Coast FIRE -------------------------------------------------------------
# At the coast age, stop contributing but keep working enough to cover expenses.
# The portfolio compounds untouched until the real retirement age: no new
# savings, but no withdrawals either.
COAST_FIRE_ENABLED = False
COAST_FIRE_AGE = 45

# -----------------------------------------------------------------------------
# COMPUTED TOTALS (for reference)
# -----------------------------------------------------------------------------
TOTAL_RETIREMENT_ACCOUNTS = (YOUR_401K + YOUR_ROTH_IRA + YOUR_TRADITIONAL_IRA +
                              YOUR_HSA + PARTNER_401K + PARTNER_ROTH_IRA)
TOTAL_TAXABLE = YOUR_BROKERAGE + PARTNER_BROKERAGE
TOTAL_CASH = YOUR_CASH + PARTNER_CASH
TOTAL_INVESTMENTS = TOTAL_RETIREMENT_ACCOUNTS + TOTAL_TAXABLE + TOTAL_CASH
TOTAL_NET_WORTH = TOTAL_INVESTMENTS + HOME_EQUITY

if __name__ == "__main__":
    print("=" * 70)
    print("RETIREMENT MONTE CARLO SIMULATOR")
    print("=" * 70)
    print("FINANCIAL SUMMARY (EXAMPLE VALUES)")
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
    married = normalize_filing_status() == _FILING_MFJ
    print(f"  Primary age: {YOUR_AGE}, Partner age: {PARTNER_AGE}")
    print(f"  Filing status: {FILING_STATUS}")
    if MORTGAGE_YEARS_REMAINING > 0:
        print(f"  Mortgage paid off at age {YOUR_AGE + MORTGAGE_YEARS_REMAINING}")
    else:
        print("  Renting (no mortgage)")

    print("\nANNUAL SAVINGS:")
    your_total = calculate_your_total_savings(YOUR_AGE)
    partner_total = calculate_partner_total_savings(PARTNER_SALARY, 0, married=married)
    print(f"  Primary savings:      ${your_total:>12,.0f}")
    print(f"  Partner savings:      ${partner_total:>12,.0f}")
    print(f"  {'-' * 40}")
    print(f"  COMBINED:             ${your_total + partner_total:>12,.0f}")

    print("\nCURRENT EXPENSES:")
    print(f"  Mortgage:             ${MORTGAGE_ANNUAL:>12,.0f}")
    print(f"  Utilities:            ${UTILITIES_ANNUAL:>12,.0f}")
    print(f"  Primary other:        ${YOUR_OTHER_ANNUAL:>12,.0f}")
    print(f"  Partner other:        ${PARTNER_ANNUAL_SPENDING:>12,.0f}")
    print(f"  {'-' * 40}")
    print(f"  TOTAL:                ${CURRENT_ANNUAL_EXPENSES:>12,.0f}")

    print("\nEXPENSE TIMELINE:")
    for age in [YOUR_AGE, YOUR_AGE + 5, YOUR_AGE + 10, YOUR_AGE + 15, 55, 65]:
        child_exp = calculate_child_expenses(age)
        mortgage_status = "w/mortgage" if has_mortgage(age) else "no mortgage"
        total = calculate_annual_expenses(age)
        print(f"  Age {age}: Children ${child_exp:>6,.0f}/yr, Total ${total:>7,.0f}/yr ({mortgage_status})")

    print("\nSAVINGS PROJECTION:")
    for age in [YOUR_AGE, YOUR_AGE + 5, YOUR_AGE + 10, YOUR_AGE + 15]:
        your_s = calculate_your_total_savings(age)
        years = age - YOUR_AGE
        partner_salary = PARTNER_SALARY * ((1 + PARTNER_SALARY_GROWTH_RATE) ** years)
        partner_s = calculate_partner_total_savings(partner_salary, years, married)
        print(f"  Age {age}: Primary ${your_s:,.0f} + Partner ${partner_s:,.0f} = ${your_s + partner_s:,.0f}")


# =============================================================================
# EARLY-RETIREMENT STRATEGY HELPERS
# =============================================================================

def sepp_72t_annual_amount(traditional_balance: float, age: float,
                           rate: float = None) -> float:
    """Annual 72(t) SEPP using the FIXED AMORTIZATION method.

    The balance is amortized over the owner's single-life expectancy at the
    chosen interest rate, giving a level annual payment. This is the method that
    produces the largest of the three IRS-permitted amounts for a given balance,
    which is why early retirees use it.

    Returns 0 when there is nothing to distribute.
    """
    balance = max(0.0, float(traditional_balance or 0.0))
    if balance <= 0:
        return 0.0
    life_expectancy = single_life_expectancy(age)
    if life_expectancy <= 0:
        return 0.0
    r = SEPP_72T_RATE if rate is None else float(rate)
    if r <= 0:
        return balance / life_expectancy
    # Level payment amortizing `balance` over `life_expectancy` years.
    return balance * r / (1.0 - (1.0 + r) ** -life_expectancy)


def single_life_expectancy(age: float) -> float:
    """Remaining years under the IRS Single Life Table (Reg. 1.401(a)(9)-9).

    Interpolated from table anchor points; ages outside the table clamp to the
    nearest end. Used by the 72(t) amortization method.
    """
    table = {
        30: 55.3, 35: 50.5, 40: 45.7, 45: 41.0, 50: 36.2, 52: 34.3,
        55: 31.6, 57: 29.8, 59: 28.0, 60: 27.1, 65: 22.9, 70: 18.8,
        75: 14.8, 80: 11.2, 85: 8.1, 90: 5.7,
    }
    a = float(age)
    ages = sorted(table)
    if a <= ages[0]:
        return table[ages[0]]
    if a >= ages[-1]:
        return table[ages[-1]]
    for lo, hi in zip(ages, ages[1:]):
        if lo <= a <= hi:
            span = hi - lo
            if span == 0:
                return table[lo]
            frac = (a - lo) / span
            return table[lo] + frac * (table[hi] - table[lo])
    return table[ages[-1]]


def sepp_72t_must_continue(age: float, start_age: float) -> bool:
    """True while an active SEPP schedule is still locked in.

    The schedule must run the LONGER of 5 years or until age 59.5 — stopping
    early retroactively penalizes every distribution already taken.
    """
    if start_age is None:
        return False
    years_in = float(age) - float(start_age)
    return years_in < SEPP_72T_MIN_YEARS or float(age) < EARLY_WITHDRAWAL_AGE_401K_IRA


def sepp_72t_balance_for_payment(target_annual: float, age: float,
                                 rate: float = None) -> float:
    """Inverse of ``sepp_72t_annual_amount``: the balance to DESIGNATE to produce
    ``target_annual`` per year.

    This is the practical direction of the calculation — you know the bridge
    income you need, and you split off exactly enough traditional money to
    generate it, leaving the remainder outside the 72(t) schedule (no 5-year
    lock-in, still convertible to Roth).
    """
    target = max(0.0, float(target_annual or 0.0))
    if target <= 0:
        return 0.0
    life_expectancy = single_life_expectancy(age)
    if life_expectancy <= 0:
        return 0.0
    r = SEPP_72T_RATE if rate is None else float(rate)
    if r <= 0:
        return target * life_expectancy
    # Invert: payment = balance * r / (1 - (1+r)^-n)
    return target * (1.0 - (1.0 + r) ** -life_expectancy) / r
