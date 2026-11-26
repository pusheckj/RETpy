"""Tests for ui/utils/file_reader.py, the in-browser file reader that replaces st.file_uploader
for small JSON files (a phone's dropped connection makes the uploader's HTTP PUT fail with 400).

Covers the Python wrapper (value parsing, size limit, None handling), the browser script run in
node against a fake DOM, and AppTests of Save / Load profile and the check-up's "Save or load my
answers" with the component replaced by a stub that returns a chosen value. The real browser
(iPhone Safari) is checked by hand.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils import file_reader as fr  # noqa: E402
from utils.profile_io import serialize_checkup, serialize_overrides  # noqa: E402

HTML = os.path.join(_UI, "components", "file_reader", "index.html")
HARNESS = os.path.join(_ROOT, "tests", "file_reader_harness", "run.js")


def _value(text='{"a": 1}', name="inputs.json", **over):
    v = {"name": name, "text": text, "size": len(text.encode("utf-8")), "nonce": "n1"}
    v.update(over)
    return v


class _St:
    """Enough of ``st`` for read_file: session_state and error."""
    def __init__(self):
        self.session_state = {}
        self.errors = []

    def error(self, msg):
        self.errors.append(msg)


# --------------------------------------------------------------------------
# parse_value
# --------------------------------------------------------------------------

def test_none_means_nothing_chosen():
    assert fr.parse_value(None) == (None, None)


def test_a_good_value_comes_back_clean():
    file, problem = fr.parse_value(_value(name="my\x00inputs.json"))
    assert problem is None
    assert file == {"name": "myinputs.json", "text": '{"a": 1}', "size": 8, "nonce": "n1"}


def test_a_missing_nonce_is_an_empty_string():
    file, _ = fr.parse_value({"name": "a.json", "text": "{}", "size": 2})
    assert file["nonce"] == ""


@pytest.mark.parametrize("bad", [
    "text", 5, [], {}, {"name": "a", "size": 1},
    {"name": "a", "text": 5, "size": 1}, {"name": 5, "text": "x", "size": 1},
    {"name": "a", "text": "x", "size": "1"}, {"name": "a", "text": "x", "size": True},
    {"name": "a", "text": "x", "size": -1},
    {"name": "a", "text": "x", "size": float("inf")}, {"name": "a", "text": "x", "size": float("nan")},
])
def test_malformed_values_are_rejected_in_plain_words(bad):
    file, problem = fr.parse_value(bad)
    assert file is None
    assert problem == "We could not read that file. Choose it again."


def test_oversize_is_rejected_by_the_claimed_size():
    file, problem = fr.parse_value(_value(size=2_000_001), max_bytes=2_000_000)
    assert file is None and problem == "That file is too large. The limit is 2 MB."


def test_oversize_is_rejected_by_the_real_text_even_when_the_size_claim_lies():
    file, problem = fr.parse_value({"name": "a", "text": "é" * 600, "size": 10, "nonce": "x"}, max_bytes=1000)
    assert file is None and "too large" in problem        # 600 characters, 1200 bytes


def test_a_file_exactly_at_the_limit_is_taken():
    file, problem = fr.parse_value({"name": "a", "text": "x" * 1000, "size": 1000, "nonce": "x"}, max_bytes=1000)
    assert problem is None and file["size"] == 1000


def test_the_limit_is_named_in_the_error():
    assert "1.5 MB" in fr.parse_value(_value(size=9_999_999), max_bytes=1_500_000)[1]


# --------------------------------------------------------------------------
# read_file with the component stubbed
# --------------------------------------------------------------------------

@pytest.fixture
def stub(monkeypatch):
    """Replace the component: records each call's kwargs and returns ``stub.value``."""
    class Stub:
        value = None
        calls = []

        def __call__(self, **kw):
            self.calls.append(kw)
            return self.value
    s = Stub()
    s.calls = []
    monkeypatch.setattr(fr, "_component", lambda: s)
    return s


def test_read_file_returns_none_when_nothing_chosen(stub):
    st = _St()
    assert fr.read_file(st, "Upload", key="k") is None
    assert st.errors == []
    call = stub.calls[0]
    assert call["key"] == "k" and call["label"] == "Upload" and call["default"] is None
    assert call["accept"] == ".json,application/json" and call["max_bytes"] == 2_000_000


def test_read_file_returns_the_file(stub):
    stub.value = _value()
    st = _St()
    got = fr.read_file(st, "Upload", key="k")
    assert got["name"] == "inputs.json" and got["text"] == '{"a": 1}'
    assert st.errors == []


def test_read_file_shows_one_error_line_and_returns_none_when_too_large(stub):
    stub.value = _value(size=5_000_000)
    st = _St()
    assert fr.read_file(st, "Upload", key="k", max_bytes=1_000_000) is None
    assert st.errors == ["That file is too large. The limit is 1 MB."]


def test_read_file_passes_the_held_name_and_nonce_so_the_page_can_stop_resending(stub):
    st = _St()
    st.session_state["k"] = _value(name="held.json", nonce="abc")
    fr.read_file(st, "Upload", key="k")
    assert stub.calls[0]["shown"] == "held.json" and stub.calls[0]["shown_nonce"] == "abc"
    st.session_state["k"] = None
    fr.read_file(st, "Upload", key="k")
    assert stub.calls[1]["shown"] is None and stub.calls[1]["shown_nonce"] is None


def test_read_file_confirms_a_value_it_rejected_so_the_page_stops_resending_it(stub):
    st = _St()
    st.session_state["k"] = _value(size=9_000_000, nonce="big")
    stub.value = st.session_state["k"]
    assert fr.read_file(st, "Upload", key="k") is None
    assert stub.calls[0]["shown_nonce"] == "big"


def test_the_component_folder_holds_its_page():
    assert os.path.isfile(os.path.join(str(fr.COMPONENT_DIR), "index.html"))


# --------------------------------------------------------------------------
# The browser script, run in node against a fake DOM
# --------------------------------------------------------------------------

def _run_js(tmp_path, scenario):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    proc = subprocess.run(["node", HARNESS, HTML, str(path)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    out["values"] = [m["value"] for m in out["posted"] if m["type"] == "streamlit:setComponentValue"]
    return out


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
ARGS = {"label": "Upload saved inputs", "accept": ".json", "max_bytes": 1000, "shown": None}
FILE = {"name": "a.json", "size": 7, "text": '{"a":1}'}


@needs_node
def test_js_announces_itself_and_sets_a_height(tmp_path):
    out = _run_js(tmp_path, {"args": ARGS})
    kinds = [(m["type"], m.get("apiVersion")) for m in out["posted"]]
    assert ("streamlit:componentReady", 1) in kinds
    heights = [m["height"] for m in out["posted"] if m["type"] == "streamlit:setFrameHeight"]
    assert heights and all(h > 0 for h in heights)
    assert out["ui"]["label"]["text"] == "Upload saved inputs" and out["ui"]["accept"] == ".json"
    assert out["ui"]["file"]["hidden"] is True and out["ui"]["choose"]["hidden"] is False


@needs_node
def test_js_reads_a_picked_file_and_posts_its_text(tmp_path):
    out = _run_js(tmp_path, {"args": ARGS, "steps": [{"pick": FILE}]})
    (value,) = out["values"]
    assert {k: value[k] for k in ("name", "text", "size")} == FILE
    assert value["nonce"]
    assert out["ui"]["file"]["hidden"] is False and out["ui"]["name"]["text"] == "a.json"
    assert out["ui"]["choose"]["hidden"] is True
    assert out["ui"]["inputValue"] == ""                    # reset, so the same file can be picked again


@needs_node
def test_js_picking_the_same_file_twice_posts_two_different_values(tmp_path):
    out = _run_js(tmp_path, {"args": ARGS, "steps": [{"pick": FILE}, {"pick": FILE}]})
    first, second = out["values"]
    assert first["text"] == second["text"] and first["nonce"] != second["nonce"]


@needs_node
def test_js_drop_reads_the_file_like_a_pick(tmp_path):
    out = _run_js(tmp_path, {"args": ARGS, "steps": [{"drop": FILE}]})
    assert out["values"][0]["text"] == FILE["text"]


@needs_node
def test_js_refuses_an_oversize_file_with_a_plain_error_and_posts_nothing(tmp_path):
    big = {"name": "big.json", "size": 5000, "text": "x"}
    out = _run_js(tmp_path, {"args": ARGS, "steps": [{"pick": big}]})
    assert out["values"] == []
    assert out["ui"]["err"]["hidden"] is False
    assert "too large" in out["ui"]["err"]["text"] and "limit" in out["ui"]["err"]["text"]
    assert out["ui"]["file"]["hidden"] is True


@needs_node
def test_js_clear_posts_none_and_restores_the_drop_zone(tmp_path):
    out = _run_js(tmp_path, {"args": ARGS, "steps": [{"pick": FILE}, {"clear": True}]})
    assert out["values"][-1] is None
    assert out["ui"]["file"]["hidden"] is True and out["ui"]["choose"]["hidden"] is False


@needs_node
def test_js_a_read_failure_shows_a_plain_error(tmp_path):
    out = _run_js(tmp_path, {"args": ARGS, "steps": [{"fail_read": True, "pick": FILE}]})
    assert out["values"] == []
    assert out["ui"]["err"]["hidden"] is False and out["ui"]["err"]["text"] == "We could not read that file. Choose a file and try again."


@needs_node
def test_js_a_rebuilt_frame_shows_the_file_python_still_holds(tmp_path):
    out = _run_js(tmp_path, {"args": {**ARGS, "shown": "held.json"}})
    assert out["ui"]["file"]["hidden"] is False and out["ui"]["name"]["text"] == "held.json"
    assert out["values"] == []                              # showing a name never posts a value


@needs_node
def test_js_resends_the_file_on_a_timer_until_the_app_confirms_it(tmp_path):
    out = _run_js(tmp_path, {"args": ARGS, "steps": [{"pick": FILE}, {"tick": 3}]})
    posts = out["values"]
    assert len(posts) == 4 and len({p["nonce"] for p in posts}) == 1       # same value, same nonce
    assert out["timers"] == 1


@needs_node
def test_js_stops_resending_once_a_render_shows_its_nonce(tmp_path):
    # the nonce is random per run, so the harness builds the confirming render itself (ack_last)
    out = _run_js(tmp_path, {"args": ARGS, "steps": [{"pick": FILE}, {"ack_last": True}, {"tick": 5}]})
    assert len(out["values"]) == 1
    assert out["timers"] == 0


@needs_node
def test_js_a_render_with_another_nonce_does_not_stop_it(tmp_path):
    out = _run_js(tmp_path, {"args": ARGS, "steps": [
        {"pick": FILE}, {"render": {**ARGS, "shown": "old.json", "shown_nonce": "someone-else"}}, {"tick": 2}]})
    assert len(out["values"]) == 3 and out["timers"] == 1


@needs_node
def test_js_resends_at_once_when_the_app_comes_back_from_disabled(tmp_path):
    out = _run_js(tmp_path, {"args": {**ARGS, "disabled": False}, "steps": [
        {"pick": FILE}, {"render": {**ARGS, "disabled": True}}, {"render": {**ARGS, "disabled": False}}]})
    assert len(out["values"]) == 2                                          # no timer tick needed
    assert out["values"][0]["nonce"] == out["values"][1]["nonce"]


@needs_node
def test_js_disabled_flipping_with_nothing_pending_posts_nothing(tmp_path):
    out = _run_js(tmp_path, {"args": {**ARGS, "disabled": False}, "steps": [
        {"render": {**ARGS, "disabled": True}}, {"render": {**ARGS, "disabled": False}}, {"tick": 3}]})
    assert out["values"] == [] and out["timers"] == 0


@needs_node
def test_js_gives_up_after_the_limit_with_a_plain_line_and_never_loops(tmp_path):
    out = _run_js(tmp_path, {"args": ARGS, "steps": [{"pick": FILE}, {"tick": 200}]})
    assert 2 < len(out["values"]) <= 31                                     # one pick + at most 30 resends
    assert out["timers"] == 0
    assert out["ui"]["err"]["hidden"] is False
    assert out["ui"]["err"]["text"] == "Still connecting. Choose the file again if nothing appears."
    assert out["ui"]["name"]["text"] == "a.json"


@needs_node
def test_js_a_new_pick_replaces_the_pending_file(tmp_path):
    other = {"name": "b.json", "size": 7, "text": '{"b":2}'}
    out = _run_js(tmp_path, {"args": ARGS, "steps": [{"pick": FILE}, {"pick": other}, {"tick": 2}]})
    assert [p["name"] for p in out["values"]] == ["a.json", "b.json", "b.json", "b.json"]
    assert out["timers"] == 1


@needs_node
def test_js_clear_is_resent_too_until_python_shows_nothing_held(tmp_path):
    out = _run_js(tmp_path, {"args": ARGS, "steps": [
        {"pick": FILE}, {"ack_last": True}, {"clear": True}, {"tick": 2}]})
    assert [p is None for p in out["values"]] == [False, True, True, True]
    out = _run_js(tmp_path, {"args": ARGS, "steps": [
        {"pick": FILE}, {"ack_last": True}, {"clear": True}, {"render": {**ARGS, "shown": None, "shown_nonce": None}},
        {"tick": 3}]})
    assert [p is None for p in out["values"]] == [False, True]
    assert out["timers"] == 0


@needs_node
def test_js_clearing_a_file_that_never_arrived_stops_resending_it(tmp_path):
    out = _run_js(tmp_path, {"args": ARGS, "steps": [
        {"pick": FILE}, {"clear": True}, {"render": {**ARGS, "shown": None, "shown_nonce": None}}, {"tick": 3}]})
    assert [p is None for p in out["values"]] == [False, True]
    assert out["timers"] == 0


@needs_node
def test_js_the_hint_follows_the_accept_filter(tmp_path):
    out = _run_js(tmp_path, {"args": {**ARGS, "accept": ".csv,text/csv"}})
    assert out["ui"]["hintSmall"]["text"].startswith("CSV file")
    out = _run_js(tmp_path, {"args": {**ARGS, "accept": ""}})
    assert out["ui"]["hintSmall"]["text"].startswith("File")


@needs_node
def test_js_a_file_dropped_outside_the_box_does_not_open_in_the_frame(tmp_path):
    out = _run_js(tmp_path, {"args": ARGS})
    assert out["docEvents"].get("dragover") is True and out["docEvents"].get("drop") is True


@needs_node
def test_js_the_hidden_input_leaves_the_tab_order_while_a_file_is_shown(tmp_path):
    shown = _run_js(tmp_path, {"args": ARGS, "steps": [{"pick": FILE}]})
    assert shown["ui"]["tabIndex"] == -1
    cleared = _run_js(tmp_path, {"args": ARGS, "steps": [{"pick": FILE}, {"clear": True}]})
    assert cleared["ui"]["tabIndex"] == 0


# --------------------------------------------------------------------------
# AppTests: the component replaced by a stub that returns a chosen value
# --------------------------------------------------------------------------

@pytest.fixture
def staged(monkeypatch):
    """key -> value the stub component returns; also records the keys asked for."""
    values, asked = {}, []

    def make():
        def comp(**kw):
            asked.append(kw["key"])
            return values.get(kw["key"])
        return comp
    monkeypatch.setattr(fr, "_component", make)
    monkeypatch.setenv("RETIREMENT_SIM_PROFILE", "/nonexistent/retirement-sim-test-profile.json")
    monkeypatch.delenv("RETIREMENT_SIM_HOSTED", raising=False)
    return values, asked


def _planner_script():
    import sys
    for p in (ROOT_FOR_SCRIPT, UI_FOR_SCRIPT):
        if p not in sys.path:
            sys.path.insert(0, p)
    import streamlit as st
    from components import save_load, profile_picker
    if "user_overrides" not in st.session_state:
        st.session_state["user_overrides"] = {"YOUR_AGE": 41}
    profile_picker.render(st)
    save_load.render(st)


def _planner_app():
    from streamlit.testing.v1 import AppTest
    src = f"ROOT_FOR_SCRIPT = {_ROOT!r}\nUI_FOR_SCRIPT = {_UI!r}\n"
    import inspect
    import textwrap
    body = textwrap.dedent(inspect.getsource(_planner_script)).split("\n", 1)[1]
    return AppTest.from_string(src + textwrap.dedent(body), default_timeout=60)


def _captions(at):
    return [c.value for c in at.caption]


def test_save_load_previews_then_loads_and_clears_the_reader(staged):
    values, asked = staged
    at = _planner_app().run()
    assert not at.exception, at.exception
    assert asked[-1] == "save_load_upload_0"
    assert not [b for b in at.button if b.key == "save_load_apply_btn"]       # nothing staged yet

    values["save_load_upload_0"] = _value(serialize_overrides({"YOUR_AGE": 52}), name="mine.json")
    at.run()
    assert not at.exception, at.exception
    assert any("mine.json" in c and "1 inputs ready to load" in c for c in _captions(at))
    assert at.session_state["user_overrides"]["YOUR_AGE"] == 41               # a preview changes nothing

    at.button(key="save_load_apply_btn").click().run()
    assert not at.exception, at.exception
    assert at.session_state["user_overrides"]["YOUR_AGE"] == 52
    assert at.session_state["profile"] == "Custom (keep current values)"
    assert asked[-1] == "save_load_upload_1"                                   # a fresh, empty reader
    assert not [b for b in at.button if b.key == "save_load_apply_btn"]       # staged file gone
    assert any("Loaded 1 inputs from mine.json" in s.value for s in at.success)
    assert "Last loaded: mine.json" in _captions(at)


def test_save_load_reports_a_file_that_is_not_json(staged):
    values, _ = staged
    values["save_load_upload_0"] = _value("not json at all", name="bad.txt")
    at = _planner_app().run()
    assert not at.exception, at.exception
    assert any("Couldn't read that file" in e.value for e in at.error)
    assert not [b for b in at.button if b.key == "save_load_apply_btn"]


def test_save_load_rejects_a_file_over_the_limit_on_the_server(staged):
    values, _ = staged
    values["save_load_upload_0"] = _value("x", size=50_000_000)
    at = _planner_app().run()
    assert not at.exception, at.exception
    assert any("too large" in e.value for e in at.error)
    assert not [b for b in at.button if b.key == "save_load_apply_btn"]


def test_switching_profile_clears_a_staged_file(staged):
    from components import profile_picker
    values, asked = staged
    values["save_load_upload_0"] = _value(serialize_overrides({"YOUR_AGE": 52}))
    at = _planner_app().run()
    assert [b for b in at.button if b.key == "save_load_apply_btn"]           # staged
    box = at.selectbox[0]
    other = next(n for n in box.options if n != box.value and n != "Custom (keep current values)"
                 and profile_picker.PROFILES.get(n))
    box.select(other).run()
    assert not at.exception, at.exception
    assert asked[-1] != "save_load_upload_0"
    assert not [b for b in at.button if b.key == "save_load_apply_btn"]


def test_the_staged_file_is_never_saved_to_the_tab_copy(staged):
    from utils import persist
    values, _ = staged
    values["save_load_upload_0"] = _value(serialize_overrides({"YOUR_AGE": 52}))
    at = _planner_app().run()
    state = dict(at.session_state.filtered_state)
    state["save_load_upload_0"] = values["save_load_upload_0"]
    state["simple_save_upload_0"] = values["save_load_upload_0"]
    payload, *_ = persist.build_payload(state)
    assert "save_load_upload" not in json.dumps(payload, default=str)
    assert "simple_save_upload" not in json.dumps(payload, default=str)


def _checkup_script():
    import sys
    for p in (ROOT_FOR_SCRIPT, UI_FOR_SCRIPT):
        if p not in sys.path:
            sys.path.insert(0, p)
    import streamlit as st
    from components import simple_mode
    from utils import simple_finance as sf
    simple_mode._render_save_load(st, sf.normalize_inputs(st.session_state.get("simple_inputs")))


def _checkup_app():
    from streamlit.testing.v1 import AppTest
    import inspect
    import textwrap
    src = f"ROOT_FOR_SCRIPT = {_ROOT!r}\nUI_FOR_SCRIPT = {_UI!r}\n"
    body = textwrap.dedent(inspect.getsource(_checkup_script)).split("\n", 1)[1]
    return AppTest.from_string(src + textwrap.dedent(body), default_timeout=60)


def test_checkup_previews_and_loads_saved_answers_then_clears(staged):
    from utils import simple_finance as sf
    values, asked = staged
    at = _checkup_app().run()
    assert not at.exception, at.exception
    assert asked[-1] == "simple_save_upload_0"
    assert not [b for b in at.button if b.key == "simple_save_apply"]

    mine = {**sf.DEFAULT_INPUTS, "gross_salary_annual": 123_456.0}
    values["simple_save_upload_0"] = _value(serialize_checkup(mine), name="answers.json")
    at.run()
    assert not at.exception, at.exception
    at.button(key="simple_save_apply").click().run()
    assert not at.exception, at.exception
    assert at.session_state["simple_inputs"]["gross_salary_annual"] == 123_456.0
    assert asked[-1] == "simple_save_upload_1"
    assert not [b for b in at.button if b.key == "simple_save_apply"]


def test_checkup_says_so_when_the_file_is_a_planner_profile(staged):
    values, _ = staged
    values["simple_save_upload_0"] = _value(serialize_overrides({"YOUR_AGE": 52}))
    at = _checkup_app().run()
    assert not at.exception, at.exception
    assert any("Couldn't read that file" in e.value for e in at.error)
    assert not [b for b in at.button if b.key == "simple_save_apply"]
