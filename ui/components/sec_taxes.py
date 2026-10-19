"""Section 3: Taxes — computed display + state / marginal-rate override knobs."""
from __future__ import annotations

try:
    from utils.coerce import safe_float, ensure_default
    from utils.formatting import money, money_md, pct
    from utils.derived import compute_taxes, compute_total_income
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money, money_md, pct  # type: ignore
    from ui.utils.derived import compute_taxes, compute_total_income  # type: ignore

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore


_STATE_OPTIONS = ["California", "No state income tax", "Other (use marginal rate)"]
_STATE_TO_CODE = {
    "California": "CA",
    "No state income tax": "No state tax",
    "Other (use marginal rate)": "Other",
}
_CODE_TO_STATE = {v: k for k, v in _STATE_TO_CODE.items()}


def render_body(st) -> None:
    overrides = st.session_state.get("user_overrides", {}) or {}

    # Computed display
    income = compute_total_income(overrides)
    taxes = compute_taxes(overrides)

    # 2x2, not 4-across: four columns in the fixed 328px sidebar leaves ~52px
    # each, which is not enough for either "$111.4K" or the label "Effective
    # rate" (they overlapped and spilled past the sidebar's right edge).
    row1 = st.columns(2)
    with row1[0]:
        st.metric("Federal", money(taxes["federal"], shorten=True))
    with row1[1]:
        st.metric("State", money(taxes["state"], shorten=True))
    row2 = st.columns(2)
    with row2[0]:
        st.metric("FICA", money(taxes["fica"], shorten=True))
    with row2[1]:
        st.metric("Effective rate", pct(taxes["effective_rate"]))

    if income > 0:
        st.caption(
            f"**Total tax: {money_md(taxes['total'], shorten=True)}** on "
            f"{money_md(income, shorten=True)} household income."
        )
    else:
        st.caption("Enter income above to see your tax estimate.")

    # State selector
    current_code = str(get_override(st, "STATE_CHOICE", "CA"))
    current_label = _CODE_TO_STATE.get(current_code, "California")
    if current_label not in _STATE_OPTIONS:
        current_label = "California"
    ensure_default(st, "st_state", current_label)
    state = st.selectbox("State", _STATE_OPTIONS, key="st_state",
                         help="California uses 2024 progressive brackets; "
                              "other states use a generic 5% effective rate. "
                              "Select 'Other' to enable the marginal rate slider.")
    set_override(st, "STATE_CHOICE", _STATE_TO_CODE[state])

    if state == "Other (use marginal rate)":
        ensure_default(st, "st_marginal",
                       float(safe_float(get_override(st, "YOUR_MARGINAL_TAX_RATE", 0.22), 0.22)) * 100)
        r = st.slider("Override marginal tax rate (%)",
                      min_value=0.0, max_value=50.0, step=1.0,
                      key="st_marginal",
                      help="Used by some rough estimates.")
        set_override(st, "YOUR_MARGINAL_TAX_RATE", r / 100)

    # What's modeled
    with st.expander("What's modeled", expanded=False):
        st.markdown(
            "- **Federal**: 2024 IRS brackets (MFJ if married, else Single), "
            "with standard deduction (\\$29,200 MFJ / \\$14,600 Single).\n"
            "- **State**: California 2024 brackets / no state tax / generic 5% on taxable.\n"
            "- **FICA**: 7.65% on wages up to \\$168,600, 1.45% above "
            "(Social Security + Medicare).\n"
            "- **Not modeled here**: NIIT, AMT, capital-gains tax (handled in retirement), "
            "self-employment tax."
        )

    st.caption(
        "These estimate pre-retirement working years. Retirement taxes "
        "(LTCG, RMDs, Social Security) are computed by the simulator "
        "using full 2024 IRS rules."
    )


def render(st) -> None:
    with st.expander("Taxes", expanded=False, icon=":material/receipt_long:"):
        render_body(st)
