"""Individual Monte Carlo trajectories tab."""
from __future__ import annotations

import plotly.graph_objects as go
import numpy as np

from utils.formatting import money

try:
    from utils.plot_theme import style_fig
except ImportError:  # pragma: no cover
    from ui.utils.plot_theme import style_fig  # type: ignore


def render(st, results: dict, chart_key: str = "trajectories_tab_main") -> None:
    if not results:
        return
    pr = results.get("primary_result", {}) or {}
    paths = pr.get("sample_paths", []) or []
    if not paths:
        st.info("No sample paths available.")
        return

    # Compute per-path outcome
    outcomes = []
    for path in paths:
        if not path:
            outcomes.append(("unknown", 0.0))
            continue
        final_balance = path[-1][1] if path else 0
        outcomes.append(("success" if final_balance > 100 else "failure", final_balance))

    n_success = sum(1 for o, _ in outcomes if o == "success")
    n_total = len(paths)
    success_rate = n_success / n_total if n_total else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Sample paths shown", f"{n_total}")
    with col2:
        st.metric("Successful", f"{n_success} ({success_rate*100:.0f}%)")
    with col3:
        final_balances = [b for _, b in outcomes if b > 0]
        median_final = float(np.median(final_balances)) if final_balances else 0.0
        st.metric("Median final (this sample)", money(median_final, shorten=True))

    fig = go.Figure()
    for path, (outcome, _) in zip(paths, outcomes):
        if not path:
            continue
        ages, values = zip(*path)
        color = "rgba(5, 150, 105, 0.35)" if outcome == "success" else "rgba(220, 38, 38, 0.45)"
        fig.add_trace(go.Scatter(
            x=list(ages),
            y=list(values),
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
        xaxis=dict(title="Age", zeroline=False),
        yaxis=dict(title="Portfolio value", zeroline=False, tickformat="$,.3~s"),
        hovermode="closest",
    )
    fig = style_fig(fig, st)
    st.plotly_chart(fig, width="stretch", key=chart_key, config={"displayModeBar": False})

    # Distribution table
    st.markdown("**Final balance distribution** (among sample paths)")
    final_balances = [b for _, b in outcomes]
    if final_balances:
        pcts = [10, 25, 50, 75, 90]
        values = [float(np.percentile(final_balances, p)) for p in pcts]
        import pandas as pd
        df = pd.DataFrame({
            "Percentile": [f"{p}th" for p in pcts],
            "Final balance": [money(v, shorten=True) for v in values],
        })
        st.dataframe(df, width="stretch", hide_index=True)
