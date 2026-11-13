"""The Investments sidebar section.

It holds the old Savings section ("Saving each year") and the investing half of
Assumptions ("Returns and mix"). Assumptions (advanced) keeps spending rules and
pre-Medicare healthcare; "Retirement goals" is now "Retirement". Widget keys,
override keys and saved-profile values did not change.
"""
import ast
import os
import re
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.conftest import load_sample_household  # noqa: E402
from utils.derived import KEEP_AMOUNTS_MODE, MANUAL_MODE, SAVINGS_MODES  # noqa: E402
from utils.widget_sync import DIRECT_MAPPINGS  # noqa: E402

SECTION_ORDER = ["About you", "Family", "Income", "Taxes", "House", "Expenses", "Debts",
                 "Accounts", "Investments", "Retirement", "Assumptions (advanced)"]

RETURNS_AND_MIX_KEYS = {"sa_scenario", "sa_stock_alloc", "sa_fee_bps", "sa_vol_drag",
                        "sa_inflation", "sa_glide_enable", "sa_glide_start", "sa_glide_end",
                        "sa_roth_enable", "sa_roth_target", "sa_roth_max", "sa_roth_stop"}
ASSUMPTIONS_LEFTOVER_KEYS = {"sa_dyn_enable", "sa_ret_spend", "sa_aca", "sa_aca_benchmark",
                             "sa_aca_child"}
SAVING_KEYS = {"sv_mode", "sv_match_pct", "sv_inflation_adjust", "sv_after_tax_401k"}
MANUAL_KEYS = {"sv_manual_your_401k", "sv_manual_your_hsa", "sv_manual_your_roth",
               "sv_manual_your_brk", "sv_manual_partner_401k", "sv_manual_partner_roth",
               "sv_manual_partner_brk"}
MAX_OUT_KEYS = {"sv_max_your_401k_contribution", "sv_max_your_hsa_contribution",
                "sv_max_your_backdoor_roth", "sv_max_partner_401k_contribution",
                "sv_max_partner_roth_contribution", "sv_max_all"}


def _script():
    import os
    import sys
    sys.path[:0] = [os.environ["INV_TEST_UI"], os.path.dirname(os.environ["INV_TEST_UI"])]
    import streamlit as st
    from components import sec_assumptions, sec_investments
    {"investments": sec_investments, "assumptions": sec_assumptions}[os.environ["INV_TEST_WHAT"]].render(st)


def _draw(monkeypatch, what, overrides):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("INV_TEST_UI", _UI)
    monkeypatch.setenv("INV_TEST_WHAT", what)
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    at = AppTest.from_function(_script, default_timeout=60)
    at.session_state["user_overrides"] = dict(overrides)
    at.run()
    assert not at.exception, at.exception
    return at


def _keys(at):
    keys = set()
    for kind in ("number_input", "slider", "toggle", "radio", "selectbox", "button"):
        keys |= {w.key for w in getattr(at, kind) if w.key}
    return keys


def _couple(**extra):
    ov = load_sample_household()
    ov.update(extra)
    return ov


# ---------------------------------------------------------------- titles and order

def _labels(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    return [(c.args[1].value, c.args[2].value) for c in ast.walk(tree)
            if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "section_expander"]


def test_section_titles_and_icons():
    comp = os.path.join(_UI, "components")
    assert _labels(os.path.join(comp, "sec_investments.py")) == [("Investments", "trending_up")]
    assert _labels(os.path.join(comp, "sec_retirement_goals.py")) == [("Retirement", "flag")]
    assert _labels(os.path.join(comp, "sec_assumptions.py")) == [("Assumptions (advanced)", "tune")]
    assert _labels(os.path.join(comp, "account_inputs.py")) == [("Accounts", "account_balance")]
    # Savings is no longer a section of its own
    assert _labels(os.path.join(comp, "sec_savings.py")) == []
    assert not hasattr(__import__("components.sec_savings", fromlist=["x"]), "render")


def test_app_renders_the_sections_in_the_new_order():
    src = open(os.path.join(_UI, "app.py"), encoding="utf-8").read()
    body = src[src.index("        # Linear walkthrough"):]
    body = body[:body.index('_safe_render("components.faq")')]
    order = re.findall(r'_safe_render\("components\.(\w+)"\)', body)
    assert order == ["sec_about_you", "sec_family", "sec_income", "sec_taxes", "sec_house",
                     "sec_expenses", "sec_debts", "account_inputs", "sec_investments",
                     "sec_retirement_goals", "sec_assumptions"]
    # Savings and the investing assumptions are drawn inside Investments, never twice
    assert "sec_savings" not in order
    # Investments draws after Taxes (which reads its widgets) and before Retirement
    assert order.index("sec_taxes") < order.index("sec_investments") < order.index("sec_retirement_goals")


def test_planner_sidebar_shows_the_sections_in_order(monkeypatch):
    from streamlit.testing.v1 import AppTest, element_tree as et

    def indices(self):                     # AppTest cannot rerun a segmented control otherwise
        values = [self.value] if isinstance(self.value, str) else self.value
        return [self.options.index(self.format_func(v)) for v in values]
    monkeypatch.setattr(et.ButtonGroup, "indices", property(indices))
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    at = AppTest.from_file(os.path.join(_UI, "app.py"), default_timeout=90).run()
    at.button(key="device_skip").click().run()
    next(b for b in at.button if b.label == "Open the retirement planner").click().run()
    at.button(key="gs_skip").click().run()
    assert not at.exception, at.exception
    labels = [e.label for e in at.sidebar.get("status")]
    assert labels == SECTION_ORDER + ["Settings FAQ"]
    # every section drew (no placeholder replaced a broken one)
    sidebar_keys = {w.key for kind in ("number_input", "slider", "toggle", "radio", "selectbox")
                    for w in getattr(at.sidebar, kind) if w.key}
    assert {"sv_mode", "sa_scenario", "sa_dyn_enable", "ai_your_401k"} <= sidebar_keys


# ---------------------------------------------------------------- what is inside

def test_investments_holds_saving_and_returns_widgets(monkeypatch):
    at = _draw(monkeypatch, "investments",
               _couple(SAVINGS_MODE=KEEP_AMOUNTS_MODE, YOUR_401K_CONTRIBUTION=0,
                       YOUR_HSA_CONTRIBUTION=0, YOUR_BACKDOOR_ROTH=0))
    keys = _keys(at)
    assert SAVING_KEYS <= keys
    assert {"sv_manual_your_401k", "sv_manual_your_hsa", "sv_manual_your_roth",
            "sv_manual_partner_401k", "sv_manual_partner_roth"} <= keys
    assert "sv_max_all" in keys and keys & MAX_OUT_KEYS
    assert RETURNS_AND_MIX_KEYS <= keys
    assert not keys & ASSUMPTIONS_LEFTOVER_KEYS
    # the two group labels, saving first
    bold = [m.value for m in at.markdown if m.value in ("**Saving each year**", "**Returns and mix**")]
    assert bold == ["**Saving each year**", "**Returns and mix**"]


@pytest.mark.parametrize("mode", SAVINGS_MODES)
def test_every_savings_mode_still_renders_inside_investments(monkeypatch, mode):
    at = _draw(monkeypatch, "investments", _couple(SAVINGS_MODE=mode))
    assert at.radio(key="sv_mode").value == mode
    assert RETURNS_AND_MIX_KEYS <= _keys(at)


def test_savings_mode_switch_works(monkeypatch):
    at = _draw(monkeypatch, "investments", _couple(SAVINGS_MODE=SAVINGS_MODES[0]))
    assert not _keys(at) & MANUAL_KEYS
    at.radio(key="sv_mode").set_value(MANUAL_MODE).run()
    assert not at.exception, at.exception
    assert "sv_manual_your_401k" in _keys(at)
    assert at.session_state["user_overrides"]["SAVINGS_MODE"] == MANUAL_MODE


def test_max_out_works_inside_investments(monkeypatch):
    at = _draw(monkeypatch, "investments", _couple(SAVINGS_MODE=KEEP_AMOUNTS_MODE,
                                                   YOUR_HSA_CONTRIBUTION=0))
    at.button(key="sv_max_all").click().run()
    assert not at.exception, at.exception
    assert at.number_input(key="sv_manual_your_hsa").value > 0
    assert at.session_state["user_overrides"]["YOUR_HSA_CONTRIBUTION"] == \
        at.number_input(key="sv_manual_your_hsa").value


def test_return_scenario_change_reaches_the_overrides(monkeypatch):
    at = _draw(monkeypatch, "investments", _couple(ACTIVE_RETURN_SCENARIO="historical"))
    at.radio(key="sa_scenario").set_value("Pessimistic").run()
    assert not at.exception, at.exception
    assert at.session_state["user_overrides"]["ACTIVE_RETURN_SCENARIO"] == "pessimistic"


def test_assumptions_keeps_only_the_leftovers(monkeypatch):
    at = _draw(monkeypatch, "assumptions", _couple())
    keys = _keys(at)
    assert ASSUMPTIONS_LEFTOVER_KEYS <= keys
    assert not keys & (RETURNS_AND_MIX_KEYS | SAVING_KEYS | MANUAL_KEYS)


def test_moved_widgets_keep_their_keys_and_overrides():
    """widget_sync maps each moved widget key to the same override as before."""
    expected = {"sa_scenario": "ACTIVE_RETURN_SCENARIO", "sa_stock_alloc": "STOCK_ALLOCATION",
                "sa_fee_bps": "INVESTMENT_FEE_RATE", "sa_vol_drag": "APPLY_VOLATILITY_DRAG",
                "sa_inflation": "EXPECTED_INFLATION", "sa_glide_enable": "GLIDE_PATH_ENABLED",
                "sa_roth_enable": "ENABLE_ROTH_CONVERSION", "sv_mode": "SAVINGS_MODE",
                "sv_manual_your_401k": "YOUR_401K_CONTRIBUTION",
                "sv_after_tax_401k": "YOUR_AFTER_TAX_401K_PCT",
                "sa_dyn_enable": "DYNAMIC_SPENDING_ENABLED", "sa_aca": "ACA_ENABLED"}
    for widget, override in expected.items():
        assert DIRECT_MAPPINGS[widget][0] == override


def test_a_saved_profile_loads_unchanged(monkeypatch):
    """Drawing Investments and Assumptions on a saved profile leaves its investing,
    savings and healthcare settings exactly as saved."""
    ov = _couple(SAVINGS_MODE=KEEP_AMOUNTS_MODE, ACTIVE_RETURN_SCENARIO="conservative",
                 STOCK_ALLOCATION=0.7, INVESTMENT_FEE_RATE=0.0025, EXPECTED_INFLATION=0.03,
                 GLIDE_PATH_ENABLED=True, GLIDE_PATH_START_STOCK_PCT=0.85,
                 GLIDE_PATH_END_STOCK_PCT=0.5, ENABLE_ROTH_CONVERSION=True,
                 ROTH_CONVERSION_MAX_ANNUAL=80_000, ROTH_CONVERSION_STOP_AGE=65,
                 YOUR_401K_CONTRIBUTION=12_000, YOUR_HSA_CONTRIBUTION=3_000,
                 YOUR_401K_MATCH_PCT=0.04, YOUR_AFTER_TAX_401K_PCT=0.05,
                 DYNAMIC_SPENDING_ENABLED=False, ACA_BENCHMARK_MONTHLY_AT_40=720)
    investing = ["SAVINGS_MODE", "ACTIVE_RETURN_SCENARIO", "STOCK_ALLOCATION", "INVESTMENT_FEE_RATE",
                 "EXPECTED_INFLATION", "GLIDE_PATH_ENABLED", "GLIDE_PATH_START_STOCK_PCT",
                 "GLIDE_PATH_END_STOCK_PCT", "ENABLE_ROTH_CONVERSION", "ROTH_CONVERSION_MAX_ANNUAL",
                 "ROTH_CONVERSION_STOP_AGE", "YOUR_401K_CONTRIBUTION", "YOUR_HSA_CONTRIBUTION",
                 "YOUR_401K_MATCH_PCT", "YOUR_AFTER_TAX_401K_PCT"]
    leftovers = ["DYNAMIC_SPENDING_ENABLED", "ACA_BENCHMARK_MONTHLY_AT_40"]
    for what, keys in (("investments", investing), ("assumptions", leftovers)):
        out = _draw(monkeypatch, what, ov).session_state["user_overrides"]
        for k in keys:
            assert out[k] == pytest.approx(ov[k]), (what, k)
