"""WHAT-IF delta pane: compares the plan WITH active lifecycle toggles
(car purchase, house move, retirement vacation, etc.) vs a BASELINE with
those toggles forced off.

Purely a display component — all numbers come from
``utils.sim_runner.run_whatif_delta``; this module renders them.
"""
from __future__ import annotations

from typing import Any, Dict

from utils.formatting import money, pct

# Human-readable labels for the lifecycle toggle config keys.
TOGGLE_LABELS = {
    "CAR_ONETIME_ENABLED": "One-time car purchase",
    "CAR_RECURRING_ENABLED": "Recurring car purchases",
    "HOUSE_MOVE_ENABLED": "House move",
    "HOME_EVENTS": "Home moves",
    "RETIREMENT_VACATION_ENABLED": "Retirement vacation spending",
}


def _fmt_age_delta(value) -> str:
    if value is None:
        return "—"
    value = int(value)
    if value == 0:
        return "No change"
    arrow = "▲" if value > 0 else "▼"
    return f"{arrow} {abs(value)} yr{'s' if abs(value) != 1 else ''}"


def _fmt_signed_pct(value) -> str:
    if value is None:
        return "—"
    arrow = "▲" if value > 0 else ("▼" if value < 0 else "")
    return f"{arrow} {pct(abs(value))}".strip()


def _fmt_signed_money(value) -> str:
    if value is None:
        return "—"
    arrow = "▲" if value > 0 else ("▼" if value < 0 else "")
    return f"{arrow} {money(abs(value), shorten=True)}".strip()


def _fmt_earliest(value) -> str:
    """Render an earliest-retirement age, or "Not achieved" when there is none.

    The results dict stores an explicit ``None`` when no age in the scan hits
    the target success rate, so ``.get(key, "Not achieved")`` does NOT catch it
    (the key exists) and the card rendered the literal text "None".
    """
    return "Not achieved" if value is None else str(value)


def _delta_color(value, higher_is_better: bool = True) -> str:
    """Light-mode color: green when the delta favors the plan, red when it hurts."""
    if value is None or value == 0:
        return "#64748b"
    favorable = (value > 0) if higher_is_better else (value < 0)
    return "#059669" if favorable else "#dc2626"


def _delta_class(value, higher_is_better: bool = True) -> str:
    """Utility class so the risk color survives dark mode (see theme_toggle)."""
    if value is None or value == 0:
        return ""  # neutral gray -> dark theme lightens it
    favorable = (value > 0) if higher_is_better else (value < 0)
    return "mc-good" if favorable else "mc-bad"


def render(st, results: Dict[str, Any] | None = None, delta: Dict[str, Any] | None = None) -> None:
    """Render the WHAT-IF pane.

    Args:
        st: the streamlit module (or a compatible mock).
        results: the output of ``utils.sim_runner.run_whatif_delta`` — a dict
            with ``scenario``, ``baseline``, ``active_toggles``, and ``delta``.
            May also be passed via the ``delta`` kwarg for callers that already
            unpacked it; if both are given, ``results`` wins.
    """
    payload = results if results is not None else delta
    if not payload:
        st.caption("Run a simulation to see the what-if comparison.")
        return

    scenario = payload.get("scenario", {}) or {}
    baseline = payload.get("baseline", {}) or {}
    active_toggles = payload.get("active_toggles", []) or []
    deltas = payload.get("delta", {}) or {}

    scenario_primary = scenario.get("primary_result", {}) or {}
    baseline_primary = baseline.get("primary_result", {}) or {}

    st.markdown('<div class="mc-section">What-if: lifecycle events</div>', unsafe_allow_html=True)

    if active_toggles:
        labels = ", ".join(TOGGLE_LABELS.get(k, k) for k in active_toggles)
        st.caption(f"Active toggles: {labels}")

    earliest_delta = deltas.get("earliest_retirement_age")
    success_delta = deltas.get("success_rate")
    median_delta = deltas.get("median_final")

    # NOTE: HTML lines must start at column 0 — Streamlit's markdown treats any
    # line indented 4+ spaces as a code block and renders the HTML verbatim,
    # even with unsafe_allow_html=True.
    html = (
        '<div class="mc-card" style="padding: 16px;">'
        '<div class="mc-ink-strong" style="font-size: 13px; font-weight: 600; margin-bottom: 10px;">'
        'Baseline (toggles off) vs. Scenario (toggles on)</div>'
        '<div style="font-size: 12px; color: #64748b;">Earliest retirement age</div>'
        f'<div class="mc-ink-strong" style="font-size: 14px; margin-bottom: 2px;">'
        f'Baseline: {_fmt_earliest(baseline.get("earliest_retirement_age"))}'
        f' &rarr; Scenario: {_fmt_earliest(scenario.get("earliest_retirement_age"))}</div>'
        f'<div class="{_delta_class(earliest_delta, higher_is_better=False)}" style="font-size: 16px; font-weight: 600; color: {_delta_color(earliest_delta, higher_is_better=False)}; margin-bottom: 10px;">'
        f'{_fmt_age_delta(earliest_delta)}</div>'
        '<div style="font-size: 12px; color: #64748b;">Success rate (target age)</div>'
        f'<div class="mc-ink-strong" style="font-size: 14px; margin-bottom: 2px;">'
        f'Baseline: {pct(baseline_primary.get("success_rate"))}'
        f' &rarr; Scenario: {pct(scenario_primary.get("success_rate"))}</div>'
        f'<div class="{_delta_class(success_delta, higher_is_better=True)}" style="font-size: 16px; font-weight: 600; color: {_delta_color(success_delta, higher_is_better=True)}; margin-bottom: 10px;">'
        f'{_fmt_signed_pct(success_delta)}</div>'
        '<div style="font-size: 12px; color: #64748b;">Median ending balance</div>'
        f'<div class="mc-ink-strong" style="font-size: 14px; margin-bottom: 2px;">'
        f'Baseline: {money(baseline_primary.get("median_final"), shorten=True)}'
        f' &rarr; Scenario: {money(scenario_primary.get("median_final"), shorten=True)}</div>'
        f'<div class="{_delta_class(median_delta, higher_is_better=True)}" style="font-size: 16px; font-weight: 600; color: {_delta_color(median_delta, higher_is_better=True)};">'
        f'{_fmt_signed_money(median_delta)}</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
