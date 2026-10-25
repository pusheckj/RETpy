"""Section: Big purchases & goals — car, home moves, retirement vacation.

Optional lifecycle events, each OFF / empty by default so the baseline
simulation is unaffected until a user explicitly opts in:
  - Car: one-time purchase and/or recurring replacement (paid cash from
    the portfolio).
  - Home moves: a list of dated events (cfg.HOME_EVENTS) — buy a home, sell
    and buy another, sell and rent. Today's home is set in Expenses.
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
    from utils.derived import housing_timeline
except ImportError:  # pragma: no cover
    from ui.utils.derived import housing_timeline  # type: ignore

# Plain-language choices for a move, by what you have just before it.
_RENTING_CHOICES = ("Buy a home", "Move to another rental")
_OWNING_CHOICES = ("Sell and buy another home", "Sell and rent")
_MEDIAN_HOME_PRICE = 420_000      # US median existing-home price, a starting point


def _section_label(st, txt):
    st.markdown(f'<div style="font-size: 13px; color: #64748b; text-transform: uppercase; '
                f'letter-spacing: 0.05em; margin: 12px 0 6px 0;">{txt}</div>',
                unsafe_allow_html=True)


def _migrate_legacy_move(st) -> None:
    """Show an old plan's single house move (HOUSE_MOVE_*) in the moves list.

    It becomes one HOME_EVENTS entry carrying the plan's exact loan and payment,
    so its results don't move, and the old switch is turned off."""
    ov = st.session_state.get("user_overrides", {}) or {}
    if not ov.get("HOUSE_MOVE_ENABLED"):
        return
    legacy = housing_timeline({**ov, "HOME_EVENTS": []})
    for e in legacy:
        e["down_pct"] = round(1.0 - e["loan"] / e["price"], 4) if e["price"] > 0 else 0.0
    events = sorted(list(ov.get("HOME_EVENTS") or []) + legacy, key=lambda e: e.get("age", 0))
    set_override(st, "HOME_EVENTS", events)
    set_override(st, "HOUSE_MOVE_ENABLED", False)


def _clear_move_widgets(st) -> None:
    for k in [k for k in list(st.session_state.keys())
              if isinstance(k, str) and k.startswith("bp_ev")]:
        del st.session_state[k]


def _events(st) -> list:
    return [dict(e) for e in (get_override(st, "HOME_EVENTS", None) or []) if isinstance(e, dict)]


def _owns_after(st, events, upto: int) -> bool:
    """Owning (True) or renting just before events[upto], in age order."""
    ov = st.session_state.get("user_overrides", {}) or {}
    owns = safe_int(ov.get("HOME_VALUE", 0), 0) > 0 or safe_int(ov.get("MORTGAGE_MONTHLY", 0), 0) > 0
    target = events[upto]
    for j, e in sorted(enumerate(events), key=lambda je: (safe_int(je[1].get("age"), 0), je[0])):
        if e is target:
            break
        owns = e.get("action") != "sell_rent"
    return owns


def _add_move(st) -> None:
    events = _events(st)
    your_age = safe_int(get_override(st, "YOUR_AGE", 30), 30)
    last = max([safe_int(e.get("age"), your_age) for e in events] + [your_age])
    owns = (_owns_after(st, events + [{"age": 10 ** 6}], len(events)) if events else
            safe_int(get_override(st, "HOME_VALUE", 0), 0) > 0
            or safe_int(get_override(st, "MORTGAGE_MONTHLY", 0), 0) > 0)
    price = safe_int(get_override(st, "HOME_VALUE", 0), 0) if owns else 0
    events.append({"age": last + 5, "action": "sell_buy" if owns else "buy",
                   "price": price or _MEDIAN_HOME_PRICE, "down_pct": 0.20,
                   "rate": 0.065, "years": 30,
                   "costs": safe_int(get_override(st, "HOUSE_MOVING_COSTS", 10_000), 10_000),
                   "selling_cost_pct": safe_float(get_override(st, "HOME_SELLING_COST_PCT", 0.06), 0.06)})
    set_override(st, "HOME_EVENTS", events)
    _clear_move_widgets(st)


def _remove_move(st, i: int) -> None:
    events = _events(st)
    if 0 <= i < len(events):
        events.pop(i)
    set_override(st, "HOME_EVENTS", events)
    _clear_move_widgets(st)


def _num_input(st, label, key, value, **kw):
    ensure_default(st, key, value)
    return st.number_input(label, key=key, **kw)


def _move_row(st, i: int, event: dict, owns_before: bool) -> dict:
    """Inputs for one move; returns the event to store."""
    choices = _OWNING_CHOICES if owns_before else _RENTING_CHOICES
    ensure_default(st, f"bp_ev{i}_kind", 1 if event.get("action") == "sell_rent" else 0)
    kind = st.selectbox("Move", (0, 1), key=f"bp_ev{i}_kind",
                        format_func=lambda k: choices[k])
    c2, _ = st.columns(2, vertical_alignment="bottom")
    with c2:
        age = _num_input(st, "At age", f"bp_ev{i}_age", safe_int(event.get("age"), 40),
                         min_value=18, max_value=100, step=1)
    out = {"age": safe_int(age), "costs": event.get("costs"),
           "selling_cost_pct": event.get("selling_cost_pct")}
    if kind == 1:
        out["action"] = "sell_rent"
        c3, c4 = st.columns(2, vertical_alignment="bottom")
        with c3:
            out["rent"] = safe_int(_num_input(st, "New rent ($/mo)", f"bp_ev{i}_rent",
                                              safe_int(event.get("rent"), 2_000),
                                              min_value=0, max_value=50_000, step=50))
        with c4:
            out["costs"] = safe_int(_num_input(st, "Moving costs ($)", f"bp_ev{i}_costs",
                                               safe_int(event.get("costs"), 5_000),
                                               min_value=0, max_value=200_000, step=1_000))
    else:
        out["action"] = "sell_buy" if owns_before else "buy"
        price0 = safe_int(event.get("price"), _MEDIAN_HOME_PRICE)
        down0 = event.get("down_pct")
        if down0 is None:
            loan0 = safe_float(event.get("loan"), price0 * 0.8)
            down0 = 1.0 - loan0 / price0 if price0 > 0 else 0.2
        rate0 = safe_float(event.get("rate"), 0.065)
        years0 = safe_int(event.get("years"), 30)
        c3, c4 = st.columns(2, vertical_alignment="bottom")
        with c3:
            price = safe_int(_num_input(st, "Home price ($)", f"bp_ev{i}_price", price0,
                                        min_value=0, max_value=20_000_000, step=10_000))
        with c4:
            rate = _num_input(st, "Mortgage rate (%)", f"bp_ev{i}_rate",
                              round(rate0 * 100, 2), min_value=0.0, max_value=20.0,
                              step=0.25, format="%.2f") / 100
        c5, c6 = st.columns(2, vertical_alignment="bottom")
        with c5:
            down = _num_input(st, "Down payment (%)", f"bp_ev{i}_down",
                              round(safe_float(down0, 0.2) * 100, 2), min_value=0.0,
                              max_value=100.0, step=1.0,
                              help="Below 20% typically adds PMI, which this model "
                                   "does not charge separately.") / 100
        with c6:
            years = safe_int(_num_input(st, "Loan term (years)", f"bp_ev{i}_years", years0,
                                        min_value=1, max_value=40, step=1))
        costs = safe_int(_num_input(st, "Buying and moving costs ($)", f"bp_ev{i}_costs",
                                    safe_int(event.get("costs"), 10_000),
                                    min_value=0, max_value=500_000, step=1_000))
        out.update(price=price, down_pct=round(down, 6), rate=round(rate, 6), years=years,
                   costs=costs)
        # A move carried over from an old plan keeps its exact loan and payment
        # until one of its numbers is edited.
        same = (price == price0 and abs(down - safe_float(down0, 0.2)) < 5e-5
                and abs(rate - rate0) < 5e-7 and years == years0)
        if same and event.get("loan") is not None and event.get("monthly") is not None:
            out.update(loan=event["loan"], monthly=event["monthly"])
    if owns_before:
        out["selling_cost_pct"] = round(_num_input(
            st, "Selling costs (%)", f"bp_ev{i}_sell",
            round(safe_float(event.get("selling_cost_pct"),
                             safe_float(get_override(st, "HOME_SELLING_COST_PCT", 0.06), 0.06)) * 100, 2),
            min_value=0.0, max_value=20.0, step=0.5,
            help="Agent fees and closing costs on the sale.") / 100, 6)
    return {k: v for k, v in out.items() if v is not None}


def _move_summary(st, event: dict, owns_before: bool) -> None:
    """One plain line on what the move does, from the engine's own resolution."""
    ov = st.session_state.get("user_overrides", {}) or {}
    resolved = housing_timeline({**ov, "HOUSE_MOVE_ENABLED": False, "HOME_EVENTS": [event]})
    if not resolved:
        return
    e = resolved[0]
    if e["age"] < safe_int(ov.get("YOUR_AGE", e["age"]), e["age"]):
        st.caption(":orange[This age has already passed, so the move won't happen.]")
    sale = "Sell your home, then " if owns_before else ""
    if e["action"] == "sell_rent":
        st.caption(f"{sale}rent for {money_md(e['rent'])}/mo from {e['age']}.")
        return
    down = max(0.0, e["price"] - e["loan"])
    # NOTE: escape every literal "$" -- money_md does it; Streamlit's markdown
    # renders $...$ as LaTeX math.
    st.caption(f"{sale}buy for {money_md(e['price'])}: {money_md(down)} down, loan "
               f"{money_md(e['loan'])}, {money_md(e['monthly'])}/mo with tax and insurance.")
    if e["loan"] > 0:
        payoff = e["age"] + e["years"]
        ret = safe_int(get_override(st, "TARGET_RETIREMENT_AGE", 60), 60)
        if payoff > ret:
            st.warning(
                f"This loan is paid off at **{payoff}**, **{payoff - ret} years into "
                f"retirement** (you target {ret}). Those payments come out of your "
                f"savings. A shorter term costs more per month while you're earning "
                f"but often lets you retire *sooner*, so it's worth testing both."
            )


def _home_moves(st) -> None:
    """Planned moves: buy, sell and buy, sell and rent (cfg.HOME_EVENTS)."""
    _section_label(st, "Home moves")
    _migrate_legacy_move(st)
    ov = st.session_state.get("user_overrides", {}) or {}
    owns_today = safe_int(ov.get("HOME_VALUE", 0), 0) > 0 or safe_int(ov.get("MORTGAGE_MONTHLY", 0), 0) > 0
    st.caption("Today you " + (f"own a home worth {money_md(safe_int(ov.get('HOME_VALUE', 0), 0))}"
                               if owns_today else
                               f"rent for {money_md(safe_int(ov.get('SPEND_RENT_MONTHLY', 0), 0))}/mo")
               + " (set in Expenses). Add a move to buy, sell or start renting later.")
    events = _events(st)
    stored = []
    for i, event in enumerate(events):
        with st.container(border=True):
            owns_before = _owns_after(st, stored + events[i:], i)   # this run's edits so far
            new_event = _move_row(st, i, event, owns_before)
            _move_summary(st, new_event, owns_before)
            st.button("Remove this move", key=f"bp_ev{i}_del", type="tertiary",
                      on_click=_remove_move, args=(st, i))
        stored.append(new_event)
    if stored != events:
        set_override(st, "HOME_EVENTS", stored)
    st.button("Add a move", key="bp_add_move", on_click=_add_move, args=(st,),
              icon=":material/add_home:")

    buys = [e for e in stored if e.get("action") != "sell_rent"]
    if buys or (owns_today and stored):
        st.caption("Applies to all your moves:")
    if buys:
        ensure_default(st, "bp_new_home_escrow_pct",
                       safe_float(get_override(st, "NEW_HOME_ESCROW_PCT", 0.0135), 0.0135) * 100)
        v = st.number_input("Property tax + insurance (%/yr)", min_value=0.0, max_value=5.0,
                            step=0.05, key="bp_new_home_escrow_pct",
                            help="Percent of the home's value per year, added to the "
                                 "monthly payment and kept once the loan is paid off. "
                                 "Varies by state (California is about 1.1% tax + 0.25% insurance).")
        set_override(st, "NEW_HOME_ESCROW_PCT", v / 100)
    if owns_today and stored:
        value = safe_int(ov.get("HOME_VALUE", 0), 0)
        basis = get_override(st, "HOME_COST_BASIS", None)
        ensure_default(st, "bp_home_cost_basis", value if basis is None else safe_int(basis))
        v = safe_int(st.number_input(
            "What you paid for your home ($)", min_value=0, max_value=20_000_000, step=10_000,
            key="bp_home_cost_basis",
            help="Include improvements. When you sell, a gain above $250,000 per owner "
                 "($500,000 for a married couple) is taxed. Leave it at the home's "
                 "value if you're not sure."))
        set_override(st, "HOME_COST_BASIS", None if v == value else v)
    st.caption("Sale money (price − loan left − selling costs − any tax) goes into your "
               "savings; down payments and moving costs come out of them.")


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
        c1, c2 = st.columns(2, vertical_alignment="bottom")
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
        c3, c4 = st.columns(2, vertical_alignment="bottom")
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
        ensure_default(st, "bp_car_recurring_amount",
                       safe_int(get_override(st, "CAR_RECURRING_AMOUNT", 40_000), 40_000))
        v = st.number_input("Amount ($)", min_value=0, max_value=500_000,
                            step=1_000, key="bp_car_recurring_amount")
        set_override(st, "CAR_RECURRING_AMOUNT", safe_int(v))
        st.caption("Replaces the car every N years starting at the given age, "
                   "paid from the portfolio.")

    st.divider()

    # ===== Home moves =====
    _home_moves(st)

    st.divider()

    # ===== Extra mortgage principal =====
    # Deliberately OUTSIDE the house-move block: extra principal applies to
    # whichever loan you currently hold. Placed right after the "this loan
    # outlives your working years" warning because it is the direct remedy.
    _section_label(st, "Extra mortgage principal")
    _ov_now = st.session_state.get("user_overrides", {}) or {}
    _loan_ages = [e["age"] for e in housing_timeline(_ov_now)
                  if e["action"] != "sell_rent" and e["loan"] > 0]
    _has_loan = safe_int(get_override(st, "MORTGAGE_BALANCE", 0), 0) > 0 or bool(_loan_ages)
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
            # Offer "start at the purchase" because that is when the big new
            # loan appears; paying down a house you're about to sell only raises
            # the sale proceeds (and a renter has nothing to pay down before).
            _move_age = min((a for a in _loan_ages if a > _your_age), default=0)
            _opts = [_your_age] + ([_move_age] if _move_age else [])
            ensure_default(st, "bp_extra_mortgage_start",
                           safe_int(get_override(st, "EXTRA_MORTGAGE_PAYMENT_START_AGE",
                                                 _your_age) or _your_age, _your_age))
            if len(_opts) > 1:
                start = st.radio(
                    "Start paying extra at age", _opts, horizontal=True,
                    key="bp_extra_mortgage_start_radio",
                    format_func=lambda a: (f"{a} (now)" if a == _your_age
                                            else f"{a} (after you buy)"),
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
                    "MORTGAGE_RATE_FOR_PAYOFF", "YOUR_AGE",
                )) + (repr(housing_timeline(_ov)), safe_int(extra), safe_int(start))
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
                       "success rate.")
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
                                   "chosen slow-down age. It is on top of the "
                                   "\"Extra for travel and hobbies\" in Retirement goals.")
    set_override(st, "RETIREMENT_VACATION_ENABLED", bool(vacation_on))
    if vacation_on:
        c8, c9 = st.columns(2, vertical_alignment="bottom")
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
