"""Share of Social Security benefits paid after the trust fund runs short
(SS_PAYABLE_FRACTION from SS_PAYABLE_FROM_YEAR). Default 1.0 changes nothing."""
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


@pytest.fixture
def household(monkeypatch):
    for k, v in {"YOUR_AGE": 40, "PARTNER_AGE": 38, "YOUR_SS_MONTHLY_FRA": 3000,
                 "PARTNER_SS_MONTHLY_FRA": 2000, "PARTNER_SS_CLAIM_AGE": 67,
                 "SS_PAYABLE_FROM_YEAR": cfg.CURRENT_YEAR + 10}.items():
        monkeypatch.setattr(cfg, k, v)
    return monkeypatch


def test_default_pays_full_benefits(household):
    household.setattr(cfg, "SS_PAYABLE_FRACTION", 1.0)
    assert cfg.ss_payable_factor(90) == 1.0


def test_cut_starts_in_the_from_year(household):
    household.setattr(cfg, "SS_PAYABLE_FRACTION", 0.78)
    assert cfg.ss_payable_factor(49) == 1.0          # year before
    assert cfg.ss_payable_factor(50) == 0.78         # from year on
    full = {"you": 3000 * 12 * cfg.ss_claim_factor(67), "partner": 2000 * 12 * cfg.ss_claim_factor(67)}
    household.setattr(cfg, "MODEL_SPOUSAL_SS_BENEFIT", False)
    got = cfg.social_security_by_person(75, 67)
    assert got["you"] == pytest.approx(full["you"] * 0.78)
    assert got["partner"] == pytest.approx(full["partner"] * 0.78)


def test_single_person_is_cut_too(household):
    household.setattr(cfg, "PARTNER_AGE", 0)
    household.setattr(cfg, "SS_PAYABLE_FRACTION", 0.5)
    assert cfg.calculate_social_security(80, 67) == pytest.approx(3000 * 12 * cfg.ss_claim_factor(67) * 0.5)


def test_slider_reaches_the_overrides(monkeypatch):
    from tests.test_investments_section import _couple
    from streamlit.testing.v1 import AppTest

    def script():
        import os, sys
        sys.path[:0] = [os.environ["SSP_UI"], os.path.dirname(os.environ["SSP_UI"])]
        import streamlit as st
        from components import sec_retirement_goals
        sec_retirement_goals.render(st)

    monkeypatch.setenv("SSP_UI", _UI)
    at = AppTest.from_function(script, default_timeout=60)
    at.session_state["user_overrides"] = _couple()
    at.run()
    assert not at.exception, at.exception
    at.slider(key="rg_ss_payable").set_value(78).run()
    assert not at.exception, at.exception
    assert at.session_state["user_overrides"]["SS_PAYABLE_FRACTION"] == 0.78
