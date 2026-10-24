"""The savings accounts the Savings charts show, and how a year's savings add up.

Both Savings charts read ``results['primary_result']['savings_contributions_by_year']``
(``utils.sim_runner._approximate_savings_contributions``): the simulation's own
per-year deferrals, employer match, Roth and brokerage sweep from
``account_simulation.working_year_cashflow``. This module is their one
definition of which accounts count and in what order, so "Year 1 savings", the
stacked bars and the savings-rate bars are the same sum.

(The old per-account input form that used to live here was superseded by
``sec_savings.py``. Its projection helper re-derived contributions from the
inputs with a rough 55% primary-earner share for the employer match, so the
charts disagreed with the simulation; it is gone.)
"""
from __future__ import annotations

try:
    from utils.plot_theme import series_color
except ImportError:  # pragma: no cover
    from ui.utils.plot_theme import series_color  # type: ignore


# (label, savings_contributions_by_year field, owner), in stacking order.
# Employer match is included: "total savings" counts everything flowing into
# your accounts, not just what leaves the paycheck.
ALLOCATION_ORDER = [
    ("Your 401(k)",             "your_401k",              "you"),
    ("Your 401(k) match",       "your_employer_match",    "you"),
    ("Your HSA",                "your_hsa",               "you"),
    ("Your Roth (backdoor)",    "your_roth",              "you"),
    ("After-tax 401(k) → Roth", "your_aftertax_roth",     "you"),
    ("Your brokerage",          "your_brokerage",         "you"),
    ("Partner 401(k)",          "partner_401k",           "partner"),
    ("Partner 401(k) match",    "partner_employer_match", "partner"),
    ("Partner Roth IRA",        "partner_roth",           "partner"),
    ("Partner brokerage",       "partner_brokerage",      "partner"),
]

CONTRIBUTION_FIELDS = [field for _, field, _ in ALLOCATION_ORDER]


def year_savings(row: dict) -> float:
    """Everything saved in one working year, employer match included."""
    return sum(float(row.get(field, 0.0) or 0.0) for field in CONTRIBUTION_FIELDS)


def get_allocation_colors(st) -> dict:
    """Map each account to an active-palette color by its index in ALLOCATION_ORDER,
    so allocation colors follow the user's palette. Read at render time so it
    reacts to the palette picker.
    """
    return {label: series_color(i, st) for i, (label, _, _) in enumerate(ALLOCATION_ORDER)}
