"""Section: Debts — credit cards, student loans, car loans and other debts.

The rows write ``DEBTS`` (a list of plain dicts, see retirement_sim/config.py);
the extra payment and the payoff order write ``DEBT_EXTRA_MONTHLY`` and
``DEBT_STRATEGY``. The simulation pays them every month until each is gone
(retirement_sim/debts.py). The mortgage stays in House.

Every widget key starts with "debt_". The rows are a dynamic list: their keys
(``utils/debt_view.row_key``) are filled and cleared as a family by
``utils/widget_sync`` (``_sync_debts``); the add and remove buttons rewrite them
in their callbacks, before the widgets are drawn. Sections drawn earlier in
the run (Expenses, Taxes) read this run's values through ``debt_view.live``.

Drawn after Expenses and before Accounts: the payments are a monthly outflow
like spending, and the Investments section's "Left to save" (drawn later in the
same run) already leaves them out.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

try:
    from utils.section_icon import section_expander
except ImportError:  # pragma: no cover
    from ui.utils.section_icon import section_expander  # type: ignore

try:
    from utils.coerce import safe_int, ensure_default
    from utils.formatting import money_md
    from utils.overrides import get_override, set_override
    from utils import debt_view as dv
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, ensure_default  # type: ignore
    from ui.utils.formatting import money_md  # type: ignore
    from ui.utils.overrides import get_override, set_override  # type: ignore
    from ui.utils import debt_view as dv  # type: ignore

from retirement_sim import debts as dm

PREFIX, row_key, seed_rows = dv.PREFIX, dv.row_key, dv.seed_rows
BALANCE_MAX, PAYMENT_MAX = dv.BALANCE_MAX, dv.PAYMENT_MAX
EXTRA_KEY, STRATEGY_KEY = dv.EXTRA_KEY, dv.STRATEGY_KEY
STRATEGY_LABELS = {"avalanche": "Highest rate first (avalanche)",
                   "snowball": "Smallest balance first (snowball)"}


def _store(ss, debts: List[Dict[str, Any]]) -> None:
    ss.setdefault("user_overrides", {})["DEBTS"] = debts
    seed_rows(ss, debts, force=True)


def _add(ss) -> None:
    rows = dv.current_rows(ss)
    if len(rows) < dm.MAX_DEBTS:
        rows.append({"name": f"Debt {len(rows) + 1}", "kind": "credit_card", "balance": 0.0,
                     "apr": 0.0, "min_payment": 0.0})
    _store(ss, rows)


def _remove(ss, index: int) -> None:
    rows = dv.current_rows(ss)
    if 0 <= index < len(rows):
        del rows[index]
    _store(ss, rows)


def _row(st, i: int) -> None:
    """One debt's card. The 328px side panel fits two inputs a row, so the name
    and the type (whose labels are long) each get the width they need."""
    with st.container(border=True, key=f"mc-debt-row-{i}"):
        # A horizontal container, not columns: phones stack columns, which put the
        # remove button on a line of its own.
        with st.container(horizontal=True, vertical_alignment="bottom", key=f"mc-debt-name-{i}"):
            st.text_input("Name", key=row_key(i, "name"), max_chars=dm.NAME_MAX_LEN)
            st.button("", key=f"{PREFIX}rm_{i}", on_click=_remove, args=(st.session_state, i),
                      icon=":material/delete:", type="tertiary", width="content",
                      help="Remove this debt")
        st.selectbox("Type", dm.KINDS, key=row_key(i, "kind"), format_func=dm.KIND_LABELS.get)
        c1, c2 = st.columns(2, vertical_alignment="bottom")
        c1.number_input("Balance ($)", min_value=0, max_value=BALANCE_MAX, step=100,
                        key=row_key(i, "balance"), help="What you owe now.")
        c2.number_input("APR (%)", min_value=0.0, max_value=100.0, step=0.25, format="%.2f",
                        key=row_key(i, "apr"),
                        help="The yearly interest rate on your statement.")
        st.number_input("Minimum ($ a month)", min_value=0, max_value=PAYMENT_MAX, step=10,
                        key=row_key(i, "min"), help="The minimum payment due each month.")


def _summary(st, overrides: Dict[str, Any]) -> None:
    s = dv.summary(overrides, date.today())
    if not s.per_debt:
        return
    head = (f"Owed: **{money_md(s.owed)}**. Paying **{money_md(s.monthly)}** a month")
    if s.paid_off:
        st.caption(f"{head}, debt-free by **{s.debt_free}** ({dv.duration(s.months)}), "
                   f"with {money_md(s.interest)} of interest. The Debt payoff section has the details.")
    else:
        st.caption(f"{head}.")
        st.warning("At these payments the debts aren't paid off within 50 years. "
                   "Raise the extra payment or a minimum.")
    if s.underwater:
        st.caption("⚠ The minimum on " + ", ".join(s.underwater)
                   + " doesn't cover its monthly interest, so on its own that balance grows.")


def render_body(st) -> None:
    ss = st.session_state
    st.caption("Credit cards, student loans, car loans and other debts. Your mortgage stays in "
               "House. Leave these payments out of Expenses: the plan pays them here until "
               "each debt is gone, then saves the money instead.")
    debts = dm.normalize_debts(get_override(st, "DEBTS", []))
    seed_rows(ss, debts)
    for i in range(len(debts)):
        _row(st, i)
    rows = [dv.row_from_widgets(ss, i, d) for i, d in enumerate(debts)]
    set_override(st, "DEBTS", rows)
    if len(rows) < dm.MAX_DEBTS:
        st.button("Add a debt", key=f"{PREFIX}add", on_click=_add, args=(ss,), icon=":material/add:")

    ensure_default(st, EXTRA_KEY, min(safe_int(get_override(st, "DEBT_EXTRA_MONTHLY", 0), 0), PAYMENT_MAX))
    ensure_default(st, STRATEGY_KEY, dm.normalize_strategy(get_override(st, "DEBT_STRATEGY")))
    if rows:
        st.number_input("Extra each month ($)", min_value=0, max_value=PAYMENT_MAX, step=25,
                        key=EXTRA_KEY,
                        help="Paid on top of the minimums. It comes out of what you would "
                             "otherwise save. When a debt is paid off, its minimum goes to the "
                             "next one too.")
        st.radio("Pay off first", list(STRATEGY_LABELS), key=STRATEGY_KEY,
                 format_func=STRATEGY_LABELS.get,
                 help="Where the extra goes. Highest rate first costs the least interest. "
                      "Smallest balance first clears a debt sooner, which keeps some people going.")
    set_override(st, "DEBT_EXTRA_MONTHLY", safe_int(ss.get(EXTRA_KEY, 0), 0))
    set_override(st, "DEBT_STRATEGY", dm.normalize_strategy(ss.get(STRATEGY_KEY)))
    _summary(st, ss.get("user_overrides", {}))


def render(st) -> None:
    with section_expander(st, "Debts", "credit_card"):
        render_body(st)
