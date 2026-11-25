"""Section: Family — your children: when they arrive, what they cost, college.

The rows write ``CHILDREN``. Their widget keys all start with "se_kid" and are
filled and cleared as a family by ``utils/widget_sync`` (``_sync_children``).
"""
from __future__ import annotations

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


def _in_childcare_years(years_until_birth: int, childcare_monthly: int = 0) -> bool:
    """Whether a child gets the childcare box: planned, under the childcare age now, or
    already carrying a childcare amount (so it can still be seen and cleared)."""
    return (years_until_birth > 0 or -years_until_birth < cfg.CHILDCARE_END_AGE
            or childcare_monthly > 0)


def move_childcare(old_cost: int, old_care: int, new_care: int, leaves_home_age: int) -> int:
    """The monthly cost once childcare is ``new_care`` a month instead of ``old_care``.

    The monthly cost runs for every year at home and childcare only for the first
    CHILDCARE_END_AGE, so the same total money moves when the cost falls by the childcare
    change scaled by those years. Never below zero."""
    shift = (new_care - old_care) * cfg.CHILDCARE_END_AGE / max(1, leaves_home_age)
    return max(0, old_cost - round(shift))


def _use_childcare(st, p: str, typical: int) -> None:
    """Button callback: childcare takes the typical figure and the monthly cost gives up the
    same money, spread over the years at home. Says so in a caption."""
    ss = st.session_state
    old_cost, old_care = safe_int(ss.get(p + "cost"), 0), safe_int(ss.get(p + "care"), 0)
    new_cost = move_childcare(old_cost, old_care, typical, safe_int(ss.get(p + "leaves"), 18))
    ss[p + "care"], ss[p + "cost"] = typical, new_cost
    if new_cost < old_cost:
        what = f"lowered from {money_md(old_cost)} to {money_md(new_cost)}"
    elif new_cost > old_cost:
        what = f"raised from {money_md(old_cost)} to {money_md(new_cost)}"
    else:
        what = f"stays at {money_md(new_cost)}"
    ss[p + "note"] = (f"Monthly cost {what}. The childcare part now sits in its own box.", typical)


def _child_row(st, i: int, kid: dict, typical: int = 0) -> dict:
    """One child's inputs; returns the child's CHILDREN entry. ``typical`` is the
    suggested childcare a month for the household's area (0 = no suggestion)."""
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
    has_box = _in_childcare_years(yub, safe_int(st.session_state.get(care_key, saved_care), 0))
    with c2:
        has_care = safe_int(st.session_state.get(care_key, saved_care), 0) > 0
        help_cost = "Childcare, food, clothes and activities while they live with you, in today's dollars."
        if has_box:
            help_cost = ("Food, clothes and activities while they live with you, in today's dollars. "
                         "Childcare for the first five years is in the box below." if has_care else
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
                               "Paid childcare in the first five years, in today's dollars. It comes "
                               "on top of the monthly cost above. Use typical lowers the monthly "
                               "cost by the same money, spread over the years at home.")
        with c6:
            if typical > 0:
                st.button(f"Use typical {money_md(typical)}/mo", key=p + "use_care",
                          on_click=_use_childcare, args=(st, p, typical),
                          disabled=care == typical,
                          help="Sets this child's childcare to the typical figure for your area "
                               "and lowers the monthly cost so the total is not counted twice.")
        note = st.session_state.get(p + "note")
        if note and note[1] == care:
            st.caption(note[0])
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


def _typical_childcare(st, kids: list, n_children: int) -> int:
    """Draw the area picker and the "typical childcare here" line when a child is in the
    childcare years; return the typical childcare a month for one child (0 if none is)."""
    eligible = any(i >= len(kids) or _in_childcare_years(kids[i]["years_until_birth"],
                                                         kids[i]["childcare_monthly"])
                   for i in range(n_children))
    if not eligible:
        return 0
    ov = st.session_state.get("user_overrides", {}) or {}
    est, where = childcare_cost.for_household({**ov, "CHILDREN": [{}] * n_children})
    budget_area.render(st, "se_kid_area")
    st.caption(f"Typical childcare in {where}: {money_md(est.per_child)}/yr per child "
               f"(2026 dollars). Source: {childcare_cost.SOURCE}")
    return round(est.per_child / 12)


def _children(st) -> list:
    """The Children inputs: how many, then one row each. Writes CHILDREN."""
    kids = cfg.children_in(st.session_state.get("user_overrides", {}) or {})
    ensure_default(st, "se_kids_n", min(len(kids), MAX_CHILDREN))
    n = st.number_input("Number of children", min_value=0, max_value=MAX_CHILDREN, step=1,
                        key="se_kids_n", help="Children you have now or plan to have.")
    out: list = []
    typical = _typical_childcare(st, kids, safe_int(n))
    for i in range(safe_int(n)):
        out.append(_child_row(st, i, kids[i] if i < len(kids) else _new_child(out), typical))
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
