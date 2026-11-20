"""Deep dives -> Roth conversions: which conversion plan works best for you?

A button runs ``sim_runner.plan_roth_sweep``: your plan at the target age with
no conversions, "fill the 12% / 22% / 24% bracket" x a yearly cap of
$50K / $100K / $200K, and your current setting. All of them replay the same
market paths, so the differences come from the setting, not from luck. Cells
within simulation noise of the best (2 paired standard errors) are marked, so
a tie is not sold as a winner.

"Use best" writes the three Roth keys into ``user_overrides`` (with Undo);
"Preview best as a scenario" runs the full analysis on the best setting and
pins it, next to your current plan, in Scenario comparison (What if tile).
"""
from __future__ import annotations

import html

try:
    from utils.formatting import money, pct
    from utils.sim_runner import _hashable
except ImportError:  # pragma: no cover
    from ui.utils.formatting import money, pct  # type: ignore
    from ui.utils.sim_runner import _hashable  # type: ignore

STATE_KEY = "roth_sweep_result"
APPLIED_KEY = "roth_sweep_applied"
PIN_NOTE_KEY = "roth_sweep_pinned"
KIND = "roth"
_KEYS = ("ENABLE_ROTH_CONVERSION", "ROTH_CONVERSION_TARGET_BRACKET", "ROTH_CONVERSION_MAX_ANNUAL")
_ABSENT = "__absent__"

# One sequential teal ramp per theme: (low, high) success. Dark mode is its own
# ramp (low sits near the dark tile, high is the bright accent), not a flip.
_RAMP_LIGHT = ("#e3f4f0", "#0f5c55")
_RAMP_DARK = ("#2a4744", "#5eead4")


def _k(v) -> str:
    """A yearly cap in short form: $50K, $100K, $1.2M."""
    v = float(v or 0)
    return f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v / 1e3:,.0f}K"


def _m(v) -> str:
    """A balance in short form: $9.2M, $177.5K."""
    return money(v, 0, shorten=True)


def _inputs_hash(overrides: dict, n_sims: int, target_age: int):
    try:
        return hash((_hashable(overrides), int(n_sims), int(target_age)))
    except Exception:
        return None


def _hex(c: str):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb) -> float:
    def ch(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cell_colors(success: float, lo: float, hi: float, dark: bool):
    """(fill, text) for a cell: the ramp position by success, the text color by
    the fill's luminance (dark ink on light fills, white on dark ones)."""
    a, b = (_hex(c) for c in (_RAMP_DARK if dark else _RAMP_LIGHT))
    t = 0.5 if hi - lo < 1e-9 else min(1.0, max(0.0, (success - lo) / (hi - lo)))
    rgb = tuple(round(x + (y - x) * t) for x, y in zip(a, b))
    fill = "#%02x%02x%02x" % rgb
    ink = "#0f172a" if _luminance(rgb) > 0.30 else "#ffffff"
    return fill, ink


def setting_label(cell: dict, rows: list) -> str:
    """Plain name of a setting, e.g. "Fill the 12% bracket, up to $50K a year"."""
    if not cell.get("enabled"):
        return "No conversions"
    name = next((r["label"] for r in rows if int(r["target"]) == int(cell.get("target") or -1)),
                f"Fill to income of {money(cell.get('target'))}")
    return f"{name}, up to {_k(cell.get('cap'))} a year"


def _grid_html(res: dict, dark: bool) -> str:
    cells, rows, caps = res["cells"], res["rows"], res["caps"]
    best = res["best_key"]
    offered = [c for k, c in cells.items() if k != "current"]
    hi = max(c["success"] for c in offered)
    # At least a 10-point span, so a 1-point gap doesn't look like night and day.
    lo = min(min(c["success"] for c in offered), hi - 0.10)
    head = "".join(f'<th scope="col">Up to {_k(c)}/yr</th>' for c in caps)
    body = []
    for row in rows:
        tds = []
        for cap in caps:
            c = cells[f"{row['rate']:.2f}|{cap}"]
            fill, ink = cell_colors(c["success"], lo, hi, dark)
            tag = ""
            cls = "mc-roth-cell"
            if c["key"] == best:
                cls += " is-best"
                tag = '<span class="mc-roth-tag">BEST</span>'
            elif c["within_noise"]:
                tag = '<span class="mc-roth-tag">≈ best</span>'
            tip = (f"{row['label']}, up to {_k(cap)} a year: "
                   f"{pct(c['success'])} success, {_m(c['median_final'])} "
                   f"median at the end, {_m(c['median_taxes'])} median taxes in retirement")
            tds.append(
                f'<td class="{cls}" style="background:{fill};color:{ink}" tabindex="0" '
                f'title="{html.escape(tip)}" aria-label="{html.escape(tip)}">'
                f'<span class="mc-roth-pct">{c["success"]:.0%}</span>'
                f'<span class="mc-roth-sub">{_m(c["median_final"])}<span class="mc-roth-left"> left</span></span>'
                f'{tag}</td>')
        body.append(f'<tr><th scope="row">{html.escape(row["label"])}</th>{"".join(tds)}</tr>')
    return (f'<div class="mc-roth-wrap"><table class="mc-roth-grid">'
            f'<caption>Chance of success at {res["retirement_age"]} and the median left at the end, '
            f'by conversion plan</caption>'
            f'<thead><tr><td></td>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def _refs_html(res: dict, before: bool = False) -> str:
    """The two reference points beside the grid: no conversions, your setting."""
    cells = res["cells"]
    off, cur = cells["off"], cells[res["current_key"]]
    best = res["best_key"]

    def chip(title, c, extra=""):
        tag = ('<span class="mc-roth-chip-tag">BEST</span>' if c["key"] == best else
               ('<span class="mc-roth-chip-tag">≈ best</span>' if c["within_noise"] else ""))
        return (f'<div class="mc-roth-chip{" is-best" if c["key"] == best else ""}">'
                f'<span class="mc-roth-chip-k">{html.escape(title)}</span>'
                f'<b>{c["success"]:.0%}</b> · {_m(c["median_final"])} left{extra}{tag}</div>')

    who = "Your setting before" if before else "Your current setting"
    if not res["current_enabled"]:
        cur_title = f"{who} (no conversions)"
        return f'<div class="mc-roth-refs">{chip(cur_title, off)}</div>'
    cur_title = (f"{who} (fill to {money(res['current_target'])}, "
                 f"up to {_k(res['current_cap'])}/yr)")
    return f'<div class="mc-roth-refs">{chip("No conversions", off)}{chip(cur_title, cur)}</div>'


def _table(st, res: dict) -> None:
    import pandas as pd
    cells, rows = res["cells"], res["rows"]
    best = cells[res["best_key"]]
    order = ["off"] + [f"{r['rate']:.2f}|{c}" for r in rows for c in res["caps"]]
    if res["current_key"] == "current":
        order.append("current")
    out = []
    for k in order:
        c = cells[k]
        name = setting_label(c, rows) + (" (your setting)" if k == res["current_key"] else "")
        gap = (c["success"] - best["success"]) * 100
        out.append({
            "Plan": name,
            "Success": pct(c["success"]),
            "vs best": "best" if k == res["best_key"] else
            (f"{gap:+.1f} points" + (" (within noise)" if c["within_noise"] else "")),
            "Median left at the end": _m(c["median_final"]),
            "Median taxes in retirement": _m(c["median_taxes"]),
        })
    st.dataframe(pd.DataFrame(out), width="stretch", hide_index=True)


def _apply(st, best: dict) -> None:
    """Write the best setting into the inputs, keeping the old values for Undo."""
    try:
        from utils.widget_sync import sync_widgets_from_overrides
    except ImportError:  # pragma: no cover
        from ui.utils.widget_sync import sync_widgets_from_overrides  # type: ignore
    ov = st.session_state.setdefault("user_overrides", {})
    prev = {k: ov.get(k, _ABSENT) for k in _KEYS}
    ov["ENABLE_ROTH_CONVERSION"] = bool(best["enabled"])
    if best["enabled"]:
        ov["ROTH_CONVERSION_TARGET_BRACKET"] = int(best["target"])
        ov["ROTH_CONVERSION_MAX_ANNUAL"] = int(best["cap"])
    sync_widgets_from_overrides(st)
    st.session_state[APPLIED_KEY] = {"prev": prev, "after": {k: ov.get(k, _ABSENT) for k in _KEYS}}


def _undo(st) -> None:
    try:
        from utils.widget_sync import sync_widgets_from_overrides
    except ImportError:  # pragma: no cover
        from ui.utils.widget_sync import sync_widgets_from_overrides  # type: ignore
    rec = st.session_state.pop(APPLIED_KEY, None) or {}
    ov = st.session_state.setdefault("user_overrides", {})
    for k, v in (rec.get("prev") or {}).items():
        if v == _ABSENT:
            ov.pop(k, None)
        else:
            ov[k] = v
    sync_widgets_from_overrides(st)


def _best_overrides(overrides: dict, best: dict) -> dict:
    out = dict(overrides, ENABLE_ROTH_CONVERSION=bool(best["enabled"]))
    if best["enabled"]:
        out.update(ROTH_CONVERSION_TARGET_BRACKET=int(best["target"]),
                   ROTH_CONVERSION_MAX_ANNUAL=int(best["cap"]))
    return out


def _preview(st, overrides: dict, best: dict, label: str, results: dict,
             n_sims: int, target_age: int) -> None:
    """Pin the best setting (full analysis) and your current plan side by side."""
    try:
        from utils import sim_runner as sr
        from utils import browser_compute as bc
        from components.scenario_compare import _pinned, _extract_summary
    except ImportError:  # pragma: no cover
        from ui.utils import sim_runner as sr  # type: ignore
        from ui.utils import browser_compute as bc  # type: ignore
        from ui.components.scenario_compare import _pinned, _extract_summary  # type: ignore
    best_ov = _best_overrides(overrides, best)
    name = f"Best Roth plan: {label}"

    def store(res):
        pinned = _pinned(st)
        if results and not any((e or {}).get("overrides") == overrides for e in pinned.values()):
            pinned["Current plan"] = {"summary": _extract_summary(results), "overrides": dict(overrides)}
        pinned[name] = {"summary": _extract_summary(res), "overrides": best_ov}
        st.session_state[PIN_NOTE_KEY] = name

    bc.run_or_submit(st, "roth_preview", sr.plan_full_analysis(best_ov, int(n_sims), int(target_age)),
                     store, "Simulating the best plan…")


def render(st, results: dict = None) -> None:
    st.markdown('<div class="mc-section">Which Roth conversion plan works best for you?</div>',
                unsafe_allow_html=True)
    if not results:
        st.caption("Run the main simulation first.")
        return
    try:
        from utils import sim_runner as sr
        from utils import browser_compute as bc
        from utils.plot_theme import is_dark
        from utils.validation import validate_run_inputs
    except ImportError:  # pragma: no cover
        from ui.utils import sim_runner as sr  # type: ignore
        from ui.utils import browser_compute as bc  # type: ignore
        from ui.utils.plot_theme import is_dark  # type: ignore
        from ui.utils.validation import validate_run_inputs  # type: ignore

    overrides = dict(st.session_state.get("user_overrides", {}) or {})
    n_sims = int(st.session_state.get("n_simulations", 1000))
    target_age = int(overrides.get("TARGET_RETIREMENT_AGE", 55) or 55)
    st.caption(
        "A Roth conversion moves money from traditional to Roth accounts. You pay tax now, "
        "so later withdrawals are tax-free. This tries 9 conversion plans plus none, on the "
        "same simulated markets, and shows which one gives your plan the best chance."
    )

    res = st.session_state.get(STATE_KEY)
    cur_hash = _inputs_hash(overrides, n_sims, target_age)
    fresh = bool(res) and cur_hash is not None and res.get("_inputs_hash") == cur_hash
    applied = st.session_state.get(APPLIED_KEY)
    just_applied = bool(applied) and all(
        overrides.get(k, _ABSENT) == v for k, v in (applied.get("after") or {}).items())
    waiting = bool(bc.pending(st, KIND))
    label = ("✓ Plans up to date" if fresh else
             ("Comparing plans…" if waiting else "Find my best Roth conversion plan"))
    if st.button(label, key="roth_sweep_btn", type="primary", disabled=fresh or waiting,
                 help="Up to date. Change an input or the simulation count to run it again."
                 if fresh else None):
        errs = validate_run_inputs(overrides, target_age)
        if errs:
            for e in errs:
                st.error(e)
            return

        def store(r):
            st.session_state[STATE_KEY] = {**r, "_inputs_hash": cur_hash}

        bc.run_or_submit(st, KIND, sr.plan_roth_sweep(overrides, n_sims, target_age), store,
                         "Comparing Roth conversion plans…")
        st.rerun()

    if not res:
        st.caption("It runs about 11 extra simulations of your plan, so it takes a little while.")
        return
    if not fresh and not just_applied:
        st.warning("Your inputs changed since this ran. Click the button to update it.")

    st.markdown(_grid_html(res, is_dark(st)), unsafe_allow_html=True)
    st.markdown(_refs_html(res, before=just_applied), unsafe_allow_html=True)

    cells, rows = res["cells"], res["rows"]
    best = cells[res["best_key"]]
    best_label = setting_label(best, rows)
    near = [k for k, c in cells.items() if c["within_noise"] and k != "current"]
    n = res.get("n_simulations", 0)
    note = (f"Each plan ran the same {n:,} simulated markets. "
            f"Fills are income before the {money(res['standard_deduction'])} standard deduction. ")
    if near:
        note += (f"Plans marked ≈ best are within simulation noise of the best "
                 f"(2 standard errors). Treat them as a tie.")
    else:
        note += "No other plan comes within simulation noise of the best."
    if res.get("two_returns"):
        note += " You file two returns, so each of you fills your own return to this amount."
    st.caption(note)

    is_current = (res["current_key"] == res["best_key"]
                  or (overrides.get("ENABLE_ROTH_CONVERSION", True) == bool(best["enabled"])
                      and (not best["enabled"] or (
                          overrides.get("ROTH_CONVERSION_TARGET_BRACKET") == best["target"]
                          and overrides.get("ROTH_CONVERSION_MAX_ANNUAL") == best["cap"]))))
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✓ You use the best plan" if is_current else f"Use best: {best_label}",
                     key="roth_use_best", type="primary", disabled=is_current, width="stretch"):
            _apply(st, best)
            st.rerun()
    with c2:
        if st.button("Preview best as a scenario", key="roth_preview_best", width="stretch",
                     disabled=bool(bc.pending(st, "roth_preview"))):
            _preview(st, overrides, best, best_label, results, n_sims, target_age)
            st.rerun()

    if just_applied:
        u1, u2 = st.columns([3, 1], vertical_alignment="center")
        with u1:
            st.success(f"Now using: {best_label}. Run the simulation to update your results.")
        with u2:
            if st.button("Undo", key="roth_undo", width="stretch"):
                _undo(st)
                st.rerun()
    pinned = st.session_state.get(PIN_NOTE_KEY)
    if pinned:
        st.caption(f"Pinned **{pinned}** next to your current plan. See Scenario comparison "
                   "in the What if tile.")

    with st.expander("Show as a table", expanded=False):
        _table(st, res)
        st.caption("Taxes are the income tax and penalties paid from your accounts in "
                   "retirement, per simulated life, in today's dollars.")
