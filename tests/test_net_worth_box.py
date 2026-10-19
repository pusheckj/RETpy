"""Test the net-worth box-plot percentile pipeline (sim_runner._networth_percentiles)."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import sim_runner as sr
from utils.plot_theme import beeswarm_xy


def test_networth_percentiles_monotone_full_axis_and_depletion():
    paths = [
        [(40, 100.0), (41, 110.0), (42, 120.0)],
        [(40, 100.0), (41, 90.0)],            # depletes after 41 -> age 42 counts as $0
        [(40, 100.0), (41, 200.0), (42, 300.0)],
        [(40, 100.0), (41, 150.0), (42, 90.0)],
    ]
    out = sr._networth_percentiles(paths)
    # Full, contiguous age axis (union), sorted.
    assert [r["age"] for r in out] == [40, 41, 42]
    # Percentiles are monotone within each age.
    for r in out:
        assert r["p10"] <= r["p25"] <= r["p50"] <= r["p75"] <= r["p90"]
    # Age 40: all paths identical -> zero spread. Age 42: spread exists, and the
    # depleted path drags the low end down (below the min surviving balance 90).
    assert out[0]["p90"] - out[0]["p10"] == 0.0
    assert out[-1]["p90"] - out[-1]["p10"] > 0.0
    assert out[-1]["p10"] < 90.0
    assert sr._networth_percentiles([]) == []


def test_networth_rows_carry_samples():
    paths = [[(40, float(100 + i))] for i in range(200)]  # >80 -> sampled/capped
    out = sr._networth_percentiles(paths)
    assert "samples" in out[0]
    assert 1 <= len(out[0]["samples"]) <= 80  # capped for the point-cloud view


def test_beeswarm_packs_symmetrically_within_half_width():
    # A dense cluster + a sparse one -> fullest bin spans ~2*half_width (violin),
    # points stay within +/- half_width of the center, sparse bin is narrower.
    xs, ys = beeswarm_xy([10.0] * 40 + [20.0] * 4, x_center=50.0, half_width=0.42)
    assert len(xs) == 44
    assert max(abs(x - 50.0) for x in xs) <= 0.42 + 1e-9
    dense_spread = max(x for x, y in zip(xs, ys) if y == 10.0) - min(x for x, y in zip(xs, ys) if y == 10.0)
    sparse_spread = max(x for x, y in zip(xs, ys) if y == 20.0) - min(x for x, y in zip(xs, ys) if y == 20.0)
    assert dense_spread > sparse_spread  # density -> width (the violin shape)
    assert beeswarm_xy([], 1.0) == ([], [])
    assert beeswarm_xy([5.0, 5.0, 5.0], 3.0)[0] == [3.0, 3.0, 3.0]  # identical -> single column
