"""Account balances expander."""
from __future__ import annotations

try:
    from utils.coerce import safe_int, safe_float, ensure_default  # noqa: F401
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # noqa: F401

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore


def render(st) -> None:
    with st.expander("Accounts", expanded=False, icon=":material/account_balance:"):
        st.caption("Edit individual account balances. Totals flow into the simulation.")

        st.markdown("**You**")
        col1, col2 = st.columns(2)
        with col1:
            ensure_default(st, "ai_your_401k", safe_int(get_override(st, "YOUR_401K", 10_000), 10_000))
            v = st.number_input("401(k) ($)", min_value=0, max_value=10_000_000, step=1_000, key="ai_your_401k")
            set_override(st, "YOUR_401K", safe_int(v))
            ensure_default(st, "ai_your_roth", safe_int(get_override(st, "YOUR_ROTH_IRA", 3_500), 3_500))
            v = st.number_input("Roth IRA ($)", min_value=0, max_value=10_000_000, step=1_000, key="ai_your_roth")
            set_override(st, "YOUR_ROTH_IRA", safe_int(v))
            ensure_default(st, "ai_your_trad", safe_int(get_override(st, "YOUR_TRADITIONAL_IRA", 0), 0))
            v = st.number_input("Traditional IRA ($)", min_value=0, max_value=10_000_000, step=1_000, key="ai_your_trad")
            set_override(st, "YOUR_TRADITIONAL_IRA", safe_int(v))
        with col2:
            ensure_default(st, "ai_your_hsa", safe_int(get_override(st, "YOUR_HSA", 500), 500))
            v = st.number_input("HSA ($)", min_value=0, max_value=10_000_000, step=500, key="ai_your_hsa")
            set_override(st, "YOUR_HSA", safe_int(v))
            ensure_default(st, "ai_your_brk", safe_int(get_override(st, "YOUR_BROKERAGE", 2_500), 2_500))
            v = st.number_input("Taxable brokerage ($)", min_value=0, max_value=10_000_000, step=1_000, key="ai_your_brk")
            set_override(st, "YOUR_BROKERAGE", safe_int(v))
            ensure_default(st, "ai_your_cash", safe_int(get_override(st, "YOUR_CASH", 4_000), 4_000))
            v = st.number_input("Cash / savings ($)", min_value=0, max_value=10_000_000, step=500, key="ai_your_cash")
            set_override(st, "YOUR_CASH", safe_int(v))

        if safe_int(get_override(st, "PARTNER_AGE", 0), 0) <= 0:
            # Single household: no partner accounts (About you zeroes them too).
            for k in ("PARTNER_401K", "PARTNER_ROTH_IRA", "PARTNER_BROKERAGE", "PARTNER_CASH"):
                set_override(st, k, 0)
            return

        st.markdown("**Partner**")
        col3, col4 = st.columns(2)
        with col3:
            ensure_default(st, "ai_partner_401k", safe_int(get_override(st, "PARTNER_401K", 7_000), 7_000))
            v = st.number_input("401(k) ($)", min_value=0, max_value=10_000_000, step=1_000, key="ai_partner_401k")
            set_override(st, "PARTNER_401K", safe_int(v))
            ensure_default(st, "ai_partner_roth", safe_int(get_override(st, "PARTNER_ROTH_IRA", 2_500), 2_500))
            v = st.number_input("Roth IRA ($)", min_value=0, max_value=10_000_000, step=1_000, key="ai_partner_roth")
            set_override(st, "PARTNER_ROTH_IRA", safe_int(v))
        with col4:
            ensure_default(st, "ai_partner_brk", safe_int(get_override(st, "PARTNER_BROKERAGE", 1_000), 1_000))
            v = st.number_input("Taxable brokerage ($)", min_value=0, max_value=10_000_000, step=1_000, key="ai_partner_brk")
            set_override(st, "PARTNER_BROKERAGE", safe_int(v))
            ensure_default(st, "ai_partner_cash", safe_int(get_override(st, "PARTNER_CASH", 3_000), 3_000))
            v = st.number_input("Cash / savings ($)", min_value=0, max_value=10_000_000, step=500, key="ai_partner_cash")
            set_override(st, "PARTNER_CASH", safe_int(v))
