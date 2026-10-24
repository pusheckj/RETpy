"""Individual Monte Carlo trajectories tab."""
from __future__ import annotations

import plotly.graph_objects as go

from utils.formatting import money

try:
    from utils.plot_theme import style_fig, show_chart
except ImportError:  # pragma: no cover
    from ui.utils.plot_theme import style_fig, show_chart  # type: ignore


# (label, primary_result key): final-balance percentiles over ALL runs, the
# same figures as the stat tiles above ("Median final portfolio" is the 50th,
# "10th percentile" the 10th).
FINAL_PERCENTILES = [("10th", "p10_final"), ("25th", "p25_final"), ("50th (median)", "median_final"),
                     ("75th", "p75_final"), ("90th", "p90_final")]


def sample_outcomes(pr: dict) -> list:
    """(path, ran_out) for each sample path. A path that ran out stops
    recording the year before, so its last balance is not $0: use the run's own
    success flag (older stored results without one fall back to the balance)."""
    paths = pr.get("sample_paths", []) or []
    flags = pr.get("sample_successes")
    out = []
    for i, path in enumerate(paths):
        if flags is not None and i < len(flags):
            ran_out = not bool(flags[i])
        else:
            ran_out = not path or path[-1][1] <= 100
        out.append((path, ran_out))
    return out


def render(st, results: dict, chart_key: str = "trajectories_tab_main") -> None:
    if not results:
        return
    pr = results.get("primary_result", {}) or {}
    outcomes = [(p, bad) for p, bad in sample_outcomes(pr) if p]
    if not outcomes:
        st.info("No sample paths available.")
        return

    n_runs = int(pr.get("n_simulations")
                 or (results.get("config_snapshot", {}) or {}).get("NUM_SIMULATIONS") or 0)
    n_shown = len(outcomes)
    n_out = sum(1 for _, bad in outcomes if bad)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Sample paths shown",
                  f"{n_shown} of {n_runs:,}" if n_runs >= n_shown else f"{n_shown}")
    with col2:
        st.metric("Ran out of money (in this sample)", f"{n_out} of {n_shown}")

    fig = go.Figure()
    for path, ran_out in outcomes:
        ages, values = (list(v) for v in zip(*path))
        if ran_out:
            # Show where the money ran out: down to $0 the following year.
            ages.append(ages[-1] + 1)
            values.append(0.0)
        color = "rgba(220, 38, 38, 0.45)" if ran_out else "rgba(5, 150, 105, 0.35)"
        fig.add_trace(go.Scatter(
            x=ages,
            y=values,
            mode="lines",
            line=dict(color=color, width=1),
            hoverinfo="skip",
            showlegend=False,
        ))

    fig.update_layout(
        title=dict(
            text="<b>Individual simulation paths</b><br><span style='font-size:13px;color:#94a3b8;'>Green = portfolio survives, red = runs out</span>",
            x=0.0, xanchor="left", font=dict(size=16),
        ),
        height=440,
        margin=dict(l=50, r=30, t=80, b=50),
        xaxis=dict(title="Age", zeroline=False,
                   range=[min(p[0][0] for p, _ in outcomes), max(p[-1][0] for p, _ in outcomes)]),
        yaxis=dict(title="Portfolio value", zeroline=False, tickformat="$,.3~s"),
        hovermode="closest",
    )
    show_chart(st, fig, chart_key, {"displayModeBar": False})

    # Distribution table: every run, not the sample above (a handful of paths
    # gave a median far from the tile's).
    rows = [(label, pr[key]) for label, key in FINAL_PERCENTILES if pr.get(key) is not None]
    if rows:
        import pandas as pd
        st.markdown(f"**Final balance at plan end** (all {n_runs:,} simulations)"
                    if n_runs else "**Final balance at plan end** (all simulations)")
        df = pd.DataFrame({
            "Percentile": [label for label, _ in rows],
            "Final balance": [money(float(v), shorten=True) for _, v in rows],
        })
        st.dataframe(df, width="stretch", hide_index=True)
        st.caption("The lines above are a small sample to show how runs differ; the table "
                   "and the summary tiles use every simulation. Runs that ran out end at about $0.")
