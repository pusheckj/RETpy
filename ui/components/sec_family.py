"""Section: Family — your children: when they arrive, what they cost, college.

The rows write ``CHILDREN``. Their widget keys all start with "se_kid" and are
filled and cleared as a family by ``utils/widget_sync`` (``_sync_children``).
"""
from __future__ import annotations

from typing import Optional, Tuple

try:
    from utils.section_icon import section_expander
except ImportError:  # pragma: no cover
    from ui.utils.section_icon import section_expander  # type: ignore

try:
    from utils.coerce import safe_int, ensure_default
    from utils.formatting import money_md
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, ensure_default  # type: ignore
    from ui.utils.formatting import money_md  # type: ignore

try:
    from utils.overrides import set_override
    from utils.derived import children_at_home_now, child_monthly_now
    from utils import childcare_cost
    from components import budget_area
except ImportError:  # pragma: no cover
    from ui.utils.overrides import set_override  # type: ignore
    from ui.utils.derived import children_at_home_now, child_monthly_now  # type: ignore
    from ui.utils import childcare_cost  # type: ignore
    from ui.components import budget_area  # type: ignore

from retirement_sim import config as cfg

# Children: one row per child, up to MAX_CHILDREN. Every row widget's key starts
# with "se_kid" (utils/widget_sync fills and clears them as a family).
MAX_CHILDREN = 6
_NEW_CHILD_COST = (2_100, 1_400)   # a first child, and each one after (the defaults)


def _clamped(v, lo, hi):
    return max(lo, min(hi, safe_int(v, lo)))


def _kid_number(st, key, label, seed, lo, hi, step, help_text=None) -> int:
    ensure_default(st, key, _clamped(seed, lo, hi))
    return safe_int(st.number_input(label, min_value=lo, max_value=hi, step=step, key=key,
                                    help=help_text))


def _new_child(earlier: list) -> dict:
    """A row added by raising the number of children: born 3 years after the
    previous child (or in a year), at the default cost."""
    yub = earlier[-1]["years_until_birth"] + 3 if earlier else 1
    return {**cfg.CHILD_DEFAULTS, "years_until_birth": max(1, yub),
            "monthly_cost": _NEW_CHILD_COST[1 if earlier else 0]}


def _years_left(years_until_birth: int) -> bool:
    """Whether a child still has childcare years ahead: planned, or under CHILDCARE_END_AGE now."""
    return years_until_birth > 0 or -years_until_birth < cfg.CHILDCARE_END_AGE


def _age_now(years_until_birth: int) -> int:
    """A born child's age today, or 0 for a child not yet born."""
    return max(0, -years_until_birth)


def move_childcare(old_cost: int, old_care: int, new_care: int, leaves_home_age: int,
                   age: Optional[int] = None) -> Tuple[int, int]:
    """(monthly cost, childcare a month) once childcare moves from ``old_care`` to ``new_care``.

    The plan charges the monthly cost for the years still at home and childcare for the
    childcare years still ahead. For a child of ``age`` (None or 0: planned or newborn) those
    are ``leaves - age`` and ``CHILDCARE_END_AGE - age``, so the same future money moves when the
    cost falls by the childcare change times the second over the first. The cost never goes
    below zero: past that point the childcare amount is capped at what the cost can give up."""
    a = max(0, age or 0)
    care_years = max(0, cfg.CHILDCARE_END_AGE - a)
    home_years = max(1, leaves_home_age - a)
    if care_years == 0:
        return old_cost, old_care
    shift = (new_care - old_care) * care_years / home_years
    if old_cost - round(shift) < 0:                   # more than the cost has to give
        return 0, old_care + int(old_cost * home_years / care_years)
    return old_cost - round(shift), new_care


def _use_childcare(st, p: str, typical: int, age: int) -> None:
    """Button callback: childcare takes the typical figure and the monthly cost gives up the
    same money, spread over the years still at home. Says so in a caption."""
    ss = st.session_state
    old_cost, old_care = safe_int(ss.get(p + "cost"), 0), safe_int(ss.get(p + "care"), 0)
    new_cost, new_care = move_childcare(old_cost, old_care, typical,
                                        safe_int(ss.get(p + "leaves"), 18), age)
    ss[p + "care"], ss[p + "cost"] = new_care, new_cost
    if new_care < typical:
        what = (f"Childcare is set to {money_md(new_care)}, below the typical {money_md(typical)}, "
                f"because the monthly cost cannot go below {money_md(0)}.")
    else:
        if new_cost < old_cost:
            how = f"lowered from {money_md(old_cost)} to {money_md(new_cost)}"
        elif new_cost > old_cost:
            how = f"raised from {money_md(old_cost)} to {money_md(new_cost)}"
        else:
            how = f"stays at {money_md(new_cost)}"
        what = f"Monthly cost {how}. The childcare part now sits in its own box."
    ss[p + "note"] = (what, new_care)


def _live_years_until_birth(st, i: int, kid: dict) -> int:
    """Child ``i``'s years until birth as the row's widgets hold it now (not last run's)."""
    ss, p = st.session_state, f"se_kid{i}_"
    yub = int(kid["years_until_birth"])
    if ss.get(p + "born", yub <= 0):
        age = ss.get(p + "age")
        return -safe_int(age, 0) if age is not None else (yub if yub <= 0 else 0)
    n = ss.get(p + "in")
    return safe_int(n, 1) if n is not None else (yub if yub > 0 else 1)


def _typical_monthly(st, age: int) -> int:
    """Typical childcare a month for a child of ``age`` in the plan's place (0: none left)."""
    ov = st.session_state.get("user_overrides", {}) or {}
    est, _ = childcare_cost.for_household({**ov, "CHILDREN": [{}]}, child_age=age)
    return round(est.per_child / 12)


def _child_row(st, i: int, kid: dict) -> dict:
    """One child's inputs; returns the child's CHILDREN entry."""
    p = f"se_kid{i}_"
    yub = int(kid["years_until_birth"])
    st.markdown(f"**Child {i + 1}**")
    ensure_default(st, p + "born", yub <= 0)
    born = st.toggle("Already born", key=p + "born")
    c1, c2 = st.columns(2, vertical_alignment="bottom")
    with c1:
        if born:
            yub = -_kid_number(st, p + "age", "Age today", -yub if yub <= 0 else 0, 0, 30, 1)
        else:
            yub = _kid_number(st, p + "in", "Born in (years)", yub if yub > 0 else 1, 1, 30, 1)
    care_key = p + "care"
    saved_care = safe_int(kid["childcare_monthly"], 0)
    shown_care = safe_int(st.session_state.get(care_key, saved_care), 0)
    left = _years_left(yub)
    has_box = left or shown_care > 0               # an amount past the childcare years can be cleared
    with c2:
        help_cost = "Childcare, food, clothes and activities while they live with you, in today's dollars."
        if has_box:
            help_cost = ("Food, clothes and activities while they live with you, in today's dollars. "
                         "Childcare for the first five years is in the box below." if shown_care > 0 else
                         help_cost + " Use typical below moves the childcare part into its own box "
                         "and lowers this to match.")
        cost = _kid_number(st, p + "cost", "Monthly cost ($)", kid["monthly_cost"], 0, 10_000, 100,
                           help_cost)
    care = saved_care
    if has_box:
        c5, c6 = st.columns(2, vertical_alignment="bottom")
        with c5:
            care = _kid_number(st, care_key, "Childcare until age 5 ($/mo)", saved_care,
                               0, 10_000, 50,
                               "Paid childcare in the first five years, in today's dollars. It is "
                               "on top of the monthly cost above.")
        typical = _typical_monthly(st, _age_now(yub)) if left else 0
        with c6:
            if typical > 0:
                st.button(f"Use typical {money_md(typical)}/mo", key=p + "use_care",
                          on_click=_use_childcare, args=(st, p, typical, _age_now(yub)),
                          disabled=care == typical,
                          help="Moves childcare into this box at the typical amount. "
                               "Lowers the monthly cost so the total stays the same.")
        note = st.session_state.get(p + "note")
        if note and note[1] == care:
            st.caption(note[0])
        elif note:
            st.session_state.pop(p + "note", None)     # edited since: the caption is stale for good
    c3, c4 = st.columns(2, vertical_alignment="bottom")
    with c3:
        leaves = _kid_number(st, p + "leaves", "Leaves home at", kid["leaves_home_age"], 16, 30, 1,
                             "Their costs stop at this age.")
    with c4:
        pct = _kid_number(st, p + "college", "College you pay (%)",
                          round(100 * float(kid["college_funding_pct"])), 0, 100, 5,
                          "Share of college you plan to pay. It's saved in a 529 from birth "
                          "and paid out at college. 0 means none.")
    return {**kid, "years_until_birth": yub, "monthly_cost": cost, "childcare_monthly": care,
            "leaves_home_age": leaves, "college_funding_pct": pct / 100.0}


def _typical_childcare(st, kids: list, n_children: int) -> None:
    """Draw the area picker and the "typical childcare here" line when a child still has
    childcare years ahead (by the row widgets as they are now, not as last run left them)."""
    live = [_live_years_until_birth(st, i, kids[i] if i < len(kids) else _new_child(kids))
            for i in range(n_children)]
    if not any(_years_left(y) for y in live):
        return
    ov = st.session_state.get("user_overrides", {}) or {}
    est, where = childcare_cost.for_household({**ov, "CHILDREN": [{}]})
    budget_area.render(st, "se_kid_area")
    st.caption(f"Typical childcare in {where}: {money_md(est.per_child)}/yr per child "
               f"over the first five years (2026 dollars). Source: {childcare_cost.SOURCE}")


def _children(st) -> list:
    """The Children inputs: how many, then one row each. Writes CHILDREN."""
    kids = cfg.children_in(st.session_state.get("user_overrides", {}) or {})
    ensure_default(st, "se_kids_n", min(len(kids), MAX_CHILDREN))
    n = st.number_input("Number of children", min_value=0, max_value=MAX_CHILDREN, step=1,
                        key="se_kids_n", help="Children you have now or plan to have.")
    out: list = []
    _typical_childcare(st, kids, safe_int(n))
    for i in range(safe_int(n)):
        out.append(_child_row(st, i, kids[i] if i < len(kids) else _new_child(out)))
    if any(c["college_funding_pct"] > 0 for c in out):
        # College prices: one pair for every child.
        first = next(c for c in out if c["college_funding_pct"] > 0)
        c1, c2 = st.columns(2, vertical_alignment="bottom")
        with c1:
            fee = _kid_number(st, "se_kid_college_cost", "A year of college ($)",
                              first["college_annual_cost"], 0, 200_000, 1_000,
                              "Tuition, housing and fees for one year, in today's dollars.")
        with c2:
            years = _kid_number(st, "se_kid_college_years", "Years of college",
                                first["college_years"], 1, 8, 1)
        out = [{**c, "college_annual_cost": fee, "college_years": years} for c in out]
    set_override(st, "CHILDREN", out)
    return out


def family_summary(overrides: dict) -> dict:
    """Children now at home, their monthly cost today, and the age you are when
    the last child leaves home (None with no children). Same data and same
    at-home rule the plan spends from (``derived.compute_expenses_today``)."""
    kids = cfg.children_in(overrides)
    home = children_at_home_now(overrides)
    your_age = safe_int(overrides.get("YOUR_AGE", cfg.YOUR_AGE), cfg.YOUR_AGE)
    last = max((your_age + k["years_until_birth"] + k["leaves_home_age"] for k in kids),
               default=None)
    return {"children": len(kids), "at_home": len(home),
            "monthly_cost": sum(child_monthly_now(k) for k in home),
            "last_leaves_age": last, "your_age": your_age}


def _summary_line(s: dict) -> str:
    if not s["children"]:
        return "No children in the plan."
    gone = s["last_leaves_age"] <= s["your_age"]
    n = s["at_home"]
    if gone:
        return "All your children have left home."
    now = (f"{n} child{'ren' if n != 1 else ''} at home now, {money_md(s['monthly_cost'])}/mo today"
           if n else "No children at home yet")
    return f"{now}. The last one leaves home when you're {s['last_leaves_age']}."


def render_body(st) -> None:
    _children(st)
    overrides = st.session_state.get("user_overrides", {}) or {}
    st.caption(_summary_line(family_summary(overrides)))
    if any(c["college_funding_pct"] > 0 for c in cfg.children_in(overrides)):
        st.caption("The yearly 529 saving comes out of your budget in Investments.")


def render(st) -> None:
    with section_expander(st, "Family", "family_restroom"):
        render_body(st)
