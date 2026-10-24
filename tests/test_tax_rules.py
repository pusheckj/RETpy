"""Working-year taxes, filing-status tables, state tables and income wiring.

Pins the audit's taxes/income items:
  R1  take-home from real rules (federal by status + state table + FICA per
      earner), ONE function for the engine and the sidebar
  R3  every married-only table keyed by filing status
  R4  an unmarried couple files two Single returns, income tracked per owner
  R8  partner bonus/RSU/other income and your other income reach the engine;
      partner match honoured; partner Roth follows income, not marriage
  R12 a real per-state model (all 50 states + DC) with legacy values mapped
  R13 the employer match is capped by what you actually defer
  R14 the current year comes from the clock

Hand-computed figures use the official 2024 tables (the engine's frame).
"""
import datetime
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import state_tax_data  # noqa: E402
from retirement_sim import account_simulation as asim  # noqa: E402

INF = float("inf")


@pytest.fixture
def sandbox(monkeypatch):
    """A clean single-earner household; tests set what they need."""
    def setp(**kw):
        for k, v in kw.items():
            monkeypatch.setattr(cfg, k, v, raising=False)
    setp(YOUR_AGE=40, PARTNER_AGE=0, FILING_STATUS="Single", STATE_CHOICE="TX",
         YOUR_401K_CONTRIBUTION=0, YOUR_HSA_CONTRIBUTION=0, YOUR_BACKDOOR_ROTH=0,
         YOUR_401K_MATCH_PCT=0.0, YOUR_AFTER_TAX_401K_PCT=0.0, YOUR_OTHER_INCOME=0,
         PARTNER_SALARY=0, PARTNER_BONUS_AMOUNT=0, PARTNER_RSU_AMOUNT=0,
         PARTNER_OTHER_INCOME=0, PARTNER_401K_CONTRIBUTION=0, PARTNER_401K_MATCH_PCT=0.0,
         PARTNER_ROTH_CONTRIBUTION=0, YOUR_SALARY_GROWTH_RATE=0.0,
         PARTNER_SALARY_GROWTH_RATE=0.0,
         YOUR_COMPENSATION_BY_AGE={40: {"base": 150_000, "bonus": 0, "rsu_gross": 0,
                                        "total_comp": 150_000, "saved": 0}})
    return setp


def _comp(base, bonus=0, rsu=0, age=40, **extra):
    return {age: {"base": base, "bonus": bonus, "rsu_gross": rsu,
                  "total_comp": base + bonus + rsu, "saved": 0, **extra}}


# ---------------------------------------------------------------------------
# R1: take-home vs hand-computed examples
# ---------------------------------------------------------------------------
class TestTakeHomeByHand:
    def test_single_150k_texas(self):
        t = cfg.working_year_taxes(150_000, status="S", partner=False, state="TX")
        # 150,000 - 14,600 = 135,400 taxable:
        # 1,160 + 4,266 + 11,742.50 + 24% x 34,875 = 25,538.50
        assert t["federal"] == pytest.approx(25_538.50)
        assert t["state"] == 0.0
        assert t["fica"] == pytest.approx(150_000 * 0.0765)
        assert t["take_home"] == pytest.approx(150_000 - 25_538.50 - 11_475.0)
        assert t["take_home"] / 150_000 == pytest.approx(0.753, abs=0.001)

    def test_married_200k_california(self):
        t = cfg.working_year_taxes(120_000, 80_000, status="MFJ", partner=True, state="CA",
                                   your_age=40, partner_age=40)
        # Federal: 200,000 - 29,200 = 170,800 -> 2,320 + 8,532 + 16,830
        assert t["federal"] == pytest.approx(27_682.0)
        # CA 2024 joint: 200,000 - 11,080 = 188,920 ->
        # 215.12 + 589.72 + 1,179.68 + 1,874.52 + 2,358.40 + 9.3% x 47,708
        ca_income = 215.12 + 589.72 + 1_179.68 + 1_874.52 + 2_358.40 + 0.093 * 47_708
        assert t["state"] == pytest.approx(ca_income + 0.011 * 200_000)   # + SDI
        assert t["state_payroll"] == pytest.approx(2_200.0)
        assert t["fica"] == pytest.approx(200_000 * 0.0765)
        # Joint income tax is shared pro-rata to each person's income.
        assert t["you"]["federal"] == pytest.approx(27_682.0 * 0.6)

    def test_head_of_household_60k_north_carolina(self):
        t = cfg.working_year_taxes(60_000, status="HOH", partner=False, state="NC")
        # 60,000 - 21,900 = 38,100 -> 1,655 + 12% x 21,550
        assert t["federal"] == pytest.approx(1_655 + 2_586)
        assert t["state"] == pytest.approx((60_000 - 19_125) * 0.045)
        assert t["fica"] == pytest.approx(4_590.0)

    def test_high_earner_over_the_wage_base(self):
        t = cfg.working_year_taxes(250_000, status="S", partner=False, state="TX")
        ss = 168_600 * 0.062
        medicare = 250_000 * 0.0145 + 0.009 * (250_000 - 200_000)
        assert t["fica"] == pytest.approx(ss + medicare)

    def test_fica_per_earner_with_own_wage_base(self):
        t = cfg.working_year_taxes(200_000, 200_000, status="MFJ", partner=True, state="TX")
        ss = 2 * 168_600 * 0.062
        medicare = 400_000 * 0.0145 + 0.009 * (400_000 - 250_000)
        assert t["fica"] == pytest.approx(ss + medicare)

    def test_unmarried_couple_files_two_single_returns(self):
        t = cfg.working_year_taxes(90_000, 70_000, status="S", partner=True, state="TX")
        assert t["two_returns"]
        you = cfg.progressive_tax(cfg.get_federal_brackets("S"), 90_000 - 14_600)
        them = cfg.progressive_tax(cfg.get_federal_brackets("S"), 70_000 - 14_600)
        assert t["you"]["federal"] == pytest.approx(you)
        assert t["partner"]["federal"] == pytest.approx(them)
        one_return = cfg.progressive_tax(cfg.get_federal_brackets("S"), 160_000 - 14_600)
        assert t["federal"] < one_return - 8_000      # the audit's $35.1k vs $22.0k gap

    def test_unmarried_head_of_household_partner_is_single(self):
        t = cfg.working_year_taxes(60_000, 40_000, status="HOH", partner=True, state="TX")
        assert t["you"]["federal"] == pytest.approx(
            cfg.progressive_tax(cfg.get_federal_brackets("HOH"), 60_000 - 21_900))
        assert t["partner"]["federal"] == pytest.approx(
            cfg.progressive_tax(cfg.get_federal_brackets("S"), 40_000 - 14_600))

    def test_pretax_deferrals_lower_income_tax_but_401k_still_pays_fica(self):
        base = cfg.working_year_taxes(100_000, status="S", partner=False, state="TX")
        k = cfg.working_year_taxes(100_000, your_401k=20_000, status="S", partner=False, state="TX")
        h = cfg.working_year_taxes(100_000, your_hsa=4_000, status="S", partner=False, state="TX")
        assert k["federal"] == pytest.approx(
            cfg.progressive_tax(cfg.get_federal_brackets("S"), 100_000 - 20_000 - 14_600))
        assert k["fica"] == pytest.approx(base["fica"])                 # 401(k): FICA wages
        assert h["fica"] == pytest.approx(base["fica"] - 4_000 * 0.0765)  # payroll HSA: not
        assert k["take_home"] == pytest.approx(100_000 - 20_000 - k["total"])

    def test_state_quirks_pa_taxes_401k_and_ca_taxes_hsa(self):
        pa = cfg.working_year_taxes(100_000, your_401k=20_000, status="S", partner=False, state="PA")
        assert pa["state"] == pytest.approx(100_000 * 0.0307)
        ca_hsa = cfg.working_year_taxes(100_000, your_hsa=4_000, status="S", partner=False, state="CA")
        ca_none = cfg.working_year_taxes(100_000, status="S", partner=False, state="CA")
        assert ca_hsa["state"] == pytest.approx(ca_none["state"])

    def test_other_income_is_taxed_but_not_ficad(self):
        t = cfg.working_year_taxes(0, your_other=50_000, status="S", partner=False, state="TX")
        assert t["fica"] == 0.0
        assert t["federal"] == pytest.approx(
            cfg.progressive_tax(cfg.get_federal_brackets("S"), 50_000 - 14_600))


class TestUiShowsWhatTheEngineSimulates:
    def test_sidebar_taxes_equal_engine_year_one(self, sample_household):
        from utils import derived
        from utils import sim_runner as sr
        ov = dict(sample_household)
        ov["YOUR_COMPENSATION_BY_AGE"] = {
            int(ov["YOUR_AGE"]): {"base": ov["YOUR_BASE_SALARY"], "bonus": ov["YOUR_BONUS_AMOUNT"],
                                  "rsu_gross": ov["YOUR_RSU_AMOUNT"],
                                  "total_comp": ov["YOUR_BASE_SALARY"] + ov["YOUR_BONUS_AMOUNT"]
                                  + ov["YOUR_RSU_AMOUNT"], "saved": 0}}
        shown = derived.compute_taxes(ov)
        original = sr._apply_overrides(sr.build_config_overrides(ov))
        try:
            cf = asim.working_year_cashflow(cfg.YOUR_AGE)
        finally:
            sr._restore_overrides(original)
        assert shown["federal"] == pytest.approx(cf["federal"], rel=1e-9)
        assert shown["state"] == pytest.approx(cf["state"], rel=1e-9)
        assert shown["fica"] == pytest.approx(cf["fica"], rel=1e-9)

    def test_pretax_savings_lower_the_tax(self):
        from utils import derived
        ov = {"YOUR_BASE_SALARY": 100_000, "YOUR_401K_CONTRIBUTION": 20_000,
              "FILING_STATUS": "Single", "PARTNER_AGE": 0, "STATE_CHOICE": "TX"}
        assert derived.compute_taxes(ov)["total"] < derived.compute_taxes(ov, pretax_savings=False)["total"]


# ---------------------------------------------------------------------------
# R3: status-keyed tables
# ---------------------------------------------------------------------------
class TestFilingStatusTables:
    def test_ltcg_brackets(self):
        assert asim.calculate_ltcg_tax(10_000, 40_000, status="S") == pytest.approx(
            (50_000 - 47_025) * 0.15)
        assert asim.calculate_ltcg_tax(10_000, 40_000, status="MFJ") == 0.0
        # The audit's single filer: an $80k gain on top of $0 ordinary income.
        assert asim.calculate_ltcg_tax(80_000, 0, status="S") == pytest.approx(
            (80_000 - 47_025) * 0.15)

    def test_social_security_thresholds(self):
        # Single, $40k other income, $20k benefits -> provisional $50k
        single = cfg.calculate_taxable_social_security(20_000, 40_000, status="S")
        assert single == pytest.approx(min(0.85 * 20_000, 0.85 * (50_000 - 34_000) + 4_500))
        mfj = cfg.calculate_taxable_social_security(20_000, 40_000, status="MFJ")
        assert mfj < single

    def test_niit_threshold(self):
        assert cfg.calculate_niit(220_000, 50_000, status="S") == pytest.approx(20_000 * 0.038)
        assert cfg.calculate_niit(220_000, 50_000, status="MFJ") == 0.0

    def test_irmaa_individual_tiers(self, monkeypatch):
        monkeypatch.setattr(cfg, "PARTNER_AGE", 0)
        assert cfg.calculate_medicare_irmaa(150_000, enrollees=1, status="S") > \
            cfg.calculate_medicare_irmaa(150_000, enrollees=1, status="MFJ")
        # An unmarried couple: each person is tested on half the household MAGI.
        monkeypatch.setattr(cfg, "PARTNER_AGE", 66)
        monkeypatch.setattr(cfg, "FILING_STATUS", "Single")
        assert cfg.calculate_medicare_irmaa(200_000, enrollees=2) == \
            cfg.calculate_medicare_irmaa(100_000, enrollees=2, status="S")

    def test_roth_conversion_target_follows_status(self, monkeypatch):
        monkeypatch.setattr(cfg, "ROTH_CONVERSION_TARGET_BRACKET", None)
        assert cfg.roth_conversion_target("MFJ") == 94_300
        assert cfg.roth_conversion_target("S") == 47_150
        assert cfg.roth_conversion_target("HOH") == 63_100
        monkeypatch.setattr(cfg, "ROTH_CONVERSION_TARGET_BRACKET", 80_000)
        assert cfg.roth_conversion_target("S") == 80_000

    def test_roth_ira_phaseout(self):
        assert cfg.roth_ira_allowed(7_000, 100_000, "S") == 7_000
        assert cfg.roth_ira_allowed(7_000, 153_500, "S") == pytest.approx(3_500)
        assert cfg.roth_ira_allowed(7_000, 170_000, "S") == 0.0
        assert cfg.roth_ira_allowed(7_000, 235_000, "MFJ") == pytest.approx(3_500)


# ---------------------------------------------------------------------------
# R4: two returns in the engine (retirement draws on each owner's own return)
# ---------------------------------------------------------------------------
class TestTwoReturnsInTheEngine:
    def _couple(self, setp, status="Single"):
        setp(PARTNER_AGE=60, YOUR_AGE=60, FILING_STATUS=status, STATE_CHOICE="TX")
        p = asim.AccountPortfolio()
        p.update_ages(60)
        return p

    def test_partner_withdrawal_uses_partner_return(self, sandbox):
        p = self._couple(sandbox)
        assert p.two_returns
        p.year_ordinary_income = 80_000            # all yours
        tax = p.calculate_marginal_tax_on_income(20_000, owner="partner", retirement=True)
        assert tax == pytest.approx(0.10 * (20_000 - 14_600))
        assert p.year_partner_income == 20_000
        assert p._return_income("you") == 80_000

    def test_married_couple_stacks_on_one_return(self, sandbox):
        p = self._couple(sandbox, status="Married filing jointly")
        assert not p.two_returns
        p.year_ordinary_income = 80_000
        tax = p.calculate_marginal_tax_on_income(20_000, owner="partner")
        assert tax == pytest.approx(0.12 * 20_000)

    def test_working_partner_pay_is_the_stacking_base_in_retirement(self, sandbox):
        sandbox(PARTNER_AGE=55, YOUR_AGE=60, FILING_STATUS="Married filing jointly")
        p = asim.create_initial_portfolio()
        asim.simulate_retirement_year(p, 62, 50_000, 0.0, partner_income=40_000,
                                      partner_magi=60_000, partner_working=True)
        assert p.year_ordinary_income >= 60_000


# ---------------------------------------------------------------------------
# R8 / R13: income wiring and the match cap in the engine
# ---------------------------------------------------------------------------
class TestIncomeWiringAndMatch:
    def test_match_is_capped_by_the_deferral(self, sandbox):
        sandbox(YOUR_401K_CONTRIBUTION=2_000, YOUR_401K_MATCH_PCT=0.04,
                YOUR_COMPENSATION_BY_AGE=_comp(100_000))
        cf = asim.working_year_cashflow(40)
        assert cf["your_match"] == 2_000           # not 4% x 100k = 4,000
        p = asim.create_initial_portfolio()
        before = p.accounts["your_401k"].balance
        asim.simulate_accumulation_year(p, 40, 0.0)
        assert p.accounts["your_401k"].balance - before == pytest.approx(4_000)

    def test_full_match_when_deferring_enough(self, sandbox):
        sandbox(YOUR_401K_CONTRIBUTION=10_000, YOUR_401K_MATCH_PCT=0.04,
                YOUR_COMPENSATION_BY_AGE=_comp(100_000))
        assert asim.working_year_cashflow(40)["your_match"] == 4_000

    def test_deferral_cannot_exceed_pay(self, sandbox):
        sandbox(YOUR_401K_CONTRIBUTION=20_000, YOUR_COMPENSATION_BY_AGE=_comp(5_000))
        assert asim.working_year_cashflow(40)["your_401k"] == 5_000

    def test_partner_bonus_rsu_other_and_match_reach_the_engine(self, sandbox):
        sandbox(PARTNER_AGE=40, FILING_STATUS="Married filing jointly",
                PARTNER_SALARY=80_000, PARTNER_401K_CONTRIBUTION=8_000,
                PARTNER_401K_MATCH_PCT=0.05)
        plain = asim.working_year_cashflow(40)
        assert plain["partner_match"] == 4_000
        sandbox(PARTNER_BONUS_AMOUNT=10_000, PARTNER_RSU_AMOUNT=20_000,
                PARTNER_OTHER_INCOME=5_000)
        more = asim.working_year_cashflow(40)
        assert more["partner_wages"] == 110_000
        assert more["partner_take_home"] > plain["partner_take_home"] + 15_000
        p = asim.create_initial_portfolio()
        before = p.accounts["partner_401k"].balance
        asim.simulate_accumulation_year(p, 40, 0.0)
        assert p.accounts["partner_401k"].balance - before == pytest.approx(12_000)

    def test_your_other_income_reaches_the_engine(self, sandbox):
        base = asim.working_year_cashflow(40)["your_take_home"]
        sandbox(YOUR_OTHER_INCOME=10_000)
        assert asim.working_year_cashflow(40)["your_take_home"] > base + 5_000

    def test_partner_roth_follows_income_not_marriage(self, sandbox):
        sandbox(PARTNER_AGE=40, FILING_STATUS="Married filing jointly",
                PARTNER_SALARY=40_000, PARTNER_ROTH_CONTRIBUTION=7_000,
                YOUR_COMPENSATION_BY_AGE=_comp(60_000), YEARS_UNTIL_WEDDING=0)
        assert asim.working_year_cashflow(40)["partner_roth"] == 7_000
        sandbox(YOUR_COMPENSATION_BY_AGE=_comp(300_000))
        assert asim.working_year_cashflow(40)["partner_roth"] == 0.0

    def test_explicit_after_tax_is_still_honoured(self, sandbox):
        sandbox(YOUR_COMPENSATION_BY_AGE=_comp(150_000, after_tax=99_000))
        assert asim.working_year_cashflow(40)["your_take_home"] == 99_000

    def test_take_home_drives_the_brokerage_sweep(self, sandbox):
        sandbox(SPEND_RENT_MONTHLY=0)
        cf = asim.working_year_cashflow(40)
        p = asim.create_initial_portfolio()
        before = p.get_total_balance()
        asim.simulate_accumulation_year(p, 40, 0.0)
        living = cfg.calculate_annual_expenses(40, 1.0, childcare_factor=1.0)
        assert p.get_total_balance() - before == pytest.approx(
            max(0.0, cf["your_take_home"] - living), abs=1.0)


# ---------------------------------------------------------------------------
# R12: state tables
# ---------------------------------------------------------------------------
class TestStateTables:
    def test_every_state_and_dc_present(self):
        assert len(state_tax_data.STATES) == 51
        assert "DC" in state_tax_data.STATES
        assert set(state_tax_data.NO_INCOME_TAX) == {
            "AK", "FL", "NV", "NH", "SD", "TN", "TX", "WA", "WY"}

    @pytest.mark.parametrize("code", sorted(state_tax_data.STATES))
    def test_row_is_well_formed(self, code):
        row = state_tax_data.STATES[code]
        assert row["year"] >= 2024
        assert row["confidence"] in ("high", "medium", "approx")
        for status in ("S", "MFJ", "HOH"):
            brackets = row["brackets"][status]
            limits = [b for b, _ in brackets]
            rates = [r for _, r in brackets]
            assert limits[-1] == INF
            assert limits == sorted(limits) and len(set(limits)) == len(limits)
            assert rates == sorted(rates), "rates must not fall as income rises"
            assert all(0.0 <= r < 0.15 for r in rates)
            rules = cfg.state_tax_rules(code, status)
            assert rules["deduction"] >= 0

    def test_ca_engine_matches_the_ca_joint_table(self):
        model = asim._select_state_tax_brackets("MFJ", people=2)
        rules = cfg.state_tax_rules("CA", "MFJ")
        assert rules["deduction"] == cfg.CA_STANDARD_DEDUCTION_MFJ_2024
        for income in (50_000, 200_000, 2_000_000):
            assert model.calculate_tax(income) == pytest.approx(
                asim.CaliforniaTaxBrackets().calculate_tax(income))

    def test_ca_2024_refresh_is_within_rounding_of_the_old_table(self):
        old_2023 = [(20_824, .01), (49_368, .02), (77_918, .04), (108_162, .06),
                    (136_700, .08), (698_274, .093), (837_922, .103),
                    (1_396_542, .113), (INF, .123)]
        new = cfg.state_tax_rules("CA", "MFJ")["brackets"]
        for income in (60_000, 150_000, 400_000):
            delta = cfg.progressive_tax(new, income) - cfg.progressive_tax(old_2023, income)
            assert -250 < delta <= 0

    @pytest.mark.parametrize("value,code", [
        ("CA", "CA"), ("ca", "CA"), ("California", "CA"), ("Texas", "TX"),
        ("No state tax", "No state tax"), ("None", "No state tax"),
        ("Other", "Other"), ("Other (use marginal rate)", "Other"),
        ("Another state (flat rate)", "Other"), ("Narnia", "CA"),
    ])
    def test_legacy_values_resolve(self, value, code):
        assert cfg.resolve_state_code(value) == code

    def test_legacy_values_load_into_the_widgets(self):
        from utils import widget_sync as ws
        from utils import state_choice as sc
        assert ws._state_code_to_label("CA") == "California"
        assert ws._state_code_to_label("No state tax") == sc.NONE_LABEL
        assert ws._state_code_to_label("Other") == sc.FLAT_LABEL
        assert ws._state_code_to_label("NY") == "New York"
        for label in sc.OPTIONS:
            assert sc.label_for(sc.code_for(label)) == label

    def test_social_security_rules(self, monkeypatch):
        monkeypatch.setattr(cfg, "PARTNER_AGE", 0)
        monkeypatch.setattr(cfg, "FILING_STATUS", "Single")
        for code, taxed in (("CA", False), ("MT", True), ("UT", True), ("IL", False)):
            monkeypatch.setattr(cfg, "STATE_CHOICE", code)
            p = asim.AccountPortfolio()
            p.update_ages(70)
            p.year_ordinary_income = 60_000
            monkeypatch.setattr(cfg, "STATE_CHOICE", "TX")      # same, no state tax
            federal_only = asim.AccountPortfolio()
            federal_only.update_ages(70)
            federal_only.year_ordinary_income = 60_000
            monkeypatch.setattr(cfg, "STATE_CHOICE", code)
            gap = (p.quote_marginal_tax_on_income(10_000, is_state_taxable=False)
                   - federal_only.quote_marginal_tax_on_income(10_000, is_state_taxable=False))
            assert (gap > 0) == taxed, code

    def test_retirement_income_exclusions(self, monkeypatch):
        monkeypatch.setattr(cfg, "PARTNER_AGE", 0)
        monkeypatch.setattr(cfg, "FILING_STATUS", "Single")

        def state_tax(code, age, amount=30_000):
            monkeypatch.setattr(cfg, "STATE_CHOICE", code)
            p = asim.AccountPortfolio()
            p.update_ages(age)
            p.year_ordinary_income = 50_000
            monkeypatch.setattr(cfg, "STATE_CHOICE", "TX")
            fed = asim.AccountPortfolio()
            fed.update_ages(age)
            fed.year_ordinary_income = 50_000
            return (p.calculate_marginal_tax_on_income(amount, retirement=True)
                    - fed.calculate_marginal_tax_on_income(amount, retirement=True))

        assert state_tax("IL", 45) == pytest.approx(0.0)            # all retirement income
        assert state_tax("PA", 62) == pytest.approx(0.0)            # after 59.5
        assert state_tax("PA", 55) == pytest.approx(30_000 * 0.0307)
        ny = state_tax("NY", 62)                                     # $20k excluded
        assert ny == pytest.approx(10_000 * 0.055)


# ---------------------------------------------------------------------------
# R14 and legacy profiles
# ---------------------------------------------------------------------------
class TestYearAndLegacyProfiles:
    def test_current_year_comes_from_the_clock(self):
        assert cfg.CURRENT_YEAR == datetime.date.today().year

    def test_saved_current_year_is_ignored(self):
        from utils.config_builder import build_config_overrides
        assert "CURRENT_YEAR" not in build_config_overrides({"CURRENT_YEAR": 2019})

    def test_retired_keys_are_dropped_quietly(self):
        from utils.config_builder import build_config_overrides
        out = build_config_overrides({"PARTNER_ESTIMATED_TAX_RATE": 0.25, "PARTNER_401K_MATCH": 0})
        assert out == {}

    def test_auto_70pct_take_home_is_stripped_but_explicit_is_kept(self):
        from utils.config_builder import build_config_overrides
        comp = {30: {"base": 100_000, "bonus": 0, "rsu_gross": 0, "total_comp": 100_000,
                     "after_tax": 70_000, "saved": 7_000},
                31: {"base": 100_000, "bonus": 0, "rsu_gross": 0, "total_comp": 100_000,
                     "after_tax": 66_100, "saved": 7_000}}
        out = build_config_overrides({"YOUR_COMPENSATION_BY_AGE": comp})["YOUR_COMPENSATION_BY_AGE"]
        assert "after_tax" not in out[30]
        assert out[31]["after_tax"] == 66_100

    def test_legacy_joint_roth_target_follows_the_status(self):
        from utils.config_builder import build_config_overrides
        single = build_config_overrides({"FILING_STATUS": "Single",
                                         "ROTH_CONVERSION_TARGET_BRACKET": 94_300})
        assert single["ROTH_CONVERSION_TARGET_BRACKET"] is None
        mfj = build_config_overrides({"FILING_STATUS": "Married filing jointly",
                                      "ROTH_CONVERSION_TARGET_BRACKET": 94_300})
        assert mfj["ROTH_CONVERSION_TARGET_BRACKET"] == 94_300
        custom = build_config_overrides({"FILING_STATUS": "Single",
                                         "ROTH_CONVERSION_TARGET_BRACKET": 60_000})
        assert custom["ROTH_CONVERSION_TARGET_BRACKET"] == 60_000

    def test_config_stays_plain_data(self):
        """The browser receives cfg_snapshot(); nothing new may break it."""
        from retirement_sim import mc_jobs, mc_parallel
        snap = mc_parallel.cfg_snapshot()
        assert mc_jobs.loads(mc_jobs.dumps(snap)).keys() == snap.keys()
