"""The server's in-memory result caches must not hold a visitor's raw inputs in
their keys (hosted: the caches are shared across sessions). Keys are a sha256
of the inputs, a repeat of the same inputs still hits, and the old privacy
strings are gone from the UI."""
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_ROOT, "ui"), _ROOT]

from utils import sim_runner as sr  # noqa: E402

MARKER_INT = 7_654_321
MARKER_STR = "zz-distinctive-note-48151623"
BASE = {"YOUR_AGE": 50, "PARTNER_AGE": 0, "YOUR_401K": MARKER_INT,
        "SPEND_RENT_MONTHLY": 1_500, "MARKER_NOTE": MARKER_STR}
KW = dict(n_simulations=60, target_retirement_age=55, scan_age_range=(55, 56, 1))


def _atoms(obj):
    """Every leaf value inside nested tuples/lists/dicts, keys included."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _atoms(k)
            yield from _atoms(v)
    elif isinstance(obj, (tuple, list, set, frozenset)):
        for v in obj:
            yield from _atoms(v)
    else:
        yield obj


def _holds_marker(key) -> bool:
    for a in _atoms(key):
        if a == MARKER_INT or (isinstance(a, str) and MARKER_STR in a):
            return True
    return False


def _all_memory_keys():
    keys = list(sr._CACHE._data) + list(sr._CACHE._order)
    for cache in sr._SMALL_CACHES:
        keys += list(cache)
    return keys


@pytest.fixture
def hosted(monkeypatch):
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")     # no disk tier in this test
    sr.clear_cache(include_disk=False)
    yield
    sr.clear_cache(include_disk=False)


def test_no_memory_cache_key_holds_the_inputs(hosted):
    sr.run_full_analysis(dict(BASE), **KW)
    keys = _all_memory_keys()
    assert keys, "the run should have filled the caches"
    assert not [k for k in keys if _holds_marker(k)]
    assert all(isinstance(k, str) and re.fullmatch(r"[0-9a-f]{64}", k) for k in keys)


def test_small_cache_keys_are_digests_too(hosted):
    key = (sr._hashable(BASE), 1000, 70)
    sr._small_cache_insert(sr._NW_CACHE, key, {"x": 1})
    assert not [k for k in sr._NW_CACHE if _holds_marker(k)]
    assert sr._small_cache_lookup(sr._NW_CACHE, "networth", key) == {"x": 1}
    sr._small_cache_writer(sr._SWR_CACHE, "swr", key)({"y": 2})
    assert not [k for k in sr._SWR_CACHE if _holds_marker(k)]
    assert sr._small_cache_lookup(sr._SWR_CACHE, "swr", key) == {"y": 2}


def test_identical_inputs_still_hit_the_cache(hosted):
    first = sr.run_full_analysis(dict(BASE), **KW)
    again = sr.plan_full_analysis(dict(BASE), **KW)
    assert again.result is first                  # served from memory, nothing to compute
    other = sr.plan_full_analysis({**BASE, "YOUR_401K": MARKER_INT + 1}, **KW)
    assert other.result is None                   # different inputs miss


def test_clear_cache_empties_the_digest_keyed_caches(hosted):
    sr.run_full_analysis(dict(BASE), **KW)
    sr.clear_cache(include_disk=False)
    assert _all_memory_keys() == []


def test_old_privacy_wording_is_gone_from_the_ui():
    old = ("saved on this device only if you turn on",
           "keep them on this device.")
    hits = []
    for folder, _dirs, files in os.walk(os.path.join(_ROOT, "ui")):
        for name in files:
            if name.endswith((".py", ".md", ".html", ".js")):
                with open(os.path.join(folder, name), encoding="utf-8") as fh:
                    text = fh.read()
                hits += [(name, s) for s in old if s in text]
    assert hits == []


def test_welcome_and_checkup_use_the_new_wording():
    from components import welcome
    html = welcome.privacy_html(hosted=False)
    assert ("Nothing is stored on the server. Your inputs stay in this browser tab, so a "
            "refresh keeps them. Closing the tab clears them unless you turn on "
            "<b>Remember me on this device</b>.") in html
    with open(os.path.join(_ROOT, "ui", "components", "simple_mode.py"), encoding="utf-8") as fh:
        flat = re.sub(r'"\s*\n\s*"', "", fh.read())      # join adjacent string literals
    assert ("Your numbers stay in this tab. Keep them in a file, or turn on "
            "Remember me to keep them after you close it.") in flat
    with open(os.path.join(_ROOT, "ui", "components", "theme_toggle.py"), encoding="utf-8") as fh:
        assert "Display choices such as dark mode are kept in this browser." in fh.read()


def test_hosted_welcome_says_results_stay_in_server_memory(monkeypatch):
    from components import welcome
    sentence = ("To speed things up, recent results stay in server memory for a short time. "
                "They are never written to disk.")
    assert sentence in welcome.privacy_html(hosted=True)
    assert sentence not in welcome.privacy_html(hosted=False)
