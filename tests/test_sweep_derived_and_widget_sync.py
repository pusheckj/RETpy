"""Function-level coverage for ``ui/utils/derived.py`` compute_* helpers and the
``ui/utils/widget_sync.py`` mapping tables (function-gap sweep, 2026-08-22).

``compute_total_income`` / ``compute_taxes`` / ``compute_expenses_today`` drive
every "here's what your inputs imply" caption in the sidebar and feed
``compute_disposable`` -> ``auto_allocate_savings``, but had no direct test.
The widget_sync mapping tables had no structural test either, so a typo'd
override key would silently make a widget un-restorable after a profile load.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest

from retirement_sim import config as cfg
from utils import derived
from utils import widget_sync as ws
from utils.config_builder import _UI_ONLY_KEYS


class FakeSt:
    def __init__(self, **state):
        self.session_state = dict(state)


# ---------------------------------------------------------------------------
# compute_total_income
# ---------------------------------------------------------------------------
class TestComputeTotalIncome:
    def test_empty_is_zero(self):
        assert derived.compute_total_income({}) == 0

    def test_sums_every_component_for_both_earners(self):
        o = {
            "YOUR_BASE_SALARY": 100_000, "YOUR_BONUS_AMOUNT": 10_000,
            "YOUR_RSU_AMOUNT": 50_000, "YOUR_OTHER_INCOME": 1_000,
            "PARTNER_BASE_SALARY": 80_000, "PARTNER_BONUS_AMOUNT": 5_000,
            "PARTNER_RSU_AMOUNT": 0, "PARTNER_OTHER_INCOME": 2_000,
        }
        assert derived.compute_total_income(o) == 248_000

    def test_quick_income_fallback_only_when_breakdown_is_empty(self):
        assert derived.compute_total_income({"HOUSEHOLD_INCOME_QUICK": 150_000}) == 150_000
        # Breakdown wins; the quick number is NOT added on top.
        o = {"HOUSEHOLD_INCOME_QUICK": 150_000, "YOUR_BASE_SALARY": 90_000}
        assert derived.compute_total_income(o) == 90_000

    def test_garbage_components_are_ignored_not_fatal(self):
        o = {"YOUR_BASE_SALARY": None, "YOUR_BONUS_AMOUNT": "abc",
             "YOUR_RSU_AMOUNT": 25_000}
        assert derived.compute_total_income(o) == 25_000

    def test_returns_int(self):
        assert isinstance(derived.compute_total_income({"YOUR_BASE_SALARY": 10.9}), int)


# ---------------------------------------------------------------------------
# compute_taxes
# ---------------------------------------------------------------------------
class TestComputeTaxes:
    def test_zero_income_is_all_zero(self):
        t = derived.compute_taxes({})
        assert t == {"federal": 0.0, "state": 0.0, "fica": 0.0,
                     "total": 0.0, "effective_rate": 0.0}

    def test_negative_income_is_all_zero(self):
        assert derived.compute_taxes({"YOUR_BASE_SALARY": -50_000})["total"] == 0.0

    def test_total_is_the_sum_and_rate_is_consistent(self):
        t = derived.compute_taxes({"YOUR_BASE_SALARY": 200_000})
        assert t["total"] == pytest.approx(t["federal"] + t["state"] + t["fica"])
        assert t["effective_rate"] == pytest.approx(t["total"] / 200_000)
        assert 0.0 < t["effective_rate"] < 0.6

    def test_federal_matches_the_engines_bracket_math(self):
        """The rough UI estimate must agree with the engine's own MFJ schedule."""
        income = 250_000
        t = derived.compute_taxes({"YOUR_BASE_SALARY": income, "FILING_STATUS": "MFJ"})
        from retirement_sim.account_simulation import _progressive_tax
        taxable = income - cfg.STANDARD_DEDUCTION_MFJ_2024
        assert t["federal"] == pytest.approx(
            _progressive_tax(cfg.get_federal_brackets("MFJ"), taxable))

    @pytest.mark.parametrize("status", ["MFJ", "Married filing jointly", "S", "Single",
                                        "HOH", "Head of household", None, "garbage"])
    def test_filing_status_forms_are_tolerated(self, status):
        t = derived.compute_taxes({"YOUR_BASE_SALARY": 150_000, "FILING_STATUS": status})
        assert t["federal"] > 0

    def test_single_pays_more_federal_than_mfj(self):
        mfj = derived.compute_taxes({"YOUR_BASE_SALARY": 200_000, "FILING_STATUS": "MFJ"})
        single = derived.compute_taxes({"YOUR_BASE_SALARY": 200_000, "FILING_STATUS": "Single"})
        assert single["federal"] > mfj["federal"]
        assert single["state"] > mfj["state"]

    def test_unknown_status_defaults_to_mfj(self):
        a = derived.compute_taxes({"YOUR_BASE_SALARY": 200_000, "FILING_STATUS": "garbage"})
        b = derived.compute_taxes({"YOUR_BASE_SALARY": 200_000, "FILING_STATUS": "MFJ"})
        assert a == b

    @pytest.mark.parametrize("choice", ["No state tax", "None"])
    def test_no_state_tax_choices(self, choice):
        assert derived.compute_taxes({"YOUR_BASE_SALARY": 200_000,
                                      "STATE_CHOICE": choice})["state"] == 0.0

    def test_state_code_matches_what_sec_taxes_stores(self):
        """sec_taxes._STATE_TO_CODE emits these codes; compute_taxes must know them."""
        from components.sec_taxes import _STATE_TO_CODE
        for code in _STATE_TO_CODE.values():
            t = derived.compute_taxes({"YOUR_BASE_SALARY": 200_000, "STATE_CHOICE": code})
            if code == "No state tax":
                assert t["state"] == 0.0
            else:
                assert t["state"] > 0.0

    def test_other_state_uses_flat_estimate(self):
        income = 200_000
        t = derived.compute_taxes({"YOUR_BASE_SALARY": income, "STATE_CHOICE": "Other"})
        expected = (income - cfg.STANDARD_DEDUCTION_MFJ_2024) * 0.05
        assert t["state"] == pytest.approx(expected)

    def test_ca_is_progressive(self):
        low = derived.compute_taxes({"YOUR_BASE_SALARY": 60_000, "STATE_CHOICE": "CA"})
        high = derived.compute_taxes({"YOUR_BASE_SALARY": 600_000, "STATE_CHOICE": "CA"})
        assert high["state"] / 600_000 > low["state"] / 60_000

    def test_fica_caps_ss_per_earner_not_per_household(self):
        """Two earners get two Social Security wage bases."""
        base = 168_600
        solo = derived.compute_taxes({"YOUR_BASE_SALARY": 2 * base})["fica"]
        couple = derived.compute_taxes({"YOUR_BASE_SALARY": base,
                                        "PARTNER_BASE_SALARY": base})["fica"]
        assert couple > solo
        assert couple == pytest.approx(2 * (base * 0.062 + base * 0.0145))

    def test_fica_medicare_is_uncapped(self):
        a = derived.compute_taxes({"YOUR_BASE_SALARY": 1_000_000})["fica"]
        b = derived.compute_taxes({"YOUR_BASE_SALARY": 2_000_000})["fica"]
        assert b - a == pytest.approx(1_000_000 * 0.0145)

    def test_fica_includes_bonus_and_rsu(self):
        a = derived.compute_taxes({"YOUR_BASE_SALARY": 50_000})["fica"]
        b = derived.compute_taxes({"YOUR_BASE_SALARY": 50_000,
                                   "YOUR_BONUS_AMOUNT": 10_000,
                                   "YOUR_RSU_AMOUNT": 20_000})["fica"]
        assert b == pytest.approx(a * 80_000 / 50_000)

    # FIXED 2026-08-22: was xfail(strict) while the defect stood; the fix is in.
    def test_non_wage_income_is_not_subject_to_fica(self):
        assert derived.compute_taxes({"YOUR_OTHER_INCOME": 100_000})["fica"] == 0.0

    def test_partner_other_income_alone_is_not_ficad(self):
        """Documents the asymmetry: routed through the two-earner branch only if
        partner WAGES exist, so partner other-income alone hits the same fallback."""
        t = derived.compute_taxes({"PARTNER_BASE_SALARY": 50_000,
                                   "PARTNER_OTHER_INCOME": 100_000})
        assert t["fica"] == pytest.approx(50_000 * 0.062 + 50_000 * 0.0145)


# ---------------------------------------------------------------------------
# compute_expenses_today / compute_disposable
# ---------------------------------------------------------------------------
class TestComputeExpensesToday:
    NO_PARTNER = {"PARTNER_MONTHLY_SPENDING": 0, "YEARS_UNTIL_FIRST_CHILD": 99}

    def test_empty_uses_the_partner_spending_default(self):
        assert derived.compute_expenses_today({}) == 1_500 * 12

    def test_categories_are_annualized(self):
        o = dict(self.NO_PARTNER, SPEND_FOOD_MONTHLY=1_000, SPEND_UTILITIES_MONTHLY=200,
                 SPEND_TRANSPORT_MONTHLY=300, SPEND_HEALTH_MONTHLY=100,
                 SPEND_DISCRETIONARY_MONTHLY=400, SPEND_OTHER_MONTHLY=0)
        assert derived.compute_expenses_today(o) == 2_000 * 12

    def test_mortgage_wins_over_rent(self):
        o = dict(self.NO_PARTNER, MORTGAGE_MONTHLY=3_000, SPEND_RENT_MONTHLY=2_000)
        assert derived.compute_expenses_today(o) == 3_000 * 12

    def test_rent_counts_only_for_non_owners(self):
        renter = dict(self.NO_PARTNER, SPEND_RENT_MONTHLY=2_000)
        owner = dict(renter, HOME_VALUE=800_000)
        assert derived.compute_expenses_today(renter) == 2_000 * 12
        # Owner with a paid-off house: no rent or mortgage, but property tax +
        # insurance (home value x 1.35%) are still paid -- the engine charges
        # them too, so the sidebar total must match.
        assert derived.compute_expenses_today(owner) == round(800_000 * 0.0135)
        off = dict(owner, MODEL_HOME_CARRYING_COST_AFTER_PAYOFF=False)
        assert derived.compute_expenses_today(off) == 0

    def test_child_cost_only_once_born(self):
        unborn = dict(self.NO_PARTNER, YEARS_UNTIL_FIRST_CHILD=3,
                      FIRST_CHILD_MONTHLY_COST=2_100)
        born = dict(unborn, YEARS_UNTIL_FIRST_CHILD=0)
        assert derived.compute_expenses_today(unborn) == 0
        assert derived.compute_expenses_today(born) == 2_100 * 12

    def test_partner_spending_default_is_applied_when_key_absent(self):
        o = {"SPEND_FOOD_MONTHLY": 500, "YEARS_UNTIL_FIRST_CHILD": 99}
        assert derived.compute_expenses_today(o) == (500 + 1_500) * 12

    def test_garbage_values_are_ignored(self):
        o = dict(self.NO_PARTNER, SPEND_FOOD_MONTHLY="abc", SPEND_UTILITIES_MONTHLY=None,
                 SPEND_TRANSPORT_MONTHLY=100)
        assert derived.compute_expenses_today(o) == 100 * 12

    def test_returns_int(self):
        assert isinstance(derived.compute_expenses_today({}), int)


class TestComputeDisposable:
    def test_identity_income_minus_taxes_minus_expenses(self):
        o = {"YOUR_BASE_SALARY": 300_000, "PARTNER_MONTHLY_SPENDING": 0,
             "YEARS_UNTIL_FIRST_CHILD": 99, "SPEND_FOOD_MONTHLY": 1_000}
        expected = (derived.compute_total_income(o)
                    - derived.compute_taxes(o)["total"]
                    - derived.compute_expenses_today(o))
        assert derived.compute_disposable(o) == int(max(0, expected))

    def test_floored_at_zero_when_expenses_swamp_income(self):
        o = {"YOUR_BASE_SALARY": 30_000, "SPEND_FOOD_MONTHLY": 10_000}
        assert derived.compute_disposable(o) == 0

    def test_zero_income(self):
        assert derived.compute_disposable({}) == 0


class TestAutoAllocateSavings:
    def test_zero_and_negative_disposable_allocates_nothing(self):
        for d in (0, -1, -100_000):
            alloc = derived.auto_allocate_savings(d, {"YOUR_AGE": 30})
            assert all(v == 0 for v in alloc.values())

    def test_fills_401k_first(self):
        alloc = derived.auto_allocate_savings(5_000, {"YOUR_AGE": 30})
        assert alloc["YOUR_401K_CONTRIBUTION"] == 5_000
        assert sum(alloc.values()) == 5_000

    def test_never_allocates_more_than_disposable(self):
        for d in (1, 1_000, 23_000, 40_000, 100_000, 1_000_000):
            alloc = derived.auto_allocate_savings(d, {"YOUR_AGE": 40, "PARTNER_AGE": 40})
            assert sum(alloc.values()) == d

    def test_respects_the_irs_caps_before_spilling_over(self):
        alloc = derived.auto_allocate_savings(1_000_000, {"YOUR_AGE": 30, "PARTNER_AGE": 30})
        assert alloc["YOUR_401K_CONTRIBUTION"] == derived.get_limit("401k", 30)
        assert alloc["PARTNER_401K_CONTRIBUTION"] == derived.get_limit("401k", 30)
        assert alloc["YOUR_HSA_CONTRIBUTION"] == derived.get_limit("hsa", 30)
        assert alloc["YOUR_BACKDOOR_ROTH"] == derived.get_limit("ira", 30)

    def test_no_partner_means_no_partner_buckets(self):
        alloc = derived.auto_allocate_savings(500_000, {"YOUR_AGE": 30, "PARTNER_AGE": 0})
        assert alloc["PARTNER_401K_CONTRIBUTION"] == 0
        assert alloc["PARTNER_ROTH_CONTRIBUTION"] == 0
        assert alloc["PARTNER_BROKERAGE_CONTRIBUTION"] == 0

    def test_catchup_raises_the_caps_at_50(self):
        young = derived.auto_allocate_savings(1_000_000, {"YOUR_AGE": 40})
        old = derived.auto_allocate_savings(1_000_000, {"YOUR_AGE": 55})
        assert old["YOUR_401K_CONTRIBUTION"] > young["YOUR_401K_CONTRIBUTION"]

    def test_brokerage_residual_follows_the_higher_earner(self):
        o = {"YOUR_AGE": 40, "PARTNER_AGE": 40,
             "YOUR_BASE_SALARY": 400_000, "PARTNER_BASE_SALARY": 50_000,
             "PARTNER_MONTHLY_SPENDING": 0, "YEARS_UNTIL_FIRST_CHILD": 99}
        alloc = derived.auto_allocate_savings(200_000, o)
        assert alloc["YOUR_BROKERAGE_CONTRIBUTION"] > alloc["PARTNER_BROKERAGE_CONTRIBUTION"]

    def test_brokerage_splits_evenly_with_no_income_breakdown(self):
        alloc = derived.auto_allocate_savings(200_000, {"YOUR_AGE": 40, "PARTNER_AGE": 40})
        assert (alloc["YOUR_BROKERAGE_CONTRIBUTION"]
                == alloc["PARTNER_BROKERAGE_CONTRIBUTION"])


# ---------------------------------------------------------------------------
# widget_sync casts + mapping-table structure
# ---------------------------------------------------------------------------
class TestWidgetSyncCasts:
    def test_clamp_tolerates_open_bounds(self):
        assert ws._clamp(5, None, None) == 5
        assert ws._clamp(-5, 0, None) == 0
        assert ws._clamp(500, None, 100) == 100

    def test_as_int(self):
        cast = ws._as_int(10, 0, 100)
        assert cast(42) == 42
        assert cast("42") == 42
        assert cast(42.9) == 42          # int(float(v)) truncates
        assert cast("42.9") == 42        # decimal STRING also works here
        assert cast(-5) == 0             # clamped
        assert cast(1_000) == 100        # clamped
        assert cast(None) == 10          # default
        assert cast("abc") == 10

    def test_as_float(self):
        cast = ws._as_float(1.5, 0.0, 10.0)
        assert cast("2.25") == pytest.approx(2.25)
        assert cast(-1) == 0.0
        assert cast(99) == 10.0
        assert cast(None) == 1.5

    def test_as_pct_accepts_either_form(self):
        cast = ws._as_pct(4.0, 0.0, 100.0)
        assert cast(0.04) == pytest.approx(4.0)     # fraction -> percent
        assert cast(7.0) == pytest.approx(7.0)      # already percent
        assert cast(1.0) == pytest.approx(100.0)    # 1.0 reads as 100%
        assert cast(0.0) == pytest.approx(0.0)
        assert cast(None) == pytest.approx(4.0)
        assert cast(500) == pytest.approx(100.0)    # clamped

    def test_as_bps(self):
        cast = ws._as_bps(15, 0, 100)
        assert cast(0.0015) == 15
        assert cast(0.0) == 0
        assert cast(1.0) == 100        # clamped
        assert cast("abc") == 15

    def test_as_pct_int(self):
        cast = ws._as_pct_int(80, 70, 95)
        assert cast(0.80) == 80
        assert cast(85) == 85
        assert cast(0.99) == 95        # clamped
        assert cast(None) == 80

    @pytest.mark.parametrize("code,label", [
        ("CA", "California"),
        ("California", "California"),
        ("No state tax", "No state income tax"),
        ("No state income tax", "No state income tax"),
        ("Other", "Another state (flat rate)"),
        ("Other (use marginal rate)", "Another state (flat rate)"),
        ("Another state (flat rate)", "Another state (flat rate)"),
        (None, "California"),
        ("", "California"),
        ("Freedonia", "California"),
    ])
    def test_state_code_to_label(self, code, label):
        assert ws._state_code_to_label(code) == label

    def test_state_label_mapping_is_idempotent(self):
        for code in ("CA", "No state tax", "Other"):
            once = ws._state_code_to_label(code)
            assert ws._state_code_to_label(once) == once

    def test_state_labels_match_the_component_options(self):
        from components.sec_taxes import _STATE_OPTIONS, _STATE_TO_CODE
        for code in _STATE_TO_CODE.values():
            assert ws._state_code_to_label(code) in _STATE_OPTIONS

    @pytest.mark.parametrize("raw,expected", [
        ("conservative", "Conservative"), ("HISTORICAL", "Historical"),
        ("pessimistic", "Pessimistic"), ("  historical ", "Historical"),
        ("nonsense", "Historical"), (None, "Historical"),
    ])
    def test_scenario_cast(self, raw, expected):
        assert ws._scenario_cast(raw) == expected

    def test_scenario_cast_covers_every_engine_scenario(self):
        for name in cfg.RETURN_SCENARIOS:
            assert ws._scenario_cast(name).lower() == name.lower()


class TestWidgetSyncDerivations:
    @pytest.mark.parametrize("yuw,expected", [
        (0, "Married"), (5, "Getting married"), (99, "Single (no wedding planned)"),
        (999, "Single (no wedding planned)"), (None, "Married"), ("x", "Married"),
    ])
    def test_marital(self, yuw, expected):
        assert ws._derive_marital({"YEARS_UNTIL_WEDDING": yuw}) == expected

    @pytest.mark.parametrize("o,expected", [
        ({"YEARS_UNTIL_FIRST_CHILD": 3, "FIRST_CHILD_MONTHLY_COST": 2_100},
         "Kids planned / already born"),
        ({"YEARS_UNTIL_FIRST_CHILD": 0, "FIRST_CHILD_MONTHLY_COST": 2_100},
         "Kids planned / already born"),
        ({"YEARS_UNTIL_FIRST_CHILD": 99}, "No kids planned"),
        ({"FIRST_CHILD_MONTHLY_COST": 0}, "No kids planned"),
        ({}, "Kids planned / already born"),
    ])
    def test_kids(self, o, expected):
        assert ws._derive_kids(o) == expected

    @pytest.mark.parametrize("hv,expected", [
        (0, "Renting"), (1, "Own home"), (800_000, "Own home"),
        (None, "Renting"), ("abc", "Renting"),
    ])
    def test_rent_own(self, hv, expected):
        assert ws._derive_rent_own({"HOME_VALUE": hv}) == expected

    def test_rent_own_missing_key_defaults_to_renting(self):
        assert ws._derive_rent_own({}) == "Renting"

    def test_scenario_derivation(self):
        assert ws._derive_scenario({}) == "Historical"
        assert ws._derive_scenario({"ACTIVE_RETURN_SCENARIO": "conservative"}) == "Conservative"
        assert ws._derive_scenario({"ACTIVE_RETURN_SCENARIO": "junk"}) == "Historical"

    @pytest.mark.parametrize("guardrails,trigger,reduction", [
        (None, 70.0, 15.0),
        ({}, 70.0, 15.0),
        ({"floor_trigger": 0.60, "floor_reduction": 0.25}, 60.0, 25.0),
        ({"floor_trigger": 60.0, "floor_reduction": 25.0}, 60.0, 25.0),
        ("not-a-dict", 70.0, 15.0),
        ({"floor_trigger": "x", "floor_reduction": "y"}, 70.0, 15.0),
    ])
    def test_guardrail_derivations(self, guardrails, trigger, reduction):
        o = {"SPENDING_GUARDRAILS": guardrails}
        assert ws._derive_spending_guardrail_trigger(o) == pytest.approx(trigger)
        assert ws._derive_spending_guardrail_reduction(o) == pytest.approx(reduction)

    @pytest.mark.parametrize("hc,expected", [
        (None, 24_000), ({}, 24_000), ({"early_retirement": 30_000}, 30_000),
        ({"early_retirement": "x"}, 24_000), ("junk", 24_000),
    ])
    def test_hc_early(self, hc, expected):
        assert ws._derive_hc_early({"HEALTHCARE_COSTS_BY_AGE": hc}) == expected


class TestMappingTableIntegrity:
    def test_every_direct_override_key_is_a_real_config_attribute(self):
        """A typo'd override key makes the widget silently un-restorable after a
        profile load (sync writes nothing and the stale value persists)."""
        bad = [(w, k) for w, (k, _) in ws.DIRECT_MAPPINGS.items()
               if not hasattr(cfg, k) and k not in _UI_ONLY_KEYS]
        assert bad == []

    def test_no_widget_key_is_in_both_tables(self):
        assert not (set(ws.DIRECT_MAPPINGS) & set(ws.DERIVED_MAPPINGS))

    def test_every_cast_is_callable_and_survives_garbage(self):
        for widget_key, (_, cast) in ws.DIRECT_MAPPINGS.items():
            assert callable(cast), widget_key

    def test_sync_writes_every_mapped_widget_and_reset_clears_them_all(self):
        st = FakeSt(user_overrides={k: getattr(cfg, k, 0)
                                    for _, (k, _) in ws.DIRECT_MAPPINGS.items()})
        ws.sync_widgets_from_overrides(st)
        written = set(st.session_state) - {"user_overrides"}
        assert written, "sync wrote nothing"
        ws.reset_input_widget_state(st)
        assert set(st.session_state) == {"user_overrides"}

    def test_sync_never_raises_on_garbage_overrides(self):
        garbage = {k: object() for _, (k, _) in ws.DIRECT_MAPPINGS.items()}
        st = FakeSt(user_overrides=garbage)
        ws.sync_widgets_from_overrides(st)   # must not raise

    def test_sync_skips_none_valued_overrides(self):
        st = FakeSt(user_overrides={"YOUR_401K": None}, ai_your_401k=999)
        ws.sync_widgets_from_overrides(st)
        assert st.session_state["ai_your_401k"] == 999

    def test_sync_applies_unit_conversions(self):
        st = FakeSt(user_overrides={
            "YOUR_401K": 12_345,
            "STOCK_ALLOCATION": 0.75,        # fraction -> 75.0 percent
            "INVESTMENT_FEE_RATE": 0.0025,   # -> 25 bps
            "TARGET_SUCCESS_RATE": 0.90,     # -> 90 (int percent)
            "STATE_CHOICE": "No state tax",  # -> label
            "ACTIVE_RETURN_SCENARIO": "conservative",
        })
        ws.sync_widgets_from_overrides(st)
        assert st.session_state["ai_your_401k"] == 12_345
        assert st.session_state["sa_stock_alloc"] == pytest.approx(75.0)
        assert st.session_state["sa_fee_bps"] == 25
        assert st.session_state["rg_target_success"] == 90
        assert st.session_state["sa_scenario"] == "Conservative"
        assert st.session_state["se_rent_own"] == "Renting"

    def test_sync_is_idempotent(self):
        overrides = {"YOUR_401K": 12_345, "STOCK_ALLOCATION": 0.75,
                     "INVESTMENT_FEE_RATE": 0.0025, "HOME_VALUE": 500_000}
        st = FakeSt(user_overrides=dict(overrides))
        ws.sync_widgets_from_overrides(st)
        first = dict(st.session_state)
        ws.sync_widgets_from_overrides(st)
        assert dict(st.session_state) == first

    def test_reset_clears_extra_and_prefixed_keys(self):
        st = FakeSt(si_comp_editor=[{"base": 1}], si_comp_customized=True, le_age=44,
                    sv_pct_0=10, sv_pct_1=20, keep_me="yes")
        ws.reset_input_widget_state(st)
        assert set(st.session_state) == {"keep_me"}

    def test_reset_on_empty_state_is_a_noop(self):
        st = FakeSt()
        ws.reset_input_widget_state(st)
        assert st.session_state == {}
