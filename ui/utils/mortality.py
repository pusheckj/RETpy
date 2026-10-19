"""Actuarial life-expectancy model — a survival / age-at-death DISTRIBUTION
adjusted for personal risk factors.

Approach (self-contained, no external data): a **Gompertz** force of mortality
parameterised by the *modal* age at death ``M`` and a *dispersion* ``b``:

    mu(x) = (1/b) * exp((x - M) / b)          # force of mortality at age x
    q(x)  = 1 - exp(-mu(x))                    # probability of dying within year x

Personal risk factors enter as a single **proportional-hazards multiplier**
(relative risk) ``RR`` applied to mu. Because Gompertz mortality is
log-linear in age, a constant hazard multiplier is exactly a horizontal SHIFT of
the modal age: ``mu_RR(x) = RR * mu(x)`` is the same curve with
``M' = M - b*ln(RR)``. So RR = 2 (e.g. a smoker) moves the modal age down by
``b*ln 2 ≈ 7`` years, matching the epidemiological "smoking costs ~7-10 years".

Baseline modal ages are set so the implied period life expectancies land near
recent US Social Security life-table values (life expectancy at 65 ≈ 18 yrs male
/ 21 yrs female). Hazard ratios are rounded approximations from public
epidemiology (relative-risk literature) — good enough for planning intuition,
NOT medical advice.
"""
from __future__ import annotations

import math

# Modal age at death by sex (Gompertz mode). US-ish, ~2020 period tables.
_BASE_MODE = {"Male": 84.5, "Female": 87.5}
_DISPERSION = 10.5  # Gompertz dispersion b (years); larger = wider spread.
_MAX_AGE = 120      # everyone is assumed dead by here (q forced to 1).

# Risk factors: label -> ordered options -> relative-risk (all-cause hazard)
# multiplier. RR = 1.0 is the neutral reference. The product of the selected
# multipliers is the household's overall hazard ratio.
RISK_FACTORS = {
    "smoking": {
        "label": "Smoking",
        "help": "Current smoking roughly doubles all-cause mortality; the excess "
                "risk fades over years after quitting.",
        "options": {"Never": 1.0, "Former": 1.35, "Current": 2.2},
        "default": "Never",
    },
    "weight": {
        "label": "Body weight (BMI)",
        "help": "Relative to a normal BMI (~18.5-25). Both obesity and being "
                "underweight raise mortality.",
        "options": {"Underweight": 1.25, "Normal": 1.0, "Overweight": 1.08,
                    "Obese": 1.3, "Severely obese": 1.8},
        "default": "Normal",
    },
    "activity": {
        "label": "Physical activity",
        "help": "Regular exercise is one of the strongest modifiable protective factors. "
                "'Moderate' is the neutral reference.",
        "options": {"Active": 0.8, "Moderate": 1.0, "Sedentary": 1.25},
        "default": "Moderate",
    },
    "alcohol": {
        "label": "Alcohol",
        "help": "Heavy drinking raises mortality; none-to-moderate is roughly neutral.",
        "options": {"None": 1.0, "Light / moderate": 1.0, "Heavy": 1.35},
        "default": "Light / moderate",
    },
    "health": {
        "label": "Self-rated health",
        "help": "Self-rated health is a remarkably strong independent predictor of survival.",
        "options": {"Excellent": 0.8, "Good": 1.0, "Fair": 1.3, "Poor": 1.8},
        "default": "Good",
    },
    "family": {
        "label": "Family longevity",
        "help": "Whether close relatives (parents/grandparents) tended to live long or die young.",
        "options": {"Long-lived (85+)": 0.82, "Average": 1.0, "Died young (<70)": 1.25},
        "default": "Average",
    },
}

# Chronic conditions — each present condition multiplies the hazard. Independent
# multiselect (multiple can apply).
CONDITIONS = {
    "Diabetes": 1.5,
    "Heart disease": 1.7,
    "High blood pressure": 1.2,
    "Cancer (current/recent)": 1.7,
    "COPD / lung disease": 1.9,
}


def hazard_ratio(selections: dict, conditions: list | None = None) -> float:
    """Overall relative-risk multiplier = product of selected factor RRs and any
    chronic-condition RRs. ``selections`` maps factor key -> chosen option label."""
    rr = 1.0
    for key, spec in RISK_FACTORS.items():
        choice = selections.get(key, spec["default"])
        rr *= float(spec["options"].get(choice, 1.0))
    for cond in (conditions or []):
        rr *= float(CONDITIONS.get(cond, 1.0))
    return rr


def _adjusted_mode(sex: str, rr: float) -> float:
    """Modal age at death shifted by the hazard multiplier (Gompertz identity)."""
    base = _BASE_MODE.get(sex, _BASE_MODE["Male"])
    m = base - _DISPERSION * math.log(max(rr, 1e-6))
    # Keep the mode in a sane band so extreme inputs can't produce absurd ages.
    return max(45.0, min(105.0, m))


def life_distribution(current_age: int, sex: str, selections: dict,
                      conditions: list | None = None) -> dict:
    """Return the age-at-death distribution CONDITIONAL on being alive at
    ``current_age``, plus summary statistics.

    Keys: ``ages`` (list), ``death_pdf`` (P(die in year x | alive now)),
    ``survival`` (P(alive at start of year x | alive now)), ``hazard_ratio``,
    ``mode``, ``median``, ``mean`` (life expectancy, age), ``p10``/``p90`` (age),
    ``reach`` ({age: probability}).
    """
    current_age = int(max(0, min(current_age, _MAX_AGE - 1)))
    rr = hazard_ratio(selections, conditions)
    M = _adjusted_mode(sex, rr)
    b = _DISPERSION

    ages = list(range(current_age, _MAX_AGE + 1))
    survival = []          # S(x) = P(alive at START of year x | alive at current_age)
    death_pdf = []         # d(x) = P(die during year x | alive at current_age)
    s = 1.0
    for x in ages:
        survival.append(s)
        if x >= _MAX_AGE:
            q = 1.0
        else:
            mu = math.exp((x - M) / b) / b
            q = 1.0 - math.exp(-mu)
            q = max(0.0, min(1.0, q))
        d = s * q
        death_pdf.append(d)
        s *= (1.0 - q)

    total = sum(death_pdf) or 1.0
    death_pdf = [d / total for d in death_pdf]  # normalize (tail beyond MAX_AGE folded in)

    # Cumulative death CDF for percentiles: F(x) = P(dead by end of year x).
    def _percentile_age(p: float) -> int:
        cum = 0.0
        for x, d in zip(ages, death_pdf):
            cum += d
            if cum >= p:
                return x
        return ages[-1]

    median = _percentile_age(0.50)
    p10 = _percentile_age(0.10)
    p90 = _percentile_age(0.90)
    # Mean age at death (each death placed at mid-year).
    mean = sum((x + 0.5) * d for x, d in zip(ages, death_pdf))

    surv_by_age = {x: sv for x, sv in zip(ages, survival)}

    def _reach(age: int) -> float:
        if age <= current_age:
            return 1.0
        return float(surv_by_age.get(age, 0.0))

    return {
        "current_age": current_age,
        "sex": sex,
        "hazard_ratio": rr,
        "mode": M,
        "ages": ages,
        "death_pdf": death_pdf,
        "survival": survival,
        "median": int(median),
        "mean": mean,
        "p10": int(p10),
        "p90": int(p90),
        "reach": {a: _reach(a) for a in (80, 85, 90, 95, 100)},
        "reach_fn": surv_by_age,
    }
