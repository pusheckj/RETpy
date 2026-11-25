"""Spending tab: your spending against similar households.

The comparison itself is ``utils/budget_compare.py`` (BiggerPockets Money's method over BLS
Consumer Expenditure 2025, BEA price levels and HUD rents). This file draws it: the area and
income-group pickers, the table and the credit.

Your figures are the plan's monthly inputs. With statements loaded, ``actual`` (the
"Use my actual spending" figures) replaces the plan's wherever the statements have the category.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

try:
    from utils import budget_compare as bc
    from utils import budget_data as bd
    from utils.expense_categories import CATEGORIES, HOUSING_KEYS
    from utils.formatting import money, money_md
    from components import budget_area
except ImportError:  # pragma: no cover
    from ui.utils import budget_compare as bc  # type: ignore
    from ui.utils import budget_data as bd  # type: ignore
    from ui.utils.expense_categories import CATEGORIES, HOUSING_KEYS  # type: ignore
    from ui.utils.formatting import money, money_md  # type: ignore
    from ui.components import budget_area  # type: ignore

AUTO = "auto"
VERDICT = {"below": "Below typical", "in range": "Typical", "above": "Above typical", "": "–"}
CREDIT = ("This is a statistical average of what similar households spend. It is not a target "
          "and not advice. Source: BLS Consumer Expenditure Survey 2025. Prices are adjusted for "
          "your area with BEA Regional Price Parities and HUD Fair Market Rents. Costs are "
          "carried to 2026 with BLS CPI. Method from BiggerPockets Money's Household Spending "
          "Comparison.")


def yours_from_actual(actual: Optional[Dict[str, int]]) -> Dict[str, float]:
    """Statement averages ({config key: $/month}) as {expense label: $/month}."""
    out: Dict[str, float] = {c.label: float(actual[c.key]) for c in CATEGORIES
                             if actual and c.key in actual}
    housing = next((actual[k] for k in HOUSING_KEYS if actual and k in actual), None)
    if housing is not None:
        out["Housing"] = float(housing)
    return out


def table(rows) -> pd.DataFrame:
    """The comparison as display text, one line per group and a Total."""
    return pd.DataFrame({
        "Category": [r.label for r in rows],
        "You, a month": [money(r.you) if r.you > 0 else "–" for r in rows],
        "Typical, a month": [money(r.typical) for r in rows],
        "Typical range": [f"{money(r.low)} to {money(r.high)}" for r in rows],
        "You are": [VERDICT[r.verdict] for r in rows],
    })


def _pick_group(st) -> None:
    """Selectbox callback: save the hand-picked income group in the plan ("auto" forgets it)."""
    ov = st.session_state.setdefault("user_overrides", {})
    choice = st.session_state.get("sb_income")
    if choice in bc.QUINTILES:
        ov[bc.GROUP_KEY] = choice
    else:
        ov.pop(bc.GROUP_KEY, None)


def render(st, actual: Optional[Dict[str, int]] = None) -> None:
    ov = st.session_state.get("user_overrides", {}) or {}
    st.markdown("**Your spending vs similar households**")
    c1, c2 = st.columns(2, vertical_alignment="bottom")
    with c1:
        budget_area.render(st, "se_kid_area_spend")
    auto = bc.household(ov).auto_quintile
    saved = ov.get(bc.GROUP_KEY) if ov.get(bc.GROUP_KEY) in bc.QUINTILES else AUTO
    if st.session_state.get("sb_income") not in (AUTO, *bc.QUINTILES):
        st.session_state["sb_income"] = saved
    with c2:
        pick = st.selectbox("Income group", [AUTO, *bc.QUINTILES], key="sb_income",
                            on_change=_pick_group, args=(st,),
                            format_func=lambda q: (f"From your pay: {bc.QUINTILE_LABELS[auto]}"
                                                   if q == AUTO else bc.QUINTILE_LABELS[q]),
                            help="Households are split into five equal groups by income before "
                                 "tax. The cutoffs here are rough, so pick your group if it "
                                 "looks wrong. Saved with your plan.")
    rows, h = bc.spending_rows(ov, None if pick == AUTO else pick, yours_from_actual(actual))
    group = bc.QUINTILE_LABELS[auto if pick == AUTO else pick]
    where = h.area or (bd.statewide(h.state)["l"].replace(" " + bd.STATEWIDE_SUFFIX, "")
                       if h.state else "the US")
    st.caption(f"Households with {h.adults} adult{'' if h.adults == 1 else 's'}, you aged {h.age}, "
               f"in the {group.lower()} income group, near {where}. "
               + (f"Housing is sized for all {h.at_home} people at home. " if h.at_home > h.adults else "")
               + "Your figures are your plan's monthly inputs"
               + (" and your statements where they have the category." if actual else "."))
    st.dataframe(table(rows), hide_index=True, width="stretch")
    total = rows[-1]
    st.caption(f"Typical total: {money_md(total.typical)} a month. The typical range is "
               f"{money_md(total.low)} to {money_md(total.high)}, 10% either side. "
               f"You are at {money_md(total.you)}.")
    notes = [f"{r.label}: {r.note}" for r in rows if r.note]
    st.caption(" ".join(notes) + " " + bc.EXCLUDED + " Your children's costs are not compared.")
    st.caption(CREDIT)
