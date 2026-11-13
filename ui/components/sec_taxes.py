"""Section 3: Taxes — computed display + state / marginal-rate override knobs."""
from __future__ import annotations

try:
    from utils.section_icon import section_expander
except ImportError:  # pragma: no cover
    from ui.utils.section_icon import section_expander  # type: ignore

try:
    from utils.coerce import safe_float, ensure_default
    from utils.formatting import money, money_md, pct
    from utils.derived import sidebar_savings_budget, files_two_returns
    from utils import state_choice
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money, money_md, pct  # type: ignore
    from ui.utils.derived import sidebar_savings_budget, files_two_returns  # type: ignore
    from ui.utils import state_choice  # type: ignore

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore


# Widget label <-> stored STATE_CHOICE (all states + DC, plus the two legacy
# choices). Kept as module names for callers and tests.
try:
    from utils.slider_input import slider_with_box
except ImportError:  # pragma: no cover
    from ui.utils.slider_input import slider_with_box  # type: ignore


_STATE_OPTIONS = state_choice.OPTIONS
_STATE_TO_CODE = {label: state_choice.code_for(label) for label in _STATE_OPTIONS}
_CODE_TO_STATE = {code: label for label, code in _STATE_TO_CODE.items()}


def render_body(st) -> None:
    # State first, so the figures below already reflect a just-changed choice
    # (computed before the selector, they lagged one rerun behind it).
    current_label = state_choice.label_for(get_override(st, "STATE_CHOICE", "CA"))
    ensure_default(st, "st_state", current_label)
    if st.session_state.get("st_state") not in _STATE_OPTIONS:
        st.session_state["st_state"] = current_label
    state = st.selectbox("State", _STATE_OPTIONS, key="st_state",
                         help="Where you live, for state income tax. Each state uses its "
                              "own tax table.")
    code = state_choice.code_for(state)
    set_override(st, "STATE_CHOICE", code)
    st.caption(state_choice.caption_for(code))

    if state == state_choice.FLAT_LABEL:
        ensure_default(st, "st_marginal",
                       float(safe_float(get_override(st, "YOUR_MARGINAL_TAX_RATE", 0.05), 0.05)) * 100)
        r = slider_with_box(st, "State income tax rate (%)",
                      0.0, 15.0, 0.5, unit="%",
                      key="st_marginal",
                      help="A flat state tax on income above the federal standard "
                           "deduction. 5% is a middle-of-the-road guess.")
        set_override(st, "YOUR_MARGINAL_TAX_RATE", r / 100)

    # This year's tax on your pay -- the same function the simulation uses, on
    # the 401(k)/HSA amounts the Investments section puts in (so the "Taxes"
    # figure under its "Saving each year" is this same one).
    overrides = st.session_state.get("user_overrides", {}) or {}
    budget = sidebar_savings_budget(st.session_state)
    income = budget["income"]
    taxes = budget["taxes"]

    # 2x2, not 4-across: four columns in the fixed 328px sidebar leaves ~52px
    # each, which is not enough for either "$111.4K" or the label "Effective
    # rate" (they overlapped and spilled past the sidebar's right edge).
    row1 = st.columns(2)
    with row1[0]:
        st.metric("Federal", money(taxes["federal"], shorten=True),
                  help="Federal income tax after credits. Below zero means a refund: "
                       "the refundable child tax credit pays out more than the tax owed.")
    with row1[1]:
        st.metric("State", money(taxes["state"], shorten=True))
    row2 = st.columns(2)
    with row2[0]:
        st.metric("FICA", money(taxes["fica"], shorten=True),
                  help="Social Security and Medicare tax taken from pay.")
    with row2[1]:
        st.metric("Effective rate", pct(taxes["effective_rate"]))

    if taxes["federal"] < 0:
        st.caption(
            f"Federal is {money_md(taxes['federal'], shorten=True)} because the child tax credit "
            "is bigger than your federal income tax. The refundable part is paid out as a refund."
        )
    if income > 0:
        st.caption(
            f"**Total tax: {money_md(taxes['total'], shorten=True)}** on "
            f"{money_md(income, shorten=True)} household income this year. "
            "The simulation uses these same numbers."
        )
        if files_two_returns(overrides):
            st.caption("You're not married, so each of you files your own return "
                       "and is taxed on your own income.")
    else:
        st.caption("Enter your income above to see your tax estimate.")

    # What's modeled
    with st.expander("What's modeled", expanded=False):
        st.markdown(
            "- **Federal**: 2024 tax tables (brackets and standard deduction, held flat "
            "in today's dollars) for your filing "
            "status (\\$29,200 married / \\$14,600 single / \\$21,900 head of household). "
            "Contribution limits use 2026 values. "
            "An unmarried couple files two returns.\n"
            "- **State**: your state's 2024 brackets, deductions and exemptions, "
            "including whether it taxes Social Security and retirement income. "
            "City and county income taxes are not included.\n"
            "- **FICA**: Social Security tax of 6.2% on pay up to \\$168,600 per person, "
            "plus Medicare tax of 1.45% on all pay and 0.9% more over \\$200,000 "
            "(\\$250,000 married).\n"
            "- **Pre-tax savings**: 401(k) and HSA contributions lower your income "
            "tax (not FICA, for the 401(k)).\n"
            "- **Child tax credit**: \\$2,200 per child under 17, in working years only. "
            "If it is more than your tax, the refundable part is paid out, so federal "
            "tax can show below zero.\n"
            "- **Not modeled**: other tax credits (such as the earned income credit), "
            "itemized deductions, AMT, self-employment tax."
        )

    st.caption(
        "Taxes in retirement (withdrawals, Social Security, Roth conversions) "
        "are worked out year by year with the same rules."
    )


def render(st) -> None:
    with section_expander(st, "Taxes", "receipt_long"):
        render_body(st)
