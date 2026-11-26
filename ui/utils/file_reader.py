"""Read a small file in the visitor's browser and hand its text to Python.

WHY NOT st.file_uploader
    ``st.file_uploader`` sends the file in a separate HTTP PUT to
    ``/_stcore/upload_file/<session>/<file>``. The server rejects it (HTTP 400,
    "Invalid session_id") unless that session has a live websocket. On an iPhone
    the Files picker puts Safari in the background, the connection is
    interrupted, and the upload goes out before it is back.

HOW THIS WORKS
    A static-HTML component (``components/file_reader/index.html``, plain JS, no
    build step) reads the chosen file with FileReader and returns
    ``{name, text, size, nonce}`` as its component value, over the app's normal
    connection. Streamlit drops a value posted while the connection is down, and
    does not resend it by itself on reconnect. So the page keeps the value as
    "pending" and posts it again (same nonce) until a render arrives whose
    ``shown_nonce`` equals it: the app's confirmation. It retries on a timer and
    at once when the app's widgets turn from disabled to enabled (that happens
    when the connection returns). It gives up after about a minute.

LIMITS
    Meant for small text files (saved inputs, a few KB). The size cap is checked
    in the browser and again here. Nothing is stored: the value lives in the
    widget state for this session and is never written to the tab copy.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "components" / "file_reader"
DEFAULT_ACCEPT = ".json,application/json"
DEFAULT_MAX_BYTES = 2_000_000
NAME_MAX = 120

_component_func = None


def _component():
    """Declare the static-HTML component once (cached once it is registered with a running app)."""
    global _component_func
    if _component_func is not None:
        return _component_func
    import streamlit.components.v1 as components
    func = components.declare_component("file_reader", path=str(COMPONENT_DIR))
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is not None:
            _component_func = func
    except Exception:  # pragma: no cover
        pass
    return func


def _megabytes(n: int) -> str:
    mb = n / 1_000_000
    return f"{mb:.0f} MB" if mb >= 10 or mb == int(mb) else f"{mb:.1f} MB"


def _clean_name(name: Any) -> str:
    text = "".join(c for c in str(name) if c.isprintable())[:NAME_MAX].strip()
    return text or "file"


def parse_value(value: Any, max_bytes: int = DEFAULT_MAX_BYTES) -> tuple[Optional[dict], Optional[str]]:
    """Check the browser's value. Returns ``(file, None)``, ``(None, None)`` when nothing
    is chosen, or ``(None, plain-words problem)``. Never raises."""
    if value is None:
        return None, None
    unreadable = "We could not read that file. Choose it again."
    if not isinstance(value, dict):
        return None, unreadable
    name, text, size, nonce = (value.get(k) for k in ("name", "text", "size", "nonce"))
    if not isinstance(text, str) or not isinstance(name, str):
        return None, unreadable
    if isinstance(size, bool) or not isinstance(size, (int, float)) or size < 0:
        return None, unreadable
    if isinstance(size, float) and not math.isfinite(size):
        return None, unreadable
    # Judge the text itself (the browser's size is only what it claims).
    if max(int(size), len(text.encode("utf-8", errors="replace"))) > max_bytes:
        return None, f"That file is too large. The limit is {_megabytes(max_bytes)}."
    return {"name": _clean_name(name), "text": text, "size": int(size),
            "nonce": nonce if isinstance(nonce, str) else ""}, None


def read_file(st, label: str, key: str, accept: str = DEFAULT_ACCEPT,
              max_bytes: int = DEFAULT_MAX_BYTES) -> Optional[dict]:
    """Draw a drop zone with a "Choose a file" button. Returns ``{"name", "text", "size",
    "nonce"}`` once a file is read, else None (nothing chosen, cleared, or rejected: a
    rejection also shows a plain error line).

    To clear it from Python (after the file is used), put a counter in ``key`` and bump
    it: a new key is a new, empty component."""
    try:
        held = st.session_state.get(key)
    except Exception:  # pragma: no cover
        held = None
    held = held if isinstance(held, dict) else {}
    shown = held.get("name") if isinstance(held.get("name"), str) else None
    # The held nonce is the app's confirmation: the page resends its file until it sees this.
    # It is passed even for a value rejected below, so the page stops resending that too.
    shown_nonce = held.get("nonce") if isinstance(held.get("nonce"), str) else None
    value = _component()(label=label, accept=accept, max_bytes=max_bytes, shown=shown,
                         shown_nonce=shown_nonce, key=key, default=None)
    file, problem = parse_value(value, max_bytes)
    if problem:
        st.error(problem)
    return file
