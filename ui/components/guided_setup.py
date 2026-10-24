"""Guided setup: walks a new visitor through the planner, one topic per screen.

Shown instead of the planner (and its side panel) until the visitor finishes
or skips. Answers go straight into ``st.session_state.user_overrides`` -- the
same keys the side panel edits -- and on finish the side panel's widgets are
synced from them, so nothing is entered twice. Someone who used the money
check-up starts with those answers filled in (utils/simple_to_full.py).

State lives in ``st.session_state["setup"]`` (JSON-safe, so "Remember me"
keeps it): status "active" / "skipped" / "done", the current step, the widget
keys already shown (a question seen before re-opens on its saved answer; a new
one opens blank or on the check-up's answer, never on the sample household's),
and the check-up figures quoted in the guidance.

Each step is a ``draw`` (widgets + plain "how to answer" cues), a ``commit``
(widget values -> overrides) and a ``check`` (what's still missing). Commit
runs after every draw and again in the navigation callbacks: a value typed
just before clicking Next arrives in the same run as the click, and the
callback runs before the script, so only it can save that value.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, NamedTuple, Optional

from retirement_sim import config as cfg

try:
    from utils.expense_categories import CATEGORIES
    from utils.formatting import money, money_md
    from utils.derived import AUTO_ALLOCATE_MODE, KEEP_AMOUNTS_MODE, get_limit
    from utils import simple_to_full as s2f
    from utils.household import (JUST_ME, SPOUSE, PARTNER, MFJ, SINGLE, HOH, household_of,
                                 clear_partner)
    from utils import state_choice as sc
except ImportError:  # pragma: no cover
    from ui.utils.expense_categories import CATEGORIES  # type: ignore
    from ui.utils.formatting import money, money_md  # type: ignore
    from ui.utils.derived import AUTO_ALLOCATE_MODE, KEEP_AMOUNTS_MODE, get_limit  # type: ignore
    from ui.utils import simple_to_full as s2f  # type: ignore
    from ui.utils.household import (JUST_ME, SPOUSE, PARTNER, MFJ, SINGLE, HOH,  # type: ignore
                                    household_of, clear_partner)
    from ui.utils import state_choice as sc  # type: ignore

STATE = "setup"
_DOLLAR = ":material/attach_money:"
_PCT = ":material/percent:"
# Required questions start blank (with this hint); optional amounts start at 0.
_REQUIRED = "Required"

# Where-you-live choices: every state + DC (by name), then a flat-rate fallback.
# Saved legacy values ("CA", "No state tax", "Other") map onto these.
STATES = {**{label: sc.code_for(label) for label in sc.STATE_LABELS},
          "Somewhere else (enter a rate)": cfg.STATE_FLAT}
RENT, OWN = "Rent", "Own"
KEEP, FILL = "Keep my amounts and invest the rest", "Fill my 401(k) first, then invest the rest"
SS_YES, SS_NO = "Yes", "No, plan without it"
# Children: at most this many in all (the Expenses section shows one row each),
# planned ones spaced this many years apart, and each child after the first
# costing this share of the first (the planner's default family: $2,100 for one,
# $1,400 more for the second).
MAX_KIDS = 6
_KIDS_APART = 3
_ONE_KID_COST = 2_100
_MORE_KIDS_SHARE = 2 / 3
# Short "what goes here" hints for the monthly categories.
_SPEND_HINTS = {
    "SPEND_UTILITIES_MONTHLY": "Electric, gas, water, internet, phone.",
    "SPEND_FOOD_MONTHLY": "Groceries and eating out.",
    "SPEND_TRANSPORT_MONTHLY": "Gas, car insurance, repairs, transit.",
    "SPEND_HEALTH_MONTHLY": "Health insurance you pay each month (on your pay stub).",
    "SPEND_DISCRETIONARY_MONTHLY": "Travel, shopping, hobbies, subscriptions.",
    "SPEND_OTHER_MONTHLY": "Everything else: other insurance, pets, personal care, debt payments.",
    "PARTNER_OTHER_MONTHLY": "Your partner's own spending, beyond the shared costs above.",
}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def state(st) -> Dict[str, Any]:
    return st.session_state.get(STATE) or {}


def active(st) -> bool:
    return state(st).get("status") == "active"


def skipped(st) -> bool:
    return state(st).get("status") == "skipped"


def started(st) -> bool:
    return STATE in st.session_state


def mark_done(st) -> None:
    """For a planner that is already set up (the owner's profile, a returning visitor)."""
    st.session_state[STATE] = {"status": "done", "step": 0, "seen": []}


def begin(st, simple: Any = None) -> None:
    """Start the walkthrough; copy the check-up's answers in if the visitor used it."""
    s: Dict[str, Any] = {"status": "active", "step": 0, "seen": [], "checkup": None}
    if s2f.used(simple):
        carried = s2f.carried(simple)
        st.session_state.setdefault("user_overrides", {}).update(carried)
        s["checkup"] = {**s2f.summary(simple), "keys": sorted(carried)}
    st.session_state[STATE] = s


def resume(st) -> None:
    st.session_state[STATE] = {**state(st), "status": "active", "error": None}


def restore(saved: Any) -> Optional[Dict[str, Any]]:
    """A remembered setup state, repaired; None if unusable."""
    if not isinstance(saved, dict) or saved.get("status") not in ("active", "skipped", "done"):
        return None
    step = saved.get("step")
    seen = saved.get("seen")
    checkup = saved.get("checkup")
    return {"status": saved["status"],
            "step": step if isinstance(step, int) and 0 <= step < len(STEPS) else 0,
            "seen": [k for k in seen if isinstance(k, str)] if isinstance(seen, list) else [],
            "checkup": checkup if isinstance(checkup, dict) else None}


# ---------------------------------------------------------------------------
# Widget helpers
# ---------------------------------------------------------------------------

def _ov(st) -> Dict[str, Any]:
    return st.session_state.setdefault("user_overrides", {})


def _num(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _seed(st, key: str, saved: Any, first: Any) -> None:
    """Open a question on its saved answer if it was shown before, else on ``first``."""
    ss = st.session_state
    seen = ss[STATE]["seen"]
    if key not in ss:
        ss[key] = saved if key in seen else first
    if key not in seen:
        seen.append(key)


def _from_checkup(st, *keys: str) -> bool:
    c = state(st).get("checkup") or {}
    return any(k in c.get("keys", []) for k in keys)


def _cue(st, text: str, checkup: bool = False) -> None:
    st.caption((("✓ From your check-up. " if checkup else "") + text).strip())


def _money(st, key: str, label: str, saved: Any, first: Any, hi: int = s2f.BALANCE_MAX,
           step: int = 100) -> None:
    _seed(st, key, None if saved is None else int(_num(saved)),
          None if first is None else int(_num(first)))
    st.number_input(label, min_value=0, max_value=hi, step=step, key=key, icon=_DOLLAR,
                    placeholder=_REQUIRED if first is None else None)


def _pct(st, key: str, label: str, saved: Any, first: Any) -> None:
    _seed(st, key, None if saved is None else round(_num(saved), 1),
          None if first is None else round(_num(first), 1))
    st.number_input(label, min_value=0.0, max_value=100.0, step=0.5, format="%.1f",
                    key=key, icon=_PCT, placeholder=_REQUIRED if first is None else None)


def _whole(st, key: str, label: str, saved: Any, first: Any, lo: int, hi: int) -> None:
    def ok(v):
        return None if v is None else int(min(max(_num(v, lo), lo), hi))
    _seed(st, key, ok(saved), ok(first))
    st.number_input(label, min_value=lo, max_value=hi, step=1, key=key,
                    placeholder=_REQUIRED if first is None else None)


def _choice(st, key: str, label: str, options: List[str], saved: Any, first: Any,
            horizontal: Optional[bool] = None) -> Optional[str]:
    _seed(st, key, saved if saved in options else None, first if first in options else None)
    if horizontal is None:      # short options sit in one row, long ones stack
        horizontal = sum(len(o) for o in options) <= 40
    return st.radio(label, options, key=key, horizontal=horizontal)


def _val(st, key: str) -> Any:
    return st.session_state.get(key)


def _partner(st) -> bool:
    return int(_num(_ov(st).get("PARTNER_AGE"))) > 0


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def draw_you(st) -> None:
    ov = _ov(st)
    _whole(st, "gs_age", "How old are you?", ov.get("YOUR_AGE"), None, 18, 100)
    _cue(st, "Your age today, in years.")
    hh = _choice(st, "gs_household", "Who is this plan for?", [JUST_ME, SPOUSE, PARTNER],
                 household_of(ov), None)
    _cue(st, "Pick spouse or partner if you share bills and savings. Their income and "
             "accounts come on later steps.")
    if hh in (SPOUSE, PARTNER):
        _whole(st, "gs_partner_age", "How old are they?",
               ov.get("PARTNER_AGE") if int(_num(ov.get("PARTNER_AGE"))) > 0 else None,
               None, 18, 100)


def commit_you(st) -> None:
    ov = _ov(st)
    if _val(st, "gs_age") is not None:
        ov["YOUR_AGE"] = int(_val(st, "gs_age"))
    hh = _val(st, "gs_household")
    if hh == JUST_ME:
        clear_partner(ov)
        ov["FILING_STATUS"] = SINGLE
    elif hh in (SPOUSE, PARTNER):
        ov["FILING_STATUS"] = MFJ if hh == SPOUSE else SINGLE
        if _val(st, "gs_partner_age") is not None:
            ov["PARTNER_AGE"] = int(_val(st, "gs_partner_age"))


def check_you(st) -> Optional[str]:
    if _val(st, "gs_age") is None:
        return "Enter your age to continue."
    if _val(st, "gs_household") is None:
        return "Choose who the plan is for."
    if _val(st, "gs_household") != JUST_ME and _val(st, "gs_partner_age") is None:
        return "Enter your partner's age to continue."
    return None


def _kids_saved(ov) -> Dict[str, Any]:
    """The children step's earlier answers, from the plan's children list:
    ages of those born (oldest first), how many are planned, and when."""
    kids = cfg.children_in(ov)
    born = sorted((-int(c["years_until_birth"]) for c in kids if c["years_until_birth"] <= 0),
                  reverse=True)
    planned = sorted(int(c["years_until_birth"]) for c in kids if c["years_until_birth"] > 0)
    return {"born": born, "planned": len(planned), "next": planned[0] if planned else None,
            "cost": kids[0]["monthly_cost"] if kids else None}


def _kid_count(st) -> int:
    return int(_num(_val(st, "gs_kids_have"))) + int(_num(_val(st, "gs_kids_plan")))


def draw_kids(st) -> None:
    ov = _ov(st)
    saved = _kids_saved(ov)
    _whole(st, "gs_kids_have", "How many children do you have?", len(saved["born"]), None,
           0, MAX_KIDS)
    _cue(st, "Count the children whose costs you cover. Enter 0 if none.")
    have = int(_num(_val(st, "gs_kids_have")))
    for i in range(have):
        _whole(st, f"gs_kid{i}_age", f"Age of child {i + 1}",
               saved["born"][i] if i < len(saved["born"]) else None, None, 0, 30)
    if have:
        _cue(st, "Oldest first. Their age today, in years.")
    _whole(st, "gs_kids_plan", "How many more do you plan to have?", saved["planned"], None,
           0, MAX_KIDS)
    _cue(st, "A guess is fine. Enter 0 if none.")
    if int(_num(_val(st, "gs_kids_plan"))) > 0:
        _whole(st, "gs_kids_in", "In about how many years do you expect the next one?",
               saved["next"], None, 0, 20)
        _cue(st, f"0 means this year. We space any after that {_KIDS_APART} years apart.")
    if _kid_count(st) > 0:
        _money(st, "gs_kid_cost", "Monthly cost of one child", saved["cost"], _ONE_KID_COST,
               hi=10_000, step=100)
        _cue(st, "Childcare, food, clothes and activities, until they leave home at 18. Each "
                 "child after the first is counted at about two-thirds of this. A rough guess "
                 "is fine; you can fine-tune each child later under Expenses.")


def commit_kids(st) -> None:
    have, plan = _val(st, "gs_kids_have"), _val(st, "gs_kids_plan")
    if have is None or plan is None:
        return
    ages = [_val(st, f"gs_kid{i}_age") for i in range(int(have))]
    if any(a is None for a in ages) or (plan and _val(st, "gs_kids_in") is None):
        return
    births = sorted(-int(a) for a in ages)               # oldest first
    first_planned = int(_num(_val(st, "gs_kids_in")))
    births += [first_planned + _KIDS_APART * j for j in range(int(plan))]
    cost = int(_num(_val(st, "gs_kid_cost"), _ONE_KID_COST))
    ov = _ov(st)
    ov["CHILDREN"] = [
        {**cfg.CHILD_DEFAULTS, "years_until_birth": b, "leaves_home_age": 18,
         "monthly_cost": cost if i == 0 else int(round(cost * _MORE_KIDS_SHARE))}
        for i, b in enumerate(births[:MAX_KIDS])
    ]
    if household_of(ov) == JUST_ME:
        # A single parent with a child at home usually files as head of
        # household (the side panel's About you can change it).
        ov["FILING_STATUS"] = HOH if any(-18 < b <= 0 for b in births) else SINGLE


def check_kids(st) -> Optional[str]:
    have, plan = _val(st, "gs_kids_have"), _val(st, "gs_kids_plan")
    if have is None:
        return "Enter how many children you have (0 if none)."
    if any(_val(st, f"gs_kid{i}_age") is None for i in range(int(have))):
        return "Enter each child's age."
    if plan is None:
        return "Enter how many more children you plan to have (0 if none)."
    if plan and _val(st, "gs_kids_in") is None:
        return "Enter about how many years until your next child."
    if _kid_count(st) > MAX_KIDS:
        return f"The planner takes up to {MAX_KIDS} children in all."
    return None


_STATE_FLAT_LABEL = next(label for label, c in STATES.items() if c == cfg.STATE_FLAT)


def _state_saved(ov) -> Optional[str]:
    code = ov.get("STATE_CHOICE")
    if code is None or cfg.resolve_state_code(code) == cfg.STATE_NONE:
        return None   # "no state tax" from an older plan: pick the actual state
    if cfg.resolve_state_code(code) == cfg.STATE_FLAT:
        return _STATE_FLAT_LABEL
    return sc.label_for(code)


def draw_state(st) -> None:
    ov = _ov(st)
    _seed(st, "gs_state", _state_saved(ov), None)
    where = st.selectbox("Where do you live?", list(STATES), key="gs_state",
                         placeholder="Choose your state")
    _cue(st, "Used for state income tax, with your state's own rates and rules. Texas, "
             "Florida, Washington, Nevada, Tennessee and a few others have none.")
    if where == _STATE_FLAT_LABEL:
        _pct(st, "gs_state_rate", "Your state's income tax rate", _num(
            ov.get("YOUR_MARGINAL_TAX_RATE"), 0.05) * 100, 5.0)
        _cue(st, "Search \"[your state] income tax rate\". Not sure? Keep 5%.")
    elif where in STATES and cfg.state_tax_rules(STATES[where])["confidence"] == "approx":
        _cue(st, "We use approximate figures for this state.")


def commit_state(st) -> None:
    if _val(st, "gs_state") in STATES:
        _ov(st)["STATE_CHOICE"] = STATES[_val(st, "gs_state")]
    if _val(st, "gs_state") == _STATE_FLAT_LABEL and _val(st, "gs_state_rate") is not None:
        _ov(st)["YOUR_MARGINAL_TAX_RATE"] = min(_num(_val(st, "gs_state_rate")), 15.0) / 100.0


def check_state(st) -> Optional[str]:
    return None if _val(st, "gs_state") else "Choose where you live to continue."


def draw_income(st) -> None:
    ov = _ov(st)
    c = state(st).get("checkup") or {}
    _money(st, "gs_salary", "Your yearly pay before taxes", ov.get("YOUR_BASE_SALARY"),
           c.get("salary") or None, hi=s2f.SALARY_MAX, step=1_000)
    _cue(st, "Gross pay: the salary on your offer letter, or one paycheck's gross amount times "
             "the number of paychecks in a year. Enter 0 if you're not working.",
         _from_checkup(st, "YOUR_BASE_SALARY"))
    _money(st, "gs_bonus", "Typical yearly bonus", ov.get("YOUR_BONUS_AMOUNT"), 0,
           hi=1_000_000, step=500)
    _cue(st, "Before taxes. Enter 0 if you don't get one.")
    if _partner(st):
        _money(st, "gs_partner_salary", "Your partner's yearly pay before taxes",
               ov.get("PARTNER_BASE_SALARY"), None, hi=s2f.SALARY_MAX, step=1_000)
        _cue(st, "Also before taxes. Enter 0 if they don't work for pay.")


def commit_income(st) -> None:
    ov = _ov(st)
    if _val(st, "gs_salary") is not None:
        ov["YOUR_BASE_SALARY"] = int(_val(st, "gs_salary"))
    if _val(st, "gs_bonus") is not None:
        ov["YOUR_BONUS_AMOUNT"] = int(_val(st, "gs_bonus"))
    if _partner(st) and _val(st, "gs_partner_salary") is not None:
        ov["PARTNER_BASE_SALARY"] = ov["PARTNER_SALARY"] = int(_val(st, "gs_partner_salary"))


def check_income(st) -> Optional[str]:
    if _val(st, "gs_salary") is None:
        return "Enter your yearly pay (0 if you're not working)."
    if _partner(st) and _val(st, "gs_partner_salary") is None:
        return "Enter your partner's yearly pay (0 if they don't work for pay)."
    return None


_YOUR_ACCOUNTS = [
    ("gs_401k", "YOUR_401K", "401(k) or 403(b)"),
    ("gs_roth", "YOUR_ROTH_IRA", "Roth IRA"),
    ("gs_trad", "YOUR_TRADITIONAL_IRA", "Traditional IRA"),
    ("gs_hsa_bal", "YOUR_HSA", "HSA (health savings account)"),
    ("gs_brk", "YOUR_BROKERAGE", "Regular investment account"),
    ("gs_cash", "YOUR_CASH", "Checking and savings"),
]
_PARTNER_ACCOUNTS = [
    ("gs_p401k", "PARTNER_401K", "Their 401(k) or 403(b)"),
    ("gs_proth", "PARTNER_ROTH_IRA", "Their Roth IRA"),
    ("gs_pbrk", "PARTNER_BROKERAGE", "Their investment account"),
    ("gs_pcash", "PARTNER_CASH", "Their checking and savings"),
]


def draw_saved(st) -> None:
    ov = _ov(st)
    _cue(st, "Check your bank, 401(k) and investing apps. Rounding to the nearest $1,000 is "
             "fine. Enter 0 for any account you don't have.".replace("$", "\\$"))
    cols = st.columns(2)
    for i, (key, ok, label) in enumerate(_YOUR_ACCOUNTS):
        with cols[i % 2]:
            first = ov.get(ok) if _from_checkup(st, ok) else 0
            _money(st, key, label, ov.get(ok), first, step=1_000)
            if _from_checkup(st, ok):
                _cue(st, "", True)
    if _partner(st):
        st.markdown("**Your partner**")
        cols = st.columns(2)
        for i, (key, ok, label) in enumerate(_PARTNER_ACCOUNTS):
            with cols[i % 2]:
                _money(st, key, label, ov.get(ok), 0, step=1_000)


def commit_saved(st) -> None:
    ov = _ov(st)
    for key, ok, _ in _YOUR_ACCOUNTS + (_PARTNER_ACCOUNTS if _partner(st) else []):
        if _val(st, key) is not None:
            ov[ok] = int(_val(st, key))


def draw_saving(st) -> None:
    ov = _ov(st)
    c = state(st).get("checkup") or {}
    salary = _num(ov.get("YOUR_BASE_SALARY"))
    pct_saved = 100.0 * _num(ov.get("YOUR_401K_CONTRIBUTION")) / salary if salary else 0.0
    _pct(st, "gs_401k_pct", "What % of your pay goes into your 401(k)?", pct_saved,
         c.get("pct_401k", 0.0))
    _cue(st, "It's on your pay stub or benefits site, often 3–10%. Enter 0 if you don't put "
             "anything in or don't have one.", _from_checkup(st, "YOUR_401K_CONTRIBUTION"))
    _pct(st, "gs_match", "Your employer matches up to what % of your pay?",
         _num(ov.get("YOUR_401K_MATCH_PCT")) * 100, _num(ov.get("YOUR_401K_MATCH_PCT")) * 100
         if _from_checkup(st, "YOUR_401K_MATCH_PCT") else 0.0)
    _cue(st, "The most your employer adds, as in \"we match up to 4%\". Enter 0 if there's "
             "no match.", _from_checkup(st, "YOUR_401K_MATCH_PCT"))
    hsa = _choice(st, "gs_hsa", "Is your health plan HSA-eligible?", ["No", "Yes"],
                  "Yes" if _num(ov.get("YOUR_HSA_CONTRIBUTION")) > 0 else "No",
                  "Yes" if c.get("hsa_eligible") else "No", horizontal=True)
    _cue(st, "Only high-deductible plans are. Your plan documents say so; if you're not sure, "
             "choose No.")
    if hsa == "Yes":
        _money(st, "gs_hsa_amt", "How much goes into your HSA each year?",
               ov.get("YOUR_HSA_CONTRIBUTION"),
               ov.get("YOUR_HSA_CONTRIBUTION") if _from_checkup(st, "YOUR_HSA_CONTRIBUTION") else 0,
               hi=s2f.CONTRIB_MAX)
        _cue(st, "Include anything your employer puts in.")
    _money(st, "gs_ira", "How much do you put into an IRA each year?",
           ov.get("YOUR_BACKDOOR_ROTH"),
           ov.get("YOUR_BACKDOOR_ROTH") if _from_checkup(st, "YOUR_BACKDOOR_ROTH") else 0,
           hi=s2f.CONTRIB_MAX)
    so_far = c.get("ira_so_far") or 0
    _cue(st, (f"Your check-up had {money_md(so_far)} so far this year; enter what you'll put in "
              "over a full year. " if so_far else "")
         + "Roth or traditional. Enter 0 if you don't have one.")
    if _partner(st):
        p_salary = _num(ov.get("PARTNER_BASE_SALARY"))
        p_pct = 100.0 * _num(ov.get("PARTNER_401K_CONTRIBUTION")) / p_salary if p_salary else 0.0
        _pct(st, "gs_p401k_pct", "What % of their pay goes into their 401(k)?", p_pct, 0.0)
    _choice(st, "gs_invest", "What should happen to the money you don't spend?", [KEEP, FILL],
            KEEP if ov.get("SAVINGS_MODE") == KEEP_AMOUNTS_MODE else FILL, KEEP)
    _cue(st, "Either way, every dollar you don't spend gets invested. Keeping your amounts shows "
             "your plan as it is today. Filling your 401(k) first can lower your taxes.")


def commit_saving(st) -> None:
    ov = _ov(st)
    age = int(_num(ov.get("YOUR_AGE"), 30))
    if _val(st, "gs_401k_pct") is not None:
        ov["YOUR_401K_CONTRIBUTION"] = s2f.contribution_401k(
            _num(ov.get("YOUR_BASE_SALARY")), _num(_val(st, "gs_401k_pct")), get_limit("401k", age))
    if _val(st, "gs_match") is not None:
        ov["YOUR_401K_MATCH_PCT"] = _num(_val(st, "gs_match")) / 100.0
    if _val(st, "gs_hsa") == "No":
        ov["YOUR_HSA_CONTRIBUTION"] = 0
    elif _val(st, "gs_hsa") == "Yes" and _val(st, "gs_hsa_amt") is not None:
        ov["YOUR_HSA_CONTRIBUTION"] = int(_val(st, "gs_hsa_amt"))
    if _val(st, "gs_ira") is not None:
        ov["YOUR_BACKDOOR_ROTH"] = int(_val(st, "gs_ira"))
    if _partner(st) and _val(st, "gs_p401k_pct") is not None:
        p_age = int(_num(ov.get("PARTNER_AGE"), 30))
        ov["PARTNER_401K_CONTRIBUTION"] = s2f.contribution_401k(
            _num(ov.get("PARTNER_BASE_SALARY")), _num(_val(st, "gs_p401k_pct")),
            get_limit("401k", p_age))
        ov["PARTNER_ROTH_CONTRIBUTION"] = 0
    if _val(st, "gs_invest") == KEEP:
        ov.update(SAVINGS_MODE=KEEP_AMOUNTS_MODE, YOUR_BROKERAGE_CONTRIBUTION=0,
                  PARTNER_BROKERAGE_CONTRIBUTION=0)
    elif _val(st, "gs_invest") == FILL:
        ov["SAVINGS_MODE"] = AUTO_ALLOCATE_MODE


def draw_home(st) -> None:
    ov = _ov(st)
    c = state(st).get("checkup")
    owns = _num(ov.get("HOME_VALUE")) > 0
    home = _choice(st, "gs_home", "Do you rent or own your home?", [RENT, OWN],
                   OWN if owns else RENT, None, horizontal=True)
    if c:
        _cue(st, f"Your check-up's needs ({money_md(c['needs'])} a month) include this payment; "
                 "it comes out of your other spending on the next step.")
    if home == RENT:
        _money(st, "gs_rent", "Monthly rent", ov.get("SPEND_RENT_MONTHLY") if not owns else None,
               None, hi=20_000, step=50)
        _cue(st, "What you pay each month, not counting utilities. Enter 0 if you don't pay rent.")
    elif home == OWN:
        _money(st, "gs_home_value", "What your home is worth", ov.get("HOME_VALUE") if owns else None,
               None, step=10_000)
        _cue(st, "A rough estimate of what it would sell for today. Zillow or Redfin can help.")
        _money(st, "gs_mortgage_balance", "What you still owe on the mortgage",
               ov.get("MORTGAGE_BALANCE") if owns else None, None, hi=5_000_000, step=10_000)
        _cue(st, "On your latest mortgage statement. Enter 0 if it's paid off.")
        _money(st, "gs_mortgage_monthly", "Monthly mortgage payment",
               ov.get("MORTGAGE_MONTHLY") if owns else None, None, hi=20_000, step=50)
        _cue(st, "The full payment, including property tax and insurance if they're part of it. "
                 "Enter 0 if it's paid off.")
        _whole(st, "gs_mortgage_years", "Years left on the mortgage",
               ov.get("MORTGAGE_YEARS_REMAINING") if owns else None, None, 0, 40)
        _cue(st, "Enter 0 if it's paid off.")


def _housing(st) -> float:
    if _val(st, "gs_home") == RENT:
        return _num(_val(st, "gs_rent"))
    if _val(st, "gs_home") == OWN:
        return _num(_val(st, "gs_mortgage_monthly"))
    return 0.0


def commit_home(st) -> None:
    ov = _ov(st)
    home = _val(st, "gs_home")
    if home == RENT and _val(st, "gs_rent") is not None:
        ov.update(HOME_VALUE=0, MORTGAGE_BALANCE=0, MORTGAGE_MONTHLY=0, MORTGAGE_YEARS_REMAINING=0,
                  SPEND_RENT_MONTHLY=int(_val(st, "gs_rent")))
    elif home == OWN:
        for key, ok in (("gs_home_value", "HOME_VALUE"), ("gs_mortgage_balance", "MORTGAGE_BALANCE"),
                        ("gs_mortgage_monthly", "MORTGAGE_MONTHLY"),
                        ("gs_mortgage_years", "MORTGAGE_YEARS_REMAINING")):
            if _val(st, key) is not None:
                ov[ok] = int(_val(st, key))
        ov["SPEND_RENT_MONTHLY"] = 0
    else:
        return
    # Check-up visitors: their needs (rent included) sit in Other until now.
    c = state(st).get("checkup")
    if c and "gs_spend_SPEND_OTHER_MONTHLY" not in state(st).get("seen", []):
        ov["SPEND_OTHER_MONTHLY"] = s2f.spending_split(
            {"needs_monthly": c["needs"], "wants_monthly": c["wants"]}, _housing(st))["SPEND_OTHER_MONTHLY"]


def check_home(st) -> Optional[str]:
    home = _val(st, "gs_home")
    if home is None:
        return "Choose rent or own to continue."
    if home == RENT and _val(st, "gs_rent") is None:
        return "Enter your monthly rent (0 if you don't pay rent)."
    if home == OWN and any(_val(st, k) is None for k in (
            "gs_home_value", "gs_mortgage_balance", "gs_mortgage_monthly", "gs_mortgage_years")):
        return "Fill in all four home questions (0 is fine for a paid-off mortgage)."
    return None


def _shown_categories(st):
    return [c for c in CATEGORIES if _partner(st) or not c.partner_only]


def draw_spending(st) -> None:
    ov = _ov(st)
    c = state(st).get("checkup")
    housing = _num(ov.get("MORTGAGE_MONTHLY")) or _num(ov.get("SPEND_RENT_MONTHLY"))
    if c:
        rest = max(0.0, c["needs"] - housing)
        _cue(st, f"From your check-up: {money_md(c['needs'])} of needs and {money_md(c['wants'])} "
                 f"of wants a month. Housing ({money_md(housing)}) was the previous step, so the "
                 f"other {money_md(rest)} of needs is in Other below"
                 + (f", including {money_md(c['debt_min'])} of minimum debt payments"
                    if c.get("debt_min") else "")
                 + ". Move parts of it into the right boxes if you can, especially health "
                   "insurance. The total is what matters most."
                 + (" Leave the debt payments in Other, and lower it once a debt is paid off."
                    if c.get("debt_min") else ""))
    else:
        _cue(st, "About how much do you spend each month? Your bank or card app's spending "
                 "summary helps. Rough numbers are fine. Leave out housing (the previous step) and "
                 "money you save. Each box starts at a typical amount: change any that don't fit.")
    cats = _shown_categories(st)
    for row in range(0, len(cats), 2):      # one row of columns per pair, so the boxes line up
        for col, cat in zip(st.columns(2), cats[row:row + 2]):
            with col:
                _money(st, "gs_spend_" + cat.key, cat.label, ov.get(cat.key),
                       ov.get(cat.key, cat.default), hi=cat.max_value, step=cat.step)
                _cue(st, _SPEND_HINTS.get(cat.key, ""))
    total = sum(_num(_val(st, "gs_spend_" + cat.key)) for cat in cats)
    line = f"**{money_md(total)} a month**, plus {money_md(housing)} for housing."
    if c:
        target = max(0.0, c["needs"] + c["wants"] - housing)
        gap = total - (_num(_val(st, "gs_spend_PARTNER_OTHER_MONTHLY")) if _partner(st) else 0) - target
        if abs(gap) < 1:
            line += " ✓ Matches your check-up."
        else:
            line += (f" That's {money_md(abs(gap))} {'more' if gap > 0 else 'less'} than your "
                     "check-up; fine if that's more accurate.")
    st.markdown(line)


def commit_spending(st) -> None:
    ov = _ov(st)
    for cat in _shown_categories(st):
        v = _val(st, "gs_spend_" + cat.key)
        if v is not None:
            ov[cat.key] = int(v)
            if cat.mirror:
                ov[cat.mirror] = int(v)


def draw_retire(st) -> None:
    ov = _ov(st)
    age = int(_num(ov.get("YOUR_AGE"), 30))
    lo = max(25, min(age, 75))
    target = int(_num(ov.get("TARGET_RETIREMENT_AGE"), 60))
    _seed(st, "gs_target", max(lo, min(target, 75)), max(lo, min(target, 75)))
    if st.session_state["gs_target"] < lo:
        st.session_state["gs_target"] = lo
    st.slider("At what age would you like to retire?", min_value=lo, max_value=75, step=1,
              key="gs_target")
    _cue(st, "A guess is fine. Your results show the earliest age that works, and you can "
             "adjust from there.")
    ss = _choice(st, "gs_ss", "Count on Social Security?", [SS_YES, SS_NO],
                 SS_YES if ov.get("INCLUDE_SOCIAL_SECURITY", True) else SS_NO, SS_YES,
                 horizontal=True)
    _cue(st, "Choose No for a cautious plan that doesn't rely on it.")
    if ss == SS_YES:
        _money(st, "gs_ss_amt", "Your estimated monthly benefit at full retirement age",
               ov.get("YOUR_SS_MONTHLY_FRA"), ov.get("YOUR_SS_MONTHLY_FRA", 2_000), hi=5_000, step=50)
        _cue(st, "Your estimate is at ssa.gov/myaccount (signing up takes a few minutes). "
                 "Not sure? Keep this typical amount.")
        if _partner(st):
            _money(st, "gs_pss_amt", "Your partner's estimated monthly benefit",
                   ov.get("PARTNER_SS_MONTHLY_FRA"), ov.get("PARTNER_SS_MONTHLY_FRA", 1_800),
                   hi=5_000, step=50)


def commit_retire(st) -> None:
    ov = _ov(st)
    if _val(st, "gs_target") is not None:
        ov["TARGET_RETIREMENT_AGE"] = int(_val(st, "gs_target"))
    if _val(st, "gs_ss") is not None:
        ov["INCLUDE_SOCIAL_SECURITY"] = _val(st, "gs_ss") == SS_YES
    if _val(st, "gs_ss_amt") is not None:
        ov["YOUR_SS_MONTHLY_FRA"] = int(_val(st, "gs_ss_amt"))
    if _partner(st) and _val(st, "gs_pss_amt") is not None:
        ov["PARTNER_SS_MONTHLY_FRA"] = int(_val(st, "gs_pss_amt"))


def review_lines(ov: Dict[str, Any]) -> List[str]:
    """One plain line per topic, for the last step."""
    partner = int(_num(ov.get("PARTNER_AGE"))) > 0
    kids = _kids_saved(ov)
    n_born, n_planned = len(kids["born"]), kids["planned"]
    kids_line = ("no kids." if not (n_born or n_planned) else
                 ", ".join(filter(None, [
                     f"{n_born} {'child' if n_born == 1 else 'children'}" if n_born else "",
                     f"{n_planned} planned" if n_planned else ""])) + ".")
    who = "just you" if not partner else f"you and your partner ({int(_num(ov.get('PARTNER_AGE')))})"
    pay = _num(ov.get("YOUR_BASE_SALARY")) + _num(ov.get("YOUR_BONUS_AMOUNT"))
    if partner:
        pay += _num(ov.get("PARTNER_BASE_SALARY"))
    saved = sum(_num(ov.get(k)) for _, k, _ in _YOUR_ACCOUNTS
                + (_PARTNER_ACCOUNTS if partner else []))
    housing = _num(ov.get("MORTGAGE_MONTHLY")) or _num(ov.get("SPEND_RENT_MONTHLY"))
    spend = sum(_num(ov.get(c.key)) for c in CATEGORIES if partner or not c.partner_only)
    yearly = sum(_num(ov.get(k)) for k in ("YOUR_401K_CONTRIBUTION", "YOUR_HSA_CONTRIBUTION",
                                           "YOUR_BACKDOOR_ROTH"))
    ss = (f"Social Security {money_md(_num(ov.get('YOUR_SS_MONTHLY_FRA')))}/month"
          if ov.get("INCLUDE_SOCIAL_SECURITY", True) else "no Social Security")
    return [
        f"**You:** {int(_num(ov.get('YOUR_AGE')))}, planning for {who}; {kids_line}",
        f"**Income:** {money_md(pay)} a year before taxes.",
        f"**Saved so far:** {money_md(saved)}.",
        f"**Saving:** {money_md(yearly)} a year into your 401(k), HSA and IRA"
        + (", plus your employer's match" if _num(ov.get("YOUR_401K_MATCH_PCT")) > 0 else "")
        + "; the rest of what you don't spend is invested.",
        f"**Spending:** {money_md(spend + housing)} a month, including "
        f"{money_md(housing)} for housing.",
        f"**Retirement:** at {int(_num(ov.get('TARGET_RETIREMENT_AGE'), 60))}, {ss}.",
    ]


def draw_review(st) -> None:
    st.markdown("\n".join(f"- {line}" for line in review_lines(_ov(st))))
    _cue(st, "Use Back to change an answer. Later, everything is in the side panel "
             "(on a phone, tap the arrow at the top left).")


def _nothing(st) -> Optional[str]:
    return None


class Step(NamedTuple):
    title: str
    intro: str
    draw: Callable
    commit: Callable
    check: Callable


STEPS: List[Step] = [
    Step("About you", "A few basics. Rough answers are fine, and you can change anything later.",
         draw_you, commit_you, check_you),
    Step("Kids", "", draw_kids, commit_kids, check_kids),
    Step("Where you live", "", draw_state, commit_state, check_state),
    Step("Your income", "", draw_income, commit_income, check_income),
    Step("What you've saved so far", "", draw_saved, commit_saved, _nothing),
    Step("Saving each year", "", draw_saving, commit_saving, _nothing),
    Step("Your home", "", draw_home, commit_home, check_home),
    Step("Monthly spending", "", draw_spending, commit_spending, _nothing),
    Step("Retirement", "", draw_retire, commit_retire, _nothing),
    Step("All set", "Here's what the planner will use.", draw_review, lambda st: None, _nothing),
]


# ---------------------------------------------------------------------------
# Navigation and page
# ---------------------------------------------------------------------------

def _sync_planner(st) -> None:
    """Hand over to the planner: its side-panel widgets take the answers, and
    the first simulation runs on them rather than the sample household."""
    try:
        from utils.widget_sync import sync_widgets_from_overrides
    except ImportError:  # pragma: no cover
        from ui.utils.widget_sync import sync_widgets_from_overrides  # type: ignore
    sync_widgets_from_overrides(st)
    st.session_state["profile"] = "Custom (keep current values)"   # theirs, not the sample's
    st.session_state["si_comp_customized"] = False   # pay table follows the new salary
    st.session_state["results"] = None
    st.session_state.pop("_autorun_done", None)


def _go(st, delta: int) -> None:
    s = st.session_state[STATE]
    step = STEPS[s["step"]]
    step.commit(st)
    if delta > 0:
        missing = step.check(st)
        if missing:
            s["error"] = missing
            return
    s["error"] = None
    if s["step"] + delta >= len(STEPS):
        s["status"] = "done"
        _sync_planner(st)
        return
    s["step"] = max(0, s["step"] + delta)


def _skip(st) -> None:
    s = st.session_state[STATE]
    STEPS[s["step"]].commit(st)
    s.update(status="skipped", error=None)
    _sync_planner(st)


def render(st) -> None:
    s = st.session_state[STATE]
    s.setdefault("seen", [])
    i = s["step"] = min(max(int(s.get("step", 0)), 0), len(STEPS) - 1)
    step = STEPS[i]
    with st.container(key="mc-setup"):
        # Plain HTML, not st.progress: a progress bar on the page is what the
        # animation layer reads as "a simulation is running" (its overlay).
        pct = round(100 * (i + 1) / len(STEPS))
        st.markdown(f'<div class="mc-setup-count">Step {i + 1} of {len(STEPS)}</div>'
                    f'<div class="mc-setup-bar" role="progressbar" aria-valuenow="{i + 1}" '
                    f'aria-valuemin="1" aria-valuemax="{len(STEPS)}"><span style="width:{pct}%">'
                    '</span></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="mc-section">{step.title}</div>', unsafe_allow_html=True)
        if step.intro:
            st.markdown(f'<div class="mc-setup-intro">{step.intro}</div>', unsafe_allow_html=True)
        step.draw(st)
        step.commit(st)
        if s.get("error"):
            st.warning(s["error"], icon=":material/info:")
        with st.container(key="mc-setup-nav", horizontal=True, vertical_alignment="center"):
            if i > 0:
                st.button("Back", key="gs_back", on_click=_go, args=(st, -1),
                          icon=":material/arrow_back:")
            last = i == len(STEPS) - 1
            if not last:
                st.button("Skip for now", key="gs_skip", on_click=_skip, args=(st,),
                          type="tertiary",
                          help="Go straight to the planner. Unanswered questions keep sample "
                               "numbers until you finish setting up.")
            st.button("Show my results" if last else "Next", key="gs_next", on_click=_go,
                      args=(st, 1), type="primary",
                      icon=":material/check:" if last else ":material/arrow_forward:")


def render_banner(st) -> None:
    """In the planner after a skip: a way back into the walkthrough."""
    with st.container(border=True, key="mc-setup-banner"):
        st.markdown("**Finish setting up.** Some answers still use sample numbers, so your "
                    "results may not fit you yet.")
        st.button("Continue setup", key="gs_resume", on_click=resume, args=(st,), type="primary",
                  icon=":material/arrow_forward:")
