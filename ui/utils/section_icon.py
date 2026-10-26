"""Sidebar section expander that keeps its category icon while open (phone).

Streamlit swaps an expander's icon for a chevron when it is open, so an open
section lost its identity.  On phone the CSS (theme.css, "Phone polish H5")
moves that chevron to the right edge and draws the category icon from the
marker emitted here instead.  The marker is out of flow (absolutely positioned
over the summary chip), so it adds no space to the section body.
"""
from contextlib import contextmanager


@contextmanager
def section_expander(st, label: str, icon: str):
    """``st.expander(label, icon=':material/<icon>:')`` plus the icon marker."""
    with st.expander(label, expanded=False, icon=f":material/{icon}:"):
        st.markdown(f'<span class="mc-sec-ico" aria-hidden="true">{icon}</span>', unsafe_allow_html=True)
        yield
