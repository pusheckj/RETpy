"""Tests for ui/utils/persist.py: what the app keeps in the browser tab and on the
device, which copy wins at start-up, and how a copy is put back.

Pure helpers first, then the restore itself against a fake session, then AppTest
runs of the real app with a pre-seeded browser answer (the browser round trip is
covered by tests/e2e/test_refresh_persistence.py)."""
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.conftest import load_sample_household  # noqa: E402
from utils import device_store as ds  # noqa: E402
from utils import persist  # noqa: E402
from utils.profile_io import deserialize_overrides, serialize_overrides  # noqa: E402

FIXTURE = os.path.join(_ROOT, "tests", "fixtures", "retpy_v1.json")
APP = os.path.join(_ROOT, "ui", "app.py")
SIM_OPTIONS = [500, 1000, 5000, 10000, 25000]


class State(dict):
    """A stand-in for st.session_state (attribute access too)."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


class FakeSt:
    def __init__(self, **state):
        self.session_state = State(state)


@pytest.fixture
def picker(monkeypatch):
    """``picker(monkeypatch, profile_path)`` starts "a server" for the owner: the profile picker
    is imported again, so it reads the profile file now and keeps those bytes until the next call.
    The module is put back to a no-profile import after the test."""
    import importlib
    from components import profile_picker

    def restart(mp, path):
        mp.setenv("RETIREMENT_SIM_PROFILE", str(path))
        mp.delenv("RETIREMENT_SIM_HOSTED", raising=False)
        importlib.reload(profile_picker)
        return profile_picker
    yield restart
    monkeypatch.undo()
    monkeypatch.setenv("RETIREMENT_SIM_PROFILE", os.devnull + ".none")
    importlib.reload(profile_picker)
    monkeypatch.undo()


def _planner_state(**extra):
    ov = load_sample_household()
    state = {"app_mode": "full", "user_overrides": ov, "profile": "Mid-career couple (40, kids)",
             "si_comp_customized": True, "setup": {"status": "done", "step": 3, "seen": ["age"], "checkup": None},
             "simple_inputs": {"age": 40}, "remember_device": False, "_full_touched": True}
    state.update(extra)
    return State(state)


# --------------------------------------------------------------------------
# pick(): which copy wins
# --------------------------------------------------------------------------

class TestPick:
    TAB = {"mode": "full", "remember": False}
    DEV = {"mode": "simple", "remember": True}

    def test_tab_beats_device(self):
        assert persist.pick(self.TAB, self.DEV, None) == ("tab", self.TAB)

    def test_device_used_only_when_remember_is_on(self):
        assert persist.pick(None, self.DEV, None) == ("device", self.DEV)
        assert persist.pick(None, {"mode": "simple", "remember": False}, None) == ("none", None)

    def test_nothing_saved(self):
        assert persist.pick(None, None, None) == ("none", None)
        assert persist.pick({}, {}, "abc") == ("none", None)

    def test_owner_copy_with_matching_base_is_kept(self):
        tab = dict(self.TAB, base="aaaa")
        assert persist.pick(tab, None, "aaaa") == ("tab", tab)

    def test_owner_base_mismatch_loads_the_file(self):
        tab = dict(self.TAB, base="aaaa")
        assert persist.pick(tab, self.DEV, "bbbb") == ("file", None)
        dev = dict(self.DEV, base="aaaa")
        assert persist.pick(None, dev, "bbbb") == ("file", None)

    def test_copy_without_base_or_without_a_file_is_kept(self):
        assert persist.pick(self.TAB, None, "bbbb") == ("tab", self.TAB)
        tab = dict(self.TAB, base="aaaa")
        assert persist.pick(tab, None, None) == ("tab", tab)

    def test_newer_schema_counts_as_nothing_saved(self):
        env = {"schema": 2, "payload": {"mode": "full"}}
        assert ds.migrate(env) is None
        assert persist.pick(ds.migrate(env), None, None) == ("none", None)


class TestFileFingerprint:
    """persist.file_fp() is the hash of the bytes the picker read when the server started, not of
    the file on disk now (the planner shows what was loaded)."""

    def test_hash_of_the_bytes_the_picker_loaded(self, tmp_path, monkeypatch, picker):
        f = tmp_path / "p.json"
        f.write_text(serialize_overrides(load_sample_household()))
        picker(monkeypatch, f)
        first = persist.file_fp()
        assert first == persist.file_fp_of(str(f))
        assert isinstance(first, str) and len(first) == 16

    def test_an_edit_while_the_server_runs_does_not_change_it(self, tmp_path, monkeypatch, picker):
        f = tmp_path / "p.json"
        f.write_text(serialize_overrides(load_sample_household()))
        picker(monkeypatch, f)
        first = persist.file_fp()
        f.write_text(serialize_overrides(dict(load_sample_household(), TARGET_RETIREMENT_AGE=49)))
        assert persist.file_fp() == first                     # still the loaded contents
        picker(monkeypatch, f)                                 # a restart
        assert persist.file_fp() != first

    def test_none_when_missing_or_hosted(self, tmp_path, monkeypatch, picker):
        picker(monkeypatch, tmp_path / "nope.json")
        assert persist.file_fp() is None
        f = tmp_path / "p.json"
        f.write_text(serialize_overrides(load_sample_household()))
        picker(monkeypatch, f)
        assert persist.file_fp() is not None
        monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
        assert persist.file_fp() is None


# --------------------------------------------------------------------------
# build_payload()
# --------------------------------------------------------------------------

class TestBuildPayload:
    def test_planner_state_goes_to_both_copies_when_remember_is_on(self):
        state = _planner_state(remember_device=True)
        tab, device, prefs = persist.build_payload(state)
        assert tab["mode"] == "full" and tab["remember"] is True
        assert device["mode"] == "full" and device["remember"] is True
        assert deserialize_overrides(tab["full"]) == deserialize_overrides(device["full"])
        assert tab["comp_customized"] is True
        assert tab["setup"] == {"status": "done", "step": 3, "seen": ["age"], "checkup": None}

    def test_device_copy_only_with_remember(self):
        tab, device, _ = persist.build_payload(_planner_state(remember_device=False))
        assert tab is not None and tab["remember"] is False
        assert device is None

    def test_no_tab_copy_before_a_version_is_chosen(self):
        tab, device, _ = persist.build_payload(State({"app_mode": None}))
        assert tab is None and device is None

    def test_view_state_is_for_the_tab_copy_only(self):
        view = {"main_view": "Spending", "tax_tab_view": "% of income"}
        tab, device, _ = persist.build_payload(_planner_state(remember_device=True, _view_saved=view))
        assert tab["view"] == view
        assert "view" not in device

    def test_never_saved_keys(self):
        state = _planner_state(
            remember_device=True, results={"big": "x" * 5000}, whatif_results={"a": 1},
            sp_uploads={"f": b"raw"}, _bc={"x": 1}, last_run_inputs_hash=123456789,
            _autorun_done=True, _extras_pending=[1], _lz_deepdives=True,
            ay_your_age=41, se_food=900, user_name="x")
        tab, device, prefs = persist.build_payload(state)
        blob = json.dumps([tab, device, prefs])
        for needle in ("results", "whatif", "sp_uploads", "_bc", "last_run_inputs_hash", "123456789",
                       "_autorun_done", "_extras_pending", "_lz_", "ay_your_age", "se_food", "xxxxxxxx"):
            assert needle not in blob, needle

    def test_extras_are_an_allow_list(self):
        state = _planner_state(le_sex="Female", le_age=44, le_conditions=["Diabetes"], ms_rate=3.5,
                               ms_barista=20000, wifc_stock=70, wifc_result={"plot": [1, 2]},
                               ms_use_swr=False, ay_your_age=41, ms_res_abc={"x": 1})
        tab, _, _ = persist.build_payload(state)
        assert tab["extra"] == {"le_sex": "Female", "le_age": 44, "le_conditions": ["Diabetes"],
                                "ms_rate": 3.5, "ms_barista": 20000, "wifc_stock": 70}

    def test_pins_keep_the_newest_ten_and_their_engine_fingerprint(self):
        ov = load_sample_household()
        pins = {f"S{i}": {"summary": {"success_rate": 0.8}, "overrides": dict(ov)} for i in range(12)}
        pins["S11"]["engine_fp"] = "oldmodel"
        tab, _, _ = persist.build_payload(_planner_state(pinned_scenarios=pins))
        assert [p["name"] for p in tab["pins"]] == [f"S{i}" for i in range(2, 12)]
        assert tab["pins"][-1]["engine_fp"] == "oldmodel"
        assert tab["pins"][0]["engine_fp"] == persist.engine_fp()
        assert deserialize_overrides(tab["pins"][0]["overrides"]) == deserialize_overrides(serialize_overrides(ov))

    def test_hash_is_stable_across_two_builds(self):
        state = _planner_state(remember_device=True, _view_saved={"main_view": "Spending"},
                               pinned_scenarios={"A": {"summary": {"x": 1}, "overrides": load_sample_household()}},
                               _appearance_saved={"theme_mode": "🌙 Dark"}, _n_simulations_saved=5000)
        first = persist.build_payload(state)
        import time
        time.sleep(1.1)   # serialize_overrides stamps the second: the payload must not
        second = persist.build_payload(state)
        assert first == second
        assert [ds.payload_hash(p) if p else None for p in first] == [ds.payload_hash(p) if p else None for p in second]

    def test_prefs(self):
        state = _planner_state(_appearance_saved={"theme_mode": "🌙 Dark", "font_choice": "Inter", "junk": 1},
                               _n_simulations_saved=5000)
        _, _, prefs = persist.build_payload(state)
        assert prefs == {"theme_mode": "🌙 Dark", "font_choice": "Inter", "n_simulations": 5000}
        assert persist.build_payload(State({"app_mode": None}))[2] == {}

    def test_numpy_numbers_in_a_pin_summary_are_saved_as_plain_numbers(self):
        np = pytest.importorskip("numpy")
        pins = {"A": {"summary": {"success_rate": np.float64(0.8), "age": np.int64(52)},
                      "overrides": {"YOUR_AGE": 40}}}
        tab, _, _ = persist.build_payload(_planner_state(pinned_scenarios=pins))
        assert tab["pins"][0]["summary"] == {"success_rate": 0.8, "age": 52}


class TestSizeCap:
    def _fat_state(self, n_pins):
        ov = load_sample_household()
        pins = {f"S{i}": {"summary": {}, "overrides": dict(ov)} for i in range(n_pins)}
        return _planner_state(pinned_scenarios=pins, _view_saved={"main_view": "Spending"})

    def test_under_the_cap_nothing_is_dropped(self):
        tab, _, _ = persist.build_payload(self._fat_state(2))
        assert tab["pins"] and tab["view"]

    def test_pins_go_first_then_view_never_the_inputs(self):
        state = self._fat_state(10)
        full = persist.build_payload(state)[0]
        inputs_only = {k: v for k, v in full.items() if k not in ("pins", "view")}
        size_inputs = len(json.dumps(inputs_only))
        size_no_pins = len(json.dumps({k: v for k, v in full.items() if k != "pins"}))
        # a cap between "inputs + view" and "inputs + view + pins": only the pins go
        trimmed = persist.trim(dict(full), cap=size_no_pins + 5)
        assert "pins" not in trimmed and trimmed["view"] == full["view"]
        # a cap below inputs + view: the view goes too, the inputs stay
        trimmed = persist.trim(dict(full), cap=size_inputs + 5)
        assert "pins" not in trimmed and "view" not in trimmed
        assert trimmed["full"] == full["full"]
        # a cap nothing can meet still keeps the inputs
        assert persist.trim(dict(full), cap=10)["full"] == full["full"]

    def test_default_cap_is_200_kb(self):
        assert persist.CAP_BYTES == 200_000


# --------------------------------------------------------------------------
# apply(): putting a copy back
# --------------------------------------------------------------------------

def _v1_payload():
    with open(FIXTURE, encoding="utf-8") as fh:
        return ds.migrate(json.load(fh))


class TestApply:
    def test_v1_copy_restores_with_comp_customized_from_the_fallback(self):
        data = _v1_payload()
        assert "comp_customized" not in data
        st = FakeSt()
        failed = persist.apply(st, data, "device")
        ss = st.session_state
        assert failed == []
        assert ss["app_mode"] == "full"
        assert ss["remember_device"] is True
        assert ss["user_overrides"] == load_sample_household()
        assert ss["si_comp_customized"] is True            # from YOUR_COMPENSATION_BY_AGE
        assert ss["profile"] == ss["profile_selectbox"] == persist.CUSTOM_PROFILE
        assert ss["setup"]["status"] == "done"
        assert ss["simple_inputs"]["age"] == data["simple"]["age"] if "age" in data["simple"] else True

    def test_widgets_are_synced_from_the_overrides(self):
        st = FakeSt()
        persist.apply(st, _v1_payload(), "tab")
        ov = load_sample_household()
        assert st.session_state["ay_target_age"] == ov["TARGET_RETIREMENT_AGE"]

    def test_explicit_comp_customized_wins_over_the_fallback(self):
        data = dict(_v1_payload(), comp_customized=False)
        st = FakeSt()
        persist.apply(st, data, "tab")
        assert st.session_state["si_comp_customized"] is False

    def test_extras_fill_only_missing_keys(self):
        data = dict(_v1_payload(), extra={"le_sex": "Female", "le_age": 50, "ms_rate": 3.5})
        st = FakeSt(le_age=33)
        persist.apply(st, data, "tab")
        assert st.session_state["le_sex"] == "Female"
        assert st.session_state["ms_rate"] == 3.5
        assert st.session_state["le_age"] == 33

    def test_pins_and_view_come_back_from_a_tab_copy_only(self):
        ov = load_sample_household()
        data = dict(_v1_payload(), view={"main_view": "Spending", "tax_tab_view": "% of income", "evil": "x"},
                    pins=[{"name": "A", "overrides": serialize_overrides(ov), "summary": {"success_rate": 0.9},
                           "engine_fp": "old", "saved_at": "2026-11-01T00:00:00Z"}])
        tab_st = FakeSt()
        persist.apply(tab_st, data, "tab")
        pins = tab_st.session_state["pinned_scenarios"]
        assert list(pins) == ["A"] and pins["A"]["engine_fp"] == "old"
        assert pins["A"]["overrides"] == deserialize_overrides(serialize_overrides(ov))
        assert pins["A"]["summary"] == {"success_rate": 0.9}
        assert tab_st.session_state["_main_view_default"] == "Spending"   # the control opens on it
        assert tab_st.session_state["tax_tab_view"] == "% of income"
        assert "evil" not in tab_st.session_state
        assert tab_st.session_state["_view_saved"]["main_view"] == "Spending"
        dev_st = FakeSt()
        persist.apply(dev_st, data, "device")
        assert "_main_view_default" not in dev_st.session_state
        assert list(dev_st.session_state["pinned_scenarios"]) == ["A"]

    def test_one_bad_part_does_not_drop_the_others(self):
        data = dict(_v1_payload(), simple="not a dict", setup="junk", pins="junk", extra=5)
        st = FakeSt()
        failed = persist.apply(st, data, "tab")
        assert st.session_state["user_overrides"] == load_sample_household()
        assert st.session_state["app_mode"] == "full"
        assert "full" not in failed

    def test_unreadable_inputs_are_reported_and_leave_the_session_alone(self):
        data = dict(_v1_payload(), full="{not json")
        st = FakeSt()
        failed = persist.apply(st, data, "tab")
        assert "full" in failed
        assert "user_overrides" not in st.session_state

    def test_tab_copy_in_simple_mode(self):
        st = FakeSt()
        persist.apply(st, {"mode": "simple", "remember": False, "simple": {"age": 41}}, "tab")
        assert st.session_state["app_mode"] == "simple"
        assert st.session_state["simple_inputs"]["age"] == 41
        assert st.session_state["remember_device"] is False

    def test_prefs_apply_on_their_own(self):
        st = FakeSt()
        persist.apply_prefs(st, {"theme_mode": "🌙 Dark", "font_choice": "Inter", "n_simulations": 5000,
                                 "palette_choice": "no such palette", "x": 1}, SIM_OPTIONS)
        ss = st.session_state
        assert ss["theme_mode"] == "🌙 Dark" and ss["_appearance_saved"]["theme_mode"] == "🌙 Dark"
        assert ss["font_choice"] == "Inter"
        assert ss["n_simulations"] == ss["_n_simulations_saved"] == 5000
        assert "palette_choice" not in ss and "x" not in ss

    def test_n_simulations_outside_the_options_is_ignored(self):
        st = FakeSt()
        persist.apply_prefs(st, {"n_simulations": 7}, SIM_OPTIONS)
        assert "n_simulations" not in st.session_state


class TestTabDefault:
    def test_returns_the_saved_tab_when_it_exists(self):
        st = FakeSt(_view_tabs={"mc-tile-deepdives": "Sensitivity"})
        labels = ["Trajectories", "Withdrawal", "Sensitivity"]
        assert persist.tab_default("mc-tile-deepdives", labels, st.session_state) == "Sensitivity"

    def test_none_when_unknown_or_missing(self):
        st = FakeSt(_view_tabs={"mc-tile-deepdives": "Gone"})
        assert persist.tab_default("mc-tile-deepdives", ["A"], st.session_state) is None
        assert persist.tab_default("other", ["A"], st.session_state) is None
        assert persist.tab_default("g", ["A"], {}) is None


# --------------------------------------------------------------------------
# AppTest: the real app with a pre-seeded browser answer
# --------------------------------------------------------------------------

def _ready_store(tab=None, device=None, prefs=None, view_tabs=None, narrow=None):
    return {"status": "ready", "tab": tab, "device": device, "prefs": prefs,
            "view_client": {"tabs": view_tabs or {}} if view_tabs else None, "narrow": narrow,
            "targets": {"tab": "ok", "device": "ok", "prefs": "ok"}}


def _tab_payload(**over):
    ov = load_sample_household()
    ov["TARGET_RETIREMENT_AGE"] = 52
    payload = {"remember": False, "mode": "full", "full": persist.serialize_full(ov),
               "setup": {"status": "active", "step": 5, "seen": ["age", "income"], "checkup": None},
               "comp_customized": False,
               "view": {"main_view": "Spending"}}
    payload.update(over)
    return payload


def _reset_state_warning(monkeypatch):
    """Streamlit shows its "default value and Session State API" warning once per server process.
    Make it show again, so a test sees it whatever ran before."""
    from streamlit.elements.lib import policies
    monkeypatch.setattr(policies, "_shown_default_value_warning", False)


def _state_warnings(at):
    return [w.value for w in at.warning if "Session State API" in w.value]


def _at(monkeypatch, store, profile_env=None, hosted=True):
    from streamlit.testing.v1 import AppTest, element_tree as et
    _reset_state_warning(monkeypatch)

    def indices(self):      # AppTest cannot rerun a page that holds a segmented control; teach it
        values = [self.value] if isinstance(self.value, str) else self.value
        return [self.options.index(self.format_func(v)) for v in values]
    monkeypatch.setattr(et.ButtonGroup, "indices", property(indices))
    if hosted:
        monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    else:
        monkeypatch.delenv("RETIREMENT_SIM_HOSTED", raising=False)
    if profile_env is not None:
        monkeypatch.setenv("RETIREMENT_SIM_PROFILE", str(profile_env))
    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state[ds.STATE_KEY_PREFIX + ds.DEFAULT_KEY] = store
    return at


def test_tab_copy_is_back_before_the_sidebar_and_autorun(monkeypatch):
    prefs = {"theme_mode": "🌙 Dark", "n_simulations": 5000}
    at = _at(monkeypatch, _ready_store(tab=_tab_payload(), prefs=prefs, view_tabs={"mc-tile-deepdives": "Sensitivity"},
                                       narrow=True))
    at.run()
    assert not at.exception
    ss = at.session_state
    assert ss["app_mode"] == "full"
    assert ss["user_overrides"]["TARGET_RETIREMENT_AGE"] == 52
    assert ss["si_comp_customized"] is False
    assert ss["profile"] == persist.CUSTOM_PROFILE
    assert ss["setup"]["step"] == 5 and ss["setup"]["status"] == "active"
    assert ss["n_simulations"] == 5000 and ss["_n_simulations_saved"] == 5000
    assert ss["theme_mode"] == "🌙 Dark"
    assert ss["_view_saved"]["main_view"] == "Spending"
    assert ss["_view_tabs"] == {"mc-tile-deepdives": "Sensitivity"}
    assert ss["_viewport_narrow"] is True
    assert ss["_device_restored"] is True
    # guided setup is showing, on its saved step, not the welcome screen
    assert not [b for b in at.button if b.label == "Open the retirement planner"]


def _owner_file(tmp_path, age=47):
    profile = tmp_path / "owner.json"
    profile.write_text(serialize_overrides(dict(load_sample_household(), TARGET_RETIREMENT_AGE=age)))
    return profile


def test_restore_runs_before_the_sidebar_draws_and_before_the_autorun_starts(monkeypatch):
    """Setup is done, so the sidebar and the first-load simulation both run on the restore run.
    Both must see the browser copy (target age 52), not the preset the session started from."""
    tab = _tab_payload(setup={"status": "done", "step": 0, "seen": []}, view={})   # the planner view, not Spending
    at = _at(monkeypatch, _ready_store(tab=tab, prefs={"n_simulations": 500}))
    at.run()
    assert not at.exception
    ss = at.session_state
    assert ss["user_overrides"]["TARGET_RETIREMENT_AGE"] == 52
    target = [w for w in at.slider if w.key == "ay_target_age"]
    assert target and target[0].value == 52                    # the sidebar drew the restored value
    assert ss["_autorun_done"] is True and ss["results"] is not None
    from utils.sim_runner import _hashable
    assert ss["last_run_inputs_hash"] == hash((_hashable(ss["user_overrides"]), 500))   # the autorun used it


def test_a_slow_browser_counts_as_continue_and_a_late_answer_still_restores(monkeypatch):
    """After LOAD_TIMEOUT_S the page opens (welcome screen) but the reader stays, so an answer
    that arrives later is used when nothing was edited. Storage is not reported as blocked."""
    import time
    slow = {"status": "loading", "started": time.monotonic() - 10, "read_token": "tok"}
    at = _at(monkeypatch, slow)
    at.run()
    assert not at.exception
    assert [b for b in at.button if b.label == "Open the retirement planner"]     # the page opened
    store = at.session_state[ds.STATE_KEY_PREFIX + ds.DEFAULT_KEY]
    assert store["status"] == "loading" and store["read_token"] == "tok"          # still listening
    assert at.session_state["_device_skip"] is True
    store.update(_ready_store(tab=_tab_payload(setup={"status": "done", "step": 0, "seen": []})))
    store["read_token"] = None
    at.run()
    assert not at.exception
    assert at.session_state["user_overrides"]["TARGET_RETIREMENT_AGE"] == 52
    assert at.session_state["app_mode"] == "full"


def test_a_theme_change_after_forget_does_not_write_the_tab_copy_again(monkeypatch):
    at = _at(monkeypatch, _ready_store(tab=_tab_payload(setup={"status": "done", "step": 0, "seen": []}),
                                       prefs={"n_simulations": 500}))
    at.run()
    assert not at.exception
    store = at.session_state[ds.STATE_KEY_PREFIX + ds.DEFAULT_KEY]
    at.session_state["_forgot_pending"] = True                 # what the Forget button leaves behind...
    store["hashes"]["tab"] = None                              # ...with the browser's copy gone
    store["op"] = None
    at.run()
    assert not at.exception
    assert not (store["op"] or {}).get("tab")                  # nothing was edited: nothing is written
    at.session_state["_appearance_saved"] = {"theme_mode": "🌙 Dark"}
    at.run()
    assert not at.exception
    assert not (store["op"] or {}).get("tab")                  # a new theme is not an edit either


def test_tab_copy_in_simple_mode_beats_the_forced_full_mode_for_the_owner(monkeypatch, tmp_path, picker):
    profile = _owner_file(tmp_path)
    picker(monkeypatch, profile)
    tab = {"remember": False, "mode": "simple", "simple": {"age": 44}, "base": persist.file_fp()}
    at = _at(monkeypatch, _ready_store(tab=tab), profile_env=profile, hosted=False)
    at.run()
    assert not at.exception
    assert at.session_state["app_mode"] == "simple"


def test_owner_base_match_keeps_the_copy_and_mismatch_loads_the_file(monkeypatch, tmp_path, picker):
    profile = _owner_file(tmp_path, age=47)
    picker(monkeypatch, profile)
    base = persist.file_fp()

    keep = _at(monkeypatch, _ready_store(tab=_tab_payload(base=base, setup={"status": "done", "step": 0, "seen": []})),
               profile_env=profile, hosted=False).run()
    assert not keep.exception
    assert keep.session_state["user_overrides"]["TARGET_RETIREMENT_AGE"] == 52
    assert not keep.toast

    stale = _at(monkeypatch, _ready_store(tab=_tab_payload(base="0123456789abcdef")),
                profile_env=profile, hosted=False).run()
    assert not stale.exception
    # the file wins: the browser copy's age (52) is not restored, the file's (47) is shown
    assert stale.session_state["user_overrides"]["TARGET_RETIREMENT_AGE"] == 47
    assert stale.session_state["app_mode"] == "full"                 # the owner's own planner
    assert [t.value for t in stale.toast] == [persist.OWNER_NOTICE]


def test_a_file_edit_while_the_server_runs_keeps_the_browser_copy_until_a_restart(monkeypatch, tmp_path, picker):
    """The planner shows the profile as the server loaded it. An edit to the file changes nothing
    until a restart, so a refresh must keep the browser copy and must not claim the file loaded."""
    profile = _owner_file(tmp_path, age=47)
    picker(monkeypatch, profile)
    tab = _tab_payload(base=persist.file_fp(), setup={"status": "done", "step": 0, "seen": []})

    profile.write_text(serialize_overrides(dict(load_sample_household(), TARGET_RETIREMENT_AGE=49)))
    running = _at(monkeypatch, _ready_store(tab=tab), profile_env=profile, hosted=False).run()
    assert not running.exception
    assert running.session_state["user_overrides"]["TARGET_RETIREMENT_AGE"] == 52     # browser edits kept
    assert not running.toast                                                          # no false notice

    picker(monkeypatch, profile)                                                      # restart: loads the edit
    restarted = _at(monkeypatch, _ready_store(tab=tab), profile_env=profile, hosted=False).run()
    assert not restarted.exception
    assert restarted.session_state["user_overrides"]["TARGET_RETIREMENT_AGE"] == 49   # the file really loaded
    assert [t.value for t in restarted.toast] == [persist.OWNER_NOTICE]


def test_a_broken_copy_shows_the_failed_text_and_drops_the_tab_copy(monkeypatch):
    # inputs are unreadable but the mode and setup parts are fine: those stay, and the toast says
    # "all", not "fresh" (a part restored, so the visitor is told to check, not that nothing came back)
    dropped = []
    real_drop = ds.drop_tab
    monkeypatch.setattr(ds, "drop_tab", lambda st, *a, **k: (dropped.append(True), real_drop(st, *a, **k))[1])
    at = _at(monkeypatch, _ready_store(tab=_tab_payload(full="{not json")))
    at.run()
    assert not at.exception
    assert [t.value for t in at.toast] == [persist.RESTORE_FAILED]
    assert "starting fresh" not in persist.RESTORE_FAILED.lower()
    assert at.session_state["user_overrides"] != {}                 # the preset seed, not a crash
    assert at.session_state["app_mode"] == "full"                   # the parts that restored stay
    assert at.session_state["setup"]["step"] == 5
    store = at.session_state[ds.STATE_KEY_PREFIX + ds.DEFAULT_KEY]
    assert dropped == [True]                                         # the bad copy was removed...
    assert store["tab"] is not None and store["tab"]["full"] != "{not json"   # ...and a fresh one saved


def test_a_profile_switch_does_not_restore_twice(monkeypatch):
    at = _at(monkeypatch, _ready_store(tab=_tab_payload(setup={"status": "done", "step": 0, "seen": []})))
    at.run()
    assert not at.exception
    assert at.session_state["user_overrides"]["TARGET_RETIREMENT_AGE"] == 52
    at.session_state["ay_target_age"] = 49          # an edit in the sidebar
    at.run()
    assert at.session_state["user_overrides"]["TARGET_RETIREMENT_AGE"] == 49
    assert at.session_state["_device_restored"] is True
    for key in ("_view_saved", "_viewport_narrow", "_view_tabs", "_persist_seed_sig"):
        assert key in persist.PRESERVED_KEYS


def test_preserved_keys_are_in_the_profile_picker_preserve_set():
    import inspect
    from components import profile_picker
    src = inspect.getsource(profile_picker)
    for key in persist.PRESERVED_KEYS:
        assert f'"{key}"' in src, key


def test_prefs_apply_for_a_visitor_with_no_saved_inputs(monkeypatch):
    at = _at(monkeypatch, _ready_store(prefs={"theme_mode": "🌙 Dark"}))
    at.run()
    assert not at.exception
    assert at.session_state["theme_mode"] == "🌙 Dark"
    assert [b.label for b in at.button if b.label == "Open the retirement planner"]   # still the welcome screen


def test_restored_main_view_opens_the_spending_view_without_a_streamlit_warning(monkeypatch):
    tab = _tab_payload(setup={"status": "done", "step": 0, "seen": []}, view={"main_view": "Spending"})
    at = _at(monkeypatch, _ready_store(tab=tab))
    at.run()
    assert not at.exception
    assert at.session_state["main_view"] == "Spending"
    assert not [w for w in at.warning if "main_view" in w.value]


class TestReapplyView:
    def test_puts_back_a_choice_whose_widget_was_not_drawn(self):
        state = State(_view_saved={"income_over_time_main_dollars_mode": "Future $", "tax_tab_view": "% of income",
                                   "main_view": "Spending", "evil": "x"})
        state["tax_tab_view"] = "Dollar amount"          # drawn this run: left alone
        persist.reapply_view(state)
        assert state["income_over_time_main_dollars_mode"] == "Future $"
        assert state["tax_tab_view"] == "Dollar amount"
        assert "main_view" not in state and "evil" not in state

    def test_nothing_saved_is_fine(self):
        persist.reapply_view(State())

    def test_a_restored_value_is_assigned_again_on_every_run_until_the_visitor_changes_it(self):
        st = FakeSt()
        persist.apply(st, {"view": {"x_dollars_mode": "Future $"}, "extra": {"le_sex": "Female"}}, "tab")
        state = st.session_state
        assert state["x_dollars_mode"] == "Future $" and state["le_sex"] == "Female"
        sets = []

        class Spy(State):
            def __setitem__(self, k, v):
                sets.append(k)
                super().__setitem__(k, v)
        spy = Spy(state)
        persist.reapply_view(spy)
        assert {"x_dollars_mode", "le_sex"} <= set(sets)          # assigned again, so the browser is told
        spy["x_dollars_mode"] = "Today's $"                       # the visitor picked the other option
        persist.reapply_view(spy)
        assert spy["x_dollars_mode"] == "Today's $"               # their choice stays
        del spy["x_dollars_mode"]                                  # Streamlit forgot it after a run without the widget
        persist.reapply_view(spy)
        assert spy["x_dollars_mode"] == "Today's $"               # and comes back as their choice, not the restored one

    def test_a_widget_already_drawn_in_this_run_is_skipped_not_a_crash(self):
        class Locked(State):
            def __setitem__(self, k, v):
                if k == "le_sex":
                    raise RuntimeError("cannot be modified after the widget is instantiated")
                super().__setitem__(k, v)
        st = FakeSt()
        persist.apply(st, {"extra": {"le_sex": "Female", "le_age": 50}}, "tab")
        locked = Locked(st.session_state)
        persist.reapply_view(locked)
        assert locked["le_age"] == 50


class TestMirrorView:
    def test_a_choice_equal_to_the_widget_default_is_not_saved(self):
        state = State(income_over_time_main_dollars_mode="Today's $", tax_tab_view="Dollar amount",
                      main_view="Retirement plan")
        assert persist.mirror_view(state) == {}

    def test_going_back_to_the_default_removes_the_saved_choice(self):
        state = State(_view_saved={"x_dollars": "Future $"}, x_dollars="Today's $")
        assert persist.mirror_view(state) == {}

    def test_a_choice_that_differs_is_saved_and_a_widget_not_drawn_keeps_its_saved_value(self):
        state = State(_view_saved={"y_dollars": "Future $"}, tax_tab_view="% of income")
        assert persist.mirror_view(state) == {"y_dollars": "Future $", "tax_tab_view": "% of income"}

    def test_first_draw_of_a_tile_does_not_change_the_saved_payload(self):
        before = _planner_state()
        tab_before, _, _ = persist.build_payload(before)
        after = _planner_state(x_dollars_mode="Today's $", tax_tab_view="Dollar amount")
        after["_view_saved"] = persist.mirror_view(after)
        tab_after, _, _ = persist.build_payload(after)
        assert tab_before == tab_after and "view" not in tab_after


class TestMainViewDefault:
    def test_follows_the_last_choice_after_a_run_that_did_not_draw_the_control(self):
        state = State(_view_saved={"main_view": "Spending"}, _main_view_default="Retirement plan")
        assert persist.main_view_default(state) == "Spending"        # control gone from the session
        state["main_view"] = "Spending"
        state["_view_saved"] = {}                                     # saved copy changes, control still drawn
        assert persist.main_view_default(state) == "Spending"        # default must not move while drawn

    def test_default_is_the_planner_view(self):
        assert persist.main_view_default(State()) == "Retirement plan"


# --------------------------------------------------------------------------
# A restored value must show in the browser, not only in the code
# --------------------------------------------------------------------------

def shown(widget):
    """The option the browser draws for a widget. A value that was not sent with ``set_value``
    is invisible to the browser: it draws the widget's own default."""
    proto, options = widget.proto, list(widget.options)
    if widget.type == "radio":
        return options[proto.value if proto.set_value else proto.default]
    if widget.type == "selectbox":
        return proto.raw_value if proto.set_value else options[proto.default]
    return list(proto.raw_values) if proto.set_value else [options[i] for i in proto.default]


_LAZY_SCRIPT = """
import sys
sys.path[:0] = [{ui!r}, {root!r}]
import streamlit as st
from utils import persist
st.session_state.setdefault("n", 0)
st.session_state.n += 1
if st.session_state.n == 1:
    # the restore run: the lazy tile below is not drawn yet
    persist.apply(st, {{"view": {{"x_dollars_mode": "Future $"}},
                       "extra": {{"le_sex": "Female", "le_conditions": ["b", "c"], "wifc_stock": 30}}}}, "tab")
    st.button("load tile")
else:
    persist.reapply_view(st.session_state)
    radio = st.radio("Dollars", ["Today's $", "Future $"], key="x_dollars_mode")
    sex = st.selectbox("Sex", ["Male", "Female"], key="le_sex")
    conds = st.multiselect("Conditions", ["a", "b", "c"], key="le_conditions")
    from utils.slider_input import slider_with_box
    slider_with_box(st, "Stock allocation (%)", 0, 100, 5, key="wifc_stock", unit="%", value=80)
    st.write("BACKEND", radio, sex, ",".join(conds))
    st.button("again")
"""


class TestRestoredValuesShowInTheBrowser:
    @pytest.fixture(autouse=True)
    def _warning_visible(self, monkeypatch):
        _reset_state_warning(monkeypatch)

    def _lazy_app(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_string(_LAZY_SCRIPT.format(ui=_UI, root=_ROOT), default_timeout=60)
        at.run()
        assert not at.exception
        at.button[0].click().run()
        assert not at.exception
        return at

    def test_a_lazy_tile_shows_what_the_code_uses(self):
        at = self._lazy_app()
        assert at.radio[0].value == shown(at.radio[0]) == "Future $"
        assert at.selectbox[0].value == shown(at.selectbox[0]) == "Female"
        assert at.multiselect[0].value == shown(at.multiselect[0]) == ["b", "c"]
        slider = at.slider[0]                                  # what-if inputs (slider with a typed box)
        assert slider.value == 30 and list(slider.proto.value) == [30] and slider.proto.set_value
        assert at.number_input[0].value == 30

    def test_the_shown_choice_survives_the_next_rerun_and_a_change_wins(self):
        at = self._lazy_app()
        at.button[0].click().run()                                    # "again": a rerun, nothing edited
        assert at.radio[0].value == shown(at.radio[0]) == "Future $"
        at.radio[0].set_value("Today's $").run()
        assert at.radio[0].value == shown(at.radio[0]) == "Today's $"
        at.button[0].click().run()
        assert at.radio[0].value == "Today's $"                       # not overwritten by the restored value
        assert at.selectbox[0].value == shown(at.selectbox[0]) == "Female"


def _ready_planner_tab(**over):
    """Setup finished, on the planner view (not Spending)."""
    over.setdefault("view", {})
    return _tab_payload(setup={"status": "done", "step": 0, "seen": []}, **over)


def _draw_lazy_tile(at, flag, found):
    """Open a lazy tile (the browser does this by scrolling to it). Finishing a simulation closes
    every tile again, and the first-load queue can finish after the restore run, so ask again."""
    for _ in range(4):
        at.session_state[flag] = True
        at.run()
        assert not at.exception
        widgets = found(at)
        if widgets:
            return widgets
    return []


def test_the_income_tile_radio_shows_future_dollars_after_a_restore(monkeypatch):
    """The real app: the restore run does not draw the income tile; the radio draws on a later
    run, and the browser must be told its restored value."""
    tab = _ready_planner_tab(view={"income_over_time_main_dollars_mode": "Future $"})
    at = _at(monkeypatch, _ready_store(tab=tab))
    at.run()
    assert not at.exception
    radios = _draw_lazy_tile(at, "_lz_income",
                             lambda a: [r for r in a.radio if r.key == "income_over_time_main_dollars_mode"])
    assert radios, "the income tile did not draw its radio"
    assert radios[0].value == shown(radios[0]) == "Future $"
    assert not _state_warnings(at)


def test_the_life_expectancy_tile_inputs_show_the_restored_values(monkeypatch):
    tab = _ready_planner_tab(extra={"le_sex": "Female", "le_conditions": ["Diabetes"]})
    from components.life_expectancy_section import CONDITIONS
    cond = next(iter(CONDITIONS))
    tab["extra"]["le_conditions"] = [cond]
    at = _at(monkeypatch, _ready_store(tab=tab))
    at.run()
    assert not at.exception
    _draw_lazy_tile(at, "_lz_lifespan", lambda a: [w for w in a.selectbox if w.key == "le_sex"])
    sex = [w for w in at.selectbox if w.key == "le_sex"]
    conds = [w for w in at.multiselect if w.key == "le_conditions"]
    assert sex and conds, "the life expectancy tile did not draw"
    assert sex[0].value == shown(sex[0]) == "Female"
    assert conds[0].value == shown(conds[0]) == [cond]
    assert not _state_warnings(at)


def test_the_whatif_tile_shows_restored_levers_without_a_streamlit_warning(monkeypatch):
    """The what-if levers are saved even when they equal their defaults. Assigning them again
    before the tile draws must not trip Streamlit's "default value and Session State API" warning."""
    from components.whatif_retirement_curve import _SCENARIOS
    tab = _ready_planner_tab(extra={"wifc_ss": True, "wifc_savings": 0, "wifc_stock": 80.0,
                                    "wifc_scenario": _SCENARIOS[-1]})
    at = _at(monkeypatch, _ready_store(tab=tab))
    at.run()
    assert not at.exception
    drawn = _draw_lazy_tile(at, "_lz_whatif", lambda a: [t for t in a.toggle if t.key == "wifc_ss"])
    assert drawn, "the what-if tile did not draw"
    assert not _state_warnings(at)
    again = _draw_lazy_tile(at, "_lz_whatif", lambda a: [t for t in a.toggle if t.key == "wifc_ss"])
    assert again and not _state_warnings(at)
    box = [w for w in at.selectbox if w.key == "wifc_scenario"][0]
    assert box.value == _SCENARIOS[-1] and shown(box) == box.format_func(_SCENARIOS[-1])


def test_a_non_default_whatif_value_also_shows_without_a_warning(monkeypatch):
    tab = _ready_planner_tab(extra={"wifc_savings": 5000, "wifc_ss": False})
    at = _at(monkeypatch, _ready_store(tab=tab))
    at.run()
    assert not at.exception
    _draw_lazy_tile(at, "_lz_whatif", lambda a: [t for t in a.toggle if t.key == "wifc_ss"])
    assert not _state_warnings(at)
    assert [n for n in at.number_input if n.key == "wifc_savings"][0].value == 5000
    assert [t for t in at.toggle if t.key == "wifc_ss"][0].value is False


def test_a_choice_made_in_the_session_survives_its_tile_closing_and_opening_again(monkeypatch):
    """Finishing a simulation closes every lazy tile. Two runs later the tile opens again.
    The browser must show the choice the code uses (round-2 review, issue 1)."""
    key = "income_over_time_main_dollars_mode"
    at = _at(monkeypatch, _ready_store(tab=_ready_planner_tab()))
    at.run()
    radios = _draw_lazy_tile(at, "_lz_income", lambda a: [r for r in a.radio if r.key == key])
    assert radios
    radios[0].set_value("Future $").run()
    assert at.session_state["_view_saved"].get(key) == "Future $"
    at.session_state["_lz_income"] = False
    at.run()
    at.run()
    at.session_state["_lz_income"] = True
    at.run()
    radio = [r for r in at.radio if r.key == key]
    assert radio and radio[0].value == shown(radio[0]) == "Future $"
    assert not _state_warnings(at)


_CLOSE_REOPEN_SCRIPT = """
import sys
sys.path[:0] = [{ui!r}, {root!r}]
import streamlit as st
from utils import persist
persist.reapply_view(st.session_state)
if st.checkbox("tile open", key="open", value=True):
    st.radio("Dollars", ["Today's $", "Future $"], key="x_dollars_mode")
st.button("rerun")
st.session_state["_view_saved"] = persist.mirror_view(st.session_state)
"""


def test_close_and_reopen_a_tile_with_no_app_around_it():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string(_CLOSE_REOPEN_SCRIPT.format(ui=_UI, root=_ROOT), default_timeout=60)
    at.run()
    at.radio[0].set_value("Future $").run()
    at.checkbox[0].uncheck().run()
    at.button[0].click().run()
    at.checkbox[0].check().run()
    assert at.radio[0].value == shown(at.radio[0]) == "Future $"
    at.radio[0].set_value("Today's $").run()          # a change after the reopen still wins
    at.button[0].click().run()
    assert at.radio[0].value == shown(at.radio[0]) == "Today's $"


# --------------------------------------------------------------------------
# Loading a file (or switching profile) wipes the inputs, and a restored value must not return
# --------------------------------------------------------------------------

_RESET_SCRIPT = """
import sys
sys.path[:0] = [{ui!r}, {root!r}]
import streamlit as st
from utils import persist
from utils.widget_sync import reset_input_widget_state
st.session_state.setdefault("n", 0)
st.session_state.n += 1
if st.session_state.n == 1:
    persist.apply(st, {{"view": {{"x_dollars_mode": "Future $"}},
                       "extra": {{"le_sex": "Female", "ms_rate": 3.5, "ms_barista": 12000}}}}, "tab")
persist.reapply_view(st.session_state)
if st.button("load json"):
    reset_input_widget_state(st)
    st.rerun()
st.selectbox("Sex", ["Male", "Female"], key="le_sex")
st.number_input("Rate", key="ms_rate", min_value=0.0, max_value=10.0, step=0.25,
                on_change=lambda: st.session_state.__setitem__("_rate_cb", st.session_state["ms_rate"]))
st.number_input("Barista", key="ms_barista", min_value=0, max_value=100000, step=1000)
st.radio("Dollars", ["Today's $", "Future $"], key="x_dollars_mode")
"""


def _reset_app():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string(_RESET_SCRIPT.format(ui=_UI, root=_ROOT), default_timeout=60)
    at.run()
    at.run()
    return at


class TestLoadingAFileAfterARestore:
    def test_restored_values_show_before_the_load(self):
        at = _reset_app()
        assert at.selectbox[0].value == "Female"
        assert [n for n in at.number_input if n.key == "ms_rate"][0].value == 3.5
        assert [n for n in at.number_input if n.key == "ms_barista"][0].value == 12000

    def test_a_load_clears_the_restored_values_for_good(self):
        at = _reset_app()
        at.button[0].click().run()
        assert at.selectbox[0].value == "Male"
        assert "ms_rate" not in at.session_state or [n for n in at.number_input
                                                     if n.key == "ms_rate"][0].value == 0.0
        at.run()
        assert at.selectbox[0].value == "Male"
        assert [n for n in at.number_input if n.key == "ms_rate"][0].value == 0.0
        assert at.session_state[persist.PENDING_KEY].get("le_sex") is None

    def test_the_view_choice_is_not_an_input_and_stays_after_a_load(self):
        at = _reset_app()
        at.button[0].click().run()
        assert at.radio[0].value == shown(at.radio[0]) == "Future $"

    def test_a_typed_rate_after_the_restore_is_kept(self):
        at = _reset_app()
        [n for n in at.number_input if n.key == "ms_rate"][0].set_value(4.25).run()
        assert [n for n in at.number_input if n.key == "ms_rate"][0].value == 4.25
        assert at.session_state["_rate_cb"] == 4.25                   # its on_change callback ran
        at.run()
        assert [n for n in at.number_input if n.key == "ms_rate"][0].value == 4.25

    def test_a_rate_the_code_writes_wins_over_the_restored_one(self):
        """freedom_milestones writes ms_rate from a callback ("Use my safe rate")."""
        at = _reset_app()
        at.session_state["ms_rate"] = 5.0           # what the callback does, before the next draw
        at.run()
        assert [n for n in at.number_input if n.key == "ms_rate"][0].value == 5.0
        at.run()
        assert [n for n in at.number_input if n.key == "ms_rate"][0].value == 5.0


def test_reset_input_widget_state_drops_pending_values_of_the_inputs_it_clears():
    from utils.widget_sync import reset_input_widget_state
    st = FakeSt()
    persist.apply(st, {"view": {"x_dollars_mode": "Future $"},
                       "extra": {"le_sex": "Female", "ms_rate": 3.5, "wifc_stock": 30}}, "tab")
    assert set(st.session_state[persist.PENDING_KEY]) >= {"le_sex", "ms_rate", "wifc_stock", "x_dollars_mode"}
    reset_input_widget_state(st)
    persist.reapply_view(st.session_state)
    for key in ("le_sex", "ms_rate", "wifc_stock"):
        assert key not in st.session_state
    assert st.session_state["x_dollars_mode"] == "Future $"        # a view choice is not an input


def test_loading_a_json_file_after_a_restore_starts_clean():
    """save_load._apply_restored is the Load button's path: the file's inputs replace the restored ones."""
    from components import save_load
    st = FakeSt()
    persist.apply(st, {"view": {"income_over_time_main_dollars_mode": "Future $"},
                       "extra": {"le_sex": "Female", "ms_rate": 3.5, "wifc_scenario": "pessimistic"}}, "tab")
    persist.reapply_view(st.session_state)
    assert st.session_state["le_sex"] == "Female"
    save_load._apply_restored(st, load_sample_household(), "file.json")
    persist.reapply_view(st.session_state)
    persist.reapply_view(st.session_state)
    for key in ("le_sex", "ms_rate", "wifc_scenario"):
        assert key not in st.session_state, key
    assert st.session_state["income_over_time_main_dollars_mode"] == "Future $"


def test_a_fragment_rerun_saves_the_tab_copy(monkeypatch):
    """A chart's Today's/Future $ switch reruns only its fragment, which skips main()'s save.
    persist.fragment must save after it, so a refresh right after keeps the choice."""
    from types import SimpleNamespace
    from utils import device_store
    calls = []
    st = SimpleNamespace(session_state={}, fragment=lambda fn: fn)
    monkeypatch.setattr(device_store, "in_full_run", lambda _st: False)
    monkeypatch.setattr(persist, "SAVE_HOOK", lambda: calls.append("saved"))
    persist.fragment(st, lambda: calls.append("drawn"))()
    assert calls == ["drawn", "saved"]
    calls.clear()
    monkeypatch.setattr(device_store, "in_full_run", lambda _st: True)   # main() saves a full run
    persist.fragment(st, lambda: calls.append("drawn"))()
    assert calls == ["drawn"]
