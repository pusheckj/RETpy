"""Healthcare by area: the data loader and the estimator's price formulas.

Source of the numbers: BiggerPockets Money Healthcare Costs Estimator v3.6.2 (captured
2026-11-25), built from the CMS 2027 Rate PUF, KFF, HHS and Rev. Proc. 2026-26. The Alabama
case (rating area 1, two adults 35, children 5 and 3, MAGI $80,000) is the estimator's own
worked example.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from retirement_sim import healthcare_data as hd  # noqa: E402


# ---------------------------------------------------------------------------
# ZIP -> area (decoder for the shipped base-36 delta ranges)
# ---------------------------------------------------------------------------

def test_zip_resolves_to_a_rating_area():
    assert hd.zip_to_area("35004") == "AL:3"
    assert hd.zip_to_area("90001") == "CA:16"
    assert hd.zip_to_area(" 92101 ") == "CA:19"


def test_zip_in_a_state_exchange_state_falls_back_to_the_state_average():
    # New York has no rating-area crosswalk: the first three digits name the state.
    assert hd.zip_to_area("10001") == "NY:avg"


def test_unknown_or_malformed_zip_is_none():
    for bad in ("", "abc", "1234", "123456", "00000", None, 90210.5):
        assert hd.zip_to_area(bad) is None, bad


def test_decoded_ranges_do_not_overlap_and_count_matches_the_source():
    starts, ends, states, areas = hd.zip_ranges()
    assert len(starts) == 6164
    assert all(starts[i] <= ends[i] for i in range(len(starts)))
    assert all(ends[i] < starts[i + 1] for i in range(len(starts) - 1))


def test_the_shipped_data_is_small_and_leaves_out_the_big_tables():
    folder = hd.DATA_DIR
    names = set(os.listdir(folder))
    assert "zipra_by_zip.json" not in names and "zipra_ranges.json" not in names
    assert sum(os.path.getsize(os.path.join(folder, n)) for n in names) < 200_000


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

AL1 = "AL:1"


def test_alabama_fixture_prices_from_the_loader():
    area = hd.area("AL:1")
    silver = hd.household_monthly(area, [35, 35], [5, 3], plan="silver")
    bronze = hd.household_monthly(area, [35, 35], [5, 3], plan="bronze")
    assert silver == pytest.approx(2134.11, abs=0.005)
    assert bronze == pytest.approx(1287.61, abs=0.005)


def test_alabama_credit_and_out_of_pocket_from_the_loader():
    fpl4 = hd.fpl(4)
    assert fpl4 == 33_000
    pct = hd.applicable_pct(80_000 / fpl4)
    assert pct == pytest.approx(0.08375, abs=1e-5)          # the estimator shows 8.375%
    bench = 12 * hd.household_monthly(hd.area("AL:1"), [35, 35], [5, 3], plan="silver")
    assert bench - 80_000 * pct == pytest.approx(18_909.16, abs=0.01)
    assert hd.household_oop([35, 35, 5, 3], plan="silver") == 3_200
    assert hd.household_oop([35, 35, 5, 3], plan="bronze") == pytest.approx(4_160)


def test_state_age_curve_is_used_where_filed():
    area = hd.area("UT:1")                     # Utah files its own curve (flat 27-35)
    s21 = area["entry"]["s21"]
    assert hd.rate_at_age(area, 30, "silver") == pytest.approx(s21 * 1.39)
    assert hd.rate_at_age(area, 35, "silver") == pytest.approx(s21 * 1.39)


def test_federal_curve_states_interpolate_in_factor_space_not_age_space():
    area = hd.area("TX:1")
    e = area["entry"]
    f = hd.age_factors()
    t = (f[45] - f[40]) / (f[50] - f[40])
    assert hd.rate_at_age(area, 45, "silver") == pytest.approx(e["s40"] + t * (e["s50"] - e["s40"]))
    # Linear in age would give the 50% point: the two answers must differ.
    assert hd.rate_at_age(area, 45, "silver") != pytest.approx(0.5 * (e["s40"] + e["s50"]), rel=1e-3)
    # Every filed anchor is hit exactly.
    for age, key in ((21, "s21"), (30, "s30"), (40, "s40"), (50, "s50"), (60, "s60"), (64, "s64")):
        assert hd.rate_at_age(area, age, "silver") == pytest.approx(e[key])


def test_no_premium_from_age_65():
    assert hd.rate_at_age(hd.area("AL:1"), 65, "silver") == 0


def test_only_the_three_oldest_children_under_21_are_charged():
    area = hd.area("TX:2")
    three = hd.household_monthly(area, [40, 40], [15, 12, 9])
    four = hd.household_monthly(area, [40, 40], [15, 12, 9, 2])
    assert four == pytest.approx(three)
    # A fourth child older than the others replaces the youngest of the three.
    older = hd.household_monthly(area, [40, 40], [19, 15, 12, 9])
    assert older > three


def test_children_pay_the_child_age_factors_not_a_flat_amount():
    area = hd.area("TX:2")
    young = hd.household_monthly(area, [40], [3])
    teen = hd.household_monthly(area, [40], [19])
    adult = hd.household_monthly(area, [40], [])
    assert teen > young > adult


def test_young_adult_dependents_21_to_25_pay_adult_rates():
    area = hd.area("TX:2")
    assert (hd.household_monthly(area, [40], [23])
            == pytest.approx(hd.household_monthly(area, [40, 23], [])))


def test_bronze_is_the_silver_price_times_the_bronze_to_silver_ratio():
    area = hd.area("TX:2")
    e = area["entry"]
    for ages in ([30], [40, 38], [60]):
        assert (hd.household_monthly(area, ages, [], "bronze")
                == pytest.approx(hd.household_monthly(area, ages, [], "silver") * e["b21"] / e["s21"]))


def test_new_york_is_community_rated_with_family_tiers():
    area = hd.area("NY:avg")
    single = hd.household_monthly(area, [30], [])
    assert hd.household_monthly(area, [62], []) == pytest.approx(single)       # age never enters
    assert hd.household_monthly(area, [30, 30], []) == pytest.approx(2 * single)
    assert hd.household_monthly(area, [30], [4]) == pytest.approx(1.70 * single)
    assert hd.household_monthly(area, [30, 30], [4, 6]) == pytest.approx(2.85 * single)
    vt = hd.area("VT:avg")
    assert (hd.household_monthly(vt, [30, 30], [4]) / hd.household_monthly(vt, [30], [])
            == pytest.approx(2.81))


def test_california_prices_by_covered_california_group():
    metro = hd.area("CA:19")
    assert hd.rate_at_age(metro, 40, "silver") == pytest.approx(439.07 * 1.278)
    assert hd.rate_at_age(hd.area("CA:19d"), 40, "silver") > hd.rate_at_age(metro, 40, "silver")


def test_a_state_average_weights_rating_areas_by_plan_count():
    avg = hd.area("AL:avg")["entry"]
    areas = [a for a in hd._ffe()["AL"].values()]
    want = sum(a["s40"] * a["n"] for a in areas) / sum(a["n"] for a in areas)
    assert avg["s40"] == pytest.approx(want)
    # Utah files one curve in every area, so the average keeps it.
    assert hd.area("UT:avg")["entry"].get("curve") == "UT"


def test_every_state_and_dc_has_prices():
    names = hd.state_names()
    assert len(names) == 51
    for code in names:
        a = hd.area(hd.state_average_key(code))
        assert hd.rate_at_age(a, 40, "silver") > 300, code


def test_labels_name_the_state_and_area():
    assert hd.area_label("AL:3") == "Alabama, rating area 3"
    assert hd.area_label("CA:19") == "California, Covered California region 19, price group 19"
    assert hd.area_label("CA:19d") == "California, Covered California region 19, price group 19d"
    assert hd.area_label("GA:avg") == "Georgia, statewide average"
    assert hd.area_label("nonsense") == ""


def test_bad_keys_do_not_resolve():
    for bad in ("", "AL", "ZZ:1", "AL:99", None, 5):
        assert hd.area(bad) is None, bad


def test_out_of_pocket_follows_the_age_curve():
    assert hd.oop_at_age(0) == 400 and hd.oop_at_age(17) == 400
    assert hd.oop_at_age(35) == 1_200 and hd.oop_at_age(64) == 3_600
    assert hd.oop_at_age(32) == pytest.approx(1_050 + 2 / 5 * 150)
    assert hd.oop_at_age(65) == 0


def test_alaska_and_hawaii_have_their_own_poverty_guidelines():
    assert hd.fpl(1) == 15_960 and hd.fpl(4) == 33_000
    assert hd.fpl(1, "AK") == 19_950 and hd.fpl(3, "HI") == 18_360 + 2 * 6_530


def test_family_tier_areas_have_no_child_price():
    assert hd.reference_prices("NY:avg")["child"] is None
    assert hd.reference_prices("VT:avg")["child"] is None
    assert hd.reference_prices("AL:1")["child"] > 0


def test_the_source_note_is_plain_sentences():
    note = hd.SOURCE_LINE
    assert ";" not in note and "PUF" not in note and "BiggerPockets Money" in note
    assert all(len(sentence.split()) <= 20 for sentence in note.split(". "))
