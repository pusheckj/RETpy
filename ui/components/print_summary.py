"""One-page printable summary — a self-contained, downloadable HTML report.

No PDF/template library exists in this repo (no kaleido, reportlab,
weasyprint, pdfkit, or jinja2) and pulling one in just for a single static
export is disproportionate -- kaleido alone bundles a full Chromium. Instead
this ships a self-contained HTML file (embedding the fan chart via
``fig.to_html(include_plotlyjs="cdn")``, zero new dependencies) that a browser
can open directly or print to PDF (Cmd/Ctrl+P -> Save as PDF).

Always renders LIGHT-themed regardless of the live app's dark/light setting
(a print report should look the same on paper either way), via a duck-typed
stub passed to the existing ``style_fig`` instead of a hand-rolled theming
path.
"""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go

try:
    from utils.formatting import pct
    from utils.household import plan_end_ages, plan_end_text
    from utils.plot_theme import style_fig
    from components import bridge_years_gauge, first_decade_stress
except ImportError:  # pragma: no cover
    from ui.utils.formatting import pct  # type: ignore
    from ui.utils.household import plan_end_ages, plan_end_text  # type: ignore
    from ui.utils.plot_theme import style_fig  # type: ignore
    from ui.components import bridge_years_gauge, first_decade_stress  # type: ignore

_TEAL = "#0d9488"
_INK = "#0f172a"
_MUTED = "#64748b"


class _LightStub:
    """Duck-typed 'st' for forcing light theme + palette defaults through the
    existing style_fig -- avoids a second, hand-rolled theming path just for
    this one export."""
    session_state = {}


def _build_fan_chart_html(results: dict) -> str:
    rows = (results.get("primary_result", {}) or {}).get("networth_by_year", []) or []
    fig = go.Figure()
    if rows:
        ages = [int(r["age"]) for r in rows]
        p50 = [float(r["p50"]) for r in rows]
        p10 = [float(r["p10"]) for r in rows]
        p90 = [float(r["p90"]) for r in rows]
        fig.add_trace(go.Scatter(
            x=ages, y=p90, mode="lines", line=dict(width=0), showlegend=False,
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=ages, y=p10, mode="lines", line=dict(width=0), fill="tonexty",
            fillcolor="rgba(13,148,136,0.15)", name="10th-90th percentile",
            hovertemplate="Age %{x}<br>$%{y:,.0f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=ages, y=p50, mode="lines", line=dict(color=_TEAL, width=2.5),
            name="Median", hovertemplate="Age %{x}<br>median $%{y:,.0f}<extra></extra>",
        ))
    fig.update_layout(
        title=dict(text="Projected investable net worth (today's dollars)",
                    x=0.0, xanchor="left", font=dict(size=15, color=_INK)),
        height=340, margin=dict(l=50, r=30, t=50, b=40),
        xaxis=dict(title="Age", gridcolor="#e5e7eb", zeroline=False),
        yaxis=dict(title="$", gridcolor="#e5e7eb", zeroline=False, rangemode="tozero",
                    tickformat="$,.3~s"),
        showlegend=True, plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
    )
    fig = style_fig(fig, _LightStub())
    return fig.to_html(include_plotlyjs="cdn", full_html=False)


def _assumptions_html(overrides: dict) -> str:
    rows = [
        ("Your age", overrides.get("YOUR_AGE", "—")),
        ("Target retirement age", overrides.get("TARGET_RETIREMENT_AGE", "—")),
        ("Plan runs until", plan_end_text(overrides)),
        ("Return scenario", overrides.get("ACTIVE_RETURN_SCENARIO", "—")),
        ("State", overrides.get("STATE_CHOICE", "—")),
        ("Filing status", overrides.get("FILING_STATUS", "—")),
    ]
    items = "".join(f"<li><b>{label}:</b> {value}</li>" for label, value in rows)
    return f"<ul style='margin:0; padding-left:18px;'>{items}</ul>"


def _narrative_html(results: dict, overrides: dict) -> str:
    """Reuses decision_narrative's underlying data sources so the report's
    prose can't disagree with the live dashboard's."""
    retire_age = int(overrides.get("TARGET_RETIREMENT_AGE", 55) or 55)
    plan_until = plan_end_ages(overrides)[0]  # when the plan ends (cfg.plan_end_age)
    parts = []

    verdict = bridge_years_gauge.compute_verdict(results, retire_age)
    if verdict is not None:
        if verdict["funded"]:
            parts.append("Your penalty-free savings look big enough to reach age 59½.")
        else:
            parts.append(f"Your penalty-free savings look short starting around age {verdict['first_short']}.")

    unlucky = first_decade_stress.compute_unlucky_summary(results, retire_age, plan_until)
    if unlucky is not None and unlucky["depletion_age"] is not None:
        parts.append(f"In an unlucky run of markets, the portfolio could run out by age {unlucky['depletion_age']}.")

    if not parts:
        return ""
    items = "".join(f"<li>{p}</li>" for p in parts)
    return f"<h3 style='color:{_INK};font-size:15px;margin:20px 0 8px;'>Biggest risks</h3><ul style='margin:0; padding-left:18px;'>{items}</ul>"


_PRINT_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Retirement plan summary, {today}</title>
<style>
  body {{ font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          color: {ink}; max-width: 820px; margin: 32px auto; padding: 0 24px; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  .muted {{ color: {muted}; font-size: 13px; }}
  .headline {{ font-size: 48px; font-weight: 700; color: {teal}; margin: 8px 0; }}
  .card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 20px; margin: 16px 0; }}
  @media print {{ body {{ margin: 0; padding: 0 12px; }} }}
</style>
</head>
<body>
  <h1>Retirement plan summary</h1>
  <div class="muted">Generated {today}. Today's dollars unless noted.</div>

  <div class="card">
    <div class="muted">Earliest retirement age that meets your success target</div>
    <div class="headline">{earliest}</div>
    <div class="muted">At target age {target_age}: {success_str} chance of success</div>
  </div>

  <div class="card">
    <h3 style="margin-top:0;">Assumptions</h3>
    {assumptions}
  </div>

  <div class="card">{fan_chart}</div>

  {narrative}

  <div class="muted" style="margin-top:24px;">
    Made with Retirement planner. This is not financial advice.
  </div>
</body></html>
"""


def render(st) -> None:
    with st.expander("Print summary", expanded=False, icon=":material/print:"):
        results = st.session_state.get("results")
        if not results:
            st.caption("Run a simulation first.")
            return
        try:
            overrides = st.session_state.get("user_overrides", {}) or {}
            primary = results.get("primary_result", {}) or {}
            earliest = results.get("earliest_retirement_age")
            html_blob = _PRINT_TEMPLATE.format(
                today=date.today().isoformat(),
                ink=_INK, muted=_MUTED, teal=_TEAL,
                earliest="Not achieved" if earliest is None else str(earliest),
                target_age=primary.get("retirement_age", "—"),
                success_str=pct(primary.get("success_rate")),
                assumptions=_assumptions_html(overrides),
                fan_chart=_build_fan_chart_html(results),
                narrative=_narrative_html(results, overrides),
            )
            st.download_button(
                label="⬇ Download printable summary (HTML)",
                data=html_blob,
                file_name=f"retirement_summary_{date.today().isoformat()}.html",
                mime="text/html",
                width="stretch",
                key="print_summary_download_btn",
            )
            st.caption("Opens in any browser. For a PDF, print it (Cmd/Ctrl+P) and choose Save as PDF.")
        except Exception as exc:
            st.error(f"Couldn't prepare the summary: {exc}")
