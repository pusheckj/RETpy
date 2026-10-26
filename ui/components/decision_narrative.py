"""Decision-narrative auto-summary — a plain-English paragraph synthesizing
what the dashboard already shows: whether the pre-59½ bridge is funded, how
exposed the plan is to a bad early market, and (if computed) the cheapest
lever to close any gap to the success target.

Pure string templating over data ALREADY COMPUTED by bridge_years_gauge and
first_decade_stress (no new modeling here) -- degrades gracefully, clause by
clause, when a piece isn't available (e.g. the break-even sweep hasn't been
run yet this session). Renders nothing if every clause comes back empty.
"""
from __future__ import annotations

try:
    from utils.coerce import safe_int
    from utils.household import plan_end_ages
    from utils.formatting import pct
    from components import bridge_years_gauge, first_decade_stress
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int  # type: ignore
    from ui.utils.household import plan_end_ages  # type: ignore
    from ui.utils.formatting import pct  # type: ignore
    from ui.components import bridge_years_gauge, first_decade_stress  # type: ignore


def render(st, results: dict = None) -> None:
    if not results:
        return

    overrides = st.session_state.get("user_overrides", {}) or {}
    retire_age = safe_int(overrides.get("TARGET_RETIREMENT_AGE", 55), 55)
    plan_until = plan_end_ages(overrides)[0]  # when the plan ends (cfg.plan_end_age)

    parts = []

    verdict = bridge_years_gauge.compute_verdict(results, retire_age)
    if verdict is not None:
        if verdict["funded"]:
            parts.append(
                "Your penalty-free savings (cash, taxable brokerage, Roth) should "
                "**cover the bridge to 59½** without an early-withdrawal penalty."
            )
        else:
            parts.append(
                f"Your penalty-free savings run **short starting around age "
                f"{verdict['first_short']}**. Before 59½, that means a penalized "
                f"withdrawal."
            )

    unlucky = first_decade_stress.compute_unlucky_summary(results, retire_age, plan_until)
    if unlucky is not None:
        if unlucky["depletion_age"] is not None:
            parts.append(
                f"Your biggest risk is a **bad early market**: in an unlucky "
                f"(10th-percentile) sequence, the portfolio is exhausted by age "
                f"**{unlucky['depletion_age']}**."
            )
        elif unlucky["med_10"] is not None and unlucky["p10_10"] is not None and unlucky["med_10"] > 0:
            gap10 = (unlucky["med_10"] - unlucky["p10_10"]) / unlucky["med_10"]
            parts.append(
                f"Your biggest risk is a **bad early market**: in an unlucky "
                f"(10th-percentile) sequence, you'd still be about "
                f"**{pct(gap10)} below your median plan** a decade into "
                f"retirement, though the plan survives."
            )

    # Genuinely optional -- unlike the two above, this sweep is behind a button
    # in the Sensitivity tab and may never have been run this session.
    be = st.session_state.get("break_even_result")
    if be and be.get("break_even_value") is not None:
        parts.append(
            f"The lever that moves your plan most: **{be['label']}** of "
            f"**{be['break_even_value']:,.0f}** would reach your "
            f"{pct(be.get('target_success_rate', 0.0))} target."
        )

    if not parts:
        return
    st.markdown('<div class="mc-section">What this means</div>', unsafe_allow_html=True)
    st.markdown(" ".join(parts))
