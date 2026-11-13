"""Freedom milestones: the markers of freedom you have passed, and when the rest arrive.

A section on the planner's results page. It shows

* net worth and invested ladders ($100K, $250K, $500K, $1M, ...),
* Coast FIRE and FIRE in a set of places (US regions and abroad) that you can edit,
* other markers: emergency fund, Lean and Barista FIRE, returns that pay a year of
  costs, mortgage paid off.

The test for each is a quick rule that costs nothing to run (utils/milestones.py).
A place's spending is built per category against where you live now, and moving
there sells your home, then buys or rents at that place's prices (utils/place_costs.py
holds the rough data). Each place has a "Confirm with simulation" button that runs
the real Monte Carlo with the same move, spending, health prices and tax
(sim_runner.plan_place_check), on the server or in the visitor's browser like the
other sweeps.

Edits and custom places are saved in ``user_overrides["MS_PLACES"]`` (utils/places.py),
so they travel with Save/Load, Remember me and profiles. Widget keys start with ``ms_``.
"""
from __future__ import annotations

import html as _html
from datetime import date

try:
    from utils import milestones as ms
    from utils import place_costs as pc
    from utils import places as pl
    from utils.coerce import safe_int, safe_float, ensure_default
    from utils.formatting import money
    from utils.household import has_partner, plan_end_ages
    from utils.sim_runner import _hashable
except ImportError:  # pragma: no cover
    from ui.utils import milestones as ms  # type: ignore
    from ui.utils import place_costs as pc  # type: ignore
    from ui.utils import places as pl  # type: ignore
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money  # type: ignore
    from ui.utils.household import has_partner, plan_end_ages  # type: ignore
    from ui.utils.sim_runner import _hashable  # type: ignore

DEFAULT_RETURN = 0.075       # used only if the net-worth chart's table can't be read


# --------------------------------------------------------------------------- text helpers

def _e(text) -> str:
    """HTML-safe text. Dollar signs become entities so markdown never reads $...$ as math."""
    return _html.escape(str(text), quote=True).replace("$", "&#36;")


def _when(m: "ms.Milestone", end_age=None) -> str:
    """Plain words for when: the state of the milestone and its age."""
    if m.status == ms.REACHED:
        return "Reached"
    if m.status == ms.PROGRESS:
        if m.age is None:
            return "Not yet"
        if m.after_retire:
            return f"Only after you retire: projected at {m.age} ({m.year})"
        return f"Projected at {m.age} ({m.year})"
    return "Not in this plan" + (f" (through {end_age})" if end_age else "")


def _icon(m: "ms.Milestone") -> str:
    return {"reached": "&#10003;", "progress": "&#9654;", "beyond": "&#8212;"}[m.status]


def _bar(m: "ms.Milestone") -> str:
    if m.progress is None:
        return ""
    pct = int(round(100 * m.progress))
    return (f'<div class="ms-bar" role="img" aria-label="{pct} percent there">'
            f'<i style="width:{pct}%"></i></div>')


def _item(m: "ms.Milestone", end_age, is_next: bool, with_detail: bool = True, label=None) -> str:
    cls = f"ms-item is-{m.status}" + (" is-next" if is_next else "")
    pct = f' · {int(round(100 * m.progress))}% there' if (m.progress is not None and m.status != ms.REACHED) else ""
    detail = f'<span class="ms-detail">{_e(m.detail)}</span>' if (with_detail and m.detail) else ""
    nxt = '<span class="ms-tag">Next up</span>' if is_next else ""
    return (f'<li class="{cls}"><span class="ms-dot" aria-hidden="true">{_icon(m)}</span>'
            f'<div class="ms-body"><b class="ms-label">{_e(label or m.label)}</b>{nxt}'
            f'<span class="ms-when">{_e(_when(m, end_age))}{_e(pct)}</span>{detail}{_bar(m)}</div></li>')


def first_in_progress(items):
    """Key of the first item still ahead of you (a ladder's own "next up")."""
    return next((m.key for m in items if m.status == ms.PROGRESS), None)


def ladder_html(title: str, sub: str, items, end_age, next_keys, earlier: int) -> str:
    rows = "".join(_item(m, end_age, m.key in next_keys) for m in items)
    more = (f'<div class="ms-earlier">+ {earlier} smaller {"milestone" if earlier == 1 else "milestones"} '
            f'already passed</div>') if earlier else ""
    return (f'<div class="ms-ladder"><div class="ms-ladder-head"><b>{_e(title)}</b>'
            f'<span>{_e(sub)}</span></div>{more}<ul class="ms-list">{rows}</ul></div>')


def summary_html(rep: "ms.Report", end_age) -> str:
    nxt = rep.next_up
    if nxt is not None:
        tail = (f'<span class="ms-next">Next up: <b>{_e(nxt.label)}</b> at {nxt.age} ({nxt.year})</span>')
    elif rep.reached >= rep.total and rep.total:
        tail = '<span class="ms-next">Every milestone shown is reached.</span>'
    else:
        tail = '<span class="ms-next">None of the rest arrive within this plan.</span>'
    pct = int(round(100 * rep.reached / rep.total)) if rep.total else 0
    return (f'<div class="ms-summary"><div class="ms-count"><b>{rep.reached}</b>'
            f'<span>of {rep.total} reached</span></div>'
            f'<div class="ms-summary-body">{tail}'
            f'<div class="ms-bar" role="img" aria-label="{pct} percent reached"><i style="width:{pct}%"></i></div>'
            f'</div></div>')


_HOUSING_CHIP = {"buy": "Buys a home", "rent": "Rents", "keep": "Keeps your home"}


def _facts(pr: "ms.PlaceResult", ret_age) -> str:
    """The pieces of a place's FIRE test, as label / value rows."""
    c = pr.cost
    rows = [("Spending there", f"{ms.short_money(pr.spend)} a year")]
    if c is not None and not pr.place.here and pr.place.housing != "keep":
        if c.proceeds > 0:
            rows.append(("Home sale frees", ms.short_money(c.proceeds)))
        if c.price > 0:
            buy = ms.short_money(c.price) + (f" (loan {ms.short_money(c.loan)})" if c.loan > 0 else "")
            rows.append(("Home there costs", buy))
        elif c.rent > 0:
            rows.append(("Rent there", f"${c.rent:,.0f} a month"))
    rows.append(("FIRE number", ms.short_money(pr.fire_number)))
    body = "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in rows)
    return f'<dl class="ms-facts">{body}</dl>'


def place_html(pr: "ms.PlaceResult", end_age, next_keys, ret_age=None, owns_home: bool = True) -> str:
    p = pr.place
    tax = pl.tax_label(p.tax, p.abroad)
    rows = "".join(_item(m, end_age, m.key in next_keys, with_detail=False, label=lab)
                   for m, lab in ((pr.coast, "Coast FIRE"), (pr.fire, "FIRE")))
    note = f'<div class="ms-note">{_e(p.note)}</div>' if p.note else ""
    ratio = (pr.cost.ratio if pr.cost is not None else 1.0) * p.adjust
    housing = "keep" if p.here else p.housing
    chip = _HOUSING_CHIP.get(housing, "") if (owns_home or housing != "keep") else "Your plan's housing"
    return (f'<div class="ms-place-head"><b>{_e(p.name)}</b>'
            f'<span class="ms-chip">{_e(chip)}</span>'
            f'<span class="ms-chip">Everyday {ratio:.2f}&times;</span>'
            f'<span class="ms-chip">{_e(tax)}</span></div>'
            f'<div class="ms-place-sub">At age {_e(ret_age if ret_age is not None else "")}, in today\'s dollars.</div>'
            f'{_facts(pr, ret_age)}'
            f'<ul class="ms-list ms-list-place">{rows}</ul>{note}')


def breakdown_html(pr: "ms.PlaceResult", here: "ms.PlaceCost", home_name: str) -> str:
    """Monthly spending now and there, line by line, so you see what scales."""
    c = pr.cost
    if c is None:
        return ""
    now_by = {k: v for k, v, _ in here.categories}
    rows = [("Housing", here.housing, c.housing)]
    rows += [(pc.LABELS.get(k, k), now_by.get(k, v_now), v_there) for k, v_now, v_there in c.categories]
    rows.append(("Health insurance and care", here.health, c.health))
    if c.other > 0.5:
        rows.append(("Children and other planned costs", here.other, c.other))
    rows.append(("Total", here.spend, c.spend))

    def m(v):
        return f"${v / 12.0:,.0f}"

    total = ' class="ms-total"'
    body = "".join(
        f'<tr{total if lab == "Total" else ""}><th scope="row">{_e(lab)}</th>'
        f"<td>{_e(m(a))}</td><td>{_e(m(b))}</td></tr>" for lab, a, b in rows)
    return (f'<table class="ms-break"><caption>A month in retirement. Everyday costs are compared '
            f'with {_e(home_name)}.</caption><thead><tr><th scope="col">Item</th>'
            f'<th scope="col">Now</th><th scope="col">There</th></tr></thead><tbody>{body}</tbody></table>')


def result_html(res: dict, plan_age, stale: bool) -> str:
    age = res.get("earliest_retirement_age")
    tgt = res.get("target_age")
    succ = res.get("success_at_target", 0.0)
    goal = res.get("target_success", 0.8)
    age_txt = f"{age}" if age is not None else "none by 75"
    delta = ""
    if age is not None and plan_age is not None:
        d = int(age) - int(plan_age)
        delta = (" (same as your plan)" if d == 0 else
                 f" ({abs(d)} {'year' if abs(d) == 1 else 'years'} {'earlier' if d < 0 else 'later'} than your plan)")
    old = '<div class="ms-stale">Out of date. Your inputs changed.</div>' if stale else ""
    return (f'<div class="ms-result"><div class="ms-result-head">&#10003; Simulation check</div>'
            f'<div>Earliest age at {goal:.0%} success: <b>{_e(age_txt)}</b>{_e(delta)}</div>'
            f'<div>Success if you retire at {_e(tgt)}: <b>{succ:.0%}</b></div>{old}</div>')


# --------------------------------------------------------------------------- gathering inputs

def _projection(clean: dict):
    """The deterministic projection from the net-worth chart, or None."""
    try:
        try:
            from components.net_worth_projection_chart import project_net_worth
        except ImportError:  # pragma: no cover
            from ui.components.net_worth_projection_chart import project_net_worth  # type: ignore
        return project_net_worth(clean)
    except Exception:
        return None


def _real_return(clean: dict) -> float:
    try:
        try:
            from components.net_worth_projection_chart import _SCENARIO_RETURNS
        except ImportError:  # pragma: no cover
            from ui.components.net_worth_projection_chart import _SCENARIO_RETURNS  # type: ignore
        scen = str(clean.get("ACTIVE_RETURN_SCENARIO", "historical")).lower()
        return float(_SCENARIO_RETURNS.get(scen, _SCENARIO_RETURNS["historical"])["investment"])
    except Exception:
        return DEFAULT_RETURN


def series(clean: dict, results):
    """(ages, invested, home, source): the median path of the last run when there is
    one, else the simple projection the net-worth chart uses. ``source`` is "median"
    or "projection"; ages is empty if neither exists."""
    proj = _projection(clean)
    home_by_age, last_home = {}, 0.0
    det_ages, det_invested = [], []
    if proj and proj.get("ages"):
        det_ages = list(proj["ages"])
        by = proj["by_account"]
        home = by.get("Home equity", [0.0] * len(det_ages))
        home_by_age = dict(zip(det_ages, home))
        last_home = float(home[-1]) if len(home) else 0.0
        det_invested = [sum(float(v[i]) for k, v in by.items() if k != "Home equity")
                        for i in range(len(det_ages))]
    traj = ((results or {}).get("primary_result") or {}).get("median_trajectory") or []
    # A plan that runs out of money at once leaves one point (no median path to
    # follow). The simple projection is the better timeline then.
    if len(traj) >= 2 or (traj and not det_ages):
        ages = [int(a) for a, _ in traj]
        inv = [float(v) for _, v in traj]
        # A path that is held flat at the last known home equity (the projection stops at retirement).
        home = [float(home_by_age.get(a, last_home)) for a in ages]
        return ages, inv, home, "median"
    home = [float(home_by_age.get(a, last_home)) for a in det_ages]
    return det_ages, det_invested, home, "projection"


def _debt_by_age(clean: dict, ages) -> list:
    """What the plan's debts leave owed at each age (today's dollars), so net worth
    here subtracts them as the top bar does. Empty when there are no debts."""
    try:
        from retirement_sim import debts as dm
        try:
            from utils import debt_view as dv
        except ImportError:  # pragma: no cover
            from ui.utils import debt_view as dv  # type: ignore
        if not dv.rows(clean):
            return []
        bal = dm.real_schedule(dv.rows(clean), dv.extra(clean), dv.strategy(clean),
                               dv.inflation(clean)).balances
        first = int(ages[0])
        return [float(bal[a - first]) if 0 <= a - first < len(bal) else 0.0 for a in (int(x) for x in ages)]
    except Exception:
        return []


def build_inputs(overrides: dict, results, state: dict, rate: float, barista: float):
    """The pure-logic inputs for this plan, or None if there is no timeline.

    Returns ((inputs, basis, sale), source): ``basis`` is
    sim_runner.retirement_spending_basis, ``sale`` sim_runner.home_sale_path."""
    try:
        from utils import sim_runner as sr
    except ImportError:  # pragma: no cover
        from ui.utils import sim_runner as sr  # type: ignore
    clean = {k: v for k, v in overrides.items() if k != pl.KEY}
    ages, invested, home, source = series(clean, results)
    if not ages:
        return None, source
    ret_age = safe_int(clean.get("TARGET_RETIREMENT_AGE", 55), 55)
    try:
        basis = sr.retirement_spending_basis(clean, ret_age)
    except Exception:
        basis = {"core": 0.0, "health": 0.0, "living": 0.0, "today": 0.0, "discretionary_ratio": 0.30}
    try:
        sale = sr.home_sale_path(clean, max(int(ages[-1]), ret_age, 76))
    except Exception:
        sale = {"proceeds": {}, "events": []}
    couple = has_partner(clean)
    cash = safe_float(clean.get("YOUR_CASH", 0), 0.0) + (safe_float(clean.get("PARTNER_CASH", 0), 0.0) if couple else 0.0)
    mort = safe_float(clean.get("MORTGAGE_BALANCE", 0), 0.0) > 0
    cost = ms.CostBasis(
        home=pl.home_area(state, clean), weights=dict(basis.get("weights") or {}),
        housing_now=float(basis.get("housing", 0.0)),
        housing_plan=(sale.get("housing") or {}).get(ret_age), pre_medicare=bool(basis.get("pre_medicare", True)),
        proceeds=dict(sale.get("proceeds") or {}), moving_costs=float(sale.get("moving_costs", 10_000.0)),
        mortgage_rate=float(sale.get("mortgage_rate", 0.065)),
        carry_after_payoff=bool(sale.get("carry_after_payoff", True)))
    inp = ms.Inputs(
        your_age=ages[0], retire_age=ret_age, year=date.today().year, ages=ages, invested=invested,
        home=home, spend_core=basis["core"], living_base=basis["living"], health=basis["health"], today_spend=basis["today"],
        discretionary_ratio=basis["discretionary_ratio"], rate=rate, real_return=_real_return(clean),
        cash=cash, barista_income=float(barista),
        mortgage_years=safe_int(clean.get("MORTGAGE_YEARS_REMAINING", 0), 0) if mort else 0,
        places=pl.resolve(state), cost=cost, debt=_debt_by_age(clean, ages))
    return (inp, basis, sale), source


# --------------------------------------------------------------------------- state writes (callbacks)

def _write_state(st, state: dict) -> None:
    ov = st.session_state.setdefault("user_overrides", {})
    pl.store(ov, state)


def _current_state(st) -> dict:
    return pl.get_state(st.session_state.get("user_overrides", {}))


_EDIT_FIELDS = ("area", "housing", "price", "rent", "adjust", "tax", "note")


def _forget_edit_widgets(st, pid: str) -> None:
    """Drop a place's edit values so the inputs re-read the saved place."""
    for f in _EDIT_FIELDS:
        st.session_state.pop(f"ms_{f}_{pid}", None)


def _clean_overrides(st) -> dict:
    return {k: v for k, v in (st.session_state.get("user_overrides", {}) or {}).items() if k != pl.KEY}


def _on_rate(st) -> None:
    v = safe_float(st.session_state.get("ms_rate"), pl.DEFAULT_RATE * 100) / 100.0
    _write_state(st, pl.with_setting(_current_state(st), "rate", v))


def _on_barista(st) -> None:
    v = safe_float(st.session_state.get("ms_barista"), pl.DEFAULT_BARISTA)
    _write_state(st, pl.with_setting(_current_state(st), "barista", v))


def _on_use_swr(st, rate: float) -> None:
    st.session_state["ms_rate"] = round(rate * 100, 2)
    _on_rate(st)


def _on_home(st) -> None:
    _write_state(st, pl.with_home(_current_state(st), st.session_state.get("ms_home_area"), _clean_overrides(st)))


def _on_field(st, pid: str, f: str) -> None:
    """One edit input changed: save it on the place."""
    ss = st.session_state
    value = ss.get(f"ms_{f}_{pid}")
    state = _current_state(st)
    place = pl.get_place(state, pid)
    if place is None:
        return
    if f in ("price", "rent"):
        home = pl.home_area(state, _clean_overrides(st))
        typical = getattr(pc.get(place.area_code(home)), f)
        value = None if value is None or int(round(float(value))) == int(typical) else value
    _write_state(st, pl.with_edit(state, pid, **{f: value}))
    if f == "area":
        for k in ("price", "rent", "housing"):
            ss.pop(f"ms_{k}_{pid}", None)


def _on_reset_place(st, pid: str) -> None:
    _write_state(st, pl.with_reset(_current_state(st), pid))
    _forget_edit_widgets(st, pid)


def _on_remove_place(st, pid: str) -> None:
    _write_state(st, pl.with_removed(_current_state(st), pid))
    _forget_edit_widgets(st, pid)
    st.session_state.pop(f"ms_res_{pid}", None)


def _on_restore(st) -> None:
    _write_state(st, pl.with_restored(_current_state(st)))


_AUTO = "auto"


def _on_add_place(st) -> None:
    ss = st.session_state
    housing = ss.get("ms_new_housing", _AUTO)
    tax = ss.get("ms_new_tax", _AUTO)
    state, pid = pl.with_custom(_current_state(st), ss.get("ms_new_name"), ss.get("ms_new_area", pc.US_CODE),
                                None if housing == _AUTO else housing, None if tax == _AUTO else tax,
                                ss.get("ms_new_note", ""))
    if pid is None:
        ss["ms_new_msg"] = ("Enter a name." if not str(ss.get("ms_new_name") or "").strip()
                            else f"You can add up to {pl.MAX_CUSTOM} places.")
        return
    ss.pop("ms_new_msg", None)
    _write_state(st, state)
    for k in ("ms_new_name", "ms_new_note"):
        ss[k] = ""
    ss["ms_new_housing"] = _AUTO
    ss["ms_new_tax"] = _AUTO


# --------------------------------------------------------------------------- the confirm run

def _check_hash(clean: dict, n_sims: int, target_age: int, place, home: str) -> int:
    try:
        return hash((_hashable(clean), int(n_sims), int(target_age), place, home))
    except Exception:
        return 0


def confirm_settings(inp, place, basis: dict, sale: dict):
    """(engine overrides, per-age patch or None) that test ``place`` in the real
    simulation: the quick rule's spending, health and tax, and the same move at
    each age the scan tries (sim_runner.plan_place_check)."""
    place_ov = ms.place_overrides(inp, place, basis.get("health_knobs"))
    if not ms.moves(place):
        return place_ov, None
    events = list(sale.get("events") or [])

    def age_patch(age: int) -> dict:
        return {"HOME_EVENTS": ms.place_home_events(inp, place, age, events), "HOUSE_MOVE_ENABLED": False}

    return place_ov, age_patch


def _confirm(st, clean: dict, inp, place, basis: dict, sale: dict, n_sims: int, target_age: int,
             res_key: str, h: int) -> None:
    """Run the real Monte Carlo for one place. In the visitor's browser when its
    workers are ready, else here with a progress bar."""
    try:
        from utils import sim_runner as sr
        from utils import browser_compute as bc
        from utils.validation import validate_run_inputs
    except ImportError:  # pragma: no cover
        from ui.utils import sim_runner as sr  # type: ignore
        from ui.utils import browser_compute as bc  # type: ignore
        from ui.utils.validation import validate_run_inputs  # type: ignore
    errs = validate_run_inputs(clean, target_age)
    if errs:
        for e in errs:
            st.error(e)
        return
    place_ov, age_patch = confirm_settings(inp, place, basis, sale)
    plan = sr.plan_place_check(clean, place_ov, n_sims, target_age, age_patch)

    def store(res):
        st.session_state[res_key] = {**res, "_inputs_hash": h}

    if plan.result is not None:
        store(plan.result)
    elif bc.ready(st):
        bc.submit(st, f"place:{place.id}", plan, store)
    else:
        prog = st.progress(0.0, text=f"Testing {place.name}…")

        def _cb(frac, msg):
            try:
                prog.progress(min(1.0, max(0.0, float(frac))), text=str(msg))
            except Exception:
                pass

        try:
            store(sr.execute_plan(plan, _cb))
        finally:
            prog.empty()
    st.rerun()


# --------------------------------------------------------------------------- render

def _place_cards(st, rep, inp, basis, sale, state, clean, results, n_sims, target_age, end_age,
                 next_keys) -> None:
    plan_age = (results or {}).get("earliest_retirement_age") if results else None
    try:
        from utils import browser_compute as bc
    except ImportError:  # pragma: no cover
        from ui.utils import browser_compute as bc  # type: ignore
    home = inp.cost.home
    owns_home = safe_float(clean.get("HOME_VALUE", 0), 0.0) > 0
    here_place = pl.default_place(pl.HERE_ID)
    here_cost = ms.place_cost(inp, here_place, inp.retire_age)
    per_row = 3
    for start in range(0, len(rep.places), per_row):
        cols = st.columns(per_row)
        for col, pr in zip(cols, rep.places[start:start + per_row]):
            p = pr.place
            res_key = f"ms_res_{p.id}"
            with col:
                with st.container(border=True, key=f"ms-place-{p.id}"):
                    st.markdown(place_html(pr, end_age, next_keys, inp.retire_age, owns_home=owns_home),
                                unsafe_allow_html=True)
                    h = _check_hash(clean, n_sims, target_age, p, home)
                    res = st.session_state.get(res_key)
                    fresh = bool(res) and res.get("_inputs_hash") == h
                    stale = bool(res) and not fresh
                    waiting = bool(bc.pending(st, f"place:{p.id}"))
                    label = "✓ Confirmed" if fresh else ("Checking…" if waiting else "Confirm with simulation")
                    if st.button(label, key=f"ms_confirm_{p.id}", type="secondary",
                                 disabled=fresh or waiting,
                                 help=("Up to date. Change an input or this place to run it again." if fresh else
                                       "Runs the full simulation with this place's move, spending and tax.")):
                        _confirm(st, clean, inp, p, basis, sale, n_sims, target_age, res_key, h)
                    if res:
                        st.markdown(result_html(res, plan_age, stale), unsafe_allow_html=True)
                    _edit_place(st, state, p, pr, here_cost, home)


def _edit_place(st, state: dict, p, pr, here_cost, home: str) -> None:
    """The place's costs line by line, and its settings (saved as you change them)."""
    with st.expander("Costs and settings", expanded=False):
        st.markdown(breakdown_html(pr, here_cost, pc.get(home).name), unsafe_allow_html=True)
        pid = p.id
        args = lambda f: (st, pid, f)  # noqa: E731
        if p.custom:
            opts = pc.place_options()
            ensure_default(st, f"ms_area_{pid}", p.area if p.area in opts else pc.US_CODE)
            st.selectbox("Based on", opts, key=f"ms_area_{pid}", format_func=pc.label,
                         on_change=_on_field, args=args("area"),
                         help="The area whose prices this place uses.")
        if not p.here:
            choices = list(pl.HOUSING_CHOICES)
            ensure_default(st, f"ms_housing_{pid}", p.housing)
            st.radio("Housing", choices, key=f"ms_housing_{pid}", format_func=pl.HOUSING_LABELS.get,
                     on_change=_on_field, args=args("housing"),
                     help="Buying or renting sells the home you own at the retirement age. "
                          "The sale pays for the new home; a loan covers any shortfall.")
            if p.housing == pl.HOUSING_BUY:
                ensure_default(st, f"ms_price_{pid}", int(p.home_price(home)))
                st.number_input("Home price there ($)", min_value=0, max_value=pl.PRICE_MAX, step=10_000,
                                key=f"ms_price_{pid}", on_change=_on_field, args=args("price"),
                                help=f"Typical for the area: ${pc.get(p.area_code(home)).price:,}. "
                                     f"Property tax and insurance: {p.carry(home) * 100:.2f}% a year.")
            elif p.housing == pl.HOUSING_RENT:
                ensure_default(st, f"ms_rent_{pid}", int(p.monthly_rent(home)))
                st.number_input("Rent there ($ a month)", min_value=0, max_value=pl.RENT_MAX, step=50,
                                key=f"ms_rent_{pid}", on_change=_on_field, args=args("rent"),
                                help=f"Typical for the area: ${pc.get(p.area_code(home)).rent:,} a month.")
        ensure_default(st, f"ms_adjust_{pid}", float(p.adjust))
        st.number_input("Everyday costs adjustment (1.00 = as estimated)", min_value=pl.ADJUST_MIN,
                        max_value=pl.ADJUST_MAX, step=0.05, format="%.2f", key=f"ms_adjust_{pid}",
                        on_change=_on_field, args=args("adjust"),
                        help="Multiplies every everyday category above. Housing and children are not changed.")
        tax_opts = [v for _, v in pl.tax_choices()]
        tax_labels = {v: lab for lab, v in pl.tax_choices()}
        ensure_default(st, f"ms_tax_{pid}", p.tax if p.tax in tax_opts else pl.TAX_SAME)
        st.selectbox("Income tax in retirement", tax_opts, key=f"ms_tax_{pid}",
                     format_func=lambda v: tax_labels.get(v, v), on_change=_on_field, args=args("tax"))
        ensure_default(st, f"ms_note_{pid}", p.note)
        st.text_area("Note", key=f"ms_note_{pid}", max_chars=pl.NOTE_MAX, height=68, on_change=_on_field,
                     args=args("note"))
        if not p.custom and pl.is_edited(state, pid):
            st.button("Reset to built-in", key=f"ms_reset_{pid}", on_click=_on_reset_place, args=(st, pid))
        if not p.here:
            st.button("Remove this place", key=f"ms_remove_{pid}", on_click=_on_remove_place, args=(st, pid))


def _add_places(st, state: dict) -> None:
    with st.expander("Add a place", expanded=False, icon=":material/add_location:"):
        st.caption("Base it on any state, metro area or city abroad, then fine-tune it in its card. "
                   "Changes are saved with your profile.")
        ensure_default(st, "ms_new_name", "")
        ensure_default(st, "ms_new_note", "")
        ensure_default(st, "ms_new_area", pc.US_CODE)
        ensure_default(st, "ms_new_housing", _AUTO)
        ensure_default(st, "ms_new_tax", _AUTO)
        housing_opts = [_AUTO, pl.HOUSING_BUY, pl.HOUSING_RENT]
        housing_labels = {_AUTO: "Typical for the area", **pl.HOUSING_LABELS}
        tax_opts = [_AUTO] + [v for _, v in pl.tax_choices()]
        tax_labels = {_AUTO: "The area's own tax", **{v: lab for lab, v in pl.tax_choices()}}
        with st.form("ms_new_form", border=False):
            st.text_input("Name", key="ms_new_name", max_chars=pl.NAME_MAX)
            st.selectbox("Based on", pc.place_options(), key="ms_new_area", format_func=pc.label)
            st.selectbox("Housing", housing_opts, key="ms_new_housing", format_func=housing_labels.get,
                         help="Typical: buy a home in the US, rent abroad.")
            st.selectbox("Income tax", tax_opts, key="ms_new_tax", format_func=lambda v: tax_labels.get(v, v))
            st.text_input("Note", key="ms_new_note", max_chars=pl.NOTE_MAX)
            st.form_submit_button("Add place", type="primary", on_click=_on_add_place, args=(st,))
        msg = st.session_state.get("ms_new_msg")
        if msg:
            st.caption(msg)
        if state.get("hidden"):
            st.button("Bring back removed places", key="ms_restore", on_click=_on_restore, args=(st,))


def _how_it_works(st, inp, rate: float, basis: dict, source: str, end_age) -> None:
    home = pc.get(inp.cost.home).name
    with st.expander("How this is calculated", expanded=False, icon=":material/help:"):
        st.markdown(
            "**Quick rule, then a real test.** Each card compares your money with a target. "
            "The test costs nothing to run. It is an estimate. Press **Confirm with simulation** on a "
            "place to test it with the full Monte Carlo model.\n\n"
            f"- **Money in today's dollars.** Inflation is already taken out.\n"
            f"- **Timeline.** {'The median path of your last simulation.' if source == 'median' else 'A simple projection, because no simulation has run yet. Run one for the median path.'} "
            "Net worth adds home equity. Invested leaves it out.\n"
            f"- **Spending in a place** is built line by line at age {inp.retire_age}. Each everyday "
            f"category (utilities, food, transport, healthcare premiums, fun, other, partner) is your plan's "
            f"amount times that place's price level divided by the price level where you live now "
            f"(**{_md(home)}**), times the place's adjustment. Health insurance before Medicare scales the "
            "same way. Medicare years and children's costs stay as planned.\n"
            "- **Housing in a place.** Moving sells the home you own at that age. You get its value less "
            "the loan, selling costs and tax on any gain above the exclusion. Then you buy a typical home "
            "there with that money (a loan covers any shortfall, at your plan's new-loan rate) and pay its "
            "property tax and insurance, or you rent there. Leftover sale money joins your investments. "
            "*Where you live now* keeps your housing as planned.\n"
            f"- **FIRE in a place.** Investments plus what the move frees cover a year of spending there "
            f"divided by the withdrawal rate (now **{rate * 100:.2f}%**). Your plan spends about "
            f"{_md(ms.short_money(inp.spend_core + inp.health))} a year in retirement.\n"
            f"- **Coast FIRE.** Your investments, left alone with no more saving, grow at "
            f"**{inp.real_return * 100:.1f}%** a year after inflation (the rate behind the net-worth "
            f"projection chart). With the move's cash they reach the FIRE number by age {inp.retire_age}.\n"
            f"- **Other markers.** Essentials are {100 - int(round(inp.discretionary_ratio * 100))}% of everyday "
            "spending plus health. Barista FIRE subtracts the part-time income you set. "
            "The emergency fund counts cash accounts only.\n"
            "- **Not in the quick rule.** Income tax, Social Security, guardrails and market swings. "
            "The simulation counts them.\n\n"
            "**What Confirm changes.** For each retirement age it tries, it moves you at that age: the "
            "same sale, purchase or rent as the card. Any home moves in your plan from that age on are "
            "replaced. It sets your retirement everyday spending to the place's, scales pre-Medicare "
            "health prices, and applies the place's state tax to retirement years. Your working years "
            "keep the state you live in now.\n\n"
            "**Rough numbers.** Prices, home values and rents are rough estimates in the shape of "
            "BEA regional price parities, typical home values and rents, and Numbeo-style ratios abroad. "
            f"They are not data. Edit any place. {pl.ABROAD_CAVEAT}"
        )


def _md(text) -> str:
    return str(text).replace("$", "\\$")


def render(st, results: dict = None) -> None:
    st.markdown('<div class="mc-section">Freedom milestones</div>', unsafe_allow_html=True)
    overrides = st.session_state.get("user_overrides", {}) or {}
    state = pl.get_state(overrides)
    st.caption("Markers of freedom you pass on the way. Each shows when you reach it, "
               "or that it is out of reach in this plan.")

    # ---- the two settings (saved with the profile) ----
    ensure_default(st, "ms_rate", round(pl.setting(state, "rate") * 100, 2))
    ensure_default(st, "ms_barista", int(pl.setting(state, "barista")))
    swr = st.session_state.get("swr_result") or {}
    # A rate at the top of the sweep is only "at least" that, not a rate to plan on.
    swr_rate = (swr.get("swr_rate") if isinstance(swr, dict) and not swr.get("swr_is_lower_bound") else None)

    c1, c2 = st.columns(2)
    with c1:
        st.number_input("Withdrawal rate (%)", min_value=pl.RATE_MIN * 100, max_value=pl.RATE_MAX * 100,
                        step=0.25, format="%.2f", key="ms_rate", on_change=_on_rate, args=(st,),
                        help="What share of your investments you spend each year in the FIRE test. "
                             "4% is the classic rule.")
    with c2:
        st.number_input("Part-time income for Barista FIRE ($ a year)", min_value=0, max_value=pl.BARISTA_MAX,
                        step=1000, key="ms_barista", on_change=_on_barista, args=(st,),
                        help="Work you would keep doing after leaving your career.")
    state = _current_state(st)
    rate = pl.setting(state, "rate")
    if swr_rate and abs(float(swr_rate) - rate) > 0.0004:
        st.button(f"Use my safe rate ({float(swr_rate) * 100:.2f}%)", key="ms_use_swr", on_click=_on_use_swr,
                  args=(st, float(swr_rate)),
                  help="The rate from the Safe withdrawal rate section below, for your own plan.")

    built, source = build_inputs(overrides, results, state, rate, pl.setting(state, "barista"))
    if built is None:
        st.info("Add your accounts and ages to see your milestones.")
        return
    inp, basis, sale = built
    rep = ms.build(inp)
    end_age = plan_end_ages(overrides)[0]  # "through" the end of the plan, not the end of the timeline
    overall = rep.next_up.key if rep.next_up else None
    next_keys = {k for k in (overall, first_in_progress(rep.networth), first_in_progress(rep.invested)) if k}
    clean = {k: v for k, v in overrides.items() if k != pl.KEY}
    n_sims = int(st.session_state.get("n_simulations", 1000))
    target_age = safe_int(clean.get("TARGET_RETIREMENT_AGE", 55), 55)

    st.markdown(summary_html(rep, end_age), unsafe_allow_html=True)
    st.caption("Timeline: the median path of your last simulation."
               if source == "median" else
               ("Timeline: a simple projection. Your last simulation has no median path to follow, "
                "because the plan runs out of money at once."
                if results else
                "Timeline: a simple projection. Run the simulation for the median path."))
    st.caption("The percent on each marker is how far along you are (your balance divided by the target). "
               "It is not a chance of success. An age after your retirement age means the median path only "
               "gets there while you spend it down. This quick rule leaves out Social Security, tax and market swings, "
               "so your simulated chance of success can look better than these markers.")

    # ---- net worth ladders ----
    st.markdown(
        '<div class="ms-groups">'
        + ladder_html("Net worth", "with home equity", rep.networth, end_age, next_keys, rep.earlier_networth)
        + ladder_html("Invested", "without your home", rep.invested, end_age, next_keys, rep.earlier_invested)
        + '</div>', unsafe_allow_html=True)

    # ---- places ----
    st.markdown('<div class="ms-subhead">Freedom by place</div>', unsafe_allow_html=True)
    if not rep.spending_known:
        st.caption("Add your spending to see Coast FIRE and FIRE by place.")
    else:
        st.caption("**Coast FIRE:** stop saving, growth does the rest. **FIRE:** your investments pay for "
                   "life there. Moving sells your home, then buys or rents there. Everyday costs are "
                   "scaled line by line against where you live now. The numbers are rough, so confirm "
                   "the places you care about.")
        homes = pc.home_options()
        ensure_default(st, "ms_home_area", inp.cost.home if inp.cost.home in homes else pc.US_CODE)
        with st.columns(2)[0]:
            st.selectbox("Where you live now", homes, key="ms_home_area", format_func=pc.label,
                         on_change=_on_home, args=(st,),
                         help="Everyday costs in each place are compared with this area. "
                              "Your own housing comes from your plan. Starts at your plan's state.")
        _place_cards(st, rep, inp, basis, sale, state, clean, results, n_sims, target_age, end_age, next_keys)
        if any(p.abroad for p in inp.places):
            st.caption(pl.ABROAD_CAVEAT)
    _add_places(st, state)

    # ---- other markers ----
    if rep.markers:
        st.markdown('<div class="ms-subhead">Other markers</div>', unsafe_allow_html=True)
        rows = "".join(_item(m, end_age, m.key in next_keys) for m in rep.markers)
        st.markdown(f'<div class="ms-ladder ms-ladder-wide"><ul class="ms-list ms-list-grid">{rows}</ul></div>',
                    unsafe_allow_html=True)

    _how_it_works(st, inp, rate, basis, source, end_age)
