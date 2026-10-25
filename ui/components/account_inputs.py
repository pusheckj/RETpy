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


# (widget key, label, override key, default, step); rows of two, same order for both owners.
_YOU = [
    [("ai_your_401k", "401(k) ($)", "YOUR_401K", 10_000, 1_000),
     ("ai_your_roth", "Roth IRA ($)", "YOUR_ROTH_IRA", 3_500, 1_000)],
    [("ai_your_trad", "Traditional IRA ($)", "YOUR_TRADITIONAL_IRA", 0, 1_000),
     ("ai_your_hsa", "HSA ($)", "YOUR_HSA", 500, 500)],
    [("ai_your_brk", "Taxable brokerage ($)", "YOUR_BROKERAGE", 2_500, 1_000),
     ("ai_your_cash", "Cash / savings ($)", "YOUR_CASH", 4_000, 500)],
]
_PARTNER = [
    [("ai_partner_401k", "401(k) ($)", "PARTNER_401K", 7_000, 1_000),
     ("ai_partner_roth", "Roth IRA ($)", "PARTNER_ROTH_IRA", 2_500, 1_000)],
    [("ai_partner_brk", "Taxable brokerage ($)", "PARTNER_BROKERAGE", 1_000, 1_000),
     ("ai_partner_cash", "Cash / savings ($)", "PARTNER_CASH", 3_000, 500)],
]


def _rows(st, rows) -> None:
    for row in rows:
        for col, (key, label, ov, default, step) in zip(
                st.columns(2, vertical_alignment="bottom"), row):
            with col:
                ensure_default(st, key, safe_int(get_override(st, ov, default), default))
                v = st.number_input(label, min_value=0, max_value=10_000_000, step=step, key=key)
                set_override(st, ov, safe_int(v))


def render(st) -> None:
    with st.expander("Accounts", expanded=False, icon=":material/account_balance:"):
        st.caption("Edit individual account balances. Totals flow into the simulation.")

        st.markdown("**You**")
        _rows(st, _YOU)

        if safe_int(get_override(st, "PARTNER_AGE", 0), 0) <= 0:
            # Single household: no partner accounts (About you zeroes them too).
            for k in ("PARTNER_401K", "PARTNER_ROTH_IRA", "PARTNER_BROKERAGE", "PARTNER_CASH"):
                set_override(st, k, 0)
            return

        st.markdown("**Partner**")
        _rows(st, _PARTNER)
