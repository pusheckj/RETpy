"""Freedom milestones: a place's health cost follows the engine's own pricing.

The quick rule used the flat 'early_retirement' band ($24k a couple) before
Medicare, which the engine never charges (it prices the age-rated marketplace
with a subsidy and out-of-pocket, and nothing while a working partner's employer
plan covers the household). These tests hold the quick rule to the engine's
AccountPortfolio.quote_health_insurance_cost for the same ages and MAGI.
"""
import os
import sys
from contextlib import contextmanager

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.conftest import load_sample_household  # noqa: E402
from retirement_sim import account_simulation as sim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from utils import milestones as ms  # noqa: E402
from utils import place_costs as pc  # noqa: E402
from utils import places as pl  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402


@contextmanager
def applied(ov):
    original = sr._apply_overrides(build_config_overrides(ov))
    try:
        yield
    finally:
        sr._restore_overrides(original)


def engine_quote(ov, age, magi, factor, employer=False, scale=1.0):
    """The engine's premium at ``age``; ``scale`` multiplies the marketplace
    prices the way milestones.place_overrides does for a place."""
    if scale != 1.0:
        with applied(ov):
            bands = dict(cfg.HEALTHCARE_COSTS_BY_AGE)
            bench, child = cfg.ACA_BENCHMARK_MONTHLY_AT_40, cfg.ACA_CHILD_MONTHLY
        bands["early_retirement"] *= scale
        ov = {**ov, "ACA_BENCHMARK_MONTHLY_AT_40": bench * scale,
              "ACA_CHILD_MONTHLY": child * scale, "HEALTHCARE_COSTS_BY_AGE": bands}
    with applied(ov):
        p = sim.create_initial_portfolio()
        p.update_ages(age)
        p.employer_health_coverage = employer
        return p.quote_health_insurance_cost(age, magi, factor)


def _sample(**kw):
    ov = load_sample_household()
    ov["PARTNER_RETIREMENT_AGE"] = None          # retire together unless a test says otherwise
    ov.update(kw)
    return ov


PLANS = {
    "default": ({}, 55),
    "single": ({"PARTNER_AGE": 0, "FILING_STATUS": "Single"}, 50),
    "couple_kids": (_sample(), 45),
    "legacy_flat_band": ({"MODEL_ACA_AGE_RATED": False}, 55),
    "medicare_age": ({}, 67),
    "age_gap": ({"YOUR_AGE": 40, "PARTNER_AGE": 33}, 66),     # you on Medicare, partner on the marketplace
}


@pytest.mark.parametrize("name", list(PLANS))
def test_where_you_live_now_matches_the_engine(name):
    ov, ra = PLANS[name]
    basis = sr.retirement_spending_basis(ov, ra)
    hp = basis["health_params"]
    magi = 0.5 * basis["core"] + hp["income"] + hp["conversion"]
    want = engine_quote(ov, hp["age"], magi, hp["factor"], employer=hp["employer"])
    assert basis["health"] == pytest.approx(want, rel=1e-9, abs=1e-6)
    assert ms.health_cost(hp, 0.5 * basis["core"]) == pytest.approx(want, rel=1e-9, abs=1e-6)


def test_roth_conversions_count_in_the_income():
    on = sr.retirement_spending_basis({}, 55)["health_params"]
    off = sr.retirement_spending_basis({"ENABLE_ROTH_CONVERSION": False}, 55)["health_params"]
    with applied({}):
        target = cfg.roth_conversion_target()
    assert on["conversion"] == pytest.approx(min(target, cfg.ROTH_CONVERSION_MAX_ANNUAL))
    assert off["conversion"] == 0.0
    assert ms.health_cost(on, 20_000.0) > ms.health_cost(off, 20_000.0)   # conversions cost the subsidy


def test_no_longer_the_flat_band():
    basis = sr.retirement_spending_basis({}, 55)
    with applied({}):
        band = 2 * cfg.healthcare_cost_per_adult(55)
    assert basis["health"] != pytest.approx(band)


@pytest.mark.parametrize("spend_magi", [20_000.0, 60_000.0, 400_000.0])
@pytest.mark.parametrize("scale", [0.7, 1.35])
def test_a_place_follows_the_engine_with_scaled_prices(spend_magi, scale):
    ov, ra = PLANS["couple_kids"]
    hp = sr.retirement_spending_basis(ov, ra)["health_params"]
    want = engine_quote(ov, hp["age"], spend_magi + hp["income"] + hp["conversion"], hp["factor"],
                        scale=scale)
    assert ms.health_cost(hp, spend_magi, scale) == pytest.approx(want, rel=1e-9, abs=1e-6)


def test_subsidized_premium_does_not_move_with_prices_but_full_price_does():
    ov, ra = {"PARTNER_AGE": 0, "FILING_STATUS": "Single", "ENABLE_ROTH_CONVERSION": False}, 60
    hp = sr.retirement_spending_basis(ov, ra)["health_params"]
    low, high = 15_000.0, 300_000.0                    # well under / far over the 400% FPL cliff
    assert ms.health_cost(hp, low, 1.4) == pytest.approx(ms.health_cost(hp, low, 1.0))
    assert ms.health_cost(hp, high, 1.4) > ms.health_cost(hp, high, 1.0)
    assert ms.health_cost(hp, low, 1.4) == pytest.approx(
        engine_quote(ov, hp["age"], low, hp["factor"], scale=1.4))


def test_place_cost_prices_health_from_its_own_spending():
    ov, ra = PLANS["couple_kids"]
    basis = sr.retirement_spending_basis(ov, ra)
    cost = ms.CostBasis(home="CA", weights=basis["weights"], housing_now=basis["housing"],
                        pre_medicare=basis["pre_medicare"], health=basis["health_params"])
    inp = ms.Inputs(your_age=ov["YOUR_AGE"], retire_age=ra, year=2026, ages=[ov["YOUR_AGE"], ra],
                    invested=[1e6, 2e6], home=[0.0, 0.0], spend_core=basis["core"],
                    living_base=basis["living"], health=basis["health"], today_spend=basis["today"],
                    discretionary_ratio=0.3, rate=0.04, real_return=0.05, cash=0.0,
                    barista_income=0.0, mortgage_years=0, places=(), cost=cost)
    here = ms.place_cost(inp, pl.default_place(pl.HERE_ID), ra)
    assert here.health == pytest.approx(basis["health"])
    sf = pl.Place("s", "S", pl.GROUP_US, "M_SFB", pl.HOUSING_RENT, "US:CA")
    c = ms.place_cost(inp, sf, ra)
    h = pc.ratio(sf.area_code("CA"), "CA", pc.CAT_HEALTH)
    hp = basis["health_params"]
    want = engine_quote(ov, ra, 0.5 * (c.living + c.housing + c.other) + hp["conversion"], hp["factor"],
                        scale=h)
    assert c.health == pytest.approx(want, rel=1e-9)


def test_without_health_params_the_old_scaling_still_applies():
    cost = ms.CostBasis(home="CA", weights={pc.CAT_FOOD: 12_000.0}, housing_now=0.0, pre_medicare=True)
    inp = ms.Inputs(your_age=35, retire_age=55, year=2026, ages=[35, 55], invested=[1, 2], home=[0, 0],
                    spend_core=12_000.0, living_base=12_000.0, health=10_000.0, today_spend=12_000.0,
                    discretionary_ratio=0.3, rate=0.04, real_return=0.05, cash=0.0, barista_income=0.0,
                    mortgage_years=0, places=(), cost=cost)
    oh = pl.Place("o", "O", pl.GROUP_US, "OH", pl.HOUSING_KEEP, pl.TAX_SAME)
    assert ms.place_cost(inp, oh, 55).health == pytest.approx(10_000.0 * pc.ratio("OH", "CA", pc.CAT_HEALTH))


def test_partner_on_an_employer_plan_to_the_plan_end_means_no_premium():
    ov = _sample(PARTNER_RETIREMENT_AGE=200)         # never stops within the plan
    basis = sr.retirement_spending_basis(ov, 45)
    hp = basis["health_params"]
    assert hp["employer"] and basis["health"] == pytest.approx(hp["medicare"])
    # The engine charges the same: no marketplace premium, Medicare as planned.
    assert engine_quote(ov, hp["age"], 0.5 * basis["core"] + hp["income"] + hp["conversion"], hp["factor"],
                        employer=True) == pytest.approx(hp["medicare"])
    young = sr.retirement_spending_basis(_sample(PARTNER_RETIREMENT_AGE=200, PLAN_UNTIL_AGE=60), 45)
    assert young["health"] == 0.0                     # nobody reaches Medicare: nothing to pay
    assert engine_quote(_sample(PARTNER_RETIREMENT_AGE=200, PLAN_UNTIL_AGE=60), 45, 50_000.0, 1.0,
                        employer=True) == 0.0


def test_partner_on_an_employer_plan_until_medicare_is_priced_on_medicare():
    ov = _sample(PARTNER_RETIREMENT_AGE=70)          # stops at your 71: both on Medicare by then
    basis = sr.retirement_spending_basis(ov, 45)
    hp = basis["health_params"]
    assert hp["age"] == 71 and not hp["employer"] and hp["medicare"] > 0
    assert hp["conversion"] == 0.0                    # conversions stop at ROTH_CONVERSION_STOP_AGE
    assert basis["health"] == pytest.approx(engine_quote(ov, 71, 0.5 * basis["core"], hp["factor"]))


def test_a_partner_working_a_little_longer_is_priced_from_their_first_retired_year():
    ov = _sample(PARTNER_RETIREMENT_AGE=46)          # partner stops at your 47
    basis = sr.retirement_spending_basis(ov, 45)
    hp = basis["health_params"]
    assert hp["age"] == 47 and not hp["employer"] and hp["income"] == 0.0
    want = engine_quote(ov, 47, 0.5 * basis["core"] + hp["conversion"], hp["factor"])
    assert want > 0 and basis["health"] == pytest.approx(want, rel=1e-9)
