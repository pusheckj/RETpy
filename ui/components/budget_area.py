"""The area picker: which of the 739 areas your prices follow.

One saved setting, ``BENCH_AREA`` (an area label from ui/data/budget/locations.json), drives
two features: the childcare suggestion in Family and "Your spending vs similar households"
in the Spending tab. Each screen draws its own selectbox (its own widget key); a change in
one resets the other so both show the saved choice. With nothing picked the household's
state is used.
"""
from __future__ import annotations

from typing import List

try:
    from utils import budget_data as bd
    from utils import state_choice as sc
except ImportError:  # pragma: no cover
    from ui.utils import budget_data as bd  # type: ignore
    from ui.utils import state_choice as sc  # type: ignore

KEYS = ("se_kid_area", "se_kid_area_spend")   # both start with "se_kid": a profile switch clears them
KEY = "BENCH_AREA"


def _first(state) -> str:
    return f"{sc.label_for(state)} (statewide average)" if state else "US average"


def options(overrides: dict) -> List[str]:
    """The choices: the state-wide average first, then that state's areas. A saved area
    from another state (the state was changed later) stays in the list."""
    opts = [_first(bd.state_code(overrides))] + bd.area_labels(bd.state_code(overrides))
    cur = overrides.get(KEY)
    if bd.area(cur) and cur not in opts:
        opts.append(cur)
    return opts


def choice_for(overrides: dict) -> str:
    """The option that shows the saved choice."""
    opts = options(overrides)
    cur = overrides.get(KEY)
    return cur if cur in opts else opts[0]


def _changed(st, key: str) -> None:
    ov = st.session_state.setdefault("user_overrides", {})
    picked = st.session_state.get(key)
    if picked is None or picked == _first(bd.state_code(ov)) or not bd.area(picked):
        ov.pop(KEY, None)
    else:
        ov[KEY] = picked
    for other in KEYS:
        if other != key:
            st.session_state.pop(other, None)       # redrawn from the saved choice


def render(st, key: str, label: str = "Area for local prices") -> None:
    ov = st.session_state.setdefault("user_overrides", {})
    opts = options(ov)
    if st.session_state.get(key) not in opts:       # first draw, or the state changed
        st.session_state[key] = choice_for(ov)
    st.selectbox(label, opts, key=key, on_change=_changed, args=(st, key),
                 help="Prices and rents differ a lot by area. Pick the metro area or county "
                      "closest to you. Type to search. Saved with your plan.")
