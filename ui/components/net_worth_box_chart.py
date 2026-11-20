"""Investable-net-worth box plot over time — the distribution of projected
investable balance across all Monte Carlo runs, per age.

EXCLUDES home equity: the underlying rows are portfolio balance paths, the same
rows first_decade_stress.py reads. The top bar and portfolio_breakdown's
"Net worth" card DO include home equity, so this chart must not reuse that
label or the two disagree on screen with no explanation.

Reads ``results['primary_result']['networth_by_year']`` = per-age percentiles
(p10/p25/p50/p75/p90) of total portfolio balance, aligned on the full horizon
(a depleted path counts as $0 in later years). Shows how the outcome fans out
as market returns compound over decades.

Three views: Range + milestones (default), Box plot, and Point cloud (violin). Range + milestones: a
median line with 25-75% and 10-90% bands, and markers for the years the plan
changes, taken from the user's own inputs (``milestones``). Marker labels never
overlap: ``stagger`` gives each one the first row where it fits, and the plot keeps
headroom above the data for those rows.
"""
from __future__ import annotations

import math

import plotly.graph_objects as go

try:
    from retirement_sim import config as cfg
    from retirement_sim import debts as debts_mod
except ImportError:  # pragma: no cover
    cfg = None  # type: ignore
    debts_mod = None  # type: ignore

try:
    from utils.coerce import safe_int, as_fraction
    from utils.household import plan_end_ages
    from utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark, beeswarm_xy
    from utils.household import has_partner
except ImportError:  # pragma: no cover
    from ui.utils.household import has_partner  # type: ignore
    from ui.utils.coerce import safe_int, as_fraction  # type: ignore
    from ui.utils.household import plan_end_ages  # type: ignore
    from ui.utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark, beeswarm_xy  # type: ignore


STYLES = ["Box plot", "Point cloud (violin)", "Range + milestones"]

# Range + milestones: one text size for every marker label (the size the app's other
# chart annotations use, e.g. the success target line), rows of that height.
LABEL_SIZE = 11
_ROW_PX = 17
_CHAR_PX = 6.4          # average width of one character at LABEL_SIZE
_PLOT_PX = {False: 700, True: 210}   # assumed plot width (regular, phone): narrower is safe
_PLOT_H = 290            # plot-area height: figure height less the margins set below


# Phone labels: the plot is ~200px wide there.
SHORT_LABELS = {
    "You retire": "Retire", "Both retire": "Retire", "Partner retires": "Partner retires",
    "Mortgage paid off": "No mortgage", "Kids in college": "College", "59½: penalty-free": "59½",
    "Your Social Security": "Your SS", "Partner's Social Security": "Partner SS",
    "Social Security (both)": "SS", "RMDs start": "RMDs", "Debts paid off": "Debt-free",
    "Plan ends": "End",
}


def milestones(overrides: dict, current_age: int, plan_until: int) -> list:
    """The years the plan changes, from the user's inputs, in YOUR age.

    Each item is ``{"age", "end", "label", "short", "detail"}``; ``end`` is set only
    for a span (the children's college years). ``short`` is the phone label. Only items after today and up to the plan's
    end are kept, in age order.
    """
    ov = overrides or {}
    out = []

    def add(age, label, detail, end=None):
        if age is not None and current_age < age <= plan_until:
            out.append({"age": float(age), "end": (None if end is None else float(min(end, plan_until))),
                        "label": label, "short": SHORT_LABELS.get(label, label), "detail": detail})

    def cfg_val(key, default):
        v = ov.get(key)
        return (getattr(cfg, key, default) if cfg is not None else default) if v is None else v

    retire = safe_int(cfg_val("TARGET_RETIREMENT_AGE", 55), 55)
    partner = has_partner(ov)
    gap = current_age - safe_int(ov.get("PARTNER_AGE", 0), 0) if partner else 0
    pra = ov.get("PARTNER_RETIREMENT_AGE")
    if not partner:
        add(retire, "You retire", f"You stop work at {retire}. Saving stops and withdrawals begin.")
    elif pra is None or safe_int(pra, 0) + gap == retire:
        add(retire, "Both retire", f"You retire at {retire} and your partner at {retire - gap}. "
                                   "Saving stops and withdrawals begin.")
    else:
        p_age = safe_int(pra, 0)
        add(retire, "You retire", f"You stop work at {retire}.")
        add(p_age + gap, "Partner retires",
            f"Your partner stops work at {p_age} (you are {p_age + gap}).")

    # Mortgage: the same schedule as the Spending chart (extra principal, house moves).
    try:
        try:
            from utils.derived import mortgage_schedule
        except ImportError:  # pragma: no cover
            from ui.utils.derived import mortgage_schedule  # type: ignore
        payoff = mortgage_schedule(ov, range(current_age, plan_until + 1))["payoff_age"]
    except Exception:  # pragma: no cover - defensive
        payoff = None
    add(payoff, "Mortgage paid off", "No more mortgage payments. Housing drops to property tax "
                                     "and insurance.")

    # College: each child's years, merged where they overlap.
    if cfg is not None:
        start_age = safe_int(cfg_val("COLLEGE_START_AGE", 18), 18)
        spans = []
        for c in cfg.children_in(ov):
            years = safe_int(c.get("college_years", cfg.CHILD_DEFAULTS["college_years"]), 4)
            if years <= 0:
                continue
            a = current_age + safe_int(c.get("years_until_birth", 0), 0) + start_age
            spans.append([a, a + years, 1, float(c.get("college_funding_pct") or 0) > 0])
        spans.sort()
        merged = []
        for sp in spans:
            if merged and sp[0] <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], sp[1])
                merged[-1][2] += 1
                merged[-1][3] = merged[-1][3] or sp[3]
            else:
                merged.append(sp)
        for a, b, n, funded in merged:
            who = "One child is" if n == 1 else f"{n} children are"
            pays = (" The plan pays its share of the bill, from the 529s first." if funded
                    else " The plan pays none of the bill (no college funding set).")
            first = max(a, current_age + 1)
            if first < b:
                add(first, "College" if n == 1 else "Kids in college",
                    f"From your age {a} to {b - 1}, {who.lower()} in college.{pays}", end=b)

    add(59.5, "59½: penalty-free", "401(k) and IRA money opens without the 10% early "
                                   "withdrawal penalty.")

    if bool(cfg_val("INCLUDE_SOCIAL_SECURITY", True)):
        claim = safe_int(cfg_val("SS_CLAIM_AGE", 67), 67)
        p_claim = (safe_int(ov.get("PARTNER_SS_CLAIM_AGE") or claim, claim) + gap) if partner else None
        if partner and p_claim == claim:
            add(claim, "Social Security (both)", f"You claim at {claim} and your partner "
                                                 f"at {claim - gap}.")
        else:
            add(claim, "Your Social Security", f"You claim Social Security at {claim}.")
            if partner:
                add(p_claim, "Partner's Social Security",
                    f"Your partner claims at {p_claim - gap} (you are {p_claim}).")

    if cfg is not None:
        rmd = int(cfg.get_rmd_start_age(int(cfg.CURRENT_YEAR) - current_age))
        add(rmd, "RMDs start", f"Required withdrawals from pre-tax accounts begin at {rmd}.")

    debts = ov.get("DEBTS")
    if debts and debts_mod is not None:
        try:
            p = debts_mod.amortize(debts, ov.get("DEBT_EXTRA_MONTHLY", 0), ov.get("DEBT_STRATEGY"))
            if p.paid_off and p.months > 0:
                add(round(current_age + p.months / 12.0, 1), "Debts paid off",
                    f"Your last debt is paid off after {p.months} months. "
                    "That money goes back to saving.")
        except Exception:  # pragma: no cover - defensive
            pass

    add(plan_until, "Plan ends", f"The plan runs until you are {plan_until}.")
    out.sort(key=lambda m: (m["age"], m["label"]))
    return out


def stagger(items: list, lo: float, hi: float, plot_px: float, key: str = "label") -> list:
    """``[(row, anchor)]`` for each milestone so no two labels overlap.

    A label (``item[key]``) starts at its marker and runs right (``anchor``
    "left"), or ends at it when it would run past ``hi`` and fits before it
    ("right"). Its width in ages comes from its length at LABEL_SIZE and the
    assumed plot width. Each label takes the first row whose last label ends
    before it starts.
    """
    span = max(1e-9, hi - lo)
    row_end = []
    out = []
    for m in items:
        w = (len(m[key]) * _CHAR_PX + 12) / plot_px * span
        x = m["age"]
        right = x + w > hi and x - w >= lo
        start, end, anchor = (x - w, x, "right") if right else (x, x + w, "left")
        for r, e in enumerate(row_end):
            if start > e:
                row_end[r] = end
                break
        else:
            r = len(row_end)
            row_end.append(end)
        out.append((r, anchor))
    return out


def axis_top(p75, p90) -> tuple:
    """(top of the data the axis must show, whether the 90th percentile runs past it).
    A few lucky paths can put the 90th percentile far above the rest, which flattens
    the median into the floor; past 1.6x the 75th percentile's peak the axis stops."""
    peak75 = max([v for v in p75 if v] or [1.0])
    peak90 = max([v for v in p90 if v] or [1.0])
    limit = 1.6 * peak75
    return (min(peak90, limit), peak90 > limit)


def _milestone_figure(ages, p10, p25, p50, p75, p90, items, *, dark: bool, compact: bool,
                      mode_label: str, unit: str) -> go.Figure:
    """Median line, 25-75% and 10-90% bands, and the milestone markers."""
    line = "#14b8a6" if dark else "#0f766e"
    band_outer = "rgba(20,184,166,0.20)" if dark else "rgba(13,148,136,0.13)"
    band_inner = "rgba(20,184,166,0.30)" if dark else "rgba(13,148,136,0.24)"
    text = "#e2e8f0" if dark else "#0f172a"
    mark = "rgba(148,163,184,0.75)" if dark else "rgba(71,85,105,0.55)"
    chip = "rgba(55,52,63,0.92)" if dark else "rgba(255,255,255,0.92)"
    college = "rgba(242,154,107,0.12)" if dark else "rgba(196,104,58,0.09)"

    lo, hi = min(ages) - 1, max(ages) + 1
    key = "short" if compact else "label"
    layout = stagger(items, lo, hi, _PLOT_PX[compact], key)
    rows = 1 + max([r for r, _ in layout] or [-1])
    head = (rows * _ROW_PX + 6) / _PLOT_H          # share of the plot the label rows take
    top = 1.05 * axis_top(p75, p90)[0] / max(0.2, 1.0 - head)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ages + ages[::-1], y=p90 + p10[::-1], fill="toself",
                             fillcolor=band_outer, line=dict(width=0), hoverinfo="skip",
                             name="Middle 80% of paths"))
    fig.add_trace(go.Scatter(x=ages + ages[::-1], y=p75 + p25[::-1], fill="toself",
                             fillcolor=band_inner, line=dict(width=0), hoverinfo="skip",
                             name="Middle 50% of paths"))
    fig.add_trace(go.Scatter(
        x=ages, y=p50, mode="lines", line=dict(color=line, width=2.2), name="Median",
        customdata=list(zip(p10, p25, p75, p90)),
        hovertemplate=("Age %{x}<br>90th $%{customdata[3]:,.0f}<br>75th $%{customdata[2]:,.0f}<br>"
                       "median $%{y:,.0f}<br>25th $%{customdata[1]:,.0f}<br>"
                       "10th $%{customdata[0]:,.0f}<extra></extra>"),
    ))

    def median_at(a: float) -> float:
        if a <= ages[0]:
            return p50[0]
        for i in range(1, len(ages)):
            if a <= ages[i]:
                t = (a - ages[i - 1]) / (ages[i] - ages[i - 1])
                return p50[i - 1] + t * (p50[i] - p50[i - 1])
        return p50[-1]

    def age_text(a: float) -> str:
        return "59½" if abs(a - 59.5) < 1e-9 else f"{a:g}"

    for m, (r, anchor) in zip(items, layout):
        y_label = 1 - (4 + r * _ROW_PX) / _PLOT_H
        tip = f"Age {age_text(m['age'])}: {m['label']}. {m['detail']}"
        if m["end"] is not None:
            fig.add_shape(type="rect", xref="x", yref="paper", x0=m["age"], x1=m["end"],
                          y0=0, y1=1, fillcolor=college, line=dict(width=0), layer="below")
        fig.add_shape(type="line", xref="x", yref="paper", x0=m["age"], x1=m["age"],
                      y0=0, y1=y_label, line=dict(color=mark, width=1, dash="dot"))
        fig.add_annotation(
            x=m["age"], xref="x", y=y_label, yref="paper", yanchor="top",
            xanchor=anchor, xshift=(3 if anchor == "left" else -3), showarrow=False,
            text=m[key], font=dict(size=LABEL_SIZE, color=text), bgcolor=chip,
            borderpad=1, hovertext=tip)
    if items:
        fig.add_trace(go.Scatter(
            x=[m["age"] for m in items], y=[median_at(m["age"]) for m in items], mode="markers",
            marker=dict(size=7, color=text, line=dict(color=line, width=1.5)),
            customdata=[f"Age {age_text(m['age'])}: <b>{m['label']}</b><br>{m['detail']}"
                        for m in items],
            hovertemplate="%{customdata}<extra></extra>", name="Milestones", showlegend=False))

    fig.update_layout(
        title=dict(
            text="<b>Investable portfolio range over time</b><br>"
                 f"<span style='font-size:13px;color:#64748b;'>Median and the middle 50% and "
                 f"80% of simulated paths · {mode_label}</span>",
            x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
        ),
        height=_PLOT_H + 80 + 50, margin=dict(l=50, r=40, t=80, b=50),
        xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False,
                   tickfont=dict(color="#64748b"), fixedrange=False, range=[lo, hi]),
        yaxis=dict(title=f"Investable portfolio ({unit})", gridcolor="#f1f5f9", zeroline=False,
                   tickformat="$,.3~s", tickfont=dict(color="#64748b"), range=[0, top]),
        showlegend=True, dragmode="pan", hovermode="closest", uirevision="keep",
    )
    return fig


def render(st, results: dict = None, chart_key: str = "net_worth_box_main") -> None:
    if not results:
        return
    rows = (results.get("primary_result", {}) or {}).get("networth_by_year", []) or []
    if not rows:
        return

    overrides = st.session_state.get("user_overrides", {}) or {}
    current_age = safe_int(overrides.get("YOUR_AGE", 25), 25)
    retirement_age = safe_int(overrides.get("TARGET_RETIREMENT_AGE", 55), 55)
    plan_until = plan_end_ages(overrides)[0]  # when the plan ends (cfg.plan_end_age)
    inflation_rate = as_fraction(overrides.get("EXPECTED_INFLATION", 0.0275), 0.0275)

    def _body() -> None:
        c1, c2 = st.columns(2)
        with c1:
            mode = st.radio(
                "Dollars", options=["Today's $", "Future $"],
                horizontal=True, key=f"{chart_key}_dollars", label_visibility="collapsed",
            )
        with c2:
            style = st.radio(
                "Style", options=STYLES, index=STYLES.index("Range + milestones"),
                horizontal=True, key=f"{chart_key}_style", label_visibility="collapsed",
            )
        future = str(mode).startswith("Future")
        points_mode = "Point cloud" in str(style)
        milestone_mode = str(style) == STYLES[2]

        def infl(a: int) -> float:
            return (1.0 + inflation_rate) ** (a - current_age) if future else 1.0

        ages = [int(r["age"]) for r in rows]
        p10 = [float(r["p10"]) * infl(int(r["age"])) for r in rows]
        p25 = [float(r["p25"]) * infl(int(r["age"])) for r in rows]
        p50 = [float(r["p50"]) * infl(int(r["age"])) for r in rows]
        p75 = [float(r["p75"]) * infl(int(r["age"])) for r in rows]
        p90 = [float(r["p90"]) * infl(int(r["age"])) for r in rows]

        dark = is_dark(st)
        if milestone_mode:
            mode_label = "future (nominal) dollars" if future else "today's dollars"
            unit = "$, nominal" if future else "$, today"
            items = milestones(overrides, current_age, plan_until)
            show_chart(st, lambda compact: _milestone_figure(
                ages, p10, p25, p50, p75, p90, items, dark=dark, compact=compact,
                mode_label=mode_label, unit=unit),
                f"{chart_key}_{'nom' if future else 'tod'}_ms_{'dk' if dark else 'lt'}",
                PLOTLY_CONFIG)
            clipped = axis_top(p75, p90)[1]
            st.caption(
                "The line is the median across simulated market paths. The darker band holds "
                "the middle 50% of paths and the lighter band the middle 80%. The markers come "
                "from your own inputs. Hover one to see what changes that year. Like the other "
                "views, this leaves out home equity and counts runs that run out as $0."
                + (" The axis stops early so the median stays readable. The top of the light "
                   "band runs past it." if clipped else "")
            )
            return
        box_color = "#14b8a6" if dark else "#0d9488"
        fill = "rgba(20,184,166,0.35)" if dark else "rgba(13,148,136,0.30)"
        ref_line = "#e2e8f0" if dark else "#0f172a"

        fig = go.Figure()
        if points_mode:
            allx, ally = [], []
            for r in rows:
                a = int(r["age"]); f = infl(a)
                xs, ys = beeswarm_xy([float(s) * f for s in r.get("samples", [])], a)
                allx += xs; ally += ys
            fig.add_trace(go.Scatter(
                x=allx, y=ally, mode="markers",
                marker=dict(size=3, color=box_color, opacity=0.45),
                hoverinfo="skip", showlegend=False, name="paths",
            ))
            fig.add_trace(go.Scatter(
                x=ages, y=p50, mode="lines", line=dict(color=ref_line, width=2),
                name="median", hovertemplate="Age %{x}<br>median $%{y:,.0f}<extra></extra>",
            ))
        else:
            fig.add_trace(go.Box(
                x=ages, q1=p25, median=p50, q3=p75, lowerfence=p10, upperfence=p90,
                name="Investable portfolio", boxpoints=False,
                marker_color=box_color, line=dict(color=box_color, width=1.2),
                fillcolor=fill,
                customdata=list(zip(p10, p25, p50, p75, p90)),
                hovertemplate=(
                    "Age %{x}<br>90th $%{customdata[4]:,.0f}<br>75th $%{customdata[3]:,.0f}<br>"
                    "median $%{customdata[2]:,.0f}<br>25th $%{customdata[1]:,.0f}<br>"
                    "10th $%{customdata[0]:,.0f}<extra></extra>"
                ),
            ))
        if current_age <= retirement_age <= plan_until:
            fig.add_vline(
                x=retirement_age, line_dash="dash", line_color="#94a3b8",
                annotation_text=f"Retirement (age {retirement_age})",
                annotation_position="top left", annotation_font=dict(size=10, color="#64748b"),
            )

        mode_label = "future (nominal) dollars" if future else "today's dollars"
        unit = "$, nominal" if future else "$, today"
        # In point-cloud mode a few lucky paths can be orders of magnitude above
        # p90 (e.g. historical returns compounding to $1B+), which would flatten
        # the whole cloud. Clip the axis to the same p90-based range the box plot
        # uses so the violin body stays readable (extreme outliers are suppressed).
        y_cap = 1.15 * max([v for v in p90 if v] or [1.0]) if points_mode else None
        fig.update_layout(
            title=dict(
                text="<b>Investable portfolio range over time</b><br>"
                     f"<span style='font-size:13px;color:#64748b;'>Projected investable "
                     f"balance across simulated runs · {mode_label}</span>",
                x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
            ),
            height=420, margin=dict(l=50, r=40, t=80, b=50),
            # Clamp to the data: on narrow charts Plotly autoranged the box
            # axis down to age 0 (a big empty left third on a phone).
            xaxis=dict(title="Age", gridcolor="#f1f5f9", zeroline=False,
                       tickfont=dict(color="#64748b"), fixedrange=False,
                       range=[min(ages) - 1, max(ages) + 1]),
            yaxis=dict(title=f"Investable portfolio ({unit})", gridcolor="#f1f5f9", zeroline=False,
                       rangemode="tozero", tickformat="$,.3~s", tickfont=dict(color="#64748b"),
                       range=([0, y_cap] if points_mode else None)),
            showlegend=False, dragmode="pan", boxgap=0.2,
            transition=(dict(duration=0) if points_mode
                        else dict(duration=350, easing="cubic-in-out")),
            uirevision="keep",
        )
        show_chart(st, fig, f"{chart_key}_{'nom' if future else 'tod'}_{'pts' if points_mode else 'box'}_{'dk' if dark else 'lt'}", PLOTLY_CONFIG)
        st.caption(
            "Each box shows the spread of **investable net worth across all simulated market "
            "paths** at that age. It leaves out home equity, unlike the \"Net worth\" figures "
            "elsewhere. The box covers the middle 50% (25th to 75th percentile), the whiskers "
            "reach the 10th and 90th, and the line is the median. The range widens over time as "
            "returns compound. Runs that run out of money count as $0, which pulls the lower "
            "percentiles toward zero in later years."
        )

    _body()
