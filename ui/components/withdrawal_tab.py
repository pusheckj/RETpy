"""Withdrawal strategy tab."""
from __future__ import annotations

import logging


def render(st, results: dict, chart_key: str = "withdrawal_tab_main") -> None:
    st.markdown('<div class="mc-section">Tax-efficient withdrawal order</div>', unsafe_allow_html=True)
    st.caption("The simulator pulls from accounts in this order each year to minimize lifetime taxes.")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            """
            **Before age 59.5**
            1. Cash / savings — no tax impact
            2. Taxable brokerage — LTCG rates (0/15/20%)
            3. Roth contributions — tax + penalty free (no earnings)
            4. Traditional 401(k) / IRA — income tax **+ 10% penalty**
            5. HSA non-medical — income tax **+ 20% penalty**

            *Rationale*: avoid the 10-20% penalties entirely; drain taxable first so tax-advantaged accounts keep compounding.
            """
        )
    with col_b:
        st.markdown(
            """
            **Age 59.5 and after**
            1. Cash / savings
            2. Taxable brokerage — LTCG
            3. Traditional 401(k) / IRA — ordinary income tax
            4. Roth — tax-free (saved for last)
            5. HSA — tax-free for qualified medical expenses

            *Rationale*: Roth is the most tax-efficient, so preserve it. Traditional drawn before Roth lets tax brackets fill up gradually.
            """
        )

    st.markdown("---")
    st.markdown('<div class="mc-section">Roth conversion strategy</div>', unsafe_allow_html=True)
    st.markdown(
        """
        When enabled, the simulator converts Traditional → Roth during low-income early-retirement years,
        filling up to the 12% tax bracket ceiling (\$94,300 MFJ, 2024). This creates tax-free growth in Roth
        and reduces future RMDs from Traditional balances at age 73/75.

        Conversions typically run from retirement age through the Social Security claim age (often 67),
        which is the period of lowest earned income. They are **capped** at \$100k/year by default.
        """
    )

    # Re-use income sources chart as a visualization of withdrawal composition
    st.markdown("---")
    pr = results.get("primary_result", {}) or {} if results else {}
    rows = pr.get("income_sources_by_year", []) or []
    if rows:
        st.markdown('<div class="mc-section">Withdrawal composition by year</div>', unsafe_allow_html=True)
        try:
            from components.income_sources_chart import render as render_inc
            render_inc(st, results, chart_key="income_sources_withdrawal_tab")
        except Exception:
            # Keep the internals out of the UI (every other component shows a
            # plain placeholder); the traceback still goes to the server log.
            logging.exception("withdrawal_tab: chart render failed")
            st.info("This chart isn't available for this run.")
    else:
        st.info("Detailed per-year withdrawal composition not available for this run.")

    # Withdrawal-rate drawdown chart (% of portfolio pulled each year, by source)
    wd_rows = pr.get("withdrawals_by_year", []) or []
    if wd_rows:
        st.markdown('<div class="mc-section">Withdrawal rate by source</div>', unsafe_allow_html=True)
        # Same chart also appears in the main "Spending" section — say so, so it
        # doesn't read as two different analyses.
        st.caption(":gray[Same chart as the one in the **Spending** section above, "
                   "repeated here alongside the withdrawal deep-dive.]")
        try:
            from components.withdrawal_drawdown_chart import render as render_dd
            render_dd(st, results, chart_key="withdrawal_drawdown_withdrawal_tab")
        except Exception:
            # Keep the internals out of the UI (every other component shows a
            # plain placeholder); the traceback still goes to the server log.
            logging.exception("withdrawal_tab: chart render failed")
            st.info("This chart isn't available for this run.")
