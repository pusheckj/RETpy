"""What the app keeps in the visitor's browser, and how it comes back after a refresh.

Pure helpers with no Streamlit import at module level, so every rule is unit-testable.
The transport (sessionStorage, localStorage, one reader round trip) is
``utils/device_store.py``. The full design is in ``perf/persistence_design.md``.

Three things are built from the session each run:

* the tab copy (always on): the visitor's inputs, mode, setup step, pinned scenarios and a
  little view state. A refresh keeps it. Closing the tab erases it.
* the device copy (only while "Remember me on this device" is on): the same, without the view
  state. It stays after the tab closes.
* display prefs (always on, no inputs): theme, font, palette and simulation count.

At start-up ``pick`` chooses one copy (tab, then device, then the owner's profile file) and
``apply`` puts it back before the sidebar and the auto-run draw. Each part is restored in its
own try, so one bad part never drops the others.

Never saved: results, uploaded statements, the salted input hash, the browser-compute and lazy-load
flags, undo stacks, and every widget key that ``DIRECT_MAPPINGS`` already mirrors from the inputs
(saving both would give two sources of truth).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

CAP_BYTES = 200_000                  # one stored item; pins go first when it is over, then the view
MAX_PINS = 10
CUSTOM_PROFILE = "Custom (keep current values)"

OWNER_NOTICE = "Your profile file changed, so the planner loaded it. Your earlier browser copy was replaced."
RESTORE_FAILED = "We couldn't bring back your last inputs. You're starting fresh."

# Plain session keys this module relies on across a profile switch (the profile picker
# wipes every key that is not in its preserve set).
PRESERVED_KEYS = ("_view_saved", "_viewport_narrow", "_view_tabs", "_persist_seed_sig", "_persist_base",
                  "_main_view_default")

# Inputs that are not in user_overrides but belong to the visitor.
_EXTRA_PREFIXES = ("le_",)
_EXTRA_NAMES = ("ms_rate", "ms_barista",
                "wifc_scenario", "wifc_stock", "wifc_spend", "wifc_savings", "wifc_fee", "wifc_infl",
                "wifc_ss", "wifc_ss_claim")
_VIEW_NAMES = ("main_view", "tax_tab_view")
_VIEW_SUFFIXES = ("_dollars", "_dollars_mode")
_APPEARANCE_KEYS = ("theme_mode", "font_choice", "palette_choice")
_SETUP_KEYS = ("status", "step", "seen", "checkup")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _plain(value: Any) -> Any:
    """JSON round trip that also turns numpy numbers into plain ones."""
    def fallback(obj):
        item = getattr(obj, "item", None)
        if callable(item):
            return item()
        return str(obj)
    return json.loads(json.dumps(value, default=fallback, ensure_ascii=False))


def _is_scalar_or_str_list(value: Any) -> bool:
    if isinstance(value, (str, int, float, bool)):
        return True
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def engine_fp() -> str:
    """Fingerprint of the model code (a pin made with other code is out of date)."""
    try:
        from utils import disk_cache
        return disk_cache.engine_fingerprint()
    except Exception:
        return ""


def serialize_full(overrides: dict) -> str:
    """The inputs as the same JSON text a profile download holds (it loads with
    ``deserialize_overrides``), minus the timestamp and with sorted keys, so two
    builds of the same inputs are the same text and the same hash."""
    from utils import profile_io
    envelope = {"version": profile_io.SCHEMA_VERSION, "app": profile_io.APP_TAG,
                "overrides": profile_io._stringify_keys(overrides)}
    return json.dumps(envelope, default=str, sort_keys=True, separators=(",", ":"))


def file_fp_of(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:16]
    except OSError:
        return None


def file_fp() -> str | None:
    """Short hash of the owner's profile file, or None when hosted or there is no file."""
    try:
        from utils.hosting import is_hosted
        from utils.profile_io import personal_profile_path
        if is_hosted():
            return None
        return file_fp_of(personal_profile_path())
    except Exception:
        return None


# --------------------------------------------------------------------------
# Building what gets saved
# --------------------------------------------------------------------------

def _extras(state: Mapping) -> dict:
    out = {}
    for key in list(state.keys()):
        if not isinstance(key, str):
            continue
        if (key in _EXTRA_NAMES or key.startswith(_EXTRA_PREFIXES)) and _is_scalar_or_str_list(state[key]):
            out[key] = state[key]
    return out


def _pins(state: Mapping) -> list:
    pins = state.get("pinned_scenarios")
    if not isinstance(pins, dict) or not pins:
        return []
    current = engine_fp()
    out = []
    for name, entry in list(pins.items())[-MAX_PINS:]:
        if not isinstance(entry, dict):
            continue
        overrides = entry.get("overrides")
        pin = {"name": str(name), "summary": _plain(entry.get("summary") or {}),
               "engine_fp": entry.get("engine_fp") or current}
        if isinstance(overrides, dict):
            pin["overrides"] = serialize_full(overrides)
        if isinstance(entry.get("saved_at"), str):
            pin["saved_at"] = entry["saved_at"]
        out.append(pin)
    return out


def trim(payload: dict, cap: int = CAP_BYTES) -> dict:
    """Drop optional parts until the payload fits: pins first, then the view.
    The inputs are never dropped (a payload that still does not fit is not stored)."""
    for part in ("pins", "view"):
        if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) <= cap:
            break
        payload.pop(part, None)
    return payload


def _is_view_key(key: Any) -> bool:
    return isinstance(key, str) and (key in _VIEW_NAMES or key.endswith(_VIEW_SUFFIXES))


def mirror_view(state: Mapping) -> dict:
    """The view choices (main view, Today's/Future $ radios, tax view) as a plain dict. Streamlit
    drops a widget's value on any run that does not draw it, so the last seen value is kept here
    and a value is replaced only when the widget is drawn with a new one."""
    saved = dict(state.get("_view_saved") or {})
    for key in list(state.keys()):
        if _is_view_key(key) and isinstance(state[key], str):
            saved[key] = state[key]
    return saved


def reapply_view(state) -> None:
    """Put the saved view choices back into widgets that were not drawn on the last run (a lazy
    tile, a closed section): Streamlit forgets a widget's value after a run that skips it. Runs
    before the page draws, so it never touches a widget that was already created this run."""
    saved = state.get("_view_saved")
    if not isinstance(saved, dict):
        return
    for key, value in saved.items():
        if key != "main_view" and _is_view_key(key) and isinstance(value, str) and key not in state:
            state[key] = value


def build_prefs(state: Mapping) -> dict:
    saved = state.get("_appearance_saved")
    prefs = {k: saved[k] for k in _APPEARANCE_KEYS if isinstance(saved, dict) and isinstance(saved.get(k), str)}
    sims = state.get("_n_simulations_saved")
    if isinstance(sims, int) and not isinstance(sims, bool):
        prefs["n_simulations"] = sims
    return prefs


def build_payload(state: Mapping) -> tuple:
    """``(tab, device, prefs)`` for this run. ``tab`` is None until a version is chosen
    (so a welcome-screen visit never hides a remembered copy), ``device`` is None unless
    Remember me is on. No timestamps or counters, so equal inputs give equal hashes."""
    prefs = build_prefs(state)
    mode = state.get("app_mode")
    if mode not in ("simple", "full"):
        return None, None, prefs
    remember = bool(state.get("remember_device"))
    payload: dict = {"remember": remember, "mode": mode}
    if isinstance(state.get("simple_inputs"), dict):
        payload["simple"] = _plain(state["simple_inputs"])
    overrides = state.get("user_overrides")
    if (mode == "full" or state.get("_full_touched")) and isinstance(overrides, dict):
        payload["full"] = serialize_full(overrides)
        payload["comp_customized"] = bool(state.get("si_comp_customized"))
        extra = _extras(state)
        if extra:
            payload["extra"] = _plain(extra)
    setup = state.get("setup")
    if isinstance(setup, dict):
        payload["setup"] = {k: setup.get(k) for k in _SETUP_KEYS}
    pins = _pins(state)
    if pins:
        payload["pins"] = pins
    base = state.get("_persist_base")
    if isinstance(base, str) and base:
        payload["base"] = base
    device = trim(dict(payload)) if remember else None
    view = state.get("_view_saved")
    if isinstance(view, dict) and view:
        payload["view"] = _plain(view)
    return trim(payload), device, prefs


# --------------------------------------------------------------------------
# Choosing a copy
# --------------------------------------------------------------------------

def pick(tab: Any, device: Any, fp: str | None = None) -> tuple:
    """``(source, data)``: the tab copy, else the device copy (if Remember me was on), else
    nothing. ``("file", None)`` means a copy exists but the owner's profile file changed
    after it was made (its ``base`` differs from ``fp``), so the file wins."""
    for source, data in (("tab", tab), ("device", device)):
        if not isinstance(data, dict) or not data:
            continue
        if source == "device" and not data.get("remember"):
            continue
        base = data.get("base")
        if fp and isinstance(base, str) and base and base != fp:
            return "file", None
        return source, data
    return "none", None


# --------------------------------------------------------------------------
# Putting a copy back
# --------------------------------------------------------------------------

def _apply_remember(st, data: dict, source: str) -> None:
    st.session_state["remember_device"] = bool(data.get("remember"))


def _apply_mode(st, data: dict, source: str) -> None:
    if data.get("mode") in ("simple", "full"):
        st.session_state["app_mode"] = data["mode"]


def _apply_simple(st, data: dict, source: str) -> None:
    if isinstance(data.get("simple"), dict):
        from utils.simple_finance import normalize_inputs
        st.session_state["simple_inputs"] = normalize_inputs(data["simple"])


def _apply_full(st, data: dict, source: str) -> None:
    if not isinstance(data.get("full"), str):
        return
    from utils.profile_io import deserialize_overrides
    from utils.widget_sync import sync_widgets_from_overrides
    overrides = deserialize_overrides(data["full"])
    st.session_state["user_overrides"] = overrides
    st.session_state["_full_touched"] = True
    sync_widgets_from_overrides(st)


def _apply_extras(st, data: dict, source: str) -> None:
    extra = data.get("extra")
    if not isinstance(extra, dict):
        return
    for key, value in extra.items():
        if isinstance(key, str) and (key in _EXTRA_NAMES or key.startswith(_EXTRA_PREFIXES)) \
                and _is_scalar_or_str_list(value) and key not in st.session_state:
            st.session_state[key] = value


def _apply_profile(st, data: dict, source: str) -> None:
    if not isinstance(data.get("full"), str):
        return
    customized = data.get("comp_customized")
    if not isinstance(customized, bool):
        customized = bool((st.session_state.get("user_overrides") or {}).get("YOUR_COMPENSATION_BY_AGE"))
    st.session_state["si_comp_customized"] = customized
    st.session_state["profile"] = CUSTOM_PROFILE
    st.session_state["profile_selectbox"] = CUSTOM_PROFILE


def _apply_pins(st, data: dict, source: str) -> None:
    pins = data.get("pins")
    if not isinstance(pins, list):
        return
    from utils.profile_io import deserialize_overrides
    restored = {}
    for pin in pins[-MAX_PINS:]:
        if not isinstance(pin, dict) or not isinstance(pin.get("name"), str):
            continue
        entry = {"summary": pin.get("summary") if isinstance(pin.get("summary"), dict) else {},
                 "engine_fp": pin.get("engine_fp")}
        if isinstance(pin.get("saved_at"), str):
            entry["saved_at"] = pin["saved_at"]
        try:
            entry["overrides"] = deserialize_overrides(pin["overrides"]) if isinstance(pin.get("overrides"), str) else {}
        except Exception:
            continue
        restored[pin["name"]] = entry
    if restored:
        st.session_state["pinned_scenarios"] = restored


def _apply_view(st, data: dict, source: str) -> None:
    view = data.get("view")
    if source != "tab" or not isinstance(view, dict):
        return
    clean = {k: v for k, v in view.items() if _is_view_key(k) and isinstance(v, str)}
    for key, value in clean.items():
        if key == "main_view":
            # A segmented control with a default must not also get its value from session_state
            # (Streamlit warns). It opens on this default instead, fixed for the whole session.
            st.session_state["_main_view_default"] = value
        else:
            st.session_state[key] = value
    st.session_state["_view_saved"] = clean


def _apply_setup(st, data: dict, source: str) -> None:
    from components import guided_setup
    setup = guided_setup.restore(data.get("setup"))
    if setup:
        st.session_state[guided_setup.STATE] = setup
    elif isinstance(data.get("full"), str):
        guided_setup.mark_done(st)           # saved before the walkthrough existed


# Order matters: inputs and their widgets first, then what hangs off them, then mode and setup.
_PARTS = (
    ("full", _apply_full),
    ("simple", _apply_simple),
    ("extras", _apply_extras),
    ("profile", _apply_profile),
    ("pins", _apply_pins),
    ("view", _apply_view),
    ("remember", _apply_remember),
    ("mode", _apply_mode),
    ("setup", _apply_setup),
)
# Parts whose loss means the visitor's inputs did not come back.
_CRITICAL = ("full", "simple", "mode", "setup")
# Parts that only make sense on top of restored inputs.
_NEEDS_FULL = ("extras", "profile")


def apply(st, data: dict, source: str) -> list:
    """Put a copy back into ``st.session_state``, each part in its own try. Returns the names
    of the parts that failed (empty when everything came back)."""
    failed: list = []
    for name, fn in _PARTS:
        if name in _NEEDS_FULL and "full" in failed:
            continue
        try:
            fn(st, data, source)
        except Exception:
            failed.append(name)
    return failed


def critical_failure(failed: Iterable[str]) -> bool:
    return any(name in _CRITICAL for name in failed)


def apply_prefs(st, prefs: Any, sim_options: Iterable[int]) -> None:
    """Display choices: theme, font, palette and simulation count. Each is checked against
    what the app offers; an unknown value is ignored."""
    if not isinstance(prefs, dict):
        return
    saved = dict(st.session_state.get("_appearance_saved") or {})
    valid: dict = {"theme_mode": ("☀ Light", "🌙 Dark")}
    try:
        from components.theme_toggle import FONT_OPTIONS
        valid["font_choice"] = tuple(FONT_OPTIONS)
    except Exception:
        pass
    try:
        from utils.plot_theme import PALETTES
        valid["palette_choice"] = tuple(PALETTES)
    except Exception:
        pass
    for key in _APPEARANCE_KEYS:
        value = prefs.get(key)
        if isinstance(value, str) and value in valid.get(key, ()):
            st.session_state[key] = value
            saved[key] = value
    if saved:
        st.session_state["_appearance_saved"] = saved
    sims = prefs.get("n_simulations")
    if isinstance(sims, int) and not isinstance(sims, bool) and sims in set(sim_options):
        st.session_state["n_simulations"] = sims
        st.session_state["_n_simulations_saved"] = sims


def tab_default(group: str, labels: list, state: Mapping | None = None) -> str | None:
    """The tab to open in a ``st.tabs`` group: the one the browser reported open before the
    refresh (``_view_tabs``), if it still exists. ``st.tabs`` cannot be read back, so only the
    browser knows which tab the visitor had open."""
    if state is None:
        import streamlit as st
        state = st.session_state
    tabs = state.get("_view_tabs")
    label = tabs.get(group) if isinstance(tabs, dict) else None
    return label if label in labels else None
