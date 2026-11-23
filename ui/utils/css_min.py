"""The theme sent to the browser: comments and blank lines removed, cached per file version."""
from __future__ import annotations

import functools
import re
from pathlib import Path

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_BLANK = re.compile(r"\n\s*\n+")


def minify(css: str) -> str:
    """Strip /* ... */ comments and collapse blank lines. Rules and selectors stay as written."""
    return _BLANK.sub("\n", _COMMENT.sub("", css)).strip()


@functools.lru_cache(maxsize=4)
def _minified(path: str, mtime_ns: int) -> str:
    return minify(Path(path).read_text(encoding="utf-8"))


def minified_css(path) -> str:
    """The minified file. Read again only when its modification time changes."""
    p = Path(path)
    return _minified(str(p), p.stat().st_mtime_ns)
