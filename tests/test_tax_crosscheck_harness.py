"""The dev-only tax cross-check harness (tools/tax_crosscheck).

The pure-Python checks always run. The end-to-end run needs Node and the BPM tax
calculator page (not stored in the repo): set BPM_TAX_SOURCE to its path, or the test
is skipped.
"""
import ast
import importlib.util
import os
import shutil
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HARNESS = os.path.join(_ROOT, "tools", "tax_crosscheck")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import state_tax_data  # noqa: E402


def _load_driver():
    spec = importlib.util.spec_from_file_location(
        "tax_crosscheck_driver", os.path.join(_HARNESS, "crosscheck.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_driver_never_imports_the_app():
    """The driver must not be able to change the app's config: only the per-fixture
    child process imports retirement_sim."""
    with open(os.path.join(_HARNESS, "crosscheck.py")) as fh:
        tree = ast.parse(fh.read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert "retirement_sim" not in imported


def test_grid_covers_the_required_states_and_statuses():
    drv = _load_driver()
    assert set(drv.GRID_STATES) <= set(state_tax_data.STATES)
    # CA, a no-tax state, flat taxes, a high-tax state
    assert {"CA", "TX", "PA", "IL", "NJ"} <= set(drv.GRID_STATES)
    fixtures = drv.build_fixtures(drv.GRID_STATES)
    grid = [f for f in fixtures if f["group"] == "grid"]
    assert {f["status"] for f in grid} == {"S", "MFJ", "HOH"}
    assert {f["mix"] for f in grid} == {"W2", "ORD_LTCG", "ORD_LTCG_SS"}
    assert len(grid) == len(drv.GRID_STATES) * 3 * 4
    ids = [f["id"] for f in fixtures]
    assert len(ids) == len(set(ids))
    edge = {f["id"] for f in fixtures if f["group"] == "edge"}
    assert any("niit" in i for i in edge) and any("irmaa" in i for i in edge)
    assert any("senior" in i for i in edge) and any("hoh-24" in i for i in edge)


def test_every_changed_state_is_in_the_grid():
    """Every row whose table is not a plain copy of the old 2024 one is in the grid."""
    drv = _load_driver()
    changed = {"AR", "CO", "GA", "HI", "IA", "ID", "IN", "KY", "LA", "MA", "MD", "ME", "MN",
               "MO", "MS", "MT", "NC", "ND", "NE", "NM", "NY", "OH", "OK", "OR", "RI", "SC",
               "UT", "VA", "VT", "WI", "WV"}
    assert changed <= set(drv.GRID_STATES)


@pytest.mark.skipif(not shutil.which("node") or not os.environ.get("BPM_TAX_SOURCE"),
                    reason="needs node and BPM_TAX_SOURCE (the BPM tax calculator page)")
def test_harness_runs_clean_and_leaves_the_config_alone(tmp_path):
    before = (cfg.STATE_CHOICE, cfg.FILING_STATUS, cfg.YOUR_AGE, cfg.CURRENT_YEAR,
              repr(state_tax_data.STATES["GA"]), cfg.state_tax_rules)
    report = tmp_path / "REPORT.md"
    proc = subprocess.run(
        [sys.executable, os.path.join(_HARNESS, "crosscheck.py"), "--states", "quick",
         "--report", str(report), "--work-dir", str(tmp_path / "work")],
        capture_output=True, text=True, env=dict(os.environ))
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-1500:]
    text = report.read_text()
    assert "reproduces its verified figures: **yes**" in text
    assert "reproduce the federal, state, credit and payroll parts: **yes**" in text
    assert "Unexplained differences: **0**" in text
    after = (cfg.STATE_CHOICE, cfg.FILING_STATUS, cfg.YOUR_AGE, cfg.CURRENT_YEAR,
             repr(state_tax_data.STATES["GA"]), cfg.state_tax_rules)
    assert before == after
