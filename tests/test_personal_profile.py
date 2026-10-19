"""The private "My situation" profile: read from outside the repo, and optional.

profile_picker loads ~/.config/retirement-sim/my_profile.json (or whatever
RETIREMENT_SIM_PROFILE points at). Every test here points the loader at temp
files or the committed sample household, so the suite behaves the same whether
or not this machine has a personal profile.
"""
import importlib
import os
import shutil
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import components.profile_picker as picker  # noqa: E402
from components.top_bar import _resolve_names  # noqa: E402
from utils.profile_io import (  # noqa: E402
    PERSONAL_PROFILE_ENV,
    deserialize_overrides,
    personal_profile_path,
    serialize_overrides,
)
from tests.conftest import SAMPLE_HOUSEHOLD_PATH, load_sample_household  # noqa: E402

FIRST_PRESET = "Median US 25-year-old household"


def test_missing_file_means_no_entry(tmp_path):
    assert picker.load_personal_profile(str(tmp_path / "absent.json")) is None
    assert picker._load_my_situation(str(tmp_path / "absent.json")) is None


def test_label_comes_from_the_file_and_feeds_the_name_metric(tmp_path):
    path = tmp_path / "mine.json"
    shutil.copy(SAMPLE_HOUSEHOLD_PATH, path)
    label, overrides = picker.load_personal_profile(str(path))
    assert label == "Sample household (Primary & Partner)"
    assert _resolve_names(label) == "Primary & Partner"
    assert overrides == load_sample_household()
    # The label-free accessor (used by local analysis scripts) returns the dict.
    assert picker._load_my_situation(str(path)) == overrides


def test_label_defaults_when_the_file_has_none(tmp_path):
    # A plain Settings -> Save export carries no label.
    path = tmp_path / "mine.json"
    path.write_text(serialize_overrides({"YOUR_AGE": 40}), encoding="utf-8")
    label, overrides = picker.load_personal_profile(str(path))
    assert label == picker.MY_SITUATION_DEFAULT_LABEL == "My situation"
    assert overrides == {"YOUR_AGE": 40}


def test_broken_file_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "mine.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.warns(UserWarning, match="Ignoring unreadable profile"):
        assert picker.load_personal_profile(str(path)) is None


def test_label_never_leaks_into_overrides_and_round_trips():
    with open(SAMPLE_HOUSEHOLD_PATH, encoding="utf-8") as fh:
        overrides = deserialize_overrides(fh.read())
    assert "label" not in overrides
    assert deserialize_overrides(serialize_overrides(overrides)) == overrides


def test_env_var_overrides_the_default_path(monkeypatch, tmp_path):
    monkeypatch.setenv(PERSONAL_PROFILE_ENV, str(tmp_path / "elsewhere.json"))
    assert personal_profile_path() == str(tmp_path / "elsewhere.json")
    monkeypatch.delenv(PERSONAL_PROFILE_ENV)
    assert personal_profile_path() == os.path.expanduser(
        "~/.config/retirement-sim/my_profile.json")


def _reload_picker_with(path):
    old = os.environ.get(PERSONAL_PROFILE_ENV)
    os.environ[PERSONAL_PROFILE_ENV] = path
    try:
        return importlib.reload(picker)
    finally:
        if old is None:
            os.environ.pop(PERSONAL_PROFILE_ENV, None)
        else:
            os.environ[PERSONAL_PROFILE_ENV] = old


def test_picker_lists_the_personal_entry_first_only_when_present(tmp_path):
    try:
        with_file = _reload_picker_with(SAMPLE_HOUSEHOLD_PATH)
        names = list(with_file.PROFILES)
        assert names[0] == with_file.DEFAULT_PROFILE == "Sample household (Primary & Partner)"
        assert with_file.PROFILES[names[0]]["YOUR_401K"] == 250_000
        assert names[1] == FIRST_PRESET

        without = _reload_picker_with(str(tmp_path / "absent.json"))
        assert list(without.PROFILES)[0] == without.DEFAULT_PROFILE == FIRST_PRESET
        assert not any(n.startswith("My situation") for n in without.PROFILES)
        assert "Sample household (Primary & Partner)" not in without.PROFILES
    finally:
        importlib.reload(picker)  # back to this machine's real configuration


def test_hosted_app_never_offers_a_personal_profile(monkeypatch, tmp_path):
    """Even if a profile file ends up on a hosted server, visitors never see it."""
    path = tmp_path / "mine.json"
    shutil.copy(SAMPLE_HOUSEHOLD_PATH, path)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    assert picker.load_personal_profile(str(path)) is None
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    assert picker.load_personal_profile(str(path)) is not None
