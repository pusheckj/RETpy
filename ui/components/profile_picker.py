"""Profile picker component — top of sidebar."""
from __future__ import annotations

import json
import os
import warnings

try:
    from utils.hosting import is_hosted
    from utils.profile_io import deserialize_overrides, personal_profile_path
except ImportError:  # pragma: no cover
    from ui.utils.hosting import is_hosted  # type: ignore
    from ui.utils.profile_io import deserialize_overrides, personal_profile_path  # type: ignore

# "My situation" is your own saved profile: an app-export JSON (Settings -> Save)
# kept OUTSIDE the repository at ~/.config/retirement-sim/my_profile.json, or
# wherever RETIREMENT_SIM_PROFILE points, so personal numbers never get
# committed. Its optional top-level "label" names the picker entry; a label like
# "My situation (Name & Name)" also feeds the top bar's Name(s) metric. With no
# file, the entry simply doesn't appear.
MY_SITUATION_DEFAULT_LABEL = "My situation"


def load_personal_profile(path: str | None = None) -> tuple[str, dict] | None:
    """(label, overrides) for the private profile, or None when there isn't one.
    A hosted app never offers one, even if a profile file is on the server."""
    if is_hosted():
        return None
    path = path or personal_profile_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        overrides = deserialize_overrides(text)
        label = json.loads(text).get("label")
    except Exception as exc:  # broken file: leave the entry out, never crash the app
        warnings.warn(f"Ignoring unreadable profile {path}: {exc}")
        return None
    if not isinstance(label, str) or not label.strip():
        label = MY_SITUATION_DEFAULT_LABEL
    return label.strip(), overrides


def _load_my_situation(path: str | None = None) -> dict | None:
    """Just the private profile's overrides (None when there isn't one)."""
    found = load_personal_profile(path)
    return found[1] if found else None


PROFILES = {
    "Median US 25-year-old household": {
        'YOUR_AGE': 25, 'PARTNER_AGE': 25,
        'YOUR_BIRTH_YEAR': 2001, 'PARTNER_BIRTH_YEAR': 2001,
        'CURRENT_YEAR': 2026,
        'YEARS_UNTIL_WEDDING': 3, 'YEARS_UNTIL_FIRST_CHILD': 3,
        'YOUR_401K': 10_000, 'YOUR_ROTH_IRA': 3_500, 'YOUR_TRADITIONAL_IRA': 0,
        'YOUR_HSA': 500, 'YOUR_BROKERAGE': 2_500, 'YOUR_CASH': 4_000,
        'PARTNER_401K': 7_000, 'PARTNER_ROTH_IRA': 2_500, 'PARTNER_BROKERAGE': 1_000, 'PARTNER_CASH': 3_000,
        'HOME_VALUE': 0, 'MORTGAGE_BALANCE': 0, 'MORTGAGE_MONTHLY': 0, 'MORTGAGE_YEARS_REMAINING': 0,
        'PARTNER_SALARY': 42_000,
        'YOUR_BASE_SALARY': 45_000, 'YOUR_BONUS_AMOUNT': 0, 'YOUR_RSU_AMOUNT': 0, 'YOUR_OTHER_INCOME': 0,
        'PARTNER_BASE_SALARY': 42_000, 'PARTNER_BONUS_AMOUNT': 0, 'PARTNER_RSU_AMOUNT': 0, 'PARTNER_OTHER_INCOME': 0,
        'FILING_STATUS': "Married filing jointly", 'STATE_CHOICE': "CA",
        'RETIREMENT_SPENDING_MODE': "Same as today's expenses", 'SAVINGS_MODE': "Auto-allocate (recommended)",
        'YOUR_401K_CONTRIBUTION': 2_700, 'YOUR_401K_MATCH_PCT': 0.04,
        'YOUR_HSA_CONTRIBUTION': 0, 'YOUR_HSA_MATCH': 0, 'YOUR_BACKDOOR_ROTH': 0, 'YOUR_ESPP_PCT': 0.0, 'YOUR_ESPP_DISCOUNT': 0.0,
        'YOUR_SS_MONTHLY_FRA': 2_000, 'PARTNER_SS_MONTHLY_FRA': 1_800,
        'TARGET_RETIREMENT_AGE': 60,
    },
    "Young professional (28, single)": {
        'YOUR_AGE': 28, 'PARTNER_AGE': 0,
        'YOUR_BIRTH_YEAR': 1998, 'PARTNER_BIRTH_YEAR': 1998,
        'YEARS_UNTIL_WEDDING': 99, 'YEARS_UNTIL_FIRST_CHILD': 99,
        'YOUR_401K': 50_000, 'YOUR_ROTH_IRA': 25_000, 'YOUR_TRADITIONAL_IRA': 0,
        'YOUR_HSA': 8_000, 'YOUR_BROKERAGE': 30_000, 'YOUR_CASH': 25_000,
        'PARTNER_401K': 0, 'PARTNER_ROTH_IRA': 0, 'PARTNER_BROKERAGE': 0, 'PARTNER_CASH': 0,
        'PARTNER_SALARY': 0,
        'YOUR_BASE_SALARY': 135_000, 'YOUR_BONUS_AMOUNT': 13_500, 'YOUR_RSU_AMOUNT': 30_000, 'YOUR_OTHER_INCOME': 0,
        'PARTNER_BASE_SALARY': 0, 'PARTNER_BONUS_AMOUNT': 0, 'PARTNER_RSU_AMOUNT': 0, 'PARTNER_OTHER_INCOME': 0,
        'FILING_STATUS': "Single", 'STATE_CHOICE': "CA",
        'RETIREMENT_SPENDING_MODE': "Same as today's expenses", 'SAVINGS_MODE': "Auto-allocate (recommended)",
        'HOME_VALUE': 0, 'MORTGAGE_BALANCE': 0, 'MORTGAGE_MONTHLY': 0, 'MORTGAGE_YEARS_REMAINING': 0,
        'YOUR_401K_CONTRIBUTION': 23_000, 'YOUR_401K_MATCH_PCT': 0.06,
        'YOUR_HSA_CONTRIBUTION': 7_550, 'YOUR_HSA_MATCH': 750, 'YOUR_BACKDOOR_ROTH': 7_000, 'YOUR_ESPP_PCT': 0.10, 'YOUR_ESPP_DISCOUNT': 0.15,
        'YOUR_SS_MONTHLY_FRA': 2_800, 'PARTNER_SS_MONTHLY_FRA': 0,
        'TARGET_RETIREMENT_AGE': 55,
    },
    "Mid-career couple (40, kids)": {
        'YOUR_AGE': 40, 'PARTNER_AGE': 38,
        'YOUR_BIRTH_YEAR': 1986, 'PARTNER_BIRTH_YEAR': 1988,
        'YEARS_UNTIL_WEDDING': 0, 'YEARS_UNTIL_FIRST_CHILD': -5,
        'YOUR_401K': 350_000, 'YOUR_ROTH_IRA': 95_000, 'YOUR_TRADITIONAL_IRA': 20_000,
        'YOUR_HSA': 25_000, 'YOUR_BROKERAGE': 180_000, 'YOUR_CASH': 40_000,
        'PARTNER_401K': 180_000, 'PARTNER_ROTH_IRA': 55_000, 'PARTNER_BROKERAGE': 30_000, 'PARTNER_CASH': 25_000,
        'HOME_VALUE': 700_000, 'MORTGAGE_BALANCE': 350_000, 'MORTGAGE_MONTHLY': 2_800, 'MORTGAGE_YEARS_REMAINING': 10,
        'PARTNER_SALARY': 120_000,
        'YOUR_BASE_SALARY': 180_000, 'YOUR_BONUS_AMOUNT': 25_000, 'YOUR_RSU_AMOUNT': 40_000, 'YOUR_OTHER_INCOME': 0,
        'PARTNER_BASE_SALARY': 120_000, 'PARTNER_BONUS_AMOUNT': 0, 'PARTNER_RSU_AMOUNT': 0, 'PARTNER_OTHER_INCOME': 0,
        'FILING_STATUS': "Married filing jointly", 'STATE_CHOICE': "CA",
        'RETIREMENT_SPENDING_MODE': "Same as today's expenses", 'SAVINGS_MODE': "Auto-allocate (recommended)",
        'YOUR_401K_CONTRIBUTION': 23_000, 'YOUR_401K_MATCH_PCT': 0.06,
        'YOUR_HSA_CONTRIBUTION': 7_550, 'YOUR_HSA_MATCH': 750,
        'YOUR_SS_MONTHLY_FRA': 3_200, 'PARTNER_SS_MONTHLY_FRA': 2_400,
        'TARGET_RETIREMENT_AGE': 55,
    },
    "Near retirement (55)": {
        'YOUR_AGE': 55, 'PARTNER_AGE': 53,
        'YOUR_BIRTH_YEAR': 1971, 'PARTNER_BIRTH_YEAR': 1973,
        'YEARS_UNTIL_WEDDING': 0, 'YEARS_UNTIL_FIRST_CHILD': -25,
        'YOUR_401K': 1_200_000, 'YOUR_ROTH_IRA': 300_000, 'YOUR_TRADITIONAL_IRA': 150_000,
        'YOUR_HSA': 80_000, 'YOUR_BROKERAGE': 600_000, 'YOUR_CASH': 75_000,
        'PARTNER_401K': 450_000, 'PARTNER_ROTH_IRA': 180_000, 'PARTNER_BROKERAGE': 100_000, 'PARTNER_CASH': 60_000,
        'HOME_VALUE': 850_000, 'MORTGAGE_BALANCE': 120_000, 'MORTGAGE_MONTHLY': 1_700, 'MORTGAGE_YEARS_REMAINING': 7,
        'PARTNER_SALARY': 130_000,
        'YOUR_BASE_SALARY': 220_000, 'YOUR_BONUS_AMOUNT': 35_000, 'YOUR_RSU_AMOUNT': 0, 'YOUR_OTHER_INCOME': 0,
        'PARTNER_BASE_SALARY': 130_000, 'PARTNER_BONUS_AMOUNT': 0, 'PARTNER_RSU_AMOUNT': 0, 'PARTNER_OTHER_INCOME': 0,
        'FILING_STATUS': "Married filing jointly", 'STATE_CHOICE': "CA",
        'RETIREMENT_SPENDING_MODE': "Same as today's expenses", 'SAVINGS_MODE': "Auto-allocate (recommended)",
        'YOUR_SS_MONTHLY_FRA': 3_900, 'PARTNER_SS_MONTHLY_FRA': 2_300,
        'ACTIVE_RETURN_SCENARIO': 'conservative',
        'TARGET_RETIREMENT_AGE': 60,
    },
    "Custom (keep current values)": None,  # sentinel: don't overwrite
}

_MY_SITUATION = load_personal_profile()
if _MY_SITUATION is not None:
    PROFILES = {_MY_SITUATION[0]: _MY_SITUATION[1], **PROFILES}

# The app opens on your own profile when you have one, else the first preset.
DEFAULT_PROFILE = next(iter(PROFILES))


def render(st) -> None:
    st.markdown('<div style="font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;">Profile</div>', unsafe_allow_html=True)
    names = list(PROFILES.keys())

    # Keep the selectbox in sync with an EXTERNAL profile change (e.g. a JSON
    # upload sets `profile` without touching `profile_selectbox`). A USER change
    # is handled by the on_change callback below — which updates `profile` first,
    # so this seed never clobbers the selection (the previous bug: this ran on
    # the same rerun as a user pick and reset the selectbox before the change was
    # applied, so switching profiles "did nothing").
    current_profile = st.session_state.get("profile", names[0])
    if current_profile not in names:
        current_profile = names[0]
    if st.session_state.get("profile_selectbox") != current_profile:
        st.session_state["profile_selectbox"] = current_profile

    def _apply_profile() -> None:
        """Fired only on a real user selection. Applies the chosen profile and
        resets every input so the whole app refreshes to the new values."""
        selected = st.session_state.get("profile_selectbox")
        if selected is None or selected == st.session_state.get("profile"):
            return
        st.session_state["profile"] = selected
        preset = PROFILES.get(selected)
        if preset is None:
            return  # "Custom (keep current values)" sentinel — leave inputs as-is
        st.session_state["user_overrides"] = dict(preset)
        st.session_state["results"] = None
        st.session_state["whatif_results"] = None
        # If the preset carries an explicit compensation ramp, mark it customized
        # so sec_income preserves it instead of overwriting with its auto table.
        st.session_state["si_comp_customized"] = "YOUR_COMPENSATION_BY_AGE" in preset
        for k in ("fi_result", "swr_result", "last_run_inputs_hash"):
            st.session_state.pop(k, None)
        # Clear EVERY widget's session_state entry so all inputs re-initialize
        # from the new profile. A widget's stored key takes precedence over its
        # component default, so any field NOT covered by the sync mappings would
        # otherwise keep the old profile's value (and write it back into
        # user_overrides). Preserve only app-control keys. This runs in the
        # callback (before the widgets re-instantiate), so deletes are safe.
        _PRESERVE = {
            "profile", "profile_selectbox", "user_overrides", "results",
            "whatif_results", "si_comp_customized", "theme_mode",
            "font_choice", "palette_choice", "n_simulations", "pinned_scenarios",
            "_anim_epoch",
            # Auto-run fires ONCE per browser session, on first page open only.
            # Without preserving this, the wildcard sweep below deletes it and a
            # profile switch silently kicks off a full (~95s cold) simulation
            # sweep -- i.e. "changing a value" auto-simulates, which is exactly
            # what we don't want. Switching profiles now just clears results and
            # waits for an explicit Run.
            "_autorun_done",
        }
        for widget_key in list(st.session_state.keys()):
            if widget_key not in _PRESERVE:
                try:
                    del st.session_state[widget_key]
                except Exception:
                    pass
        try:
            from utils.widget_sync import sync_widgets_from_overrides
        except Exception:  # pragma: no cover
            from ui.utils.widget_sync import sync_widgets_from_overrides  # type: ignore
        sync_widgets_from_overrides(st)
        # NOTE: deliberately NOT calling sim_runner.clear_cache() here. The cache
        # is content-keyed on (hashed overrides, n_simulations, target age), so a
        # different profile misses it naturally. Clearing only evicted the OTHER
        # profiles' entries, so switching A -> B -> A recomputed A from scratch
        # (main MC + FI sweep + SWR sweep) instead of hitting a valid cache.
        # clear_cache() remains for dev use after editing the model itself.
        #
        # Bump a token the animation layer watches: its celebration state lives
        # on window.parent and never resets, so profile A at 85% would suppress
        # confetti for a different profile B at 90% ("already above 80").
        st.session_state["_anim_epoch"] = st.session_state.get("_anim_epoch", 0) + 1

    st.selectbox(
        "Profile",
        options=names,
        label_visibility="collapsed",
        key="profile_selectbox",
        on_change=_apply_profile,
    )
