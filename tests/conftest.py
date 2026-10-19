"""Shared test helpers.

Tests never read your private "My situation" profile: it lives outside the repo
(~/.config/retirement-sim/my_profile.json) and a clean checkout has none.
Profile-driven tests use the committed, FICTIONAL household in
``fixtures/sample_household.json`` instead. It is a full app export with the
same keys a real saved profile carries, so every input path is still exercised:

* married couple aged 34 and 33, two kids (first next year, second two years
  later), both retiring at 45 (TARGET_RETIREMENT_AGE / PARTNER_RETIREMENT_AGE);
* primary: $180k base + $20k bonus + $120k RSU (bonus + RSU is about 44% of
  total comp), with a year-by-year comp table for ages 34-45; partner: $100k;
* $840k invested; a $600k home with a $400k, 15-year mortgage ($3,800/mo
  all-in);
* a house move at 36 to a $1.0M home with 20% down and a 15-year loan at 6.11%
  plus 1.35%/yr escrow: $800k balance, P&I $6,798.49 + escrow $1,125 = $7,923/mo.
  Either loan is still owed at 42;
* guardrail dicts, return-based spending rules, ACA, LTC, Roth conversions and
  a 100%-stock glide path all switched on.

Derive any number a test pins from this file rather than hard-coding it.
"""
import os
import sys

import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_UI = os.path.join(os.path.dirname(_TESTS), "ui")

SAMPLE_HOUSEHOLD_PATH = os.path.join(_TESTS, "fixtures", "sample_household.json")


def load_sample_household() -> dict:
    """A fresh overrides dict for the sample household, loaded the way the app
    loads a saved profile (``profile_io``), so comp-table keys come back as ints."""
    if _UI not in sys.path:
        sys.path.insert(0, _UI)
    from utils.profile_io import deserialize_overrides

    with open(SAMPLE_HOUSEHOLD_PATH, encoding="utf-8") as fh:
        return deserialize_overrides(fh.read())


@pytest.fixture
def sample_household() -> dict:
    return load_sample_household()
