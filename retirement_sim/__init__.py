"""Open-source Monte Carlo retirement simulator with realistic tax modeling.

License: MIT
"""

__version__ = "0.1.0"
__license__ = "MIT"

from .account_simulation import (
    run_monte_carlo_detailed,
    run_detailed_simulation,
    simulate_accumulation_year,
    simulate_retirement_year,
    AccountPortfolio,
    TaxBrackets,
    CaliforniaTaxBrackets,
)
from . import config

__all__ = [
    "run_monte_carlo_detailed",
    "run_detailed_simulation",
    "simulate_accumulation_year",
    "simulate_retirement_year",
    "AccountPortfolio",
    "TaxBrackets",
    "CaliforniaTaxBrackets",
    "config",
    "__version__",
    "__license__",
]
