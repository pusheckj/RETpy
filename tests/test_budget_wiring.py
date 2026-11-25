"""The budget features' saved settings: BENCH_AREA and each child's childcare_monthly.

Both travel with Save/Load and the profile, never reach the engine as config, and never make
a finished run look stale.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from utils import budget_data as bd  # noqa: E402
from utils import config_builder, profile_io, sim_runner  # noqa: E402

SD = "San Diego-Chula Vista-Carlsbad, CA"


def test_the_area_and_childcare_survive_save_and_load():
    ov = {"BENCH_AREA": SD, "CHILDREN": [{"years_until_birth": -1, "monthly_cost": 1_000,
                                          "childcare_monthly": 1_450}]}
    back = profile_io.deserialize_overrides(profile_io.serialize_overrides(ov))
    assert back["BENCH_AREA"] == SD
    assert back["CHILDREN"][0]["childcare_monthly"] == 1_450


def test_an_older_profile_without_childcare_loads_with_none():
    back = profile_io.sanitize_overrides({"CHILDREN": [{"years_until_birth": 2, "monthly_cost": 2_100}]})
    assert cfg.children_in(back)[0]["childcare_monthly"] == 0


def test_a_garbled_area_in_a_saved_file_is_ignored_not_fatal():
    for junk in (["x"], 7, None, {"a": 1}):
        fixed = profile_io.sanitize_overrides({"BENCH_AREA": junk})
        assert bd.picked_area(fixed) is None
        assert bd.picked_area({"BENCH_AREA": junk}) is None


def test_the_area_is_not_a_config_key_and_not_part_of_the_cache_key():
    assert "BENCH_AREA" not in config_builder.build_config_overrides({"BENCH_AREA": SD, "YOUR_AGE": 40})
    a = sim_runner._hashable({"YOUR_AGE": 40, "BENCH_AREA": SD})
    b = sim_runner._hashable({"YOUR_AGE": 40})
    assert a == b
    assert "BENCH_AREA" in sim_runner.UI_ONLY_KEYS
    assert "BENCH_INCOME_GROUP" in sim_runner.UI_ONLY_KEYS
    assert sim_runner._hashable({"YOUR_AGE": 40, "BENCH_INCOME_GROUP": "Q2"}) == b
    assert "BENCH_INCOME_GROUP" not in config_builder.build_config_overrides({"BENCH_INCOME_GROUP": "Q2"})


def test_the_income_group_survives_save_and_load():
    back = profile_io.deserialize_overrides(profile_io.serialize_overrides({"BENCH_INCOME_GROUP": "Q4"}))
    assert back["BENCH_INCOME_GROUP"] == "Q4"
    assert profile_io.sanitize_overrides({"BENCH_INCOME_GROUP": ["x"]}).get("BENCH_INCOME_GROUP") in (None, "")


def test_childcare_reaches_the_engine_inside_the_children_list():
    out = config_builder.build_config_overrides(
        {"CHILDREN": [{"years_until_birth": 0, "monthly_cost": 900, "childcare_monthly": 700}]})
    assert out["CHILDREN"][0]["childcare_monthly"] == 700
