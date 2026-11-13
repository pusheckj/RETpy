"""Section: House -- where you live, planned moves and extra mortgage payments.

  - Housing: rent or own today, and the loan on the home you own.
  - Home moves: a list of dated events (cfg.HOME_EVENTS): buy a home, sell and
    buy another, sell and rent, plus the two fields that apply to every move.
  - Extra mortgage principal: yearly prepayment and when it starts.

A summary at the top shows this year's housing cost and the age the mortgage is
paid off. It is drawn last (into a slot at the top) so it never lags an edit.
"""
from __future__ import annotations

try:
    from utils.section_icon import section_expander
except ImportError:  # pragma: no cover
    from ui.utils.section_icon import section_expander  # type: ignore

try:
    from utils.coerce import safe_int, safe_float, ensure_default
    from utils.formatting import money_md
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money_md  # type: ignore

try:
    from utils.overrides import get_override, set_override
    from utils.derived import housing_timeline, mortgage_schedule, extra_mortgage_for_age
    from components.sec_expenses import _money_input
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore
    from ui.utils.derived import (housing_timeline, mortgage_schedule,  # type: ignore
                                  extra_mortgage_for_age)
    from ui.components.sec_expenses import _money_input  # type: ignore

# Plain-language choices for a move, by what you have just before it.
try:
    from utils.slider_input import slider_with_box
except ImportError:  # pragma: no cover
    from ui.utils.slider_input import slider_with_box  # type: ignore


_RENTING_CHOICES = ("Buy a home", "Move to another rental")
_OWNING_CHOICES = ("Sell, buy another", "Sell and rent")
_MEDIAN_HOME_PRICE = 420_000      # US median existing-home price, a starting point


def _section_label(st, txt):
    st.markdown(f'<div style="font-size: 13px; color: #64748b; text-transform: uppercase; '
                f'letter-spacing: 0.05em; margin: 12px 0 6px 0;">{txt}</div>',
                unsafe_allow_html=True)


def _housing(st) -> None:
    """Rent or own today, and the loan on the home you own."""
    _section_label(st, "Housing")
    # Own when there is a home value or a payment (cfg.is_renter's rule): a mortgage
    # with no home value is still a housing cost, and "Renting" would erase it.
    owns_default = (safe_int(get_override(st, "HOME_VALUE", 0), 0) > 0
                    or safe_int(get_override(st, "MORTGAGE_MONTHLY", 0), 0) > 0)
    ensure_default(st, "se_rent_own", "Own home" if owns_default else "Renting")
    status = st.radio("Rent or own?", ["Renting", "Own home"], horizontal=True, key="se_rent_own")
    owns = status == "Own home"

    if owns:
        c1, c2 = st.columns(2, vertical_alignment="bottom")
        with c1:
            _money_input(st, "Home value", "se_home_value", "HOME_VALUE",
                         800_000, 10_000_000, 10_000)
        with c2:
            _money_input(st, "Monthly mortgage payment", "se_mortgage_monthly",
                         "MORTGAGE_MONTHLY", 3_000, 20_000, 100)
        _money_input(st, "Mortgage balance", "se_mortgage_balance",
                     "MORTGAGE_BALANCE", 500_000, 5_000_000, 10_000)
        yrs_default = max(0, min(40, safe_int(get_override(st, "MORTGAGE_YEARS_REMAINING", 28), 28)))
        ensure_default(st, "se_mortgage_years", yrs_default)
        v = slider_with_box(st, "Years left on mortgage", 0, 40, 1, key="se_mortgage_years",
                            unit=" yr",
                            help="How many more years of payments you have on the loan.")
        set_override(st, "MORTGAGE_YEARS_REMAINING", safe_int(v))
        if safe_int(get_override(st, "MORTGAGE_BALANCE", 0), 0) > 0:
            ensure_default(st, "se_mortgage_rate",
                           safe_float(get_override(st, "MORTGAGE_RATE_FOR_PAYOFF", 0.065), 0.065) * 100)
            v = st.number_input("Mortgage interest rate (%)", min_value=0.0, max_value=20.0,
                                step=0.25, format="%.2f", key="se_mortgage_rate",
                                help="On your mortgage statement. Sets how fast you pay down "
                                     "the loan, so how much you'd keep if you sold.")
            set_override(st, "MORTGAGE_RATE_FOR_PAYOFF", round(v / 100, 6))
        # Clear rent if owning
        set_override(st, "SPEND_RENT_MONTHLY", 0)
    else:
        for k in ("HOME_VALUE", "MORTGAGE_BALANCE", "MORTGAGE_MONTHLY", "MORTGAGE_YEARS_REMAINING"):
            set_override(st, k, 0)
        _money_input(st, "Monthly rent", "se_rent_monthly", "SPEND_RENT_MONTHLY",
                     1_500, 20_000, 50)


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
    events = sorted(_events(st) + legacy, key=lambda e: e.get("age", 0))
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
                              help="Under 20% down usually adds PMI. The plan doesn't "
                                   "charge it separately.") / 100
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
                f"This loan runs until **{payoff}**, **{payoff - ret} {'year' if payoff - ret == 1 else 'years'} into "
                f"retirement** (you plan to retire at {ret}). Those payments come "
                f"out of your savings. A shorter term costs more each month while "
                f"you work, but can let you retire *sooner*. Try both."
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
               + " (set above). Add a move to buy, sell or start renting later.")
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
                            help="Yearly cost as a percent of the home's value. It's added to "
                                 "the monthly payment and continues after the loan is "
                                 "paid off. California is about 1.1% tax plus 0.25% insurance.")
        set_override(st, "NEW_HOME_ESCROW_PCT", v / 100)
    if owns_today and stored:
        value = safe_int(ov.get("HOME_VALUE", 0), 0)
        basis = get_override(st, "HOME_COST_BASIS", None)
        ensure_default(st, "bp_home_cost_basis", value if basis is None else safe_int(basis))
        v = safe_int(st.number_input(
            "What you paid for your home ($)", min_value=0, max_value=20_000_000, step=10_000,
            key="bp_home_cost_basis",
            help="Include improvements. When you sell, a gain above $250,000 per owner "
                 "($500,000 for a married couple) is taxed. If you're not sure, "
                 "leave it at the home's value."))
        set_override(st, "HOME_COST_BASIS", None if v == value else v)
    st.caption("Sale proceeds (price minus loan balance, selling costs and any tax) go "
               "into your savings. Down payments and moving costs come out of them.")


def _extra_principal(st) -> None:
    # Deliberately OUTSIDE the house-move block: extra principal applies to
    # whichever loan you currently hold. Placed right after the "this loan
    # outlives your working years" warning because it is the direct remedy.
    _section_label(st, "Extra mortgage principal")
    _ov_now = st.session_state.get("user_overrides", {}) or {}
    _loan_ages = [e["age"] for e in housing_timeline(_ov_now)
                  if e["action"] != "sell_rent" and e["loan"] > 0]
    _has_loan = safe_int(get_override(st, "MORTGAGE_BALANCE", 0), 0) > 0 or bool(_loan_ages)
    if not _has_loan:
        st.caption("You have no mortgage, so there's nothing to pay down.")
    else:
        ensure_default(st, "bp_extra_mortgage",
                       safe_int(get_override(st, "EXTRA_MORTGAGE_PAYMENT_ANNUAL", 0), 0))
        extra = st.number_input(
            "Extra principal per year ($)", min_value=0, max_value=300_000, step=1_000,
            key="bp_extra_mortgage",
            help="Paid on top of your regular payment. That money isn't "
                 "invested, and your regular payment stops once the loan is "
                 "paid off.")
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
                    help="Before a move, extra payments mostly just raise your sale "
                         "proceeds. After it, they pay down the new loan.")
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
                            f"Paid off at **{n_age}** instead of {b_age}, "
                            f"**{saved} year{'s' if saved != 1 else ''} earlier**. "
                            f"You save {money_md(interest)} of interest."
                        )
                    else:
                        st.caption(f"Payoff age unchanged at {n_age}.")
            except Exception:
                pass
            st.caption("See **What if → Mortgage paydown** for the effect on your "
                       "chance of success.")
        else:
            set_override(st, "EXTRA_MORTGAGE_PAYMENT_START_AGE", None)
            st.caption("Enter an amount to see the effect of paying off your mortgage "
                       "sooner. Having no payment in retirement lowers your fixed "
                       "costs when a bad market hurts most.")


def house_summary(overrides: dict) -> dict:
    """This year's housing cost and when the mortgage is paid off, from the same
    schedule the charts use (``derived.mortgage_schedule``).

    ``kind`` is "rent", "mortgage" or "owned" (a home with no loan, which still
    pays property tax and insurance). ``monthly`` is the scheduled payment, the
    rent, or that tax and insurance; ``monthly_extra`` is this year's extra
    principal. ``payoff_age`` and ``payoff_age_no_extra`` are None when there is
    no loan to pay off."""
    age = safe_int(overrides.get("YOUR_AGE", 30), 30)
    ages = range(age, 101)
    now = mortgage_schedule(overrides, ages)
    plain = mortgage_schedule({**overrides, "EXTRA_MORTGAGE_PAYMENT_ANNUAL": 0}, ages)
    year = now["by_age"][age]
    has_loan = now["payoff_age"] is not None and now["payoff_age"] > age
    return {"kind": ("rent" if not year["owns"] else "mortgage" if year["balance"] > 0 else "owned"),
            "monthly": (year["housing"] - year["extra"]) / 12.0,
            "monthly_extra": extra_mortgage_for_age(overrides, age) / 12.0 if year["extra"] > 0 else 0.0,
            "payoff_age": now["payoff_age"] if has_loan else None,
            "payoff_age_no_extra": plain["payoff_age"] if has_loan else None}


_COST_OF = {"rent": "rent", "mortgage": "mortgage payment, with property tax and insurance",
            "owned": "property tax and insurance, no mortgage"}


def _summary_lines(s: dict) -> list:
    first = f"Housing costs {money_md(s['monthly'])}/mo this year: {_COST_OF[s['kind']]}."
    if s["monthly_extra"] > 0:
        first += f" Plus {money_md(s['monthly_extra'])}/mo extra principal."
    lines = [first]
    if s["payoff_age"] is not None:
        line = f"Mortgage paid off at {s['payoff_age']}"
        if s["payoff_age_no_extra"] not in (None, s["payoff_age"]):
            line += f" with your extra payments, {s['payoff_age_no_extra']} without"
        lines.append(line + ".")
    return lines


def render_body(st) -> None:
    summary_slot = st.container()
    _housing(st)
    st.divider()
    _home_moves(st)
    st.divider()
    _extra_principal(st)
    with summary_slot:
        summary = house_summary(st.session_state.get("user_overrides", {}) or {})
        if summary["kind"] == "rent" and st.session_state.get("se_rent_own") == "Own home":
            # "Own home" is picked but no home or payment is entered yet, so the
            # plan still treats you as a renter; don't print a rent line for it.
            st.caption("Enter your home value and mortgage payment to include your housing costs.")
        else:
            st.caption("  \n".join(_summary_lines(summary)))


def render(st) -> None:
    with section_expander(st, "House", "home"):
        render_body(st)
