"""Spending patterns inputs — category breakdown and lifecycle preset.

.. warning::
   **This module is HALF LIVE — do not delete it.** Its ``render()`` /
   ``render_body()`` UI is superseded by ``sec_expenses.py`` and is no longer
   called from ``app.py``, but its *compute helpers* are load-bearing:

     * ``components/spending_chart.py`` imports ``SPENDING_CATEGORIES`` and
       ``compute_lifecycle_multipliers`` (a per-age view of the engine's own
       ``cfg.lifecycle_multiplier``, which the simulation reads directly).

   Removing the file breaks the spending chart. Safe cleanup = drop only the
   unused ``render``/``render_body`` functions, or move the helpers into
   ``utils/``.

Provides a monthly-spending-by-category breakdown plus a lifecycle preset that
describes how spending evolves over time (e.g., mortgage pay-off, travel boom,
empty-nest). These inputs are informational/visualization-only today — the
core simulator still consumes ``YOUR_OTHER_MONTHLY``, ``UTILITIES_MONTHLY``,
etc. — but they persist to ``user_overrides`` so they save/load with profiles
and feed the spending_chart component.
"""
from __future__ import annotations

try:
    from utils.coerce import safe_int, safe_float, ensure_default  # noqa: F401
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # noqa: F401

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore


# Lifecycle preset names. These must match the keys in
# ``compute_lifecycle_multipliers`` and the options in the select box.
# (The "Paid off mortgage" preset was removed because the chart now derives
# housing from the mortgage inputs — it auto-drops at payoff.)
LIFECYCLE_PRESETS = [
    "Flat (no change)",
    "Early-retirement travel boom, quieter later",
    "Conservative senior years",
    "Children then empty-nest",
]


# Spending categories: (widget_key, override_key, label, default_monthly)
# NOTE: Housing intentionally NOT here — it's auto-derived from the mortgage
# inputs in sec_expenses.py (drops to $0 once the mortgage is paid off, or
# uses Monthly rent for renters).
SPENDING_CATEGORIES = [
    ("sp_utilities",     "SPEND_UTILITIES_MONTHLY",     "Utilities",                        200),
    ("sp_food",          "SPEND_FOOD_MONTHLY",          "Food & groceries",                 900),
    ("sp_transport",     "SPEND_TRANSPORT_MONTHLY",     "Transportation",                   500),
    ("sp_health",        "SPEND_HEALTH_MONTHLY",        "Healthcare premiums (pre-ret.)",   400),
    ("sp_discretionary", "SPEND_DISCRETIONARY_MONTHLY", "Entertainment/travel/discretionary", 600),
    ("sp_other",         "SPEND_OTHER_MONTHLY",         "Miscellaneous",                    300),
]


def compute_lifecycle_multipliers(
    preset: str,
    current_age: int,
    retirement_age: int,
    plan_until_age: int,
    years_until_first_child: int = 99,
    child_leaves_home_age: int = 18,
) -> dict:
    """Return {category: {age: multiplier}} for the lifecycle preset.

    Multipliers are applied on top of inflation in the spending chart. A value
    of 1.0 means "no change from today's spending in real terms." Only the
    non-1.0 entries are stored; callers should default missing ages to 1.0.

    The mapping itself is the engine's (``cfg.lifecycle_multiplier``), so the
    chart shows exactly what the simulation spends: the go-go and later-years
    ages follow ``retirement_age``, and empty-nest follows every child at home
    (``cfg.children_at_home_ages``). Children come from the ENGINE config, so a
    caller drawing a plan from overrides must patch the children inputs onto it
    first (spending_chart does). ``years_until_first_child`` and
    ``child_leaves_home_age`` are accepted for older callers and ignored.
    """
    from retirement_sim import config as cfg

    ages = list(range(int(current_age), int(plan_until_age) + 1))
    # Every category maps to a {age: multiplier} dict (default 1.0).
    out: dict = {c[1]: {} for c in SPENDING_CATEGORIES}
    if preset not in LIFECYCLE_PRESETS[1:]:
        return out   # "Flat (no change)" and unknown presets: all multipliers stay 1.0.
    nest = cfg.empty_nest_age(current_age, plan_until_age)
    for a in ages:
        kids = bool(cfg.children_at_home_ages(a))
        for category in out:
            m = cfg.lifecycle_multiplier(category, a, retirement_age, preset,
                                         retired=a >= int(retirement_age),
                                         kids_at_home=kids, empty_nest_from=nest)
            if m != 1.0:
                out[category][a] = m
    return out


def render_body(st) -> None:
    """Render the widgets WITHOUT the outer expander (for embedding)."""
    st.caption(
        "Break down today's spending by category, then pick a lifecycle "
        "pattern for how spending evolves. **Housing is auto-derived** from "
        "your mortgage / rent inputs in **Housing & utilities** above — it "
        "drops off automatically when the mortgage is paid off."
    )

    st.markdown("**Current spending (monthly, today's dollars)**")

    # Render category inputs in two columns.
    col1, col2 = st.columns(2)
    for idx, (wkey, okey, label, default) in enumerate(SPENDING_CATEGORIES):
        target_col = col1 if idx % 2 == 0 else col2
        with target_col:
            # Special handling: SPEND_UTILITIES_MONTHLY mirrors UTILITIES_MONTHLY.
            if okey == "SPEND_UTILITIES_MONTHLY":
                current = safe_int(
                    get_override(st, okey, get_override(st, "UTILITIES_MONTHLY", default)),
                    default,
                )
            else:
                current = safe_int(get_override(st, okey, default), default)

            ensure_default(st, wkey, current)
            v = st.number_input(
                label,
                min_value=0,
                max_value=50_000,
                step=50,
                key=wkey,
            )
            set_override(st, okey, safe_int(v))
            # Keep UTILITIES_MONTHLY in sync (two-way reflection).
            if okey == "SPEND_UTILITIES_MONTHLY":
                set_override(st, "UTILITIES_MONTHLY", safe_int(v))

    # Total display.
    total_monthly = sum(
        safe_int(get_override(st, okey, 0), 0) for _, okey, _, _ in SPENDING_CATEGORIES
    )
    st.metric("Total monthly spending", f"${total_monthly:,.0f}")
    st.metric("Total annual spending", f"${total_monthly * 12:,.0f}")

    st.markdown("---")
    st.markdown("**Lifecycle pattern**")

    current_preset = str(get_override(st, "SPEND_LIFECYCLE_PRESET", LIFECYCLE_PRESETS[0]))
    if current_preset not in LIFECYCLE_PRESETS:
        current_preset = LIFECYCLE_PRESETS[0]
    ensure_default(st, "sp_lifecycle", current_preset)

    preset = st.selectbox(
        "How does spending change over time?",
        LIFECYCLE_PRESETS,
        key="sp_lifecycle",
        help=(
            "Flat: expenses only inflate.  |  "
            "Travel boom: discretionary +50% early in retirement, -20% later.  |  "
            "Conservative senior: discretionary -30% in later years.  |  "
            "Empty-nest: food/discretionary +30% while kids at home, "
            "-25% after they leave.  |  "
            "(Mortgage drop-off at payoff is automatic.)"
        ),
    )
    set_override(st, "SPEND_LIFECYCLE_PRESET", preset)

    # Precompute multipliers for downstream consumers (chart, saved profiles).
    current_age = safe_int(get_override(st, "YOUR_AGE", 25), 25)
    retirement_age = safe_int(get_override(st, "TARGET_RETIREMENT_AGE", 55), 55)
    plan_until = safe_int(get_override(st, "PLAN_UNTIL_AGE", 90), 90)
    yufc = safe_int(get_override(st, "YEARS_UNTIL_FIRST_CHILD", 99), 99)
    leave_age = safe_int(get_override(st, "CHILD_LEAVES_HOME_AGE", 18), 18)

    multipliers = compute_lifecycle_multipliers(
        preset=preset,
        current_age=current_age,
        retirement_age=retirement_age,
        plan_until_age=plan_until,
        years_until_first_child=yufc,
        child_leaves_home_age=leave_age,
    )
    set_override(st, "SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE", multipliers)


def render(st) -> None:
    """Render the standalone expander version."""
    with st.expander("Spending patterns", expanded=False):
        render_body(st)
