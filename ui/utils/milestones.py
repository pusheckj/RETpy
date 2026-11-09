"""Freedom milestones: which markers of freedom you have passed, and when the rest arrive.

Pure logic, no Streamlit. The component (components/freedom_milestones.py) gathers
the numbers and draws the result.

Everything is in today's dollars, the engine's all-real frame.

How each marker is decided
--------------------------
The timeline is a list of ages with the invested balance at each (and the home
equity, for net worth). A milestone is REACHED if the balance already clears it
at the first age, IN PROGRESS if the balance clears it at a later age (that age
is the projection) and BEYOND if it never does within the plan.

* Net worth / invested ladders: fixed rungs ($100K, $250K, $500K, $1M, ...). Net
  worth is invested balance plus home equity. Invested leaves the home out.
* FIRE in a place: invested balance >= that place's yearly spending / withdrawal
  rate. Spending there = everyday spending, housing and children at the retirement
  age, times the place's cost factor, plus health costs (health is not scaled).
  Housing and children's costs stay as the plan has them, so the factor cannot
  take spending below those.
* Coast FIRE in a place: the balance, left alone with no more saving, grows at the
  real return to the FIRE number by the planned retirement age.
* Other markers: emergency fund (cash covers 6 / 12 months), investments cover
  essentials (Lean FIRE), Barista FIRE (part-time income closes the gap), returns
  cover a year of costs, mortgage paid off.

These are quick rules to show direction. The simulation is the real test:
``place_overrides`` turns a place into the engine settings that test it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Union

try:
    from utils.places import Place, engine_state, GROUP_ABROAD
except ImportError:  # pragma: no cover
    from ui.utils.places import Place, engine_state, GROUP_ABROAD  # type: ignore

REACHED, PROGRESS, BEYOND = "reached", "progress", "beyond"

KIND_NETWORTH, KIND_INVESTED, KIND_COAST, KIND_FIRE, KIND_MARKER = (
    "networth", "invested", "coast", "fire", "marker")

# Ladders: how many passed rungs and how many coming rungs to show.
KEEP_REACHED = 2
SHOW_AHEAD = 4


@dataclass(frozen=True)
class Milestone:
    key: str
    kind: str
    label: str
    status: str                      # REACHED | PROGRESS | BEYOND
    current: float                   # what you have now
    target: float                    # what it takes
    progress: Optional[float]        # 0..1, or None when there is no bar to draw
    age: Optional[int]               # REACHED: your age now. PROGRESS: projected age
    year: Optional[int]
    detail: str = ""                 # one short line
    place_id: Optional[str] = None
    unit: str = "$"                  # "$" or "months"

    @property
    def reached(self) -> bool:
        return self.status == REACHED


@dataclass(frozen=True)
class PlaceResult:
    place: Place
    spend: float                     # yearly spending there (today's dollars)
    fire_number: float               # invested balance that covers it at the rate
    coast: Milestone
    fire: Milestone


@dataclass(frozen=True)
class Inputs:
    your_age: int
    retire_age: int
    year: int
    ages: Sequence[int]              # ascending, starting at your_age
    invested: Sequence[float]        # invested balance at each age (no home)
    home: Sequence[float]            # home equity at each age (zeros if none)
    spend_core: float                # yearly everyday spending + housing + kids in retirement
    living_base: float               # the part of spend_core a place can scale (not housing or kids)
    health: float                    # yearly health costs in retirement
    today_spend: float               # yearly spending now
    discretionary_ratio: float       # share of spending that is not essential
    rate: float                      # withdrawal rate, a fraction (0.04)
    real_return: float               # expected real return, a fraction
    cash: float                      # cash accounts today
    barista_income: float            # part-time income per year
    mortgage_years: int              # years left on the mortgage (0 = none)
    places: Sequence[Place] = field(default_factory=tuple)


@dataclass(frozen=True)
class Report:
    networth: List[Milestone]
    invested: List[Milestone]
    places: List[PlaceResult]
    markers: List[Milestone]
    earlier_networth: int            # passed rungs below the ones shown
    earlier_invested: int
    reached: int
    total: int
    next_up: Optional[Milestone]
    spending_known: bool             # False when there is no spending to test


# --------------------------------------------------------------------------- helpers

def short_money(value: float) -> str:
    """$250K, $1M, $1.5M, $12.5K, $850."""
    v = abs(float(value))
    sign = "-" if value < 0 else ""
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= size:
            n = v / size
            text = f"{n:.1f}".rstrip("0").rstrip(".") if n < 100 else f"{n:.0f}"
            return f"{sign}${text}{suffix}"
    return f"{sign}${v:,.0f}"


def rungs() -> List[float]:
    """The fixed ladder: $10K, $25K, $50K, $100K, $250K, $500K, $1M, $2M, $3M, $5M, $10M, ..."""
    out = [10e3, 25e3, 50e3, 100e3, 250e3, 500e3]
    mag = 1e6
    while mag <= 1e9:
        out += [mag * m for m in (1, 2, 3, 5)]
        mag *= 10
    return out


def pick_rungs(current: float, keep_reached: int = KEEP_REACHED, ahead: int = SHOW_AHEAD):
    """(rungs to show, how many passed rungs are left out below them)."""
    allr = rungs()
    passed = [r for r in allr if r <= current]
    coming = [r for r in allr if r > current]
    shown_passed = passed[-keep_reached:] if keep_reached > 0 else []
    return shown_passed + coming[:ahead], len(passed) - len(shown_passed)


def year_of(age: Optional[int], your_age: int, year: int) -> Optional[int]:
    return None if age is None else year + (int(age) - int(your_age))


Need = Union[float, Callable[[int], float]]


def _need_at(need: Need, age: int) -> float:
    return float(need(age)) if callable(need) else float(need)


def track(ages: Sequence[int], values: Sequence[float], need: Need):
    """(status, age, progress) for a balance against a target.

    ``need`` is a number, or a function of age (Coast FIRE: the target falls the
    closer you are to retirement). REACHED when the first value clears it;
    PROGRESS with the first later age that does; BEYOND when none does."""
    if not ages or not values:
        return BEYOND, None, 0.0
    n = min(len(ages), len(values))
    first_need = _need_at(need, ages[0])
    now = float(values[0])
    progress = 1.0 if first_need <= 0 else min(1.0, max(0.0, now / first_need))
    if now >= first_need:
        return REACHED, int(ages[0]), 1.0
    for i in range(1, n):
        if float(values[i]) >= _need_at(need, ages[i]):
            return PROGRESS, int(ages[i]), progress
    return BEYOND, None, progress


def _make(inp: Inputs, key, kind, label, status, current, target, age, progress, detail="",
          place_id=None, unit="$") -> Milestone:
    return Milestone(key=key, kind=kind, label=label, status=status, current=float(current),
                     target=float(target), progress=progress, age=age,
                     year=year_of(age, inp.your_age, inp.year), detail=detail,
                     place_id=place_id, unit=unit)


def _tracked(inp: Inputs, key, kind, label, values, need, current, target, detail="",
             place_id=None) -> Milestone:
    status, age, prog = track(inp.ages, values, need)
    return _make(inp, key, kind, label, status, current, target, age, prog, detail, place_id)


# --------------------------------------------------------------------------- the spending rule

def place_spend(core: float, health: float, factor: float, living: Optional[float] = None) -> float:
    """Yearly spending in a place: everyday spending times the cost factor, plus health.

    The simulation can move only the living part of ``core`` (the rest is housing
    and children, which stay as the plan has them), so the factor cannot take
    spending below ``core - living``. Health costs are not scaled."""
    core = max(0.0, core)
    floor = 0.0 if living is None else max(0.0, core - max(0.0, living))
    return max(core * max(0.0, factor), floor) + max(0.0, health)


def fire_number(spend: float, rate: float) -> float:
    """The invested balance whose yearly withdrawal at ``rate`` covers ``spend``."""
    return spend / rate if rate > 0 else float("inf")


def coast_need(fire: float, age: int, retire_age: int, real_return: float) -> float:
    """What you need invested at ``age`` to coast: it grows to ``fire`` by retirement."""
    years = max(0, int(retire_age) - int(age))
    return fire / ((1.0 + real_return) ** years)


def place_overrides(place: Place, spend_core: float, living_base: float) -> dict:
    """Engine settings that test retiring in ``place`` with the real simulation.

    Spending: the retirement living base moves by (factor - 1) x everyday
    spending, so year-one spending there is factor x everyday spending, the same
    as the quick rule (``place_spend``). It cannot go below your housing and
    children's costs. Health costs and your plan's other rules stay as they are.
    A factor of 1 leaves spending alone. Tax: ``RETIREMENT_STATE_CHOICE`` applies
    the place's state to retirement-phase tax only; your working years keep the
    state you live in now. A place that changes nothing returns {}.
    """
    out: dict = {}
    if abs(place.factor - 1.0) > 1e-9:
        out["RETIREMENT_SPENDING_MODE"] = "Absolute amount ($/yr)"
        out["RETIREMENT_SPENDING_ABSOLUTE"] = round(
            max(0.0, float(living_base) + (place.factor - 1.0) * float(spend_core)), 2)
    state = engine_state(place.tax)
    if state is not None:
        out["RETIREMENT_STATE_CHOICE"] = state
    return out


# --------------------------------------------------------------------------- the report

def _ladder(inp: Inputs, kind: str, values: Sequence[float], word: str):
    current = float(values[0]) if len(values) else 0.0
    shown, earlier = pick_rungs(current)
    out = []
    for r in shown:
        status, age, prog = track(inp.ages, values, r)
        gap = max(0.0, r - current)
        detail = (f"You have {short_money(current)}" if status == REACHED
                  else f"{short_money(gap)} to go")
        out.append(_make(inp, f"{kind}:{int(r)}", kind, f"{short_money(r)} {word}", status,
                         current, r, age, prog, detail))
    return out, earlier


def _place_result(inp: Inputs, place: Place) -> PlaceResult:
    spend = place_spend(inp.spend_core, inp.health, place.factor, inp.living_base)
    fire = fire_number(spend, inp.rate)
    current = float(inp.invested[0]) if len(inp.invested) else 0.0
    ret = inp.retire_age
    r = inp.real_return
    coast = _tracked(
        inp, f"coast:{place.id}", KIND_COAST, f"Coast FIRE in {place.name}", inp.invested,
        lambda a, _f=fire: coast_need(_f, a, ret, r), current,
        coast_need(fire, inp.ages[0] if len(inp.ages) else inp.your_age, ret, r),
        f"Stop saving. Growth alone gets you to {short_money(fire)} by {max(ret, inp.your_age)}.",
        place.id)
    fire_m = _tracked(
        inp, f"fire:{place.id}", KIND_FIRE, f"FIRE in {place.name}", inp.invested, fire, current, fire,
        f"Covers {short_money(spend)} a year at {inp.rate * 100:.4g}%.", place.id)
    return PlaceResult(place, spend, fire, coast, fire_m)


def _markers(inp: Inputs, spending_known: bool) -> List[Milestone]:
    out: List[Milestone] = []
    current = float(inp.invested[0]) if len(inp.invested) else 0.0

    # Emergency fund: cash accounts only (the plan keeps new savings in investments).
    monthly = inp.today_spend / 12.0
    if monthly > 0:
        for months in (6, 12):
            need = months * monthly
            have = inp.cash / monthly
            status = REACHED if inp.cash >= need else PROGRESS
            out.append(_make(inp, f"emergency:{months}", KIND_MARKER,
                             f"{months}-month emergency fund", status, inp.cash, need,
                             inp.your_age if status == REACHED else None,
                             min(1.0, max(0.0, inp.cash / need)),
                             f"Cash covers {have:.1f} of {months} months.", unit="months"))

    if spending_known:
        total = inp.spend_core + inp.health
        essentials = inp.spend_core * (1.0 - inp.discretionary_ratio) + inp.health
        lean = fire_number(essentials, inp.rate)
        out.append(_tracked(inp, "lean", KIND_MARKER, "Investments cover the essentials", inp.invested,
                            lean, current, lean,
                            f"Essentials are about {short_money(essentials)} a year."))
        gap = max(0.0, total - max(0.0, inp.barista_income))
        barista = fire_number(gap, inp.rate)
        out.append(_tracked(inp, "barista", KIND_MARKER, "Barista FIRE", inp.invested, barista, current,
                            barista,
                            f"Part-time {short_money(inp.barista_income)} a year, investments cover the rest."))
        if inp.real_return > 0:
            need = total / inp.real_return
            out.append(_tracked(inp, "returns", KIND_MARKER, "A year of returns pays a year of costs",
                                inp.invested, need, current, need,
                                f"Growth at {inp.real_return * 100:.1f}% a year covers {short_money(total)}."))

    if inp.mortgage_years > 0:
        age = inp.your_age + int(inp.mortgage_years)
        out.append(_make(inp, "mortgage", KIND_MARKER, "Mortgage paid off", PROGRESS, 0, 0, age, None,
                         f"{int(inp.mortgage_years)} years of payments left."))
    return out


def _next_up(all_ms: Sequence[Milestone]) -> Optional[Milestone]:
    coming = [m for m in all_ms if m.status == PROGRESS and m.age is not None]
    return min(coming, key=lambda m: m.age) if coming else None


def build(inp: Inputs) -> Report:
    """Every milestone for these inputs."""
    nw_values = [float(i) + float(h) for i, h in zip(inp.invested, inp.home)]
    networth, e_nw = _ladder(inp, KIND_NETWORTH, nw_values, "net worth")
    invested, e_inv = _ladder(inp, KIND_INVESTED, inp.invested, "invested")

    spending_known = (inp.spend_core + inp.health) > 0 and inp.rate > 0
    places = [_place_result(inp, p) for p in inp.places] if spending_known else []
    markers = _markers(inp, spending_known)

    flat: List[Milestone] = list(invested) + list(networth)
    for pr in places:
        flat += [pr.coast, pr.fire]
    flat += markers
    reached = sum(1 for m in flat if m.status == REACHED) + e_nw + e_inv
    return Report(networth=networth, invested=invested, places=places, markers=markers,
                  earlier_networth=e_nw, earlier_invested=e_inv, reached=reached,
                  total=len(flat) + e_nw + e_inv, next_up=_next_up(flat),
                  spending_known=spending_known)


def status_word(m: Milestone) -> str:
    """Plain words for the status, so colour is never the only signal."""
    return {REACHED: "Reached", PROGRESS: "In progress", BEYOND: "Not in this plan"}[m.status]
