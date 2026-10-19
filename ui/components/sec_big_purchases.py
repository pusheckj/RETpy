"""Section: Big purchases & goals — car, house move, retirement vacation.

Three optional lifecycle events, each OFF by default so the baseline
simulation is unaffected until a user explicitly opts in:
  - Car: one-time purchase and/or recurring replacement (paid cash from
    the portfolio).
  - House move: sell the current home, buy a new one, switch the ongoing
    mortgage.
  - Retirement vacation: extra "go-go years" spending from retirement
    until a chosen slow-down age.
"""
from __future__ import annotations

try:
    from utils.coerce import safe_int, safe_float, ensure_default
    from utils.formatting import money_md
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money_md  # type: ignore

try:
    from utils.overrides import get_override, set_override
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore

try:
    from utils.derived import new_home_financing, implied_mortgage_rate
except ImportError:  # pragma: no cover
    from ui.utils.derived import new_home_financing, implied_mortgage_rate  # type: ignore


def _section_label(st, txt):
    st.markdown(f'<div style="font-size: 13px; color: #64748b; text-transform: uppercase; '
                f'letter-spacing: 0.05em; margin: 12px 0 6px 0;">{txt}</div>',
                unsafe_allow_html=True)


def render_body(st) -> None:
    # ===== Car =====
    _section_label(st, "Car")

    ensure_default(st, "bp_car_onetime_enable",
                   bool(get_override(st, "CAR_ONETIME_ENABLED", False)))
    onetime_on = st.toggle("Plan a one-time car purchase",
                             key="bp_car_onetime_enable",
                             help="A single cash outlay in the chosen year, paid from "
                                  "the portfolio (accumulation or retirement).")
    set_override(st, "CAR_ONETIME_ENABLED", bool(onetime_on))
    if onetime_on:
        c1, c2 = st.columns(2)
        with c1:
            ensure_default(st, "bp_car_onetime_age",
                           safe_int(get_override(st, "CAR_ONETIME_AGE", 40), 40))
            v = st.number_input("Purchase age", min_value=18, max_value=100,
                                step=1, key="bp_car_onetime_age")
            set_override(st, "CAR_ONETIME_AGE", safe_int(v))
        with c2:
            ensure_default(st, "bp_car_onetime_amount",
                           safe_int(get_override(st, "CAR_ONETIME_AMOUNT", 40_000), 40_000))
            v = st.number_input("Purchase amount ($)", min_value=0, max_value=500_000,
                                step=1_000, key="bp_car_onetime_amount")
            set_override(st, "CAR_ONETIME_AMOUNT", safe_int(v))
        st.caption("One-time cash outlay in the chosen year, paid from the portfolio.")

    ensure_default(st, "bp_car_recurring_enable",
                   bool(get_override(st, "CAR_RECURRING_ENABLED", False)))
    recurring_on = st.toggle("Plan recurring car replacements",
                               key="bp_car_recurring_enable",
                               help="Repeats a cash outlay every N years, starting at "
                                    "the chosen age.")
    set_override(st, "CAR_RECURRING_ENABLED", bool(recurring_on))
    if recurring_on:
        c3, c4, c5 = st.columns(3)
        with c3:
            ensure_default(st, "bp_car_recurring_start",
                           safe_int(get_override(st, "CAR_RECURRING_START_AGE", 40), 40))
            v = st.number_input("Start age", min_value=18, max_value=100,
                                step=1, key="bp_car_recurring_start")
            set_override(st, "CAR_RECURRING_START_AGE", safe_int(v))
        with c4:
            ensure_default(st, "bp_car_recurring_every",
                           safe_int(get_override(st, "CAR_RECURRING_EVERY_YEARS", 8), 8))
            v = st.number_input("Every N years", min_value=1, max_value=30,
                                step=1, key="bp_car_recurring_every")
            set_override(st, "CAR_RECURRING_EVERY_YEARS", safe_int(v))
        with c5:
            ensure_default(st, "bp_car_recurring_amount",
                           safe_int(get_override(st, "CAR_RECURRING_AMOUNT", 40_000), 40_000))
            v = st.number_input("Amount ($)", min_value=0, max_value=500_000,
                                step=1_000, key="bp_car_recurring_amount")
            set_override(st, "CAR_RECURRING_AMOUNT", safe_int(v))
        st.caption("Replaces the car every N years starting at the given age, "
                   "paid from the portfolio.")

    st.divider()

    # ===== House move =====
    _section_label(st, "House move")

    ensure_default(st, "bp_house_move_enable",
                   bool(get_override(st, "HOUSE_MOVE_ENABLED", False)))
    house_on = st.toggle("Plan a house move",
                           key="bp_house_move_enable",
                           help="Sell the current home, buy a new one, and switch "
                                "the mortgage payment/payoff at the chosen age.")
    set_override(st, "HOUSE_MOVE_ENABLED", bool(house_on))
    if house_on:
        # The loan balance and monthly payment are DERIVED from price / down
        # payment / rate / term / escrow rather than typed in separately. They
        # used to be independent free-text fields, so raising the home price left
        # the loan and payment costing the OLD house — the model then reported a
        # materially better result than the purchase deserved (e.g. 80.4% for a
        # $1.6M buy that really scores 78.0%, flipping a "meets your 80% target"
        # verdict into a miss).
        #
        # Seed the rate / down % from a plan saved BEFORE these fields existed so
        # it keeps producing its original payment instead of jumping to a new
        # default rate.
        _price_seed = safe_int(get_override(st, "NEW_HOME_VALUE", 1_000_000), 1_000_000)
        _years_seed = safe_int(get_override(st, "NEW_MORTGAGE_YEARS", 30), 30)
        _escrow_seed = safe_float(get_override(st, "NEW_HOME_ESCROW_PCT", 0.0135), 0.0135)
        if get_override(st, "NEW_MORTGAGE_RATE", None) is None:
            _bal = safe_float(get_override(st, "NEW_MORTGAGE_BALANCE", 0), 0.0)
            _mo = safe_float(get_override(st, "NEW_MORTGAGE_MONTHLY", 0), 0.0)
            if _price_seed > 0 and _bal > 0 and _mo > 0:
                _pi = max(0.0, _mo - _price_seed * _escrow_seed / 12.0)
                set_override(st, "NEW_MORTGAGE_RATE",
                             round(implied_mortgage_rate(_bal, _pi, _years_seed), 5))
                set_override(st, "NEW_HOME_DOWN_PCT",
                             round(max(0.0, 1.0 - _bal / _price_seed), 4))
            else:
                set_override(st, "NEW_MORTGAGE_RATE", 0.065)

        c6, c7 = st.columns(2)
        with c6:
            ensure_default(st, "bp_house_move_age",
                           safe_int(get_override(st, "HOUSE_MOVE_AGE", 45), 45))
            v = st.number_input("Move age", min_value=18, max_value=100,
                                step=1, key="bp_house_move_age")
            set_override(st, "HOUSE_MOVE_AGE", safe_int(v))
            ensure_default(st, "bp_new_home_value",
                           safe_int(get_override(st, "NEW_HOME_VALUE", 1_000_000), 1_000_000))
            v = st.number_input("New home value ($)", min_value=0, max_value=20_000_000,
                                step=10_000, key="bp_new_home_value")
            set_override(st, "NEW_HOME_VALUE", safe_int(v))
            ensure_default(st, "bp_new_home_down_pct",
                           safe_float(get_override(st, "NEW_HOME_DOWN_PCT", 0.20), 0.20) * 100)
            v = st.number_input("Down payment (%)", min_value=0.0, max_value=100.0,
                                step=1.0, key="bp_new_home_down_pct",
                                help="Below 20% typically adds PMI, which this model "
                                     "does not charge separately.")
            set_override(st, "NEW_HOME_DOWN_PCT", v / 100)
        with c7:
            ensure_default(st, "bp_new_mortgage_rate",
                           safe_float(get_override(st, "NEW_MORTGAGE_RATE", 0.065), 0.065) * 100)
            v = st.number_input("Mortgage rate (%)", min_value=0.0, max_value=20.0,
                                step=0.125, format="%.3f", key="bp_new_mortgage_rate")
            set_override(st, "NEW_MORTGAGE_RATE", v / 100)
            ensure_default(st, "bp_new_mortgage_years",
                           safe_int(get_override(st, "NEW_MORTGAGE_YEARS", 30), 30))
            v = st.number_input("New mortgage term (years)", min_value=1, max_value=40,
                                step=1, key="bp_new_mortgage_years")
            set_override(st, "NEW_MORTGAGE_YEARS", safe_int(v))
            ensure_default(st, "bp_new_home_escrow_pct",
                           safe_float(get_override(st, "NEW_HOME_ESCROW_PCT", 0.0135), 0.0135) * 100)
            v = st.number_input("Property tax + insurance (%/yr)", min_value=0.0, max_value=5.0,
                                step=0.05, key="bp_new_home_escrow_pct",
                                help="Percent of home value per year, added to the "
                                     "monthly payment. CA is roughly 1.1% tax + "
                                     "0.25% insurance.")
            set_override(st, "NEW_HOME_ESCROW_PCT", v / 100)

        # Write the engine-facing keys from the derived figures.
        fin = new_home_financing(st.session_state.get("user_overrides", {}) or {})
        set_override(st, "NEW_MORTGAGE_BALANCE", int(round(fin["loan"])))
        set_override(st, "NEW_MORTGAGE_MONTHLY", int(round(fin["monthly"])))
        # NOTE: escape every literal "$" as "\$" — Streamlit's markdown renders
        # $...$ as LaTeX math, which silently mangled this caption into
        # "Loan 800,000∗∗after∗∗200,000" on the first attempt.
        st.caption(
            f"Loan **\\${fin['loan']:,.0f}** after **\\${fin['down_payment']:,.0f}** down · "
            f"**\\${fin['monthly']:,.0f}/mo** all-in "
            f"(\\${fin['principal_interest']:,.0f} P&I + \\${fin['escrow']:,.0f} tax/ins)"
        )

        # The single most consequential house decision for an early retiree: a
        # term that outlives your working years is carried by the PORTFOLIO.
        _move = safe_int(get_override(st, "HOUSE_MOVE_AGE", 45), 45)
        _term = safe_int(get_override(st, "NEW_MORTGAGE_YEARS", 30), 30)
        _ret = safe_int(get_override(st, "TARGET_RETIREMENT_AGE", 60), 60)
        _payoff = _move + _term
        if _payoff > _ret:
            _yrs = _payoff - _ret
            st.warning(
                f"This loan is paid off at **{_payoff}**, which is **{_yrs} years "
                f"into retirement** (you target {_ret}). Those payments come out of "
                f"the portfolio. A shorter term costs more per month while you're "
                f"earning but often retires you *sooner* — worth testing both."
            )
        else:
            st.caption(f":gray[Paid off at {_payoff}, before you retire at {_ret}.]")

        ensure_default(st, "bp_home_selling_cost_pct",
                       safe_float(get_override(st, "HOME_SELLING_COST_PCT", 0.06), 0.06) * 100)
        v = st.number_input("Selling costs (%)", min_value=0.0, max_value=20.0,
                            step=0.5, key="bp_home_selling_cost_pct",
                            help="Realtor fees and closing costs on the sale of "
                                 "the current home.")
        set_override(st, "HOME_SELLING_COST_PCT", v / 100)

        ensure_default(st, "bp_house_moving_costs",
                       safe_int(get_override(st, "HOUSE_MOVING_COSTS", 10_000), 10_000))
        v = st.number_input("Moving costs ($)", min_value=0, max_value=200_000,
                            step=1_000, key="bp_house_moving_costs",
                            help="Movers, buy-side closing costs, etc.")
        set_override(st, "HOUSE_MOVING_COSTS", safe_int(v))
        st.caption("Net sale proceeds (value − remaining mortgage − selling costs) "
                   "flow into the portfolio. The down payment and moving costs are "
                   "drawn from it, and the mortgage payment and home equity switch to "
                   "the new house.")

    st.divider()

    # ===== Extra mortgage principal =====
    # Deliberately OUTSIDE the house-move block: extra principal applies to
    # whichever loan you currently hold. Placed right after the "this loan
    # outlives your working years" warning because it is the direct remedy.
    _section_label(st, "Extra mortgage principal")
    _has_loan = safe_int(get_override(st, "MORTGAGE_BALANCE", 0), 0) > 0 or bool(
        get_override(st, "HOUSE_MOVE_ENABLED", False))
    if not _has_loan:
        st.caption(":gray[No mortgage configured, so there's nothing to pay down.]")
    else:
        ensure_default(st, "bp_extra_mortgage",
                       safe_int(get_override(st, "EXTRA_MORTGAGE_PAYMENT_ANNUAL", 0), 0))
        extra = st.number_input(
            "Extra principal per year ($)", min_value=0, max_value=300_000, step=1_000,
            key="bp_extra_mortgage",
            help="Paid on top of the scheduled payment. Charged as real cash, so it "
                 "competes with investing the same dollars — and the scheduled "
                 "payment stops once the loan is gone.")
        set_override(st, "EXTRA_MORTGAGE_PAYMENT_ANNUAL", safe_int(extra))

        _your_age = safe_int(get_override(st, "YOUR_AGE", 32), 32)
        if safe_int(extra) > 0:
            _move_age = safe_int(get_override(st, "HOUSE_MOVE_AGE", 0), 0)
            _move_on = bool(get_override(st, "HOUSE_MOVE_ENABLED", False))
            # Offer "start at the move" because that is when the big new loan
            # appears; paying down a house you're about to sell only raises the
            # sale proceeds.
            _opts = [_your_age] + ([_move_age] if (_move_on and _move_age > _your_age) else [])
            ensure_default(st, "bp_extra_mortgage_start",
                           safe_int(get_override(st, "EXTRA_MORTGAGE_PAYMENT_START_AGE",
                                                 _your_age) or _your_age, _your_age))
            if len(_opts) > 1:
                start = st.radio(
                    "Start paying extra at age", _opts, horizontal=True,
                    key="bp_extra_mortgage_start_radio",
                    format_func=lambda a: (f"{a} (now)" if a == _your_age
                                            else f"{a} (after the move)"),
                    help="Before a move, extra principal mostly just raises your sale "
                         "proceeds; after it, it attacks the new loan.")
            else:
                start = _your_age
            set_override(st, "EXTRA_MORTGAGE_PAYMENT_START_AGE", safe_int(start))

            # Instant feedback: amortisation is deterministic, so this needs no
            # simulation at all.
            try:
                try:
                    from utils.sim_runner import _payoff_projection_for
                except ImportError:  # pragma: no cover
                    from ui.utils.sim_runner import _payoff_projection_for  # type: ignore
                _ov = dict(st.session_state.get("user_overrides", {}) or {})
                # Memoised on just the loan inputs. _payoff_projection_for
                # monkeypatches cfg and recomputes every derived constant, and
                # Streamlit reruns this whole sidebar on EVERY keystroke -- so
                # without a cache a single edit anywhere did that work twice per
                # rerun, mutating global engine state during render for a figure
                # that almost never changes.
                _sig = tuple(_ov.get(k) for k in (
                    "MORTGAGE_BALANCE", "MORTGAGE_YEARS_REMAINING", "MORTGAGE_MONTHLY",
                    "HOUSE_MOVE_ENABLED", "HOUSE_MOVE_AGE", "NEW_MORTGAGE_BALANCE",
                    "NEW_MORTGAGE_YEARS", "MORTGAGE_RATE_FOR_PAYOFF", "YOUR_AGE",
                )) + (safe_int(extra), safe_int(start))
                _memo = st.session_state.setdefault("_bp_payoff_memo", {})
                if _sig in _memo:
                    base, now = _memo[_sig]
                else:
                    base = _payoff_projection_for({**_ov, "EXTRA_MORTGAGE_PAYMENT_ANNUAL": 0}, 0.0)
                    now = _payoff_projection_for(_ov, float(extra))
                    _memo.clear()          # only the current signature is useful
                    _memo[_sig] = (base, now)
                b_age, n_age = base.get("payoff_age"), now.get("payoff_age")
                if b_age and n_age:
                    saved = b_age - n_age
                    interest = (base.get("total_interest") or 0) - (now.get("total_interest") or 0)
                    if saved > 0:
                        st.success(
                            f"Paid off at **{n_age}** instead of {b_age} — "
                            f"**{saved} year{'s' if saved != 1 else ''} earlier**, "
                            f"saving {money_md(interest)} of interest."
                        )
                    else:
                        st.caption(f":gray[Payoff age unchanged at {n_age}.]")
            except Exception:
                pass
            st.caption("See **What if → Mortgage paydown** for what this does to your "
                       "success probability.")
        else:
            set_override(st, "EXTRA_MORTGAGE_PAYMENT_START_AGE", None)
            st.caption("Set an amount to model paying the mortgage down faster. "
                       "Freeing that payment before retirement removes a large fixed "
                       "cost from the years most exposed to a bad market.")

    st.divider()

    # ===== Retirement vacation =====
    _section_label(st, "Retirement vacation (go-go years)")

    ensure_default(st, "bp_vacation_enable",
                   bool(get_override(st, "RETIREMENT_VACATION_ENABLED", False)))
    vacation_on = st.toggle("Plan extra travel spending early in retirement",
                              key="bp_vacation_enable",
                              help="Extra annual spending from retirement until a "
                                   "chosen slow-down age.")
    set_override(st, "RETIREMENT_VACATION_ENABLED", bool(vacation_on))
    if vacation_on:
        c8, c9 = st.columns(2)
        with c8:
            ensure_default(st, "bp_vacation_annual",
                           safe_int(get_override(st, "RETIREMENT_VACATION_ANNUAL", 20_000), 20_000))
            v = st.number_input("Annual amount ($)", min_value=0, max_value=200_000,
                                step=1_000, key="bp_vacation_annual")
            set_override(st, "RETIREMENT_VACATION_ANNUAL", safe_int(v))
        with c9:
            ensure_default(st, "bp_vacation_until",
                           safe_int(get_override(st, "RETIREMENT_VACATION_UNTIL_AGE", 75), 75))
            v = st.number_input("Until age (slow-down)", min_value=50, max_value=100,
                                step=1, key="bp_vacation_until")
            set_override(st, "RETIREMENT_VACATION_UNTIL_AGE", safe_int(v))
        st.caption("Extra spending on top of normal expenses, from retirement age "
                   "until the slow-down age.")


def render(st) -> None:
    with st.expander("Big purchases & goals", expanded=False, icon=":material/shopping_bag:"):
        render_body(st)
