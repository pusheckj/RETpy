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
    from utils.derived import children_at_home_now
except ImportError:  # pragma: no cover
    from ui.utils.overrides import set_override  # type: ignore
    from ui.utils.derived import children_at_home_now  # type: ignore

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
    with c2:
        cost = _kid_number(st, p + "cost", "Monthly cost ($)", kid["monthly_cost"], 0, 10_000, 100,
                           "Childcare, food, clothes and activities while they live with you, "
                           "in today's dollars.")
    c3, c4 = st.columns(2, vertical_alignment="bottom")
    with c3:
        leaves = _kid_number(st, p + "leaves", "Leaves home at", kid["leaves_home_age"], 16, 30, 1,
                             "Their costs stop at this age.")
    with c4:
        pct = _kid_number(st, p + "college", "College you pay (%)",
                          round(100 * float(kid["college_funding_pct"])), 0, 100, 5,
                          "Share of college you plan to pay. It's saved in a 529 from birth "
                          "and paid out at college. 0 means none.")
    return {**kid, "years_until_birth": yub, "monthly_cost": cost, "leaves_home_age": leaves,
            "college_funding_pct": pct / 100.0}


def _children(st) -> list:
    """The Children inputs: how many, then one row each. Writes CHILDREN."""
    kids = cfg.children_in(st.session_state.get("user_overrides", {}) or {})
    ensure_default(st, "se_kids_n", min(len(kids), MAX_CHILDREN))
    n = st.number_input("Number of children", min_value=0, max_value=MAX_CHILDREN, step=1,
                        key="se_kids_n", help="Children you have now or plan to have.")
    out: list = []
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
            "monthly_cost": sum(safe_int(k["monthly_cost"], 0) for k in home),
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
        st.caption("The yearly 529 saving comes out of your budget in Savings.")


def render(st) -> None:
    with section_expander(st, "Family", "family_restroom"):
        render_body(st)
