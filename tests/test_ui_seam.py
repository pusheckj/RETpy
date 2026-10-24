"""Pinning tests for the UI seam: config_builder + sim_runner override plumbing.

These pin the currently-verified behavior of:
- build_config_overrides (quick-key translation)
- _apply_overrides / _recompute_derived / _restore_overrides (global mutation + restore)
- derived-constant propagation after a base-input override (pins the
  _recompute_derived fix for YOUR_HSA_TOTAL, RETIREMENT_ANNUAL_EXPENSES,
  COLLEGE_TARGET_PER_CHILD).

sim_runner imports ``from retirement_sim import config`` and
``from utils.config_builder import build_config_overrides``. The ``retirement_sim``
package is importable from ROOT, but ``utils`` lives under ``ui/``; we add both the
project root and ``ui/`` to sys.path so the same imports resolve under
``pytest tests/`` from ROOT.
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
from utils import sim_runner as sr
from utils.config_builder import build_config_overrides
from utils import widget_sync as ws


# ---------------------------------------------------------------------------
# (a) build_config_overrides translates the quick keys correctly
# ---------------------------------------------------------------------------

def test_build_config_overrides_passes_through_direct_keys():
    out = build_config_overrides({"MORTGAGE_MONTHLY": 3000})
    assert out["MORTGAGE_MONTHLY"] == 3000
    # UI-only keys are dropped, never passed through as config attributes.
    assert "TARGET_RETIREMENT_AGE" not in build_config_overrides(
        {"TARGET_RETIREMENT_AGE": 55}
    )


def test_build_config_overrides_household_income_quick():
    out = build_config_overrides({"HOUSEHOLD_INCOME_QUICK": 200_000, "YOUR_AGE": 30})
    # 55/45 split: partner gets income - int(income*0.55).
    assert out["PARTNER_SALARY"] == 200_000 - int(200_000 * 0.55)
    assert out["PARTNER_SALARY"] == 90_000
    # Synthesized comp table starts at YOUR_AGE with primary = int(income*0.55).
    table = out["YOUR_COMPENSATION_BY_AGE"]
    assert table[30]["base"] == int(200_000 * 0.55)
    assert table[30]["base"] == 110_000


def test_build_config_overrides_total_savings_quick_allocates():
    out = build_config_overrides({"TOTAL_SAVINGS_QUICK": 1_000_000})
    # Allocation across account types (see _DEFAULT_SAVINGS_ALLOCATION).
    assert out["YOUR_401K"] == int(1_000_000 * 0.30)
    assert out["PARTNER_401K"] == int(1_000_000 * 0.20)


def test_explicit_account_override_suppresses_savings_allocation():
    # When the user has explicitly set an account, TOTAL_SAVINGS_QUICK is NOT
    # spread across accounts; the manual value wins and YOUR_CASH is absent.
    out = build_config_overrides({"TOTAL_SAVINGS_QUICK": 1_000_000, "YOUR_401K": 12_345})
    assert out["YOUR_401K"] == 12_345
    assert "YOUR_CASH" not in out


# ---------------------------------------------------------------------------
# (b) _apply_overrides mutates cfg then _restore_overrides restores exactly
# ---------------------------------------------------------------------------

def test_apply_then_restore_roundtrip():
    before_monthly = cfg.MORTGAGE_MONTHLY
    before_annual = cfg.MORTGAGE_ANNUAL

    original = sr._apply_overrides({"MORTGAGE_MONTHLY": 9999})
    assert cfg.MORTGAGE_MONTHLY == 9999
    assert cfg.MORTGAGE_ANNUAL == 9999 * 12  # derived recomputed

    sr._restore_overrides(original)
    assert cfg.MORTGAGE_MONTHLY == before_monthly
    assert cfg.MORTGAGE_ANNUAL == before_annual


def test_restore_recovers_derived_totals():
    before_401k = cfg.YOUR_401K
    before_total_ret = cfg.TOTAL_RETIREMENT_ACCOUNTS
    before_net_worth = cfg.TOTAL_NET_WORTH

    original = sr._apply_overrides({"YOUR_401K": before_401k + 100_000})
    # Base input mutated; dependent totals shift by the same delta.
    assert cfg.YOUR_401K == before_401k + 100_000
    assert cfg.TOTAL_RETIREMENT_ACCOUNTS == before_total_ret + 100_000
    assert cfg.TOTAL_NET_WORTH == before_net_worth + 100_000

    sr._restore_overrides(original)
    assert cfg.YOUR_401K == before_401k
    assert cfg.TOTAL_RETIREMENT_ACCOUNTS == before_total_ret
    assert cfg.TOTAL_NET_WORTH == before_net_worth


# ---------------------------------------------------------------------------
# (c) after overriding a base input, _recompute_derived updates dependents
#     (pins the #15/#16 fix)
# ---------------------------------------------------------------------------

def test_hsa_total_recomputed_from_contribution_and_match():
    before = cfg.YOUR_HSA_TOTAL
    original = sr._apply_overrides({"YOUR_HSA_CONTRIBUTION": 4000, "YOUR_HSA_MATCH": 1000})
    try:
        # config.py:165 — YOUR_HSA_TOTAL = YOUR_HSA_CONTRIBUTION + YOUR_HSA_MATCH
        assert cfg.YOUR_HSA_TOTAL == 5000
    finally:
        sr._restore_overrides(original)
    assert cfg.YOUR_HSA_TOTAL == before


def test_retirement_annual_expenses_tracks_base():
    # LEGACY-FALLBACK path: with every granular SPEND_* category left at None,
    # the engine still derives the non-housing base from the legacy
    # YOUR_OTHER_MONTHLY / UTILITIES bundle. This pins that fallback so the
    # granular-preference change (test_granular_* below) can't silently break the
    # no-granular case.
    before = cfg.RETIREMENT_ANNUAL_EXPENSES
    original = sr._apply_overrides({"YOUR_OTHER_MONTHLY": 5000})
    try:
        # config.py — RETIREMENT_ANNUAL_EXPENSES == BASE_RETIREMENT_EXPENSES_NO_MORTGAGE
        assert cfg.RETIREMENT_ANNUAL_EXPENSES == cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE
        # Legacy bundle drives it (no granular categories present).
        assert cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE == (
            cfg.YOUR_OTHER_ANNUAL + cfg.UTILITIES_ANNUAL + cfg.PARTNER_OTHER_MONTHLY * 12
        )
    finally:
        sr._restore_overrides(original)
    assert cfg.RETIREMENT_ANNUAL_EXPENSES == before


def test_college_target_per_child_recomputed():
    # An old profile's COLLEGE_FUNDING_PCT now lands on each child (there is no
    # derived per-child target constant any more) and is undone on restore.
    before = cfg.CHILDREN
    original = sr._apply_overrides({"COLLEGE_FUNDING_PCT": 0.5})
    try:
        targets = [cfg.college_target(c) for c in cfg.CHILDREN]
        assert targets == [40_000 * 4 * 0.5] * 2
        assert cfg.calculate_529_contribution(cfg.YOUR_AGE + 6) == 2 * targets[0] / 18
    finally:
        sr._restore_overrides(original)
    assert cfg.CHILDREN == before


# ---------------------------------------------------------------------------
# (c2) granular SPEND_* categories drive BOTH current and retirement non-housing
#      living expenses (item #2: retirement-expense disconnect). Editing the six
#      monthly categories in the UI Expenses section must flow through
#      _recompute_derived into BASE_RETIREMENT_EXPENSES_NO_MORTGAGE /
#      CURRENT_ANNUAL_EXPENSES / RETIREMENT_ANNUAL_EXPENSES and into the engine's
#      calculate_annual_expenses(), superseding the legacy YOUR_OTHER/UTILITIES
#      bundle. Housing (mortgage/rent) stays a separate component.
# ---------------------------------------------------------------------------

_GRANULAR_OVERRIDES = {
    "SPEND_UTILITIES_MONTHLY": 350,
    "SPEND_FOOD_MONTHLY": 1_050,
    "SPEND_TRANSPORT_MONTHLY": 600,
    "SPEND_HEALTH_MONTHLY": 400,
    "SPEND_DISCRETIONARY_MONTHLY": 500,
    "SPEND_OTHER_MONTHLY": 200,
    "PARTNER_OTHER_MONTHLY": 2_000,
}
# Sum of the six categories * 12 + partner spending * 12.
_GRANULAR_EXPECTED_BASE = (350 + 1_050 + 600 + 400 + 500 + 200) * 12 + 2_000 * 12  # 61_200


def test_granular_categories_drive_retirement_and_current_expenses():
    before_base = cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE
    before_current = cfg.CURRENT_ANNUAL_EXPENSES
    original = sr._apply_overrides(dict(_GRANULAR_OVERRIDES))
    try:
        # Non-housing retirement base is the granular sum, NOT the legacy bundle.
        assert cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE == _GRANULAR_EXPECTED_BASE
        assert cfg.RETIREMENT_ANNUAL_EXPENSES == _GRANULAR_EXPECTED_BASE
        # Current expenses = mortgage/housing + granular base (housing separate).
        assert cfg.CURRENT_ANNUAL_EXPENSES == cfg.MORTGAGE_ANNUAL + _GRANULAR_EXPECTED_BASE
    finally:
        sr._restore_overrides(original)
    # Clean round-trip back to the defaults (granular keys revert to None).
    assert cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE == before_base
    assert cfg.CURRENT_ANNUAL_EXPENSES == before_current


def test_granular_categories_flow_into_calculate_annual_expenses():
    # The engine reads cfg.calculate_annual_expenses() at runtime; it must reflect
    # the granular base (plus mortgage while it is still being paid).
    original = sr._apply_overrides(dict(_GRANULAR_OVERRIDES))
    try:
        no_mortgage_age = cfg.YOUR_AGE + cfg.MORTGAGE_YEARS_REMAINING + 5
        child_free_age = 80  # past child-leave age so calculate_child_expenses == 0
        base = cfg.calculate_annual_expenses(
            max(no_mortgage_age, child_free_age), inflation_factor=1.0
        )
        assert base == _GRANULAR_EXPECTED_BASE
    finally:
        sr._restore_overrides(original)


def test_granular_partial_override_supersedes_legacy():
    # Even a SINGLE granular category present flips the engine to the granular
    # formula (summing only the present categories); the legacy bundle no longer
    # contributes. Pins the "any present -> granular" contract.
    original = sr._apply_overrides({"SPEND_FOOD_MONTHLY": 1_000})
    try:
        expected = 1_000 * 12 + cfg.PARTNER_OTHER_MONTHLY * 12
        assert cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE == expected
    finally:
        sr._restore_overrides(original)


def test_granular_matches_full_profile_number():
    # Regression pin on a full saved profile (the committed sample household):
    # retirement spending must reflect the granular SPEND_* categories the user
    # enters, NOT the legacy understated ~$43.8k bundle. Derive the expected value
    # from the profile so this stays correct if the fixture's inputs change.
    from tests.conftest import load_sample_household

    profile = load_sample_household()
    ovr = build_config_overrides(profile)
    granular = (
        profile["SPEND_UTILITIES_MONTHLY"] + profile["SPEND_FOOD_MONTHLY"]
        + profile["SPEND_TRANSPORT_MONTHLY"] + profile["SPEND_HEALTH_MONTHLY"]
        + profile["SPEND_DISCRETIONARY_MONTHLY"] + profile["SPEND_OTHER_MONTHLY"]
    ) * 12 + profile["PARTNER_OTHER_MONTHLY"] * 12
    original = sr._apply_overrides(ovr)
    try:
        assert cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE == granular
        # Sanity: strictly greater than the legacy default the engine used before.
        assert cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE > 43_800
    finally:
        sr._restore_overrides(original)


# ---------------------------------------------------------------------------
# (d) sweep_break_even: pure-logic bisection-style scan over run_full_analysis
# ---------------------------------------------------------------------------

def test_sweep_break_even_finds_first_crossing(monkeypatch):
    # Fake success rate that increases monotonically with the swept value so
    # the break-even point is unambiguous: value -> success_rate.
    fake_rates = {10: 0.40, 20: 0.60, 30: 0.79, 40: 0.85, 50: 0.95}

    def fake_run_full_analysis(user_overrides, n_simulations, target_retirement_age):
        value = user_overrides["SOME_PARAM"]
        return {"primary_result": {"success_rate": fake_rates[value]}}

    monkeypatch.setattr(sr, "run_full_analysis", fake_run_full_analysis)

    result = sr.sweep_break_even(
        user_overrides={},
        param_name="SOME_PARAM",
        values=[10, 20, 30, 40, 50],
        target_retirement_age=55,
        target_success_rate=0.80,
        n_simulations=10,
    )

    assert result["success_rates"] == [0.40, 0.60, 0.79, 0.85, 0.95]
    # 40 is the first (lowest) value whose rate (0.85) >= target (0.80).
    assert result["break_even_value"] == 40
    assert result["param_name"] == "SOME_PARAM"
    assert result["target_success_rate"] == 0.80


def test_sweep_break_even_returns_none_when_target_unreachable():
    def fake_run_full_analysis(user_overrides, n_simulations, target_retirement_age):
        return {"primary_result": {"success_rate": 0.10}}

    original = sr.run_full_analysis
    sr.run_full_analysis = fake_run_full_analysis
    try:
        result = sr.sweep_break_even(
            user_overrides={},
            param_name="SOME_PARAM",
            values=[1, 2, 3],
            target_retirement_age=55,
            target_success_rate=0.80,
            n_simulations=10,
        )
    finally:
        sr.run_full_analysis = original

    assert result["break_even_value"] is None
    assert result["success_rates"] == [0.10, 0.10, 0.10]


def test_sweep_break_even_handles_exceptions_as_zero_rate(monkeypatch):
    def flaky_run_full_analysis(user_overrides, n_simulations, target_retirement_age):
        if user_overrides["SOME_PARAM"] == 2:
            raise RuntimeError("simulated failure")
        return {"primary_result": {"success_rate": 0.90}}

    monkeypatch.setattr(sr, "run_full_analysis", flaky_run_full_analysis)

    result = sr.sweep_break_even(
        user_overrides={},
        param_name="SOME_PARAM",
        values=[1, 2, 3],
        target_retirement_age=55,
        target_success_rate=0.80,
        n_simulations=10,
    )

    assert result["success_rates"] == [0.90, 0.0, 0.90]
    # First crossing is value 1 (index 0), not value 3, despite value 2's failure.
    assert result["break_even_value"] == 1


# ---------------------------------------------------------------------------
# (e) hardened input coercion: out-of-range / hand-edited profile values are
#     clamped in-range rather than crashing sync_widgets_from_overrides or
#     build_config_overrides (item #30).
# ---------------------------------------------------------------------------

class _FakeSessionState(dict):
    """Minimal stand-in for st.session_state (attribute + dict access)."""
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(item)

    def __setattr__(self, key, value):
        self[key] = value

    def get(self, key, default=None):
        return dict.get(self, key, default)


class _FakeSt:
    def __init__(self, overrides):
        self.session_state = _FakeSessionState()
        self.session_state["user_overrides"] = overrides


def test_widget_sync_clamps_out_of_range_age():
    # A hand-edited / uploaded profile with an absurd age must not propagate
    # an out-of-range value into the widget's session_state slot (which would
    # crash st.number_input(min_value=18, max_value=100) on next render).
    st = _FakeSt({"YOUR_AGE": 99999})
    ws.sync_widgets_from_overrides(st)
    assert st.session_state["ay_your_age"] == 100  # clamped to max_value


def test_widget_sync_clamps_negative_savings_contribution():
    st = _FakeSt({"YOUR_401K_CONTRIBUTION": -5000})
    ws.sync_widgets_from_overrides(st)
    assert st.session_state["sr_your_401k"] == 0  # clamped to min_value


def test_widget_sync_clamps_full_bad_profile_without_crashing():
    # Simulates a hand-edited / uploaded profile: absurd age + negative
    # savings. Should clamp every affected widget key into range, not raise.
    bad_profile = {
        "YOUR_AGE": 99999,
        "PARTNER_AGE": -50,
        "YOUR_401K_CONTRIBUTION": -1_000_000,
        "TARGET_RETIREMENT_AGE": 5,
        "STOCK_ALLOCATION": 500.0,  # way over 100% -> out of 0-100 range
    }
    st = _FakeSt(bad_profile)
    ws.sync_widgets_from_overrides(st)  # must not raise
    assert st.session_state["ay_your_age"] == 100
    assert st.session_state["ay_partner_age"] == 0
    assert st.session_state["sr_your_401k"] == 0
    assert st.session_state["ay_target_age"] == 25
    assert st.session_state["sa_stock_alloc"] == 100.0


def test_widget_sync_in_range_values_unchanged():
    # Pure sanitization: in-range inputs behave identically to before.
    st = _FakeSt({"YOUR_AGE": 42, "YOUR_401K_CONTRIBUTION": 5_000})
    ws.sync_widgets_from_overrides(st)
    assert st.session_state["ay_your_age"] == 42
    assert st.session_state["sr_your_401k"] == 5_000


def test_build_config_overrides_clamps_negative_quick_income_and_savings():
    out = build_config_overrides({
        "HOUSEHOLD_INCOME_QUICK": -50_000,
        "TOTAL_SAVINGS_QUICK": -1_000_000,
        "YOUR_AGE": 99999,
    })
    # Negative quick income/savings must not produce negative derived amounts.
    assert out["PARTNER_SALARY"] >= 0
    assert out["YOUR_401K"] >= 0
    assert out["YOUR_CASH"] >= 0


# ---------------------------------------------------------------------------
# (e) Pin build_config_overrides output byte-for-byte (item #25: extracting
#     the quick-income magic literals into named constants must not change
#     a single number produced by this function).
# ---------------------------------------------------------------------------

def test_build_config_overrides_household_income_quick_byte_identical():
    import json

    out = build_config_overrides({"HOUSEHOLD_INCOME_QUICK": 150_000, "YOUR_AGE": 28})
    serialized = json.dumps(out, sort_keys=True, default=str)

    expected = (
        '{"PARTNER_SALARY": 67500, "YOUR_AGE": 28, "YOUR_COMPENSATION_BY_AGE": '
        '{"28": {"after_tax": 57749, "base": 82500, "bonus": 0, "rsu_gross": 0, '
        '"saved": 5774, "total_comp": 82500}, "29": {"after_tax": 58904, "base": '
        '84150, "bonus": 0, "rsu_gross": 0, "saved": 5890, "total_comp": 84150}, '
        '"30": {"after_tax": 60083, "base": 85833, "bonus": 0, "rsu_gross": 0, '
        '"saved": 6008, "total_comp": 85833}, "31": {"after_tax": 61284, "base": '
        '87549, "bonus": 0, "rsu_gross": 0, "saved": 6128, "total_comp": 87549}, '
        '"32": {"after_tax": 62509, "base": 89300, "bonus": 0, "rsu_gross": 0, '
        '"saved": 6250, "total_comp": 89300}, "33": {"after_tax": 63760, "base": '
        '91086, "bonus": 0, "rsu_gross": 0, "saved": 6376, "total_comp": 91086}, '
        '"34": {"after_tax": 65035, "base": 92908, "bonus": 0, "rsu_gross": 0, '
        '"saved": 6503, "total_comp": 92908}, "35": {"after_tax": 66336, "base": '
        '94766, "bonus": 0, "rsu_gross": 0, "saved": 6633, "total_comp": 94766}, '
        '"36": {"after_tax": 67662, "base": 96661, "bonus": 0, "rsu_gross": 0, '
        '"saved": 6766, "total_comp": 96661}, "37": {"after_tax": 69016, "base": '
        '98595, "bonus": 0, "rsu_gross": 0, "saved": 6901, "total_comp": 98595}, '
        '"38": {"after_tax": 70396, "base": 100567, "bonus": 0, "rsu_gross": 0, '
        '"saved": 7039, "total_comp": 100567}, "39": {"after_tax": 71804, "base": '
        '102578, "bonus": 0, "rsu_gross": 0, "saved": 7180, "total_comp": 102578}, '
        '"40": {"after_tax": 73240, "base": 104629, "bonus": 0, "rsu_gross": 0, '
        '"saved": 7324, "total_comp": 104629}, "41": {"after_tax": 74705, "base": '
        '106722, "bonus": 0, "rsu_gross": 0, "saved": 7470, "total_comp": 106722}, '
        '"42": {"after_tax": 76199, "base": 108856, "bonus": 0, "rsu_gross": 0, '
        '"saved": 7619, "total_comp": 108856}}}'
    )
    assert serialized == expected


# ---------------------------------------------------------------------------
# (e2) finding #9: the savings-contributions chart must derive
#      your_brokerage/partner_brokerage from the SAME residual-sweep formula
#      simulate_accumulation_year uses in Auto mode -- not a stale
#      10%-of-after-tax approximation. Pin exact parity against a real
#      one-year engine run (0% return isolates the contribution-only delta).
# ---------------------------------------------------------------------------

from retirement_sim import account_simulation as accsim


def _engine_brokerage_delta(age: int) -> tuple:
    """Run one real accumulation year and return the $ actually swept into
    your_brokerage / partner_brokerage (isolates contributions from any
    market return by using annual_return=0.0)."""
    portfolio = accsim.create_initial_portfolio()
    before_your = portfolio.accounts["your_brokerage"].balance
    before_partner = portfolio.accounts["partner_brokerage"].balance
    accsim.simulate_accumulation_year(portfolio, age, 0.0)
    after_your = portfolio.accounts["your_brokerage"].balance
    after_partner = portfolio.accounts["partner_brokerage"].balance
    return after_your - before_your, after_partner - before_partner


@pytest.mark.parametrize("age", [25, 28, 30, 35, 38])
def test_savings_contributions_brokerage_matches_engine_sweep_default_profile(age):
    """Default config, Auto-allocate mode: sim_runner's derived
    your_brokerage/partner_brokerage must equal the engine's actual sweep
    exactly, not a static 10%-of-income guess."""
    engine_your, engine_partner = _engine_brokerage_delta(age)

    rows = sr._approximate_savings_contributions(retirement_age=age + 1)
    row = next(r for r in rows if r["age"] == age)

    assert row["your_brokerage"] == pytest.approx(engine_your, abs=0.01)
    assert row["partner_brokerage"] == pytest.approx(engine_partner, abs=0.01)


def test_savings_contributions_brokerage_matches_engine_sweep_after_marriage():
    """A married couple (filing jointly; the wedding-year flag is gone) gets
    no direct partner Roth from the engine (MFJ phase-out), which also changes
    the swept brokerage split. The chart-derived row must track this exactly
    (regression for the 'unconditional partner_roth elective' sub-bug found
    while fixing #9 against a real married profile; the sample household is
    married too)."""
    from tests.conftest import load_sample_household

    overrides = load_sample_household()
    original = sr._apply_overrides(overrides)
    try:
        start_age = int(cfg.YOUR_AGE)
        assert cfg.normalize_filing_status() == "MFJ"  # sanity: married

        for age in (start_age, start_age + 3, start_age + 10):
            engine_your, engine_partner = _engine_brokerage_delta(age)
            rows = sr._approximate_savings_contributions(retirement_age=age + 1)
            row = next(r for r in rows if r["age"] == age)
            assert row["your_brokerage"] == pytest.approx(engine_your, abs=0.01)
            assert row["partner_brokerage"] == pytest.approx(engine_partner, abs=0.01)
            # Married -> partner direct Roth must read as $0, not the flat
            # PARTNER_ROTH_CONTRIBUTION default (the pre-fix bug).
            assert row["partner_roth"] == 0.0
    finally:
        sr._restore_overrides(original)


def test_savings_contributions_backdoor_roth_reads_real_config_not_hardcoded_7000():
    """YOUR_BACKDOOR_ROTH defaults to $0 in the base config (only a full saved
    profile is likely to set it to $7,000) -- the chart must respect
    whatever value is configured, not a hardcoded $7,000 guess."""
    start_age = int(cfg.YOUR_AGE)
    assert int(getattr(cfg, "YOUR_BACKDOOR_ROTH", -1)) == 0  # base default

    rows = sr._approximate_savings_contributions(retirement_age=start_age + 1)
    row = next(r for r in rows if r["age"] == start_age)
    assert row["your_roth"] == 0.0  # not the stale hardcoded $7,000


# ---------------------------------------------------------------------------
# (f) representative withdrawal_log selection (#27): the withdrawal chart must
#     span the FULL retirement horizon (retirement_age..PLAN_UNTIL_AGE) by
#     choosing a SURVIVING path, never a depleted one whose log stops early and
#     spikes to ~100%.
# ---------------------------------------------------------------------------

class _FakePortfolio:
    def __init__(self, log):
        self.withdrawal_log = log


def _wd_log(start_age, end_age, portfolio_value=1_000_000.0, withdraw=40_000.0):
    """Build a plausible withdrawal_log spanning [start_age, end_age]."""
    return [
        {
            "age": a,
            "cash": 0.0, "taxable": withdraw, "traditional": 0.0,
            "roth": 0.0, "hsa": 0.0, "total": withdraw,
            "portfolio_value": portfolio_value,
            "withdrawal_pct": withdraw / portfolio_value,
            "total_taxes": 0.0, "ss_tax": 0.0, "niit": 0.0, "penalties": 0.0,
        }
        for a in range(start_age, end_age + 1)
    ]


def test_median_withdrawal_log_prefers_surviving_path():
    # Two candidates: a DEPLETED path (log stops early at 50, tiny final balance)
    # and a SURVIVING path (log to 95). The survivor must win even though its
    # final balance is far from the overall median.
    retire, plan_until = 45, 95
    depleted_log = _wd_log(retire, 50)
    survivor_log = _wd_log(retire, plan_until)

    paths = [
        [(retire, 500_000.0), (50, 0.0)],          # depleted: low final
        [(retire, 900_000.0), (plan_until, 2_000_000.0)],  # survivor: high final
    ]
    portfolios = [_FakePortfolio(depleted_log), _FakePortfolio(survivor_log)]
    successes = [False, True]

    rows = sr._median_withdrawal_log(paths, portfolios, successes)
    assert rows, "expected a non-empty representative log"
    assert rows[0]["age"] == retire
    assert rows[-1]["age"] == plan_until  # spans full horizon, not truncated at 50


def test_median_withdrawal_log_falls_back_when_no_survivors():
    # If every path depleted, fall back to closest-to-median overall rather than
    # returning nothing.
    paths = [
        [(45, 400_000.0), (50, 0.0)],
        [(45, 600_000.0), (55, 0.0)],
    ]
    portfolios = [_FakePortfolio(_wd_log(45, 50)), _FakePortfolio(_wd_log(45, 55))]
    successes = [False, False]
    rows = sr._median_withdrawal_log(paths, portfolios, successes)
    assert rows  # non-empty even with no survivors


def test_median_withdrawal_log_flags_depletion_row():
    # A row whose pre-withdrawal balance is negligible vs the amount withdrawn
    # must be flagged `depleted` and have its % capped, so the chart can't paint
    # a spurious ~100% (or higher) bar.
    log = _wd_log(45, 95)
    log[-1]["portfolio_value"] = 10.0     # ~0 balance
    log[-1]["total"] = 40_000.0
    log[-1]["withdrawal_pct"] = 4000.0    # absurd raw fraction
    port = _FakePortfolio(log)
    rows = sr._median_withdrawal_log([[(45, 1.0), (95, 5.0)]], [port], [True])
    last = rows[-1]
    assert last["depleted"] is True
    assert last["withdrawal_pct"] <= 1.0


@pytest.mark.slow
def test_withdrawals_by_year_spans_to_plan_until_for_surviving_scenario():
    # Integration pin: a surviving-heavy scenario (young couple, modest expenses,
    # retire late) must produce withdrawals_by_year reaching ~PLAN_UNTIL_AGE, not
    # truncating at an early depletion age.
    import numpy as np

    np.random.seed(42)
    overrides = {
        "YOUR_AGE": 40,
        "HOUSEHOLD_INCOME_QUICK": 300_000,
        "TOTAL_SAVINGS_QUICK": 3_000_000,
    }
    res = sr.run_full_analysis(
        user_overrides=overrides,
        n_simulations=200,
        target_retirement_age=60,
        scan_age_range=(55, 66, 1),
    )
    pr = res["primary_result"]
    wy = pr.get("withdrawals_by_year", [])
    assert wy, "expected a per-year withdrawal breakdown"
    plan_until = int(cfg.PLAN_UNTIL_AGE)
    assert wy[0]["age"] == pr["retirement_age"]
    # Last withdrawal-log age should reach the plan-until horizon (allow 1yr slack
    # for the final record_year boundary).
    assert wy[-1]["age"] >= plan_until - 1


# ---------------------------------------------------------------------------
# (e) run_whatif_delta / active_lifecycle_toggles: WHAT-IF pane data plumbing
#     (Stage 3 #1B). No engine changes — reuses run_full_analysis twice
#     (scenario as-is, baseline with all 4 lifecycle toggles forced off).
# ---------------------------------------------------------------------------

def test_active_lifecycle_toggles_empty_by_default():
    assert sr.active_lifecycle_toggles({}) == []


def test_active_lifecycle_toggles_detects_each_flag():
    assert sr.active_lifecycle_toggles({"CAR_ONETIME_ENABLED": True}) == ["CAR_ONETIME_ENABLED"]
    assert sr.active_lifecycle_toggles({"CAR_RECURRING_ENABLED": True}) == ["CAR_RECURRING_ENABLED"]
    assert sr.active_lifecycle_toggles({"HOUSE_MOVE_ENABLED": True}) == ["HOUSE_MOVE_ENABLED"]
    assert sr.active_lifecycle_toggles({"RETIREMENT_VACATION_ENABLED": True}) == ["RETIREMENT_VACATION_ENABLED"]
    # Multiple toggles: order follows LIFECYCLE_TOGGLE_KEYS.
    multi = sr.active_lifecycle_toggles({"HOUSE_MOVE_ENABLED": True, "CAR_ONETIME_ENABLED": True})
    assert multi == ["CAR_ONETIME_ENABLED", "HOUSE_MOVE_ENABLED"]
    # Explicit False does not count as active.
    assert sr.active_lifecycle_toggles({"CAR_ONETIME_ENABLED": False}) == []


def test_run_whatif_delta_calls_run_full_analysis_twice_scenario_and_baseline(monkeypatch):
    calls = []

    def fake_run_full_analysis(user_overrides, n_simulations, target_retirement_age, scan_age_range=(25, 76, 1)):
        calls.append(dict(user_overrides))
        # Baseline (toggles forced off) sees a worse outcome than scenario here
        # purely to exercise the delta math with distinguishable numbers.
        is_baseline = not any(user_overrides.get(k) for k in sr.LIFECYCLE_TOGGLE_KEYS)
        if is_baseline:
            return {
                "earliest_retirement_age": 45,
                "primary_result": {"success_rate": 0.90, "median_final": 1_000_000.0},
            }
        return {
            "earliest_retirement_age": 47,
            "primary_result": {"success_rate": 0.80, "median_final": 800_000.0},
        }

    monkeypatch.setattr(sr, "run_full_analysis", fake_run_full_analysis)

    result = sr.run_whatif_delta(
        user_overrides={"CAR_ONETIME_ENABLED": True, "CAR_ONETIME_COST": 40_000},
        n_simulations=100,
        target_retirement_age=50,
    )

    assert len(calls) == 2
    # First call: overrides as-is (scenario) -> the toggle is still True.
    assert calls[0]["CAR_ONETIME_ENABLED"] is True
    # Second call: baseline -> every lifecycle toggle forced False.
    assert calls[1]["CAR_ONETIME_ENABLED"] is False
    assert calls[1]["CAR_RECURRING_ENABLED"] is False
    assert calls[1]["HOUSE_MOVE_ENABLED"] is False
    assert calls[1]["RETIREMENT_VACATION_ENABLED"] is False
    # Non-toggle overrides pass through unchanged to the baseline call too.
    assert calls[1]["CAR_ONETIME_COST"] == 40_000

    assert result["active_toggles"] == ["CAR_ONETIME_ENABLED"]
    assert result["scenario"]["earliest_retirement_age"] == 47
    assert result["baseline"]["earliest_retirement_age"] == 45
    assert result["delta"]["earliest_retirement_age"] == 47 - 45
    assert result["delta"]["success_rate"] == pytest.approx(0.80 - 0.90)
    assert result["delta"]["median_final"] == pytest.approx(800_000.0 - 1_000_000.0)


def test_run_whatif_delta_handles_earliest_age_not_achieved(monkeypatch):
    def fake_run_full_analysis(user_overrides, n_simulations, target_retirement_age, scan_age_range=(25, 76, 1)):
        is_baseline = not any(user_overrides.get(k) for k in sr.LIFECYCLE_TOGGLE_KEYS)
        earliest = 50 if is_baseline else None  # scenario never hits target success rate
        return {"earliest_retirement_age": earliest, "primary_result": {"success_rate": 0.5, "median_final": 0.0}}

    monkeypatch.setattr(sr, "run_full_analysis", fake_run_full_analysis)

    result = sr.run_whatif_delta(user_overrides={"HOUSE_MOVE_ENABLED": True}, n_simulations=50, target_retirement_age=50)
    assert result["scenario"]["earliest_retirement_age"] is None
    assert result["delta"]["earliest_retirement_age"] is None  # can't diff None ages


@pytest.mark.slow
def test_run_whatif_delta_integration_car_purchase_hurts_outcome():
    # Real (uncached-safe) integration run: a one-time car purchase should never
    # make the plan look BETTER than the toggle-off baseline. Uses a tight
    # budget (modest income/savings relative to an $80k car) so the $80k hit
    # dominates over Monte Carlo path-to-path noise; a wide-margin scenario
    # (e.g. high income + large savings) can flip sign purely from noise.
    import numpy as np

    sr.clear_cache()
    np.random.seed(42)
    overrides = {
        "YOUR_AGE": 45,
        "HOUSEHOLD_INCOME_QUICK": 120_000,
        "TOTAL_SAVINGS_QUICK": 300_000,
        "CAR_ONETIME_ENABLED": True,
        "CAR_ONETIME_AGE": 47,
        "CAR_ONETIME_COST": 80_000,
    }
    result = sr.run_whatif_delta(
        user_overrides=overrides, n_simulations=500, target_retirement_age=60,
        scan_age_range=(55, 66, 5),
    )
    assert result["active_toggles"] == ["CAR_ONETIME_ENABLED"]
    # Spending an extra $80k against a $300k base can't improve the outcome.
    assert result["delta"]["median_final"] <= 0
    assert result["delta"]["success_rate"] <= 0


def test_run_whatif_delta_not_invoked_when_no_toggle_active():
    # Guard the "only run baseline when a toggle is on" contract at the call
    # site: active_lifecycle_toggles({}) is falsy, so app.py should skip
    # run_whatif_delta entirely (verified indirectly here; app.py wiring
    # mirrors this check before calling run_whatif_delta).
    assert sr.active_lifecycle_toggles({}) == []
    assert sr.active_lifecycle_toggles({"CAR_ONETIME_ENABLED": False, "HOUSE_MOVE_ENABLED": False}) == []


# ---------------------------------------------------------------------------
# (f) what_if_pane.render: pure display, must not crash on any payload shape
# ---------------------------------------------------------------------------

class _MockSt:
    """Minimal tolerant mock, mirrors ui/_smoke_test.py's MockSt."""
    def __getattr__(self, attr):
        def _catchall(*args, **kwargs):
            return _MockSt()
        return _catchall
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def columns(self, n):
        return [_MockSt() for _ in range(n if isinstance(n, int) else len(n))]


def test_what_if_pane_renders_without_crashing_on_full_payload():
    from components import what_if_pane

    payload = {
        "scenario": {"earliest_retirement_age": 47, "primary_result": {"success_rate": 0.80, "median_final": 800_000.0}},
        "baseline": {"earliest_retirement_age": 45, "primary_result": {"success_rate": 0.90, "median_final": 1_000_000.0}},
        "active_toggles": ["CAR_ONETIME_ENABLED"],
        "delta": {"earliest_retirement_age": 2, "success_rate": -0.10, "median_final": -200_000.0},
    }
    what_if_pane.render(_MockSt(), results=payload)  # must not raise


def test_what_if_pane_renders_placeholder_when_no_results():
    from components import what_if_pane

    what_if_pane.render(_MockSt(), results=None)  # must not raise


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
