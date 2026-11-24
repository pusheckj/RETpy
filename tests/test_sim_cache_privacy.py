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


_TAB_CLAIMS = ("stay in this browser tab", "stay in this tab", "kept in this browser",
               "a refresh keeps them")


def _ui_text():
    for folder, _dirs, files in os.walk(os.path.join(_ROOT, "ui")):
        for name in files:
            if name.endswith((".py", ".md", ".html", ".js")):
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8") as fh:
                    yield path, re.sub(r'"\s*\n\s*"', "", fh.read())   # join adjacent literals


def test_no_copy_promises_tab_persistence_without_a_tab_store():
    """Welcome, check-up and Settings may say inputs survive a refresh only once
    something writes them to the tab (ui/utils/persist.py, package P1). Until
    then that copy is false, so it must not ship."""
    if os.path.exists(os.path.join(_ROOT, "ui", "utils", "persist.py")):
        pytest.skip("the tab store exists: the claim is allowed")
    hits = [(os.path.basename(path), c) for path, text in _ui_text()
            for c in _TAB_CLAIMS if c in text and os.path.basename(path) != "device_store.py"]
    assert hits == []


def test_welcome_privacy_sentence_matches_what_the_app_does():
    if os.path.exists(os.path.join(_ROOT, "ui", "utils", "persist.py")):
        pytest.fail("P1's tab store has landed: its Welcome rewrites this sentence. "
                    "Update the expected sentence here to P1's wording.")
    from components import welcome
    html = welcome.privacy_html(hosted=False)
    assert ("Nothing is stored on the server. Your inputs are saved on this device only if "
            "you turn on <b>Remember me on this device</b>.") in html


def test_hosted_welcome_says_results_stay_in_server_memory(monkeypatch):
    from components import welcome
    sentence = ("To speed things up, recent results stay in server memory for a short time. "
                "They are never written to disk.")
    assert sentence in welcome.privacy_html(hosted=True)
    assert sentence not in welcome.privacy_html(hosted=False)


def test_memory_results_expire_after_the_hosted_ttl(hosted, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(sr, "_mem_now", lambda: clock[0])
    sr.run_full_analysis(dict(BASE), **KW)
    assert sr.plan_full_analysis(dict(BASE), **KW).result is not None
    clock[0] += sr._MEM_TTL_S - 1
    assert sr.plan_full_analysis(dict(BASE), **KW).result is not None   # still inside the TTL
    clock[0] += 2
    assert sr.plan_full_analysis(dict(BASE), **KW).result is None       # expired: recompute
    assert _all_memory_keys() == []                                     # and gone from memory


def test_small_cache_entries_expire_too(hosted, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(sr, "_mem_now", lambda: clock[0])
    key = ("k", 1)
    sr._small_cache_insert(sr._NW_CACHE, key, {"x": 1})
    clock[0] += sr._MEM_TTL_S + 1
    assert sr._small_cache_lookup(sr._NW_CACHE, "networth", key) is None
    assert not sr._NW_CACHE


def test_local_memory_cache_has_no_ttl(monkeypatch):
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    clock = [0.0]
    monkeypatch.setattr(sr, "_mem_now", lambda: clock[0])
    sr._small_cache_insert(sr._NW_CACHE, ("local", 1), {"x": 1})
    clock[0] += 10 * sr._MEM_TTL_S
    assert sr._small_cache_lookup(sr._NW_CACHE, "networth", ("local", 1)) == {"x": 1}
    sr.clear_cache(include_disk=False)


def test_hosting_doc_says_what_the_shared_cache_holds():
    """The cached value keeps the plan's numbers (a snapshot of ages and balances),
    and debts.py still keys on raw values: HOSTING.md must say so."""
    with open(os.path.join(_ROOT, "docs", "HOSTING.md"), encoding="utf-8") as fh:
        text = " ".join(fh.read().split())
    assert "never the inputs themselves" not in text
    assert "starting balances" in text
    assert "debts.py" in text


def test_every_streamlit_data_cache_has_the_hosted_ttl():
    """st.cache_data is process-wide, so hosted it is shared by every visitor. With no
    ttl it would outlive the Welcome's "short time" and HOSTING.md's 30 minutes. No
    ui/ module may use cache_data or cache_resource without ttl=_MEM_TTL_S."""
    import ast
    offenders = []
    for folder, _dirs, files in os.walk(os.path.join(_ROOT, "ui")):
        for name in (n for n in files if n.endswith(".py")):
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                calls = [node] if isinstance(node, ast.Call) else []
                # A bare "@st.cache_data" decorator is an Attribute with no Call.
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    calls += [d for d in node.decorator_list if not isinstance(d, ast.Call)]
                for c in calls:
                    f = c.func if isinstance(c, ast.Call) else c
                    ident = getattr(f, "attr", getattr(f, "id", ""))
                    kws = {k.arg for k in c.keywords} if isinstance(c, ast.Call) else set()
                    if ident in ("cache_data", "cache_resource") and "ttl" not in kws:
                        offenders.append(os.path.relpath(path, _ROOT))
    assert offenders == []


def test_net_worth_projection_cache_expires_after_the_hosted_ttl():
    from components import net_worth_projection_chart as nw
    assert nw.project_net_worth._info.ttl == sr._MEM_TTL_S
