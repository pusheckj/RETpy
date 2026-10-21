"""Age is the only input; each person's birth year (which sets their SECURE 2.0
RMD start age) follows from it, so the two can never disagree."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402
from utils.sim_runner import _apply_overrides, _restore_overrides  # noqa: E402


def _derived(**overrides):
    original = _apply_overrides(build_config_overrides(overrides))
    try:
        return cfg.YOUR_BIRTH_YEAR, cfg.PARTNER_BIRTH_YEAR, cfg.RMD_START_AGE
    finally:
        _restore_overrides(original)


def test_config_defaults_follow_age():
    assert cfg.YOUR_BIRTH_YEAR == cfg.CURRENT_YEAR - cfg.YOUR_AGE
    assert cfg.PARTNER_BIRTH_YEAR == cfg.CURRENT_YEAR - cfg.PARTNER_AGE


def test_age_sets_each_persons_rmd_start_age():
    year = cfg.CURRENT_YEAR
    you, partner, rmd = _derived(YOUR_AGE=70, PARTNER_AGE=60)
    assert (you, partner) == (year - 70, year - 60)
    assert rmd == cfg.get_rmd_start_age(year - 70) == 73        # born 1951-59
    assert cfg.get_rmd_start_age(partner) == 75                  # born 1960+


def test_stale_birth_year_from_an_old_profile_is_ignored():
    year = cfg.CURRENT_YEAR
    you, partner, _ = _derived(YOUR_AGE=40, PARTNER_AGE=38, YOUR_BIRTH_YEAR=1950, PARTNER_BIRTH_YEAR=1950)
    assert (you, partner) == (year - 40, year - 38)
    assert "YOUR_BIRTH_YEAR" not in build_config_overrides({"YOUR_BIRTH_YEAR": 1950})


def test_restore_puts_the_defaults_back():
    before = (cfg.YOUR_BIRTH_YEAR, cfg.PARTNER_BIRTH_YEAR, cfg.RMD_START_AGE)
    _derived(YOUR_AGE=70)
    assert (cfg.YOUR_BIRTH_YEAR, cfg.PARTNER_BIRTH_YEAR, cfg.RMD_START_AGE) == before


def test_about_you_asks_for_age_only():
    from streamlit.testing.v1 import AppTest

    def app():
        import streamlit as st
        from components import sec_about_you
        st.session_state.setdefault("user_overrides", {"YOUR_AGE": 35, "PARTNER_AGE": 33})
        sec_about_you.render_body(st)

    at = AppTest.from_function(app, default_timeout=30).run()
    assert not at.exception
    labels = [n.label.strip() for n in at.number_input]
    assert labels == ["Age", "Age"]
    assert not any("birth" in lbl.lower() for lbl in labels)
