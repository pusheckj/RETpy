"""Your employer's HSA deposit (YOUR_HSA_MATCH).

The engine used to ignore it: the simulated HSA got only your own amount, while
the savings table showed both. Now the deposit reaches the balance, is not paid
from take-home, and shares the IRS limit with your own amount. Max out sets your
amount to limit minus the employer's. A warning shows when the two are over the
limit. Saved Roth-conversion targets from the 2025 table follow the default.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import account_simulation as asim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from utils import derived, planner_max as pm  # noqa: E402
from utils.config_builder import build_config_overrides  # noqa: E402

LIMIT_FAMILY = 8_750


@pytest.fixture
def hsa(monkeypatch):
    """Set the HSA inputs for one test (restored after): family coverage, TX."""
    def _set(contribution, match, family=True, state="TX"):
        monkeypatch.setattr(cfg, "YOUR_HSA_CONTRIBUTION", contribution)
        monkeypatch.setattr(cfg, "YOUR_HSA_MATCH", match)
        monkeypatch.setattr(cfg, "hsa_is_family", lambda: family)
        monkeypatch.setattr(cfg, "STATE_CHOICE", state)
    return _set


def _cf(age=None):
    return asim.working_year_cashflow(cfg.YOUR_AGE if age is None else age)


# ------------------------------------------------------------------- engine

def test_cash_flow_reports_the_employer_deposit(hsa):
    hsa(2_000, 750)
    cf = _cf()
    assert cf["your_hsa"] == 2_000
    assert cf["your_hsa_employer"] == 750


def test_deposit_goes_into_the_hsa_account_each_working_year(hsa):
    def first_year_hsa(match):
        hsa(2_000, match)
        _, p = asim.run_detailed_simulation(50, random_seed=11)
        return p.yearly_history[1]["accounts"]["your_hsa"]    # after the first working year

    # Same seed, same returns: the only difference is the employer's deposit.
    assert first_year_hsa(750) - first_year_hsa(0) == pytest.approx(750)


def test_employer_money_is_not_paid_from_take_home(hsa):
    hsa(2_000, 0)
    without = _cf()
    hsa(2_000, 750)
    with_match = _cf()
    assert with_match["your_take_home"] == pytest.approx(without["your_take_home"])
    assert with_match["federal"] == pytest.approx(without["federal"])
    assert with_match["fica"] == pytest.approx(without["fica"])


def test_california_taxes_the_employer_deposit_but_federal_does_not(hsa):
    hsa(2_000, 0, state="CA")
    without = _cf()
    hsa(2_000, 750, state="CA")
    with_match = _cf()
    assert with_match["federal"] == pytest.approx(without["federal"])
    assert with_match["state"] > without["state"]
    # It is a tax paid from take-home, not a deduction from it.
    assert with_match["your_take_home"] < without["your_take_home"]


def test_a_state_that_does_not_tax_hsa_ignores_the_employer_deposit():
    base = cfg.working_year_taxes(150_000, 0, status="S", partner=False, state="NY",
                                  your_hsa=2_000)
    plus = cfg.working_year_taxes(150_000, 0, status="S", partner=False, state="NY",
                                  your_hsa=2_000, your_hsa_employer=750)
    assert cfg.state_tax_rules("NY", "S")["hsa_taxed"] is False
    assert plus["total"] == pytest.approx(base["total"])


def test_employee_plus_employer_stay_inside_the_limit(hsa):
    hsa(8_300, 750)                                  # the audit's example
    cf = _cf()
    assert cf["your_hsa_employer"] == 750
    assert cf["your_hsa"] == 8_000
    assert cf["your_hsa"] + cf["your_hsa_employer"] == LIMIT_FAMILY


def test_employer_deposit_is_held_to_the_limit_itself(hsa):
    hsa(3_000, 12_000)
    cf = _cf()
    assert cf["your_hsa_employer"] == LIMIT_FAMILY
    assert cf["your_hsa"] == 0


def test_an_amount_at_todays_room_still_means_the_max_and_follows_the_limit(hsa):
    hsa(LIMIT_FAMILY - 750, 750)                     # what Max out stores
    age = cfg.YOUR_AGE
    assert _cf(age)["your_hsa"] == LIMIT_FAMILY - 750
    hsa_55 = cfg.get_hsa_limit(55, cfg.CURRENT_YEAR + 55 - cfg.YOUR_AGE, is_family=True)
    assert hsa_55 == LIMIT_FAMILY + 1_000            # catch-up from 55
    cf = _cf(55)
    assert cf["your_hsa"] + cf["your_hsa_employer"] == hsa_55


def test_a_smaller_set_amount_stays_flat(hsa):
    hsa(3_000, 750)
    for age in (cfg.YOUR_AGE, 40, 55):
        assert _cf(age)["your_hsa"] == 3_000


def test_no_employer_deposit_changes_nothing(hsa):
    """YOUR_HSA_MATCH = 0 is the old behaviour, to the dollar."""
    for amount in (0, 2_000, LIMIT_FAMILY, 20_000):
        hsa(amount, 0)
        cf = _cf()
        limit = cfg.get_hsa_limit(cfg.YOUR_AGE, cfg.CURRENT_YEAR, is_family=True)
        old = max(0.0, min(asim._contribution_for_year(float(amount), limit, limit),
                           cf["your_wages"] - cf["your_401k"]))
        assert cf["your_hsa"] == old
        assert cf["your_hsa_employer"] == 0.0


def test_no_deposit_in_a_year_you_do_not_work(hsa):
    hsa(2_000, 750)
    cf = asim.working_year_cashflow(cfg.YOUR_AGE, partner_working=True, you_working=False)
    assert cf["your_hsa_employer"] == 0.0
    assert cf["your_hsa"] == 0.0


# --------------------------------------------------------------- UI agrees

def test_savings_table_shows_what_the_engine_deposits(hsa):
    from utils import sim_runner as sr
    hsa(2_000, 750)
    row = sr._approximate_savings_contributions(cfg.YOUR_AGE + 5)[0]
    cf = _cf()
    assert row["your_hsa"] == pytest.approx(cf["your_hsa"] + cf["your_hsa_employer"])
    # Over the limit the table shows the capped total, not 8,300 + 750.
    hsa(8_300, 750)
    row = sr._approximate_savings_contributions(cfg.YOUR_AGE + 5)[0]
    assert row["your_hsa"] == pytest.approx(LIMIT_FAMILY)


def _household(**kw):
    base = {"YOUR_AGE": 40, "PARTNER_AGE": 38, "FILING_STATUS": "MFJ", "STATE_CHOICE": "TX",
            "YOUR_BASE_SALARY": 120_000, "PARTNER_BASE_SALARY": 80_000}
    base.update(kw)
    return base


def test_sidebar_tax_uses_the_same_employee_cap_as_the_engine():
    o = _household(YOUR_HSA_CONTRIBUTION=8_300, YOUR_HSA_MATCH=750)
    kw = derived._working_tax_inputs(o)
    assert kw["your_hsa"] == 8_000
    assert kw["your_hsa_employer"] == 750


def test_auto_allocate_and_custom_percent_leave_room_for_the_employer():
    o = _household(YOUR_HSA_MATCH=750)
    caps = derived.custom_pct_amounts({"YOUR_HSA_CONTRIBUTION": 100}, 1_000_000, o)
    assert caps["YOUR_HSA_CONTRIBUTION"] == LIMIT_FAMILY - 750
    auto = derived.auto_allocate_defaults(o)
    assert auto["YOUR_HSA_CONTRIBUTION"] <= LIMIT_FAMILY - 750


# ---------------------------------------------------------------- Max out

def test_max_out_is_the_limit_minus_the_employer_amount():
    o = _household(YOUR_HSA_MATCH=750)
    assert pm.irs_limit(pm.YOUR_HSA, o) == LIMIT_FAMILY - 750
    assert pm.max_out_target(pm.YOUR_HSA, o) == LIMIT_FAMILY - 750
    assert pm.max_out_updates(o)[pm.YOUR_HSA] == LIMIT_FAMILY - 750


def test_max_out_without_employer_money_is_the_plain_limit():
    assert pm.max_out_target(pm.YOUR_HSA, _household()) == LIMIT_FAMILY
    assert pm.max_out_target(pm.YOUR_HSA, _household(YOUR_HSA_MATCH=0)) == LIMIT_FAMILY


def test_at_the_limit_once_your_amount_plus_employer_is_full():
    o = _household(YOUR_HSA_MATCH=750, YOUR_HSA_CONTRIBUTION=LIMIT_FAMILY - 750)
    assert pm.max_out_state(pm.YOUR_HSA, o).state == pm.AT_LIMIT


def test_max_out_tooltip_names_the_employer_share():
    o = _household(YOUR_HSA_MATCH=750)
    assert "from your employer" in pm.max_out_help(pm.YOUR_HSA, o, LIMIT_FAMILY - 750)


def test_employer_deposit_beyond_the_limit_leaves_nothing_to_max_out():
    o = _household(YOUR_HSA_MATCH=20_000)
    assert pm.max_out_state(pm.YOUR_HSA, o).state == pm.NONE


# ----------------------------------------------------------------- warning

def test_warning_text_for_amount_plus_employer_over_the_limit():
    note = derived.hsa_limit_note(8_300, 750, 8_750)
    assert note == ("Your \\$8,300 plus \\$750 from your employer is \\$300 over the "
                    "\\$8,750 limit. The plan uses \\$8,000.")


def test_no_warning_at_or_under_the_limit():
    assert derived.hsa_limit_note(8_000, 750, 8_750) is None
    assert derived.hsa_limit_note(0, 0, 8_750) is None


def test_warning_when_your_amount_alone_or_the_employer_alone_is_over():
    assert "over the \\$8,750 HSA limit" in derived.hsa_limit_note(9_000, 0, 8_750)
    assert "Your employer's" in derived.hsa_limit_note(0, 9_000, 8_750)


def test_check_up_note_leaves_out_the_plan():
    note = derived.hsa_limit_note(9_000, 0, 8_750, plan=False)
    assert "over the" in note and "plan" not in note


def _investments(monkeypatch, overrides):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("HSA_TEST_UI", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")

    def script():
        import os
        import sys
        sys.path[:0] = [os.environ["HSA_TEST_UI"], os.path.dirname(os.environ["HSA_TEST_UI"])]
        import streamlit as st
        from components import sec_investments
        sec_investments.render(st)

    at = AppTest.from_function(script, default_timeout=60)
    at.session_state["user_overrides"] = dict(overrides)
    at.run()
    assert not at.exception, at.exception
    return at


def test_investments_section_warns_next_to_the_hsa_input(monkeypatch):
    from utils.derived import KEEP_AMOUNTS_MODE
    ov = _household(SAVINGS_MODE=KEEP_AMOUNTS_MODE, YOUR_HSA_CONTRIBUTION=8_300,
                    YOUR_HSA_MATCH=750)
    at = _investments(monkeypatch, ov)
    warnings = [w.value for w in at.warning]
    assert any("\\$300 over the \\$8,750 limit" in w and "The plan uses \\$8,000" in w
               for w in warnings), warnings
    assert any(n.key == "sv_hsa_match" and n.value == 750 for n in at.number_input)


def test_investments_section_is_quiet_inside_the_limit(monkeypatch):
    from utils.derived import KEEP_AMOUNTS_MODE
    ov = _household(SAVINGS_MODE=KEEP_AMOUNTS_MODE, YOUR_HSA_CONTRIBUTION=8_000,
                    YOUR_HSA_MATCH=750)
    at = _investments(monkeypatch, ov)
    assert not [w for w in at.warning if "HSA limit" in w.value or "limit." in w.value]


# --------------------------------------------- stale Roth-conversion targets

@pytest.mark.parametrize("stored", [
    94_300, 47_150, 63_100,         # 2024: joint, single, head of household
    96_950, 48_475, 64_850,         # 2025: joint, single, head of household
])
def test_old_default_roth_targets_follow_the_filing_status(stored):
    for status in ("Married filing jointly", "Single", "Head of household"):
        out = build_config_overrides({"FILING_STATUS": status,
                                      "ROTH_CONVERSION_TARGET_BRACKET": stored})
        assert out["ROTH_CONVERSION_TARGET_BRACKET"] is None


@pytest.mark.parametrize("custom", [0, 60_000, 96_951, 97_000, 100_000, 100_800])
def test_custom_roth_targets_are_never_touched(custom):
    out = build_config_overrides({"FILING_STATUS": "Married filing jointly",
                                  "ROTH_CONVERSION_TARGET_BRACKET": custom})
    assert out["ROTH_CONVERSION_TARGET_BRACKET"] == custom


def test_a_saved_2025_target_now_means_the_2026_default_in_the_engine():
    out = build_config_overrides({"FILING_STATUS": "Married filing jointly",
                                  "ROTH_CONVERSION_TARGET_BRACKET": 96_950})
    assert out["ROTH_CONVERSION_TARGET_BRACKET"] is None
    assert cfg.ROTH_CONVERSION_TARGET_BY_STATUS[cfg.normalize_filing_status("MFJ")] == 100_800
