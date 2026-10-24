# =============================================================================
# ACCOUNT-BASED RETIREMENT SIMULATION
# =============================================================================
# License: MIT (see LICENSE at project root)
#
# Tracks individual account balances and implements tax-efficient withdrawals
# with support for:
# - Roth conversion strategies
# - ACA health insurance costs
# - Asset allocation glide path
# - Sequence of returns risk analysis
# =============================================================================

# Standard library imports
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple, Optional

# Third-party imports
import numpy as np

# Local application imports
from . import config as cfg


# =============================================================================
# CONSTANTS - Named values for magic numbers used throughout simulation
# =============================================================================

# Withdrawal tolerance: allow 1% shortfall before declaring failure
WITHDRAWAL_SHORTFALL_TOLERANCE = 0.99

# Gross-up solver: withdrawals must cover the NET need PLUS the income tax and
# early-withdrawal penalties they incur. Because the tax on the gross-up amount
# is itself taxable, the required gross is a fixed point that we reach by
# iteratively funding the residual net shortfall. Iterate until the remaining
# net shortfall is within GROSSUP_TOLERANCE dollars (or a pass withdraws nothing,
# i.e. the portfolio is depleted), capped at GROSSUP_MAX_ITERATIONS.
GROSSUP_TOLERANCE = 1.0          # dollars of remaining net shortfall
GROSSUP_MAX_ITERATIONS = 12

# Medical expense portion of total expenses (before/after Medicare)
MEDICAL_EXPENSE_PORTION_PRE_MEDICARE = 0.15
MEDICAL_EXPENSE_PORTION_POST_MEDICARE = 0.10

# Default cost basis assumption for existing taxable accounts
# Assumes 50% of balance is unrealized gains (conservative)
DEFAULT_COST_BASIS_RATIO = 0.5

# Retirement lifestyle ages (go-go years, later-years reduction) live in config:
# cfg.retirement_leisure_end_age / cfg.late_retirement_start_age.

# Minimum portfolio value to continue simulation (avoid floating point issues)
MINIMUM_PORTFOLIO_VALUE = 100.0

# Maximum/minimum reasonable annual returns (based on historical extremes)
# Historical (1926-2024): Worst stock year -38.5% (1931), Best +57.6% (1933)
# We use slightly wider bounds to allow for tail events, but not impossible scenarios
MAX_ANNUAL_RETURN = 0.60   # 60% max gain (historical max was 57.6%)
MIN_ANNUAL_RETURN = -0.45  # 45% max loss (historical max was -38.5%)

# For blended portfolios, bounds are tighter due to diversification
MAX_BLENDED_RETURN = 0.50  # 50% max for 80/20 portfolio
MIN_BLENDED_RETURN = -0.35 # 35% max loss for 80/20 portfolio


def clamp_return(annual_return: float) -> float:
    """
    Clamp annual return to reasonable bounds based on historical extremes.

    Args:
        annual_return: Raw annual return to be clamped

    Returns:
        Clamped return between MIN_BLENDED_RETURN and MAX_BLENDED_RETURN
    """
    return max(MIN_BLENDED_RETURN, min(MAX_BLENDED_RETURN, annual_return))


def update_inflation_factors(inflation_factors: Dict[str, float]) -> None:
    """
    Advance the inflation factors by one year, in an ALL-REAL (today's-dollars) frame.

    The engine draws investment returns in REAL terms (cfg.EXPECTED_STOCK_RETURN etc.
    are real, after-inflation), so every liability must also live in real dollars for
    the comparison to be apples-to-apples. General CPI therefore does NOT grow any
    liability: the ``general`` factor stays constant at 1.0 forever. Only categories
    that genuinely outpace general CPI (healthcare, childcare) grow, and they
    grow at their REAL-EXCESS rate = (category_rate - general_rate) -- i.e. the portion
    of their nominal inflation that is left over after deflating by general CPI.

    Example: healthcare 4.5% - general 2.75% = 1.75% real-excess per year. A category
    whose nominal rate equals general has a 0% real-excess rate and stays flat in real
    terms, correctly (such categories are simply left out of INFLATION_RATES).

    Args:
        inflation_factors: Dictionary of inflation factors by category (modified in-place)
    """
    general_rate = cfg.INFLATION_RATES['general']
    for category, base_rate in cfg.INFLATION_RATES.items():
        if category not in inflation_factors:
            continue
        if category == 'general':
            # General CPI never grows a real liability: real dollars are the frame.
            continue
        # Real-excess = how much faster this category runs than general CPI.
        real_excess_rate = base_rate - general_rate
        # Preserve category-specific volatility, but center on the real-excess mean.
        actual_rate = np.random.normal(real_excess_rate, cfg.INFLATION_VOLATILITY)
        # Real-excess growth is small; clamp to a sane band around it.
        actual_rate = max(-0.05, min(0.10, actual_rate))
        inflation_factors[category] *= (1 + actual_rate)


def generate_correlated_returns() -> Tuple[float, float]:
    """
    Generate correlated stock and bond returns using Cholesky decomposition.

    This properly models the historical relationship between stocks and bonds,
    where bonds often perform well when stocks perform poorly (flight to safety).

    Order of operations (mathematically correct):
    1. Deduct investment fees from expected returns (fees reduce the mean)
    2. Add stochastic variation (volatility * random normal)

    These are ARITHMETIC (after-fee) returns. The geometric/volatility-drag
    correction is applied at the PORTFOLIO level in calculate_blended_return,
    using the blended portfolio variance -- which is lower than the weighted
    average of the component variances thanks to the stock/bond correlation.
    Applying the drag per-asset here would over-penalize a diversified
    portfolio by ignoring that diversification benefit.

    Returns:
        Tuple of (stock_return, bond_return) for the year (arithmetic)
    """
    # Generate independent standard normal random variables
    z1 = np.random.standard_normal()
    z2 = np.random.standard_normal()

    # Apply Cholesky decomposition for correlation
    # For correlation rho: z2_correlated = rho * z1 + sqrt(1 - rho^2) * z2
    rho = cfg.STOCK_BOND_CORRELATION
    z2_correlated = rho * z1 + np.sqrt(1 - rho**2) * z2

    # Step 1: Deduct investment fees from expected returns
    # Fees reduce the mean return, not individual realizations
    stock_mean = cfg.EXPECTED_STOCK_RETURN - cfg.INVESTMENT_FEE_RATE
    bond_mean = cfg.EXPECTED_BOND_RETURN - cfg.INVESTMENT_FEE_RATE

    # Step 2: Generate returns with stochastic variation
    # Return = mean + volatility * random_normal
    stock_return = stock_mean + cfg.STOCK_VOLATILITY * z1
    bond_return = bond_mean + cfg.BOND_VOLATILITY * z2_correlated

    return stock_return, bond_return


def generate_correlated_bond_for_stock(stock_return: float) -> float:
    """
    Draw a stochastic bond return correlated to a KNOWN (e.g. historical) stock
    return, reusing the same Cholesky machinery as generate_correlated_returns.

    The known stock realization is standardized into its shock z1 relative to
    the stock distribution (after-fee mean, STOCK_VOLATILITY). The bond shock is
    then z2_correlated = rho*z1 + sqrt(1-rho^2)*z2 with z2 an independent draw,
    so bonds are correlated to the fixed stock shock yet still vary across runs.
    Returns an ARITHMETIC (after-fee) bond return, matching
    generate_correlated_returns.
    """
    stock_mean = cfg.EXPECTED_STOCK_RETURN - cfg.INVESTMENT_FEE_RATE
    # Standardized stock shock implied by the known stock return.
    z1 = (stock_return - stock_mean) / cfg.STOCK_VOLATILITY
    z2 = np.random.standard_normal()
    rho = cfg.STOCK_BOND_CORRELATION
    z2_correlated = rho * z1 + np.sqrt(1 - rho**2) * z2
    bond_mean = cfg.EXPECTED_BOND_RETURN - cfg.INVESTMENT_FEE_RATE
    return bond_mean + cfg.BOND_VOLATILITY * z2_correlated


def calculate_blended_return(stock_alloc: float, bond_alloc: float) -> float:
    """
    Calculate blended portfolio return with proper correlation modeling.

    The volatility-drag (geometric) correction is applied at the PORTFOLIO
    level, not per-asset. The blended portfolio variance is

        var_p = w_s^2*var_s + w_b^2*var_b + 2*w_s*w_b*rho*sd_s*sd_b

    which is lower than the weighted average of the component variances when
    rho < 1 (here rho = -0.20), so subtracting var_p/2 correctly rewards the
    diversification benefit instead of over-penalizing per-asset. For a
    100%-stock portfolio (w_s=1, w_b=0) this reduces to var_s/2, matching the
    old per-asset stock drag exactly.

    Args:
        stock_alloc: Fraction allocated to stocks (0-1)
        bond_alloc: Fraction allocated to bonds (0-1)

    Returns:
        Blended annual return for the portfolio
    """
    stock_return, bond_return = generate_correlated_returns()
    blended = stock_alloc * stock_return + bond_alloc * bond_return

    # Portfolio-level volatility-drag correction (geometric adjustment)
    if cfg.APPLY_VOLATILITY_DRAG:
        var_s = cfg.STOCK_VOLATILITY ** 2
        var_b = cfg.BOND_VOLATILITY ** 2
        cov = (cfg.STOCK_BOND_CORRELATION
               * cfg.STOCK_VOLATILITY * cfg.BOND_VOLATILITY)
        blended_variance = (stock_alloc ** 2 * var_s
                            + bond_alloc ** 2 * var_b
                            + 2 * stock_alloc * bond_alloc * cov)
        blended -= blended_variance / 2

    return clamp_return(blended)


def _progressive_tax(brackets: List[Tuple[float, float]], taxable_income: float) -> float:
    """
    Calculate tax on ``taxable_income`` using a progressive bracket schedule.

    Shared implementation for the federal, California, and any other
    progressive ``calculate_tax`` methods. ``brackets`` is a list of
    (income_threshold, marginal_rate) tuples in ascending order, the last of
    which uses float('inf') as its threshold.

    Args:
        brackets: List of (income_threshold, tax_rate) tuples
        taxable_income: Income after deductions

    Returns:
        Total tax owed under the progressive schedule
    """
    return cfg.progressive_tax(brackets, taxable_income)


class AccountType(Enum):
    """
    Types of investment accounts with different tax treatments.

    Attributes:
        TRADITIONAL_401K: Traditional 401(k) - pre-tax contributions, taxed on withdrawal
        TRADITIONAL_IRA: Traditional IRA - pre-tax contributions, taxed on withdrawal
        ROTH_401K: Roth 401(k) - post-tax contributions, tax-free withdrawals
        ROTH_IRA: Roth IRA - post-tax contributions, tax-free withdrawals
        TAXABLE: Taxable brokerage account - capital gains treatment
        HSA: Health Savings Account - triple tax advantaged
        CASH: Cash savings account - no growth, no tax
        COLLEGE_529: 529 education savings - tax-free for qualified education expenses
    """
    TRADITIONAL_401K = "traditional_401k"
    TRADITIONAL_IRA = "traditional_ira"
    ROTH_401K = "roth_401k"
    ROTH_IRA = "roth_ira"
    TAXABLE = "taxable"
    HSA = "hsa"
    CASH = "cash"
    COLLEGE_529 = "college_529"


# Distributions from these count as retirement income for state exclusions.
_TRADITIONAL_TYPES = (AccountType.TRADITIONAL_401K, AccountType.TRADITIONAL_IRA)


@dataclass
class Account:
    """
    Individual investment account with balance tracking and tax treatment.

    Attributes:
        name: Account identifier (e.g., 'your_401k', 'partner_roth_ira')
        account_type: Type of account determining tax treatment
        balance: Current account balance
        owner: Account owner ('you', 'partner', or 'child1', 'child2', ... for 529s)
        cost_basis: For taxable accounts, tracks cost basis for capital gains calculation
    """
    name: str
    account_type: AccountType
    balance: float
    owner: str
    cost_basis: float = 0.0

    def __post_init__(self):
        if self.account_type == AccountType.TAXABLE:
            self.cost_basis = self.balance * DEFAULT_COST_BASIS_RATIO


@dataclass
class TaxBrackets:
    """
    Progressive federal income-tax brackets.

    The default field is the 2024 married-filing-jointly schedule; callers pass
    ``brackets=cfg.get_federal_brackets()`` to select the MFJ / Single / HOH
    table for the active ``cfg.FILING_STATUS`` (finding #8).

    Implements the progressive federal income tax system where income
    is taxed at increasing marginal rates as income rises through brackets.

    Attributes:
        brackets: List of (income_threshold, tax_rate) tuples defining tax brackets
    """
    brackets: List[Tuple[float, float]] = field(default_factory=lambda: [
        (23_200, 0.10), (94_300, 0.12), (201_050, 0.22),
        (383_900, 0.24), (487_450, 0.32), (731_200, 0.35),
        (float('inf'), 0.37)
    ])

    def calculate_tax(self, taxable_income: float) -> float:
        """
        Calculate federal income tax using progressive bracket system.

        Args:
            taxable_income: Income after deductions

        Returns:
            Total federal income tax owed
        """
        return _progressive_tax(self.brackets, taxable_income)


@dataclass
class CaliforniaTaxBrackets:
    """
    California's married-filing-jointly schedule (2024, incl. the 1%
    mental-health surtax above $1M), read from state_tax_data.

    Kept as a convenience for callers that want the CA joint table directly.
    The engine itself uses StateIncomeTax, which covers every state, filing
    status, deduction and retirement-income rule. Exposes the
    ``calculate_tax(taxable_income)`` interface every state model shares.

    Attributes:
        brackets: List of (income_threshold, tax_rate) tuples defining CA tax brackets
    """
    brackets: List[Tuple[float, float]] = field(
        default_factory=lambda: list(cfg.state_tax_rules("CA", "MFJ")["brackets"]))

    def calculate_tax(self, taxable_income: float) -> float:
        """
        Calculate California state income tax using progressive bracket system.

        Args:
            taxable_income: Income after deductions

        Returns:
            Total California state income tax owed
        """
        return _progressive_tax(self.brackets, taxable_income)


@dataclass
class NoStateTax:
    """State tax model for states with no income tax (e.g. TX, FL, WA).

    Exposes the same ``calculate_tax(taxable_income)`` interface as
    CaliforniaTaxBrackets so it can be swapped in transparently.
    """
    brackets: List[Tuple[float, float]] = field(default_factory=lambda: [
        (float('inf'), 0.0)
    ])

    def calculate_tax(self, taxable_income: float) -> float:
        return 0.0


@dataclass
class FlatRateStateTax:
    """State tax model applying a single flat rate to all taxable income."""
    rate: float = 0.0

    def calculate_tax(self, taxable_income: float) -> float:
        if taxable_income <= 0:
            return 0.0
        return taxable_income * self.rate


@dataclass
class StateIncomeTax:
    """One STATE return: brackets, deduction and rules for one filing status.

    Built from ``cfg.state_tax_rules`` (state_tax_data.py: all 50 states + DC,
    plus "No state tax" and the flat-rate "Other"). ``calculate_tax`` takes
    income AFTER ``deduction`` (the state's standard deduction plus personal
    exemptions), like every other bracket model here.
    """
    rules: dict

    @property
    def code(self) -> str:
        return self.rules["code"]

    @property
    def deduction(self) -> float:
        return float(self.rules["deduction"])

    @property
    def brackets(self) -> List[Tuple[float, float]]:
        return self.rules["brackets"]

    def calculate_tax(self, taxable_income: float) -> float:
        return _progressive_tax(self.rules["brackets"], taxable_income)


def _select_state_tax_brackets(status=None, people=None) -> StateIncomeTax:
    """The state income-tax model of one return, from cfg.STATE_CHOICE.

    A two-letter code -> that state's table; "No state tax" -> zero; "Other" ->
    flat cfg.YOUR_MARGINAL_TAX_RATE above the federal standard deduction.
    Unknown values fall back to CA so existing results are unchanged.
    ``status``/``people`` default to the active filing status and the return's
    personal exemptions (two on a joint return with a partner, else one).
    """
    status = cfg.normalize_filing_status(status)
    if people is None:
        people = 2 if (status == cfg._FILING_MFJ and cfg.has_partner()) else 1
    return StateIncomeTax(cfg.state_tax_rules(getattr(cfg, "STATE_CHOICE", "CA"),
                                              status, people=people))


# Federal LTCG brackets, married filing jointly (kept for callers that read the
# joint table; every status is in cfg.LTCG_BRACKETS_BY_STATUS).
LTCG_BRACKETS = cfg.LTCG_BRACKETS_BY_STATUS[cfg._FILING_MFJ]


def calculate_ltcg_tax(gains: float, other_income: float, status=None) -> float:
    """Federal long-term capital gains tax (0% / 15% / 20%).

    ``gains`` stack on top of ``other_income`` (TAXABLE ordinary income, after
    the standard deduction), per the IRS Qualified Dividends and Capital Gain
    worksheet. ``status`` picks the bracket table (default the active one).
    """
    if gains <= 0:
        return 0
    brackets = cfg.LTCG_BRACKETS_BY_STATUS[cfg.normalize_filing_status(status)]
    tax = 0.0
    lower = 0.0
    start = max(0.0, other_income)
    end = start + gains
    for upper, rate in brackets:
        lo = max(start, lower)
        hi = min(end, upper)
        if hi > lo:
            tax += (hi - lo) * rate
        lower = upper
        if upper >= end:
            break
    return tax


# Helper: map AccountType to the coarse withdrawal-log category used by the UI.
# Returns None for account types we do not surface (e.g. COLLEGE_529).
def _withdrawal_category(account_type: "AccountType") -> Optional[str]:
    if account_type == AccountType.CASH:
        return 'cash'
    if account_type == AccountType.TAXABLE:
        return 'taxable'
    if account_type in (AccountType.TRADITIONAL_401K, AccountType.TRADITIONAL_IRA):
        return 'traditional'
    if account_type in (AccountType.ROTH_401K, AccountType.ROTH_IRA):
        return 'roth'
    if account_type == AccountType.HSA:
        return 'hsa'
    return None


def _withdrawal_order(your_age: float, is_medical: bool) -> List[Tuple[List["AccountType"], str]]:
    """
    Return the tax-efficient withdrawal order as a list of
    (account_types, tax_treatment) tuples.

    Selection mirrors the prior inline tables in _withdraw_single_pass:
    - Non-medical: before age 59.5 prioritize penalty-free accounts (Roth
      contributions ahead of traditional; HSA non-medical last); after 59.5
      use the standard order (traditional before Roth).
    - Medical: HSA first (tax-free for qualified medical), then the same
      remaining ordering split on the 59.5 boundary.
    """
    if is_medical:
        if your_age < cfg.EARLY_WITHDRAWAL_AGE_401K_IRA:
            return [
                ([AccountType.CASH], "none"),
                ([AccountType.HSA], "none"),  # Tax-free for medical
                ([AccountType.TAXABLE], "ltcg"),
                ([AccountType.ROTH_401K, AccountType.ROTH_IRA], "roth_early"),
                ([AccountType.TRADITIONAL_401K, AccountType.TRADITIONAL_IRA], "income_early"),
            ]
        return [
            ([AccountType.CASH], "none"),
            ([AccountType.HSA], "none"),
            ([AccountType.TAXABLE], "ltcg"),
            ([AccountType.TRADITIONAL_401K, AccountType.TRADITIONAL_IRA], "income"),
            ([AccountType.ROTH_401K, AccountType.ROTH_IRA], "none"),
        ]

    if your_age < cfg.EARLY_WITHDRAWAL_AGE_401K_IRA:
        return [
            ([AccountType.CASH], "none"),
            ([AccountType.TAXABLE], "ltcg"),
            # Roth CONTRIBUTIONS can be withdrawn tax/penalty-free
            ([AccountType.ROTH_401K, AccountType.ROTH_IRA], "roth_early"),
            # Traditional accounts: income tax + 10% penalty
            ([AccountType.TRADITIONAL_401K, AccountType.TRADITIONAL_IRA], "income_early"),
            # HSA for non-medical: income tax + 20% penalty (WORST option, last resort)
            # HSA should be LAST before age 65 for non-medical (20% > 10% penalty)
            ([AccountType.HSA], "none" if is_medical else "hsa_nonmedical"),
        ]
    # After 59.5, standard withdrawal order
    return [
        ([AccountType.CASH], "none"),
        ([AccountType.TAXABLE], "ltcg"),
        ([AccountType.TRADITIONAL_401K, AccountType.TRADITIONAL_IRA], "income"),
        ([AccountType.ROTH_401K, AccountType.ROTH_IRA], "none"),
        # A non-medical HSA draw keeps its 20% additional tax until age 65
        # (cfg.EARLY_WITHDRAWAL_AGE_HSA), NOT 59.5 — tagging it "income" across the
        # whole >=59.5 branch skipped the penalty for ages 59.5-64 and made the
        # 'hsa_nonmedical' handler's own 65 guard unreachable.
        ([AccountType.HSA],
         "none" if is_medical
         else ("income" if your_age >= cfg.EARLY_WITHDRAWAL_AGE_HSA else "hsa_nonmedical")),
    ]


def _level_payment(balance: float, annual_rate: float, years: int) -> float:
    """Level monthly principal + interest that retires ``balance`` over ``years``.

    Used to build an amortization schedule anchored to the loan balance the user
    actually entered, so home equity can be credited with principal repayment.
    Deliberately derived from (balance, term) at the engine's standard
    ``MORTGAGE_RATE_FOR_PAYOFF`` rather than from the stored monthly payment,
    which is all-in (it includes property tax and insurance).
    """
    try:
        balance = max(0.0, float(balance))
        years = int(years)
    except (TypeError, ValueError):
        return 0.0
    if balance <= 0 or years <= 0:
        return 0.0
    n = years * 12
    r = max(0.0, float(annual_rate)) / 12.0
    if r <= 0:
        return balance / n
    return balance * r / (1.0 - (1.0 + r) ** -n)


class AccountPortfolio:
    """
    Manages multiple accounts with tax-efficient strategies.

    Implements realistic tax modeling including:
    - Federal income tax with standard deduction, by filing status
    - State income tax (any state, from state_tax_data)
    - Two separate returns for an unmarried couple, each person's income on
      their own (the partner's share is tracked in the year_partner_* fields)
    - Social Security taxation (up to 85% taxable)
    - Early withdrawal penalties (10% on 401k/IRA before 59.5)
    - Net Investment Income Tax (NIIT) 3.8% surtax
    - Medicare IRMAA surcharges for high earners
    """

    def __init__(self):
        self.accounts: Dict[str, Account] = {}
        # Returns filed this year. A married couple or a single person files one
        # (keyed "you"); an unmarried couple files two -- "you" on
        # cfg.FILING_STATUS and "partner" as Single -- and each person's income
        # is taxed on their own return (cfg.files_two_returns).
        self.two_returns = cfg.files_two_returns()
        self.return_status = {"you": cfg.return_status("you"),
                              "partner": cfg.return_status("partner")}
        # Federal brackets selected from cfg.FILING_STATUS (MFJ / Single / HOH).
        # MFJ remains the default (byte-identical to the prior hardcoded table);
        # Single/HOH pull the 2024 IRS schedules so the filing-status selector
        # actually changes federal tax (finding #8).
        self.federal_tax_brackets = TaxBrackets(
            brackets=list(cfg.get_federal_brackets(self.return_status["you"])))
        # State income-tax model of the primary return, from cfg.STATE_CHOICE
        # (any state; "No state tax" -> zero, "Other" -> flat rate). The
        # attribute keeps its historical name.
        self.ca_tax_brackets = _select_state_tax_brackets(self.return_status["you"])
        if self.two_returns:
            self._partner_federal_brackets = TaxBrackets(
                brackets=list(cfg.get_federal_brackets(cfg._FILING_SINGLE)))
            self._partner_state_tax = _select_state_tax_brackets(cfg._FILING_SINGLE, people=1)
        else:
            self._partner_federal_brackets = self.federal_tax_brackets
            self._partner_state_tax = self.ca_tax_brackets
        self.total_taxes_paid = 0.0
        self.total_early_withdrawal_penalties = 0.0
        self.total_niit_paid = 0.0
        self.total_ss_taxes_paid = 0.0
        self.yearly_history: List[Dict] = []
        self.home_equity = cfg.HOME_EQUITY * cfg.HOME_EQUITY_ACCESSIBLE_PCT
        self.home_equity_used = 0.0
        # --- Home state for the housing timeline (cfg.housing_events) --------
        # These mirror the config's housing representation so that, with no
        # timeline (no HOME_EVENTS, no legacy house move), the engine reads
        # mortgage payment + payoff from config exactly as before
        # (byte-identical). When an event fires, apply_housing_events() mutates
        # this state (sell, buy, start renting) and the expense paths read the
        # engine values instead of config.
        self.mortgage_annual = float(cfg.MORTGAGE_ANNUAL)
        self.mortgage_payoff_age = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING
        self.mortgage_monthly = float(cfg.MORTGAGE_MONTHLY)
        self.home_value = float(cfg.HOME_VALUE)
        # Monthly rent while renting (0 once a home is bought).
        self.rent_monthly = (float(getattr(cfg, "SPEND_RENT_MONTHLY", 0) or 0)
                             if cfg.is_renter() else 0.0)
        # What today's home cost, for tax on its sale. None = no taxable gain
        # (basis = its value when sold); a purchased home's basis is its price.
        basis = getattr(cfg, "HOME_COST_BASIS", None)
        self.home_cost_basis = None if basis is None else float(basis)
        self.house_moved = False          # True once any housing event has fired
        self._home_events = None          # normalized timeline, read on first use
        self._home_events_done = set()
        # Loan balance, tracked so principal repayment can be credited to the
        # accessible-equity reserve (see refresh_home_equity). Anchored at the
        # KNOWN starting balance; the P&I payment is derived from it rather than
        # read off ``mortgage_monthly`` because that figure is all-in (it bundles
        # property tax + insurance) and would overstate principal paydown.
        self.mortgage_balance = float(cfg.MORTGAGE_BALANCE)
        # Rate of the loan currently being paid down (switches at a house move).
        self._mortgage_rate = float(cfg.MORTGAGE_RATE_FOR_PAYOFF)
        self._mortgage_pi = _level_payment(
            self.mortgage_balance, self._mortgage_rate,
            cfg.MORTGAGE_YEARS_REMAINING,
        )
        self._last_recorded_age = None
        # Count of working years where spending + after-tax electives exceeded
        # after-tax income (accumulation sweep found no surplus to invest). The
        # UI can surface this; it never crashes the sim.
        self.overspent_years = 0
        self.year_ordinary_income = 0.0
        # Cumulative income recognized this year that the ACTIVE state model
        # exempts from state tax (Social Security where the state exempts it,
        # retirement-income exclusions). Subtracted from year_ordinary_income
        # wherever a STATE (not federal) taxable base is computed. See
        # _state_taxable_base().
        self.year_state_exempt_income = 0.0
        self.year_investment_income = 0.0  # Track for NIIT calculation
        # The partner's own-return part of the three totals above (two returns
        # only; always 0 on a joint or single return). The primary's part is
        # the total minus this, so code that sets year_ordinary_income directly
        # keeps attributing it to the primary.
        self.year_partner_income = 0.0
        self.year_partner_state_exempt = 0.0
        self.year_partner_investment = 0.0
        # Retirement-income exclusion used so far this year, per person.
        self._retirement_excluded = {"you": 0.0, "partner": 0.0}
        self.total_roth_conversions = 0.0
        self.roth_conversion_taxes = 0.0
        # --- Early-retirement access strategies -----------------------------
        # Age the owner separated from service. Set when retirement begins; the
        # Rule of 55 needs it because the exception depends on the age you LEFT
        # the employer, not just your current age.
        self.separation_age = None
        # 72(t) SEPP: the annual payment is fixed at the schedule's start age.
        self.sepp_annual_amount = None
        self.sepp_start_age = None
        # Notional balance of the sub-account designated for the 72(t). None means
        # "no carve-out — the schedule acts on the whole traditional balance".
        self.sepp_carveout_balance = None
        self.total_sepp_distributions = 0.0
        # Roth conversion ladder: dated cohorts of converted PRINCIPAL, so the
        # 5-year seasoning rule can be enforced. [(age_converted, amount), ...]
        self.roth_conversion_cohorts: List[Tuple[float, float]] = []
        # Cumulative ORDINARY Roth contribution basis: direct/backdoor Roth IRA
        # contributions and mega-backdoor after-tax 401(k) dollars, plus whatever
        # Roth balance the household started with. Unlike converted principal this
        # money is ALWAYS withdrawable tax- and penalty-free at any age, so the
        # ROTH_LADDER_ENABLED branch must count it as free room -- otherwise
        # enabling the ladder penalizes contributions that the IRS never
        # penalizes. Maintained by add_account() and contribute().
        self.roth_contribution_basis = 0.0
        # Roth basis consumed so far by penalty-free ladder draws.
        self._roth_basis_drawn = 0.0
        # Contributions stopped because Coast FIRE kicked in (for reporting).
        self.coasting = False
        self.total_aca_premiums = 0.0
        self.total_medicare_premiums = 0.0
        # Track ages for standard deduction calculation
        self.current_your_age = cfg.YOUR_AGE
        self.current_partner_age = cfg.PARTNER_AGE
        # True in retirement years when a still-working partner's employer plan
        # covers the household (set each year by simulate_retirement_year).
        self.employer_health_coverage = False
        # Track for dynamic spending guardrails
        self.initial_retirement_portfolio = 0.0
        self.target_portfolio_inflation_adjusted = 0.0
        # Track LTC costs
        self.total_ltc_costs = 0.0
        self.ltc_needs_by_age = {}  # Store whether LTC is needed for each age
        # Per-year withdrawal log (populated during retirement phase). Each entry:
        #   {'age', 'cash', 'taxable', 'traditional', 'roth', 'hsa',
        #    'total', 'portfolio_value', 'withdrawal_pct',
        #    'total_taxes', 'ss_tax', 'niit', 'penalties'}
        # 'portfolio_value' is the PRE-withdrawal total balance for the year (denominator).
        # 'total_taxes' is the real taxes paid that year (fed + state income + LTCG +
        #    NIIT + SS + RMD + Roth-conversion tax, excluding penalties); 'ss_tax',
        #    'niit', and 'penalties' are the separable components of that year.
        self.withdrawal_log: List[Dict] = []
        # Per-year household spending (today's/real dollars). Each row:
        #   {'age', 'living', 'total'} where 'living' is the guardrail-adjusted
        # base living expense (the amount markets + spending guardrails flex in
        # retirement) and 'total' additionally includes healthcare/LTC/car. Used
        # by the UI's spending-range boxplot to show the cross-scenario spread.
        self.spending_log: List[Dict] = []
        # Scratch accumulator: category-summed withdrawals for the CURRENT retirement year.
        # simulate_retirement_year() resets this at the start of each year and
        # appends a consolidated row to withdrawal_log at the end.
        self._current_year_withdrawals: Dict[str, float] = {
            'cash': 0.0, 'taxable': 0.0, 'traditional': 0.0, 'roth': 0.0, 'hsa': 0.0,
        }

    def set_retirement_baseline(self, inflation_factor: float = 1.0):
        """Set the baseline portfolio value at retirement for spending guardrails."""
        self.initial_retirement_portfolio = self.get_total_balance()
        self.target_portfolio_inflation_adjusted = self.initial_retirement_portfolio

    def update_target_portfolio(self, inflation_factor: float):
        """Update target portfolio for inflation (for spending guardrails)."""
        if self.initial_retirement_portfolio > 0:
            self.target_portfolio_inflation_adjusted = self.initial_retirement_portfolio * inflation_factor

    def add_account(self, account: Account):
        self.accounts[account.name] = account
        # A starting Roth balance is (for a pre-retirement household) contribution
        # basis, so credit it: the default non-ladder path already assumes Roth
        # draws come from contributions, and the ladder must not be stricter about
        # money that was never a conversion.
        if account.account_type in (AccountType.ROTH_IRA, AccountType.ROTH_401K):
            self.roth_contribution_basis += max(0.0, float(account.balance))

    def get_total_balance(self) -> float:
        return sum(a.balance for a in self.accounts.values())

    def get_investable_balance(self) -> float:
        """Spendable investable portfolio.

        Excludes earmarked 529 college balances, which ``_withdrawal_order``
        never taps for retirement, so they can't fund living expenses. This is
        the measure the net-worth-to-retire trigger uses (home equity isn't an
        account here, so it's already excluded).
        """
        return sum(a.balance for a in self.accounts.values()
                   if a.account_type != AccountType.COLLEGE_529)

    def get_balance_by_type(self) -> Dict[str, float]:
        by_type = {}
        for account in self.accounts.values():
            type_name = account.account_type.value
            by_type[type_name] = by_type.get(type_name, 0) + account.balance
        return by_type

    def reset_yearly_income(self):
        """Reset yearly income tracking at the start of each year."""
        self.year_ordinary_income = 0.0
        self.year_state_exempt_income = 0.0
        self.year_investment_income = 0.0
        self.year_partner_income = 0.0
        self.year_partner_state_exempt = 0.0
        self.year_partner_investment = 0.0
        self._retirement_excluded = {"you": 0.0, "partner": 0.0}

    def update_ages(self, your_age: int):
        """Update tracked ages for standard deduction calculation."""
        self.current_your_age = your_age
        self.current_partner_age = your_age - (cfg.YOUR_AGE - cfg.PARTNER_AGE)

    # ------------------------------------------------------------------
    # Returns: one (joint or single) or two (unmarried couple). ``owner`` is an
    # account owner ("you"/"partner"); ``ret`` is the return it lands on.
    # ------------------------------------------------------------------
    def _return_of(self, owner: str = "you") -> str:
        return "partner" if (self.two_returns and owner == "partner") else "you"

    def _return_income(self, ret: str = "you") -> float:
        if ret == "partner":
            return self.year_partner_income
        return self.year_ordinary_income - self.year_partner_income

    def _return_investment(self, ret: str = "you") -> float:
        if ret == "partner":
            return self.year_partner_investment
        return self.year_investment_income - self.year_partner_investment

    def _federal_model(self, ret: str = "you") -> "TaxBrackets":
        return self._partner_federal_brackets if ret == "partner" else self.federal_tax_brackets

    def _state_model(self, ret: str = "you"):
        return self._partner_state_tax if ret == "partner" else self.ca_tax_brackets

    def get_standard_deduction(self, owner: str = "you") -> float:
        """Federal standard deduction of ``owner``'s return, from current ages."""
        if not self.two_returns:
            return cfg.get_standard_deduction(self.current_your_age, self.current_partner_age)
        if self._return_of(owner) == "partner":
            return cfg.standard_deduction_for_return(cfg._FILING_SINGLE, [self.current_partner_age])
        return cfg.standard_deduction_for_return(self.return_status["you"], [self.current_your_age])

    def _state_taxable_base(self, ret: str = "you") -> float:
        """Ordinary income actually subject to STATE tax this year on a return.

        Equal to the return's ordinary income (the federal-stacking total)
        minus whatever's been recognized as state-exempt so far (Social
        Security where the state exempts it, retirement-income exclusions).
        Federal calculations must keep using the ordinary income directly --
        this base is state-only.
        """
        if ret == "partner":
            return max(0.0, self.year_partner_income - self.year_partner_state_exempt)
        return max(0.0, (self.year_ordinary_income - self.year_partner_income)
                   - (self.year_state_exempt_income - self.year_partner_state_exempt))

    def _state_exempt_portion(self, income: float, owner: str, is_social_security: bool,
                              retirement: bool) -> float:
        """How much of ``income`` the return's state exempts (pure, no mutation).

        Social Security follows the state's rule (exempt, taxed, or exempt below
        an income limit); traditional 401(k)/IRA distributions use the owner's
        remaining yearly retirement-income exclusion at their current age.
        """
        if income <= 0:
            return 0.0
        ret = self._return_of(owner)
        rules = getattr(self._state_model(ret), "rules", None)
        if not rules:
            return 0.0
        if is_social_security:
            agi = self._return_income(ret) + self._return_investment(ret) + income
            return income if cfg.state_exempts_social_security(rules, agi) else 0.0
        if retirement:
            who = "partner" if owner == "partner" else "you"
            age = self.current_partner_age if who == "partner" else self.current_your_age
            room = cfg.state_retirement_exclusion(rules, age) - self._retirement_excluded[who]
            return min(income, max(0.0, room))
        return 0.0

    def calculate_federal_tax_with_deduction(self, gross_income: float) -> float:
        """
        Calculate federal tax after applying standard deduction.

        This is the CORRECT way to calculate federal tax - apply the
        standard deduction BEFORE calculating tax.
        """
        standard_deduction = self.get_standard_deduction()
        taxable_income = max(0, gross_income - standard_deduction)
        return self.federal_tax_brackets.calculate_tax(taxable_income)

    def quote_marginal_tax_on_income(self, income: float, is_state_taxable: bool = True,
                                     owner: str = "you", retirement: bool = False) -> float:
        """
        Return the marginal federal + state tax on ``income`` stacked on top of
        the income already recognized on ``owner``'s return this year, WITHOUT
        mutating any state.

        Kept side-effect-free so it can be used for a provisional estimate (e.g.
        sizing withdrawals against a taxable-SS quote) and then again for the
        final booked tax, without double-counting income into
        ``year_ordinary_income``. ``calculate_marginal_tax_on_income`` delegates
        here and adds the side effect.

        ``is_state_taxable=False`` marks the income as taxable Social Security:
        the state's Social Security rule decides whether it is state-exempt
        (most states exempt it) without touching the federal side -- see
        ``_state_taxable_base``. ``retirement=True`` marks a traditional
        401(k)/IRA distribution, eligible for the state's retirement-income
        exclusion. ``owner`` picks the return on an unmarried couple's two.
        """
        if income <= 0:
            return 0

        ret = self._return_of(owner)
        base = self._return_income(ret)

        # Federal tax using taxable income (after the standard deduction)
        std_deduction = self.get_standard_deduction(owner)
        federal = self._federal_model(ret)
        taxable_before = max(0, base - std_deduction)
        taxable_after = max(0, base + income - std_deduction)
        federal_tax = federal.calculate_tax(taxable_after) - federal.calculate_tax(taxable_before)

        # State tax on the non-exempt part, after the state's own deduction.
        state = self._state_model(ret)
        state_deduction = getattr(state, "deduction", cfg.CA_STANDARD_DEDUCTION_MFJ_2024)
        state_base = self._state_taxable_base(ret)
        taxable_part = income - self._state_exempt_portion(
            income, owner, not is_state_taxable, retirement)
        state_taxable_before = max(0, state_base - state_deduction)
        state_taxable_after = max(0, state_base + taxable_part - state_deduction)
        state_tax = state.calculate_tax(state_taxable_after) - state.calculate_tax(state_taxable_before)

        return federal_tax + state_tax

    def calculate_marginal_tax_on_income(self, income: float, is_state_taxable: bool = True,
                                         owner: str = "you", retirement: bool = False) -> float:
        """
        Calculate marginal tax on additional income with standard deduction, and
        RECOGNIZE that income into ``year_ordinary_income`` (side-effecting).

        The standard deduction is applied to total income before calculating
        the marginal tax on additional income.

        The state-exempt part (Social Security under ``is_state_taxable=False``,
        a ``retirement`` distribution's exclusion) is also recognized into
        ``year_state_exempt_income`` so LATER same-year income (another
        withdrawal, an LTCG event) correctly computes ITS state tax as if this
        income had never entered the state base.
        """
        if income <= 0:
            return 0

        exempt = self._state_exempt_portion(income, owner, not is_state_taxable, retirement)
        tax = self.quote_marginal_tax_on_income(income, is_state_taxable=is_state_taxable,
                                                owner=owner, retirement=retirement)
        ret = self._return_of(owner)
        self.year_ordinary_income += income
        if ret == "partner":
            self.year_partner_income += income
        if exempt > 0:
            self.year_state_exempt_income += exempt
            if ret == "partner":
                self.year_partner_state_exempt += exempt
            if retirement:
                self._retirement_excluded["partner" if owner == "partner" else "you"] += exempt
        return tax

    def apply_returns(self, annual_return: float):
        for account in self.accounts.values():
            if account.account_type != AccountType.CASH:
                growth = account.balance * annual_return
                account.balance += growth
        # The designated 72(t) sub-account is real traditional money (already grown
        # above); this notional ledger tracks how much of it is left, so it has to
        # grow at the same rate or the schedule would appear to exhaust it early.
        if self.sepp_carveout_balance:
            self.sepp_carveout_balance *= (1.0 + annual_return)

    def contribute(self, account_name: str, amount: float):
        if account_name in self.accounts:
            self.accounts[account_name].balance += amount
            if self.accounts[account_name].account_type == AccountType.TAXABLE:
                self.accounts[account_name].cost_basis += amount
            elif self.accounts[account_name].account_type in (
                AccountType.ROTH_IRA, AccountType.ROTH_401K
            ):
                # Direct/backdoor Roth IRA and mega-backdoor after-tax 401(k)
                # dollars: always penalty-free basis. (Roth CONVERSIONS bypass
                # contribute() -- perform_roth_conversion credits the balance
                # directly and records a dated cohort instead.)
                self.roth_contribution_basis += max(0.0, float(amount))

    def withdraw_tax_efficient(self, amount_needed: float, is_medical: bool = False,
                               your_age: float = 60) -> Tuple[float, float]:
        """
        Withdraw enough to cover a NET cash need, funding the income tax and
        early-withdrawal penalties out of additional withdrawals ("gross-up").

        The single-pass helper below withdraws a gross target and returns the
        gross withdrawn plus the tax+penalty it incurred. Because that tax is
        itself funded from the portfolio (and the tax on the gross-up is again
        taxable), we iterate: fund the net need, then keep funding whatever net
        shortfall remains after taxes/penalties, until the shortfall is within
        GROSSUP_TOLERANCE, a pass can withdraw nothing (portfolio depleted), or
        we hit GROSSUP_MAX_ITERATIONS. State (balances, cost basis, year income,
        penalty/NIIT totals, per-year withdrawal buckets) accumulates naturally
        across passes because each pass resumes from the current balances.

        Args:
            amount_needed: NET amount that must remain after taxes/penalties
            is_medical: Whether withdrawal is for qualified medical expenses
            your_age: Current age (for early withdrawal penalty calculation)

        Returns:
            Tuple of (total_amount_withdrawn, total_taxes_and_penalties_paid)
        """
        total_withdrawn = 0.0
        total_cost = 0.0
        # Net cash delivered so far = gross withdrawn minus taxes/penalties paid.
        net_shortfall = amount_needed

        for _ in range(GROSSUP_MAX_ITERATIONS):
            if net_shortfall <= GROSSUP_TOLERANCE:
                break
            withdrawn, cost = self._withdraw_single_pass(
                net_shortfall, is_medical=is_medical, your_age=your_age
            )
            total_withdrawn += withdrawn
            total_cost += cost
            # Recompute the outstanding NET shortfall: what we still owe minus
            # the additional net cash this pass delivered (gross minus its cost).
            net_shortfall -= (withdrawn - cost)
            if withdrawn <= 0:
                # Portfolio (including home-equity backup) is exhausted; no
                # further pass can reduce the shortfall. Stop to preserve the
                # depletion / failure condition upstream.
                break

        return total_withdrawn, total_cost

    def _withdraw_single_pass(self, amount_needed: float, is_medical: bool = False,
                              your_age: float = 60) -> Tuple[float, float]:
        """
        Withdraw a GROSS target from accounts in tax-efficient order, applying
        early-withdrawal penalties, and return the gross withdrawn plus the
        tax+penalty incurred.

        This is one pass of the gross-up solver in withdraw_tax_efficient(); it
        does NOT itself fund the taxes it computes. Callers other than the
        gross-up loop should not use it directly.

        Args:
            amount_needed: Gross amount to withdraw this pass
            is_medical: Whether withdrawal is for qualified medical expenses
            your_age: Current age (for early withdrawal penalty calculation)

        Returns:
            Tuple of (gross_withdrawn, taxes_and_penalties_paid)
        """
        remaining = amount_needed
        taxes_paid = 0.0
        penalties_paid = 0.0
        withdrawals = []

        # Withdrawal order - adjusted to avoid early withdrawal penalties when
        # possible, with medical expenses prioritizing the HSA (tax-free for
        # qualified medical). See _withdrawal_order for the full selection logic.
        withdrawal_order = _withdrawal_order(your_age, is_medical)

        for account_types, tax_treatment in withdrawal_order:
            if remaining <= 0:
                break
            for account in self.accounts.values():
                if remaining <= 0:
                    break
                if account.account_type in account_types and account.balance > 0:
                    withdraw_amount = min(remaining, account.balance)
                    tax = 0
                    penalty = 0

                    if tax_treatment == "none":
                        tax = 0
                        penalty = 0

                    elif tax_treatment == "ltcg":
                        if account.balance > MINIMUM_PORTFOLIO_VALUE:
                            gains_ratio = max(0, min(1, 1 - account.cost_basis / account.balance))
                            gains = withdraw_amount * gains_ratio

                            # Federal LTCG tax. Per the IRS Qualified Dividends &
                            # Capital Gain worksheet, gains stack on TAXABLE ordinary
                            # income (gross minus the standard deduction), not gross.
                            #
                            # Gains already realized EARLIER THIS YEAR must be part of
                            # the stacking base too, or every taxable account in the
                            # withdrawal order — and every iteration of the gross-up
                            # loop — restarts at the bottom of the 0% bracket. The
                            # default portfolio shape (your_brokerage +
                            # partner_brokerage) was claiming the 0% bracket twice.
                            # Everything below is on the return of the
                            # account's owner (one return unless an unmarried
                            # couple files two).
                            ret = self._return_of(account.owner)
                            ret_status = self.return_status[ret]
                            prior_gains = self._return_investment(ret)
                            fed_std_deduction = self.get_standard_deduction(account.owner)
                            fed_taxable_ordinary = max(
                                0, self._return_income(ret) + prior_gains - fed_std_deduction
                            )
                            federal_ltcg = calculate_ltcg_tax(gains, fed_taxable_ordinary,
                                                              status=ret_status)

                            # States tax LTCG as ordinary income, less any
                            # state capital-gains exclusion.
                            state = self._state_model(ret)
                            state_gains = gains * (1.0 - float(
                                getattr(state, "rules", {}).get("ltcg_exclusion", 0.0) or 0.0))
                            state_deduction = getattr(state, "deduction",
                                                      cfg.CA_STANDARD_DEDUCTION_MFJ_2024)
                            state_base = self._state_taxable_base(ret) + prior_gains
                            state_taxable_before = max(0, state_base - state_deduction)
                            state_taxable_after = max(0, state_base + state_gains - state_deduction)
                            state_ltcg = state.calculate_tax(state_taxable_after) - \
                                state.calculate_tax(state_taxable_before)

                            # Track investment income for NIIT
                            self.year_investment_income += gains
                            if ret == "partner":
                                self.year_partner_investment += gains

                            # NIIT (3.8% on investment income above the
                            # return's MAGI threshold)
                            total_magi = self._return_income(ret) + self._return_investment(ret)
                            niit = cfg.calculate_niit(
                                total_magi, gains,
                                years_from_start=max(0, (self.current_your_age or cfg.YOUR_AGE) - cfg.YOUR_AGE),
                                status=ret_status,
                            )
                            self.total_niit_paid += niit

                            tax = federal_ltcg + state_ltcg + niit

                            # Update cost basis
                            if account.balance > withdraw_amount:
                                account.cost_basis *= (1 - withdraw_amount / account.balance)
                            else:
                                account.cost_basis = 0
                        else:
                            tax = 0
                            account.cost_basis = 0

                    elif tax_treatment == "income":
                        # Regular income tax (after 59.5, no penalty)
                        tax = self.calculate_marginal_tax_on_income(
                            withdraw_amount, owner=account.owner,
                            retirement=account.account_type in _TRADITIONAL_TYPES)

                    elif tax_treatment == "income_early":
                        # Income tax PLUS 10% early withdrawal penalty — unless
                        # an exception applies (Rule of 55 on an employer plan,
                        # or an active 72(t) SEPP schedule).
                        tax = self.calculate_marginal_tax_on_income(
                            withdraw_amount, owner=account.owner,
                            retirement=account.account_type in _TRADITIONAL_TYPES)
                        # 72(t) coverage is NOT claimed here. A SEPP exempts only
                        # the SCHEDULED distribution, and that distribution never
                        # reaches this function -- _collect_sepp takes it directly
                        # off the traditional balances (penalty-free) before any
                        # discretionary withdrawal runs. Every dollar that DOES
                        # arrive here is therefore an extra, unscheduled draw,
                        # which is fully penalized (and in reality would bust the
                        # schedule if it touched the designated sub-account).
                        # Previously a plain `sepp_active` boolean was passed as
                        # sepp_covered for the ENTIRE withdraw_amount, with no
                        # reference to the SEPP amount or the designated balance,
                        # turning an active 72(t) into a universal penalty waiver.
                        penalty = cfg.calculate_early_withdrawal_penalty(
                            withdraw_amount, account.account_type.value, your_age,
                            separation_age=self.separation_age,
                            sepp_covered=False,
                        )
                        self.total_early_withdrawal_penalties += penalty

                    elif tax_treatment == "hsa_nonmedical":
                        # HSA non-medical before 65: income tax + 20% penalty
                        tax = self.calculate_marginal_tax_on_income(withdraw_amount,
                                                                    owner=account.owner)
                        if your_age < cfg.EARLY_WITHDRAWAL_AGE_HSA:
                            penalty = cfg.calculate_early_withdrawal_penalty(
                                withdraw_amount, 'hsa', your_age, is_medical=False
                            )
                            self.total_early_withdrawal_penalties += penalty

                    elif tax_treatment == "roth_early":
                        # Roth before 59.5. Default simplification: assume the
                        # draw comes from contributions, which are always
                        # tax/penalty-free.
                        tax = 0
                        penalty = 0
                        if getattr(cfg, "ROTH_LADDER_ENABLED", False):
                            # Ladder mode ENFORCES the 5-year rule instead: only
                            # SEASONED conversion principal PLUS ordinary
                            # contribution basis escapes the penalty. Anything
                            # beyond that is earnings or unseasoned conversion
                            # money and is penalized.
                            #
                            # roth_contribution_basis is what the comment always
                            # claimed but nothing actually tracked: direct/backdoor
                            # Roth contributions and mega-backdoor after-tax 401(k)
                            # dollars. Omitting it meant free_room was 0 for a Roth
                            # made entirely of contributions, so enabling the
                            # ladder penalized money the IRS never penalizes and
                            # made the strategy look strictly worse than leaving it
                            # off.
                            seasoned = self.seasoned_conversion_basis(your_age)
                            basis = getattr(self, "roth_contribution_basis", 0.0)
                            used = getattr(self, "_roth_basis_drawn", 0.0)
                            free_room = max(0.0, seasoned + basis - used)
                            penalized = max(0.0, withdraw_amount - free_room)
                            self._roth_basis_drawn = used + min(withdraw_amount, free_room)
                            if penalized > 0:
                                penalty = penalized * cfg.EARLY_WITHDRAWAL_PENALTY_401K_IRA
                                self.total_early_withdrawal_penalties += penalty

                    account.balance -= withdraw_amount
                    remaining -= withdraw_amount
                    taxes_paid += tax
                    penalties_paid += penalty
                    withdrawals.append((account.name, withdraw_amount, tax, penalty))

                    # Per-year withdrawal tracking: bucket by account category.
                    # simulate_retirement_year() flushes these into withdrawal_log.
                    category = _withdrawal_category(account.account_type)
                    if category is not None:
                        self._current_year_withdrawals[category] = (
                            self._current_year_withdrawals.get(category, 0.0) + withdraw_amount
                        )

        # Use home equity as last resort
        if remaining > 0 and self.home_equity > 0 and cfg.USE_HOME_AS_BACKUP:
            home_contribution = min(remaining, self.home_equity)
            self.home_equity -= home_contribution
            self.home_equity_used += home_contribution
            remaining -= home_contribution

        total_cost = taxes_paid + penalties_paid
        self.total_taxes_paid += total_cost
        return amount_needed - remaining, total_cost

    def _amortize_year_capped(self, extra_annual: float = 0.0):
        """Run 12 months of amortization, capping extra principal at what the
        loan can actually absorb.

        Returns ``(end_balance, extra_actually_applied)`` and mutates nothing, so
        the expense calculation and the balance update can agree in the payoff
        year. Without the cap the scheduled payment can retire the loan in, say,
        month 3 while the full year's extra is still billed as an outflow --
        cash leaves the portfolio against principal that no longer exists.

        With ``extra_annual=0`` the balance is identical to the previous
        scheduled-only amortization.
        """
        bal = max(0.0, self.mortgage_balance)
        if bal <= 0 or self._mortgage_pi <= 0:
            return bal, 0.0
        r = max(0.0, getattr(self, "_mortgage_rate", cfg.MORTGAGE_RATE_FOR_PAYOFF)) / 12.0
        extra_monthly = max(0.0, float(extra_annual or 0.0)) / 12.0
        applied = 0.0
        for _ in range(12):
            if bal <= 0:
                break
            after_scheduled = bal * (1.0 + r) - self._mortgage_pi
            if after_scheduled <= 0:
                bal = 0.0
                break
            take = min(extra_monthly, after_scheduled)
            applied += take
            bal = after_scheduled - take
            if bal < 0.01:
                bal = 0.0
                break
        return (0.0 if bal < 0.01 else bal), applied

    def _amortize_mortgage_year(self, extra_annual: float = 0.0) -> None:
        """Advance the loan balance 12 months (principal repayment only).

        ``extra_annual`` is additional principal for the year, applied evenly
        across the 12 months (so it compounds into the interest saving the way a
        real monthly prepayment does, rather than as one year-end lump).
        """
        if self.mortgage_balance <= 0 or self._mortgage_pi <= 0:
            self.mortgage_balance = max(0.0, self.mortgage_balance)
            return
        self.mortgage_balance, _ = self._amortize_year_capped(extra_annual)

    def refresh_home_equity(self) -> None:
        """Recompute the accessible-equity reserve from value minus principal.

        ``home_equity_used`` (drawn as an emergency backstop) is netted out so a
        prior draw is not silently restored by the next year's paydown.
        """
        if not getattr(cfg, "TRACK_HOME_EQUITY_PAYDOWN", False):
            return
        gross = max(0.0, self.home_value - self.mortgage_balance)
        self.home_equity = max(
            0.0, gross * cfg.HOME_EQUITY_ACCESSIBLE_PCT - self.home_equity_used
        )

    def seasoned_conversion_basis(self, your_age: float) -> float:
        """Converted principal that has cleared the 5-year seasoning rule.

        This is the accessible rung of a Roth conversion ladder: principal
        converted at least ``ROTH_LADDER_SEASONING_YEARS`` ago comes out tax- and
        penalty-free even before 59.5. Money converted more recently has not
        seasoned yet.
        """
        years = getattr(cfg, "ROTH_LADDER_SEASONING_YEARS", 5)
        return sum(
            amount for (converted_at, amount) in self.roth_conversion_cohorts
            if float(your_age) - float(converted_at) >= years
        )

    def unseasoned_conversion_basis(self, your_age: float) -> float:
        """Converted principal still inside its 5-year window."""
        years = getattr(cfg, "ROTH_LADDER_SEASONING_YEARS", 5)
        return sum(
            amount for (converted_at, amount) in self.roth_conversion_cohorts
            if float(your_age) - float(converted_at) < years
        )

    def record_year(self, year: int, age: int):
        # A year has elapsed since the last snapshot -> pay down the mortgage and
        # re-derive the accessible equity. record_year() is the single per-year
        # boundary every simulation path already crosses exactly once, so this
        # covers accumulation, retirement and the net-worth-target variants
        # without touching each loop. The first (t=0) call only refreshes, so the
        # opening reserve still equals today's real equity.
        if self._last_recorded_age is not None and age > self._last_recorded_age:
            if getattr(cfg, "TRACK_HOME_EQUITY_PAYDOWN", False):
                # Extra principal is attributed to the year being CLOSED, which
                # is the year whose expense assembly already charged it.
                self._amortize_mortgage_year(
                    cfg.extra_mortgage_payment_for_age(self._last_recorded_age)
                    if hasattr(cfg, "extra_mortgage_payment_for_age") else 0.0
                )
        self._last_recorded_age = age
        self.refresh_home_equity()
        record = {
            'year': year, 'age': age, 'total': self.get_total_balance(),
            'by_type': self.get_balance_by_type(),
            'accounts': {name: acc.balance for name, acc in self.accounts.items()},
            'home_equity': self.home_equity, 'home_equity_used': self.home_equity_used,
            # Loan state, so the UI can chart real home equity (value − principal)
            # instead of the accessible reserve.
            'home_value': self.home_value,
            'mortgage_balance': self.mortgage_balance,
        }
        self.yearly_history.append(record)

    def perform_roth_conversion(self, your_age: int) -> Tuple[float, float]:
        """Perform Roth conversion to fill up lower tax brackets."""
        if not cfg.ENABLE_ROTH_CONVERSION:
            return 0.0, 0.0
        if your_age >= cfg.ROTH_CONVERSION_STOP_AGE:
            return 0.0, 0.0
        if self.two_returns:
            return self._perform_roth_conversion_two_returns(your_age)

        bracket_room = max(0, cfg.roth_conversion_target(self.return_status["you"])
                           - self.year_ordinary_income)
        if bracket_room <= 0:
            return 0.0, 0.0

        conversion_target = min(bracket_room, cfg.ROTH_CONVERSION_MAX_ANNUAL)

        trad_available = 0
        for account in self.accounts.values():
            if account.account_type in [AccountType.TRADITIONAL_401K, AccountType.TRADITIONAL_IRA]:
                trad_available += account.balance

        if trad_available <= 0:
            return 0.0, 0.0

        conversion_amount = min(conversion_target, trad_available)

        # CONSERVATION (#18b): route converted dollars to the SAME owner's Roth
        # IRA. A Roth conversion is per-account (you cannot convert your partner's
        # traditional balance into your own Roth), so drain each owner's
        # traditional accounts and credit the matching owner's Roth. Track the
        # converted amount per owner while draining, then deposit to that owner's
        # Roth (falling back to any available Roth if the owner lacks one).
        remaining_conversion = conversion_amount
        converted_by_owner: dict = {}
        for account in self.accounts.values():
            if remaining_conversion <= 0:
                break
            if account.account_type in [AccountType.TRADITIONAL_401K, AccountType.TRADITIONAL_IRA]:
                convert_from_this = min(remaining_conversion, account.balance)
                if convert_from_this <= 0:
                    continue
                account.balance -= convert_from_this
                remaining_conversion -= convert_from_this
                converted_by_owner[account.owner] = (
                    converted_by_owner.get(account.owner, 0.0) + convert_from_this
                )

        # Map each owner to their Roth IRA; deposit converted dollars there.
        roth_by_owner = {
            acct.owner: name
            for name, acct in self.accounts.items()
            if acct.account_type == AccountType.ROTH_IRA
        }
        for owner, amount in converted_by_owner.items():
            target = roth_by_owner.get(owner)
            if target is None:
                # Owner has no Roth IRA: fall back to any available Roth so the
                # converted dollars are not lost (conservation over attribution).
                target = next(iter(roth_by_owner.values()), None)
            if target is not None:
                self.accounts[target].balance += amount

        tax_paid = self.calculate_marginal_tax_on_income(conversion_amount)
        self.total_roth_conversions += conversion_amount
        self.roth_conversion_taxes += tax_paid
        # Record the cohort so the ladder's 5-year seasoning can be enforced.
        self.roth_conversion_cohorts.append((float(your_age), float(conversion_amount)))
        self.total_taxes_paid += tax_paid

        return conversion_amount, tax_paid

    def _perform_roth_conversion_two_returns(self, your_age: int) -> Tuple[float, float]:
        """Roth conversion for an unmarried couple: each person fills THEIR OWN
        return up to the target for its filing status, converting their own
        traditional money into their own Roth IRA. The yearly cap
        (ROTH_CONVERSION_MAX_ANNUAL) is shared by the household."""
        cap_left = float(cfg.ROTH_CONVERSION_MAX_ANNUAL)
        total_converted = 0.0
        total_tax = 0.0
        roth_by_owner = {
            acct.owner: name
            for name, acct in self.accounts.items()
            if acct.account_type == AccountType.ROTH_IRA
        }
        for owner in ("you", "partner"):
            room = max(0.0, cfg.roth_conversion_target(self.return_status[owner])
                       - self._return_income(owner))
            target = min(room, cap_left)
            if target <= 0:
                continue
            converted = 0.0
            for account in self.accounts.values():
                if converted >= target:
                    break
                if account.owner == owner and account.account_type in _TRADITIONAL_TYPES:
                    take = min(target - converted, account.balance)
                    if take > 0:
                        account.balance -= take
                        converted += take
            if converted <= 0:
                continue
            roth = roth_by_owner.get(owner) or next(iter(roth_by_owner.values()), None)
            if roth is not None:
                self.accounts[roth].balance += converted
            total_tax += self.calculate_marginal_tax_on_income(converted, owner=owner)
            total_converted += converted
            cap_left -= converted
        if total_converted <= 0:
            return 0.0, 0.0
        self.total_roth_conversions += total_converted
        self.roth_conversion_taxes += total_tax
        self.roth_conversion_cohorts.append((float(your_age), float(total_converted)))
        self.total_taxes_paid += total_tax
        return total_converted, total_tax

    def quote_health_insurance_cost(self, your_age: int, modified_agi: float,
                                     inflation_factor: float = 1.0) -> float:
        """
        Return the health insurance premium (ACA or Medicare with IRMAA) for the
        given MAGI WITHOUT mutating any running totals.

        Kept side-effect-free so it can be called for a provisional estimate
        (before withdrawals realize gains / Roth conversions add income) and then
        again for the true MAGI, without double-counting into the premium totals.

        Priced PER COVERED ADULT from each person's OWN age, because Medicare
        eligibility is individual. Branching on the primary's age alone meant an
        age-gapped couple lost the younger spouse's marketplace premium entirely
        the year the primary turned 65 (while still being billed TWO Medicare
        premiums, one of them for someone not yet eligible). With equal ages and
        the default MFJ status this is arithmetically identical to the old
        single-branch calculation.

        The MAGI-driven figure above is PREMIUMS ONLY.
        cfg.HEALTHCARE_COSTS_BY_AGE is wired in two different ways because its
        bands mean two different things (see config.py's note):

          * pre-65, the 'early_retirement' band IS the full-price premium, so it
            drives calculate_aca_premium's unsubsidized ceiling. No floor is
            applied here -- flooring would override a legitimate subsidy and
            charge a low-income early retiree full price. With
            cfg.MODEL_ACA_AGE_RATED on, the band is NOT used: the marketplace
            cost is the age/household-rated premium plus out-of-pocket from
            quote_marketplace_cost (which also covers children at home).
          * 65+, the 'medicare_*' bands are premium PLUS care, and out-of-pocket
            is charged nowhere else in the engine, so the band acts as an ALL-IN
            floor. max() rather than sum() avoids double-counting the premium,
            and IRMAA still wins where it exceeds the band. The bands are for a
            couple: each Medicare adult is charged half the band for their OWN
            age (cfg.healthcare_cost_per_adult), so a single person pays one share.

        Covered adults = you plus a partner whenever there is one
        (cfg.has_partner), married or not: an unmarried partner needs coverage
        too.
        """
        ages = [your_age] + ([self.current_partner_age] if cfg.has_partner() else [])
        n_adults = len(ages)
        if n_adults == 0:
            return 0.0

        on_medicare = sum(1 for a in ages if a >= cfg.MEDICARE_AGE)
        on_marketplace = n_adults - on_medicare

        total = 0.0
        if on_medicare:
            # IRMAA is based on MAGI from 2 years prior; we use current-year MAGI
            # as an approximation.
            total += cfg.calculate_medicare_irmaa(
                modified_agi, inflation_factor, enrollees=on_medicare
            )
            # All-in (premium + care) floor on the Medicare members only -- see
            # docstring. One per-adult share per Medicare member, each by their
            # own age, applied BEFORE a pre-65 spouse's marketplace cost is added
            # so that cost can't mask it.
            if getattr(cfg, "MODEL_HEALTHCARE_COST_FLOOR", False):
                all_in = sum(cfg.healthcare_cost_per_adult(a, inflation_factor)
                             for a in ages if a >= cfg.MEDICARE_AGE)
                total = max(total, all_in)
        if self.employer_health_coverage:
            pass  # the working partner's employer plan covers the pre-Medicare household
        elif getattr(cfg, "MODEL_ACA_AGE_RATED", False):
            # Age/household-rated premium + out-of-pocket for the marketplace
            # members (pre-Medicare adults + children at home). See config.py.
            premium, oop = self.quote_marketplace_cost(
                your_age, ages, modified_agi, inflation_factor
            )
            total += premium + oop
        elif on_marketplace and cfg.ACA_ENABLED:
            # calculate_aca_premium quotes a whole-household premium, so charge
            # the per-adult share for whoever is still pre-Medicare.
            household_aca = cfg.calculate_aca_premium(modified_agi) * inflation_factor
            total += household_aca * (on_marketplace / n_adults)

        return total

    def quote_marketplace_cost(self, your_age: int, adult_ages, modified_agi: float,
                               inflation_factor: float = 1.0) -> Tuple[float, float]:
        """
        Age-rated marketplace (premium, out-of-pocket) for this year, in the
        caller's healthcare-factor dollars. Side-effect-free; used by
        quote_health_insurance_cost when cfg.MODEL_ACA_AGE_RATED is on.

        Members = pre-Medicare adults among ``adult_ages`` + children at home
        (cfg.children_at_home_ages). FPL household = all ``adult_ages`` (a
        Medicare spouse stays in the tax household) + children at home. The
        living base's SPEND_HEALTH line is netted against out-of-pocket for the
        members' share of the household so it is not counted twice.
        """
        if not cfg.ACA_ENABLED:
            return 0.0, 0.0
        kids = cfg.children_at_home_ages(your_age)
        members = [a for a in adult_ages if a < cfg.MEDICARE_AGE] + kids
        if not members:
            return 0.0, 0.0
        household = len(adult_ages) + len(kids)
        premium = cfg.calculate_aca_premium_age_rated(
            modified_agi, members, household
        ) * inflation_factor
        oop = cfg.aca_oop_annual(len(members), len(members) / household, inflation_factor)
        return premium, oop

    def calculate_health_insurance_cost(self, your_age: int, modified_agi: float,
                                         inflation_factor: float = 1.0) -> float:
        """
        Calculate health insurance cost (ACA or Medicare with IRMAA) and record
        it into the running premium totals.

        For Medicare (age 65+), uses IRMAA brackets based on MAGI from 2 years prior.
        Higher income = higher Medicare premiums.
        """
        premium = self.quote_health_insurance_cost(your_age, modified_agi, inflation_factor)
        if premium > 0:
            if your_age >= cfg.MEDICARE_AGE:
                self.total_medicare_premiums += premium
            else:
                self.total_aca_premiums += premium
        return premium

    def withdraw_529_for_college(self, your_age: int, inflation_factor: float = 1.0) -> float:
        """
        Withdraw from each child's 529 for that child's college bill this year
        (tax-free), up to the 529's balance.

        Returns:
            Amount withdrawn from 529 accounts to cover college expenses
        """
        college_expenses = cfg.calculate_college_expenses(your_age)
        total_withdrawn = 0
        for child, expense in college_expenses.items():
            account = self.accounts.get(f"{child}_529") if child != "total" else None
            if expense > 0 and account is not None:
                withdraw_amount = min(expense * inflation_factor, account.balance)
                account.balance -= withdraw_amount
                total_withdrawn += withdraw_amount
        return total_withdrawn

    # ------------------------------------------------------------------
    # Lifecycle big-purchase helpers (car purchase, housing timeline)
    # ------------------------------------------------------------------
    def owns_home(self) -> bool:
        """Whether the household owns its home now (else it rents). The rule of
        ``cfg.is_renter``: a home value or a mortgage payment means owning."""
        return self.home_value > 0 or self.mortgage_annual > 0

    def has_mortgage_for_age(self, your_age: int) -> bool:
        """
        Whether a mortgage payment is still owed at ``your_age``.

        Without a housing timeline this defers to config (``cfg.has_mortgage``)
        so behavior is byte-identical to before. With one, it reads the engine's
        mortgage state, which apply_housing_events() may have switched to a new
        loan (new payoff age) or ended by a sale.
        """
        if not _housing_timeline_on():
            return cfg.has_mortgage(your_age)
        return your_age < self.mortgage_payoff_age

    def mortgage_expense_for_age(self, your_age: int) -> float:
        """
        Annual housing loan outflow owed at ``your_age`` (0 once paid off).

        Without a housing timeline this uses config (byte-identical). With one
        it uses engine state, so the payment amount and payoff timing reflect
        every purchase and sale so far.

        When extra principal is configured, two things change -- and both are
        required for a prepayment sweep to be meaningful:

          * the TRACKED BALANCE becomes authoritative for "is there still a
            loan?". Both fallbacks above decide that from a config SCHEDULE (an
            age), which cannot know the balance was retired early -- so without
            this the engine would keep billing a paid-off mortgage and
            prepayment would look like pure cost with no benefit.
          * the extra principal is added to the outflow, so it costs real cash.

        Gated on ``extra_mortgage_payment_enabled()`` so the default path is
        untouched.
        """
        extra_on = (hasattr(cfg, "extra_mortgage_payment_enabled")
                    and cfg.extra_mortgage_payment_enabled())
        timeline = _housing_timeline_on()

        if extra_on and getattr(cfg, "TRACK_HOME_EQUITY_PAYDOWN", False):
            if self.mortgage_balance <= 0:
                return 0.0
            scheduled = (self.mortgage_annual if timeline
                         else float(cfg.MORTGAGE_ANNUAL))
            # Never bill more principal than the loan can absorb this year. The
            # cap must account for the scheduled payments too, not just the
            # opening balance -- in the payoff year the schedule alone may
            # retire the loan, and billing the full extra on top would spend
            # cash against principal that is already gone.
            _, extra = self._amortize_year_capped(
                cfg.extra_mortgage_payment_for_age(your_age))
            return scheduled + extra

        if not timeline:
            return cfg.MORTGAGE_ANNUAL if cfg.has_mortgage(your_age) else 0.0
        return self.mortgage_annual if your_age < self.mortgage_payoff_age else 0.0

    def housing_expense_for_age(self, your_age: int) -> float:
        """
        Housing outflow at ``your_age``: rent while renting; for an owner the
        mortgage outflow while one is owed, else property tax + insurance on the
        home currently held (``self.home_value``). Engine twin of
        ``cfg.housing_annual``. The all-in payment already includes escrow, so
        the carrying cost is only added once no payment is owed.
        """
        if not self.owns_home():
            return self.rent_monthly * 12.0
        mortgage = self.mortgage_expense_for_age(your_age)
        if mortgage > 0:
            return mortgage
        return mortgage + cfg.home_carrying_cost_annual(self.home_value)

    def pay_lump_sum(self, amount: float, your_age: float) -> Tuple[float, float]:
        """
        Fund a one-time cash outflow (e.g. a car purchase) from the portfolio in
        the standard tax-efficient order, grossing up for any taxes/penalties.

        Returns (gross_withdrawn, taxes_and_penalties_paid). A no-op for amount<=0.
        """
        if amount <= 0:
            return 0.0, 0.0
        return self.withdraw_tax_efficient(amount, is_medical=False, your_age=your_age)

    def apply_housing_events(self, your_age: int) -> bool:
        """
        Apply the housing timeline's events at ``your_age`` (cfg.housing_events:
        HOME_EVENTS plus the legacy single house move), each once. Returns True
        if any fired. Runs before the year's expenses so that year already pays
        the new housing cost.

        Each event:
          1. sells the home if one is owned (_sell_home): net proceeds = value -
             remaining principal - selling costs - tax on the gain above the
             exclusion, into cash;
          2. then either buys (_buy_home): down payment (price - loan) + costs
             from the portfolio, and the new loan, value and accessible equity
             replace the old; or starts renting (_start_renting): costs from the
             portfolio, no home, the new rent from now on.
        """
        if not _housing_timeline_on():
            return False
        if self._home_events is None:
            self._home_events = cfg.housing_events()
        fired = False
        for i, event in enumerate(self._home_events):
            if event["age"] != your_age or i in self._home_events_done:
                continue
            self._home_events_done.add(i)
            if self.owns_home():
                self._sell_home(your_age, event["selling_cost_pct"])
            if event["action"] == cfg.HOME_SELL_RENT:
                self._start_renting(your_age, event)
            else:
                self._buy_home(your_age, event)
            fired = True
        if fired:
            self.house_moved = True
        return fired

    # The single-move name, kept for callers and tests that predate the timeline.
    maybe_execute_house_move = apply_housing_events

    def _sell_home(self, your_age: int, selling_cost_pct: float) -> None:
        """Sell the home held now; net proceeds land in cash."""
        # Prefer the TRACKED loan balance: it is anchored to the balance the user
        # entered and amortized forward, whereas the fallback estimator has to
        # reconstruct principal from the payment — and that payment is all-in (it
        # bundles property tax + insurance), which overstates the outstanding
        # principal and so understated sale proceeds (~$61k on the packaged
        # profile). Fall back to the estimator when paydown tracking is off.
        if getattr(cfg, "TRACK_HOME_EQUITY_PAYDOWN", False):
            remaining_principal = max(0.0, self.mortgage_balance)
        else:
            months_remaining = max(0, (self.mortgage_payoff_age - your_age) * 12)
            remaining_principal = cfg.estimate_remaining_mortgage_principal(
                self.mortgage_monthly, months_remaining
            )
        selling_costs = self.home_value * selling_cost_pct
        net_proceeds = max(0.0, self.home_value - remaining_principal - selling_costs)
        # Main-home gain above the exclusion ($250k per owner, $500k joint) is a
        # long-term capital gain. Paid from the proceeds, any rest from savings.
        basis = self.home_value if self.home_cost_basis is None else self.home_cost_basis
        taxable_gain = self.home_value - selling_costs - basis - cfg.home_sale_exclusion()
        tax = self._tax_home_sale_gain(taxable_gain) if taxable_gain > 0 else 0.0
        self._deposit_cash(net_proceeds - min(tax, net_proceeds))
        if tax > net_proceeds:
            self.pay_lump_sum(tax - net_proceeds, your_age)

    def _tax_home_sale_gain(self, gain: float) -> float:
        """Tax on the taxable part of a home-sale gain, stacked on this year's
        income: the same pieces as a taxable-account sale in _withdraw_single_pass
        (federal LTCG by filing status, state as ordinary income less any state
        capital-gains exclusion, NIIT), on the owner's return. Unmarried
        co-owners (two returns) each report half."""
        if gain <= 0:
            return 0.0
        shares = [("you", gain / 2.0), ("partner", gain / 2.0)] if self.two_returns else [("you", gain)]
        total = 0.0
        for ret, part in shares:
            status = self.return_status[ret]
            prior = self._return_investment(ret)
            fed_taxable_ordinary = max(0, self._return_income(ret) + prior
                                       - self.get_standard_deduction("partner" if ret == "partner" else "you"))
            federal = calculate_ltcg_tax(part, fed_taxable_ordinary, status=status)
            state_model = self._state_model(ret)
            state_part = part * (1.0 - float(
                getattr(state_model, "rules", {}).get("ltcg_exclusion", 0.0) or 0.0))
            deduction = getattr(state_model, "deduction", cfg.CA_STANDARD_DEDUCTION_MFJ_2024)
            base = self._state_taxable_base(ret) + prior
            state = (state_model.calculate_tax(max(0, base + state_part - deduction))
                     - state_model.calculate_tax(max(0, base - deduction)))
            self.year_investment_income += part
            if ret == "partner":
                self.year_partner_investment += part
            niit = cfg.calculate_niit(
                self._return_income(ret) + self._return_investment(ret), part,
                years_from_start=max(0, (self.current_your_age or cfg.YOUR_AGE) - cfg.YOUR_AGE),
                status=status,
            )
            self.total_niit_paid += niit
            total += federal + state + niit
        self.total_taxes_paid += total
        return total

    def _buy_home(self, your_age: int, event: dict) -> None:
        """Buy ``event``'s home: down payment + costs from the portfolio (after
        any sale proceeds landed, so cash is used first), then switch the loan,
        value and accessible-equity reserve to it."""
        down_payment = max(0.0, event["price"] - event["loan"])
        self.pay_lump_sum(down_payment + event["costs"], your_age)
        self.home_value = float(event["price"])
        self.home_cost_basis = self.home_value
        self.mortgage_monthly = float(event["monthly"])
        self.mortgage_annual = float(event["monthly"]) * 12.0
        self.mortgage_payoff_age = your_age + event["years"]
        self.home_equity = down_payment * cfg.HOME_EQUITY_ACCESSIBLE_PCT
        self.rent_monthly = 0.0
        # Re-anchor the amortization schedule on the NEW loan so equity starts
        # rebuilding from the down payment at this age.
        self.mortgage_balance = float(event["loan"])
        self._mortgage_rate = event["rate"]          # the new loan's own rate
        self._mortgage_pi = _level_payment(
            self.mortgage_balance, self._mortgage_rate, event["years"],
        )

    def _start_renting(self, your_age: int, event: dict) -> None:
        """Rent from now on: moving costs from the portfolio, no home or loan."""
        self.pay_lump_sum(event["costs"], your_age)
        self.home_value = self.home_cost_basis = 0.0
        self.mortgage_monthly = self.mortgage_annual = 0.0
        self.mortgage_payoff_age = your_age
        self.mortgage_balance = self._mortgage_pi = 0.0
        self.home_equity = 0.0
        self.rent_monthly = float(event["rent"])

    def _deposit_cash(self, amount: float) -> None:
        """Deposit a lump sum of liquid cash into the portfolio (into 'your_cash'
        if present, else the first CASH account, else create one)."""
        if amount <= 0:
            return
        if 'your_cash' in self.accounts:
            self.accounts['your_cash'].balance += amount
            return
        for account in self.accounts.values():
            if account.account_type == AccountType.CASH:
                account.balance += amount
                return
        self.add_account(Account("house_sale_cash", AccountType.CASH, amount, "you"))

    def _deposit_taxable(self, amount: float) -> None:
        """Reinvest a lump sum into a taxable brokerage account (into
        'your_brokerage' if present, else the first TAXABLE account, else create
        one). Uses ``contribute`` so cost basis is tracked (the reinvested
        after-tax dollars are the basis; only future growth is taxable)."""
        if amount <= 0:
            return
        if 'your_brokerage' in self.accounts:
            self.contribute('your_brokerage', amount)
            return
        for name, account in self.accounts.items():
            if account.account_type == AccountType.TAXABLE:
                self.contribute(name, amount)
                return
        self.add_account(Account("reinvest_brokerage", AccountType.TAXABLE, 0.0, "you"))
        self.contribute("reinvest_brokerage", amount)


def create_initial_portfolio() -> AccountPortfolio:
    """Create portfolio with current account balances."""
    portfolio = AccountPortfolio()
    portfolio.add_account(Account("your_401k", AccountType.TRADITIONAL_401K, cfg.YOUR_401K, "you"))
    portfolio.add_account(Account("your_roth_ira", AccountType.ROTH_IRA, cfg.YOUR_ROTH_IRA, "you"))
    portfolio.add_account(Account("your_trad_ira", AccountType.TRADITIONAL_IRA, cfg.YOUR_TRADITIONAL_IRA, "you"))
    portfolio.add_account(Account("your_hsa", AccountType.HSA, cfg.YOUR_HSA, "you"))
    portfolio.add_account(Account("your_brokerage", AccountType.TAXABLE, cfg.YOUR_BROKERAGE, "you"))
    portfolio.add_account(Account("your_cash", AccountType.CASH, cfg.YOUR_CASH, "you"))
    # A single household has no partner accounts, so stray partner balances
    # (an old profile, a preset's sample numbers) can't count as savings.
    if cfg.has_partner():
        portfolio.add_account(Account("partner_401k", AccountType.TRADITIONAL_401K, cfg.PARTNER_401K, "partner"))
        portfolio.add_account(Account("partner_roth_ira", AccountType.ROTH_IRA, cfg.PARTNER_ROTH_IRA, "partner"))
        portfolio.add_account(Account("partner_brokerage", AccountType.TAXABLE, cfg.PARTNER_BROKERAGE, "partner"))
        portfolio.add_account(Account("partner_cash", AccountType.CASH, cfg.PARTNER_CASH, "partner"))
    # One 529 per child (starts at $0, funded from birth when college funding is on)
    for i in range(1, len(cfg.CHILDREN) + 1):
        portfolio.add_account(Account(f"child{i}_529", AccountType.COLLEGE_529, 0, f"child{i}"))
    return portfolio


def _contribute_529s(portfolio: AccountPortfolio, amounts) -> None:
    """Deposit this year's 529 saving into each child's own account."""
    for i, amount in enumerate(amounts, 1):
        if amount > 0:
            portfolio.contribute(f"child{i}_529", amount)


def _your_comp_for_age(your_age: int) -> Dict[str, Optional[float]]:
    """The primary's comp-table row for ``your_age``: base, wages (total_comp),
    the Manual-mode ``saved`` figure and the optional explicit ``after_tax``.

    Ages not in the table are projected from the LAST row (not a hard-coded
    age) by YOUR_SALARY_GROWTH_RATE, so custom tables of any age range work.
    All zero when the table is empty.
    """
    table = cfg.YOUR_COMPENSATION_BY_AGE
    if not table:
        return {"base": 0.0, "wages": 0.0, "saved": 0.0, "after_tax": None}
    if your_age in table:
        row, growth = table[your_age], 1.0
    else:
        last_age = max(table.keys())
        row = table[last_age]
        growth = (1 + cfg.YOUR_SALARY_GROWTH_RATE) ** (your_age - last_age)
    base = float(row.get("base", 0.0) or 0.0)
    wages = row.get("total_comp")
    if wages is None:
        wages = base + float(row.get("bonus", 0.0) or 0.0) + float(row.get("rsu_gross", 0.0) or 0.0)
    after_tax = row.get("after_tax")
    return {"base": base * growth, "wages": float(wages) * growth,
            "saved": float(row.get("saved", 0.0) or 0.0) * growth,
            "after_tax": None if after_tax is None else float(after_tax) * growth}


def working_year_cashflow(your_age: int, partner_working: bool = True,
                          you_working: bool = True) -> Dict[str, Any]:
    """One working year's pay, pre-tax savings, taxes and take-home.

    Deterministic (no portfolio, no random draws), so the engine and the UI's
    per-year charts read the same numbers: simulate_accumulation_year and a
    partner who keeps working after you retire (_simulate_partner_working_year)
    use it for their cash flow; utils.sim_runner uses it for the tax and
    savings charts.

    * Your wages = the comp-table row's total_comp (base + bonus + RSU); your
      other income = YOUR_OTHER_INCOME (no FICA, while you work).
    * Partner wages = PARTNER_SALARY + PARTNER_BONUS_AMOUNT + PARTNER_RSU_AMOUNT,
      grown at PARTNER_SALARY_GROWTH_RATE; plus PARTNER_OTHER_INCOME.
    * 401(k)/HSA deferrals are capped at the IRS limits and at the pay itself.
      Each employer match is dollar for dollar on the deferral, up to the match
      % of base pay -- contributing less than the match % earns less match.
    * Taxes: cfg.working_year_taxes (federal by filing status, the state's
      table, FICA per earner; two returns for an unmarried couple).
    * The partner's direct Roth is limited by the Roth income phase-out of the
      return it's on (and by earned income), not by being married.
    * A comp row that sets ``after_tax`` overrides your computed take-home
      (older profiles); the tax totals reported for that year are scaled to it.

    Pass ``you_working=False`` for a year you're retired but your partner still
    works, ``partner_working=False`` for a year they've stopped.
    """
    years_from_start = your_age - cfg.YOUR_AGE
    current_year = cfg.CURRENT_YEAR + years_from_start
    partner_age = your_age - (cfg.YOUR_AGE - cfg.PARTNER_AGE)

    # ----- You -----------------------------------------------------------
    comp = (_your_comp_for_age(your_age) if you_working
            else {"base": 0.0, "wages": 0.0, "saved": 0.0, "after_tax": None})
    base_salary = comp["base"]
    your_wages = comp["wages"]
    your_other = float(getattr(cfg, "YOUR_OTHER_INCOME", 0.0) or 0.0) if you_working else 0.0
    your_401k = your_match = your_after_tax_401k = your_hsa = your_roth = 0.0
    if you_working:
        limit_401k = cfg.get_401k_limit(your_age, current_year)
        desired = float(getattr(cfg, "YOUR_401K_CONTRIBUTION", limit_401k))
        your_401k = max(0.0, min(desired, limit_401k, your_wages))
        your_match = min(your_401k, base_salary * cfg.YOUR_401K_MATCH_PCT)
        # Mega backdoor Roth: after-tax 401(k) up to the 415(c) total-additions
        # room left after the deferral and the match (see simulate_accumulation_year).
        after_tax_pct = float(getattr(cfg, "YOUR_AFTER_TAX_401K_PCT", 0.0) or 0.0)
        if after_tax_pct > 0:
            room = max(0.0, cfg.get_401k_total_limit(your_age, current_year)
                       - your_401k - your_match)
            your_after_tax_401k = min(after_tax_pct * base_salary, room)
        hsa_limit = cfg.get_hsa_limit(your_age, current_year, is_family=True)
        desired = float(getattr(cfg, "YOUR_HSA_CONTRIBUTION", hsa_limit))
        your_hsa = max(0.0, min(desired, hsa_limit, your_wages - your_401k))
        ira_limit = cfg.get_ira_limit(your_age, current_year)
        your_roth = max(0.0, min(float(getattr(cfg, "YOUR_BACKDOOR_ROTH", ira_limit)), ira_limit))

    # ----- Partner -------------------------------------------------------
    partner_base = partner_wages = partner_other = 0.0
    partner_401k = partner_match = 0.0
    if partner_working:
        growth = (1 + cfg.PARTNER_SALARY_GROWTH_RATE) ** years_from_start
        partner_base = float(cfg.PARTNER_SALARY) * growth
        partner_wages = (float(cfg.PARTNER_SALARY)
                         + float(getattr(cfg, "PARTNER_BONUS_AMOUNT", 0.0) or 0.0)
                         + float(getattr(cfg, "PARTNER_RSU_AMOUNT", 0.0) or 0.0)) * growth
        partner_other = float(getattr(cfg, "PARTNER_OTHER_INCOME", 0.0) or 0.0)
        limit_401k = cfg.get_401k_limit(partner_age, current_year)
        desired = float(getattr(cfg, "PARTNER_401K_CONTRIBUTION", limit_401k))
        partner_401k = max(0.0, min(desired, limit_401k, partner_wages))
        partner_match = min(partner_401k, partner_base
                            * float(getattr(cfg, "PARTNER_401K_MATCH_PCT", 0.0) or 0.0))

    taxes = cfg.working_year_taxes(
        your_wages, partner_wages,
        your_other=your_other, partner_other=partner_other,
        your_401k=your_401k, partner_401k=partner_401k, your_hsa=your_hsa,
        your_age=your_age, partner_age=partner_age, years_from_start=years_from_start,
    )
    two = taxes["two_returns"]

    partner_roth = 0.0
    if partner_working:
        ira_limit = cfg.get_ira_limit(partner_age, current_year)
        desired = max(0.0, min(float(getattr(cfg, "PARTNER_ROTH_CONTRIBUTION", ira_limit)), ira_limit))
        joint = (not two) and cfg.normalize_filing_status() == cfg._FILING_MFJ
        magi = taxes["partner"]["agi"] + (0.0 if two else taxes["you"]["agi"])
        # An IRA contribution needs earned income (a spouse's counts on a joint return).
        earned = partner_wages + (max(0.0, your_wages - your_roth) if joint else 0.0)
        partner_roth = min(cfg.roth_ira_allowed(desired, magi, cfg.return_status("partner")),
                           earned)

    your_take_home = taxes["you"]["take_home"]
    federal, state, fica = taxes["federal"], taxes["state"], taxes["fica"]
    if comp["after_tax"] is not None:
        # Explicit take-home override: report the tax it implies, split like
        # the rule-based tax.
        your_take_home = comp["after_tax"]
        implied = max(0.0, taxes["you"]["gross"] - taxes["you"]["deferrals"] - your_take_home)
        rule = taxes["you"]["total"]
        if rule > 0:
            k = implied / rule
            federal += taxes["you"]["federal"] * (k - 1)
            state += taxes["you"]["state"] * (k - 1)
            fica += taxes["you"]["fica"] * (k - 1)
        else:
            federal += implied

    return {
        "years_from_start": years_from_start, "current_year": current_year,
        "partner_age": partner_age, "two_returns": two,
        "base_salary": base_salary, "your_wages": your_wages, "your_other": your_other,
        "saved": comp["saved"],
        "your_401k": your_401k, "your_match": your_match,
        "your_after_tax_401k": your_after_tax_401k, "your_hsa": your_hsa,
        "your_roth": your_roth,
        "partner_base": partner_base, "partner_wages": partner_wages,
        "partner_other": partner_other, "partner_401k": partner_401k,
        "partner_match": partner_match, "partner_roth": partner_roth,
        "your_agi": taxes["you"]["agi"], "partner_agi": taxes["partner"]["agi"],
        "your_take_home": your_take_home,
        "partner_take_home": taxes["partner"]["take_home"],
        "federal": federal, "state": state, "fica": fica,
        "total_tax": federal + state + fica,
        "gross_income": your_wages + your_other + partner_wages + partner_other,
        "taxes": taxes,
    }


def _simulate_partner_working_year(
    portfolio: AccountPortfolio, your_age: int, current_year: int,
    years_from_start: int, married: bool,
) -> Tuple[float, float, float]:
    """Run the partner's WORKING-year cash flow in a year YOU are retired (the
    separate-partner-retirement-age feature): make their pre-tax 401(k) +
    employer match and direct Roth contributions, and return their take-home.

    Uses working_year_cashflow(you_working=False), so their pay is taxed by the
    same rules as in your working years. Returns ``(after_tax, taxable_income,
    roth_contribution)``: ``taxable_income`` is the partner's AGI (pay minus
    pre-tax 401(k), plus other income) and ``roth_contribution`` the after-tax
    elective already funded here. ``married`` is ignored (the Roth limit now
    follows income); it stays in the signature for existing callers.
    """
    cf = working_year_cashflow(your_age, partner_working=True, you_working=False)
    portfolio.contribute("partner_401k", cf["partner_401k"] + cf["partner_match"])
    if cf["partner_roth"] > 0:
        portfolio.contribute("partner_roth_ira", cf["partner_roth"])
    return cf["partner_take_home"], cf["partner_agi"], cf["partner_roth"]


def simulate_accumulation_year(portfolio: AccountPortfolio, your_age: int, annual_return: float,
                               partner_working: bool = True) -> bool:
    """Simulate one year of accumulation (working phase).

    ``partner_working`` is True by default (the household-wide behavior that
    predates the separate-partner-retirement-age feature). When False, the
    partner has already retired while the primary keeps working: their salary
    and contributions stop, and if the household's remaining take-home no longer
    covers the year's spending the shortfall is drawn from the portfolio.

    Returns True while solvent, False if a partner-retired-early drawdown
    depletes the portfolio. The default path always returns True.
    """
    portfolio.apply_returns(annual_return)
    # Start a fresh tax year. Without this, ``year_ordinary_income`` (and the
    # tracked ages used for the age-65 standard-deduction add-on) were only ever
    # reset inside simulate_retirement_year, so any working-year portfolio draw
    # (car purchase, house down payment) was taxed off a stale base that RATCHETED
    # upward across accumulation years -- the tax on a purchase depended on how
    # many purchases preceded it.
    portfolio.reset_yearly_income()
    portfolio.update_ages(your_age)

    # Coast FIRE: past the coast age the household keeps working just enough to
    # cover expenses, so NO new contributions are made — but nothing is withdrawn
    # either. The portfolio simply compounds untouched until real retirement.
    # Returns were already applied above, so an early return here is exactly
    # "growth, no contributions, no drawdown".
    if (getattr(cfg, "COAST_FIRE_ENABLED", False)
            and your_age >= getattr(cfg, "COAST_FIRE_AGE", 999)):
        portfolio.coasting = True
        return True

    # This year's pay, pre-tax savings, taxes and take-home for both earners:
    # one deterministic function shared with the UI (working_year_cashflow).
    cf = working_year_cashflow(your_age, partner_working=partner_working)
    base_salary = cf["base_salary"]
    saved_after_tax = cf["saved"]

    # Your 401(k) deferral (capped at the IRS limit and your pay) plus the
    # employer match, which only matches what you actually defer.
    your_401k_contribution = cf["your_401k"]
    your_401k_match = cf["your_match"]
    portfolio.contribute("your_401k", your_401k_contribution + your_401k_match)

    # Mega backdoor Roth: after-tax 401(k) contributions up to the 415(c) total-
    # additions limit (after the employee deferral + employer match), converted
    # in-plan to Roth (routed to the Roth bucket for tax-free growth). Funded from
    # take-home (added to after-tax electives below), so it reallocates savings
    # from the taxable brokerage sweep into Roth. 0% -> no-op / byte-identical.
    your_after_tax_401k = cf["your_after_tax_401k"]
    if your_after_tax_401k > 0:
        portfolio.contribute("your_roth_ira", your_after_tax_401k)

    your_hsa_contribution = cf["your_hsa"]
    portfolio.contribute("your_hsa", your_hsa_contribution)

    your_roth_contribution = cf["your_roth"]

    # 529 contributions, one per child (elective; funded from after-tax
    # take-home below).
    child_529s = cfg.child_529_contributions(your_age)
    contribution_529 = sum(child_529s)

    # ------------------------------------------------------------------
    # Partner pre-tax + Roth contributions (computed here so the household
    # residual sweep below can net partner's after-tax income and electives).
    # When the partner has already retired (partner_working=False), they earn
    # and contribute nothing this year -- their salary and contributions drop to
    # zero and the residual sweep naturally routes everything to the primary.
    # ------------------------------------------------------------------
    if partner_working:
        portfolio.contribute("partner_401k", cf["partner_401k"] + cf["partner_match"])
        if cf["partner_roth"] > 0:
            portfolio.contribute("partner_roth_ira", cf["partner_roth"])
    partner_after_tax = cf["partner_take_home"]
    partner_roth_contribution = cf["partner_roth"]

    # ------------------------------------------------------------------
    # Recognize this year's income into the tax year, so any portfolio draw
    # later in this function (house-move down payment, car purchase) is taxed at
    # the household's real MARGINAL rate instead of from a $0 income base. The
    # wages' own tax is already netted out of take-home (working_year_cashflow);
    # this is only the stacking base. An unmarried couple's partner part sits on
    # the partner's own return.
    # ------------------------------------------------------------------
    portfolio.year_ordinary_income = max(0.0, cf["your_agi"] + cf["partner_agi"])
    if portfolio.two_returns:
        portfolio.year_partner_income = max(0.0, cf["partner_agi"])

    # ------------------------------------------------------------------
    # Housing timeline (accumulation phase). Executed BEFORE computing living
    # expenses so that a working-year purchase, move or sale already pays the
    # NEW housing cost this year. No timeline -> no-op. (Sale proceeds land in
    # cash before the down payment + car are drawn.)
    # ------------------------------------------------------------------
    portfolio.apply_housing_events(your_age)

    # ------------------------------------------------------------------
    # Household take-home for the year: pay minus pre-tax deferrals minus
    # federal + state + FICA (or a comp row's explicit after_tax).
    # ------------------------------------------------------------------
    your_after_tax = cf["your_take_home"]
    household_after_tax = your_after_tax + partner_after_tax

    # Living expenses for the WORKING year via the existing helper. The
    # accumulation loop runs in the all-real frame (inflation factor 1.0). This
    # already includes mortgage (has_mortgage), the granular household base
    # (SPEND_* incl. PARTNER_OTHER_MONTHLY), and child costs.
    living = cfg.calculate_annual_expenses(your_age, 1.0, childcare_factor=1.0)
    # With a housing timeline the config housing term (today's home for the
    # whole plan) no longer reflects reality; swap in the engine's using the
    # SAME delta as calculate_retirement_expenses. Guarded so the no-timeline
    # path is byte-identical. Housing, not just mortgage, so rent stops once you
    # buy and the post-payoff carrying cost follows the engine's home.
    if _mortgage_swap_active(portfolio):
        living += _housing_swap_delta(portfolio, your_age)

    # College while still working: each child's 529 pays this year's bill and
    # the budget covers what it can't (as in retirement, where the bill is an
    # expense and the 529 draw an offset). Without this, college during the
    # working years was never paid and the 529 sat untouched for good.
    college_bill = cfg.calculate_college_expenses(your_age)["total"]
    if college_bill > 0:
        living += college_bill - portfolio.withdraw_529_for_college(your_age)

    # Record working-year spending too (deterministic, so no cross-scenario
    # spread — it anchors the spending-range chart before retirement). Living
    # expenses already include housing/children/base, so living == total here.
    portfolio.spending_log.append({
        "age": int(your_age), "living": float(living), "total": float(living),
    })

    # After-tax electives funded from take-home (401k employee, HSA, and the
    # employer match are pre-tax / employer money already EXCLUDED from
    # after_tax, so they are NOT subtracted here). The mega-backdoor after-tax
    # 401(k) IS after-tax money, so it belongs here — it reduces the brokerage
    # sweep dollar-for-dollar (reallocating that saving into Roth).
    your_after_tax_electives = your_roth_contribution + contribution_529 + your_after_tax_401k
    partner_after_tax_electives = partner_roth_contribution
    after_tax_electives = your_after_tax_electives + partner_after_tax_electives

    # Residual = un-spent after-tax income available to invest in brokerage.
    # ``raw_residual`` keeps the sign so a partner-retired-early shortfall (below)
    # can be detected; the sweep itself still floors at 0 exactly as before.
    raw_residual = household_after_tax - living - after_tax_electives
    residual = max(0.0, raw_residual)

    savings_mode = str(getattr(cfg, "SAVINGS_MODE", "Auto"))
    # Amount by which a user-set brokerage FLOOR exceeds this year's real
    # surplus. Funded from the portfolio at the end of the year (see below);
    # 0 in the overwhelmingly common case that income covers the floor.
    _floor_excess_to_fund = 0.0
    your_brokerage_override = getattr(cfg, "YOUR_BROKERAGE_CONTRIBUTION", None)
    partner_brokerage_override = (getattr(cfg, "PARTNER_BROKERAGE_CONTRIBUTION", None)
                                  if cfg.has_partner() else None)

    if savings_mode.startswith("Auto"):
        # AUTO: sweep the full residual into taxable brokerage. The flat
        # per-person overrides act as a FLOOR (never invest less than the user
        # explicitly configured).
        your_floor = float(your_brokerage_override) if your_brokerage_override else 0.0
        partner_floor = (
            float(partner_brokerage_override) if partner_brokerage_override else 0.0
        )
        total_brokerage = max(residual, your_floor + partner_floor)
        # Any part of the floor not covered by income has to come from
        # somewhere real -- tracked here, withdrawn at the end of the year.
        _floor_excess_to_fund = max(0.0, total_brokerage - residual)

        # Attribution: the couple SPLITS HOUSEHOLD EXPENSES EVENLY, so each person
        # first covers HALF of living from their own after-tax income, then banks
        # their OWN remainder in their OWN brokerage. Because the higher earner has
        # more left after their equal half, the residual is NOT split 50/50 -- it
        # lands mostly (or entirely) in the higher earner's account. If one
        # person's income can't cover their half, the other effectively funds the
        # shortfall, so their whole remainder is theirs. The two shares always sum
        # to total_brokerage (dollar-conserving); this is purely account
        # attribution (both are taxable brokerage, so results are unchanged).
        half_living = 0.5 * living
        your_capacity = max(0.0, your_after_tax - your_after_tax_electives)
        partner_capacity = max(0.0, partner_after_tax - partner_after_tax_electives)
        # Per-person share of expenses. Default: split all living evenly. If
        # PRIMARY_PAYS_HOUSING, the primary covers the full mortgage/housing and
        # only the rest is split evenly.
        if bool(getattr(cfg, "PRIMARY_PAYS_HOUSING", False)):
            if _mortgage_swap_active(portfolio):
                mortgage_year = portfolio.housing_expense_for_age(your_age)
            else:
                mortgage_year = cfg.owner_housing_annual(your_age)
            rest = max(0.0, living - mortgage_year)
            your_expense = mortgage_year + 0.5 * rest
            partner_expense = 0.5 * rest
        else:
            your_expense = partner_expense = half_living
        your_after_half = your_capacity - your_expense
        partner_after_half = partner_capacity - partner_expense
        pos_total = max(0.0, your_after_half) + max(0.0, partner_after_half)
        if pos_total > 0:
            your_share = max(0.0, your_after_half) / pos_total
        else:
            your_share = 1.0  # neither covers their half from income -> route to primary
        to_brokerage = total_brokerage * your_share
        to_brokerage_partner = total_brokerage - to_brokerage

        if residual <= 0.0:
            # Spend + electives exceeded income this year; flag it for the UI.
            # (total_brokerage may still be > 0 if a user-set floor applies.)
            portfolio.overspent_years += 1

        portfolio.contribute("your_roth_ira", your_roth_contribution)  # Backdoor Roth
        _contribute_529s(portfolio, child_529s)
        portfolio.contribute("your_brokerage", max(0.0, to_brokerage))
        portfolio.contribute("partner_brokerage", max(0.0, to_brokerage_partner))
    else:
        # MANUAL: preserve the legacy flat-override behavior EXACTLY (no sweep).
        if your_brokerage_override is not None and float(your_brokerage_override) > 0:
            to_brokerage = float(your_brokerage_override)
        else:
            # Subtract the mega-backdoor after-tax 401(k) too — it's funded from
            # the same take-home pool, so leaving it out would double-fund it
            # (phantom dollars: contributed to Roth AND left in brokerage).
            to_brokerage = saved_after_tax - your_roth_contribution - contribution_529 - your_after_tax_401k
        to_brokerage = max(0.0, to_brokerage)

        # Disposable-income sanity clamp: an over-configured profile (e.g. huge
        # 401k + HSA + backdoor Roth) must not fund more than the year's gross
        # salary. Shrink the discretionary tail (brokerage first, then the
        # backdoor Roth) so total elective contributions never exceed income.
        elective_total = (
            your_401k_contribution
            + your_hsa_contribution
            + your_roth_contribution
            + your_after_tax_401k
            + contribution_529
            + to_brokerage
        )
        overshoot = elective_total - base_salary
        if overshoot > 0:
            trim = min(to_brokerage, overshoot)
            to_brokerage -= trim
            overshoot -= trim
            if overshoot > 0:
                your_roth_contribution = max(0.0, your_roth_contribution - overshoot)

        portfolio.contribute("your_roth_ira", your_roth_contribution)  # Backdoor Roth
        _contribute_529s(portfolio, child_529s)
        portfolio.contribute("your_brokerage", to_brokerage)

        if partner_brokerage_override is not None and float(partner_brokerage_override) > 0:
            to_brokerage_partner = float(partner_brokerage_override)
        else:
            to_brokerage_partner = (
                partner_after_tax - partner_roth_contribution - cfg.PARTNER_ANNUAL_SPENDING
            )
        portfolio.contribute("partner_brokerage", max(0, to_brokerage_partner))

    # ------------------------------------------------------------------
    # ESPP discount benefit (CONSERVATION #18c). YOUR_ESPP_PCT and
    # YOUR_ESPP_DISCOUNT were previously read by no engine function (dead inputs).
    # An ESPP lets the employee buy company stock at a discount; the discount is
    # employer-subsidized value (extra compensation) on the shares purchased.
    # Model it simply as an additional after-tax deposit into taxable brokerage:
    #   espp_benefit = base_salary * YOUR_ESPP_PCT * YOUR_ESPP_DISCOUNT
    # This is additive to net worth (employer money on top of normal savings) and
    # is $0 whenever either knob is 0 (the default), so feature-OFF is a no-op.
    espp_pct = float(getattr(cfg, "YOUR_ESPP_PCT", 0.0) or 0.0)
    espp_discount = float(getattr(cfg, "YOUR_ESPP_DISCOUNT", 0.0) or 0.0)
    espp_benefit = base_salary * espp_pct * espp_discount
    if espp_benefit > 0:
        portfolio.contribute("your_brokerage", espp_benefit)

    # ------------------------------------------------------------------
    # Lifecycle big purchases (accumulation phase). Car purchase(s): a one-time
    # cash outlay funded from the portfolio. Kept as a SEPARATE portfolio
    # outflow -- NOT a living expense, NOT part of the residual. (The house move
    # already fired above.) Default OFF -> no-op.
    # ------------------------------------------------------------------
    car_cost = cfg.calculate_car_purchase(your_age)
    if car_cost > 0:
        portfolio.pay_lump_sum(car_cost, your_age)

    # ------------------------------------------------------------------
    # Partner-retired-early shortfall (separate-partner-retirement-age feature).
    # If the partner has stopped working while the primary keeps working and the
    # household's take-home no longer covers the year's spending, draw the
    # shortfall from the portfolio tax-efficiently ("cover bills, draw the rest").
    #
    # A spending deficit must be FUNDED, not discarded. This previously ran only
    # when `not partner_working`, so in the normal case (anyone still working) a
    # negative ``raw_residual`` was merely floored at zero above and the shortfall
    # vanished — the household spent money that was never funded, inflating both
    # the ending balance and the reported success rate (a probe showed a $170k/yr
    # shortfall disappear with the portfolio untouched).
    # Compare NET delivered (gross withdrawn minus taxes/penalties) against the
    # shortfall: the tax on a withdrawal does not buy groceries.
    # ------------------------------------------------------------------
    if raw_residual < 0:
        shortfall = -raw_residual
        withdrawn, cost = portfolio.withdraw_tax_efficient(
            shortfall, is_medical=False, your_age=your_age
        )
        net_delivered = withdrawn - cost
        if net_delivered < shortfall * WITHDRAWAL_SHORTFALL_TOLERANCE:
            return False

    # A brokerage-contribution FLOOR above the year's actual surplus must also be
    # funded from the portfolio. Previously the AUTO branch did
    # ``total_brokerage = max(residual, floors)`` and then contribute()d that
    # amount with no offsetting withdrawal -- so any floor exceeding income
    # CREATED money out of nothing. Distinct from the deficit case above (which
    # only covers raw_residual < 0): here the residual can be comfortably
    # POSITIVE and still short of the floor. Measured on a real profile, a floor
    # about 9% above the year's surplus inflated success by ~7pp.
    #
    # Funding it (rather than clamping the floor) is the faithful reading of "I
    # will invest at least $X": in reality you would sell something, and the tax
    # on that sale is exactly why over-configuring a floor is a bad idea.
    #
    # KNOWN LIMITATION (second-order, and only for a MISCONFIGURED floor): this
    # withdrawal runs AFTER the contribution, so it can draw on the just-added
    # taxable basis and therefore realises no gain. A real household selling to
    # fund the gap would tap PRE-EXISTING assets and owe tax. Dollar conservation
    # is correct either way -- only the tax drag of an over-set floor is
    # understated -- so this is left rather than reordering the well-tested
    # deficit path above.
    if _floor_excess_to_fund > 0:
        withdrawn, cost = portfolio.withdraw_tax_efficient(
            _floor_excess_to_fund, is_medical=False, your_age=your_age
        )
        net_delivered = withdrawn - cost
        if net_delivered < _floor_excess_to_fund * WITHDRAWAL_SHORTFALL_TOLERANCE:
            return False
    return True


def _housing_timeline_on() -> bool:
    """Is there a housing timeline (HOME_EVENTS or the legacy house move)? Then
    the engine's own home state, not config, decides housing costs."""
    return bool(getattr(cfg, "HOUSE_MOVE_ENABLED", False)) or bool(getattr(cfg, "HOME_EVENTS", None))


def _mortgage_swap_active(portfolio) -> bool:
    """Whether the ENGINE's housing figure should replace the config one.

    True with a housing timeline (purchases, moves and sales change what the
    household pays) and ALSO whenever extra principal is configured --
    otherwise the extra payment never reaches the expense total on the
    no-timeline path, and the tracked early payoff would be invisible to the
    expense side.
    """
    if portfolio is None:
        return False
    if _housing_timeline_on():
        return True
    return (hasattr(cfg, "extra_mortgage_payment_enabled")
            and cfg.extra_mortgage_payment_enabled()
            and getattr(cfg, "TRACK_HOME_EQUITY_PAYDOWN", False))


def _housing_swap_delta(portfolio, your_age: int) -> float:
    """Engine-minus-config housing at ``your_age`` (today's dollars).

    0 unless ``_mortgage_swap_active``; otherwise the amount that replaces the
    config housing term (``cfg.housing_annual``: today's mortgage, rent or
    carrying cost) with the engine's (timeline- and extra-principal-aware)
    figure. Rent is part of both, so a renter who buys stops paying it.
    """
    if portfolio is None or not _mortgage_swap_active(portfolio):
        return 0.0
    return portfolio.housing_expense_for_age(your_age) - cfg.housing_annual(your_age)


def _retirement_housing_expense(
    current_age: int, general_factor: float = 1.0, portfolio=None
) -> float:
    """Housing dollars inside ``calculate_retirement_expenses`` for this year.

    Built from the SAME pieces that put housing into that total: the config term
    (``cfg.housing_annual``: mortgage / rent / post-payoff carrying cost), the
    engine swap (``_housing_swap_delta``) and the general inflation factor. The
    later-years spending reduction leaves housing alone.
    """
    return (cfg.housing_annual(current_age)
            + _housing_swap_delta(portfolio, current_age)) * general_factor


def calculate_retirement_expenses(
    current_age: int,
    inflation_factors: Dict[str, float],
    retirement_age: Optional[int] = None,
    portfolio: Optional["AccountPortfolio"] = None,
) -> float:
    """
    Calculate retirement expenses with all adjustments.

    This helper function consolidates expense calculation logic to prevent
    duplication and bugs from inconsistent updates.

    NOTE: Healthcare insurance premiums (ACA/Medicare) are calculated separately
    in simulate_retirement_year() via calculate_health_insurance_cost().
    This function only includes base living expenses, NOT insurance premiums.

    Args:
        current_age: Person's current age
        inflation_factors: Dict with inflation factors by category
        retirement_age: Age retirement began. Places the go-go years, the
            later-years reduction and the lifecycle preset's retirement-relative
            ages, and the optional vacation add-on. None = the plain age rules.
        portfolio: Portfolio whose engine housing state replaces the config
            housing term once a housing timeline exists (purchases, moves,
            sales). None / no timeline keeps the exact prior behavior.

    Returns:
        Total annual retirement expenses (adjusted for age, leisure, college)
        Does NOT include health insurance premiums (added separately)
    """
    base_expenses = cfg.calculate_annual_expenses(
        current_age,
        inflation_factors['general'],
        childcare_factor=inflation_factors['childcare'],
        retirement=True,
        retirement_age=retirement_age,
    )

    # Housing timeline: replace the config housing term with the engine's.
    # Only when a portfolio is supplied and the swap is active, so the default
    # path is byte-identical.
    if portfolio is not None and _mortgage_swap_active(portfolio):
        base_expenses += _housing_swap_delta(portfolio, current_age) * inflation_factors['general']

    # NOTE: Healthcare insurance premiums are added separately in simulate_retirement_year()
    # via portfolio.calculate_health_insurance_cost() which calculates ACA or Medicare premiums.
    # We do NOT add HEALTHCARE_INCREASE_PRE_MEDICARE here to avoid double-counting.

    # Go-go years: extra travel/hobby spending from retirement until
    # retirement_leisure_end_age (70, or 5 years after a late retirement).
    if (current_age < cfg.retirement_leisure_end_age(retirement_age)
            and (retirement_age is None or current_age >= retirement_age)):
        base_expenses += cfg.retirement_leisure_increase() * inflation_factors['general']

    # Later years (75, or 10 years after a late retirement): living spending
    # drops. Housing is held out -- the payment or rent doesn't shrink -- and
    # mirrored in _retirement_housing_expense.
    if current_age >= cfg.late_retirement_start_age(retirement_age):
        housing = _retirement_housing_expense(current_age, inflation_factors['general'], portfolio)
        base_expenses = housing + (base_expenses - housing) * (1 - cfg.LATE_RETIREMENT_LEISURE_DECREASE)

    # Add college expenses (from COLLEGE_START_AGE, for each child)
    college_costs = cfg.calculate_college_expenses(current_age)
    base_expenses += college_costs['total'] * inflation_factors['general']

    # Retirement "go-go years" vacation spending (optional; OFF by default).
    # Grows with the general inflation factor like other base liabilities.
    if retirement_age is not None:
        base_expenses += (
            cfg.calculate_retirement_vacation(current_age, retirement_age)
            * inflation_factors['general']
        )

    return base_expenses


def _apply_spending_guardrails(
    portfolio: AccountPortfolio, expenses: float, annual_return: float,
    your_age: Optional[int] = None, inflation_factor: float = 1.0,
) -> float:
    """
    Apply the dynamic spending adjustments (portfolio-based guardrails and
    return-based adjustment) to the discretionary portion of expenses.

    With MODEL_GUARDRAILS_EXCLUDE_HOUSING (and ``your_age`` supplied) this year's
    housing -- ``_retirement_housing_expense``, the same term inside ``expenses``
    -- is always fixed, and DISCRETIONARY_EXPENSE_RATIO applies only to the
    non-housing remainder.

    Returns the adjusted total expenses (fixed + adjusted discretionary).
    """
    # ==========================================================================
    # DYNAMIC SPENDING ADJUSTMENTS
    # ==========================================================================
    # Split expenses into fixed and discretionary components
    discretionary_ratio = cfg.DISCRETIONARY_EXPENSE_RATIO
    housing = 0.0
    if your_age is not None and getattr(cfg, "MODEL_GUARDRAILS_EXCLUDE_HOUSING", False):
        # Capped at ``expenses`` so a direct caller's synthetic total can't go
        # negative on the non-housing side.
        housing = min(expenses, max(0.0, _retirement_housing_expense(
            your_age, inflation_factor, portfolio)))
    if housing > 0:
        discretionary_expenses = (expenses - housing) * discretionary_ratio
        fixed_expenses = expenses - discretionary_expenses
    else:
        fixed_expenses = expenses * (1 - discretionary_ratio)
        discretionary_expenses = expenses * discretionary_ratio

    # 1. Portfolio-based guardrails (apply to discretionary portion)
    portfolio_adjustment = cfg.calculate_spending_adjustment(
        portfolio.get_total_balance(),
        portfolio.target_portfolio_inflation_adjusted
    )

    # 2. Return-based adjustment (apply to discretionary portion)
    # This adjusts spending based on THIS YEAR's market returns
    return_adjustment = cfg.calculate_return_based_spending_adjustment(annual_return)

    # Combine adjustments (multiplicative) - only affects discretionary
    # Example: 0.95 (portfolio down) * 0.80 (bad returns) = 0.76 total on discretionary
    combined_discretionary_adjustment = portfolio_adjustment * return_adjustment

    # Clamp combined adjustment to the configured bounds (default 60% to 140%
    # of discretionary).
    combined_discretionary_adjustment = max(
        getattr(cfg, "GUARDRAIL_MIN_DISCRETIONARY_FACTOR", 0.60),
        min(getattr(cfg, "GUARDRAIL_MAX_DISCRETIONARY_FACTOR", 1.40),
            combined_discretionary_adjustment),
    )

    # Apply adjustment to discretionary expenses only
    adjusted_discretionary = discretionary_expenses * combined_discretionary_adjustment
    adjusted_expenses = fixed_expenses + adjusted_discretionary
    return adjusted_expenses


def _collect_sepp(
    portfolio: AccountPortfolio, your_age: int
) -> Tuple[float, float]:
    """Take this year's 72(t) SEPP distribution from traditional accounts.

    Structurally the same as an RMD — a fixed, mandatory-once-started draw taxed
    as ordinary income — but PENALTY-FREE before 59.5, which is the whole point
    of the strategy. The annual amount is locked in at the start age from the
    then-current traditional balance and does not float with the market.

    Returns (sepp_total, sepp_tax); (0, 0) when the strategy is off or the
    schedule has run its course.
    """
    if not getattr(cfg, "SEPP_72T_ENABLED", False):
        return 0.0, 0.0
    start_age = getattr(cfg, "SEPP_72T_START_AGE", None)
    if start_age is None or your_age < start_age:
        return 0.0, 0.0
    # Once age 59.5 is reached AND the 5-year minimum is served, the schedule is
    # over; ordinary penalty-free access takes over from here.
    if not cfg.sepp_72t_must_continue(your_age, start_age):
        return 0.0, 0.0

    trad = [a for a in portfolio.accounts.values()
            if a.account_type in (AccountType.TRADITIONAL_401K,
                                  AccountType.TRADITIONAL_IRA)]
    total_trad = sum(a.balance for a in trad)

    # Lock the annual payment on the first year of the schedule, amortizing only
    # the DESIGNATED balance. Splitting a sub-account off for the 72(t) is the
    # standard way to right-size it: the rest of the traditional money stays
    # outside the schedule (no 5-year lock-in, still convertible to Roth).
    if portfolio.sepp_annual_amount is None:
        carveout = float(getattr(cfg, "SEPP_72T_CARVEOUT", 0.0) or 0.0)
        basis = min(carveout, total_trad) if carveout > 0 else total_trad
        portfolio.sepp_annual_amount = cfg.sepp_72t_annual_amount(basis, your_age)
        portfolio.sepp_start_age = start_age
        # Notional ledger for the designated account: it grows with the market
        # (see apply_returns) and is drawn down by each payment. When it runs dry
        # the schedule ends — a 72(t) may terminate without penalty once the
        # designated account is exhausted, and crucially the payments can never
        # reach into the traditional money that was left outside it.
        portfolio.sepp_carveout_balance = basis if carveout > 0 else None

    target = float(portfolio.sepp_annual_amount or 0.0)
    if target <= 0:
        return 0.0, 0.0

    # Draw pro-rata across traditional accounts, capped by what's left — and, when
    # a carve-out was designated, by what remains in it.
    available = total_trad
    if portfolio.sepp_carveout_balance is not None:
        if portfolio.sepp_carveout_balance <= 0:
            return 0.0, 0.0          # designated account exhausted -> schedule over
        available = min(available, portfolio.sepp_carveout_balance)
    take = min(target, available)
    if take <= 0:
        return 0.0, 0.0
    drawn = 0.0
    drawn_by_owner: Dict[str, float] = {}
    for account in trad:
        if drawn >= take or account.balance <= 0:
            continue
        share = take * (account.balance / total_trad) if total_trad > 0 else 0.0
        amount = min(share, account.balance, take - drawn)
        account.balance -= amount
        drawn += amount
        drawn_by_owner[account.owner] = drawn_by_owner.get(account.owner, 0.0) + amount
    if portfolio.sepp_carveout_balance is not None:
        portfolio.sepp_carveout_balance = max(0.0, portfolio.sepp_carveout_balance - drawn)
    # Taxed per owner (their own return / retirement-income exclusion); on one
    # return the stacked total equals the tax on the sum.
    tax = sum(portfolio.calculate_marginal_tax_on_income(amount, owner=owner, retirement=True)
              for owner, amount in drawn_by_owner.items())
    if tax > 0:
        portfolio.total_taxes_paid += tax
    portfolio.total_sepp_distributions += drawn
    return drawn, tax


def _collect_rmds(
    portfolio: AccountPortfolio, your_age: int, partner_age: int
) -> Tuple[float, float]:
    """
    Take required minimum distributions from traditional accounts and compute the
    income tax on them. Drains balances and rolls RMD tax into total_taxes_paid.

    Returns (rmd_total, rmd_tax).
    """
    # RMDs - must be taken and are taxable as ordinary income
    # Each person's RMDs start when THEY reach their RMD_START_AGE (based on birth year)
    rmd_total = 0
    rmd_tax = 0
    for account in portfolio.accounts.values():
        if account.account_type in [AccountType.TRADITIONAL_401K, AccountType.TRADITIONAL_IRA]:
            # Determine owner's age and birth year for RMD calculation
            if account.owner == "partner":
                owner_age = partner_age
                owner_birth_year = cfg.PARTNER_BIRTH_YEAR
            else:
                owner_age = your_age
                owner_birth_year = cfg.YOUR_BIRTH_YEAR

            # Calculate RMD start age based on owner's birth year
            rmd_start_age = cfg.get_rmd_start_age(owner_birth_year)

            # Only take RMD if owner has reached their RMD age
            if owner_age >= rmd_start_age:
                rmd_amount = cfg.calculate_rmd(account.balance, owner_age, rmd_start_age)
                if rmd_amount > 0:
                    actual_rmd = min(rmd_amount, account.balance)
                    account.balance -= actual_rmd
                    rmd_total += actual_rmd
                    rmd_tax += portfolio.calculate_marginal_tax_on_income(
                        actual_rmd, owner=account.owner, retirement=True)
    if rmd_tax > 0:
        portfolio.total_taxes_paid += rmd_tax
    return rmd_total, rmd_tax


def _collect_social_security(
    portfolio: AccountPortfolio, your_age: int, inflation_factor: float
) -> Tuple[float, float]:
    """
    Compute Social Security income (COLA-indexed) and a PROVISIONAL income tax on
    its taxable portion, purely to size this year's net-expense withdrawals.

    CONSERVATION (#18a): the taxable portion of SS is driven by the year's
    provisional income (IRS formula: other AGI + 50% of SS). At this point in the
    year only RMD income has been recognized -- the expense withdrawals and Roth
    conversion (which realize LTCG / traditional-account / conversion income) have
    NOT run yet, so ``year_ordinary_income`` understates the true provisional
    income and would under-tax SS. Consistent with the #3 MAGI-timing philosophy
    and the health-premium two-pass approach, this is only a PROVISIONAL quote:
    it is side-effect-free (does not touch running tax totals, does not mutate
    ``year_ordinary_income``). The real SS tax is recomputed and booked AFTER
    withdrawals + Roth conversion in ``_true_up_social_security_tax``.

    Returns (ss_income, provisional_ss_tax).
    """
    # Social Security income (inflation-adjusted since SS has COLA)
    ss_income = 0
    ss_tax = 0
    if cfg.INCLUDE_SOCIAL_SECURITY:
        ss_income = cfg.calculate_social_security(your_age, cfg.SS_CLAIM_AGE) * inflation_factor

        # Calculate taxable portion of Social Security (up to 85% taxable).
        if ss_income > 0:
            # Use income recognized so far (RMDs) as a lower-bound "other AGI".
            # Provisional (non-booking) tax quote to size withdrawals; the
            # state's Social Security rule applies (most states exempt it).
            for owner, ss_part in _social_security_by_return(portfolio, ss_income):
                taxable_ss = cfg.calculate_taxable_social_security(
                    ss_part, portfolio._return_income(owner),
                    years_from_start=max(0, your_age - cfg.YOUR_AGE),
                    status=portfolio.return_status[owner],
                )
                if taxable_ss > 0:
                    ss_tax += portfolio.quote_marginal_tax_on_income(
                        taxable_ss, is_state_taxable=False, owner=owner)
    return ss_income, ss_tax


def _social_security_by_return(portfolio: AccountPortfolio, ss_income: float):
    """[(owner, benefits)] per tax return: the whole household benefit on one
    return, or each person's own benefit on an unmarried couple's two.

    The split weights each person's full-retirement-age benefit among those old
    enough to be claiming (an approximation: it ignores different early/late
    claiming adjustments between the two)."""
    if not portfolio.two_returns or ss_income <= 0:
        return [("you", ss_income)]
    your_claim = cfg.SS_CLAIM_AGE
    partner_claim = getattr(cfg, "PARTNER_SS_CLAIM_AGE", None) or your_claim
    w_you = cfg.YOUR_SS_MONTHLY_FRA if (portfolio.current_your_age or 0) >= your_claim else 0.0
    w_partner = (cfg.PARTNER_SS_MONTHLY_FRA
                 if (portfolio.current_partner_age or 0) >= partner_claim else 0.0)
    total = float(w_you) + float(w_partner)
    if total <= 0:
        return [("you", ss_income)]
    return [("you", ss_income * w_you / total), ("partner", ss_income * w_partner / total)]


def _true_up_social_security_tax(
    portfolio: AccountPortfolio, ss_income: float, provisional_ss_tax: float
) -> float:
    """
    Recompute the taxable portion of Social Security from the year's FULLY
    realized ordinary income (after expense withdrawals + Roth conversion) and
    book the real SS tax into the running totals (CONSERVATION #18a).

    ``other_agi`` for the IRS provisional-income formula is all recognized
    ordinary income EXCLUDING the taxable SS itself, which is exactly the current
    ``year_ordinary_income`` (SS tax was quoted, not recognized, in
    ``_collect_social_security``). The final taxable SS is then recognized into
    ``year_ordinary_income`` and its tax booked once.

    Returns the FINAL (booked) SS tax so the caller can net it against SS income.
    """
    if not cfg.INCLUDE_SOCIAL_SECURITY or ss_income <= 0:
        return 0.0

    ss_tax = 0.0
    for owner, ss_part in _social_security_by_return(portfolio, ss_income):
        taxable_ss = cfg.calculate_taxable_social_security(
            ss_part, portfolio._return_income(owner),
            years_from_start=max(0, (portfolio.current_your_age or cfg.YOUR_AGE) - cfg.YOUR_AGE),
            status=portfolio.return_status[owner],
        )
        if taxable_ss > 0:
            ss_tax += portfolio.calculate_marginal_tax_on_income(
                taxable_ss, is_state_taxable=False, owner=owner)
    if ss_tax <= 0:
        return 0.0

    portfolio.total_ss_taxes_paid += ss_tax
    portfolio.total_taxes_paid += ss_tax
    return ss_tax


def _assemble_health_ltc_car_expenses(
    portfolio: AccountPortfolio, your_age: int, adjusted_expenses: float,
    healthcare_factor: float
) -> Tuple[float, float, float]:
    """
    Quote the PROVISIONAL health-insurance premium (Pass 1), model long-term care
    for ages 85+, and compute the one-time car outlay for this year.

    Returns (health_insurance, ltc_cost, car_cost).
    """
    # ------------------------------------------------------------------
    # Health insurance (ACA subsidy before 65, Medicare + IRMAA after) is
    # MAGI-driven, but the premium is itself an expense that drives the
    # withdrawals which realize the LTCG and Roth-conversion income that make
    # up MAGI. That circularity is resolved with a two-pass estimate:
    #
    #   Pass 1 (here): quote a PROVISIONAL premium from the income known so far
    #                  (RMDs + taxable SS) plus the historical expenses*0.5
    #                  proxy, purely to size this year's withdrawals. This uses
    #                  the side-effect-free quote (does not touch premium totals).
    #   Pass 2 (below, after withdrawals + Roth conversion): recompute the
    #                  premium from ACTUAL MAGI = year_ordinary_income +
    #                  year_investment_income (realized gains + conversion
    #                  income), record it, and fund any shortfall vs the
    #                  provisional premium with a supplemental withdrawal.
    # ------------------------------------------------------------------
    provisional_agi = portfolio.year_ordinary_income + (adjusted_expenses * 0.5)
    health_insurance = portfolio.quote_health_insurance_cost(
        your_age, provisional_agi, healthcare_factor
    )

    # Long-term care (LTC) modeling for ages 85+
    ltc_cost = 0.0
    if cfg.LTC_ENABLED and your_age >= cfg.LTC_START_AGE:
        # Determine if LTC is needed this year (cached for consistency across calculations)
        if your_age not in portfolio.ltc_needs_by_age:
            # First time at this age - do a stochastic draw
            import random
            portfolio.ltc_needs_by_age[your_age] = random.random() < cfg.LTC_PROBABILITY

        needs_ltc = portfolio.ltc_needs_by_age[your_age]
        ltc_cost = cfg.calculate_ltc_cost(your_age, healthcare_factor, needs_ltc)
        portfolio.total_ltc_costs += ltc_cost

    # Lifecycle car purchase (retirement phase): a one-time cash outlay folded
    # into this year's expenses so it flows through the normal withdrawal +
    # solvency machinery. OFF by default -> calculate_car_purchase returns 0.
    car_cost = cfg.calculate_car_purchase(your_age)
    return health_insurance, ltc_cost, car_cost


def _fund_net_expenses(
    portfolio: AccountPortfolio, your_age: int, adjusted_expenses: float,
    health_insurance: float, ltc_cost: float, car_cost: float,
    ss_income: float, ss_tax: float, rmd_total: float, rmd_tax: float,
    college_529_withdrawn: float, healthcare_factor: float,
    partner_income: float = 0.0, partner_magi: float = 0.0,
    sepp_total: float = 0.0, sepp_tax: float = 0.0,
) -> Tuple[bool, float]:
    """
    Fund this year's net expenses via tax-efficient withdrawals, run the Roth
    conversion, true-up the health-insurance premium from actual MAGI (Pass 2),
    and apply the solvency check.

    ``partner_income`` is the after-tax take-home of a partner who is STILL
    WORKING while the primary is retired (separate-partner-retirement-age
    feature); it offsets the withdrawal need just like Social Security / RMD
    proceeds, and any surplus is banked into taxable brokerage by the existing
    surplus path below. ``partner_magi`` is that partner's earned income; it is
    already part of year_ordinary_income (seeded by simulate_retirement_year),
    so the Pass-2 ACA/IRMAA MAGI includes it. Both default to 0.0 -> byte-identical when the partner isn't
    working (the household-wide behavior that predates the feature).

    Returns (solvent, rmd_total, reinvested_surplus). ``solvent`` is False when
    withdrawals cannot cover the shortfall-tolerance fraction of net expenses.
    ``rmd_total`` is
    returned unchanged for the caller's downstream log flush.
    """
    total_expenses = adjusted_expenses + health_insurance + ltc_cost + car_cost

    # Calculate net expenses after SS income (minus SS tax), RMD after-tax proceeds, and 529 withdrawals
    ss_after_tax = ss_income - ss_tax
    rmd_after_tax = rmd_total - rmd_tax
    # 72(t) SEPP proceeds are after-tax cash in hand, so they reduce what has to
    # be withdrawn this year exactly like SS or RMD proceeds do.
    sepp_after_tax = max(0.0, sepp_total - sepp_tax)
    covering_income = (ss_after_tax + rmd_after_tax + sepp_after_tax
                       + college_529_withdrawn + partner_income)
    net_expenses = total_expenses - covering_income

    # CONSERVATION (#4): when after-tax SS + RMD proceeds + 529 withdrawals exceed
    # this year's spending, the excess cash is NOT destroyed. RMDs are mandatory
    # withdrawals that drained real traditional balances; proceeds not needed for
    # spending are, in reality, reinvested into a taxable brokerage account. Deposit
    # the positive surplus back into the portfolio instead of clamping it away.
    reinvested_surplus = 0.0
    if net_expenses < 0:
        reinvested_surplus = -net_expenses
        portfolio._deposit_taxable(reinvested_surplus)
        net_expenses = 0.0

    # Split expenses into medical and other (for HSA withdrawal optimization)
    medical_portion = MEDICAL_EXPENSE_PORTION_PRE_MEDICARE if your_age < cfg.MEDICARE_AGE else MEDICAL_EXPENSE_PORTION_POST_MEDICARE
    medical_expenses = net_expenses * medical_portion
    other_expenses = net_expenses - medical_expenses

    # Withdraw with early withdrawal penalty awareness
    withdrawn_medical, tax_medical = portfolio.withdraw_tax_efficient(
        medical_expenses, is_medical=True, your_age=your_age
    )
    withdrawn_other, tax_other = portfolio.withdraw_tax_efficient(
        other_expenses, is_medical=False, your_age=your_age
    )

    # Roth conversion (fill up lower brackets before SS kicks in)
    # IMPORTANT: must run AFTER expense withdrawals so year_ordinary_income reflects
    # all income recognized this year, preventing accidental bracket overflow
    roth_conversion, roth_tax = portfolio.perform_roth_conversion(your_age)

    # CONSERVATION (#3): perform_roth_conversion books the conversion income tax
    # into the running totals but the converted principal moved intact from
    # traditional to Roth, so the tax itself must come from somewhere. The standard
    # modeling assumption is that Roth-conversion tax is paid from OUTSIDE funds
    # (taxable/cash), not by shrinking the conversion. Fund it with a real
    # withdrawal so total portfolio dollars actually decrease by the tax paid.
    if roth_tax > 0:
        portfolio.withdraw_tax_efficient(roth_tax, is_medical=False, your_age=your_age)

    total_withdrawn = withdrawn_medical + withdrawn_other
    # NET cash actually delivered to spending: taxes and penalties on a withdrawal
    # do not pay for groceries. The solvency test below compares this (not the
    # gross) against the need — otherwise a year is declared solvent after the
    # portfolio is emptied while expenses go underfunded by the whole tax bill.
    net_delivered = (withdrawn_medical - tax_medical) + (withdrawn_other - tax_other)

    # ------------------------------------------------------------------
    # SS tax true-up (CONSERVATION #18a): _collect_social_security only QUOTED a
    # provisional SS tax from RMD-only income. Now that expense withdrawals + the
    # Roth conversion have recognized the rest of the year's ordinary income,
    # recompute the taxable-SS portion from the full provisional income and book
    # the real SS tax. The taxable-SS portion is now recognized into
    # year_ordinary_income (so the health-premium true-up below sees it too). The
    # provisional SS tax was already netted into covering_income when sizing the
    # withdrawals, so only the ADDITIONAL tax vs the provisional quote is an
    # unfunded shortfall -- fund that delta with a real withdrawal.
    # ------------------------------------------------------------------
    real_ss_tax = _true_up_social_security_tax(portfolio, ss_income, ss_tax)
    ss_tax_shortfall = real_ss_tax - ss_tax
    if ss_tax_shortfall > 0:
        extra_ss_withdrawn, _ = portfolio.withdraw_tax_efficient(
            ss_tax_shortfall, is_medical=False, your_age=your_age
        )
        withdrawn_other += extra_ss_withdrawn
        total_withdrawn += extra_ss_withdrawn
        net_delivered += extra_ss_withdrawn
        net_expenses += ss_tax_shortfall

    # ------------------------------------------------------------------
    # Pass 2: true-up health insurance from ACTUAL MAGI.
    # Withdrawals above realized LTCG (year_investment_income) and the Roth
    # conversion added ordinary income (year_ordinary_income). Recompute the
    # premium from real MAGI = ordinary + investment income and record it. If
    # the true premium exceeds the provisional one that sized the withdrawals,
    # fund the delta with a supplemental withdrawal so the year stays solvent.
    # ------------------------------------------------------------------
    # A working partner's pay is already in year_ordinary_income (seeded at the
    # start of simulate_retirement_year), so partner_magi is not added again.
    actual_magi = portfolio.year_ordinary_income + portfolio.year_investment_income
    true_health_insurance = portfolio.quote_health_insurance_cost(
        your_age, actual_magi, healthcare_factor
    )
    # Record the TRUE premium into the running totals (once).
    if true_health_insurance > 0:
        if your_age >= cfg.MEDICARE_AGE:
            portfolio.total_medicare_premiums += true_health_insurance
        else:
            portfolio.total_aca_premiums += true_health_insurance

    premium_shortfall = true_health_insurance - health_insurance
    if premium_shortfall > 0:
        # The extra premium was not covered by the Pass-1 withdrawals. Fund it
        # now (non-medical: a health-insurance premium is not a qualified HSA
        # medical expense).
        extra_withdrawn, _extra_tax = portfolio.withdraw_tax_efficient(
            premium_shortfall, is_medical=False, your_age=your_age
        )
        withdrawn_other += extra_withdrawn
        total_withdrawn += extra_withdrawn
        net_delivered += extra_withdrawn
        net_expenses += premium_shortfall

    # Solvency is judged on NET cash delivered, not gross withdrawn: taxes and
    # penalties reduce what is available to spend. Using the gross figure reported
    # depletion a year late and could turn a final-year depletion into a counted
    # success.
    if net_delivered < net_expenses * WITHDRAWAL_SHORTFALL_TOLERANCE:
        return False, rmd_total, reinvested_surplus

    return True, rmd_total, reinvested_surplus


def _flush_withdrawal_log(
    portfolio: AccountPortfolio, your_age: int, rmd_total: float,
    pre_withdrawal_total: float, taxes_start: float, niit_start: float,
    ss_tax_start: float, penalties_start: float,
    roth_conversion_start: float = 0.0, roth_conversion_tax_start: float = 0.0,
    reinvested_surplus: float = 0.0,
) -> None:
    """
    Append this retirement year's consolidated withdrawal + tax-attribution row
    to portfolio.withdrawal_log, using the pre-withdrawal snapshot as denominator
    and the start-of-year running-total snapshots for per-year tax deltas.
    """
    # --- Per-year withdrawal tracking: flush the accumulator into the log ---
    # RMDs drain traditional balances and are the functional equivalent of a
    # mandatory withdrawal, so they count toward the year's withdrawals — BUT any
    # RMD/SS/529 proceeds beyond this year's spending were reinvested into taxable
    # (they never left the portfolio to be spent). Subtract that reinvested
    # surplus so `total`/`withdrawal_pct` reflect money actually consumed, not the
    # forced-out-then-put-back RMD overflow (which otherwise inflated the rate).
    net_rmd_out = max(0.0, float(rmd_total) - float(reinvested_surplus))
    wk = portfolio._current_year_withdrawals
    total_wd = (
        wk.get('cash', 0.0) + wk.get('taxable', 0.0) + wk.get('traditional', 0.0)
        + wk.get('roth', 0.0) + wk.get('hsa', 0.0) + net_rmd_out
    )
    denom = max(1.0, pre_withdrawal_total)
    # Per-year tax attribution (ADDITIVE / backward compatible): end-of-year minus
    # start-of-year deltas of the cumulative running totals. `total_taxes_paid`
    # rolls in penalties (withdraw_tax_efficient adds taxes+penalties), so subtract
    # the penalty delta to report pure taxes. Components that are readily separable
    # (SS tax, NIIT, early-withdrawal penalties) are logged alongside the total.
    year_penalties = portfolio.total_early_withdrawal_penalties - penalties_start
    year_ss_tax = portfolio.total_ss_taxes_paid - ss_tax_start
    year_niit = portfolio.total_niit_paid - niit_start
    year_total_taxes = (portfolio.total_taxes_paid - taxes_start) - year_penalties
    # finding #14 — Roth-conversion delta for THIS year (traditional -> Roth
    # transfer, not a withdrawal/spend). Reported as its own field so chart
    # code can render it as a distinct, clearly-labeled transfer band rather
    # than folding it silently into `total_taxes` (only the conversion tax
    # previously showed up there) or `traditional`/`roth` withdrawals (neither
    # of which the conversion touches — see perform_roth_conversion, which
    # moves balances directly and never goes through withdraw_tax_efficient).
    year_roth_conversion = portfolio.total_roth_conversions - roth_conversion_start
    year_roth_conversion_tax = portfolio.roth_conversion_taxes - roth_conversion_tax_start
    portfolio.withdrawal_log.append({
        'age': int(your_age),
        'cash': float(wk.get('cash', 0.0)),
        'taxable': float(wk.get('taxable', 0.0)),
        # RMDs drain traditional balances — fold the net (post-reinvestment) RMD
        # outflow into the traditional bucket so total == sum of buckets.
        'traditional': float(wk.get('traditional', 0.0) + net_rmd_out),
        'roth': float(wk.get('roth', 0.0)),
        'hsa': float(wk.get('hsa', 0.0)),
        'total': float(total_wd),
        'portfolio_value': float(pre_withdrawal_total),
        'withdrawal_pct': float(total_wd / denom),
        # --- RMD attribution (ADDITIVE — does not change any total above) ---
        # `traditional` above is forced RMDs + chosen draws combined, so the UI
        # previously could not show how much of a year's draw was MANDATORY.
        # These split it without altering `traditional`/`total`/`withdrawal_pct`:
        #   rmd_gross         the full IRS-forced withdrawal for the year
        #   rmd_spent         the part that funded spending (== the amount folded
        #                     into `traditional`; the remainder was reinvested)
        #   traditional_chosen  discretionary traditional draws only
        # Invariant: traditional == traditional_chosen + rmd_spent.
        'rmd_gross': float(max(0.0, float(rmd_total))),
        'rmd_spent': float(net_rmd_out),
        'traditional_chosen': float(wk.get('traditional', 0.0)),
        # Real per-year taxes paid this retirement year (see comment above).
        'total_taxes': float(max(0.0, year_total_taxes)),
        'ss_tax': float(max(0.0, year_ss_tax)),
        'niit': float(max(0.0, year_niit)),
        'penalties': float(max(0.0, year_penalties)),
        # Transfer, NOT spending/withdrawal — deliberately excluded from `total`.
        'roth_conversion': float(max(0.0, year_roth_conversion)),
        'roth_conversion_tax': float(max(0.0, year_roth_conversion_tax)),
    })


def simulate_retirement_year(
    portfolio: AccountPortfolio,
    your_age: int,
    expenses: float,
    annual_return: float,
    inflation_factor: float = 1.0,
    retirement_age: int = 50,
    healthcare_factor: float = None,
    partner_income: float = 0.0,
    partner_magi: float = 0.0,
    partner_working: bool = False,
) -> bool:
    """
    Simulate one year of retirement with realistic tax modeling.

    Includes:
    - RMD calculations and taxation
    - Social Security with proper taxation (up to 85% taxable)
    - Roth conversion strategy
    - Health insurance (ACA/Medicare with IRMAA)
    - Early withdrawal penalties before 59.5
    - NIIT on investment income
    - Standard deduction applied to federal taxes
    - Dynamic spending adjustment (guardrails)
    - Return-based discretionary spending adjustment

    ALL-REAL frame: ``inflation_factor`` is the GENERAL factor (constant 1.0 in the
    all-real convention) and applies to real-flat liabilities -- Social Security
    (COLA-indexed, so real-flat is correct), the guardrail target, and 529/college.
    ``healthcare_factor`` is the healthcare-category factor (grows at the real-excess
    rate) and applies to the categories that outpace general CPI: ACA/Medicare
    premiums and long-term care. If not supplied it defaults to ``inflation_factor``
    so direct callers/tests keep their prior single-factor behavior.
    """
    if healthcare_factor is None:
        healthcare_factor = inflation_factor
    portfolio.reset_yearly_income()
    # A partner still working while you're retired: their pay is this year's
    # first income on the return, so withdrawals, Roth conversions and the
    # Social Security formula all stack on top of it (their own tax was netted
    # out of partner_income by working_year_cashflow).
    if partner_magi > 0:
        portfolio.year_ordinary_income = float(partner_magi)
        if portfolio.two_returns:
            portfolio.year_partner_income = float(partner_magi)
    portfolio.update_ages(your_age)
    portfolio.employer_health_coverage = partner_working and getattr(
        cfg, "PARTNER_EMPLOYER_HEALTH_COVERAGE", False)
    portfolio.update_target_portfolio(inflation_factor)

    # Snapshot cumulative tax/penalty running totals so the per-year deltas can be
    # logged into withdrawal_log below. The engine accumulates all taxes into these
    # running totals (RMD tax, SS tax, LTCG/NIIT via withdraw_tax_efficient, Roth
    # conversion tax, penalties); taking the end-of-year minus start-of-year delta
    # captures the taxes actually attributable to THIS retirement year regardless of
    # which code path recorded them.
    _taxes_start = portfolio.total_taxes_paid
    _niit_start = portfolio.total_niit_paid
    _ss_tax_start = portfolio.total_ss_taxes_paid
    _penalties_start = portfolio.total_early_withdrawal_penalties
    _roth_conversion_start = portfolio.total_roth_conversions
    _roth_conversion_tax_start = portfolio.roth_conversion_taxes

    # Reset per-year withdrawal accumulator and snapshot pre-withdrawal portfolio.
    # This becomes the denominator for the withdrawal-rate plot.
    portfolio._current_year_withdrawals = {
        'cash': 0.0, 'taxable': 0.0, 'traditional': 0.0, 'roth': 0.0, 'hsa': 0.0,
    }
    pre_withdrawal_total = portfolio.get_total_balance()

    # Calculate partner's age
    partner_age = your_age - (cfg.YOUR_AGE - cfg.PARTNER_AGE)

    # Record the age employment ended. The Rule of 55 exception depends on the
    # age you SEPARATED FROM SERVICE, not merely your current age, so capture it
    # the first time we enter the retirement phase.
    if portfolio.separation_age is None:
        portfolio.separation_age = float(retirement_age)

    # Spending guardrails: adjust the discretionary portion of expenses
    # (housing held fixed when MODEL_GUARDRAILS_EXCLUDE_HOUSING).
    adjusted_expenses = _apply_spending_guardrails(
        portfolio, expenses, annual_return, your_age, inflation_factor
    )

    # RMD collection (drains traditional balances, computes RMD tax).
    rmd_total, rmd_tax = _collect_rmds(portfolio, your_age, partner_age)

    # 72(t) SEPP: a fixed, penalty-free draw from traditional accounts that,
    # once started, must run for the longer of 5 years or until 59.5.
    sepp_total, sepp_tax = _collect_sepp(portfolio, your_age)

    # Social Security income + tax on its taxable portion.
    ss_income, ss_tax = _collect_social_security(portfolio, your_age, inflation_factor)

    # 529 withdrawals for college expenses (tax-free)
    college_529_withdrawn = portfolio.withdraw_529_for_college(your_age, inflation_factor)

    # Health / LTC / car expense assembly (Pass-1 provisional premium).
    health_insurance, ltc_cost, car_cost = _assemble_health_ltc_car_expenses(
        portfolio, your_age, adjusted_expenses, healthcare_factor
    )

    # Record this year's spending for the cross-scenario spending-range chart.
    # 'living' is the guardrail-adjusted base living expense (what markets +
    # guardrails flex); 'total' adds healthcare + LTC + car. Recorded in today's
    # (real) dollars, consistent with the all-real engine frame.
    portfolio.spending_log.append({
        "age": int(your_age),
        "living": float(adjusted_expenses),
        "total": float(adjusted_expenses + health_insurance + ltc_cost + car_cost),
    })

    # Net-expense withdrawals + Roth conversion + premium true-up + solvency.
    # A still-working partner's take-home (partner_income) offsets the withdrawal
    # need and their earned income (partner_magi) is folded into the ACA/IRMAA
    # MAGI; both are 0.0 unless the separate-partner-retirement-age feature has
    # the partner working past the primary's retirement.
    solvent, rmd_total, reinvested_surplus = _fund_net_expenses(
        portfolio, your_age, adjusted_expenses, health_insurance, ltc_cost,
        car_cost, ss_income, ss_tax, rmd_total, rmd_tax, college_529_withdrawn,
        healthcare_factor, partner_income=partner_income, partner_magi=partner_magi,
        sepp_total=sepp_total, sepp_tax=sepp_tax,
    )
    if not solvent:
        return False

    # Withdrawal-log flush for this retirement year.
    _flush_withdrawal_log(
        portfolio, your_age, rmd_total, pre_withdrawal_total,
        _taxes_start, _niit_start, _ss_tax_start, _penalties_start,
        _roth_conversion_start, _roth_conversion_tax_start,
        reinvested_surplus=reinvested_surplus,
    )

    # Apply the return the CALLER passed in. ``_run_retirement_phase`` builds it
    # from the historical stress sequence when one was supplied, else from a
    # correlated parametric draw, so re-drawing here would (and previously did)
    # mean no historical sequence ever reached the portfolio, the
    # RETURN_BASED_SPENDING guardrail reacted to a return the portfolio never
    # earned, and two RNG draws were burned per retirement year. Passing -30%
    # used to produce +29.7% growth. This now matches simulate_accumulation_year,
    # which has always applied its argument directly.
    portfolio.apply_returns(annual_return)

    return True


def _run_retirement_phase(portfolio, retirement_age, inflation_factors,
                          historical_returns, verbose, partner_working_at) -> bool:
    """Run the decumulation phase from ``retirement_age`` to ``cfg.plan_end_age()``.

    Shared by ``run_detailed_simulation`` (fixed retirement age) and
    ``run_detailed_simulation_networth`` (retire when net worth hits a target).
    ``partner_working_at(age) -> bool`` decides whether the partner still earns in
    a given retirement year (for the separate-partner-retirement-age feature);
    pass ``lambda a: False`` when both retire together. Returns True while solvent,
    False the first year withdrawals can't be funded. Set the retirement baseline
    (``portfolio.set_retirement_baseline``) before calling.
    """
    years_until_retirement = retirement_age - cfg.YOUR_AGE
    years_in_retirement = cfg.plan_end_age() - retirement_age
    for year in range(years_in_retirement):
        current_age = retirement_age + year
        current_year = cfg.CURRENT_YEAR + years_until_retirement + year

        # Housing events landing in retirement must run BEFORE expenses are
        # computed so this year's housing reflects the purchase or sale. No-op
        # without a housing timeline.
        portfolio.apply_housing_events(current_age)

        base_expenses = calculate_retirement_expenses(
            current_age, inflation_factors, retirement_age=retirement_age,
            portfolio=portfolio,
        )

        historical_year_index = years_until_retirement + year
        if historical_returns and historical_year_index < len(historical_returns):
            # NOTE: NOMINAL config returns deflated to REAL by the single-year general
            # inflation rate (see accumulation-phase note above for the bug this fixes).
            single_year_inflation = cfg.INFLATION_RATES['general']
            stock_return = historical_returns[historical_year_index] - single_year_inflation
            # Bonds are a stochastic draw correlated (rho) to the historical
            # stock shock, not the fixed EXPECTED_BOND_RETURN.
            bond_return = generate_correlated_bond_for_stock(stock_return)
            stock_alloc, bond_alloc = cfg.calculate_asset_allocation(current_age, retirement_age)
            annual_return = stock_alloc * stock_return + bond_alloc * bond_return
            annual_return = clamp_return(annual_return)
        else:
            # Use correlated returns with volatility drag and fees
            stock_alloc, bond_alloc = cfg.calculate_asset_allocation(current_age, retirement_age)
            annual_return = calculate_blended_return(stock_alloc, bond_alloc)

        # Partner still working after the primary retired (feature): make their
        # 401(k)/Roth contributions and hand their take-home to the year's
        # funding as an income offset (surplus is banked), plus their wages to
        # the ACA/IRMAA MAGI. Zero when partner_working_at returns False.
        partner_income = 0.0
        partner_magi = 0.0
        if partner_working_at(current_age):
            years_from_start = current_age - cfg.YOUR_AGE
            married = cfg.normalize_filing_status() == cfg._FILING_MFJ
            p_after_tax, p_taxable, p_roth = _simulate_partner_working_year(
                portfolio, current_age, current_year, years_from_start, married
            )
            # Net cash the partner brings home = after-tax minus the after-tax
            # elective they already funded (Roth), mirroring how the accumulation
            # residual nets partner electives before the brokerage sweep.
            partner_income = max(0.0, p_after_tax - p_roth)
            partner_magi = p_taxable

        success = simulate_retirement_year(
            portfolio, current_age, base_expenses, annual_return,
            inflation_factors['general'], retirement_age,
            healthcare_factor=inflation_factors['healthcare'],
            partner_income=partner_income, partner_magi=partner_magi,
            partner_working=partner_working_at(current_age),
        )

        if not success:
            if verbose:
                print(f"  Ran out of money at age {current_age}")
            return False

        update_inflation_factors(inflation_factors)

        portfolio.record_year(current_year + 1, current_age + 1)
        if verbose and year % 10 == 0:
            print(f"  Age {current_age}: ${portfolio.get_total_balance()/1e6:.2f}M")

    return True


def run_detailed_simulation(
    retirement_age: int,
    verbose: bool = False,
    historical_sequence: Optional[str] = None,
    random_seed: Optional[int] = None
) -> Tuple[bool, AccountPortfolio]:
    """
    Run full simulation with all features.

    Args:
        retirement_age: Age to retire at
        verbose: Print progress updates
        historical_sequence: Use historical returns sequence (e.g., 'dot_com_crisis')
        random_seed: Optional seed for reproducible results
    """
    if random_seed is not None:
        np.random.seed(random_seed)
        import random as random_module
        random_module.seed(random_seed)

    # Guard: if retirement_age is less than current age, clamp to current age
    # (treat as "retire right now") so the simulation doesn't rewind time.
    if retirement_age < cfg.YOUR_AGE:
        retirement_age = cfg.YOUR_AGE

    portfolio = create_initial_portfolio()
    inflation_factors = {'general': 1.0, 'healthcare': 1.0, 'childcare': 1.0}
    historical_returns = []
    if historical_sequence:
        historical_returns = cfg.get_historical_returns_for_sequence(historical_sequence)

    portfolio.record_year(cfg.CURRENT_YEAR, cfg.YOUR_AGE)
    years_until_retirement = retirement_age - cfg.YOUR_AGE

    # ------------------------------------------------------------------
    # Partner retirement timing (separate-partner-retirement-age feature).
    # ``_partner_working_at(your_age)`` reports whether the partner is still
    # earning in the year the primary is that age. When PARTNER_RETIREMENT_AGE is
    # None (the default) or there is no partner, it exactly tracks the primary's
    # own working state, so both loops below reproduce the original household-wide
    # switch byte-for-byte. Set it and the partner can retire before the primary
    # (stop earning during accumulation) or after (keep earning into retirement).
    # A single household has no partner, so no partner working years at all.
    # ------------------------------------------------------------------
    _partner_ret_age = getattr(cfg, "PARTNER_RETIREMENT_AGE", None)
    _has_partner = cfg.has_partner()
    _age_gap = cfg.YOUR_AGE - cfg.PARTNER_AGE  # primary_age - partner_age (constant)

    def _partner_working_at(your_age_now: int) -> bool:
        if not _has_partner:
            return False
        if _partner_ret_age is None:
            return your_age_now < retirement_age  # default: partner retires with primary
        return (your_age_now - _age_gap) < int(_partner_ret_age)

    # Accumulation phase
    for year in range(years_until_retirement):
        current_age = cfg.YOUR_AGE + year
        current_year = cfg.CURRENT_YEAR + year

        if historical_returns and year < len(historical_returns):
            # NOTE: historical_returns from config.py HISTORICAL_RETURNS are NOMINAL
            # and must be deflated to REAL to match the all-real engine frame.
            # Subtract the SINGLE-YEAR general inflation rate (not the cumulative
            # factor). The old code subtracted (inflation_factors['general'] - 1.0),
            # a cumulative factor that over-deflated more every year; and in the
            # all-real frame that factor is pinned at 1.0, so it would deflate by 0.
            single_year_inflation = cfg.INFLATION_RATES['general']
            stock_return = historical_returns[year] - single_year_inflation
            # Split the historical stock shock across the portfolio: the bond
            # sleeve gets a stochastic draw correlated to that stock shock,
            # rather than riding the equity return.
            bond_return = generate_correlated_bond_for_stock(stock_return)
            annual_return = (cfg.STOCK_ALLOCATION * stock_return
                             + cfg.BOND_ALLOCATION * bond_return)
        else:
            # Use correlated returns with volatility drag and fees
            annual_return = calculate_blended_return(cfg.STOCK_ALLOCATION, cfg.BOND_ALLOCATION)
        annual_return = clamp_return(annual_return)

        acc_solvent = simulate_accumulation_year(
            portfolio, current_age, annual_return,
            partner_working=_partner_working_at(current_age),
        )
        if not acc_solvent:
            # A partner-retired-early drawdown depleted the portfolio while the
            # primary was still working (feature-only path; never reached in the
            # default case where partner_working is always True here).
            if verbose:
                print(f"  Ran out of money at age {current_age}")
            return False, portfolio

        update_inflation_factors(inflation_factors)

        portfolio.record_year(current_year + 1, current_age + 1)
        if verbose and year % 5 == 0:
            print(f"  Age {current_age}: ${portfolio.get_total_balance()/1e6:.2f}M")

    # Retirement phase
    # Set baseline portfolio for spending guardrails
    portfolio.set_retirement_baseline(inflation_factors['general'])

    if not _run_retirement_phase(portfolio, retirement_age, inflation_factors,
                                 historical_returns, verbose, _partner_working_at):
        return False, portfolio

    return True, portfolio


def run_detailed_simulation_networth(
    networth_target: float,
    max_work_age: int = 70,
    verbose: bool = False,
    random_seed: Optional[int] = None,
) -> Tuple[bool, AccountPortfolio, int]:
    """Retire the moment the INVESTABLE portfolio first reaches ``networth_target``.

    Answers "what net worth lets us stop working?" rather than "at what age?":
    both partners keep working (and contributing) until the household's investable
    balance hits the target, then BOTH retire that year and decumulate to the
    plan's end (``cfg.plan_end_age()``). If the target isn't reached by
    ``max_work_age``, they retire then anyway (with less than the target). If the
    target is at/below today's balance, they retire immediately.

    Returns ``(success, portfolio, retire_age)``. Parametric returns only (no
    historical sequence) — this drives the net-worth sweep.
    """
    if random_seed is not None:
        np.random.seed(random_seed)
        import random as random_module
        random_module.seed(random_seed)

    portfolio = create_initial_portfolio()
    inflation_factors = {'general': 1.0, 'healthcare': 1.0, 'childcare': 1.0}
    portfolio.record_year(cfg.CURRENT_YEAR, cfg.YOUR_AGE)

    # Can't work past the plan horizon; keep at least a few retirement years.
    cap_age = max(cfg.YOUR_AGE, min(int(max_work_age), cfg.plan_end_age() - 1))

    year = 0
    # Accumulate (both partners working) until the investable portfolio first
    # reaches the target, or we hit the work-cap age. Measured on the spendable
    # investable balance (get_investable_balance excludes earmarked 529 funds),
    # so we never "retire" on money that can't cover retirement expenses.
    while (cfg.YOUR_AGE + year) < cap_age and portfolio.get_investable_balance() < networth_target:
        current_age = cfg.YOUR_AGE + year
        current_year = cfg.CURRENT_YEAR + year
        annual_return = clamp_return(
            calculate_blended_return(cfg.STOCK_ALLOCATION, cfg.BOND_ALLOCATION)
        )
        acc_solvent = simulate_accumulation_year(
            portfolio, current_age, annual_return, partner_working=cfg.has_partner()
        )
        if not acc_solvent:  # rare partner-retired-early-style drawdown depletion
            return False, portfolio, current_age
        update_inflation_factors(inflation_factors)
        portfolio.record_year(current_year + 1, current_age + 1)
        year += 1

    retire_age = cfg.YOUR_AGE + year
    portfolio.set_retirement_baseline(inflation_factors['general'])
    # Both partners retire together at the trigger -> no partner work income.
    success = _run_retirement_phase(
        portfolio, retire_age, inflation_factors, [], verbose, lambda a: False
    )
    return success, portfolio, retire_age


def run_monte_carlo_networth(
    networth_target: float, n_simulations: int = 1000,
    max_work_age: int = 70, random_seed: Optional[int] = None,
) -> Dict:
    """Monte Carlo of the net-worth-trigger sim: success rate + the distribution
    of the age at which the household reaches ``networth_target`` and retires."""
    if random_seed is not None:
        np.random.seed(random_seed)
        import random as random_module
        random_module.seed(random_seed)

    successes = 0
    retire_ages: List[int] = []
    for _ in range(int(n_simulations)):
        ok, _p, rage = run_detailed_simulation_networth(networth_target, max_work_age=max_work_age)
        if ok:
            successes += 1
        retire_ages.append(rage)
    n = max(1, int(n_simulations))
    sr = successes / n
    return {
        'networth_target': float(networth_target),
        'success_rate': sr,
        'success_rate_se': float(np.sqrt(sr * (1 - sr) / n)),
        'median_retire_age': float(np.median(retire_ages)) if retire_ages else None,
        'p10_retire_age': float(np.percentile(retire_ages, 10)) if retire_ages else None,
        'p90_retire_age': float(np.percentile(retire_ages, 90)) if retire_ages else None,
    }


def run_monte_carlo_detailed(retirement_age: int, n_simulations: int = 1000, random_seed: Optional[int] = None) -> Dict:
    """
    Run Monte Carlo simulation with detailed tax tracking.

    Args:
        retirement_age: Age to retire at
        n_simulations: Number of simulations to run
        random_seed: Optional seed for reproducible results
    """
    if random_seed is not None:
        np.random.seed(random_seed)
        import random as random_module
        random_module.seed(random_seed)

    successes = 0
    final_balances = []
    total_taxes = []
    roth_conversions = []
    aca_premiums = []
    early_penalties = []
    niit_taxes = []
    ss_taxes = []
    ltc_costs = []

    for i in range(n_simulations):
        success, portfolio = run_detailed_simulation(retirement_age)
        if success:
            successes += 1
        final_balances.append(portfolio.get_total_balance())
        total_taxes.append(portfolio.total_taxes_paid)
        roth_conversions.append(portfolio.total_roth_conversions)
        aca_premiums.append(portfolio.total_aca_premiums + portfolio.total_medicare_premiums)
        early_penalties.append(portfolio.total_early_withdrawal_penalties)
        niit_taxes.append(portfolio.total_niit_paid)
        ss_taxes.append(portfolio.total_ss_taxes_paid)
        ltc_costs.append(portfolio.total_ltc_costs)

    success_rate = successes / n_simulations
    success_rate_se = np.sqrt(success_rate * (1 - success_rate) / n_simulations)
    return {
        'retirement_age': retirement_age,
        'success_rate': success_rate,
        'success_rate_se': success_rate_se,
        'success_rate_ci95': (success_rate - 1.96 * success_rate_se,
                              success_rate + 1.96 * success_rate_se),
        'median_final': np.median(final_balances),
        'percentile_10': np.percentile(final_balances, 10),
        'percentile_25': np.percentile(final_balances, 25),
        'percentile_75': np.percentile(final_balances, 75),
        'percentile_90': np.percentile(final_balances, 90),
        'median_taxes': np.median(total_taxes),
        'median_roth_conversions': np.median(roth_conversions),
        'median_health_premiums': np.median(aca_premiums),
        'median_early_penalties': np.median(early_penalties),
        'median_niit': np.median(niit_taxes),
        'median_ss_taxes': np.median(ss_taxes),
        'median_ltc_costs': np.median(ltc_costs),
    }


def run_sequence_of_returns_analysis(retirement_age: int, n_simulations: int = 1000) -> Dict:
    """Run sequence of returns risk analysis."""
    results = {}

    print(f"Running Monte Carlo baseline ({n_simulations} simulations)...")
    mc_result = run_monte_carlo_detailed(retirement_age, n_simulations)
    results['monte_carlo'] = {
        'name': 'Random Monte Carlo',
        'success_rate': mc_result['success_rate'],
        'median_final': mc_result['median_final'],
        'percentile_10': mc_result['percentile_10'],
        'description': f'{n_simulations} random simulations'
    }

    for seq_name, seq_info in cfg.SEQUENCE_TESTS.items():
        print(f"Running {seq_info['name']}...")
        successes = 0
        final_balances = []
        n_seq_runs = min(100, n_simulations)

        for _ in range(n_seq_runs):
            success, portfolio = run_detailed_simulation(
                retirement_age, verbose=False, historical_sequence=seq_name
            )
            if success:
                successes += 1
            final_balances.append(portfolio.get_total_balance())

        results[seq_name] = {
            'name': seq_info['name'],
            'success_rate': successes / n_seq_runs,
            'median_final': np.median(final_balances),
            'percentile_10': np.percentile(final_balances, 10),
            'description': seq_info['description'],
            'years': seq_info['years']
        }

    return results


def print_sequence_analysis_report(results: Dict, retirement_age: int):
    """Print formatted report of sequence analysis."""
    print("\n" + "=" * 70)
    print(f"SEQUENCE OF RETURNS RISK ANALYSIS - Retire at Age {retirement_age}")
    print("=" * 70)

    sorted_results = sorted(results.items(), key=lambda x: x[1]['success_rate'])

    print(f"\n{'Scenario':<40} {'Success Rate':>12} {'Median Final':>15}")
    print("-" * 70)

    for name, data in sorted_results:
        success_pct = f"{data['success_rate']:.1%}"
        median_str = f"${data['median_final']/1e6:.2f}M"
        print(f"{data['name']:<40} {success_pct:>12} {median_str:>15}")


def generate_correlated_returns_for_scenario(scenario: str = None) -> Tuple[float, float]:
    """
    Generate correlated stock and bond returns for a specific return scenario.

    Order of operations (mathematically correct):
    1. Deduct investment fees from expected returns
    2. Apply volatility drag adjustment to net returns
    3. Add stochastic variation

    Args:
        scenario: One of 'conservative', 'historical', 'pessimistic'

    Returns:
        Tuple of (stock_return, bond_return) for the year
    """
    params = cfg.get_return_parameters(scenario)

    z1 = np.random.standard_normal()
    z2 = np.random.standard_normal()

    rho = cfg.STOCK_BOND_CORRELATION
    z2_correlated = rho * z1 + np.sqrt(1 - rho**2) * z2

    # Step 1: Deduct investment fees from expected returns
    stock_mean = params['stock_return'] - cfg.INVESTMENT_FEE_RATE
    bond_mean = params['bond_return'] - cfg.INVESTMENT_FEE_RATE

    # Step 2: Apply volatility drag adjustment to net returns
    if cfg.APPLY_VOLATILITY_DRAG:
        stock_vol_drag = (params['stock_volatility'] ** 2) / 2
        bond_vol_drag = (params['bond_volatility'] ** 2) / 2
        stock_mean -= stock_vol_drag
        bond_mean -= bond_vol_drag

    # Step 3: Generate returns with stochastic variation
    stock_return = stock_mean + params['stock_volatility'] * z1
    bond_return = bond_mean + params['bond_volatility'] * z2_correlated

    return stock_return, bond_return


def run_monte_carlo_with_scenario(
    retirement_age: int,
    scenario: str = 'conservative',
    n_simulations: int = 1000,
    random_seed: Optional[int] = None
) -> Dict:
    """Run Monte Carlo simulation with a specific return scenario."""
    if random_seed is not None:
        np.random.seed(random_seed)
        import random as random_module
        random_module.seed(random_seed)

    successes = 0
    final_balances = []
    total_taxes = []
    roth_conversions = []
    aca_premiums = []
    early_penalties = []

    # Partner retirement timing (see run_detailed_simulation for the rationale).
    # Constant across all simulations; None tracks the primary's own working
    # state so this scenario path stays byte-identical when unused. No partner,
    # no partner working years.
    _partner_ret_age = getattr(cfg, "PARTNER_RETIREMENT_AGE", None)
    _has_partner = cfg.has_partner()
    _age_gap = cfg.YOUR_AGE - cfg.PARTNER_AGE

    def _partner_working_at(your_age_now: int) -> bool:
        if not _has_partner:
            return False
        if _partner_ret_age is None:
            return your_age_now < retirement_age
        return (your_age_now - _age_gap) < int(_partner_ret_age)

    for _ in range(n_simulations):
        portfolio = create_initial_portfolio()
        inflation_factors = {'general': 1.0, 'healthcare': 1.0, 'childcare': 1.0}
        portfolio.record_year(cfg.CURRENT_YEAR, cfg.YOUR_AGE)
        years_until_retirement = retirement_age - cfg.YOUR_AGE

        # Accumulation phase
        acc_solvent = True
        for year in range(years_until_retirement):
            current_age = cfg.YOUR_AGE + year
            current_year = cfg.CURRENT_YEAR + year

            stock_return, bond_return = generate_correlated_returns_for_scenario(scenario)
            annual_return = cfg.STOCK_ALLOCATION * stock_return + cfg.BOND_ALLOCATION * bond_return
            annual_return = clamp_return(annual_return)

            acc_solvent = simulate_accumulation_year(
                portfolio, current_age, annual_return,
                partner_working=_partner_working_at(current_age),
            )

            update_inflation_factors(inflation_factors)

            portfolio.record_year(current_year + 1, current_age + 1)
            if not acc_solvent:
                break

        # Retirement phase
        # Set baseline portfolio for spending guardrails
        portfolio.set_retirement_baseline(inflation_factors['general'])

        # A partner-retired-early drawdown that depleted the portfolio during
        # accumulation is an outright failure -- don't run the retirement phase.
        success = acc_solvent
        years_in_retirement = cfg.plan_end_age() - retirement_age
        for year in range(years_in_retirement if acc_solvent else 0):
            current_age = retirement_age + year
            current_year = cfg.CURRENT_YEAR + (retirement_age - cfg.YOUR_AGE) + year

            portfolio.apply_housing_events(current_age)

            base_expenses = calculate_retirement_expenses(
                current_age, inflation_factors, retirement_age=retirement_age,
                portfolio=portfolio,
            )

            stock_alloc, bond_alloc = cfg.calculate_asset_allocation(current_age, retirement_age)
            stock_return, bond_return = generate_correlated_returns_for_scenario(scenario)
            annual_return = stock_alloc * stock_return + bond_alloc * bond_return
            annual_return = clamp_return(annual_return)

            partner_income = 0.0
            partner_magi = 0.0
            if _partner_working_at(current_age):
                years_from_start = current_age - cfg.YOUR_AGE
                married = cfg.normalize_filing_status() == cfg._FILING_MFJ
                p_after_tax, p_taxable, p_roth = _simulate_partner_working_year(
                    portfolio, current_age, current_year, years_from_start, married
                )
                partner_income = max(0.0, p_after_tax - p_roth)
                partner_magi = p_taxable

            result = simulate_retirement_year(
                portfolio, current_age, base_expenses, annual_return,
                inflation_factors['general'], retirement_age,
                healthcare_factor=inflation_factors['healthcare'],
                partner_income=partner_income, partner_magi=partner_magi,
                partner_working=_partner_working_at(current_age),
            )

            if not result:
                success = False
                break

            update_inflation_factors(inflation_factors)

            portfolio.record_year(current_year + 1, current_age + 1)

        if success:
            successes += 1
        final_balances.append(portfolio.get_total_balance())
        total_taxes.append(portfolio.total_taxes_paid)
        roth_conversions.append(portfolio.total_roth_conversions)
        aca_premiums.append(portfolio.total_aca_premiums + portfolio.total_medicare_premiums)
        early_penalties.append(portfolio.total_early_withdrawal_penalties)

    success_rate = successes / n_simulations
    success_rate_se = np.sqrt(success_rate * (1 - success_rate) / n_simulations)
    return {
        'retirement_age': retirement_age,
        'scenario': scenario,
        'scenario_name': cfg.RETURN_SCENARIOS[scenario]['name'],
        'success_rate': success_rate,
        'success_rate_se': success_rate_se,
        'success_rate_ci95': (success_rate - 1.96 * success_rate_se,
                              success_rate + 1.96 * success_rate_se),
        'median_final': np.median(final_balances),
        'percentile_10': np.percentile(final_balances, 10),
        'percentile_25': np.percentile(final_balances, 25),
        'percentile_75': np.percentile(final_balances, 75),
        'percentile_90': np.percentile(final_balances, 90),
        'median_taxes': np.median(total_taxes),
        'median_roth_conversions': np.median(roth_conversions),
        'median_health_premiums': np.median(aca_premiums),
        'median_early_penalties': np.median(early_penalties),
    }


def compare_return_scenarios(
    retirement_ages: List[int] = None,
    n_simulations: int = 1000
) -> Dict:
    """
    Compare results across all return scenarios.

    Args:
        retirement_ages: List of retirement ages to test (default: [45, 50, 55])
        n_simulations: Number of Monte Carlo runs per scenario

    Returns:
        Dict with results for each scenario and retirement age combination
    """
    if retirement_ages is None:
        retirement_ages = [45, 50, 55]

    results = {}
    scenarios = list(cfg.RETURN_SCENARIOS.keys())

    for ret_age in retirement_ages:
        results[ret_age] = {}
        for scenario in scenarios:
            print(f"Running {scenario} scenario for retirement age {ret_age}...")
            result = run_monte_carlo_with_scenario(ret_age, scenario, n_simulations)
            results[ret_age][scenario] = result

    return results


def print_scenario_comparison_report(results: Dict):
    """Print formatted report comparing return scenarios."""
    print("\n" + "=" * 80)
    print("RETURN SCENARIO COMPARISON")
    print("=" * 80)

    for ret_age, scenarios in results.items():
        print(f"\n--- Retirement Age {ret_age} ---")
        print(f"{'Scenario':<20} {'Success Rate':>12} {'Median Final':>15} {'10th %ile':>15}")
        print("-" * 65)

        for scenario, data in scenarios.items():
            success_pct = f"{data['success_rate']:.1%}"
            median_str = f"${data['median_final']/1e6:.2f}M"
            p10_str = f"${data['percentile_10']/1e6:.2f}M"
            print(f"{data['scenario_name']:<20} {success_pct:>12} {median_str:>15} {p10_str:>15}")


if __name__ == "__main__":
    print("=" * 70)
    print("ACCOUNT-BASED SIMULATION TEST (WITH REALISTIC TAX MODELING)")
    print("=" * 70)
    print("\nTax features implemented:")
    print("  - Standard deduction ($29,200 MFJ + age 65+ additions)")
    print("  - Social Security taxation (up to 85% taxable)")
    print("  - Early withdrawal penalties (10% on 401k/IRA before 59.5)")
    print("  - HSA penalties (20% for non-medical before 65)")
    print("  - NIIT (3.8% on investment income above $250k)")
    print("  - Medicare IRMAA surcharges for high earners")

    print("\nRunning single simulation (retire at 50)...\n")
    success, portfolio = run_detailed_simulation(50, verbose=True)

    print(f"\n{'SUCCESS' if success else 'FAILED'}")
    print(f"\nFinal account balances:")
    for name, account in portfolio.accounts.items():
        if account.balance > 0:
            print(f"  {name}: ${account.balance:,.0f}")

    print(f"\nTotal: ${portfolio.get_total_balance():,.0f}")
    print(f"\n--- TAX BREAKDOWN ---")
    print(f"Total taxes paid: ${portfolio.total_taxes_paid:,.0f}")
    print(f"  - SS taxes: ${portfolio.total_ss_taxes_paid:,.0f}")
    print(f"  - Early withdrawal penalties: ${portfolio.total_early_withdrawal_penalties:,.0f}")
    print(f"  - NIIT: ${portfolio.total_niit_paid:,.0f}")
    print(f"\nTotal Roth conversions: ${portfolio.total_roth_conversions:,.0f}")
    print(f"Total ACA premiums: ${portfolio.total_aca_premiums:,.0f}")
    print(f"Total Medicare premiums: ${portfolio.total_medicare_premiums:,.0f}")
    print(f"Total LTC costs: ${portfolio.total_ltc_costs:,.0f}")

    print("\n" + "=" * 70)
    print("SEQUENCE OF RETURNS ANALYSIS")
    print("=" * 70)
    seq_results = run_sequence_of_returns_analysis(50, n_simulations=500)
    print_sequence_analysis_report(seq_results, 50)


def mortgage_payoff_projection(extra_annual: float = 0.0,
                               max_age: int = 120) -> dict:
    """Deterministically project when the mortgage is retired.

    Amortisation depends only on (balance, rate, payment, extra) -- NOT on market
    returns -- so this is exact and free, rather than something to mine out of
    Monte Carlo output (where per-year loan state isn't even surfaced).

    Mirrors the engine's own schedule: ``_level_payment`` at
    ``MORTGAGE_RATE_FOR_PAYOFF`` for today's loan, then the housing timeline
    (cfg.housing_events): a purchase replaces the loan with its own, a sale to
    rent ends it. Kept next to ``_amortize_mortgage_year`` so the two stay
    consistent.

    Returns ``{payoff_age, total_interest, years_saved_vs_scheduled}``;
    ``payoff_age`` is None when the loan outlives ``max_age``.
    """
    rate = max(0.0, float(cfg.MORTGAGE_RATE_FOR_PAYOFF))
    r = rate / 12.0
    start_age = int(cfg.YOUR_AGE)
    bal = float(cfg.MORTGAGE_BALANCE or 0.0)
    pi = _level_payment(bal, rate, int(cfg.MORTGAGE_YEARS_REMAINING or 0))
    extra_annual = max(0.0, float(extra_annual or 0.0))

    events = cfg.housing_events()
    last_purchase = max((e["age"] for e in events if e["action"] != cfg.HOME_SELL_RENT),
                        default=None)

    interest = 0.0
    payoff_age = None
    age = start_age
    while age <= max_age:
        for e in events:
            if e["age"] != age:
                continue
            if e["action"] == cfg.HOME_SELL_RENT:
                bal, pi = 0.0, 0.0                      # sold: the loan is repaid
            else:
                bal, rate = e["loan"], e["rate"]        # the new loan's own rate
                r = rate / 12.0
                pi = _level_payment(bal, rate, e["years"])
        if bal <= 0:
            # Only conclude "paid off" once no future purchase can revive the loan.
            if payoff_age is None and not (last_purchase is not None and age < last_purchase):
                payoff_age = age
                break
        else:
            extra_monthly = extra_annual / 12.0
            for _ in range(12):
                if bal <= 0:
                    break
                interest += bal * r
                bal = bal * (1.0 + r) - pi - extra_monthly
                if bal < 0:
                    bal = 0.0
                    break
            if bal < 0.01:
                bal = 0.0
        age += 1

    scheduled_payoff = None
    if extra_annual > 0:
        base = mortgage_payoff_projection(0.0, max_age=max_age)
        scheduled_payoff = base.get("payoff_age")
    years_saved = None
    if payoff_age is not None and scheduled_payoff is not None:
        years_saved = scheduled_payoff - payoff_age

    return {"payoff_age": payoff_age, "total_interest": interest,
            "years_saved_vs_scheduled": years_saved}
