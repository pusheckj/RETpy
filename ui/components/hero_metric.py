"""Hero metric — earliest retirement age card."""
from __future__ import annotations

from utils.formatting import pct


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
    if (success_rate or 0.0) >= 0.8:
        green, green_cls = "#059669", "mc-good"
    elif (success_rate or 0.0) >= 0.6:
        green, green_cls = "#d97706", "mc-warn"
    else:
        green, green_cls = "#dc2626", "mc-bad"
    if earliest is None:
        big_num = "Not achieved"
        big_color, big_cls = "#64748b", ""  # muted; dark theme lightens it
        subtitle = "Portfolio cannot support retirement within the scanned age range. Try raising savings, lowering target age, or adjusting return scenario."
    else:
        big_num = str(earliest)
        big_color, big_cls = "#0d9488", "mc-teal"
        subtitle = f"with {pct(target_success_rate)} success probability. Selected target: age {target_age} ({pct(success_rate)})."

    st.markdown(
        f'''
        <div class="mc-card" style="display: flex; align-items: center; justify-content: space-between; padding: 32px 40px; margin-bottom: 24px;">
            <div>
                <div class="mc-hero-label" style="font-size: 13px; color: #64748b; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 8px;">
                    Earliest retirement age
                </div>
                <div class="{big_cls}" style="font-size: 72px; font-weight: 700; color: {big_color}; line-height: 1.0;">
                    {big_num}
                </div>
                <div style="font-size: 14px; color: #64748b; margin-top: 10px; max-width: 480px;">
                    {subtitle}
                </div>
            </div>
            <div style="text-align: right;">
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
        </div>
        ''',
        unsafe_allow_html=True,
    )
