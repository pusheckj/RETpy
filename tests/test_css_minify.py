"""The theme is sent minified: no comments, same rules, small enough."""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
CSS_PATH = os.path.join(_UI, "styles", "theme.css")


def _selectors(css: str) -> list:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for chunk in css.split("{")[:-1]:
        # The text before a "{" runs from the last "}" or ";" to the brace.
        sel = re.split(r"[};]", chunk)[-1]
        out.append(re.sub(r"\s+", " ", sel).strip())
    return out


def _load():
    if _UI not in sys.path:
        sys.path.insert(0, _UI)
    from utils import css_min
    return css_min


def test_minified_keeps_every_selector():
    mod = _load()
    original = open(CSS_PATH, encoding="utf-8").read()
    mini = mod.minified_css(CSS_PATH)
    assert _selectors(mini) == _selectors(original)


def test_no_comments_left_and_under_170kb():
    mini = _load().minified_css(CSS_PATH)
    assert "/*" not in mini and "*/" not in mini
    assert len(mini.encode("utf-8")) < 170_000


def test_result_is_cached_by_path_and_mtime():
    mod = _load()
    assert mod.minified_css(CSS_PATH) is mod.minified_css(CSS_PATH)


def test_inter_font_import_is_gone():
    assert "fonts.googleapis.com" not in open(CSS_PATH, encoding="utf-8").read()
