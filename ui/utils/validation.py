"""Shared input validation for simulation / sweep runs.

Centralizes the hard-invalid input checks so the main Run button AND the
FI-number / safe-withdrawal-rate sweeps all gate the same way (previously only
the main Run validated, so the sweeps could run on nonsensical inputs and
present misleading numbers).
"""
from __future__ import annotations


def validate_run_inputs(overrides: dict, target_age=None) -> list:
    """Return human-readable error strings for input combinations that the
    engine would otherwise silently clamp / misattribute. Empty list = OK to run.

    ``target_age`` is the fixed retirement age for age-targeted runs (the main
    simulation and the safe-withdrawal-rate sweep). Pass ``None`` for analyses
    that *earn* the retirement age instead (the FI-number sweep retires when the
    portfolio first hits a target), which only need a valid planning horizon.
    """
    from retirement_sim import config as cfg
    errs: list = []
    try:
        your_age = int(overrides.get("YOUR_AGE", getattr(cfg, "YOUR_AGE", 30)))
        # Your age when the plan ends: the simulation's horizon (cfg.plan_end_age,
        # which a younger partner's plan-until age can extend past your own).
        plan_until = int(cfg.plan_end_age(overrides))
    except Exception:
        return errs  # unparseable ages -> skip validation rather than crash

    if target_age is not None:
        target_age = int(target_age)
        if target_age < your_age:
            errs.append(
                f"Target retirement age ({target_age}) is below your current age ({your_age}). "
                "Fix it in **About you**, or the result would apply to a different age "
                "than the one shown."
            )
        if plan_until <= target_age:
            errs.append(
                f"The plan ends when you're {plan_until}, which must be after your target "
                f"retirement age ({target_age}). Raise the plan-until age in **About you** so "
                "there's a retirement period to model."
            )
    else:
        if plan_until <= your_age:
            errs.append(
                f"The plan ends when you're {plan_until}, which must be after your current age "
                f"({your_age}). Raise the plan-until age in **About you** so there's a horizon "
                "to model."
            )
    return errs
