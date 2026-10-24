"""Who the plan is for: one adult, a married couple, or an unmarried couple.

Said only through existing config keys, so the engine needs nothing new:
PARTNER_AGE > 0 means there is a partner (``cfg.has_partner``), and
FILING_STATUS "Married filing jointly" means the couple is married. An
unmarried partner keeps Single or Head of household as the filing status.
"""
from __future__ import annotations

try:
    from utils.coerce import safe_int
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int  # type: ignore

JUST_ME, SPOUSE, PARTNER = "Just me", "Me and my spouse", "Me and my partner (not married)"
HOUSEHOLDS = [JUST_ME, SPOUSE, PARTNER]

MFJ, SINGLE, HOH = "Married filing jointly", "Single", "Head of household"
# Filing statuses open to someone who isn't married.
UNMARRIED_FILING = [SINGLE, HOH]

# Every partner input. With no partner they are all zeroed: the engine already
# leaves them out (cfg.has_partner), and a saved profile then says so too.
PARTNER_AMOUNT_KEYS = (
    "PARTNER_401K", "PARTNER_ROTH_IRA", "PARTNER_BROKERAGE", "PARTNER_CASH",
    "PARTNER_401K_CONTRIBUTION", "PARTNER_ROTH_CONTRIBUTION", "PARTNER_BROKERAGE_CONTRIBUTION",
    "PARTNER_SALARY", "PARTNER_BASE_SALARY", "PARTNER_BONUS_AMOUNT", "PARTNER_RSU_AMOUNT",
    "PARTNER_OTHER_INCOME", "PARTNER_SS_MONTHLY_FRA",
    "PARTNER_OTHER_MONTHLY", "PARTNER_MONTHLY_SPENDING",
)
# Partner settings that fall back to "same as you" (None) with no partner.
PARTNER_OPTIONAL_KEYS = ("PARTNER_RETIREMENT_AGE", "PARTNER_PLAN_UNTIL_AGE", "PARTNER_SS_CLAIM_AGE")


def household_of(overrides: dict) -> str:
    """The household an overrides dict describes."""
    if safe_int(overrides.get("PARTNER_AGE", 0), 0) <= 0:
        return JUST_ME
    return SPOUSE if str(overrides.get("FILING_STATUS", MFJ)) in (MFJ, "MFJ") else PARTNER


def clear_partner(overrides: dict) -> None:
    """Make ``overrides`` a single household: no partner and no partner money."""
    overrides["PARTNER_AGE"] = 0
    for key in PARTNER_AMOUNT_KEYS:
        overrides[key] = 0
    for key in PARTNER_OPTIONAL_KEYS:
        overrides[key] = None
    overrides["PRIMARY_PAYS_HOUSING"] = False
