"""milestones.build is memoised on the (frozen) inputs, and callers get a copy."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.test_milestones import _cost, _inputs  # noqa: E402
from utils import milestones as ms  # noqa: E402
from utils import places as pl  # noqa: E402


def test_build_memo_returns_equal_reports_that_callers_cannot_corrupt():
    a = ms.build(_inputs())
    b = ms.build(_inputs())                       # equal inputs, built separately
    assert a == b and a is not b
    a.networth.clear()                            # a caller editing its copy ...
    a.markers.append("junk")
    assert ms.build(_inputs()) == b               # ... leaves the cached one alone


def test_build_memo_misses_when_inputs_or_the_place_list_change(monkeypatch):
    runs = []
    real = ms._build
    monkeypatch.setattr(ms, "_build", lambda inp: runs.append(1) or real(inp))
    ms.clear_build_cache()
    ms.build(_inputs())
    ms.build(_inputs())
    assert len(runs) == 1                         # second call served from the memo
    ms.build(_inputs(places=(pl.default_place("here"),)))
    assert len(runs) == 2                         # a changed place list misses
    ms.build(_inputs(rate=0.035))
    assert len(runs) == 3
    ms.build(_inputs(cost=_cost(proceeds={60: 1.0})))
    assert len(runs) == 4                         # a changed mapping inside CostBasis misses
