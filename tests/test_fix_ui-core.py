"""Regression pins for the ui/app.py + ui/utils/ fix pass (2026-08-22).

Each test corresponds to one verified defect that was fixed:

1. ``reset_input_widget_state`` did not clear the ``ea_*`` (early-access),
   ``bp_new_*`` (house financing), ``wifc_*`` (what-if) or ``le_*`` widget keys,
   so the Save/Load-JSON switch path let the PREVIOUS session's values be pushed
   straight back into ``user_overrides`` on the very next rerun — silently
   re-enabling strategies the loaded profile had off and re-deriving the
   engine-facing new-mortgage balance/payment from stale inputs.
2. ``derived.compute_taxes`` ignored ``YOUR_MARGINAL_TAX_RATE`` for the "Other"
   state choice (hard-coded 5%) while the engine charges that rate flat.
3. ``derived.get_limit("hsa", age)`` ignored age, dropping the 55+ catch-up.
4. ``app._run_simulation`` re-raised after reporting a failure — and it runs
   inside ``_safe_render("components.top_bar", …)``, so the whole top bar
   (Run button / sim count / Settings popover) was replaced by a placeholder.
5. ``initial_sidebar_state="expanded"`` made the sidebar cover a phone screen,
   leaving the Run button unclickable.
6. Stale results had no indicator, so the top bar mixed live-from-inputs metrics
   with the previous run's success rate.

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

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim.account_simulation import _select_state_tax_brackets  # noqa: E402
from utils import derived  # noqa: E402
from utils.widget_sync import (  # noqa: E402
    DERIVED_MAPPINGS,
    DIRECT_MAPPINGS,
    reset_input_widget_state,
)

_APP_PY = os.path.join(_UI, "app.py")


# ===========================================================================
# Fake streamlit — widgets return whatever their session_state key holds,
# which is exactly Streamlit's behaviour once a key exists.
# ===========================================================================
class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeSt:
    def __init__(self):
        self.session_state = {}
        self.warnings = []

    # --- layout / text (no-ops) --------------------------------------------
    def markdown(self, *a, **k):
        pass

    caption = markdown
    write = markdown
    divider = markdown

    def warning(self, msg, *a, **k):
        self.warnings.append(msg)

    error = warning
    success = warning
    info = warning

    def expander(self, *a, **k):
        return _Ctx()

    container = expander

    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Ctx() for _ in range(n)]

    # --- widgets ------------------------------------------------------------
    def _widget(self, *a, key=None, value=None, **k):
        if key is not None and key in self.session_state:
            return self.session_state[key]
        if key is not None:
            self.session_state[key] = value
        return value

    toggle = _widget
    checkbox = _widget
    number_input = _widget
    slider = _widget
    selectbox = _widget
    radio = _widget
    text_input = _widget


# ===========================================================================
# 1. reset_input_widget_state — both switch paths must clear the same keys
# ===========================================================================
# Widget keys inside ui/components/sec_*.py that are NOT user inputs, so they
# are legitimately absent from the reset set.
_NON_INPUT_SEC_KEYS = {
    "si_comp_sync",         # a button ("Sync to inputs")
    "sv_auto_alloc_chart",  # st.plotly_chart element key
}


def _reset_covers(key: str) -> bool:
    """True if reset_input_widget_state would delete ``key``."""
    st = _FakeSt()
    st.session_state[key] = "stale"
    reset_input_widget_state(st)
    return key not in st.session_state


@pytest.mark.parametrize("key", [
    # sec_early_access — every one of these is pushed to cfg via set_override on
    # each rerun, so a stale value re-enables a disabled strategy.
    "ea_rule55", "ea_sepp", "ea_sepp_age", "ea_sepp_rate", "ea_sepp_carveout",
    "ea_ladder", "ea_coast", "ea_coast_age",
    # sec_big_purchases — NEW_MORTGAGE_BALANCE / _MONTHLY are re-derived from
    # these, so a stale pair rewrites the loaded profile's loan and payment.
    "bp_new_home_down_pct", "bp_new_mortgage_rate", "bp_new_home_escrow_pct",
    # what-if levers plus its cached result payload
    "wifc_scenario", "wifc_stock", "wifc_spend", "wifc_savings", "wifc_fee",
    "wifc_infl", "wifc_ss", "wifc_ss_claim", "wifc_result",
    # life-expectancy card
    "le_age", "le_sex", "le_conditions",
    # previously-covered families must stay covered
    "si_comp_editor", "si_comp_customized", "sv_pct_your_401k",
])
def test_reset_clears_every_live_input_widget(key):
    assert _reset_covers(key), f"{key} survived reset_input_widget_state"


def test_every_sidebar_section_widget_key_is_cleared():
    """Guard: a NEW sec_* widget must be covered by the reset by default.

    Without this, adding a section (as sec_early_access did) silently makes its
    widgets sticky across a profile switch / JSON load.
    """
    sec_dir = os.path.join(_UI, "components")
    missed = {}
    for name in sorted(os.listdir(sec_dir)):
        if not (name.startswith("sec_") and name.endswith(".py")):
            continue
        with open(os.path.join(sec_dir, name)) as fh:
            keys = set(re.findall(r'key="([a-z0-9_]+)"', fh.read()))
        bad = sorted(k for k in keys - _NON_INPUT_SEC_KEYS if not _reset_covers(k))
        if bad:
            missed[name] = bad
    assert not missed, f"input widget keys not cleared by the reset: {missed}"


def test_reset_preserves_overrides_and_app_prefs():
    """The broader prefix sweep must not eat the new overrides or app settings."""
    st = _FakeSt()
    st.session_state.update({
        "user_overrides": {"YOUR_AGE": 28},
        "theme_mode": "Dark",
        "font_choice": "Inter",
        "palette_choice": "Vibrant",
        "n_simulations": 5000,
        "profile": "Custom (keep current values)",
        "profile_selectbox": "Custom (keep current values)",
        "pinned_scenarios": {"a": 1},
    })
    reset_input_widget_state(st)
    assert st.session_state["user_overrides"] == {"YOUR_AGE": 28}
    assert st.session_state["theme_mode"] == "Dark"
    assert st.session_state["font_choice"] == "Inter"
    assert st.session_state["palette_choice"] == "Vibrant"
    assert st.session_state["n_simulations"] == 5000
    assert st.session_state["profile_selectbox"] == "Custom (keep current values)"
    assert st.session_state["pinned_scenarios"] == {"a": 1}


def test_json_load_then_rerun_keeps_early_access_strategies_off():
    """End-to-end: load a profile with every strategy OFF, then re-render.

    Before the fix the stale ea_* widget keys survived the load and
    sec_early_access pushed them straight back into user_overrides, re-enabling
    the Rule of 55 / 72(t) / ladder / Coast FIRE the loaded plan had off.
    """
    from components.save_load import _apply_restored
    from components import sec_early_access

    st = _FakeSt()
    st.session_state.update({
        "user_overrides": {"RULE_OF_55_ENABLED": True, "SEPP_72T_ENABLED": True,
                           "ROTH_LADDER_ENABLED": True, "COAST_FIRE_ENABLED": True,
                           "SEPP_72T_CARVEOUT": 500_000},
        "ea_rule55": True, "ea_sepp": True, "ea_ladder": True, "ea_coast": True,
        "ea_sepp_carveout": 500_000,
    })

    profile_b = {"YOUR_AGE": 30, "TARGET_RETIREMENT_AGE": 55,
                 "RULE_OF_55_ENABLED": False, "SEPP_72T_ENABLED": False,
                 "ROTH_LADDER_ENABLED": False, "COAST_FIRE_ENABLED": False}
    _apply_restored(st, profile_b, "profileB.json")
    sec_early_access.render(st)          # the very next rerun

    ov = st.session_state["user_overrides"]
    for key in ("RULE_OF_55_ENABLED", "SEPP_72T_ENABLED",
                "ROTH_LADDER_ENABLED", "COAST_FIRE_ENABLED"):
        assert ov[key] is False, f"{key} was resurrected from stale widget state"
    assert "SEPP_72T_CARVEOUT" not in ov


def test_json_load_then_rerun_uses_loaded_house_financing():
    """The engine-facing new-mortgage numbers must follow the LOADED profile."""
    from components.save_load import _apply_restored

    st = _FakeSt()
    st.session_state.update({
        "user_overrides": {"NEW_HOME_VALUE": 1_500_000, "NEW_HOME_DOWN_PCT": 0.40,
                           "NEW_MORTGAGE_RATE": 0.05},
        "bp_new_home_down_pct": 40.0,
        "bp_new_mortgage_rate": 5.0,
    })
    _apply_restored(st, {"HOUSE_MOVE_ENABLED": True, "NEW_HOME_VALUE": 1_500_000,
                         "NEW_HOME_DOWN_PCT": 0.20, "NEW_MORTGAGE_RATE": 0.07,
                         "NEW_MORTGAGE_YEARS": 30}, "profileB.json")

    assert "bp_new_home_down_pct" not in st.session_state
    assert "bp_new_mortgage_rate" not in st.session_state
    fin = derived.new_home_financing(st.session_state["user_overrides"])
    assert fin["loan"] == pytest.approx(1_200_000)      # 20% down, not 40%


# ===========================================================================
# 2. compute_taxes — "Other" state must charge what the engine charges
# ===========================================================================
class TestOtherStateTax:
    def _ui_state_tax(self, rate):
        return derived.compute_taxes({
            "YOUR_BASE_SALARY": 250_000,
            "FILING_STATUS": "MFJ",
            "STATE_CHOICE": "Other",
            "YOUR_MARGINAL_TAX_RATE": rate,
        })["state"]

    def test_state_tax_tracks_the_marginal_rate_slider(self):
        assert self._ui_state_tax(0.0) == 0.0
        assert self._ui_state_tax(0.22) > self._ui_state_tax(0.05) > 0

    def test_matches_the_engine_flat_rate_model(self, monkeypatch):
        """Same taxable base × same rate as FlatRateStateTax."""
        monkeypatch.setattr(cfg, "STATE_CHOICE", "Other", raising=False)
        monkeypatch.setattr(cfg, "YOUR_MARGINAL_TAX_RATE", 0.22, raising=False)
        model = _select_state_tax_brackets()
        taxable = 250_000 - 29_200                      # MFJ standard deduction
        assert self._ui_state_tax(0.22) == pytest.approx(model.calculate_tax(taxable))

    def test_whole_percent_form_is_accepted(self):
        assert self._ui_state_tax(22.0) == pytest.approx(self._ui_state_tax(0.22))

    def test_ca_and_no_tax_paths_unchanged(self):
        """Only the "Other" branch reads the marginal-rate slider."""
        ca_lo = derived.compute_taxes({"YOUR_BASE_SALARY": 250_000, "STATE_CHOICE": "CA",
                                       "YOUR_MARGINAL_TAX_RATE": 0.0})["state"]
        ca_hi = derived.compute_taxes({"YOUR_BASE_SALARY": 250_000, "STATE_CHOICE": "CA",
                                       "YOUR_MARGINAL_TAX_RATE": 0.5})["state"]
        assert ca_lo == ca_hi == pytest.approx(15_525.26, abs=1.0)  # CA schedule
        none = derived.compute_taxes({"YOUR_BASE_SALARY": 250_000,
                                      "STATE_CHOICE": "No state tax",
                                      "YOUR_MARGINAL_TAX_RATE": 0.5})["state"]
        assert none == 0.0


# ===========================================================================
# 3. get_limit — HSA 55+ catch-up
# ===========================================================================
class TestHsaCatchup:
    def test_catchup_applies_from_55(self):
        base = derived.LIMITS_2024["hsa_family"]
        assert derived.get_limit("hsa", 54) == base
        assert derived.get_limit("hsa", 55) == base + derived.LIMITS_2024["hsa_catchup_55"]
        assert derived.get_limit("hsa", 70) == base + derived.LIMITS_2024["hsa_catchup_55"]

    def test_catchup_is_55_not_50(self):
        """HSA's catch-up age differs from 401k/IRA — don't copy the 50 rule."""
        assert derived.get_limit("hsa", 50) == derived.LIMITS_2024["hsa_family"]

    def test_individual_coverage_also_gets_it(self):
        assert (derived.get_limit("hsa", 60, family=False)
                == derived.LIMITS_2024["hsa_individual"]
                + derived.LIMITS_2024["hsa_catchup_55"])

    def test_matches_the_engine_catchup_amount(self):
        """The $1,000 catch-up must be the engine's, not an invented number."""
        engine_catchup = (cfg.get_hsa_limit(55, 2024, True)
                          - cfg.get_hsa_limit(54, 2024, True))
        assert derived.LIMITS_2024["hsa_catchup_55"] == engine_catchup

    def test_auto_allocation_fills_the_bigger_hsa_cap(self):
        alloc = derived.auto_allocate_savings(
            500_000, {"YOUR_AGE": 56, "YOUR_BASE_SALARY": 600_000})
        assert alloc["YOUR_HSA_CONTRIBUTION"] == derived.get_limit("hsa", 56)


# ===========================================================================
# 4/5/6. app.py source pins (app.py calls st.set_page_config at import time,
# so it can't be imported in a test process — pin the source instead).
# ===========================================================================
def _app_source() -> str:
    with open(_APP_PY) as fh:
        return fh.read()


def _run_simulation_source() -> str:
    src = _app_source()
    start = src.index("def _run_simulation(")
    end = src.index("\ndef ", start + 1)
    return src[start:end]


def test_run_simulation_does_not_reraise():
    """A failed run must not blow up the enclosing _safe_render('top_bar').

    Re-raising replaced the entire top bar — Run button, sim-count selector and
    the Settings popover (theme / profile / save-load) — with a placeholder, so
    there was no in-app way to change an input and retry.
    """
    body = _run_simulation_source()
    tail = body[body.index("except Exception as e:"):]
    assert not re.search(r"^\s+raise\s*$", tail, re.MULTILINE), \
        "_run_simulation re-raises again; the top bar will be wiped on failure"


def test_run_simulation_clears_state_and_progress_on_failure():
    body = _run_simulation_source()
    tail = body[body.index("except Exception as e:"):]
    for stmt in ("st.session_state.results = None",
                 "st.session_state.whatif_results = None",
                 "st.session_state.last_run_inputs_hash = None"):
        assert stmt in tail, f"failure path no longer clears state: {stmt}"
    # prog.empty() must run on BOTH paths, else the bar freezes mid-run.
    assert re.search(r"finally:\s*\n(?:\s*#.*\n)*\s*prog\.empty\(\)", body), \
        "prog.empty() is not in a finally — a failed run leaves a stuck bar"


def test_sidebar_is_not_force_expanded():
    """Phone viewports: 'expanded' overlaid a 328px sidebar on a 390px screen and
    the primary Run button could not be clicked at all."""
    assert 'initial_sidebar_state="auto"' in _app_source()
    assert 'initial_sidebar_state="expanded"' not in _app_source()


def test_stale_results_are_flagged():
    """The run fingerprint must actually drive a user-visible stale marker.

    The top bar recomputes Net worth / Income / Target age live from the sidebar
    but reads Success rate from the stored run, so an edit left the two silently
    disagreeing.
    """
    src = _app_source()
    assert "def _results_are_stale()" in src
    marker = src.index("results = st.session_state.results")
    assert "_results_are_stale()" in src[marker:marker + 2000], \
        "the main panel never checks staleness"
    assert "Your inputs changed since this simulation ran" in src


def test_stale_check_needs_two_computable_fingerprints():
    """An un-hashable override must not produce a false 'stale' nag.

    `_results_are_fresh()` returns False when a fingerprint can't be computed
    (safe for a button); the banner must require a proven MISMATCH instead.
    """
    src = _app_source()
    start = src.index("def _results_are_stale()")
    body = src[start:src.index("\ndef ", start + 1)]
    assert "last != cur" in body
    assert "last is not None and cur is not None" in body
