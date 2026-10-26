"""Sensitivity analysis tab."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import streamlit as st_mod  # for session_state access

from utils.formatting import pct, money


def render(st, results: dict) -> None:
    st.markdown('<div class="mc-section">Sensitivity analysis</div>', unsafe_allow_html=True)
    st.caption(
        "How your chance of success at your target retirement age changes as inputs move. "
        "Each row is a new simulation."
    )

    if not results:
        st.info("Run the main simulation first.")
        return

    base_overrides = dict(st.session_state.get("user_overrides", {}))
    target_age = int(base_overrides.get("TARGET_RETIREMENT_AGE", 55))

    run_btn = st.button("Run sensitivity analysis", width="stretch")

    if "sensitivity_results" not in st.session_state:
        st.session_state["sensitivity_results"] = None

    if run_btn:
        from utils.sim_runner import run_full_analysis

        scenarios = [
            ("Base case", {}, target_age),
            # NOTE: these scale STARTING BALANCES, not the annual savings rate.
            # They were labeled "Savings ±20%", which reads as "save 20% more
            # each year" — a different (and much slower-acting) lever.
            ("Starting balances +20%", _scale_balances(base_overrides, 1.20), target_age),
            ("Starting balances -20%", _scale_balances(base_overrides, 0.80), target_age),
            ("Annual savings +20%", _scale_contributions(base_overrides, 1.20), target_age),
            ("Annual savings -20%", _scale_contributions(base_overrides, 0.80), target_age),
            ("Conservative returns", {"ACTIVE_RETURN_SCENARIO": "conservative"}, target_age),
            ("Pessimistic returns", {"ACTIVE_RETURN_SCENARIO": "pessimistic"}, target_age),
            ("Retire 5 years later", {}, target_age + 5),
            ("Retire 5 years earlier", {}, max(target_age - 5, 40)),
        ]

        rows = []
        status_placeholder = st.empty()
        status_placeholder.info(f"Running {len(scenarios)} scenarios, about 10 seconds each…")
        progress = st.progress(0.0, text="Getting scenarios ready…")
        with st.spinner("Running sensitivity analysis…"):
            for i, (name, delta, age) in enumerate(scenarios):
                progress.progress(
                    i / len(scenarios),
                    text=f"Running scenario {i+1}/{len(scenarios)}: {name} ({int(100 * i / len(scenarios))}%)",
                )
                merged = {**base_overrides, **delta}
                try:
                    res = run_full_analysis(merged, n_simulations=500, target_retirement_age=age)
                    pr = res.get("primary_result", {}) or {}
                    rows.append({
                        "Scenario": name,
                        "Retire age": age,
                        "Success": pr.get("success_rate", 0.0),
                        "Median final": pr.get("median_final", 0.0),
                        "P10 final": pr.get("p10_final", 0.0),
                    })
                except Exception as e:
                    progress.progress(
                        (i + 1) / len(scenarios),
                        text=f"Scenario {name} failed, continuing…",
                    )
                    rows.append({
                        "Scenario": name, "Retire age": age, "Success": 0.0,
                        "Median final": 0.0, "P10 final": 0.0,
                    })

        st.session_state["sensitivity_results"] = rows
        progress.progress(1.0, text="Done.")
        time.sleep(0.3)
        progress.empty()
        status_placeholder.success(f"Sensitivity analysis complete: {len(rows)} scenarios.")

    rows = st.session_state.get("sensitivity_results")
    if rows:
        df = pd.DataFrame(rows)
        df["Success"] = df["Success"].apply(pct)
        df["Median final"] = df["Median final"].apply(lambda v: money(v, shorten=True))
        df["P10 final"] = df["P10 final"].apply(lambda v: money(v, shorten=True))
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("Click **Run sensitivity analysis** above to see how your plan responds when inputs change.")

    st.divider()
    _render_break_even(st, base_overrides, target_age)


# Parameters offered for the break-even sweep: label -> (config key, grid of
# values to try, in ascending order). Grids are intentionally small (6 points)
# since each point is a fresh Monte Carlo run.
_BREAK_EVEN_PARAMS = {
    "Your 401(k) contribution ($/yr)": (
        "YOUR_401K_CONTRIBUTION",
        [10_000, 15_000, 18_500, 23_000, 27_500, 32_000],
    ),
    "Your HSA contribution ($/yr)": (
        "YOUR_HSA_CONTRIBUTION",
        [1_000, 2_000, 3_000, 4_150, 5_500, 7_000],
    ),
    "Retirement age": (
        "TARGET_RETIREMENT_AGE_SWEEP",  # handled specially below
        [45, 50, 55, 60, 65, 70],
    ),
}


def _render_break_even(st, base_overrides: dict, target_age: int) -> None:
    """Read-only break-even sweep: pick a parameter, find the smallest value
    (at the fixed target retirement age) that reaches TARGET_SUCCESS_RATE.
    """
    from retirement_sim import config as cfg
    from utils.sim_runner import sweep_break_even

    st.markdown("#### Break-even finder")
    st.caption(
        "Try a range of values for one input, with retirement age fixed, to find the "
        "smallest value that reaches your success target."
    )

    # Read the USER's target, not cfg's module default. sim_runner restores cfg
    # after every run, so `getattr(cfg, ...)` here always returned the shipped
    # 0.80 — a user planning to 95% got a break-even value that only cleared
    # 80% (and a green box that said so). Every other consumer (hero_metric,
    # success_by_age) honours the override, so match them.
    target_success_rate = float(
        (base_overrides or {}).get("TARGET_SUCCESS_RATE")
        or getattr(cfg, "TARGET_SUCCESS_RATE", 0.80)
    )
    label = st.selectbox(
        "Parameter to sweep", list(_BREAK_EVEN_PARAMS.keys()), key="break_even_param_label"
    )
    run_sweep_btn = st.button("Find break-even value", width="stretch", key="break_even_run_btn")

    if run_sweep_btn:
        param_name, values = _BREAK_EVEN_PARAMS[label]
        with st.spinner(f"Sweeping {label}…"):
            if param_name == "TARGET_RETIREMENT_AGE_SWEEP":
                # Retirement age is a sweep parameter passed to run_full_analysis
                # directly rather than a cfg override, so sweep it in-line here
                # using the same success-rate lookup, oldest-first (break-even
                # is the *earliest* age that reaches target, so this reads
                # top-down consistent with the other params' ascending scan).
                sweep_result = _sweep_retirement_age(base_overrides, values, target_success_rate)
            else:
                sweep_result = sweep_break_even(
                    base_overrides, param_name, values,
                    target_retirement_age=target_age,
                    target_success_rate=target_success_rate,
                    n_simulations=500,
                )
        st.session_state["break_even_result"] = {"label": label, **sweep_result}

    sweep_state = st.session_state.get("break_even_result")
    if sweep_state:
        be_value = sweep_state.get("break_even_value")
        if be_value is None:
            st.warning(
                f"No value tested for **{sweep_state['label']}** reaches "
                f"{pct(sweep_state['target_success_rate'])} success."
            )
        else:
            st.success(
                f"Break-even **{sweep_state['label']}**: **{be_value:,.0f}** "
                f"reaches {pct(sweep_state['target_success_rate'])} success."
            )
        chart_df = pd.DataFrame({
            sweep_state["label"]: sweep_state["values"],
            "Success rate": [pct(r) for r in sweep_state["success_rates"]],
        })
        st.dataframe(chart_df, width="stretch", hide_index=True)


def _sweep_retirement_age(base_overrides: dict, ages: list, target_success_rate: float) -> dict:
    """Same shape as sweep_break_even, but sweeps the retirement age argument
    itself (rather than a cfg override) via run_full_analysis.
    """
    from utils.sim_runner import run_full_analysis

    success_rates = []
    break_even_value = None
    for age in ages:
        try:
            res = run_full_analysis(base_overrides, n_simulations=500, target_retirement_age=age)
            primary = res.get("primary_result", {}) or {}
            rate = float(primary.get("success_rate", 0.0))
        except Exception:
            rate = 0.0
        success_rates.append(rate)
        if break_even_value is None and rate >= target_success_rate:
            break_even_value = age
    return {
        "values": list(ages),
        "success_rates": success_rates,
        "break_even_value": break_even_value,
        "target_success_rate": target_success_rate,
    }


def _scale_contributions(overrides: dict, factor: float) -> dict:
    """Scale every ANNUAL contribution by the given factor.

    This is the "save more/less each year" lever most people mean by
    "Savings ±20%" (the balance lever above is a different question: "what if I
    already had more saved today?").
    """
    keys = [
        "YOUR_401K_CONTRIBUTION", "YOUR_HSA_CONTRIBUTION", "YOUR_BACKDOOR_ROTH",
        "YOUR_BROKERAGE_CONTRIBUTION",
        "PARTNER_401K_CONTRIBUTION", "PARTNER_ROTH_CONTRIBUTION",
        "PARTNER_BROKERAGE_CONTRIBUTION",
    ]
    out = {}
    for k in keys:
        if k in overrides and overrides[k]:
            out[k] = int(overrides[k] * factor)
    return out


def _scale_balances(overrides: dict, factor: float) -> dict:
    """Scale every CURRENT account balance by the given factor.

    Renamed from ``_scale_savings``: it moves today's starting balances, not the
    annual contribution rate, and the old name/label implied the latter.
    """
    keys = [
        "YOUR_401K", "YOUR_ROTH_IRA", "YOUR_TRADITIONAL_IRA", "YOUR_HSA",
        "YOUR_BROKERAGE", "YOUR_CASH",
        "PARTNER_401K", "PARTNER_ROTH_IRA", "PARTNER_BROKERAGE", "PARTNER_CASH",
    ]
    out = {}
    for k in keys:
        if k in overrides:
            out[k] = int(overrides[k] * factor)
    return out
