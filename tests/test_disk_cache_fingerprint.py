"""The disk cache must miss after an edit to the engine OR to ui/utils
(sim_runner, config_builder ...), which build the engine's inputs and results."""
import os

from ui.utils import disk_cache


def _fp(monkeypatch, root):
    monkeypatch.setattr(disk_cache, "_engine_fp_cache", None)
    monkeypatch.setattr(disk_cache, "_project_root", lambda: str(root))
    return disk_cache.engine_fingerprint()


def _tree(tmp_path):
    for folder in ("retirement_sim", os.path.join("ui", "utils")):
        d = tmp_path / folder
        d.mkdir(parents=True)
        (d / "a.py").write_text("x = 1\n")
    return tmp_path


def test_ui_utils_edit_changes_the_fingerprint(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    before = _fp(monkeypatch, root)
    (root / "ui" / "utils" / "a.py").write_text("x = 2\n")
    assert _fp(monkeypatch, root) != before


def test_engine_edit_changes_the_fingerprint(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    before = _fp(monkeypatch, root)
    (root / "retirement_sim" / "a.py").write_text("x = 2\n")
    assert _fp(monkeypatch, root) != before


def test_same_source_same_fingerprint(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    assert _fp(monkeypatch, root) == _fp(monkeypatch, root)


def test_a_data_table_edit_changes_the_fingerprint(tmp_path, monkeypatch):
    """Healthcare prices by area live in JSON under retirement_sim/data: new vintage, new results."""
    root = _tree(tmp_path)
    data = root / "retirement_sim" / "data" / "healthcare" / "2027"
    data.mkdir(parents=True)
    (data / "age_factors.json").write_text('{"0": 0.765}')
    before = _fp(monkeypatch, root)
    (data / "age_factors.json").write_text('{"0": 0.8}')
    assert _fp(monkeypatch, root) != before
