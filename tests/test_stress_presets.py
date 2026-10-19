"""One-click stress-test preset pins.

Presets are pure preset-authoring over EXISTING config knobs (mirrors
sensitivity_tab.py's merge-and-rerun pattern) -- these tests mock
``run_full_analysis`` to inspect exactly what gets passed, rather than
running real Monte Carlo simulations, so they stay fast and precise.

``utils``/``components`` live under ``ui/``; add both roots to sys.path.
"""
import os
import sys
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components import stress_presets  # noqa: E402


class _FakeCtx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeSt:
    def __init__(self, user_overrides=None, clicked_buttons=None):
        self.session_state = {"user_overrides": user_overrides or {}}
        self._clicked_buttons = set(clicked_buttons or [])
        self.captions = []
        self.metrics = []

    def caption(self, text, **k):
        self.captions.append(text)

    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [_FakeCtx() for _ in range(n)]

    def button(self, label, key=None, **k):
        return key in self._clicked_buttons

    def metric(self, label, value, **k):
        self.metrics.append((label, value))


def _fake_run_full_analysis(overrides, n_simulations, target_retirement_age):
    """Deterministic stand-in: echoes back what it was called with so the
    test can assert on exactly what stress_presets.py passed."""
    return {
        "earliest_retirement_age": target_retirement_age,
        "primary_result": {
            "success_rate": 0.5,
            "median_final": 1_000_000,
            "retirement_age": target_retirement_age,
        },
        "_called_with_overrides": dict(overrides),
        "_called_with_age": target_retirement_age,
    }


def test_presets_are_all_existing_config_knobs_no_target_retirement_age_key():
    """TARGET_RETIREMENT_AGE is UI-only and silently dropped -- no preset delta
    may rely on it; age changes must go through the age_offset mechanism."""
    for label, delta, age_offset in stress_presets.PRESETS:
        assert "TARGET_RETIREMENT_AGE" not in delta, label


def test_age_offset_clamped_at_your_age():
    st = _FakeSt(
        user_overrides={"YOUR_AGE": 50, "TARGET_RETIREMENT_AGE": 52},
        clicked_buttons={"stress_preset_Forced early retirement (-6 yrs)"},
    )
    with patch("utils.sim_runner.run_full_analysis", side_effect=_fake_run_full_analysis):
        stress_presets.render(st, results={"primary_result": {}})

    entry = st.session_state["stress_preset_results"]["Forced early retirement (-6 yrs)"]
    # 52 - 6 = 46, clamped up to YOUR_AGE (50) since you can't retire before
    # your current age.
    assert entry["age"] == 50
    assert entry["shocked"]["_called_with_age"] == 50
    assert entry["baseline"]["_called_with_age"] == 52


def test_forced_early_retirement_age_change_comes_from_the_parameter_not_overrides():
    st = _FakeSt(
        user_overrides={"YOUR_AGE": 30, "TARGET_RETIREMENT_AGE": 55},
        clicked_buttons={"stress_preset_Forced early retirement (-6 yrs)"},
    )
    with patch("utils.sim_runner.run_full_analysis", side_effect=_fake_run_full_analysis):
        stress_presets.render(st, results={"primary_result": {}})

    entry = st.session_state["stress_preset_results"]["Forced early retirement (-6 yrs)"]
    assert "TARGET_RETIREMENT_AGE" not in entry["shocked"]["_called_with_overrides"] or \
        entry["shocked"]["_called_with_overrides"]["TARGET_RETIREMENT_AGE"] == 55  # inert if present
    assert entry["shocked"]["_called_with_age"] == 49  # the actual retirement-age effect


def test_clicking_one_preset_only_populates_that_entry():
    st = _FakeSt(
        user_overrides={"YOUR_AGE": 30, "TARGET_RETIREMENT_AGE": 55},
        clicked_buttons={"stress_preset_Prolonged bad returns"},
    )
    with patch("utils.sim_runner.run_full_analysis", side_effect=_fake_run_full_analysis):
        stress_presets.render(st, results={"primary_result": {}})

    store = st.session_state["stress_preset_results"]
    assert list(store.keys()) == ["Prolonged bad returns"]


def test_noop_without_results():
    st = _FakeSt()
    stress_presets.render(st, results=None)
    assert "stress_preset_results" not in st.session_state
    assert any("first" in c.lower() for c in st.captions)
