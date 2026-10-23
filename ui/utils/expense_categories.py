"""The monthly expense categories, in one place.

The Expenses section's inputs (components/sec_expenses.py), the Spending tab's
buckets (components/spending_dashboard.py) and the widget sync table
(utils/widget_sync.py) are all built from this list, so every statement
category lands in the input it informs and the two screens can't drift apart.
"""
from __future__ import annotations

from typing import Dict, NamedTuple, Tuple


class Category(NamedTuple):
    label: str
    key: str                      # config / override key, $ per month
    statement: Tuple[str, ...]    # Spending-tab categories that add up to it
    widget: str                   # the Expenses-section input's session key
    default: int
    max_value: int
    step: int
    mirror: str = ""              # a second config key that must hold the same value
    partner_only: bool = False    # an input (and an expense) only with a partner
    help: str = ""


HOUSING = "Housing"
HOUSING_KEYS = ("MORTGAGE_MONTHLY", "SPEND_RENT_MONTHLY")   # owner, renter
HOUSING_STATEMENT = ("Housing",)
PARTNER = "Partner spending"

CATEGORIES = [
    Category("Utilities", "SPEND_UTILITIES_MONTHLY", ("Utilities",),
             "se_utilities", 200, 2_000, 25, mirror="UTILITIES_MONTHLY"),
    Category("Food & groceries", "SPEND_FOOD_MONTHLY", ("Groceries", "Dining"),
             "se_food", 900, 10_000, 50),
    Category("Transportation", "SPEND_TRANSPORT_MONTHLY", ("Auto & transport",),
             "se_transport", 500, 5_000, 50),
    Category("Healthcare premiums", "SPEND_HEALTH_MONTHLY", ("Health & fitness",),
             "se_health", 400, 5_000, 25),
    Category("Entertainment / discretionary", "SPEND_DISCRETIONARY_MONTHLY",
             ("Travel", "Entertainment", "Jewelry & watches", "Shopping", "Subscriptions",
              "Personal care", "Gifts & giving"),
             "se_discretionary", 600, 10_000, 50),
    Category("Other / miscellaneous", "SPEND_OTHER_MONTHLY",
             ("Insurance", "Home & garden", "Pets", "Fees & interest", "Cash & ATM",
              "People & shared", "Other"),
             "se_other", 300, 20_000, 25),
    # The engine spends PARTNER_OTHER_MONTHLY; the partner-savings math nets
    # PARTNER_MONTHLY_SPENDING out of the partner's pay (config.py: the two are
    # independent knobs that must agree). Not in your own statements, so the
    # Spending tab only has it from a fixed monthly estimate (rules "fixed_monthly").
    Category(PARTNER, "PARTNER_OTHER_MONTHLY", (PARTNER,),
             "se_partner", 1_500, 10_000, 50, mirror="PARTNER_MONTHLY_SPENDING",
             partner_only=True,
             help="Your partner's own monthly spending, beyond the shared costs above."),
]

# Every input "Use my actual spending" can set: override key -> (widget key, max).
INPUTS: Dict[str, Tuple[str, int]] = {
    "MORTGAGE_MONTHLY": ("se_mortgage_monthly", 20_000),
    "SPEND_RENT_MONTHLY": ("se_rent_monthly", 20_000),
    **{c.key: (c.widget, c.max_value) for c in CATEGORIES},
}
MIRRORS: Dict[str, str] = {c.key: c.mirror for c in CATEGORIES if c.mirror}
