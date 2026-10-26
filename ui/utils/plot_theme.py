"""Theme-aware Plotly styling.

Streamlit's dark-mode CSS (see ui/components/theme_toggle.py) restyles the
DOM, but Plotly figures bake their colors into the figure JSON and are
unaffected by CSS. This module re-styles figures (background, fonts, axes,
hover labels) to match the current app theme so charts remain legible and
consistent in both light and dark mode.
"""
from __future__ import annotations

_FONT_FAMILY = "Inter, -apple-system, BlinkMacSystemFont, sans-serif"

# Shared Plotly config for st.plotly_chart calls: keep the mode bar but drop lasso/select tools.
PLOTLY_CONFIG = {"displayModeBar": True, "displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}

# Named chart palettes — the user picks one in Settings (session key
# "palette_choice"). "Pastel" is the historical default. Each palette carries
# ~10 distinct hues so the widest categorical charts (7 savings buckets, etc.)
# never have to cycle. Only ARBITRARY categorical series follow the palette;
# semantic colors (good/bad, brand teal, median-vs-p10, reference lines) are
# hardcoded in the charts and unaffected.
PALETTES = {
    "Pastel": [
        "#5eb3a6", "#7a8db3", "#e0917f", "#9cb380", "#b2a4d4", "#d9b96b",
        "#8ec3d9", "#cf9bab", "#8fcbb0", "#e3b18a", "#9aa8d8", "#b6a596",
    ],
    "Warm earthy": [
        "#3f8f83", "#c2703d", "#8a9a5b", "#d4a13a", "#a35d4a", "#6b8e9e",
        "#b08968", "#7d6b8a", "#c98b6b", "#5c7a6b", "#9c7b4f", "#8a6d5e",
    ],
    "Cool professional": [
        "#0d9488", "#2563eb", "#0891b2", "#475569", "#7c3aed", "#0ea5e9",
        "#0f766e", "#4f46e5", "#64748b", "#0369a1", "#0e7490", "#1d4ed8",
    ],
    "Vibrant": [
        "#14b8a6", "#f59e0b", "#ef4444", "#8b5cf6", "#22c55e", "#3b82f6",
        "#ec4899", "#eab308", "#06b6d4", "#f97316", "#a855f7", "#10b981",
    ],
}
_DEFAULT_PALETTE = "Pastel"

# Backward-compatible module constant (the historical pastel palette). New code
# should call active_palette(st)/series_color(i, st) so it reacts to the picker.
PALETTE = PALETTES[_DEFAULT_PALETTE]


def active_palette(st=None) -> list:
    """Return the user-selected palette (list of hex colors), defaulting to Pastel.

    Defensive against a stub/mock ``st`` or missing session_state.
    """
    if st is None:
        return PALETTES[_DEFAULT_PALETTE]
    try:
        choice = st.session_state.get("palette_choice", _DEFAULT_PALETTE)
    except Exception:
        choice = _DEFAULT_PALETTE
    return PALETTES.get(choice, PALETTES[_DEFAULT_PALETTE])


def series_color(index: int, st=None) -> str:
    """Nth categorical color from the active palette (cycles if out of range)."""
    pal = active_palette(st)
    return pal[index % len(pal)]


def assign_colors(names: list, st=None) -> dict:
    """Map each name to an active-palette color in order, cycling if needed.

    Pass ``st`` so the mapping follows the user's palette choice; without it the
    default Pastel palette is used (keeps older call sites working).
    """
    pal = active_palette(st)
    return {name: pal[i % len(pal)] for i, name in enumerate(names)}


# One color per CONCEPT (account type / income source), shared by every chart so
# the same thing is the same color everywhere. Each concept pins a fixed index
# into the active palette (so it still follows the palette picker). Indices are
# chosen so concepts that appear TOGETHER in one chart stay visually distinct
# (e.g. 0 vs 8 are both teals in Pastel, so they are never paired).
# "Your X" and "Partner X" share the concept hue; the partner is lightened.
CONCEPT_INDEX = {
    "401(k)": 0, "Roth IRA": 1, "Traditional IRA": 4, "HSA": 6,
    "Taxable brokerage": 11, "Cash": 3, "Home equity": 7, "Retirement": 0,
    "401(k) match": 9, "Salary": 2, "Social Security": 5,
    "Bonus": 10, "RSU": 4, "Other income": 1, "RMD": 5,
    # After-tax 401(k) -> Roth sits beside "Your 401(k)" in the savings stack, so
    # it must not share its teal (it used to resolve to the 401(k) concept).
    "After-tax Roth": 7,
}
_OWNER_PREFIXES = ("your ", "partner ", "their ")


def concept_of(name: str):
    """Canonical concept for a user-facing series name, or None if unknown."""
    n = str(name).lower()
    for pre in _OWNER_PREFIXES:
        if n.startswith(pre):
            n = n[len(pre):]
            break
    if "conversion" in n:
        return None
    if "after-tax" in n:
        return "After-tax Roth"
    if "401" in n and "match" in n:
        return "401(k) match"
    if "401" in n:
        return "401(k)"
    if "traditional" in n:
        return "Traditional IRA"
    if "roth" in n:
        return "Roth IRA"
    for key, concept in (("hsa", "HSA"), ("brokerage", "Taxable brokerage"),
                         ("taxable", "Taxable brokerage"), ("cash", "Cash"),
                         ("home", "Home equity"), ("retirement", "Retirement"),
                         ("social security", "Social Security"),
                         ("salary", "Salary"), ("base", "Salary"),
                         ("bonus", "Bonus"), ("rsu", "RSU"), ("other", "Other income")):
        if key in n:
            return concept
    return None


def _lighten(hex_color: str, amount: float = 0.4) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    f = lambda c: round(c + (255 - c) * amount)
    return f"#{f(r):02x}{f(g):02x}{f(b):02x}"


def concept_color(name: str, st=None, fallback=None) -> str:
    """Shared color for ``name`` (see CONCEPT_INDEX); ``fallback`` when unknown."""
    concept = concept_of(name)
    if concept is None:
        return fallback if fallback is not None else "#94a3b8"
    color = series_color(CONCEPT_INDEX[concept], st)
    if str(name).lower().startswith(("partner ", "their ")):
        color = _lighten(color)
    return color


def is_dark(st) -> bool:
    """Return True when the app's session theme_mode is set to Dark."""
    try:
        return "Dark" in str(st.session_state.get("theme_mode", ""))
    except Exception:
        # Defensive: a stub/mock st (or missing session_state) -> treat as light.
        return False


def _font_family(st) -> str:
    """Resolve the currently-selected font family (CSS stack) so Plotly charts
    match the app font selector. Plotly bakes font-family into the SVG, so this
    must be applied to the figure — CSS can't reach chart text.
    """
    try:
        from components.theme_toggle import FONT_OPTIONS, _DEFAULT_FONT
    except Exception:  # pragma: no cover
        try:
            from ui.components.theme_toggle import FONT_OPTIONS, _DEFAULT_FONT  # type: ignore
        except Exception:
            return _FONT_FAMILY
    try:
        choice = st.session_state.get("font_choice", _DEFAULT_FONT)
    except Exception:
        choice = _DEFAULT_FONT
    opt = FONT_OPTIONS.get(choice) or FONT_OPTIONS.get(_DEFAULT_FONT)
    return opt[1] if opt else _FONT_FAMILY


# Title/subtitle wrap widths (characters). A Plotly figure never knows its
# rendered width, so every chart is drawn twice (see show_chart): a regular
# version for wide screens and a compact one for phones. Regular: the title has
# the card minus the modebar (~700px). Compact: ~300px, one bold line of
# ~34 characters; subtitles are dropped there (the caption under each chart says
# the same) so nothing is clipped.
_TITLE_CHARS = {False: 64, True: 34}
_SUB_CHARS = {False: 100, True: 46}
_LEGEND_ASSUMED_PX = 330  # conservative chart width when estimating legend rows


def _bars_reach(fig, y, left: bool) -> bool:
    """True if a bar in the first (left) / last quarter of a bar chart rises above y,
    i.e. a label sitting just above a horizontal line at y would overlap it."""
    if not isinstance(y, (int, float)):
        return False
    for t in fig.data:
        if t.type == "bar" and t.y is not None and len(t.y) >= 4:
            ys = [v for v in t.y if isinstance(v, (int, float))]
            q = max(1, len(ys) // 4)
            if max(ys[:q] if left else ys[-q:], default=0) > y:
                return True
    return False


def _set_margin(fig, **new) -> None:
    """Apply margins; grow a fixed figure height by the same amount so the plot
    area keeps the size the chart was designed with."""
    m = fig.layout.margin
    grow = sum(v - (getattr(m, k) or 0) for k, v in new.items() if k in ("t", "b"))
    fig.update_layout(margin=new)
    if grow and fig.layout.height:  # keeps the plot area the same size
        fig.update_layout(height=fig.layout.height + grow)


def _has_title(t) -> bool:
    return bool(t is not None and getattr(t, "text", None))


def _legend_entries(fig) -> list:
    return [str(tr.name) for tr in (fig.data or [])
            if getattr(tr, "showlegend", None) is not False and getattr(tr, "name", None)]


def _legend_rows(fig, compact: bool = False) -> int:
    """Legend rows Plotly will draw. 0 when there is no legend (a lone trace
    gets none by default). Compact (phone): one entry per row. Otherwise with
    >=4 entries the legend uses a fixed 2-column grid (see style_fig), so
    rows = ceil(n/2) at ANY chart width; fewer entries flow in one line."""
    import math
    names = _legend_entries(fig)
    n = len(names)
    if n == 0 or (n == 1 and getattr(fig.layout, "showlegend", None) is not True):
        return 0
    if compact:
        return n
    if n >= 4:
        return math.ceil(n / 2)
    return max(1, math.ceil(sum(len(x) * 6.3 + 40 for x in names) / _LEGEND_ASSUMED_PX))


def _wrap_title(fig, compact: bool = False) -> None:
    """Wrap long title/subtitle lines with <br> (Plotly never wraps titles) and
    grow the top margin to fit the extra lines. Compact figures drop subtitle
    lines altogether."""
    import re
    import textwrap
    try:
        txt = fig.layout.title.text
    except Exception:
        return
    if not txt:
        return
    out, height = [], 0
    for i, line in enumerate(re.split(r"<br\s*/?>", txt)):
        if compact and i > 0:
            break
        m = re.match(r"^((?:<[^>]+>)*)([^<]*)((?:</[^>]+>)*)$", line)
        limit = _TITLE_CHARS[compact] if i == 0 else _SUB_CHARS[compact]
        if m and len(m.group(2)) > limit:
            pre, inner, post = m.groups()
            pieces = textwrap.wrap(inner, limit)
            if compact and len(pieces) > 1:
                # Balance the lines so a phone title never ends on a one-word orphan.
                even = textwrap.wrap(inner, min(limit, -(-len(inner) // len(pieces)) + 4))
                if len(even) == len(pieces):
                    pieces = even
            out.extend(f"{pre}{p}{post}" for p in pieces)
            n = len(pieces)
        else:
            out.append(line)
            n = 1
        height += n * (22 if i == 0 else 18)
    # Pin the title to the top of the figure so extra wrapped lines grow DOWN
    # into the reserved margin instead of being centred over the plot.
    # Plotly's top anchor puts a wrapped (multi-line) title ~11px per extra line too high, so
    # on a phone a two-line title sat ~8px under the card top: push it down to match one line.
    top_pad = 20 + 11 * (len(out) - 1) if compact else 14
    fig.update_layout(title=dict(text="<br>".join(out), yref="container", y=1,
                                 yanchor="top", pad=dict(t=top_pad, l=10 if compact else 0)))
    if compact:
        _set_margin(fig, t=20 + height + 14)   # same ~20px below the title for one and two lines
    else:
        _set_margin(fig, t=max(fig.layout.margin.t or 0, 36 + height))


def _x_extent(fig):
    """(lo, hi) of the x data / explicit x range, or None when not numeric."""
    rng = fig.layout.xaxis.range
    if rng is not None and len(rng) == 2:
        try:
            return float(rng[0]), float(rng[1])
        except (TypeError, ValueError):
            return None  # date axis
    lo = hi = None
    for tr in fig.data or []:
        xs = getattr(tr, "x", None)
        try:
            vals = [float(x) for x in xs if x is not None] if xs is not None else []
        except (TypeError, ValueError):
            return None
        if vals:
            lo = min(vals) if lo is None else min(lo, min(vals))
            hi = max(vals) if hi is None else max(hi, max(vals))
    return (lo, hi) if lo is not None and hi > lo else None


def _lift_vline_labels(fig, compact: bool) -> None:
    """Move the labels of vertical reference lines ("Retire @ 60", "Retirement
    (age 40)") from inside the plot, where they sat on top of the data and the
    top y tick, to the strip just above it. Each label is anchored to the side
    of its line that faces the plot centre (so none runs off the edge), and a
    label that would collide with the previous one is lifted one row higher."""
    ext = _x_extent(fig)
    anns = [a for a in (fig.layout.annotations or [])
            if a.xref == "x" and str(a.yref or "").endswith("domain") and a.y in (1, 1.0)
            and isinstance(a.x, (int, float))]
    if not anns or ext is None:
        return
    lo, hi = ext
    plot_w = 250 if compact else 700
    prev_end, level, max_level = -1.0, 0, 0
    for a in sorted(anns, key=lambda a: a.x):
        frac = (a.x - lo) / (hi - lo)
        right = frac > 0.6
        width = len(str(a.text)) * 6.0 / plot_w
        start, end = (frac - width, frac) if right else (frac, frac + width)
        level = (level + 1) if start < prev_end else 0
        prev_end = max(prev_end, end) if level else end
        max_level = max(max_level, level)
        a.update(yref="paper", y=1, yanchor="bottom", yshift=1 + 15 * level,
                 xanchor="right" if right else "left", xshift=-3 if right else 3,
                 showarrow=False)
    m = fig.layout.margin
    _set_margin(fig, t=max((m.t or 0) + 15 * max_level, 28 + 15 * max_level))


def _fit_age_axis(fig) -> None:
    """Pin a numeric "Age" x-axis to the data. Plotly otherwise anchors on 0
    when a bar/annotation/shape is present, squashing the plot into the right
    part of a narrow chart."""
    try:
        if str(fig.layout.xaxis.title.text) != "Age" or fig.layout.xaxis.range is not None:
            return
    except Exception:
        return
    lo = hi = None
    for tr in fig.data or []:
        xs = getattr(tr, "x", None)
        if xs is None or len(xs) == 0:
            continue
        try:
            vals = [float(x) for x in xs if x is not None]
        except (TypeError, ValueError):
            return  # categorical x: leave alone
        if not vals:
            continue
        pad = 0.5 if getattr(tr, "type", "") == "bar" else 0.0
        lo = min(vals) - pad if lo is None else min(lo, min(vals) - pad)
        hi = max(vals) + pad if hi is None else max(hi, max(vals) + pad)
    if lo is not None and hi > lo:
        fig.update_xaxes(range=[lo, hi])


def style_fig(fig, st, compact: bool = False):
    """Mutate `fig` with theme-aware colors and return it. ``compact`` is the
    phone variant (single-column legend, one-line title, no subtitle)."""
    dark = is_dark(st)
    fam = _font_family(st)

    text_color = "#e2e8f0" if dark else "#0f172a"
    grid_color = "#334155" if dark else "#e5e7eb"
    hover_bg = "#1e293b" if dark else "#ffffff"
    hover_border = "#334155" if dark else "#e5e7eb"

    # Pie/donut charts opt out of the global right-legend rule: their legend is
    # placed BELOW the chart by the component (so labels aren't truncated by the
    # capped pie width). Only theme its font here; don't move it or reserve a
    # right margin.
    is_pie = any(getattr(t, "type", None) == "pie" for t in (fig.data or []))

    layout_kwargs = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=fam, color=text_color),
        # Default categorical color cycle -> the user-selected palette. Only
        # affects traces that DON'T set an explicit color (charts with semantic
        # colors set their own and are unaffected); keeps auto-colored charts
        # consistent with the picker.
        colorway=active_palette(st),
        hoverlabel=dict(
            bgcolor=hover_bg,
            bordercolor=hover_border,
            font=dict(family=fam, color=text_color),
        ),
        modebar=dict(
            bgcolor="rgba(0,0,0,0)",
            color="#94a3b8",
            activecolor="#14b8a6",
        ),
    )
    if is_pie:
        # keep the component's own legend placement; just theme its font
        layout_kwargs["legend"] = dict(font=dict(family=fam, color=text_color))
    else:
        # Legend BELOW the plot, horizontal. A right-hand legend needs a fixed
        # pixel gutter reserved at figure-build time, but the rendered width is a
        # Streamlit column width we can't know here — so any fixed value is wrong
        # in both directions at once. Measured with r=150: a 396px-wide chart was
        # left a 153px data area (38% of the width gone), while on an 870px chart
        # long labels still overflowed the right edge. Below-the-plot costs a
        # little height instead, and scales at every viewport width.
        # yref="container" pins the legend to the bottom of the FIGURE, not the
        # plot area: a plot-relative y (-0.18) lands on the x-axis title ("Age")
        # whenever the plot height differs from what the offset was tuned for.
        layout_kwargs["legend"] = dict(
            orientation="h", yref="container", yanchor="bottom", y=0.0,
            xref="container" if compact else "paper", xanchor="left", x=0.03 if compact else 0.0,
            font=dict(family=fam, color=text_color,
                      size=10.5 if len(_legend_entries(fig)) >= 4 else 11.5),
            itemsizing="constant",
            # >=4 entries: exactly two columns (half the plot width each), so the
            # row count - and so the bottom margin we reserve - does not depend on
            # the unknown rendered width. Compact (phone): one column, because
            # half of a ~300px chart is too narrow for names like "Partner taxable
            # brokerage" (they truncated or overprinted).
            **(dict(entrywidthmode="fraction", entrywidth=1.0 if compact else 0.5)
               if len(_legend_entries(fig)) >= 4 or compact else {}),
        )
    fig.update_layout(**layout_kwargs)

    # Give the below-plot legend room, and drop the old right-hand gutter so the
    # data area gets the full width.
    if not is_pie and getattr(fig.layout, "showlegend", None) is not False:
        try:
            m = fig.layout.margin
            cur_r, cur_b = m.r, m.b
        except Exception:
            cur_r = cur_b = None
        new_r = 30 if (cur_r is None or cur_r >= 150) else cur_r
        if compact:  # the legend is clipped to the plot width: don't waste it on a gutter
            new_r = 18
        # Room for tick labels (+ the x-axis title if any) and then the legend rows.
        rows = _legend_rows(fig, compact)
        if compact and rows:
            # The x-axis title would sit between the ticks and the legend (they
            # collided); the caption and tick values carry the axis meaning.
            fig.update_xaxes(title_text=None)
        axis_h = 64 if _has_title(getattr(fig.layout.xaxis, "title", None)) else 40
        need_b = axis_h + rows * 20 + 14
        # Compact: exact (the legend is one column of known length, and any more
        # leaves a gap); regular: never less than the chart asked for.
        new_b = (need_b if compact else max(cur_b or 0, need_b)) if rows else cur_b
        _set_margin(fig, r=new_r, **({"b": new_b} if new_b is not None else {}))
        fig.update_xaxes(automargin=True)
        fig.update_yaxes(automargin=True)

    if compact and not is_pie:
        # Even side gutters on a ~300px card: tick labels grow the left one
        # (automargin), so the fixed margins stay small, and labels that sat in
        # the old right gutter move inside the plot, above their line at the left
        # (the right end is where the tall values are).
        m = fig.layout.margin
        fig.update_layout(margin=dict(l=min(m.l if m.l is not None else 80, 14), r=24))
        fig.update_yaxes(automargin=True)
        fig.update_xaxes(automargin=True)
        for a in fig.layout.annotations or []:
            if a.xref in ("paper", "x domain") and (a.x or 0) >= 1 and a.xanchor in (None, "auto", "left"):
                a.update(xanchor="left", x=0, yanchor="bottom", yshift=2)
                if _bars_reach(fig, a.y, left=True) and not _bars_reach(fig, a.y, left=False):
                    a.update(xanchor="right", x=1)   # bars at the left end poke through the label: use the right
    if compact:
        # Right-hand axis title + a wide gutter squeezed a ~300px plot (and the
        # legend, which is clipped to the plot width); the legend already names
        # the series, so keep only the ticks.
        try:
            if fig.layout.yaxis2.title.text:
                fig.update_layout(yaxis2_title_text=None)
        except Exception:
            pass
    _wrap_title(fig, compact)
    _fit_age_axis(fig)
    _lift_vline_labels(fig, compact)

    # Theme the title font ONLY when a title actually exists. Setting title_font
    # on a title-less figure makes Plotly render a literal "undefined" title.
    try:
        if fig.layout.title is not None and fig.layout.title.text:
            fig.update_layout(title_font_color=text_color, title_font_family=fam)
    except Exception:
        pass

    axis_kwargs = dict(
        gridcolor=grid_color,
        linecolor=grid_color,
        zerolinecolor=grid_color,
        tickfont=dict(family=fam, color=text_color),
        title_font=dict(family=fam, color=text_color),
    )

    # Figures without cartesian axes (e.g. pie/donut charts) don't support
    # update_xaxes/update_yaxes — guard so styling never raises.
    try:
        fig.update_xaxes(**axis_kwargs)
    except Exception:
        pass
    try:
        fig.update_yaxes(**axis_kwargs)
    except Exception:
        pass

    # Annotations don't inherit layout.font when they set their own font (some
    # hardcode family="Inter"), so apply the selected family explicitly — this is
    # what makes ALL chart text follow the app font selector.
    try:
        for ann in fig.layout.annotations:
            ann.font.family = fam
    except Exception:
        pass

    # Reference-line / caption annotations and title subtitles across the app
    # hardcode the muted caption gray #64748b, which is sub-AA (~3.1:1) on the
    # dark card background. In dark mode bump those specific greys to a lighter
    # muted (#94a3b8, AA-passing) — leaving any other deliberate annotation color
    # (e.g. a strong reference color) untouched.
    if dark:
        muted = "#94a3b8"
        try:
            for ann in fig.layout.annotations:
                if getattr(ann.font, "color", None) == "#64748b":
                    ann.font.color = muted
        except Exception:
            pass
        try:
            t = fig.layout.title
            if t is not None and t.text and "#64748b" in t.text:
                t.text = t.text.replace("#64748b", muted)
        except Exception:
            pass

    return fig


def show_chart(st, fig, key: str, config: dict | None = None) -> None:
    """Draw a chart twice - regular and phone-compact - and let theme.css show
    the one that fits (the server can't know a visitor's width; see
    ``style_fig``). ``fig`` is a Figure, or ``build(compact) -> Figure`` when
    the phone version needs different content (fewer points, shorter labels).
    The regular chart keeps ``key``; the compact one is ``{key}_compact``.
    """
    import copy
    config = PLOTLY_CONFIG if config is None else config
    build = fig if callable(fig) else (lambda compact, _f=fig: copy.deepcopy(_f))
    if not hasattr(st, "container"):  # stub st (tests / print): regular chart only
        st.plotly_chart(style_fig(build(False), st), width="stretch", config=config, key=key)
        return
    with st.container(key=f"mc-wide-{key}"):
        st.plotly_chart(style_fig(build(False), st), width="stretch", config=config, key=key)
    with st.container(key=f"mc-narrow-{key}"):
        st.plotly_chart(style_fig(build(True), st, compact=True), width="stretch",
                        config=config, key=f"{key}_compact")


def beeswarm_xy(values, x_center: float, half_width: float = 0.42, n_bins: int = 30):
    """Pack ``values`` into a density beeswarm centered on ``x_center`` — a
    "packed grid" that forms a violin-shaped point cloud.

    Values are binned along the y (value) axis; within each bin the points are
    spread symmetrically in x, scaled so the fullest bin spans ~``2*half_width``
    (narrower bins are narrower -> the outline traces the distribution's density,
    like a violin). Returns parallel ``(xs, ys)`` lists suitable for a scatter
    trace. ``half_width`` < 0.5 keeps each age's cloud from overlapping its
    neighbors on an integer-age x-axis.
    """
    import numpy as np

    v = np.asarray([x for x in values if x is not None], dtype=float)
    if v.size == 0:
        return [], []
    lo, hi = float(v.min()), float(v.max())
    if hi <= lo:  # all identical -> single centered column
        return [float(x_center)] * v.size, v.tolist()

    edges = np.linspace(lo, hi, n_bins + 1)
    bins = np.clip(np.digitize(v, edges) - 1, 0, n_bins - 1)
    max_count = max(1, int(np.bincount(bins, minlength=n_bins).max()))
    step = (2.0 * half_width) / max_count

    xs, ys = [], []
    for b in range(n_bins):
        members = np.where(bins == b)[0]
        m = members.size
        if m == 0:
            continue
        for k, ix in enumerate(members):
            xs.append(float(x_center) + (k - (m - 1) / 2.0) * step)
            ys.append(float(v[ix]))
    return xs, ys
