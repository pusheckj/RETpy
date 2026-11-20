"""Ways to reach your goal: the levers behind the results headline.

After the main run, ``plan_goal_levers`` tests a few one-input changes to the
plan -- retire later, spend less in retirement, a partner who works longer, and
one year later plus a smaller spending cut -- each as its own seeded Monte
Carlo at the target age (``sim_runner.Plan``, so the server, its fork pool or
the visitor's browser can run it). Every scenario replays the main run's market
paths (``mc_jobs.PATH_SEED``), so a lever's change in success comes from the
lever, not from noise; at the main run's simulation count, "no change" gives
exactly the headline success rate.

A plan that already clears 95% gets the "You have room" variant instead: the
earliest age that still meets the success target, and the largest spending
raise (+5/+10/+15%) that still meets it.

Each lever is a set of ordinary ``user_overrides`` changes (``changes``), so
"Keep this change" writes exactly what was simulated. Also here: the success
band and the guardrail cushion the hero card shows (``success_band``,
``guardrail_cushion``).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from utils import sim_runner as sr
    from utils.config_builder import build_config_overrides
    from utils.age_limits import TARGET_MAX
except ImportError:  # pragma: no cover
    from ui.utils import sim_runner as sr  # type: ignore
    from ui.utils.config_builder import build_config_overrides  # type: ignore
    from ui.utils.age_limits import TARGET_MAX  # type: ignore

from retirement_sim import config as cfg
from retirement_sim import mc_jobs

#: Where the results go in session state (app._queue_extras stores them there).
RESULT_KEY = "goal_levers_result"
#: The goal steps above the user's own target, and where "You have room" starts.
GOAL_STEPS = (0.90, 0.95)
ROOM_AT = 0.95
SPEND_CUTS = (0.05, 0.10, 0.15, 0.20, 0.25)
SPEND_RAISES = (0.05, 0.10, 0.15)
MAX_LATER_YEARS = 6
MAX_PARTNER_YEARS = 5
MAX_EARLIER_TRIES = 4
#: A "retire later" age just short of the goal is still shown when this close.
CLOSE_TO_GOAL = 0.05
MAX_ROWS = 5
#: The lowest spending share the Retirement section's slider takes (50%).
MIN_SPEND_PCT = 0.50
MAX_SPEND_PCT = 1.50

PCT_MODE = "% of today's expenses"
ABS_MODE = "Absolute amount ($/yr)"

_CACHE: Dict[tuple, Any] = {}
sr._SMALL_CACHES.append(_CACHE)        # cleared with the others by sr.clear_cache()
_CUSHION_CACHE: Dict[tuple, Any] = {}
sr._SMALL_CACHES.append(_CUSHION_CACHE)

# Success bands for the hero card: (lowest rate, name). Highest first.
BANDS = ((0.90, "Strong"), (0.80, "Good"), (0.65, "Fair"), (0.0, "Needs attention"))


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

def goal_for(success: float, target: float) -> Optional[float]:
    """The success rate the card aims for: your own target while you are below
    it, else the next step up (90%, then 95%). None from 95% up ("You have room")."""
    success, target = float(success), float(target)
    if success < target:
        return target
    for step in GOAL_STEPS:
        if success < step:
            return step
    return None


def lever_sims(n_sims: int) -> int:
    """Runs per lever: the main run's count (so "no change" equals the headline),
    capped at 2,000 like the other sweeps so a 10k-run setting stays responsive."""
    return max(100, min(int(n_sims), 2000))


def success_band(rate: float) -> str:
    """"Needs attention" (<65%), "Fair" (65-80%), "Good" (80-90%), "Strong" (90%+)."""
    rate = float(rate or 0.0)
    return next(name for lo, name in BANDS if rate >= lo - 1e-9)


def monthly_text(dollars_per_year: float) -> str:
    """'$1,800' for a yearly amount: per month, rounded to $50 (to $100 from $1,000)."""
    m = abs(float(dollars_per_year)) / 12.0
    step = 100 if m >= 1000 else 50
    m = max(step, round(m / step) * step)
    return f"${m:,.0f}"


def _more_years(n: int, word: str) -> str:
    """'3 more working years' / '1 fewer working year'."""
    return f"{n} {word} working year" + ("" if n == 1 else "s")


def _value(overrides: dict, key: str, default=None):
    v = overrides.get(key)
    return getattr(cfg, key, default) if v is None else v


def spend_changes(overrides: dict, factor: float, living_today: float) -> Dict[str, Any]:
    """Overrides that set retirement spending to ``factor`` x the plan's own, in
    the plan's own terms: an absolute amount stays absolute; otherwise a share of
    today's spending (whole percents). Below the slider's 50% it becomes an
    absolute amount (``living_today`` is today's non-housing living base)."""
    mode = str(_value(overrides, "RETIREMENT_SPENDING_MODE", "Same as today's expenses"))
    if mode.startswith("Absolute"):
        amount = float(_value(overrides, "RETIREMENT_SPENDING_ABSOLUTE", 0) or 0)
        return {"RETIREMENT_SPENDING_ABSOLUTE": int(round(amount * factor / 100.0) * 100)}
    share = float(_value(overrides, "RETIREMENT_SPENDING_PCT", 0.80) or 0.80) if mode.startswith("%") else 1.0
    new = round(share * factor, 2)
    if MIN_SPEND_PCT <= new <= MAX_SPEND_PCT:
        return {"RETIREMENT_SPENDING_MODE": PCT_MODE, "RETIREMENT_SPENDING_PCT": new}
    return {"RETIREMENT_SPENDING_MODE": ABS_MODE,
            "RETIREMENT_SPENDING_ABSOLUTE": int(round(living_today * share * factor / 100.0) * 100)}


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------

def _plan_context(overrides: dict) -> dict:
    """What the scenarios are built from (cfg holds the plan)."""
    has_partner = bool(cfg.has_partner())
    your_age = int(cfg.YOUR_AGE)
    gap = your_age - int(cfg.PARTNER_AGE) if has_partner else 0
    return {
        "your_age": your_age,
        "has_partner": has_partner,
        "partner_age": int(cfg.PARTNER_AGE) if has_partner else None,
        "gap": gap,
        "plan_end": int(cfg.plan_end_age()),
        "partner_retire": getattr(cfg, "PARTNER_RETIREMENT_AGE", None),
        "living_today": float(getattr(cfg, "BASE_RETIREMENT_EXPENSES_NO_MORTGAGE", 0.0) or 0.0),
        "living": float(cfg.retirement_living_base()),
    }


def _scenarios(overrides: dict, ctx: dict, t: int, goal: Optional[float], target: float,
               earliest: Optional[int]) -> List[dict]:
    """Each: {kind, step, age, changes}. ``age`` is the retirement age simulated."""
    out: List[dict] = []
    working = t > ctx["your_age"]                  # not retired yet: the age can move
    last_age = min(TARGET_MAX, ctx["plan_end"] - 1)

    def add(kind, step, age, changes):
        out.append({"kind": kind, "step": step, "age": int(age), "changes": changes})

    def spend(factor):
        return spend_changes(overrides, factor, ctx["living_today"])

    if goal is None:                               # "You have room"
        if working and earliest is not None and earliest < t:
            first = max(int(earliest), ctx["your_age"])
            for a in range(first, min(first + MAX_EARLIER_TRIES, t)):
                add("earlier", t - a, a, {"TARGET_RETIREMENT_AGE": a})
        for r in SPEND_RAISES:
            add("more", r, t, spend(1.0 + r))
        return out

    if working:
        for a in range(t + 1, min(t + MAX_LATER_YEARS, last_age) + 1):
            add("later", a - t, a, {"TARGET_RETIREMENT_AGE": a})
    for c in SPEND_CUTS:
        add("spend", c, t, spend(1.0 - c))
    if ctx["has_partner"]:
        p0 = ctx["partner_retire"]
        p0 = int(p0) if p0 is not None else t - ctx["gap"]
        p_last = min(TARGET_MAX, ctx["plan_end"] - ctx["gap"] - 1)
        if p0 > ctx["partner_age"]:                # still working: can work longer
            for e in range(1, MAX_PARTNER_YEARS + 1):
                if p0 + e <= p_last:
                    add("partner", e, t, {"PARTNER_RETIREMENT_AGE": p0 + e, "_from": p0})
    if working and t + 1 <= last_age:
        for c in SPEND_CUTS:
            add("combo", c, t + 1, {"TARGET_RETIREMENT_AGE": t + 1, **spend(1.0 - c)})
    return out


def plan_goal_levers(user_overrides: dict, n_simulations: int, target_retirement_age: int,
                     main_result: dict) -> "sr.Plan":
    """The levers as one "scan" call per scenario (no early stop), each under
    its own config patch. ``main_result`` is the run the card explains (its
    success rate, success target and earliest age)."""
    t = int(target_retirement_age)
    n = lever_sims(n_simulations)
    key = ("v1", sr._hashable(user_overrides), int(n_simulations), t)
    hit = sr._small_cache_lookup(_CACHE, "goal_levers", key)
    if hit is not None:
        return sr.Plan("levers", key, user_overrides, result=hit)
    store = sr._small_cache_writer(_CACHE, "goal_levers", key)
    primary = (main_result or {}).get("primary_result", {}) or {}
    base = float(primary.get("success_rate", 0.0) or 0.0)
    target = float(((main_result or {}).get("config_snapshot", {}) or {}).get(
        "TARGET_SUCCESS_RATE", getattr(cfg, "TARGET_SUCCESS_RATE", 0.80)))
    earliest = (main_result or {}).get("earliest_retirement_age")
    goal = goal_for(base, target)

    original = sr._apply_overrides(build_config_overrides(user_overrides))
    try:
        ctx = _plan_context(user_overrides)
        snap = mc_jobs.snapshot()
    finally:
        sr._restore_overrides(original)
    scenarios = _scenarios(user_overrides, ctx, t, goal, target, earliest)
    head = {"mode": "room" if goal is None else "reach", "goal": goal, "target": target,
            "base": base, "target_age": t, "n": n, "rows": []}
    if not scenarios:
        store(head)
        return sr.Plan("levers", key, user_overrides, result=head)

    patches, calls = [], []
    for i, sc in enumerate(scenarios):
        changes = {k: v for k, v in sc["changes"].items() if not k.startswith("_")}
        o = sr._apply_overrides(build_config_overrides({**user_overrides, **changes}))
        try:
            patches.append(mc_jobs.diff(snap, mc_jobs.snapshot()))
            sc["living"] = float(cfg.retirement_living_base())
        finally:
            sr._restore_overrides(o)
        # min_n = n: every run counts (no early stop), on the main run's paths.
        calls.append(["scan", i, [sc["age"], n, mc_jobs.PATH_SEED, goal or target, n]])
    job = {"base": snap, "patches": patches, "calls": calls}

    def finish(results: List[Any]) -> Dict[str, Any]:
        for sc, r in zip(scenarios, results):
            sc["value"] = (int(r["successes"]) / int(r["n"])) if r.get("n") else 0.0
        rows = (_room_rows if goal is None else _reach_rows)(scenarios, ctx, t, base, goal, target)
        return {**head, "rows": rows}

    return sr.Plan("levers", key, user_overrides, job, finish, store=store)


def run_goal_levers(user_overrides: dict, n_simulations: int, target_retirement_age: int,
                    main_result: dict) -> Dict[str, Any]:
    """The whole lever sweep on the server (tests, tools)."""
    return sr.execute_plan(plan_goal_levers(user_overrides, n_simulations,
                                            target_retirement_age, main_result))


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

def _row(sc: dict, label: str, sub: str, hit: bool) -> dict:
    return {"id": f"{sc['kind']}-{sc['step']}", "kind": sc["kind"], "label": label, "sub": sub,
            "value": float(sc["value"]), "hit": bool(hit), "age": sc["age"],
            "changes": {k: v for k, v in sc["changes"].items() if not k.startswith("_")}}


def _money_sub(sc: dict, ctx: dict, word: str) -> str:
    return f"about {monthly_text(ctx['living'] - sc['living'])}/mo {word}"


def _reach_rows(scenarios, ctx, t, base, goal, target) -> List[dict]:
    by = {}
    for sc in scenarios:
        by.setdefault(sc["kind"], []).append(sc)

    def pick(kind):
        items = by.get(kind, [])
        return next((s for s in items if s["value"] >= goal), items[-1] if items else None)

    groups: List[List[dict]] = []          # a "just short" age stays under its lever
    later = by.get("later", [])
    best = pick("later")
    if best is not None:
        def later_row(s):
            return _row(s, f"Retire at {s['age']} instead of {t}",
                        f"{_more_years(s['age'] - t, 'more')}", s["value"] >= goal)
        group = [later_row(best)]
        before = next((s for s in later if s["age"] == best["age"] - 1), None)
        if best["value"] >= goal and before is not None and before["value"] >= goal - CLOSE_TO_GOAL:
            group.append(later_row(before))
        groups.append(group)
    s = pick("spend")
    if s is not None:
        groups.append([_row(s, f"Spend {s['step']:.0%} less in retirement",
                            _money_sub(s, ctx, "less"), s["value"] >= goal)])
    one_later = next((x for x in later if x["age"] == t + 1), None)
    if one_later is None or one_later["value"] < goal:
        s = pick("combo")
        if s is not None:
            groups.append([_row(s, f"Retire at {t + 1} and spend {s['step']:.0%} less",
                                f"1 more year + {_money_sub(s, ctx, 'less')}", s["value"] >= goal)])
    s = pick("partner")
    if s is not None:
        p0 = s["changes"]["_from"]
        groups.append([_row(s, f"Your partner works to {p0 + s['step']} instead of {p0}",
                            f"you still retire at {t}", s["value"] >= goal)])
    # Honest values only: a lever that doesn't beat today's plan isn't a way to reach it.
    groups = [[r for r in g if r["value"] > base] for g in groups]
    groups = [g for g in groups if g]
    # Levers that reach the goal first (in the order above), then the best of the rest.
    hits = [g for g in groups if g[0]["hit"]]
    rest = sorted((g for g in groups if not g[0]["hit"]), key=lambda g: -g[0]["value"])
    return [r for g in hits + rest for r in g][:MAX_ROWS]


def _room_rows(scenarios, ctx, t, base, goal, target) -> List[dict]:
    rows: List[dict] = []
    earlier = next((s for s in sorted((s for s in scenarios if s["kind"] == "earlier"),
                                      key=lambda s: s["age"]) if s["value"] >= target), None)
    if earlier is not None:
        rows.append(_row(earlier, f"Retire at {earlier['age']} instead of {t}",
                         f"{_more_years(t - earlier['age'], 'fewer')}", True))
    more = [s for s in scenarios if s["kind"] == "more" and s["value"] >= target]
    if more:
        s = max(more, key=lambda s: s["step"])
        rows.append(_row(s, f"Spend {s['step']:.0%} more in retirement",
                         f"about {monthly_text(s['living'] - ctx['living'])}/mo more", True))
    return rows


# ---------------------------------------------------------------------------
# The guardrail cushion (hero card)
# ---------------------------------------------------------------------------

def guardrail_cushion(user_overrides: dict, retirement_age: int) -> Optional[dict]:
    """The engine's spending guardrail as plain numbers, for the hero card.

    ``drop``: how far (a fraction) the portfolio may fall below its value at
    retirement before the rule acts (1 - floor_trigger). ``trim_year``: the
    yearly cut it then makes, in today's dollars: floor_reduction x the
    discretionary share of retirement spending, housing left out when the
    engine leaves it out (MODEL_GUARDRAILS_EXCLUDE_HOUSING). ``enabled`` False
    when dynamic spending is off. None if the plan can't be read."""
    try:
        key = (sr._hashable(user_overrides), int(retirement_age))
    except Exception:
        return None
    if key in _CUSHION_CACHE:
        return _CUSHION_CACHE[key]
    try:
        original = sr._apply_overrides(build_config_overrides(user_overrides))
    except Exception:
        return None
    try:
        age = max(int(retirement_age), int(cfg.YOUR_AGE))
        g = dict(getattr(cfg, "SPENDING_GUARDRAILS", {}) or {})
        core = float(cfg.calculate_annual_expenses(age, 1.0, 1.0, retirement=True,
                                                   retirement_age=age))
        housing = float(cfg.housing_annual(age)) if getattr(
            cfg, "MODEL_GUARDRAILS_EXCLUDE_HOUSING", False) else 0.0
        flexible = max(0.0, core - min(core, housing)) * float(cfg.DISCRETIONARY_EXPENSE_RATIO)
        out = {
            "enabled": bool(getattr(cfg, "DYNAMIC_SPENDING_ENABLED", False)),
            "drop": 1.0 - float(g.get("floor_trigger", 0.70)),
            "cut": float(g.get("floor_reduction", 0.15)),
            "trim_year": float(g.get("floor_reduction", 0.15)) * flexible,
        }
    except Exception:
        out = None
    finally:
        sr._restore_overrides(original)
    sr._small_cache_insert(_CUSHION_CACHE, key, out)
    return out
