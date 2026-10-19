"""Where the app is running: on your own machine, or hosted for other people.

Hosted mode turns off everything that reads the server's filesystem on a
visitor's behalf (e.g. the Spending tab's statements folder) in favour of
per-session uploads. It is on when RETIREMENT_SIM_HOSTED is set to a truthy
value, or automatically on Streamlit Community Cloud (apps run from /mount/src).
"""
from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}


def is_hosted() -> bool:
    flag = os.environ.get("RETIREMENT_SIM_HOSTED", "").strip().lower()
    if flag:
        return flag in _TRUTHY
    return os.path.abspath(__file__).startswith("/mount/src/")
