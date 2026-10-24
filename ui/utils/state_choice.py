"""Where-you-live choices shared by the Taxes section, guided setup and widget sync.

The stored value is ``STATE_CHOICE``: a two-letter state code (all 50 states +
DC, see retirement_sim/state_tax_data.py), or one of the two legacy values
older saved plans carry: "No state tax" and "Other" (a flat rate in
YOUR_MARGINAL_TAX_RATE). Widgets show labels; these helpers convert.
"""
from __future__ import annotations

from retirement_sim import config as cfg
from retirement_sim import state_tax_data

NONE_LABEL = "No state income tax"
FLAT_LABEL = "Another state (flat rate)"

# State names alphabetically, then the two non-state choices.
_BY_NAME = sorted((row["name"], code) for code, row in state_tax_data.STATES.items())
STATE_LABELS = [name for name, _ in _BY_NAME]
OPTIONS = STATE_LABELS + [NONE_LABEL, FLAT_LABEL]

_LABEL_TO_CODE = {name: code for name, code in _BY_NAME}
_LABEL_TO_CODE[NONE_LABEL] = cfg.STATE_NONE
_LABEL_TO_CODE[FLAT_LABEL] = cfg.STATE_FLAT


def code_for(label) -> str:
    """Stored STATE_CHOICE for a widget label (or anything resolve_state_code accepts)."""
    return _LABEL_TO_CODE.get(label) or cfg.resolve_state_code(label)


def label_for(code) -> str:
    """Widget label for a stored STATE_CHOICE (legacy values and names included)."""
    resolved = cfg.resolve_state_code(code if code else "CA")
    if resolved == cfg.STATE_NONE:
        return NONE_LABEL
    if resolved == cfg.STATE_FLAT:
        return FLAT_LABEL
    return state_tax_data.STATES[resolved]["name"]


def caption_for(code) -> str:
    """Plain-language note on how exact the chosen state's figures are
    (Markdown-safe: dollar signs escaped)."""
    rules = cfg.state_tax_rules(code)
    if rules["code"] == cfg.STATE_NONE:
        return "No state income tax."
    if rules["code"] == cfg.STATE_FLAT:
        return "A flat rate on income above the federal standard deduction."
    note = rules.get("note") or ""
    if rules["confidence"] == "approx":
        text = f"Approximate {rules['year']} figures for {rules['name']}. {note}"
    else:
        text = f"{rules['name']} {rules['year']} tax table. {note}"
    return text.strip().replace("$", "\\$")
