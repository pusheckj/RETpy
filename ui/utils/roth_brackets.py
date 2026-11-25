"""Roth conversion targets in bracket terms.

The engine fills each year's income up to ``ROTH_CONVERSION_TARGET_BRACKET``
(``AccountPortfolio.perform_roth_conversion``: room = target minus
``year_ordinary_income``). ``year_ordinary_income`` is gross ordinary income:
the standard deduction is only taken later, when the tax is worked out
(``_marginal_tax_parts``). So "fill the 22% bracket" means a target of the 22%
bracket's top PLUS the standard deduction. (The extra deduction at 65+ is left
out, so after 65 the fill stops a little short of the top: the safe side.)

All figures come from the config's 2026 tables for the filing status of your
return (``cfg.return_status("you")``). An unmarried couple files two returns
with one shared target, so two Single returns use the Single figures.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from retirement_sim import config as cfg

# The brackets the optimizer offers, by marginal rate.
SWEEP_RATES = (0.12, 0.22, 0.24)


def _status(status=None) -> str:
    return cfg.normalize_filing_status(status)


def fill_target(rate: float, status=None) -> int:
    """Income (before the standard deduction) that fills the ``rate`` bracket
    to its top on a return with this filing status."""
    s = _status(status)
    top = next(t for t, r in cfg.FEDERAL_BRACKETS_BY_STATUS[s] if abs(r - rate) < 1e-9)
    return int(round(top + cfg.STANDARD_DEDUCTION_BY_STATUS[s]))


def sweep_targets(status=None) -> List[Tuple[float, int]]:
    """``[(rate, income target), ...]`` for the optimizer's rows."""
    return [(r, fill_target(r, status)) for r in SWEEP_RATES]


def bracket_note(income: Optional[float], status=None) -> str:
    """Which bracket a "fill up to income of" value reaches, in words.

    E.g. ``"≈ top of the 12% bracket"`` or ``"partway into the 12% bracket"``.
    The value is income before the standard deduction, as the engine reads it.
    """
    s = _status(status)
    try:
        income = float(income or 0.0)
    except (TypeError, ValueError):
        return ""
    taxable = income - cfg.STANDARD_DEDUCTION_BY_STATUS[s]
    if taxable <= 0:
        return "within the standard deduction, so no ordinary tax (it also stops sheltering any gains sold this year)"
    lower = 0.0
    for top, rate in cfg.FEDERAL_BRACKETS_BY_STATUS[s]:
        if taxable <= top:
            name = f"{rate:.0%} bracket"
            width = top - lower
            # Within 3% of the band's width from either edge reads as "the top".
            if top != float("inf") and top - taxable <= 0.03 * width:
                return f"≈ top of the {name}"
            if taxable - lower <= 0.03 * width and lower > 0:
                prev = _rate_below(s, lower)
                return f"≈ top of the {prev:.0%} bracket" if prev is not None else f"in the {name}"
            return f"partway into the {name}"
        lower = top
    return ""


def _rate_below(status: str, top: float) -> Optional[float]:
    for t, r in cfg.FEDERAL_BRACKETS_BY_STATUS[status]:
        if abs(t - top) < 1e-6:
            return r
    return None
