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
from utils import place_costs as pc  # noqa: E402
from utils import places as pl  # noqa: E402
from utils.milestones import BEYOND, PROGRESS, REACHED  # noqa: E402


# ------------------------------------------------------------------ places

def test_built_in_places_are_generic_and_sane():
    ids = [p.id for p in pl.BUILT_IN]
    assert len(ids) == len(set(ids))
    assert ids[0] == pl.HERE_ID
    here = pl.default_place(pl.HERE_ID)
    assert here.area == "" and here.housing == pl.HOUSING_KEEP and here.adjust == 1.0
    for p in pl.BUILT_IN[1:]:
        assert pc.known(p.area)                              # every place is based on an area
        assert p.housing == (pl.HOUSING_RENT if p.abroad else pl.HOUSING_BUY)   # buy in the US, rent abroad
        assert p.adjust == 1.0 and p.price is None and p.rent is None
    for p in pl.BUILT_IN:
        assert pl.normalize_tax(p.tax) == p.tax              # every built-in tax setting is valid
    names = {p.name for p in pl.BUILT_IN}
    assert {"Midwest", "Texas", "Portugal", "Italy", "Thailand"} <= names
    assert all(p.tax == pl.TAX_NONE for p in pl.BUILT_IN if p.abroad)


def test_area_data_is_complete_and_sane():
    from retirement_sim import state_tax_data
    assert set(state_tax_data.STATES) <= set(pc.AREAS)       # every state (and DC) has prices
    for a in pc.AREAS.values():
        for v in (a.goods, a.services, a.utilities, a.health):
            assert 0.15 <= v <= 2.5, a
        assert 50_000 <= a.price <= 3_000_000 and 300 <= a.rent <= 10_000, a
        assert 0.0 <= a.carry <= 0.04, a
        assert a.tax == "same" or pl.normalize_tax(a.tax) == a.tax, a
        for c in pc.CATEGORIES:
            assert pc.index(a, c) > 0
    names = {pc.get(c).name for c in pc.home_options()}
    for metro in ("San Francisco Bay Area", "Los Angeles area", "San Diego area", "Seattle area",
                  "New York City area", "Boston area", "Washington, DC area", "Denver area",
                  "Austin area", "Chicago area", "Miami area"):
        assert metro in names
    assert not any(pc.get(c).kind == pc.KIND_ABROAD for c in pc.home_options())   # you live in the US now
    assert set(pc.home_options()) < set(pc.place_options())
    # Every expense category in the Expenses section is priced.
    from utils.expense_categories import CATEGORIES
    assert {c.key for c in CATEGORIES} == set(pc.CONFIG_KEYS)


def test_home_area_defaults_to_the_plans_state():
    assert pc.default_home("CA") == "CA" and pc.default_home("tx") == "TX"
    assert pc.default_home("No state tax") == pc.US_CODE and pc.default_home(None) == pc.US_CODE
    assert pl.home_area(pl.empty_state(), {"STATE_CHOICE": "OH"}) == "OH"
    s = pl.with_home(pl.empty_state(), "M_SFB", {"STATE_CHOICE": "CA"})
    assert pl.home_area(s, {"STATE_CHOICE": "CA"}) == "M_SFB"
    assert pl.with_home(s, "CA", {"STATE_CHOICE": "CA"})["settings"] == {}     # the default is not stored
    assert pl.with_home(s, "nowhere", {})["settings"] == {}
    # A saved home equal to the plan's state, or abroad, is dropped on load.
    assert pl.get_state({"STATE_CHOICE": "CA", pl.KEY: {"v": 2, "settings": {"home": "CA"}}})["settings"] == {}
    assert pl.get_state({pl.KEY: {"v": 2, "settings": {"home": "X_PT"}}})["settings"] == {}


def test_price_ratios_are_against_where_you_live_now():
    for c in pc.CATEGORIES:
        assert pc.ratio("OH", "OH", c) == pytest.approx(1.0)
        assert pc.ratio("OH", "CA", c) == pytest.approx(pc.index(pc.get("OH"), c) / pc.index(pc.get("CA"), c))
    # The same Midwest is cheaper still against a San Francisco baseline than against California.
    assert pc.ratio("OH", "M_SFB", pc.CAT_OTHER) < pc.ratio("OH", "CA", pc.CAT_OTHER) < 1.0
    # Everyday spending weighted by what you spend on each category.
    w = {pc.CAT_FOOD: 1000.0, pc.CAT_UTILITIES: 3000.0}
    want = (1000 * pc.ratio("HI", "US", pc.CAT_FOOD) + 3000 * pc.ratio("HI", "US", pc.CAT_UTILITIES)) / 4000
    assert ms.everyday_ratio(w, "HI", "US") == pytest.approx(want)
    assert ms.everyday_ratio({}, "HI", "US") == 1.0


def test_untouched_state_is_not_stored():
    ov = {"YOUR_AGE": 30}
    state = pl.get_state(ov)
    pl.store(ov, state)
    assert pl.KEY not in ov                     # an untouched profile saves exactly as before


def test_get_state_survives_junk():
    for junk in (None, 5, "x", [], {"edits": 3, "custom": "no", "hidden": 7, "settings": []},
                 {"v": 2, "edits": {"midwest": {"adjust": "abc", "tax": "US:ZZ", "housing": "castle",
                                                "price": -5}, "nowhere": {"adjust": 2}},
                  "custom": [{"name": ""}, 3, {"id": "c1", "name": "Ok", "adjust": 99, "area": "nowhere",
                                               "housing": "rent", "rent": "x"}],
                  "hidden": ["here", "texas", "bogus"]}):
        state = pl.get_state({pl.KEY: junk})
        assert set(state) == {"v", "edits", "custom", "hidden", "settings"}
        pl.resolve(state)
    state = pl.get_state({pl.KEY: junk})
    assert "nowhere" not in state["edits"]
    mid = state["edits"]["midwest"]
    assert mid["tax"] == pl.TAX_SAME and "housing" not in mid and "price" not in mid   # junk falls back
    c = state["custom"][0]
    assert c["adjust"] == pl.ADJUST_MAX and c["area"] == pc.US_CODE and c["rent"] is None
    assert state["hidden"] == ["texas"]                         # "here" can't be hidden


def test_edit_reset_hide_and_restore():
    s = pl.empty_state()
    s = pl.with_edit(s, "midwest", adjust=0.7, tax="US:TX", note="x", housing="rent", rent=1_200,
                     price=300_000)
    mid = pl.get_place(s, "midwest")
    assert (mid.adjust, mid.tax, mid.note, mid.housing, mid.rent, mid.price) == (0.7, "US:TX", "x", "rent", 1200, 300000)
    assert mid.monthly_rent("CA") == 1200 and mid.home_price("CA") == 300000
    assert pl.is_edited(s, "midwest")
    s = pl.with_edit(s, "midwest", price=None, rent=0)            # back to the area's typical
    assert pl.get_place(s, "midwest").home_price("CA") == pc.get("OH").price
    base = pl.default_place("midwest")
    s = pl.with_edit(s, "midwest", adjust=base.adjust, tax=base.tax, note=base.note, housing=base.housing)
    assert not pl.is_edited(s, "midwest") and pl.is_empty(s)        # editing back is a reset
    s = pl.with_edit(s, pl.HERE_ID, housing="buy", price=1, adjust=0.9)
    assert pl.get_place(s, pl.HERE_ID).housing == pl.HOUSING_KEEP   # "here" always keeps your home
    assert pl.get_place(s, pl.HERE_ID).adjust == 0.9
    assert pl.with_reset(s, pl.HERE_ID)["edits"] == {}
    s = pl.with_removed(pl.empty_state(), "texas")
    assert pl.get_place(s, "texas") is None
    assert pl.with_removed(s, pl.HERE_ID)["hidden"] == ["texas"]    # "here" stays
    s = pl.with_restored(s)
    assert pl.get_place(s, "texas") is not None


def test_custom_places_add_edit_remove_and_limits():
    s = pl.empty_state()
    s, pid = pl.with_custom(s, "  Lisbon  ", "X_PT", note="my note")
    assert pid == "c1"
    p = pl.get_place(s, pid)
    assert (p.name, p.area, p.housing, p.tax, p.custom, p.abroad) == ("Lisbon", "X_PT", "rent", pl.TAX_NONE, True, True)
    s, pid2 = pl.with_custom(s, "Denver", "M_DEN")
    assert pid2 == "c2"
    den = pl.get_place(s, "c2")
    assert (den.housing, den.tax, den.home_price("CA")) == ("buy", "US:CO", pc.get("M_DEN").price)
    s = pl.with_edit(s, "c2", price=500_000, adjust=0.65)
    assert pl.get_place(s, "c2").home_price("CA") == 500_000
    s = pl.with_edit(s, "c2", area="M_AUS")                         # a new area: its own typical price
    aus = pl.get_place(s, "c2")
    assert (aus.area, aus.price, aus.adjust) == ("M_AUS", None, 0.65)
    s = pl.with_removed(s, "c1")
    assert pl.get_place(s, "c1") is None
    s, pid3 = pl.with_custom(s, "Again")
    assert pid3 == "c1" and pl.get_place(s, "c1").area == pc.US_CODE   # a freed id is reused
    assert pl.with_custom(s, "   ")[1] is None                      # empty name
    full = pl.empty_state()
    for i in range(pl.MAX_CUSTOM):
        full, _ = pl.with_custom(full, f"P{i}")
    assert pl.with_custom(full, "one more")[1] is None


def test_old_single_factor_state_migrates():
    """A version-1 save (one cost factor per place) still loads. A built-in's edited
    factor keeps its size relative to the old built-in factor; a custom place keeps
    your home and becomes an adjustment."""
    old = {"edits": {"midwest": {"factor": 0.80, "tax": "US:IA", "note": "mine"},
                     "here": {"factor": 0.9}, "texas": {"factor": 0.95}},
           "custom": [{"id": "c1", "name": "Lisbon", "factor": 0.7, "tax": "none", "note": "n"}],
           "hidden": ["thailand"], "settings": {"rate": 0.035}}
    state = pl.get_state({"STATE_CHOICE": "CA", pl.KEY: old})
    assert state["v"] == pl.VERSION
    assert state["edits"]["midwest"] == {"adjust": round(0.80 / 0.88, 3), "tax": "US:IA", "note": "mine"}
    assert state["edits"]["here"] == {"adjust": 0.9}
    assert "texas" not in state["edits"]                            # its old default: nothing to keep
    lis = pl.get_place(state, "c1")
    assert (lis.area, lis.housing, lis.adjust, lis.tax, lis.note) == ("CA", "keep", 0.7, "none", "n")
    assert state["hidden"] == ["thailand"] and state["settings"] == {"rate": 0.035}
    # Loading it again (now version 2) changes nothing.
    assert pl.get_state({"STATE_CHOICE": "CA", pl.KEY: state}) == state


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
    s = pl.with_edit(pl.get_state(ov), "midwest", adjust=0.8, tax="US:IA", housing="rent", rent=1_400)
    s, _ = pl.with_custom(s, "Lisbon", "X_PT", note="note")
    s = pl.with_removed(s, "thailand")
    s = pl.with_setting(s, "rate", 0.035)
    s = pl.with_home(s, "M_SFB", ov)
    pl.store(ov, s)
    back = deserialize_overrides(serialize_overrides(ov))
    assert pl.get_state(back) == pl.get_state(ov)
    assert [p.id for p in pl.resolve(pl.get_state(back))] == [p.id for p in pl.resolve(s)]
    assert pl.home_area(pl.get_state(back), back) == "M_SFB"
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
    assert ms.fire_number(40_000, 0.04) == pytest.approx(1_000_000)
    assert ms.fire_number(40_000, 0) == float("inf")
    assert ms.coast_need(1_000_000, 35, 55, 0.05) == pytest.approx(1_000_000 / 1.05 ** 20)
    assert ms.coast_need(1_000_000, 60, 55, 0.05) == 1_000_000       # past retirement age: no growth left


_WEIGHTS = {pc.CAT_UTILITIES: 3_000.0, pc.CAT_FOOD: 12_000.0, pc.CAT_TRANSPORT: 6_000.0,
            pc.CAT_HEALTH: 2_400.0, pc.CAT_FUN: 9_000.0, pc.CAT_OTHER: 3_600.0}   # 36,000 a year


def _cost(**kw):
    base = dict(home="CA", weights=_WEIGHTS, housing_now=30_000.0, pre_medicare=True,
                proceeds={a: 200_000.0 + 10_000.0 * (a - 35) for a in range(35, 91)},
                moving_costs=10_000.0, mortgage_rate=0.06, loan_years=30)
    base.update(kw)
    return ms.CostBasis(**base)


def _inputs(**kw):
    ages = list(range(35, 66))
    invested = [200_000 * 1.07 ** i + 40_000 * i for i in range(len(ages))]
    # core = living 36k + housing 30k + children 4k
    base = dict(your_age=35, retire_age=55, year=2026, ages=ages, invested=invested,
                home=[100_000.0] * len(ages), spend_core=70_000, living_base=36_000, health=12_000, today_spend=84_000,
                discretionary_ratio=0.30, rate=0.04, real_return=0.05, cash=30_000,
                barista_income=24_000, mortgage_years=10,
                places=(pl.default_place("here"), pl.default_place("midwest"), pl.default_place("thailand")),
                cost=_cost())
    base.update(kw)
    return ms.Inputs(**base)


def test_where_you_live_now_is_the_plan_exactly():
    inp = _inputs()
    here = ms.place_cost(inp, pl.default_place(pl.HERE_ID), 55)
    assert here.spend == pytest.approx(70_000 + 12_000)                  # core + health, nothing scaled
    assert here.ratio == pytest.approx(1.0) and here.release == 0 and here.housing == 30_000
    assert all(now == pytest.approx(there) for _, now, there in here.categories)
    assert ms.place_overrides(inp, pl.default_place(pl.HERE_ID), {"ACA_CHILD_MONTHLY": 390}) == {}
    assert ms.place_home_events(inp, pl.default_place(pl.HERE_ID), 55, [{"age": 60}]) is None
    # The plan's own housing then (its own moves included) replaces the config term.
    inp2 = _inputs(cost=_cost(housing_plan=50_000.0))
    assert ms.place_cost(inp2, pl.default_place(pl.HERE_ID), 55).spend == pytest.approx(70_000 - 30_000 + 50_000 + 12_000)
    # Any area matched to itself, with no move, is the plan too.
    same = pl.Place("x", "Same", pl.GROUP_CUSTOM, "CA", pl.HOUSING_KEEP, pl.TAX_SAME)
    assert ms.place_cost(inp, same, 55).spend == pytest.approx(here.spend)
    assert ms.place_overrides(inp, same) == {}


def test_each_category_scales_by_its_own_price_ratio():
    inp = _inputs()
    mid = pl.default_place("midwest")                                     # Ohio, against California
    c = ms.place_cost(inp, mid, 55)
    by = {k: (now, there) for k, now, there in c.categories}
    for k, w in _WEIGHTS.items():
        assert by[k][0] == pytest.approx(w)
        assert by[k][1] == pytest.approx(w * pc.ratio("OH", "CA", k))
    assert c.living == pytest.approx(sum(t for _, t in by.values()))
    # Utilities and services drop more than goods, so the categories do not share one factor.
    assert len({round(by[k][1] / by[k][0], 3) for k in by}) >= 4
    assert c.health == pytest.approx(12_000 * pc.ratio("OH", "CA", pc.CAT_HEALTH))   # pre-Medicare health
    assert c.other == pytest.approx(4_000)                                # children: as planned
    # The overall adjustment multiplies the per-category result.
    half = ms.place_cost(inp, pl.Place("m", "M", pl.GROUP_US, "OH", "buy", "US:OH", adjust=0.5), 55)
    assert half.living == pytest.approx(c.living * 0.5)
    # After Medicare, health is not scaled.
    late = ms.place_cost(_inputs(cost=_cost(pre_medicare=False)), mid, 55)
    assert late.health == 12_000


def test_retirement_spending_mode_scales_the_categories_as_a_group():
    # "% of today" at 80%: the living base is 80% of the categories, and each one shrinks alike.
    inp = _inputs(living_base=36_000 * 0.8, spend_core=70_000 - 36_000 * 0.2)
    here = ms.place_cost(inp, pl.default_place(pl.HERE_ID), 55)
    assert dict((k, now) for k, now, _ in here.categories)[pc.CAT_FOOD] == pytest.approx(12_000 * 0.8)
    mid = ms.place_cost(inp, pl.default_place("midwest"), 55)
    full = ms.place_cost(_inputs(), pl.default_place("midwest"), 55)
    assert mid.living == pytest.approx(full.living * 0.8)
    assert mid.other == pytest.approx(4_000)


def test_home_area_is_the_baseline():
    """The same place is cheaper against a pricier home area."""
    mid = pl.default_place("midwest")
    vs_ca = ms.place_cost(_inputs(cost=_cost(home="CA")), mid, 55)
    vs_sf = ms.place_cost(_inputs(cost=_cost(home="M_SFB")), mid, 55)
    vs_oh = ms.place_cost(_inputs(cost=_cost(home="OH")), mid, 55)
    assert vs_sf.living < vs_ca.living < vs_oh.living
    assert vs_oh.ratio == pytest.approx(1.0)
    assert vs_sf.housing == vs_ca.housing                                 # housing is the place's own


def test_buy_or_rent_there():
    inp = _inputs()
    oh = pc.get("OH")
    buy = ms.place_cost(inp, pl.default_place("midwest"), 55)            # proceeds 400k > a 235k home
    assert buy.proceeds == pytest.approx(400_000) and buy.price == oh.price and buy.loan == 0
    assert buy.housing == pytest.approx(oh.price * oh.carry)              # paid off: tax + insurance only
    assert buy.release == pytest.approx(400_000 - oh.price - 10_000)
    rent = ms.place_cost(inp, pl.Place("r", "R", pl.GROUP_US, "OH", pl.HOUSING_RENT, "US:OH"), 55)
    assert rent.housing == pytest.approx(oh.rent * 12) and rent.price == 0
    assert rent.release == pytest.approx(400_000 - 10_000)
    assert rent.spend != buy.spend
    # A pricier home than the sale brings: the loan covers the shortfall.
    sf = pl.Place("s", "S", pl.GROUP_US, "M_SFB", pl.HOUSING_BUY, "US:CA")
    c = ms.place_cost(inp, sf, 55)
    price = pc.get("M_SFB").price
    assert c.loan == pytest.approx(price - 400_000) and c.down == pytest.approx(400_000)
    pay = ms._loan_payment(c.loan, 0.06, 30) * 12
    assert c.housing == pytest.approx(pay + price * pc.get("M_SFB").carry)
    assert c.release == pytest.approx(-10_000)
    # Your own price and rent win over the area's.
    mine = pl.Place("m", "M", pl.GROUP_US, "OH", pl.HOUSING_BUY, "US:OH", price=100_000)
    assert ms.place_cost(inp, mine, 55).price == 100_000
    # A renter today has nothing to sell: the whole price is borrowed.
    renter = _inputs(cost=_cost(proceeds={}))
    c = ms.place_cost(renter, pl.default_place("midwest"), 55)
    assert c.proceeds == 0 and c.loan == oh.price and c.release == pytest.approx(-10_000)


def test_home_equity_counts_in_the_fire_test():
    """Selling a home you own and buying a cheaper one frees cash, so FIRE comes sooner
    than with the same spending and no home to sell."""
    mid = pl.default_place("midwest")
    with_home = ms.build(_inputs(places=(mid,)))
    no_home = ms.build(_inputs(places=(mid,), cost=_cost(proceeds={})))
    a, b = with_home.places[0], no_home.places[0]
    assert a.cost.release > 0 > b.cost.release
    assert a.fire.age is not None and (b.fire.age is None or a.fire.age < b.fire.age)
    assert a.coast.age is not None and (b.coast.age is None or a.coast.age <= b.coast.age)


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
        assert pr.cost is not None and pr.spend == pr.cost.spend
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


def test_place_overrides_set_spending_health_and_tax():
    inp = _inputs()
    knobs = {"ACA_BENCHMARK_MONTHLY_AT_40": 650, "ACA_CHILD_MONTHLY": 390,
             "HEALTHCARE_COSTS_BY_AGE": {"early_retirement": 24_000, "medicare_base": 8_000}}
    mid = pl.default_place("midwest")
    ov = ms.place_overrides(inp, mid, knobs)
    assert ov["RETIREMENT_SPENDING_MODE"].startswith("Absolute")
    assert ov["RETIREMENT_SPENDING_ABSOLUTE"] == pytest.approx(ms.place_cost(inp, mid, 55).living, abs=0.01)
    h = pc.ratio("OH", "CA", pc.CAT_HEALTH)
    assert ov["ACA_BENCHMARK_MONTHLY_AT_40"] == pytest.approx(650 * h, abs=0.01)
    assert ov["ACA_CHILD_MONTHLY"] == pytest.approx(390 * h, abs=0.01)
    assert ov["HEALTHCARE_COSTS_BY_AGE"] == {"early_retirement": pytest.approx(24_000 * h, abs=0.01),
                                             "medicare_base": 8_000}              # Medicare as planned
    assert knobs["HEALTHCARE_COSTS_BY_AGE"]["early_retirement"] == 24_000     # the plan's dict is untouched
    assert ov["RETIREMENT_STATE_CHOICE"] == "OH"
    thai = ms.place_overrides(inp, pl.default_place("thailand"))
    assert thai["RETIREMENT_STATE_CHOICE"] == "No state tax" and "ACA_CHILD_MONTHLY" not in thai


def test_place_home_events_match_the_quick_rule():
    inp = _inputs()
    plan = [{"age": 40, "action": "sell_rent", "rent": 2_000}, {"age": 55, "action": "buy", "price": 1},
            {"age": 70, "action": "sell_rent", "rent": 900}]
    ev = ms.place_home_events(inp, pl.default_place("midwest"), 55, plan)
    assert [e["age"] for e in ev] == [40, 55]                       # moves from that age on are replaced
    move = ev[-1]
    c = ms.place_cost(inp, pl.default_place("midwest"), 55)
    assert move["action"] == "sell_buy" and move["price"] == c.price and move["loan"] == c.loan == 0
    assert move["years"] == 0 and move["costs"] == 10_000 and move["carrying_pct"] == pc.get("OH").carry
    sf = pl.Place("s", "S", pl.GROUP_US, "M_SFB", pl.HOUSING_BUY, "US:CA")
    move = ms.place_home_events(inp, sf, 50, [])[-1]
    assert move["loan"] > 0 and move["years"] == 30 and move["rate"] == 0.06
    rent = ms.place_home_events(inp, pl.default_place("thailand"), 60, [])
    assert rent == [{"age": 60, "action": "sell_rent", "rent": pc.get("X_TH").rent, "costs": 10_000}]
    keep = pl.Place("k", "K", pl.GROUP_CUSTOM, "OH", pl.HOUSING_KEEP, pl.TAX_SAME)
    assert ms.place_home_events(inp, keep, 55, plan) is None


# ------------------------------------------------------------------ the engine and the runner

def test_cache_keys_ignore_places_and_the_builder_drops_them():
    from utils import sim_runner as sr
    from utils.config_builder import build_config_overrides
    ov = load_sample_household()
    edited = dict(ov)
    pl.store(edited, pl.with_edit(pl.empty_state(), "midwest", adjust=0.5))
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


def _section_inputs(ov, state=None):
    from components import freedom_milestones as fm
    state = pl.get_state(ov) if state is None else state
    (inp, basis, sale), _ = fm.build_inputs(ov, None, state, 0.04, 24_000)
    return fm, state, inp, basis, sale


def _engine_year(ov, age):
    """Run the engine's own home and spending steps up to ``age`` (no markets):
    (cash the year's housing events add, housing that year, living base, the year's
    expenses before health)."""
    from retirement_sim import account_simulation as sim
    from retirement_sim import config as cfg
    from utils import sim_runner as sr
    original = sr._apply_overrides(ov)
    try:
        pf = sim.create_initial_portfolio()
        pf.record_year(cfg.CURRENT_YEAR, cfg.YOUR_AGE)
        for a in range(cfg.YOUR_AGE, age):
            pf.apply_housing_events(a)
            pf.record_year(cfg.CURRENT_YEAR + a + 1 - cfg.YOUR_AGE, a + 1)
        before = pf.get_total_balance()
        pf.apply_housing_events(age)
        freed = pf.get_total_balance() - before
        core = (cfg.calculate_annual_expenses(age, 1.0, 1.0, retirement=True, retirement_age=age)
                + sim._housing_swap_delta(pf, age))
        return freed, pf.housing_expense_for_age(age), cfg.retirement_living_base(), core
    finally:
        sr._restore_overrides(original)


@pytest.mark.parametrize("renter", [False, True])
def test_quick_rule_and_confirm_settings_agree_in_the_engine(renter):
    """What Confirm hands the engine reproduces the card's numbers: the cash the move
    frees, housing there, everyday spending and the year's total (health aside)."""
    from utils.config_builder import build_config_overrides
    ov = load_sample_household()
    if renter:
        ov.update(HOME_VALUE=0, MORTGAGE_BALANCE=0, MORTGAGE_MONTHLY=0, MORTGAGE_YEARS_REMAINING=0,
                  SPEND_RENT_MONTHLY=2_500, HOUSE_MOVE_ENABLED=False)
    fm, state, inp, basis, sale = _section_inputs(ov)
    for pid, age in (("here", inp.retire_age), ("midwest", inp.retire_age), ("coastal", inp.retire_age - 4),
                     ("portugal", inp.retire_age), ("midwest", inp.retire_age + 6)):
        place = pl.get_place(state, pid)
        po, patch = fm.confirm_settings(inp, place, basis, sale)
        merged = {**build_config_overrides(ov), **po, **(patch(age) if patch else {})}
        freed, housing, living, core = _engine_year(merged, age)
        q = ms.place_cost(inp, place, age)
        assert freed == pytest.approx(q.release, abs=1.0), pid
        assert housing == pytest.approx(q.housing, abs=1.0), pid
        assert living == pytest.approx(q.living, abs=1.0), pid
        assert core == pytest.approx(q.spend - q.health, abs=1.0), pid


def test_spending_basis_reports_categories_housing_and_health_knobs():
    from utils import sim_runner as sr
    ov = load_sample_household()
    ra = int(ov["TARGET_RETIREMENT_AGE"])
    basis = sr.retirement_spending_basis(ov, ra)
    assert basis["core"] > 0 and basis["health"] > 0 and basis["living"] > 0
    assert sum(basis["weights"].values()) == pytest.approx(basis["living"])     # mode "same as today"
    assert basis["weights"][pc.CAT_FOOD] == ov["SPEND_FOOD_MONTHLY"] * 12
    assert basis["housing"] > 0 and basis["pre_medicare"] is True
    assert basis["health_knobs"]["ACA_BENCHMARK_MONTHLY_AT_40"] > 0
    fm, state, inp, _, sale = _section_inputs(ov)
    po = ms.place_overrides(inp, pl.default_place("midwest"), basis["health_knobs"])
    after = sr.retirement_spending_basis({**ov, **po}, ra)
    assert after["living"] == pytest.approx(ms.place_cost(inp, pl.default_place("midwest"), ra).living, abs=0.01)


def test_home_sale_path_follows_the_loan_and_the_plans_moves():
    from utils import sim_runner as sr
    ov = {**load_sample_household(), "HOUSE_MOVE_ENABLED": False}
    path = sr.home_sale_path(ov, 80)
    p = path["proceeds"]
    first = ov["YOUR_AGE"]
    assert p[first] == pytest.approx(ov["HOME_VALUE"] * (1 - 0.06) - ov["MORTGAGE_BALANCE"])
    assert all(p[a + 1] >= p[a] for a in range(first, 79))             # the loan only shrinks
    assert path["owner"] and not path["legacy_move"]
    assert path["housing"][first] == pytest.approx(ov["MORTGAGE_MONTHLY"] * 12)
    moved = sr.home_sale_path({**ov, "HOME_EVENTS": [{"age": 50, "action": "sell_rent", "rent": 1_000}]}, 80)
    assert moved["proceeds"][50] == pytest.approx(p[50])               # a sale at 50 happens before the plan's move
    assert moved["proceeds"][51] == 0 and moved["housing"][55] == 12_000
    renter = sr.home_sale_path({**ov, "HOME_VALUE": 0, "MORTGAGE_BALANCE": 0, "MORTGAGE_MONTHLY": 0}, 70)
    assert set(renter["proceeds"].values()) == {0.0} and not renter["owner"]


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
    assert plan.job["patches"] == [] and {c[1] for c in plan.job["calls"]} == {-1}


def test_place_check_moves_you_at_each_age_it_tries():
    """A place with a move gets one patch per scanned age (and the target age): the
    move happens at the age you would retire, as in the quick rule."""
    from utils import sim_runner as sr
    from retirement_sim import mc_jobs
    ov = load_sample_household()
    fm, state, inp, basis, sale = _section_inputs(ov)
    place = pl.get_place(state, "midwest")
    po, patch = fm.confirm_settings(inp, place, basis, sale)
    plan = sr.plan_place_check(ov, po, 200, inp.retire_age, patch)
    assert mc_jobs.loads(mc_jobs.dumps(plan.job)) == plan.job
    for fn, idx, args in plan.job["calls"]:
        age = args[0]
        events = plan.job["patches"][idx]["HOME_EVENTS"]
        assert events[-1]["age"] == age and events[-1]["action"] == "sell_buy"
        assert all(e["age"] < age for e in events[:-1])
        assert plan.job["patches"][idx]["HOUSE_MOVE_ENABLED"] is False
    # Different places are different checks.
    other = sr.plan_place_check(ov, po, 200, inp.retire_age,
                                fm.confirm_settings(inp, pl.get_place(state, "portugal"), basis, sale)[1])
    assert other.key != plan.key
    # "Where you live now" has no patches at all: the plan's own run.
    po_here, patch_here = fm.confirm_settings(inp, pl.get_place(state, "here"), basis, sale)
    assert po_here == {} and patch_here is None


def test_engine_default_is_unchanged_without_a_place():
    """The engine change (a purchase may carry its own property tax + insurance rate)
    leaves every existing plan alone: no new keys on old events, the default rate
    when none is given, and identical results."""
    import random
    import numpy as np
    from retirement_sim import account_simulation as sim
    from retirement_sim import config as cfg
    from utils import sim_runner as sr
    from utils.config_builder import build_config_overrides
    assert cfg.home_carrying_cost_annual(500_000) == cfg.home_carrying_cost_annual(500_000, None)
    ev = {"age": 50, "action": "buy", "price": 400_000, "down_pct": 1.0}
    assert "carrying_pct" not in cfg.housing_events({"HOME_EVENTS": [ev]})[0]
    base = build_config_overrides(load_sample_household())

    def run(extra):
        original = sr._apply_overrides({**base, **extra})
        try:
            np.random.seed(5)
            random.seed(5)
            r = sim.run_monte_carlo_detailed(retirement_age=48, n_simulations=40, random_seed=5)
            return r["success_rate"], r["median_final"]
        finally:
            sr._restore_overrides(original)

    pct = float(base.get("HOME_CARRYING_COST_PCT", cfg.HOME_CARRYING_COST_PCT))
    plain = run({"HOME_EVENTS": [ev]})
    assert run({"HOME_EVENTS": [{**ev, "carrying_pct": pct}]}) == plain
    assert run({"HOME_EVENTS": [{**ev, "carrying_pct": pct + 0.02}]})[1] < plain[1]   # the rate is used
    pf_original = sr._apply_overrides(base)
    try:
        assert sim.create_initial_portfolio().home_carrying_pct is None
    finally:
        sr._restore_overrides(pf_original)
