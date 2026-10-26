"""Withdrawal strategy tab."""
from __future__ import annotations

import logging

from retirement_sim import config as cfg


def render(st, results: dict, chart_key: str = "withdrawal_tab_main") -> None:
    st.markdown('<div class="mc-section">Tax-efficient withdrawal order</div>', unsafe_allow_html=True)
    st.caption("Each year the simulator takes money from your accounts in this order to keep lifetime taxes low, "
               "unless you turn on an early-access strategy (72(t) payments or a Roth ladder).")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            """
            **Before age 59½**
            1. Cash / savings: no tax
            2. Taxable brokerage: LTCG rates (0/15/20%)
            3. Roth contributions: no tax or penalty (not earnings)
            4. Traditional 401(k) / IRA: income tax **+ 10% penalty**
            5. HSA non-medical: income tax **+ 20% penalty**

            *Why*: this avoids the 10-20% penalties and lets your tax-advantaged accounts keep growing.
            """
        )
    with col_b:
        st.markdown(
            """
            **Age 59½ and after**
            1. Cash / savings
            2. Taxable brokerage: LTCG
            3. Traditional 401(k) / IRA: ordinary income tax
            4. Roth: tax-free (saved for last)
            5. HSA: tax-free for qualified medical expenses

            *Why*: Roth is the most tax-efficient, so it waits. Using Traditional first fills your tax brackets gradually.
            """
        )

    st.markdown("---")
    st.markdown('<div class="mc-section">Roth conversion strategy</div>', unsafe_allow_html=True)
    try:
        from utils.overrides import get_override
    except ImportError:  # pragma: no cover
        from ui.utils.overrides import get_override  # type: ignore
    _age = int(get_override(st, "YOUR_AGE", cfg.YOUR_AGE) or cfg.YOUR_AGE)
    _rmd_age = cfg.get_rmd_start_age(cfg.CURRENT_YEAR - _age)
    _cap = int(get_override(st, "ROTH_CONVERSION_MAX_ANNUAL", cfg.ROTH_CONVERSION_MAX_ANNUAL)
               or 0)
    _t = cfg.ROTH_CONVERSION_TARGET_BY_STATUS
    _top = " / ".join(f"\\${_t[k]:,.0f} {name}" for k, name in
                      ((cfg._FILING_MFJ, "joint"), (cfg._FILING_SINGLE, "single"),
                       (cfg._FILING_HOH, "head of household")))
    st.markdown(
        f"""
        When on, the simulator moves money from Traditional to Roth in low-income early-retirement years,
        up to the top of the 12% tax bracket for your filing status ({_top}; 2024 values).
        That money then grows tax-free and your future RMDs get smaller
        (your RMD age is {_rmd_age}).

        Conversions usually run from retirement through the Social Security claim age (often 67),
        when your earned income is lowest. They are **capped** at \\${_cap:,.0f}/year (change it in Assumptions).
        """
    )

    # Re-use income sources chart as a visualization of withdrawal composition
    st.markdown("---")
    pr = results.get("primary_result", {}) or {} if results else {}
    rows = pr.get("income_sources_by_year", []) or []
    if rows:
        try:
            from components.income_sources_chart import render as render_inc
            render_inc(st, results, chart_key="income_sources_withdrawal_tab")
        except Exception:
            # Keep the internals out of the UI (every other component shows a
            # plain placeholder); the traceback still goes to the server log.
            logging.exception("withdrawal_tab: chart render failed")
            st.info("This chart isn't available for this run.")
    else:
        st.info("No year-by-year withdrawal breakdown for this run.")
