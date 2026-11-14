"""The sourced place-cost data (ui/utils/place_costs.py, November 2026) is complete
and plausible. These checks catch a typo or a half-pasted row, not the sources."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ui"))
sys.path.insert(0, os.path.join(HERE, ".."))

from retirement_sim import state_tax_data  # noqa: E402
from utils import place_costs as pc  # noqa: E402
from utils import places as pl  # noqa: E402

AREAS = list(pc.AREAS.values())


def test_row_counts_and_unique_codes():
    kinds = [a.kind for a in AREAS]
    assert len(AREAS) == 76                      # US + 50 states + DC + 19 metros + 5 abroad
    assert kinds.count(pc.KIND_US) == 1 and kinds.count(pc.KIND_STATE) == 51
    assert kinds.count(pc.KIND_METRO) == 19 and kinds.count(pc.KIND_ABROAD) == 5
    assert len({a.code for a in AREAS}) == len(AREAS)
    assert len({a.name for a in AREAS}) == len(AREAS)
    assert all(a.code == code for code, a in pc.AREAS.items())


def test_every_us_state_and_dc_is_present():
    assert set(state_tax_data.STATES) <= set(pc.AREAS)
    states = {a.code for a in AREAS if a.kind == pc.KIND_STATE}
    assert states == set(state_tax_data.STATES)


@pytest.mark.parametrize("area", AREAS, ids=lambda a: a.code)
def test_each_row_is_plausible(area):
    for v in (area.goods, area.services, area.utilities, area.health):
        assert 0.1 <= v <= 3.0, area
    assert area.price > 0 and area.rent > 0 and area.carry > 0, area
    assert area.carry <= 0.06, area       # Italy's resident main-home tax is 0: insurance alone, 0.05%
    assert area.price % 100 == 0 and area.rent % 10 == 0, area      # rounded as documented
    # Rent is well under the price: a gross yield a place can really have.
    assert 0.002 <= area.rent * 12 / area.price <= 0.12, area


def test_the_us_row_is_the_unit_of_the_indices():
    us = pc.get(pc.US_CODE)
    for v in (us.goods, us.services, us.utilities, us.health):
        assert v == pytest.approx(1.0, abs=1e-9)
    assert us.price == 364_800 and us.rent == 2_240 and us.carry == pytest.approx(0.0201)
    # The states' indices straddle 1.00 (renormalized, not all above or all below).
    for field in ("goods", "services", "utilities", "health"):
        vals = [getattr(a, field) for a in AREAS if a.kind == pc.KIND_STATE]
        assert min(vals) < 1.0 < max(vals), field


def test_carry_includes_insurance():
    # Property tax alone is under 1.6% almost everywhere; Florida's insurance dominates.
    assert pc.get("FL").carry > 0.04 and pc.get("HI").carry < 0.01
    assert pc.get("CA").carry > 0.015              # a new buyer resets Prop 13: not the 0.7% owner rate


def test_high_health_states_and_cheap_abroad_health():
    for code in ("VT", "WV", "WY", "AK"):
        assert pc.get(code).health >= 1.6, code
    assert pc.get("MD").health < 0.7
    for a in AREAS:
        if a.kind == pc.KIND_ABROAD:
            assert a.health < 0.4, a


def test_abroad_places_match_their_cities():
    assert pc.get("X_IT").name == "Italy (Bologna)" and pc.get("X_ES").name == "Spain (Valencia)"
    assert pc.get("X_MX").name == "Mexico (Mérida)" and pc.get("X_TH").name == "Thailand (Chiang Mai)"
    assert pc.get("X_PT").name == "Portugal (Lisbon area)"
    notes = {p.id: p.note for p in pl.BUILT_IN}
    for pid, city in (("portugal", "Lisbon"), ("italy", "Bologna"), ("spain", "Valencia"),
                      ("mexico", "Mérida"), ("thailand", "Chiang Mai")):
        assert city in notes[pid], pid


def test_metro_tax_states_are_real_and_metros_share_their_states_health():
    for p in AREAS:
        if p.kind == pc.KIND_METRO:
            assert pl.normalize_tax(p.tax) == p.tax and p.tax != "same", p
    assert pc.get("M_LAX").health == pc.get("CA").health
    assert pc.get("M_NYC").health == pc.get("NY").health
