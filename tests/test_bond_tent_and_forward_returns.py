"""Bond tent glide path and the forward-looking return scenario.

The tent ramps from the working mix down to the retirement mix over the years
before retirement, then climbs to the end mix. "Ease into bonds" (the default
shape) is unchanged. The forward-looking scenario carries its own stock-bond
correlation, which applies only while it is active.
"""
import os
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from tests.test_investments_section import _couple, _draw  # noqa: E402


@pytest.fixture
def glide(monkeypatch):
    for k, v in {"GLIDE_PATH_ENABLED": True, "STOCK_ALLOCATION": 1.0, "BOND_ALLOCATION": 0.0,
                 "GLIDE_PATH_START_STOCK_PCT": 0.6, "GLIDE_PATH_END_STOCK_PCT": 1.0,
                 "GLIDE_PATH_END_AGE": 75, "GLIDE_PATH_TENT_RAMP_YEARS": 5,
                 "GLIDE_PATH_TENT_RISE_YEARS": 10}.items():
        monkeypatch.setattr(cfg, k, v)
    return monkeypatch


def _stocks(ages, retire=40):
    return [round(cfg.calculate_asset_allocation(a, retire)[0], 4) for a in ages]


def test_tent_ramps_down_before_retirement_and_climbs_after(glide):
    glide.setattr(cfg, "GLIDE_PATH_SHAPE", "tent")
    assert _stocks(range(33, 41)) == [1.0, 1.0, 1.0, 0.92, 0.84, 0.76, 0.68, 0.6]
    assert _stocks([45, 50, 60, 90]) == [0.8, 1.0, 1.0, 1.0]
    s, b = cfg.calculate_asset_allocation(43, 40)
    assert s + b == pytest.approx(1.0)


def test_tent_with_no_ramp_or_rise_steps_at_the_edges(glide):
    glide.setattr(cfg, "GLIDE_PATH_SHAPE", "tent")
    glide.setattr(cfg, "GLIDE_PATH_TENT_RAMP_YEARS", 0)
    glide.setattr(cfg, "GLIDE_PATH_TENT_RISE_YEARS", 0)
    assert _stocks([39, 40, 41]) == [1.0, 1.0, 1.0]


def test_ease_into_bonds_is_unchanged(glide):
    glide.setattr(cfg, "GLIDE_PATH_SHAPE", "down")
    glide.setattr(cfg, "GLIDE_PATH_END_STOCK_PCT", 0.6)
    glide.setattr(cfg, "GLIDE_PATH_START_STOCK_PCT", 0.8)
    assert _stocks([30, 39]) == [1.0, 1.0]              # working mix until retirement
    assert _stocks([40, 75, 90]) == [0.8, 0.6, 0.6]


def test_forward_scenario_sets_and_restores_its_correlation():
    from utils import sim_runner as sr
    before = cfg.STOCK_BOND_CORRELATION
    seen = {}
    real = sr._recompute_derived

    def spy(original):
        real(original)
        seen["rho"] = cfg.STOCK_BOND_CORRELATION
        seen["mean"] = cfg.EXPECTED_STOCK_RETURN
    sr._recompute_derived = spy
    try:
        orig = sr._apply_overrides({"ACTIVE_RETURN_SCENARIO": "forward"})
        sr._restore_overrides(orig)
    finally:
        sr._recompute_derived = real
    assert seen == {"rho": 0.10, "mean": 0.051}
    assert cfg.STOCK_BOND_CORRELATION == before


def test_forward_scenario_geometric_rate_matches_the_forecast():
    p = cfg.get_return_parameters("forward")
    g = cfg.geometric_portfolio_return(1.0, p["stock_return"], p["bond_return"],
                                       p["stock_volatility"], p["bond_volatility"],
                                       p["stock_bond_correlation"])
    assert g == pytest.approx(0.039, abs=0.0005)        # the forecasts' 3.9% real


def test_tent_choice_shows_climb_years_and_reaches_the_overrides(monkeypatch):
    at = _draw(monkeypatch, "investments", _couple(GLIDE_PATH_ENABLED=True))
    assert not [s for s in at.slider if s.key == "sa_tent_years"]
    at.radio(key="sa_glide_shape").set_value("Bond tent").run()
    assert not at.exception, at.exception
    assert [s for s in at.slider if s.key == "sa_tent_years"]
    ov = at.session_state["user_overrides"]
    assert ov["GLIDE_PATH_SHAPE"] == "tent" and ov["GLIDE_PATH_TENT_RISE_YEARS"] == 10


def test_forward_looking_choice_reaches_the_overrides(monkeypatch):
    at = _draw(monkeypatch, "investments", _couple(ACTIVE_RETURN_SCENARIO="historical"))
    at.radio(key="sa_scenario").set_value("Forward-looking").run()
    assert not at.exception, at.exception
    assert at.session_state["user_overrides"]["ACTIVE_RETURN_SCENARIO"] == "forward"
