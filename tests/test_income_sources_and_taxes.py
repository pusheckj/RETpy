"""Pinning tests for rank #9/#10-ui: income-sources and tax-tab data must be
derived from the REAL representative ``withdrawal_log`` (see
``_median_withdrawal_log`` / engine's per-year tax logging from #10-engine),
not the fabricated 50/20/20/10 split or flat federal/state/ltcg constants.

See ui/utils/sim_runner.py::_approximate_income_sources and
::_approximate_taxes.
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


# ---------------------------------------------------------------------------
# _approximate_income_sources: rows must track the withdrawal_log draws,
# not a hardcoded 50/20/20/10 split of a flat "need".
# ---------------------------------------------------------------------------

def test_income_sources_map_account_draws_directly_from_log():
    withdrawal_rows = [
        {"age": 50, "cash": 1_000.0, "taxable": 20_000.0, "traditional": 30_000.0,
         "roth": 5_000.0, "hsa": 2_000.0, "total": 58_000.0},
        {"age": 51, "cash": 0.0, "taxable": 10_000.0, "traditional": 40_000.0,
         "roth": 0.0, "hsa": 0.0, "total": 50_000.0},
    ]
    original = sr._apply_overrides({"INCLUDE_SOCIAL_SECURITY": False})
    try:
        out = sr._approximate_income_sources(withdrawal_rows, retirement_age=50)
    finally:
        sr._restore_overrides(original)

    assert [r["age"] for r in out] == [50, 51]

    row0 = out[0]
    # traditional/roth/hsa map straight from the log.
    assert row0["traditional"] == 30_000.0
    assert row0["roth"] == 5_000.0
    assert row0["hsa"] == 2_000.0
    # taxable absorbs cash (both already-taxed, no separate cash bucket in
    # this chart's fixed 5-series schema): 20,000 + 1,000 = 21,000.
    assert row0["taxable"] == 21_000.0

    row1 = out[1]
    assert row1["traditional"] == 40_000.0
    assert row1["roth"] == 0.0
    assert row1["taxable"] == 10_000.0

    # This is NOT the old hardcoded 50/20/20/10 split of a flat need — the two
    # rows have very different underlying draws, so they must differ too.
    assert row0["traditional"] != row1["traditional"] or row0["taxable"] != row1["taxable"]


def test_income_sources_drops_rows_before_retirement_age():
    withdrawal_rows = [
        {"age": 48, "cash": 0.0, "taxable": 999.0, "traditional": 0.0, "roth": 0.0, "hsa": 0.0, "total": 999.0},
        {"age": 50, "cash": 0.0, "taxable": 5_000.0, "traditional": 0.0, "roth": 0.0, "hsa": 0.0, "total": 5_000.0},
    ]
    out = sr._approximate_income_sources(withdrawal_rows, retirement_age=50)
    assert [r["age"] for r in out] == [50]


def test_income_sources_adds_real_social_security_when_enabled():
    withdrawal_rows = [
        {"age": 67, "cash": 0.0, "taxable": 10_000.0, "traditional": 20_000.0,
         "roth": 0.0, "hsa": 0.0, "total": 30_000.0},
    ]
    original = sr._apply_overrides({"INCLUDE_SOCIAL_SECURITY": True, "SS_CLAIM_AGE": 67})
    try:
        out = sr._approximate_income_sources(withdrawal_rows, retirement_age=60)
        expected_ss = cfg.calculate_social_security(67, 67)
    finally:
        sr._restore_overrides(original)

    assert out[0]["ss"] == pytest.approx(expected_ss)
    assert expected_ss > 0  # sanity: real SS calc, not a placeholder 0.


def test_income_sources_empty_log_yields_no_rows():
    assert sr._approximate_income_sources([], retirement_age=50) == []


def test_income_sources_surfaces_roth_conversion_as_distinct_transfer_field():
    """finding #14: Roth conversions must appear as their own
    ``roth_conversion`` field (a transfer, not income/spend) -- the
    traditional/roth/taxable withdrawal buckets must stay untouched by it so
    the conversion cannot be misread as consumption."""
    withdrawal_rows = [
        {
            "age": 62, "cash": 0.0, "taxable": 5_000.0, "traditional": 2_000.0,
            "roth": 0.0, "hsa": 0.0, "total": 7_000.0,
            "roth_conversion": 40_000.0, "roth_conversion_tax": 8_500.0,
        },
    ]
    out = sr._approximate_income_sources(withdrawal_rows, retirement_age=60)
    row = out[0]
    assert row["roth_conversion"] == pytest.approx(40_000.0)
    # Untouched by the conversion -- it must not have been folded in anywhere.
    assert row["traditional"] == pytest.approx(2_000.0)
    assert row["taxable"] == pytest.approx(5_000.0)
    assert row["roth"] == pytest.approx(0.0)


def test_income_sources_roth_conversion_defaults_to_zero_when_absent():
    """Rows without a roth_conversion key (e.g. working-year rows or an older
    log shape) must default to $0, not KeyError or a placeholder."""
    withdrawal_rows = [
        {"age": 55, "cash": 0.0, "taxable": 1_000.0, "traditional": 0.0,
         "roth": 0.0, "hsa": 0.0, "total": 1_000.0},
    ]
    out = sr._approximate_income_sources(withdrawal_rows, retirement_age=50)
    assert out[0]["roth_conversion"] == 0.0


# ---------------------------------------------------------------------------
# _approximate_taxes: retirement-year rows must come from the log's real
# per-year tax totals, not the flat federal=12000/state=4000/ltcg=2000.
# ---------------------------------------------------------------------------

def test_taxes_retirement_years_use_real_log_totals_not_flat_constants():
    withdrawal_rows = [
        {"age": 50, "total": 80_000.0, "total_taxes": 9_500.0, "niit": 0.0},
        {"age": 51, "total": 82_000.0, "total_taxes": 25_000.0, "niit": 1_200.0},
    ]
    original = sr._apply_overrides({
        "YOUR_AGE": 50, "PLAN_UNTIL_AGE": 51, "INCLUDE_SOCIAL_SECURITY": False,
    })
    try:
        out = sr._approximate_taxes(withdrawal_rows, retirement_age=50)
    finally:
        sr._restore_overrides(original)

    by_age = {r["age"]: r for r in out}
    # Neither retirement row matches the old flat placeholders.
    assert by_age[50]["federal"] != 12_000.0
    assert by_age[51]["federal"] != 12_000.0
    # finding #17: `total_taxes` already INCLUDES niit, so the four stacked
    # series (federal+state+ltcg+niit) must sum to the real total_taxes
    # EXACTLY ONCE -- niit must not be added on top of an already-inclusive
    # federal figure. Age 50 has niit=0 so the split is unaffected either way;
    # age 51 (niit=1_200) is the case that pins the fix: federal absorbs
    # (total_taxes - niit) and the separate niit field makes up the rest.
    assert by_age[50]["federal"] + by_age[50]["state"] + by_age[50]["ltcg"] + by_age[50]["niit"] == pytest.approx(9_500.0)
    assert by_age[51]["federal"] + by_age[51]["state"] + by_age[51]["ltcg"] + by_age[51]["niit"] == pytest.approx(25_000.0)
    assert by_age[51]["federal"] == pytest.approx(25_000.0 - 1_200.0)
    # NIIT is the real separable component, not a hardcoded 0.
    assert by_age[51]["niit"] == pytest.approx(1_200.0)
    # gross_income reflects the real withdrawal total, not CURRENT_ANNUAL_EXPENSES.
    assert by_age[50]["gross_income"] == pytest.approx(80_000.0)
    assert by_age[51]["gross_income"] == pytest.approx(82_000.0)
    # Two different years with different underlying log rows must produce
    # different tax figures (pins against a flat constant for all years).
    assert by_age[50]["federal"] != by_age[51]["federal"]


def test_taxes_retirement_year_missing_from_log_defaults_to_zero_not_placeholder():
    # Age 52 has no corresponding withdrawal_log row (e.g. representative path
    # ended earlier) -> must be honest zeros, not the old flat placeholder.
    withdrawal_rows = [
        {"age": 50, "total": 80_000.0, "total_taxes": 9_500.0, "niit": 0.0},
    ]
    original = sr._apply_overrides({
        "YOUR_AGE": 50, "PLAN_UNTIL_AGE": 52, "INCLUDE_SOCIAL_SECURITY": False,
    })
    try:
        out = sr._approximate_taxes(withdrawal_rows, retirement_age=50)
    finally:
        sr._restore_overrides(original)

    by_age = {r["age"]: r for r in out}
    assert by_age[52]["federal"] == 0.0
    assert by_age[52]["gross_income"] == 0.0


def test_taxes_working_years_still_estimated_from_salary():
    # Working-year branch is still salary/comp-derived, not from the log
    # (finding #10 changed WHICH comp fields feed it -- total_comp/after_tax
    # instead of base-only -- but it stays a comp-table approximation).
    withdrawal_rows = []
    original = sr._apply_overrides({
        "YOUR_AGE": 40, "PLAN_UNTIL_AGE": 41, "INCLUDE_SOCIAL_SECURITY": False,
    })
    try:
        out = sr._approximate_taxes(withdrawal_rows, retirement_age=65)
        comp = cfg.YOUR_COMPENSATION_BY_AGE.get(40, {}).get("base", 0)
    finally:
        sr._restore_overrides(original)

    row = next(r for r in out if r["age"] == 40)
    assert row["gross_income"] > 0
    assert row["gross_income"] != comp or comp == 0  # gross includes partner salary too


def test_taxes_working_years_include_bonus_and_rsu_not_just_base():
    """finding #10: the working-year tax gross/total must be driven by
    comp['total_comp'] (base + bonus + rsu_gross) and comp['after_tax'], not
    a flat 18%/6% of base-salary-only gross -- the sample household's comp
    table has bonus+RSU at about 44% of total comp, so a base-only formula
    would understate tax by roughly that same proportion."""
    import os
    import sys as _sys

    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _UI = os.path.join(_ROOT, "ui")
    for _p in (_ROOT, _UI):
        if _p not in _sys.path:
            _sys.path.insert(0, _p)
    from tests.conftest import load_sample_household

    overrides = load_sample_household()
    original = sr._apply_overrides(overrides)
    try:
        age = int(cfg.YOUR_AGE)
        comp = cfg.YOUR_COMPENSATION_BY_AGE[age]
        assert comp["bonus"] + comp["rsu_gross"] > comp["total_comp"] * 0.4  # sanity: RSU-heavy profile
        out = sr._approximate_taxes([], retirement_age=65)
    finally:
        sr._restore_overrides(original)

    row = next(r for r in out if r["age"] == age)
    # gross_income must include the FULL total_comp (base+bonus+RSU), not base alone.
    assert row["gross_income"] >= comp["total_comp"]
    real_your_tax = comp["total_comp"] - comp["after_tax"]
    total_tax = row["federal"] + row["state"]
    # The old bug used flat 18%/6% of (base + partner_salary) only -- omitting
    # bonus+RSU entirely. Reject any total that's consistent with a base-only
    # formula; the real comp-derived tax on just the primary's income already
    # exceeds what an 18%+6%=24% flat rate on base salary alone would yield.
    stale_base_only_tax = comp["base"] * 0.24
    assert total_tax > stale_base_only_tax
    assert total_tax >= real_your_tax * 0.99  # your-side real tax must be (near) fully captured


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
