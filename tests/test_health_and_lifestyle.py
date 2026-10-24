"""Healthcare per adult, marketplace price inputs, and retirement lifestyle.

* HEALTHCARE_COSTS_BY_AGE bands are for a couple: each covered adult pays half
  a band for their own age, so a single person pays one share.
* An unmarried partner (cfg.has_partner(), not married) is covered too.
* The marketplace benchmark premium is an input (Assumptions panel).
* The go-go extra and the later-years drop follow the retirement age, scale
  with household size, are inputs (Retirement goals), and leave housing alone.
* Lifecycle presets follow the retirement age; empty-nest waits for the last
  child.
"""
import copy
import os
import sys
from contextlib import contextmanager

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import account_simulation as sim  # noqa: E402
from retirement_sim.account_simulation import AccountPortfolio  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402

IF = {"general": 1.0, "healthcare": 1.0, "childcare": 1.0}
DISC, FOOD = "SPEND_DISCRETIONARY_MONTHLY", "SPEND_FOOD_MONTHLY"


@pytest.fixture(autouse=True)
def _restore_cfg():
    saved = {k: copy.deepcopy(v) for k, v in vars(cfg).items() if k.isupper()}
    yield
    for k, v in saved.items():
        setattr(cfg, k, v)


@contextmanager
def applied(overrides):
    original = sr._apply_overrides(build_config_overrides(overrides))
    try:
        yield
    finally:
        sr._restore_overrides(original)


def _quote(your_age, partner_age, filing="Married filing jointly", magi=60_000.0):
    cfg.MODEL_ACA_AGE_RATED = True
    cfg.ACA_ENABLED = True
    cfg.YEARS_UNTIL_FIRST_CHILD = 99
    cfg.YOUR_AGE, cfg.PARTNER_AGE, cfg.FILING_STATUS = your_age, partner_age, filing
    p = AccountPortfolio()
    p.update_ages(your_age)
    return p.quote_health_insurance_cost(your_age, magi)


# ---------------------------------------------------------------------------
# Healthcare per adult
# ---------------------------------------------------------------------------

def test_medicare_floor_is_per_adult():
    """At 70 the band ($8,000 for a couple) is the floor: half for one person."""
    cfg.MODEL_HEALTHCARE_COST_FLOOR = True
    band = cfg.HEALTHCARE_COSTS_BY_AGE["medicare_base"]
    assert _quote(70, 70) == pytest.approx(band)
    assert _quote(70, 0, "Single") == pytest.approx(band / 2)       # was the full $8,000


def test_each_adult_is_charged_by_their_own_age():
    """Primary 80 (mid band), partner 72 (base band): one share of each."""
    cfg.MODEL_HEALTHCARE_COST_FLOOR = True
    hc = cfg.HEALTHCARE_COSTS_BY_AGE
    assert _quote(80, 72) == pytest.approx(hc["medicare_mid"] / 2 + hc["medicare_base"] / 2)
    # A pre-65 primary with a Medicare spouse: the spouse's share is a Medicare
    # band, not the primary's $24k marketplace band (which it used to be).
    got = _quote(62, 66)
    premium, oop = AccountPortfolio().quote_marketplace_cost(62, [62, 66], 60_000.0)
    medicare = max(cfg.calculate_medicare_irmaa(60_000.0, 1.0, enrollees=1),
                   hc["medicare_base"] / 2)
    assert got == pytest.approx(medicare + premium + oop)


def test_unmarried_partner_is_covered():
    """Filing Single with a partner: both adults are on the marketplace."""
    cfg.MODEL_HEALTHCARE_COST_FLOOR = True
    single = _quote(55, 0, "Single", magi=10_000_000.0)
    partners = _quote(55, 55, "Single", magi=10_000_000.0)
    married = _quote(55, 55, magi=10_000_000.0)
    assert partners == pytest.approx(married)
    assert partners == pytest.approx(2 * single)       # two 55-year-olds, full price


# ---------------------------------------------------------------------------
# Marketplace benchmark input
# ---------------------------------------------------------------------------

def test_benchmark_input_changes_premiums():
    full_price = {}
    for bench in (650, 1_000):
        with applied({"ACA_BENCHMARK_MONTHLY_AT_40": bench, "YOUR_AGE": 55,
                      "PARTNER_AGE": 0, "FILING_STATUS": "Single", "YEARS_UNTIL_FIRST_CHILD": 99}):
            p = AccountPortfolio()
            p.update_ages(55)
            full_price[bench] = p.quote_marketplace_cost(55, [55], 10_000_000.0)[0]
    assert full_price[1_000] == pytest.approx(full_price[650] * 1_000 / 650)


# ---------------------------------------------------------------------------
# Retirement lifestyle
# ---------------------------------------------------------------------------

def test_lifestyle_ages_follow_retirement_age():
    assert cfg.retirement_leisure_end_age(None) == 70 and cfg.late_retirement_start_age(None) == 75
    for ret in (40, 60, 65):                         # unchanged for retiring by 65
        assert cfg.retirement_leisure_end_age(ret) == 70
        assert cfg.late_retirement_start_age(ret) == 75
    assert cfg.retirement_leisure_end_age(68) == 73 and cfg.late_retirement_start_age(68) == 78
    cfg.EARLY_RETIREMENT_LEISURE_UNTIL_AGE, cfg.LATE_RETIREMENT_START_AGE = 66, 72
    assert cfg.retirement_leisure_end_age(55) == 66 and cfg.late_retirement_start_age(55) == 72


def test_leisure_extra_scales_with_household():
    cfg.EARLY_RETIREMENT_LEISURE_INCREASE = None
    cfg.PARTNER_AGE = 30
    assert cfg.retirement_leisure_increase() == 10_000
    cfg.PARTNER_AGE = 0
    assert cfg.retirement_leisure_increase() == pytest.approx(10_000 * 2 / 3)
    cfg.EARLY_RETIREMENT_LEISURE_INCREASE = 4_000            # a chosen amount is used as-is
    assert cfg.retirement_leisure_increase() == 4_000


def _renter_expenses(age, retirement_age):
    cfg.HOME_VALUE = cfg.MORTGAGE_BALANCE = cfg.MORTGAGE_MONTHLY = cfg.MORTGAGE_ANNUAL = 0
    cfg.MORTGAGE_YEARS_REMAINING = 0
    cfg.SPEND_RENT_MONTHLY = 2_000
    cfg.YEARS_UNTIL_FIRST_CHILD = 99
    cfg.SPEND_LIFECYCLE_PRESET = "Flat (no change)"
    cfg.EARLY_RETIREMENT_LEISURE_INCREASE = 10_000
    return sim.calculate_retirement_expenses(age, IF, retirement_age)


def test_go_go_years_and_later_drop_in_the_expense_total():
    base = _renter_expenses(72, 60) # between the two phases: no extra, no drop
    assert _renter_expenses(69, 60) == pytest.approx(base + 10_000)
    assert _renter_expenses(72, 68) == pytest.approx(base + 10_000)   # retired late: 5 years
    # The drop cuts living spending, not the $24k rent.
    living = base - 24_000
    assert _renter_expenses(76, 60) == pytest.approx(24_000 + living * 0.85)
    assert _renter_expenses(76, 68) == pytest.approx(base)             # drop waits until 78
    cfg.LATE_RETIREMENT_LEISURE_DECREASE = 0.30
    assert _renter_expenses(76, 60) == pytest.approx(24_000 + living * 0.70)


def test_lifestyle_reaches_the_engine_through_overrides():
    with applied({"EARLY_RETIREMENT_LEISURE_INCREASE": 3_000,
                  "EARLY_RETIREMENT_LEISURE_UNTIL_AGE": 65,
                  "LATE_RETIREMENT_LEISURE_DECREASE": 0.2, "LATE_RETIREMENT_START_AGE": 80}):
        assert cfg.retirement_leisure_increase() == 3_000
        assert cfg.retirement_leisure_end_age(55) == 65
        assert cfg.late_retirement_start_age(55) == 80


# ---------------------------------------------------------------------------
# Lifecycle presets
# ---------------------------------------------------------------------------

def test_travel_boom_starts_at_retirement():
    boom = cfg.LIFECYCLE_TRAVEL_BOOM
    m = lambda age, ret: cfg.lifecycle_multiplier(DISC, age, ret, boom, retired=age >= ret)
    assert m(58, 62) == 1.0                  # still working (used to be +50% from 55)
    assert m(62, 62) == 1.5 and m(69, 62) == 1.5 and m(70, 62) == 1.0
    assert m(75, 62) == 0.8
    assert m(72, 68) == 1.5 and m(75, 68) == 1.0 and m(78, 68) == 0.8
    assert cfg.lifecycle_multiplier(FOOD, 62, 62, boom) == 1.0


def test_empty_nest_waits_for_the_last_child():
    with applied({"YOUR_AGE": 30, "YEARS_UNTIL_FIRST_CHILD": 0, "YEARS_BETWEEN_CHILDREN": 4,
                  "CHILD_LEAVES_HOME_AGE": 18, "FIRST_CHILD_MONTHLY_COST": 1_500,
                  "BOTH_CHILDREN_MONTHLY_COST": 2_500,
                  "SPEND_LIFECYCLE_PRESET": cfg.LIFECYCLE_EMPTY_NEST}):
        assert cfg.SPEND_EMPTY_NEST_AGE == 52            # second child leaves at 52
        assert cfg.lifecycle_multiplier(FOOD, 50) == 1.30  # (only the first had left)
        assert cfg.lifecycle_multiplier(FOOD, 52) == 0.75
        from components.spending_inputs import compute_lifecycle_multipliers
        chart = compute_lifecycle_multipliers(cfg.LIFECYCLE_EMPTY_NEST, 30, 60, 90)
        assert chart[FOOD][51] == 1.30 and chart[FOOD][52] == 0.75
    with applied({"YEARS_UNTIL_FIRST_CHILD": 99}):
        assert cfg.SPEND_EMPTY_NEST_AGE is None
        assert cfg.lifecycle_multiplier(FOOD, 60, preset=cfg.LIFECYCLE_EMPTY_NEST) == 1.0


def test_chart_and_engine_use_the_same_mapping():
    from components.spending_inputs import compute_lifecycle_multipliers
    with applied({"SPEND_LIFECYCLE_PRESET": cfg.LIFECYCLE_TRAVEL_BOOM,
                  "SPEND_DISCRETIONARY_MONTHLY": 1_000, "YEARS_UNTIL_FIRST_CHILD": 99}):
        chart = compute_lifecycle_multipliers(cfg.LIFECYCLE_TRAVEL_BOOM, 30, 63, 95)
        for age in range(30, 96):
            engine = cfg.lifecycle_spend_delta_annual(age, 1.0, 63, retired=age >= 63)
            assert engine == pytest.approx(12_000 * (chart[DISC].get(age, 1.0) - 1.0)), age
