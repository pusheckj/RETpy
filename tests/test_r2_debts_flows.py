"""Round-2 QA fixes: debts that never pay off, the check-up <-> planner carry, the
guided setup's age and spending, the partner's retirement age, and re-adding a
partner. Each test failed before its fix."""
import ast
import os
import sys
from types import SimpleNamespace

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(_ROOT, "ui")
APP = os.path.join(UI, "app.py")
for _p in (_ROOT, UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retirement_sim import debts as dm  # noqa: E402
from utils import debt_view as dv  # noqa: E402
from utils import simple_finance as sf  # noqa: E402
from utils import simple_to_full as s2f  # noqa: E402
from utils.simple_finance import DEFAULT_INPUTS, normalize_inputs  # noqa: E402

LOAN = {"name": "Personal loan", "kind": "personal", "balance": 20_000.0, "apr": 0.24, "min_payment": 300.0}
CARD = {"name": "Visa", "kind": "credit_card", "balance": 8_000.0, "apr": 0.24, "min_payment": 200.0}
BASE = {"YOUR_AGE": 35, "PARTNER_AGE": 0, "CHILDREN": [], "SPEND_RENT_MONTHLY": 1_500,
        "HOME_VALUE": 0, "MORTGAGE_MONTHLY": 0, "TARGET_RETIREMENT_AGE": 55}


@pytest.fixture(autouse=True)
def _hosted_and_rerunnable(monkeypatch):
    """Hosted mode; and AppTest reads a segmented control's single choice as a list,
    so teach it that or the planner cannot be rerun."""
    from streamlit.testing.v1 import element_tree as et
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")

    def indices(self):
        values = [self.value] if isinstance(self.value, str) else self.value
        return [self.options.index(self.format_func(v)) for v in values]
    monkeypatch.setattr(et.ButtonGroup, "indices", property(indices))


# ------------------------------------------------ 1. a debt that never pays off

def test_growing_debt_is_flagged_and_its_chart_stops():
    p = dm.amortize([LOAN], 0)
    assert not p.paid_off and p.growing and p.remaining > 100 * LOAN["balance"]
    cut = dm.until_runaway(p.balances)
    assert 1 < len(cut) < 100 and max(cut) <= 2 * LOAN["balance"]
    # a plan that pays off, or a slow one that still shrinks, is not "growing"
    assert not dm.amortize([LOAN], 200).growing
    slow = dm.amortize([{**LOAN, "apr": 0.06, "min_payment": 101.0}], 0)
    assert not slow.paid_off and not slow.growing


def _tile_script():
    import os
    import sys
    sys.path[:0] = [os.environ["R2_UI"], os.path.dirname(os.environ["R2_UI"])]
    import streamlit as st
    from components import debt_payoff
    with st.container(border=True, key="mc-tile-debts"):
        debt_payoff.render(st)


def _tile(monkeypatch, overrides):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("R2_UI", UI)
    at = AppTest.from_function(_tile_script, default_timeout=60)
    at.session_state["user_overrides"] = dict(overrides)
    at.run()
    assert not at.exception, at.exception
    return at


def test_the_tile_shows_no_absurd_numbers_for_a_debt_that_never_pays_off(monkeypatch):
    at = _tile(monkeypatch, {**BASE, "DEBTS": [LOAN], "DEBT_EXTRA_MONTHLY": 0})
    html = "\n".join(m.value for m in at.markdown)
    text = html + "\n".join(c.value for c in at.caption) + "\n".join(w.value for w in at.warning)
    assert "Keeps growing" in html and "keeps growing" in " ".join(w.value for w in at.warning)
    assert "723" not in text and "worse off" not in text and "less at" not in text
    assert "no fair comparison" in " ".join(c.value for c in at.caption)
    assert at.get("plotly_chart")


def test_the_balance_chart_stays_readable_when_a_balance_grows():
    from datetime import date
    from components import debt_payoff
    now, faster = dv.plan({"DEBTS": [LOAN]}), dv.plan({"DEBTS": [LOAN]}, more=100)
    mins = dv.plan({"DEBTS": [LOAN]}, minimums_only=True)
    fig = debt_payoff.balance_figure(now, faster, mins, 100, date(2026, 11, 13), False)
    top = max(max(t.y) for t in fig.data)
    assert top <= 2 * LOAN["balance"] + 1                    # was $700 million
    assert "keeps growing" in fig.data[0].name
    assert len(fig.data[2].y) > len(fig.data[1].y)           # $100 more does pay it off


# ------------------------------------------------ 4. $0 minimum at 0%, zero rows

def test_a_zero_percent_debt_is_not_underwater():
    promo = {"name": "Promo", "kind": "credit_card", "balance": 6_000.0, "apr": 0.0, "min_payment": 0.0}
    assert dm.amortize([promo]).underwater == [] and dm.no_minimum([promo]) == [0]
    s = dv.summary({"DEBTS": [promo]})
    assert s.underwater == [] and s.no_minimum == ["Promo"]
    assert sf.underwater_debts([{"name": "P", "balance": 6_000.0, "apr_pct": 0.0, "min_payment": 0.0}]) == []
    assert dm.amortize([LOAN], 0).underwater == [0]       # a real underwater loan still is


def test_a_paid_off_row_has_no_minimum_in_the_needs():
    paid = {"name": "Paid card", "balance": 0.0, "apr_pct": 20.0, "min_payment": 25.0}
    card = {"name": "Card", "balance": 3_000.0, "apr_pct": 20.0, "min_payment": 90.0}
    simple = normalize_inputs({**DEFAULT_INPUTS, "debts": [paid, card], "needs_monthly": 2_500.0})
    assert s2f.debt_minimums(simple) == 90.0
    assert s2f.spending_split(simple)["SPEND_OTHER_MONTHLY"] == 2_410
    planner = {"DEBTS": [{**CARD, "balance": 0.0, "min_payment": 25.0},
                         {**CARD, "name": "Card", "min_payment": 90.0}]}
    back = s2f.debts_to_checkup(simple, planner)
    assert back is None or back["needs_monthly"] == 2_500.0


def test_the_checkup_footnote_reads_as_a_sentence():
    src = open(os.path.join(UI, "components", "simple_mode.py"), encoding="utf-8").read()
    assert "Contribution limits are yearly include" not in src
    assert "limits. They include age-50+ catch-up amounts" in src


# ------------------------------------------------ 5. the version switch guard

def test_the_mode_switch_ignores_a_label_it_does_not_know():
    tree = ast.parse(open(APP, encoding="utf-8").read())
    wanted = [n for n in tree.body
              if (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "MODES")
              or (isinstance(n, ast.FunctionDef) and n.name in ("_on_mode_switch", "_share_debts"))]
    ns = {"st": SimpleNamespace(session_state={"mode_switch_full": None, "app_mode": "full"})}
    exec(compile(ast.Module(wanted, []), APP, "exec"), ns)
    ns["_on_mode_switch"]("mode_switch_full")              # was StopIteration
    assert ns["st"].session_state["app_mode"] == "full"
    ns["st"].session_state["mode_switch_full"] = "Nonsense"
    ns["_on_mode_switch"]("mode_switch_full")
    assert ns["st"].session_state["app_mode"] == "full"


# ------------------------------------------------ 2. planner -> check-up -> planner

def _planner():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.button(key="device_skip").click().run()
    next(b for b in at.button if b.label == "Open the retirement planner").click().run()
    at.button(key="gs_skip").click().run()
    assert not at.exception, at.exception
    return at


def test_the_extra_payment_and_order_survive_a_trip_to_the_checkup():
    at = _planner()
    at.button(key="debt_add").click().run()
    at.text_input(key="debt_0_name").set_value("Visa card")
    at.number_input(key="debt_0_balance").set_value(8_000)
    at.number_input(key="debt_0_apr").set_value(24.0)
    at.number_input(key="debt_0_min").set_value(200).run()
    at.number_input(key="debt_extra").set_value(100)
    at.radio(key="debt_strategy").set_value("snowball").run()
    ov = at.session_state["user_overrides"]
    assert ov["DEBT_EXTRA_MONTHLY"] == 100 and ov["DEBT_STRATEGY"] == "snowball"
    [r for r in at.radio if r.key == "mode_switch_full"][-1].set_value("Money check-up").run()
    assert not at.exception, at.exception
    at.radio(key="mode_switch_simple").set_value("Retirement planner").run()
    assert not at.exception, at.exception
    ov = at.session_state["user_overrides"]
    assert ov["DEBT_EXTRA_MONTHLY"] == 100 and ov["DEBT_STRATEGY"] == "snowball"
    assert at.number_input(key="debt_extra").value == 100
    assert at.radio(key="debt_strategy").value == "snowball"
    assert at.number_input(key="debt_0_balance").value == 8_000


# ------------------------------------------------ 3. the what-if box

def test_the_what_if_box_carries_its_default_in_the_element(monkeypatch):
    """A box that mounts again (after Run simulation) starts from what its element
    carries, so the default must be the element's, not just a session-state seed."""
    at = _tile(monkeypatch, {**BASE, "DEBTS": [CARD], "DEBT_EXTRA_MONTHLY": 0})
    box = at.number_input(key="debt_whatif")
    assert box.value == 100 and box.proto.default == 100


# ------------------------------------------------ 6. min == max sliders

def _slider_script():
    import os
    import sys
    sys.path[:0] = [os.environ["R2_UI"], os.path.dirname(os.environ["R2_UI"])]
    import streamlit as st
    from utils.slider_input import slider_with_box
    st.session_state["out"] = slider_with_box(st, "Retire at", 99, 99, 1, key="s_fixed")


def test_a_slider_with_nothing_to_slide_is_a_fixed_value(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("R2_UI", UI)
    at = AppTest.from_function(_slider_script, default_timeout=30).run()
    assert not at.exception, at.exception
    assert at.session_state["out"] == 99 and not at.slider
    assert any("Retire at: **99**" in m.value for m in at.markdown)


def _setup_script():
    import os
    import sys
    sys.path[:0] = [os.environ["R2_UI"], os.path.dirname(os.environ["R2_UI"])]
    import streamlit as st
    from components import guided_setup
    if not guided_setup.started(st):
        guided_setup.begin(st, st.session_state.get("simple_inputs"))
    if guided_setup.active(st):
        guided_setup.render(st)


@pytest.fixture
def wizard(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("R2_UI", UI)

    def make(step=None, simple=None, **overrides):
        at = AppTest.from_function(_setup_script, default_timeout=60)
        at.session_state["user_overrides"] = {"YOUR_AGE": 25, "PARTNER_AGE": 25, **overrides}
        if simple is not None:
            at.session_state["simple_inputs"] = simple
        at.run()
        if step is not None:
            at.session_state["setup"] = {**at.session_state["setup"], "step": step}
            at.run()
        assert not at.exception, at.exception
        return at
    return make


def test_the_setup_retirement_step_works_for_a_99_year_old(wizard):
    from components import guided_setup as gs
    step = next(i for i, s in enumerate(gs.STEPS) if s.title == "Retirement")
    at = wizard(step=step, YOUR_AGE=99, PARTNER_AGE=0, TARGET_RETIREMENT_AGE=99)
    assert not at.exception and not at.slider
    assert at.session_state["gs_target"] == 99


# ------------------------------------------------ 7. the partner's retirement age

def _goals_script():
    import os
    import sys
    sys.path[:0] = [os.environ["R2_UI"], os.path.dirname(os.environ["R2_UI"])]
    import streamlit as st
    from components import sec_retirement_goals
    sec_retirement_goals.render_retirement_ages(st)


@pytest.fixture
def goals(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("R2_UI", UI)
    at = AppTest.from_function(_goals_script, default_timeout=60)
    at.session_state["user_overrides"] = {"YOUR_AGE": 38, "PARTNER_AGE": 36,
                                          "TARGET_RETIREMENT_AGE": 55, "PARTNER_RETIREMENT_AGE": None}
    return at.run()


def test_the_years_after_you_box_uses_the_slider_range(goals):
    at = goals
    box = at.number_input(key="ay_partner_later")
    box.set_value(30).run()                      # 55 - 2 + 30 = 83, once clamped to 75
    assert at.session_state["user_overrides"]["PARTNER_RETIREMENT_AGE"] == 83
    assert at.number_input(key="ay_partner_later").value == 30
    at.number_input(key="ay_partner_later").set_value(80).run()      # past 99: moved, with a note
    assert at.session_state["user_overrides"]["PARTNER_RETIREMENT_AGE"] == 99
    assert at.number_input(key="ay_partner_later").value == 46
    assert any("can only be 25 to 99, so 99 was used" in c.value for c in at.caption)
    assert at.slider(key="ay_partner_target_age").value == 99
    at.number_input(key="ay_partner_later").set_value(-60).run()
    assert at.session_state["user_overrides"]["PARTNER_RETIREMENT_AGE"] == 25
    assert any("so 25 was used" in c.value for c in at.caption)


def test_the_setup_partner_gap_is_moved_into_range_with_a_note(wizard):
    from components import guided_setup as gs
    step = next(i for i, s in enumerate(gs.STEPS) if s.title == "Retirement")
    at = wizard(step=step, YOUR_AGE=40, PARTNER_AGE=37, FILING_STATUS="Married filing jointly",
                TARGET_RETIREMENT_AGE=55)
    at.number_input(key="gs_partner_later").set_value(90).run()
    assert not at.exception, at.exception
    assert at.number_input(key="gs_partner_later").value == 47      # 55 - 3 + 47 = 99
    assert any("so 47 years was used" in c.value for c in at.caption)
    assert gs._partner_retire_age(at.session_state["user_overrides"], 55, 47) == 99


# ------------------------------------------------ 8. check-up -> setup

def test_the_checkup_age_is_carried_into_the_setup(wizard):
    simple = {**DEFAULT_INPUTS, "gross_salary_annual": 80_000.0, "age": 35}
    assert s2f.carried(simple)["YOUR_AGE"] == 35 and s2f.summary(simple)["age"] == 35
    assert "YOUR_AGE" not in s2f.carried({**simple, "age": 0})
    at = wizard(simple=simple)
    assert at.number_input(key="gs_age").value == 35
    assert any("From your check-up" in c.value for c in at.caption)


def test_the_setup_spending_matches_the_married_checkup_truthfully(wizard):
    from components import guided_setup as gs
    step = next(i for i, s in enumerate(gs.STEPS) if s.title == "Monthly spending")
    simple = {**DEFAULT_INPUTS, "gross_salary_annual": 90_000.0, "needs_monthly": 5_000.0,
              "wants_monthly": 2_500.0, "married": True, "partner_salary_annual": 95_000.0,
              "debts": [], "extra_debt_payment_monthly": 0.0}
    at = wizard(step=step, simple=simple, FILING_STATUS="Married filing jointly",
                SPEND_RENT_MONTHLY=1_800, MORTGAGE_MONTHLY=0, PARTNER_OTHER_MONTHLY=400)
    assert at.number_input(key="gs_spend_PARTNER_OTHER_MONTHLY").value == 0
    text = " ".join(m.value for m in at.markdown)
    assert "Matches your check-up" in text and "$7,500 a month" in text.replace("\\$", "$")
    at.number_input(key="gs_spend_PARTNER_OTHER_MONTHLY").set_value(400).run()
    assert "more than your check-up" in " ".join(m.value for m in at.markdown)


def test_max_out_at_the_401k_limit_carries_exactly_the_limit():
    pct = sf.max_401k_pct(320_000, None, 56)
    simple = {**DEFAULT_INPUTS, "gross_salary_annual": 320_000.0, "age": 56, "retirement_contrib_pct": pct}
    limit = sf.contribution_limits(False, None, 56)["401k"]
    assert s2f.carried(simple)["YOUR_401K_CONTRIBUTION"] == limit
    src = open(os.path.join(UI, "components", "simple_mode.py"), encoding="utf-8").read()
    assert 'decimals=2)' in src          # the percent box shows 10.16, not 10.2 (= $32,640)


# ------------------------------------------------ 9. a partner removed and added again

def _about_script():
    import os
    import sys
    sys.path[:0] = [os.environ["R2_UI"], os.path.dirname(os.environ["R2_UI"])]
    import streamlit as st
    from components import sec_about_you, sec_retirement_goals
    sec_about_you.render_body(st)
    sec_retirement_goals.render_retirement_ages(st)
    st.session_state["mc_partner_stale"] = st.session_state.get("sv_manual_partner_401k")


def test_a_partner_added_again_starts_clean(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from utils.household import JUST_ME, SPOUSE
    monkeypatch.setenv("R2_UI", UI)
    at = AppTest.from_function(_about_script, default_timeout=60)
    at.session_state["user_overrides"] = {"YOUR_AGE": 38, "PARTNER_AGE": 36,
                                          "FILING_STATUS": "Married filing jointly",
                                          "TARGET_RETIREMENT_AGE": 55, "PARTNER_RETIREMENT_AGE": 45,
                                          "PARTNER_401K_CONTRIBUTION": 24_500}
    at.session_state["sv_manual_partner_401k"] = 24_500
    at.session_state["si_partner_base"] = 90_000
    at.run()
    assert at.session_state["user_overrides"]["PARTNER_RETIREMENT_AGE"] == 45
    at.radio(key="ay_household").set_value(JUST_ME).run()
    assert not at.exception, at.exception
    for k in ("sv_manual_partner_401k", "si_partner_base", "ay_partner_target_age"):
        assert k not in at.session_state.filtered_state, k
    at.radio(key="ay_household").set_value(SPOUSE).run()
    assert not at.exception, at.exception
    ov = at.session_state["user_overrides"]
    assert ov.get("PARTNER_401K_CONTRIBUTION", 0) == 0 and ov["PARTNER_RETIREMENT_AGE"] != 45
    assert ov["PARTNER_AGE"] == 38           # starts at your own age
