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
    def test_hash_of_the_file_bytes(self, tmp_path, monkeypatch):
        f = tmp_path / "p.json"
        f.write_text('{"a": 1}')
        monkeypatch.setenv("RETIREMENT_SIM_PROFILE", str(f))
        monkeypatch.delenv("RETIREMENT_SIM_HOSTED", raising=False)
        first = persist.file_fp()
        assert isinstance(first, str) and len(first) == 16
        f.write_text('{"a": 2}')
        assert persist.file_fp() != first

    def test_none_when_missing_or_hosted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RETIREMENT_SIM_PROFILE", str(tmp_path / "nope.json"))
        monkeypatch.delenv("RETIREMENT_SIM_HOSTED", raising=False)
        assert persist.file_fp() is None
        f = tmp_path / "p.json"
        f.write_text("{}")
        monkeypatch.setenv("RETIREMENT_SIM_PROFILE", str(f))
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


def _at(monkeypatch, store, profile_env=None, hosted=True):
    from streamlit.testing.v1 import AppTest, element_tree as et

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


def test_tab_copy_in_simple_mode_beats_the_forced_full_mode_for_the_owner(monkeypatch, tmp_path):
    profile = tmp_path / "owner.json"
    profile.write_text(serialize_overrides(load_sample_household()))
    base = persist.file_fp_of(str(profile))
    tab = {"remember": False, "mode": "simple", "simple": {"age": 44}, "base": base}
    at = _at(monkeypatch, _ready_store(tab=tab), profile_env=profile, hosted=False)
    at.run()
    assert not at.exception
    assert at.session_state["app_mode"] == "simple"


def test_owner_base_match_keeps_the_copy_and_mismatch_loads_the_file(monkeypatch, tmp_path):
    profile = tmp_path / "owner.json"
    owner = load_sample_household()
    profile.write_text(serialize_overrides(owner))
    base = persist.file_fp_of(str(profile))

    keep = _at(monkeypatch, _ready_store(tab=_tab_payload(base=base, setup={"status": "done", "step": 0, "seen": []})),
               profile_env=profile, hosted=False).run()
    assert not keep.exception
    assert keep.session_state["user_overrides"]["TARGET_RETIREMENT_AGE"] == 52

    stale = _at(monkeypatch, _ready_store(tab=_tab_payload(base="0123456789abcdef")),
                profile_env=profile, hosted=False).run()
    assert not stale.exception
    # the file wins: the browser copy's age (52) is not restored. (The profile picker reads the file
    # when the server starts, so this in-process test cannot see the file's own numbers.)
    assert stale.session_state["user_overrides"]["TARGET_RETIREMENT_AGE"] != 52
    assert stale.session_state["app_mode"] == "full"                 # the owner's own planner
    assert [t.value for t in stale.toast] == [persist.OWNER_NOTICE]


def test_a_broken_copy_shows_the_failed_text_and_starts_fresh(monkeypatch):
    at = _at(monkeypatch, _ready_store(tab=_tab_payload(full="{not json")))
    at.run()
    assert not at.exception
    assert [t.value for t in at.toast] == [persist.RESTORE_FAILED]
    assert at.session_state["user_overrides"] != {}                 # the preset seed, not a crash


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
