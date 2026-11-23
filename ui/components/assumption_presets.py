"""The "All conservative assumptions" and "All typical assumptions" buttons.

Drawn at the top of the Assumptions section. The rules live in
``utils/assumption_presets.py``. This file only draws: a status line, two full-width
buttons and, after a click, a box listing what changed with an Undo button.

The buttons use ``on_click`` callbacks. The widgets they change (Investments, About you,
Retirement) were drawn earlier in the same run, and Streamlit does not allow writing a
widget's state after it has drawn. A callback runs before the page draws anything.
"""
from __future__ import annotations

try:
    from utils import assumption_presets as ap
    from utils.household import plan_end_text
except ImportError:  # pragma: no cover
    from ui.utils import assumption_presets as ap  # type: ignore
    from ui.utils.household import plan_end_text  # type: ignore

SHOW_LINES = 8


def _situation_line(last: dict) -> str:
    f = last["facts"]
    who = f"{f['A']}" + (f" and a partner at {f['P']}" if f["P"] > 0 else "")
    retire = ("already retired" if f["R"] <= f["A"] else f"retiring at {f['R']}")
    line = f"Set for you at {who}, {retire}, money lasting until {_plan_end(last)}."
    horizon = int(last.get("horizon") or 0)
    if horizon > 0:
        line += f" That is {horizon} years of retirement."
    return line


def _plan_end(last: dict) -> str:
    """"you're 102 and your partner is 100": the plan end the simulation uses, so the
    years of retirement below add up for a couple with a younger partner."""
    after = last["after"]
    f = last["facts"]
    values = {"YOUR_AGE": f["A"], "PARTNER_AGE": f["P"],
              "PLAN_UNTIL_AGE": after.get("PLAN_UNTIL_AGE"),
              "PARTNER_PLAN_UNTIL_AGE": after.get("PARTNER_PLAN_UNTIL_AGE")}
    return plan_end_text(values)


def _change_lines(last: dict) -> list:
    lines = []
    for key in last["changes"]:
        old = ap.format_value(key, last["old"].get(key))
        new = ap.format_value(key, last["after"][key])
        lines.append(f"{ap.LABELS[key]}: {old} → {new}")
    if last["facts"].get("comp_customized"):
        lines.append(ap.COPY["kept_pay"])
    return lines


def _draw_box(st, last: dict) -> None:
    n = len(last["changes"])
    with st.container(border=True):
        st.markdown(f"**What changed ({n} setting{'s' if n != 1 else ''})**")
        st.caption(_situation_line(last))
        lines = _change_lines(last)
        st.markdown("\n".join(f"- {line}" for line in lines[:SHOW_LINES]))
        if len(lines) > SHOW_LINES:
            with st.expander("Show all"):
                st.markdown("\n".join(f"- {line}" for line in lines[SHOW_LINES:]))
        if last.get("name") == ap.TYPICAL and last.get("scenario") == "conservative":
            st.caption(ap.COPY["long_plan_note"])
        with st.expander("Why these numbers?"):
            st.markdown("\n".join(f"- {ap.LABELS[k]}: {last['reasons'][k]}" for k in last["changes"]
                                  if k in last["reasons"]))
        st.caption(ap.COPY["run_note"])
        st.button("Undo", key="assume_undo", on_click=ap.undo_preset, args=(st,), width="stretch")


def render(st) -> None:
    ss = st.session_state
    kind, text = ap.status(st)
    st.caption(text)
    st.caption(ap.COPY["intro"])
    st.button("All conservative assumptions", key="assume_btn_conservative",
              on_click=ap.apply_preset, args=(st, ap.CONSERVATIVE), width="stretch",
              help=ap.COPY["conservative_help"])
    st.button("All typical assumptions", key="assume_btn_typical",
              on_click=ap.apply_preset, args=(st, ap.TYPICAL), width="stretch",
              help=ap.COPY["typical_help"])

    if ss.pop("assume_undone", False):
        st.caption(ap.COPY["undone"])
        return
    if ss.get("assume_noop") == kind:
        st.caption(f"Your settings already match {ap.TITLES[kind]}. Nothing changed.")
    last = ss.get("assume_last")
    if last and ap.undo_available(st):
        _draw_box(st, last)
