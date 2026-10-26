"""Sticky top bar for the main pane.

Renders a full-width bar that stays pinned to the top of the main content
area as the user scrolls (position: sticky, styled via the `.mc-topbar`
class in theme.css, with dark-mode overrides in theme_toggle.py).

Content left -> right: a compact "Retirement Monte Carlo" title, then the
household metrics: NAME(S), NET WORTH, INCOME, TARGET RETIREMENT AGE, and
SUCCESS @ TARGET.

IMPORTANT: the HTML is built with left-aligned string concatenation (NOT
4-space-indented multiline blocks). Streamlit's markdown renderer treats a
4-space indent as a code fence, which previously caused the bar to render as
a literal code block (this bit us in what_if_pane).
"""
from __future__ import annotations

from html import escape
from typing import Any, Dict, Optional

# Dual-import shim so the module works whether imported as `components.top_bar`
# (ui/ on sys.path) or `ui.components.top_bar`.
try:
    from utils.formatting import money
except Exception:  # pragma: no cover
    try:
        from ui.utils.formatting import money  # type: ignore
    except Exception:  # pragma: no cover
        def money(value, precision: int = 0, shorten: bool = False) -> str:
            try:
                return f"${float(value):,.0f}"
            except Exception:
                return "—"

try:
    from utils.derived import compute_total_income as _compute_total_income
except Exception:  # pragma: no cover
    try:
        from ui.utils.derived import compute_total_income as _compute_total_income  # type: ignore
    except Exception:  # pragma: no cover
        _compute_total_income = None


# Net-worth account keys summed from overrides when no snapshot is available.
_NET_WORTH_KEYS = (
    "YOUR_401K", "YOUR_ROTH_IRA", "YOUR_TRADITIONAL_IRA", "YOUR_HSA",
    "YOUR_BROKERAGE", "YOUR_CASH",
    "PARTNER_401K", "PARTNER_ROTH_IRA", "PARTNER_BROKERAGE", "PARTNER_CASH",
)

_INCOME_KEYS = (
    "YOUR_BASE_SALARY", "YOUR_BONUS_AMOUNT", "YOUR_RSU_AMOUNT", "YOUR_OTHER_INCOME",
    "PARTNER_BASE_SALARY", "PARTNER_BONUS_AMOUNT", "PARTNER_RSU_AMOUNT", "PARTNER_OTHER_INCOME",
)


def _num(value) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _resolve_names(profile: Optional[str]) -> str:
    """Parse a display name from the profile label.

    "My situation (You & Partner)" -> "You & Partner"; "Custom (...)" -> "Your
    plan"; else the profile as-is; else "Household". The personal profile's label comes from its JSON file.
    """
    try:
        if profile:
            s = str(profile)
            if s.startswith("Custom"):      # values the visitor entered (setup, JSON load)
                return "Your plan"
            if "(" in s and ")" in s:
                inner = s[s.index("(") + 1:s.rindex(")")].strip()
                if inner:
                    return inner
            return s.strip() or "Household"
    except Exception:
        pass
    return "Household"


def _resolve_net_worth(results: Optional[dict], overrides: Optional[dict]) -> Optional[float]:
    # Prefer a computed snapshot from the last run.
    try:
        snap = (results or {}).get("config_snapshot") or {}
        if "TOTAL_NET_WORTH" in snap:
            return _num(snap["TOTAL_NET_WORTH"])
    except Exception:
        pass
    try:
        ov = overrides or {}
        total = sum(_num(ov.get(k, 0)) for k in _NET_WORTH_KEYS)
        home_equity = _num(ov.get("HOME_VALUE", 0)) - _num(ov.get("MORTGAGE_BALANCE", 0))
        return total + home_equity
    except Exception:
        return None


def _resolve_income(overrides: Optional[dict]) -> Optional[float]:
    ov = overrides or {}
    try:
        if _compute_total_income is not None:
            return _num(_compute_total_income(ov))
    except Exception:
        pass
    try:
        return sum(_num(ov.get(k, 0)) for k in _INCOME_KEYS)
    except Exception:
        return None


def _resolve_target_age(overrides: Optional[dict]) -> int:
    try:
        return int((overrides or {}).get("TARGET_RETIREMENT_AGE", 55))
    except Exception:
        return 55


def _resolve_success(results: Optional[dict]):
    """Return (value_str, hint_str). hint is a subtle 'run to see' when absent."""
    try:
        if results:
            pr = results.get("primary_result") or {}
            rate = pr.get("success_rate")
            if rate is not None:
                return f"{float(rate) * 100:.0f}%", ""
    except Exception:
        pass
    return "—", "run to see"


def _metric_html(label: str, value: str, hint: str = "", short: str = "") -> str:
    """``short``: a phone-only label (theme.css swaps it in under 640px) for a long one."""
    parts = []
    parts.append('<div class="mc-topbar-metric">')
    if short:
        parts.append('<span class="mc-topbar-metric-label"><span class="mc-lbl-full">' + label
                     + '</span><span class="mc-lbl-short">' + short + '</span></span>')
    else:
        parts.append('<span class="mc-topbar-metric-label">' + label + '</span>')
    if hint:
        parts.append(
            '<span class="mc-topbar-metric-value">' + value
            + ' <span class="mc-topbar-metric-hint">' + hint + '</span></span>'
        )
    else:
        parts.append('<span class="mc-topbar-metric-value">' + value + '</span>')
    parts.append('</div>')
    return "".join(parts)


def render(st, results: Optional[dict] = None,
           overrides: Optional[dict] = None,
           profile: Optional[str] = None,
           run_render=None,
           sims_render=None,
           settings_render=None,
           view_render=None,
           in_card: bool = False,
           control_slots=None,
           title: str = "Retirement Monte Carlo",
           stats: Optional[list] = None) -> None:
    """Render the sticky top bar.

    Layout is a keyed ``st.container`` (the sticky element — it lives in the
    tall main block so it has room to pin) holding one row of columns: the
    metrics (title + Name(s)/Net worth/Income/Target retirement age/Success) on the left,
    then the Run-simulation button, the simulation-count selector, and a
    Settings popover on the right. ``run_render``/``sims_render``/
    ``settings_render`` are callbacks invoked inside their columns so the caller
    owns the widgets (and keeps each component's own error handling).
    ``view_render`` (optional) draws the Retirement plan | Spending switch as
    the card's first row. ``in_card=True`` means the caller already opened the
    keyed card container (so the switch could be drawn before the autorun);
    only the metrics/controls row is rendered then. ``control_slots`` (three
    placeholders, from the card's toolbar row) puts the controls there and the
    metrics on their own full-width row.
    """
    names = _resolve_names(profile)

    net_worth = _resolve_net_worth(results, overrides)
    net_worth_str = money(net_worth, shorten=True) if net_worth is not None else "—"

    income = _resolve_income(overrides)
    income_str = money(income, shorten=True) if income is not None else "—"

    target_age = _resolve_target_age(overrides)
    success_str, success_hint = _resolve_success(results)

    html_parts = []
    html_parts.append('<div class="mc-topbar mc-topbar-stats">' if stats is not None
                      else '<div class="mc-topbar">')
    html_parts.append(f'<span class="mc-topbar-title">{escape(title)}</span>')
    html_parts.append(_metric_html("Name(s)", names))
    if stats is not None:       # Spending view: figures from the statements instead
        html_parts.extend(_metric_html(st_[0], st_[1], short=st_[2] if len(st_) > 2 else "")
                          for st_ in stats)
    else:
        html_parts.append(_metric_html("Net worth", net_worth_str))
        html_parts.append(_metric_html("Gross income", income_str))
        # Label matches the sidebar slider and the hero card ("Target retirement
        # age") — the same value was previously called three different things on
        # screen at once.
        html_parts.append(_metric_html("Target retirement age", str(target_age), short="Target age"))
        html_parts.append(_metric_html("Success rate", success_str, success_hint))
    html_parts.append('</div>')

    from contextlib import nullcontext
    with (nullcontext() if in_card else st.container(key="mc-topbar")):
        if view_render is not None:
            view_render(st)
        # Control columns must be wide enough for their contents: at the previous
        # [0.65, 0.13, 0.11, 0.11] the sims selectbox collapsed to ~0.1px (its
        # value was in the DOM but invisible) and the Run button clipped to
        # "Run sim". The metrics column absorbs the difference — it wraps
        # gracefully, the controls don't.
        if control_slots is not None:
            run_col, sims_col, settings_col = control_slots
            st.markdown("".join(html_parts), unsafe_allow_html=True)
        else:
            metrics_col, run_col, sims_col, settings_col = st.columns(
                [0.50, 0.18, 0.15, 0.17], vertical_alignment="center")
            with metrics_col:
                st.markdown("".join(html_parts), unsafe_allow_html=True)
        with run_col:
            if run_render is not None:
                run_render(st)
        with sims_col:
            if sims_render is not None:
                sims_render(st)
        with settings_col:
            try:
                pop = st.popover("Settings", icon=":material/settings:",
                                 use_container_width=True)
            except TypeError:  # pragma: no cover - older Streamlit without icon=
                pop = st.popover("⚙ Settings", use_container_width=True)
            with pop:
                if settings_render is not None:
                    settings_render(st)
