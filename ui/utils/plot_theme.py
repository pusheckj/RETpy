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


def style_fig(fig, st):
    """Mutate `fig` with theme-aware colors and return it."""
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
        layout_kwargs["legend"] = dict(
            orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0.0,
            font=dict(family=fam, color=text_color, size=11.5),
            itemsizing="constant",
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
        new_b = max(cur_b or 0, 96)
        fig.update_layout(margin=dict(r=new_r, b=new_b))

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
