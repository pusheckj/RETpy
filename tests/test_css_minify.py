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


def test_known_limit_a_string_holding_a_comment_opener_is_not_safe():
    """The minifier is a regex, not a parser. A string or url() holding "/*" would be cut.
    This records the limit, and the next test keeps the theme free of such strings."""
    mod = _load()
    css = 'a{content:"/*"} b{color:red} /* note */ c{top:0}'
    assert "c{top:0}" in mod.minify(css)
    assert 'content:"/*"' not in mod.minify(css)  # the limit: the string is damaged


def test_theme_has_no_comment_opener_inside_a_string_or_url():
    css = open(CSS_PATH, encoding="utf-8").read()
    bare = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert not re.search(r"""(["'])[^"'\n]*/\*""", bare)
    assert not re.search(r"url\([^)]*/\*", bare)
