"""Investments: how you save each year, and the market assumptions behind growth.

Two groups under one section header:

* "Saving each year" -- the whole of ``sec_savings.render_body`` (what goes into
  each account, the four savings modes, Max out buttons, the summary figures).
* "Returns and mix" -- ``sec_assumptions.render_investing_body`` (returns,
  stock/bond mix, fees, inflation, glide path, Roth conversion).

Widget keys (sv_*, sa_*) and override keys are those of the two modules, so saved
profiles and widget_sync are untouched. It draws after Accounts and before
Retirement, as Savings did.
"""
from __future__ import annotations

try:
    from utils.section_icon import section_expander
    from components import sec_assumptions, sec_savings
except ImportError:  # pragma: no cover
    from ui.utils.section_icon import section_expander  # type: ignore
    from ui.components import sec_assumptions, sec_savings  # type: ignore


def _group_label(st, txt: str) -> None:
    st.markdown(f"**{txt}**")


def render_body(st) -> None:
    _group_label(st, "Saving each year")
    sec_savings.render_body(st)
    st.divider()
    _group_label(st, "Returns and mix")
    sec_assumptions.render_investing_body(st)


def render(st) -> None:
    with section_expander(st, "Investments", "trending_up"):
        render_body(st)
