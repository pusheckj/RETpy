"""Age-rated ACA marketplace ("fair marketplace assumptions", Covered
California, San Diego, 2026) behind cfg.MODEL_ACA_AGE_RATED.

Pins:
  * full price is rated per member by age (federal CMS curve) + per child at home
  * children enter/leave the marketplace household on the SAME timeline as
    calculate_child_expenses
  * FPL scales with household size (2025 HHS), so the 400% cliff moves
  * 2026 applicable-percentage interpolation
  * out-of-pocket is charged net of the living base's SPEND_HEALTH line, and is
    booked where premiums are booked (once, not per pass)
  * subsidy still wins for low MAGI; Medicare pricing unchanged
  * toggle OFF is byte-identical to the pre-change engine (run_full_analysis)
"""
import copy
import hashlib
import os
import pickle
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest

from retirement_sim import config as cfg
from retirement_sim import account_simulation as sim
from retirement_sim.account_simulation import (
    Account, AccountPortfolio, AccountType, simulate_retirement_year,
)


@pytest.fixture(autouse=True)
def _restore_cfg():
    """Snapshot every cfg global and restore it after each test."""
    saved = {k: copy.deepcopy(v) for k, v in vars(cfg).items() if k.isupper()}
    yield
    for k, v in saved.items():
        setattr(cfg, k, v)


RICH = 10_000_000.0  # far above any cliff -> full price


def _household(your_age, partner_age=None, *, kids=False):
    """Portfolio for a household whose primary is ``your_age`` today."""
    cfg.MODEL_ACA_AGE_RATED = True
    cfg.ACA_ENABLED = True
    cfg.YOUR_AGE = your_age
    cfg.FILING_STATUS = "Single" if partner_age is None else "Married filing jointly"
    cfg.PARTNER_AGE = your_age if partner_age is None else partner_age
    if not kids:
        cfg.CHILDREN = []
    p = AccountPortfolio()
    p.update_ages(your_age)
    return p


def _rate(age):
    return cfg.ACA_BENCHMARK_MONTHLY_AT_40 * cfg.ACA_AGE_CURVE[age] / cfg.ACA_AGE_CURVE[40] * 12


# ---------------------------------------------------------------------------
# 1. Age rating
# ---------------------------------------------------------------------------

def test_defaults():
    assert cfg.MODEL_ACA_AGE_RATED is True
    assert cfg.ACA_BENCHMARK_MONTHLY_AT_40 == 650
    assert cfg.ACA_CHILD_MONTHLY == 390
    assert cfg.ACA_OOP_PER_PERSON_ANNUAL == 1_500
    assert cfg.ACA_AGE_CURVE[21] == 1.000 and cfg.ACA_AGE_CURVE[64] == 3.000
    assert sorted(cfg.ACA_AGE_CURVE) == list(range(21, 65))


def test_sixty_year_old_pays_curve_ratio_of_forty_year_old():
    at_40 = cfg.aca_member_full_price_annual(40)
    at_60 = cfg.aca_member_full_price_annual(60)
    assert at_40 == pytest.approx(650 * 12)
    assert at_60 / at_40 == pytest.approx(2.714 / 1.278)
    # Through the engine: single filers, rich (no subsidy).
    p40, _ = _household(40).quote_marketplace_cost(40, [40], RICH)
    p60, _ = _household(60).quote_marketplace_cost(60, [60], RICH)
    assert p60 / p40 == pytest.approx(2.714 / 1.278)


def test_curve_caps_at_64_and_children_use_child_rate():
    assert cfg.aca_member_full_price_annual(64) == pytest.approx(_rate(64))
    assert cfg.aca_member_full_price_annual(70) == pytest.approx(_rate(64))
    assert cfg.aca_member_full_price_annual(0) == pytest.approx(390 * 12)
    assert cfg.aca_member_full_price_annual(20) == pytest.approx(390 * 12)
    assert cfg.aca_member_full_price_annual(21) == pytest.approx(_rate(21))


def test_couple_full_price_is_sum_of_members_not_flat_band():
    p = _household(55, 50)
    prem, _ = p.quote_marketplace_cost(55, [55, 50], RICH)
    assert prem == pytest.approx(_rate(55) + _rate(50))


def test_early_retirement_band_is_not_the_ceiling_when_on():
    """Documented: the age-rated figure replaces the flat band."""
    cfg.HEALTHCARE_COSTS_BY_AGE = {**cfg.HEALTHCARE_COSTS_BY_AGE, "early_retirement": 5_000}
    p = _household(60, 60)
    prem, _ = p.quote_marketplace_cost(60, [60, 60], RICH)
    assert prem == pytest.approx(2 * _rate(60))
    assert prem > 5_000


# ---------------------------------------------------------------------------
# 2. Children enter and leave the marketplace household by age
# ---------------------------------------------------------------------------

def _kids(*births, leave=18):
    """CHILDREN for children born ``births`` years from now."""
    return [{"years_until_birth": b, "monthly_cost": 1_000, "leaves_home_age": leave}
            for b in births]


def test_children_added_and_removed_by_age():
    cfg.YOUR_AGE = 30
    cfg.CHILDREN = _kids(2, 5)        # born at primary 32 and 35
    kids = cfg.children_at_home_ages
    assert kids(31) == []
    assert kids(32) == [0]
    assert kids(35) == [3, 0]
    assert kids(49) == [17, 14]
    assert kids(50) == [15]          # first child left at 18
    assert kids(53) == []            # second child left too


def test_children_timeline_matches_child_expense_timeline():
    """Reuse, not reinvention: kids are on the marketplace exactly in the years
    calculate_child_expenses charges for them."""
    cfg.YOUR_AGE = 30
    # Each child costs a different power of two, so the bill says exactly which
    # children were charged; leave-home ages differ per child.
    for births, leaves in [((2, 5), (18, 18)), ((0, 1), (18, 22)), ((-5, -3, 4), (18, 25, 16)),
                           ((4, 14), (21, 18)), ((), ())]:
        cfg.CHILDREN = [{"years_until_birth": b, "monthly_cost": 2 ** i, "leaves_home_age": l}
                        for i, (b, l) in enumerate(zip(births, leaves))]
        for age in range(30, 80):
            at_home = cfg.children_at_home_ages(age)
            charged = int(cfg.calculate_child_expenses(age) / 12)
            assert len(at_home) == bin(charged).count("1"), (births, age)
            assert sorted(at_home) == sorted(
                age - 30 - b for i, b in enumerate(births) if charged & (2 ** i)), (births, age)


def test_engine_prices_children_at_home():
    p = _household(40, 40, kids=True)
    cfg.CHILDREN = _kids(2, 5)
    child = cfg.ACA_CHILD_MONTHLY * 12
    adults = 2 * _rate(41)
    p.update_ages(41)
    assert p.quote_marketplace_cost(41, [41, 41], RICH)[0] == pytest.approx(adults)
    p.update_ages(42)   # first child born
    assert p.quote_marketplace_cost(42, [42, 42], RICH)[0] == pytest.approx(2 * _rate(42) + child)
    p.update_ages(45)   # both at home
    assert p.quote_marketplace_cost(45, [45, 45], RICH)[0] == pytest.approx(2 * _rate(45) + 2 * child)
    p.update_ages(60)   # first left at 18 (born 42)
    assert p.quote_marketplace_cost(60, [60, 60], RICH)[0] == pytest.approx(2 * _rate(60) + child)
    p.update_ages(63)   # both gone
    assert p.quote_marketplace_cost(63, [63, 63], RICH)[0] == pytest.approx(2 * _rate(63))


# ---------------------------------------------------------------------------
# 3. FPL by household size moves the cliff
# ---------------------------------------------------------------------------

def test_fpl_by_household_size():
    assert cfg.aca_fpl(1) == 15_650
    assert cfg.aca_fpl(2) == 21_150
    assert cfg.aca_fpl(4) == 32_150


def test_cliff_moves_with_household_size():
    magi = 4.0 * cfg.aca_fpl(2) + 1_000        # just over the couple's cliff
    members = [50, 50]
    full = 2 * _rate(50)
    couple = cfg.calculate_aca_premium_age_rated(magi, members, household_size=2)
    family = cfg.calculate_aca_premium_age_rated(magi, members, household_size=4)
    assert couple == pytest.approx(full)                      # no credit
    assert magi < 4.0 * cfg.aca_fpl(4)                        # family still under cliff
    assert family == pytest.approx(magi * cfg.aca_applicable_pct(magi / cfg.aca_fpl(4)))
    assert family < couple


# ---------------------------------------------------------------------------
# 4. Applicable-percentage interpolation (2026)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ratio,expected", [
    (0.80, 0.0210),
    (1.33, 0.0210),
    ((1.33 + 1.50) / 2, (0.0210 + 0.0419) / 2),
    (1.50, 0.0419),
    (1.75, (0.0419 + 0.0660) / 2),
    (2.00, 0.0660),
    (2.25, (0.0660 + 0.0844) / 2),
    (2.75, (0.0844 + 0.0996) / 2),
    (3.00, 0.0996),
    (3.60, 0.0996),
    (4.00, 0.0996),
])
def test_applicable_pct_interpolation(ratio, expected):
    assert cfg.aca_applicable_pct(ratio) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 5. Subsidy still wins for low MAGI
# ---------------------------------------------------------------------------

def test_subsidy_wins_for_low_magi():
    p = _household(60, 60)
    magi = 40_000.0
    ratio = magi / cfg.aca_fpl(2)
    prem, _ = p.quote_marketplace_cost(60, [60, 60], magi)
    assert prem == pytest.approx(magi * cfg.aca_applicable_pct(ratio))
    assert prem < 0.1 * (2 * _rate(60))
    # Below 133% FPL -> 2.10% of MAGI.
    low = 0.9 * cfg.aca_fpl(2)
    assert p.quote_marketplace_cost(60, [60, 60], low)[0] == pytest.approx(low * 0.021)


# ---------------------------------------------------------------------------
# 6. Out-of-pocket: not double-counted, booked once
# ---------------------------------------------------------------------------

def test_oop_netted_against_living_base_health_line():
    p = _household(55, 55)
    cfg.SPEND_HEALTH_MONTHLY = None
    assert p.quote_marketplace_cost(55, [55, 55], RICH)[1] == pytest.approx(3_000)
    cfg.SPEND_HEALTH_MONTHLY = 100        # $1,200/yr already in the base
    assert p.quote_marketplace_cost(55, [55, 55], RICH)[1] == pytest.approx(3_000 - 1_200)
    cfg.SPEND_HEALTH_MONTHLY = 400        # base already covers more than the OOP
    assert p.quote_marketplace_cost(55, [55, 55], RICH)[1] == 0.0


def test_oop_uses_marketplace_share_when_a_spouse_is_on_medicare():
    p = _household(66, 60)
    cfg.SPEND_HEALTH_MONTHLY = 100
    prem, oop = p.quote_marketplace_cost(66, [66, 60], RICH)
    assert prem == pytest.approx(_rate(60))             # only the 60-yr-old
    assert oop == pytest.approx(1_500 - 1_200 * 0.5)    # half the base line


def test_quote_includes_oop_and_stays_side_effect_free():
    p = _household(55, 55)
    cfg.SPEND_HEALTH_MONTHLY = None
    before = (p.total_aca_premiums, p.total_medicare_premiums)
    q = p.quote_health_insurance_cost(55, RICH)
    assert q == pytest.approx(2 * _rate(55) + 3_000)
    assert (p.total_aca_premiums, p.total_medicare_premiums) == before


def test_oop_is_booked_once_in_a_simulated_year():
    """Cash-funded year => MAGI 0 => premium 0, so the recorded marketplace
    total is exactly the OOP (Pass 1 + Pass 2 must not double it)."""
    p = _household(55, 55)
    cfg.SPEND_HEALTH_MONTHLY = None
    p.accounts = {}
    p.add_account(Account(name="cash", account_type=AccountType.CASH,
                          balance=1_000_000.0, owner="you"))
    p.set_retirement_baseline(1.0)
    p.ltc_needs_by_age = {}
    assert simulate_retirement_year(p, your_age=55, expenses=40_000.0, annual_return=0.0,
                                    inflation_factor=1.0, retirement_age=55)
    assert p.year_ordinary_income + p.year_investment_income == 0.0
    assert p.total_aca_premiums == pytest.approx(3_000)


def _cash_year_marketplace_total(partner_working):
    p = _household(55, 50)
    cfg.SPEND_HEALTH_MONTHLY = None
    p.accounts = {}
    p.add_account(Account(name="cash", account_type=AccountType.CASH,
                          balance=1_000_000.0, owner="you"))
    p.set_retirement_baseline(1.0)
    p.ltc_needs_by_age = {}
    assert simulate_retirement_year(p, your_age=55, expenses=40_000.0, annual_return=0.0,
                                    inflation_factor=1.0, retirement_age=55,
                                    partner_working=partner_working)
    return p.total_aca_premiums


def test_working_partner_employer_plan_replaces_marketplace():
    """While the partner still works, their employer plan covers the household:
    no marketplace premium or OOP. Charged again once they stop, or with the
    toggle off."""
    assert _cash_year_marketplace_total(partner_working=True) == 0.0
    assert _cash_year_marketplace_total(partner_working=False) > 0.0
    cfg.PARTNER_EMPLOYER_HEALTH_COVERAGE = False
    assert _cash_year_marketplace_total(partner_working=True) > 0.0


# ---------------------------------------------------------------------------
# 7. Medicare unchanged
# ---------------------------------------------------------------------------

def test_medicare_years_unchanged_by_toggle():
    for magi in (40_000.0, 300_000.0):
        p = _household(70, 70)
        on = p.quote_health_insurance_cost(70, magi, 1.3)
        cfg.MODEL_ACA_AGE_RATED = False
        off = p.quote_health_insurance_cost(70, magi, 1.3)
        assert on == off


def test_spouse_marketplace_cost_does_not_mask_medicare_floor():
    """Primary 66 on Medicare, spouse 61 on the marketplace: the all-in floor
    applies to the Medicare member's share, then the spouse's cost is added."""
    cfg.MODEL_HEALTHCARE_COST_FLOOR = True
    p = _household(66, 61)
    magi = 80_000.0  # floor share ($4,000) > one IRMAA premium (~$2,220)
    medicare = max(cfg.calculate_medicare_irmaa(magi, 1.0, enrollees=1),
                   cfg.calculate_healthcare_cost(66, is_retired=True, inflation_factor=1.0) / 2)
    premium, oop = p.quote_marketplace_cost(66, [66, 61], magi, 1.0)
    assert p.quote_health_insurance_cost(66, magi, 1.0) == pytest.approx(medicare + premium + oop)


# ---------------------------------------------------------------------------
# 8. Toggle OFF is byte-identical to the pre-change engine
# ---------------------------------------------------------------------------

def _legacy_quote(self, your_age, modified_agi, inflation_factor=1.0):
    """The pre-change AccountPortfolio.quote_health_insurance_cost, verbatim."""
    married = cfg.normalize_filing_status() == cfg._FILING_MFJ
    ages = [your_age] + ([self.current_partner_age] if married else [])
    n_adults = len(ages)
    if n_adults == 0:
        return 0.0
    on_medicare = sum(1 for a in ages if a >= cfg.MEDICARE_AGE)
    on_marketplace = n_adults - on_medicare
    total = 0.0
    if on_medicare:
        total += cfg.calculate_medicare_irmaa(
            modified_agi, inflation_factor, enrollees=on_medicare
        )
    if on_marketplace and cfg.ACA_ENABLED:
        household_aca = cfg.calculate_aca_premium(modified_agi) * inflation_factor
        total += household_aca * (on_marketplace / n_adults)
    if getattr(cfg, "MODEL_HEALTHCARE_COST_FLOOR", False) and on_medicare:
        all_in = cfg.calculate_healthcare_cost(
            your_age, is_retired=True, inflation_factor=inflation_factor
        ) * (on_medicare / n_adults)
        total = max(total, all_in)
    return total


@pytest.fixture
def full_run(monkeypatch):
    from utils import sim_runner as sr
    monkeypatch.setattr(sr, "_disk", lambda: None)   # never read/write the disk tier

    def run(overrides):
        sr.clear_cache(include_disk=False)
        r = sr.run_full_analysis(dict(overrides), n_simulations=120,
                                 target_retirement_age=42, scan_age_range=(40, 47, 3))
        return hashlib.sha256(pickle.dumps(r)).hexdigest()

    yield run
    sr.clear_cache(include_disk=False)


def _median_profile():
    from components.profile_picker import PROFILES
    return dict(PROFILES["Median US 25-year-old household"])


@pytest.mark.parametrize("profile", [dict, _median_profile], ids=["defaults", "median"])
def test_toggle_off_byte_identical_to_legacy_engine(full_run, monkeypatch, profile):
    base = profile()
    off = full_run({**base, "MODEL_ACA_AGE_RATED": False})
    on = full_run({**base, "MODEL_ACA_AGE_RATED": True})
    assert on != off, "the toggle must reach the engine through run_full_analysis"
    # The new knobs are inert when the toggle is off.
    knobs_moved = full_run({**base, "MODEL_ACA_AGE_RATED": False,
                            "ACA_BENCHMARK_MONTHLY_AT_40": 2_000, "ACA_CHILD_MONTHLY": 900,
                            "ACA_OOP_PER_PERSON_ANNUAL": 9_000,
                            "ACA_FPL_FIRST_PERSON": 99_000})
    assert knobs_moved == off
    # And toggle-off equals the pre-change quote implementation, byte for byte.
    monkeypatch.setattr(sim.AccountPortfolio, "quote_health_insurance_cost", _legacy_quote)
    legacy = full_run({**base, "MODEL_ACA_AGE_RATED": True})
    assert legacy == off
