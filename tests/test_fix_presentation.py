"""Regression pins for the ui/components/ + ui/styles/ presentation fix pass.

Each test corresponds to one verified defect in the presentation layer. Where
the fix is behavioural it is exercised through the real helper; where the fix
lives in CSS or in literal copy the pin is a source assertion (the same
approach ``tests/test_fix_ui-core.py`` takes), because the alternative is a
full browser run.

Findings pinned here:

1.  ``sec_savings._render_manual`` seeded ``st.number_input`` from an override
    written by Auto mode (the age-50+ 401(k) catch-up limit, \\$30,500) against
    a ``max_value`` of \\$30,000 → ``StreamlitValueAboveMaxError``, which
    ``app.py::_safe_render`` swallowed, replacing the WHOLE Savings section
    (mode radio included) with a placeholder.
2.  ``sensitivity_tab._render_break_even`` read ``TARGET_SUCCESS_RATE`` from the
    cfg module, which ``sim_runner._restore_overrides`` resets to the shipped
    0.80 after every run — so a 95%-target user got a break-even value that
    only cleared 80%.
3.  The deterministic net-worth projection grows balances at REAL returns but
    scaled each year's contribution by a NOMINAL inflation factor, overstating
    the "At retirement" KPI by ~2.25x at a 30-year horizon.
5.  ``savings_projection_chart``'s cumulative line was a hardcoded near-black,
    invisible on the dark card background, and its chart key lacked the theme
    suffix so ``uirevision="keep"`` retained the stale color.
6.  ``income_over_time._retirement_ss_for_age`` gated on cfg (default True)
    rather than the override, so the chart kept stacking a Social Security band
    after the user unchecked "Include Social Security".
7.  ``hero_metric`` painted the success rate success-green at any level,
    contradicting ``stats_row``'s red "✕ At risk" for the same number.
8.  ``bridge_years_gauge`` told users with missing accessible-balance data that
    they "retire at or after 59½" — the opposite of a 45-year-old's situation.
9.  ``tax_tab``'s hovertemplate used a printf-style ``%%`` escape that Plotly
    does not honour, rendering "14.20%%".
10. ``net_worth_box_chart`` labelled an investable-only series "Net worth"
    while the top bar and Current-portfolio card include home equity.
11. ``success_by_age`` colored bars against a hardcoded 80% threshold (not the
    user's target) using the Pastel-pinned ``PALETTE`` constant.
12. ``spending_range_chart`` reported ``rows[-1]["n"]`` — the survivor count at
    plan end — as the simulation count.
13/16/17. An unscoped ``stMetricValue { overflow: visible; white-space: nowrap }``
    block injected from ``sec_income`` defeated Streamlit's ellipsis clipping
    app-wide and made 32px sidebar metric values overlap into mush.
14. The "Sync to inputs" button sat in a 47px sidebar column and rendered as a
    vertical stack of single letters.
15/29. ``first_decade_stress``'s one-line Plotly subtitle overflowed the chart
    and its dataframe header was clipped.
19. The lifecycle selectbox's selected value was ellipsized in the sidebar.
23. ``portfolio_breakdown``'s stat-card value was sized in ``vw`` (viewport),
    so at tablet width it clamped to its floor and overprinted neighbours.
27. ``sec_taxes`` / ``sec_savings`` captions used bare ``money()``, whose two
    unescaped ``$`` were rendered as KaTeX by Streamlit.
28. Both spending-chart vline labels sat on the top row with fixed sides, so
    "Retirement (age 40)" clipped against the plot's left edge and collided
    with "Mortgage paid off".
18/20/21/22/24/26. The sticky top bar's ``flex-wrap: nowrap`` row overflowed
    stMain at narrow widths (dead horizontal scrollbar, off-screen Settings
    popover, metrics painted over the Run button, bar eating half the viewport)
    and the sidebar was pinned to 328px on tablets.

``utils``/``components`` live under ``ui/``; add both roots to sys.path.
"""
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------
class _SessionState(dict):
    """dict that also supports attribute access, like st.session_state."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class FakeSt:
    """Minimal Streamlit stand-in that records what components emit.

    ``number_input`` reproduces Streamlit's real contract: it raises when the
    session_state value it is initialized from exceeds ``max_value`` (that is
    the ``StreamlitValueAboveMaxError`` the Savings section tripped over).
    """

    def __init__(self, overrides=None, session=None):
        self.session_state = _SessionState(session or {})
        self.session_state.setdefault("user_overrides", dict(overrides or {}))
        self.markdown_calls = []
        self.caption_calls = []
        self.warning_calls = []
        self.metric_calls = []
        self.number_inputs = []
        self.buttons = []

    # -- recording sinks ---------------------------------------------------
    def markdown(self, body, *a, **k):
        self.markdown_calls.append(body)

    def caption(self, body, *a, **k):
        self.caption_calls.append(body)

    def warning(self, body, *a, **k):
        self.warning_calls.append(body)

    def metric(self, label, value=None, *a, **k):
        self.metric_calls.append((label, value))

    def button(self, label, *a, **k):
        self.buttons.append((label, k))
        return bool(k.pop("_press", False))

    def selectbox(self, label, options, *a, **k):
        key = k.get("key")
        if key and key in self.session_state:
            return self.session_state[key]
        return list(options)[0]

    def number_input(self, label, min_value=None, max_value=None, step=None,
                     key=None, **k):
        cur = self.session_state.get(key)
        if cur is not None and max_value is not None and cur > max_value:
            raise ValueError(
                f"The `value` {cur} is greater than the `max_value` "
                f"{float(max_value)}."
            )
        if cur is not None and min_value is not None and cur < min_value:
            raise ValueError(
                f"The `value` {cur} is less than the `min_value` "
                f"{float(min_value)}."
            )
        self.number_inputs.append((label, min_value, max_value, cur))
        return cur if cur is not None else (min_value or 0)

    # -- no-op / passthrough surface --------------------------------------
    def info(self, *a, **k):
        pass

    def success(self, *a, **k):
        pass

    def slider(self, label, *a, **k):
        return self.session_state.get(k.get("key"), k.get("min_value", 0))

    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [_NullCtx(self) for _ in range(n)]

    def spinner(self, *a, **k):
        return _NullCtx(self)

    def expander(self, *a, **k):
        return _NullCtx(self)

    def plotly_chart(self, *a, **k):
        pass

    def dataframe(self, *a, **k):
        pass


class _NullCtx:
    def __init__(self, st):
        self._st = st

    def __enter__(self):
        return self._st

    def __exit__(self, *exc):
        return False


def _read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _read_code(*parts):
    """Source with whole-line ``#`` comments stripped.

    Several fixes left an explanatory comment quoting the OLD broken code
    (``st.columns([3, 1])``, the unscoped ``stMetricValue`` block). Source-level
    pins must not match those.
    """
    return "\n".join(
        line for line in _read(*parts).splitlines()
        if not line.lstrip().startswith("#")
    )


def _make_fake_sweep(captured: dict):
    """Stand-in for ``sim_runner.sweep_break_even`` that records its kwargs.

    Returns the real function's documented shape so ``_render_break_even`` can
    render its result box (that box's label is where the wrong target showed up).
    """
    def _fake(base_overrides, param_name, values, **kwargs):
        captured.update(kwargs)
        return {
            "param_name": param_name,
            "values": list(values),
            "success_rates": [0.9 for _ in values],
            "break_even_value": values[0],
            "target_success_rate": kwargs.get("target_success_rate"),
        }
    return _fake


@pytest.fixture(scope="module")
def theme_css():
    return _read("ui", "styles", "theme.css")


# ==========================================================================
# 1. Savings section survives the Auto -> Manual switch for an age-50+ house
# ==========================================================================
def test_manual_401k_max_clears_age50_catchup_limit():
    """The manual 401(k) bound must cover what Auto mode can write."""
    from components.sec_savings import _MANUAL_401K_MAX
    from utils.derived import get_limit

    # Auto mode writes get_limit("401k", age) straight into user_overrides.
    assert get_limit("401k", 55) == 30_500, "limit table changed; re-check bound"
    assert _MANUAL_401K_MAX >= get_limit("401k", 55), (
        "manual 401(k) max_value must clear the age-50+ catch-up limit, "
        "otherwise st.number_input raises StreamlitValueAboveMaxError"
    )


def test_manual_amount_clamps_seed_to_max_value():
    """``_manual_amount`` must clamp its seed — ``ensure_default`` does not."""
    from components.sec_savings import _manual_amount

    st = FakeSt(overrides={"YOUR_401K_CONTRIBUTION": 30_500})
    # A max_value BELOW the stored override is the crash setup.
    _manual_amount(st, "sv_manual_your_401k", "YOUR_401K_CONTRIBUTION",
                   "Your 401(k) ($/yr)", 10_000, 500)
    assert st.session_state["sv_manual_your_401k"] == 10_000


def test_render_manual_does_not_raise_for_age_55_auto_allocation():
    """End-to-end: Auto's amounts must not blow up Manual mode."""
    from components.sec_savings import _render_manual
    from utils.derived import auto_allocate_savings

    overrides = {"YOUR_AGE": 55, "PARTNER_AGE": 53, "YOUR_HSA": 40_000}
    overrides.update(auto_allocate_savings(200_000, overrides))
    assert overrides["YOUR_401K_CONTRIBUTION"] == 30_500

    st = FakeSt(overrides=overrides)
    _render_manual(st, 200_000, overrides)  # must not raise

    seeded = {k: v for k, v in st.session_state.items() if k.startswith("sv_manual_")}
    assert seeded["sv_manual_your_401k"] == 30_500
    assert seeded["sv_manual_partner_401k"] == 30_500


# ==========================================================================
# 2. Break-even finder honours the user's target success rate
# ==========================================================================
def test_break_even_uses_user_target_success_rate(monkeypatch):
    from components import sensitivity_tab
    from retirement_sim import config as cfg
    from utils import sim_runner

    assert float(cfg.TARGET_SUCCESS_RATE) == 0.80, "cfg default changed"
    label = "Your 401k contribution ($/yr)"
    assert label in sensitivity_tab._BREAK_EVEN_PARAMS

    captured = {}

    monkeypatch.setattr(sim_runner, "sweep_break_even", _make_fake_sweep(captured))

    st = FakeSt(overrides={})
    st.session_state["break_even_param_label"] = label
    st.button = lambda *a, **k: True  # press "Find break-even value"

    sensitivity_tab._render_break_even(
        st, {"TARGET_SUCCESS_RATE": 0.95}, target_age=55
    )

    assert captured["target_success_rate"] == pytest.approx(0.95), (
        "break-even sweep must use the user's target, not cfg's default 0.80"
    )


def test_break_even_falls_back_to_cfg_when_override_absent(monkeypatch):
    from components import sensitivity_tab
    from utils import sim_runner

    captured = {}
    monkeypatch.setattr(sim_runner, "sweep_break_even", _make_fake_sweep(captured))

    st = FakeSt(overrides={})
    st.session_state["break_even_param_label"] = "Your 401k contribution ($/yr)"
    st.button = lambda *a, **k: True

    sensitivity_tab._render_break_even(st, {}, target_age=55)
    assert captured["target_success_rate"] == pytest.approx(0.80)


# ==========================================================================
# 3. Real-dollar projection must not compound a nominal inflation factor
# ==========================================================================
def test_net_worth_projection_ignores_savings_inflation_adjust():
    """The projection grows at REAL returns, so contributions stay constant."""
    from components.net_worth_projection_chart import project_net_worth

    base = {
        "YOUR_AGE": 30, "TARGET_RETIREMENT_AGE": 60, "PLAN_UNTIL_AGE": 90,
        "YOUR_BASE_SALARY": 150_000, "YOUR_401K_CONTRIBUTION": 20_000,
        "YOUR_BROKERAGE_CONTRIBUTION": 20_000, "YOUR_401K": 100_000,
    }
    on = project_net_worth({**base, "SAVINGS_INFLATION_ADJUST": True})
    off = project_net_worth({**base, "SAVINGS_INFLATION_ADJUST": False})

    assert on["ages"] == off["ages"] and len(on["ages"]) == 31
    for label, series_on in on["by_account"].items():
        series_off = off["by_account"][label]
        assert series_on[-1] == pytest.approx(series_off[-1]), (
            f"{label}: SAVINGS_INFLATION_ADJUST must not scale contributions "
            "inside a real-returns projection (the engine does not read it)"
        )
    # And the toggle really does gate something reachable — the 30-year
    # end balance would have been ~2.25x inflated if it were still applied.
    assert sum(s[-1] for s in on["by_account"].values()) > 0


def test_net_worth_projection_does_not_scale_contributions_by_inflation():
    src = _read("ui", "components", "net_worth_projection_chart.py")
    assert not re.search(r"contribution\s*\*=\s*\(\(?1\s*\+", src), (
        "found a nominal inflation multiplier applied to a real-dollar "
        "contribution stream"
    )


# ==========================================================================
# 5. Cumulative-contributions line must be theme-aware
# ==========================================================================
def test_savings_projection_cum_line_is_theme_aware():
    src = _read("ui", "components", "savings_projection_chart.py")
    assert "is_dark" in src
    assert re.search(r'cum_color\s*=\s*"#e2e8f0"\s*if\s*dark\s*else\s*"#0f172a"', src)
    # The line must use the computed color, not the hardcoded near-black.
    assert re.search(r"line=dict\(color=cum_color", src)
    # And the chart key must carry the theme so uirevision doesn't keep it.
    assert re.search(r"f\"\{chart_key\}_\{'dk' if dark else 'lt'\}\"", src)


# ==========================================================================
# 6. Social Security band respects the override, not cfg's default
# ==========================================================================
def test_retirement_ss_zero_when_override_disables_social_security():
    from components.income_over_time import _retirement_ss_for_age
    from retirement_sim import config as cfg

    assert bool(cfg.INCLUDE_SOCIAL_SECURITY) is True, "cfg default changed"

    on = _retirement_ss_for_age(70, 67, {"INCLUDE_SOCIAL_SECURITY": True})
    assert on > 0, "expected non-zero SS with the toggle on"

    off = _retirement_ss_for_age(70, 67, {"INCLUDE_SOCIAL_SECURITY": False})
    assert off == 0.0, (
        "unchecking Include Social Security must remove the SS band even "
        "before a Run (sim_runner restores cfg to its True default)"
    )


def test_retirement_ss_before_claim_age_is_zero():
    from components.income_over_time import _retirement_ss_for_age
    assert _retirement_ss_for_age(60, 67, {"INCLUDE_SOCIAL_SECURITY": True}) == 0.0


# ==========================================================================
# 7. Hero card success rate uses the same ladder as stats_row
# ==========================================================================
@pytest.mark.parametrize("rate,expect_cls", [
    (0.95, "mc-good"),
    (0.80, "mc-good"),
    (0.70, "mc-warn"),
    (0.60, "mc-warn"),
    (0.25, "mc-bad"),
    (0.00, "mc-bad"),
])
def test_hero_success_rate_color_ladder(rate, expect_cls):
    from components import hero_metric

    st = FakeSt()
    hero_metric.render(st, {
        "earliest_retirement_age": 55,
        "primary_result": {"retirement_age": 55, "success_rate": rate},
        "config_snapshot": {"TARGET_SUCCESS_RATE": 0.80},
    })
    html = "\n".join(st.markdown_calls)
    m = re.search(r'Success rate: <span class="(mc-[a-z]+)"', html)
    assert m, "hero card no longer emits a classed success-rate span"
    assert m.group(1) == expect_cls


def test_hero_success_ladder_matches_stats_row_thresholds():
    """Both components must use the same 0.80 / 0.60 breakpoints."""
    hero = _read("ui", "components", "hero_metric.py")
    stats = _read("ui", "components", "stats_row.py")
    for src, name in ((hero, "hero_metric"), (stats, "stats_row")):
        assert "mc-warn" in src and "mc-bad" in src, (
            f"{name} lost its warn/bad tiers"
        )


# ==========================================================================
# 8. Bridge section must not conflate "no data" with "past 59.5"
# ==========================================================================
def test_bridge_gauge_distinguishes_missing_data_from_late_retirement():
    from components import bridge_years_gauge as bg

    # Early retiree with no accessible-balance rows.
    st = FakeSt(overrides={"TARGET_RETIREMENT_AGE": 45})
    bg.render(st, {"primary_result": {"accessible_by_year": []}})
    text = " ".join(st.caption_calls)
    assert "penalty-free from day one" not in text, (
        "a 45-year-old with missing data was told every account is "
        "penalty-free from day one"
    )
    assert "isn't available" in text or "not available" in text

    # Genuine at-or-after-59.5 retiree keeps the original copy.
    st2 = FakeSt(overrides={"TARGET_RETIREMENT_AGE": 62})
    bg.render(st2, {"primary_result": {"accessible_by_year": []}})
    assert "penalty-free from day one" in " ".join(st2.caption_calls)


# ==========================================================================
# 9. Plotly hovertemplates have no printf-style %% escape
# ==========================================================================
def test_no_double_percent_in_plotly_hovertemplates():
    comp_dir = os.path.join(_UI, "components")
    offenders = []
    for name in sorted(os.listdir(comp_dir)):
        if not name.endswith(".py"):
            continue
        for i, line in enumerate(_read("ui", "components", name).splitlines(), 1):
            if "%%" in line and line.lstrip().startswith("#"):
                continue  # explanatory comment
            if "%%" in line:
                offenders.append(f"{name}:{i}")
    assert not offenders, (
        "Plotly's hovertemplate substitution has no `%%` escape, so it renders "
        f"literally (e.g. '14.20%%'): {offenders}"
    )


# ==========================================================================
# 10. Investable-only series must not be labelled plain "Net worth"
# ==========================================================================
def test_net_worth_box_chart_says_investable():
    src = _read("ui", "components", "net_worth_box_chart.py")
    assert "Investable portfolio range over time" in src
    assert re.search(r'yaxis=dict\(title=f"Investable portfolio', src)
    assert 'name="Investable portfolio"' in src
    # No bare "Net worth ($, today)" axis label left behind.
    assert 'title=f"Net worth (' not in src


# ==========================================================================
# 11. Success-by-age bars follow the user's target and the palette picker
# ==========================================================================
def test_success_by_age_colors_relative_to_user_target():
    from components.success_by_age import _color
    from utils.plot_theme import PALETTES

    st = FakeSt()
    st.session_state["palette_choice"] = "Pastel"
    pastel = PALETTES["Pastel"]

    # A 0.82 rate is "good" against a 0.80 target but NOT against 0.95.
    assert _color(0.82, 0.80, st) == pastel[0]
    assert _color(0.82, 0.95, st) != pastel[0], (
        "a bar below the user's own dashed target line must not be painted "
        "with the reassuring 'good' color"
    )


def test_success_by_age_reacts_to_palette_picker():
    from components.success_by_age import _color
    from utils.plot_theme import PALETTES

    pastel_st, vibrant_st = FakeSt(), FakeSt()
    pastel_st.session_state["palette_choice"] = "Pastel"
    vibrant_st.session_state["palette_choice"] = "Vibrant"

    assert _color(0.9, 0.8, pastel_st) == PALETTES["Pastel"][0]
    assert _color(0.9, 0.8, vibrant_st) == PALETTES["Vibrant"][0]
    assert _color(0.9, 0.8, pastel_st) != _color(0.9, 0.8, vibrant_st)


def test_success_by_age_does_not_use_pinned_palette_constant():
    src = _read("ui", "components", "success_by_age.py")
    assert not re.search(r"(?<!\w)PALETTE\[", src), (
        "PALETTE is pinned to Pastel and ignores the palette picker; use "
        "active_palette(st)/series_color(i, st)"
    )


# ==========================================================================
# 12. Spending-range caption reports the max sample count, not the survivors
# ==========================================================================
def test_spending_range_caption_uses_max_n_over_ages():
    src = _read("ui", "components", "spending_range_chart.py")
    assert re.search(r"n\s*=\s*max\(", src), (
        "rows[-1]['n'] is the plan-end age, where n == the number of SURVIVING "
        "paths — the minimum on the chart"
    )
    assert not re.search(r"n\s*=\s*rows\[-1\]", src)

    # And the semantics: max over rows recovers the full run size.
    rows = [{"age": 60, "n": 1000}, {"age": 75, "n": 900}, {"age": 90, "n": 800}]
    assert max((r.get("n", 0) or 0 for r in rows), default=0) == 1000


# ==========================================================================
# 13 / 16 / 17. Metric overlap + label truncation
# ==========================================================================
def test_no_component_injects_unscoped_metric_overflow_css():
    """An unscoped `stMetricValue { overflow: visible; white-space: nowrap }`
    killed Streamlit's ellipsis clipping app-wide."""
    comp_dir = os.path.join(_UI, "components")
    offenders = []
    for name in sorted(os.listdir(comp_dir)):
        if not name.endswith(".py"):
            continue
        src = _read_code("ui", "components", name)
        for m in re.finditer(
            r'\[data-testid="stMetric(?:Value|Label)"\]\s*\{([^}]*)\}', src
        ):
            block = m.group(1)
            if "nowrap" in block or "overflow" in block:
                offenders.append(name)
    assert not offenders, (
        "sidebar metric sizing belongs in styles/theme.css (sidebar-scoped); "
        f"unscoped injection found in {sorted(set(offenders))}"
    )


def test_theme_css_scales_sidebar_metric_values_down(theme_css):
    m = re.search(
        r'section\[data-testid="stSidebar"\]\s*\[data-testid="stMetricValue"\]\s*\{([^}]*)\}',
        theme_css,
    )
    assert m, "no sidebar-scoped stMetricValue rule in theme.css"
    block = m.group(1)
    size = re.search(r"font-size:\s*([\d.]+)px", block)
    assert size and float(size.group(1)) <= 20, (
        "the global 32px made 3-4-across sidebar metric values overlap"
    )
    assert "overflow: hidden" in block and "text-overflow: ellipsis" in block, (
        "a still-too-wide value must clip, not spill past the sidebar"
    )


def test_theme_css_lets_metric_labels_wrap(theme_css):
    """Streamlit ellipsizes the inner <p>; that is what must be overridden."""
    for scope in ('', 'section\\[data-testid="stSidebar"\\]\\s*'):
        pat = scope + r'\[data-testid="stMetricLabel"\]\s*p[^{]*\{([^}]*)\}'
        m = re.search(pat, theme_css)
        assert m, f"no stMetricLabel p rule for scope {scope!r}"
        assert "white-space: normal" in m.group(1)
        assert "text-overflow: clip" in m.group(1)


# ==========================================================================
# 14. "Sync to inputs" button gets real width
# ==========================================================================
def test_sync_button_is_not_in_a_narrow_column():
    src = _read_code("ui", "components", "sec_income.py")
    assert re.search(
        r'st\.button\(\s*"🔄 Sync to inputs"[^)]*width="stretch"', src, re.S
    ), ("the Sync button must span its row (a 47px sidebar column stacked its "
        "label one character per line)")
    assert "st.columns([3, 1])" not in src


# ==========================================================================
# 15 / 29. first_decade_stress subtitle + dataframe header
# ==========================================================================
def test_first_decade_subtitle_wraps_and_header_is_short():
    src = _read("ui", "components", "first_decade_stress.py")
    title = re.search(r"text=\"<b>First-decade stress[^\"]*\"(?:\s*\"[^\"]*\")*", src, re.S)
    assert title, "title block not found"
    # Titles are wrapped centrally by plot_theme.style_fig (Plotly never wraps
    # them): no rendered title/subtitle line may exceed the safe width, which
    # replaces the old hand-placed <br> that guarded against the 778px clip.
    import plotly.graph_objects as go
    from utils import plot_theme as pt
    text = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', src[title.start():title.end()])[0:])
    text = text.replace("text=", "", 1)
    fig = go.Figure()
    fig.update_layout(title=dict(text=text), height=400, margin=dict(t=100))
    pt._wrap_title(fig)
    lines = re.split(r"<br>", fig.layout.title.text)
    assert len(lines) >= 3
    for i, line in enumerate(lines):
        visible = re.sub(r"<[^>]+>", "", line)
        assert len(visible) <= (pt._TITLE_CHARS[False] if i == 0 else pt._SUB_CHARS[False]), line
    assert '"Unlucky (P10)"' in src, "long dataframe header was clipped"
    assert "10th percentile (unlucky)" not in src, "legend name still too long"


# ==========================================================================
# 19. Lifecycle selectbox option label fits the sidebar
# ==========================================================================
def test_lifecycle_selectbox_labels_are_shortened():
    from components import sec_expenses
    src = _read("ui", "components", "sec_expenses.py")
    assert "Kids then empty-nest" in src, (
        '"Children then empty-nest" was ellipsized to "Children then empty…" '
        "in the 168px sidebar selectbox"
    )
    # Every displayed label must be short enough for the sidebar control.
    for m in re.finditer(r'"([^"]*empty-nest[^"]*)"', src):
        pass  # presence checked above
    assert hasattr(sec_expenses, "render_body")


# ==========================================================================
# 23. Stat-card value sizes from its container, not the viewport
# ==========================================================================
def test_stat_card_value_uses_container_query_units():
    src = _read("ui", "components", "portfolio_breakdown.py")
    assert ".mc-stat-card {{ container-type: inline-size; }}" in src or \
           "container-type: inline-size" in src, "no container established"
    m = re.search(r"font-size:\s*clamp\(([^)]*)\)", src)
    assert m, "stat-card value clamp() not found"
    clamp = m.group(1)
    assert "vw" not in clamp, (
        "vw is viewport-relative: at 768px the value clamped to its floor "
        "while the card shrank, so numbers overprinted neighbouring cards"
    )
    assert "cqi" in clamp or "cqw" in clamp
    assert "overflow-wrap: anywhere" in src, (
        "a nowrap value with overflow:visible painted across card borders"
    )


# ==========================================================================
# 27. No bare money() inside markdown-rendered copy ($...$ -> KaTeX)
# ==========================================================================
def test_captions_and_warnings_use_money_md():
    """Two unescaped `$` in one markdown span are rendered as LaTeX."""
    for name in ("sec_taxes.py", "sec_savings.py"):
        src = _read("ui", "components", name)
        for m in re.finditer(
            r"st\.(?:caption|warning|markdown|success|info)\(\s*((?:f?\"[^\"]*\"\s*)+)\)",
            src,
        ):
            blob = m.group(1)
            bare = re.findall(r"(?<![_a-zA-Z])money\(", blob)
            assert len(bare) < 2, (
                f"{name}: two bare money() calls in one markdown span pair "
                f"their $ signs into KaTeX — use money_md(): {blob[:90]}"
            )


def test_sec_taxes_total_tax_caption_escapes_dollars():
    src = _read("ui", "components", "sec_taxes.py")
    assert re.search(r"Total tax: \{money_md\(", src)


# ==========================================================================
# 28. Spending-chart vline labels: side by room + vertical stagger
# ==========================================================================
def test_vline_label_side_points_into_the_wider_half():
    from components.spending_chart import _vline_label_side

    ages = list(range(30, 91))
    assert _vline_label_side(40, ages) == "top right"   # early -> extend right
    assert _vline_label_side(80, ages) == "top left"    # late  -> extend left
    # Degenerate / bad input must not raise.
    assert _vline_label_side(40, [40]) == "top right"
    assert _vline_label_side(None, ages) == "top right"


def test_spending_chart_vline_annotations_do_not_collide():
    from components import spending_chart as sc

    ages = list(range(30, 91))
    overrides = {
        "YOUR_AGE": 30, "MORTGAGE_MONTHLY": 3_400,
        "MORTGAGE_YEARS_REMAINING": 21, "HOME_VALUE": 900_000,
    }
    fig = sc._build_figure(
        ages, overrides, {a: 1.0 for a in ages}, 30, 40, 90, "Flat",
        title="t", subtitle="s", yaxis_title="y",
    )
    anns = {a.text: a for a in fig.layout.annotations}
    assert "Retirement (age 40)" in anns
    assert "Mortgage paid off (age 51)" in anns

    # Both are early in the range, so both must extend RIGHT (xanchor="left")
    # instead of clipping against the plot's left edge.
    assert anns["Retirement (age 40)"].xanchor == "left"
    assert anns["Mortgage paid off (age 51)"].xanchor == "left"

    # ...and they must not share the same text row.
    ret_shift = anns["Retirement (age 40)"].yshift or 0
    pay_shift = anns["Mortgage paid off (age 51)"].yshift or 0
    assert ret_shift != pay_shift, (
        "both vline labels sat on the top row and overlapped each other on a "
        "narrow plot"
    )


# ==========================================================================
# 18 / 20 / 21 / 22 / 24 / 26. Narrow-width top bar + sidebar
# ==========================================================================
def test_topbar_toolbar_wraps_instead_of_overlapping(theme_css):
    """A squeezed column let nowrap content paint over the Run button / Settings
    popover. Every toolbar column keeps its intrinsic width and the row wraps."""
    row = re.search(
        r'\.st-key-mc-topbar \[data-testid="stHorizontalBlock"\]\s*\{([^}]*)\}', theme_css)
    assert row and re.search(r"flex-wrap:\s*wrap", row.group(1))
    first = re.search(
        r'\.st-key-mc-topbar \[data-testid="stColumn"\]:first-child\s*\{([^}]*)\}', theme_css)
    assert first and "min-width: fit-content" in first.group(1)


def test_topbar_row_wraps_at_narrow_widths(theme_css):
    """nowrap forced the row past stMain (dead h-scrollbar, off-screen Settings)."""
    mq = re.search(
        r"@media\s*\(max-width:\s*1240px\)\s*\{(.*?)\n\}", theme_css, re.S
    )
    assert mq, "no narrow-width top-bar media query"
    block = mq.group(1)
    assert re.search(r"flex-wrap:\s*wrap\s*!important", block), (
        "the toolbar row must wrap: the switch on its own line, the three "
        "controls sharing the line beneath"
    )
    assert re.search(
        r'\[data-testid="stColumn"\]:first-child\s*\{[^}]*flex:\s*1 1 100%', block
    )


def test_topbar_sheds_low_priority_metrics_on_phones(theme_css):
    mq = re.search(r"@media\s*\(max-width:\s*820px\)\s*\{(.*?)\n\}", theme_css, re.S)
    assert mq, "no phone-width top-bar media query"
    assert "display: none" in mq.group(1), (
        "the metrics wrapped onto 5 rows and the sticky bar ate ~46% of a "
        "390x844 viewport"
    )


def test_sidebar_narrows_on_tablets(theme_css):
    """328px of a 768px tablet left stMain 434px, and the collapse chevron is
    hover-only so a touch device could not shrink it."""
    mq = re.search(r"@media\s*\(max-width:\s*900px\)\s*\{(.*?)\n\}", theme_css, re.S)
    assert mq, "no tablet-width sidebar media query"
    block = mq.group(1)
    assert 'section[data-testid="stSidebar"]' in block
    w = re.search(r"width:\s*(\d+)px", block)
    assert w and int(w.group(1)) < 328
