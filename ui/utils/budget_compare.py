"""Your spending against similar households, by BiggerPockets Money's method.

BPM's method (Household Spending Comparison v2.4.0; credits in docs/DATA_SOURCES.md).
For each BLS Consumer Expenditure (CE) 2025 group the benchmark is

    CE mean for your income fifth
      x (1 + DAMP x (size ratio  - 1))      CE Table 1400, your household size
      x (1 + DAMP x (age ratio   - 1))      CE Table 1300, your age band
      x BEA price level of the area         (a price index per group, US = 1.00)
      x CPI factor, 2025 to 2026

with the dampening DAMP = 0.5 (BPM's choice: income already tracks size and age, so the
full ratios would count them twice). Two groups are special when an area is known:
Housing is HUD's Fair Market Rent for the bedrooms your household needs, times a
rent-by-income factor, and Utilities keeps only the phone and internet share (HUD's gross
rent already holds power, gas and water). Without an area the CE housing line is used.

What the app adds, and BPM does not:
* CE "Pensions" (payroll tax, retirement contributions, life insurance) is left out. The
  planner models those elsewhere.
* The CE groups are folded into the app's spending categories, see ``ROWS``.
* The income fifth comes from your household pay, with rough cutoffs (``QUINTILE_UPPER``).

A statistical average of what similar households spend, not a target and not advice.
Pure functions, no Streamlit.
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Tuple

from retirement_sim import config as cfg

try:
    from utils import budget_data as bd
    from utils import childcare_cost as ccost
    from utils.coerce import safe_int
    from utils.derived import compute_total_income, children_at_home_now
    from utils.expense_categories import CATEGORIES, HOUSING_KEYS, PARTNER
except ImportError:  # pragma: no cover
    from ui.utils import budget_data as bd  # type: ignore
    from ui.utils import childcare_cost as ccost  # type: ignore
    from ui.utils.coerce import safe_int  # type: ignore
    from ui.utils.derived import compute_total_income, children_at_home_now  # type: ignore
    from ui.utils.expense_categories import CATEGORIES, HOUSING_KEYS, PARTNER  # type: ignore

BAND = 0.10                       # the "typical" range: within 10% of the benchmark
QUINTILES = ("Q1", "Q2", "Q3", "Q4", "Q5")
QUINTILE_LABELS = {"Q1": "Bottom 20%", "Q2": "Second 20%", "Q3": "Middle 20%",
                   "Q4": "Fourth 20%", "Q5": "Top 20%"}

# Top of each income fifth (US households, before tax, 2025 dollars). ROUGH: only the
# first, $32,623, comes from BPM's data (the CE's published bottom-fifth ceiling). The
# others are round estimates and are NOT in the BPM files. Replace them with the CE
# Table 1101 income cutoffs when you have them. The page lets you pick the group by hand.
QUINTILE_UPPER = (32_623, 61_000, 98_000, 158_000)

# CPI factor that BPM uses for all-items (located Utilities, whose line is the phone share).
CPI_ALL_ITEMS = 1.0462

# Spending groups on screen: (label, CE groups it adds up, app expense categories it compares).
HOUSING_UTILITIES = "Housing and utilities"
ROWS: Tuple[Tuple[str, Tuple[str, ...], Tuple[str, ...]], ...] = (
    (HOUSING_UTILITIES, ("Housing", "Utilities"), ("Housing", "Utilities")),
    ("Food & groceries", ("Food",), ("Food & groceries",)),
    ("Transportation", ("Transportation",), ("Transportation",)),
    ("Healthcare premiums", ("Healthcare",), ("Healthcare premiums",)),
    # Apparel has no line of its own in the app: shopping sits under Fun and discretionary.
    ("Fun and discretionary", ("Entertainment", "Apparel"), ("Fun and discretionary",)),
    # The partner's own spending has no CE line, so it goes in with Other.
    ("Other", ("Other",), ("Other", PARTNER)),
)
NOTES = {
    HOUSING_UTILITIES: "Rent for a home sized to your household. Owners with a small or paid-off "
                       "mortgage often pay less.",
    "Healthcare premiums": "The CE line also holds out-of-pocket costs, so it runs above premiums alone.",
    "Fun and discretionary": "Includes the CE's clothing line.",
    "Other": "Includes your partner's own spending, if any.",
}
EXCLUDED = "Retirement contributions and payroll tax (the CE's Pensions line) are not compared."


def quintile_for(income: float) -> str:
    """Income fifth for a household's yearly pay. The rough cutoffs are QUINTILE_UPPER."""
    for q, top in zip(QUINTILES, QUINTILE_UPPER):
        if income <= top:
            return q
    return QUINTILES[-1]


def benchmark(quintile: str, size: str, age: str, state: Optional[str] = None,
              area_label: Optional[str] = None, inflate: bool = True,
              renormalize: bool = True) -> Dict[str, float]:
    """Yearly benchmark per CE group (Housing, Utilities, Transportation, Food, Healthcare,
    Entertainment, Apparel, Other, Pensions) in 2026 dollars when ``inflate``.

    ``size`` is "1".."5+", ``age`` a band from ``childcare_cost.AGE_BANDS``. The place is
    the area, else the state's statewide row, else the US with no local adjustment.
    ``renormalize=False`` reads BEA the way BPM does, for checking against its tool.
    """
    x, damp = bd.ce_xtab(), bd.ce_xtab()["DAMP"]
    cpi, k = bd.cpi_factors(), bd.constants()
    loc = bd.area(area_label) or bd.statewide(state)
    p = bd.price_levels(loc, renormalize)
    local_price = {"Transportation": p["rg"], "Healthcare": p["rs"], "Entertainment": p["rs"],
                   "Apparel": p["rg"]}
    out: Dict[str, float] = {}
    for cat, base in x["Q"][quintile].items():
        v = base * (1 + damp * (x["S"][cat][size] - 1)) * (1 + damp * (x["A"][cat][age] - 1))
        if cat == "Housing" and loc:
            bedrooms = k["SIZE_BR"][size]
            rent = loc.get(f"f{bedrooms}", loc["f2"])
            mult = k["HOUSING_INC_MULT"][quintile]
            v = (rent if mult == 1 else bd.round_half_up(rent * mult / 50) * 50) * 12
            out[cat] = v
            continue                              # HUD rents are current: no CPI leg
        if cat == "Housing":
            v *= p["rr"]
        elif cat == "Food":
            v *= p["rg"]
        elif cat == "Utilities":
            if loc:
                v *= k["UTIL_TELECOM_SHARE"][quintile]
            v *= p["ra"]
        elif cat == "Other":
            v *= p["ra"]
        elif cat != "Pensions":
            v *= local_price[cat]
        if inflate:
            v *= CPI_ALL_ITEMS if (cat == "Utilities" and loc) else cpi[cat]
        out[cat] = v
    return out


class Household(NamedTuple):
    size: int
    age: int
    income: int
    auto_quintile: str
    state: Optional[str]         # two-letter code, or None when the plan has no single state
    area: Optional[str]          # one of the 739 area labels, or None


def household(overrides: dict) -> Household:
    """The household the benchmark describes, read from the plan: you, a partner, and the
    children at home now; your age; your pay; your state and the area you picked."""
    partner = safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0
    size = 1 + int(partner) + len(children_at_home_now(overrides))
    return Household(size=size,
                     age=safe_int(overrides.get("YOUR_AGE", cfg.YOUR_AGE), cfg.YOUR_AGE),
                     income=compute_total_income(overrides),
                     auto_quintile=quintile_for(compute_total_income(overrides))
                     if compute_total_income(overrides) > 0 else "Q3",
                     state=bd.state_code(overrides),
                     area=bd.picked_area(overrides))


class Row(NamedTuple):
    label: str
    you: float                 # $ a month
    typical: float             # $ a month
    low: float
    high: float
    verdict: str               # "below" | "in range" | "above" | "" (no figure of yours)
    note: str


def _plan_value(overrides: dict, label: str) -> float:
    if label == "Housing":
        vals = [float(overrides.get(k, 0) or 0) for k in HOUSING_KEYS]
        return next((v for v in vals if v > 0), 0.0)
    key = next(c.key for c in CATEGORIES if c.label == label)
    return float(overrides.get(key, 0) or 0)


def spending_rows(overrides: dict, quintile: Optional[str] = None,
                  yours: Optional[Dict[str, float]] = None) -> Tuple[List[Row], Household]:
    """The comparison table: one row per ``ROWS`` group and a last "Total" row.

    ``yours`` maps an expense label (a ``CATEGORIES`` label or "Housing") to $ a month and
    replaces the plan's own figure for it, for example your statements' averages.
    """
    h = household(overrides)
    q = quintile if quintile in QUINTILES else h.auto_quintile
    bench = benchmark(q, ccost.size_key(h.size), ccost.age_band(h.age), h.state, h.area)
    has_partner = safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0
    rows: List[Row] = []
    tot_you = tot_typ = 0.0
    for label, ce_groups, mine in ROWS:
        typical = sum(bench[g] for g in ce_groups) / 12
        you = 0.0
        for name in mine:
            if name == PARTNER and not has_partner:
                continue
            you += (yours or {}).get(name, _plan_value(overrides, name))
        rows.append(_row(label, you, typical))
        tot_you += you
        tot_typ += typical
    rows.append(_row("Total", tot_you, tot_typ))
    return rows, h


def _row(label: str, you: float, typical: float) -> Row:
    low, high = typical * (1 - BAND), typical * (1 + BAND)
    verdict = "below" if you < low else "above" if you > high else "in range"
    return Row(label, you, typical, low, high, verdict, NOTES.get(label, ""))


class Checkup(NamedTuple):
    typical: float       # $ a month, similar households at US average prices
    you: float           # $ a month, your needs plus wants
    group: str           # the income group, in words


def checkup_compare(inputs: dict) -> Optional[Checkup]:
    """The Money check-up's one-line comparison, from its few answers (pay, age, married).
    It has no area or children, so it uses US average prices and a household of one or two.
    None when it has no pay or no age."""
    married = bool(inputs.get("married"))
    gross = float(inputs.get("gross_salary_annual") or 0)
    gross += float(inputs.get("partner_salary_annual") or 0) if married else 0.0
    age = int(inputs.get("age") or 0)
    if gross <= 0 or age <= 0:
        return None
    q = quintile_for(gross)
    bench = benchmark(q, ccost.size_key(1 + int(married)), ccost.age_band(age))
    typical = (sum(bench.values()) - bench["Pensions"]) / 12
    you = float(inputs.get("needs_monthly") or 0) + float(inputs.get("wants_monthly") or 0)
    return Checkup(typical, you, QUINTILE_LABELS[q].lower())
