"""Your spending vs similar households: BiggerPockets Money's formulas over BLS CE 2025.

The no-area and San Diego totals are BPM's README worked examples (Q3, 4 people, 35-44).
BPM reads BEA raw; the app renormalizes so the US is 1.00, so those checks use
``renormalize=False`` and a separate test pins what the renormalized app shows.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import budget_compare as bc  # noqa: E402

SD = "San Diego-Chula Vista-Carlsbad, CA"
FAMILY = {"YOUR_AGE": 38, "PARTNER_AGE": 37, "STATE_CHOICE": "CA", "YOUR_BASE_SALARY": 90_000,
          "PARTNER_BASE_SALARY": 40_000, "CHILDREN": [{"years_until_birth": -4}, {"years_until_birth": -1}],
          "SPEND_RENT_MONTHLY": 3_000, "MORTGAGE_MONTHLY": 0,
          "SPEND_UTILITIES_MONTHLY": 250, "SPEND_FOOD_MONTHLY": 1_200, "SPEND_TRANSPORT_MONTHLY": 900,
          "SPEND_HEALTH_MONTHLY": 500, "SPEND_DISCRETIONARY_MONTHLY": 700, "SPEND_OTHER_MONTHLY": 500,
          "PARTNER_OTHER_MONTHLY": 0, "HOME_VALUE": 0}


def _total(b):
    return sum(b.values())


def test_national_benchmark_matches_bpms_worked_example():
    b = bc.benchmark("Q3", "4", "35-44", renormalize=False)
    assert {k: round(v) for k, v in b.items()} == {
        "Housing": 19_671, "Utilities": 5_947, "Transportation": 16_339, "Food": 12_988,
        "Healthcare": 6_319, "Entertainment": 2_859, "Apparel": 2_054, "Other": 11_920,
        "Pensions": 11_056}
    assert round(_total(b)) == 89_152


def test_san_diego_benchmark_matches_bpms_worked_example():
    b = bc.benchmark("Q3", "4", "35-44", area_label=SD, renormalize=False)
    assert b["Housing"] == 3_743 * 12                    # HUD 3-bedroom rent, middle fifth
    assert round(b["Utilities"]) == 2_055                # the phone share only
    assert round(b["Transportation"]) == 17_646 and round(b["Food"]) == 14_027
    assert sum(round(v) for v in b.values()) == 114_447   # BPM adds the rounded lines


def test_renormalizing_moves_each_price_group_by_its_own_us_reading():
    raw = bc.benchmark("Q3", "4", "35-44", area_label=SD, renormalize=False)
    norm = bc.benchmark("Q3", "4", "35-44", area_label=SD)
    assert norm["Transportation"] / raw["Transportation"] == pytest.approx(1 / 0.996)   # goods
    assert norm["Healthcare"] / raw["Healthcare"] == pytest.approx(1 / 1.001)           # services
    assert norm["Housing"] == raw["Housing"]            # HUD rents carry no index
    assert norm["Other"] == raw["Other"]                # all-items is 100 already


def test_a_state_with_no_area_uses_its_statewide_row():
    ca = bc.benchmark("Q3", "2", "35-44", state="CA")
    sd = bc.benchmark("Q3", "2", "35-44", state="CA", area_label=SD)
    ms = bc.benchmark("Q3", "2", "35-44", state="MS")
    assert sd["Housing"] > ca["Housing"] > ms["Housing"]
    assert ca["Housing"] == 2_151 * 12                  # HUD 1-bedroom, California statewide
    us = bc.benchmark("Q3", "2", "35-44")
    assert us["Utilities"] > ca["Utilities"]            # no area: the full CE utilities line


def test_size_and_age_are_dampened_by_half():
    q3, x = bc.benchmark("Q3", "4", "35-44", inflate=False), bc.bd.ce_xtab()
    want = x["Q"]["Q3"]["Food"] * (1 + 0.5 * (x["S"]["Food"]["4"] - 1)) * (1 + 0.5 * (x["A"]["Food"]["35-44"] - 1))
    assert q3["Food"] == pytest.approx(want)
    older = bc.benchmark("Q3", "4", "65+", inflate=False)
    assert older["Healthcare"] > q3["Healthcare"] and older["Transportation"] < q3["Transportation"]


def test_a_higher_income_group_has_a_higher_benchmark_in_every_group():
    lo, hi = bc.benchmark("Q2", "3", "35-44", state="TX"), bc.benchmark("Q4", "3", "35-44", state="TX")
    assert all(hi[k] > lo[k] for k in lo)


def test_income_groups_follow_pay():
    assert [bc.quintile_for(x) for x in (0, 30_000, 32_623, 50_000, 90_000, 120_000, 300_000)] == [
        "Q1", "Q1", "Q1", "Q2", "Q3", "Q4", "Q5"]


def test_the_household_is_read_from_the_plan():
    h = bc.household(FAMILY)
    assert (h.adults, h.age, h.income, h.state, h.area) == (2, 38, 130_000, "CA", None)
    assert h.auto_quintile == "Q4"
    solo = bc.household({"YOUR_AGE": 30, "PARTNER_AGE": 0, "CHILDREN": [], "STATE_CHOICE": "Other",
                         "YOUR_BASE_SALARY": 0})
    assert (solo.adults, solo.state, solo.auto_quintile) == (1, None, "Q3")   # no pay: the middle group


def test_household_size_counts_adults_only_because_children_costs_are_not_compared():
    """You compare everyday costs without your children's, so the benchmark must not count them."""
    for kids in ([], [{"years_until_birth": -4}], [{"years_until_birth": -4}, {"years_until_birth": -1}]):
        assert bc.household({**FAMILY, "CHILDREN": kids}).adults == 2
        rows, _ = bc.spending_rows({**FAMILY, "CHILDREN": kids})
        assert rows[-1].typical == bc.spending_rows({**FAMILY, "CHILDREN": []})[0][-1].typical
    assert bc.household({**FAMILY, "PARTNER_AGE": 0}).adults == 1


def test_rows_compare_your_plan_with_the_benchmark_per_month():
    rows, h = bc.spending_rows({**FAMILY, "BENCH_AREA": SD})
    by = {r.label: r for r in rows}
    assert list(by) == ["Housing and utilities", "Food & groceries", "Transportation",
                        "Healthcare premiums", "Fun and discretionary", "Other", "Total"]
    assert by["Housing and utilities"].you == 3_000 + 250        # rent plus utilities
    assert by["Food & groceries"].you == 1_200
    bench = bc.benchmark("Q4", "2", "35-44", state="CA", area_label=SD)
    assert by["Housing and utilities"].typical == pytest.approx((bench["Housing"] + bench["Utilities"]) / 12)
    # Apparel is folded into Fun and discretionary, as the module says.
    assert by["Fun and discretionary"].typical == pytest.approx((bench["Entertainment"] + bench["Apparel"]) / 12)
    # The CE's Pensions line is not compared, so the total is the six rows.
    assert by["Total"].typical == pytest.approx(sum(r.typical for r in rows[:-1]))
    assert by["Total"].typical == pytest.approx((_total(bench) - bench["Pensions"]) / 12)
    assert by["Total"].you == pytest.approx(sum(r.you for r in rows[:-1]))


def test_an_owner_is_compared_by_the_mortgage_payment():
    rows, _ = bc.spending_rows({**FAMILY, "SPEND_RENT_MONTHLY": 0, "MORTGAGE_MONTHLY": 2_400, "HOME_VALUE": 500_000,
                                          "MORTGAGE_YEARS_REMAINING": 20})
    assert {r.label: r for r in rows}["Housing and utilities"].you == 2_400 + 250


def test_the_partners_own_spending_goes_in_other_only_with_a_partner():
    withp, _ = bc.spending_rows({**FAMILY, "PARTNER_OTHER_MONTHLY": 400})
    alone, _ = bc.spending_rows({**FAMILY, "PARTNER_AGE": 0, "PARTNER_OTHER_MONTHLY": 400})
    assert {r.label: r for r in withp}["Other"].you == 500 + 400
    assert {r.label: r for r in alone}["Other"].you == 500


def test_the_typical_band_is_ten_percent_either_side():
    row = bc._row("X", 100.0, 100.0)
    assert (row.low, row.high) == pytest.approx((90.0, 110.0))
    assert row.verdict == "in range"
    assert bc._row("X", 89.9, 100.0).verdict == "below"
    assert bc._row("X", 110.1, 100.0).verdict == "above"
    assert bc._row("X", 90.0, 100.0).verdict == bc._row("X", 110.0, 100.0).verdict == "in range"


def test_a_chosen_income_group_replaces_the_one_from_pay():
    auto, _ = bc.spending_rows(FAMILY)
    top, _ = bc.spending_rows(FAMILY, "Q5")
    assert top[-1].typical > auto[-1].typical
    junk, _ = bc.spending_rows(FAMILY, "Q9")           # not a group: the one from pay
    assert junk[-1].typical == auto[-1].typical


def test_your_statement_figures_replace_the_plan_where_given():
    rows, _ = bc.spending_rows(FAMILY, yours={"Food & groceries": 2_000, "Housing": 3_300})
    by = {r.label: r for r in rows}
    assert by["Food & groceries"].you == 2_000
    assert by["Housing and utilities"].you == 3_300 + 250
    assert by["Transportation"].you == 900             # no statement figure: the plan's


# ---- the Money check-up's one-line comparison

CHECKUP = {"gross_salary_annual": 65_000.0, "partner_salary_annual": 0.0, "married": False, "age": 30,
           "needs_monthly": 2_300.0, "wants_monthly": 1_000.0}


def test_checkup_compares_needs_plus_wants_with_a_household_of_one():
    c = bc.checkup_compare(CHECKUP)
    bench = bc.benchmark("Q3", "1", "25-34")
    assert c.group == "middle 20%"
    assert c.typical == pytest.approx((sum(bench.values()) - bench["Pensions"]) / 12)
    assert c.you == 3_300


def test_checkup_counts_a_married_partner_in_size_and_pay_but_not_when_single():
    married = bc.checkup_compare({**CHECKUP, "married": True, "partner_salary_annual": 80_000.0})
    single = bc.checkup_compare({**CHECKUP, "partner_salary_annual": 80_000.0})
    assert married.group == "fourth 20%" and single.group == "middle 20%"
    assert married.typical > single.typical


def test_checkup_says_nothing_without_pay_or_age():
    assert bc.checkup_compare({**CHECKUP, "gross_salary_annual": 0.0}) is None
    assert bc.checkup_compare({**CHECKUP, "age": 0}) is None


# ---- review fixes

def test_a_row_with_no_figure_of_yours_has_no_verdict():
    assert bc._row("X", 0.0, 500.0).verdict == ""
    rows, _ = bc.spending_rows({**FAMILY, "SPEND_FOOD_MONTHLY": 0})
    by = {r.label: r for r in rows}
    assert by["Food & groceries"].verdict == "" and by["Transportation"].verdict != ""
    none, _ = bc.spending_rows({"YOUR_AGE": 35, "STATE_CHOICE": "CA", "SPEND_RENT_MONTHLY": 0,
                                **{k: 0 for k in FAMILY if k.startswith("SPEND_") and k != "SPEND_RENT_MONTHLY"}})
    assert none[-1].verdict == ""


def test_housing_follows_the_plans_own_rule_for_a_paid_off_home():
    from utils import derived
    paid_off = {**FAMILY, "SPEND_RENT_MONTHLY": 0, "HOME_VALUE": 800_000, "MORTGAGE_MONTHLY": 3_000,
                "MORTGAGE_YEARS_REMAINING": 0}
    rows, _ = bc.spending_rows(paid_off)
    carry = 800_000 * 0.0135 / 12                        # property tax and insurance, as the plan counts them
    assert {r.label: r for r in rows}["Housing and utilities"].you == pytest.approx(carry + 250)
    payment, carrying = derived.housing_parts(paid_off)
    assert payment == 0 and carrying == pytest.approx(800_000 * 0.0135)
    live = {**paid_off, "MORTGAGE_YEARS_REMAINING": 12}
    assert {r.label: r for r in bc.spending_rows(live)[0]}["Housing and utilities"].you == 3_000 + 250
    renter = {**FAMILY, "HOME_VALUE": 0, "MORTGAGE_MONTHLY": 0, "SPEND_RENT_MONTHLY": 2_000}
    assert {r.label: r for r in bc.spending_rows(renter)[0]}["Housing and utilities"].you == 2_000 + 250


def test_a_partner_with_no_spending_figure_gets_the_plans_default_of_1500():
    ov = {k: v for k, v in FAMILY.items() if k != "PARTNER_OTHER_MONTHLY"}
    rows, _ = bc.spending_rows(ov)
    assert {r.label: r for r in rows}["Other"].you == 500 + 1_500


def test_a_hand_picked_income_group_is_saved_in_the_plan():
    auto, _ = bc.spending_rows(FAMILY)
    picked, _ = bc.spending_rows({**FAMILY, "BENCH_INCOME_GROUP": "Q5"})
    assert picked[-1].typical > auto[-1].typical
    junk, _ = bc.spending_rows({**FAMILY, "BENCH_INCOME_GROUP": "Q9"})
    assert junk[-1].typical == auto[-1].typical


def test_income_cutoffs_live_in_one_constant_and_only_the_first_is_sourced():
    assert bc.QUINTILE_UPPER[0] == 32_623
    assert len(bc.QUINTILE_UPPER) == 4 and list(bc.QUINTILE_UPPER) == sorted(bc.QUINTILE_UPPER)


def test_all_items_cpi_comes_from_the_data_files():
    assert bc.CPI_ALL_ITEMS == bc.bd.cpi_factors()["Other"] == 1.0462


def test_checkup_leaves_out_minimum_debt_payments():
    debts = [{"name": "Card", "balance": 5_000.0, "min_payment": 160.0},
             {"name": "Paid", "balance": 0.0, "min_payment": 99.0}]
    c = bc.checkup_compare({**CHECKUP, "debts": debts})
    assert c.you == 3_300 - 160                          # the survey has no debt principal; paid-off debts are not counted
    big = bc.checkup_compare({**CHECKUP, "needs_monthly": 100.0, "wants_monthly": 0.0, "debts": debts})
    assert big.you == 0                                  # never below zero
