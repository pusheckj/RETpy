"""Regression tests for engine (``retirement_sim/``) defect fixes.

One class per fixed defect. Every test states the WRONG value the engine produced
before the fix so a regression is unambiguous.

Fixes covered here:
  * ``simulate_accumulation_year`` starts a fresh tax year and recognizes wage
    income, so working-year lump-sum draws are taxed at the real marginal rate
    and ``year_ordinary_income`` no longer leaks across years.
  * ``quote_health_insurance_cost`` prices health insurance PER COVERED ADULT
    from each spouse's own age (age-gapped couples / single filers).
  * An active 72(t) SEPP no longer makes *all* traditional withdrawals
    penalty-free.
  * ``ROTH_LADDER_ENABLED`` counts ordinary Roth contribution basis as
    penalty-free room.
  * ``mc_parallel.sim_task`` reports how many simulations raised instead of
    silently shrinking the denominator.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import mc_parallel  # noqa: E402
from retirement_sim import account_simulation as asim  # noqa: E402
from retirement_sim.account_simulation import (  # noqa: E402
    Account,
    AccountPortfolio,
    AccountType,
    simulate_accumulation_year,
)


@pytest.fixture
def cfg_sandbox():
    """Snapshot/restore every cfg attribute these tests mutate."""
    keys = (
        "YOUR_AGE", "PARTNER_AGE", "FILING_STATUS", "STATE_CHOICE",
        "YOUR_COMPENSATION_BY_AGE", "PARTNER_SALARY", "YOUR_401K_CONTRIBUTION",
        "YOUR_401K_MATCH_PCT", "YOUR_HSA_CONTRIBUTION", "YOUR_BACKDOOR_ROTH",
        "YOUR_BROKERAGE_CONTRIBUTION", "PARTNER_401K_CONTRIBUTION",
        "PARTNER_ROTH_CONTRIBUTION", "PARTNER_BROKERAGE_CONTRIBUTION",
        "YOUR_AFTER_TAX_401K_PCT", "SAVINGS_MODE", "COAST_FIRE_ENABLED",
        "CAR_ONETIME_ENABLED", "CAR_ONETIME_AGE", "CAR_ONETIME_AMOUNT",
        "CAR_RECURRING_ENABLED", "CAR_RECURRING_AMOUNT",
        "CAR_RECURRING_EVERY_YEARS", "CAR_RECURRING_START_AGE",
        "HOUSE_MOVE_ENABLED", "USE_HOME_AS_BACKUP",
        "SEPP_72T_ENABLED", "SEPP_72T_START_AGE", "SEPP_72T_CARVEOUT",
        "ROTH_LADDER_ENABLED", "ACA_ENABLED", "SAVINGS_529_PER_CHILD_ANNUAL",
        "MODEL_HEALTHCARE_COST_FLOOR", "MODEL_ACA_AGE_RATED",
    )
    saved = {k: getattr(cfg, k) for k in keys if hasattr(cfg, k)}
    try:
        yield cfg
    finally:
        for k, v in saved.items():
            setattr(cfg, k, v)


def _flat_comp(base, after_tax, ages=range(20, 80)):
    return {
        a: {"base": base, "bonus": 0, "rsu_gross": 0, "total_comp": base,
            "after_tax": after_tax, "saved": 0.0}
        for a in ages
    }


def _quiet_household(sandbox, base=300_000, after_tax=200_000):
    """A single-earner household with every elective contribution switched off."""
    sandbox.YOUR_COMPENSATION_BY_AGE = _flat_comp(base, after_tax)
    sandbox.PARTNER_SALARY = 0.0
    sandbox.YOUR_401K_CONTRIBUTION = 0.0
    sandbox.YOUR_401K_MATCH_PCT = 0.0
    sandbox.YOUR_HSA_CONTRIBUTION = 0.0
    sandbox.YOUR_BACKDOOR_ROTH = 0.0
    sandbox.YOUR_BROKERAGE_CONTRIBUTION = 0
    sandbox.PARTNER_401K_CONTRIBUTION = 0.0
    sandbox.PARTNER_ROTH_CONTRIBUTION = 0.0
    sandbox.PARTNER_BROKERAGE_CONTRIBUTION = 0
    sandbox.YOUR_AFTER_TAX_401K_PCT = 0.0
    sandbox.SAVINGS_529_PER_CHILD_ANNUAL = 0
    sandbox.HOUSE_MOVE_ENABLED = False
    sandbox.COAST_FIRE_ENABLED = False
    sandbox.USE_HOME_AS_BACKUP = False


# ===========================================================================
# Accumulation-phase tax year: reset + wage recognition
# ===========================================================================
class TestAccumulationTaxYear:
    """``simulate_accumulation_year`` must open a fresh, wage-populated tax year.

    Before the fix ``reset_yearly_income()`` / ``update_ages()`` were called ONLY
    from ``simulate_retirement_year``, and accumulation never recognized wages.
    So a working-year lump-sum draw (car purchase, house down payment) was taxed
    from a $0 income base, and the recognized amount then LEAKED into every later
    accumulation year -- identical $200k purchases at 40/41/42 booked
    $23,118 / $48,210 / $52,858 as the ratchet climbed.
    """

    def _one_car_year(self, sandbox, age, base=300_000, after_tax=200_000,
                      trad_balance=5_000_000.0):
        _quiet_household(sandbox, base=base, after_tax=after_tax)
        sandbox.CAR_ONETIME_ENABLED = True
        sandbox.CAR_ONETIME_AGE = age
        sandbox.CAR_ONETIME_AMOUNT = 200_000
        sandbox.CAR_RECURRING_ENABLED = False
        p = AccountPortfolio()
        p.add_account(Account("your_401k", AccountType.TRADITIONAL_401K,
                              trad_balance, "you"))
        before = p.total_taxes_paid
        simulate_accumulation_year(p, your_age=age, annual_return=0.0)
        return p, p.total_taxes_paid - before

    def test_a_lump_sum_costs_more_for_a_high_income_household(self, cfg_sandbox):
        """The draw must stack on WAGES, so the same car costs a rich household more.

        Before the fix ``year_ordinary_income`` started at $0 in every
        accumulation year, so the tax on the car was identical whether the
        household earned $0 or $300k -- it got the bottom ordinary brackets (and
        the whole 0%-LTCG bracket) for free. Measured understatement on a
        traditional-funded $200k net purchase: $71,328 booked vs $135,359 correct.
        """
        cfg_sandbox.YOUR_AGE = 40
        _p_poor, cost_poor = self._one_car_year(
            cfg_sandbox, 40, base=0, after_tax=0
        )
        _p_rich, cost_rich = self._one_car_year(
            cfg_sandbox, 40, base=300_000, after_tax=200_000
        )
        assert cost_poor > 0 and cost_rich > 0
        assert cost_rich > cost_poor * 1.10, (
            "lump-sum tax ignores wage income: "
            f"$0-income household paid {cost_poor:,.0f}, "
            f"$300k household paid {cost_rich:,.0f}"
        )

    def test_wages_are_recognized_into_the_tax_year(self, cfg_sandbox):
        """No lump sum at all -> year_ordinary_income is exactly the wage base."""
        cfg_sandbox.YOUR_AGE = 40
        _quiet_household(cfg_sandbox, base=300_000, after_tax=200_000)
        cfg_sandbox.CAR_ONETIME_ENABLED = False
        cfg_sandbox.CAR_RECURRING_ENABLED = False
        p = AccountPortfolio()
        p.add_account(Account("your_401k", AccountType.TRADITIONAL_401K, 1e6, "you"))
        simulate_accumulation_year(p, your_age=40, annual_return=0.0)
        assert p.year_ordinary_income == pytest.approx(300_000.0), (
            "wage income was not recognized into the tax year"
        )

    def test_ages_are_tracked_during_accumulation(self, cfg_sandbox):
        """``current_your_age`` must follow the simulated age, not stay at YOUR_AGE."""
        cfg_sandbox.YOUR_AGE = 40
        _quiet_household(cfg_sandbox)
        cfg_sandbox.CAR_ONETIME_ENABLED = False
        cfg_sandbox.CAR_RECURRING_ENABLED = False
        p = AccountPortfolio()
        p.add_account(Account("your_401k", AccountType.TRADITIONAL_401K, 1e6, "you"))
        simulate_accumulation_year(p, your_age=67, annual_return=0.0)
        assert p.current_your_age == 67, "update_ages() not called in accumulation"

    def _consecutive_car_costs(self, sandbox, ages=(40, 41, 42)):
        """Per-year tax cost of an identical purchase, on ONE shared portfolio."""
        _quiet_household(sandbox, base=300_000, after_tax=200_000)
        sandbox.CAR_ONETIME_ENABLED = False
        sandbox.CAR_RECURRING_ENABLED = True
        sandbox.CAR_RECURRING_AMOUNT = 200_000
        sandbox.CAR_RECURRING_EVERY_YEARS = 1
        sandbox.CAR_RECURRING_START_AGE = ages[0]
        p = AccountPortfolio()
        p.add_account(Account("your_401k", AccountType.TRADITIONAL_401K,
                              20_000_000.0, "you"))
        costs = []
        for age in ages:
            before = p.total_taxes_paid
            simulate_accumulation_year(p, your_age=age, annual_return=0.0)
            costs.append(p.total_taxes_paid - before)
        return costs

    def test_identical_purchases_cost_the_same_every_year(self, cfg_sandbox):
        """No ratchet: the tax on a lump sum must not depend on prior years.

        Before the fix, identical $200k purchases at 40/41/42 booked
        $23,118 / $48,210 / $52,858 as ``year_ordinary_income`` climbed
        123,117 -> 271,327 -> 424,183 because nothing ever reset it.
        """
        cfg_sandbox.YOUR_AGE = 40
        costs = self._consecutive_car_costs(cfg_sandbox)
        assert costs[0] > 0
        for c in costs[1:]:
            assert c == pytest.approx(costs[0], rel=1e-6), (
                f"lump-sum tax leaked across accumulation years: {costs}"
            )

    def test_year_income_does_not_leak_between_consecutive_years(self, cfg_sandbox):
        """``year_ordinary_income`` must not accumulate across years."""
        cfg_sandbox.YOUR_AGE = 40
        _quiet_household(cfg_sandbox, base=300_000, after_tax=200_000)
        cfg_sandbox.CAR_ONETIME_ENABLED = False
        cfg_sandbox.CAR_RECURRING_ENABLED = True
        cfg_sandbox.CAR_RECURRING_AMOUNT = 200_000
        cfg_sandbox.CAR_RECURRING_EVERY_YEARS = 1
        cfg_sandbox.CAR_RECURRING_START_AGE = 40
        p = AccountPortfolio()
        p.add_account(Account("your_401k", AccountType.TRADITIONAL_401K, 2e7, "you"))
        simulate_accumulation_year(p, your_age=40, annual_return=0.0)
        first = p.year_ordinary_income
        simulate_accumulation_year(p, your_age=41, annual_return=0.0)
        assert first > 300_000  # wages + the recognized car draw
        assert p.year_ordinary_income == pytest.approx(first, rel=1e-6), (
            "year_ordinary_income accumulated across accumulation years"
        )


# ===========================================================================
# Health insurance priced per covered adult
# ===========================================================================
class TestHealthInsurancePerPerson:
    """Medicare eligibility is INDIVIDUAL, so the premium must be per person.

    Before the fix ``quote_health_insurance_cost`` branched on the primary's age
    alone and ``calculate_medicare_irmaa`` always billed exactly two enrollees.
    A 60/50 couple's modelled premium DROPPED from $6,554 to $4,440 the year the
    primary turned 65 -- losing the 55-year-old spouse's marketplace coverage
    entirely while being billed Medicare for someone 10 years from eligible.
    """

    MAGI = 80_000

    def test_irmaa_scales_with_enrollee_count(self):
        one = cfg.calculate_medicare_irmaa(self.MAGI, 1.0, enrollees=1)
        two = cfg.calculate_medicare_irmaa(self.MAGI, 1.0, enrollees=2)
        assert one > 0
        assert two == pytest.approx(2 * one)

    def test_default_enrollees_is_still_two(self):
        """Back-compat: existing callers that omit the argument get a couple."""
        assert cfg.calculate_medicare_irmaa(self.MAGI, 1.0) == pytest.approx(
            cfg.calculate_medicare_irmaa(self.MAGI, 1.0, enrollees=2)
        )

    def _quote(self, sandbox, your_age, partner_age, magi=MAGI):
        # This class tests the PER-ADULT PREMIUM arithmetic, so the all-in
        # healthcare floor (MODEL_HEALTHCARE_COST_FLOOR) is switched off here:
        # at MAGI $80k the subsidised premium is ~$6.5k, well under the $24k
        # early-retirement band, so leaving the floor on would clamp every
        # assertion below to the band and test nothing about per-adult pricing.
        # The floor has its own coverage in TestHealthcareCostFloor.
        sandbox.MODEL_HEALTHCARE_COST_FLOOR = False
        sandbox.YOUR_AGE = your_age
        sandbox.PARTNER_AGE = partner_age
        p = AccountPortfolio()
        p.update_ages(your_age)
        return p.quote_health_insurance_cost(your_age, magi)

    def test_equal_ages_are_unchanged_pre_medicare(self, cfg_sandbox):
        """Identity for the default (equal-age MFJ) household: full ACA premium."""
        cfg_sandbox.MODEL_ACA_AGE_RATED = False  # identity is against the flat-band quote
        got = self._quote(cfg_sandbox, 60, 60)
        assert got == pytest.approx(cfg.calculate_aca_premium(self.MAGI))

    def test_equal_ages_are_unchanged_post_medicare(self, cfg_sandbox):
        """Identity for the default household once both are 65+: two enrollees."""
        got = self._quote(cfg_sandbox, 70, 70)
        assert got == pytest.approx(
            cfg.calculate_medicare_irmaa(self.MAGI, 1.0, enrollees=2)
        )

    def test_gapped_couple_keeps_paying_for_the_younger_spouse(self, cfg_sandbox):
        """Primary 65, spouse 55: one Medicare premium PLUS marketplace cover."""
        both_medicare = cfg.calculate_medicare_irmaa(self.MAGI, 1.0, enrollees=2)
        one_medicare = cfg.calculate_medicare_irmaa(self.MAGI, 1.0, enrollees=1)
        got = self._quote(cfg_sandbox, 65, 55)
        assert got > one_medicare, "younger spouse's coverage is missing"
        assert got != pytest.approx(both_medicare), (
            "still billing two Medicare premiums with one eligible person"
        )

    def test_gapped_couple_premium_does_not_collapse_at_65(self, cfg_sandbox):
        """The pre-65 -> 65 step must not be a windfall while a spouse is 55.

        Before the fix the modelled household premium DROPPED $6,554 -> $4,440
        (-32%) the year the primary turned 65, silently deleting ~10 more years of
        marketplace coverage for the 55-year-old spouse.
        """
        at_64 = self._quote(cfg_sandbox, 64, 54)
        at_65 = self._quote(cfg_sandbox, 65, 55)
        assert at_65 > 0.8 * at_64, (
            f"premium collapsed at 65 with a 10-year-younger spouse: "
            f"{at_64:,.0f} -> {at_65:,.0f}"
        )

    def test_single_filer_pays_one_medicare_premium(self, cfg_sandbox):
        """A single filer must be billed HALF what an equivalent couple is billed."""
        cfg_sandbox.FILING_STATUS = "Married filing jointly"
        couple = self._quote(cfg_sandbox, 70, 70)
        cfg_sandbox.FILING_STATUS = "Single"
        single = self._quote(cfg_sandbox, 70, 70)
        assert single == pytest.approx(0.5 * couple), (
            f"single filer charged {single:,.0f} vs couple {couple:,.0f} "
            "-- two Medicare premiums for one person"
        )


# ===========================================================================
# 72(t) SEPP is not a universal penalty waiver
# ===========================================================================
class TestSeppIsNotAUniversalWaiver:
    """A 72(t) exempts only its SCHEDULED distribution.

    ``_collect_sepp`` takes the scheduled amount off the traditional balances
    directly, so nothing that reaches ``_withdraw_single_pass`` is covered.
    Before the fix a plain ``sepp_active`` boolean was passed as ``sepp_covered``
    for the entire withdrawal, so a discretionary $500k net draw at age 50 booked
    $0 of 10% penalty (~$66,885 missing).
    """

    def _portfolio(self):
        p = AccountPortfolio()
        p.add_account(Account("your_401k", AccountType.TRADITIONAL_401K,
                              2_000_000.0, "you"))
        return p

    def test_discretionary_draw_is_penalized_while_a_sepp_runs(self, cfg_sandbox):
        _quiet_household(cfg_sandbox)
        cfg_sandbox.SEPP_72T_ENABLED = True
        cfg_sandbox.SEPP_72T_START_AGE = 45
        p = self._portfolio()
        # Start the schedule, then take an unscheduled draw.
        asim._collect_sepp(p, 45)
        assert p.sepp_start_age == 45
        before = p.total_early_withdrawal_penalties
        gross, _cost = p.withdraw_tax_efficient(500_000, your_age=50)
        penalty = p.total_early_withdrawal_penalties - before
        assert gross > 0
        assert penalty == pytest.approx(
            0.10 * gross, rel=1e-6
        ), "an active 72(t) still waives the penalty on unscheduled draws"

    def test_scheduled_distribution_itself_stays_penalty_free(self, cfg_sandbox):
        _quiet_household(cfg_sandbox)
        cfg_sandbox.SEPP_72T_ENABLED = True
        cfg_sandbox.SEPP_72T_START_AGE = 45
        p = self._portfolio()
        drawn, _tax = asim._collect_sepp(p, 45)
        assert drawn > 0
        assert p.total_early_withdrawal_penalties == 0.0


# ===========================================================================
# Roth ladder counts ordinary contribution basis
# ===========================================================================
class TestRothLadderContributionBasis:
    """Roth CONTRIBUTIONS are always penalty-free, ladder or not.

    ``free_room`` used to come solely from seasoned CONVERSION cohorts, so a Roth
    made entirely of contributions had zero free room: a $100k net draw at 50
    booked $11,111 of 10% penalty. Enabling a strategy meant to IMPROVE early
    access made the plan look strictly worse.
    """

    def _roth_only(self, balance=500_000.0):
        p = AccountPortfolio()
        p.add_account(Account("your_roth_ira", AccountType.ROTH_IRA, balance, "you"))
        return p

    def test_starting_balance_counts_as_basis(self, cfg_sandbox):
        _quiet_household(cfg_sandbox)
        cfg_sandbox.ROTH_LADDER_ENABLED = True
        p = self._roth_only()
        assert p.roth_contribution_basis == pytest.approx(500_000.0)
        gross, cost = p.withdraw_tax_efficient(100_000, your_age=50)
        assert cost == 0.0, "contribution basis was penalized under the ladder"
        assert gross == pytest.approx(100_000.0)
        assert p.total_early_withdrawal_penalties == 0.0

    def test_contributions_made_during_the_sim_count_as_basis(self, cfg_sandbox):
        _quiet_household(cfg_sandbox)
        cfg_sandbox.ROTH_LADDER_ENABLED = True
        p = AccountPortfolio()
        p.add_account(Account("your_roth_ira", AccountType.ROTH_IRA, 0.0, "you"))
        assert p.roth_contribution_basis == 0.0
        p.contribute("your_roth_ira", 50_000.0)
        assert p.roth_contribution_basis == pytest.approx(50_000.0)
        _gross, cost = p.withdraw_tax_efficient(40_000, your_age=50)
        assert cost == 0.0

    def test_money_beyond_basis_is_still_penalized(self, cfg_sandbox):
        """Growth / unseasoned conversions must NOT become free."""
        _quiet_household(cfg_sandbox)
        cfg_sandbox.ROTH_LADDER_ENABLED = True
        p = AccountPortfolio()
        p.add_account(Account("your_roth_ira", AccountType.ROTH_IRA, 0.0, "you"))
        p.contribute("your_roth_ira", 10_000.0)      # basis
        p.accounts["your_roth_ira"].balance += 90_000.0  # pure growth, not basis
        before = p.total_early_withdrawal_penalties
        p.withdraw_tax_efficient(50_000, your_age=50)
        assert p.total_early_withdrawal_penalties > before, (
            "the ladder no longer penalizes anything"
        )

    def test_conversions_do_not_inflate_contribution_basis(self, cfg_sandbox):
        """perform_roth_conversion must stay on the dated-cohort path."""
        _quiet_household(cfg_sandbox)
        p = AccountPortfolio()
        p.add_account(Account("your_roth_ira", AccountType.ROTH_IRA, 0.0, "you"))
        p.add_account(Account("your_401k", AccountType.TRADITIONAL_401K, 1e6, "you"))
        basis_before = p.roth_contribution_basis
        p.perform_roth_conversion(50)
        assert p.roth_contribution_basis == pytest.approx(basis_before), (
            "converted principal was miscounted as contribution basis"
        )


# ===========================================================================
# mc_parallel surfaces crashed simulations
# ===========================================================================
class TestSimTaskReportsErrors:
    """A crashed path must be counted, not silently dropped.

    ``sim_task`` swallowed every exception and reported ``n = len(finals)``, so a
    config that made 30% of paths raise produced a confident success rate over
    the surviving 70% with no warning anywhere.
    """

    def test_errors_are_counted_and_the_first_is_reported(self, monkeypatch):
        def boom(age, verbose=False):
            raise RuntimeError("synthetic engine crash")

        monkeypatch.setattr(mc_parallel.sim, "run_detailed_simulation", boom)
        out = mc_parallel.sim_task((50, 7, 2, 123))
        assert out["n"] == 0
        assert out["successes"] == 0
        assert out["errors"] == 7
        assert "synthetic engine crash" in out["first_error"]

    def test_partial_failure_is_visible(self, monkeypatch):
        """The mixed case is the dangerous one: n shrinks but errors explains it."""
        real = mc_parallel.sim.run_detailed_simulation
        state = {"i": 0}

        def flaky(age, verbose=False):
            state["i"] += 1
            if state["i"] % 2 == 0:
                raise ValueError("every other path fails")
            return real(age, verbose=False)

        monkeypatch.setattr(mc_parallel.sim, "run_detailed_simulation", flaky)
        out = mc_parallel.sim_task((50, 6, 1, 7))
        assert out["errors"] == 3
        assert out["n"] == 3
        assert out["n"] + out["errors"] == 6

    def test_clean_batch_reports_zero_errors(self):
        out = mc_parallel.sim_task((50, 3, 1, 11))
        assert out["errors"] == 0
        assert out["first_error"] is None
        assert out["n"] == 3


# --------------------------------------------------------------------------
# Unindexed tax thresholds must decay in real terms (2026-08-23)
# --------------------------------------------------------------------------
# The engine runs in an ALL-REAL frame (update_inflation_factors keeps `general`
# at 1.0 forever), so holding a NOMINAL threshold constant is identical to
# assuming it IS inflation-indexed. NIIT's $250k (fixed 2013) and the Social
# Security taxability thresholds $32k/$44k (fixed 1993) are not indexed by
# statute; Medicare IRMAA is (since 2020) and is deliberately NOT decayed.

def test_frozen_threshold_loses_real_value():
    from retirement_sim import config as cfg

    assert cfg.real_frozen_threshold(250_000, 0) == 250_000
    later = cfg.real_frozen_threshold(250_000, 60)
    assert 40_000 < later < 60_000, later          # ~$49k at 2.75%
    # Monotonically decreasing with time.
    seq = [cfg.real_frozen_threshold(250_000, y) for y in range(0, 50, 10)]
    assert seq == sorted(seq, reverse=True)


def test_frozen_threshold_handles_bad_input():
    from retirement_sim import config as cfg

    assert cfg.real_frozen_threshold(250_000, None) == 250_000
    assert cfg.real_frozen_threshold(250_000, -5) == 250_000
    assert cfg.real_frozen_threshold(250_000, "x") == 250_000


def test_toggle_off_reproduces_undecayed_behaviour():
    from retirement_sim import config as cfg

    original = cfg.MODEL_UNINDEXED_THRESHOLD_DECAY
    cfg.MODEL_UNINDEXED_THRESHOLD_DECAY = False
    try:
        assert cfg.real_frozen_threshold(250_000, 60) == 250_000
        assert cfg.calculate_niit(300_000, 100_000, 60) == cfg.calculate_niit(300_000, 100_000, 0)
    finally:
        cfg.MODEL_UNINDEXED_THRESHOLD_DECAY = original


def test_niit_bites_harder_later_in_the_plan():
    from retirement_sim import config as cfg

    early = cfg.calculate_niit(300_000, 100_000, 0)
    late = cfg.calculate_niit(300_000, 100_000, 40)
    assert late > early
    # Once the threshold has decayed below MAGI, the full NII is taxed at 3.8%.
    assert abs(late - 100_000 * 0.038) < 1.0


def test_social_security_becomes_more_taxable_later():
    from retirement_sim import config as cfg

    early = cfg.calculate_taxable_social_security(50_000, 40_000, 0)
    late = cfg.calculate_taxable_social_security(50_000, 40_000, 40)
    assert late > early
    # Capped at 85% of the benefit no matter how far the thresholds decay.
    assert late <= 50_000 * 0.85 + 1.0


def test_irmaa_is_not_decayed():
    """IRMAA HAS been indexed since 2020, so it must stay flat in a real frame."""
    import inspect

    from retirement_sim import config as cfg

    src = inspect.getsource(cfg.calculate_irmaa_surcharge) if hasattr(
        cfg, "calculate_irmaa_surcharge") else ""
    assert "real_frozen_threshold" not in src, (
        "IRMAA brackets are inflation-indexed; they must not be decayed"
    )


# ==============================================================================
# HEALTHCARE_COSTS_BY_AGE was a DEAD INPUT (2026-09-21)
# ==============================================================================
# The UI's healthcare editor wrote to cfg, but no engine code path ever called
# calculate_healthcare_cost() -- so the control changed the displayed
# assumptions and nothing else. It slipped past the inert-control audit because
# the attribute DOES exist on cfg; it was simply never read.
#
# Surfaced by an independent third-party review that modelled the exported
# healthcare assumptions faithfully and so charged what ours only documented.
#
# The two band groups are wired DIFFERENTLY on purpose, which is the subtle part
# and the reason a naive single floor is WRONG:
#   * 'early_retirement' IS a full-price ACA premium, so it drives the
#     unsubsidized CEILING. Flooring there would override a legitimate subsidy.
#   * 'medicare_*' are premium PLUS care, and out-of-pocket is charged nowhere
#     else, so they act as an all-in FLOOR for 65+.

class TestHealthcareCostFloor:
    MAGI_HIGH = 300_000     # well past the 400%-FPL cliff -> no subsidy
    MAGI_LOW = 40_000       # deep in subsidy territory

    def _quote(self, sandbox, your_age, magi, floor=True):
        sandbox.MODEL_HEALTHCARE_COST_FLOOR = floor
        p = AccountPortfolio()
        p.update_ages(your_age)
        return p.quote_health_insurance_cost(your_age, magi)

    def test_early_retirement_band_drives_the_unsubsidized_ceiling(self, cfg_sandbox):
        """Editing the band must move the full-price pre-65 premium."""
        cfg_sandbox.MODEL_ACA_AGE_RATED = False  # the band prices only the flat-band path
        hc = dict(cfg_sandbox.HEALTHCARE_COSTS_BY_AGE)
        base = self._quote(cfg_sandbox, 55, self.MAGI_HIGH)
        cfg_sandbox.HEALTHCARE_COSTS_BY_AGE = {**hc, "early_retirement": hc["early_retirement"] + 20_000}
        bumped = self._quote(cfg_sandbox, 55, self.MAGI_HIGH)
        cfg_sandbox.HEALTHCARE_COSTS_BY_AGE = hc
        assert bumped > base, "the healthcare editor is inert again (pre-65)"
        assert bumped - base == pytest.approx(20_000, abs=1.0)

    def test_subsidy_is_not_overridden_for_a_low_income_early_retiree(self, cfg_sandbox):
        """THE regression that a naive max() floor would cause.

        A low-income pre-65 retiree qualifies for a large ACA subsidy. Flooring
        at the $24k full-price band would charge them full price and silently
        delete the subsidy the engine went to trouble to model.
        """
        low = self._quote(cfg_sandbox, 55, self.MAGI_LOW)
        high = self._quote(cfg_sandbox, 55, self.MAGI_HIGH)
        band = cfg_sandbox.HEALTHCARE_COSTS_BY_AGE["early_retirement"]
        assert low < high, "premium must still scale with MAGI"
        assert low < band, f"subsidy overridden: charged {low:,.0f} vs band {band:,.0f}"

    @pytest.mark.parametrize("age,key", [(70, "medicare_base"), (80, "medicare_mid"), (90, "medicare_late")])
    def test_medicare_bands_act_as_an_all_in_floor(self, cfg_sandbox, age, key):
        """65+: out-of-pocket/care is charged nowhere else, so the band floors."""
        hc = dict(cfg_sandbox.HEALTHCARE_COSTS_BY_AGE)
        base = self._quote(cfg_sandbox, age, self.MAGI_HIGH)
        cfg_sandbox.HEALTHCARE_COSTS_BY_AGE = {**hc, key: hc[key] + 20_000}
        bumped = self._quote(cfg_sandbox, age, self.MAGI_HIGH)
        cfg_sandbox.HEALTHCARE_COSTS_BY_AGE = hc
        assert bumped > base, f"the {key} band is inert"

    def test_floor_never_double_counts_the_premium(self, cfg_sandbox):
        """Charged amount must equal max(premium, band) -- never premium + band."""
        for age in (70, 80, 90):
            premium_only = self._quote(cfg_sandbox, age, self.MAGI_HIGH, floor=False)
            with_floor = self._quote(cfg_sandbox, age, self.MAGI_HIGH, floor=True)
            band = cfg.calculate_healthcare_cost(age, True, 1.0)
            assert with_floor == pytest.approx(max(premium_only, band), abs=1.0), (
                f"age {age}: {with_floor:,.0f} != max({premium_only:,.0f}, {band:,.0f})"
            )

    def test_toggle_off_reproduces_premium_only_behaviour(self, cfg_sandbox):
        on = self._quote(cfg_sandbox, 90, self.MAGI_HIGH, floor=True)
        off = self._quote(cfg_sandbox, 90, self.MAGI_HIGH, floor=False)
        assert on > off, "the floor should bind at 85+ where care costs exceed premiums"

    def test_working_years_are_not_charged_the_pre_retirement_band(self, cfg_sandbox):
        """'pre_retirement' ($6k) is employer-payroll-deducted and already inside
        comp['after_tax']; charging it again would double-count. The premium
        methods are retirement-only, so assert the accumulation path never
        reaches them."""
        import inspect
        from retirement_sim import account_simulation as sim
        src = inspect.getsource(sim.simulate_accumulation_year)
        assert "health_insurance_cost" not in src
