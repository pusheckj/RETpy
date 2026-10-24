"""Withdrawal drawdown plot — withdrawal % of portfolio over time, colored by source."""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.plot_theme import style_fig, concept_color, PLOTLY_CONFIG
except ImportError:  # pragma: no cover
    from ui.utils.plot_theme import style_fig, concept_color, PLOTLY_CONFIG


def render(st, results: dict, chart_key: str = "withdrawal_drawdown_main") -> None:
    if not results:
        return
    pr = results.get("primary_result", {}) or {}
    rows = pr.get("withdrawals_by_year", []) or []
    if not rows:
        st.info("Per-year withdrawal breakdown not available.")
        return

    ages = [r["age"] for r in rows]

    # Split the traditional bucket into DISCRETIONARY vs IRS-FORCED (RMD) draws.
    # The engine reports `traditional == traditional_chosen + rmd_spent`, so
    # stacking the two parts keeps the total identical to the old single bar.
    # Backward compatible: results produced before the engine exposed these
    # fields have no `traditional_chosen`, so fall back to the combined value
    # (chosen = traditional, rmd = 0) rather than silently under-counting.
    def _trad_split(r):
        if "traditional_chosen" in r:
            return float(r.get("traditional_chosen", 0.0)), float(r.get("rmd_spent", 0.0))
        return float(r.get("traditional", 0.0)), 0.0

    for r in rows:
        chosen, rmd = _trad_split(r)
        r["_trad_chosen"] = chosen
        r["_trad_rmd"] = rmd

    has_rmd = any(r["_trad_rmd"] > 0 for r in rows)

    # Stacked bars: withdrawal % from each source, pastel palette.
    sources = [
        ("Cash", "cash"),
        ("Taxable brokerage", "taxable"),
        ("Traditional 401(k)/IRA", "_trad_chosen"),
    ]
    if has_rmd:
        # Only surface the forced band when RMDs actually occur — with a Roth
        # conversion strategy running, traditional balances are often drained
        # before the RMD age and this is legitimately empty.
        sources.append(("RMD (IRS-forced)", "_trad_rmd"))
    sources += [
        ("Roth", "roth"),
        ("HSA", "hsa"),
    ]
    colors = {label: concept_color(label, st) for label, _ in sources}
    # The forced band is a CONSTRAINT, not a portfolio choice — give it a fixed
    # amber rather than a categorical palette color so it reads as "imposed".
    _RMD_LABEL = "RMD (IRS-forced)"
    if _RMD_LABEL in colors:
        colors[_RMD_LABEL] = "#d97706"

    fig = go.Figure()
    for label, key in sources:
        dollars = [r.get(key, 0) for r in rows]
        # Guard the % so a near-zero (depleted) portfolio can't paint a spurious
        # ~100% stack: rows flagged `depleted` are floored to a $1 denominator's
        # worth only implicitly — instead we cap the plotted fraction at 100%.
        pcts = []
        for d, r in zip(dollars, rows):
            pv = max(1.0, r.get("portfolio_value", 1))
            pct = 100.0 * d / pv
            if r.get("depleted"):
                pct = min(pct, 100.0)
            pcts.append(pct)
        if label == _RMD_LABEL:
            # For the forced band, hover reports the FULL forced amount and how
            # much of it actually funded spending — the remainder was reinvested
            # into taxable, which is the part users can't otherwise see.
            gross = [float(r.get("rmd_gross", 0.0)) for r in rows]
            reinv = [max(0.0, g - float(r["_trad_rmd"])) for g, r in zip(gross, rows)]
            fig.add_trace(go.Bar(
                x=ages, y=pcts, name=label,
                marker_color=colors[label], marker_line_width=0,
                customdata=list(zip(dollars, gross, reinv)),
                hovertemplate=(
                    "RMD forced: $%{customdata[1]:,.0f}<br>"
                    "&nbsp;&nbsp;spent: $%{customdata[0]:,.0f} (%{y:.1f}% of portfolio)<br>"
                    "&nbsp;&nbsp;reinvested: $%{customdata[2]:,.0f}<extra></extra>"
                ),
            ))
            continue
        # customdata carries the raw $ amount alongside the plotted % so the
        # unified hover can show both without a second trace per source.
        fig.add_trace(go.Bar(
            x=ages, y=pcts, name=label,
            marker_color=colors[label], marker_line_width=0,
            customdata=dollars,
            hovertemplate=f"{label}: $%{{customdata:,.0f}} (%{{y:.1f}}% of portfolio)<extra></extra>",
        ))

    # finding #14 — Roth CONVERSION is a traditional->Roth transfer, not a
    # withdrawal/spend (it is deliberately excluded from `total` upstream in
    # _flush_withdrawal_log), so it is drawn as a separate dashed overlay line
    # rather than added to the stacked withdrawal-source bars, to avoid
    # reading as consumption.
    conversion_dollars = [r.get("roth_conversion", 0) for r in rows]
    if any(conversion_dollars):
        conversion_pcts = [
            100.0 * d / max(1.0, r.get("portfolio_value", 1))
            for d, r in zip(conversion_dollars, rows)
        ]
        fig.add_trace(go.Scatter(
            x=ages, y=conversion_pcts, name="Roth conversion (transfer)",
            mode="lines+markers", line=dict(color="#7c3aed", dash="dot", width=2),
            marker=dict(size=5, symbol="diamond"),
            customdata=conversion_dollars,
            hovertemplate="Roth conversion (transfer): $%{customdata:,.0f} (%{y:.1f}% of portfolio)<extra></extra>",
        ))

    # Add a reference line at 4% withdrawal rate
    fig.add_hline(y=4.0, line_dash="dash", line_color="#94a3b8",
                  annotation_text="4% safe withdrawal rate", annotation_position="top right",
                  annotation_font=dict(size=11))

    fig.update_layout(
        barmode="stack", bargap=0.15,
        title=dict(
            text="<b>Withdrawal rate by source</b><br><span style='font-size:13px;'>Annual withdrawal as % of current portfolio, colored by account type</span>",
            x=0.0, xanchor="left", font=dict(size=16),
        ),
        height=400,
        margin=dict(l=50, r=200, t=80, b=50),
        xaxis=dict(title="Age", zeroline=False, fixedrange=False),
        yaxis=dict(title="Withdrawal rate (%)", zeroline=False, rangemode="tozero"),
        hovermode="x unified", dragmode="pan",
        legend=dict(orientation="v", yanchor="top", y=1.0, xanchor="left", x=1.02, bgcolor="rgba(0,0,0,0)"),
        uirevision="keep",
    )

    fig = style_fig(fig, st)

    st.plotly_chart(fig, width="stretch", key=chart_key, config=PLOTLY_CONFIG)
    st.caption(
        "Each bar shows what fraction of the portfolio is withdrawn from each account "
        "type that year. The rate trends toward 0% in later years because the portfolio "
        "grows faster than spending (and Social Security covers part of the need) — a "
        "sign of an over-funded plan, not a data gap. The dotted purple line (if shown) "
        "is Roth conversions — money moved from Traditional to Roth accounts, not spent."
    )

