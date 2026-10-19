"""Override-wiring enforcement test (root-cause guard for the inert-control class).

The UI builds a dict of config overrides via ``build_config_overrides`` and
``sim_runner._apply_overrides`` writes each key onto ``cfg`` ONLY when
``hasattr(cfg, key)``. Any key that is neither a real ``cfg`` attribute nor a
legitimately UI-only key is therefore SILENTLY DROPPED and never reaches the
Monte Carlo engine — the mechanism behind the inert-control findings (filing
status, retirement-spending mode, rent, spending-lifecycle preset, ...).

This test feeds a full saved profile (the fictional household in
tests/fixtures/sample_household.json, which carries every key a real app export
does) through ``build_config_overrides`` and asserts that every resulting key
is either UI-only or a real ``cfg`` attribute. It is EXPECTED TO FAIL until the
individual inert-control findings are fixed, and the failure message lists the
exact dropped keys so each can be wired up.

sim_runner imports ``from retirement_sim import config`` and
``from utils.config_builder import build_config_overrides``. ``retirement_sim``
is importable from ROOT; ``utils`` lives under ``ui/``. Add both to sys.path so
the same imports resolve under ``pytest tests/`` from ROOT.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg
from utils import sim_runner as sr
from utils.config_builder import build_config_overrides
from tests.conftest import SAMPLE_HOUSEHOLD_PATH as _PROFILE_PATH


def _load_profile_overrides() -> dict:
    with open(_PROFILE_PATH) as f:
        data = json.load(f)
    return data["overrides"]


def test_audit_helper_flags_only_true_gaps():
    """audit_override_keys ignores UI-only keys and real cfg attrs, flags the rest."""
    built = {
        "MORTGAGE_MONTHLY": 3000,          # real cfg attr -> not flagged
        "TARGET_RETIREMENT_AGE": 45,       # UI-only -> not flagged
        "TOTALLY_MADE_UP_KEY": 1,          # neither -> flagged
    }
    dropped = sr.audit_override_keys(built)
    assert "TOTALLY_MADE_UP_KEY" in dropped
    assert "MORTGAGE_MONTHLY" not in dropped
    assert "TARGET_RETIREMENT_AGE" not in dropped


def test_ui_only_keys_seeded_from_builder():
    """sim_runner's guard trusts the config_builder translation layer."""
    from utils.config_builder import _UI_ONLY_KEYS as builder_ui_only
    assert builder_ui_only <= sr.UI_ONLY_KEYS


def test_every_profile_override_key_reaches_the_engine():
    """Every built override key must be UI-only or a real cfg attribute.

    Findings #6 (SPEND_RENT_MONTHLY), #7 (RETIREMENT_SPENDING_MODE/PCT/ABSOLUTE),
    #8 (FILING_STATUS) and #11 (SPEND_LIFECYCLE_PRESET) declared these as real
    cfg attributes and wired them into the engine, so the guard now enforces
    strictly: any newly-added override key that neither maps onto cfg nor is
    UI-only fails here instead of silently no-op'ing.
    """
    overrides = _load_profile_overrides()
    built = build_config_overrides(overrides)
    dropped = sr.audit_override_keys(built)
    assert not dropped, (
        "These override keys are silently dropped by _apply_overrides "
        "(neither UI-only nor a real cfg attribute) and never reach the "
        "Monte Carlo engine:\n  " + "\n  ".join(dropped)
    )
