"""Places for the Freedom milestones section: the built-in list and the saved edits.

A place is a rough answer to "what if I retired THERE?" Each place is based on an
AREA (a US state, a metro area or a city abroad, utils/place_costs.py) and has

* a housing choice: BUY a typical home there, RENT there, or KEEP your home
  ("Where you live now" always keeps it). Buying or renting sells the home you
  own now at the retirement age;
* an optional home price and rent of your own (None = the area's typical one);
* an overall adjustment for everyday (non-housing) spending, 1.00 = as the area
  data says. It multiplies the per-category result;
* an income-tax setting and a short note.

Everyday spending is compared with WHERE YOU LIVE NOW, an area you pick (saved
as the "home" setting; by default the plan's state). The data are ROUGH,
ILLUSTRATIVE estimates, not facts. Edit any place, hide the ones you don't want
and add your own.

Everything here is plain data with no Streamlit, so it is easy to test. Edits
live in ONE saved key, ``MS_PLACES``, inside ``user_overrides``. That makes them
travel with Save/Load, Remember me and the profile picker for free. The engine
never reads the key (config_builder drops it) and sim_runner leaves it out of
the cache keys, so editing a place does not make a finished run look stale.
A profile saved before this feature has no key and loads exactly as before.

Saved versions: v1 (one cost ``factor`` per place) loads into v2. A built-in
place's edited factor becomes an adjustment of factor / old built-in factor, so
your tweak keeps its size on top of the new data. A custom place had no area,
so it keeps your home (no move), is priced like where you live now, and its
factor becomes the adjustment.

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

try:
    from utils import place_costs as pc
except ImportError:  # pragma: no cover
    from ui.utils import place_costs as pc  # type: ignore

KEY = "MS_PLACES"
VERSION = 2

TAX_SAME = "same"
TAX_NONE = "none"
TAX_US_PREFIX = "US:"

HOUSING_BUY, HOUSING_RENT, HOUSING_KEEP = "buy", "rent", "keep"
HOUSING_CHOICES = (HOUSING_BUY, HOUSING_RENT, HOUSING_KEEP)
HOUSING_LABELS = {HOUSING_BUY: "Buy a home there", HOUSING_RENT: "Rent there",
                  HOUSING_KEEP: "Keep my home (no move)"}

HERE_ID = "here"
GROUP_HERE, GROUP_US, GROUP_ABROAD, GROUP_CUSTOM = "here", "us", "abroad", "custom"

ADJUST_MIN, ADJUST_MAX = 0.20, 3.00
PRICE_MAX = 20_000_000
RENT_MAX = 50_000
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
    area: str              # place_costs code; "" = where you live now
    housing: str           # "buy" | "rent" | "keep"
    tax: str               # "same" | "US:XX" | "none"
    note: str = ""
    price: Optional[int] = None    # home price there; None = the area's typical
    rent: Optional[int] = None     # monthly rent there; None = the area's typical
    adjust: float = 1.0            # extra multiplier on everyday spending

    @property
    def custom(self) -> bool:
        return self.group == GROUP_CUSTOM

    @property
    def here(self) -> bool:
        return self.id == HERE_ID

    @property
    def abroad(self) -> bool:
        return self.group == GROUP_ABROAD or (
            bool(self.area) and pc.get(self.area).kind == pc.KIND_ABROAD)

    def area_code(self, home: str) -> str:
        """The area whose prices apply: its own, or where you live now."""
        return self.area or home

    def home_price(self, home: str) -> int:
        return int(self.price) if self.price is not None else int(pc.get(self.area_code(home)).price)

    def monthly_rent(self, home: str) -> int:
        return int(self.rent) if self.rent is not None else int(pc.get(self.area_code(home)).rent)

    def carry(self, home: str) -> float:
        return float(pc.get(self.area_code(home)).carry)


_ABROAD_NOTE = "State tax set to none as a placeholder."

BUILT_IN: Tuple[Place, ...] = (
    Place(HERE_ID, "Where you live now", GROUP_HERE, "", HOUSING_KEEP, TAX_SAME,
          "Your plan as you entered it."),
    Place("midwest", "Midwest", GROUP_US, "OH", HOUSING_BUY, "US:OH",
          "Ohio's costs and tax table stand in for the region."),
    Place("southeast", "Southeast", GROUP_US, "NC", HOUSING_BUY, "US:NC",
          "North Carolina's costs and tax table stand in for the region."),
    Place("texas", "Texas", GROUP_US, "TX", HOUSING_BUY, "US:TX",
          "No state income tax. Property taxes run high."),
    Place("arizona", "Arizona", GROUP_US, "AZ", HOUSING_BUY, "US:AZ", "Low flat state income tax."),
    Place("pnw", "Pacific Northwest", GROUP_US, "WA", HOUSING_BUY, "US:WA",
          "Washington's numbers. No state income tax."),
    Place("coastal", "High-cost coastal", GROUP_US, "M_LAX", HOUSING_BUY, "US:CA",
          "A big coastal city. Los Angeles numbers stand in."),
    Place("portugal", "Portugal", GROUP_ABROAD, "X_PT", HOUSING_RENT, TAX_NONE,
          "Lisbon-area living. " + _ABROAD_NOTE),
    Place("italy", "Italy", GROUP_ABROAD, "X_IT", HOUSING_RENT, TAX_NONE,
          "A mid-size city, not Milan or Rome. " + _ABROAD_NOTE),
    Place("spain", "Spain", GROUP_ABROAD, "X_ES", HOUSING_RENT, TAX_NONE,
          "A mid-size coastal city. " + _ABROAD_NOTE),
    Place("mexico", "Mexico", GROUP_ABROAD, "X_MX", HOUSING_RENT, TAX_NONE,
          "A mid-size city. " + _ABROAD_NOTE),
    Place("thailand", "Thailand", GROUP_ABROAD, "X_TH", HOUSING_RENT, TAX_NONE,
          "A regional city such as Chiang Mai. " + _ABROAD_NOTE),
)
_BUILT_IN_BY_ID: Dict[str, Place] = {p.id: p for p in BUILT_IN}

# The single cost factors of saved version 1, to migrate edits made then.
_V1_FACTORS = {"here": 1.00, "midwest": 0.88, "southeast": 0.92, "texas": 0.95, "arizona": 0.98,
               "pnw": 1.12, "coastal": 1.35, "portugal": 0.72, "italy": 0.80, "spain": 0.74,
               "mexico": 0.58, "thailand": 0.48}

ABROAD_CAVEAT = ("Places abroad use no state income tax as a placeholder. US federal tax still "
                 "applies. Foreign tax, tax treaties, visas and currency swings are not modeled. "
                 "Health insurance there is a rough local price, and Medicare stays as planned.")


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


# --------------------------------------------------------------------------- cleaning

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


def _adjust(value: Any, default: float = 1.0) -> float:
    return round(_num(value, default, ADJUST_MIN, ADJUST_MAX), 3)


def _money(value: Any, hi: int) -> Optional[int]:
    """A whole-dollar amount, or None for "the area's typical"."""
    if value is None or value == "":
        return None
    v = _num(value, -1, -1, hi)
    return None if v <= 0 else int(round(v))


def _housing(value: Any, default: str) -> str:
    v = str(value or "").strip().lower()
    return v if v in HOUSING_CHOICES else default


def _area(value: Any, default: str) -> str:
    return str(value) if pc.known(value) else default


def default_housing(area: str) -> str:
    """Buy in the US, rent abroad."""
    return HOUSING_RENT if pc.get(area).kind == pc.KIND_ABROAD else HOUSING_BUY


# --------------------------------------------------------------------------- saved state

def empty_state() -> Dict[str, Any]:
    return {"v": VERSION, "edits": {}, "custom": [], "hidden": [], "settings": {}}


def _clean_edit(pid: str, e: dict, v1: bool) -> dict:
    base = _BUILT_IN_BY_ID[pid]
    clean: Dict[str, Any] = {}
    if v1 and "factor" in e:
        old = _V1_FACTORS.get(pid, 1.0)
        clean["adjust"] = _adjust(_num(e["factor"], old, ADJUST_MIN, ADJUST_MAX) / old)
    if "adjust" in e:
        clean["adjust"] = _adjust(e["adjust"])
    if "tax" in e:
        clean["tax"] = normalize_tax(e["tax"])
    if "note" in e:
        clean["note"] = _clean_text(e["note"], NOTE_MAX)
    if not base.here:
        if "housing" in e:
            clean["housing"] = _housing(e["housing"], base.housing)
        for k, hi in (("price", PRICE_MAX), ("rent", RENT_MAX)):
            if k in e and _money(e[k], hi) is not None:
                clean[k] = _money(e[k], hi)
    return _drop_defaults(clean, base)


def _drop_defaults(e: dict, base: Place) -> dict:
    for k in ("adjust", "tax", "note", "housing", "price", "rent"):
        if k in e and e[k] == getattr(base, k):
            del e[k]
    return e


def _clean_custom(c: dict, pid: str, name: str, v1: bool, home: str) -> dict:
    if v1 or "area" not in c:
        # Version 1 had no areas: keep your home and area, the factor is the adjustment.
        area = home
        housing = HOUSING_KEEP
        adjust = _adjust(c.get("factor", 1.0))
    else:
        area = _area(c.get("area"), home)
        housing = _housing(c.get("housing"), default_housing(area))
        adjust = _adjust(c.get("adjust", 1.0))
    return {"id": pid, "name": name, "area": area, "housing": housing,
            "price": _money(c.get("price"), PRICE_MAX), "rent": _money(c.get("rent"), RENT_MAX),
            "adjust": adjust, "tax": normalize_tax(c.get("tax")),
            "note": _clean_text(c.get("note"), NOTE_MAX)}


def get_state(overrides: Optional[dict]) -> Dict[str, Any]:
    """The saved state from ``user_overrides``, cleaned and brought up to the
    current version. Missing or damaged parts come back empty, so an older or
    hand-edited profile still loads."""
    overrides = overrides or {}
    raw = overrides.get(KEY)
    state = empty_state()
    if not isinstance(raw, dict):
        return state
    try:
        v1 = int(raw.get("v", 1)) < 2
    except (TypeError, ValueError):
        v1 = True
    settings = raw.get("settings")
    if isinstance(settings, dict):
        if "rate" in settings:
            state["settings"]["rate"] = round(_num(settings["rate"], DEFAULT_RATE, RATE_MIN, RATE_MAX), 4)
        if "barista" in settings:
            state["settings"]["barista"] = int(_num(settings["barista"], DEFAULT_BARISTA, 0, BARISTA_MAX))
        if pc.known(settings.get("home")) and pc.get(settings["home"]).kind != pc.KIND_ABROAD:
            if settings["home"] != pc.default_home(overrides.get("STATE_CHOICE")):
                state["settings"]["home"] = settings["home"]
    edits = raw.get("edits")
    if isinstance(edits, dict):
        for pid, e in edits.items():
            if pid in _BUILT_IN_BY_ID and isinstance(e, dict):
                clean = _clean_edit(pid, e, v1)
                if clean:
                    state["edits"][pid] = clean
    custom = raw.get("custom")
    if isinstance(custom, list):
        seen = set(_BUILT_IN_BY_ID)
        home = home_area(state, overrides)
        for c in custom:
            if not isinstance(c, dict):
                continue
            pid = _clean_text(c.get("id"), 20)
            name = _clean_text(c.get("name"), NAME_MAX)
            if not pid or not name or pid in seen or len(state["custom"]) >= MAX_CUSTOM:
                continue
            seen.add(pid)
            state["custom"].append(_clean_custom(c, pid, name, v1, home))
    hidden = raw.get("hidden")
    if isinstance(hidden, list):
        state["hidden"] = [h for h in hidden if h in _BUILT_IN_BY_ID and h != HERE_ID]
    return state


def home_area(state: dict, overrides: Optional[dict]) -> str:
    """Where you live now: the area you picked, else the plan's state, else the US average."""
    picked = (state.get("settings") or {}).get("home")
    if pc.known(picked):
        return picked
    return pc.default_home((overrides or {}).get("STATE_CHOICE"))


def with_home(state: dict, code: Any, overrides: Optional[dict]) -> dict:
    """Pick where you live now. The plan's own state is the default and is not stored."""
    new = copy.deepcopy(state)
    if pc.known(code) and code != pc.default_home((overrides or {}).get("STATE_CHOICE")):
        new["settings"]["home"] = code
    else:
        new["settings"].pop("home", None)
    return new


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
        out.append(replace(base, **{k: e[k] for k in ("adjust", "tax", "note", "housing", "price", "rent")
                                    if k in e}))
    for c in state.get("custom", []):
        out.append(Place(c["id"], c["name"], GROUP_CUSTOM, c["area"], c["housing"], c["tax"],
                         c.get("note", ""), c.get("price"), c.get("rent"), c.get("adjust", 1.0)))
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


_UNSET = object()


def with_edit(state: dict, pid: str, *, area: Any = _UNSET, housing: Any = _UNSET, price: Any = _UNSET,
              rent: Any = _UNSET, adjust: Any = _UNSET, tax: Any = _UNSET, note: Any = _UNSET) -> dict:
    """Change some of a place's settings. A price or rent of None (or 0) means the
    area's typical one. A value equal to the built-in default is dropped, so
    "reset" is just editing back. Only custom places can change area; doing so
    goes back to the new area's typical price and rent. "Where you live now"
    keeps your home, so only its adjustment, tax and note change."""
    new = copy.deepcopy(state)
    given = {k: v for k, v in (("housing", housing), ("price", price), ("rent", rent),
                               ("adjust", adjust), ("tax", tax), ("note", note)) if v is not _UNSET}
    if pid in _BUILT_IN_BY_ID:
        base = _BUILT_IN_BY_ID[pid]
        e = dict(new["edits"].get(pid, {}))
        for k, v in given.items():
            if base.here and k in ("housing", "price", "rent"):
                continue
            e[k] = _clean_field(k, v, base.housing)
        for k in ("price", "rent"):
            if k in e and e[k] is None:
                del e[k]
        e = _drop_defaults(e, base)
        if e:
            new["edits"][pid] = e
        else:
            new["edits"].pop(pid, None)
        return new
    for c in new["custom"]:
        if c["id"] != pid:
            continue
        if area is not _UNSET and pc.known(area) and area != c["area"]:
            c["area"] = area
            c["price"] = c["rent"] = None
            if c["housing"] != HOUSING_KEEP and "housing" not in given:
                c["housing"] = default_housing(area)
        for k, v in given.items():
            c[k] = _clean_field(k, v, c["housing"])
    return new


def _clean_field(key: str, value: Any, housing_default: str) -> Any:
    if key == "housing":
        return _housing(value, housing_default)
    if key == "price":
        return _money(value, PRICE_MAX)
    if key == "rent":
        return _money(value, RENT_MAX)
    if key == "adjust":
        return _adjust(value)
    if key == "tax":
        return normalize_tax(value)
    return _clean_text(value, NOTE_MAX)


def with_custom(state: dict, name: Any, area: Any = pc.US_CODE, housing: Any = None, tax: Any = None,
                note: Any = "") -> Tuple[dict, Optional[str]]:
    """Add a place of your own, based on an area. Returns (new state, its id), or
    (state, None) when the name is empty or the limit is reached. Housing and tax
    default to the area's (buy in the US, rent abroad; that state's tax)."""
    new = copy.deepcopy(state)
    nm = _clean_text(name, NAME_MAX)
    if not nm or len(new["custom"]) >= MAX_CUSTOM:
        return new, None
    code = _area(area, pc.US_CODE)
    used = {c["id"] for c in new["custom"]}
    n = 1
    while f"c{n}" in used:
        n += 1
    pid = f"c{n}"
    new["custom"].append({"id": pid, "name": nm, "area": code,
                          "housing": _housing(housing, default_housing(code)),
                          "price": None, "rent": None, "adjust": 1.0,
                          "tax": normalize_tax(pc.get(code).tax if tax is None else tax),
                          "note": _clean_text(note, NOTE_MAX)})
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


def with_reset(state: dict, pid: str) -> dict:
    """Put a built-in place back to its defaults."""
    new = copy.deepcopy(state)
    new["edits"].pop(pid, None)
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
