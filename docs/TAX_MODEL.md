# Tax Model

This document describes every tax rule encoded in the simulator, with bracket tables and formulas sufficient to audit the engine line-by-line against a spreadsheet or against IRS / FTB source documents.

---

## 1. Scope

- **Jurisdictions modeled:** US federal income tax, federal long-term capital gains tax, federal Net Investment Income Tax (NIIT), federal Medicare IRMAA surcharges, federal payroll (via wage inputs only), and **California** state income tax.
- **Tax year baseline:** **2024** statutory brackets, thresholds, and contribution limits. The engine runs in an **all-real (today's-dollars) frame**: statutory items that are CPI-indexed in reality (federal ordinary/LTCG brackets, standard deduction, contribution limits) are held **flat at their 2024 real values**. Statutory thresholds that are *not* indexed in reality — **NIIT** ($250k MFJ), **IRMAA** brackets, and **Social Security taxation** provisional-income thresholds ($32k–$44k MFJ) — are also held at nominal 2024 values, which means they *tighten* in real terms over the horizon (a conservative, realistic bias). See `METHODOLOGY.md` §4.
- **Granularity:** taxes are computed once per simulated year at year-end, using that year's aggregated income by type.
- **Filing status:** either **Married Filing Jointly (MFJ)** or **Single**, driven by the configured wedding year. The engine selects the correct status automatically for each year; no other filing statuses (HoH, MFS, QW) are modeled.
- **Out of scope by design:** state taxes other than California (see §4 for substitution guidance), AMT, self-employment tax, FICA re-calculation in retirement, estate tax, gift tax, and foreign-tax credits.

---

## 2. Federal income tax (2024 MFJ)

### 2.1 Ordinary-income brackets (MFJ)

| Rate | Taxable income range (MFJ) |
|------|----------------------------|
| 10%  | $0 – $23,200               |
| 12%  | $23,200 – $94,300          |
| 22%  | $94,300 – $201,050         |
| 24%  | $201,050 – $383,900        |
| 32%  | $383,900 – $487,450        |
| 35%  | $487,450 – $731,200        |
| 37%  | $731,200+                  |

Single brackets are the MFJ thresholds halved for every tier except the 35%→37% boundary (which is not exactly half, per IRC §1); the engine uses the statutory Single table, not a naive halving.

### 2.2 Standard deduction (2024)

| Filing status | Standard deduction |
|---------------|--------------------|
| MFJ           | $29,200            |
| Single        | $14,600            |

**Age-65 additional standard deduction** (on top of the base):

| Filing status | Per qualifying spouse age 65+ |
|---------------|-------------------------------|
| MFJ           | +$1,550                       |
| Single        | +$1,950                       |

The engine itemizes only if `USE_ITEMIZED_DEDUCTION = True`; otherwise the standard deduction is always taken.

### 2.3 Income types flowing into ordinary income

- Wages, salary, bonuses
- RSUs (treated as ordinary wage income in the year of vest)
- Traditional 401(k) and Traditional IRA withdrawals
- Roth **conversions** (in the year of conversion)
- Taxable portion of Social Security (§5)
- Taxable interest and non-qualified dividends
- HSA non-qualified distributions (plus the 20% penalty; see §8)

---

## 3. Federal long-term capital gains (2024 MFJ)

### 3.1 LTCG brackets (MFJ)

| Rate | Taxable income range (MFJ) |
|------|----------------------------|
| 0%   | $0 – $94,050               |
| 15%  | $94,050 – $583,750         |
| 20%  | $583,750+                  |

LTCG stacks **on top of** ordinary income: the engine fills ordinary brackets first, then the LTCG brackets begin at the sum-of-incomes level. This matches the IRS Qualified Dividends and Capital Gain Tax Worksheet in the 1040 instructions.

### 3.2 Application to taxable-brokerage withdrawals

On a withdrawal of size `W` from taxable brokerage:

```
realized_gain = W × EMBEDDED_GAIN_RATIO
ordinary_cost_basis_recovered = W × (1 − EMBEDDED_GAIN_RATIO)
```

`EMBEDDED_GAIN_RATIO` defaults to **0.50** (assumes 50% of balance is unrealized gain at time of withdrawal) and is configurable. Only the gain portion is taxed; the cost basis flows through untaxed.

Short-term capital gains are not modeled — all holdings are assumed long-term by the time of withdrawal.

---

## 4. California state tax (2024 MFJ)

### 4.1 California brackets (MFJ)

| Rate  | Taxable income range (MFJ) |
|-------|----------------------------|
| 1.0%  | $0 – $21,512               |
| 2.0%  | $21,512 – $50,998          |
| 4.0%  | $50,998 – $80,490          |
| 6.0%  | $80,490 – $111,732         |
| 8.0%  | $111,732 – $141,212        |
| 9.3%  | $141,212 – $721,318        |
| 10.3% | $721,318 – $865,574        |
| 11.3% | $865,574 – $1,442,628      |
| 12.3% | $1,442,628+                |

A **1% mental health surtax** applies to CA taxable income over $1,000,000 and is added on top of the bracket rates.

### 4.2 California LTCG treatment

California **does not** provide preferential rates for long-term capital gains. All capital gains, qualified dividends, and Roth conversions are taxed as **ordinary income** at the bracket rates above.

California also **does not tax Social Security** benefits.

### 4.3 Substituting another state

For users outside California:

- Subclass `CaliforniaTaxBrackets` in `config.py` and override the bracket edges and rates with your state's table; or
- Set all rates in the bracket list to `0.0` for no-income-tax states (FL, TX, TN, WA, NV, SD, WY, AK, NH for wages only).

The engine does not currently model state-level LTCG preferences, reciprocity, or city income taxes (e.g. NYC, Philadelphia). Adding those requires extending the withdrawal-tax pipeline in `account_simulation.py`.

---

## 5. Social Security taxation

### 5.1 Provisional income

```
provisional_income = AGI_excluding_SS + 0.5 × SS_benefits + tax_exempt_interest
```

### 5.2 Taxable-SS thresholds (MFJ)

| Provisional income (MFJ) | Includable in taxable income |
|--------------------------|------------------------------|
| < $32,000                | 0%                           |
| $32,000 – $44,000        | up to 50% of SS              |
| > $44,000                | up to 85% of SS              |

The precise formula used by the engine (IRS Publication 915 worksheet):

```
lower = max(0, provisional_income − 32,000)        # MFJ
upper = max(0, provisional_income − 44,000)        # MFJ

taxable_SS = min(
    0.85 × SS,
    0.50 × min(SS, lower) + 0.85 × upper + 0.50 × min(6,000, ...)
)
```

### 5.3 Example (MFJ)

- SS benefits: $40,000
- Other AGI (Traditional withdrawals + LTCG): $60,000
- Provisional income: $60,000 + 0.5 × $40,000 = $80,000
- Excess above $44k: $36,000 → 85% × $36,000 = $30,600 potentially taxable
- Capped at 85% × $40,000 = $34,000
- **Taxable SS = $30,600 + small 50% tranche from the $32k–$44k band**, rounded.

California excludes the full $40,000 from state taxable income.

---

## 6. Net Investment Income Tax (NIIT)

- **Rate:** 3.8%
- **MAGI threshold (MFJ):** $250,000
- **MAGI threshold (Single):** $200,000

The tax applies to the **lesser** of:

1. Net investment income (interest, dividends, LTCG, taxable brokerage gains, passive rental income), or
2. MAGI − threshold.

The engine computes MAGI as AGI plus any excluded foreign earned income (not modeled) and the non-taxable portion of SS, per IRC §1411. NIIT does not apply to distributions from Traditional 401(k) or IRA (those are ordinary income, not investment income), nor to Roth distributions.

---

## 7. Medicare IRMAA

IRMAA surcharges apply to **Medicare Part B and Part D** premiums starting at age 65, based on **MAGI from two years prior**.

### 7.1 2024 IRMAA tiers (MFJ)

| MAGI (MFJ)            | Part B monthly surcharge | Part D monthly surcharge | Combined annual surcharge per person |
|-----------------------|--------------------------|--------------------------|--------------------------------------|
| ≤ $206,000            | $0.00                    | $0.00                    | $0                                   |
| $206,001 – $258,000   | $69.90                   | $12.90                   | $994                                 |
| $258,001 – $322,000   | $174.70                  | $33.30                   | $2,496                               |
| $322,001 – $386,000   | $279.50                  | $53.80                   | $3,999                               |
| $386,001 – $750,000   | $384.30                  | $74.20                   | $5,502                               |
| > $750,000            | $419.30                  | $81.00                   | $6,004                               |

Surcharges are **per person enrolled in Medicare**, so a couple on Medicare pays the surcharge twice.

### 7.2 Two-year lookback

The 2026 IRMAA surcharge is based on 2024 MAGI. The engine maintains a two-year MAGI history per simulation and applies the lookback automatically. In the first two retirement years after age 65, working-years MAGI dominates and often triggers high IRMAA brackets.

---

## 8. Early-withdrawal penalties

| Account type                              | Penalty before age 59½ | Exceptions modeled |
|-------------------------------------------|------------------------|--------------------|
| Traditional 401(k) / IRA                  | 10% of withdrawal       | None (Rule 72(t), SEPP, and separation-from-service exceptions are not modeled) |
| Roth IRA **contributions**                | 0% (always penalty-free) | N/A |
| Roth IRA **earnings** before 59½          | 10%                     | Not typically touched by the withdrawal waterfall |
| HSA non-qualified before age 65           | 20%                     | Qualified medical is always 0% |
| HSA non-qualified at or after age 65      | 0% (still ordinary income) | Medical remains tax-free |

Penalties are added to the federal tax bill for that year. They are not deductible against California tax.

---

## 9. Required Minimum Distributions

### 9.1 Start age (SECURE 2.0)

| Birth year      | RMD start age |
|-----------------|---------------|
| 1951 – 1959     | 73            |
| 1960 or later   | 75            |

### 9.2 Calculation

```
RMD_t = Balance_{t-1, Dec 31} / UniformLifetimeDivisor(age_t)
```

Applied separately to Traditional 401(k) and Traditional IRA balances. Roth IRAs have no RMD during the original owner's lifetime. HSAs have no RMD.

### 9.3 Uniform Lifetime Table (2024 version)

| Age | Divisor | Age | Divisor | Age | Divisor |
|-----|---------|-----|---------|-----|---------|
| 72  | 27.4    | 89  | 12.9    | 106 | 3.6     |
| 73  | 26.5    | 90  | 12.2    | 107 | 3.4     |
| 74  | 25.5    | 91  | 11.5    | 108 | 3.3     |
| 75  | 24.6    | 92  | 10.8    | 109 | 3.1     |
| 76  | 23.7    | 93  | 10.1    | 110 | 3.0     |
| 77  | 22.9    | 94  | 9.5     | 111 | 2.9     |
| 78  | 22.0    | 95  | 8.9     | 112 | 2.8     |
| 79  | 21.1    | 96  | 8.4     | 113 | 2.7     |
| 80  | 20.2    | 97  | 7.8     | 114 | 2.5     |
| 81  | 19.4    | 98  | 7.3     | 115 | 2.3     |
| 82  | 18.5    | 99  | 6.8     | 116 | 2.1     |
| 83  | 17.7    | 100 | 6.4     | 117 | 2.1     |
| 84  | 16.8    | 101 | 6.0     | 118 | 2.0     |
| 85  | 16.0    | 102 | 5.6     | 119 | 2.0     |
| 86  | 15.2    | 103 | 5.2     | 120+| 2.0     |
| 87  | 14.4    | 104 | 4.9     |     |         |
| 88  | 13.7    | 105 | 4.6     |     |         |

The engine linearly interpolates only at table boundaries; ages not in the table above 120 use divisor 2.0 per IRS rules.

---

## 10. Roth conversions

### 10.1 Tax treatment

The converted amount is included in **ordinary income** for the conversion year. It flows into the federal and California ordinary-income calculations as if it were a Traditional withdrawal, but with **no 10% early-withdrawal penalty** and **no withholding** assumed.

### 10.2 Five-year rule

The separate 5-year rule for each conversion (restricting penalty-free withdrawal of **converted principal** before 5 years have elapsed) is **not modeled**. Because the withdrawal waterfall draws Roth only after age 59½ in practice, this simplification is inconsequential for typical plans.

### 10.3 Strategic use

See `METHODOLOGY.md` §14 for the conversion policy (bracket-fill up to the 12% ceiling, $100k annual cap, stops at SS claim age).

---

## 11. Contribution limits (2024 base)

IRS limits are CPI-indexed in reality, so in the all-real frame they are **held flat at their 2024 values** (`CONTRIBUTION_LIMIT_INFLATION_RATE = 0.0`) — no per-year growth is applied.

| Account              | Base limit (2024) | Catch-up (age threshold)         |
|----------------------|-------------------|-----------------------------------|
| 401(k) elective      | $23,000           | +$7,500 at 50+                    |
| 401(k) total (EE+ER) | $69,000           | +$7,500 at 50+                    |
| IRA                  | $7,000            | +$1,000 at 50+                    |
| HSA — self-only      | $4,150            | +$1,000 at 55+                    |
| HSA — family         | $8,300            | +$1,000 at 55+ (per eligible spouse) |
| SS wage base         | $168,600          | N/A                               |

The backdoor Roth pathway uses the IRA limit; no separate cap is enforced for the conversion step itself.

---

## 12. Source references

- **IRS Publication 590-A** — Contributions to IRAs
- **IRS Publication 590-B** — Distributions from IRAs (Uniform Lifetime Table, RMD rules)
- **IRS Publication 915** — Social Security and Equivalent Railroad Retirement Benefits (provisional-income worksheet)
- **IRS Revenue Procedure 2023-34** — 2024 inflation adjustments for brackets, standard deduction, LTCG thresholds
- **IRS Notice 2023-75** — 2024 retirement plan contribution limits
- **IRC §1411** — Net Investment Income Tax
- **SSA POMS RS 00605 and RS 00615** — PIA computation and actuarial adjustments for early/delayed claiming
- **CMS Medicare IRMAA tables** — annual Part B and Part D surcharge schedules
- **California Franchise Tax Board Form 540 instructions** — state brackets, standard deduction, mental-health surtax
- **SECURE Act 2.0 (2022)** — RMD start-age increases
