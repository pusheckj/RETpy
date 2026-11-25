"""Typical childcare cost where you live.

The data and most steps come from BiggerPockets Money's Household Spending Comparison
v2.4.0 (credits in docs/DATA_SOURCES.md):

* Prices are the DOL National Database of Childcare Prices (NDCP, 2022) for four age
  tiers (infant, toddler, preschool, school-age), center-based care.
* A county's median is used as it is. A state's price is scaled by the area's BEA
  Rents index (clamped 0.65 to 1.70, BPM's clamp) when you pick an area with no county
  figure. A state with no area picked uses the state price as it is.
* The 2022 price is carried to 2025 with the CPI day-care index (x 1.172) and to 2026
  with one more year of it (x 1.0299).

The weights over the four tiers are OUR method, not BPM's. The childcare box covers a
child's first five years (ages 0 to 4). In NDCP's tiers those are two years of infant
(under 2), one of toddler (2) and two of preschool (3 and 4), so the weights are
0.4, 0.2, 0.4 and 0 for school-age. BPM's own weights guess how a household's children
spread over the tiers from the parent's age and the household size. They stay in
``bpm_weights`` to check this module against BPM's tool.

Pure functions, no Streamlit.
"""
from __future__ import annotations

from typing import List, NamedTuple, Optional, Tuple

from retirement_sim import config as cfg

try:
    from utils import budget_data as bd
except ImportError:  # pragma: no cover
    from ui.utils import budget_data as bd  # type: ignore

# The short credit shown beside the figure. The long one: docs/DATA_SOURCES.md.
SOURCE = ("US Dept. of Labor childcare prices, method from BiggerPockets Money. "
          "A statistical average, not a quote.")
RENT_SCALE_MIN, RENT_SCALE_MAX = 0.65, 1.70     # BPM's clamp on the state-price scaling
AGE_BANDS = ("Under25", "25-34", "35-44", "45-54", "55-64", "65+")
_INFANT_UNDER, _TODDLER_UNDER = 2, 3            # NDCP: infant under 2, toddler 2, preschool 3 to 5


def _time_in_tier() -> List[float]:
    """Share of a child's first CHILDCARE_END_AGE years spent in each NDCP tier."""
    years = cfg.CHILDCARE_END_AGE
    share = [0.0, 0.0, 0.0, 0.0]
    for age in range(years):
        share[0 if age < _INFANT_UNDER else 1 if age < _TODDLER_UNDER else 2] += 1.0 / years
    return share


TIME_IN_TIER = _time_in_tier()


class Estimate(NamedTuple):
    per_child: int          # a year of care for one child, 2026 dollars
    annual: int             # for ``n_children`` children
    coverage: str           # "county" | "area" (state price scaled) | "state" | "national"
    prices_2022: List[int]  # the eight NDCP prices used, before any inflation
    weights: List[float]    # the four tier weights used


def age_band(age: int) -> str:
    """BPM's age band for a person's age."""
    a = int(age)
    if a < 25:
        return "Under25"
    if a < 35:
        return "25-34"
    if a < 45:
        return "35-44"
    if a < 55:
        return "45-54"
    return "55-64" if a < 65 else "65+"


def size_key(people: int) -> str:
    """BPM's household-size key: 1, 2, 3, 4 or 5+."""
    return "5+" if int(people) >= 5 else str(max(1, int(people)))


def bpm_weights(parent_age: int, household_size: int) -> List[float]:
    """BPM's own weights over [infant, toddler, preschool, school-age] for full-time paid
    care: its table by the parent's age band and household size, school-age moved to
    preschool. Not used by the app. Kept to check the data and rounding against BPM."""
    table = bd.constants()["AGE_WEIGHT"]
    band, size = age_band(parent_age), size_key(household_size)
    w = list(table.get(band, table["35-44"]).get(size, table["35-44"]["4"]))
    w[2] += w[3]
    w[3] = 0.0
    return w


def _prices(state: Optional[str], area_label: Optional[str], renormalize: bool):
    """The eight 2022 prices for the place, and how they were found."""
    county = bd.county_childcare_prices(area_label)
    row = bd.area(area_label)
    if county:
        return list(county), "county"
    base = bd.state_childcare_prices(row["st"] if row else state)
    coverage = "state"
    if base is None:
        base, coverage = bd.constants()["NATIONAL"], "national"
    base = list(base)
    if row is not None:                         # an area with no county median: scale the state
        rents = bd.price_levels(row, renormalize)["rr"]
        factor = max(RENT_SCALE_MIN, min(RENT_SCALE_MAX, rents))
        base = [bd.round_half_up(p * factor) for p in base]
        coverage = "area" if coverage == "state" else coverage
    return base, coverage


def estimate(state: Optional[str], area_label: Optional[str], n_children: int = 1,
             renormalize: bool = True, weights: Optional[List[float]] = None) -> Estimate:
    """Typical yearly childcare cost per child (and for ``n_children``), 2026 dollars,
    for a child in their first five years.

    ``state`` is a two-letter code (or None), ``area_label`` one of the 739 area labels
    (or None). ``renormalize=False`` reads BEA rents the way BPM does (raw index / 100).
    ``weights`` replaces the time-in-tier weights (``bpm_weights`` gives BPM's).
    """
    c = bd.constants()
    base, coverage = _prices(state, area_label, renormalize)
    prices = [bd.round_half_up(p * c["CPI_MULT"]) for p in base]       # 2022 -> 2025
    w = list(TIME_IN_TIER if weights is None else weights)
    per_child = sum(prices[t] * w[t] for t in range(4))
    cpi26 = c["CPI_CC_2025_2026"]                                       # 2025 -> 2026
    annual = bd.round_half_up(bd.round_half_up(per_child * max(0, n_children)) * cpi26)
    return Estimate(bd.round_half_up(per_child * cpi26), annual, coverage, list(base), w)


def for_household(overrides: dict) -> Optional[Tuple[Estimate, str]]:
    """The suggestion for the plan's place and where it applies, in words. None when the
    plan has no children. The figure does not depend on the parents or the household."""
    try:
        from utils import state_choice as sc
    except ImportError:  # pragma: no cover
        from ui.utils import state_choice as sc  # type: ignore
    if not cfg.children_in(overrides):
        return None
    state, label = bd.state_code(overrides), bd.picked_area(overrides)
    where = label or (sc.label_for(state) if state else "the US")
    return estimate(state, label), where
