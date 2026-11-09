"""Freedom milestones: places, the milestone rules, saving, and the engine knob.

The logic modules (utils/places.py, utils/milestones.py) have no Streamlit, so most
tests call them directly. The last block checks the pieces that touch the engine:
the retirement-only state tax setting must leave every existing plan unchanged, and
a place must turn into settings that move spending as the quick rule says.
"""
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.conftest import load_sample_household  # noqa: E402
from utils import milestones as ms  # noqa: E402
from utils import places as pl  # noqa: E402
from utils.milestones import BEYOND, PROGRESS, REACHED  # noqa: E402


# ------------------------------------------------------------------ places

def test_built_in_places_are_generic_and_sane():
    ids = [p.id for p in pl.BUILT_IN]
    assert len(ids) == len(set(ids))
    assert ids[0] == pl.HERE_ID
    for p in pl.BUILT_IN:
        assert pl.FACTOR_MIN <= p.factor <= pl.FACTOR_MAX
        assert pl.normalize_tax(p.tax) == p.tax          # every built-in tax setting is valid
    names = {p.name for p in pl.BUILT_IN}
    assert {"Midwest", "Texas", "Portugal", "Italy", "Thailand"} <= names
    assert all(p.tax == pl.TAX_NONE for p in pl.BUILT_IN if p.abroad)


def test_untouched_state_is_not_stored():
    ov = {"YOUR_AGE": 30}
    state = pl.get_state(ov)
    pl.store(ov, state)
    assert pl.KEY not in ov                     # an untouched profile saves exactly as before


def test_get_state_survives_junk():
    for junk in (None, 5, "x", [], {"edits": 3, "custom": "no", "hidden": 7, "settings": []},
                 {"edits": {"midwest": {"factor": "abc", "tax": "US:ZZ"}, "nowhere": {"factor": 2}},
                  "custom": [{"name": ""}, 3, {"id": "c1", "name": "Ok", "factor": 99}],
                  "hidden": ["here", "texas", "bogus"]}):
        state = pl.get_state({pl.KEY: junk})
        assert set(state) == {"v", "edits", "custom", "hidden", "settings"}
        pl.resolve(state)
    state = pl.get_state({pl.KEY: junk})
    assert "nowhere" not in state["edits"]
    assert state["edits"]["midwest"]["tax"] == pl.TAX_SAME     # unknown state falls back
    assert state["custom"][0]["factor"] == pl.FACTOR_MAX        # clamped
    assert state["hidden"] == ["texas"]                         # "here" can't be hidden


def test_edit_reset_hide_and_restore():
    s = pl.empty_state()
    s = pl.with_edit(s, "midwest", factor=0.7, tax="US:TX", note="x")
    mid = pl.get_place(s, "midwest")
    assert (mid.factor, mid.tax, mid.note) == (0.7, "US:TX", "x")
    assert pl.is_edited(s, "midwest")
    base = pl.default_place("midwest")
    s = pl.with_edit(s, "midwest", factor=base.factor, tax=base.tax, note=base.note)
    assert not pl.is_edited(s, "midwest") and pl.is_empty(s)        # editing back is a reset
    s = pl.with_removed(s, "texas")
    assert pl.get_place(s, "texas") is None
    assert pl.with_removed(s, pl.HERE_ID)["hidden"] == ["texas"]    # "here" stays
    s = pl.with_restored(s)
    assert pl.get_place(s, "texas") is not None


def test_custom_places_add_edit_remove_and_limits():
    s = pl.empty_state()
    s, pid = pl.with_custom(s, "  Lisbon  ", 0.7, "none", "my note")
    assert pid == "c1"
    p = pl.get_place(s, pid)
    assert (p.name, p.factor, p.tax, p.custom) == ("Lisbon", 0.7, pl.TAX_NONE, True)
    s, pid2 = pl.with_custom(s, "Denver", 1.05, "US:CO")
    assert pid2 == "c2"
    s = pl.with_edit(s, "c1", factor=0.65)
    assert pl.get_place(s, "c1").factor == 0.65
    s = pl.with_removed(s, "c1")
    assert pl.get_place(s, "c1") is None
    s, pid3 = pl.with_custom(s, "Again")
    assert pid3 == "c1"                                             # a freed id is reused
    assert pl.with_custom(s, "   ")[1] is None                      # empty name
    full = pl.empty_state()
    for i in range(pl.MAX_CUSTOM):
        full, _ = pl.with_custom(full, f"P{i}")
    assert pl.with_custom(full, "one more")[1] is None


def test_settings_clamp_and_default_dropped():
    s = pl.with_setting(pl.empty_state(), "rate", 0.10)
    assert pl.setting(s, "rate") == pl.RATE_MAX
    s = pl.with_setting(s, "rate", pl.DEFAULT_RATE)
    assert pl.is_empty(s)
    s = pl.with_setting(s, "barista", 30_000)
    assert pl.setting(s, "barista") == 30_000


def test_tax_settings():
    assert pl.normalize_tax("US:tx") == "US:TX"
    assert pl.normalize_tax("US:ZZ") == pl.TAX_SAME
    assert pl.normalize_tax(None) == pl.TAX_SAME
    assert pl.engine_state(pl.TAX_SAME) is None
    assert pl.engine_state("US:TX") == "TX"
    assert pl.engine_state(pl.TAX_NONE) == "No state tax"
    assert "placeholder" in pl.tax_label(pl.TAX_NONE, abroad=True)
    values = [v for _, v in pl.tax_choices()]
    assert values[:2] == [pl.TAX_SAME, pl.TAX_NONE] and "US:CA" in values and len(values) >= 52


def test_places_survive_save_and_load_and_old_profiles_load_unchanged():
    from utils.profile_io import serialize_overrides, deserialize_overrides
    ov = load_sample_household()
    before = deserialize_overrides(serialize_overrides(ov))
    assert pl.KEY not in before                                     # an older profile has no key
    s = pl.with_edit(pl.get_state(ov), "midwest", factor=0.8, tax="US:IA")
    s, _ = pl.with_custom(s, "Lisbon", 0.7, "none", "note")
    s = pl.with_removed(s, "thailand")
    s = pl.with_setting(s, "rate", 0.035)
    pl.store(ov, s)
    back = deserialize_overrides(serialize_overrides(ov))
    assert pl.get_state(back) == pl.get_state(ov)
    assert [p.id for p in pl.resolve(pl.get_state(back))] == [p.id for p in pl.resolve(s)]
    assert json.loads(serialize_overrides(ov))["overrides"][pl.KEY]["custom"][0]["name"] == "Lisbon"
    # Everything else in the profile is untouched by the extra key.
    assert {k: v for k, v in back.items() if k != pl.KEY} == before


# ------------------------------------------------------------------ rules

def test_short_money():
    assert ms.short_money(250_000) == "$250K"
    assert ms.short_money(1_000_000) == "$1M"
    assert ms.short_money(1_500_000) == "$1.5M"
    assert ms.short_money(12_500) == "$12.5K"
    assert ms.short_money(850) == "$850"
    assert ms.short_money(-40_000) == "-$40K"
    assert ms.short_money(2_000_000_000) == "$2B"


def test_rungs_ascend_and_adapt():
    r = ms.rungs()
    assert r == sorted(r) and r[:7] == [10e3, 25e3, 50e3, 100e3, 250e3, 500e3, 1e6]
    shown, earlier = ms.pick_rungs(0)
    assert shown == r[:4] and earlier == 0                           # nothing yet: the first four
    shown, earlier = ms.pick_rungs(1_200_000)
    assert shown[:2] == [500e3, 1e6] and shown[2:] == [2e6, 3e6, 5e6, 1e7] and earlier == 5
    shown, earlier = ms.pick_rungs(-5_000)                           # negative net worth
    assert shown == r[:4] and earlier == 0
    shown, earlier = ms.pick_rungs(8e9)                              # past every rung
    assert all(x <= 8e9 for x in shown) and earlier >= 0


def test_track_statuses():
    ages, vals = [30, 31, 32, 33], [100, 150, 220, 300]
    assert ms.track(ages, vals, 90) == (REACHED, 30, 1.0)
    st, age, prog = ms.track(ages, vals, 200)
    assert (st, age) == (PROGRESS, 32) and prog == pytest.approx(0.5)
    st, age, prog = ms.track(ages, vals, 1000)
    assert (st, age) == (BEYOND, None) and prog == pytest.approx(0.1)
    assert ms.track([], [], 10)[0] == BEYOND
    assert ms.track(ages, vals, 0)[0] == REACHED                     # a zero target is met
    assert ms.track(ages, [-50, -20, 5, 8], 100)[2] == 0.0           # progress never below zero
    # A target that falls with age (Coast FIRE): the later age clears it.
    st, age, _ = ms.track(ages, vals, lambda a: 400 - 40 * (a - 30))
    assert (st, age) == (PROGRESS, 33)


def test_fire_and_coast_math():
    assert ms.place_spend(60_000, 12_000, 0.5) == 42_000             # health is not scaled
    assert ms.place_spend(60_000, 12_000, -1) == 12_000
    # Housing and children (core - living) can't be scaled away: 60k - 40k = 20k floor.
    assert ms.place_spend(60_000, 12_000, 0.1, living=40_000) == 32_000
    assert ms.place_spend(60_000, 12_000, 1.5, living=40_000) == 102_000
    assert ms.fire_number(40_000, 0.04) == pytest.approx(1_000_000)
    assert ms.fire_number(40_000, 0) == float("inf")
    assert ms.coast_need(1_000_000, 35, 55, 0.05) == pytest.approx(1_000_000 / 1.05 ** 20)
    assert ms.coast_need(1_000_000, 60, 55, 0.05) == 1_000_000       # past retirement age: no growth left


def _inputs(**kw):
    ages = list(range(35, 66))
    invested = [200_000 * 1.07 ** i + 40_000 * i for i in range(len(ages))]
    base = dict(your_age=35, retire_age=55, year=2026, ages=ages, invested=invested,
                home=[100_000.0] * len(ages), spend_core=60_000, living_base=40_000, health=12_000, today_spend=84_000,
                discretionary_ratio=0.30, rate=0.04, real_return=0.05, cash=30_000,
                barista_income=24_000, mortgage_years=10,
                places=(pl.default_place("here"), pl.default_place("midwest"), pl.default_place("thailand")))
    base.update(kw)
    return ms.Inputs(**base)


def test_build_report_basics():
    rep = ms.build(_inputs())
    assert [m.kind for m in rep.networth] == ["networth"] * len(rep.networth)
    here, mid, thai = rep.places
    # A cheaper place needs a smaller balance, so it arrives no later.
    assert thai.fire_number < mid.fire_number < here.fire_number
    assert thai.fire.age <= mid.fire.age <= here.fire.age
    for pr in rep.places:                                            # coast never arrives after FIRE
        if pr.fire.age is not None:
            assert pr.coast.age is not None and pr.coast.age <= pr.fire.age
    assert rep.total == len(rep.networth) + len(rep.invested) + 6 + len(rep.markers) + rep.earlier_networth + rep.earlier_invested
    assert rep.next_up is not None and rep.next_up.status == PROGRESS
    years = {m.year - m.age for m in rep.invested if m.age is not None}
    assert years == {2026 - 35}                                      # year follows from age


def test_net_worth_counts_home_equity_but_invested_does_not():
    rep = ms.build(_inputs(invested=[400_000] * 31, home=[600_000] * 31))
    assert {m.label for m in rep.networth if m.reached} >= {"$1M net worth"}
    assert "$1M invested" not in {m.label for m in rep.invested if m.reached}


def test_edge_no_money_no_partner_negative():
    ages = [40, 41, 42]
    rep = ms.build(_inputs(your_age=40, ages=ages, invested=[0.0, 0.0, 0.0], home=[0.0] * 3, cash=0))
    assert all(m.status == BEYOND for m in rep.invested)
    assert rep.next_up is None or rep.next_up.status == PROGRESS     # only the mortgage can be ahead
    rep = ms.build(_inputs(your_age=40, ages=ages, invested=[-5e4, -4e4, -3e4], home=[0.0] * 3))
    assert all(m.progress == 0.0 for m in rep.invested)


def test_edge_past_every_threshold_and_retirement_age_passed():
    ages = [60, 61, 62]
    rep = ms.build(_inputs(your_age=60, retire_age=55, ages=ages, invested=[2e8, 2e8, 2e8], home=[0.0] * 3))
    assert all(m.reached for m in rep.invested[:ms.KEEP_REACHED])
    # Retirement age already passed: Coast FIRE is the same test as FIRE.
    for pr in rep.places:
        assert pr.coast.status == pr.fire.status
    assert rep.reached > 0


def test_edge_no_spending_hides_place_tests():
    rep = ms.build(_inputs(spend_core=0, health=0))
    assert not rep.spending_known and rep.places == []
    assert all(m.key.startswith(("emergency", "mortgage")) for m in rep.markers)


def test_place_equal_to_here_changes_nothing_in_the_engine():
    here = pl.default_place("here")
    assert ms.place_overrides(here, 60_000, 40_000) == {}
    same = pl.Place("x", "Same", pl.GROUP_CUSTOM, 1.0, pl.TAX_SAME)
    assert ms.place_overrides(same, 60_000, 40_000) == {}


def test_place_overrides_scale_spending_and_set_tax():
    p = pl.Place("x", "Cheap", pl.GROUP_US, 0.5, "US:TX")
    ov = ms.place_overrides(p, spend_core=60_000, living_base=40_000)
    assert ov["RETIREMENT_SPENDING_MODE"].startswith("Absolute")
    assert ov["RETIREMENT_SPENDING_ABSOLUTE"] == 10_000              # 40k + (0.5 - 1) x 60k
    assert ov["RETIREMENT_STATE_CHOICE"] == "TX"
    far = pl.Place("y", "Far", pl.GROUP_ABROAD, 0.1, pl.TAX_NONE)
    ov = ms.place_overrides(far, 60_000, 4_000)
    assert ov["RETIREMENT_SPENDING_ABSOLUTE"] == 0.0                 # never negative
    assert ov["RETIREMENT_STATE_CHOICE"] == "No state tax"


# ------------------------------------------------------------------ the engine and the runner

def test_cache_keys_ignore_places_and_the_builder_drops_them():
    from utils import sim_runner as sr
    from utils.config_builder import build_config_overrides
    ov = load_sample_household()
    edited = dict(ov)
    pl.store(edited, pl.with_edit(pl.empty_state(), "midwest", factor=0.5))
    assert pl.KEY in edited
    assert sr._hashable(ov) == sr._hashable(edited)                  # editing a place can't make a run look stale
    assert pl.KEY not in build_config_overrides(edited)
    assert pl.KEY in sr.UI_ONLY_KEYS and sr.audit_override_keys(build_config_overrides(edited)) == []


def test_retirement_state_choice_default_leaves_results_unchanged():
    import numpy as np
    from retirement_sim import account_simulation as sim
    from retirement_sim import config as cfg
    from utils import sim_runner as sr
    from utils.config_builder import build_config_overrides
    assert cfg.RETIREMENT_STATE_CHOICE is None
    ov = build_config_overrides(load_sample_household())

    def run(extra):
        original = sr._apply_overrides({**ov, **extra})
        try:
            np.random.seed(11)
            import random
            random.seed(11)
            r = sim.run_monte_carlo_detailed(retirement_age=50, n_simulations=60, random_seed=11)
            return r["success_rate"], r["median_final"]
        finally:
            sr._restore_overrides(original)

    base = run({})
    assert run({"RETIREMENT_STATE_CHOICE": None}) == base
    # Naming the state you already live in is also the same plan.
    assert run({"RETIREMENT_STATE_CHOICE": ov.get("STATE_CHOICE", "CA")}) == base
    # A no-tax state in retirement can only help.
    assert run({"RETIREMENT_STATE_CHOICE": "No state tax"})[1] >= base[1]


def test_retirement_state_choice_reaches_only_the_retirement_tax_model():
    from retirement_sim import account_simulation as sim
    from retirement_sim import config as cfg
    from utils import sim_runner as sr
    from utils.config_builder import build_config_overrides
    ov = build_config_overrides({**load_sample_household(), "STATE_CHOICE": "CA"})
    original = sr._apply_overrides({**ov, "RETIREMENT_STATE_CHOICE": "TX"})
    try:
        pf = sim.create_initial_portfolio()
        assert pf.ca_tax_brackets.rules["code"] == "TX"
        w = cfg.working_year_taxes(300_000, 0)                       # working years still use CA
        assert w["state"] > 0
    finally:
        sr._restore_overrides(original)


def test_spending_basis_matches_what_a_place_override_does():
    from retirement_sim import config as cfg
    from utils import sim_runner as sr
    ov = load_sample_household()
    ra = int(ov["TARGET_RETIREMENT_AGE"])
    basis = sr.retirement_spending_basis(ov, ra)
    assert basis["core"] > 0 and basis["health"] > 0 and basis["living"] > 0
    for factor in (0.5, 0.88, 1.35):
        place = pl.Place("t", "T", pl.GROUP_US, factor, pl.TAX_SAME)
        po = ms.place_overrides(place, basis["core"], basis["living"])
        after = sr.retirement_spending_basis({**ov, **po}, ra)
        quick = ms.place_spend(basis["core"], 0.0, factor, basis["living"])        # the quick rule's number
        assert after["core"] == pytest.approx(quick, rel=1e-6)
        assert after["health"] == pytest.approx(basis["health"])


def test_place_check_plan_with_no_change_reproduces_the_plan():
    from utils import sim_runner as sr
    ov = load_sample_household()
    ra = int(ov["TARGET_RETIREMENT_AGE"])
    sr.clear_cache()
    res = sr.run_place_check(ov, {}, 200, ra)
    main = sr.run_full_analysis(ov, 200, ra)
    assert res["earliest_retirement_age"] == main["earliest_retirement_age"]
    assert res["target_age"] == ra and 0.0 <= res["success_at_target"] <= 1.0
    # Spending far less, and paying no state tax in retirement, can't make it worse.
    cheap = sr.run_place_check(ov, {"RETIREMENT_SPENDING_MODE": "Absolute amount ($/yr)",
                                    "RETIREMENT_SPENDING_ABSOLUTE": 5_000.0,
                                    "RETIREMENT_STATE_CHOICE": "No state tax"}, 200, ra)
    assert cheap["success_at_target"] >= res["success_at_target"]
    assert (cheap["earliest_retirement_age"] or 99) <= (res["earliest_retirement_age"] or 99)


def test_place_check_is_plain_scan_and_batch_calls_so_the_browser_can_run_it():
    from utils import sim_runner as sr
    ov = load_sample_household()
    plan = sr.plan_place_check(ov, {"RETIREMENT_STATE_CHOICE": "TX"}, 200, 50)
    assert plan.result is None
    fns = {c[0] for c in plan.job["calls"]}
    assert fns == {"scan", "batch"} and plan.job["calls"][-1][0] == "batch"
    from retirement_sim import mc_jobs
    assert mc_jobs.loads(mc_jobs.dumps(plan.job)) == plan.job        # plain data end to end
    assert plan.job["base"]["RETIREMENT_STATE_CHOICE"] == "TX"
