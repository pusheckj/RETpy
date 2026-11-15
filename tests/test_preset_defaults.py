"""A preset (or any overrides dict) run directly gives the same plan as after the side panel.

The side panel writes a value for every input it draws: the expense boxes, the
employer match, Auto-allocate's contribution amounts, the partner's retirement /
plan-until / claim ages. Overrides that never went through it (a preset, a test, a
tool) used to simulate the config's sample values for those instead.
``config_builder.sidebar_defaults`` now fills them, with the panel's own helpers.

These tests compare what reaches the engine: ``build_config_overrides(preset)`` against
``build_config_overrides(preset after the side panel drew it)``.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PATHS = 12


def _same_engine_inputs(a_overrides, b_overrides):
    """What reaches cfg for each of two overrides dicts, over the same keys: a key only
    one side writes is read from the config's own value for the other (so a key both
    leave at the config's default compares equal whether or not it is written)."""
    from retirement_sim import config as cfg
    from utils.config_builder import build_config_overrides
    a, b = build_config_overrides(a_overrides), build_config_overrides(b_overrides)
    keys = set(a) | set(b)
    return ({k: a.get(k, getattr(cfg, k, None)) for k in keys},
            {k: b.get(k, getattr(cfg, k, None)) for k in keys})


def _finals(overrides, paths=PATHS):
    """Final balances of ``paths`` seeded runs at the target age."""
    from retirement_sim import mc_parallel
    from utils import sim_runner as sr
    original = sr._apply_overrides(sr.build_config_overrides(overrides))
    try:
        return mc_parallel.sim_task((int(overrides["TARGET_RETIREMENT_AGE"]), paths, 0, 1000))["finals"]
    finally:
        sr._restore_overrides(original)


def test_every_preset_run_directly_reaches_the_engine_as_after_the_side_panel(after_side_panel):
    for name, (preset, panel) in after_side_panel.items():
        direct, drawn = _same_engine_inputs(preset, panel)
        different = {k: (direct[k], drawn[k]) for k in direct if direct[k] != drawn[k]}
        assert not different, (name, different)


def test_every_preset_run_directly_has_the_side_panels_success(after_side_panel):
    for name, (preset, panel) in after_side_panel.items():
        direct, drawn = _finals(preset), _finals(panel)
        assert direct == drawn, name
        assert sum(f > 0 for f in direct) == sum(f > 0 for f in drawn)


def test_the_presets_state_no_contributions_the_side_panel_would_replace(after_side_panel):
    """Auto-allocate stores its own amounts, so a preset in that mode carries none (they
    would be dead values); the panel's are what run."""
    from utils.derived import CONTRIBUTION_KEYS
    for name, (preset, panel) in after_side_panel.items():
        assert preset["SAVINGS_MODE"].startswith("Auto-allocate"), name
        assert not [k for k in CONTRIBUTION_KEYS if k in preset], name
        assert panel["YOUR_401K_CONTRIBUTION"] > 0 or name.startswith("Near"), name


def test_a_saved_profile_gives_the_same_results_with_or_without_the_defaults(sample_household, monkeypatch):
    """A profile saved from the side panel holds every value the defaults would fill (or
    one the engine treats the same), so filling changes nothing for it."""
    from utils import config_builder
    with_defaults = _finals(sample_household, paths=PATHS)
    monkeypatch.setattr(config_builder, "sidebar_defaults", lambda overrides: {})
    assert _finals(sample_household, paths=PATHS) == with_defaults


def test_values_that_are_there_are_never_replaced():
    from utils.config_builder import build_config_overrides
    stated = {"PARTNER_AGE": 38, "YOUR_AGE": 40, "TARGET_RETIREMENT_AGE": 55,
              "SPEND_FOOD_MONTHLY": 0, "SPEND_RENT_MONTHLY": 0, "UTILITIES_MONTHLY": 5,
              "YOUR_401K_MATCH_PCT": 0.03, "PARTNER_RETIREMENT_AGE": 62,
              "PARTNER_PLAN_UNTIL_AGE": 99, "PARTNER_SS_CLAIM_AGE": 70, "HOME_VALUE": 0,
              "YOUR_401K_CONTRIBUTION": 1, "SAVINGS_MODE": "Auto-allocate (recommended)"}
    out = build_config_overrides(stated)
    assert all(out[k] == v for k, v in stated.items() if k != "TARGET_RETIREMENT_AGE")
    assert out["SPEND_UTILITIES_MONTHLY"] == 200 and out["UTILITIES_MONTHLY"] == 5
    # an amount is there, so Auto-allocate fills no other
    assert "YOUR_HSA_CONTRIBUTION" not in out


def test_an_empty_box_is_filled_like_a_missing_one():
    from utils.config_builder import sidebar_defaults
    assert sidebar_defaults({"YOUR_AGE": 30, "PARTNER_AGE": 0, "SPEND_FOOD_MONTHLY": None})[
        "SPEND_FOOD_MONTHLY"] == 900


def test_a_single_household_spends_nothing_for_a_partner():
    from utils.config_builder import build_config_overrides
    out = build_config_overrides({"YOUR_AGE": 30, "PARTNER_AGE": 0})
    assert out["PARTNER_OTHER_MONTHLY"] == out["PARTNER_MONTHLY_SPENDING"] == 0
    assert out["PARTNER_PLAN_UNTIL_AGE"] is None and out["PARTNER_RETIREMENT_AGE"] is None


def test_a_couple_starts_the_partner_where_the_side_panel_does():
    from utils.config_builder import sidebar_defaults
    got = sidebar_defaults({"YOUR_AGE": 40, "PARTNER_AGE": 37, "TARGET_RETIREMENT_AGE": 55,
                            "PLAN_UNTIL_AGE": 92, "SS_CLAIM_AGE": 68})
    assert got["PARTNER_RETIREMENT_AGE"] == 52        # their age the year you retire
    assert got["PARTNER_PLAN_UNTIL_AGE"] == 92 and got["PARTNER_SS_CLAIM_AGE"] == 68
    assert got["PARTNER_OTHER_MONTHLY"] == got["PARTNER_MONTHLY_SPENDING"] == 1_500


def test_a_partner_retirement_age_off_the_slider_stays_retire_together():
    from utils.config_builder import sidebar_defaults
    got = sidebar_defaults({"YOUR_AGE": 30, "PARTNER_AGE": 70, "TARGET_RETIREMENT_AGE": 99})
    assert got["PARTNER_RETIREMENT_AGE"] is None


def test_a_dict_that_does_not_say_who_is_in_the_plan_keeps_the_configs_partner():
    from utils.config_builder import sidebar_defaults
    got = sidebar_defaults({"YOUR_AGE": 40})
    for key in ("PARTNER_RETIREMENT_AGE", "PARTNER_PLAN_UNTIL_AGE", "PARTNER_SS_CLAIM_AGE",
                "PARTNER_OTHER_MONTHLY", "PARTNER_MONTHLY_SPENDING"):
        assert key not in got, key


def test_a_renter_pays_the_default_rent_and_owns_nothing():
    from utils.config_builder import build_config_overrides
    from utils.expense_categories import RENT_DEFAULT
    out = build_config_overrides({"YOUR_AGE": 30, "PARTNER_AGE": 0})
    assert out["SPEND_RENT_MONTHLY"] == RENT_DEFAULT
    assert out["HOME_VALUE"] == out["MORTGAGE_MONTHLY"] == 0
    owner = build_config_overrides({"YOUR_AGE": 30, "PARTNER_AGE": 0, "HOME_VALUE": 500_000,
                                    "MORTGAGE_MONTHLY": 2_000})
    assert owner["SPEND_RENT_MONTHLY"] == 0 and owner["HOME_VALUE"] == 500_000


def test_auto_allocate_fills_the_amounts_the_investments_section_stores(after_side_panel):
    from utils.derived import CONTRIBUTION_KEYS
    from utils.config_builder import build_config_overrides
    for name, (preset, panel) in after_side_panel.items():
        built = build_config_overrides(preset)
        assert {k: built[k] for k in CONTRIBUTION_KEYS} == {k: panel[k] for k in CONTRIBUTION_KEYS}, name


def test_other_savings_modes_keep_the_amounts_they_have():
    from utils.config_builder import build_config_overrides
    out = build_config_overrides({"YOUR_AGE": 30, "PARTNER_AGE": 0, "YOUR_BASE_SALARY": 100_000,
                                  "SAVINGS_MODE": "Manual amounts"})
    assert "YOUR_401K_CONTRIBUTION" not in out


def test_the_glide_path_starts_where_the_accumulation_mix_ends(after_side_panel):
    """One default: the side panel's glide path start is the config's, which is the
    accumulation mix (so the stock share never steps up at retirement)."""
    from retirement_sim import config as cfg
    for name, (_preset, panel) in after_side_panel.items():
        assert panel["GLIDE_PATH_START_STOCK_PCT"] == cfg.GLIDE_PATH_START_STOCK_PCT == cfg.STOCK_ALLOCATION, name
