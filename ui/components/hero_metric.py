"""Hero metric — earliest retirement age card.

Below the hero number, a band explains the success rate (Needs attention /
Fair / Good / Strong), says it as a count of simulated markets, and turns the
engine's spending guardrail into a dollar cushion (``_band_html``).
"""
from __future__ import annotations

from html import escape

from utils.formatting import money, pct, success_tier


def render(st, results: dict) -> None:
    if not results:
        return

    earliest = results.get("earliest_retirement_age")
    primary = results.get("primary_result", {}) or {}
    target_age = primary.get("retirement_age", "—")
    success_rate = primary.get("success_rate", 0.0)
    config_snapshot = results.get("config_snapshot", {}) or {}
    target_success_rate = config_snapshot.get("TARGET_SUCCESS_RATE", 0.80)

    # Semantic accents carry utility classes (mc-teal / mc-good) so dark mode
    # recolors them to bright variants; the inline color is the light-mode value.
    # The success rate uses the SAME threshold ladder as stats_row.py — it was
    # unconditionally success-green here, so a 25%-success plan showed a
    # confident green "25.0%" directly above stats_row's red "✕ At risk 25.0%".
    tier = success_tier(success_rate, target_success_rate)
    if tier == "good":
        green, green_cls = "#059669", "mc-good"
    elif tier == "warn":
        green, green_cls = "#d97706", "mc-warn"
    else:
        green, green_cls = "#dc2626", "mc-bad"
    if earliest is None:
        big_num = "Not achieved"
        big_color, big_cls = "#64748b", ""  # muted; dark theme lightens it
        subtitle = "None of the retirement ages checked reach your success target. Try saving more, spending less, or changing the return scenario."
    else:
        big_num = str(earliest)
        big_color, big_cls = "#0d9488", "mc-teal"
        subtitle = f"to reach your {pct(target_success_rate)} success target. At your target age of {target_age}, the chance of success is {pct(success_rate)}."

    st.markdown(
        f'''
        <div class="mc-card mc-hero-card" style="display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; padding: 32px 40px; margin-bottom: 24px;">
            <div class="mc-hero-main">
                <div class="mc-hero-label" style="font-size: 13px; color: #64748b; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 8px;">
                    Earliest retirement age
                </div>
                <div class="{big_cls} mc-hero-big" style="font-size: 72px; font-weight: 700; color: {big_color}; line-height: 1.0;">
                    {big_num}
                </div>
                <div style="font-size: 14px; color: #64748b; margin-top: 10px; max-width: 480px;">
                    {subtitle}
                </div>
            </div>
            <div class="mc-hero-side" style="text-align: right;">
                <div style="font-size: 13px; color: #64748b; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 8px;">
                    Target retirement age
                </div>
                <div style="font-size: 40px; font-weight: 600; color: #0f172a;">
                    {target_age}
                </div>
                <div style="font-size: 14px; color: #64748b; margin-top: 4px;">
                    Success rate: <span class="{green_cls}" style="color: {green}; font-weight: 600;">{pct(success_rate)}</span>
                </div>
            </div>
            {_band_html(st, results)}
        </div>
        ''',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Success band, simulated-market count and guardrail cushion
# ---------------------------------------------------------------------------

# (name, low, high) -- the same thresholds as goal_levers.BANDS, low to high.
_ZONES = (("Needs attention", 0.0, 0.65), ("Fair", 0.65, 0.80), ("Good", 0.80, 0.90),
          ("Strong", 0.90, 1.0))


def _zone_help(name: str, lo: float, hi: float) -> str:
    if lo <= 0:
        return f"{name}: below {lo + hi:.0%}"
    if hi >= 1:
        return f"{name}: {lo:.0%} and up"
    return f"{name}: {lo:.0%} to {hi:.0%}"


def _dollars(text: str) -> str:
    """A literal $ in HTML (two of them in one block would start KaTeX math)."""
    return text.replace("$", "&#36;")


def _ends_text(results: dict, overrides: dict) -> str:
    """'until your partner turns 95' / 'until you turn 95': the plan's last year,
    said for whoever is younger then (the same year either way)."""
    try:
        from utils.household import plan_end_ages
    except ImportError:  # pragma: no cover
        from ui.utils.household import plan_end_ages  # type: ignore
    snap = (results.get("config_snapshot") or {})
    try:
        end, partner_end = plan_end_ages(snap if snap.get("YOUR_AGE") is not None else overrides)
    except Exception:
        return "to the end of the plan"
    if partner_end is not None and partner_end < end:
        return f"until your partner turns {partner_end}"
    return f"until you turn {end}"


def _cushion_html(results: dict, overrides: dict, rate_age) -> str:
    """The guardrail cushion line ('' when it can't be worked out)."""
    try:
        from utils.goal_levers import guardrail_cushion, monthly_text
    except ImportError:  # pragma: no cover
        from ui.utils.goal_levers import guardrail_cushion, monthly_text  # type: ignore
    snap = results.get("config_snapshot") or {}
    if snap.get("DYNAMIC_SPENDING_ENABLED") is False:
        return ('<div class="mc-cushion"><b>Spending never adjusts.</b> Your plan keeps '
                'spending the same, even after markets fall.</div>')
    rows = (results.get("primary_result") or {}).get("networth_by_year") or []
    at_ret = next((r for r in rows if r.get("age") == rate_age), None)
    if not at_ret or not overrides or rate_age in (None, "—"):
        return ""
    c = guardrail_cushion(overrides, int(rate_age))
    if not c:
        return ""
    if not c["enabled"]:
        return ('<div class="mc-cushion"><b>Spending never adjusts.</b> Your plan keeps '
                'spending the same, even after markets fall.</div>')
    invested = float(at_ret.get("p50") or 0.0)
    if invested <= 0 or c["trim_year"] <= 0:
        return ""
    fall = round(invested * c["drop"], -4)
    return _dollars(
        f'<div class="mc-cushion"><b>Your cushion:</b> on a typical path you\'d retire with '
        f'about <b>{money(invested, shorten=True)}</b> invested. It could fall about '
        f'<b>{money(fall)}</b> ({c["drop"]:.0%}) below that before your spending rule trims '
        f'fun money by about <b>{monthly_text(c["trim_year"])} a month</b>.</div>')


def _band_html(st, results: dict) -> str:
    """Band meter + one plain sentence + the cushion, as one full-width row of
    the hero card. Text uses theme colors; only the zones are tinted."""
    primary = results.get("primary_result", {}) or {}
    rate = primary.get("success_rate")
    if rate is None:
        return ""
    rate = float(rate)
    state = getattr(st, "session_state", {}) or {}
    overrides = state.get("user_overrides", {}) or {}
    n = int(primary.get("n_simulations") or (results.get("config_snapshot") or {}).get(
        "NUM_SIMULATIONS") or 0)
    current = next(name for name, lo, hi in reversed(_ZONES) if rate >= lo - 1e-9)
    zones = "".join(
        f'<div class="mc-band-zone mc-band-z{i}" style="flex: {round((hi - lo) * 100)}" '
        f'title="{_zone_help(name, lo, hi)}"></div>'
        for i, (name, lo, hi) in enumerate(_ZONES, 1))
    labels = "".join(
        f'<span class="mc-band-label{" mc-band-on" if name == current else ""}'
        f'{" mc-band-alt" if i % 2 else ""}{" mc-band-last" if i == len(_ZONES) - 1 else ""}" '
        f'style="left: {(lo + hi) * 50:.1f}%" title="{_zone_help(name, lo, hi)}">{name}</span>'
        for i, (name, lo, hi) in enumerate(_ZONES))
    spot = min(98.5, max(1.5, rate * 100))
    helps = ". ".join(_zone_help(name, lo, hi) for name, lo, hi in _ZONES)
    count = (f"{round(rate * n):,} of {n:,} simulated markets last {_ends_text(results, overrides)}."
             if n > 0 else f"{pct(rate)} of simulated markets last {_ends_text(results, overrides)}.")
    return (
        f'<div class="mc-hero-band">'
        f'<div class="mc-band" role="img" aria-label="Chance of success {pct(rate)}: {current}. '
        f'{escape(helps)}." title="{escape(helps)}">'
        f'<div class="mc-band-track">{zones}'
        f'<div class="mc-band-marker" style="left: calc({spot:.1f}% - 8px)" title="{pct(rate)}"></div>'
        f'</div><div class="mc-band-labels">{labels}</div></div>'
        f'<div class="mc-band-says"><b>{current}.</b> {count}</div>'
        f'{_cushion_html(results, overrides, primary.get("retirement_age"))}'
        f'</div>')
