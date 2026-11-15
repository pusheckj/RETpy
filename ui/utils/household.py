"""Who the plan is for: one adult, a married couple, or an unmarried couple.

Said only through existing config keys, so the engine needs nothing new:
PARTNER_AGE > 0 means there is a partner (``cfg.has_partner``), and
FILING_STATUS "Married filing jointly" means the couple is married. An
unmarried partner keeps Single or Head of household as the filing status.
"""
from __future__ import annotations

try:
    from utils.coerce import safe_int
    from utils.age_limits import TARGET_MIN, TARGET_MAX
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int  # type: ignore
    from ui.utils.age_limits import TARGET_MIN, TARGET_MAX  # type: ignore

JUST_ME, SPOUSE, PARTNER = "Just me", "Me and my spouse", "Me and my partner (not married)"
HOUSEHOLDS = [JUST_ME, SPOUSE, PARTNER]

MFJ, SINGLE, HOH = "Married filing jointly", "Single", "Head of household"
# Filing statuses open to someone who isn't married.
UNMARRIED_FILING = [SINGLE, HOH]

# Every partner input. With no partner they are all zeroed: the engine already
# leaves them out (cfg.has_partner), and a saved profile then says so too.
PARTNER_AMOUNT_KEYS = (
    "PARTNER_401K", "PARTNER_ROTH_IRA", "PARTNER_BROKERAGE", "PARTNER_CASH",
    "PARTNER_401K_CONTRIBUTION", "PARTNER_ROTH_CONTRIBUTION", "PARTNER_BROKERAGE_CONTRIBUTION",
    "PARTNER_SALARY", "PARTNER_BASE_SALARY", "PARTNER_BONUS_AMOUNT", "PARTNER_RSU_AMOUNT",
    "PARTNER_OTHER_INCOME", "PARTNER_SS_MONTHLY_FRA",
    "PARTNER_OTHER_MONTHLY", "PARTNER_MONTHLY_SPENDING",
)
# Partner settings that fall back to "same as you" (None) with no partner.
PARTNER_OPTIONAL_KEYS = ("PARTNER_RETIREMENT_AGE", "PARTNER_PLAN_UNTIL_AGE", "PARTNER_SS_CLAIM_AGE")


def household_of(overrides: dict) -> str:
    """The household an overrides dict describes."""
    if safe_int(overrides.get("PARTNER_AGE", 0), 0) <= 0:
        return JUST_ME
    return SPOUSE if str(overrides.get("FILING_STATUS", MFJ)) in (MFJ, "MFJ") else PARTNER


def clear_partner(overrides: dict) -> None:
    """Make ``overrides`` a single household: no partner and no partner money."""
    overrides["PARTNER_AGE"] = 0
    for key in PARTNER_AMOUNT_KEYS:
        overrides[key] = 0
    for key in PARTNER_OPTIONAL_KEYS:
        overrides[key] = None
    overrides["PRIMARY_PAYS_HOUSING"] = False


def forget_partner_widgets(session_state) -> None:
    """Drop what every partner widget holds (and the typed box beside each slider).

    ``clear_partner`` zeroes the plan's values, but the widgets keep their own: a
    partner added again would come back with the old 401(k) and Roth amounts and
    retirement age. With the widgets dropped, each reseeds from the cleared plan."""
    try:
        from utils.widget_sync import DIRECT_MAPPINGS
        from utils.slider_input import SUFFIXES
    except ImportError:  # pragma: no cover
        from ui.utils.widget_sync import DIRECT_MAPPINGS  # type: ignore
        from ui.utils.slider_input import SUFFIXES  # type: ignore
    keys = [w for w, (okey, _cast) in DIRECT_MAPPINGS.items() if okey.startswith("PARTNER_")]
    for key in keys + ["ay_partner_later"]:
        for k in [key] + [key + sfx for sfx in SUFFIXES]:
            session_state.pop(k, None)


def _value(values: dict, key: str):
    """``values[key]``, else the active config's (what the simulation would use)."""
    from retirement_sim import config as cfg
    v = (values or {}).get(key)
    return getattr(cfg, key, None) if v is None else v


def has_partner(values: dict) -> bool:
    """cfg.has_partner() for an overrides dict (or a run's config snapshot):
    PARTNER_AGE > 0, falling back to the config's when the dict has none."""
    return safe_int(_value(values, "PARTNER_AGE"), 0) > 0


def retire_floor(age: int) -> int:
    """Lowest retirement age the sliders offer: the person's own age today (an earlier
    age has already passed). Never reaches the top, so a slider always has a range."""
    return max(TARGET_MIN, min(age, TARGET_MAX - 1))


def retire_together(overrides: dict) -> tuple:
    """(the partner's age in the year YOU retire, clamped to the slider's range; whether it
    fitted in that range without clamping). The Retirement section starts the partner's
    retirement age here, and stores None (retire together) when it cannot be shown."""
    target = safe_int(overrides.get("TARGET_RETIREMENT_AGE", 60), 60)
    gap = safe_int(overrides.get("YOUR_AGE", 30), 30) - safe_int(overrides.get("PARTNER_AGE", 0), 0)
    raw = target - gap
    floor = retire_floor(safe_int(overrides.get("PARTNER_AGE", 0), 0))
    return max(floor, min(TARGET_MAX, raw)), floor <= raw <= TARGET_MAX


def partner_defaults(overrides: dict) -> dict:
    """What the side panel stores for the partner settings ``overrides`` leaves out
    (a missing key, or None). Only when the dict says who is in the plan (PARTNER_AGE):

    * no partner (PARTNER_AGE <= 0): every partner amount 0, the partner's own ages None;
    * a partner: retires the year you do (None when that age is off the slider), plans
      to your plan-until age and claims Social Security at your claim age.
    """
    if overrides.get("PARTNER_AGE") is None:
        return {}
    if safe_int(overrides["PARTNER_AGE"], 0) <= 0:
        return {**dict.fromkeys(PARTNER_AMOUNT_KEYS, 0), **dict.fromkeys(PARTNER_OPTIONAL_KEYS)}
    together, fits = retire_together(overrides)
    return {"PARTNER_RETIREMENT_AGE": together if fits else None,
            "PARTNER_PLAN_UNTIL_AGE": safe_int(_value(overrides, "PLAN_UNTIL_AGE"), 95),
            "PARTNER_SS_CLAIM_AGE": safe_int(_value(overrides, "SS_CLAIM_AGE"), 67)}


def plan_end_ages(values: dict) -> tuple:
    """(your age, partner's age or None) when the plan ends.

    The one horizon every screen shows: the simulation runs until the later of
    your plan-until age and your partner's (cfg.plan_end_age), so with a
    younger partner it runs past your own plan-until age.
    """
    from retirement_sim import config as cfg
    end = int(cfg.plan_end_age(values or {}))
    if not has_partner(values):
        return end, None
    gap = safe_int(_value(values, "YOUR_AGE"), 0) - safe_int(_value(values, "PARTNER_AGE"), 0)
    return end, end - gap


def plan_end_text(values: dict) -> str:
    """'you're 100 and your partner is 95' / 'you're 95'."""
    end, partner_end = plan_end_ages(values)
    if partner_end is None:
        return f"you're {end}"
    return f"you're {end} and your partner is {partner_end}"
