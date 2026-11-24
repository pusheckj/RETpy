"""Welcome: the first screen for a new visitor. Two starting points — the simple
money check-up or the full retirement planner. The choice is kept for the
session (and on the visitor's device if they turn on "Remember me")."""
from __future__ import annotations

from typing import Optional

PATHS = [
    ("simple", "Money check-up",
     "Your savings rate, emergency fund, where your next dollar goes, a debt "
     "payoff plan and a 50/30/20 budget check. About three minutes.",
     "Start the money check-up"),
    ("full", "Retirement planner",
     "When can you retire? Thousands of market simulations of your accounts, "
     "taxes, Social Security and spending.",
     "Open the retirement planner"),
]


HOSTED_RESULTS_NOTE = ("To speed things up, recent results stay in server memory for a short "
                       "time. They are never written to disk.")


def privacy_html(hosted: bool) -> str:
    """The privacy sentence under the two paths. Hosted visitors also hear that
    results are cached in server memory (keyed on a hash of their inputs)."""
    text = ("Nothing is stored on the server. Your inputs are saved on this device only if "
            "you turn on <b>Remember me on this device</b>.")
    if hosted:
        text += " " + HOSTED_RESULTS_NOTE
    return f'<p class="mc-welcome-privacy">{text}</p>'


def render(st) -> Optional[str]:
    """Draw the welcome screen; return the chosen mode once a path is picked."""
    st.markdown(
        '<div class="mc-welcome-head"><div class="mc-welcome-kicker">RETpy</div>'
        "<h1>What would you like to do?</h1>"
        "<p>Pick a starting point. You can switch any time.</p></div>",
        unsafe_allow_html=True,
    )
    chosen = None
    for col, (mode, title, blurb, cta) in zip(st.columns(2), PATHS):
        with col, st.container(border=True, key=f"mc-welcome-{mode}"):
            st.markdown(f'<div class="mc-welcome-card"><h3>{title}</h3><p>{blurb}</p></div>',
                        unsafe_allow_html=True)
            if st.button(cta, key=f"welcome_{mode}", width="stretch",
                         type="primary"):
                chosen = mode
    from utils.hosting import is_hosted
    st.markdown(privacy_html(is_hosted()), unsafe_allow_html=True)
    return chosen
