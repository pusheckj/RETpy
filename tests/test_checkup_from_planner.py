"""The money check-up opens on the owner's planner numbers (utils/simple_to_full.from_planner,
components/simple_mode._open_on_own_numbers). Synthetic household only."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components import simple_mode as sm  # noqa: E402
from utils import derived, simple_to_full as s2f  # noqa: E402
from utils.derived import KEEP_AMOUNTS_MODE  # noqa: E402
from utils.simple_finance import DEFAULT_INPUTS, normalize_inputs  # noqa: E402

PLANNER = {
    "YOUR_AGE": 35, "PARTNER_AGE": 33, "STATE_CHOICE": "Texas", "FILING_STATUS": "Married filing jointly",
    "YOUR_BASE_SALARY": 120_000, "YOUR_BONUS_AMOUNT": 10_000, "PARTNER_BASE_SALARY": 80_000,
    "YOUR_401K_CONTRIBUTION": 13_000, "YOUR_401K_MATCH_PCT": 0.04, "PARTNER_401K_CONTRIBUTION": 8_000,
    "YOUR_HSA_CONTRIBUTION": 4_000, "YOUR_BACKDOOR_ROTH": 7_000,
    "YOUR_CASH": 20_000, "PARTNER_CASH": 10_000,
    "SPEND_UTILITIES_MONTHLY": 300, "SPEND_FOOD_MONTHLY": 900, "SPEND_TRANSPORT_MONTHLY": 500,
    "SPEND_HEALTH_MONTHLY": 400, "SPEND_DISCRETIONARY_MONTHLY": 1_200, "SPEND_OTHER_MONTHLY": 300,
    "PARTNER_OTHER_MONTHLY": 600, "MORTGAGE_MONTHLY": 2_800, "HOME_VALUE": 500_000,
    "SAVINGS_MODE": KEEP_AMOUNTS_MODE,
}


def test_cash_flow_matches_the_planners_savings_budget():
    r = s2f.from_planner(PLANNER)
    spend = derived.compute_expenses_today(PLANNER) / 12
    assert abs(r["needs_monthly"] + r["wants_monthly"] - spend) < 1.5
    assert r["wants_monthly"] == 1_200 + 600            # discretionary + partner's own spending
    # What's left each month = the planner's "left to save" minus the pre-tax saving it counts.
    pretax = sum(PLANNER.get(k, 0) for k in derived.PRETAX_KEYS)
    left = (r["take_home_monthly"] - r["needs_monthly"] - r["wants_monthly"]) * 12
    assert abs(left - (derived.savings_budget(PLANNER)["disposable"] - pretax)) < 20


def test_auto_allocate_uses_the_amounts_the_planner_works_out():
    auto = {k: v for k, v in PLANNER.items() if k != "SAVINGS_MODE"}       # Auto-allocate is the default
    amounts = derived.savings_budget(auto)["amounts"]
    r = s2f.from_planner(auto)
    assert abs(r["retirement_contrib_pct"] - 100 * amounts["YOUR_401K_CONTRIBUTION"] / 130_000) < 1e-6
    pretax = sum(amounts.get(k, 0) for k in derived.PRETAX_KEYS)
    left = (r["take_home_monthly"] - r["needs_monthly"] - r["wants_monthly"]) * 12
    assert abs(left - (derived.savings_budget(auto)["disposable"] - pretax)) < 20


def test_pay_and_retirement_answers_are_yours():
    r = s2f.from_planner(PLANNER)
    assert r["gross_salary_annual"] == 130_000
    assert abs(r["retirement_contrib_pct"] - 10.0) < 1e-6
    assert abs(r["employer_match_pct"] - 4.0) < 1e-9
    assert r["hsa_eligible"] and r["hsa_family"] and r["hsa_contrib_annual"] == 4_000
    assert r["ira_contrib_annual"] == 7_000
    assert r["cash_savings"] == 30_000
    assert r["debts"] == []                              # a mortgage is not a check-up debt
    assert s2f.used(r)
    assert normalize_inputs(r) == r


def test_single_without_hsa_or_partner():
    r = s2f.from_planner({"YOUR_AGE": 30, "YOUR_BASE_SALARY": 60_000, "YOUR_401K_CONTRIBUTION": 3_000,
                          "SAVINGS_MODE": KEEP_AMOUNTS_MODE})
    assert not r["hsa_eligible"] and not r["hsa_family"]
    assert r["take_home_monthly"] > 0


class _NoHosting:
    pass


def _seed(monkeypatch, hosted, profile):
    import components.profile_picker as pp
    import utils.hosting as hosting
    monkeypatch.setattr(hosting, "is_hosted", lambda: hosted)
    monkeypatch.setattr(pp, "load_personal_profile", lambda path=None: profile)
    ss = {"user_overrides": dict(PLANNER)}
    sm._open_on_own_numbers(ss)
    return ss


def test_owner_machine_opens_on_planner_numbers(monkeypatch):
    ss = _seed(monkeypatch, hosted=False, profile=("Me", {}))
    assert ss[sm.STATE_KEY]["gross_salary_annual"] == 130_000


def test_hosted_visitors_keep_the_example_numbers(monkeypatch):
    ss = _seed(monkeypatch, hosted=True, profile=("Me", {}))
    assert sm.STATE_KEY not in ss
    ss = _seed(monkeypatch, hosted=False, profile=None)           # no personal profile
    assert sm.STATE_KEY not in ss


def test_own_checkup_answers_are_never_overwritten(monkeypatch):
    import components.profile_picker as pp
    import utils.hosting as hosting
    monkeypatch.setattr(hosting, "is_hosted", lambda: False)
    monkeypatch.setattr(pp, "load_personal_profile", lambda path=None: ("Me", {}))
    mine = normalize_inputs({**DEFAULT_INPUTS, "cash_savings": 1_234.0})
    ss = {"user_overrides": dict(PLANNER), sm.STATE_KEY: mine}
    sm._open_on_own_numbers(ss)
    assert ss[sm.STATE_KEY] == mine
    ss2 = {"user_overrides": dict(PLANNER)}
    sm._open_on_own_numbers(ss2)
    ss2[sm.STATE_KEY]["cash_savings"] = 5.0
    sm._open_on_own_numbers(ss2)                                   # once per session
    assert ss2[sm.STATE_KEY]["cash_savings"] == 5.0
