"""Places for the Freedom milestones section: the built-in list and the saved edits.

A place is a rough answer to "what if I retired THERE?" It has a name, a cost
factor (spending there compared with spending where you live now), an
income-tax setting and a short note.

The built-in numbers are ROUGH, ILLUSTRATIVE estimates for a household that now
lives in an average-cost area. They are not data. Edit any of them, hide the
ones you don't want and add your own.

Everything here is plain data with no Streamlit, so it is easy to test. Edits
live in ONE saved key, ``MS_PLACES``, inside ``user_overrides``. That makes them
travel with Save/Load, Remember me and the profile picker for free. The engine
never reads the key (config_builder drops it) and sim_runner leaves it out of
the cache keys, so editing a place does not make a finished run look stale.
A profile saved before this feature has no key and loads exactly as before.

Tax settings (one string per place):
    "same"   keep your plan's state tax
    "US:TX"  that US state's tax table (retirement_sim/state_tax_data.py)
    "none"   no income tax. For a place abroad this is a PLACEHOLDER only:
             US federal tax still applies and foreign tax is not modeled.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

from retirement_sim import state_tax_data

KEY = "MS_PLACES"
VERSION = 1

TAX_SAME = "same"
TAX_NONE = "none"
TAX_US_PREFIX = "US:"

HERE_ID = "here"
GROUP_HERE, GROUP_US, GROUP_ABROAD, GROUP_CUSTOM = "here", "us", "abroad", "custom"

FACTOR_MIN, FACTOR_MAX = 0.20, 3.00
NAME_MAX = 40
NOTE_MAX = 120
MAX_CUSTOM = 12

# Section settings saved next to the places.
DEFAULT_RATE = 0.04            # the classic 4% rule, as in the charts and FAQ
RATE_MIN, RATE_MAX = 0.025, 0.06
DEFAULT_BARISTA = 24_000       # part-time income for Barista FIRE, per year
BARISTA_MAX = 200_000


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    group: str
    factor: float          # spending there / spending where you live now
    tax: str               # "same" | "US:XX" | "none"
    note: str = ""

    @property
    def custom(self) -> bool:
        return self.group == GROUP_CUSTOM

    @property
    def abroad(self) -> bool:
        return self.group == GROUP_ABROAD


_ABROAD_NOTE = "State tax set to none as a placeholder."

BUILT_IN: Tuple[Place, ...] = (
    Place(HERE_ID, "Where you live now", GROUP_HERE, 1.00, TAX_SAME, "Your plan as you entered it."),
    Place("midwest", "Midwest", GROUP_US, 0.88, "US:OH", "Lower housing costs. Ohio's tax table stands in for the region."),
    Place("southeast", "Southeast", GROUP_US, 0.92, "US:NC", "Mild costs. North Carolina's tax table stands in for the region."),
    Place("texas", "Texas", GROUP_US, 0.95, "US:TX", "No state income tax. Property taxes run high."),
    Place("arizona", "Arizona", GROUP_US, 0.98, "US:AZ", "Low flat state income tax."),
    Place("pnw", "Pacific Northwest", GROUP_US, 1.12, "US:WA", "No state income tax in Washington. Housing costs more."),
    Place("coastal", "High-cost coastal", GROUP_US, 1.35, "US:CA", "Big coastal city. California's tax table stands in. Edit it if you already live in one."),
    Place("portugal", "Portugal", GROUP_ABROAD, 0.72, TAX_NONE, "Lisbon-area living. " + _ABROAD_NOTE),
    Place("italy", "Italy", GROUP_ABROAD, 0.80, TAX_NONE, "A mid-size city, not Milan or Rome. " + _ABROAD_NOTE),
    Place("spain", "Spain", GROUP_ABROAD, 0.74, TAX_NONE, "A mid-size coastal city. " + _ABROAD_NOTE),
    Place("mexico", "Mexico", GROUP_ABROAD, 0.58, TAX_NONE, "A mid-size city. " + _ABROAD_NOTE),
    Place("thailand", "Thailand", GROUP_ABROAD, 0.48, TAX_NONE, "A regional city such as Chiang Mai. " + _ABROAD_NOTE),
)
_BUILT_IN_BY_ID: Dict[str, Place] = {p.id: p for p in BUILT_IN}

ABROAD_CAVEAT = ("Places abroad use no state income tax as a placeholder. US federal tax still "
                 "applies. Foreign tax, tax treaties, visas, healthcare and currency swings are "
                 "not modeled.")


# --------------------------------------------------------------------------- tax settings

def us_state_options() -> List[Tuple[str, str]]:
    """(name, code) for every state in the tax tables, by name."""
    return sorted((row["name"], code) for code, row in state_tax_data.STATES.items())


def normalize_tax(tax: Any) -> str:
    """A valid tax setting; anything unknown becomes "same"."""
    s = str(tax or "").strip()
    if s == TAX_NONE:
        return TAX_NONE
    if s.upper().startswith(TAX_US_PREFIX):
        code = s[len(TAX_US_PREFIX):].strip().upper()
        if code in state_tax_data.STATES:
            return TAX_US_PREFIX + code
    return TAX_SAME


def tax_label(tax: str, abroad: bool = False) -> str:
    """Short plain label for a tax setting."""
    tax = normalize_tax(tax)
    if tax == TAX_SAME:
        return "Your state's tax"
    if tax == TAX_NONE:
        return "No income tax (placeholder)" if abroad else "No state income tax"
    return state_tax_data.STATES[tax[len(TAX_US_PREFIX):]]["name"] + " tax"


def tax_choices() -> List[Tuple[str, str]]:
    """(label, value) for a tax picker: same, none, then every state."""
    out = [("Keep my current state's tax", TAX_SAME), ("No income tax (placeholder)", TAX_NONE)]
    out += [(name + " tax", TAX_US_PREFIX + code) for name, code in us_state_options()]
    return out


def engine_state(tax: str) -> Optional[str]:
    """The ``RETIREMENT_STATE_CHOICE`` for a tax setting, or None to leave it alone."""
    tax = normalize_tax(tax)
    if tax == TAX_SAME:
        return None
    if tax == TAX_NONE:
        return "No state tax"
    return tax[len(TAX_US_PREFIX):]


# --------------------------------------------------------------------------- saved state

def _num(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):
        return default
    return min(hi, max(lo, v))


def _clean_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def empty_state() -> Dict[str, Any]:
    return {"v": VERSION, "edits": {}, "custom": [], "hidden": [], "settings": {}}


def get_state(overrides: Optional[dict]) -> Dict[str, Any]:
    """The saved state from ``user_overrides``, cleaned. Missing or damaged
    parts come back empty, so an older or hand-edited profile still loads."""
    raw = (overrides or {}).get(KEY)
    state = empty_state()
    if not isinstance(raw, dict):
        return state
    edits = raw.get("edits")
    if isinstance(edits, dict):
        for pid, e in edits.items():
            if pid in _BUILT_IN_BY_ID and isinstance(e, dict):
                clean = {}
                if "factor" in e:
                    clean["factor"] = round(_num(e["factor"], _BUILT_IN_BY_ID[pid].factor, FACTOR_MIN, FACTOR_MAX), 3)
                if "tax" in e:
                    clean["tax"] = normalize_tax(e["tax"])
                if "note" in e:
                    clean["note"] = _clean_text(e["note"], NOTE_MAX)
                if clean:
                    state["edits"][pid] = clean
    custom = raw.get("custom")
    if isinstance(custom, list):
        seen = set(_BUILT_IN_BY_ID)
        for c in custom:
            if not isinstance(c, dict):
                continue
            pid = _clean_text(c.get("id"), 20)
            name = _clean_text(c.get("name"), NAME_MAX)
            if not pid or not name or pid in seen or len(state["custom"]) >= MAX_CUSTOM:
                continue
            seen.add(pid)
            state["custom"].append({"id": pid, "name": name,
                                    "factor": round(_num(c.get("factor"), 1.0, FACTOR_MIN, FACTOR_MAX), 3),
                                    "tax": normalize_tax(c.get("tax")),
                                    "note": _clean_text(c.get("note"), NOTE_MAX)})
    hidden = raw.get("hidden")
    if isinstance(hidden, list):
        state["hidden"] = [h for h in hidden if h in _BUILT_IN_BY_ID and h != HERE_ID]
    settings = raw.get("settings")
    if isinstance(settings, dict):
        if "rate" in settings:
            state["settings"]["rate"] = round(_num(settings["rate"], DEFAULT_RATE, RATE_MIN, RATE_MAX), 4)
        if "barista" in settings:
            state["settings"]["barista"] = int(_num(settings["barista"], DEFAULT_BARISTA, 0, BARISTA_MAX))
    return state


def is_empty(state: dict) -> bool:
    return not (state.get("edits") or state.get("custom") or state.get("hidden") or state.get("settings"))


def to_overrides(state: dict) -> Optional[dict]:
    """What to store in ``user_overrides[KEY]``; None when nothing differs from the
    defaults (the key is then left out, so an untouched profile saves as before)."""
    return None if is_empty(state) else copy.deepcopy(state)


def store(overrides: dict, state: dict) -> None:
    """Write ``state`` into ``overrides`` (or drop the key when it is all defaults)."""
    packed = to_overrides(state)
    if packed is None:
        overrides.pop(KEY, None)
    else:
        overrides[KEY] = packed


def resolve(state: dict) -> List[Place]:
    """Every place to show: built-ins (edited, minus hidden), then custom ones."""
    out: List[Place] = []
    for base in BUILT_IN:
        if base.id in state.get("hidden", []):
            continue
        e = state.get("edits", {}).get(base.id, {})
        out.append(replace(base, factor=e.get("factor", base.factor), tax=e.get("tax", base.tax),
                           note=e.get("note", base.note)))
    for c in state.get("custom", []):
        out.append(Place(c["id"], c["name"], GROUP_CUSTOM, c["factor"], c["tax"], c.get("note", "")))
    return out


def get_place(state: dict, pid: str) -> Optional[Place]:
    return next((p for p in resolve(state) if p.id == pid), None)


def setting(state: dict, key: str) -> float:
    if key == "rate":
        return state.get("settings", {}).get("rate", DEFAULT_RATE)
    if key == "barista":
        return state.get("settings", {}).get("barista", DEFAULT_BARISTA)
    raise KeyError(key)


def with_setting(state: dict, key: str, value: Any) -> dict:
    new = copy.deepcopy(state)
    if key == "rate":
        v = round(_num(value, DEFAULT_RATE, RATE_MIN, RATE_MAX), 4)
        default = DEFAULT_RATE
    elif key == "barista":
        v = int(_num(value, DEFAULT_BARISTA, 0, BARISTA_MAX))
        default = DEFAULT_BARISTA
    else:
        raise KeyError(key)
    if v == default:
        new["settings"].pop(key, None)
    else:
        new["settings"][key] = v
    return new


def with_edit(state: dict, pid: str, factor: Any = None, tax: Any = None, note: Any = None) -> dict:
    """Change a place's factor, tax and/or note. A value equal to the built-in
    default is dropped, so "reset" is just editing back."""
    new = copy.deepcopy(state)
    if pid in _BUILT_IN_BY_ID:
        base = _BUILT_IN_BY_ID[pid]
        e = dict(new["edits"].get(pid, {}))
        if factor is not None:
            f = round(_num(factor, base.factor, FACTOR_MIN, FACTOR_MAX), 3)
            e["factor"] = f
        if tax is not None:
            e["tax"] = normalize_tax(tax)
        if note is not None:
            e["note"] = _clean_text(note, NOTE_MAX)
        for k, default in (("factor", base.factor), ("tax", base.tax), ("note", base.note)):
            if k in e and e[k] == default:
                del e[k]
        if e:
            new["edits"][pid] = e
        else:
            new["edits"].pop(pid, None)
        return new
    for c in new["custom"]:
        if c["id"] == pid:
            if factor is not None:
                c["factor"] = round(_num(factor, c["factor"], FACTOR_MIN, FACTOR_MAX), 3)
            if tax is not None:
                c["tax"] = normalize_tax(tax)
            if note is not None:
                c["note"] = _clean_text(note, NOTE_MAX)
    return new


def with_custom(state: dict, name: Any, factor: Any = 1.0, tax: Any = TAX_SAME, note: Any = "") -> Tuple[dict, Optional[str]]:
    """Add a place of your own. Returns (new state, its id), or (state, None)
    when the name is empty or the limit is reached."""
    new = copy.deepcopy(state)
    nm = _clean_text(name, NAME_MAX)
    if not nm or len(new["custom"]) >= MAX_CUSTOM:
        return new, None
    used = {c["id"] for c in new["custom"]}
    n = 1
    while f"c{n}" in used:
        n += 1
    pid = f"c{n}"
    new["custom"].append({"id": pid, "name": nm,
                          "factor": round(_num(factor, 1.0, FACTOR_MIN, FACTOR_MAX), 3),
                          "tax": normalize_tax(tax), "note": _clean_text(note, NOTE_MAX)})
    return new, pid


def with_removed(state: dict, pid: str) -> dict:
    """Delete a custom place, or hide a built-in one (not "Where you live now")."""
    new = copy.deepcopy(state)
    if pid in _BUILT_IN_BY_ID:
        if pid != HERE_ID and pid not in new["hidden"]:
            new["hidden"].append(pid)
        new["edits"].pop(pid, None)
    else:
        new["custom"] = [c for c in new["custom"] if c["id"] != pid]
    return new


def with_restored(state: dict) -> dict:
    """Bring back every hidden built-in place."""
    new = copy.deepcopy(state)
    new["hidden"] = []
    return new


def is_edited(state: dict, pid: str) -> bool:
    return pid in state.get("edits", {})


def default_place(pid: str) -> Optional[Place]:
    return _BUILT_IN_BY_ID.get(pid)
