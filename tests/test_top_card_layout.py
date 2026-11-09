"""The sticky top card: row 1 = title + Run / simulations / Settings, row 2 =
metrics + the Retirement plan | Spending switch at the bottom right. The rows
are two keyed containers (``mc-topbar-head``, ``mc-topbar-foot``) of one card;
theme.css ("Top card layout", the last block) lays them out."""
import os
import re

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.path.join(_ROOT, "ui", "app.py")
APP = open(APP_PATH, encoding="utf-8").read()
CSS = open(os.path.join(_ROOT, "ui", "styles", "theme.css"), encoding="utf-8").read()
BLOCK = CSS[CSS.index("Top card layout. The card"):]


@pytest.fixture(autouse=True)
def _planner_can_rerun(monkeypatch):
    """AppTest reads a segmented control's single choice as a list (see
    test_mode_switch_sidebar); teach it that so the planner can be rerun."""
    from streamlit.testing.v1 import element_tree as et

    def indices(self):
        values = [self.value] if isinstance(self.value, str) else self.value
        return [self.options.index(self.format_func(v)) for v in values]
    monkeypatch.setattr(et.ButtonGroup, "indices", property(indices))


def _planner(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "1")
    at = AppTest.from_file(APP_PATH, default_timeout=90).run()
    at.button(key="device_skip").click().run()
    next(b for b in at.button if b.label == "Open the retirement planner").click().run()
    at.button(key="gs_skip").click().run()
    assert not at.exception, at.exception
    return at


def _rows(at):
    """(head, foot): the two rows of the top card, found through the Run button."""
    def has_run(block):
        return any(getattr(c, "key", None) == "topbar_run_button" for c in block.children.values())
    card = next(b for b in at.main.children.values() if type(b).__name__ == "Block"
                and any(type(r).__name__ == "Block" and has_run(r) for r in b.children.values()))
    head, foot = list(card.children.values())
    return head, foot


def _kinds(row):
    return [(type(c).__name__, getattr(c, "key", None)) for c in row.children.values()]


def test_card_has_a_title_row_over_a_metrics_and_switch_row(monkeypatch):
    at = _planner(monkeypatch)
    head, foot = _rows(at)
    assert _kinds(head) == [("Markdown", None), ("Button", "topbar_run_button"),
                            ("Selectbox", "n_simulations"), ("Block", None)]       # Settings popover
    assert "mc-topbar-title" in head.children[0].value and "Retirement planner" in head.children[0].value
    assert _kinds(foot) == [("Markdown", None), ("ButtonGroup", "main_view")]
    assert 'class="mc-topbar"' in foot.children[0].value and "mc-topbar-title" not in foot.children[0].value
    switch = foot.children[1]
    assert switch.options and [o.content for o in switch.options] == ["Retirement plan", "Spending"]
    assert switch.value == "Retirement plan"


def test_spending_view_uses_the_same_two_rows(monkeypatch):
    at = _planner(monkeypatch)
    at.get("button_group")[0].set_value("Spending").run()
    assert not at.exception, at.exception
    head, foot = _rows(at)
    assert "Spending" in head.children[0].value and "mc-topbar-title" in head.children[0].value
    assert _kinds(foot) == [("Markdown", None), ("ButtonGroup", "main_view")]
    assert "mc-topbar-stats" in foot.children[0].value


def test_head_row_is_drawn_before_the_foot_row_and_keys_are_kept():
    head, foot = APP.index('key="mc-topbar-head"'), APP.index('key="mc-topbar-foot"')
    assert head < foot
    body = APP[head:APP.index("return view, control_slots, metrics_slot")]
    assert body.index("title_slot = _st.empty()") < body.index("control_slots = ") < foot - head
    assert body.index("metrics_slot = _st.empty()") < body.index('key="main_view"')
    assert 'key="mc-topbar"' in APP and "mc-topbar-title" in APP


def test_no_column_rules_are_left_for_the_top_card():
    assert not re.search(r"mc-topbar[^{]*(stHorizontalBlock|stColumn)", CSS)


def test_switch_is_large_in_the_bottom_right_and_only_resizes_the_tokens():
    assert BLOCK.rstrip().endswith("/* -- end Top card layout -- */")
    big = re.search(r"@media \(min-width: 641px\) \{\s*\.st-key-mc-topbar-foot \.st-key-main_view \{([^}]*)\}", BLOCK)
    assert big
    assert "--mc-seg-item-h: 46px" in big.group(1) and "--mc-seg-fs: 17px" in big.group(1)   # 56px group, 17px text
    assert "border-radius" not in BLOCK and "--mc-seg-r" not in BLOCK                      # shape = shared tokens
    sw = re.search(r"\.st-key-mc-topbar-foot > \.st-key-main_view \{([^}]*)\}", BLOCK)
    assert "margin-left: auto" in sw.group(1) and "max-width: 312px" in sw.group(1)
    foot = re.search(r"\.st-key-mc-topbar-foot \{[^}]*align-items: flex-end", BLOCK)
    assert foot, "the switch's bottom is level with the metric values"


def test_phone_keeps_switch_then_controls_then_title_then_metrics():
    phone = re.search(r"/\* Phones: switch, then the controls.*?\n\}\n", BLOCK, re.S).group(0)
    orders = {name: int(re.search(name + r"[^{]*\{ order: (\d)", phone).group(1))
              for name in ("st-key-main_view", "st-key-topbar_run_button", "st-key-n_simulations",
                           r"\[data-testid=\"stLayoutWrapper\"\]", r"has\(\.mc-topbar-title\)", r"has\(\.mc-topbar\)")}
    assert list(orders.values()) == [1, 2, 3, 4, 5, 6]
    assert "display: contents" in phone
