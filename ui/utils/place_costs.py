"""What things cost in each area: the data behind Freedom milestones' places.

Every number here is a ROUGH, ILLUSTRATIVE ESTIMATE in today's dollars, typed in
from memory of published sources. It is not live data. Edit any row.

Source families (shape only; no figure is copied exactly):
* Price levels by kind of spending (US average = 1.00): the US Bureau of Economic
  Analysis Regional Price Parities (RPP), which split prices into goods, housing
  rents, utilities and other services, by state and by metro area.
* Health: how far a benchmark (second-lowest Silver) marketplace plan costs from
  the US average, in the style of KFF's yearly state tables.
* Home prices: a typical family home (Zillow Home Value Index style, mid-tier).
* Rent: a typical family-size rental (Zillow Observed Rent Index style, sized up
  for a 2-3 bedroom home).
* Carrying cost: property tax a NEW buyer pays (Tax Foundation style effective
  rates, adjusted for assessment caps such as California's) plus homeowners
  insurance, as a share of the price per year.
* Abroad: Numbeo-style cost-of-living, rent and price ratios against the US, and
  local private health insurance in place of a US marketplace plan.

How a row becomes spending (utils/milestones.py): each everyday category is
scaled by place index / home-area index, so only the DIFFERENCE between where
you live and where you go matters. Housing uses the place's own price or rent.
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Tuple


class Area(NamedTuple):
    code: str
    name: str
    kind: str          # "us" | "state" | "metro" | "abroad"
    goods: float       # price level of goods, US = 1.00
    services: float    # price level of services other than housing and utilities
    utilities: float   # power, heat, water
    health: float      # marketplace (or local private) health insurance
    price: int         # typical family home, $
    rent: int          # typical family-size rent, $ a month
    carry: float       # property tax + insurance a year, share of the price
    tax: str           # Freedom milestones tax setting ("US:XX" or "none")


KIND_US, KIND_STATE, KIND_METRO, KIND_ABROAD = "us", "state", "metro", "abroad"
US_CODE = "US"

# code, name, goods, services, utilities, health, home price, rent / month, carry
_STATES = (
    ("AL", "Alabama", 0.94, 0.90, 1.00, 1.00, 230_000, 1_450, 0.0090),
    ("AK", "Alaska", 1.05, 1.06, 1.35, 1.75, 370_000, 1_800, 0.0130),
    ("AZ", "Arizona", 0.98, 0.97, 1.00, 0.85, 430_000, 2_000, 0.0090),
    ("AR", "Arkansas", 0.93, 0.89, 0.95, 0.85, 210_000, 1_350, 0.0100),
    ("CA", "California", 1.06, 1.08, 1.30, 1.00, 780_000, 3_200, 0.0135),
    ("CO", "Colorado", 1.01, 1.02, 0.95, 0.85, 550_000, 2_400, 0.0080),
    ("CT", "Connecticut", 1.03, 1.05, 1.35, 1.10, 420_000, 2_500, 0.0200),
    ("DE", "Delaware", 1.00, 0.98, 1.05, 1.15, 380_000, 2_000, 0.0080),
    ("DC", "District of Columbia", 1.05, 1.10, 1.05, 0.85, 620_000, 3_000, 0.0090),
    ("FL", "Florida", 1.00, 1.00, 1.00, 1.05, 400_000, 2_500, 0.0190),
    ("GA", "Georgia", 0.97, 0.96, 1.00, 0.95, 330_000, 1_900, 0.0115),
    ("HI", "Hawaii", 1.10, 1.10, 2.10, 1.05, 850_000, 3_300, 0.0060),
    ("ID", "Idaho", 0.97, 0.95, 0.85, 0.95, 460_000, 2_000, 0.0080),
    ("IL", "Illinois", 1.00, 1.00, 0.95, 0.90, 270_000, 1_900, 0.0230),
    ("IN", "Indiana", 0.95, 0.92, 1.00, 0.95, 250_000, 1_500, 0.0110),
    ("IA", "Iowa", 0.94, 0.91, 0.95, 1.05, 225_000, 1_400, 0.0175),
    ("KS", "Kansas", 0.95, 0.92, 1.05, 1.10, 235_000, 1_450, 0.0170),
    ("KY", "Kentucky", 0.94, 0.91, 0.95, 1.00, 215_000, 1_400, 0.0110),
    ("LA", "Louisiana", 0.96, 0.92, 0.90, 1.25, 205_000, 1_450, 0.0170),
    ("ME", "Maine", 1.00, 0.98, 1.20, 1.15, 400_000, 2_000, 0.0135),
    ("MD", "Maryland", 1.02, 1.03, 1.10, 0.75, 430_000, 2_400, 0.0130),
    ("MA", "Massachusetts", 1.04, 1.07, 1.40, 0.90, 640_000, 3_100, 0.0130),
    ("MI", "Michigan", 0.96, 0.94, 1.10, 0.85, 245_000, 1_600, 0.0165),
    ("MN", "Minnesota", 0.98, 0.98, 1.00, 0.75, 340_000, 1_800, 0.0130),
    ("MS", "Mississippi", 0.93, 0.88, 1.00, 1.15, 185_000, 1_300, 0.0120),
    ("MO", "Missouri", 0.95, 0.92, 0.95, 1.05, 255_000, 1_450, 0.0120),
    ("MT", "Montana", 0.99, 0.96, 0.90, 1.10, 460_000, 1_900, 0.0100),
    ("NE", "Nebraska", 0.95, 0.93, 0.95, 1.30, 270_000, 1_550, 0.0180),
    ("NV", "Nevada", 1.00, 0.98, 1.00, 0.90, 440_000, 2_100, 0.0080),
    ("NH", "New Hampshire", 1.01, 1.02, 1.35, 0.75, 490_000, 2_500, 0.0200),
    ("NJ", "New Jersey", 1.03, 1.05, 1.15, 1.00, 550_000, 2_900, 0.0240),
    ("NM", "New Mexico", 0.96, 0.93, 0.95, 0.80, 300_000, 1_600, 0.0095),
    ("NY", "New York", 1.03, 1.05, 1.25, 1.15, 480_000, 2_400, 0.0180),
    ("NC", "North Carolina", 0.97, 0.95, 1.00, 1.15, 340_000, 1_850, 0.0095),
    ("ND", "North Dakota", 0.96, 0.93, 0.90, 1.10, 260_000, 1_300, 0.0120),
    ("OH", "Ohio", 0.95, 0.93, 1.00, 0.85, 235_000, 1_500, 0.0165),
    ("OK", "Oklahoma", 0.94, 0.90, 0.95, 1.05, 205_000, 1_400, 0.0175),
    ("OR", "Oregon", 1.01, 1.02, 0.95, 1.00, 500_000, 2_300, 0.0110),
    ("PA", "Pennsylvania", 0.98, 0.97, 1.05, 0.90, 265_000, 1_750, 0.0160),
    ("RI", "Rhode Island", 1.01, 1.02, 1.35, 0.80, 470_000, 2_500, 0.0150),
    ("SC", "South Carolina", 0.96, 0.93, 1.05, 1.00, 300_000, 1_750, 0.0090),
    ("SD", "South Dakota", 0.95, 0.92, 0.95, 1.30, 300_000, 1_450, 0.0140),
    ("TN", "Tennessee", 0.96, 0.93, 0.95, 1.05, 320_000, 1_800, 0.0085),
    ("TX", "Texas", 0.97, 0.96, 1.05, 0.95, 305_000, 2_000, 0.0230),
    ("UT", "Utah", 0.98, 0.96, 0.85, 0.90, 530_000, 2_100, 0.0075),
    ("VT", "Vermont", 1.02, 1.00, 1.15, 1.70, 400_000, 2_100, 0.0200),
    ("VA", "Virginia", 1.00, 1.00, 1.05, 0.90, 400_000, 2_200, 0.0105),
    ("WA", "Washington", 1.03, 1.04, 0.90, 0.95, 600_000, 2_600, 0.0110),
    ("WV", "West Virginia", 0.93, 0.89, 1.00, 1.60, 165_000, 1_250, 0.0080),
    ("WI", "Wisconsin", 0.96, 0.94, 1.00, 1.05, 300_000, 1_600, 0.0170),
    ("WY", "Wyoming", 0.97, 0.94, 0.95, 1.80, 340_000, 1_700, 0.0080),
)

# Big metro areas, mostly high-cost ones. The last field is the state whose
# income tax applies.
_METROS = (
    ("M_SFB", "San Francisco Bay Area", 1.10, 1.15, 1.35, 1.05, 1_300_000, 4_200, 0.0130, "CA"),
    ("M_LAX", "Los Angeles area", 1.07, 1.10, 1.25, 0.95, 950_000, 3_600, 0.0135, "CA"),
    ("M_SAN", "San Diego area", 1.07, 1.09, 1.45, 1.00, 950_000, 3_700, 0.0135, "CA"),
    ("M_SEA", "Seattle area", 1.06, 1.10, 0.95, 0.95, 800_000, 3_000, 0.0110, "WA"),
    ("M_PDX", "Portland (Oregon) area", 1.02, 1.04, 0.95, 1.00, 540_000, 2_300, 0.0115, "OR"),
    ("M_NYC", "New York City area", 1.08, 1.15, 1.30, 1.20, 700_000, 3_800, 0.0160, "NY"),
    ("M_BOS", "Boston area", 1.06, 1.12, 1.45, 0.90, 720_000, 3_400, 0.0125, "MA"),
    ("M_WDC", "Washington, DC area", 1.04, 1.09, 1.05, 0.85, 580_000, 2_900, 0.0105, "DC"),
    ("M_PHL", "Philadelphia area", 1.00, 1.02, 1.05, 0.90, 340_000, 2_100, 0.0150, "PA"),
    ("M_DEN", "Denver area", 1.02, 1.04, 0.95, 0.85, 600_000, 2_600, 0.0080, "CO"),
    ("M_AUS", "Austin area", 0.99, 1.00, 1.05, 0.95, 450_000, 2_200, 0.0220, "TX"),
    ("M_DFW", "Dallas-Fort Worth area", 0.98, 0.99, 1.05, 0.95, 380_000, 2_200, 0.0230, "TX"),
    ("M_HOU", "Houston area", 0.97, 0.98, 1.05, 0.95, 310_000, 2_000, 0.0240, "TX"),
    ("M_CHI", "Chicago area", 1.01, 1.04, 0.95, 0.90, 330_000, 2_300, 0.0230, "IL"),
    ("M_MSP", "Minneapolis-St. Paul area", 0.99, 1.00, 1.00, 0.75, 380_000, 2_000, 0.0130, "MN"),
    ("M_ATL", "Atlanta area", 0.98, 0.99, 1.00, 0.95, 390_000, 2_100, 0.0115, "GA"),
    ("M_MIA", "Miami area", 1.03, 1.06, 1.00, 1.10, 520_000, 3_200, 0.0220, "FL"),
    ("M_PHX", "Phoenix area", 0.99, 0.99, 1.00, 0.85, 440_000, 2_000, 0.0085, "AZ"),
    ("M_HNL", "Honolulu", 1.12, 1.12, 2.10, 1.05, 900_000, 3_500, 0.0055, "HI"),
)

# Abroad: prices against the US average, a comparable family home and rent in
# that kind of city, and local private health insurance as the health index.
_ABROAD = (
    ("X_PT", "Portugal (Lisbon area)", 0.80, 0.60, 0.75, 0.30, 480_000, 2_300, 0.0050),
    ("X_IT", "Italy (mid-size city)", 0.85, 0.70, 1.05, 0.30, 280_000, 1_200, 0.0040),
    ("X_ES", "Spain (mid-size coastal city)", 0.78, 0.60, 0.80, 0.30, 350_000, 1_500, 0.0050),
    ("X_MX", "Mexico (mid-size city)", 0.68, 0.42, 0.55, 0.25, 230_000, 1_100, 0.0030),
    ("X_TH", "Thailand (Chiang Mai)", 0.60, 0.35, 0.60, 0.20, 180_000, 750, 0.0020),
)


def _build() -> Dict[str, Area]:
    out: Dict[str, Area] = {US_CODE: Area(US_CODE, "US average", KIND_US, 1.0, 1.0, 1.0, 1.0,
                                          360_000, 2_100, 0.0130, "same")}
    for code, name, g, s, u, h, price, rent, carry in _STATES:
        out[code] = Area(code, name, KIND_STATE, g, s, u, h, price, rent, carry, "US:" + code)
    for code, name, g, s, u, h, price, rent, carry, st in _METROS:
        out[code] = Area(code, name, KIND_METRO, g, s, u, h, price, rent, carry, "US:" + st)
    for code, name, g, s, u, h, price, rent, carry in _ABROAD:
        out[code] = Area(code, name, KIND_ABROAD, g, s, u, h, price, rent, carry, "none")
    return out


AREAS: Dict[str, Area] = _build()

# ---------------------------------------------------------------- categories
# How each spending category is priced: weights on (goods, services, utilities,
# health). Food mixes groceries (goods) with dining out (services); driving is
# mostly goods (cars, fuel) with some services (repairs, insurance).
CAT_UTILITIES, CAT_FOOD, CAT_TRANSPORT, CAT_HEALTH, CAT_FUN, CAT_OTHER, CAT_PARTNER = (
    "utilities", "food", "transport", "health", "fun", "other", "partner")

_MIX: Dict[str, Tuple[float, float, float, float]] = {
    CAT_UTILITIES: (0.0, 0.0, 1.0, 0.0),
    CAT_FOOD: (0.7, 0.3, 0.0, 0.0),
    CAT_TRANSPORT: (0.8, 0.2, 0.0, 0.0),
    CAT_HEALTH: (0.0, 0.0, 0.0, 1.0),
    CAT_FUN: (0.5, 0.5, 0.0, 0.0),
    CAT_OTHER: (0.0, 1.0, 0.0, 0.0),
    CAT_PARTNER: (0.5, 0.5, 0.0, 0.0),
}
CATEGORIES: Tuple[str, ...] = tuple(_MIX)

# Config keys (ui/utils/expense_categories.py) -> category.
CONFIG_KEYS: Dict[str, str] = {
    "SPEND_UTILITIES_MONTHLY": CAT_UTILITIES,
    "SPEND_FOOD_MONTHLY": CAT_FOOD,
    "SPEND_TRANSPORT_MONTHLY": CAT_TRANSPORT,
    "SPEND_HEALTH_MONTHLY": CAT_HEALTH,
    "SPEND_DISCRETIONARY_MONTHLY": CAT_FUN,
    "SPEND_OTHER_MONTHLY": CAT_OTHER,
    "PARTNER_OTHER_MONTHLY": CAT_PARTNER,
}

LABELS: Dict[str, str] = {
    CAT_UTILITIES: "Utilities",
    CAT_FOOD: "Food & groceries",
    CAT_TRANSPORT: "Transportation",
    CAT_HEALTH: "Healthcare premiums",
    CAT_FUN: "Fun and discretionary",
    CAT_OTHER: "Other",
    CAT_PARTNER: "Partner spending",
}


def get(code: Optional[str]) -> Area:
    """The area for ``code``; the US average when it is unknown."""
    return AREAS.get(str(code or ""), AREAS[US_CODE])


def known(code) -> bool:
    return str(code or "") in AREAS


def index(area: Area, category: str) -> float:
    """Price level of ``category`` in ``area`` (US average = 1.00)."""
    g, s, u, h = _MIX[category]
    return g * area.goods + s * area.services + u * area.utilities + h * area.health


def ratio(place: str, home: str, category: str) -> float:
    """How much more (or less) ``category`` costs in ``place`` than in ``home``."""
    base = index(get(home), category)
    return index(get(place), category) / base if base > 0 else 1.0


def ratios(place: str, home: str) -> Dict[str, float]:
    return {c: ratio(place, home, c) for c in CATEGORIES}


def default_home(state_choice) -> str:
    """Where you live now, from the plan's state (a two-letter code), else the US average."""
    code = str(state_choice or "").strip().upper()
    return code if code in AREAS and AREAS[code].kind == KIND_STATE else US_CODE


def home_options() -> List[str]:
    """Codes you can pick for where you live now: the US average, states, then metros."""
    states = sorted((a for a in AREAS.values() if a.kind == KIND_STATE), key=lambda a: a.name)
    metros = sorted((a for a in AREAS.values() if a.kind == KIND_METRO), key=lambda a: a.name)
    return [US_CODE] + [a.code for a in states] + [a.code for a in metros]


def place_options() -> List[str]:
    """Codes a place can be based on: everything you can live in now, then abroad."""
    abroad = sorted((a for a in AREAS.values() if a.kind == KIND_ABROAD), key=lambda a: a.name)
    return home_options() + [a.code for a in abroad]


def label(code) -> str:
    """Name for a picker, with the kind when it helps tell rows apart."""
    a = get(code)
    if a.kind == KIND_METRO:
        return f"{a.name} (metro)"
    if a.kind == KIND_ABROAD:
        return f"{a.name} (abroad)"
    return a.name
