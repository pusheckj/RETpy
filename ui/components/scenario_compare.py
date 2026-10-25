"""Read-only side-by-side scenario comparison.

Lets the user "pin" the current results (already computed by
``utils.sim_runner.run_full_analysis``) under a name, then shows all pinned
scenarios side by side: earliest retirement age, success rate at the target
age, and median/p10 ending balance.

No simulation code is touched by the pinning/summary itself — that purely
snapshots and displays existing ``results`` dicts already sitting in
``st.session_state.results``. The "Compare inputs" section below DOES run
small preview simulations (n=500, mirroring sensitivity_tab.py's pattern) to
estimate a differing input's isolated effect, but never touches the main
``user_overrides``/``results``.
"""
from __future__ import annotations

from typing import Any, Dict

from utils.formatting import money, pct

_STATE_KEY = "pinned_scenarios"
_NO_VALUE = object()  # sentinel: key wasn't in this scenario's overrides at pin time


def _extract_summary(results: dict) -> Dict[str, Any]:
    """Pull the handful of comparable metrics out of a results dict.

    Defensive: every lookup falls back to a safe default so a partially
    populated results dict (or future shape change) never raises here.
    """
    primary = (results or {}).get("primary_result", {}) or {}
    return {
        "earliest_retirement_age": (results or {}).get("earliest_retirement_age"),
        "target_age": primary.get("retirement_age"),
        "success_rate": primary.get("success_rate"),
        "median_final": primary.get("median_final"),
        "p10_final": primary.get("p10_final"),
    }


def _pinned(st) -> Dict[str, Any]:
    if _STATE_KEY not in st.session_state or st.session_state[_STATE_KEY] is None:
        st.session_state[_STATE_KEY] = {}
    return st.session_state[_STATE_KEY]


def render(st, results: dict | None) -> None:
    """Render the pin control plus a side-by-side comparison table.

    Args:
        st: the streamlit module (or a compatible mock).
        results: the currently active results dict (``st.session_state.results``),
            or None if no simulation has been run yet.
    """
    pinned = _pinned(st)

    st.markdown('<div class="mc-section">Scenario comparison</div>', unsafe_allow_html=True)

    if not results:
        st.caption("Run a simulation to pin a scenario.")
        return

    with st.form("pin_scenario_form", clear_on_submit=True):
        cols = st.columns([3, 1], vertical_alignment="bottom")
        with cols[0]:
            default_name = f"Scenario {len(pinned) + 1}"
            name = st.text_input("Name this scenario", value=default_name, key="pin_scenario_name")
        with cols[1]:
            submitted = st.form_submit_button("📌 Pin current scenario", width="stretch")
    if submitted:
        label = (name or "").strip() or f"Scenario {len(pinned) + 1}"
        pinned[label] = {
            "summary": _extract_summary(results),
            "overrides": dict(st.session_state.get("user_overrides", {})),
        }

    if not pinned:
        st.caption("No scenarios pinned yet. Run a simulation, then pin it to compare.")
        return

    # Simple clear-all control; keeps the feature read-only/low-risk (no
    # per-row delete UI needed for a v1 comparison view).
    if st.button("Clear pinned scenarios", key="clear_pinned_scenarios", width="stretch"):
        pinned.clear()
        return

    cols = st.columns(len(pinned))
    for col, (label, entry) in zip(cols, pinned.items()):
        # Defensive fallback in case anything else ever writes the old flat
        # (pre-input-snapshot) shape directly.
        summary = entry.get("summary", entry) if isinstance(entry, dict) else entry
        with col:
            earliest = summary.get("earliest_retirement_age")
            earliest_str = str(earliest) if earliest is not None else "Not achieved"
            st.markdown(
                f'''
                <div class="mc-card" style="padding: 16px; height: 100%;">
                    <div class="mc-ink-strong" style="font-size: 13px; font-weight: 600; margin-bottom: 10px;">
                        {label}
                    </div>
                    <div style="font-size: 12px; color: #64748b;">Earliest retirement age</div>
                    <div class="mc-teal" style="font-size: 22px; font-weight: 600; color: #0d9488; margin-bottom: 8px;">
                        {earliest_str}
                    </div>
                    <div style="font-size: 12px; color: #64748b;">Success rate (target age)</div>
                    <div class="mc-ink-strong" style="font-size: 18px; font-weight: 600; margin-bottom: 8px;">
                        {pct(summary.get("success_rate"))}
                    </div>
                    <div style="font-size: 12px; color: #64748b;">Median ending balance</div>
                    <div class="mc-ink-strong" style="font-size: 16px; font-weight: 600; margin-bottom: 8px;">
                        {money(summary.get("median_final"), shorten=True)}
                    </div>
                    <div style="font-size: 12px; color: #64748b;">P10 ending balance</div>
                    <div class="mc-ink-strong" style="font-size: 16px; font-weight: 600;">
                        {money(summary.get("p10_final"), shorten=True)}
                    </div>
                </div>
                ''',
                unsafe_allow_html=True,
            )

    _render_compare_inputs(st, pinned)


def diff_overrides(overrides_a: dict, overrides_b: dict) -> list[tuple[str, Any, Any]]:
    """Every key that differs between two override dicts, sorted by name.

    A key present in only one side compares against ``_NO_VALUE`` (rendered
    as "(default)" — the engine's built-in default applies when a key is
    simply absent from an overrides dict).
    """
    all_keys = sorted(set(overrides_a) | set(overrides_b))
    diffs = []
    for key in all_keys:
        va = overrides_a.get(key, _NO_VALUE)
        vb = overrides_b.get(key, _NO_VALUE)
        if va is _NO_VALUE and vb is _NO_VALUE:
            continue
        if va == vb:
            continue
        diffs.append((key, va, vb))
    return diffs


def _render_compare_inputs(st, pinned: Dict[str, Any]) -> None:
    labels = list(pinned.keys())
    if len(labels) < 2:
        return

    st.markdown("#### Compare inputs")
    cols = st.columns(2)
    with cols[0]:
        label_a = st.selectbox("Scenario A", labels, index=0, key="scenario_compare_a")
    with cols[1]:
        label_b = st.selectbox(
            "Scenario B", labels, index=min(1, len(labels) - 1), key="scenario_compare_b"
        )
    if label_a == label_b:
        st.caption("Pick two different scenarios to compare their inputs.")
        return

    entry_a, entry_b = pinned[label_a], pinned[label_b]
    overrides_a = (entry_a.get("overrides") or {}) if isinstance(entry_a, dict) else {}
    overrides_b = (entry_b.get("overrides") or {}) if isinstance(entry_b, dict) else {}
    if not overrides_a and not overrides_b:
        st.caption(
            "These scenarios were pinned before input snapshots were added — "
            "re-pin them to compare inputs."
        )
        return

    diffs = diff_overrides(overrides_a, overrides_b)
    if not diffs:
        st.caption("No differing inputs between these two scenarios.")
        return

    import pandas as pd

    def _fmt(v):
        return "(default)" if v is _NO_VALUE else v

    table = pd.DataFrame(
        [{"Input": k, label_a: _fmt(va), label_b: _fmt(vb)} for k, va, vb in diffs]
    )
    st.dataframe(table, width="stretch", hide_index=True)
    st.caption(
        "Click **Compute impact** on a row to isolate that ONE input's effect "
        "(Scenario A's inputs, with just that key swapped to Scenario B's "
        "value, re-run at a lighter simulation count). Same one-variable-at-a-"
        "time approximation the Sensitivity tab already uses — effects are not "
        "guaranteed to add up exactly to the full A-vs-B gap."
    )

    impacts = st.session_state.setdefault("scenario_compare_impacts", {})
    summary_a = entry_a.get("summary", {}) if isinstance(entry_a, dict) else {}
    base_earliest = summary_a.get("earliest_retirement_age")
    base_success = summary_a.get("success_rate")
    target_age_a = int(overrides_a.get("TARGET_RETIREMENT_AGE", 55) or 55)

    for key, va, vb in diffs:
        impact_key = f"{label_a}|{label_b}|{key}"
        row_cols = st.columns([3, 2, 3])
        with row_cols[0]:
            st.caption(f"**{key}**")
        with row_cols[1]:
            clicked = st.button("Compute impact", key=f"cmp_impact_{impact_key}", width="stretch")
        if clicked:
            from utils.sim_runner import run_full_analysis

            merged = dict(overrides_a)
            if vb is _NO_VALUE:
                merged.pop(key, None)
            else:
                merged[key] = vb
            res = run_full_analysis(merged, n_simulations=500, target_retirement_age=target_age_a)
            impacts[impact_key] = {
                "earliest_retirement_age": res.get("earliest_retirement_age"),
                "success_rate": (res.get("primary_result", {}) or {}).get("success_rate"),
            }
        with row_cols[2]:
            impact = impacts.get(impact_key)
            if not impact:
                st.caption("—")
                continue
            d_age = None
            new_age = impact.get("earliest_retirement_age")
            if new_age is not None and base_earliest is not None:
                d_age = new_age - base_earliest
            d_success = None
            new_success = impact.get("success_rate")
            if new_success is not None and base_success is not None:
                d_success = new_success - base_success
            age_str = f"{d_age:+d}yr" if d_age is not None else "—"
            succ_str = f"{d_success * 100:+.1f}pp" if d_success is not None else "—"
            st.caption(f"earliest {age_str} · success {succ_str}")
