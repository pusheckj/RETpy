"""One-click stress-test presets — named disaster buttons.

Each preset is a small bundle of EXISTING config overrides (no new engine
primitives) merged onto the current inputs, re-run at a reduced simulation
count (mirroring sensitivity_tab.py's pattern), and compared against a fresh
baseline run at the SAME reduced count so the before/after delta isn't
confounded by simulation-count noise. Preview only -- never touches
``user_overrides``/the main ``results``. ``run_full_analysis`` is memoized, so
repeat clicks on the same preset are cheap.
"""
from __future__ import annotations

try:
    from utils.coerce import safe_int
    from utils.formatting import money, pct
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int  # type: ignore
    from ui.utils.formatting import money, pct  # type: ignore

_N_SIMULATIONS = 500

# (label, overrides delta merged onto current inputs, age offset applied to
# the retirement-age PARAMETER -- TARGET_RETIREMENT_AGE is UI-only and would
# be silently dropped if put in the overrides dict instead).
#
# "High inflation" (EXPECTED_INFLATION bump) was tried and DROPPED: in this
# all-real-dollar engine, EXPECTED_INFLATION mainly drives nominal
# contribution-limit growth (401k/HSA/IRA), which is a windfall here, not a
# stress -- it moved the default profile's success rate UP (+5.4pp), the
# opposite of what a "disaster button" should show. "Extended lifespan"
# is an unambiguous stress with no such confound.
PRESETS = [
    ("Prolonged bad returns", {"ACTIVE_RETURN_SCENARIO": "pessimistic"}, 0),
    ("Forced early retirement (-6 yrs)", {}, -6),
    ("Major medical event", {"LTC_ENABLED": True, "LTC_PROBABILITY": 0.60,
                              "LTC_ANNUAL_COST": 180_000}, 0),
    ("Extended lifespan (to 110)", {"PLAN_UNTIL_AGE": 110}, 0),
]


def render(st, results: dict = None) -> None:
    if not results:
        st.caption("Run the main simulation first.")
        return

    from utils.sim_runner import run_full_analysis

    base_overrides = dict(st.session_state.get("user_overrides", {}) or {})
    your_age = safe_int(base_overrides.get("YOUR_AGE", 25), 25)
    target_age = safe_int(base_overrides.get("TARGET_RETIREMENT_AGE", 55), 55)

    st.caption(
        "Each button runs a lighter simulation twice, with and without the "
        "shock, using the same number of runs so simulation noise doesn't "
        "skew the before and after. This is a preview only. Your plan and "
        "inputs don't change."
    )

    store = st.session_state.setdefault("stress_preset_results", {})

    for label, delta, age_offset in PRESETS:
        clicked = st.button(label, key=f"stress_preset_{label}", width="stretch")
        if clicked:
            age = max(target_age + age_offset, your_age)
            baseline = run_full_analysis(
                base_overrides, n_simulations=_N_SIMULATIONS, target_retirement_age=target_age,
            )
            shocked = run_full_analysis(
                {**base_overrides, **delta}, n_simulations=_N_SIMULATIONS, target_retirement_age=age,
            )
            store[label] = {"baseline": baseline, "shocked": shocked, "age": age}

        entry = store.get(label)
        if not entry:
            continue

        base_pr = entry["baseline"].get("primary_result", {}) or {}
        shock_pr = entry["shocked"].get("primary_result", {}) or {}
        base_earliest = entry["baseline"].get("earliest_retirement_age")
        shock_earliest = entry["shocked"].get("earliest_retirement_age")

        cols = st.columns(3)
        with cols[0]:
            st.metric(
                "Earliest retirement age",
                "Not achieved" if shock_earliest is None else str(shock_earliest),
                delta=None if (base_earliest is None or shock_earliest is None)
                else shock_earliest - base_earliest,
                delta_color="inverse",
            )
        with cols[1]:
            base_sr = base_pr.get("success_rate")
            shock_sr = shock_pr.get("success_rate")
            st.metric(
                f"Success at {entry['age']}",
                pct(shock_sr) if shock_sr is not None else "—",
                delta=None if (base_sr is None or shock_sr is None)
                else f"{(shock_sr - base_sr) * 100:+.1f} points",
            )
        with cols[2]:
            base_med = base_pr.get("median_final")
            shock_med = shock_pr.get("median_final")
            st.metric(
                "Median ending balance",
                money(shock_med, shorten=True),
                delta=None if (base_med is None or shock_med is None)
                else money(shock_med - base_med, shorten=True),
            )
