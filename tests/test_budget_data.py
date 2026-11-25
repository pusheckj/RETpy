"""The public cost-of-living data (ui/data/budget) and its loader.

The files are BiggerPockets Money's Household Spending Comparison v2.4.0 data, copied
unchanged. The counts and the San Diego row are the ones BPM's own README verifies.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import budget_data as bd  # noqa: E402

SD = "San Diego-Chula Vista-Carlsbad, CA"


def test_the_files_have_the_documented_counts():
    assert len(bd.locations()) == 739
    assert len(bd._load("childcare_state_prices")) == 51
    assert len(bd._load("childcare_county_medians")) == 615
    assert len(bd._load("childcare_county_crosswalk")) == 648
    assert set(bd.ce_xtab()["Q"]) == {"Q1", "Q2", "Q3", "Q4", "Q5"}


def test_loader_reads_each_file_once():
    bd._load.cache_clear()
    bd.locations(), bd.locations(), bd.ce_xtab(), bd.ce_xtab()
    info = bd._load.cache_info()
    assert info.misses == 2 and info.hits == 2


def test_san_diego_row_matches_bpms_readme():
    row = bd.area(SD)
    assert (row["ra"], row["rg"], row["rr"], row["rs"]) == (112, 108, 179, 100)
    assert [row[f"f{i}"] for i in range(5)] == [2192, 2335, 2823, 3743, 4526]


def test_price_levels_are_renormalized_so_the_us_is_one():
    row = bd.area(SD)
    raw = bd.price_levels(row, renormalize=False)
    norm = bd.price_levels(row)
    assert raw["rg"] == pytest.approx(1.08)
    assert norm["rg"] == pytest.approx(108 / 99.6)        # BEA's raw US goods index is 99.6
    assert norm["rs"] == pytest.approx(100 / 100.1)       # and other services 100.1
    assert norm["rr"] == pytest.approx(1.79) and norm["ra"] == pytest.approx(1.12)
    assert bd.price_levels(None) == {"ra": 1.0, "rg": 1.0, "rr": 1.0, "rs": 1.0}


def test_area_labels_are_one_states_areas_or_all_without_the_statewide_rows():
    ca = bd.area_labels("CA")
    assert SD in ca and "Bakersfield, CA" in ca
    assert not any(label.endswith("(statewide avg)") for label in ca)
    assert ca == sorted(ca)
    everywhere = bd.area_labels()
    assert len(everywhere) == 739 - 51 and set(ca) <= set(everywhere)


def test_every_state_and_dc_has_a_statewide_row():
    assert bd.statewide("CA")["l"] == "California (statewide avg)"
    assert bd.statewide("dc")["st"] == "DC"
    assert bd.statewide("ZZ") is None and bd.statewide(None) is None


@pytest.mark.parametrize("choice, expected", [("CA", "CA"), ("No state tax", None), ("Other", None),
                                              ("TX", "TX")])
def test_state_code_is_a_state_or_none(choice, expected):
    assert bd.state_code({"STATE_CHOICE": choice}) == expected


def test_picked_area_ignores_a_label_that_is_not_in_the_data():
    assert bd.picked_area({"BENCH_AREA": SD}) == SD
    assert bd.picked_area({"BENCH_AREA": "Atlantis"}) is None
    assert bd.picked_area({}) is None


def test_childcare_prices_by_county_state_and_crosswalk():
    assert bd.county_childcare_prices(SD)[:4] == [19719, 16859, 12616, 11385]
    assert bd.county_childcare_prices("Nowhere") is None
    assert bd.state_childcare_prices("CA")[0] == 16940
    assert bd.state_childcare_prices(None) is None
