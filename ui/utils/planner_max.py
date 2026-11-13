"""Max out for the planner's Savings inputs: what each account can take.

Pure functions (no Streamlit), so the limits and the when-to-show rules can be
tested on their own. The Investments section (components/sec_savings.py, drawn under
"Saving each year") draws the
buttons and writes the amounts; this module only decides them.

How each limit is worked out (the same as the simulation and Auto-allocate):
* 401(k): the IRS deferral limit for the person's age (catch-up from 50), and
  no more than their pay.
* HSA: the family limit when there is a partner or a child, else the self-only
  limit (catch-up from 55), and no more than their pay left after the 401(k).
  (Auto-allocate and the engine use the same rule.)
* Your Roth IRA: the IRA limit (catch-up from 50). It is modeled as a backdoor
  Roth, so there is no income limit.
* Partner Roth IRA: the IRA limit too (catch-up from 50), and no more than the
  earned income behind it (derived.partner_roth_allowed). No income limit:
  above the direct-Roth range it goes in as a backdoor Roth, as yours does.
"""
from __future__ import annotations

from typing import Dict, Iterable, NamedTuple

try:
    from utils.coerce import safe_int
    from utils import derived
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int  # type: ignore
    from ui.utils import derived  # type: ignore

YOUR_401K = "YOUR_401K_CONTRIBUTION"
PARTNER_401K = "PARTNER_401K_CONTRIBUTION"
YOUR_HSA = "YOUR_HSA_CONTRIBUTION"
YOUR_ROTH = "YOUR_BACKDOOR_ROTH"
PARTNER_ROTH = "PARTNER_ROTH_CONTRIBUTION"

# The accounts that have a limit, in the order "max out all" fills them: the
# 401(k)s and HSA first, since they lower the income the partner's Roth
# phase-out is measured on.
MAX_OUT_ORDER = (YOUR_401K, PARTNER_401K, YOUR_HSA, YOUR_ROTH, PARTNER_ROTH)

# The widget key of each account's manual input (Keep my amounts / Manual).
MANUAL_WIDGETS = derived._MANUAL_WIDGETS

# Largest value each manual input accepts (st.number_input max_value). The
# 401(k) bound is fixed and generous so an age edit can never push a stored
# widget value above it; every limit below stays under these.
INPUT_MAX: Dict[str, int] = {
    YOUR_401K: 40_000, PARTNER_401K: 40_000,
    YOUR_HSA: 10_000, YOUR_ROTH: 10_000, PARTNER_ROTH: 10_000,
}

# The states a Max out control can be in.
BUTTON = "button"        # below the limit: offer the button
AT_LIMIT = "at_limit"    # already there: show "At the limit"
NONE = "none"            # nothing to show


class MaxOut(NamedTuple):
    state: str
    target: int          # dollars a click sets (0 unless state is BUTTON/AT_LIMIT)
    current: int


def has_partner(overrides: dict) -> bool:
    return safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0


def _age(overrides: dict, key: str, default: int) -> int:
    return safe_int(overrides.get(key, default), default)


def _amount(overrides: dict, key: str) -> int:
    return max(0, safe_int(overrides.get(key, 0), 0))


def _contributions(overrides: dict) -> Dict[str, int]:
    """The five limited amounts as they stand (the tax-advantaged ones)."""
    return {k: _amount(overrides, k) for k in MAX_OUT_ORDER}


def _pay(overrides: dict, key: str) -> int:
    """Yearly pay (base + bonus + RSU) behind a 401(k) / HSA."""
    kw = derived._working_tax_inputs(overrides, pretax_savings=False)
    return int(kw["partner_wages" if key.startswith("PARTNER_") else "your_wages"])


hsa_family = derived.hsa_family  # one rule for Max out, Auto-allocate and the engine


def irs_limit(key: str, overrides: dict) -> int:
    """The IRS limit for the account, at the person's own age. 0 if the person
    isn't in the plan or the key has no limit."""
    your_age = _age(overrides, "YOUR_AGE", 30)
    partner_age = _age(overrides, "PARTNER_AGE", 0)
    if key == YOUR_401K:
        return derived.get_limit("401k", your_age)
    if key == YOUR_HSA:
        return derived.get_limit("hsa", your_age, family=hsa_family(overrides))
    if key == YOUR_ROTH:
        return derived.get_limit("ira", your_age)
    if partner_age <= 0:
        return 0
    if key == PARTNER_401K:
        return derived.get_limit("401k", partner_age)
    if key == PARTNER_ROTH:
        return derived.get_limit("ira", partner_age)
    return 0


def max_out_target(key: str, overrides: dict, input_max: int = None) -> int:
    """The most ``key`` can be set to given ``overrides``: its IRS limit, held
    to the person's pay (401(k), HSA), to what the Roth income phase-out allows
    (partner Roth) and to the input's own max. 0 when nothing can go in."""
    limit = irs_limit(key, overrides)
    if limit <= 0:
        return 0
    if key in (YOUR_401K, PARTNER_401K):
        target = min(limit, _pay(overrides, key))
    elif key == YOUR_HSA:
        deferral = min(_amount(overrides, YOUR_401K), irs_limit(YOUR_401K, overrides),
                       _pay(overrides, YOUR_401K))
        target = min(limit, _pay(overrides, YOUR_HSA) - deferral)
    elif key == PARTNER_ROTH:
        target = min(limit, int(derived.partner_roth_allowed(overrides, _contributions(overrides))))
    else:
        target = limit
    if input_max is not None:
        target = min(target, input_max)
    return max(0, int(target))


def max_out_state(key: str, overrides: dict, input_max: int = None) -> MaxOut:
    """What to show beside ``key``'s input: a button, "at the limit", or nothing."""
    current = _amount(overrides, key)
    if irs_limit(key, overrides) <= 0:
        return MaxOut(NONE, 0, current)
    target = max_out_target(key, overrides, input_max)
    if target <= 0:
        return MaxOut(NONE, 0, current)
    return MaxOut(AT_LIMIT if current >= target else BUTTON, target, current)


def max_out_updates(overrides: dict, keys: Iterable[str] = MAX_OUT_ORDER) -> Dict[str, int]:
    """{key: new amount} for every account in ``keys`` that has room to raise,
    worked through in order so each sees the ones set before it."""
    work = dict(overrides)
    out: Dict[str, int] = {}
    for key in keys:
        st = max_out_state(key, work, INPUT_MAX.get(key))
        if st.state == BUTTON:
            out[key] = work[key] = st.target
    return out


def live_overrides(state) -> dict:
    """``state['user_overrides']`` with the manual-amount widgets applied on
    top: a value typed just before a click is in its widget a rerun before
    it is in the overrides (as in derived.sidebar_savings_budget)."""
    live = dict(state.get("user_overrides", {}) or {})
    for key, widget in MANUAL_WIDGETS.items():
        if widget in state and state[widget] is not None:
            live[key] = state[widget]
    return live


def max_out_label(target: int) -> str:
    """Button text. One "$" only: a pair of them would turn the text between
    into math in Streamlit's markdown."""
    return f"Max out \\${target:,}"


def max_out_help(key: str, overrides: dict, target: int) -> str:
    """The tooltip: where the figure comes from."""
    amount = f"\\${target:,}"
    limit = irs_limit(key, overrides)
    age = _age(overrides, "PARTNER_AGE", 0) if key.startswith("PARTNER_") else _age(overrides, "YOUR_AGE", 30)
    if target < limit:
        return f"Sets this to {amount}, as much as your pay allows. The limit is \\${limit:,}."
    if key in (YOUR_HSA,):
        note = (f"the 2026 {'family' if hsa_family(overrides) else 'self-only'} limit"
                + (", with the catch-up for 55 and over" if age >= 55 else ""))
    elif key in (YOUR_401K, PARTNER_401K):
        note = "the 2026 limit" + (", with the catch-up for 50 and over" if age >= 50 else "")
    else:
        note = "the 2026 IRA limit" + (", with the catch-up for 50 and over" if age >= 50 else "")
    return f"Sets this to {amount}, {note}."
