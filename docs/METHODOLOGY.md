# Methodology

This document describes the modeling assumptions, math, and code flow behind the retirement Monte Carlo simulator. It is intended for readers who want to audit the engine against their own spreadsheets or academic references before trusting the output.

---

## 1. Overview

A **Monte Carlo retirement simulation** projects a household's portfolio forward one year at a time under randomized market and inflation conditions, and repeats that projection thousands of times to estimate the probability that the plan survives to a target age. Because market returns, inflation, and sequence-of-returns risk are all stochastic, a single deterministic projection is not sufficient to characterize risk — Monte Carlo captures the full distribution of outcomes.

**The core question this tool answers:**

> What is the earliest retirement age at which the plan achieves at least X% probability of success?

**Success** is defined strictly: in every simulated year from the retirement age through the plan's end (`PLAN_UNTIL_AGE`, default 95, or later if a younger partner's own plan-until age comes later; see `plan_end_age()`), the portfolio must be able to cover at least **99%** of the required withdrawal for that year. A single year of coverage below 99% marks the path as a failure. The success rate for a given retirement age is the fraction of simulated paths that survive all years.

The output is a success probability curve over candidate retirement ages. The solver walks back from an upper-bound age until the first age whose success rate meets or exceeds `TARGET_SUCCESS_RATE` (default 0.80).

---

## 2. Simulation flow

For each candidate retirement age:

1. Run `NUM_SIMULATIONS` (default **10,000**) independent simulations.
2. Each simulation generates:
   - An annual path of stock and bond returns (correlated, see Section 3).
   - An annual path of inflation rates, one per expense category (see Section 4).
3. Each simulation runs year-by-year from the user's current age to the plan's end: the later of you reaching `PLAN_UNTIL_AGE` and your partner reaching `PARTNER_PLAN_UNTIL_AGE` (same age by default).
4. The lifecycle splits into two phases:
   - **Accumulation phase:** current age → retirement age. Contributions flow in; returns compound.
   - **Retirement phase:** retirement age → the plan's end. Withdrawals flow out; Social Security and RMDs provide income offsets.
5. If at any point the portfolio cannot cover 99% of the required withdrawal, the simulation is marked a failure and terminates.

Simulations are independent; there is no cross-path state.

---

## 3. Return model

### 3.1 Parametric Monte Carlo

The default engine draws annual stock and bond returns from a **multivariate normal distribution** with configurable means, volatilities, and a stock/bond correlation. Real (inflation-adjusted) returns are sampled directly so that the model operates in today's dollars throughout. An optional historical-sequence mode is available for sequence-of-returns stress testing, but it is not the default.

### 3.2 Correlated returns (Cholesky decomposition)

Stock and bond returns are jointly sampled to preserve the observed negative-to-low correlation between equities and Treasuries. Given the covariance matrix

```
Σ = [ σ_s²           ρ σ_s σ_b ]
    [ ρ σ_s σ_b      σ_b²       ]
```

the engine computes its Cholesky factor `L` (so `Σ = L Lᵀ`) and generates correlated draws as `r = μ + L z`, where `z` is a vector of i.i.d. standard-normal samples.

### 3.3 Fees and volatility drag

1. **Investment fees** are subtracted from the arithmetic mean *before* the volatility-drag adjustment.
2. **Volatility drag** converts arithmetic to geometric expected return:

```
geometric_return ≈ arithmetic_return − σ² / 2
```

This ensures the compounded growth of the simulated portfolio matches the stated real CAGR rather than overstating it.

### 3.4 Clamping

Annual portfolio returns are clamped to **[−35%, +50%]** for an 80/20 portfolio. These bounds bracket the worst 12-month real return in the historical S&P 500/Treasury record (≈ −38.5%, 1931) and the best (≈ +57.6%, 1933). Clamping prevents pathological tail draws from dominating the distribution while still allowing credible crisis-level drawdowns.

### 3.5 Scenarios

All values below are **real** (inflation-adjusted) returns.

| Scenario     | Stock real return | Bond real return | Stock σ | Bond σ | Correlation |
|--------------|-------------------|------------------|---------|--------|-------------|
| Conservative | 7.0%              | 2.0%             | 17%     | 7%     | 0.10        |
| Historical   | 8.7%              | 3.1%             | 17%     | 7%     | 0.10        |
| Pessimistic  | 5.0%              | 1.0%             | 17%     | 7%     | 0.10        |

`ACTIVE_RETURN_SCENARIO` selects one of these at run time.

---

## 4. Inflation

The entire model operates in a consistent **all-real (today's-dollars) frame**: investment returns are drawn real (Section 3), so every liability must also live in real dollars for the comparison to be apples-to-apples. Consequently **general CPI never grows any liability** — anything that merely tracks general inflation (most living expenses, leisure, college/529, and Social Security, which is COLA-indexed) is held **flat in real terms**.

The only categories that *grow* are those that historically **outpace** general CPI. They grow at their **real-excess rate** = (category mean − general mean), i.e. the portion of their nominal inflation left over after deflating by general CPI:

| Category    | Nominal mean | Real-excess (mean − general) | Notes                                      |
|-------------|--------------|------------------------------|--------------------------------------------|
| General     | 2.75%        | **0.00%** (flat in real terms) | Most discretionary and non-housing spend; SS (COLA) |
| Healthcare  | 4.50%        | **1.75%**                    | ACA/Medicare premiums, OOP, LTC            |
| Housing     | 2.75%        | **0.00%** (flat in real terms) | Property tax, utilities, maintenance      |
| Childcare   | 4.00%        | **1.25%**                    | Daycare, camps, activities                 |

Each real-excess category follows an **independent random walk**: each year's draw is normal with the real-excess mean above and volatility ~1.5%. The general factor is pinned at **1.0** for the whole horizon.

> **Limitation — frozen-nominal statutory thresholds.** A handful of tax thresholds are specified in *nominal* dollars by statute and are **not** inflation-indexed in reality (or are indexed on a lag we do not model). In an all-real frame these are held at their nominal 2024 values, so over a multi-decade horizon they effectively *tighten* in real terms and bite harder each year — a conservative, realistic bias. This applies to: the **NIIT** $250k MFJ MAGI threshold, the **IRMAA** Medicare surcharge brackets, and the **Social Security taxation** provisional-income thresholds ($32k–$44k MFJ). Statutory items that *are* CPI-indexed in reality (federal ordinary/LTCG brackets, the standard deduction, contribution limits) are correctly held flat in real terms.

---

## 5. Accumulation phase

Each accumulation year proceeds in the order **returns → contributions** (the standard end-of-period convention). This slightly understates the effective contribution yield versus a beginning-of-period model but is both conventional and conservative.

### 5.1 Contribution waterfall

Contributions are directed by a prioritized waterfall tied to the user's gross comp and contribution caps:

1. **401(k)** employee deferral up to the 401(k) limit, plus employer match.
2. **HSA** family contribution (if HDHP-enrolled).
3. **Backdoor Roth IRA** up to the IRA limit.
4. **ESPP** up to the configured participation rate.
5. **Brokerage** (taxable) for any remaining savings capacity.

Partner accounts mirror this structure (partner 401(k), partner Roth IRA). Roth IRA contributions stop automatically after the year the household transitions to Married-Filing-Jointly if combined MAGI exceeds the phase-out ceiling — in that case the engine routes Roth contributions through the backdoor or to brokerage, depending on configuration.

### 5.2 Contribution limit inflation

IRS contribution limits are CPI-indexed in reality, so in the all-real frame they are **held flat at their 2024 values** (`CONTRIBUTION_LIMIT_INFLATION_RATE = 0.0`). See `TAX_MODEL.md` §11 for the 2024 base values.

---

## 6. Retirement phase

Each retirement year proceeds in this order:

1. **Compute gross annual expenses** — sum of housing, food, transport, healthcare (age-banded), child costs (each child in `CHILDREN` costs their own monthly amount from birth until their own leave-home age), college (paid first from that child's own 529), leisure, and discretionary.
2. **Apply dynamic spending adjustments** (Section 8) if enabled.
3. **Apply return-based spending adjustments** (Section 9) if enabled.
4. **Subtract Social Security** income for both spouses, if each has reached their claim age.
5. **Subtract RMD** income (Section 13) — RMDs must be withdrawn regardless of need.
6. **Compute net withdrawal** needed from the portfolio = expenses + taxes − SS − RMD surplus.
7. **Withdraw from accounts** in the tax-efficient order described in Section 7.
8. **Apply investment returns** to remaining balances at year end.

---

## 7. Withdrawal order

The engine uses a strict tax-efficient withdrawal hierarchy that differs before and after age 59½.

### 7.1 Before age 59½ (early retirement)

1. Cash reserves
2. Taxable brokerage (LTCG treatment, no penalty)
3. Roth IRA **contributions** (always penalty- and tax-free)
4. Traditional 401(k) / IRA (ordinary income + 10% early-withdrawal penalty)
5. HSA for non-medical use (ordinary income + 20% penalty)

### 7.2 Age 59½ and later

1. Cash reserves
2. Taxable brokerage (LTCG)
3. Traditional 401(k) / IRA (ordinary income)
4. Roth IRA (tax-free)
5. HSA for qualified medical expenses (tax-free)

**Rationale.** Drawing from taxable first realizes LTCG at preferential rates while letting Roth and HSA compound longest. Roth is saved for last because it has no RMD during the owner's life and produces the lowest future tax drag for heirs. HSA is preserved for its triple-tax-free status on medical spending.

---

## 8. Dynamic spending (Guyton-Klinger-style guardrails)

When `DYNAMIC_SPENDING_ENABLED = True`, the engine monitors portfolio value against an inflation-adjusted target glide path and adjusts discretionary spending:

- If portfolio value falls **below 70%** of the target for the current age → cut discretionary spending by **15%**.
- If portfolio value exceeds **130%** of target → optionally boost discretionary spending. The default boost is **0%** (conservative).

Discretionary spending is approximately **30%** of total expenses. The remaining **70%** (mortgage, utilities, healthcare, food) is treated as non-discretionary and is not cut by the guardrail. This matches Guyton's original rule-set which only adjusted the flexible portion of a withdrawal.

---

## 9. Return-based spending

When `RETURN_BASED_SPENDING_ENABLED = True`, the engine applies a short-horizon reaction to the most recent year's realized return:

| Realized return | Discretionary adjustment |
|-----------------|--------------------------|
| ≥ 0%            | Maintain (or boost, if enabled) |
| < 0%            | Cut discretionary by 10% |
| < −10%          | Cut discretionary by 20% |

This layer combines with the Guyton-Klinger guardrail and is applied multiplicatively; both can fire in the same year.

---

## 10. Asset allocation glide path

When `GLIDE_PATH_ENABLED = True`, the stock/bond mix shifts with age:

| Age    | Stocks | Bonds |
|--------|--------|-------|
| ≤ retirement age | 90% | 10% |
| 75+              | 60% | 40% |
| between          | linear interpolation |

Portfolio returns each year are computed as the weighted average of stock and bond draws at the age-appropriate weighting. This reduces sequence-of-returns risk late in life but costs expected return early on.

---

## 11. Healthcare model

Healthcare costs are age-banded (values below are in today's dollars) and, in the all-real frame, grow at the healthcare **real-excess** rate of **1.75%/yr** (4.5% nominal − 2.75% general):

| Age band         | Annual cost (today's $) | Notes                                     |
|------------------|-------------------------|-------------------------------------------|
| Pre-retirement   | $6,000                  | Employer-subsidized premiums + OOP        |
| Early retirement (50–64) | $24,000         | Legacy flat band; unused by default (see below) |
| Medicare base (65–74)    | $8,000          | Part B + Part D + supplement              |
| Medicare mid (75–84)     | $12,000         | Increased OOP, supplement drift           |
| Medicare late (85+)      | $18,000         | Home care, Part A coinsurance, drugs      |

**Pre-65 marketplace years** (`MODEL_ACA_AGE_RATED = True`, default) are priced per member rather than from the flat band: each pre-Medicare adult pays the benchmark Silver premium for their age (federal 3:1 age curve, `ACA_BENCHMARK_MONTHLY_AT_40` at 40), each child at home pays `ACA_CHILD_MONTHLY`, and the premium tax credit caps the household's cost at MAGI × the 2026 applicable percentage (2.10%–9.96%), with no credit at or above 400% of the household-size FPL. Each member also carries `ACA_OOP_PER_PERSON_ANNUAL` out-of-pocket, net of the living base's `SPEND_HEALTH_MONTHLY`. While a partner is still working after the primary retires, their employer plan covers the household and no marketplace cost is charged. In years when one spouse is on Medicare and the other is not, the Medicare all-in floor applies to the Medicare spouse's share before the other's marketplace cost is added.

**IRMAA surcharges** are added on top for years in which MAGI (from 2 years prior) exceeds the $206,000 MFJ threshold. See `TAX_MODEL.md` §7 for the IRMAA bracket table.

If `LTC_ENABLED = True`, an additional long-term-care shock is modeled in late-life years. See `config.py` for the LTC parameters.

---

## 12. Social Security

### 12.1 Full retirement age

For users born in 1960 or later, FRA is **67**.

### 12.2 Claim-age adjustments

- **Early claim (62 ≤ age < FRA):** benefit is reduced by 5/9 of 1% per month for the first 36 months before FRA, then 5/12 of 1% per month for any earlier months. Claiming at 62 yields a **30% reduction** (70% of PIA).
- **Delayed credits (FRA < age ≤ 70):** benefit grows by **8% per year** of delay (2/3 of 1% per month). Delaying from FRA=67 to 70 yields **124%** of PIA. No further credits accrue after 70.
- **Each person claims at their own age:** you at `SS_CLAIM_AGE`, your partner at `PARTNER_SS_CLAIM_AGE` (in their own age; the same age by default).
- **Spousal benefit (married couples, `MODEL_SPOUSAL_SS_BENEFIT`):** once both have claimed, a spouse whose own benefit is under half of the other's gets the difference, reduced by 25/36 of 1% per month before FRA for 36 months and 5/12 of 1% beyond (65% at 62), with no delayed credit. Unmarried partners don't qualify. Survivor benefits and benefits that depend on when you stop working are not modeled.

### 12.3 Taxation

Social Security benefits are entered in today's dollars and, because SS is COLA-indexed, are held **flat in real terms** across the horizon (no growth beyond general CPI).

Up to **85%** of Social Security benefits are includable in federal taxable income, based on the **provisional income** formula (see `TAX_MODEL.md` §5). The provisional-income thresholds ($32k–$44k MFJ) are **frozen-nominal** and are not indexed (see the frozen-nominal-threshold limitation in Section 4), so a larger real share of benefits becomes taxable over time. California does not tax Social Security.

`INCLUDE_SOCIAL_SECURITY` and `SS_CLAIM_AGE` toggle and parameterize this module.

---

## 13. Required Minimum Distributions

### 13.1 Start age (SECURE 2.0)

- Born 1951–1959: RMDs begin at **age 73**.
- Born 1960 or later: RMDs begin at **age 75**.

### 13.2 Calculation

Each year's RMD is

```
RMD = (prior year-end balance of Traditional accounts) / (Uniform Lifetime Table divisor for current age)
```

The full Uniform Lifetime Table is reproduced in `TAX_MODEL.md` §9.

### 13.3 Scope

RMDs apply to **Traditional 401(k)** and **Traditional IRA** balances. **Roth IRAs** have no RMD during the original owner's life. **HSAs** have no RMDs.

RMDs are treated as mandatory income for the year; if the desired spending is below the RMD, the excess is reinvested in the taxable brokerage (net of the tax bill).

---

## 14. Roth conversions

When `ENABLE_ROTH_CONVERSION = True`, the engine executes **bracket-filling** Roth conversions during low-income early retirement years:

- Convert Traditional → Roth each year up to the top of the **12% federal bracket** (**$94,300** taxable income MFJ in 2024). Federal brackets are CPI-indexed in reality, so in the all-real frame this ceiling is held flat at its 2024 real value.
- Hard cap of **$100,000** per year on any single conversion.
- Conversions **stop** in the year the household reaches `SS_CLAIM_AGE`, because SS plus RMDs typically push taxable income above the 12% bracket ceiling.

Conversion income is added to ordinary income for the year and taxed accordingly. The 5-year rule per conversion is not modeled — Roth earnings are assumed available after 59½ without separate tracking.

---

## 15. Failure condition

A simulation path is marked a **failure** when, in any year, the portfolio cannot cover **≥ 99%** of the required net withdrawal. The 1% tolerance absorbs rounding and avoids false failures from trivial shortfalls.

### 15.1 Home equity backstop

When `USE_HOME_EQUITY_BACKUP = True`, accessible home equity (default **85%** of current equity, accounting for selling costs and a residual housing need) is treated as a last-resort cash source before declaring failure. This is modeled as a one-time lump sum that flows into the taxable brokerage; it is not a HELOC or reverse mortgage simulation.

---

## 16. Known limitations

- **Normal-distribution returns** under-sample fat tails and skew relative to real markets. Crisis-level drawdowns are reached only via clamping rather than emerging organically from the distribution.
- **No tax-loss harvesting** is modeled; taxable gains are realized at their embedded-gain ratio on withdrawal.
- **One filing status for the whole plan** (`FILING_STATUS`) — no wedding, divorce, widow(er) or head-of-household transitions.
- **Geography:** federal + California state only by default. See `TAX_MODEL.md` §4 for how to substitute another state.
- **Not modeled:** inherited IRAs (no 10-year rule accounting), pension income, rental real estate, annuities, cash-value life insurance, business equity, deferred comp.
- **Medicare/Medicaid** are modeled as flat age-banded costs; no long-term-care Medicaid spend-down logic, no separate Part A/B/D bracket interaction beyond IRMAA.
- **State residency is assumed constant.** Changing residency mid-retirement (e.g. moving from CA to a no-tax state) is not modeled.
- **Sequence-of-returns risk** is captured by Monte Carlo but not separately reported. Users concerned about SORR should inspect the distribution of failures by retirement-year cohort.
- **Fixed-horizon / no-mortality model:** both spouses are assumed alive for every year through the plan's end. There is no stochastic mortality, no survivor Social Security benefit (the higher of the two benefits continuing alone after a spouse's death), no filing-status change at first death, and no widowhood expense reduction (single-person household costs are typically lower than a couple's). `PLAN_UNTIL_AGE` sets the simulation length only, not a mortality assumption.
