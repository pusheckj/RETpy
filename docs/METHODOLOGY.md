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

1. **Investment fees** are subtracted from the arithmetic mean before the draw.
2. **The scenario returns are arithmetic means**, and the engine draws arithmetic yearly returns around them. It does **not** subtract a drag term. Compounding the draws already produces the drag: the median compounded growth is about

```
geometric_return ≈ arithmetic_return − σ_p² / 2
σ_p² = w_s² σ_s² + w_b² σ_b² + 2 w_s w_b ρ σ_s σ_b
```

   For 100% stocks at 8.7% / 19% that is about 6.9% real; for 80/20 `historical` about 6.3%.
3. **Deterministic projections** (net-worth projection, Debt payoff, Freedom milestones / Coast FIRE) need one expected rate, so they use this geometric rate (`config.geometric_portfolio_return`, blended portfolio variance with correlation). Their single path then about matches the simulation's median (the formula runs 0.1–0.2 points low).

Earlier versions also subtracted σ_p²/2 from every draw, which counted the drag twice (100% stocks compounded at about 5.3% real in simulation). `APPLY_VOLATILITY_DRAG` is kept only so old profiles load; it has no effect.

### 3.4 Clamping

Annual portfolio returns are clamped to **[−35%, +50%]** for an 80/20 portfolio. These bounds bracket the worst 12-month real return in the historical S&P 500/Treasury record (≈ −38.5%, 1931) and the best (≈ +57.6%, 1933). Clamping prevents pathological tail draws from dominating the distribution while still allowing credible crisis-level drawdowns.

### 3.5 Scenarios

All values below are **real** (inflation-adjusted) returns.

| Scenario     | Stock real return (arithmetic) | Bond real return (arithmetic) | Stock σ | Bond σ | Correlation | 80/20 geometric |
|--------------|-------------------|------------------|---------|--------|-------------|-----------------|
| Conservative | 7.0%              | 2.0%             | 19%     | 8%     | −0.20       | 4.9%            |
| Historical   | 8.7%              | 3.1%             | 20%     | 8.7%   | −0.20       | 6.3%            |
| Pessimistic  | 5.0%              | 1.0%             | 22%     | 10%    | −0.20       | 2.7%            |
| Forward-looking | 5.1%           | 2.4%             | 15.5%   | 6%     | +0.10       | 3.8%            |

`ACTIVE_RETURN_SCENARIO` selects one of these at run time. Forward-looking (`'forward'`) is the base case of a November 2026 survey of investment firms' 10-15 year forecasts: an all-stock mix of 60% US and 40% international at 3.9% real geometric with 15.5% volatility, US aggregate bonds at 2.2% real with 6%, and a stock-bond correlation of +0.10. Forecasts are geometric rates, so each arithmetic mean here is the geometric rate plus volatility²/2. It is the only scenario with its own correlation (`stock_bond_correlation` in its `RETURN_SCENARIOS` entry); the others use `STOCK_BOND_CORRELATION`.


### 3.6 Historical replay ("If you had retired in a real year")

`run_detailed_simulation(retirement_age, historical_start_year=Y)` replays real market history instead of drawing returns. The first retirement year earns year `Y`'s returns, the next year `Y+1`'s, and so on to the plan's end. The working years before use the years just before `Y` (`historical_replay_years`). Each year the stock and bond sleeves earn that year's **real** stock and bond returns from `historical_returns.py` (1926-2024, already after inflation, so nothing is deflated), less `INVESTMENT_FEE_RATE`, at the plan's mix for that age (`calculate_asset_allocation`, so glide paths and bond tents apply). Real data is not clamped (§3.4). A year outside 1926-2024 earns the plan's expected median (geometric) real return for that mix, after fees, with no randomness (`geometric_portfolio_return`). No market draws are made, so a replay is deterministic; the non-market draws (healthcare and childcare inflation, long-term care) still use `random_seed`.

The Stress tests tab (`sim_runner.plan_historical_backtest`) replays the plan once per start year, with the same seed for every year so they differ only by their markets. It uses the start years whose whole plan (working years and retirement) fits inside the data. When fewer than 10 such years exist (a plan of more than about 90 years), the range starts at 1926 and the years outside the data use the expected return; the caption says how many start years that affects. The start years overlap heavily, so they are far fewer independent tests than their count suggests, and past sequences don't bound future ones.

The older `historical_sequence=` mode (`SEQUENCE_TESTS`, nominal stock returns 2000-2024 deflated by the expected inflation rate, bonds drawn around each stock return) is unchanged.
---

## 4. Inflation

The entire model operates in a consistent **all-real (today's-dollars) frame**: investment returns are drawn real (Section 3), so every liability must also live in real dollars for the comparison to be apples-to-apples. Consequently **general CPI never grows any liability** — anything that merely tracks general inflation (most living expenses, leisure, college/529, and Social Security, which is COLA-indexed) is held **flat in real terms**.

The only categories that *grow* are those that historically **outpace** general CPI. They grow at their **real-excess rate** = (category mean − general mean), i.e. the portion of their nominal inflation left over after deflating by general CPI:

| Category    | Nominal mean | Real-excess (mean − general) | Notes                                      |
|-------------|--------------|------------------------------|--------------------------------------------|
| General     | 2.75%        | **0.00%** (flat in real terms) | Most discretionary and non-housing spend; SS (COLA) |
| Healthcare  | 4.50%        | **1.75%**                    | Medicare premiums, OOP, LTC; ACA premiums when no area is set |
| Housing     | 2.75%        | **0.00%** (flat in real terms) | Property tax, utilities, maintenance      |
| Childcare   | 4.00%        | **1.25%**                    | Daycare, camps, activities                 |
| Pre-65 premiums, with an area set | 6.00% | **3.25%**              | Marketplace premiums before 65 only (Section 11) |

The real-excess is a **fixed premium over CPI** (`INFLATION_REAL_EXCESS`: healthcare 1.75%, childcare 1.25%). It does not move with the *Expected inflation* slider.

> **What the Expected inflation slider does.** In an all-real model it changes (a) the decay of the frozen-nominal tax thresholds below (more inflation, more tax drag), (b) the deflation of a historical-return stress path, and (c) the real cost of anything fixed in nominal dollars: fixed-rate mortgage and consumer-debt payments and balances, and the home-sale cost basis and exclusion (see *Nominal-fixed amounts* below). It does not rescale spending, savings or Social Security. Healthcare and childcare used to be nominal literals measured against the slider, so 10% inflation made them fall 5% a year in real terms and success on the sample plan rose from 0.49 (0%) to 0.97 (10%). With a fixed premium the same sweep is flat (0.83 / 0.83 / 0.84).

Each real-excess category follows an **independent random walk**: each year's draw is normal with the real-excess mean above and volatility ~1.5%. The general factor is pinned at **1.0** for the whole horizon.

**Nominal-fixed amounts.** Some amounts are fixed in dollars, not in buying power. The engine converts each with one index, `cpi_index(age) = (1 + EXPECTED_INFLATION)^(age − YOUR_AGE)` (1.0 today; the same yearly deflator as the debts, Section 6.3, and like them the expectation, not a path's own draw): an amount fixed in nominal dollars is worth `nominal / cpi_index(age)` today's dollars, and a today's-dollar amount paid at `age` is `real × cpi_index(age)` dollars of that year.

| Item | Frame | In today's dollars |
|------|-------|--------------------|
| Living costs, rent, leisure, college, Social Security | track prices | flat |
| Property tax + insurance (escrow, and the carrying cost after payoff) | track prices | flat |
| Home values, purchase prices, a move's price and loan as entered | today's dollars | flat |
| Mortgage principal + interest (fixed rate) | nominal, fixed when the loan starts | shrinks by 1 / (1 + π) a year |
| Mortgage balance | nominal, amortized at the loan's rate | nominal / `cpi_index` |
| Extra mortgage principal (`EXTRA_MORTGAGE_PAYMENT_ANNUAL`) | entered in today's dollars | flat; paid as × `cpi_index` against the nominal loan |
| Consumer-debt payments and balances (Section 6.3) | nominal | nominal / `cpi_index` |
| Home-sale cost basis (`HOME_COST_BASIS`, or a purchase price × `cpi_index` at purchase) and the $250k / $500k exclusion | nominal (not indexed in law) | nominal / `cpi_index` at the sale |
| NIIT, Additional Medicare Tax, Social Security taxation, child-tax-credit phase-out, the $2,500 student-loan cap, the senior deduction ($6,000 and its phase-out start) | nominal (frozen in law) | nominal / `cpi_index` |

**Mortgage payment.** `MORTGAGE_MONTHLY` (and a purchase's `monthly`) is all-in. Its escrow part is the home's value × its carrying rate (`HOME_CARRYING_COST_PCT`, or the purchase's `carrying_pct`), capped at the payment; the rest is principal and interest. In the plan year at `age` it costs

  escrow + (all-in − escrow) × cpi_index(loan start) / cpi_index(age)

today's dollars (`config.mortgage_real_annual`), so year *k* of a loan costs escrow + P&I / (1 + π)^*k*. The term and payoff age don't change. After payoff the home costs its escrow, flat. A purchase in a later year sets its loan in that year's dollars (price and loan × `cpi_index` at that age), so its first year costs exactly the today's-dollar payment you see. The housing chart, net-worth projection, mortgage paydown tab, House section and Freedom milestones read the same schedule. Extra principal is paid only inside its window, from `EXTRA_MORTGAGE_PAYMENT_START_AGE` up to `EXTRA_MORTGAGE_PAYMENT_STOP_AGE` (`config.extra_mortgage_payment_in_window`), in the engine and in the deterministic payoff projection (`account_simulation.mortgage_payoff_projection`) behind the House section's payoff line and the Mortgage paydown tab. With `EXPECTED_INFLATION = 0` every index is 1 and results are exactly what they were before this conversion.

> **Limitation — frozen-nominal statutory thresholds.** A handful of tax thresholds are specified in *nominal* dollars by statute and are **not** inflation-indexed in reality (or are indexed on a lag we do not model). These decay in real terms (`real_frozen_threshold`: nominal ÷ (1 + π)^years), so over a multi-decade horizon they effectively *tighten* and bite harder each year — a conservative, realistic bias. This applies to: the **NIIT** and **Additional Medicare Tax** thresholds ($250k MFJ / $200k others), the **Social Security taxation** provisional-income thresholds ($32k–$44k MFJ), the **child-tax-credit** phase-out start, the **$2,500** student-loan-interest cap and the 2025–2028 **senior deduction** ($6,000 per person 65+ and its $75k / $150k phase-out start). Statutory items that *are* CPI-indexed in reality (federal ordinary/LTCG brackets, the standard deduction and its 65+ add-on, contribution limits, the **IRMAA** tiers, the ACA percentages) are held flat in real terms at their **2026** values (sources: `docs/data_sources/2026_verification.md`).

---

## 5. Accumulation phase

Each accumulation year proceeds in the order **returns → contributions** (the standard end-of-period convention). This slightly understates the effective contribution yield versus a beginning-of-period model but is both conventional and conservative.

### 5.0 Take-home pay

Each working year's pay, pre-tax savings and taxes come from one deterministic function, `account_simulation.working_year_cashflow`, which the sidebar's Taxes panel and the tax/savings charts read too:

- **Pay**: your comp-table wages (base + bonus + RSU) plus `YOUR_OTHER_INCOME`; the partner's base + bonus + RSU (grown at their growth rate) plus `PARTNER_OTHER_INCOME`.
- **Pre-tax deferrals**: 401(k) and HSA, capped at the IRS limits and at the pay itself. **Roth catch-up (SECURE 2.0):** someone whose FICA wages the year before passed $150,000 (`ROTH_CATCHUP_WAGE_THRESHOLD`, the 2026 figure) makes the 401(k) catch-up (50+, and the 60-63 super catch-up) as Roth: it is paid from after-tax pay and goes to the Roth account (the engine has no separate Roth 401(k); the tax treatment is the same). The prior year's wages are the comp table's row for the year before. `MODEL_ROTH_CATCHUP_RULE = False` keeps it pre-tax.
- **Student loan interest deduction**: up to $2,500 of the interest paid on `DEBTS` of kind `student_loan` comes off your AGI (above the line), phased out over $85k-$100k MAGI (single / head of household) or $175k-$205k (joint). The interest is the payoff math's own (`debts.student_interest_by_year`). The cap is not indexed, so it shrinks in today's dollars; the ranges are. On an unmarried couple's two returns it goes on yours. Working years only.
- **Taxes** (`config.working_year_taxes`): 2026 federal brackets and standard deduction (with the 65+ add-on and the 2025–2028 senior deduction) for the filing status; the state's table (2024; California 2026, with its exemption credits and 1% tax above $1M); FICA per earner (Social Security to the 2026 wage base of $184,500, Medicare, Additional Medicare above $200k/$250k per return). A married couple files one joint return, an unmarried couple two (each taxed on their own pay), and a joint return's income tax is shared between the two in proportion to their taxable income.
- **Take-home** = pay − deferrals (a Roth catch-up included) − taxes. A comp row that sets `after_tax` overrides your computed take-home (advanced; the app never sets it).

The year's taxable pay is also the base that any same-year portfolio draw (a car, a house down payment) stacks on.

### 5.1 Contribution waterfall

Contributions are directed by a prioritized waterfall tied to the user's gross comp and contribution caps:

1. **401(k)** employee deferral up to the 401(k) limit, plus the employer match — dollar for dollar on what you defer, up to the match % of base pay.
2. **HSA** family contribution (if HDHP-enrolled).
3. **Backdoor Roth IRA** up to the IRA limit.
4. **ESPP** up to the configured participation rate.
5. **Brokerage** (taxable) for any remaining savings capacity.

Partner accounts mirror this structure (partner 401(k) with its own match, partner Roth IRA). The partner's Roth IRA is limited by the IRA limit and earned income only (no income phase-out: above the direct range it is a backdoor Roth, like yours). The HSA uses the family limit when there is a partner or any child, else the self-only limit. A partner who keeps working after you retire is taxed the same way, and their pay is the first income on the year's return, so your withdrawals and conversions stack on top of it.

### 5.2 Contribution limit inflation

IRS contribution limits are CPI-indexed in reality, so in the all-real frame they are **held flat at their 2026 values** (`CONTRIBUTION_LIMIT_INFLATION_RATE = 0.0`). See `TAX_MODEL.md` §11 for the 2026 base values.

---

## 6. Retirement phase

Each retirement year proceeds in this order:

1. **Compute gross annual expenses** — sum of housing, food, transport, healthcare (age-banded), child costs (each child in `CHILDREN` costs their own monthly amount from birth until their own leave-home age), college (paid first from that child's own 529), leisure, and discretionary (see 6.1 and 6.2 for housing and the retirement lifestyle phases).
2. **Apply dynamic spending adjustments** (Section 8) if enabled.
3. **Apply return-based spending adjustments** (Section 9) if enabled.
4. **Subtract Social Security** income for both spouses, if each has reached their claim age. Benefits start at the claim age even while still working (the working-year cash flow adds them, with the taxable part taxed as ordinary income). The earnings test applies to anyone who claims before full retirement age and still earns wages (Section 12.4).
5. **Subtract RMD** income (Section 13) — RMDs must be withdrawn regardless of need.
6. **Compute net withdrawal** needed from the portfolio = expenses + taxes − SS − RMD surplus.
7. **Withdraw from accounts** in the tax-efficient order described in Section 7.
8. **Apply investment returns** to remaining balances at year end.

### 6.1 Housing timeline

Housing starts from today's home: an owner pays the all-in mortgage payment
until the loan is gone, then property tax + insurance (`HOME_CARRYING_COST_PCT`
of the home's value); a renter pays `SPEND_RENT_MONTHLY`. `HOME_EVENTS` adds
dated moves (the old single house move becomes one of them), applied at the start
of their year in both phases, before that year's expenses:

- **Sell** (any move while owning): proceeds = value − loan left (the tracked,
  amortized nominal balance, deflated) − selling costs − tax, into cash. The
  gain over the cost basis above $250,000 per owner ($500,000 married filing
  jointly; unmarried partners are taken as co-owners) is a long-term gain
  stacked on the year's income (federal LTCG, state, NIIT). The basis and the
  exclusion are nominal (Section 4).
- **Buy**: the down payment (price − loan) and costs come out of savings; the new
  loan, set in dollars of the purchase year, is amortized at its own rate, its
  all-in payment replaces the old housing cost (its principal and interest
  shrinking in today's dollars from then on, Section 4), and the
  accessible-equity reserve restarts at the down payment. Rent stops.
- **Sell and rent**: costs come out of savings; there is no home, loan or equity
  afterwards, and the new rent is paid every year from then on.

Home values are held flat in today's dollars, so a home bought in the plan sells
for what it cost in today's dollars (no real gain). Tax is on the nominal gain,
though: with inflation the price has risen in dollars since the purchase, and
the part of that gain above the (unindexed) exclusion is taxed. The ownership test for the exclusion (two of
the last five years) is assumed met. A sale in a retirement year is taxed
before that year's other income is counted, as the down payment always was.

### 6.2 Retirement lifestyle

Spending is higher in the first years of retirement and lower later:

- **Go-go years:** +$10,000 a year for two adults (two-thirds of that for one
  person, since shared costs like lodging don't halve) from retirement until 70,
  or for 5 years when retiring after 65.
- **Later years:** living spending 15% lower from 75, or from 10 years after
  retiring when that is later (`config.late_retirement_factor`). Housing,
  college, the vacation add-on and debt payments are not reduced.

The Spending chart draws the same rules year by year (retirement spending
mode, lifecycle preset, travel extra, later-years cut, children's costs and
long-term care growing with the childcare and healthcare factors, the college
bill), so before the guardrails its bars equal the engine's spending at every
age. What still differs: the guardrails are path-dependent, so after a run the
chart adds a line for the median the simulation really spent; long-term care is
drawn as its expected value (chance × cost); in working years the chart shows
the whole college bill, while the engine's logged working-year spending nets out
the part the 529 pays.

All of these are inputs (Retirement). The lifecycle presets use the same
phases: the travel boom's +50% discretionary covers the go-go years, its −20%
and the conservative preset's −30% start with the later years, and empty-nest
spending (−25%) starts once the last child has left home.

### 6.3 Debts

Consumer debts (`DEBTS`: credit cards, student, car, personal and medical loans; not the mortgage) are paid month by month with one fixed total payment: every minimum plus `DEBT_EXTRA_MONTHLY`. Each month interest accrues on each balance at `APR / 12`, each debt gets its minimum, and the rest goes to one target debt: the highest APR first (*avalanche*) or the smallest balance first (*snowball*, `DEBT_STRATEGY`). A paid-off debt's minimum rolls into the next target, so the total payment stays the same until the last debt is gone; then it stops and the money is saved again. A debt whose minimum doesn't cover its monthly interest is flagged; a plan that isn't paid off in 50 years is reported as such.

**Today's dollars.** Balances, minimums and APRs are nominal, as on a statement, and the payments are fixed in nominal dollars. The engine works in today's dollars by whole years and values each plan year's flows at the start of that year, so the payments made in plan year *y* (months 12*y*+1 to 12*y*+12) count as

  real payments(*y*) = nominal payments(*y*) / (1 + π)^*y*,

with π the expected general inflation (`EXPECTED_INFLATION`). This is the same as charging a real rate of about (1 + APR) / (1 + π) − 1 on a real balance while the real payment falls by 1 / (1 + π) a year. Payoff dates don't depend on the frame. Year-one payments are not deflated, so the first year matches the statements. The deflator is the expected inflation rather than each path's own inflation draw (general inflation is pinned at its expectation in this engine, Section 4).

**Where the money comes from.** The payments are spending. In working years they are added to that year's living expenses, so they come out of the brokerage sweep (the extra payment is money that would otherwise be saved); in the *Manual amounts* savings mode, as with all spending, they only matter when spending passes take-home. In retirement they are added after the spending guardrails (a loan payment can't be trimmed in a bad year) and withdrawn like other spending. The schedule doesn't depend on the retirement age. With no debts nothing changes.

**One calculation.** `retirement_sim/debts.py` holds the payoff math. The engine, the planner's Debts section and Debt payoff tile, and the Money check-up all use it, so they show the same months and interest. Student-loan interest paid in working years is deductible (Section 5.0). Not modeled: variable rates, promotional rates and fees, income-driven repayment and forgiveness, and new borrowing. Debts are not subtracted from net worth.

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
| ≤ retirement age | 80% (`STOCK_ALLOCATION`, which is also `GLIDE_PATH_START_STOCK_PCT`) | 20% |
| 75+              | 60% | 40% |
| between          | linear interpolation |

Portfolio returns each year are computed as the weighted average of stock and bond draws at the age-appropriate weighting. This reduces sequence-of-returns risk late in life but costs expected return early on.

`GLIDE_PATH_SHAPE` picks the shape. The table above is `"down"` (ease into bonds, the default). `"tent"` is a bond tent, also called a rising equity glide path:

| Age | Stocks |
|-----|--------|
| until `GLIDE_PATH_TENT_RAMP_YEARS` (5) before retirement | `STOCK_ALLOCATION` |
| ramp years | straight line down to `GLIDE_PATH_START_STOCK_PCT` at retirement |
| first `GLIDE_PATH_TENT_RISE_YEARS` (10) of retirement | straight line up to `GLIDE_PATH_END_STOCK_PCT` |
| after that | `GLIDE_PATH_END_STOCK_PCT` |

Bonds are highest in the years around retirement, when a crash does the most damage (sequence-of-returns risk). Stocks are higher later, when the money left mostly grows the estate (Kitces & Pfau, 2014). The working-years and retirement draws use the same mix function (`config.calculate_asset_allocation`), so the allocation chart shows the ramp too. The FI-number sweep (`run_detailed_simulation_networth`) has no fixed retirement age, so it holds `STOCK_ALLOCATION` while working.

---

## 11. Healthcare model

Healthcare costs are age-banded (values below are in today's dollars) and, in the all-real frame, grow at the healthcare **real-excess** rate of **1.75%/yr** (4.5% nominal − 2.75% general):

| Age band         | Annual cost (today's $) | Notes                                     |
|------------------|-------------------------|-------------------------------------------|
| Pre-retirement   | $6,000                  | Employer-subsidized premiums + OOP        |
| Early retirement (to 64) | $24,000         | Legacy flat band; unused by default (see below) |
| Medicare base (65–74)    | $8,000          | Part B + Part D + supplement + OOP (now below 2026 premiums alone; see below) |
| Medicare mid (75–84)     | $12,000         | Increased OOP, supplement drift           |
| Medicare late (85+)      | $18,000         | Home care, Part A coinsurance, drugs      |

The bands are for a couple. Each covered adult is charged half a band for their
own age, so a single person pays one share and an age-gapped couple pays one
share of each person's band. Covered adults are you and a partner whenever there
is one (`PARTNER_AGE > 0`), married or not.

**Pre-65 marketplace years** (`MODEL_ACA_AGE_RATED = True`, default) are priced per member rather than from the flat band: each pre-Medicare adult pays the benchmark Silver premium for their age (federal 3:1 age curve, `ACA_BENCHMARK_MONTHLY_AT_40` at 40, an input because prices vary widely by region), each child at home pays `ACA_CHILD_MONTHLY`, and the premium tax credit caps the household's cost at MAGI × the 2026 applicable percentage (2.10%–9.96%), with no credit at or above 400% of the household-size FPL. Each member also carries `ACA_OOP_PER_PERSON_ANNUAL` out-of-pocket, net of the living base's `SPEND_HEALTH_MONTHLY`. While a partner is still working after the primary retires, their employer plan covers the household and no marketplace cost is charged. In years when one spouse is on Medicare and the other is not, the Medicare all-in floor applies to the Medicare spouse's share before the other's marketplace cost is added.

**Healthcare by area** (new). With a ZIP code or state set under Assumptions, the marketplace years are priced for that area and the **2027 plan year**, as one bundle: 2027 premiums by rating area, the Rev. Proc. 2026-26 credit table (2.15% of income below 133% of the poverty line, rising to 10.22% at 300%, flat to 400%, no credit above) and the 2026 HHS poverty guidelines ($15,960 plus $5,680 for each other person; Alaska and Hawaii have their own). With no area set, the model above is unchanged: the two price inputs, the 3:1 curve, the 2026 table and 2025 guidelines, and premiums growing with healthcare at 1.75% a year. Details:

- **Prices** come from `retirement_sim/healthcare_data.py` (sources and limits: `DATA_SOURCES.md`). The side panel's area key (`HEALTH_AREA`, for example `AL:3`; the ZIP code is never stored) becomes plain config values in `config_builder.health_area_overrides`: a silver price for each age 0-64 (`ACA_AREA_SILVER_MONTHLY`), New York and Vermont family tiers (`ACA_AREA_TIERS`), the plan bought as a ratio of Silver (`ACA_AREA_PLAN_RATIO`, 1.0 or the Bronze-to-Silver ratio), out-of-pocket by age (`ACA_AREA_OOP_ANNUAL`, Bronze x1.30), the credit table, the poverty line and the growth rate. The engine, and the browser's copy of it, read only those values. One function (`aca_marketplace_premium`) prices the household for the engine and for the Freedom milestones quote.
- **Household:** adults at their own age's price; the three oldest children under 21 at child prices, others 21 and over at adult prices; New York and Vermont as a tier of one community rate. Plan: Benchmark Silver, or lowest-cost Bronze.
- **Credit:** `max(0, benchmark Silver − income × applicable %)`, capped at the plan's price, with income = the simulation's own income each year (so Roth conversions and gains cost credit). A Bronze buyer pays Bronze less the Silver-based credit. At or above 400% of the poverty line there is no credit.
- **Growth, 6.0% a year nominal, before 65 only.** The owner's validated assumptions file (`healthcare_inflators_pct.pre65_premiums`: 6.0 base, 4.5 optimistic, 8.0 pessimistic) sets pre-65 premiums at 6.0%, and Part B and Medigap at 6.0% too, but 5.0% for Part D and out-of-pocket at 65+. This build changes only the pre-65 premium. In the all-real frame that is 6.0% − 2.75% = **3.25% a year** above inflation, against healthcare's 1.75%. The engine takes the healthcare factor (noise included) and multiplies it by `((1 + 3.25%) / (1 + 1.75%))^years` (`aca_premium_extra`), so no extra random draws are made. It does not touch Medicare/IRMAA premiums, long-term care or the out-of-pocket table (they keep 4.5% nominal, 1.75% real) because the file's 65+ rows are a separate change. The credit's income share does not grow with prices, as in the law: prices rise, income does not, so the credit grows and a household below the cliff pays about the same share of income.
- **Cliff note.** Each marketplace year the engine records whether income was at or above 400% of the poverty line and the credit that costs: the benchmark Silver price less 400% of the poverty line times the top applicable percentage. The results screen (under the spending chart) names the first year at least half the runs are over, with the median credit lost that year. It also works with no area (2026 rules).
- **Not built:** state credits, Medicaid and CHIP, cost-sharing reductions, maximum-out-of-pocket stress years, a second "buffer" number.

**Medicare premiums** are priced per enrollee (`calculate_medicare_irmaa`): the 2026 Part B premium of the income tier ($202.90 at the standard tier), the tier's Part D surcharge, and an estimated $200 a month for a Part D plan and a Medigap policy (`MEDICARE_SUPPLEMENTAL_MONTHLY_PER_PERSON`). That is $4,835 a person a year at the standard tier, so at 65–74 premiums now exceed the $4,000 per-person share of the 'medicare_base' band and set the cost; from 75 the bands still set it. **IRMAA** tiers start above $218,000 joint / $109,000 individual (2026 CMS tiers; `MEDICARE_IRMAA_BRACKETS_MFJ`). In law the tier uses MAGI from two years earlier; the engine uses the current year's MAGI. See `TAX_MODEL.md` §7 for the tables.

If `LTC_ENABLED = True`, an additional long-term-care shock is modeled in late-life years. See `config.py` for the LTC parameters.

---

## 12. Social Security

### 12.1 Full retirement age

For users born in 1960 or later, FRA is **67**. The engine uses 67 for everyone (`ss_claim_factor` has no birth-year table), which is exact for anyone aged 66 or younger today. A person born earlier has an FRA of 66 to 66 years 10 months, so their early-claim and delayed-credit factors are a little off; enter the benefit at 67 or the amount they are already paid. Survivor benefits are not modeled (see Section 16); a widow or widower should plan as "Just me" and enter the benefit they receive now.

### 12.2 Claim-age adjustments

- **Early claim (62 ≤ age < FRA):** benefit is reduced by 5/9 of 1% per month for the first 36 months before FRA, then 5/12 of 1% per month for any earlier months. Claiming at 62 yields a **30% reduction** (70% of PIA).
- **Delayed credits (FRA < age ≤ 70):** benefit grows by **8% per year** of delay (2/3 of 1% per month). Delaying from FRA=67 to 70 yields **124%** of PIA. No further credits accrue after 70.
- **Each person claims at their own age:** you at `SS_CLAIM_AGE`, your partner at `PARTNER_SS_CLAIM_AGE` (in their own age; the same age by default).
- **Spousal benefit (married couples, `MODEL_SPOUSAL_SS_BENEFIT`):** once both have claimed, a spouse whose own benefit is under half of the other's gets the difference, reduced by 25/36 of 1% per month before FRA for 36 months and 5/12 of 1% beyond (65% at 62), with no delayed credit. Unmarried partners don't qualify. Survivor benefits and benefits that depend on when you stop working are not modeled.
- **Trust fund shortfall (`SS_PAYABLE_FRACTION`, `SS_PAYABLE_FROM_YEAR`):** from 2033 every benefit is scaled by the payable share (default 100%). The Social Security Trustees project that payroll taxes alone would pay about 77-81% of scheduled benefits after the trust fund runs short; about 78% models no fix.

### 12.3 Taxation

Social Security benefits are entered in today's dollars and, because SS is COLA-indexed, are held **flat in real terms** across the horizon (no growth beyond general CPI).

Up to **85%** of Social Security benefits are includable in federal taxable income, based on the **provisional income** formula (see `TAX_MODEL.md` §5). The provisional-income thresholds ($32k–$44k joint, $25k–$34k single/head of household) are **frozen-nominal** and are not indexed (see the frozen-nominal-threshold limitation in Section 4), so a larger real share of benefits becomes taxable over time. Each state's own rule decides state taxation: most exempt benefits, Montana and Utah tax them, a few exempt them below an income limit. An unmarried couple's benefits are split by each person's benefit amount and taxed on their own returns.

`INCLUDE_SOCIAL_SECURITY` and `SS_CLAIM_AGE` toggle and parameterize this module.

### 12.4 Earnings test

A claimant under full retirement age who still earns wages has benefits withheld (`config.ss_earnings_test_withholding`, `account_simulation.social_security_for_year`):

- **Before the year of full retirement age:** $1 for every $2 of wages above **$24,480** (`SS_EARNINGS_TEST_LIMIT`).
- **In that year** (the year at age 66): $1 for every $3 above **$65,160** (`SS_EARNINGS_TEST_LIMIT_FRA_YEAR`). Approximation: the whole year counts, not only the months before the birthday.
- **From full retirement age** nothing is withheld, and the benefit is recomputed as if it had started later by the months withheld: it is scaled by `ss_claim_factor(claim age + months withheld / 12) / ss_claim_factor(claim age)`, never past the full benefit. Months are fractional (withheld dollars ÷ the monthly benefit), where SSA counts whole months.

The limits are SSA's 2026 figures; they rise with average wages, so they are flat in today's dollars. Each person is tested on their own wages (comp-table wages for you, salary + bonus + RSU for your partner; other income doesn't count) against their own benefit plus any spousal top-up they receive. In reality a worker's excess earnings also withhold a spouse's benefit on their record; that is not modeled. The working-year cash flow, the retirement years (a partner still working) and the income chart all use this one function. `SS_EARNINGS_TEST_ENABLED = False` pays the full benefit while working.

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

- Convert Traditional → Roth each year until ordinary income reaches the top of the **12% federal bracket** for the filing status (**$100,800** joint, **$50,400** single, **$67,450** head of household in 2026; compared with income before the standard deduction, so the fill is conservative). Federal brackets are CPI-indexed in reality, so in the all-real frame this ceiling is held flat at its 2026 real value. An unmarried couple fills each person's own return from their own traditional balance.
- Hard cap of **$100,000** per year on any single conversion.
- Conversions **stop** in the year the household reaches `SS_CLAIM_AGE`, because SS plus RMDs typically push taxable income above the 12% bracket ceiling.

Conversion income is added to ordinary income for the year and taxed accordingly. The 5-year rule per conversion is not modeled — Roth earnings are assumed available after 59½ without separate tracking.

**Roth conversion optimizer (Deep dives -> Roth conversions).** `sim_runner.plan_roth_sweep` runs the plan at the target age with no conversions and with nine settings: fill the 12%, 22% or 24% bracket, with a yearly cap of $50K, $100K or $200K, plus your own setting if it is not one of them. Because the engine compares the fill target with income **before** the standard deduction, "fill the X% bracket" is the bracket's top plus the standard deduction for the filing status of your return (2026 joint: $133,000 / $243,600 / $435,750; `ui/utils/roth_brackets.py`, from `FEDERAL_BRACKETS_BY_STATUS` and `STANDARD_DEDUCTION_BY_STATUS`). The 65+ extra deduction is left out, so after 65 the fill stops a little short. Each setting runs the same count as the safe-withdrawal sweep (the app's simulation count, between 300 and 3,000) on the same seeds as the main run, so your own setting's success equals the plan's. The best setting has the highest success (ties: the larger median ending balance). Because every setting sees the same market paths, a setting is compared with the best path by path: it is marked "within noise" when its gap is at most 2 paired standard errors (the standard deviation of the per-path differences over the square root of the path count). Taxes are the median of `total_taxes_paid` per path: income tax and penalties paid from the accounts in retirement, in today's dollars.

---

## 15. Failure condition

A simulation path is marked a **failure** when, in any year, the portfolio cannot cover **≥ 99%** of the required net withdrawal. The 1% tolerance absorbs rounding and avoids false failures from trivial shortfalls. A shortfall of less than $1 never fails either: that is where the tax gross-up stops, so a need under $100 (say $52) is judged by the same $1 slack instead of 1% of itself. The same rule applies to working-year deficits.

### 15.1 Home equity backstop

When `USE_HOME_AS_BACKUP = True`, accessible home equity (`HOME_EQUITY_ACCESSIBLE_PCT`, default **85%** of current equity, accounting for selling costs and a residual housing need) is treated as a last-resort cash source before declaring failure. This is modeled as a one-time lump sum that flows into the taxable brokerage; it is not a HELOC or reverse mortgage simulation.

---

## 15.2 Freedom milestones (UI)

The planner's **Freedom milestones** section (`ui/utils/milestones.py`, `ui/utils/places.py`, data in `ui/utils/place_costs.py`) is a quick-rule layer on top of the engine, in today's dollars:

- **Timeline:** the median invested balance by age from the last run (or, before a run, the deterministic projection the net-worth chart uses). Net worth adds projected home equity.
- **Where you live now:** an area you pick (any state, DC, or one of about 20 big metros), by default the plan's `STATE_CHOICE`. Everyday costs elsewhere are priced against it.
- **Spending in a place** at the retirement age, built line by line (`milestones.place_cost`):
  - each everyday category (`SPEND_UTILITIES/FOOD/TRANSPORT/HEALTH/DISCRETIONARY/OTHER_MONTHLY`, `PARTNER_OTHER_MONTHLY`) = the plan's retirement amount × place index ÷ home-area index × the place's adjustment (default 1.00). The plan's retirement-spending mode (same / % of today / absolute) scales the categories as a group, as `retirement_living_base` does. A category's index mixes four price levels per area: goods, services other than housing, utilities and health insurance (food 70/30 goods/services, transport 80/20, fun and partner 50/50, other = services, utilities = utilities, healthcare premiums = health);
  - **housing there:** "Where you live now" keeps the plan's housing at that age (its own planned moves included). Any other place sells the home you own at the move age: value − remaining loan − selling costs (`HOME_SELLING_COST_PCT`) − a rough 20% tax on any gain above the exclusion (the engine taxes it exactly). Then it either **buys** a typical home there (the place's price; the proceeds pay for it and a 30-year loan at the plan's new-loan rate covers any shortfall; housing = the loan payment + price × the place's property-tax-and-insurance rate) or **rents** there (rent × 12). Moving costs are `HOUSE_MOVING_COSTS`. Defaults: buy in the US, rent abroad; each place can switch, or keep your home;
  - **children's costs** (childcare, college) and the lifecycle preset's food/fun change stay as planned: there is no clean per-place figure for them;
  - **health:** priced with the engine's formula at the retirement age (`config.pre_medicare_health_quote`, `milestones.health_cost`): before Medicare the age-rated marketplace premium for the covered adults and children at home, less the subsidy, plus out-of-pocket, with the place's health index ÷ the home area's scaling the prices (not the subsidy cap), grown by the expected healthcare factor since today. The subsidy needs an income: the quick rule uses half the year's spending there (the engine's own first-pass estimate) plus that year's Roth conversion and a still-working partner's pay; the simulation uses the income its withdrawals and conversions really create. If a working partner's employer plan covers the household at that age, health is priced from the partner's first retired year. Medicare years use the engine's IRMAA and floor, not scaled by place.
- **FIRE in a place at age a:** invested(a) + net sale proceeds(a) − home purchase cash(a) − moving costs ≥ spending there ÷ withdrawal rate (default 4%).
- **Coast FIRE:** invested(a) × (1 + r)^(retirement age − a) ≥ the FIRE number − the cash the move frees at retirement, with r the expected real return of the return scenario (as in the net-worth projection chart).
- **Confirm with simulation** gives the engine the same assumptions: `RETIREMENT_SPENDING_MODE = "Absolute amount ($/yr)"` with `RETIREMENT_SPENDING_ABSOLUTE` = the place's everyday spending; `ACA_BENCHMARK_MONTHLY_AT_40`, `ACA_CHILD_MONTHLY` and `HEALTHCARE_COSTS_BY_AGE['early_retirement']` × the health ratio; `RETIREMENT_STATE_CHOICE` for the place's state tax; and, for every retirement age the scan tries, a `HOME_EVENTS` patch that moves you at that age (`sell_buy` with the place's price, `loan` = the shortfall, `years` = 30 (0 when paid in cash), `carrying_pct` = the place's rate; or `sell_rent` with its rent). The plan's own home moves before that age stay; moves at or after it are replaced, and the legacy single house move is folded into the list. A purchase's `carrying_pct` is a new optional `HOME_EVENTS` field: the engine uses it for that home's escrow and for its property tax and insurance after payoff; without it nothing changes. `RETIREMENT_STATE_CHOICE` (default `None`, meaning `STATE_CHOICE`) applies only to retirement-phase tax (withdrawals, conversions, RMDs); working years keep `STATE_CHOICE`. The check reuses the main analysis's seeds and run counts, so "Where you live now" reproduces the plan's own earliest age.
- **Data:** sourced, November 2026 (full row-by-row sources in `docs/data_sources/2026_verification.md`; data in `ui/utils/place_costs.py`). Price levels: BEA Regional Price Parities 2024 for states and metros (goods, services other than housing, utilities), renormalized so the US is exactly 1.00. Health: KFF 2026 benchmark marketplace premiums as a ratio to the US benchmark; metros use their state's ratio. Home prices: Zillow ZHVI (September 2026 for states, October 2026 for the US and metros). Rents: Zillow single-family ZORI, October 2026, for the US and metros; a state's rent is modeled as the mean of its metros' ZORI × 1.172. Carry: the property tax a new buyer pays plus Insurance.com 2026 insurance on a $300,000 dwelling (flood excluded). Abroad: Numbeo estimates from November 2026 (not BEA-comparable) at ECB reference rates of 13 November 2026. Caveats: the San Francisco Bay Area row is a computed blend of two BEA metros; state rents are modeled and understate big-city states (CA, NY, WA); abroad health ratios use about age-40 premiums and so understate the cost at 60 and over; Lisbon's price is the municipality; Mérida's price is a house; Vermont, West Virginia, Wyoming and Alaska have high health ratios (1.6-2.1), and Vermont's premiums do not vary with age.
- **Carrying cost and insurance.** A place's carry rate (property tax + insurance, a share of the price a year) is what the plan's `HOME_CARRYING_COST_PCT` is (default 1.35%, an existing owner's), so it is used the same way and never added on top of it: a purchase replaces the plan's housing at that age (the old home's payment, tax and insurance are dropped), the new home pays its own rate, and renters pay none. The place rates run higher than the default because a new buyer's assessment resets (California about 1.15% tax, not the 0.70% average-owner rate) and 2026 insurance is dear in some states (Florida 4.2% in all). One small overlap remains: home insurance you pay outside a mortgage and enter under Other stays in Other (scaled by services prices), while the new home's carry also includes insurance. Enter home insurance with your housing cost to avoid it. Confirm passes the rate as the purchase's `carrying_pct`.
- **Places abroad** use "no state income tax" as a placeholder. US federal tax still applies; foreign tax, treaties, visas and currency are not modeled. Health insurance abroad is a local private plan (about age 40) applied as a ratio to the pre-Medicare marketplace price; Medicare years stay as planned.

## 15.3 Assumption presets (UI)

The planner's **Assumptions** section starts with two buttons, **All conservative assumptions** and **All typical assumptions**. A click sets 26 assumptions at once (`ui/utils/assumption_presets.py`, `compute_preset`), so a user does not need to know what a good number is. The rules read only facts about the household and never the assumption values already set, so the same situation always gets the same preset. A "What changed" box lists each old and new value, and **Undo** puts the old values back until one of them is edited.

Facts read: your age A, your partner's age P (0 for a single), the target retirement age R, the Social Security claim age, and whether there is a loan (a mortgage balance or payment, or any `DEBTS`). Derived timeline: plan end E in your age (the later of your plan-until age and your partner's, as `config.plan_end_age`), years to retirement Y = max(0, R - A), years left in the plan YL = E - A, and retirement horizon H = E - max(R, A). H ignores a separate `PARTNER_RETIREMENT_AGE`: it counts years from your own retirement age, which is close enough for choosing a glide shape and a success target.

| Setting | Conservative | Typical | Reason |
| --- | --- | --- | --- |
| Plan-until age (each person, by own age) | 100 | Single: under 50 is 100, 50-84 is 95, 85+ is 100. Couple: under 50 is 100, 50-59 is 96, 60+ is 95 | Longevity research. Never below age + 1 or above the slider's 100 |
| Return scenario | Forward-looking if YL > 35, else Pessimistic | Conservative set if YL > 35, else Forward-looking | A blend of forecasts for 10 years, then half the gap to history, averages about the Conservative set over 60 years and nearer Forward-looking over 30. The crossover is about 35 years. Historical is never used. Pessimistic is 5% stocks and 1% bonds with 22% swings, so stocks compound at about 2.5% a year |
| Stock % while working | Average of a standard glide schedule (anchors by years to retirement: 25+ is 90, 20 is 85, 15 is 74, 10 is 62, 5 is 56, 0 is 50) over years 1 to Y, rounded to 5, never below the share at retirement | Same | The engine holds one mix while you work, so the average is the single honest number |
| Glide path | Always a bond tent. H up to 30: 40% to 60% over 10 years. H 31-40: 40% to 60% over 15. H over 40: 50% to 70% over 15 | H up to 30: ease into bonds, 50% at retirement to 40% at 75. H 31-40: tent 50% to 60%, 10 years. H over 40: tent 60% to 70%, 10 years | Every standard glide path de-risks near retirement. Rising equity protects against a crash at the start |
| Investment fee | 30 bps | 10 bps | Typical index fund. The target-date average is 27 bps, rounded up to the slider step |
| Expected inflation | 3.0%, or 2.5% with a loan | 2.5% | Higher inflation shrinks fixed loan payments, so with a loan a higher rate could flatter the plan |
| Social Security paid from 2033 | min(75%, the Trustees path at the middle of your benefit years). The path is 78% falling 14.5 points by 2100 | 78% | About 78% stays payable with no fix |
| Success target | 90% if H up to 35, else 95% | 85% if H up to 35, else 90% | Longer retirements have more room for bad luck |
| Spending guardrails | On | On | People cut spending after a big drop |
| Cut spending after down years | Off | On | A cautious plan does not count on a cut every year |
| Spend less later | 0% from 75 | 15% from 75 | Real spending falls with age in the research. Conservative assumes flat |
| Pre-Medicare marketplace costs | On | On | Off removes the premiums entirely, which flatters the plan. Prices are never touched |
| Long-term care | On, from 83, $130,000 a year | On, from 83, $115,000 a year | Nursing home, private and semi-private room |
| Chance of care each year | 2.6 expected care-years x people / years of exposure, rounded to 5% (5-100%) | 1.3 x people / years | Two people double it because the engine draws once per household year |
| Salary growth (real, by own age) | Under 45: 0.5%. 45+: 0% | Under 35: 1.5%. 35-44: 1.0%. 45-54: 0.5%. 55+: 0% | Pay flattens after the mid-40s. Your rate is skipped when you edited your pay table by hand (the table keeps its own growth). A partner has no table, so the partner's rate is always set. A loaded profile counts as edited only when its table differs from the one built from its base, bonus, RSU and raise |
| Roth ladder 5-year rule | On if R is under 60 | Same | Stricter and more realistic. No effect from 59.5. It matters only with Roth conversions on. With them off, the early-access section shows its warning |
| Rule of 55 | Off | On if 55 <= R < 60 | Works only if you leave that employer at 55 or later |

Not set by a preset, because they are personal facts or strategies: balances, pay, spending, children, mortgage, Social Security claim ages and amounts, state and tax rates, Roth conversion settings, marketplace prices, the lifecycle pattern, the go-go extra, 72(t) and Coast FIRE. The Social Security on/off switch and the number of simulations are not assumptions either. The preset values are plain config values, so no engine change was needed.

---

## 16. Known limitations

- **Normal-distribution returns** under-sample fat tails and skew relative to real markets. Crisis-level drawdowns are reached only via clamping rather than emerging organically from the distribution.
- **No tax-loss harvesting** is modeled; taxable gains are realized at their embedded-gain ratio on withdrawal.
- **One filing status for the whole plan** (MFJ, Single or head of household; two returns for an unmarried couple). No divorce, widow(er) status or head-of-household transitions.
- **Geography:** federal + any state or DC (2024 tables, California 2026; `state_tax_data.py`). City/county income taxes, state credits (other than California's exemption credits) and itemized deductions are not modeled; some states' figures are labelled approximate. Federal tax credits other than the child tax credit (working years only; see `TAX_MODEL.md`) are not modeled.
- **Not modeled:** inherited IRAs (no 10-year rule accounting), pension income, rental real estate, a second home held at the same time as the main one, annuities, cash-value life insurance, business equity, deferred comp.
- **Medicare/Medicaid** are modeled as flat age-banded costs; no long-term-care Medicaid spend-down logic, no separate Part A/B/D bracket interaction beyond IRMAA.
- **State residency is assumed constant.** Changing residency mid-retirement (e.g. moving from CA to a no-tax state) is not modeled, except through `RETIREMENT_STATE_CHOICE`, which applies a different state to the whole retirement phase (used by the Freedom milestones check).
- **Sequence-of-returns risk** is captured by Monte Carlo but not separately reported. Users concerned about SORR should inspect the distribution of failures by retirement-year cohort.
- **Fixed-horizon / no-mortality model:** both spouses are assumed alive for every year through the plan's end. There is no stochastic mortality, no survivor Social Security benefit (the higher of the two benefits continuing alone after a spouse's death), no filing-status change at first death, and no widowhood expense reduction (single-person household costs are typically lower than a couple's). `PLAN_UNTIL_AGE` sets the simulation length only, not a mortality assumption.
