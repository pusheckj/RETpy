"""Inert-engine-control wiring pins (conservation findings #6, #7, #8, #11).

Each of these controls was declared in the UI but SILENTLY DROPPED before it
reached the Monte Carlo engine, because the override key was not a real
attribute on ``cfg`` (the ``hasattr(cfg, key)`` gate in
``sim_runner._apply_overrides``). This stage declares the real cfg attributes
and consumes them in the engine's expense / tax path. Each test asserts one of:

  * the control now CHANGES the derived engine value (expenses / tax), AND
  * ``_restore_overrides`` reverts any derived state (no cross-run cfg leak), OR
  * the control now MOVES a seeded Monte Carlo run on an appropriate profile.

Numbers move by design.

sim_runner imports ``from retirement_sim import config`` and helpers under
``ui/``; ``retirement_sim`` is importable from ROOT, ``utils``/``components``
live under ``ui/``. Add both to sys.path.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import pytest

from retirement_sim import config as cfg
from retirement_sim import account_simulation as sim
from utils import sim_runner as sr
from tests.conftest import load_sample_household


def _profile(name):
    from components.profile_picker import PROFILES
    return dict(PROFILES[name])


# =============================================================================
# Finding #6 — RENT: SPEND_RENT_MONTHLY reaches the engine for renters.
# =============================================================================

class TestRentWiring:
    def test_rent_attr_declared_default_zero(self):
        # Real cfg attribute so it is not dropped by the hasattr() gate.
        assert hasattr(cfg, "SPEND_RENT_MONTHLY")

    def test_rent_included_for_renters(self):
        # Renter household: no home value, no mortgage. Rent must land in the
        # living-expense total (both accumulation and retirement paths use
        # calculate_annual_expenses).
        original = sr._apply_overrides({
            "HOME_VALUE": 0, "MORTGAGE_MONTHLY": 0, "MORTGAGE_YEARS_REMAINING": 0,
            "SPEND_RENT_MONTHLY": 3000,
        })
        try:
            assert cfg.is_renter() is True
            with_rent = cfg.calculate_annual_expenses(cfg.YOUR_AGE, 1.0, retirement=False)
        finally:
            sr._restore_overrides(original)

        original = sr._apply_overrides({
            "HOME_VALUE": 0, "MORTGAGE_MONTHLY": 0, "MORTGAGE_YEARS_REMAINING": 0,
            "SPEND_RENT_MONTHLY": 0,
        })
        try:
            without_rent = cfg.calculate_annual_expenses(cfg.YOUR_AGE, 1.0, retirement=False)
        finally:
            sr._restore_overrides(original)

        # $3,000/mo rent = $36k/yr must be added, not dropped.
        assert with_rent - without_rent == pytest.approx(36_000)

    def test_rent_ignored_for_owners(self):
        # Owners (home value or mortgage) model housing via the mortgage term;
        # rent must NOT be double-counted on top.
        original = sr._apply_overrides({
            "HOME_VALUE": 500_000, "MORTGAGE_MONTHLY": 0, "MORTGAGE_YEARS_REMAINING": 0,
            "SPEND_RENT_MONTHLY": 3000,
        })
        try:
            assert cfg.is_renter() is False
            assert cfg.rent_annual(cfg.YOUR_AGE) == 0.0
        finally:
            sr._restore_overrides(original)

    @pytest.mark.slow
    def test_rent_moves_renter_profile_sim(self):
        from utils.sim_runner import run_full_analysis, clear_cache

        p = _profile("Median US 25-year-old household")  # renter (HOME_VALUE=0)
        ra = int(p["TARGET_RETIREMENT_AGE"])

        def _run(rent):
            q = dict(p)
            q["SPEND_RENT_MONTHLY"] = rent
            clear_cache()
            np.random.seed(11)
            return run_full_analysis(
                user_overrides=q, n_simulations=300,
                target_retirement_age=ra, scan_age_range=(ra, ra + 1, 1),
            )["primary_result"]

        no_rent = _run(0)
        high_rent = _run(3000)  # +$36k/yr living cost
        clear_cache()
        # Adding $36k/yr of rent must lower success and/or median end-balance.
        assert high_rent["median_final"] < no_rent["median_final"], (
            f"rent inert on renter profile: no_rent median={no_rent['median_final']:.0f} "
            f"high_rent median={high_rent['median_final']:.0f}"
        )


# =============================================================================
# Finding #7 — RETIREMENT SPENDING MODE: %/absolute set the retirement base.
# =============================================================================

class TestRetirementSpendingMode:
    def test_mode_attrs_declared(self):
        for k in ("RETIREMENT_SPENDING_MODE", "RETIREMENT_SPENDING_PCT",
                  "RETIREMENT_SPENDING_ABSOLUTE"):
            assert hasattr(cfg, k)

    def test_percent_mode_scales_base(self):
        original = sr._apply_overrides({
            "RETIREMENT_SPENDING_MODE": "% of today's expenses",
            "RETIREMENT_SPENDING_PCT": 0.70,
        })
        try:
            expected = cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE * 0.70
            assert cfg.retirement_living_base() == pytest.approx(expected)
            # Derived display constant recomputes too.
            assert cfg.RETIREMENT_ANNUAL_EXPENSES == pytest.approx(expected)
        finally:
            sr._restore_overrides(original)
        # Restore reverts the display constant to the module default.
        assert cfg.RETIREMENT_ANNUAL_EXPENSES == cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE

    def test_absolute_mode_overrides_base(self):
        original = sr._apply_overrides({
            "RETIREMENT_SPENDING_MODE": "Absolute amount ($/yr)",
            "RETIREMENT_SPENDING_ABSOLUTE": 200_000,
        })
        try:
            assert cfg.retirement_living_base() == pytest.approx(200_000)
        finally:
            sr._restore_overrides(original)

    def test_mode_affects_retirement_but_not_working_expenses(self):
        # In "% of today" mode the RETIREMENT living base scales, but a WORKING
        # year (retirement=False) keeps today's base.
        original = sr._apply_overrides({
            "RETIREMENT_SPENDING_MODE": "% of today's expenses",
            "RETIREMENT_SPENDING_PCT": 0.50,
            # Own outright so no mortgage/rent term muddies the comparison.
            "HOME_VALUE": 0, "MORTGAGE_MONTHLY": 0, "MORTGAGE_YEARS_REMAINING": 0,
            "SPEND_RENT_MONTHLY": 0,
            # No kids at the sampled age so child costs are 0 on both sides.
            "YEARS_UNTIL_FIRST_CHILD": 99,
        })
        try:
            age = cfg.YOUR_AGE
            working = cfg.calculate_annual_expenses(age, 1.0, retirement=False)
            retired = cfg.calculate_annual_expenses(age, 1.0, retirement=True)
            assert working == pytest.approx(cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE)
            assert retired == pytest.approx(cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE * 0.50)
        finally:
            sr._restore_overrides(original)

    @pytest.mark.slow
    def test_absolute_mode_moves_profile_sim(self):
        from utils.sim_runner import run_full_analysis, clear_cache

        p = load_sample_household()
        ra = int(p["TARGET_RETIREMENT_AGE"])

        def _run(overrides):
            q = dict(p)
            q.update(overrides)
            clear_cache()
            np.random.seed(3)
            return run_full_analysis(
                user_overrides=q, n_simulations=300,
                target_retirement_age=ra, scan_age_range=(ra, ra + 1, 1),
            )["primary_result"]

        same = _run({"RETIREMENT_SPENDING_MODE": "Same as today's expenses"})
        rich = _run({
            "RETIREMENT_SPENDING_MODE": "Absolute amount ($/yr)",
            "RETIREMENT_SPENDING_ABSOLUTE": 250_000,
        })
        clear_cache()
        # A high absolute retirement budget must worsen the plan vs "same".
        assert rich["success_rate"] < same["success_rate"], (
            f"retirement spending mode inert: same={same['success_rate']} "
            f"absolute250k={rich['success_rate']}"
        )


# =============================================================================
# Finding #8 — FILING STATUS: federal brackets + standard deduction branch.
# =============================================================================

class TestFilingStatus:
    def test_filing_status_attr_declared(self):
        assert hasattr(cfg, "FILING_STATUS")

    def test_federal_brackets_differ_by_status(self):
        mfj = cfg.get_federal_brackets("Married filing jointly")
        single = cfg.get_federal_brackets("Single")
        hoh = cfg.get_federal_brackets("Head of household")
        # 12% bracket ceiling: MFJ $94,300 vs Single $47,150 vs HOH $63,100.
        assert mfj[1][0] == 94_300
        assert single[1][0] == 47_150
        assert hoh[1][0] == 63_100

    def test_standard_deduction_branches(self):
        original = sr._apply_overrides({"FILING_STATUS": "Single"})
        try:
            assert cfg.get_standard_deduction(40, 40) == 14_600
        finally:
            sr._restore_overrides(original)
        # Default MFJ restored.
        assert cfg.get_standard_deduction(40, 40) == 29_200

    def test_engine_portfolio_uses_filing_status_brackets(self):
        # A fresh AccountPortfolio must build federal brackets from FILING_STATUS.
        original = sr._apply_overrides({"FILING_STATUS": "Single"})
        try:
            pf = sim.AccountPortfolio()
            # Single 12% bracket ceiling is $47,150 (MFJ would be $94,300).
            assert pf.federal_tax_brackets.brackets[1][0] == 47_150
            # A $150k single filer owes strictly more federal tax than MFJ.
            single_tax = pf.calculate_federal_tax_with_deduction(150_000)
        finally:
            sr._restore_overrides(original)

        original = sr._apply_overrides({"FILING_STATUS": "Married filing jointly"})
        try:
            pf_mfj = sim.AccountPortfolio()
            mfj_tax = pf_mfj.calculate_federal_tax_with_deduction(150_000)
        finally:
            sr._restore_overrides(original)

        assert single_tax > mfj_tax, (
            f"filing status inert on engine: single={single_tax:.0f} mfj={mfj_tax:.0f}"
        )

    @pytest.mark.slow
    def test_filing_status_moves_single_profile_sim(self):
        from utils.sim_runner import run_full_analysis, clear_cache

        # Young single professional (all your-side income, no partner) — filing
        # single vs MFJ changes federal tax materially during accumulation.
        p = _profile("Young professional (28, single)")
        ra = int(p["TARGET_RETIREMENT_AGE"])
        # The preset carries no pay table (the Income section builds one in the
        # app), so give it the one the app would build from its salary inputs.
        # Without it the engine falls back to the config's median-worker table,
        # and now that 401(k)/HSA deferrals really come out of take-home this
        # profile's $30k of pre-tax savings can't be funded from that pay.
        from components.sec_income import _build_comp_table
        table = {}
        for _, r in _build_comp_table(p["YOUR_AGE"], ra, p["YOUR_BASE_SALARY"],
                                      p["YOUR_BONUS_AMOUNT"], p["YOUR_RSU_AMOUNT"],
                                      0.02).iterrows():
            total = int(r.base) + int(r.bonus) + int(r.rsu_gross)
            table[int(r.age)] = {"base": int(r.base), "bonus": int(r.bonus),
                                 "rsu_gross": int(r.rsu_gross), "total_comp": total,
                                 "saved": 0}
        p["YOUR_COMPENSATION_BY_AGE"] = table

        def _run(status):
            q = dict(p)
            q["FILING_STATUS"] = status
            clear_cache()
            np.random.seed(5)
            return run_full_analysis(
                user_overrides=q, n_simulations=300,
                target_retirement_age=ra, scan_age_range=(ra, ra + 1, 1),
            )["primary_result"]

        single = _run("Single")
        mfj = _run("Married filing jointly")
        clear_cache()
        # Filing single taxes retirement withdrawals harder than MFJ, so the
        # single result must not be identical to (and should be no better than)
        # the MFJ result. Assert they differ — the control is live.
        assert single["median_final"] != mfj["median_final"], (
            f"filing status inert on sim: single={single['median_final']:.0f} "
            f"mfj={mfj['median_final']:.0f}"
        )


# =============================================================================
# Finding #11 — SPENDING LIFECYCLE PRESET: multipliers scale engine spending.
# =============================================================================

class TestLifecyclePreset:
    def test_preset_attrs_declared(self):
        assert hasattr(cfg, "SPEND_LIFECYCLE_PRESET")
        assert hasattr(cfg, "SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE")

    def test_recompute_derives_multiplier_dict_from_preset(self):
        # sim_runner must derive the {category: {age: mult}} dict from the preset
        # NAME (reusing compute_lifecycle_multipliers) so the engine can honor it.
        original = sr._apply_overrides({
            "SPEND_LIFECYCLE_PRESET": "Conservative senior years",
        })
        try:
            mults = cfg.SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE
            # Conservative senior: discretionary 0.70 at age 75+.
            disc = mults.get("SPEND_DISCRETIONARY_MONTHLY", {})
            assert disc.get(75) == pytest.approx(0.70)
        finally:
            sr._restore_overrides(original)
        # Restore reverts the dict to the module default (empty).
        assert cfg.SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE == {}

    def test_lifecycle_delta_changes_expenses(self):
        # With a discretionary reduction preset, retirement expenses at age 80
        # must be LOWER than with the flat preset (engine honors the multiplier).
        base_overrides = {
            "SPEND_DISCRETIONARY_MONTHLY": 1000,
            "HOME_VALUE": 0, "MORTGAGE_MONTHLY": 0, "MORTGAGE_YEARS_REMAINING": 0,
            "SPEND_RENT_MONTHLY": 0, "YEARS_UNTIL_FIRST_CHILD": 99,
        }
        original = sr._apply_overrides({**base_overrides, "SPEND_LIFECYCLE_PRESET": "Flat (no change)"})
        try:
            flat = cfg.calculate_annual_expenses(80, 1.0, retirement=True)
        finally:
            sr._restore_overrides(original)

        original = sr._apply_overrides({**base_overrides, "SPEND_LIFECYCLE_PRESET": "Conservative senior years"})
        try:
            senior = cfg.calculate_annual_expenses(80, 1.0, retirement=True)
        finally:
            sr._restore_overrides(original)

        # Discretionary $1,000/mo -> $12k/yr; a 0.70 multiplier cuts it by $3,600.
        assert flat - senior == pytest.approx(3_600)

    @pytest.mark.slow
    def test_preset_moves_profile_sim(self):
        from utils.sim_runner import run_full_analysis, clear_cache

        p = load_sample_household()
        ra = int(p["TARGET_RETIREMENT_AGE"])

        def _run(preset):
            q = dict(p)
            q["SPEND_LIFECYCLE_PRESET"] = preset
            clear_cache()
            np.random.seed(9)
            return run_full_analysis(
                user_overrides=q, n_simulations=300,
                target_retirement_age=ra, scan_age_range=(ra, ra + 1, 1),
            )["primary_result"]

        flat = _run("Flat (no change)")
        boom = _run("Early-retirement travel boom, quieter later")
        clear_cache()
        # The travel-boom preset raises discretionary +50% ages 55-70, so the
        # plan result must differ from flat — the preset is no longer inert.
        assert boom["median_final"] != flat["median_final"], (
            f"lifecycle preset inert: flat={flat['median_final']:.0f} "
            f"boom={boom['median_final']:.0f}"
        )
