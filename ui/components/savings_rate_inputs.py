"""Savings — direct annual contribution amounts per account.

.. warning::
   **This module is HALF LIVE — do not delete it.** Its ``render()`` /
   ``render_body()`` UI is superseded by ``sec_savings.py`` and is no longer
   called from ``app.py``, but ``components/savings_projection_chart.py``
   imports ``project_savings``, ``ALLOCATION_ORDER`` and
   ``get_allocation_colors`` from here. Safe cleanup = drop only the unused
   ``render``/``render_body`` functions, or move the helpers into ``utils/``.

Simple model: the user enters how much goes into each account each year.
The simulator caps these at IRS limits internally; the projection chart
extends them forward year by year with optional inflation scaling.

Storage keys (all integers, in user_overrides):
  YOUR_401K_CONTRIBUTION
  YOUR_HSA_CONTRIBUTION
  YOUR_BACKDOOR_ROTH
  YOUR_BROKERAGE_CONTRIBUTION
  PARTNER_401K_CONTRIBUTION
  PARTNER_ROTH_CONTRIBUTION
  PARTNER_BROKERAGE_CONTRIBUTION
  SAVINGS_INFLATION_ADJUST       bool — scale all amounts forward at inflation

The "Your 401(k) match" is auto-derived from primary salary × match% and
shown in the projection chart as a bonus on top of the user's contributions.
"""
from __future__ import annotations

try:
    from utils.coerce import safe_int, safe_float, ensure_default
    from utils.formatting import money
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money  # type: ignore

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore

try:
    from utils.plot_theme import series_color
except ImportError:  # pragma: no cover
    from ui.utils.plot_theme import series_color  # type: ignore


# Visualization order + colors. Keys here are stable labels used by the
# projection chart so it doesn't depend on override-key naming.
ALLOCATION_ORDER = [
    ("Your 401(k)",          "YOUR_401K_CONTRIBUTION",          "you"),
    ("Your 401(k) match",    "YOUR_401K_MATCH_DERIVED",         "you"),
    ("Your HSA",             "YOUR_HSA_CONTRIBUTION",           "you"),
    ("Your Roth (backdoor)", "YOUR_BACKDOOR_ROTH",              "you"),
    ("Your brokerage",       "YOUR_BROKERAGE_CONTRIBUTION",     "you"),
    ("Partner 401(k)",       "PARTNER_401K_CONTRIBUTION",       "partner"),
    ("Partner Roth IRA",     "PARTNER_ROTH_CONTRIBUTION",       "partner"),
    ("Partner brokerage",    "PARTNER_BROKERAGE_CONTRIBUTION",  "partner"),
]

def get_allocation_colors(st) -> dict:
    """Map each account to an active-palette color by its index in ALLOCATION_ORDER,
    so allocation colors follow the user's palette and stay consistent with the
    projection chart. Read at render time so it reacts to the palette picker.
    """
    return {label: series_color(i, st) for i, (label, _, _) in enumerate(ALLOCATION_ORDER)}


def _allocation_for_year(user_overrides: dict, age_offset: int) -> dict:
    """Per-account dollar amounts for a given offset year (0 = today)."""
    inflation_adjust = bool(user_overrides.get("SAVINGS_INFLATION_ADJUST", True))
    inflation = 0.0275
    growth_factor = (1 + inflation) ** age_offset if inflation_adjust else 1.0

    your_401k    = safe_int(user_overrides.get("YOUR_401K_CONTRIBUTION", 0), 0) * growth_factor
    your_hsa     = safe_int(user_overrides.get("YOUR_HSA_CONTRIBUTION", 0), 0) * growth_factor
    your_roth    = safe_int(user_overrides.get("YOUR_BACKDOOR_ROTH", 0), 0) * growth_factor
    your_brk     = safe_int(user_overrides.get("YOUR_BROKERAGE_CONTRIBUTION", 0), 0) * growth_factor
    partner_401k = safe_int(user_overrides.get("PARTNER_401K_CONTRIBUTION", 0), 0) * growth_factor
    partner_roth = safe_int(user_overrides.get("PARTNER_ROTH_CONTRIBUTION", 0), 0) * growth_factor
    partner_brk  = safe_int(user_overrides.get("PARTNER_BROKERAGE_CONTRIBUTION", 0), 0) * growth_factor

    # Employer match — derived from primary salary × match%
    income = safe_int(user_overrides.get("HOUSEHOLD_INCOME_QUICK", 85_000), 85_000)
    salary_growth = safe_float(user_overrides.get("YOUR_SALARY_GROWTH_RATE", 0.02), 0.02)
    primary_share = 0.55  # rough split of household income to primary earner
    primary_salary = income * primary_share * ((1 + salary_growth) ** age_offset)
    match_pct = safe_float(user_overrides.get("YOUR_401K_MATCH_PCT", 0.04), 0.04)
    your_match = primary_salary * match_pct

    return {
        "Your 401(k)":          your_401k,
        "Your 401(k) match":    your_match,
        "Your HSA":             your_hsa,
        "Your Roth (backdoor)": your_roth,
        "Your brokerage":       your_brk,
        "Partner 401(k)":       partner_401k,
        "Partner Roth IRA":     partner_roth,
        "Partner brokerage":    partner_brk,
    }


def project_savings(
    user_overrides: dict,
    start_age: int,
    retirement_age: int,
    inflation_rate: float = 0.0275,  # signature-compat
    salary_growth_rate: float = 0.02,
) -> list:
    """Per-year savings projection: [{age, annual, cumulative, by_account}, ...]"""
    rows = []
    cumulative = 0.0
    # Contributions happen in WORKING years only: current age through the year
    # BEFORE retirement (the engine accumulates for ages < retirement_age, then
    # switches to decumulation). Excluding the retirement year keeps this chart
    # aligned with the "Savings contributions" chart, which uses the same range.
    for offset in range(max(0, retirement_age - start_age)):
        age = start_age + offset
        breakdown = _allocation_for_year(user_overrides, offset)
        annual = sum(breakdown.values())
        cumulative += annual
        rows.append({
            "age": age,
            "annual": annual,
            "cumulative": cumulative,
            "by_account": breakdown,
        })
    return rows


def _account_input(st, label: str, widget_key: str, override_key: str,
                   default: int, max_value: int, step: int, help_text: str = "") -> None:
    """Render one number_input that writes to user_overrides."""
    ensure_default(st, widget_key, safe_int(get_override(st, override_key, default), default))
    v = st.number_input(
        label,
        min_value=0,
        max_value=max_value,
        step=step,
        key=widget_key,
        help=help_text or None,
    )
    set_override(st, override_key, safe_int(v))


def render_body(st) -> None:
    """Render the inputs WITHOUT the outer expander."""
    st.caption(
        "How much you'll add to each account this year — **annual amounts** in today's dollars. "
        "The simulator caps each at the IRS limit automatically."
    )

    st.markdown("**You**")
    col1, col2 = st.columns(2)
    with col1:
        _account_input(st, "401(k) ($/yr)", "sr_your_401k",
                       "YOUR_401K_CONTRIBUTION", 2_700, 30_000, 500,
                       "2024 IRS limit: $23,000 (under 50); $7,500 catch-up at 50+.")
        _account_input(st, "HSA ($/yr)", "sr_your_hsa",
                       "YOUR_HSA_CONTRIBUTION", 0, 10_000, 250,
                       "2024 family HSA limit: $8,300. Triple tax-advantaged.")
        _account_input(st, "Roth IRA / backdoor ($/yr)", "sr_your_roth",
                       "YOUR_BACKDOOR_ROTH", 0, 10_000, 500,
                       "2024 IRA limit: $7,000. Use backdoor if income exceeds the Roth phase-out.")
    with col2:
        _account_input(st, "Taxable brokerage ($/yr)", "sr_your_brk",
                       "YOUR_BROKERAGE_CONTRIBUTION", 0, 500_000, 1_000,
                       "After-tax savings in a regular brokerage account.")

    st.markdown("**Partner**")
    col3, col4 = st.columns(2)
    with col3:
        _account_input(st, "Partner 401(k) ($/yr)", "sr_partner_401k",
                       "PARTNER_401K_CONTRIBUTION", 2_500, 30_000, 500)
        _account_input(st, "Partner Roth IRA ($/yr)", "sr_partner_roth",
                       "PARTNER_ROTH_CONTRIBUTION", 0, 10_000, 500)
    with col4:
        _account_input(st, "Partner brokerage ($/yr)", "sr_partner_brk",
                       "PARTNER_BROKERAGE_CONTRIBUTION", 0, 500_000, 1_000)

    # Inflation toggle
    ensure_default(st, "sr_inflation_adjust",
                   bool(get_override(st, "SAVINGS_INFLATION_ADJUST", True)))
    inflation_adjust = st.toggle(
        "Grow contributions with inflation (~2.75%/yr)",
        key="sr_inflation_adjust",
        help="When on, the amounts above scale up each year so real "
             "purchasing power stays constant. IRS limits also rise with inflation.",
    )
    set_override(st, "SAVINGS_INFLATION_ADJUST", bool(inflation_adjust))

    # Live total
    overrides = st.session_state.get("user_overrides", {}) or {}
    breakdown = _allocation_for_year(overrides, age_offset=0)
    user_total = sum(v for k, v in breakdown.items() if k != "Your 401(k) match")
    employer_match = breakdown["Your 401(k) match"]
    grand_total = user_total + employer_match

    income = safe_int(overrides.get("HOUSEHOLD_INCOME_QUICK", 85_000), 85_000)
    rate_pct = (user_total / income * 100.0) if income > 0 else 0.0

    cols = st.columns(3)
    with cols[0]:
        st.metric("Your contributions", money(user_total, shorten=True))
    with cols[1]:
        st.metric("+ Employer match", money(employer_match, shorten=True))
    with cols[2]:
        st.metric("Total savings (yr 1)", money(grand_total, shorten=True),
                  delta=f"{rate_pct:.1f}% of income")


def render(st) -> None:
    with st.expander("Savings — annual contributions", expanded=False):
        render_body(st)
