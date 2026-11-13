"""Every built-in starting household can retire at the age its preset picks.

A preset used to fail at every age: the median household's boxes (family-sized
spending, $3,500 a month for two children) spent more than its $87k of pay, so
the first screen a visitor saw said "Not achieved" at every retirement age."""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from components.profile_picker import PROFILES, PRESET_NAMES  # noqa: E402
from components.sec_income import _build_comp_table  # noqa: E402
from utils import sim_runner as sr  # noqa: E402
from utils.derived import compute_expenses_today, compute_taxes, compute_total_income  # noqa: E402
from utils.expense_categories import CATEGORIES  # noqa: E402

BUILT_IN = [n for n in PROFILES if n in PRESET_NAMES and PROFILES[n]]


def as_the_planner_runs_it(preset: dict) -> dict:
    """The preset plus what the side panel adds on first draw: the expense boxes'
    typical amounts, a rent for a household with no home, and the pay table."""
    ov = dict(preset)
    for c in CATEGORIES:
        if c.partner_only and not ov.get("PARTNER_AGE"):
            continue
        ov.setdefault(c.key, c.default)
    if not ov.get("HOME_VALUE") and not ov.get("MORTGAGE_MONTHLY"):
        ov.setdefault("SPEND_RENT_MONTHLY", 1_500)
    table = _build_comp_table(ov["YOUR_AGE"], ov["TARGET_RETIREMENT_AGE"], ov["YOUR_BASE_SALARY"],
                              ov.get("YOUR_BONUS_AMOUNT", 0), ov.get("YOUR_RSU_AMOUNT", 0),
                              ov.get("YOUR_SALARY_GROWTH_RATE", 0.02))
    ov["YOUR_COMPENSATION_BY_AGE"] = {
        int(r.age): {"base": int(r.base), "bonus": int(r.bonus), "rsu_gross": int(r.rsu_gross),
                     "total_comp": int(r.base + r.bonus + r.rsu_gross),
                     "saved": int((r.base + r.bonus + r.rsu_gross) * 0.2)}
        for r in table.itertuples()}
    return ov


@pytest.mark.parametrize("name", BUILT_IN)
def test_preset_retires_at_its_own_target_age(name):
    ov = as_the_planner_runs_it(PROFILES[name])
    age = ov["TARGET_RETIREMENT_AGE"]
    sr.clear_cache(include_disk=False)
    res = sr.run_full_analysis(ov, n_simulations=150, target_retirement_age=age,
                               scan_age_range=(age, age + 1, 1))
    assert res["success_rate_by_age"][age] >= 0.6, name


def test_median_household_spends_less_than_it_earns():
    ov = as_the_planner_runs_it(PROFILES["Median US 25-year-old household"])
    take_home = compute_total_income(ov) - compute_taxes(ov)["total"]
    children = sum(k["monthly_cost"] for k in ov["CHILDREN"]) * 12
    assert compute_expenses_today(ov) + children < take_home
