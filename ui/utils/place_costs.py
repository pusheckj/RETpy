"""What things cost in each area: the data behind Freedom milestones' places.

SOURCED DATA, in today's dollars, checked in November 2026 (full row-by-row
sources and caveats: docs/data_sources/2026_verification.md):

* Price levels by kind of spending (goods, services other than housing, utilities):
  US Bureau of Economic Analysis Regional Price Parities (RPP), 2024 (the latest
  published), renormalized so each US component is exactly 1.00. State rows are
  BEA state RPPs; metro rows are BEA metro-area RPPs.
* Health: KFF 2026 benchmark (second-lowest Silver) marketplace premium for a
  40-year-old, as a ratio to the US benchmark. Metros use their state's ratio.
  The engine prices it (config.pre_medicare_health_quote) at this ratio, with the
  plan's own age curve and subsidy, so only the price level comes from here.
* Home price: Zillow Home Value Index (ZHVI), September 2026 for states and
  October 2026 for the US and metros. Rent: Zillow single-family Observed Rent
  Index (ZORI), October 2026, for the US and metros. There is no state ZORI, so
  a state's rent is MODELED as the mean of its metros' ZORI x 1.172.
* Carry (property tax + homeowners insurance, a share of the price each year): the
  property tax a NEW buyer pays (assessment caps reset on a sale, so Proposition
  13 states are about 1.15%, not the average owner's 0.70%) plus Insurance.com 2026
  insurance on a 300,000 dwelling. Flood cover is not included.
* Abroad: Numbeo estimates from November 2026 (not BEA-comparable), converted with
  the ECB reference rates of 13 November 2026. Health there is a local private
  plan as a ratio to the US benchmark.

Caveats worth knowing:
* The San Francisco Bay Area row is a COMPUTED blend (population-weighted) of two
  BEA metros, not a BEA figure. Honolulu's rent is a June 2026 anchor.
* State rents are modeled (above) and understate rent in the big-city states
  (CA, NY, WA).
* Abroad health ratios use roughly age-40 premiums, so they UNDERSTATE the cost
  at 60 and over. Lisbon's price is the municipality (Greater Lisbon is about a
  third cheaper); Merida's price is a house (a 90 sqm apartment is about 195,000).
* Vermont, West Virginia, Wyoming and Alaska health ratios are high (1.6 to 2.1:
  few insurers, small risk pools). Vermont's premiums do not vary with age, so its
  ratio overstates the cost at 60 against age-rated states.
* The index rows are estimates of a typical household. Edit a place's price,
  rent or adjustment to match your own search.

Carry vs the plan's own housing cost: ``carry`` is the rate on a home you BUY in
that area (milestones place_cost and the HOME_EVENTS ``carrying_pct`` the
Confirm run uses). It already includes insurance, as the plan's
HOME_CARRYING_COST_PCT (default 0.0135, property tax + insurance) does, and the
new home REPLACES the housing term of the plan (the old home's payment, tax and
insurance are dropped, see milestones.place_cost), so insurance is not counted
twice. Renters pay no carry. Everyday categories scale only goods, services,
utilities and health, never housing.

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
    ("AL", "Alabama", 0.968, 0.966, 0.860, 1.032, 238_600, 1_570, 0.0161),
    ("AK", "Alaska", 1.067, 1.021, 1.209, 1.651, 397_900, 2_410, 0.0144),
    ("AZ", "Arizona", 0.958, 1.027, 0.938, 0.851, 416_700, 1_960, 0.0128),
    ("AR", "Arkansas", 0.940, 0.952, 0.759, 1.238, 224_200, 1_340, 0.0174),
    ("CA", "California", 1.065, 1.025, 1.615, 0.912, 761_500, 2_720, 0.0170),
    ("CO", "Colorado", 0.991, 0.995, 0.864, 0.891, 529_000, 2_450, 0.0234),
    ("CT", "Connecticut", 0.977, 1.026, 1.489, 1.392, 447_300, 2_560, 0.0225),
    ("DE", "Delaware", 0.966, 1.011, 1.055, 1.106, 405_100, 2_180, 0.0103),
    ("DC", "District of Columbia", 1.069, 1.029, 1.146, 0.976, 567_300, 2_910, 0.0125),
    ("FL", "Florida", 0.985, 1.012, 0.916, 1.093, 375_400, 2_240, 0.0422),
    ("GA", "Georgia", 0.993, 0.972, 0.943, 0.984, 329_100, 1_710, 0.0156),
    ("HI", "Hawaii", 1.121, 1.028, 1.933, 0.866, 832_900, 3_880, 0.0055),
    ("ID", "Idaho", 0.967, 0.989, 0.715, 0.784, 476_800, 1_860, 0.0130),
    ("IL", "Illinois", 1.042, 1.001, 0.864, 1.034, 295_900, 1_330, 0.0281),
    ("IN", "Indiana", 0.959, 0.990, 0.869, 0.758, 257_200, 1_360, 0.0172),
    ("IA", "Iowa", 0.941, 0.928, 0.847, 0.802, 236_600, 1_340, 0.0238),
    ("KS", "Kansas", 0.944, 0.937, 0.898, 1.072, 246_100, 1_220, 0.0297),
    ("KY", "Kentucky", 0.964, 0.972, 0.765, 0.944, 230_900, 1_380, 0.0223),
    ("LA", "Louisiana", 0.941, 0.956, 0.727, 1.034, 213_900, 1_640, 0.0228),
    ("ME", "Maine", 0.976, 1.031, 1.374, 1.134, 412_000, 2_020, 0.0141),
    ("MD", "Maryland", 1.029, 1.015, 1.127, 0.662, 424_900, 2_070, 0.0185),
    ("MA", "Massachusetts", 0.992, 1.028, 1.546, 0.790, 655_200, 2_670, 0.0170),
    ("MI", "Michigan", 0.964, 1.008, 1.018, 0.837, 263_800, 1_580, 0.0280),
    ("MN", "Minnesota", 1.009, 1.001, 0.923, 0.717, 348_800, 1_480, 0.0211),
    ("MS", "Mississippi", 0.966, 0.960, 0.797, 1.059, 194_500, 1_680, 0.0145),
    ("MO", "Missouri", 0.967, 0.951, 0.807, 0.968, 265_400, 1_320, 0.0215),
    ("MT", "Montana", 0.964, 0.986, 0.735, 1.107, 467_300, 1_970, 0.0162),
    ("NE", "Nebraska", 0.945, 0.929, 0.768, 1.136, 278_300, 1_480, 0.0328),
    ("NV", "Nevada", 0.967, 0.986, 0.920, 0.795, 440_700, 2_250, 0.0113),
    ("NH", "New Hampshire", 0.990, 1.038, 1.359, 0.642, 510_900, 2_220, 0.0194),
    ("NJ", "New Jersey", 1.075, 1.034, 1.161, 0.872, 575_100, 2_400, 0.0236),
    ("NM", "New Mexico", 0.965, 0.984, 0.792, 0.997, 315_800, 1_860, 0.0212),
    ("NY", "New York", 1.077, 1.040, 1.366, 1.307, 524_900, 1_860, 0.0191),
    ("NC", "North Carolina", 0.970, 0.981, 0.900, 1.021, 332_200, 1_750, 0.0193),
    ("ND", "North Dakota", 0.961, 0.911, 0.749, 0.912, 290_700, 1_350, 0.0187),
    ("OH", "Ohio", 0.941, 0.988, 0.974, 0.821, 246_000, 1_400, 0.0206),
    ("OK", "Oklahoma", 0.942, 0.954, 0.751, 0.966, 220_800, 1_350, 0.0274),
    ("OR", "Oregon", 1.057, 1.002, 1.087, 0.869, 492_800, 2_030, 0.0136),
    ("PA", "Pennsylvania", 0.998, 0.997, 1.111, 0.915, 287_100, 1_530, 0.0174),
    ("RI", "Rhode Island", 0.976, 1.027, 1.491, 0.810, 508_500, 2_540, 0.0191),
    ("SC", "South Carolina", 0.967, 0.982, 0.897, 0.902, 304_300, 1_790, 0.0155),
    ("SD", "South Dakota", 0.959, 0.918, 0.810, 1.048, 317_900, 1_480, 0.0225),
    ("TN", "Tennessee", 0.966, 0.950, 0.733, 1.138, 330_800, 1_610, 0.0159),
    ("TX", "Texas", 0.985, 0.970, 0.889, 1.058, 296_400, 1_630, 0.0303),
    ("UT", "Utah", 0.968, 0.989, 0.800, 1.024, 532_900, 1_960, 0.0107),
    ("VT", "Vermont", 0.977, 1.015, 1.278, 2.078, 391_900, 2_240, 0.0185),
    ("VA", "Virginia", 1.008, 1.001, 0.937, 0.728, 412_300, 1_820, 0.0143),
    ("WA", "Washington", 1.048, 1.038, 0.944, 0.979, 587_500, 2_050, 0.0134),
    ("WV", "West Virginia", 0.969, 0.998, 0.937, 1.717, 176_600, 1_340, 0.0116),
    ("WI", "Wisconsin", 0.947, 0.994, 0.914, 0.978, 337_200, 1_520, 0.0193),
    ("WY", "Wyoming", 0.958, 1.003, 0.797, 1.744, 369_000, 1_860, 0.0122),
)

# Big metro areas, mostly high-cost ones. The last field is the state whose
# income tax applies.
_METROS = (
    # computed blend of the SF and San Jose BEA metros, not BEA-published
    ("M_SFB", "San Francisco Bay Area", 1.079, 1.043, 1.706, 0.912, 1_255_000, 4_360, 0.0170, "CA"),
    ("M_LAX", "Los Angeles area", 1.070, 1.043, 1.612, 0.912, 950_800, 4_420, 0.0173, "CA"),
    ("M_SAN", "San Diego area", 1.084, 0.995, 1.770, 0.912, 929_000, 4_140, 0.0170, "CA"),
    ("M_SEA", "Seattle area", 1.044, 1.067, 0.943, 0.979, 711_400, 3_350, 0.0134, "WA"),
    ("M_PDX", "Portland (Oregon) area", 1.056, 1.000, 1.087, 0.869, 535_600, 2_660, 0.0136, "OR"),
    # carry estimated (multi-jurisdiction)
    ("M_NYC", "New York City area", 1.107, 1.057, 1.291, 1.307, 730_900, 3_490, 0.0156, "NY"),
    ("M_BOS", "Boston area", 1.001, 1.035, 1.512, 0.790, 726_300, 3_500, 0.0121, "MA"),
    # carry: mean of DC, VA and MD; health is DC's (VA, MD suburbs cost less)
    ("M_WDC", "Washington, DC area", 1.052, 1.022, 1.084, 0.976, 568_200, 3_160, 0.0151, "DC"),
    ("M_PHL", "Philadelphia area", 0.972, 1.030, 1.163, 0.915, 385_600, 2_260, 0.0174, "PA"),
    ("M_DEN", "Denver area", 1.014, 0.993, 0.893, 0.891, 552_100, 2_880, 0.0234, "CO"),
    ("M_AUS", "Austin area", 0.942, 0.961, 0.833, 1.058, 410_000, 2_260, 0.0303, "TX"),
    ("M_DFW", "Dallas-Fort Worth area", 1.032, 0.996, 0.922, 1.058, 355_900, 2_320, 0.0303, "TX"),
    ("M_HOU", "Houston area", 1.010, 0.955, 0.969, 1.058, 300_800, 2_190, 0.0303, "TX"),
    ("M_CHI", "Chicago area", 1.077, 1.004, 0.850, 1.034, 357_700, 2_510, 0.0281, "IL"),
    ("M_MSP", "Minneapolis-St. Paul area", 1.035, 1.043, 0.950, 0.717, 384_900, 2_460, 0.0211, "MN"),
    ("M_ATL", "Atlanta area", 1.008, 0.966, 0.978, 0.984, 373_100, 2_250, 0.0156, "GA"),
    ("M_MIA", "Miami area", 1.040, 1.090, 0.988, 1.093, 480_100, 3_410, 0.0450, "FL"),
    ("M_PHX", "Phoenix area", 0.954, 1.039, 0.948, 0.851, 438_700, 2_290, 0.0128, "AZ"),
    # rent: June 2026 single-family anchor
    ("M_HNL", "Honolulu", 1.121, 1.028, 1.903, 0.866, 856_000, 3_630, 0.0055, "HI"),
)

# Abroad: prices against the US average, a comparable family home and rent in
# that kind of city, and local private health insurance as the health index.
_ABROAD = (
    ("X_PT", "Portugal (Lisbon area)", 0.615, 0.738, 0.700, 0.133, 621_500, 2_400, 0.0022),
    ("X_IT", "Italy (Bologna)", 0.794, 0.923, 1.050, 0.295, 381_400, 1_840, 0.0005),
    ("X_ES", "Spain (Valencia)", 0.577, 0.758, 0.750, 0.212, 346_300, 2_000, 0.0044),
    ("X_MX", "Mexico (Mérida)", 0.570, 0.620, 0.450, 0.360, 289_400, 1_100, 0.0033),
    ("X_TH", "Thailand (Chiang Mai)", 0.490, 0.342, 0.550, 0.118, 181_200, 850, 0.0080),
)


def _build() -> Dict[str, Area]:
    out: Dict[str, Area] = {US_CODE: Area(US_CODE, "US average", KIND_US, 1.0, 1.0, 1.0, 1.0,
                                          364_800, 2_240, 0.0201, "same")}
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
