"""Spending tab, upload mode: in-memory parsing, hosted isolation, session-only storage.

All fixtures are SYNTHETIC — no real statements, names or amounts. The PDFs are
generated with pymupdf inside the tests.
"""
import ast
import builtins
import inspect
import io
import json
import os
import tempfile
from types import SimpleNamespace

import pandas as pd
import pytest

from .test_spending_dashboard import (UI, FIDELITY_CSV, VENMO_CSV, APPLE_CARD_CSV,  # noqa: F401
                                      PERSONAL_RULES)
from utils import spending_parsers as sp  # noqa: E402  (ui/ put on sys.path by the import above)
from utils import spending_rules as sr  # noqa: E402
from components import spending_dashboard as sd  # noqa: E402


@pytest.fixture(autouse=True)
def _local_by_default(monkeypatch, tmp_path):
    """Local mode unless a test opts in to hosted — and never this machine's real settings."""
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")
    monkeypatch.delenv("SPENDING_DATA_DIR", raising=False)
    monkeypatch.setattr(sd, "SETTINGS_PATH", str(tmp_path / "no-settings.json"))
    monkeypatch.setenv("SPENDING_TEST_UI_DIR", os.path.abspath(UI))


# ---------------------------------------------------------------- synthetic PDFs

def _pdf(items):
    """One-page PDF with text at (x, baseline y)."""
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for x, y, text in items:
        page.insert_text((x, y), text, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


ALLY_TEXT = [
    "Ally Bank", "Account Number:  xxxxxx1111",
    "07/01/2026", "Beginning Balance", "$1,000.00",
    "07/03/2026", "ACH Withdrawal", "BIGBANK MORTGAGE", "$0.00", "-$2,000.00", "-$1,000.00",
    "07/05/2026", "ACH Withdrawal", "CARDMEMBER SERV WEB PYMT", "$0.00", "-$300.00", "-$1,300.00",
    "07/10/2026", "Direct Deposit", "ACME CORP PAYROLL", "$5,000.00", "-$0.00", "$3,700.00",
    "07/31/2026", "Ending Balance", "$3,700.00",
]


def ally_pdf():
    return _pdf([(50, 40 + 14 * i, t) for i, t in enumerate(ALLY_TEXT)])


def elan_pdf():
    """Summary at the top; one payment ('CR' a little lower, as printed), one
    purchase, and one purchase with an itinerary line below it."""
    return _pdf([
        (50, 40, "Elan Financial Services"), (50, 54, "Fidelity Rewards Visa Signature Card"),
        (50, 68, "Open Date: 12/28/2025 Closing Date: 01/27/2026"),
        (50, 82, "Account ending in: 4321"),
        (50, 110, "Purchases"), (50, 124, "$295.67"), (50, 152, "Payments"), (50, 166, "$1,234.56"),
        (64, 300, "01/16"), (100, 300, "01/16"), (136, 300, "MTC"), (172, 300, "PAYMENT THANK YOU"),
        (474, 300, "$1,234.56"), (524, 301.5, "CR"),
        (64, 320, "01/20"), (100, 320, "01/17"), (136, 320, "0001"), (172, 320, "HARDWARE STORE CA"),
        (487, 320, "$45.67"),
        (64, 340, "01/22"), (100, 340, "01/21"), (136, 340, "0002"), (172, 340, "SKY AIR 800 CA"),
        (480, 340, "$250.00"),
        (172, 350, "SPRINGFIELD TO SHELBYVILLE"),
    ])


FORMATS = {
    "fidelity_csv": lambda: {"card/fid.csv": FIDELITY_CSV.encode()},
    "fidelity_csv_bom_crlf": lambda: {"fid.csv": b"\xef\xbb\xbf" + FIDELITY_CSV.replace("\n", "\r\n").encode()},
    "venmo_csv": lambda: {"venmo/2026-07.csv": VENMO_CSV.encode()},
    "apple_card_csv": lambda: {"apple.csv": APPLE_CARD_CSV.encode()},
    "ally_pdf": lambda: {"bank/ally.pdf": ally_pdf()},
    "elan_pdf": lambda: {"card/elan.pdf": elan_pdf()},
    "unrecognized": lambda: {"notes.csv": b"a,b\n1,2\n", "scan.pdf": _pdf([(50, 50, "Hello")])},
}
_SINGLE = dict(FORMATS)
FORMATS["everything"] = lambda: {k: v for f in _SINGLE.values() for k, v in f().items()}


def _write(folder, files):
    for name, data in files.items():
        p = folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def _assert_same(a, b):
    pd.testing.assert_frame_equal(a[0], b[0])
    assert a[1] == b[1]          # reconciliation checks
    assert a[2] == b[2]          # problems


# ---------------------------------------------------------------- one code path

@pytest.mark.parametrize("kind", list(FORMATS))
def test_upload_parses_exactly_like_the_same_folder(kind, tmp_path):
    files = FORMATS[kind]()
    _write(tmp_path, files)
    from_folder = sp.load_folder(str(tmp_path))
    uploaded = sp.load_files(list(files.items()))
    _assert_same(uploaded, from_folder)
    _assert_same(sp.load_files(list(reversed(list(files.items())))), uploaded)   # pick order is irrelevant
    df, checks, problems = uploaded
    if kind == "unrecognized":
        assert df.empty and len(problems) == 2
    else:
        assert not df.empty and all(abs(c["expected"] - c["parsed"]) < 0.01 for c in checks)


def test_synthetic_pdfs_parse_in_memory():
    df, checks, problems = sp.load_files([("ally.pdf", ally_pdf()), ("elan.pdf", elan_pdf())])
    assert problems == []
    ally = df[df["source"] == "Ally"].sort_values("date")
    assert ally["amount"].tolist() == [-2000.0, -300.0, 5000.0]
    elan = df[df["source"] == "Fidelity Visa"].sort_values("date")
    assert elan["amount"].tolist() == [1234.56, -45.67, -250.00]        # the CR row is a credit
    assert elan["description"].iloc[2] == "SKY AIR 800 CA | SPRINGFIELD TO SHELBYVILLE"
    assert len(checks) == 3 and all(abs(c["expected"] - c["parsed"]) < 0.01 for c in checks)


def test_bom_and_crlf_decode_like_a_text_file():
    plain = sp.load_files(FORMATS["fidelity_csv"]().items())[0].drop(columns="file")
    odd = sp.load_files(FORMATS["fidelity_csv_bom_crlf"]().items())[0].drop(columns="file")
    pd.testing.assert_frame_equal(plain, odd)


def test_repeated_upload_names_stay_distinct_files():
    other = FIDELITY_CSV.replace("-9.00", "-7.00")
    df, _, _ = sp.load_files([("x.csv", FIDELITY_CSV.encode()), ("x.csv", other.encode())])
    assert set(df["file"]) == {"x.csv", "x (2).csv"}


def test_load_files_writes_nothing_to_disk(tmp_path, monkeypatch):
    files = list(FORMATS["everything"]().items())            # built before the guards go up
    rules = json.dumps(PERSONAL_RULES).encode()
    real_open, real_os_open = builtins.open, os.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if isinstance(file, (str, bytes, os.PathLike)) and any(c in mode for c in "wax+"):
            raise AssertionError(f"write attempted: {file} ({mode})")
        return real_open(file, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND):
            raise AssertionError(f"write attempted: {path}")
        return real_os_open(path, flags, *args, **kwargs)

    def no_temp(*_a, **_k):
        raise AssertionError("temp file attempted")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_open)
    monkeypatch.setattr(os, "open", guarded_os_open)
    for fn in ("mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryFile",
               "SpooledTemporaryFile", "TemporaryDirectory"):
        monkeypatch.setattr(tempfile, fn, no_temp)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.chdir(scratch)
    monkeypatch.setenv("TMPDIR", str(scratch))
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))

    df, _, _ = sp.load_files(files)
    data = sd.load_uploaded(files, rules)                    # the tab's whole upload path
    assert not df.empty and not data["tx"].empty
    assert list(scratch.iterdir()) == []


# ---------------------------------------------------------------- hosted isolation

def test_hosted_resolver_ignores_env_and_settings_file(tmp_path, monkeypatch):
    settings = tmp_path / "spending.json"
    settings.write_text(json.dumps({"data_dir": str(tmp_path)}), encoding="utf-8")
    monkeypatch.setattr(sd, "SETTINGS_PATH", str(settings))
    assert sd.configured_data_dir() == str(tmp_path)               # local: settings file read
    monkeypatch.setenv("SPENDING_DATA_DIR", "/")
    assert sd.configured_data_dir() == "/"                         # local: env wins

    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    opened = []
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda f, *a, **k: (opened.append(str(f)), real_open(f, *a, **k))[1])
    assert sd.configured_data_dir() == ""
    monkeypatch.delenv("SPENDING_DATA_DIR")
    assert sd.configured_data_dir() == ""
    assert str(settings) not in opened                             # not even read
    with pytest.raises(RuntimeError):
        sd.save_data_dir(str(tmp_path))
    with pytest.raises(RuntimeError):
        sd.load(str(tmp_path))


def test_upload_path_never_uses_shared_caches(monkeypatch):
    """st.cache_data / st.cache_resource (and functools caches) are shared by
    every session in the server process, so uploads must never pass through one."""
    import streamlit as st
    names = {"cache_data", "cache_resource", "experimental_memo", "experimental_singleton"}
    for mod in (sp, sr, sd):
        tree = ast.parse(inspect.getsource(mod))
        used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | \
               {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert not used & names, mod.__name__
    for fn in (sd.load_uploaded, sd._uploaded_data, sd.prepare, sp.load_files, sr.parse_rules):
        assert not hasattr(fn, "cache_info") and not hasattr(fn, "__wrapped__"), fn.__name__

    def boom(*_a, **_k):
        raise AssertionError("shared cache used on the upload path")

    monkeypatch.setattr(st, "cache_data", boom)
    monkeypatch.setattr(st, "cache_resource", boom)
    monkeypatch.setattr(sd, "_load_cached", boom)        # the folder mode's process-wide cache
    monkeypatch.setattr(sd, "load_folder", boom)
    fake = SimpleNamespace(session_state={})
    fake.session_state[sd.UPLOAD_STATE] = {"files": {"fid.csv": FIDELITY_CSV.encode()}, "rules": None}
    data = sd._uploaded_data(fake)
    assert not data["tx"].empty
    assert fake.session_state[sd.UPLOAD_STATE]["data"] is data     # kept in THIS session
    assert sd._uploaded_data(fake) is data                         # reused, not re-parsed


# ---------------------------------------------------------------- rules upload

def _hotel(data):
    tx = data["tx"]
    return tx[tx["description"].str.contains("GRAND HOTEL")].iloc[0]


def test_uploaded_rules_json_is_applied():
    files = [("fid.csv", FIDELITY_CSV.encode())]
    plain = sd.load_uploaded(files)
    ruled = sd.load_uploaded(files, json.dumps(PERSONAL_RULES).encode())
    assert _hotel(plain)["kind"] == "spend"                                    # generic defaults
    assert _hotel(ruled)["reason"] == sr.REASON_WORK_TRAVEL                    # your rule applied
    assert plain["rules_error"] is None and ruled["rules_error"] is None


def test_uploaded_rules_match_the_same_file_on_disk(tmp_path):
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(PERSONAL_RULES), encoding="utf-8")
    assert sr.parse_rules(p.read_bytes()) == sr.load_rules(str(p))


@pytest.mark.parametrize("bad,why", [(b"{not json", "Expecting"), (b"[1, 2]", "JSON object"),
                                     (b'{"work_travel_locations": ["("]}', "invalid pattern")])
def test_unusable_rules_fall_back_to_defaults(bad, why):
    data = sd.load_uploaded([("fid.csv", FIDELITY_CSV.encode())], bad)
    assert why in data["rules_error"]
    assert _hotel(data)["kind"] == "spend"


# ---------------------------------------------------------------- session store

class _Uploaded:
    """Stands in for Streamlit's UploadedFile."""
    def __init__(self, name, data):
        self.name, self._data = name, data

    def getvalue(self):
        return self._data


def test_uploads_move_into_session_state_and_clear():
    fake = SimpleNamespace(session_state={})
    key = sd._uploader_key(fake)
    fake.session_state[key] = [_Uploaded("fid.csv", b"1"), _Uploaded("my_rules.json", b"{}")]
    sd._take_uploads(fake)
    store = fake.session_state[sd.UPLOAD_STATE]
    assert store["files"] == {"fid.csv": b"1"} and store["rules"] == ("my_rules.json", b"{}")
    assert sd._uploader_key(fake) != key                           # widget emptied for the next pick
    store["data"] = "parsed"
    fake.session_state[sd._uploader_key(fake)] = [_Uploaded("fid.csv", b"2"), _Uploaded("v.csv", b"3")]
    sd._take_uploads(fake)
    assert store["files"] == {"fid.csv": b"2", "v.csv": b"3"}       # same name replaces, others add
    assert "data" not in store                                     # re-parsed on the next render
    sd._clear_uploads(fake)
    assert sd.UPLOAD_STATE not in fake.session_state


# ---------------------------------------------------------------- the tab (AppTest)

UPLOADS = {"card/fid.csv": FIDELITY_CSV.encode(), "venmo.csv": VENMO_CSV.encode(),
           "apple.csv": APPLE_CARD_CSV.encode()}


def _app(uploads=None):
    from streamlit.testing.v1 import AppTest

    def _script():
        import os
        import sys
        sys.path.insert(0, os.environ["SPENDING_TEST_UI_DIR"])
        import streamlit as st
        from components import spending_dashboard
        spending_dashboard.render(st)

    at = AppTest.from_function(_script, default_timeout=60)
    if uploads is not None:
        at.session_state[sd.UPLOAD_STATE] = {"files": dict(uploads), "rules": None}
    return at.run()


def _captions(at):
    return " ".join(c.value for c in at.caption)


def test_hosted_tab_never_reads_the_server_folder(tmp_path, monkeypatch):
    server = tmp_path / "server"
    _write(server, UPLOADS)
    settings = tmp_path / "spending.json"
    settings.write_text(json.dumps({"data_dir": str(server)}), encoding="utf-8")
    monkeypatch.setattr(sd, "SETTINGS_PATH", str(settings))
    monkeypatch.setenv("SPENDING_DATA_DIR", str(server))
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    at = _app()
    assert not at.exception, at.exception
    assert not at.metric                                   # the server's statements were not loaded
    assert not at.text_input                               # no folder box to type "/" into
    assert len(at.get("file_uploader")) == 1
    assert sd.PRIVACY_NOTE in _captions(at) and "Supported" in _captions(at)


def test_hosted_tab_renders_uploads(monkeypatch):
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    at = _app(UPLOADS)
    assert not at.exception, at.exception
    assert {"Housing", "Everything else", "Total per month", "Total per year"} <= {m.label for m in at.metric}
    assert "sp_dir_input" not in [t.key for t in at.text_input]
    assert sd.PRIVACY_NOTE in _captions(at)
    # Clearing itself is tested on the callback above: AppTest can't re-run this
    # page (it mis-serializes single-select st.pills on any interaction).
    assert at.button(key="sp_clear").label == "Clear uploaded files"


def test_local_without_folder_offers_folder_and_upload_with_same_numbers(tmp_path, monkeypatch):
    at = _app()
    assert not at.exception, at.exception                 # used to crash: folder form drawn twice
    assert "sp_dir_input" in [t.key for t in at.text_input]
    assert len(at.get("file_uploader")) == 1
    uploaded = _app(UPLOADS)
    assert not uploaded.exception, uploaded.exception
    _write(tmp_path / "folder", UPLOADS)
    monkeypatch.setenv("SPENDING_DATA_DIR", str(tmp_path / "folder"))
    folder = _app()
    assert not folder.exception, folder.exception
    assert [(m.label, m.value) for m in uploaded.metric] == [(m.label, m.value) for m in folder.metric]
    assert len(folder.metric) == 4
