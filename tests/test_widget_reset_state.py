"""Widget-reset / animation-epoch pins (state-staleness audit, 2026-08-19).

Regression pins for bugs where switching to a DIFFERENT set of inputs left
stale per-widget ``session_state`` behind:

  * The compensation ``st.data_editor`` (``si_comp_editor``) owns its own
    session_state once touched, and ``sec_income`` writes it straight back into
    ``YOUR_COMPENSATION_BY_AGE`` on every rerun. The Save/Load JSON path used to
    clear only the keys in ``DIRECT_MAPPINGS``/``DERIVED_MAPPINGS``, so loading a
    new profile silently fed the PREVIOUS profile's income table to the engine.
    The profile dropdown wildcard-deleted everything, so the two paths disagreed
    -- both now share ``reset_input_widget_state``.

  * The animation layer keeps ``__mcLastSuccess``/``__mcSeen`` on
    ``window.parent`` for the life of the browser tab. Without a reset signal, a
    profile at 85% success suppressed the celebration for a DIFFERENT profile at
    90% ("previous value already >= 80"). ``_anim_epoch`` is injected into the JS
    so it can reset that state when the inputs change.

``utils``/``components`` live under ``ui/``; add both roots to sys.path.
"""
import os
import sys


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.widget_sync import (  # noqa: E402
    DERIVED_MAPPINGS,
    DIRECT_MAPPINGS,
    reset_input_widget_state,
)


class _FakeSt:
    """Minimal stand-in for the streamlit module (session_state + no-op UI)."""

    def __init__(self):
        self.session_state = {}

    def markdown(self, *a, **k):
        pass


# --------------------------------------------------------------------------
# reset_input_widget_state — the single helper both switch paths now use
# --------------------------------------------------------------------------

def test_reset_clears_unmapped_input_widgets():
    """Keys sync can't repopulate must still be cleared, or they stay sticky."""
    st = _FakeSt()
    st.session_state.update({
        "si_comp_editor": "STALE_TABLE",
        "si_comp_customized": True,
        "le_age": 55,
        "sv_pct_your_401k": 0.42,
    })
    reset_input_widget_state(st)
    for key in ("si_comp_editor", "si_comp_customized", "le_age", "sv_pct_your_401k"):
        assert key not in st.session_state, f"{key} survived the reset"


def test_reset_clears_mapped_widgets():
    st = _FakeSt()
    mapped = list(DIRECT_MAPPINGS)[:3] + list(DERIVED_MAPPINGS)[:3]
    for key in mapped:
        st.session_state[key] = "stale"
    reset_input_widget_state(st)
    for key in mapped:
        assert key not in st.session_state, f"{key} survived the reset"


def test_reset_preserves_overrides_and_app_prefs():
    """The reset must not nuke the new overrides or the user's app settings."""
    st = _FakeSt()
    st.session_state.update({
        "user_overrides": {"YOUR_AGE": 28},
        "theme_mode": "Dark",
        "palette_choice": "Vibrant",
        "n_simulations": 5000,
    })
    reset_input_widget_state(st)
    assert st.session_state["user_overrides"] == {"YOUR_AGE": 28}
    assert st.session_state["theme_mode"] == "Dark"
    assert st.session_state["palette_choice"] == "Vibrant"
    assert st.session_state["n_simulations"] == 5000


# --------------------------------------------------------------------------
# Save/Load JSON path — the bug that fed the wrong income to the simulation
# --------------------------------------------------------------------------

def test_json_load_drops_previous_profiles_comp_table():
    from components.save_load import _apply_restored

    st = _FakeSt()
    st.session_state.update({
        "si_comp_editor": {"32": {"base": 999_999}},   # previous profile's edit
        "si_comp_customized": True,
        "le_age": 55,
        "user_overrides": {"YOUR_AGE": 55, "YOUR_401K": 111},
    })
    _apply_restored(st, {"YOUR_AGE": 28, "YOUR_401K": 50_000}, "profileB.json")

    assert "si_comp_editor" not in st.session_state
    assert "le_age" not in st.session_state
    # No comp ramp in the loaded preset -> not "customized", so sec_income
    # re-derives the table from the NEW profile's base/bonus/RSU inputs.
    assert st.session_state["si_comp_customized"] is False
    assert st.session_state["user_overrides"]["YOUR_AGE"] == 28
    assert st.session_state["results"] is None


def test_json_load_keeps_customized_when_preset_has_comp_ramp():
    from components.save_load import _apply_restored

    st = _FakeSt()
    st.session_state["si_comp_editor"] = "stale"
    _apply_restored(
        st,
        {"YOUR_AGE": 40, "YOUR_COMPENSATION_BY_AGE": {"40": {"base": 1}}},
        "p.json",
    )
    assert st.session_state["si_comp_customized"] is True


# --------------------------------------------------------------------------
# Animation epoch — lets the JS reset its window.parent-scoped state
# --------------------------------------------------------------------------

def _capture_injected_js(session_state: dict) -> str:
    """Run inject_animations with a stubbed components.html and return the JS.

    ``inject_animations`` does ``import streamlit.components.v1 as components``
    inside a try/except, so we must patch the attribute on the ALREADY-IMPORTED
    module (another test in the suite may have imported the real streamlit
    first; replacing sys.modules wholesale then silently does nothing and the
    injection is swallowed by the bare except).
    """
    import importlib

    import components.animations as anim

    captured = {}
    real_v1 = importlib.import_module("streamlit.components.v1")
    original_html = real_v1.html
    real_v1.html = lambda js, height=0, **kw: captured.setdefault("js", js)
    try:
        st = _FakeSt()
        st.session_state.update(session_state)
        anim.inject_animations(st)
    finally:
        real_v1.html = original_html
    assert "js" in captured, "inject_animations did not emit any JS"
    return captured["js"]


def test_anim_epoch_is_substituted_into_js():
    js = _capture_injected_js({"_anim_epoch": 7, "n_simulations": 5000})
    assert "__MC_EPOCH__" not in js, "epoch placeholder left unsubstituted"
    assert "var EPOCH = '7';" in js


def test_anim_epoch_defaults_when_absent():
    js = _capture_injected_js({"n_simulations": 1000})
    assert "__MC_EPOCH__" not in js
    assert "var EPOCH = '0';" in js


def test_sim_count_label_tracks_setting():
    """The paths-fan caption must state the count actually being run."""
    js = _capture_injected_js({"n_simulations": 25_000})
    assert "Simulating 25,000 futures" in js
    assert "10,000" not in js.split("fillText")[1][:80]


def test_profile_switch_bumps_epoch_and_skips_clear_cache():
    """Switching profiles signals the animation layer and leaves the LRU alone.

    The sim cache is content-keyed on (overrides, n_sims, target age), so a
    different profile misses naturally; clearing it only evicted the OTHER
    profiles, making A -> B -> A recompute from scratch.
    """
    import inspect

    import components.profile_picker as pp

    src = inspect.getsource(pp)
    assert "_anim_epoch" in src, "profile switch no longer bumps the anim epoch"
    # Strip comments — the module explains in prose WHY it doesn't clear the
    # cache, so a naive substring check would match its own rationale.
    code = "\n".join(
        line.split("#", 1)[0] for line in src.splitlines()
    )
    assert "clear_cache()" not in code, "clear_cache() reintroduced on profile switch"


# --------------------------------------------------------------------------
# Old-generation component coupling (docs previously called these "unreferenced")
# --------------------------------------------------------------------------

def test_old_gen_input_modules_are_still_load_bearing():
    """`spending_inputs` / `savings_rate_inputs` look superseded but aren't.

    Their UI halves are dead, yet the engine seam and two charts import their
    compute helpers. CLAUDE.md/rebuild_plan.md used to call them "unreferenced";
    acting on that would break the simulator. Pin the imports so a cleanup pass
    fails loudly here instead of silently at runtime.
    """
    from components.spending_inputs import (  # noqa: F401
        SPENDING_CATEGORIES,
        compute_lifecycle_multipliers,
    )
    from components.savings_rate_inputs import (  # noqa: F401
        ALLOCATION_ORDER,
        get_allocation_colors,
        year_savings,
    )

    # The spending chart must keep using the lifecycle helper. (sim_runner used
    # to as well; the engine now reads the preset itself, cfg.lifecycle_multiplier,
    # and the helper is a per-age view of that same function.)
    import components.spending_chart as spending_chart
    assert spending_chart.compute_lifecycle_multipliers is compute_lifecycle_multipliers
