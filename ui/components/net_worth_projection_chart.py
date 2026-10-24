"""Projected net worth by account — stacked bar chart, no Monte Carlo.

Deterministic forward projection: each account's balance grows at a
configurable expected real return + receives the user's annual contribution.
Reads directly from ``st.session_state.user_overrides`` so it auto-updates
as the user edits sidebar inputs (no Run needed).

The projection covers today → retirement age. After retirement we don't
project further here (retirement decumulation is shown by the Monte Carlo
fan chart and the withdrawal drawdown chart).
"""
from __future__ import annotations

import contextlib

import plotly.graph_objects as go

try:
    from retirement_sim import config as cfg
except ImportError:  # pragma: no cover
    cfg = None  # type: ignore

try:
    from utils.coerce import safe_int, safe_float
    from utils.derived import (advance_mortgage_with_extra, current_mortgage_terms,
                               mortgage_payment, housing_timeline,
                               extra_mortgage_for_age as _extra_for_age,
                               savings_budget, AUTO_ALLOCATE_MODE, KEEP_AMOUNTS_MODE)
    from utils.formatting import money
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float  # type: ignore
    from ui.utils.derived import (advance_mortgage_with_extra,  # type: ignore
                                  current_mortgage_terms, mortgage_payment, housing_timeline,
                                  extra_mortgage_for_age as _extra_for_age,
                                  savings_budget, AUTO_ALLOCATE_MODE, KEEP_AMOUNTS_MODE)
    from ui.utils.formatting import money  # type: ignore


try:
    from utils.plot_theme import assign_colors, PLOTLY_CONFIG
except ImportError:  # pragma: no cover
    from ui.utils.plot_theme import assign_colors, PLOTLY_CONFIG  # type: ignore


# Account display order (bottom → top of stack) and keys. Colors are
# assigned from the shared active palette at render time (see render()).
ACCOUNTS = [
    ("Your 401(k)",        "YOUR_401K",            "YOUR_401K_CONTRIBUTION",        None),
    ("Your Roth IRA",      "YOUR_ROTH_IRA",        "YOUR_BACKDOOR_ROTH",            None),
    ("Your Traditional IRA","YOUR_TRADITIONAL_IRA", None,                           None),
    ("Your HSA",           "YOUR_HSA",             "YOUR_HSA_CONTRIBUTION",         None),
    ("Your Brokerage",     "YOUR_BROKERAGE",       "YOUR_BROKERAGE_CONTRIBUTION",   None),
    ("Your Cash",          "YOUR_CASH",            None,                            None),
    ("Partner 401(k)",     "PARTNER_401K",         "PARTNER_401K_CONTRIBUTION",     None),
    ("Partner Roth IRA",   "PARTNER_ROTH_IRA",     "PARTNER_ROTH_CONTRIBUTION",     None),
    ("Partner Brokerage",  "PARTNER_BROKERAGE",    "PARTNER_BROKERAGE_CONTRIBUTION",None),
    ("Partner Cash",       "PARTNER_CASH",         None,                            None),
    ("Home equity",        "_HOME_EQUITY",         None,                            None),  # special-cased
]


# Per-asset-class real expected returns by scenario. Used for the
# deterministic projection (no volatility — single forward path).
_SCENARIO_RETURNS = {
    "conservative": {"investment": 0.055, "cash": 0.005, "home": 0.005},
    "historical":   {"investment": 0.075, "cash": 0.010, "home": 0.010},
    "pessimistic": {"investment": 0.040, "cash": 0.000, "home": 0.000},
}


def _expected_return_for(account_label: str, scenario_returns: dict) -> float:
    """Return the deterministic real return for a given account label."""
    if "Cash" in account_label:
        return scenario_returns["cash"]
    if account_label == "Home equity":
        return scenario_returns["home"]
    return scenario_returns["investment"]


def _employer_match(overrides: dict, age_offset: int, deferral: float = None) -> float:
    """Approximate annual employer 401(k) match in real dollars: dollar for
    dollar on your ``deferral``, up to the match % of base pay -- the
    simulation's rule (account_simulation.working_year_cashflow)."""
    base = safe_int(overrides.get("YOUR_BASE_SALARY", 0), 0)
    if base == 0:
        # fall back to a 55% slice of household income
        base = int(safe_int(overrides.get("HOUSEHOLD_INCOME_QUICK", 85_000), 85_000) * 0.55)
    growth = safe_float(overrides.get("YOUR_SALARY_GROWTH_RATE", 0.02), 0.02)
    salary = base * ((1 + growth) ** age_offset)
    match_pct = safe_float(overrides.get("YOUR_401K_MATCH_PCT", 0.04), 0.04)
    if deferral is None:
        return salary * match_pct
    return min(float(deferral), salary * match_pct)


# --- Big-purchase / goal event helpers -------------------------------------
# These read the toggle + values from ``user_overrides`` (falling back to the
# engine cfg defaults) and REUSE the engine cfg helpers so the event logic is
# not re-implemented here. The cfg helpers read module-level globals, so we
# temporarily patch those globals for the duration of the call and restore them
# afterwards — that way toggling an event in the sidebar drives exactly the same
# math the Monte Carlo engine uses.

# cfg attributes each helper depends on (so we only patch what we need).
_CAR_CFG_KEYS = (
    "CAR_ONETIME_ENABLED", "CAR_ONETIME_AGE", "CAR_ONETIME_AMOUNT",
    "CAR_RECURRING_ENABLED", "CAR_RECURRING_START_AGE",
    "CAR_RECURRING_EVERY_YEARS", "CAR_RECURRING_AMOUNT",
)
_VACATION_CFG_KEYS = (
    "RETIREMENT_VACATION_ENABLED", "RETIREMENT_VACATION_ANNUAL",
    "RETIREMENT_VACATION_UNTIL_AGE",
)


@contextlib.contextmanager
def _cfg_patched(overrides: dict, keys):
    """Temporarily set the given cfg globals from ``overrides`` (fallback: the
    existing cfg value) so the engine helpers see the user's live inputs.
    Restores the originals on exit."""
    if cfg is None:  # pragma: no cover - cfg always importable in the app
        yield
        return
    saved = {}
    try:
        for k in keys:
            saved[k] = getattr(cfg, k, None)
            if k in overrides:
                setattr(cfg, k, overrides[k])
        yield
    finally:
        for k, v in saved.items():
            setattr(cfg, k, v)


def _car_outlay(overrides: dict, age: int) -> float:
    """Car cash outlay in ``age``'s year, via cfg.calculate_car_purchase."""
    if cfg is None:  # pragma: no cover
        return 0.0
    if not (bool(overrides.get("CAR_ONETIME_ENABLED", getattr(cfg, "CAR_ONETIME_ENABLED", False)))
            or bool(overrides.get("CAR_RECURRING_ENABLED", getattr(cfg, "CAR_RECURRING_ENABLED", False)))):
        return 0.0
    with _cfg_patched(overrides, _CAR_CFG_KEYS):
        return float(cfg.calculate_car_purchase(age))


def _vacation_outlay(overrides: dict, age: int, retirement_age: int) -> float:
    """Retirement-vacation cash outlay via cfg.calculate_retirement_vacation."""
    if cfg is None:  # pragma: no cover
        return 0.0
    if not bool(overrides.get("RETIREMENT_VACATION_ENABLED",
                              getattr(cfg, "RETIREMENT_VACATION_ENABLED", False))):
        return 0.0
    with _cfg_patched(overrides, _VACATION_CFG_KEYS):
        return float(cfg.calculate_retirement_vacation(age, retirement_age))


_DRAW_ORDER_TAIL = ("Partner Cash", "Your Brokerage", "Partner Brokerage",
                    "Your 401(k)", "Partner 401(k)")


def _draw_from_balances(balances: dict, need: float, cash_label: str) -> float:
    """Spend `need` from liquid balances, cash first. Returns the amount funded.

    Every outflow in this projection must route through here. A bare
    ``max(0.0, cash - need)`` silently discards whatever cash could not cover,
    which CREATES net worth out of nothing -- measured at ~$16k in a single year
    once a mortgage prepayment drew cash down far enough for the next car outlay
    to hit the floor. Returning the funded amount lets callers that move money
    (e.g. extra mortgage principal) keep both sides of the transfer equal.
    """
    if need <= 0:
        return 0.0
    remaining = need
    for label in (cash_label,) + _DRAW_ORDER_TAIL:
        if remaining <= 0:
            break
        avail = balances.get(label, 0.0)
        if avail <= 0:
            continue
        take = min(avail, remaining)
        balances[label] = avail - take
        remaining -= take
    return need - remaining


def _cfg_default(key, fallback):
    return getattr(cfg, key, fallback) if cfg is not None else fallback


def _ov_hash(d):
    """Hashable key for a user-overrides dict (primitives kept; others stringified)."""
    return tuple(sorted(
        (k, v if isinstance(v, (int, float, str, bool)) or v is None else str(v))
        for k, v in d.items()
    ))


try:
    import streamlit as _stc
    _proj_cache = _stc.cache_data(show_spinner=False, max_entries=64, hash_funcs={dict: _ov_hash})
except Exception:  # pragma: no cover
    def _proj_cache(fn):
        return fn


@_proj_cache
def project_net_worth(user_overrides: dict) -> dict:
    """Deterministic forward projection of each account.

    Returns: {"ages": [...], "by_account": {label: [balance per age, ...]}}

    Cached (@st.cache_data) so toggling "Today / At retirement" or any rerun
    that re-reads the projection is instant instead of recomputing the loop.
    """
    start_age = safe_int(user_overrides.get("YOUR_AGE", 25), 25)
    retirement_age = safe_int(user_overrides.get("TARGET_RETIREMENT_AGE", 60), 60)
    n_years = max(1, retirement_age - start_age + 1)

    # Contributions: the stored amounts, except in the two auto modes, where
    # the simulation invests everything left in the brokerage (no stored
    # brokerage figure): use this year's amounts as the Savings section shows them.
    contributions = dict(user_overrides)
    if user_overrides.get("SAVINGS_MODE") in (AUTO_ALLOCATE_MODE, KEEP_AMOUNTS_MODE):
        contributions.update(savings_budget(user_overrides)["amounts"])

    scenario = str(user_overrides.get("ACTIVE_RETURN_SCENARIO", "historical")).lower()
    if scenario not in _SCENARIO_RETURNS:
        scenario = "historical"
    scenario_returns = _SCENARIO_RETURNS[scenario]

    # SAVINGS_INFLATION_ADJUST is intentionally NOT read here — see the
    # contribution block below for why (this projection is in real dollars).

    # Initialize each account's running balance from today's user input.
    balances = {}
    for label, balance_key, _, _ in ACCOUNTS:
        if balance_key == "_HOME_EQUITY":
            home_value = safe_int(user_overrides.get("HOME_VALUE", 0), 0)
            mortgage = safe_int(user_overrides.get("MORTGAGE_BALANCE", 0), 0)
            balances[label] = max(0.0, float(home_value - mortgage))
        else:
            balances[label] = float(safe_int(user_overrides.get(balance_key, 0), 0))

    by_account = {label: [] for label, _, _, _ in ACCOUNTS}
    ages = []

    events = housing_timeline(user_overrides)    # buy / sell and buy / sell and rent
    cash_label = "Your Cash"
    home_label = "Home equity"

    # Track the property and the loan separately so principal paydown shows up as
    # net worth (see the snapshot below). Rate/P&I are inferred from the stored
    # all-in payment, with escrow removed first.
    _home_value = float(safe_int(user_overrides.get("HOME_VALUE", 0), 0))
    _sale_value = _home_value          # the value a sale's costs are charged on
    _cur = current_mortgage_terms(user_overrides)
    _mort_balance = float(_cur["balance"])
    _mort_rate = float(_cur["rate"])
    _mort_pi = float(_cur["pi_payment"])

    for offset in range(n_years):
        age = start_age + offset
        ages.append(age)

        # --- Big-purchase / goal events happen "in this year" so the bend is
        # visible at this age. Applied BEFORE the snapshot so the drop/jump
        # shows up on the projected line without needing a Run. ---
        # Housing events: realize the net cash flow into cash and switch the
        # tracked property + loan (none after a sale to rent).
        for ev in (e for e in events if e["age"] == age):
            # Equity must come from the CURRENTLY tracked value/principal, not
            # from balances[home_label] -- that dict entry is last year's
            # snapshot, taken before this year's appreciation, amortization and
            # extra principal. Reading it stale DESTROYED the final year of
            # extra principal (charged to cash, never credited to the sale
            # proceeds): a measured $30k vanished at the move.
            old_equity = max(0.0, _home_value - _mort_balance)
            # Selling costs are charged against the home's entered value.
            selling_costs = _sale_value * ev["selling_cost_pct"]
            if ev["action"] == "sell_rent":
                new_equity = 0.0
                _home_value = _sale_value = 0.0
                _mort_balance = _mort_pi = 0.0
            else:
                new_equity = max(0.0, ev["price"] - ev["loan"])
                # Swap the tracked property + loan over to the new house so the
                # new mortgage starts amortizing from this age.
                _home_value = _sale_value = float(ev["price"])
                _mort_balance = float(ev["loan"])
                _mort_rate = float(ev["rate"])
                _mort_pi = mortgage_payment(_mort_balance, _mort_rate, ev["years"])
            # Net cash flow = sale proceeds (old equity, net of selling costs)
            # − down payment on the new home (new equity) − moving costs.
            net_cash_flow = old_equity - selling_costs - new_equity - ev["costs"]
            if net_cash_flow >= 0:
                balances[cash_label] += net_cash_flow
            else:
                # Trading up costs more than the old house released: draw the
                # difference from savings rather than flooring cash at 0, which
                # would hand back the unfunded part as free net worth.
                _draw_from_balances(balances, -net_cash_flow, cash_label)
            balances[home_label] = new_equity

        # Car purchases: cash outlay drawn from cash, then other liquid accounts.
        car = _car_outlay(user_overrides, age)
        if car > 0:
            _draw_from_balances(balances, car, cash_label)

        # Retirement vacation: extra spend drawn from cash during go-go years.
        vac = _vacation_outlay(user_overrides, age, retirement_age)
        if vac > 0:
            _draw_from_balances(balances, vac, cash_label)

        # Home equity is tracked as (home value − remaining mortgage principal)
        # rather than a single balance that only appreciates. Paying a mortgage
        # down IS net-worth accumulation, and ignoring it understated the band by
        # six figures within a decade on a real profile (and by the whole loan at
        # payoff) while the payments were charged as expenses elsewhere.
        balances[home_label] = max(0.0, _home_value - _mort_balance)

        # Year start: snapshot
        for label, _, _, _ in ACCOUNTS:
            by_account[label].append(balances[label])

        # Advance the home a year: appreciate the property, amortize the loan.
        #
        # Extra principal must be applied here AND charged against cash. This
        # projection models no expenses at all (only explicit contributions), so
        # amortising faster WITHOUT the offsetting outflow would grow net worth
        # for free -- phantom wealth. Paying extra principal is a TRANSFER (cash
        # -> home equity) that is net-worth-neutral on the day, and only pays off
        # later through avoided interest. Charging it keeps this chart
        # dollar-conserving and consistent with the engine.
        _extra = 0.0
        if _mort_balance > 0:
            # Paying extra principal is a TRANSFER (cash -> home equity): net
            # worth is unchanged on the day, and only pays off later through
            # avoided interest. So only the portion actually funded may reduce
            # the principal, otherwise the chart mints equity for free.
            _extra = _draw_from_balances(
                balances, min(_extra_for_age(user_overrides, age), _mort_balance),
                cash_label,
            )
        _home_value *= (1.0 + scenario_returns["home"])
        _mort_balance, _extra_used = advance_mortgage_with_extra(
            _mort_balance, _mort_rate, _mort_pi, months=12, extra_annual=_extra)
        if _extra > _extra_used:
            # Payoff year: the loan absorbed less than we drew. Refund the rest
            # instead of letting it evaporate.
            balances[cash_label] += _extra - _extra_used

        # End-of-year: apply contribution + return for next year
        # (Snapshot-then-grow gives a clean t=0..t=N sequence.)
        for label, _, contrib_key, _ in ACCOUNTS:
            if label == home_label:
                continue            # handled above via value − principal
            r = _expected_return_for(label, scenario_returns)
            contribution = 0.0
            if contrib_key is not None and offset < n_years - 1:
                contribution = float(safe_int(contributions.get(contrib_key, 0), 0))
                # NOTE: deliberately NOT scaled by SAVINGS_INFLATION_ADJUST.
                # This loop grows balances at _SCENARIO_RETURNS, which are REAL
                # (inflation-adjusted) returns — see the chart caption. In a real
                # frame an inflation-INDEXED contribution is a CONSTANT, so
                # multiplying by (1.0275 ** offset) compounded a nominal factor
                # onto real dollars (~2.25x by year 30) and made this chart's
                # "At retirement" KPI overstate net worth versus the Monte Carlo.
                # The engine holds cfg.*_CONTRIBUTION flat per year too
                # (account_simulation.simulate_accumulation_year), so flat here
                # is what actually matches the simulation.
                # Add employer match to Your 401(k)
                if contrib_key == "YOUR_401K_CONTRIBUTION":
                    contribution += _employer_match(user_overrides, offset, contribution)
            balances[label] = balances[label] * (1 + r) + contribution

    return {"ages": ages, "by_account": by_account}


def render(st, results: dict = None, chart_key: str = "net_worth_projection_main") -> None:
    overrides = st.session_state.get("user_overrides", {}) or {}
    proj = project_net_worth(overrides)
    ages = proj["ages"]
    if not ages:
        return

    fig = go.Figure()
    # Assign palette colors in series order (bottom → top of stack) at render
    # time so we read the user's active palette.
    account_colors = assign_colors([label for label, _, _, _ in ACCOUNTS], st)
    for label, _, _, _ in ACCOUNTS:
        ys = proj["by_account"][label]
        if not any(v > 0 for v in ys):
            continue
        fig.add_trace(go.Bar(
            x=ages,
            y=ys,
            name=label,
            marker_color=account_colors[label],
            marker_line_width=0,
            hovertemplate="%{fullData.name}: $%{y:,.0f}<extra></extra>",
        ))

    # Totals per age — used for the KPI row below. The stacked-bar height
    # already shows the total, so no separate total trace is drawn.
    totals = [sum(proj["by_account"][label][i] for label, _, _, _ in ACCOUNTS)
              for i in range(len(ages))]

    retirement_age = safe_int(overrides.get("TARGET_RETIREMENT_AGE", 60), 60)
    if ages and ages[0] <= retirement_age <= ages[-1]:
        fig.add_vline(
            x=retirement_age,
            line_dash="dash",
            line_color="#94a3b8",
            annotation_text=f"Retire @ {retirement_age}",
            annotation_position="top",
            annotation_font=dict(size=11, color="#64748b"),
        )

    final_total = totals[-1] if totals else 0.0

    # KPI row above chart
    cols = st.columns(3)
    with cols[0]:
        st.metric("Today", money(totals[0] if totals else 0, shorten=True))
    with cols[1]:
        st.metric(f"At retirement (age {retirement_age})",
                  money(final_total, shorten=True))
    with cols[2]:
        scenario = str(overrides.get("ACTIVE_RETURN_SCENARIO", "historical")).title()
        st.metric("Return scenario", scenario)

    fig.update_layout(
        barmode="stack",
        bargap=0.15,
        title=dict(
            text="<b>Projected net worth by account</b><br>"
                 "<span style='font-size:13px;'>"
                 "Deterministic projection from today through retirement · "
                 "auto-updates as you edit inputs</span>",
            x=0.0, xanchor="left", font=dict(size=16),
        ),
        height=420,
        margin=dict(l=50, r=170, t=80, b=50),
        xaxis=dict(title="Age", zeroline=False, fixedrange=False),
        yaxis=dict(title="Net worth", zeroline=False,
                   tickformat="$,.3~s", rangemode="tozero"),
        hovermode="x unified", dragmode="pan",
        legend=dict(orientation="v", yanchor="top", y=1.0,
                    xanchor="left", x=1.02, bgcolor="rgba(0,0,0,0)"),
        uirevision="keep",
    )

    try:
        from utils.plot_theme import style_fig
    except ImportError:
        from ui.utils.plot_theme import style_fig
    fig = style_fig(fig, st)

    st.plotly_chart(
        fig,
        width="stretch",
        key=chart_key,
        config=PLOTLY_CONFIG,
    )
    st.caption(
        f"Real (inflation-adjusted) return: investment accounts "
        f"{_SCENARIO_RETURNS[str(overrides.get('ACTIVE_RETURN_SCENARIO', 'historical')).lower() if str(overrides.get('ACTIVE_RETURN_SCENARIO', 'historical')).lower() in _SCENARIO_RETURNS else 'historical']['investment']*100:.1f}%, "
        f"cash {_SCENARIO_RETURNS[str(overrides.get('ACTIVE_RETURN_SCENARIO', 'historical')).lower() if str(overrides.get('ACTIVE_RETURN_SCENARIO', 'historical')).lower() in _SCENARIO_RETURNS else 'historical']['cash']*100:.1f}%, "
        f"home equity stays at value−mortgage. The Monte Carlo simulation in the "
        f"Run button below adds return uncertainty + tax-efficient drawdown."
    )
