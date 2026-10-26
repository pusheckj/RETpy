"""Theme toggle + font selector — light/dark mode and font family selectors
that live in the top-bar Settings popover.

Streamlit's config.toml theme is locked at page load, so to switch themes/fonts
dynamically we inject CSS at the top of every rerun (see ``inject_theme_css`` and
``inject_font_css``, both called once near the top of ``app.py``). CSS targets
Streamlit's stable DOM testid selectors.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Font selector
# ---------------------------------------------------------------------------
# label -> (Google-Fonts family spec or None for system, CSS font-family stack)
FONT_OPTIONS = {
    "Inter": ("Inter:wght@400;500;600;700",
              "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"),
    "Poppins": ("Poppins:wght@400;500;600;700",
                "Poppins, sans-serif"),
    "Nunito": ("Nunito:wght@400;600;700;800",
               "Nunito, sans-serif"),
    "Source Serif 4": ("Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700",
                        "'Source Serif 4', Georgia, serif"),
    "Lora": ("Lora:wght@400;500;600;700",
             "Lora, Georgia, serif"),
    "Space Grotesk": ("Space+Grotesk:wght@400;500;600;700",
                      "'Space Grotesk', sans-serif"),
    "System": (None,
               "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"),
}
_DEFAULT_FONT = "Lora"


def inject_font_css(st) -> None:
    """Apply the selected font family app-wide.

    Kept separate from ``render`` (the selector widget) so the font applies on
    every rerun regardless of whether the Settings popover is open. Call once
    near the top of the app, always.
    """
    choice = st.session_state.get("font_choice", _DEFAULT_FONT)
    gf, stack = FONT_OPTIONS.get(choice, FONT_OPTIONS[_DEFAULT_FONT])
    css = ""
    if gf:
        css += f"@import url('https://fonts.googleapis.com/css2?family={gf}&display=swap');"
    # Force the family on ALL app text — Streamlit's emotion classes set their own
    # font-family on captions, metric values, slider values, dropdowns, tabs, etc.,
    # so a narrow selector list misses "a lot of small text". Then RESTORE the
    # Material icon ligature font (else icons render as literal words).
    css += f"html, body, .stApp, .stApp * {{ font-family: {stack} !important; }}"
    css += (
        '[data-testid="stIconMaterial"], [data-testid="stAlertDynamicIcon"], [data-testid="stExpanderIcon"], '
        'span[class*="material-symbols"], span[class*="material-icons"], '
        '.material-icons, .material-symbols-rounded '
        '{ font-family: "Material Symbols Rounded","Material Symbols Outlined","Material Icons" !important; }'
    )
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Dark theme
# ---------------------------------------------------------------------------
# Palette: dark bluish-brown background (#201e27), muted-grey tile/menu interiors
# (#37343f), warm off-white text. The design-token overrides on :root cascade
# into every theme.css rule that uses var(--mc-*); the explicit rules below cover
# Streamlit's own components (which theme.css can't express via tokens).
_DARK_CSS = """
<style id="mc-dark-theme">
/* Design tokens — override the light values from theme.css :root */
:root {
    --mc-bg: #201e27;
    --mc-tile: #37343f;
    --mc-tile-border: #47434f;
    --mc-tile-shadow: 0 10px 26px rgba(0, 0, 0, 0.45);
    --mc-sidebar-bg: #2a2733;
    --mc-ink: #e8e3da;
    --mc-muted: #a89f95;
}

/* Root containers */
[data-testid="stAppViewContainer"],
[data-testid="stApp"],
section.main,
.main .block-container,
.stApp {
    background-color: #201e27 !important;
    color: #e8e3da !important;
}
/* Cream paper texture would fight the dark bg — drop it in dark. */
.stApp,
[data-testid="stAppViewContainer"] {
    background-image: none !important;
}

/* Sidebar */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div,
[data-testid="stSidebarContent"] {
    background-color: #2a2733 !important;
    color: #e8e3da !important;
}

/* Sidebar collapse / reopen chevron icons — light glyph on dark */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
[data-testid="stExpandSidebarButton"],
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {
    color: #e8e3da !important;
}
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="stExpandSidebarButton"] svg {
    fill: #e8e3da !important;
}

/* Section tiles (keyed st.container) + cards -> muted grey */
[class*="st-key-mc-tile"],
.mc-card,
.mc-stat-card {
    background-color: #37343f !important;
    border-color: #47434f !important;
    color: #e8e3da !important;
    box-shadow: 0 2px 14px rgba(0, 0, 0, 0.35) !important;
}

/* Hero / KPI text */
.mc-hero-num,
.mc-stat-value,
.mc-ink-strong,
.mc-section {
    color: #f3efe8 !important;
}
.mc-hero-label,
.mc-stat-label,
.mc-muted {
    color: #a89f95 !important;
}
/* Semantic value colors on custom cards — more specific than `.stMarkdown div`
   so success/risk/teal accents survive dark mode. */
.stMarkdown .mc-good { color: #34d399 !important; }
.stMarkdown .mc-warn { color: #fbbf24 !important; }
.stMarkdown .mc-bad  { color: #f87171 !important; }
.stMarkdown .mc-teal { color: #2dd4bf !important; }

/* Soft-segmented toggle in dark mode (container bg = grey tile via --mc-tile) */
[role="radiogroup"].mc-seg label,
[role="radiogroup"].mc-seg label div,
[role="radiogroup"].mc-seg label p { color: #a89f95 !important; }
[role="radiogroup"].mc-seg label:has(input:checked) { background: rgba(45, 212, 191, 0.16) !important; }
[role="radiogroup"].mc-seg label:has(input:checked),
[role="radiogroup"].mc-seg label:has(input:checked) div,
[role="radiogroup"].mc-seg label:has(input:checked) p { color: #2dd4bf !important; }

/* Generic Streamlit text */
.stMarkdown,
.stMarkdown p,
.stMarkdown li,
.stMarkdown div,
.stCaption,
.stCaption p,
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p,
h1, h2, h3, h4, h5, h6,
label,
[data-testid="stWidgetLabel"],
[data-testid="stHeadingWithActionElements"] {
    color: #e8e3da !important;
}
.stMarkdown code {
    background-color: #47434f !important;
    color: #f3efe8 !important;
}

/* Captions and helper text */
.stCaption,
[data-testid="stCaptionContainer"],
[data-testid="stCaption"] {
    color: #a89f95 !important;
}

/* Expanders / menus -> muted grey */
[data-testid="stExpander"],
details,
details summary,
[data-testid="stExpanderDetails"] {
    background-color: #302d38 !important;
    border-color: #47434f !important;
    color: #e8e3da !important;
}
@media (hover: hover) {
    summary:hover,
    [data-testid="stExpander"] summary:hover {
        background-color: #3d3947 !important;
    }
}

/* Inputs: number_input, text_input, text_area */
input,
textarea,
[data-baseweb="input"],
[data-baseweb="input"] input,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] textarea {
    background-color: #26232f !important;
    color: #f3efe8 !important;
    border-color: #47434f !important;
    caret-color: #f3efe8 !important;
}
input[type="number"],
input[type="text"] {
    background-color: #26232f !important;
    color: #f3efe8 !important;
}
[data-baseweb="input"]:focus-within,
[data-baseweb="select"] > div:focus-within {
    border-color: #14b8a6 !important;
}

/* Buttons inside number_input (+/-) */
button[data-testid="stNumberInputStepUp"],
button[data-testid="stNumberInputStepDown"] {
    background-color: #47434f !important;
    color: #f3efe8 !important;
    border-color: #47434f !important;
}

/* Selectbox dropdown menu */
[role="listbox"],
[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="menu"] li {
    background-color: #302d38 !important;
    color: #e8e3da !important;
}
[data-baseweb="menu"] li:hover {
    background-color: #3d3947 !important;
}

/* Radio and checkbox */
[data-baseweb="radio"] div,
[data-baseweb="checkbox"] div {
    color: #e8e3da !important;
}

/* Sliders */
.stSlider [data-baseweb="slider"] div[role="slider"] {
    background-color: #14b8a6 !important;
    border-color: #14b8a6 !important;
}
.stSlider [data-baseweb="slider"] > div:first-child > div {
    background-color: #14b8a6 !important;
}
.stSlider [data-testid="stTickBar"] {
    color: #a89f95 !important;
}

/* Buttons (primary + secondary) */
.stButton > button,
[data-testid="stButton"] > button,
[data-testid="stDownloadButton"] > button {
    background-color: #14b8a6 !important;
    color: #201e27 !important;
    border-color: #14b8a6 !important;
}
.stButton > button:hover,
[data-testid="stButton"] > button:hover,
[data-testid="stDownloadButton"] > button:hover {
    background-color: #0d9488 !important;
    color: #ffffff !important;
}
.stButton > button[kind="secondary"],
[data-testid="stButton"] > button[kind="secondary"] {
    background-color: #413d4a !important;
    color: #e8e3da !important;
    border-color: #47434f !important;
}

/* Popover trigger (e.g. the top-bar Settings button) */
[data-testid="stPopover"] > div > button,
[data-testid="stPopover"] button {
    background-color: #37343f !important;
    border-color: #47434f !important;
}
[data-testid="stPopover"] button,
[data-testid="stPopover"] button p,
[data-testid="stPopover"] button span {
    color: #e8e3da !important;
}
[data-testid="stPopover"] button:hover {
    background-color: #3d3947 !important;
}

/* Form-submit buttons (e.g. "Pin current scenario") — match the primary style. */
[data-testid="stFormSubmitButton"] > button {
    background-color: #14b8a6 !important;
    border-color: #14b8a6 !important;
}
[data-testid="stFormSubmitButton"] > button,
[data-testid="stFormSubmitButton"] > button p,
[data-testid="stFormSubmitButton"] > button span {
    color: #201e27 !important;
}
[data-testid="stFormSubmitButton"] > button:hover {
    background-color: #0d9488 !important;
}
[data-testid="stFormSubmitButton"] > button:hover,
[data-testid="stFormSubmitButton"] > button:hover p {
    color: #ffffff !important;
}

/* Tabs (soft segmented) */
.stTabs [data-baseweb="tab-list"] {
    background-color: #37343f !important;
    border-color: #47434f !important;
}
.stTabs [data-baseweb="tab"],
.stTabs [data-baseweb="tab"] p {
    color: #a89f95 !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"],
.stTabs [aria-selected="true"] p {
    color: #2dd4bf !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: rgba(45, 212, 191, 0.16) !important;
}

/* File uploader */
[data-testid="stFileUploaderDropzone"] {
    background-color: #302d38 !important;
    border-color: #47434f !important;
    color: #e8e3da !important;
}
[data-testid="stFileUploaderDropzone"] small {
    color: #a89f95 !important;
}

/* st.segmented_control: unselected segments default to the light theme's cream
   surface; give them the dark tile with muted text (selected keeps its teal). */
[data-testid="stBaseButton-segmented_control"] {
    background-color: #26232f !important;   /* inset, like the light theme's cream pill on a white card */
    border-color: var(--mc-tile-border) !important;
}
[data-testid="stBaseButton-segmented_control"],
[data-testid="stBaseButton-segmented_control"] p { color: var(--mc-muted) !important; }
/* Select chevrons were the light theme's dark ink on the dark field (invisible). */
[data-baseweb="select"] svg { color: var(--mc-ink) !important; fill: var(--mc-ink) !important; }
[data-testid="stBaseButton-segmented_controlActive"] p { color: #2dd4bf !important; }
@media (hover: hover) {
    [data-testid="stBaseButton-segmented_control"]:hover { background-color: #3d3947 !important; }
    [data-testid="stBaseButton-segmented_control"]:hover p { color: var(--mc-ink) !important; }
}

/* Help tooltips: the popup box defaults to the light cream surface (the text
   was already light, so it vanished); "?" icons need more presence on dark. */
[data-baseweb="tooltip"] > div {
    background-color: var(--mc-tile) !important;
    border: 1px solid var(--mc-tile-border) !important;
}
[data-testid="stTooltipContent"],
[data-testid="stTooltipContent"] * { color: var(--mc-ink) !important; }
[data-testid="stTooltipIcon"] svg { color: var(--mc-muted) !important; opacity: 1 !important; }

/* Data editor */
[data-testid="stDataFrame"],
[data-testid="stDataEditor"] {
    background-color: #2a2733 !important;
}
/* st.dataframe draws on a canvas using the (light) config theme, which CSS
   can't recolor; invert it (hue-rotate keeps the accents' hues) so cells,
   header and text follow the dark theme. */
[data-testid="stDataFrame"] [data-testid="stDataFrameResizable"],
[data-testid="stDataEditor"] [data-testid="stDataFrameResizable"] {
    filter: invert(0.9) hue-rotate(180deg) saturate(0.25) brightness(1.1);   /* neutral dark grey, like the tiles */
}

/* Divider */
hr {
    border-color: #47434f !important;
}

/* Info / success / warning / error boxes */
[data-testid="stAlert"], [data-testid="stAlertContainer"] {
    background-color: #302d38 !important;
    color: #e8e3da !important;
    border-color: #47434f !important;
}

/* Plotly chart backgrounds */
.js-plotly-plot,
.plotly,
.plot-container {
    background-color: transparent !important;
}

/* Progress bar track */
.stProgress > div > div {
    background-color: #47434f !important;
}
.stProgress > div > div > div {
    background-color: #14b8a6 !important;
}

/* Metric component */
[data-testid="stMetricValue"],
[data-testid="stMetricLabel"],
[data-testid="stMetricDelta"] {
    color: #f3efe8 !important;
}

/* Sticky top bar — solid tile, no accent border (matches sections) */
.st-key-mc-topbar {
    background: #37343f !important;
    border: 1px solid #47434f !important;
    box-shadow: 0 10px 26px rgba(0, 0, 0, 0.45) !important;
}
.mc-topbar-title {
    color: #2dd4bf !important;
}
.mc-topbar-metric-value {
    color: #f3efe8 !important;
}
.mc-topbar-metric-label {
    color: #5eead4 !important;
}
.mc-topbar-metric-hint {
    color: #a89f95 !important;
}

/* Primary buttons keep the pill + gradient (dark shadow) */
.stButton > button[kind="primary"],
[data-testid="stButton"] > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button {
    background: linear-gradient(90deg, #0d9488 0%, #22c55e 100%) !important;
    border-color: transparent !important;
    box-shadow: none !important;
    filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.5));
}
.stButton > button[kind="primary"], .stButton > button[kind="primary"] p,
[data-testid="stFormSubmitButton"] > button, [data-testid="stFormSubmitButton"] > button p {
    color: #ffffff !important;
}

/* Elevated cards + section tiles — deeper shadow on dark */
.mc-card, .mc-stat-card, [class*="st-key-mc-tile"] {
    box-shadow: 0 10px 26px rgba(0, 0, 0, 0.45) !important;
}

/* Callout banners (icon card) on dark */
[data-testid="stAlert"] p, [data-testid="stAlertContainer"] p {
    color: #e8e3da !important;
}
[data-testid="stAlert"] svg { color: #2dd4bf !important; fill: #2dd4bf !important; }

/* ---- Round 3 ---- */
/* Secondary / tertiary buttons (Remove, Browse files, Forget my data...) used the
   light cream surface; give them the dark tile with ink text and a tile border.
   Tertiary stays an outlined, non-primary button. */
:root button[data-testid="stBaseButton-secondary"],
:root button[data-testid="stBaseButton-tertiary"] {
    background: var(--mc-tile) !important;
    border: 1px solid var(--mc-tile-border) !important;
    box-shadow: none !important;
    filter: none !important;
}
:root button[data-testid="stBaseButton-tertiary"] { background: transparent !important; }
:root button[data-testid="stBaseButton-secondary"],
:root button[data-testid="stBaseButton-secondary"] p,
:root button[data-testid="stBaseButton-secondary"] span,
:root button[data-testid="stBaseButton-tertiary"],
:root button[data-testid="stBaseButton-tertiary"] p,
:root button[data-testid="stBaseButton-tertiary"] span { color: var(--mc-ink) !important; }
:root button[data-testid="stBaseButton-secondary"]:hover,
:root button[data-testid="stBaseButton-tertiary"]:hover { background: #3d3947 !important; }
:root button[data-testid="stBaseButton-secondary"]:hover p,
:root button[data-testid="stBaseButton-tertiary"]:hover p { color: var(--mc-ink) !important; }

/* ...except link-style tertiaries, which stay plain links as in light mode. */
:root .st-key-gs_skip button[data-testid="stBaseButton-tertiary"],
:root .st-key-gs_skip button[data-testid="stBaseButton-tertiary"]:hover {
    background: transparent !important; border: none !important;
}
:root .st-key-gs_skip button[data-testid="stBaseButton-tertiary"] p { color: var(--mc-muted) !important; }
:root .st-key-gs_skip button[data-testid="stBaseButton-tertiary"]:hover p { color: var(--mc-ink) !important; }
/* Placeholders ("Required") were dark on the dark field. */
input::placeholder, textarea::placeholder { color: var(--mc-muted) !important; opacity: .85 !important; }

/* File uploader text + icon */
[data-testid="stFileUploaderDropzone"] span,
[data-testid="stFileUploaderDropzone"] p,
[data-testid="stFileUploaderDropzone"] div { color: var(--mc-ink) !important; }
[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderDropzone"] small span { color: var(--mc-muted) !important; }
[data-testid="stFileUploaderDropzone"] svg,
[data-testid="stFileUploaderDropzoneInstructions"] svg { color: var(--mc-muted) !important; fill: var(--mc-muted) !important; }

/* Text-input wrapper draws its own (light) outline + fill */
[data-testid="stTextInputRootElement"],
[data-testid="stNumberInputContainer"] {
    background-color: #26232f !important;
    border-color: var(--mc-tile-border) !important;
}
.stApp [class*="st-key-simple-debt-"] [data-testid="stTextInputRootElement"] { border-color: var(--mc-tile-border) !important; }

/* Toggle: a visible "off" track */
label[data-baseweb="checkbox"]:has(input:not(:checked)) > div:first-child {
    background-color: #6b6577 !important;
}

/* Alert icons keep their glyphs readable */
[data-testid="stAlert"] [data-testid="stIconMaterial"],
[data-testid="stAlert"] [data-testid="stAlertDynamicIcon"] { color: #2dd4bf !important; }
/* Phone polish C4: details that stayed light or too faint on dark. */
[data-testid="stTooltipIcon"] svg { stroke: currentColor !important; }   /* theme.css fixes a dark stroke */
div:has(> [data-testid="stNumberInputIcon"]) { background-color: #4a4655 !important; }
[data-testid="stNumberInputIcon"], [data-testid="stNumberInputIcon"] * { color: var(--mc-ink) !important; }
[data-testid="stExpander"] summary [data-testid="stExpanderIcon"] { color: #2dd4bf !important; background-color: rgba(45, 212, 191, 0.16) !important; }
[role="radiogroup"].mc-seg label:not(:has(input:checked)) p { color: var(--mc-muted) !important; }
/* Polish M1: theme.css styles these groups through an :is() list that out-ranks the .mc-seg
   rules above, so their selected label stayed the light-mode teal (2.8:1). Same list, same
   weight, injected later: every selected segment label uses the bright teal. */
:is([role="radiogroup"].mc-seg, [class*="st-key-mc-mode-switch"] [role="radiogroup"], [class*="st-key-"][class*="_dollars_mode"] [role="radiogroup"]) label:has(input:checked),
:is([role="radiogroup"].mc-seg, [class*="st-key-mc-mode-switch"] [role="radiogroup"], [class*="st-key-"][class*="_dollars_mode"] [role="radiogroup"]) label:has(input:checked) div,
:is([role="radiogroup"].mc-seg, [class*="st-key-mc-mode-switch"] [role="radiogroup"], [class*="st-key-"][class*="_dollars_mode"] [role="radiogroup"]) label:has(input:checked) p { color: #2dd4bf !important; }
/* Polish F1: radio dots use the dark palette (they stayed cream) and the text input's
   inner box (cream in light mode) no longer shows as a pale rim around the dark field. */
label[data-baseweb="radio"]:has(input:not(:checked)) > div:first-child { background-color: #6b6577 !important; }
label[data-baseweb="radio"]:has(input:not(:checked)) > div:first-child > div { background-color: #26232f !important; }
label[data-baseweb="radio"]:has(input:checked) > div:first-child > div { background-color: #201e27 !important; }
[data-testid="stTextInputRootElement"] [data-baseweb="base-input"] { background-color: transparent !important; }
</style>
"""


_APPEARANCE_KEYS = ("theme_mode", "font_choice", "palette_choice")
_SAVED_KEY = "_appearance_saved"


def persist_appearance(st) -> None:
    """Keep theme/font/palette across runs that don't render their widgets.

    Streamlit drops a widget's session value after any run that doesn't render
    that widget (e.g. the welcome, check-up and guided-setup screens, which
    return before the Settings popover). So mirror the choices into a plain
    key each run and restore them when the widget key has vanished (same
    pattern as ``remember_device`` / ``remember_device_toggle``).
    """
    saved = dict(st.session_state.get(_SAVED_KEY) or {})
    for key in _APPEARANCE_KEYS:
        if key in st.session_state:
            saved[key] = st.session_state[key]
        elif key in saved:
            st.session_state[key] = saved[key]
    st.session_state[_SAVED_KEY] = saved


def inject_theme_css(st) -> None:
    """Inject the dark-mode CSS override when Dark is selected.

    Kept SEPARATE from ``render`` (the radio widget) so the theme applies on
    every run regardless of where the radio lives — the radio now sits inside
    the top-bar Settings popover, whose body would otherwise only guarantee the
    override while open. Call this once near the top of the app, always.
    """
    persist_appearance(st)
    if "Dark" in str(st.session_state.get("theme_mode", "")):
        st.markdown(_DARK_CSS, unsafe_allow_html=True)


def render(st) -> None:
    st.markdown(
        '<div style="font-size: 13px; color: #64748b; text-transform: uppercase; '
        'letter-spacing: 0.05em; margin-bottom: 6px;">Theme</div>',
        unsafe_allow_html=True,
    )

    if "theme_mode" not in st.session_state:
        st.session_state["theme_mode"] = "☀ Light"

    # Radio uses session_state["theme_mode"] as its source of truth (no index=).
    # The actual CSS injection is done by ``inject_theme_css`` at the app top so
    # dark mode holds whether or not this popover is open.
    st.radio(
        "Theme",
        options=["☀ Light", "🌙 Dark"],
        horizontal=True,
        label_visibility="collapsed",
        key="theme_mode",
    )

    st.markdown(
        '<div style="font-size: 13px; color: #64748b; text-transform: uppercase; '
        'letter-spacing: 0.05em; margin: 10px 0 6px 0;">Font</div>',
        unsafe_allow_html=True,
    )
    if "font_choice" not in st.session_state:
        st.session_state["font_choice"] = _DEFAULT_FONT
    st.selectbox(
        "Font",
        options=list(FONT_OPTIONS.keys()),
        label_visibility="collapsed",
        key="font_choice",
        help="Experiment with the app's typeface. Applies everywhere on the next rerun.",
    )

    st.markdown(
        '<div style="font-size: 13px; color: #64748b; text-transform: uppercase; '
        'letter-spacing: 0.05em; margin: 10px 0 6px 0;">Chart palette</div>',
        unsafe_allow_html=True,
    )
    try:
        from utils.plot_theme import PALETTES, _DEFAULT_PALETTE
    except ImportError:  # pragma: no cover
        from ui.utils.plot_theme import PALETTES, _DEFAULT_PALETTE  # type: ignore
    if "palette_choice" not in st.session_state:
        st.session_state["palette_choice"] = _DEFAULT_PALETTE
    st.selectbox(
        "Chart palette",
        options=list(PALETTES.keys()),
        label_visibility="collapsed",
        key="palette_choice",
        help="Color scheme for chart series. Semantic colors (success/risk, the "
             "teal brand accent, median-vs-downside bands) stay fixed; only "
             "categorical series (accounts, income sources, spending buckets) recolor.",
    )
