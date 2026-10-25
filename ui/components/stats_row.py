"""KPI stats row — 4 compact cards below the hero."""
from __future__ import annotations

from utils.formatting import money, pct, success_tier


def _stat_card(label: str, value: str, sublabel: str = "", color: str = "#0f172a", cls: str = "", two_line: bool = False) -> str:
    return f'''
    <div class="mc-stat-card" style="
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 20px;
        height: 100%;
    ">
        <div class="mc-stat-label{' mc-l2' if two_line else ''}" style="font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px;">
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

    # Plan horizon from the run's config snapshot: PLAN_END_AGE is the age the
    # simulation actually ran to (cfg.plan_end_age -- the later of your and your
    # partner's plan-until ages), the one horizon every screen shows.
    snap = results.get("config_snapshot", {}) or {}
    plan_until = int(snap.get("PLAN_END_AGE") or snap.get("PLAN_UNTIL_AGE", 95))
    years_in_ret = max(0, plan_until - retire_age)
    num_sims = snap.get("NUM_SIMULATIONS", 1000)
    partner_age = int(snap.get("PARTNER_AGE") or 0)
    horizon = f"until you're {plan_until}"
    if partner_age > 0 and snap.get("YOUR_AGE") is not None:
        horizon += f", partner {plan_until - (int(snap['YOUR_AGE']) - partner_age)}"

    # Colors. Semantic (risk) values carry a utility class (mc-good/warn/bad) so
    # dark mode recolors them to a bright, still-meaningful variant; the inline
    # color is the light-mode value. Neutral values omit the class and let the
    # dark theme's generic recolor lighten them.
    # A word + glyph accompanies each color so the risk level is legible without
    # color vision (color alone was the only signal).
    target = float(snap.get("TARGET_SUCCESS_RATE", 0.80))
    tier = success_tier(success, target)
    if tier == "good":
        success_cls, success_color, success_tag = "mc-good", "#059669", "✓ On track"
    elif tier == "warn":
        success_cls, success_color, success_tag = "mc-warn", "#d97706", "Borderline"
    else:
        success_cls, success_color, success_tag = "mc-bad", "#dc2626", "✕ At risk"
    # "Thin cushion": the bad-luck (10th percentile) ending portfolio covers
    # under two years of retirement spending (or is zero when no run survives
    # long enough to log spending).
    spend_rows = pr.get("spending_by_year", []) or []
    start_spend = next((r.get("p50") for r in spend_rows if r.get("age") == retire_age), None)
    if p10 <= 0 or (start_spend and p10 < 2 * start_spend):
        p10_cls, p10_color, p10_tag = "mc-warn", "#d97706", "Thin cushion"
    else:
        p10_cls, p10_color, p10_tag = "", "#0f172a", ""

    # On a phone the cards go two per row; a label that wraps in one card must
    # not push its neighbour's value out of line, so a pair shares its label height.
    labels = ["Median final portfolio", "10th percentile", "Success rate", "Years in retirement"]
    l2 = [any(len(labels[j]) > 15 for j in (i - i % 2, i - i % 2 + 1)) for i in range(4)]

    cols = st.columns(4)
    with cols[0]:
        st.markdown(
            _stat_card(
                "Median final portfolio",
                money(median_final, shorten=True),
                f"at plan end (age {plan_until})",
            two_line=l2[0],
            ),
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            _stat_card(
                "10th percentile",
                money(p10, shorten=True),
                (f"1 in 10 runs end lower · {p10_tag}" if p10_tag
                 else "1 in 10 runs end lower"),
                color=p10_color,
                cls=p10_cls,
            two_line=l2[1],
            ),
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(
            _stat_card(
                "Success rate",
                pct(success),
                f"{success_tag} · {num_sims:,} simulations",
                color=success_color,
                cls=success_cls,
            two_line=l2[2],
            ),
            unsafe_allow_html=True,
        )
    with cols[3]:
        st.markdown(
            _stat_card(
                "Years in retirement",
                f"{years_in_ret}",
                horizon,
            two_line=l2[3],
            ),
            unsafe_allow_html=True,
        )

    st.markdown('<div style="margin-bottom: 24px;"></div>', unsafe_allow_html=True)
