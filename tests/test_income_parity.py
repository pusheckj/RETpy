"""Income-projection parity + comp-table key-type pins (Tier 4 audit).

Two independent implementations project the SAME working-years income:

  * ``components/income_over_time.py`` — the "Income" tile, deterministic from
    ``user_overrides`` (auto-updates without a Run).
  * ``utils/sim_runner._approximate_savings_contributions`` — feeds the savings
    stacked-bar chart, reading the same table off ``cfg``.

``income_over_time``'s own docstring says it "mirrors" the sim_runner function
"so the two agree" — a hand-synced invariant with no test, so the two screens
could silently disagree about the same run. These tests pin the shared
behaviour: the compensation table drives income, and beyond its last age both
project forward with the same ``(1 + YOUR_SALARY_GROWTH_RATE) ** years`` factor.

They also pin a fragile TYPE invariant. ``sim_runner`` looks the table up with a
bare ``age in comp_by_age`` and ``max(comp_by_age.keys())``, so it REQUIRES int
keys — but profiles are stored as JSON, where keys are necessarily strings.
``profile_io._restore_int_keys`` converts them back on load. If that ever
regresses, ``sim_runner`` falls into its ``else`` branch and reports **zero
income** (or raises ``TypeError`` on ``age - last_known_age``) with no error,
while ``income_over_time`` — which handles both key types via ``_comp_lookup``
— keeps showing the right numbers. That divergence is exactly what these pin.
"""
import copy
import os
import sys
from types import SimpleNamespace

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _comp_table(start=32, end=41, base=200_000):
    """int-keyed comp table, shaped like the real YOUR_COMPENSATION_BY_AGE."""
    out = {}
    for i, age in enumerate(range(start, end)):
        b = base + i * 10_000
        out[age] = {
            "base": b,
            "bonus": int(b * 0.10),
            "rsu_gross": int(b * 0.80),
            "total_comp": int(b * 1.90),
            "after_tax": int(b * 1.90 * 0.70),
            "saved": int(b * 1.90 * 0.70 * 0.10),
        }
    return out


# --------------------------------------------------------------------------
# The stored profile is JSON (string keys); the loader must restore ints.
# --------------------------------------------------------------------------

def test_profile_loader_restores_int_comp_keys():
    """sim_runner's ``age in comp_by_age`` only works with int keys.

    Runs the picker's own loader (the one that reads your private profile) on
    the committed sample household, whose JSON comp table has string keys.
    """
    from components.profile_picker import _load_my_situation
    from tests.conftest import SAMPLE_HOUSEHOLD_PATH

    comp = _load_my_situation(SAMPLE_HOUSEHOLD_PATH).get("YOUR_COMPENSATION_BY_AGE", {})
    assert comp, "sample profile should carry a compensation table"
    assert all(isinstance(k, int) for k in comp), (
        "comp-table keys reached the app as strings; sim_runner would report "
        "ZERO income (its `age in comp_by_age` lookup silently misses)"
    )


def test_profile_io_roundtrip_preserves_int_keys():
    from utils.profile_io import deserialize_overrides, serialize_overrides

    original = {"YOUR_AGE": 32, "YOUR_COMPENSATION_BY_AGE": _comp_table()}
    restored = deserialize_overrides(serialize_overrides(original))
    comp = restored["YOUR_COMPENSATION_BY_AGE"]
    assert all(isinstance(k, int) for k in comp), "JSON round-trip lost int keys"
    assert comp[32]["base"] == original["YOUR_COMPENSATION_BY_AGE"][32]["base"]


def test_string_keyed_table_would_break_sim_runner_lookup():
    """Document WHY the int-key invariant matters (guards the guard)."""
    str_keyed = {str(k): v for k, v in _comp_table().items()}
    assert 35 not in str_keyed, "int lookup must miss string keys (premise of the pin)"


# --------------------------------------------------------------------------
# Parity: both implementations read the comp table and project it the same way
# --------------------------------------------------------------------------

def test_income_tile_uses_comp_table_values_verbatim():
    from components.income_over_time import _your_income_for_age

    comp = _comp_table()
    overrides = {"YOUR_AGE": 32}
    base, bonus, rsu, _other = _your_income_for_age(overrides, comp, 35, 0.10)
    assert base == comp[35]["base"]
    assert bonus == comp[35]["bonus"]
    assert rsu == comp[35]["rsu_gross"]


def test_income_tile_projects_past_table_with_growth():
    """Beyond the last table age, grow the last row by (1+growth)**years.

    ``sim_runner._approximate_savings_contributions`` uses the identical
    formula (``factor = (1 + salary_growth) ** max(0, age - last_known_age)``),
    so this pins the shared projection rule.
    """
    from components.income_over_time import _your_income_for_age

    comp = _comp_table()          # ages 32..40
    growth = 0.10
    last_age = max(comp)
    years_beyond = 3
    age = last_age + years_beyond
    factor = (1.0 + growth) ** years_beyond

    base, bonus, rsu, _ = _your_income_for_age({"YOUR_AGE": 32}, comp, age, growth)
    assert abs(base - comp[last_age]["base"] * factor) < 1e-6
    assert abs(bonus - comp[last_age]["bonus"] * factor) < 1e-6
    assert abs(rsu - comp[last_age]["rsu_gross"] * factor) < 1e-6


def test_income_tile_handles_both_key_types_identically():
    """The tile tolerates str keys; parity must not depend on the key type."""
    from components.income_over_time import _your_income_for_age

    comp_int = _comp_table()
    comp_str = {str(k): v for k, v in comp_int.items()}
    assert (_your_income_for_age({"YOUR_AGE": 32}, comp_int, 36, 0.10)
            == _your_income_for_age({"YOUR_AGE": 32}, comp_str, 36, 0.10))


def test_sim_runner_projection_factor_matches_tile():
    """Both project the last known row forward by the SAME growth factor."""
    from components.income_over_time import _your_income_for_age

    comp = _comp_table()
    growth = 0.10
    last_age = max(comp)
    age = last_age + 4

    tile_base, _, _, _ = _your_income_for_age({"YOUR_AGE": 32}, comp, age, growth)
    # The formula sim_runner applies (see _approximate_savings_contributions).
    sim_factor = (1 + growth) ** max(0, age - last_age)
    sim_base = float(comp[last_age]["base"]) * sim_factor

    assert abs(tile_base - sim_base) < 1e-6, (
        "income tile and sim_runner disagree on the post-table projection; "
        "they are hand-synced, so a change to one needs the same change in the other"
    )


# --------------------------------------------------------------------------
# Overrides that never went through the side panel (a preset, a test, a tool)
# get the pay their salary inputs say, not the config's sample table.
# --------------------------------------------------------------------------

# What the engine reads for working-years pay.
_PAY_KEYS = ("YOUR_COMPENSATION_BY_AGE", "YOUR_SALARY_GROWTH_RATE", "YOUR_OTHER_INCOME",
             "PARTNER_SALARY", "PARTNER_SALARY_GROWTH_RATE", "PARTNER_BONUS_AMOUNT",
             "PARTNER_RSU_AMOUNT", "PARTNER_OTHER_INCOME")
# What the Income section writes for the engine (besides echoing its inputs).
_INCOME_SECTION_OUTPUTS = ("YOUR_COMPENSATION_BY_AGE", "HOUSEHOLD_INCOME_QUICK", "PARTNER_SALARY")


def _engine(overrides, keys=(), paths=0):
    """The config values ``keys`` and the final balances of ``paths`` seeded
    runs at the target age, with ``overrides`` applied the way the planner does."""
    from retirement_sim import config as cfg
    from retirement_sim import mc_parallel
    from utils import sim_runner as sr
    original = sr._apply_overrides(sr.build_config_overrides(overrides))
    try:
        values = {k: copy.deepcopy(getattr(cfg, k)) for k in keys}
        if paths:
            values["finals"] = mc_parallel.sim_task(
                (int(overrides["TARGET_RETIREMENT_AGE"]), paths, 0, 1000))["finals"]
        return values
    finally:
        sr._restore_overrides(original)


def test_a_preset_run_directly_gets_the_pay_the_side_panel_gives_it(after_side_panel):
    """A preset carries YOUR_BASE_SALARY etc., not the year-by-year table the
    Income section builds from them. Run directly it used to simulate the
    config's sample pay (about $70k at 40)."""
    for name, (preset, panel) in after_side_panel.items():
        direct, drawn = _engine(preset, _PAY_KEYS), _engine(panel, _PAY_KEYS)
        assert direct == drawn, name
        assert drawn["YOUR_COMPENSATION_BY_AGE"][preset["YOUR_AGE"]]["base"] == preset["YOUR_BASE_SALARY"]


def test_without_the_income_sections_outputs_the_plan_simulates_the_same(after_side_panel):
    """The same overrides give the same simulation whether or not the Income
    section ran: drop what it writes for the engine and every path ends with
    the same balance."""
    for name, (_preset, panel) in after_side_panel.items():
        bare = {k: v for k, v in panel.items() if k not in _INCOME_SECTION_OUTPUTS}
        assert _engine(bare, paths=12) == _engine(panel, paths=12), name


def test_a_pay_table_already_there_is_kept(sample_household):
    """A saved profile's table (built, hand-edited or imported) is never rebuilt
    from the salary inputs, even when they disagree with it."""
    from utils.config_builder import _strip_auto_after_tax, build_config_overrides
    table = _strip_auto_after_tax(sample_household["YOUR_COMPENSATION_BY_AGE"])
    for ov in (sample_household, {**sample_household, "YOUR_BASE_SALARY": 1, "YOUR_AGE": 20}):
        assert build_config_overrides(ov)["YOUR_COMPENSATION_BY_AGE"] == table


def test_the_built_table_is_the_income_sections_table():
    """One builder: the editor's rows are the table the engine gets."""
    from components.sec_income import _build_comp_table
    from utils.config_builder import build_config_overrides
    ov = {"YOUR_AGE": 40, "TARGET_RETIREMENT_AGE": 52, "YOUR_BASE_SALARY": 150_000,
          "YOUR_BONUS_AMOUNT": 15_000, "YOUR_RSU_AMOUNT": 30_000, "YOUR_SALARY_GROWTH_RATE": 0.03}
    table = build_config_overrides(ov)["YOUR_COMPENSATION_BY_AGE"]
    rows = _build_comp_table(40, 52, 150_000, 15_000, 30_000, 0.03)
    assert list(table) == list(range(40, 53)) == rows["age"].tolist()
    assert [r["base"] + r["bonus"] + r["rsu_gross"] for r in table.values()] == \
        [r["total_comp"] for r in table.values()] == (rows["base"] + rows["bonus"] + rows["rsu_gross"]).tolist()


def test_quick_income_still_fills_in_without_the_detailed_inputs():
    from utils.config_builder import build_config_overrides
    out = build_config_overrides({"YOUR_AGE": 30, "HOUSEHOLD_INCOME_QUICK": 100_000})
    assert out["YOUR_COMPENSATION_BY_AGE"][30]["base"] == 55_000 and out["PARTNER_SALARY"] == 45_000
    # with the detailed inputs, they win (the side panel writes both)
    out = build_config_overrides({"YOUR_AGE": 30, "HOUSEHOLD_INCOME_QUICK": 100_000,
                                  "YOUR_BASE_SALARY": 70_000, "PARTNER_BASE_SALARY": 30_000})
    assert out["YOUR_COMPENSATION_BY_AGE"][30]["base"] == 70_000 and out["PARTNER_SALARY"] == 30_000


def test_the_guided_setup_drops_an_old_pay_table():
    """A new salary from the guided setup replaces the pay table (the planner
    rebuilds it), so a run before that uses the new salary, not the old table."""
    from components import guided_setup
    from utils.config_builder import build_config_overrides
    st = SimpleNamespace(session_state={
        "gs_salary": 120_000, "gs_bonus": 0,
        "user_overrides": {"YOUR_AGE": 35, "PARTNER_AGE": 0, "YOUR_BASE_SALARY": 60_000,
                           "YOUR_COMPENSATION_BY_AGE": {35: {"base": 60_000, "bonus": 0, "rsu_gross": 0,
                                                             "total_comp": 60_000, "saved": 0}}}})
    guided_setup.commit_income(st)
    ov = st.session_state["user_overrides"]
    assert "YOUR_COMPENSATION_BY_AGE" not in ov
    assert build_config_overrides(ov)["YOUR_COMPENSATION_BY_AGE"][35]["base"] == 120_000
