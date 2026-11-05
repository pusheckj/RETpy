"""The shared design tokens (theme.css, block "QA round A fixes R3"): every token that
holds a literal colour or shadow must have a dark value in theme_toggle._DARK_CSS, and
the control rules must read the tokens, so one change moves every instance."""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "ui"))
CSS = open(os.path.join(_ROOT, "ui", "styles", "theme.css"), encoding="utf-8").read()

_BLOCK = CSS.split("QA round A fixes R3.", 1)[1].split("-- end QA round A R3 --", 1)[0]
_ROOT_RULE = re.search(r":root \{(.*?)\n\}", _BLOCK, re.S).group(1)
TOKENS = dict(re.findall(r"(--mc-[a-z0-9-]+):\s*([^;]+);", _ROOT_RULE))


def test_token_set_covers_every_role():
    for name in ("ctl-h", "ctl-r", "ctl-fill", "btn-fill", "pill-h", "seg-r", "seg-item-r", "seg-item-h",
                 "seg-fw", "seg-on-bg", "seg-on-ink", "card-r", "card-pad", "label-fs", "label-fw",
                 "cap-fs", "eyebrow-fs", "eyebrow-fw", "sub-fs", "sub-fw"):
        assert f"--mc-{name}" in TOKENS, name


def test_literal_colour_tokens_have_a_dark_value():
    from components.theme_toggle import _DARK_CSS
    literal = [n for n, v in TOKENS.items() if re.search(r"#[0-9a-fA-F]{3,8}|rgba?\(", v)]
    assert literal
    missing = [n for n in literal if not re.search(re.escape(n) + r"\s*:", _DARK_CSS)]
    assert not missing, f"no dark value for {missing}"


def test_controls_read_the_tokens():
    for needle in ("min-height: var(--mc-ctl-h)", "border-radius: var(--mc-ctl-r)",
                   "background-color: var(--mc-ctl-fill)", "border-radius: var(--mc-seg-r)",
                   "border-radius: var(--mc-seg-item-r)", "min-height: var(--mc-seg-item-h)",
                   "border-radius: var(--mc-card-r)", "font-size: var(--mc-label-fs)"):
        assert needle in _BLOCK, needle
