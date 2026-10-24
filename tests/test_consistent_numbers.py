"""One figure per concept: the numbers different sections show for the same
thing agree (or are labelled as different things).

* Savings vs Taxes: the Savings summary's tax is the Taxes section's tax, which
  is the simulation's first working year (working_year_cashflow), and "left to
  save" is what the simulation saves that year.
"""
import os
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import account_simulation as asim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from utils import derived  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils.profile_io import deserialize_overrides  # noqa: E402

FIXTURES = ["sample_household", "single_renter", "couple_three_kids", "single_parent_hoh"]


def _ui_shaped(name: str) -> dict:
    """A fixture as the sidebar holds it: the Income section rewrites the comp
    table from the income inputs every rerun, with no explicit take-home."""
    with open(os.path.join(_TESTS, "fixtures", name + ".json"), encoding="utf-8") as fh:
        ov = deserialize_overrides(fh.read())
    comp = ov.get("YOUR_COMPENSATION_BY_AGE") or {}
    ov["YOUR_COMPENSATION_BY_AGE"] = {
        age: {k: v for k, v in row.items() if k != "after_tax"} for age, row in comp.items()}
    return ov


def _comp_table(age: int, base: int) -> dict:
    """A one-row comp table, as the Income section writes it for this base pay."""
    return {int(age): {"base": base, "bonus": 0, "rsu_gross": 0, "total_comp": base, "saved": 0}}


def _engine_year_one(ov: dict):
    """(working_year_cashflow at today's age, the savings rows, HSA match)."""
    original = sr._apply_overrides(sr.build_config_overrides(ov))
    try:
        cf = asim.working_year_cashflow(cfg.YOUR_AGE)
        rows = sr._approximate_savings_contributions(int(ov.get("TARGET_RETIREMENT_AGE", 60)))
        hsa_match = float(getattr(cfg, "YOUR_HSA_MATCH", 0) or 0)
        college = float(cfg.calculate_529_contribution(cfg.YOUR_AGE))
    finally:
        sr._restore_overrides(original)
    return cf, rows, hsa_match, college


def _own_savings(row: dict, hsa_match: float) -> float:
    """What the household itself put away that year (employer money excluded)."""
    keys = ("your_401k", "your_hsa", "your_roth", "your_aftertax_roth", "your_brokerage",
            "partner_401k", "partner_roth", "partner_brokerage")
    return sum(float(row[k]) for k in keys) - hsa_match


# ---------------------------------------------------------------------------
# #10 Savings summary vs Taxes section
# ---------------------------------------------------------------------------
class TestSavingsAndTaxesAgree:
    @pytest.mark.parametrize("name", FIXTURES)
    def test_one_tax_figure_and_it_is_the_engines(self, name):
        ov = _ui_shaped(name)
        budget = derived.sidebar_savings_budget({"user_overrides": ov})
        ov.update(budget["amounts"])               # what the Savings section writes
        taxes_section = derived.sidebar_savings_budget({"user_overrides": ov})["taxes"]
        cf, _, _, _ = _engine_year_one(ov)
        assert budget["taxes"]["total"] == pytest.approx(taxes_section["total"], abs=0.01)
        assert budget["taxes"]["total"] == pytest.approx(cf["total_tax"], abs=0.01)
        assert budget["income"] == pytest.approx(cf["gross_income"])

    @pytest.mark.parametrize("name", FIXTURES)
    def test_left_to_save_is_what_the_simulation_saves(self, name):
        ov = _ui_shaped(name)
        if not str(ov.get("SAVINGS_MODE", "")).startswith("Auto"):
            pytest.skip("only the auto modes save everything that's left")
        budget = derived.sidebar_savings_budget({"user_overrides": ov})
        ov.update(budget["amounts"])
        _, rows, hsa_match, college = _engine_year_one(ov)
        saved = _own_savings(rows[0], hsa_match) + college
        if rows[0]["your_brokerage"] + rows[0]["partner_brokerage"] > 0:
            assert saved == pytest.approx(budget["disposable"], abs=1.0)
        else:
            # Kept amounts above what's left: the simulation still makes them
            # and sells investments for the gap, so it saves more than is left.
            assert saved >= budget["disposable"]

    def test_mega_backdoor_and_529_are_paid_before_the_brokerage(self):
        """Auto-allocate's brokerage share must not exceed the simulation's sweep:
        the engine treats it as a floor and would sell investments to fund it."""
        ov = _ui_shaped("single_renter")
        ov.update(SAVINGS_MODE=derived.AUTO_ALLOCATE_MODE, YOUR_BASE_SALARY=200_000,
                  YOUR_AFTER_TAX_401K_PCT=0.10, YOUR_401K_MATCH_PCT=0.05,
                  YOUR_COMPENSATION_BY_AGE=_comp_table(ov["YOUR_AGE"], 200_000))
        budget = derived.savings_budget(ov)
        assert derived.AFTER_TAX_401K_LABEL in budget["set_aside"]
        ov.update(budget["amounts"])
        _, rows, hsa_match, _ = _engine_year_one(ov)
        floor = ov["YOUR_BROKERAGE_CONTRIBUTION"]
        assert rows[0]["your_brokerage"] >= floor - 1
        assert rows[0]["your_aftertax_roth"] == pytest.approx(
            budget["set_aside"][derived.AFTER_TAX_401K_LABEL])
        placed = sum(budget["amounts"].values()) + sum(budget["set_aside"].values())
        assert placed == pytest.approx(budget["disposable"], abs=1.0)

    @pytest.mark.parametrize("mode", [derived.AUTO_ALLOCATE_MODE, derived.CUSTOM_PCT_MODE])
    def test_settles_and_does_not_drift_across_reruns(self, mode):
        ov = _ui_shaped("single_renter")
        ov.update(SAVINGS_MODE=mode, YOUR_BASE_SALARY=60_000,
                  YOUR_COMPENSATION_BY_AGE=_comp_table(ov["YOUR_AGE"], 60_000))
        state = {"user_overrides": ov}
        first = derived.sidebar_savings_budget(state)
        ov.update(first["amounts"])
        second = derived.sidebar_savings_budget(state)
        assert second["disposable"] == first["disposable"]
        assert second["amounts"] == first["amounts"]
        # Pre-tax saving lowered the tax, so more is left than with none.
        no_pretax = derived.compute_taxes({**ov, **{k: 0 for k in derived.PRETAX_KEYS}})
        assert first["taxes"]["total"] < no_pretax["total"]


def _sidebar_script():
    import os
    import sys
    sys.path.insert(0, os.environ["CONSISTENT_TEST_UI_DIR"])
    import streamlit as st
    from components import sec_savings, sec_taxes
    sec_taxes.render_body(st)
    sec_savings.render_body(st)


def test_sidebar_shows_one_tax_figure(monkeypatch):
    """Taxes draws before Savings in the sidebar; both show the same tax."""
    from streamlit.testing.v1 import AppTest
    from utils.formatting import money
    monkeypatch.setenv("CONSISTENT_TEST_UI_DIR", _UI)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    ov = _ui_shaped("sample_household")
    at = AppTest.from_function(_sidebar_script, default_timeout=60)
    at.session_state["user_overrides"] = dict(ov)
    at.run()
    assert not at.exception, at.exception
    cf, _, _, _ = _engine_year_one(dict(at.session_state["user_overrides"]))
    shown = money(cf["total_tax"], shorten=True)
    savings_tax = next(m.value for m in at.metric if m.label == "− Taxes")
    assert savings_tax == shown
    assert any(f"Total tax: {shown}" in c.value.replace("\\$", "$") for c in at.caption)
    labels = [m.label for m in at.metric]
    assert "= Left to save" in labels and "= Disposable" not in labels
