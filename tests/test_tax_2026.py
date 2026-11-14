"""2026 tax figures, hand-computed from the primary sources.

Sources (docs/data_sources/2026_verification.md): Rev. Proc. 2025-32 (federal
brackets, standard deduction, LTCG), 26 U.S.C. 151(d)(5)(C) (OBBBA senior
deduction), CMS 2026 Part B fact sheet (IRMAA), Rev. Proc. 2025-25 (ACA
applicable percentages), FTB Tax News October 2026 (California).

Every test pins CURRENT_YEAR to 2026 so the 2025-2028 senior-deduction window
does not depend on the clock.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import account_simulation as asim  # noqa: E402


@pytest.fixture(autouse=True)
def year_2026(monkeypatch):
    monkeypatch.setattr(cfg, "CURRENT_YEAR", 2026)
    monkeypatch.setattr(cfg, "MODEL_SENIOR_DEDUCTION", True)


def _fed(wages, status, **kw):
    kw.setdefault("partner", False)
    kw.setdefault("state", "TX")
    kw.setdefault("your_age", 40)
    kw.setdefault("children_under_17", 0)
    return cfg.working_year_taxes(wages, status=status, **kw)


# ---------------------------------------------------------------------------
# Federal brackets and standard deduction
# ---------------------------------------------------------------------------
class TestFederal2026:
    def test_single_80k(self):
        # 80,000 - 16,100 = 63,900: 1,240 + 4,560 + 22% x 13,500 = 8,770
        assert _fed(80_000, "S")["federal"] == pytest.approx(8_770.0)

    def test_mfj_250k(self):
        # 250,000 - 32,200 = 217,800: 2,480 + 9,120 + 24,332 + 24% x 6,400 = 37,468
        t = _fed(125_000, "MFJ", partner=True, partner_wages=125_000, partner_age=40)
        assert t["federal"] == pytest.approx(37_468.0)

    def test_hoh_60k_two_kids(self):
        # 60,000 - 24,150 = 35,850: 1,770 + 12% x 18,150 = 3,948. The $4,400 child
        # credit wipes it out; the refundable rest is 452 (< 2 x 1,700 and
        # < 15% x 57,500), so federal tax is -452.
        assert _fed(60_000, "HOH", children_under_17=0)["federal"] == pytest.approx(3_948.0)
        assert _fed(60_000, "HOH", children_under_17=2)["federal"] == pytest.approx(-452.0)

    def test_hoh_schedule_is_its_own(self):
        hoh = cfg.get_federal_brackets("HOH")
        single = cfg.get_federal_brackets("S")
        assert hoh[3][0] == 201_750 and single[3][0] == 201_775
        assert hoh[4][0] == 256_200 and single[4][0] == 256_225

    def test_standard_deductions(self):
        assert cfg.STANDARD_DEDUCTION_BY_STATUS == {"MFJ": 32_200, "S": 16_100, "HOH": 24_150}
        # The old names still import and hold the 2026 values.
        assert cfg.STANDARD_DEDUCTION_MFJ_2024 == 32_200
        assert cfg.CA_STANDARD_DEDUCTION_MFJ_2024 == 11_800

    def test_ltcg_thresholds(self):
        assert cfg.LTCG_BRACKETS_BY_STATUS["MFJ"][:2] == [(98_900, 0.0), (613_700, 0.15)]
        assert cfg.LTCG_BRACKETS_BY_STATUS["S"][:2] == [(49_450, 0.0), (545_500, 0.15)]
        assert cfg.LTCG_BRACKETS_BY_STATUS["HOH"][:2] == [(66_200, 0.0), (579_600, 0.15)]
        # 10,000 of gains on 95,000 of joint taxable income: 3,900 at 0%, 6,100 at 15%.
        assert asim.calculate_ltcg_tax(10_000, 95_000, "MFJ") == pytest.approx(915.0)

    def test_roth_target_is_the_12pct_top(self):
        assert cfg.ROTH_CONVERSION_TARGET_BY_STATUS == {"MFJ": 100_800, "S": 50_400,
                                                        "HOH": 67_450}

    def test_engine_default_brackets_are_the_2026_joint_table(self):
        assert asim.TaxBrackets().brackets == cfg.FEDERAL_BRACKETS_BY_STATUS["MFJ"]


# ---------------------------------------------------------------------------
# OBBBA senior deduction (2025-2028)
# ---------------------------------------------------------------------------
class TestSeniorDeduction:
    def test_full_amount_below_the_phaseout(self):
        assert cfg.senior_deduction("MFJ", [66, 67], 150_000) == pytest.approx(12_000)
        assert cfg.senior_deduction("S", [70], 75_000) == pytest.approx(6_000)

    def test_phaseout_is_6pct_per_person(self):
        # 2 x (6,000 - 6% x 50,000) = 6,000
        assert cfg.senior_deduction("MFJ", [66, 67], 200_000) == pytest.approx(6_000)
        # 6,000 - 6% x 25,000 = 4,500
        assert cfg.senior_deduction("S", [70], 100_000) == pytest.approx(4_500)
        assert cfg.senior_deduction("HOH", [70], 100_000) == pytest.approx(4_500)
        assert cfg.senior_deduction("MFJ", [66, 67], 250_000) == 0.0
        assert cfg.senior_deduction("S", [70], 175_000) == 0.0

    def test_only_people_65_plus(self):
        assert cfg.senior_deduction("MFJ", [66, 60], 100_000) == pytest.approx(6_000)
        assert cfg.senior_deduction("MFJ", [64, 60], 100_000) == 0.0

    def test_sunset_after_2028(self):
        assert cfg.senior_deduction("MFJ", [66, 66], 100_000, years_from_start=2) > 0
        assert cfg.senior_deduction("MFJ", [66, 66], 100_000, years_from_start=3) == 0.0

    def test_not_indexed_so_it_shrinks_in_real_terms(self):
        infl = (1 + cfg.EXPECTED_INFLATION) ** 2
        assert cfg.senior_deduction("S", [70], None, years_from_start=2) == pytest.approx(6_000 / infl)
        # Phase-out start shrinks too: 6,000/infl - 6% x (100,000 - 75,000/infl)
        expected = 6_000 / infl - 0.06 * (100_000 - 75_000 / infl)
        assert cfg.senior_deduction("S", [70], 100_000, years_from_start=2) == pytest.approx(expected)

    def test_switch(self, monkeypatch):
        monkeypatch.setattr(cfg, "MODEL_SENIOR_DEDUCTION", False)
        assert cfg.senior_deduction("MFJ", [66, 67], 100_000) == 0.0

    def test_stacks_on_the_65_plus_add_on(self):
        # 32,200 + 2 x 1,650 + 2 x 6,000
        assert cfg.standard_deduction_for_return("MFJ", [66, 67], 100_000) == pytest.approx(47_500)
        # 16,100 + 2,050 + 6,000
        assert cfg.standard_deduction_for_return("S", [66], 50_000) == pytest.approx(24_150)

    def test_working_year_return_uses_its_agi(self):
        # Single 66-year-old, 100,000 wages: 100,000 - (16,100 + 2,050 + 4,500)
        # = 77,350 taxable: 1,240 + 4,560 + 22% x 26,950 = 11,729
        t = _fed(100_000, "S", your_age=66)
        assert t["federal"] == pytest.approx(11_729.0)

    def test_engine_marginal_tax_sees_the_phaseout(self, monkeypatch):
        for k, v in {"YOUR_AGE": 66, "PARTNER_AGE": 66, "FILING_STATUS": "Married filing jointly",
                     "STATE_CHOICE": "TX", "RETIREMENT_STATE_CHOICE": None}.items():
            monkeypatch.setattr(cfg, k, v, raising=False)
        pf = asim.AccountPortfolio()
        pf.reset_yearly_income()
        pf.update_ages(66)
        pf.year_ordinary_income = 140_000.0
        federal, state = pf._marginal_tax_parts(20_000)
        # Before: 140,000 - 47,500 = 92,500 -> 10,604. After: MAGI 160,000, senior
        # 2 x 5,400 -> deduction 46,300 -> 113,700 taxable -> 14,438.
        assert federal == pytest.approx(14_438 - 10_604)
        assert state == 0.0


# ---------------------------------------------------------------------------
# Medicare IRMAA 2026
# ---------------------------------------------------------------------------
class TestIrmaa2026:
    @pytest.mark.parametrize("magi,status,tier", [
        (0, "MFJ", 0), (218_000, "MFJ", 0), (218_001, "MFJ", 1), (274_001, "MFJ", 2),
        (410_000, "MFJ", 3), (410_001, "MFJ", 4), (749_999, "MFJ", 4), (750_000, "MFJ", 5),
        (109_000, "S", 0), (109_001, "S", 1), (171_001, "S", 3), (205_001, "S", 4),
        (500_000, "S", 5), (150_000, "HOH", 2),
    ])
    def test_tier_lookup(self, magi, status, tier):
        assert cfg.medicare_irmaa_tier(magi, status) == tier

    def test_standard_tier_premium(self):
        # (202.90 Part B + 200 Part D/Medigap estimate) x 12
        assert cfg.calculate_medicare_irmaa(100_000, enrollees=1, status="S") == pytest.approx(4_834.80)

    def test_surcharge_tier_premium(self):
        # Tier 2: Part B 405.80 + Part D surcharge 37.50 + 200, two people
        assert cfg.calculate_medicare_irmaa(300_000, enrollees=2, status="MFJ") == pytest.approx(
            (405.80 + 37.50 + 200) * 12 * 2)

    def test_couple_reference_premium(self):
        assert cfg.MEDICARE_MONTHLY_PREMIUM == pytest.approx(2 * (202.90 + 200))
        assert cfg.MEDICARE_MONTHLY_PREMIUM > 2 * cfg.MEDICARE_PART_B_STANDARD_MONTHLY


# ---------------------------------------------------------------------------
# ACA 2026: applicable percentages and the 400% cliff
# ---------------------------------------------------------------------------
class TestAca2026:
    @pytest.mark.parametrize("ratio,pct", [
        (1.00, 0.0210), (1.3299, 0.0210), (1.33, 0.0314), (1.415, 0.03665), (1.50, 0.0419),
        (1.75, 0.05395), (2.00, 0.0660), (2.25, 0.0752), (2.75, 0.0920), (3.00, 0.0996),
        (3.50, 0.0996),
    ])
    def test_linear_inside_each_band(self, ratio, pct):
        assert cfg.aca_applicable_pct(ratio) == pytest.approx(pct)

    def test_cliff_at_400_pct(self, monkeypatch):
        monkeypatch.setattr(cfg, "ACA_BENCHMARK_MONTHLY_AT_40", 625)
        fpl2 = cfg.aca_fpl(2)
        assert fpl2 == 21_150
        full = sum(cfg.aca_member_full_price_annual(a) for a in (60, 60))
        assert full == pytest.approx(2 * 625 * 2.714 / 1.278 * 12)
        below = cfg.calculate_aca_premium_age_rated(4 * fpl2 - 1, [60, 60], 2)
        assert below == pytest.approx((4 * fpl2 - 1) * 0.0996)
        assert cfg.calculate_aca_premium_age_rated(4 * fpl2, [60, 60], 2) == pytest.approx(full)

    def test_legacy_path_uses_the_2026_table(self):
        magi = cfg.FPL_FAMILY_OF_4 * 2.0
        assert cfg.FPL_FAMILY_OF_4 == 32_150
        assert cfg.calculate_aca_premium(magi) == pytest.approx(
            min(magi * 0.0660, cfg.full_price_aca_annual()))

    def test_benchmark(self):
        assert cfg.ACA_BENCHMARK_MONTHLY_AT_40 == 625


# ---------------------------------------------------------------------------
# California 2026
# ---------------------------------------------------------------------------
def _ca(status, taxable, people=None, seniors=0, dependents=0, agi=None):
    rules = cfg.state_tax_rules("CA", status, people=people)
    return cfg.state_income_tax(rules, taxable, seniors, dependents, agi)


class TestCalifornia2026:
    def test_deductions(self):
        assert cfg.state_tax_rules("CA", "S")["deduction"] == 5_900
        assert cfg.state_tax_rules("CA", "MFJ")["deduction"] == 11_800
        assert cfg.state_tax_rules("CA", "HOH")["deduction"] == 11_800

    def test_single_80k_wages(self):
        # 80,000 - 5,900 = 74,100: 114.56 + 314.02 + 628.16 + 998.22 + 8% x 14,602
        # = 3,223.12, less the $158 personal credit = 3,065.12, plus 1.1% SDI.
        t = cfg.working_year_taxes(80_000, status="S", partner=False, state="CA",
                                   your_age=40, children_under_17=0)
        assert t["state"] == pytest.approx(3_065.12 + 880.0)

    def test_mfj_two_personal_credits(self):
        # 229.12 + 628.04 + 1,256.32 + 1,996.44 + 2,511.84 + 9.3% x 49,606 = 11,235.118
        assert _ca("MFJ", 200_000) == pytest.approx(11_235.118 - 316)

    def test_hoh_schedule_and_dependent_credits(self):
        # HOH taxable 80,000: 229.27 + 627.78 + 628.08 + 6% x 9,982 = 2,084.05,
        # less 158 + 2 x 491.
        assert _ca("HOH", 80_000, dependents=2) == pytest.approx(2_084.05 - 1_140)
        # Credits are nonrefundable.
        assert _ca("HOH", 30_000, dependents=2) == 0.0

    def test_senior_credit(self):
        # Single 70: 114.56 + 314.02 + 628.16 + 6% x 7,139 = 1,485.08, less 158 + 158
        assert _ca("S", 50_000, seniors=1) == pytest.approx(1_485.08 - 316)

    def test_credit_phaseout(self):
        # AGI 305,900 is 45,122 over 260,778 -> 19 steps of 2,500 -> each credit -$114.
        bracket = 74_675.27 - 34_723.318 - 7_912.254 - 28_728.816 + 0.093 * (300_000 - 75_197)
        assert _ca("S", 300_000) == pytest.approx(bracket - 44)
        # Far above the threshold the credit is gone.
        assert _ca("S", 400_000) == pytest.approx(cfg.progressive_tax(
            cfg.state_tax_rules("CA", "S")["brackets"], 400_000))

    def test_behavioral_health_services_tax(self):
        # FTB: 74,675.27 at 768,213, then 12.3%; plus 1% above $1M.
        expected = 74_675.27 + 0.123 * (1_200_000 - 768_213) + 0.01 * 200_000
        assert _ca("S", 1_200_000) == pytest.approx(expected)
        assert _ca("MFJ", 1_000_000) == pytest.approx(cfg.progressive_tax(
            cfg.state_tax_rules("CA", "MFJ")["brackets"], 1_000_000))

    def test_engine_state_model_tracks_seniors_and_children(self, monkeypatch):
        for k, v in {"YOUR_AGE": 64, "PARTNER_AGE": 64, "FILING_STATUS": "Married filing jointly",
                     "STATE_CHOICE": "CA", "RETIREMENT_STATE_CHOICE": None,
                     "CHILDREN": []}.items():
            monkeypatch.setattr(cfg, k, v, raising=False)
        pf = asim.AccountPortfolio()
        pf.update_ages(64)
        assert pf.ca_tax_brackets.seniors == 0
        pf.update_ages(65)
        assert pf.ca_tax_brackets.seniors == 2
        assert pf.ca_tax_brackets.calculate_tax(50_000) == pytest.approx(_ca("MFJ", 50_000, seniors=2))
