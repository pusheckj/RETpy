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
* FIRE in a place: what you could spend from (invested balance + the cash a move
  frees or costs) >= that place's yearly spending / withdrawal rate. A move sells
  your home at that age (net of the loan, selling costs and tax on the gain) and
  buys a typical home there (the proceeds pay for it; a loan covers any
  shortfall) or rents there. Spending there is built per category:
    - each everyday category (utilities, food, transport, healthcare premiums,
      fun, other, partner) at the plan's retirement amount x the place's price
      level / your home area's price level x the place's adjustment. The plan's
      retirement-spending mode (% of today / absolute) scales them as a group,
      as the engine does;
    - housing there: rent x 12, or the new loan's payment plus property tax and
      insurance at that place's rate ("Where you live now" keeps your housing);
    - children's costs as planned (not scaled);
    - health insurance and care: pre-Medicare costs scaled by the place's health
      price level, Medicare years as planned.
* Coast FIRE in a place: the balance, left alone with no more saving, grows at the
  real return to (FIRE number - cash the move frees) by the planned retirement age.
* Other markers: emergency fund (cash covers 6 / 12 months), investments cover
  essentials (Lean FIRE), Barista FIRE (part-time income closes the gap), returns
  cover a year of costs, mortgage paid off.

These are quick rules to show direction. The simulation is the real test:
``place_overrides`` and ``place_home_events`` turn a place into the engine
settings that test it (the same move, spending and tax).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

try:
    from utils import place_costs as pc
    from utils.formatting import months_text
    from utils.places import Place, engine_state, HOUSING_BUY, HOUSING_RENT, HOUSING_KEEP
except ImportError:  # pragma: no cover
    from ui.utils import place_costs as pc  # type: ignore
    from ui.utils.formatting import months_text  # type: ignore
    from ui.utils.places import Place, engine_state, HOUSING_BUY, HOUSING_RENT, HOUSING_KEEP  # type: ignore

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
class CostBasis:
    """What a place's spending and move are built from (sim_runner.retirement_spending_basis
    and sim_runner.home_sale_path). All yearly, today's dollars."""
    home: str = pc.US_CODE                       # where you live now (place_costs code)
    weights: Mapping[str, float] = field(default_factory=dict)   # category -> today's yearly amount
    housing_now: float = 0.0                     # config housing term at the retirement age (inside spend_core)
    housing_plan: Optional[float] = None         # what the plan really pays then, its own moves included
    pre_medicare: bool = True                    # retirement age before Medicare
    proceeds: Mapping[int, float] = field(default_factory=dict)  # age -> net cash from selling your home then
    moving_costs: float = 10_000.0               # each move (HOUSE_MOVING_COSTS)
    mortgage_rate: float = 0.065                 # a new loan's rate
    loan_years: int = 30
    carry_after_payoff: bool = True              # property tax + insurance once a home is paid off


@dataclass(frozen=True)
class PlaceCost:
    """One place at one move age."""
    categories: Tuple[Tuple[str, float, float], ...]   # (category, yearly now, yearly there)
    living: float                    # everyday spending there (sum of the categories)
    housing: float                   # housing there, yearly
    other: float                     # children's and other planned costs (not scaled)
    health: float                    # health insurance and care
    spend: float                     # all of it
    proceeds: float                  # cash from selling your home (0 if you keep it or rent now)
    price: float                     # home bought there (0 if renting or keeping)
    loan: float                      # the loan for any shortfall
    down: float                      # cash put into the home
    costs: float                     # moving costs
    rent: float                      # monthly rent there (0 unless renting)
    carry: float                     # property tax + insurance rate there
    ratio: float                     # everyday spending there / here, before the adjustment

    @property
    def release(self) -> float:
        """Cash the move adds to your investments (negative when it costs you)."""
        return self.proceeds - self.down - self.costs


@dataclass(frozen=True)
class PlaceResult:
    place: Place
    spend: float                     # yearly spending there at the retirement age (today's dollars)
    fire_number: float               # what it takes at the withdrawal rate
    coast: Milestone
    fire: Milestone
    cost: Optional[PlaceCost] = None  # the pieces, at the retirement age


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
    cost: CostBasis = field(default_factory=CostBasis)


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
    units = ((1e9, "B"), (1e6, "M"), (1e3, "K"))
    for i, (size, suffix) in enumerate(units):
        if v >= size:
            n = v / size
            if i and round(n) >= 1000:   # $999.6K rounds up to $1M, not "$1000K"
                n, suffix = v / units[i - 1][0], units[i - 1][1]
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

def everyday_ratio(weights: Mapping[str, float], place_area: str, home: str) -> float:
    """Everyday spending there / here: each category's price ratio, weighted by what
    you spend on it now. 1.0 when the two areas match or nothing is known."""
    total = sum(max(0.0, float(w)) for w in weights.values())
    if total <= 0:
        return 1.0
    return sum(max(0.0, float(w)) * pc.ratio(place_area, home, c) for c, w in weights.items()) / total


def _loan_payment(loan: float, rate: float, years: int) -> float:
    """Monthly principal + interest (the engine's level payment)."""
    if loan <= 0 or years <= 0:
        return 0.0
    r = max(0.0, rate) / 12.0
    n = int(years) * 12
    return loan / n if r <= 0 else loan * r / (1.0 - (1.0 + r) ** -n)


def place_cost(inp: "Inputs", place: Place, age: int) -> PlaceCost:
    """Spending in ``place`` and the money side of moving there at ``age``."""
    cb = inp.cost
    area = place.area_code(cb.home)
    living = max(0.0, float(inp.living_base))
    housing_now = max(0.0, float(cb.housing_now))
    other = max(0.0, float(inp.spend_core) - living - housing_now)
    weights = {c: max(0.0, float(w)) for c, w in cb.weights.items() if c in pc.CATEGORIES}
    total_w = sum(weights.values())
    adj = max(0.0, float(place.adjust))
    scale = living / total_w if total_w > 0 else 0.0
    cats = tuple((c, w * scale, w * scale * pc.ratio(area, cb.home, c) * adj) for c, w in weights.items())
    ratio = everyday_ratio(weights, area, cb.home)
    living_there = living * ratio * adj
    health = max(0.0, float(inp.health))
    if cb.pre_medicare:
        health *= pc.ratio(area, cb.home, pc.CAT_HEALTH)
    proceeds = price = loan = down = costs = rent = 0.0
    carry = place.carry(cb.home)
    if place.housing == HOUSING_KEEP or place.here:
        housing = housing_now if cb.housing_plan is None else max(0.0, float(cb.housing_plan))
    else:
        proceeds = max(0.0, float(cb.proceeds.get(int(age), 0.0)))
        costs = max(0.0, float(cb.moving_costs))
        if place.housing == HOUSING_RENT:
            rent = float(place.monthly_rent(cb.home))
            housing = rent * 12.0
        else:
            price = float(place.home_price(cb.home))
            loan = max(0.0, price - proceeds)
            down = price - loan
            payment = _loan_payment(loan, cb.mortgage_rate, cb.loan_years) * 12.0
            if loan > 0:
                housing = payment + price * carry
            else:
                housing = price * carry if cb.carry_after_payoff else 0.0
    spend = living_there + housing + other + health
    return PlaceCost(categories=cats, living=living_there, housing=housing, other=other, health=health,
                     spend=spend, proceeds=proceeds, price=price, loan=loan, down=down, costs=costs,
                     rent=rent, carry=carry, ratio=ratio)


def fire_number(spend: float, rate: float) -> float:
    """The invested balance whose yearly withdrawal at ``rate`` covers ``spend``."""
    return spend / rate if rate > 0 else float("inf")


def coast_need(fire: float, age: int, retire_age: int, real_return: float) -> float:
    """What you need invested at ``age`` to coast: it grows to ``fire`` by retirement."""
    years = max(0, int(retire_age) - int(age))
    return fire / ((1.0 + real_return) ** years)


def place_overrides(inp: "Inputs", place: Place, health_knobs: Optional[Mapping] = None) -> dict:
    """Engine settings (besides housing) that test retiring in ``place``.

    Spending: ``RETIREMENT_SPENDING_ABSOLUTE`` is set to the everyday spending
    there (``place_cost(...).living``), so the engine's retirement living base is
    the quick rule's. Children, housing and the plan's other rules stay as they
    are. Health: the pre-Medicare marketplace prices (``health_knobs``: the plan's
    ACA_BENCHMARK_MONTHLY_AT_40, ACA_CHILD_MONTHLY and HEALTHCARE_COSTS_BY_AGE)
    are scaled by the place's health price level; Medicare stays as planned.
    Tax: ``RETIREMENT_STATE_CHOICE`` applies the place's state to retirement-phase
    tax only. A place that changes nothing returns {}. Housing is a HOME_EVENTS
    entry at the move age: see ``place_home_events``.
    """
    out: dict = {}
    pcost = place_cost(inp, place, inp.retire_age)
    if abs(pcost.living - float(inp.living_base)) > 0.5:
        out["RETIREMENT_SPENDING_MODE"] = "Absolute amount ($/yr)"
        out["RETIREMENT_SPENDING_ABSOLUTE"] = round(max(0.0, pcost.living), 2)
    h = pc.ratio(place.area_code(inp.cost.home), inp.cost.home, pc.CAT_HEALTH)
    if health_knobs and abs(h - 1.0) > 1e-9:
        for key in ("ACA_BENCHMARK_MONTHLY_AT_40", "ACA_CHILD_MONTHLY"):
            if health_knobs.get(key) is not None:
                out[key] = round(float(health_knobs[key]) * h, 2)
        bands = health_knobs.get("HEALTHCARE_COSTS_BY_AGE")
        if isinstance(bands, Mapping) and bands.get("early_retirement") is not None:
            new = dict(bands)
            new["early_retirement"] = round(float(bands["early_retirement"]) * h, 2)
            out["HEALTHCARE_COSTS_BY_AGE"] = new
    state = engine_state(place.tax)
    if state is not None:
        out["RETIREMENT_STATE_CHOICE"] = state
    return out


def moves(place: Place) -> bool:
    """Does testing this place sell your home and buy or rent there?"""
    return not place.here and place.housing in (HOUSING_BUY, HOUSING_RENT)


def place_home_events(inp: "Inputs", place: Place, age: int, plan_events: Sequence[dict] = ()) -> Optional[list]:
    """``HOME_EVENTS`` that test moving to ``place`` at ``age``, or None when it keeps
    your home. The plan's own moves before ``age`` stay; any at or after it are
    replaced by this one (you live there from then on). The event is what
    ``place_cost`` assumed: the same price, loan for the shortfall, rate, moving
    costs and carrying rate, or the same rent."""
    if not moves(place):
        return None
    pcost = place_cost(inp, place, age)
    kept = [dict(e) for e in plan_events if int(e.get("age", 0)) < int(age)]
    if place.housing == HOUSING_RENT:
        ev = {"age": int(age), "action": "sell_rent", "rent": round(pcost.rent, 2),
              "costs": round(pcost.costs, 2)}
    else:
        ev = {"age": int(age), "action": "sell_buy", "price": round(pcost.price, 2),
              "loan": round(pcost.loan, 2), "rate": float(inp.cost.mortgage_rate),
              "years": int(inp.cost.loan_years) if pcost.loan > 0 else 0,
              "costs": round(pcost.costs, 2), "carrying_pct": float(pcost.carry)}
    return kept + [ev]


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
    ret = inp.retire_age
    r = inp.real_return
    at = {a: place_cost(inp, place, a) for a in set(int(x) for x in inp.ages) | {int(ret)}}

    def cost_at(a: int) -> PlaceCost:
        a = int(a)
        if a not in at:
            at[a] = place_cost(inp, place, a)
        return at[a]

    here = cost_at(ret)
    fire = fire_number(here.spend, inp.rate)
    rate_txt = f"{inp.rate * 100:.4g}%"
    # FIRE at age a: invested + what the move frees at a covers spending there at the rate.
    values = [float(v) + cost_at(a).release for a, v in zip(inp.ages, inp.invested)]
    current = values[0] if values else 0.0
    fire_m = _tracked(
        inp, f"fire:{place.id}", KIND_FIRE, f"FIRE in {place.name}", values,
        lambda a: fire_number(cost_at(a).spend, inp.rate), current, fire,
        f"Covers {short_money(here.spend)} a year at {rate_txt}.", place.id)

    # Coast FIRE: invested alone grows to (FIRE number - what the move frees) by retirement.
    def coast_at(a: int) -> float:
        m = max(int(a), int(ret))
        c = cost_at(m)
        return coast_need(max(0.0, fire_number(c.spend, inp.rate) - c.release), a, ret, r)

    first_age = inp.ages[0] if len(inp.ages) else inp.your_age
    coast = _tracked(
        inp, f"coast:{place.id}", KIND_COAST, f"Coast FIRE in {place.name}", inp.invested,
        coast_at, float(inp.invested[0]) if len(inp.invested) else 0.0, coast_at(first_age),
        f"Stop saving. Growth alone gets you to {short_money(fire)} by {max(ret, inp.your_age)}.",
        place.id)
    return PlaceResult(place, here.spend, fire, coast, fire_m, here)


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
                             f"Cash covers {months_text(have)} (goal: {months}).", unit="months"))

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
