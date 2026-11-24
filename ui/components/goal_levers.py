"""Ways to reach your goal -- the card under the hero number.

Shows the levers ``utils.goal_levers`` simulated after the main run (queued by
app._queue_extras, so the main results never wait for them). Each row: the
change, a short note, a bar from today's success to the lever's, and Try it.

Try it previews the change without touching the inputs. Keep writes the
lever's overrides into ``user_overrides``, syncs the side panel's widgets and
reruns the plan (the same route as a profile load: results cleared, the
once-per-session autorun re-armed). Undo puts the previous values back the
same way. While the levers are still computing, a light placeholder shows
(never ``st.progress``: it triggers the "Simulating…" overlay).
"""
from __future__ import annotations

from html import escape

try:
    from utils import goal_levers as gl
    from utils.formatting import money, pct
    from utils.sim_runner import _hashable
except ImportError:  # pragma: no cover
    from ui.utils import goal_levers as gl  # type: ignore
    from ui.utils.formatting import money, pct  # type: ignore
    from ui.utils.sim_runner import _hashable  # type: ignore

TRY_KEY = "goal_try"            # (results stamp, row id) of the row being previewed
UNDO_KEY = "goal_undo"          # {"label", "prev", "applied"} after Keep
RERUN_KEY = "_goal_rerun_app"   # a callback asked for a whole-app rerun
MISSING = "__missing__"         # "this key wasn't in user_overrides" (for Undo)


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _fingerprint(st):
    """app._inputs_fingerprint for the current inputs (None if not hashable)."""
    ss = st.session_state
    try:
        return hash((_hashable(ss.get("user_overrides", {}) or {}),
                     int(ss.get("n_simulations", 1000))))
    except Exception:
        return None


def current_levers(st, results: dict):
    """The lever result for the results on screen, or None (not in yet)."""
    res = st.session_state.get(gl.RESULT_KEY)
    stamp = st.session_state.get("last_run_inputs_hash")
    if not isinstance(res, dict) or stamp is None or res.get("_inputs_hash") != stamp:
        return None
    primary = (results or {}).get("primary_result", {}) or {}
    if res.get("target_age") != primary.get("retirement_age"):
        return None
    return res


def pending(st) -> bool:
    """Are the levers still queued (server) or out in the browser?"""
    queued = (st.session_state.get("_extras_pending") or []) + (st.session_state.get("_extras_bg") or [])
    if any(entry[0] == "levers" for entry in queued):
        return True
    try:
        from utils import browser_compute as bc
        return bool(bc.pending(st, "levers"))
    except Exception:
        return False


def describe(changes: dict) -> str:
    """Which inputs a lever sets, in the side panel's words."""
    parts = []
    if "TARGET_RETIREMENT_AGE" in changes:
        parts.append(f"your target retirement age to {changes['TARGET_RETIREMENT_AGE']}")
    if "PARTNER_RETIREMENT_AGE" in changes:
        parts.append(f"your partner's retirement age to {changes['PARTNER_RETIREMENT_AGE']}")
    if "RETIREMENT_SPENDING_PCT" in changes:
        parts.append(f"retirement spending to {changes['RETIREMENT_SPENDING_PCT']:.0%} of today's")
    elif "RETIREMENT_SPENDING_ABSOLUTE" in changes:
        parts.append(f"retirement spending to {money(changes['RETIREMENT_SPENDING_ABSOLUTE'])} a year")
    return " and ".join(parts)


def _rerun_plan(st) -> None:
    """Results now belong to other inputs: clear them and re-arm the autorun,
    so the next script run simulates the new plan (as a profile load does)."""
    st.session_state["results"] = None
    st.session_state.pop("_autorun_done", None)
    st.session_state.pop(TRY_KEY, None)
    st.session_state[RERUN_KEY] = True


def _sync(st) -> None:
    try:
        from utils.widget_sync import sync_widgets_from_overrides
    except ImportError:  # pragma: no cover
        from ui.utils.widget_sync import sync_widgets_from_overrides  # type: ignore
    sync_widgets_from_overrides(st)


def _forget_widgets(st, keys) -> None:
    """Drop the side-panel widgets that show ``keys``, so they seed again from
    user_overrides (sync skips a None or missing value)."""
    try:
        from utils.widget_sync import DIRECT_MAPPINGS
        from utils.slider_input import forget_box
    except ImportError:  # pragma: no cover
        from ui.utils.widget_sync import DIRECT_MAPPINGS  # type: ignore
        from ui.utils.slider_input import forget_box  # type: ignore
    for widget, (key, _cast) in DIRECT_MAPPINGS.items():
        if key in keys:
            st.session_state.pop(widget, None)
            forget_box(st, widget)


def keep(st, row: dict) -> None:
    """Keep a lever: write its overrides, sync the widgets, remember how to undo."""
    ov = dict(st.session_state.get("user_overrides", {}) or {})
    changes = dict(row["changes"])
    prev = {k: ov.get(k, MISSING) for k in changes}
    ov.update(changes)
    st.session_state["user_overrides"] = ov
    _sync(st)
    st.session_state[UNDO_KEY] = {"label": row["label"], "prev": prev, "applied": changes}
    _rerun_plan(st)


def undo(st) -> None:
    """Put back the values a kept lever replaced."""
    u = st.session_state.pop(UNDO_KEY, None)
    if not u:
        return
    ov = dict(st.session_state.get("user_overrides", {}) or {})
    blank = []
    for k, v in u["prev"].items():
        if v == MISSING:
            ov.pop(k, None)
        else:
            ov[k] = v
        if v == MISSING or v is None:
            blank.append(k)
    st.session_state["user_overrides"] = ov
    _forget_widgets(st, blank)
    _sync(st)
    _rerun_plan(st)


def undo_live(st):
    """The kept change, while the inputs still hold it (else None)."""
    u = st.session_state.get(UNDO_KEY)
    if not u:
        return None
    ov = st.session_state.get("user_overrides", {}) or {}
    if all(ov.get(k) == v for k, v in u["applied"].items()):
        return u
    return None


def _toggle_try(st, stamp, row_id) -> None:
    cur = st.session_state.get(TRY_KEY)
    st.session_state[TRY_KEY] = None if cur == (stamp, row_id) else (stamp, row_id)


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _scale(res: dict) -> tuple:
    """(low, high) of the bars' shared axis: a little under the lowest value."""
    vals = [res["base"]] + [r["value"] for r in res["rows"]] + [res.get("goal") or res["target"]]
    lo = max(0.0, int((min(vals) - 0.05) * 20) / 20.0)
    return lo, 1.0


def _bar_html(base: float, value: float, line: float, lo: float, hi: float, label: str) -> str:
    def at(v):
        return (min(hi, max(lo, v)) - lo) / (hi - lo) * 100.0
    a, b = sorted((at(base), at(value)))
    return (
        f'<div class="mc-goal-bar" title="{escape(label)}: {pct(value)} (today {pct(base)})">'
        f'<div class="mc-goal-track"></div>'
        f'<div class="mc-goal-fill" style="left: {a:.1f}%; width: {b - a:.1f}%"></div>'
        f'<div class="mc-goal-line" style="left: {at(line):.1f}%"></div>'
        f'<div class="mc-goal-dot" style="left: calc({at(value):.1f}% - 6px)"></div></div>')


def _row_html(row: dict, res: dict, lo: float, hi: float, line: float, tag: str) -> str:
    mark = f' <span class="mc-good mc-goal-tag">✓ {tag}</span>' if row["hit"] else ""
    return (
        f'<div class="mc-goal-row">'
        f'<div class="mc-goal-text"><div class="mc-goal-label">{escape(row["label"])}</div>'
        f'<div class="mc-goal-sub">{escape(row["sub"]).replace("$", "&#36;")}</div></div>'
        f'{_bar_html(res["base"], row["value"], line, lo, hi, row["label"])}'
        f'<div class="mc-goal-value"><b>{pct(row["value"])}</b>{mark}</div></div>')


def _undo_bar(st) -> None:
    u = undo_live(st)
    if not u:
        return
    with st.container(key="mc-goal-undo", horizontal=True, vertical_alignment="center"):
        st.markdown(f'<div class="mc-goal-kept"><b>Kept:</b> {escape(u["label"])}.</div>'
                    .replace("$", "&#36;"), unsafe_allow_html=True)
        st.button("Undo", key="goal_undo_btn", type="tertiary", on_click=undo, args=(st,),
                  help="Put back the values you had before.")


def _preview(st, row: dict, res: dict, stale: bool) -> None:
    with st.container(key="mc-goal-preview"):
        reach = " That meets the goal." if row["hit"] else ""
        st.markdown(
            f"**Preview:** your chance of success goes from **{pct(res['base'])}** to "
            f"**{pct(row['value'])}**.{reach} Keeping it sets {describe(row['changes'])}. "
            "Nothing changes until you keep it.".replace("$", "\\$"))
        if stale:
            st.caption("Your inputs changed since this ran. Run the simulation again first.")
        with st.container(horizontal=True, key="mc-goal-preview-btns"):
            st.button("Keep this change", key="goal_keep_btn", type="primary", disabled=stale,
                      on_click=keep, args=(st, row))
            st.button("Cancel", key="goal_cancel_btn", type="tertiary",
                      on_click=lambda: st.session_state.pop(TRY_KEY, None))


def render(st, results: dict = None) -> None:
    if not results:
        return
    if st.session_state.pop(RERUN_KEY, False) and st.session_state.get("results") is not results:
        st.rerun()        # Keep/Undo clicked in this fragment: rerun the whole app
    primary = results.get("primary_result", {}) or {}
    base = primary.get("success_rate")
    if base is None:
        return
    target = float((results.get("config_snapshot", {}) or {}).get("TARGET_SUCCESS_RATE", 0.80))
    goal = gl.goal_for(base, target)
    res = current_levers(st, results)
    with st.container(key="mc-goal-card"):
        _undo_bar(st)
        if res is None:
            if pending(st):
                what = "Finding ways to reach " + pct(goal, 0) if goal else "Checking how much room you have"
                st.markdown(f'<div class="mc-goal-pending">{what}…</div>', unsafe_allow_html=True)
            return
        room = res["mode"] == "room"
        line = res["target"] if room else res["goal"]
        title = "You have room" if room else f"Ways to reach {pct(res['goal'], 0)}"
        right = (f"Today {pct(res['base'])} · target {pct(res['target'], 0)}" if room
                 else f"Goal line at {pct(res['goal'], 0)} · today {pct(res['base'])}")
        if room:
            note = (f"Your plan clears {pct(gl.ROOM_AT, 0)}. These changes still meet your "
                    f"{pct(res['target'], 0)} target.")
        else:
            note = (f"Each row is its own {res['n']:,}-run simulation. **Try it** previews the "
                    "change without touching your plan. You can then keep it or undo it.")
        st.markdown(f'<div class="mc-goal-head"><div class="mc-goal-title">{title}</div>'
                    f'<div class="mc-goal-right">{right}</div></div>'
                    f'<div class="mc-goal-note">{note.replace("**Try it**", "<b>Try it</b>")}</div>',
                    unsafe_allow_html=True)
        if not res["rows"]:
            st.caption("None of the usual changes moves your plan much. Try saving more, "
                       "or check the return scenario in Assumptions." if not room else
                       "Retiring earlier or spending more would drop you below your target.")
            return
        stale = _fingerprint(st) != st.session_state.get("last_run_inputs_hash")
        stamp = res.get("_inputs_hash")
        lo, hi = _scale(res)
        trying = st.session_state.get(TRY_KEY)
        for row in res["rows"]:
            open_ = trying == (stamp, row["id"])
            with st.container(key=f"mc-goal-row-{row['id']}", horizontal=True,
                              vertical_alignment="center"):
                st.markdown(_row_html(row, res, lo, hi, line, "target" if room else "goal"),
                            unsafe_allow_html=True)
                st.button("Close" if open_ else "Try it", key=f"goal_try_{row['id']}",
                          on_click=_toggle_try, args=(st, stamp, row["id"]),
                          help=None if open_ else "See what this change does. Your inputs stay the same.")
            if open_:
                _preview(st, row, res, stale)
