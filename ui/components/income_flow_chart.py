"""Where this year's pay goes: a Sankey of one working year, drawn in the Income tile
when its plot type is "Where this year's pay goes" (components/income_over_time.py).

Pay (you, your partner, any Social Security) flows into taxes, pre-tax savings and
take-home pay. Taxes split into federal, state and FICA, pre-tax savings into the
401(k)s and HSA, and take-home into spending, Roth IRAs, after-tax 401(k), 529s and
brokerage (what's left). Spending splits into the expense categories.

Every number is the engine's, from ``utils.sim_runner.working_year_flows`` (the
deterministic ``working_year_cashflow`` plus the engine's own spending for that
year). Today's dollars. Employer money (match, HSA deposit) is extra pay that never
passes through a paycheck, so it is a note under the chart, not a stream. When
spending and saving need more than take-home, the gap is a "Shortfall from savings"
stream into spending (the engine draws it from the portfolio).

On a phone the chart is the short version: pay -> taxes, saving, spending.
"""
from __future__ import annotations

import plotly.graph_objects as go

try:
    from utils.coerce import safe_int
    from utils.milestones import short_money
    from utils.plot_theme import PLOTLY_CONFIG, is_dark, show_chart, _font_family
    from utils.slider_input import slider_with_box
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int  # type: ignore
    from ui.utils.milestones import short_money  # type: ignore
    from ui.utils.plot_theme import PLOTLY_CONFIG, is_dark, show_chart, _font_family  # type: ignore
    from ui.utils.slider_input import slider_with_box  # type: ignore

# Colors by meaning, not by series: pay, taxes, saving, spending. One set per theme,
# each at least 3:1 against its tile (non-text graphics). Labels use the theme's
# text color, never these.
KIND_COLORS = {
    False: {"pay": "#64748b", "tax": "#9a7b4f", "save": "#0d9488", "spend": "#c4683a"},
    True: {"pay": "#a3b1c6", "tax": "#d9bd8c", "save": "#2dd4bf", "spend": "#f29a6b"},
}
_TEXT = {False: "#0f172a", True: "#e2e8f0"}
_LINK_ALPHA = {False: 0.30, True: 0.38}
_MIN = 0.5      # dollars: smaller streams are left out

# Full chart layout: four columns (pay, then taxes / pre-tax / take-home, then where
# each goes, then the spending categories). The last column sits at the right edge
# with its labels to the left of the nodes, so the third column is pulled left to
# leave those labels room. Rows run top to bottom in the order listed.
_COLUMNS = (
    (0.001, ("you", "partner", "ss")),
    (0.25, ("taxes", "pretax", "take", "short")),
    (0.50, ("fed", "state", "fica", "k401", "hsa", "spend", "roth", "at401k", "p529",
            "brk", "left")),
)
_CAT_X = 0.999
_HEIGHT = {False: 500, True: 360}
_MARGIN = dict(l=8, r=30, t=80, b=16)   # r: the tile crops ~22px on the right, as for every chart
_PAD = {False: 12, True: 10}
# Short names for the spending column (the full name is in the hover).
_SHORT = {"Food & groceries": "Food", "Fun and discretionary": "Fun",
          "Transportation": "Transport", "Healthcare premiums": "Health",
          "Partner spending": "Partner's own", "Property tax + insurance": "Tax + insurance",
          "College (after 529s)": "College", "Debt payments": "Debts"}


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _pct(value: float, gross: float) -> str:
    return f"{value / gross:.0%}" if gross > 0 else "0%"


def flow_graph(flows: dict, compact: bool = False):
    """``(nodes, links)`` for ``flows`` (``sim_runner.working_year_flows``).

    ``nodes`` is a list of ``(key, name, kind)``; ``links`` a list of
    ``(source_key, target_key, value)``. Streams under a dollar are left out, and
    so is any node they leave empty. ``compact`` is the phone version: each source
    straight to Taxes, Saving and Spending.
    """
    f = flows
    single = not f.get("has_partner") or f.get("partner", 0) <= _MIN
    you_pre = f["your_401k"] + f["your_hsa"]
    you_take = f["you"] - f["you_tax"] - you_pre   # your pay that reaches take-home
    ss = f.get("social_security", 0.0)
    nodes = [
        ("you", "Your pay" if single else "You", "pay"),
        ("partner", "Partner", "pay"),
        ("ss", "Social Security benefits", "pay"),
        ("short", "Shortfall from savings", "save"),
    ]
    if compact:
        # One household "Pay" source: splitting saving and spending by earner would be a guess.
        nodes = [("pay", "Pay", "pay"), ("short", "Shortfall from savings", "save"),
                 ("taxes", "Taxes", "tax"), ("saving", "Saving", "save"),
                 ("spend", "Spending", "spend"), ("left", "Left over", "pay")]
        saved = (you_pre + f["partner_401k"] + f["roth"] + f["after_tax_401k"]
                 + f["plan_529"] + f["brokerage"])
        links = [("pay", "taxes", f["you_tax"] + f["partner_tax"]), ("pay", "saving", saved),
                 ("pay", "spend", f["spending_total"] - f["shortfall"]),
                 ("pay", "left", f["left_over"]), ("short", "spend", f["shortfall"])]
    else:
        many = not single
        nodes += [
            ("taxes", "Taxes", "tax"), ("pretax", "Pre-tax savings", "save"),
            ("take", "Take-home pay", "pay"),
            ("fed", "Federal", "tax"), ("state", f.get("state_label", "State"), "tax"),
            ("fica", "Social Security + Medicare", "tax"),
            ("k401", "401(k)s" if many and f["partner_401k"] > _MIN and f["your_401k"] > _MIN
             else "401(k)", "save"),
            ("hsa", "HSA", "save"),
            ("spend", "Spending", "spend"),
            ("roth", "Roth IRAs" if many else "Roth IRA", "save"),
            ("at401k", "After-tax 401(k)", "save"),
            ("p529", "529 plans", "save"),
            ("brk", "Brokerage (what's left)" if f.get("auto", True) else "Brokerage", "save"),
            ("left", "Left over (not invested)", "pay"),
        ]
        cats = sorted(f["spending"].items(), key=lambda kv: -kv[1])
        nodes += [(f"c{i}", name, "spend") for i, (name, _) in enumerate(cats)]
        links = [
            ("you", "taxes", f["you_tax"]), ("you", "pretax", you_pre), ("you", "take", you_take),
            ("partner", "taxes", f["partner_tax"]), ("partner", "pretax", f["partner_401k"]),
            ("partner", "take", f["partner_take_home"]),
            ("ss", "take", ss),
            ("taxes", "fed", f["federal"]), ("taxes", "state", f["state"]),
            ("taxes", "fica", f["fica"]),
            ("pretax", "k401", f["your_401k"] + f["partner_401k"]),
            ("pretax", "hsa", f["your_hsa"]),
            ("take", "spend", f["spending_total"] - f["shortfall"]),
            ("short", "spend", f["shortfall"]),
            ("take", "roth", f["roth"]), ("take", "at401k", f["after_tax_401k"]),
            ("take", "p529", f["plan_529"]), ("take", "brk", f["brokerage"]),
            ("take", "left", f["left_over"]),
        ]
        links += [("spend", f"c{i}", v) for i, (_, v) in enumerate(cats)]
    links = [(a, b, float(v)) for a, b, v in links if v > _MIN]
    used = {a for a, _, _ in links} | {b for _, b, _ in links}
    return [n for n in nodes if n[0] in used], links


def node_positions(nodes, value: dict, compact: bool = False):
    """``(x, y)`` lists (0-1, node centres) that pin the full chart's columns and row
    order. Heights follow Plotly's own scale (the tightest column fills the plot
    height less its gaps), so the stacked nodes never overlap. ``None`` for the
    phone chart, which Plotly lays out itself."""
    if compact:
        return None
    keys = [k for k, _, _ in nodes]
    cols = [(x, [k for k in order if k in keys]) for x, order in _COLUMNS]
    cols.append((_CAT_X, [k for k in keys if k.startswith("c") and k[1:].isdigit()]))
    cols = [(x, ks) for x, ks in cols if ks]
    height = _HEIGHT[compact] - _MARGIN["t"] - _MARGIN["b"]
    pad = _PAD[compact]
    scale = min((height - pad * (len(ks) - 1)) / max(1.0, sum(value[k] for k in ks))
                for _, ks in cols)
    pos = {}
    for x, ks in cols:
        total = sum(value[k] for k in ks) * scale + pad * (len(ks) - 1)
        top = (height - total) / 2
        if x == _CAT_X and "spend" in pos:   # centre the categories on Spending
            top = min(max(0.0, pos["spend"][1] * height - total / 2), height - total)
        for k in ks:
            h = value[k] * scale
            pos[k] = (x, (top + h / 2) / height)
            top += h + pad
    return [pos[k][0] for k in keys], [pos[k][1] for k in keys]


def build_figure(flows: dict, *, dark: bool = False, compact: bool = False,
                 font_family: str | None = None) -> go.Figure:
    """The themed Sankey for ``flows``. Labels carry the amount; hover adds the share
    of gross pay."""
    nodes, links = flow_graph(flows, compact)
    gross_pay = flows["gross"]
    colors = KIND_COLORS[dark]
    index = {key: i for i, (key, _, _) in enumerate(nodes)}
    inflow = {key: 0.0 for key, _, _ in nodes}
    outflow = dict(inflow)
    for a, b, v in links:
        outflow[a] += v
        inflow[b] += v
    value = {key: max(inflow[key], outflow[key]) for key in inflow}
    names = {key: name for key, name, _ in nodes}
    kinds = {key: kind for key, _, kind in nodes}
    text = _TEXT[dark]
    xy = node_positions(nodes, value, compact)
    shown = {key: (_SHORT.get(name, name) if key.startswith("c") else name)
             for key, name, _ in nodes}
    fig = go.Figure(go.Sankey(
        arrangement="fixed" if xy else "snap",
        valueformat="$,.0f",
        node=dict(
            label=[f"{shown[key]}  {short_money(value[key])}" for key, _, _ in nodes],
            **({"x": xy[0], "y": xy[1]} if xy else {}),
            color=[colors[kind] for _, _, kind in nodes],
            pad=_PAD[compact], thickness=12 if compact else 14,
            line=dict(width=0),
            align="left",
            customdata=[[name, _pct(value[key], gross_pay)] for key, name, _ in nodes],
            hovertemplate="%{customdata[0]}<br>$%{value:,.0f} · %{customdata[1]} of gross pay"
                          "<extra></extra>",
        ),
        link=dict(
            source=[index[a] for a, _, _ in links],
            target=[index[b] for _, b, _ in links],
            value=[v for _, _, v in links],
            color=[_rgba(colors[kinds[b]], _LINK_ALPHA[dark]) for _, b, _ in links],
            customdata=[[names[a], names[b], _pct(v, gross_pay)] for a, b, v in links],
            hovertemplate="%{customdata[0]} → %{customdata[1]}<br>$%{value:,.0f} · "
                          "%{customdata[2]} of gross pay<extra></extra>",
        ),
        textfont=dict(color=text, size=12, **({"family": font_family} if font_family else {}),
                      shadow="none"),
    ))
    fig.update_layout(
        title=dict(
            text=("<b>Where this year's pay goes</b><br>"
                  f"<span style='font-size:13px;color:#64748b;'>Age {flows['age']} · "
                  "today's dollars · hover a stream for its share of pay</span>"),
            x=0.0, xanchor="left", font=dict(size=16, color="#0f172a"),
        ),
        height=_HEIGHT[compact],
        margin=dict(_MARGIN),
        showlegend=False,
    )
    return fig


def caption(flows: dict) -> str:
    """One line under the chart: how much of gross pay is saved, plus employer money."""
    saved = (flows["your_401k"] + flows["partner_401k"] + flows["your_hsa"] + flows["roth"]
             + flows["after_tax_401k"] + flows["brokerage"])
    gross = flows["gross"]
    line = f"You save **{saved / gross:.0%}** of gross pay this year." if gross > 0 else ""
    if flows.get("plan_529", 0) > _MIN:
        line += f" Another {short_money(flows['plan_529'])} goes to the children's 529 plans."
    employer = flows.get("employer") or {}
    if employer:
        names = list(employer)
        parts = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        line += (f" Your employers add {short_money(sum(employer.values()))} more "
                 f"({parts}), on top of pay.")
    if flows.get("shortfall", 0) > _MIN:
        line += (f" Spending needs {short_money(flows['shortfall'])} more than take-home, "
                 "so the plan draws it from savings.")
    if flows.get("left_over", 0) > _MIN:
        line += (f" {short_money(flows['left_over'])} is left over. In Manual savings mode "
                 "the plan doesn't invest it.")
    return line.strip()


def render_body(st, overrides: dict, chart_key: str) -> None:
    """Age picker, the chart and its caption (inside the Income tile's fragment)."""
    try:
        from utils.sim_runner import working_year_flows
    except ImportError:  # pragma: no cover
        from ui.utils.sim_runner import working_year_flows  # type: ignore
    current_age = safe_int(overrides.get("YOUR_AGE", 25), 25)
    retirement_age = safe_int(overrides.get("TARGET_RETIREMENT_AGE", 55), 55)
    last = retirement_age - 1
    if last < current_age:
        st.info("You are retired in this plan, so there is no working year to show. "
                "Pick a later retirement age to see where your pay goes.")
        return
    age = slider_with_box(st, "Working year (your age)", current_age, last, 1,
                          key=f"{chart_key}_flow_age", value=current_age)
    age = max(current_age, min(last, safe_int(age, current_age)))
    flows = working_year_flows(overrides, age, retirement_age)
    if flows["coasting"]:
        st.info(f"At {age} you are coasting (Coast FIRE): your pay covers spending "
                "and the plan saves nothing that year.")
        return
    if flows["gross"] <= _MIN:
        st.info("There is no pay in this year. Enter your income to see where it goes.")
        return
    dark = is_dark(st)
    fam = _font_family(st)
    show_chart(st, lambda compact: build_figure(flows, dark=dark, compact=compact, font_family=fam),
               f"{chart_key}_flow_{'dk' if dark else 'lt'}", PLOTLY_CONFIG)
    st.caption(caption(flows))

