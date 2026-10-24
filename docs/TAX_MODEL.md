# Tax Model

This document describes every tax rule encoded in the simulator, with bracket tables and formulas sufficient to audit the engine line-by-line against a spreadsheet or against IRS / FTB source documents.

---

## 1. Scope

- **Jurisdictions modeled:** US federal income tax, federal long-term capital gains tax, the Net Investment Income Tax (NIIT), Medicare IRMAA surcharges, payroll taxes on wages (FICA, plus California SDI), and **state income tax for all 50 states + DC** (`retirement_sim/state_tax_data.py`).
- **Tax year baseline:** **2024** statutory brackets, thresholds, and contribution limits (IRMAA uses the 2025 CMS tiers). The engine runs in an **all-real (today's-dollars) frame**: statutory items that are CPI-indexed in reality (federal ordinary/LTCG brackets, standard deduction, contribution limits, the Social Security wage base, IRMAA tiers, state tables) are held **flat at their real values**. Thresholds that are *not* indexed in reality — **NIIT** ($250k/$200k), the **Additional Medicare Tax** ($250k/$200k) and the **Social Security taxation** thresholds — decay in real terms over the horizon (a conservative, realistic bias). See `METHODOLOGY.md` §4.
- **Granularity:** working-year pay is taxed once per year by `working_year_taxes` (§2.4); retirement-year taxes are computed incrementally as income is recognized (withdrawals, RMDs, conversions, Social Security), each stacked on the income already on the return.
- **Filing status:** `FILING_STATUS` — **Married filing jointly**, **Single** or **Head of household** — selects every status-dependent table below, for the whole plan. An **unmarried couple** (a partner in the plan with a status other than MFJ) files **two returns**: you on `FILING_STATUS`, your partner as Single, each person's wages, withdrawals, RMDs, conversions, gains and Social Security on their own return (`files_two_returns()`, `return_status()`). Married filing separately and qualifying widow(er) are not modeled.
- **Out of scope by design:** AMT, self-employment tax, tax credits (child tax credit, earned-income credit, state credits), itemized deductions, city/county income taxes, estate and gift tax, foreign-tax credits.

---

## 2. Federal income tax (2024)

### 2.1 Ordinary-income brackets

| Rate | Married filing jointly | Single | Head of household |
|------|------------------------|--------|-------------------|
| 10%  | $0 – $23,200           | $0 – $11,600 | $0 – $16,550 |
| 12%  | – $94,300              | – $47,150 | – $63,100 |
| 22%  | – $201,050             | – $100,525 | – $100,500 |
| 24%  | – $383,900             | – $191,950 | – $191,950 |
| 32%  | – $487,450             | – $243,725 | – $243,700 |
| 35%  | – $731,200             | – $609,350 | – $609,350 |
| 37%  | above                  | above | above |

### 2.2 Standard deduction (2024)

| Filing status | Standard deduction | Per person 65+ |
|---------------|--------------------|----------------|
| MFJ           | $29,200            | +$1,550 per spouse |
| Single        | $14,600            | +$1,950 |
| HOH           | $21,900            | +$1,950 |

The engine itemizes only if `USE_ITEMIZED_DEDUCTION = True`; otherwise the standard deduction is always taken.

### 2.3 Income types flowing into ordinary income

- Wages, salary, bonuses, RSUs (in the year of vest), less pre-tax 401(k) and HSA deferrals
- Other income (`YOUR_OTHER_INCOME` / `PARTNER_OTHER_INCOME`)
- Traditional 401(k) and Traditional IRA withdrawals, RMDs, 72(t) distributions
- Roth **conversions** (in the year of conversion)
- Taxable portion of Social Security (§5)
- HSA non-qualified distributions (plus the 20% penalty; see §8)

### 2.4 Working-year taxes and take-home

`config.working_year_taxes()` is the single source of the tax on a year's pay; `account_simulation.working_year_cashflow()` feeds it the year's pay and deferrals and the engine, the sidebar's Taxes panel (`ui/utils/derived.compute_taxes`) and the tax chart all read the result:

```
federal  = brackets(status)[ wages + other − 401(k) − HSA − standard deduction ]   (per return)
state    = state brackets(status)[ state income − state deduction ] + state payroll tax
FICA     = 6.2% × min(wages − HSA, $168,600)          per earner
         + 1.45% × (wages − HSA)                       per earner
         + 0.9% × max(0, return's wages − $250k/$200k) per return (Additional Medicare Tax)
take-home = wages + other − 401(k) − HSA − federal − state − FICA
```

401(k) deferrals remain FICA wages; HSA contributions made through payroll do not. On a joint return each spouse's share of the income tax is pro-rata to their taxable income (used to attribute savings to each person's accounts). A comp-table row that sets `after_tax` overrides the primary's computed take-home.

The employer 401(k) match is `min(deferral, match % × base)`, per person. The partner's direct Roth IRA contribution is reduced across the 2024 phase-out (MAGI $230k–$240k joint, $146k–$161k otherwise) of the return it's on.

---

## 3. Federal long-term capital gains (2024)

### 3.1 LTCG brackets

| Rate | Married filing jointly | Single | Head of household |
|------|------------------------|--------|-------------------|
| 0%   | $0 – $94,050           | $0 – $47,025 | $0 – $63,000 |
| 15%  | – $583,750             | – $518,900 | – $551,350 |
| 20%  | above                  | above | above |

LTCG stacks **on top of** taxable ordinary income on the same return: ordinary brackets fill first, then the LTCG brackets begin at that level (IRS Qualified Dividends and Capital Gain Tax Worksheet). Gains realized earlier in the year are part of the stacking base.

### 3.2 Application to taxable-brokerage withdrawals

On a withdrawal of size `W` from taxable brokerage, the gain is `W × (1 − cost_basis / balance)`; only the gain portion is taxed and the cost basis is reduced pro-rata. Short-term capital gains are not modeled.

---

## 4. State income tax (all states + DC, 2024)

`STATE_CHOICE` is a two-letter code (or `"DC"`). `config.state_tax_rules(code, status)` reads the state's row in `state_tax_data.py`:

- **Brackets** by filing status (or a flat rate), applied to state income minus the state's **standard deduction** (`"federal"` = the federal amount) and **personal exemptions** (per person, two on a joint return).
- **Social Security**: `exempt` (most states), `taxed` (Montana, Utah: the federally taxable part), or exempt below an income limit (Minnesota, New Mexico, Rhode Island, Vermont).
- **Retirement-income exclusion**: per-person yearly amounts of traditional 401(k)/IRA distributions the state exempts from an age (e.g. Illinois and Mississippi all, Pennsylvania all after 59½, Iowa all at 55+, Georgia $35k at 62 / $65k at 65, New York $20k at 59½, South Carolina $3k / $10k at 65). Roth conversions never qualify.
- **Capital gains**: taxed as ordinary income, less a state exclusion where one exists (Arkansas 50%, South Carolina 44%, North Dakota 40%, Wisconsin 30%).
- **Wage quirks**: Pennsylvania taxes 401(k) deferrals; California and New Jersey tax HSA contributions; California State Disability Insurance (1.1% of all wages in 2024) is counted with state tax.

Each row carries its **tax year** and a **confidence**: `high` (complete within rounding for a typical household), `medium` (rates and brackets right; a credit, phase-out or local tax left out — see the row's note), or `approx` (simplified or uncertain; the app labels the state approximate). As of this version: approximate �� Alabama, Arkansas, Hawaii, Nebraska, Wisconsin. City and county income taxes (Maryland counties, NYC, Ohio/Pennsylvania/Michigan cities, Indiana counties…) are **not** included. `docs/state_tax_research_prompt.md` lists exactly what to verify.

Legacy values: `"No state tax"` (zero) and `"Other"` (flat `YOUR_MARGINAL_TAX_RATE` above the federal standard deduction, Social Security exempt). Unknown values fall back to `"CA"`. `MODEL_CA_EXEMPTS_SOCIAL_SECURITY = False` (historical name) turns every state's Social Security exemption off.

### 4.1 Example: California (2024)

| Rate  | Married filing jointly | Single | Head of household |
|-------|------------------------|--------|-------------------|
| 1.0%  | $0 – $21,512           | $0 – $10,756 | $0 – $21,527 |
| 2.0%  | – $50,998              | – $25,499 | – $51,000 |
| 4.0%  | – $80,490              | – $40,245 | – $65,744 |
| 6.0%  | – $111,732             | – $55,866 | – $81,364 |
| 8.0%  | – $141,212             | – $70,606 | – $96,107 |
| 9.3%  | – $721,318             | – $360,659 | – $490,493 |
| 10.3% | – $865,574             | – $432,787 | – $588,593 |
| 11.3% | – $1,442,628           | – $721,314 | – $980,987 |
| 12.3% | above                  | above | above |

Standard deduction $11,080 joint / head of household, $5,540 single; a 1% mental-health surtax applies above $1,000,000 (any status). Capital gains are ordinary income; Social Security is exempt. (The engine previously used the 2023 brackets; the 2024 figures lower CA tax by about $90–$220 a year for a typical household.)

---

## 5. Social Security taxation

### 5.1 Provisional income

```
provisional_income = AGI_excluding_SS + 0.5 × SS_benefits
```

### 5.2 Thresholds

| Provisional income | MFJ | Single / HOH | Includable |
|---|---|---|---|
| below the first | $32,000 | $25,000 | 0% |
| between | $32,000 – $44,000 | $25,000 – $34,000 | up to 50% |
| above the second | > $44,000 | > $34,000 | up to 85% |

```
taxable_SS = 0                                              if PI ≤ t1
           = min(0.5 × (PI − t1), 0.5 × SS)                 if t1 < PI ≤ t2
           = min(0.85 × SS, 0.85 × (PI − t2) + min(0.5 × (t2 − t1), 0.5 × SS))   otherwise
```

The thresholds were set in 1983/1993 and are never indexed, so they decay in real terms. On two returns each person's own benefit and income are used. State treatment follows §4.

### 5.3 Example (MFJ)

SS $40,000; other AGI $60,000; provisional income $80,000 → 0.85 × 36,000 + 6,000 = $36,600, capped at 0.85 × 40,000 = **$34,000** taxable.

---

## 6. Net Investment Income Tax (NIIT)

- **Rate:** 3.8%
- **MAGI threshold:** $250,000 (MFJ), $200,000 (Single / HOH) — per return, never indexed (decays in real terms)

The tax applies to the **lesser** of net investment income (here: realized brokerage gains) and MAGI − threshold. It does not apply to Traditional 401(k)/IRA or Roth distributions.

---

## 7. Medicare IRMAA

IRMAA surcharges apply to **Medicare Part B and Part D** premiums starting at age 65. The engine uses the current year's MAGI as a stand-in for the two-year lookback.

### 7.1 2025 tiers (monthly Part B premium / Part D surcharge, per person)

| MAGI (MFJ) | MAGI (individual) | Part B | Part D |
|------------|-------------------|--------|--------|
| < $212,000 | < $106,000 | $185.00 | $0.00 |
| $212,000+ | $106,000+ | $259.00 | $13.70 |
| $266,000+ | $133,000+ | $370.00 | $35.30 |
| $334,000+ | $167,000+ | $480.90 | $57.00 |
| $400,000+ | $200,000+ | $591.90 | $78.60 |
| $750,000+ | $500,000+ | $628.90 | $85.80 |

Premiums are **per person enrolled in Medicare**. An unmarried couple's household MAGI is split evenly and each person is tested on the individual tiers. IRMAA tiers are indexed, so they are held flat in the real frame.

---

## 8. Early-withdrawal penalties

| Account type                              | Penalty before age 59½ | Exceptions modeled |
|-------------------------------------------|------------------------|--------------------|
| Traditional 401(k) / IRA                  | 10% of withdrawal       | None (Rule 72(t), SEPP, and separation-from-service exceptions are not modeled) |
| Roth IRA **contributions**                | 0% (always penalty-free) | N/A |
| Roth IRA **earnings** before 59½          | 10%                     | Not typically touched by the withdrawal waterfall |
| HSA non-qualified before age 65           | 20%                     | Qualified medical is always 0% |
| HSA non-qualified at or after age 65      | 0% (still ordinary income) | Medical remains tax-free |

Penalties are added to the federal tax bill for that year. They are not deductible against state tax.

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

The converted amount is included in **ordinary income** for the conversion year. It flows into the federal and state ordinary-income calculations as if it were a Traditional withdrawal, but with **no 10% early-withdrawal penalty** and **no withholding** assumed.

### 10.2 Five-year rule

The separate 5-year rule for each conversion (restricting penalty-free withdrawal of **converted principal** before 5 years have elapsed) is **not modeled**. Because the withdrawal waterfall draws Roth only after age 59½ in practice, this simplification is inconsequential for typical plans.

### 10.3 Strategic use

See `METHODOLOGY.md` §14 for the conversion policy (fill ordinary income up to the top of the 12% bracket for the filing status — $94,300 / $47,150 / $63,100 — unless `ROTH_CONVERSION_TARGET_BRACKET` is set; $100k annual cap; stops at `ROTH_CONVERSION_STOP_AGE`). An unmarried couple fills each person's own return.

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
- **State revenue department 2024 forms and rate schedules** — the other state rows in `state_tax_data.py` (each row's `confidence` and `note` say how complete it is)
- **IRS Publication 15 / Topic 560** — FICA rates, the 2024 Social Security wage base, the Additional Medicare Tax
- **SECURE Act 2.0 (2022)** — RMD start-age increases
