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
    from utils.derived import sidebar_savings_budget
    from utils.household import plan_end_ages
    from utils.formatting import pct, money_md
    from components import bridge_years_gauge, first_decade_stress
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int  # type: ignore
    from ui.utils.derived import sidebar_savings_budget  # type: ignore
    from ui.utils.household import plan_end_ages  # type: ignore
    from ui.utils.formatting import pct, money_md  # type: ignore
    from ui.components import bridge_years_gauge, first_decade_stress  # type: ignore


def overspend_gap(state) -> dict | None:
    """How far spending plus tax exceeds income in the working years, as
    ``{"income", "taxes", "expenses", "gap"}`` -- or ``None`` when income covers
    it, when there are no working years left (retired), or when there is no
    income to compare. The engine funds such a year from savings (the plan's
    balance shrinks), so this is often the real cause of a failing plan.
    """
    overrides = state.get("user_overrides", {}) or {}
    if safe_int(overrides.get("YOUR_AGE", 0), 0) >= safe_int(overrides.get("TARGET_RETIREMENT_AGE", 55), 55):
        return None
    try:
        b = sidebar_savings_budget(state)
        income, taxes, expenses = float(b["income"]), float(b["taxes"]["total"]), float(b["expenses"])
    except Exception:  # pragma: no cover - a half-built profile must not break the tile
        return None
    gap = taxes + expenses - income
    if income <= 0 or gap < 1:
        return None
    return {"income": income, "taxes": taxes, "expenses": expenses, "gap": gap}


def render(st, results: dict = None) -> None:
    if not results:
        return

    overrides = st.session_state.get("user_overrides", {}) or {}
    retire_age = safe_int(overrides.get("TARGET_RETIREMENT_AGE", 55), 55)
    primary = results.get("primary_result", {}) or {}
    success = primary.get("success_rate")
    target = float((results.get("config_snapshot", {}) or {}).get("TARGET_SUCCESS_RATE", 0.80))
    meets = success is None or float(success) >= target

    over = overspend_gap(st.session_state)
    if over is not None:
        st.warning(
            f"**Your spending is more than your take-home pay.** You spend "
            f"{money_md(over['expenses'])} a year and pay {money_md(over['taxes'])} in tax, "
            f"against {money_md(over['income'])} of income. That is "
            f"{money_md(over['gap'])} a year more than you earn, so nothing is saved while you "
            f"work and the shortfall comes out of your savings. Spend less or earn more first."
        )
    plan_until = plan_end_ages(overrides)[0]  # when the plan ends (cfg.plan_end_age)

    parts = []

    verdict = bridge_years_gauge.compute_verdict(results, retire_age)
    if verdict is not None:
        if verdict["funded"]:
            extra = (", your 401(k) through the Rule of 55" if verdict.get("uses_rule55") else "")
            extra += (", your 72(t) payments" if verdict.get("uses_sepp") else "")
            parts.append(
                f"On a typical path, your penalty-free savings (cash, taxable brokerage, Roth{extra}) "
                "**cover the bridge to 59½** without an early-withdrawal penalty."
            )
        elif verdict.get("ran_out"):
            parts.append(
                f"On a typical path, your money **runs out around age {verdict['first_short']}**, "
                f"before 59½."
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
                f"retirement" + (", though the plan survives." if meets else ".")
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
