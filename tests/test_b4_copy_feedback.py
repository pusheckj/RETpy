"""Batch b4: one name per metric, run-health warnings, plain what-if copy,
a load message that survives the rerun, and the narrow-phone mode switch."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "ui"))

COMPONENTS = os.path.join(_ROOT, "ui", "components")
CSS = open(os.path.join(_ROOT, "ui", "styles", "theme.css"), encoding="utf-8").read()


class _Rec:
    """Records the text each st call receives."""

    def __init__(self):
        self.calls = []
        self.session_state = {}

    def __getattr__(self, name):
        def _call(*args, **kwargs):
            self.calls.append((name, args))
            return _Rec()
        return _call

    def columns(self, n):
        return [self for _ in range(n if isinstance(n, int) else len(n))]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def text(self, kind):
        return " ".join(str(a[0]) for k, a in self.calls if k == kind and a)


def _results(**pr):
    base = {"median_final": 1_000_000.0, "p10_final": 200_000.0, "success_rate": 0.85,
            "retirement_age": 50}
    return {"primary_result": {**base, **pr}, "config_snapshot": {"PLAN_UNTIL_AGE": 90}}


def test_metric_names_are_the_same_everywhere():
    for name in ("sensitivity_tab", "scenario_compare", "stress_presets", "what_if_pane"):
        src = open(os.path.join(COMPONENTS, name + ".py"), encoding="utf-8").read()
        for old in ("Median ending balance", "P10 ending balance", "Median final\"", "P10 final"):
            assert old not in src, f"{name} still says {old!r}"
        if name != "sensitivity_tab":
            assert "Median final portfolio" in src


def test_stats_row_warns_about_failed_runs():
    from components import stats_row
    st = _Rec()
    stats_row.render(st, _results(sim_errors=3, sim_first_error="ValueError: boom"))
    msg = st.text("warning")
    assert "3" in msg and "ValueError: boom" in msg


def test_stats_row_notes_synthetic_trajectory():
    from components import stats_row
    st = _Rec()
    stats_row.render(st, _results(trajectory_is_synthetic=True))
    assert "estimates" in st.text("info")


def test_stats_row_silent_without_the_keys():
    from components import stats_row
    st = _Rec()
    stats_row.render(st, _results())
    assert not st.text("warning") and not st.text("info")


def test_what_if_copy_and_home_move_labels():
    from components import what_if_pane
    st = _Rec()
    payload = {"scenario": {}, "baseline": {}, "delta": {},
               "active_toggles": ["HOUSE_MOVE_ENABLED", "HOME_EVENTS", "CAR_ONETIME_ENABLED"]}
    what_if_pane.render(st, results=payload)
    html = st.text("markdown")
    assert "toggles" not in html and "events off" in html
    caption = st.text("caption")
    assert "Home moves" in caption and "older plan" not in caption
    assert caption.count("Home move") == 1
    assert what_if_pane._toggle_labels(["HOUSE_MOVE_ENABLED"]) == ["Home move"]


def test_load_message_set_then_shown_on_next_run(monkeypatch):
    from components import save_load

    class Up:
        name = "p.json"
        def getvalue(self):
            return b"{}"

    class St(_Rec):
        staged = True

        def file_uploader(self, *a, **k):
            return Up() if self.staged else None
        def button(self, *a, **k):
            return True
        def expander(self, *a, **k):
            return self
        def rerun(self):
            pass

    monkeypatch.setattr(save_load, "deserialize_overrides", lambda raw: {"YOUR_AGE": 30})
    monkeypatch.setattr(save_load, "serialize_overrides", lambda o: "{}")
    monkeypatch.setattr(save_load, "_apply_restored", lambda st, r, n: None)
    st = St()
    save_load.render(st)
    assert "Loaded 1 inputs from p.json" in st.session_state["_save_load_msg"]
    assert "success" not in [k for k, _ in st.calls]      # not painted before the rerun
    st.staged = False                                      # the new uploader key is empty
    save_load.render(st)                                   # the next run
    assert "Loaded 1 inputs" in st.text("success")
    assert "_save_load_msg" not in st.session_state


def test_mode_switch_fits_a_360px_screen():
    i = CSS.index("@media (max-width: 400px)")
    block = CSS[i:CSS.index("\n}\n", i) + 3]
    assert "st-key-mc-mode-switch" in block and "flex: 1 1 0" in block and "max-width: 100%" in block
