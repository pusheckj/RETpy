# Tax Model

This document describes every tax rule encoded in the simulator, with bracket tables and formulas sufficient to audit the engine line-by-line against a spreadsheet or against IRS / FTB source documents.

---

## 1. Scope

- **Jurisdictions modeled:** US federal income tax, federal long-term capital gains tax, the Net Investment Income Tax (NIIT), Medicare IRMAA surcharges, payroll taxes on wages (FICA, plus California SDI), and **state income tax for all 50 states + DC** (`retirement_sim/state_tax_data.py`).
- **Tax year baseline:** **2026** for every federal figure (brackets, standard deduction and its 65+ add-on, the OBBBA senior deduction, LTCG thresholds, contribution limits, the Social Security wage base and earnings test, the Roth IRA and student-loan phase-outs, the child tax credit), for Medicare IRMAA (2026 CMS tiers), for ACA credits (Rev. Proc. 2025-25) and for **California**. The other state tables are still **2024**. Every 2026 figure was checked against primary sources in November 2026; the report, with quotes and links, is [`docs/data_sources/2026_verification.md`](data_sources/2026_verification.md).
- **Real frame:** the engine runs in an **all-real (today's-dollars) frame**: statutory items that are CPI-indexed in reality (federal ordinary/LTCG brackets, standard deduction and its 65+ add-on, contribution limits, the Social Security wage base, IRMAA tiers, ACA percentages, state tables) are held **flat at their real values**. Amounts that are *not* indexed in reality — **NIIT** ($250k/$200k), the **Additional Medicare Tax** ($250k/$200k), the **Social Security taxation** thresholds, the child-tax-credit phase-out, the $2,500 student-loan cap and the **senior deduction** ($6,000 and its $75k/$150k phase-out start) — decay in real terms over the horizon (`real_frozen_threshold`; a conservative, realistic bias). See `METHODOLOGY.md` §4.
- **Granularity:** working-year pay is taxed once per year by `working_year_taxes` (§2.4); retirement-year taxes are computed incrementally as income is recognized (withdrawals, RMDs, conversions, Social Security), each stacked on the income already on the return.
- **Filing status:** `FILING_STATUS` — **Married filing jointly**, **Single** or **Head of household** — selects every status-dependent table below, for the whole plan. An **unmarried couple** (a partner in the plan with a status other than MFJ) files **two returns**: you on `FILING_STATUS`, your partner as Single, each person's wages, withdrawals, RMDs, conversions, gains and Social Security on their own return (`files_two_returns()`, `return_status()`). Married filing separately and qualifying widow(er) are not modeled.
- **Out of scope by design:** AMT, self-employment tax, tax credits other than the working-year child tax credit (last subsection of section 11) and California's exemption credits (§4.1; the earned-income credit and other state credits are out), itemized deductions, city/county income taxes, estate and gift tax, foreign-tax credits.

---

## 2. Federal income tax (2026)

### 2.1 Ordinary-income brackets

Rev. Proc. 2025-32 §4.01. Head of household is its own schedule: its 24% and 32% bands end below the single ones.

| Rate | Married filing jointly | Single | Head of household |
|------|------------------------|--------|-------------------|
| 10%  | $0 – $24,800           | $0 – $12,400 | $0 – $17,700 |
| 12%  | – $100,800             | – $50,400 | – $67,450 |
| 22%  | – $211,400             | – $105,700 | – $105,700 |
| 24%  | – $403,550             | – $201,775 | – $201,750 |
| 32%  | – $512,450             | – $256,225 | – $256,200 |
| 35%  | – $768,700             | – $640,600 | – $640,600 |
| 37%  | above                  | above | above |

### 2.2 Standard deduction (2026)

| Filing status | Standard deduction | Per person 65+ |
|---------------|--------------------|----------------|
| MFJ           | $32,200            | +$1,650 per spouse |
| Single        | $16,100            | +$2,050 |
| HOH           | $24,150            | +$2,050 |

Rev. Proc. 2025-32 §4.14 (the OBBBA 2025 base, indexed). The 65+ add-on figures come from the same Rev. Proc.; they are not in the verification report. The engine never itemizes: the standard deduction is always taken. (`STANDARD_DEDUCTION_*_2024` remain as aliases of the 2026 values.)

### 2.2a Senior deduction (OBBBA, tax years 2025–2028)

`senior_deduction()` adds **$6,000 for each person on the return who is 65 or older by year end**, on top of the 65+ add-on. Each person's $6,000 is reduced by **6% of MAGI above $75,000** (single / head of household) or **$150,000** (joint), so it is gone at $175,000 / $250,000; a couple 65+ loses 12 cents per dollar above $150,000. A married couple must file jointly to claim it; an unmarried couple's two Single returns each qualify on their own. 26 U.S.C. §151(d)(5)(C).

- **Years:** plan year 0 is `CURRENT_YEAR` (2026), so the deduction applies while `CURRENT_YEAR + years_from_start ≤ 2028` and stops after (`SENIOR_DEDUCTION_LAST_YEAR`).
- **Not indexed:** the $6,000 and the phase-out starts are fixed dollars, so they shrink in real terms (`real_frozen_threshold`).
- **MAGI** is the return's income recognized so far (ordinary income plus realized gains). In retirement years the deduction is taken at the MAGI before and after each piece of income, so the phase-out's extra marginal rate shows up. For a capital gain the deduction is taken at the MAGI before the gain.
- Switch: `MODEL_SENIOR_DEDUCTION`.

Example (MFJ, both 66, 2026, MAGI $200,000): 2 × ($6,000 − 6% × $50,000) = **$6,000**, on top of $32,200 + 2 × $1,650.

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
federal  = brackets(status)[ wages + other − pre-tax 401(k) − HSA − student loan interest
                              − standard deduction (incl. 65+ add-on and senior deduction) ]
                                                                                    (per return)
state    = state brackets(status)[ state income − student loan interest − state deduction ]
           − state exemption credits + state surtax + state payroll tax
FICA     = 6.2% × min(wages − HSA, $184,500)          per earner (2026 wage base)
         + 1.45% × (wages − HSA)                       per earner
         + 0.9% × max(0, return's wages − $250k/$200k) per return (Additional Medicare Tax)
take-home = wages + other − 401(k) (pre-tax and Roth) − HSA − federal − state − FICA
```

**Roth catch-up (SECURE 2.0, from 2026).** If a person's FICA wages in the prior year passed **$150,000** (`ROTH_CATCHUP_WAGE_THRESHOLD`; $145,000 indexed, the IRS figure for 2026), their 401(k) catch-up (the part of the deferral above the $24,500 regular limit: $8,000 at 50+, $11,250 at 60-63) is Roth: it doesn't lower taxable pay and lands in the Roth account (`your_roth_ira` / `partner_roth_ira`; the engine has no separate Roth 401(k), and the tax treatment is the same). Prior-year wages are the comp table's row for the year before (the partner's salary a year earlier); the sidebar's Taxes panel uses this year's pay. Switch: `MODEL_ROTH_CATCHUP_RULE`.

**Student loan interest deduction.** Interest paid on `DEBTS` of kind `student_loan` (`config.student_loan_interest_for_age`, from the payoff math) is deducted above the line, up to **$2,500** a year, phased out linearly over modified AGI (AGI before this deduction) of **$85,000-$100,000** (single, head of household) or **$175,000-$205,000** (joint). The cap has never been indexed, so it decays in real terms like NIIT; the ranges are indexed and stay flat. States are assumed to follow the federal deduction. It goes on your return (on an unmarried couple's two returns, yours). Working years only. Switch: `STUDENT_LOAN_INTEREST_DEDUCTION_MAX = 0`.

401(k) deferrals remain FICA wages; HSA contributions made through payroll do not. On a joint return each spouse's share of the income tax is pro-rata to their taxable income (used to attribute savings to each person's accounts). A comp-table row that sets `after_tax` overrides the primary's computed take-home.

The employer 401(k) match is `min(deferral, match % × base)`, per person, on the whole deferral (a Roth catch-up included). The partner's Roth IRA contribution is limited by the IRA limit and earned income, with no income phase-out: above the direct-Roth range it is a backdoor Roth, as the primary's `YOUR_BACKDOOR_ROTH` is.

---

## 3. Federal long-term capital gains (2026)

### 3.1 LTCG brackets

Rev. Proc. 2025-32 §4.03.

| Rate | Married filing jointly | Single | Head of household |
|------|------------------------|--------|-------------------|
| 0%   | $0 – $98,900           | $0 – $49,450 | $0 – $66,200 |
| 15%  | – $613,700             | – $545,500 | – $579,600 |
| 20%  | above                  | above | above |

LTCG stacks **on top of** taxable ordinary income on the same return: ordinary brackets fill first, then the LTCG brackets begin at that level (IRS Qualified Dividends and Capital Gain Tax Worksheet). Gains realized earlier in the year are part of the stacking base.

### 3.2 Application to taxable-brokerage withdrawals

On a withdrawal of size `W` from taxable brokerage, the gain is `W × (1 − cost_basis / balance)`; only the gain portion is taxed and the cost basis is reduced pro-rata. Short-term capital gains are not modeled.

---

## 4. State income tax (all states + DC; 2024 tables, California 2026)

`STATE_CHOICE` is a two-letter code (or `"DC"`). `config.state_tax_rules(code, status)` reads the state's row in `state_tax_data.py`:

- **Brackets** by filing status (or a flat rate), applied to state income minus the state's **standard deduction** (`"federal"` = the federal amount) and **personal exemptions** (per person, two on a joint return).
- **Social Security**: `exempt` (most states), `taxed` (Montana, Utah: the federally taxable part), or exempt below an income limit (Minnesota, New Mexico, Rhode Island, Vermont).
- **Retirement-income exclusion**: per-person yearly amounts of traditional 401(k)/IRA distributions the state exempts from an age (e.g. Illinois and Mississippi all, Pennsylvania all after 59½, Iowa all at 55+, Georgia $35k at 62 / $65k at 65, New York $20k at 59½, South Carolina $3k / $10k at 65). Roth conversions never qualify.
- **Capital gains**: taxed as ordinary income, less a state exclusion where one exists (Arkansas 50%, South Carolina 44%, North Dakota 40%, Wisconsin 30%).
- **Wage quirks**: Pennsylvania taxes 401(k) deferrals; California and New Jersey tax HSA contributions; California State Disability Insurance (1.1% of all wages, the 2024 rate) is counted with state tax.
- **Exemption credits and surtax** (rows with `exemption_credits` / `surtax`; today only California): `config.state_income_tax` takes the nonrefundable credits off the bracket tax and adds the surtax on top.

Each row carries its **tax year** and a **confidence**: `high` (complete within rounding for a typical household), `medium` (rates and brackets right; a credit, phase-out or local tax left out — see the row's note), or `approx` (simplified or uncertain; the app labels the state approximate). As of this version: approximate �� Alabama, Arkansas, Hawaii, Nebraska, Wisconsin. City and county income taxes (Maryland counties, NYC, Ohio/Pennsylvania/Michigan cities, Indiana counties…) are **not** included. `docs/state_tax_research_prompt.md` lists exactly what to verify.

Legacy values: `"No state tax"` (zero) and `"Other"` (flat `YOUR_MARGINAL_TAX_RATE` above the federal standard deduction, Social Security exempt). Unknown values fall back to `"CA"`. `MODEL_CA_EXEMPTS_SOCIAL_SECURITY = False` (historical name) turns every state's Social Security exemption off.

### 4.1 California (2026)

FTB Tax News, October 2026 (3.4% indexing). Brackets apply to taxable income after the standard deduction. Head of household is its own schedule.

| Rate  | Married filing jointly | Single | Head of household |
|-------|------------------------|--------|-------------------|
| 1.0%  | $0 – $22,912           | $0 – $11,456 | $0 – $22,927 |
| 2.0%  | – $54,314              | – $27,157 | – $54,316 |
| 4.0%  | – $85,722              | – $42,861 | – $70,018 |
| 6.0%  | – $118,996             | – $59,498 | – $86,654 |
| 8.0%  | – $150,394             | – $75,197 | – $102,356 |
| 9.3%  | – $768,218             | – $384,109 | – $522,385 |
| 10.3% | – $921,854             | – $460,927 | – $626,864 |
| 11.3% | – $1,536,426           | – $768,213 | – $1,044,771 |
| 12.3% | above                  | above | above |

- **Standard deduction:** $5,900 single, $11,800 joint and head of household.
- **Exemption credits** (nonrefundable, off the tax): personal $158 per person on the return ($316 joint), senior $158 per person 65+, dependent $491 per child under 17 (the child-tax-credit count; older dependents are left out). The senior figure is inferred from the 2025 Form 540, where personal, blind and senior are equal. Blind credits are not modeled.
- **Credit phase-out:** each credit falls by $6 for every $2,500 (or part) of AGI above **$260,778 single / $521,561 joint / $391,173 head of household**. These 2026 thresholds are **estimates** (2025 × 1.034): the FTB had not published them. The engine takes AGI as taxable income plus the deduction (in working years, the federal AGI of the return).
- **Behavioral Health Services Tax:** 1% of taxable income above **$1,000,000**, every filing status, added after the credits. It is a separate tax, not a tenth bracket.
- Capital gains are ordinary income; Social Security is exempt.

Example (single, $80,000 wages, under 65, no children): taxable $80,000 − $5,900 = $74,100 → bracket tax $3,223.12 − $158 credit = **$3,065.12**, plus SDI.

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

### 5.3 Earnings test

Benefits claimed before full retirement age while still working are reduced before any of this: $1 for every $2 of wages above $24,480, $1 for every $3 above $65,160 in the year of full retirement age (2026 limits, flat in today's dollars). Withheld benefits are not income. From full retirement age the benefit is raised as if the claim had come later by the months withheld. See `METHODOLOGY.md` §12.4.

### 5.4 Example (MFJ)

SS $40,000; other AGI $60,000; provisional income $80,000 → 0.85 × 36,000 + 6,000 = $36,600, capped at 0.85 × 40,000 = **$34,000** taxable.

---

## 6. Net Investment Income Tax (NIIT)

- **Rate:** 3.8%
- **MAGI threshold:** $250,000 (MFJ), $200,000 (Single / HOH) — per return, never indexed (decays in real terms)

The tax applies to the **lesser** of net investment income (here: realized brokerage gains) and MAGI − threshold. It does not apply to Traditional 401(k)/IRA or Roth distributions.

---

## 7. Medicare premiums and IRMAA

Per person enrolled in Medicare (65+), `calculate_medicare_irmaa` charges the Part B premium of the MAGI tier, the Part D surcharge of that tier, and `MEDICARE_SUPPLEMENTAL_MONTHLY_PER_PERSON` ($200 a month: an **estimate** of a Part D plan, about $40, plus a Medigap Plan G, about $160; not a CMS figure). The 'medicare_*' healthcare bands then act as an all-in floor (`METHODOLOGY.md`). `MEDICARE_MONTHLY_PREMIUM` ($805.80, a couple at the standard tier) is a reference figure the engine does not read.

In law the tier is set by MAGI from **two years earlier** (2024 income sets 2026 premiums). The engine keeps its convention of testing the **current year's** MAGI: close for a steady retirement, two years early around a big change in income.

### 7.1 2026 tiers (monthly, per person)

CMS fact sheet, November 14, 2025. Standard Part B premium $202.90; Part B deductible $283 (not modeled).

| MAGI (MFJ) | MAGI (individual) | Part B | Part D surcharge |
|------------|-------------------|--------|------------------|
| ≤ $218,000 | ≤ $109,000 | $202.90 | $0.00 |
| > $218,000 | > $109,000 | $284.10 | $14.50 |
| > $274,000 | > $137,000 | $405.80 | $37.50 |
| > $342,000 | > $171,000 | $527.50 | $60.40 |
| > $410,000 | > $205,000 | $649.20 | $83.30 |
| ≥ $750,000 | ≥ $500,000 | $689.90 | $91.00 |

An unmarried couple's household MAGI is split evenly and each person is tested on the individual tiers. IRMAA tiers are indexed, so they are held flat in the real frame.

### 7.2 ACA premium tax credit (2026)

Before Medicare, marketplace members pay `min(MAGI × applicable %, full benchmark price)` (`aca_applicable_pct`, `ACA_APPLICABLE_PCT_BANDS`, Rev. Proc. 2025-25). The percentage rises linearly inside each band:

| FPL | Applicable % |
|-----|--------------|
| below 133% | 2.10% |
| 133% – 150% | 3.14% → 4.19% |
| 150% – 200% | 4.19% → 6.60% |
| 200% – 250% | 6.60% → 8.44% |
| 250% – 300% | 8.44% → 9.96% |
| 300% – 400% | 9.96% |
| 400% and above | no credit (full price) |

The enhanced credits expired December 31, 2025, so the 400% cliff is back. **Legislative watch:** the House passed a 3-year extension in January 2026; the Senate had not acted as of November 2026, so current law is modeled. FPL is the 2025 HHS guideline ($15,650 + $5,500 per extra person), which sets 2026 coverage. The benchmark premium for a 40-year-old is $625 a month (KFF, a secondary source). Below 100% FPL the law generally gives no credit (Medicaid); the model does not make that cut.

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

See `METHODOLOGY.md` §14 for the conversion policy (fill ordinary income up to the top of the 12% bracket for the filing status — $100,800 / $50,400 / $67,450 (2026) — unless `ROTH_CONVERSION_TARGET_BRACKET` is set; $100k annual cap; stops at `ROTH_CONVERSION_STOP_AGE`). An unmarried couple fills each person's own return.

---

## 11. Contribution limits (2026 base)

IRS limits are CPI-indexed in reality, so in the all-real frame they are **held flat at their 2026 values** (`LIMITS_BASE_YEAR`, `CONTRIBUTION_LIMIT_INFLATION_RATE = 0.0`) — no per-year growth is applied.

| Account              | Base limit (2026) | Catch-up (age threshold)         |
|----------------------|-------------------|-----------------------------------|
| 401(k) elective      | $24,500           | +$8,000 at 50+; +$11,250 instead at 60-63 |
| 401(k) total (EE+ER) | $72,000           | same catch-up as above            |
| IRA                  | $7,500            | +$1,100 at 50+                    |
| HSA — self-only      | $4,400            | +$1,000 at 55+                    |
| HSA — family         | $8,750            | +$1,000 at 55+ (per eligible spouse) |
| SS wage base         | $184,500 (2026)   | N/A                               |
| Roth IRA phase-out (MAGI) | $153,000-$168,000 single / HOH; $242,000-$252,000 joint | N/A |

Sources: IRS Notice 2025-67 (401(k), IRA, 415(c), Roth IRA phase-out, the $150,000 Roth catch-up wage threshold), Rev. Proc. 2025-19 (HSA), SSA's 2026 COLA fact sheet (wage base, earnings-test limits). High earners' catch-up is Roth (§2.4). The Roth IRA phase-out table (`ROTH_IRA_PHASEOUT_BY_STATUS`) is the one the Money check-up uses; the planner treats a Roth IRA above it as a backdoor Roth. The HSA uses the **family** limit when the plan has a partner or any child, else the self-only limit (`cfg.hsa_is_family`).

The backdoor Roth pathway uses the IRA limit; no separate cap is enforced for the conversion step itself.

---

### Child tax credit (working years)

$2,200 per child under 17 (One Big Beautiful Bill Act, 2025; indexed later, so flat in the real frame), off the federal tax of the return you file. It phases out by $50 per $1,000 of MAGI over $200,000 (single / head of household) or $400,000 (joint); those thresholds are not indexed and decay in real terms. If the credit is more than the tax, the refundable part pays out the rest, up to $1,700 a child and 15% of earned income over $2,500, so federal tax can be negative. An unmarried couple's children go on your return. Retirement-year taxes carry no credits. Switch: `MODEL_CHILD_TAX_CREDIT`. The 2026 amounts ($2,200 / $1,700) are confirmed by Rev. Proc. 2025-32 §4.05.

## 12. Source references

- **IRS Publication 590-A** — Contributions to IRAs
- **IRS Publication 590-B** — Distributions from IRAs (Uniform Lifetime Table, RMD rules)
- **IRS Publication 915** — Social Security and Equivalent Railroad Retirement Benefits (provisional-income worksheet)
- **2026 verification report** — [`docs/data_sources/2026_verification.md`](data_sources/2026_verification.md): every 2026 figure below with its primary source, quote and status (changed / confirmed)
- **IRS Revenue Procedure 2025-32** — 2026 brackets, standard deduction (and 65+ add-on), LTCG thresholds, child tax credit, student-loan phase-out
- **26 U.S.C. §151(d)(5)(C)** (OBBBA §70103) — the 2025–2028 senior deduction
- **IRS Revenue Procedure 2025-25** — 2026 ACA applicable percentage table
- **IRS Notice 2025-67** — 2026 retirement plan contribution limits
- **IRC §1411** — Net Investment Income Tax
- **SSA POMS RS 00605 and RS 00615** — PIA computation and actuarial adjustments for early/delayed claiming
- **CMS 2026 Medicare Parts B premiums and deductibles fact sheet** — standard premium and IRMAA tiers
- **California Franchise Tax Board, Tax News October 2026** — 2026 brackets, standard deduction, exemption credits; Behavioral Health Services Tax
- **State revenue department 2024 forms and rate schedules** — the other state rows in `state_tax_data.py` (each row's `confidence` and `note` say how complete it is)
- **IRS Publication 15 / Topic 560** — FICA rates, the Additional Medicare Tax; **SSA 2026 COLA fact sheet** — the $184,500 wage base and the $24,480 / $65,160 earnings-test limits
- **IRS Publication 970** — student loan interest deduction (2026 phase-out from Rev. Proc. 2025-32)
- **SECURE Act 2.0 (2022)** — RMD start-age increases
