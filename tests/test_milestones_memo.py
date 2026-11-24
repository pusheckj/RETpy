"""milestones.build is memoised on the (frozen) inputs, and callers get a copy."""
import threading

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "ui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.test_milestones import _cost, _inputs  # noqa: E402
from utils import milestones as ms  # noqa: E402
from utils import places as pl  # noqa: E402


def test_build_returns_copies_that_callers_cannot_corrupt():   # copy safety only: also true without a memo
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


def test_build_works_when_an_input_is_unhashable():
    """A set (or array) inside the inputs can not be a memo key: build skips the memo."""
    inp = _inputs(places=(pl.default_place("here"),))
    ms.clear_build_cache()
    expected = ms.build(inp)
    ms.clear_build_cache()
    inp.cost.proceeds[60] = {1, 2}                     # a set inside a mapping: not hashable
    try:
        assert ms.build(inp) is not None
        assert len(ms._BUILD_MEMO) == 0                # skipped, not stored
    finally:
        inp.cost.proceeds.pop(60)
    assert ms.build(inp) == expected


def test_a_hit_and_an_eviction_by_another_session_do_not_collide(monkeypatch):
    """Another session evicts the key right after this one gets its hit. That can only
    happen when the memo is not locked, so the fake evicts only while it is unlocked."""
    class Racy(ms.OrderedDict):
        def get(self, key, default=None):
            value = super().get(key, default)
            if value is not None and not ms._BUILD_LOCK.locked():
                self.pop(key, None)
            return value

    inp = _inputs()
    ms.clear_build_cache()
    expected = ms.build(inp)
    monkeypatch.setattr(ms, "_BUILD_MEMO", Racy(ms._BUILD_MEMO))
    assert ms.build(inp) == expected


def test_build_memo_survives_sessions_evicting_each_other(monkeypatch):
    """A hit in one thread and an eviction of that key in another must not raise."""
    monkeypatch.setattr(ms, "_BUILD_MEMO_MAX", 2)
    monkeypatch.setattr(ms, "_build", lambda inp: ms.Report.__new__(ms.Report))
    monkeypatch.setattr(ms, "_freeze", lambda inp: inp)   # the "inputs" are plain ints here
    ms.clear_build_cache()
    errors = []

    def worker(n):
        try:
            for i in range(400):
                ms.build((n + i) % 5)
        except Exception as e:  # pragma: no cover - the failure being tested
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    assert len(ms._BUILD_MEMO) <= 2
