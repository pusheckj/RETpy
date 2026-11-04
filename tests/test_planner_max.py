"""Max out buttons in the planner's Savings section and guided setup.

The limit and show-or-hide rules live in ``ui/utils/planner_max.py`` (no
Streamlit), so most of this tests them directly. Households here are made up.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import planner_max as pm  # noqa: E402
from utils import derived  # noqa: E402
from utils.derived import KEEP_AMOUNTS_MODE, MANUAL_MODE  # noqa: E402

K401, P401, HSA, ROTH, PROTH = (pm.YOUR_401K, pm.PARTNER_401K, pm.YOUR_HSA,
                                pm.YOUR_ROTH, pm.PARTNER_ROTH)


def household(**kw):
    """A couple in a no-income-tax state, MFJ, well under the Roth phase-out."""
    base = {"YOUR_AGE": 40, "PARTNER_AGE": 38, "FILING_STATUS": "MFJ", "STATE_CHOICE": "TX",
            "YOUR_BASE_SALARY": 120_000, "PARTNER_BASE_SALARY": 80_000}
    base.update(kw)
    return base


# ---------------------------------------------------------------- limits by age

@pytest.mark.parametrize("age,k401,ira", [(49, 23_000, 7_000), (50, 30_500, 8_000)])
def test_catch_up_starts_at_50_for_401k_and_ira(age, k401, ira):
    o = household(YOUR_AGE=age, PARTNER_AGE=age)
    assert pm.max_out_target(K401, o) == pm.max_out_target(P401, o) == k401
    assert pm.max_out_target(ROTH, o) == pm.max_out_target(PROTH, o) == ira


@pytest.mark.parametrize("age,hsa", [(54, 8_300), (55, 9_300)])
def test_hsa_catch_up_starts_at_55(age, hsa):
    assert pm.max_out_target(HSA, household(YOUR_AGE=age)) == hsa


def test_each_person_uses_their_own_age():
    o = household(YOUR_AGE=49, PARTNER_AGE=50)
    assert pm.max_out_target(K401, o) == 23_000
    assert pm.max_out_target(P401, o) == 30_500
    assert pm.max_out_target(ROTH, o) == 7_000
    assert pm.max_out_target(PROTH, o) == 8_000


def test_every_limit_fits_its_input_at_every_age():
    for age in range(18, 101):
        o = household(YOUR_AGE=age, PARTNER_AGE=age, YOUR_BASE_SALARY=900_000,
                      PARTNER_BASE_SALARY=900_000)
        for key in pm.MAX_OUT_ORDER:
            assert pm.irs_limit(key, o) <= pm.INPUT_MAX[key], (key, age)


def test_input_max_caps_the_target():
    assert pm.max_out_target(K401, household(), input_max=10_000) == 10_000


# ---------------------------------------------------------------- partner absent

def test_no_partner_means_no_partner_buttons():
    o = household(PARTNER_AGE=0, PARTNER_BASE_SALARY=0)
    for key in (P401, PROTH):
        assert pm.max_out_state(key, o) == pm.MaxOut(pm.NONE, 0, 0)
    assert set(pm.max_out_updates(o)) == {K401, HSA, ROTH}


def test_a_stale_partner_amount_does_not_show_a_note():
    o = household(PARTNER_AGE=0, PARTNER_401K_CONTRIBUTION=9_000)
    assert pm.max_out_state(P401, o).state == pm.NONE


# ---------------------------------------------------------------- pay caps

def test_401k_is_held_to_pay():
    assert pm.max_out_target(K401, household(YOUR_BASE_SALARY=15_000)) == 15_000


def test_hsa_is_held_to_pay_left_after_the_401k():
    o = household(YOUR_BASE_SALARY=25_000, YOUR_401K_CONTRIBUTION=23_000)
    assert pm.max_out_target(HSA, o) == 2_000
    assert pm.max_out_target(HSA, household(YOUR_BASE_SALARY=0)) == 0


def test_no_pay_means_nothing_to_show():
    o = household(YOUR_BASE_SALARY=0, PARTNER_BASE_SALARY=0)
    assert pm.max_out_state(K401, o).state == pm.NONE
    assert pm.max_out_state(P401, o).state == pm.NONE


# ---------------------------------------------------------------- already at the limit

def test_below_at_and_over_the_limit():
    assert pm.max_out_state(K401, household(YOUR_401K_CONTRIBUTION=22_999)).state == pm.BUTTON
    assert pm.max_out_state(K401, household(YOUR_401K_CONTRIBUTION=23_000)).state == pm.AT_LIMIT
    assert pm.max_out_state(K401, household(YOUR_401K_CONTRIBUTION=31_000)).state == pm.AT_LIMIT
    m = pm.max_out_state(HSA, household(YOUR_HSA_CONTRIBUTION=100))
    assert m == pm.MaxOut(pm.BUTTON, 8_300, 100)


def test_updates_skip_accounts_already_full():
    o = household(YOUR_401K_CONTRIBUTION=23_000, YOUR_HSA_CONTRIBUTION=8_300)
    assert K401 not in pm.max_out_updates(o) and HSA not in pm.max_out_updates(o)
    full = {**o, P401: 23_000, ROTH: 7_000, PROTH: 7_000}
    assert pm.max_out_updates(full) == {}


# ---------------------------------------------------------------- partner Roth (direct, phase-out)

def test_partner_roth_below_the_phase_out_gets_the_ira_limit():
    assert pm.max_out_state(PROTH, household()) == pm.MaxOut(pm.BUTTON, 7_000, 0)


def test_partner_roth_inside_the_phase_out_gets_part_of_it():
    # $235k of pay is the middle of the $230k-$240k joint range: half the limit.
    o = household(YOUR_BASE_SALARY=150_000, PARTNER_BASE_SALARY=85_000)
    m = pm.max_out_state(PROTH, o)
    assert m.state == pm.BUTTON and 3_000 < m.target < 4_000
    # The engine's own figure for the same inputs.
    assert m.target == int(pm.derived.partner_roth_allowed(o, pm._contributions(o)))


def test_partner_roth_above_the_phase_out_has_no_button_and_a_note():
    o = household(YOUR_BASE_SALARY=300_000, PARTNER_BASE_SALARY=90_000)
    m = pm.max_out_state(PROTH, o)
    assert m == pm.MaxOut(pm.OVER_INCOME, 0, 0)
    assert pm.over_income_note(o) == "Income is above the Roth IRA limit."


def test_partner_roth_note_says_when_saving_more_would_open_it():
    # $240k of pay is just out of range, but maxed 401(k)s and an HSA bring it back in.
    o = household(YOUR_BASE_SALARY=150_000, PARTNER_BASE_SALARY=90_000)
    assert pm.max_out_state(PROTH, o).state == pm.OVER_INCOME
    assert "401(k)" in pm.over_income_note(o)
    assert pm.max_out_updates(o)[PROTH] == 7_000


def test_partner_roth_already_at_what_income_allows_is_at_limit():
    o = household(YOUR_BASE_SALARY=150_000, PARTNER_BASE_SALARY=85_000)
    allowed = pm.max_out_target(PROTH, o)
    assert pm.max_out_state(PROTH, {**o, PROTH: allowed}).state == pm.AT_LIMIT


def test_single_filer_partner_roth_uses_the_single_range():
    # An unmarried couple files two returns; the partner's $155k is inside $146k-$161k.
    o = household(FILING_STATUS="Single", YOUR_BASE_SALARY=60_000, PARTNER_BASE_SALARY=155_000)
    m = pm.max_out_state(PROTH, o)
    assert m.state == pm.BUTTON and 0 < m.target < 7_000


# ---------------------------------------------------------------- order and live values

def test_max_out_all_sets_the_401ks_before_working_out_the_partner_roth():
    o = household(YOUR_BASE_SALARY=100_000, PARTNER_BASE_SALARY=140_000)
    assert pm.max_out_state(PROTH, o).state == pm.OVER_INCOME      # on its own: no room
    up = pm.max_out_updates(o)
    assert up == {K401: 23_000, P401: 23_000, HSA: 8_300, ROTH: 7_000, PROTH: 7_000}


def test_one_account_only():
    assert pm.max_out_updates(household(), (HSA,)) == {HSA: 8_300}


def test_typed_amounts_beat_stored_overrides():
    state = {"user_overrides": household(YOUR_401K_CONTRIBUTION=0),
             pm.MANUAL_WIDGETS[K401]: 23_000}
    assert pm.live_overrides(state)[K401] == 23_000
    assert pm.live_overrides({})  == {}


def test_label_has_one_dollar_sign_and_is_escaped():
    assert pm.max_out_label(23_000) == "Max out \\$23,000"
    assert pm.max_out_label(23_000).count("$") == 1


def test_tooltips_say_where_the_figure_comes_from():
    o = household(YOUR_AGE=55)
    assert "catch-up for 55" in pm.max_out_help(HSA, o, 9_300)
    assert "catch-up for 50" in pm.max_out_help(K401, o, 30_500)
    assert "pay allows" in pm.max_out_help(K401, household(YOUR_BASE_SALARY=15_000), 15_000)
    assert "direct Roth" in pm.max_out_help(PROTH, o, 3_000)


# ---------------------------------------------------------------- the Savings section

def _savings_script():
    import os
    import sys
    sys.path[:0] = [os.environ["GS_TEST_UI"], os.path.dirname(os.environ["GS_TEST_UI"])]
    import streamlit as st
    from components import sec_savings
    sec_savings.render_body(st)


def _savings(monkeypatch, mode=KEEP_AMOUNTS_MODE, **overrides):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("GS_TEST_UI", UI)
    at = AppTest.from_function(_savings_script, default_timeout=60)
    at.session_state["user_overrides"] = household(SAVINGS_MODE=mode, **overrides)
    at.run()
    assert not at.exception, at.exception
    return at


def _keys(at):
    return {b.key for b in at.button}


@pytest.mark.parametrize("mode", [KEEP_AMOUNTS_MODE, MANUAL_MODE])
def test_clicking_max_out_fills_the_input_and_the_override(monkeypatch, mode):
    at = _savings(monkeypatch, mode)
    assert {"sv_max_your_401k_contribution", "sv_max_partner_401k_contribution",
            "sv_max_your_hsa_contribution", "sv_max_your_backdoor_roth",
            "sv_max_partner_roth_contribution", "sv_max_all"} <= _keys(at)
    at.button(key="sv_max_your_hsa_contribution").click().run()
    assert not at.exception, at.exception
    assert at.number_input(key="sv_manual_your_hsa").value == 8_300
    assert at.session_state["user_overrides"]["YOUR_HSA_CONTRIBUTION"] == 8_300
    assert "sv_max_your_hsa_contribution" not in _keys(at)        # now full
    assert any(c.value == "✓ At the limit" for c in at.caption)
    assert at.number_input(key="sv_manual_your_401k").value == 0  # nothing else moved


def test_max_out_all_applies_every_account_at_once(monkeypatch):
    at = _savings(monkeypatch, MANUAL_MODE, YOUR_AGE=50, PARTNER_AGE=50)
    at.button(key="sv_max_all").click().run()
    assert not at.exception, at.exception
    ov = at.session_state["user_overrides"]
    assert (ov[K401], ov[P401], ov[HSA], ov[ROTH], ov[PROTH]) == (
        30_500, 30_500, 8_300, 8_000, 8_000)
    assert at.number_input(key="sv_manual_partner_roth").value == 8_000
    assert not any(k.startswith("sv_max_") for k in _keys(at))     # nothing left to max


def test_max_out_all_opens_a_partner_roth_the_income_blocked(monkeypatch):
    at = _savings(monkeypatch, YOUR_BASE_SALARY=100_000, PARTNER_BASE_SALARY=140_000)
    assert "sv_max_partner_roth_contribution" not in _keys(at)
    assert any("above the Roth IRA limit" in c.value for c in at.caption)
    at.button(key="sv_max_all").click().run()
    assert at.number_input(key="sv_manual_partner_roth").value == 7_000


def test_no_partner_no_partner_buttons(monkeypatch):
    at = _savings(monkeypatch, PARTNER_AGE=0, PARTNER_BASE_SALARY=0)
    assert not any("partner" in k for k in _keys(at))
    at.button(key="sv_max_all").click().run()
    ov = at.session_state["user_overrides"]
    assert ov[K401] == 23_000 and ov[P401] == 0 and ov[PROTH] == 0


def test_taxable_brokerage_has_no_button(monkeypatch):
    at = _savings(monkeypatch, MANUAL_MODE)
    assert not any("brk" in k or "brokerage" in k for k in _keys(at))


def test_a_typed_amount_counts_when_max_out_is_clicked(monkeypatch):
    """Typing an HSA amount and pressing Max out all in the same step: the new
    HSA figure is in its widget before it is in the overrides."""
    at = _savings(monkeypatch, MANUAL_MODE)
    at.number_input(key="sv_manual_your_hsa").set_value(100)
    at.button(key="sv_max_all").click().run()
    assert at.session_state["user_overrides"]["YOUR_HSA_CONTRIBUTION"] == 8_300


def test_auto_and_custom_modes_have_no_max_out_buttons(monkeypatch):
    for mode in ("Auto-allocate (recommended)", "Custom %"):
        at = _savings(monkeypatch, mode)
        assert not any(k.startswith("sv_max_") for k in _keys(at)), mode


# ---------------------------------------------------------------- guided setup

def _setup_script():
    import os
    import sys
    sys.path[:0] = [os.environ["GS_TEST_UI"], os.path.dirname(os.environ["GS_TEST_UI"])]
    import streamlit as st
    from components import guided_setup
    if not guided_setup.started(st):
        guided_setup.begin(st, None)
        st.session_state["setup"]["step"] = next(
            i for i, s in enumerate(guided_setup.STEPS) if s.title == "Saving each year")
    guided_setup.render(st)


def _saving_step(monkeypatch, **overrides):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("GS_TEST_UI", UI)
    at = AppTest.from_function(_setup_script, default_timeout=60)
    at.session_state["user_overrides"] = household(**overrides)
    at.run()
    assert not at.exception, at.exception
    return at


def test_guided_setup_has_max_out_for_401k_hsa_and_ira(monkeypatch):
    at = _saving_step(monkeypatch)
    assert {"gs_max_gs_401k_pct", "gs_max_gs_p401k_pct", "gs_max_gs_ira"} <= _keys(at)
    at.radio(key="gs_hsa").set_value("Yes").run()
    assert "gs_max_gs_hsa_amt" in _keys(at)

    at.button(key="gs_max_gs_hsa_amt").click().run()
    assert at.number_input(key="gs_hsa_amt").value == 8_300
    at.button(key="gs_max_gs_ira").click().run()
    assert at.number_input(key="gs_ira").value == 7_000
    at.button(key="gs_max_gs_401k_pct").click().run()
    assert not at.exception, at.exception
    ov = at.session_state["user_overrides"]
    assert (ov["YOUR_HSA_CONTRIBUTION"], ov["YOUR_BACKDOOR_ROTH"], ov[K401]) == (8_300, 7_000, 23_000)
    assert at.number_input(key="gs_401k_pct").value == 19.2          # 23,000 of $120,000, rounded up
    assert "gs_max_gs_401k_pct" not in _keys(at)
    assert sum(c.value == "✓ At the limit" for c in at.caption) == 3
    at.button(key="gs_max_gs_p401k_pct").click().run()
    assert at.session_state["user_overrides"][P401] == 23_000


def test_hsa_limit_is_self_only_for_a_single_person_without_children():
    single = {"YOUR_AGE": 35, "CHILDREN": []}
    assert pm.irs_limit(pm.YOUR_HSA, single) == derived.get_limit("hsa", 35, family=False)
    with_partner = {"YOUR_AGE": 35, "PARTNER_AGE": 33, "CHILDREN": []}
    assert pm.irs_limit(pm.YOUR_HSA, with_partner) == derived.get_limit("hsa", 35, family=True)
    one_child = {"YOUR_AGE": 35, "CHILDREN": [{"years_until_birth": -2, "leaves_home_age": 18,
                                                "monthly_cost": 1000}]}
    assert pm.irs_limit(pm.YOUR_HSA, one_child) == derived.get_limit("hsa", 35, family=True)
