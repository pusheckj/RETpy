"""House-move financing pins — derived loan/payment instead of free-text fields.

The big-purchase section used to take the new home value, loan balance AND
monthly payment as three independent inputs. Nothing linked them, so raising the
home price left the loan and payment costing the OLD house. Measured on a real
profile: raising the home price by about a quarter with the other fields
untouched reported **80.4%** success when the real figure was **78.0%** — flipping a "meets
your 80% target" verdict into a miss.

Loan and payment are now DERIVED (``utils.derived.new_home_financing``) from
price / down % / rate / term / escrow, so the cost always tracks the house.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.config_builder import build_config_overrides  # noqa: E402
from utils.derived import (  # noqa: E402
    implied_mortgage_rate,
    mortgage_payment,
    new_home_financing,
)


# --------------------------------------------------------------------------
# Mortgage math
# --------------------------------------------------------------------------

def test_payment_matches_closed_form():
    # $800k, 15yr, 6.11% -> standard amortization payment ($6,798.49)
    pmt = mortgage_payment(800_000, 0.0611, 15)
    assert 6_770 < pmt < 6_830, pmt


def test_zero_rate_is_straight_line_not_a_crash():
    assert mortgage_payment(360_000, 0.0, 30) == 1_000.0


def test_degenerate_inputs_are_safe():
    assert mortgage_payment(0, 0.06, 30) == 0.0
    assert mortgage_payment(-5, 0.06, 30) == 0.0
    assert implied_mortgage_rate(0, 100, 30) == 0.0
    assert implied_mortgage_rate(100_000, 0, 30) == 0.0
    # A payment too small to ever amortize shouldn't return a bogus rate.
    assert implied_mortgage_rate(1_000_000, 10, 30) == 0.0


def test_rate_inversion_round_trips():
    for loan, years, rate in ((800_000, 15, 0.0611), (1_280_000, 30, 0.0725),
                              (500_000, 20, 0.05)):
        pi = mortgage_payment(loan, rate, years)
        assert abs(implied_mortgage_rate(loan, pi, years) - rate) < 1e-4


# --------------------------------------------------------------------------
# The actual bug: cost must track the house price
# --------------------------------------------------------------------------

def test_loan_and_payment_scale_with_home_price():
    """The regression this whole change exists to prevent."""
    cheap = new_home_financing({
        "NEW_HOME_VALUE": 1_000_000, "NEW_HOME_DOWN_PCT": 0.20,
        "NEW_MORTGAGE_RATE": 0.0611, "NEW_MORTGAGE_YEARS": 15,
        "NEW_HOME_ESCROW_PCT": 0.0135,
    })
    dear = new_home_financing({
        "NEW_HOME_VALUE": 1_600_000, "NEW_HOME_DOWN_PCT": 0.20,
        "NEW_MORTGAGE_RATE": 0.0611, "NEW_MORTGAGE_YEARS": 15,
        "NEW_HOME_ESCROW_PCT": 0.0135,
    })
    assert dear["loan"] > cheap["loan"], "a pricier house must mean a bigger loan"
    assert dear["monthly"] > cheap["monthly"], "a pricier house must cost more per month"
    assert dear["loan"] == 1_280_000                      # 80% of 1.6M
    assert dear["down_payment"] == 320_000


def test_monthly_is_all_in_pi_plus_escrow():
    fin = new_home_financing({
        "NEW_HOME_VALUE": 1_000_000, "NEW_HOME_DOWN_PCT": 0.20,
        "NEW_MORTGAGE_RATE": 0.0611, "NEW_MORTGAGE_YEARS": 15,
        "NEW_HOME_ESCROW_PCT": 0.0135,
    })
    assert abs(fin["monthly"] - (fin["principal_interest"] + fin["escrow"])) < 1e-6
    assert abs(fin["escrow"] - 1_000_000 * 0.0135 / 12) < 1e-6


def test_reproduces_a_saved_profile():
    """An existing plan must keep its numbers, not jump to a default rate.

    The sample household's saved NEW_MORTGAGE_BALANCE / NEW_MORTGAGE_MONTHLY
    ($800k / $7,923) came from exactly these terms (see tests/conftest.py).
    """
    from tests.conftest import load_sample_household

    ov = load_sample_household()
    fin = new_home_financing({
        "NEW_HOME_VALUE": ov["NEW_HOME_VALUE"], "NEW_HOME_DOWN_PCT": 0.20,
        "NEW_MORTGAGE_RATE": 0.0611,
        "NEW_MORTGAGE_YEARS": ov["NEW_MORTGAGE_YEARS"],
        "NEW_HOME_ESCROW_PCT": 0.0135,
    })
    assert abs(fin["loan"] - ov["NEW_MORTGAGE_BALANCE"]) < 1.0
    assert abs(fin["monthly"] - ov["NEW_MORTGAGE_MONTHLY"]) <= 2.0


def test_down_payment_of_100_percent_means_no_loan():
    fin = new_home_financing({"NEW_HOME_VALUE": 900_000, "NEW_HOME_DOWN_PCT": 1.0})
    assert fin["loan"] == 0.0
    assert fin["principal_interest"] == 0.0
    assert fin["monthly"] == fin["escrow"]        # still owe tax + insurance


# --------------------------------------------------------------------------
# The derived inputs are UI-only and must not reach cfg
# --------------------------------------------------------------------------

def test_financing_inputs_do_not_leak_onto_config():
    ov = {
        "YOUR_AGE": 32,
        "NEW_HOME_VALUE": 1_000_000, "NEW_MORTGAGE_BALANCE": 800_000,
        "NEW_MORTGAGE_MONTHLY": 7_923, "NEW_MORTGAGE_YEARS": 15,
        "NEW_HOME_DOWN_PCT": 0.20, "NEW_MORTGAGE_RATE": 0.0611,
        "NEW_HOME_ESCROW_PCT": 0.0135,
    }
    out = build_config_overrides(ov)
    for k in ("NEW_HOME_DOWN_PCT", "NEW_MORTGAGE_RATE", "NEW_HOME_ESCROW_PCT"):
        assert k not in out, f"{k} is UI-only and must not be pushed onto cfg"
    # the engine-facing keys still flow through
    assert out["NEW_MORTGAGE_BALANCE"] == 800_000
    assert out["NEW_MORTGAGE_MONTHLY"] == 7_923


def test_sim_runner_guard_knows_the_ui_only_keys():
    """Otherwise the override-wiring audit flags them as inert controls."""
    from utils.sim_runner import UI_ONLY_KEYS

    for k in ("NEW_HOME_DOWN_PCT", "NEW_MORTGAGE_RATE", "NEW_HOME_ESCROW_PCT"):
        assert k in UI_ONLY_KEYS


# --------------------------------------------------------------------------
# Home equity must reflect mortgage PRINCIPAL PAYDOWN, not just appreciation
# --------------------------------------------------------------------------
# The projection chart grew "Home equity" at the home appreciation rate only, so
# 15-30 years of principal payments never showed up as net worth even though the
# payments were charged as expenses. On a real profile the band understated
# home equity at age 40 by about 40%.

def test_amortization_matches_a_closed_form_schedule():
    from utils.derived import advance_mortgage, mortgage_payment

    pi = mortgage_payment(800_000, 0.0611, 15)
    # 8 years into a 15-year note. Closed form, r = 0.0611/12:
    # 800,000 * (1+r)**96 - pi * ((1+r)**96 - 1) / r = 463,701.64. The tolerance
    # is the same ~0.25% of the expected balance the original pin allowed.
    assert abs(advance_mortgage(800_000, 0.0611, pi, 96) - 463_702) < 1_150
    # fully retired at term
    assert advance_mortgage(800_000, 0.0611, pi, 180) == 0.0


def test_amortization_never_goes_negative():
    from utils.derived import advance_mortgage

    assert advance_mortgage(1_000, 0.06, 99_999, 12) == 0.0
    assert advance_mortgage(0, 0.06, 500, 12) == 0.0


def test_current_mortgage_rate_is_inferred_net_of_escrow():
    """MORTGAGE_MONTHLY is all-in; treating it as P&I implies a silly rate."""
    from utils.derived import current_mortgage_terms

    t = current_mortgage_terms({
        "MORTGAGE_BALANCE": 400_000, "MORTGAGE_YEARS_REMAINING": 14,
        "MORTGAGE_MONTHLY": 3_800, "HOME_VALUE": 600_000,
        "NEW_HOME_ESCROW_PCT": 0.0135,
    })
    assert t["pi_payment"] < 3_800, "escrow was not removed before inverting"
    assert 0.03 < t["rate"] < 0.09, f"implausible inferred rate {t['rate']}"


def test_no_mortgage_household_is_safe():
    from utils.derived import current_mortgage_terms

    t = current_mortgage_terms({"MORTGAGE_BALANCE": 0, "HOME_VALUE": 500_000})
    assert t["pi_payment"] == 0.0 and t["rate"] == 0.0


def test_projected_equity_rises_with_paydown_and_clears_at_payoff():
    from components.net_worth_projection_chart import project_net_worth
    from tests.conftest import load_sample_household

    ov = load_sample_household()
    ov["TARGET_RETIREMENT_AGE"] = 58          # project past the payoff age
    p = project_net_worth(ov)
    eq = dict(zip(p["ages"], p["by_account"]["Home equity"]))

    move = int(ov["HOUSE_MOVE_AGE"])
    payoff = move + int(ov["NEW_MORTGAGE_YEARS"])
    assert payoff in eq, "projection should span the payoff age"

    # Equity climbs every year between the move and payoff (paydown + appreciation).
    for a in range(move + 1, payoff):
        if a in eq and a + 1 in eq:
            assert eq[a] <= eq[a + 1] + 1.0, f"equity fell at age {a}"

    # At payoff the loan is gone, so equity == the whole (appreciated) house.
    home_at_payoff = ov["NEW_HOME_VALUE"] * (1.01 ** (payoff - move))
    assert eq[payoff] > home_at_payoff * 0.97, (
        f"equity {eq[payoff]:,.0f} should be ~the full home value "
        f"{home_at_payoff:,.0f} once the mortgage is retired"
    )


def test_projected_equity_beats_appreciation_only():
    """Regression guard: the old behaviour grew equity ~1%/yr and nothing else."""
    from components.net_worth_projection_chart import project_net_worth
    from tests.conftest import load_sample_household

    ov = load_sample_household()
    p = project_net_worth(ov)
    eq = dict(zip(p["ages"], p["by_account"]["Home equity"]))
    start_age = int(ov["YOUR_AGE"])
    start_equity = eq[start_age]
    end_age = max(eq)
    appreciation_only = start_equity * (1.01 ** (end_age - start_age))
    assert eq[end_age] > appreciation_only * 1.2, (
        "principal paydown is not being credited to home equity"
    )
