"""Deep dives -> Stress tests: "If you had retired in a real year".

Replays the plan through real market history (``sim_runner.plan_historical_backtest``
-> ``run_detailed_simulation(historical_start_year=Y)``): retiring at the target
age in each start year whose whole plan fits in the 1926-2024 data. Shows how
many start years last to the end next to the Monte Carlo answer, the hardest
periods (found from the results), and a year grid by decade. Button-gated.
"""
from __future__ import annotations

import html
from typing import Dict, List

try:
    from utils.formatting import money, pct
    from utils.sim_runner import _hashable
except ImportError:  # pragma: no cover
    from ui.utils.formatting import money, pct  # type: ignore
    from ui.utils.sim_runner import _hashable  # type: ignore

STATE_KEY = "backtest_result"
KIND = "backtest"


def _inputs_hash(overrides: dict, target_age: int):
    try:
        return hash((_hashable(overrides), int(target_age)))
    except Exception:
        return None


def _span(a: int, b: int) -> str:
    return str(a) if a == b else f"{a}–{b}"


def _join(parts: List[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def hardest_starts(runs: List[dict]) -> Dict[str, str]:
    """A headline and a detail line about the worst start years, from the runs.

    Failing years are grouped into runs of consecutive years; the (up to) three
    periods whose money ran out soonest are named, in time order. With no
    failures, the closest call (the smallest ending balance) is named instead.
    """
    fails = [r for r in runs if not r.get("ok")]
    if not runs:
        return {"head": "", "detail": ""}
    if not fails:
        low = min(runs, key=lambda r: r.get("end") or 0.0)
        return {"head": "Every start year lasted to the end.",
                "detail": f"Closest call: retiring in {low['year']} left "
                          f"{money(low.get('end'), 0, shorten=True)}."}
    periods: List[List[dict]] = []
    for r in fails:
        if periods and r["year"] == periods[-1][-1]["year"] + 1:
            periods[-1].append(r)
        else:
            periods.append([r])
    worst = sorted(periods, key=lambda p: (min(x["out_age"] for x in p), -len(p)))[:3]
    worst.sort(key=lambda p: p[0]["year"])
    head = "Hardest starts: " + _join([_span(p[0]["year"], p[-1]["year"]) for p in worst]) + "."
    soonest = min(r["out_age"] for r in fails)
    years = [str(r["year"]) for r in fails if r["out_age"] == soonest]
    detail = (f"Money runs out soonest, at age {soonest}, retiring in {_join(years[:3])}.")
    return {"head": head, "detail": detail}


def _tip(r: dict) -> str:
    if r.get("ok"):
        return f"Retire in {r['year']}: lasted; {money(r.get('end'), 0, shorten=True)} left at the end"
    return f"Retire in {r['year']}: money runs out at age {r['out_age']}"


def grid_html(runs: List[dict]) -> str:
    """The year grid: one row per decade, a label column, ten equal cells."""
    by_year = {r["year"]: r for r in runs}
    if not by_year:
        return ""
    first, last = min(by_year) // 10 * 10, max(by_year) // 10 * 10
    rows = []
    for dec in range(first, last + 10, 10):
        cells = []
        for y in range(dec, dec + 10):
            r = by_year.get(y)
            if r is None:
                cells.append('<div class="mc-bt-cell is-empty" aria-hidden="true"></div>')
                continue
            ok = bool(r.get("ok"))
            tip = html.escape(_tip(r))
            cells.append(
                f'<div class="mc-bt-cell {"is-ok" if ok else "is-out"}" role="listitem" tabindex="0" '
                f'aria-label="{tip}" data-tip="{tip}">'
                f'<span class="mc-bt-ico" aria-hidden="true">{"✓" if ok else "✕"}</span>'
                f'<span class="mc-bt-yr">{y}</span>'
                f'<span class="mc-bt-age">{"lasted" if ok else "age " + str(r["out_age"])}</span>'
                f'</div>')
        rows.append(f'<div class="mc-bt-row"><div class="mc-bt-dec">{dec}s</div>'
                    f'<div class="mc-bt-cells" role="list" aria-label="Retiring in the {dec}s">'
                    f'{"".join(cells)}</div></div>')
    return f'<div class="mc-bt-grid">{"".join(rows)}</div>'


def _summary_html(runs: List[dict], sim_rate, sim_age, ret_age) -> str:
    n_ok = sum(1 for r in runs if r.get("ok"))
    hs = hardest_starts(runs)
    sim_block = ""
    if sim_rate is not None:
        sim_cap = "the simulation's answer" + (f" (at {sim_age})" if sim_age and sim_age != ret_age else "")
        sim_block = (f'<div class="mc-bt-stat"><div class="mc-bt-big">{sim_rate:.0%}</div>'
                     f'<div class="mc-bt-cap">{sim_cap}</div></div>')
    return (
        '<div class="mc-bt-summary">'
        f'<div class="mc-bt-stat"><div class="mc-bt-big">{n_ok} of {len(runs)}</div>'
        f'<div class="mc-bt-cap">start years last to the end ({n_ok / len(runs):.0%})</div></div>'
        f'{sim_block}'
        f'<div class="mc-bt-hard"><div class="mc-bt-hard-head">{html.escape(hs["head"])}</div>'
        f'<div class="mc-bt-cap">{html.escape(hs["detail"])}</div></div>'
        '</div>')


def _table(st, runs: List[dict]) -> None:
    import pandas as pd
    st.dataframe(pd.DataFrame([{
        "Retire in": str(r["year"]),
        "Result": "✓ Lasted" if r.get("ok") else "✕ Ran out",
        "Runs out at age": "—" if r.get("ok") else str(r["out_age"]),
        "Left at the end": money(r.get("end"), 0, shorten=True) if r.get("ok") else "$0",
    } for r in runs]), width="stretch", hide_index=True)


def render(st, results: dict = None) -> None:
    st.markdown('<div class="mc-section">If you had retired in a real year</div>',
                unsafe_allow_html=True)
    if not results:
        st.caption("Run the main simulation first.")
        return
    try:
        from utils import sim_runner as sr
        from utils import browser_compute as bc
        from utils.validation import validate_run_inputs
    except ImportError:  # pragma: no cover
        from ui.utils import sim_runner as sr  # type: ignore
        from ui.utils import browser_compute as bc  # type: ignore
        from ui.utils.validation import validate_run_inputs  # type: ignore

    overrides = dict(st.session_state.get("user_overrides", {}) or {})
    target_age = int(overrides.get("TARGET_RETIREMENT_AGE", 55) or 55)
    res = st.session_state.get(STATE_KEY)
    cur_hash = _inputs_hash(overrides, target_age)
    fresh = bool(res) and cur_hash is not None and res.get("_inputs_hash") == cur_hash
    waiting = bool(bc.pending(st, KIND))

    if res and res.get("runs"):
        runs = res["runs"]
        st.caption(
            f"Your plan replayed through real market history: retiring at {res['retirement_age']} "
            f"in each year from {runs[0]['year']} to {runs[-1]['year']}."
            + (f" The {res['working_years']} working years before use the years just before."
               if res.get("working_years") else ""))
    else:
        st.caption("Replays your plan through real market history: what if you had retired "
                   "in 1929, 1966 or 2000? Each start year is one real sequence of returns.")

    label = ("✓ Replay up to date" if fresh else
             ("Replaying…" if waiting else "Replay my plan through history"))
    if st.button(label, key="backtest_btn", type="primary", disabled=fresh or waiting,
                 help="Up to date. Change an input to run it again." if fresh else None):
        errs = validate_run_inputs(overrides, target_age)
        if errs:
            for e in errs:
                st.error(e)
            return

        def store(r):
            st.session_state[STATE_KEY] = {**r, "_inputs_hash": cur_hash}

        bc.run_or_submit(st, KIND, sr.plan_historical_backtest(overrides, target_age), store,
                         "Replaying your plan through history…")
        st.rerun()

    if not res:
        return
    runs = res.get("runs") or []
    if not runs:
        st.info("Couldn't replay this plan. Check your inputs and try again.")
        return
    if not fresh:
        st.warning("Your inputs changed since this ran. Click the button to update it.")

    pr = (results or {}).get("primary_result", {}) or {}
    st.markdown(_summary_html(runs, pr.get("success_rate"), pr.get("retirement_age"),
                              res["retirement_age"]), unsafe_allow_html=True)
    st.markdown(grid_html(runs), unsafe_allow_html=True)
    st.markdown('<div class="mc-bt-legend"><span>✓ lasted to the end of the plan</span>'
                '<span>✕ ran out, at the age shown</span>'
                '<span>Hover or tab to a year for details</span></div>', unsafe_allow_html=True)
    with st.expander("Show as a table", expanded=False):
        _table(st, runs)

    outside = sum(1 for r in runs if r.get("outside_data"))
    cap = (f"Stocks and bonds follow real (after-inflation) US returns from {res['data_first']} "
           f"to {res['data_last']}, at your plan's mix, less fees. ")
    if outside:
        cap += (f"For {outside} start years, part of the plan falls outside that range. "
                "Those years earn your expected return, with no ups and downs. ")
    else:
        cap += "Every year of every replay is in the data. "
    cap += (f"That is only {len(runs)} overlapping paths, so a good record here is not a promise. "
            "Past sequences don't set the limits for the future.")
    st.caption(cap)
