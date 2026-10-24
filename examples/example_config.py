"""
=============================================================================
RETIREMENT MONTE CARLO SIMULATOR - USER CONFIG TEMPLATE
=============================================================================

WHAT THIS FILE IS
-----------------
This is a TEMPLATE. It is NOT meant to be edited in place — copy it to your
own file (suggested: ``my_config.py`` at the project root) and fill in every
value marked ``REPLACE_ME``. Your personal file is gitignored by default so
you will not accidentally commit balances, salaries, or other private data.

HOW TO USE
----------
1. Copy this file to the project root::

       cp shareable_package/examples/example_config.py my_config.py

2. Open ``my_config.py`` and replace every ``REPLACE_ME`` sentinel with your
   real value. Grep for ``REPLACE_ME`` to make sure none are left behind::

       grep -n REPLACE_ME my_config.py

3. Run the smoke test at the bottom of your file to validate the inputs::

       python my_config.py

4. Use it with the simulator by importing your values on top of the package
   defaults. This pattern keeps you from having to copy every single
   economy-wide constant (tax brackets, IRMAA, RMD table, etc.) — you just
   override the user-specific values::

       # my_runner.py
       from retirement_sim import config as cfg
       from my_config import apply_overrides
       apply_overrides(cfg)

       from retirement_sim.account_simulation import run_monte_carlo_detailed
       result = run_monte_carlo_detailed(retirement_age=50, n_simulations=5000)
       print(f"Success rate: {result['success_rate']:.1%}")

   See ``apply_overrides()`` at the bottom of this template — it pushes every
   value defined here into the package's ``config`` module so the simulator
   picks up your numbers.

WHAT GETS REPLACED vs. WHAT STAYS DEFAULT
-----------------------------------------
REPLACE_ME values are truly personal: ages, account balances, compensation,
mortgage details, child plans, Social Security estimates. Everything else
(tax brackets, IRMAA tiers, RMD table, inflation, investment return
distributions) is pre-filled from ``retirement_sim.config`` and is the same
for every US household. You are free to tweak the toggle defaults near the
bottom of this file (dynamic spending, glide path, Roth conversion, etc.)
without touching the core package.

DISCLAIMER
----------
This is not financial, tax, or legal advice. The simulator produces a
probability estimate based on the assumptions you supply — garbage in,
garbage out. Validate assumptions against your own situation and consult a
qualified professional before making retirement decisions.
"""

# -----------------------------------------------------------------------------
# SENTINEL: every "REPLACE_ME" below must be overwritten before use.
# -----------------------------------------------------------------------------
# Defined as None so the file parses cleanly even when left untouched. The
# smoke test at the bottom of this file will catch any un-replaced values
# with a clear error message before you run a simulation.
REPLACE_ME = None


# =============================================================================
# 1) PERSONAL INFORMATION
# =============================================================================
# These drive the simulation timeline: when contribution catch-ups kick in,
# when Social Security becomes available, when RMDs start, etc.

# Your current age (the "primary user" in the model).
# Where to find it: your ID / your math.
# Typical range: 25-65 for accumulation-phase planning.
YOUR_AGE = REPLACE_ME                 # e.g., 35

# Your partner's current age. Set 0 for a single household: the simulator then
# leaves out every partner account, paycheck, contribution and SS benefit.
PARTNER_AGE = REPLACE_ME              # e.g., 33; or 0 if single

# Current calendar year — the simulation's "year 0".
CURRENT_YEAR = 2026

# Birth years (SECURE 2.0 RMD start age: 72/73/75) follow from age, so there is
# no separate input to keep in sync.
YOUR_BIRTH_YEAR = None if YOUR_AGE is REPLACE_ME else CURRENT_YEAR - YOUR_AGE
PARTNER_BIRTH_YEAR = None if PARTNER_AGE is REPLACE_ME else CURRENT_YEAR - PARTNER_AGE

# Plan until this age. 90-95 is typical; ~30-40% of couples have at least one
# partner live past 90, so plan long. Your partner's plan-until age (in their
# own age) defaults to the same; the plan runs until the later of the two.
PLAN_UNTIL_AGE = 95
PARTNER_PLAN_UNTIL_AGE = None         # e.g., 97; None = same as PLAN_UNTIL_AGE

# Married couples file jointly; anyone unmarried (single, or a couple who
# isn't married) files "Single" or "Head of household".
FILING_STATUS = REPLACE_ME            # e.g., "Married filing jointly"


# =============================================================================
# 2) CURRENT ASSETS
# =============================================================================
# Snapshot of every account AS OF TODAY. Check your latest statements. Don't
# inflate or project — just the current balance.

# --- Primary user ---
# Where to find: latest 401k statement. Typical mid-career: $50k-$500k.
YOUR_401K = REPLACE_ME                # e.g., 150_000
# Roth IRA: post-tax retirement account. Latest brokerage statement.
YOUR_ROTH_IRA = REPLACE_ME            # e.g., 50_000
# Traditional IRA: pre-tax IRA (can be $0 if you only have employer 401k).
YOUR_TRADITIONAL_IRA = REPLACE_ME     # e.g., 0
# HSA: only if you're on a high-deductible health plan. $0 if not.
YOUR_HSA = REPLACE_ME                 # e.g., 10_000
# Brokerage: all non-retirement taxable investment accounts combined.
YOUR_BROKERAGE = REPLACE_ME           # e.g., 75_000
# Cash: checking + savings + money market. Emergency fund + buffer.
YOUR_CASH = REPLACE_ME                # e.g., 25_000

# --- Partner ---
# Set all to 0 if modeling a single-earner household.
PARTNER_401K = REPLACE_ME             # e.g., 80_000
PARTNER_ROTH_IRA = REPLACE_ME         # e.g., 20_000
PARTNER_BROKERAGE = REPLACE_ME        # e.g., 15_000
PARTNER_CASH = REPLACE_ME             # e.g., 10_000

# --- Primary residence ---
# HOME_VALUE: Zillow / recent appraisal. 0 if you don't own.
HOME_VALUE = REPLACE_ME               # e.g., 500_000
# MORTGAGE_BALANCE: current principal remaining. 0 if paid off or renting.
MORTGAGE_BALANCE = REPLACE_ME         # e.g., 350_000

# Derived: home equity. Leave this calculation alone.
HOME_EQUITY = (HOME_VALUE or 0) - (MORTGAGE_BALANCE or 0)

# What fraction of home equity is accessible in an emergency (net of
# selling costs, capital-gains tax beyond the $500k MFJ exclusion, moving
# costs). 0.85 is a reasonable default; tighten to 0.75 to be conservative.
HOME_EQUITY_ACCESSIBLE_PCT = 0.85


# =============================================================================
# 3) PRIMARY USER INCOME - PROJECTIONS BY AGE
# =============================================================================
# Provide a row per age from YOUR_AGE out as far as you have visibility into
# comp (promotions, RSU refreshers). The simulator projects forward past the
# last row using YOUR_SALARY_GROWTH_RATE. Three rows is fine to start — add
# more if you have a specific trajectory in mind.
#
# Per-row fields (all annual, in today's dollars):
#   base:        W-2 base salary
#   bonus:       cash bonus
#   rsu_gross:   gross RSU vest value
#   total_comp:  sum of the three above (for readability)
#   after_tax:   take-home after federal + state + payroll
#   saved:       amount of after-tax that actually gets invested (brokerage,
#                ESPP, backdoor Roth). EXCLUDES 401k and HSA (those are
#                pre-tax and handled separately).
#
# How to estimate "after_tax" and "saved":
#   after_tax ≈ total_comp × (1 - your effective tax rate); use last year's
#              W-2/1099 as a sanity check.
#   saved     ≈ after_tax - (annual expenses - mortgage - etc.); this is the
#              part that actually lands in a brokerage account.
YOUR_COMPENSATION_BY_AGE = {
    # age: {"base": ?, "bonus": ?, "rsu_gross": ?, "total_comp": ?, "after_tax": ?, "saved": ?},
    REPLACE_ME: {"base": REPLACE_ME, "bonus": REPLACE_ME, "rsu_gross": REPLACE_ME,
                 "total_comp": REPLACE_ME, "after_tax": REPLACE_ME, "saved": REPLACE_ME},
    # REPLACE_ME + 1: { ... },
    # REPLACE_ME + 2: { ... },
    # Extend as far out as you have real visibility. Beyond the last row,
    # the simulator projects using YOUR_SALARY_GROWTH_RATE.
}

# Year-over-year growth assumed past the last explicit row.
YOUR_SALARY_GROWTH_RATE = 0.04        # 4% annual; typical merit + inflation
YOUR_BONUS_PCT = 0.15                 # Bonus as % of base when projecting
YOUR_RSU_PCT = 0.30                   # RSU as % of base when projecting

# --- Your contributions (annual) ---
# 401k employee contribution. Start with the IRS max ($23,000 in 2024) if
# you're maxing; otherwise put what you actually defer.
YOUR_401K_CONTRIBUTION = 23_000
# Employer match as fraction of base salary (6% = 100% match up to 6%).
YOUR_401K_MATCH_PCT = REPLACE_ME      # e.g., 0.06, or 0.0 if no match
# HSA: only if on HDHP; 2024 family limit $8,300.
YOUR_HSA_CONTRIBUTION = REPLACE_ME    # e.g., 7_550 or 0 if no HSA
YOUR_HSA_MATCH = REPLACE_ME           # e.g., 750 employer seed, or 0
YOUR_HSA_TOTAL = (YOUR_HSA_CONTRIBUTION or 0) + (YOUR_HSA_MATCH or 0)
# Backdoor Roth: $7,000 (2024 IRA max) if you do it, else 0.
YOUR_BACKDOOR_ROTH = REPLACE_ME       # e.g., 7_000 or 0
# ESPP: % of base at the 15% purchase discount. 0 if no ESPP.
YOUR_ESPP_PCT = REPLACE_ME            # e.g., 0.10 or 0.0
YOUR_ESPP_DISCOUNT = 0.15             # Standard 15%; change if your plan differs

# Rough marginal tax rate for back-of-envelope calcs (Roth vs. Traditional
# tradeoff, etc.). High earner MFJ in a high-tax state ≈ 0.32-0.37.
YOUR_MARGINAL_TAX_RATE = 0.32


# =============================================================================
# 4) PARTNER INCOME
# =============================================================================
# Set PARTNER_SALARY = 0 (and zero-out the rest) for a single-earner
# household.

PARTNER_SALARY = REPLACE_ME           # e.g., 90_000 or 0
PARTNER_SALARY_GROWTH_RATE = 0.04

PARTNER_401K_CONTRIBUTION = REPLACE_ME  # e.g., 23_000 or 0
PARTNER_401K_MATCH = REPLACE_ME         # dollars/year; e.g., 0 or 3_000
# Direct Roth contribution (stops after marriage if joint MAGI > limit).
PARTNER_ROTH_CONTRIBUTION = REPLACE_ME  # e.g., 7_000 or 0

# Partner's personal monthly discretionary spending (NOT household bills —
# those are in CURRENT_ANNUAL_EXPENSES below).
PARTNER_MONTHLY_SPENDING = REPLACE_ME   # e.g., 2_000
PARTNER_ANNUAL_SPENDING = (PARTNER_MONTHLY_SPENDING or 0) * 12
PARTNER_ESTIMATED_TAX_RATE = 0.25       # Effective (not marginal) rate


# =============================================================================
# 5) DETAILED EXPENSES
# =============================================================================
# Monthly today-dollar expenses. Grab them from a month or two of bank
# statements and round.

# Mortgage P&I (principal + interest only — property tax + insurance go in
# "other" unless you want to model escrow separately).
MORTGAGE_MONTHLY = REPLACE_ME          # e.g., 2_500 or 0 if renting/paid off
MORTGAGE_ANNUAL = (MORTGAGE_MONTHLY or 0) * 12
MORTGAGE_YEARS_REMAINING = REPLACE_ME  # e.g., 25 or 0

# Utilities: electric, gas, water, internet, phone. Exclude streaming/
# subscriptions (those go under "other").
UTILITIES_MONTHLY = REPLACE_ME         # e.g., 250
UTILITIES_ANNUAL = (UTILITIES_MONTHLY or 0) * 12

# Your personal "other" spending: groceries, gas, dining, subscriptions,
# discretionary. Exclude partner's personal spending (that's above).
YOUR_OTHER_MONTHLY = REPLACE_ME        # e.g., 2_500
YOUR_OTHER_ANNUAL = (YOUR_OTHER_MONTHLY or 0) * 12

# Partner's personal "other" — mirrors the partner-salary block above so the
# household total below is complete.
PARTNER_OTHER_MONTHLY = REPLACE_ME     # e.g., 2_000

# Total current expenses — don't edit; derived.
CURRENT_ANNUAL_EXPENSES = (
    MORTGAGE_ANNUAL
    + UTILITIES_ANNUAL
    + YOUR_OTHER_ANNUAL
    + (PARTNER_OTHER_MONTHLY or 0) * 12
)


# =============================================================================
# 6) CHILDREN
# =============================================================================
# One entry per child, born or planned; [] for no children. Per child:
#   years_until_birth    years from now until born; negative = already born
#                        (-6 is a 6-year-old today)
#   monthly_cost         cost while living at home (today's dollars)
#   leaves_home_age      age when that cost stops
#   college_funding_pct  share of college you pay (0 = none, 1 = all of it),
#                        saved in that child's own 529 from birth
#   college_annual_cost, college_years   one year of college, and how many
CHILDREN = REPLACE_ME   # e.g. [{"years_until_birth": -6, "monthly_cost": 1_800,
                        #        "leaves_home_age": 18, "college_funding_pct": 0.5,
                        #        "college_annual_cost": 40_000, "college_years": 4}]


# =============================================================================
# 7) SOCIAL SECURITY
# =============================================================================
# Estimated monthly benefit AT FULL RETIREMENT AGE (67 for everyone born
# 1960+). Get your real numbers from https://ssa.gov — create a "my Social
# Security" account to see a personalized projection.

YOUR_SS_MONTHLY_FRA = REPLACE_ME        # e.g., 3_200 (in today's $)
PARTNER_SS_MONTHLY_FRA = REPLACE_ME     # e.g., 2_200 (or 0 if no work record)

# When to start claiming (62-70). 67 is neutral; 70 maximizes benefit but
# requires bridging with portfolio from 62-70.
SS_CLAIM_AGE = 67

# Toggle — set False to stress-test "what if SS is cut?"
INCLUDE_SOCIAL_SECURITY = True


# =============================================================================
# 8) ADVANCED TOGGLES (pre-configured sensible defaults)
# =============================================================================
# These shape HOW the simulator behaves, not WHAT your numbers are. The
# defaults are reasonable for most households — read the comments and flip
# them if your situation differs.

# --- Return scenario ---
# 'conservative'  : 7% stock / 2% bond real — prudent planning
# 'historical'    : 8.7% stock / 3.1% bond real — 1926-2024 mean
# 'pessimistic'   : 5% stock / 1% bond real — stress test
ACTIVE_RETURN_SCENARIO = 'historical'

# --- Dynamic spending guardrails ---
# If True, discretionary spending gets cut when the portfolio falls below
# 70% of target. Set False for a rigid constant-spending model.
DYNAMIC_SPENDING_ENABLED = True

# If True, spending also flexes with each year's return (cut 10% in down
# years, 20% in crash years). Conservative default: cuts only, no boosts.
RETURN_BASED_SPENDING_ENABLED = True

# --- Roth conversion ladder ---
# If True, the simulator "fills up" the 12% bracket with Traditional→Roth
# conversions during the low-income years between retirement and SS. Major
# tax savings for early retirees with big 401k balances. Safe default True.
ENABLE_ROTH_CONVERSION = True

# --- Asset allocation glide path ---
# If True, gradually shift from aggressive (90/10) at retirement to
# conservative (60/40) by age 75. Safe default True.
GLIDE_PATH_ENABLED = True

# --- Long-term care ---
# If True, a fraction of simulations incur $100k/yr LTC costs at age 85+.
# Disabled by default — enable only if you're NOT planning to self-insure
# via home equity or rely on family care.
LTC_ENABLED = False

# --- Home as backup ---
# If True, home equity can be tapped to cover shortfalls (via sale or HELOC
# in the model).
USE_HOME_AS_BACKUP = True


# =============================================================================
# 9) SIMULATION SETTINGS
# =============================================================================
NUM_SIMULATIONS = 10_000               # 10k is a good balance of speed vs. stability
EARLIEST_RETIREMENT_AGE = 40           # Lowest age to test in the sweep
LATEST_RETIREMENT_AGE = 65             # Highest age to test
TARGET_SUCCESS_RATE = 0.80             # 80% is standard; 90% is conservative


# =============================================================================
# APPLY OVERRIDES TO THE PACKAGE CONFIG
# =============================================================================
# The simulator reads its parameters from ``retirement_sim.config``. This
# helper copies every variable defined in *this* file onto that module so
# you don't have to duplicate the package's 1,500 lines of tax tables and
# helper functions.

def apply_overrides(cfg_module) -> None:
    """
    Push every user-defined variable from this template onto the given
    config module (typically ``retirement_sim.config``).

    Usage::

        from retirement_sim import config as cfg
        from my_config import apply_overrides
        apply_overrides(cfg)

    Only names that already exist on the target module are copied, so
    typos here don't silently create new attributes.
    """
    import sys
    this_module = sys.modules[__name__]
    for name in dir(this_module):
        if name.startswith('_'):
            continue
        if name in ('apply_overrides', 'REPLACE_ME', 'validate_config'):
            continue
        if not hasattr(cfg_module, name):
            # Skip names that don't exist on the package config — they
            # are almost certainly a typo or a derived value that the
            # package computes internally.
            continue
        value = getattr(this_module, name)
        setattr(cfg_module, name, value)


# =============================================================================
# VALIDATION / SMOKE TEST
# =============================================================================

def validate_config() -> list:
    """
    Walk every module-level variable and return a list of names that are
    still set to REPLACE_ME (or contain REPLACE_ME inside a dict).

    Returns an empty list if the config is fully populated.
    """
    import sys
    this_module = sys.modules[__name__]
    unfilled = []

    # Only inspect ALL_CAPS user-facing constants. Skip the REPLACE_ME
    # sentinel itself (it's meant to be None).
    SKIP = {'REPLACE_ME'}

    for name in dir(this_module):
        if name.startswith('_') or not name.isupper() or name in SKIP:
            continue
        value = getattr(this_module, name)

        if value is None:
            # None = REPLACE_ME sentinel still in place.
            unfilled.append(name)
        elif isinstance(value, dict):
            # Check for REPLACE_ME inside dict keys/values (compensation table).
            for k, v in value.items():
                if k is None:
                    unfilled.append(f"{name} (dict key)")
                    break
                if isinstance(v, dict) and any(vv is None for vv in v.values()):
                    unfilled.append(f"{name}[{k}]")
                    break

    return unfilled


if __name__ == "__main__":
    # Quick sanity check — fails loudly if any REPLACE_ME is still present.
    missing = validate_config()
    if missing:
        print("=" * 70)
        print("CONFIG INCOMPLETE — please replace the following before running:")
        print("=" * 70)
        for name in missing:
            print(f"  - {name}")
        print()
        print("Open this file, search for 'REPLACE_ME', and fill in every match.")
        raise SystemExit(1)

    # Simple financial summary (only reachable once every REPLACE_ME is gone).
    total_retirement = (
        YOUR_401K + YOUR_ROTH_IRA + YOUR_TRADITIONAL_IRA + YOUR_HSA
        + PARTNER_401K + PARTNER_ROTH_IRA
    )
    total_taxable = YOUR_BROKERAGE + PARTNER_BROKERAGE
    total_cash = YOUR_CASH + PARTNER_CASH
    total_investments = total_retirement + total_taxable + total_cash
    total_net_worth = total_investments + HOME_EQUITY

    print("=" * 70)
    print("CONFIG VALIDATED — FINANCIAL SUMMARY")
    print("=" * 70)
    print(f"\nPrimary age: {YOUR_AGE}, Partner age: {PARTNER_AGE}")
    print(f"Current year: {CURRENT_YEAR}, plan until age {PLAN_UNTIL_AGE}")
    print(f"Filing status: {FILING_STATUS}")

    print("\nASSETS:")
    print(f"  Retirement accounts:  ${total_retirement:>12,.0f}")
    print(f"  Taxable investments:  ${total_taxable:>12,.0f}")
    print(f"  Cash:                 ${total_cash:>12,.0f}")
    print(f"  Home equity:          ${HOME_EQUITY:>12,.0f}")
    print(f"  {'-' * 40}")
    print(f"  TOTAL NET WORTH:      ${total_net_worth:>12,.0f}")

    print("\nCURRENT ANNUAL EXPENSES:")
    print(f"  Mortgage:             ${MORTGAGE_ANNUAL:>12,.0f}")
    print(f"  Utilities:            ${UTILITIES_ANNUAL:>12,.0f}")
    print(f"  Your other:           ${YOUR_OTHER_ANNUAL:>12,.0f}")
    print(f"  Partner other:        ${(PARTNER_OTHER_MONTHLY or 0) * 12:>12,.0f}")
    print(f"  {'-' * 40}")
    print(f"  TOTAL:                ${CURRENT_ANNUAL_EXPENSES:>12,.0f}")

    print("\nTOGGLES:")
    print(f"  Return scenario:      {ACTIVE_RETURN_SCENARIO}")
    print(f"  Dynamic spending:     {DYNAMIC_SPENDING_ENABLED}")
    print(f"  Roth conversion:      {ENABLE_ROTH_CONVERSION}")
    print(f"  Glide path:           {GLIDE_PATH_ENABLED}")
    print(f"  Social Security:      {INCLUDE_SOCIAL_SECURITY} (claim at {SS_CLAIM_AGE})")
    print(f"  Long-term care:       {LTC_ENABLED}")
    print()
    print("Ready to run simulations. See the module docstring for usage.")
