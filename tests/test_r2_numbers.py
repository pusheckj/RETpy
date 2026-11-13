"""Round-2 number fixes: withdrawal-rate definition, effective tax rate, staggered
retirements, age-following contribution limits, 2026 presets, the bridge for an
older partner, the health-band note and common random numbers on the age curve.
"""
import os
import sys
from contextlib import contextmanager

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import account_simulation as asim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import mc_jobs  # noqa: E402
from tests.conftest import load_sample_household  # noqa: E402
from utils import sim_runner as sr  # noqa: E402


@contextmanager
def applied(ov: dict):
    """The overrides written onto the shared config, restored afterwards."""
    original = sr._apply_overrides(sr.build_config_overrides(ov))
    try:
        yield
    finally:
        sr._restore_overrides(original)


@contextmanager
def raw(values: dict):
    """Raw config values (no UI translation)."""
    original = sr._apply_overrides(values)
    try:
        yield
    finally:
        sr._restore_overrides(original)


# ----------------------------------------------------------- 1. withdrawal rate

def test_first_full_retirement_year_waits_for_a_working_partner():
    ov = load_sample_household()            # you 34, partner 33: one year apart
    ov.update(TARGET_RETIREMENT_AGE=45, PARTNER_RETIREMENT_AGE=50)
    with applied(ov):
        assert mc_jobs.first_full_retirement_age(45) == 51      # partner stops at 50 = your 51
    ov.update(PARTNER_RETIREMENT_AGE=None)
    with applied(ov):
        assert mc_jobs.first_full_retirement_age(45) == 45
    ov.update(PARTNER_RETIREMENT_AGE=40, PARTNER_AGE=33)        # partner already stopped
    with applied(ov):
        assert mc_jobs.first_full_retirement_age(45) == 45


def test_swr_rate_excludes_the_still_working_partners_pay():
    """Year 1 draws only the gap left after the partner's pay; the rate is read in
    the first year nobody works, so it matches the real portfolio draw."""
    ov = load_sample_household()
    ov.update(TARGET_RETIREMENT_AGE=45, PARTNER_RETIREMENT_AGE=50)
    with applied(ov):
        w1 = mc_jobs.median_year1_withdrawal(45, n=1)
        mc_jobs._seed(13579)
        _ok, pf = asim.run_detailed_simulation(45)
        by_age = {r["age"]: r["total"] for r in pf.withdrawal_log}
    assert w1 == pytest.approx(by_age[51])
    assert by_age[51] > 1.5 * by_age[45], "the working partner's pay should cut the year-1 draw"


# ------------------------------------------------------- 2. effective tax rate

def _tax_row(age, total, rmd_gross, rmd_spent, taxes, conversion=0.0):
    return {"age": age, "total": total, "rmd_gross": rmd_gross, "rmd_spent": rmd_spent,
            "total_taxes": taxes, "niit": 0.0, "state_tax": 0.0, "roth_conversion": conversion}


def test_effective_retirement_rate_uses_gross_rmd_not_the_rmd_net_of_tax():
    """Hand case: a $300k RMD taxed 40% leaves $180k spent. The rate is 120/300."""
    ov = load_sample_household()
    ov.update(INCLUDE_SOCIAL_SECURITY=False, TARGET_RETIREMENT_AGE=60, PARTNER_RETIREMENT_AGE=None)
    with applied(ov):
        rows = sr._approximate_taxes([_tax_row(75, 180_000, 300_000, 180_000, 120_000)], 60)
    row = next(r for r in rows if r["age"] == 75)
    assert row["gross_income"] == pytest.approx(300_000)
    tax = row["federal"] + row["state"] + row["fica"] + row["ltcg"] + row["niit"]
    assert tax == pytest.approx(120_000)
    assert tax / row["gross_income"] == pytest.approx(0.40)


def test_reinvested_rmd_and_conversion_stay_in_the_denominator():
    ov = load_sample_household()
    ov.update(INCLUDE_SOCIAL_SECURITY=False, TARGET_RETIREMENT_AGE=60, PARTNER_RETIREMENT_AGE=None)
    with applied(ov):
        # $100k spent, a $60k RMD of which $20k was reinvested, a $30k conversion.
        rows = sr._approximate_taxes([_tax_row(70, 100_000, 60_000, 40_000, 25_000, conversion=30_000)], 60)
    assert next(r for r in rows if r["age"] == 70)["gross_income"] == pytest.approx(150_000)


# ------------------------------------------------- 3. staggered retirement years

def _staggered():
    ov = load_sample_household()
    ov.update(TARGET_RETIREMENT_AGE=45, PARTNER_RETIREMENT_AGE=50)   # partner works to your 51
    return ov


def test_partner_working_years_appear_in_savings_rows():
    with applied(_staggered()):
        rows = sr._approximate_savings_contributions(45)
    by_age = {r["age"]: r for r in rows}
    assert max(by_age) == 50 and 45 in by_age
    for age in range(45, 51):
        r = by_age[age]
        assert r["your_401k"] == 0 and r["your_brokerage"] == 0 and r["your_roth"] == 0
        assert r["partner_401k"] > 0 and r["partner_roth"] > 0
        assert r["gross_income"] > 0 and r["after_tax_income"] > 0
    assert by_age[44]["your_401k"] > 0                                    # still working: unchanged


def test_partner_working_years_appear_in_tax_rows():
    with applied(_staggered()):
        rows = sr._approximate_taxes([], 45)
    by_age = {r["age"]: r for r in rows}
    for age in range(45, 51):
        assert by_age[age]["fica"] > 0 and by_age[age]["federal"] > 0
        assert by_age[age]["gross_income"] > 0
    assert by_age[52]["fica"] == 0 and by_age[52]["gross_income"] == 0     # nobody works


# ------------------------------------------------- 4. limits follow the age

def test_a_maxed_amount_follows_the_limit_as_you_age():
    ov = load_sample_household()
    lim = cfg.CONTRIBUTION_LIMITS_2026
    ov.update(YOUR_AGE=40, PARTNER_AGE=38, PARTNER_RETIREMENT_AGE=None,
              YOUR_401K_CONTRIBUTION=lim["401k"], PARTNER_401K_CONTRIBUTION=lim["401k"],
              YOUR_HSA_CONTRIBUTION=lim["hsa_family"], YOUR_BACKDOOR_ROTH=lim["ira"],
              PARTNER_ROTH_CONTRIBUTION=lim["ira"], YOUR_AFTER_TAX_401K_PCT=0.0)
    with applied(ov):
        cf40 = asim.working_year_cashflow(40)
        cf51 = asim.working_year_cashflow(51)
        cf61 = asim.working_year_cashflow(61)         # you 61 (60-63), partner 59
    assert cf40["your_401k"] == lim["401k"] and cf40["your_hsa"] == lim["hsa_family"]
    assert cf51["your_401k"] == lim["401k"] + lim["401k_catchup"]
    assert cf51["your_roth"] == lim["ira"] + lim["ira_catchup"]
    assert cf51["partner_401k"] == lim["401k"]                            # partner is 49
    assert cf61["your_401k"] == lim["401k"] + lim["401k_supercatchup"]
    assert cf61["your_hsa"] == lim["hsa_family"] + lim["hsa_catchup"]
    assert cf61["partner_401k"] == lim["401k"] + lim["401k_catchup"]      # partner is 59
    assert cf61["partner_roth"] == lim["ira"] + lim["ira_catchup"]


def test_a_deliberate_smaller_amount_stays_flat():
    ov = load_sample_household()
    ov.update(YOUR_AGE=40, PARTNER_RETIREMENT_AGE=None, YOUR_401K_CONTRIBUTION=10_000,
              YOUR_BACKDOOR_ROTH=3_000, YOUR_HSA_CONTRIBUTION=2_000)
    with applied(ov):
        cf = asim.working_year_cashflow(61)
    assert (cf["your_401k"], cf["your_roth"], cf["your_hsa"]) == (10_000, 3_000, 2_000)


# --------------------------------------------------------- 5. 2026 presets

def test_presets_and_sensitivity_grid_use_the_2026_limits():
    from components import profile_picker as pp
    from components import sensitivity_tab as stab
    lim = cfg.CONTRIBUTION_LIMITS_2026
    young = pp.PROFILES["Young professional (28, single)"]
    couple = pp.PROFILES["Mid-career couple (40, kids)"]
    assert young["YOUR_401K_CONTRIBUTION"] == couple["YOUR_401K_CONTRIBUTION"] == lim["401k"]
    assert young["YOUR_BACKDOOR_ROTH"] == lim["ira"]
    assert young["YOUR_HSA_CONTRIBUTION"] == lim["hsa_individual"]      # single, no kids
    assert couple["YOUR_HSA_CONTRIBUTION"] == lim["hsa_family"]
    k401 = stab._BREAK_EVEN_PARAMS["Your 401(k) contribution ($/yr)"][1]
    hsa = stab._BREAK_EVEN_PARAMS["Your HSA contribution ($/yr)"][1]
    assert lim["401k"] in k401 and lim["hsa_individual"] in hsa and lim["hsa_family"] in hsa
    assert k401 == sorted(k401) and hsa == sorted(hsa)
    assert not {23_000, 4_150, 7_550} & set(k401 + hsa)


# ------------------------------------------------- 6. bridge, older partner

def _bt_log(ages, k401=400_000.0, partner_k401=250_000.0):
    return [{"age": a, "cash": 50_000.0, "taxable": 100_000.0, "roth_ira": 60_000.0,
             "traditional_401k": k401, "traditional_ira": 0.0, "hsa": 10_000.0,
             "partner_traditional_401k": partner_k401} for a in ages]


def _accessible(you, partner, retirement_age, ages, **extra):
    vals = {"YOUR_AGE": you, "PARTNER_AGE": partner, "PARTNER_RETIREMENT_AGE": None,
            "RULE_OF_55_ENABLED": False, "SEPP_72T_ENABLED": False}
    vals.update(extra)
    with raw(vals):
        return sr._accessible_percentiles([_bt_log(ages)], [], retirement_age)


def test_bridge_counts_an_older_partners_401k_by_their_age():
    rows = _accessible(50, 60, 52, range(52, 62))       # partner is 10 years older: 62 at your 52
    r = rows[0]
    assert r["partner_open"] == 250_000
    assert r["accessible"] == 50_000 + 100_000 + 60_000 + 250_000
    assert r["penalized"] == pytest.approx(400_000 - 250_000 + 10_000)   # your 401(k) share and HSA


def test_bridge_waits_for_a_younger_partner_to_reach_59_and_a_half():
    rows = {r["age"]: r for r in _accessible(50, 44, 52, range(52, 62))}   # partner is 6 years younger
    assert rows[52]["partner_open"] == 0
    assert rows[52]["accessible"] == 210_000
    assert rows[52]["penalized"] == pytest.approx(410_000)
    # 59.5 for the partner arrives at your 65: past the window, still not open at 61.
    assert rows[60]["partner_open"] == 0


def test_bridge_rule_of_55_follows_each_owners_own_age():
    # You are 50, the partner 56 and retired with you. You retire at 52: your own Rule of 55 is not
    # open, but the partner is 58 and left work at 58, so THEIR 401(k) is. At 60 it opens outright.
    rows = {r["age"]: r for r in _accessible(50, 56, 52, range(52, 62), RULE_OF_55_ENABLED=True)}
    assert rows[52]["rule55"] == 250_000 and rows[52]["partner_open"] == 0
    assert rows[54]["rule55"] == 0 and rows[54]["partner_open"] == 250_000
    # You retire at 56 (your Rule of 55 frees your 401(k)); the partner, 54 then, has no Rule of 55.
    rows = {r["age"]: r for r in _accessible(54, 52, 56, range(56, 62), RULE_OF_55_ENABLED=True)}
    assert rows[56]["rule55"] == pytest.approx(150_000) and rows[56]["partner_open"] == 0


def test_engine_penalty_follows_the_account_owners_age():
    ov = load_sample_household()
    ov.update(PARTNER_RETIREMENT_AGE=None)

    def penalty(you_age, partner_age):
        ov.update(YOUR_AGE=you_age, PARTNER_AGE=partner_age)
        with applied(ov):
            pf = asim.create_initial_portfolio()
            for acc in pf.accounts.values():
                acc.balance = 0.0
            pf.accounts["partner_401k"].balance = 500_000.0
            pf.reset_yearly_income()
            pf.update_ages(you_age)
            pf.withdraw_tax_efficient(50_000.0, is_medical=False, your_age=you_age)
            return pf.total_early_withdrawal_penalties

    assert penalty(52, 62) == 0                 # partner is 62: no penalty although you are 52
    assert penalty(52, 50) > 0                  # partner is 50: penalty
    assert penalty(62, 55) > 0                  # you are 62 but the 401(k) is the partner's, age 55


# ------------------------------------------------- 7. health band note

def test_health_band_note_explains_the_employer_plan_years():
    from components import spending_chart as sc
    health = {a: 0.0 for a in range(55, 60)} | {60: 46_000.0, 61: 48_000.0}
    note = sc._health_gap_note(health, 55, {"PARTNER_AGE": 36})
    assert "age 60" in note and "employer plan" in note
    assert sc._health_gap_note({55: 30_000.0, 56: 31_000.0}, 55, {"PARTNER_AGE": 36}) == ""
    assert "employer" not in sc._health_gap_note(health, 55, {"PARTNER_AGE": 0})


# ------------------------------------------------- 9. social security notes

def test_full_retirement_age_is_67_and_survivor_note_is_in_the_faq():
    from components import faq
    assert cfg.ss_claim_factor(67) == pytest.approx(1.0)
    assert cfg.ss_claim_factor(62) == pytest.approx(0.70)
    text = " ".join(f"{q} {a}" for q, a in faq.QUESTIONS)
    assert "survivor" in text and "1960" in text


# ------------------------------------------------- 10. common random numbers

def test_age_scans_share_one_seed_so_ages_replay_the_same_paths():
    ov = load_sample_household()
    sr.clear_cache()
    plan = sr.plan_full_analysis(ov, n_simulations=400, target_retirement_age=45,
                                 scan_age_range=(40, 50, 1))
    seeds = {c[2][2] for c in plan.job["calls"] if c[0] == "scan"}
    assert seeds == {1000}


def test_scan_age_seeds_path_i_with_seed_plus_i():
    ov = load_sample_household()
    with applied(ov):
        got = mc_jobs.scan_age(45, 6, 77, 0.8, min_n=6)
        want = 0
        for i in range(6):
            ok, _pf = asim.run_detailed_simulation(45, random_seed=77 + i)
            want += bool(ok)
    assert got["n"] == 6 and got["successes"] == want
