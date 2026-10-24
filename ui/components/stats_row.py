"""KPI stats row — 4 compact cards below the hero."""
from __future__ import annotations

from utils.formatting import money, pct


def _stat_card(label: str, value: str, sublabel: str = "", color: str = "#0f172a", cls: str = "") -> str:
    return f'''
    <div class="mc-stat-card" style="
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 20px;
        height: 100%;
    ">
        <div style="font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px;">
            {label}
        </div>
        <div class="{cls}" style="font-size: 28px; font-weight: 600; color: {color}; line-height: 1.2;">
            {value}
        </div>
        <div style="font-size: 12px; color: #94a3b8; margin-top: 6px;">
            {sublabel}
        </div>
    </div>
    '''


def render(st, results: dict) -> None:
    if not results:
        return
    pr = results.get("primary_result", {}) or {}
    median_final = pr.get("median_final", 0.0)
    p10 = pr.get("p10_final", 0.0)
    success = pr.get("success_rate", 0.0)
    retire_age = pr.get("retirement_age", 0)

    # Derive plan horizon from config snapshot
    snap = results.get("config_snapshot", {}) or {}
    plan_until = snap.get("PLAN_END_AGE") or snap.get("PLAN_UNTIL_AGE", 95)
    years_in_ret = max(0, plan_until - retire_age)
    num_sims = snap.get("NUM_SIMULATIONS", 1000)

    # Colors. Semantic (risk) values carry a utility class (mc-good/warn/bad) so
    # dark mode recolors them to a bright, still-meaningful variant; the inline
    # color is the light-mode value. Neutral values omit the class and let the
    # dark theme's generic recolor lighten them.
    # A word + glyph accompanies each color so the risk level is legible without
    # color vision (color alone was the only signal).
    if success >= 0.8:
        success_cls, success_color, success_tag = "mc-good", "#059669", "✓ On track"
    elif success >= 0.6:
        success_cls, success_color, success_tag = "mc-warn", "#d97706", "! Borderline"
    else:
        success_cls, success_color, success_tag = "mc-bad", "#dc2626", "✕ At risk"
    if p10 < 1_000_000:
        p10_cls, p10_color, p10_tag = "mc-warn", "#d97706", "! Thin cushion"
    else:
        p10_cls, p10_color, p10_tag = "", "#0f172a", ""

    cols = st.columns(4)
    with cols[0]:
        st.markdown(
            _stat_card(
                "Median final portfolio",
                money(median_final, shorten=True),
                "at plan end age",
            ),
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            _stat_card(
                "10th percentile",
                money(p10, shorten=True),
                f"worst-case outcome · {p10_tag}" if p10_tag else "worst-case outcome",
                color=p10_color,
                cls=p10_cls,
            ),
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(
            _stat_card(
                "Success rate",
                pct(success),
                f"{success_tag} · out of {num_sims:,} simulations",
                color=success_color,
                cls=success_cls,
            ),
            unsafe_allow_html=True,
        )
    with cols[3]:
        st.markdown(
            _stat_card(
                "Years in retirement",
                f"{years_in_ret}",
                f"through age {plan_until}",
            ),
            unsafe_allow_html=True,
        )

    st.markdown('<div style="margin-bottom: 24px;"></div>', unsafe_allow_html=True)
