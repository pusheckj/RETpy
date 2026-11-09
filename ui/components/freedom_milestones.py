"""Freedom milestones: the markers of freedom you have passed, and when the rest arrive.

A section on the planner's results page. It shows

* net worth and invested ladders ($100K, $250K, $500K, $1M, ...),
* Coast FIRE and FIRE in a set of places (US regions and abroad) that you can edit,
* other markers: emergency fund, Lean and Barista FIRE, returns that pay a year of
  costs, mortgage paid off.

The test for each is a quick rule that costs nothing to run (utils/milestones.py).
Each place has a "Confirm with simulation" button that runs the real Monte Carlo
with that place's spending and tax (sim_runner.plan_place_check), on the server or in
the visitor's browser like the other sweeps.

Edits and custom places are saved in ``user_overrides["MS_PLACES"]`` (utils/places.py),
so they travel with Save/Load, Remember me and profiles. Widget keys start with ``ms_``.
"""
from __future__ import annotations

import html as _html
from datetime import date

try:
    from utils import milestones as ms
    from utils import places as pl
    from utils.coerce import safe_int, safe_float, ensure_default
    from utils.formatting import money
    from utils.household import has_partner
    from utils.sim_runner import _hashable
except ImportError:  # pragma: no cover
    from ui.utils import milestones as ms  # type: ignore
    from ui.utils import places as pl  # type: ignore
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money  # type: ignore
    from ui.utils.household import has_partner  # type: ignore
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
    pct = f' · {int(round(100 * m.progress))}%' if (m.progress is not None and m.status != ms.REACHED) else ""
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


def place_html(pr: "ms.PlaceResult", end_age, next_keys) -> str:
    p = pr.place
    tax = pl.tax_label(p.tax, p.abroad)
    rows = "".join(_item(m, end_age, m.key in next_keys, with_detail=False, label=lab)
                   for m, lab in ((pr.coast, "Coast FIRE"), (pr.fire, "FIRE")))
    note = f'<div class="ms-note">{_e(p.note)}</div>' if p.note else ""
    return (f'<div class="ms-place-head"><b>{_e(p.name)}</b>'
            f'<span class="ms-chip">{p.factor:.2f}&times; costs</span>'
            f'<span class="ms-chip">{_e(tax)}</span></div>'
            f'<div class="ms-place-sub">Lives on {_e(ms.short_money(pr.spend))} a year. '
            f'FIRE number {_e(ms.short_money(pr.fire_number))}.</div>'
            f'<ul class="ms-list ms-list-place">{rows}</ul>{note}')


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
    if traj:
        ages = [int(a) for a, _ in traj]
        inv = [float(v) for _, v in traj]
        # A path that is held flat at the last known home equity (the projection stops at retirement).
        home = [float(home_by_age.get(a, last_home)) for a in ages]
        return ages, inv, home, "median"
    home = [float(home_by_age.get(a, last_home)) for a in det_ages]
    return det_ages, det_invested, home, "projection"


def build_inputs(overrides: dict, results, state: dict, rate: float, barista: float):
    """The pure-logic inputs for this plan, or None if there is no timeline."""
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
    couple = has_partner(clean)
    cash = safe_float(clean.get("YOUR_CASH", 0), 0.0) + (safe_float(clean.get("PARTNER_CASH", 0), 0.0) if couple else 0.0)
    mort = safe_float(clean.get("MORTGAGE_BALANCE", 0), 0.0) > 0
    inp = ms.Inputs(
        your_age=ages[0], retire_age=ret_age, year=date.today().year, ages=ages, invested=invested,
        home=home, spend_core=basis["core"], living_base=basis["living"], health=basis["health"], today_spend=basis["today"],
        discretionary_ratio=basis["discretionary_ratio"], rate=rate, real_return=_real_return(clean),
        cash=cash, barista_income=float(barista),
        mortgage_years=safe_int(clean.get("MORTGAGE_YEARS_REMAINING", 0), 0) if mort else 0,
        places=pl.resolve(state))
    return (inp, basis), source


# --------------------------------------------------------------------------- state writes (callbacks)

def _write_state(st, state: dict) -> None:
    ov = st.session_state.setdefault("user_overrides", {})
    pl.store(ov, state)


def _current_state(st) -> dict:
    return pl.get_state(st.session_state.get("user_overrides", {}))


def _forget_edit_widgets(st, pid: str) -> None:
    """Drop a place's edit-form values so the form re-reads the saved place."""
    for field in ("factor", "tax", "note"):
        st.session_state.pop(f"ms_edit_{field}_{pid}", None)


def _on_rate(st) -> None:
    v = safe_float(st.session_state.get("ms_rate"), pl.DEFAULT_RATE * 100) / 100.0
    _write_state(st, pl.with_setting(_current_state(st), "rate", v))


def _on_barista(st) -> None:
    v = safe_float(st.session_state.get("ms_barista"), pl.DEFAULT_BARISTA)
    _write_state(st, pl.with_setting(_current_state(st), "barista", v))


def _on_use_swr(st, rate: float) -> None:
    st.session_state["ms_rate"] = round(rate * 100, 2)
    _on_rate(st)


def _on_save_place(st, pid: str) -> None:
    ss = st.session_state
    note = ss.get(f"ms_edit_note_{pid}")
    state = pl.with_edit(_current_state(st), pid, factor=ss.get(f"ms_edit_factor_{pid}"),
                         tax=ss.get(f"ms_edit_tax_{pid}"), note=note)
    _write_state(st, state)


def _on_reset_place(st, pid: str) -> None:
    state = _current_state(st)
    base = pl.default_place(pid)
    if base is not None:
        state = pl.with_edit(state, pid, factor=base.factor, tax=base.tax, note=base.note)
    _write_state(st, state)
    _forget_edit_widgets(st, pid)


def _on_remove_place(st, pid: str) -> None:
    _write_state(st, pl.with_removed(_current_state(st), pid))
    _forget_edit_widgets(st, pid)
    st.session_state.pop(f"ms_res_{pid}", None)
    st.session_state.pop("ms_edit_pick", None)


def _on_restore(st) -> None:
    _write_state(st, pl.with_restored(_current_state(st)))


def _on_add_place(st) -> None:
    ss = st.session_state
    state, pid = pl.with_custom(_current_state(st), ss.get("ms_new_name"), ss.get("ms_new_factor", 1.0),
                                ss.get("ms_new_tax", pl.TAX_SAME), ss.get("ms_new_note", ""))
    if pid is None:
        ss["ms_new_msg"] = ("Enter a name." if not str(ss.get("ms_new_name") or "").strip()
                            else f"You can add up to {pl.MAX_CUSTOM} places.")
        return
    ss.pop("ms_new_msg", None)
    _write_state(st, state)
    for k in ("ms_new_name", "ms_new_note"):
        ss[k] = ""
    ss["ms_new_factor"] = 1.0
    ss["ms_new_tax"] = pl.TAX_SAME
    ss["ms_edit_pick"] = pid


# --------------------------------------------------------------------------- the confirm run

def _check_hash(clean: dict, n_sims: int, target_age: int, place) -> int:
    try:
        return hash((_hashable(clean), int(n_sims), int(target_age), round(place.factor, 4), place.tax))
    except Exception:
        return 0


def _confirm(st, clean: dict, place, basis: dict, n_sims: int, target_age: int, res_key: str, h: int) -> None:
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
    place_ov = ms.place_overrides(place, basis["core"], basis["living"])
    plan = sr.plan_place_check(clean, place_ov, n_sims, target_age)

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

def _place_cards(st, rep, inp, basis, clean, results, n_sims, target_age, end_age, next_keys) -> None:
    plan_age = (results or {}).get("earliest_retirement_age") if results else None
    try:
        from utils import browser_compute as bc
    except ImportError:  # pragma: no cover
        from ui.utils import browser_compute as bc  # type: ignore
    per_row = 3
    for start in range(0, len(rep.places), per_row):
        cols = st.columns(per_row)
        for col, pr in zip(cols, rep.places[start:start + per_row]):
            p = pr.place
            res_key = f"ms_res_{p.id}"
            with col:
                with st.container(border=True, key=f"ms-place-{p.id}"):
                    st.markdown(place_html(pr, end_age, next_keys), unsafe_allow_html=True)
                    h = _check_hash(clean, n_sims, target_age, p)
                    res = st.session_state.get(res_key)
                    fresh = bool(res) and res.get("_inputs_hash") == h
                    stale = bool(res) and not fresh
                    waiting = bool(bc.pending(st, f"place:{p.id}"))
                    label = "✓ Confirmed" if fresh else ("Checking…" if waiting else "Confirm with simulation")
                    if st.button(label, key=f"ms_confirm_{p.id}", type="secondary",
                                 disabled=fresh or waiting,
                                 help=("Up to date. Change an input or this place to run it again." if fresh else
                                       "Runs the full simulation with this place's spending and tax.")):
                        _confirm(st, clean, p, basis, n_sims, target_age, res_key, h)
                    if res:
                        st.markdown(result_html(res, plan_age, stale), unsafe_allow_html=True)


def _edit_places(st, state: dict, end_age) -> None:
    all_places = pl.resolve(state)
    with st.expander("Edit or add places", expanded=False, icon=":material/edit_location:"):
        st.caption("Cost factors are rough guesses for a household that now lives in an "
                   "average-cost area. Set your own. Changes are saved with your profile.")
        ids = [p.id for p in all_places]
        by_id = {p.id: p for p in all_places}
        if "ms_edit_pick" in st.session_state and st.session_state["ms_edit_pick"] not in ids:
            del st.session_state["ms_edit_pick"]
        pid = st.selectbox("Place to edit", ids, key="ms_edit_pick",
                           format_func=lambda i: by_id[i].name) if ids else None
        if pid:
            p = by_id[pid]
            tax_opts = [v for _, v in pl.tax_choices()]
            tax_labels = {v: l for l, v in pl.tax_choices()}
            ensure_default(st, f"ms_edit_factor_{pid}", float(p.factor))
            ensure_default(st, f"ms_edit_tax_{pid}", p.tax if p.tax in tax_opts else pl.TAX_SAME)
            ensure_default(st, f"ms_edit_note_{pid}", p.note)
            with st.form(f"ms_edit_form_{pid}", border=False):
                c1, c2 = st.columns(2)
                with c1:
                    st.number_input("Costs compared with now (1.00 = same)", min_value=pl.FACTOR_MIN,
                                    max_value=pl.FACTOR_MAX, step=0.05, format="%.2f",
                                    key=f"ms_edit_factor_{pid}")
                with c2:
                    st.selectbox("Income tax", tax_opts, key=f"ms_edit_tax_{pid}",
                                 format_func=lambda v: tax_labels.get(v, v))
                st.text_input("Note", key=f"ms_edit_note_{pid}", max_chars=pl.NOTE_MAX)
                st.form_submit_button("Save place", type="primary", on_click=_on_save_place, args=(st, pid))
            b1, b2 = st.columns(2)
            with b1:
                if not p.custom and pl.is_edited(state, pid):
                    st.button("Reset to built-in", key=f"ms_reset_{pid}", on_click=_on_reset_place, args=(st, pid))
            with b2:
                if pid != pl.HERE_ID:
                    st.button("Remove this place", key=f"ms_remove_{pid}", on_click=_on_remove_place,
                              args=(st, pid))
        if state.get("hidden"):
            st.button("Bring back removed places", key="ms_restore", on_click=_on_restore, args=(st,))

        st.markdown('<div class="ms-subhead">Add a place</div>', unsafe_allow_html=True)
        ensure_default(st, "ms_new_name", "")
        ensure_default(st, "ms_new_note", "")
        ensure_default(st, "ms_new_factor", 1.0)
        ensure_default(st, "ms_new_tax", pl.TAX_SAME)
        tax_opts = [v for _, v in pl.tax_choices()]
        tax_labels = {v: l for l, v in pl.tax_choices()}
        with st.form("ms_new_form", border=False):
            st.text_input("Name", key="ms_new_name", max_chars=pl.NAME_MAX)
            c1, c2 = st.columns(2)
            with c1:
                st.number_input("Costs compared with now (1.00 = same)", min_value=pl.FACTOR_MIN,
                                max_value=pl.FACTOR_MAX, step=0.05, format="%.2f", key="ms_new_factor")
            with c2:
                st.selectbox("Income tax", tax_opts, key="ms_new_tax",
                             format_func=lambda v: tax_labels.get(v, v))
            st.text_input("Note", key="ms_new_note", max_chars=pl.NOTE_MAX)
            st.form_submit_button("Add place", type="primary", on_click=_on_add_place, args=(st,))
        msg = st.session_state.get("ms_new_msg")
        if msg:
            st.caption(msg)


def _how_it_works(st, inp, rate: float, basis: dict, source: str, end_age) -> None:
    with st.expander("How this is calculated", expanded=False, icon=":material/help:"):
        st.markdown(
            "**Quick rule, then a real test.** Each card compares your invested balance with a target. "
            "The test costs nothing to run. It is an estimate. Press **Confirm with simulation** on a "
            "place to test it with the full Monte Carlo model.\n\n"
            f"- **Money in today's dollars.** Inflation is already taken out.\n"
            f"- **Timeline.** {'The median path of your last simulation.' if source == 'median' else 'A simple projection, because no simulation has run yet. Run one for the median path.'} "
            "Net worth adds home equity. Invested leaves it out.\n"
            f"- **FIRE in a place.** Invested balance at least yearly spending there divided by the "
            f"withdrawal rate (now **{rate * 100:.2f}%**). Spending is everyday costs, housing and children at "
            f"age {inp.retire_age} times the place's cost factor, plus health costs "
            f"(about {_md(ms.short_money(inp.health))} a year, not scaled). Your plan spends about "
            f"{_md(ms.short_money(inp.spend_core + inp.health))} a year this way.\n"
            f"- **Coast FIRE.** Your balance, left alone with no more saving, grows at "
            f"**{inp.real_return * 100:.1f}%** a year after inflation (the rate behind the net-worth "
            f"projection chart) to the FIRE number by age {inp.retire_age}.\n"
            f"- **Other markers.** Essentials are {100 - int(round(inp.discretionary_ratio * 100))}% of everyday "
            "spending plus health. Barista FIRE subtracts the part-time income you set. "
            "The emergency fund counts cash accounts only.\n"
            "- **Not in the quick rule.** Income tax, Social Security, guardrails and market swings. "
            "The simulation counts them.\n\n"
            "**What Confirm changes.** It moves your retirement spending by the cost factor and applies "
            "the place's state tax to retirement-year tax only. Your working years keep the state you "
            "live in now. Housing stays as your plan has it, so a move that changes housing is only in "
            "the cost factor.\n\n"
            f"**Rough numbers.** The built-in cost factors are illustrative guesses, not data. {pl.ABROAD_CAVEAT}"
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
    swr_rate = swr.get("swr_rate") if isinstance(swr, dict) else None

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
    inp, basis = built
    rep = ms.build(inp)
    end_age = inp.ages[-1] if len(inp.ages) else None
    overall = rep.next_up.key if rep.next_up else None
    next_keys = {k for k in (overall, first_in_progress(rep.networth), first_in_progress(rep.invested)) if k}
    clean = {k: v for k, v in overrides.items() if k != pl.KEY}
    n_sims = int(st.session_state.get("n_simulations", 1000))
    target_age = safe_int(clean.get("TARGET_RETIREMENT_AGE", 55), 55)

    st.markdown(summary_html(rep, end_age), unsafe_allow_html=True)
    st.caption("Timeline: the median path of your last simulation."
               if source == "median" else
               "Timeline: a simple projection. Run the simulation for the median path.")

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
                   "life there. Costs and tax are rough, so confirm the ones you care about.")
        _place_cards(st, rep, inp, basis, clean, results, n_sims, target_age, end_age, next_keys)
        if any(p.abroad for p in inp.places):
            st.caption(pl.ABROAD_CAVEAT)
    _edit_places(st, state, end_age)

    # ---- other markers ----
    if rep.markers:
        st.markdown('<div class="ms-subhead">Other markers</div>', unsafe_allow_html=True)
        rows = "".join(_item(m, end_age, m.key in next_keys) for m in rep.markers)
        st.markdown(f'<div class="ms-ladder ms-ladder-wide"><ul class="ms-list ms-list-grid">{rows}</ul></div>',
                    unsafe_allow_html=True)

    _how_it_works(st, inp, rate, basis, source, end_age)
