# Configuration Reference

This document describes every parameter you can edit in the retirement simulator. Parameters live in `retirement_sim/config.py` and are grouped by concern below.

---

## 1. How to customize

The recommended workflow is to leave `retirement_sim/config.py` alone and override it from your own file:

1. Copy `examples/example_config.py` to the package root as `my_config.py`.
2. Edit the values in `my_config.py` for your own situation.
3. Import from your file instead of the default config:

   ```python
   import my_config as cfg
   from retirement_sim import run_monte_carlo_detailed
   result = run_monte_carlo_detailed(retirement_age=50, n_simulations=5000, config=cfg)
   ```

If you just want to experiment quickly, you can also edit `retirement_sim/config.py` directly — but your changes will be overwritten on package upgrades.

All dollar values in the config are in **today's dollars** unless otherwise noted. Returns and inflation rates are **real** (already inflation-adjusted) unless otherwise noted.

---

## 2. Personal info

| Parameter | Default | Description |
|---|---|---|
| `YOUR_AGE` | `25` | Your current age. Drives every age-dependent calculation. |
| `PARTNER_AGE` | `25` | Spouse/partner current age. `0` = a single household: the engine then has no partner accounts, pay, contributions or Social Security (`has_partner()`), whatever partner numbers the profile still carries. |
| `CURRENT_YEAR` | this year | Read from the clock (`datetime.date.today().year`). A `CURRENT_YEAR` saved in an older profile is ignored. |
| `YOUR_BIRTH_YEAR` | derived | `CURRENT_YEAR − YOUR_AGE` (likewise `PARTNER_BIRTH_YEAR`). Sets the SECURE 2.0 RMD start age (73 if born 1951–1959, else 75). Not an input. |
| `PARTNER_BIRTH_YEAR` | `2001` | Same purpose for partner. |
| `PLAN_UNTIL_AGE` | `95` | Your plan-until age. Run longer if longevity is a concern — for a couple, about 30–40% have one spouse living past 90. |
| `PARTNER_PLAN_UNTIL_AGE` | `None` | Your partner's plan-until age, in their own age (`None` = same as yours). The plan runs until the **later** of the two (`plan_end_age()`), so a younger partner is covered to their own age. |
| `FILING_STATUS` | `"Married filing jointly"` | Married couples file jointly; a single person or an unmarried couple files `"Single"` or `"Head of household"`. Marriage is read from this (there is no separate wedding year). |

---

## 3. Current assets

All balances are in today's dollars. Enter zero for accounts you don't have.

### Your accounts

| Parameter | Example default | Notes |
|---|---|---|
| `YOUR_401K` | `$250,000` | Traditional (pre-tax) 401(k) balance. |
| `YOUR_ROTH_IRA` | `$75,000` | Roth IRA balance. Tax-free in retirement. |
| `YOUR_TRADITIONAL_IRA` | `$15,000` | Pre-tax IRA balance. Subject to RMDs. |
| `YOUR_HSA` | `$25,000` | Health savings account. Triple-tax-advantaged. |
| `YOUR_BROKERAGE` | `$200,000` | Taxable brokerage. Withdrawals pay LTCG/STCG. |
| `YOUR_CASH` | `$35,000` | Savings + checking. Assumed to earn ~inflation. |

### Partner accounts

| Parameter | Example default | Notes |
|---|---|---|
| `PARTNER_401K` | `$50,000` | |
| `PARTNER_ROTH_IRA` | `$25,000` | |
| `PARTNER_BROKERAGE` | `$10,000` | |
| `PARTNER_CASH` | `$25,000` | |

Add fields for partner Traditional IRA or HSA if relevant by copying the pattern above.

### Home

| Parameter | Example default | Notes |
|---|---|---|
| `HOME_VALUE` | `$700,000` | Current market value. Held flat in real terms (housing real-excess rate is 0%). |
| `MORTGAGE_BALANCE` | `$500,000` | Outstanding principal. |
| `MORTGAGE_RATE_FOR_PAYOFF` | `0.065` | The current loan's fixed rate (the app's *Mortgage interest rate*). The balance is amortized at it, so it sets how fast equity builds and what is left to repay at a sale. |
| `HOME_COST_BASIS` | `None` | What you paid for today's home (plus improvements), for tax on its sale. `None` = its value, i.e. no taxable gain. |
| `HOME_EQUITY_ACCESSIBLE_PCT` | `0.85` | Fraction of equity recoverable after selling costs (agent fees, transfer taxes). Only used if `USE_HOME_AS_BACKUP = True`. |

`HOME_EQUITY` is auto-computed as `HOME_VALUE - MORTGAGE_BALANCE`. A renter sets
`HOME_VALUE = 0`, `MORTGAGE_MONTHLY = 0` and `SPEND_RENT_MONTHLY`.

### Housing timeline: buy, move, downsize

`HOME_EVENTS` lists what changes later, each at an age of yours (the app's
*Big purchases → Home moves*). Empty = stay put. One home at a time.

```python
HOME_EVENTS = [
    {"age": 30, "action": "buy", "price": 450_000, "down_pct": 0.20,
     "rate": 0.065, "years": 30, "costs": 10_000},          # renter buys
    {"age": 45, "action": "sell_buy", "price": 800_000, "down_pct": 0.25,
     "rate": 0.055, "years": 15, "selling_cost_pct": 0.06},  # move / upgrade / downsize
    {"age": 72, "action": "sell_rent", "rent": 2_500, "costs": 5_000},  # sell, then rent
]
```

| Field | Default | Meaning |
|---|---|---|
| `age`, `action` | required | `buy`, `sell_buy` or `sell_rent`. Any purchase sells the home you own first. |
| `price`, `down_pct` | — , `0.20` | Purchase price and down payment. `loan` may be given instead of `down_pct`. |
| `rate`, `years` | `MORTGAGE_RATE_FOR_PAYOFF`, `30` | The new loan. |
| `monthly` | derived | All-in payment: level P&I + `price × HOME_CARRYING_COST_PCT / 12`. |
| `costs` | `HOUSE_MOVING_COSTS` | Buying and moving costs, paid from savings. |
| `selling_cost_pct` | `HOME_SELLING_COST_PCT` | Agent fees and closing costs on a sale. |
| `rent` | `0` | `sell_rent` only: monthly rent from then on (today's dollars). |

At a sale, proceeds (value − loan left − selling costs − tax) go into cash. The
gain above `HOME_SALE_EXCLUSION_SINGLE` ($250,000 per owner) or
`HOME_SALE_EXCLUSION_MFJ` ($500,000 married filing jointly) is taxed as a
long-term gain; unmarried partners are taken to own the home together ($250,000
each). Rent stops once you buy; owner costs stop once you sell to rent.

The single house move of older plans (`HOUSE_MOVE_ENABLED`, `HOUSE_MOVE_AGE`,
`NEW_HOME_VALUE`, `NEW_MORTGAGE_BALANCE`, `NEW_MORTGAGE_MONTHLY`,
`NEW_MORTGAGE_YEARS`, `NEW_MORTGAGE_RATE`) still works: `cfg.housing_events()`
turns it into one more event with exactly those numbers. The app shows it in the
moves list the first time the plan is opened.

---

## 4. Income

### Your compensation

Income is specified age-by-age through some cutoff (default: age 40), then projected forward with growth rates.

```python
YOUR_COMPENSATION_BY_AGE = {
    31: {"base": 200_000, "bonus": 20_000, "rsu_gross": 150_000,
         "total_comp": 370_000, "saved": 130_000},
    32: {...},
    # ... continue through the last age you want to hard-code
}
```

Keys per age: `base`, `bonus`, `rsu_gross`, `total_comp` (the wages that are taxed) and `saved` (the brokerage contribution in *Manual* savings mode only; *Auto* modes invest whatever is left after spending).

Take-home is **computed**, not entered: `working_year_taxes()` applies the 2024 federal brackets and standard deduction for your filing status, your state's table, FICA per earner (6.2% up to the $168,600 wage base, 1.45% Medicare, 0.9% above $200k/$250k), after your pre-tax 401(k) and HSA contributions. A row may still carry an `after_tax` value to force a known take-home (pay after taxes **and** after 401(k)/HSA deferrals); older profiles whose rows hold the app's old automatic 70% figure have it removed on load so the computed value is used.

| Parameter | Default | Description |
|---|---|---|
| `YOUR_OTHER_INCOME` | `$0` | Taxable income that isn't pay (rent, interest, side work). Taxed as ordinary income, no FICA, flat in today's dollars, received only while you work. |

| Parameter | Default | Description |
|---|---|---|
| `YOUR_SALARY_GROWTH_RATE` | `0.04` | 4%/yr growth used beyond the last age in the table. |
| `YOUR_BONUS_PCT` | `0.16` | Bonus as a fraction of salary beyond the table. |
| `YOUR_RSU_PCT` | `0.85` | RSU grant as a fraction of salary beyond the table. Set to `0` if you don't get RSUs. |

Make sure the table covers every age from `YOUR_AGE` through the year you plan to retire; anything beyond is projected from the last entry.

### Partner compensation

| Parameter | Default | Description |
|---|---|---|
| `PARTNER_SALARY` | `$42,000` | Current base salary. |
| `PARTNER_BONUS_AMOUNT`, `PARTNER_RSU_AMOUNT` | `$0` | Added to base as wages (FICA applies), grown with the salary. |
| `PARTNER_OTHER_INCOME` | `$0` | Non-wage income, as `YOUR_OTHER_INCOME`. |
| `PARTNER_SALARY_GROWTH_RATE` | `0.04` | Annual real salary growth. |

### Your contributions

| Parameter | Default | Description |
|---|---|---|
| `YOUR_401K_CONTRIBUTION` | `$23,000` | Your annual 401(k) deferral. Capped by `get_401k_limit()` and by your pay. |
| `YOUR_401K_MATCH_PCT` | `0.06` | Employer match: dollar for dollar on your deferral, up to this fraction of base salary. The match is `min(your 401(k) contribution, pct x base)`, so contributing less than the match % earns less match. Set in the Savings section. |
| `YOUR_HSA_CONTRIBUTION` | `$7,550` | Your HSA contribution. |
| `YOUR_HSA_MATCH` | `$750` | Employer HSA contribution. |
| `YOUR_BACKDOOR_ROTH` | `$7,000` | Annual backdoor Roth IRA conversion. |
| `YOUR_ESPP_PCT` | `0.10` | Fraction of base salary routed through ESPP. |
| `YOUR_ESPP_DISCOUNT` | `0.15` | ESPP purchase discount (15% is typical). |

### Partner contributions and spending

| Parameter | Default | Description |
|---|---|---|
| `PARTNER_401K_CONTRIBUTION` | `$23,000` | Partner 401(k) contribution. |
| `PARTNER_401K_MATCH_PCT` | `0.0` | Partner's employer match, same rule as `YOUR_401K_MATCH_PCT`. (Replaces the never-used `PARTNER_401K_MATCH`.) |
| `PARTNER_ROTH_CONTRIBUTION` | `$7,000` | Partner direct Roth IRA contribution, reduced by the 2024 Roth income phase-out of the return it's on (joint MAGI $230k–$240k; single/HOH $146k–$161k) and limited to earned income. Marriage alone no longer stops it. |
| `PARTNER_ANNUAL_SPENDING` | `$24,000` | Partner's personal spending — kept separate from household expenses. |

---

## 5. Expenses

### Housing and recurring expenses

| Parameter | Default | Description |
|---|---|---|
| `MORTGAGE_MONTHLY` | `$0` | Principal + interest + escrow. |
| `MORTGAGE_YEARS_REMAINING` | `0` | Years until payoff. When reached, mortgage drops from expenses. |
| `UTILITIES_MONTHLY` | `$150` | Water, gas, electric, internet, etc. |
| `YOUR_OTHER_MONTHLY` | `$2,000` | Your personal non-housing spending (food, transportation, hobbies). |
| `PARTNER_OTHER_MONTHLY` | `$1,500` | Partner's own spending, added to household expenses every year. The app's *Partner spending* input sets it and `PARTNER_MONTHLY_SPENDING` (the partner-savings math) together, and sets both to $0 for a single household (partner age 0). |

### Children

| Parameter | Default | Description |
|---|---|---|
| `CHILDREN` | two children (below) | One entry per child, born or planned; `[]` = child-free. Each entry's fields are below; a field left out takes its `CHILD_DEFAULTS` value. |
| `years_until_birth` | `3`, `6` | Years from now until the child is born; negative = already born (`-5` is a 5-year-old today). |
| `monthly_cost` | `$2,100`, `$1,400` | What the child costs each month while living at home (today's dollars, grows with the childcare factor). |
| `leaves_home_age` | `18` | The child's age when those costs stop. Each child has their own. |
| `college_funding_pct` | `0.0` | Share of college you pay (`0` = none, `1` = all). Saved in that child's own 529 from birth to `COLLEGE_START_AGE` (18), then college is paid from it, during working years or retirement; the budget covers anything the 529 can't. |
| `college_annual_cost` | `$40,000` | One year of college (today's dollars). |
| `college_years` | `4` | Years of college, from age 18. |

The engine opens one 529 per child (`child1_529`, `child2_529`, …).

**Older profiles** described at most two children with `YEARS_UNTIL_FIRST_CHILD`, `YEARS_BETWEEN_CHILDREN`, `FIRST_CHILD_MONTHLY_COST`, `BOTH_CHILDREN_MONTHLY_COST`, `CHILD_LEAVES_HOME_AGE` and `COLLEGE_*`. They still load: `migrate_legacy_overrides()` turns them into the equivalent `CHILDREN` list (the second child costs what "both children" added over the first; `YEARS_UNTIL_FIRST_CHILD` ≥ 99 means none), so they give the same results. It runs when a profile is loaded and wherever overrides reach the config.

---

## 6. Retirement expenses

| Parameter | Default | Description |
|---|---|---|
| `BASE_RETIREMENT_EXPENSES_NO_MORTGAGE` | auto-computed | Sum of `YOUR_OTHER_ANNUAL + UTILITIES_ANNUAL + PARTNER_ANNUAL_SPENDING`. Don't edit directly — change the inputs. |
| `EARLY_RETIREMENT_LEISURE_INCREASE` | `None` | Extra $/yr for travel and hobbies early in retirement. `None` = $10,000 for two adults, two-thirds of that for one. |
| `EARLY_RETIREMENT_LEISURE_UNTIL_AGE` | `70` | The extra runs from retirement until this age... |
| `RETIREMENT_LEISURE_MIN_YEARS` | `5` | ...and for at least this many years after a late retirement. |
| `LATE_RETIREMENT_LEISURE_DECREASE` | `0.15` | Later-years reduction of living spending. Housing (payment, rent, tax + insurance) is not reduced. |
| `LATE_RETIREMENT_START_AGE` | `75` | The reduction starts at this age... |
| `LATE_RETIREMENT_MIN_YEARS` | `10` | ...or this many years after retiring, whichever is later. |

All six are inputs in the app's *Retirement goals* section. Retiring at 65 or
earlier gives the old fixed ages (extra until 70, reduction from 75).

`SPEND_LIFECYCLE_PRESET` moves food/discretionary spending by age: the travel
boom (+50% discretionary) runs over the same early-retirement years and its
"quieter later" (−20%) and the conservative preset (−30%) start with the
later-years reduction; empty-nest is +30% while any child is at home and −25%
once the last has left (`SPEND_EMPTY_NEST_AGE`, derived from the children).

### Healthcare by age

`HEALTHCARE_COSTS_BY_AGE` maps life stage to annual healthcare cost (today's
dollars, for a couple: `HEALTHCARE_BAND_ADULTS = 2`). Each covered adult is
charged half a band for their own age, so one person pays one share. A partner
is covered whenever there is one (`PARTNER_AGE > 0`), married or not.

| Key | Default | Covers |
|---|---|---|
| `pre_retirement` | `$6,000` | Ages pre-retirement — employer-subsidized premiums + OOP. |
| `early_retirement` | `$24,000` | From retirement until age 65 — ACA marketplace. Used only when `MODEL_ACA_AGE_RATED = False`; otherwise the age-rated model below prices these years. |
| `medicare_base` | `$8,000` | Ages 65–74 — Medicare Part B/D + Medigap + OOP. |
| `medicare_mid` | `$12,000` | Ages 75–84 — higher utilization. |
| `medicare_late` | `$18,000` | Ages 85+ — significant medical needs (LTC handled separately). |

These are today's-dollar amounts and grow at the healthcare **real-excess** rate of 1.75%/yr (`healthcare` 4.5% − `general` 2.75%) in the all-real frame.

---

## 7. Investment assumptions

### Return scenarios

| Parameter | Default | Description |
|---|---|---|
| `ACTIVE_RETURN_SCENARIO` | `'historical'` | One of `'conservative'`, `'historical'`, `'pessimistic'`. Switches `RETURN_SCENARIOS` entry used. |

`RETURN_SCENARIOS` bundles stock/bond return and volatility assumptions:

| Scenario | Stock return | Bond return | Stock vol | Bond vol | When to use |
|---|---|---|---|---|---|
| `conservative` | 7.0% | 2.0% | 19% | 8% | Prudent planning below historical averages. |
| `historical` | 8.7% | 3.1% | 20% | 8.7% | 1926–2024 real arithmetic mean. |
| `pessimistic` | 5.0% | 1.0% | 22% | 10% | Stress test for low-return futures. |

All returns are **real** (inflation-adjusted).

### Volatility and correlation

| Parameter | Default | Description |
|---|---|---|
| `STOCK_VOLATILITY` | `0.19` | Stock std dev. Overridden when a scenario is active. |
| `BOND_VOLATILITY` | `0.08` | Bond std dev. |
| `STOCK_BOND_CORRELATION` | `-0.20` | Stock/bond correlation. Negative reflects post-2000 behavior (bonds rally on stock crashes). |
| `INVESTMENT_FEE_RATE` | `0.0015` | 0.15% blended annual expense ratio. Set to `0.0003` for pure index funds, `0.01`+ for actively managed portfolios. |
| `APPLY_VOLATILITY_DRAG` | `True` | Adjust arithmetic returns down by `vol^2 / 2` to get geometric returns for compounding. Leave on. |

### Inflation

| Parameter | Default | Description |
|---|---|---|
| `EXPECTED_INFLATION` | `0.0275` | General inflation, per year. |
| `INFLATION_VOLATILITY` | `0.015` | Std dev of annual inflation draws. |

`INFLATION_RATES` provides category-specific rates. **The model runs in an all-real (today's-dollars) frame:** because investment returns are drawn real, general CPI does not grow any liability. The `general` rate is used only to define the *baseline* that other categories are measured against — the general factor itself stays flat at 1.0. Each other category grows only by its **real-excess** rate = (category rate − `general` rate). So `housing` (equal to `general`) is flat in real terms, `healthcare` grows at 1.75%/yr real, and `childcare` at 1.25%/yr real.

| Key | Default | Real-excess (rate − general) | Used for |
|---|---|---|---|
| `general` | `0.0275` | 0.00% (flat, defines baseline) | Most expenses, leisure, college/529, SS. |
| `healthcare` | `0.045` | 1.75% | ACA/Medicare premiums, OOP, LTC. |
| `housing` | `0.0275` | 0.00% (flat) | Utilities, home value growth. |
| `childcare` | `0.04` | 1.25% | Child expenses while kids are home. |

> **Frozen-nominal thresholds (limitation).** Statutory thresholds specified in nominal dollars that are not CPI-indexed in reality are held at their 2024 values in this real frame, so they tighten over time: **NIIT** ($250k MFJ), **IRMAA** brackets, and the **Social Security taxation** provisional-income thresholds ($32k–$44k MFJ). This is a conservative, realistic bias. See `METHODOLOGY.md` §4.

---

## 8. Social Security

Get personal estimates from [ssa.gov](https://www.ssa.gov) — log in and download the latest statement.

| Parameter | Default | Description |
|---|---|---|
| `INCLUDE_SOCIAL_SECURITY` | `True` | Toggle SS entirely. Turn off for a conservative "what if SS is cut" scenario. |
| `SS_CLAIM_AGE` | `67` | Age you claim. 62–70. |
| `PARTNER_SS_CLAIM_AGE` | `None` | Age your partner claims, in their own age (`None` = same as `SS_CLAIM_AGE`). |
| `MODEL_SPOUSAL_SS_BENEFIT` | `True` | Married couples: a spouse whose own benefit is under half of the other's is topped up to half once both have claimed (reduced if claimed before 67, no delayed credit). Not for unmarried partners. `False` = each person's own benefit only. |
| `YOUR_SS_MONTHLY_FRA` | `$2,000` | Your monthly benefit at full retirement age (67). |
| `PARTNER_SS_MONTHLY_FRA` | `$1,800` | Partner's monthly benefit at FRA. |
| `EARLY_SS_AGE` | `62` | Earliest SS claim. ~30% benefit reduction vs FRA. |
| `DELAYED_SS_AGE` | `70` | Latest SS claim. ~24% benefit increase vs FRA. |

Social Security benefits are entered in today's dollars. Because SS is COLA-indexed, in the all-real frame they are held **flat in real terms** (no growth beyond general CPI) — no nominal inflation is applied.

---

## 9. Tax configuration

All tables are 2024 figures held flat in today's dollars (statutory thresholds that are never indexed decay; see METHODOLOGY §4). Every filing-status-dependent table follows `FILING_STATUS` ("Married filing jointly" / "Single" / "Head of household").

| Parameter | Default | Description |
|---|---|---|
| `FILING_STATUS` | MFJ | Selects the federal and state brackets, standard deductions, LTCG brackets, Social Security taxability thresholds, NIIT and Additional Medicare thresholds, IRMAA tiers, the Roth IRA phase-out and the Roth conversion target. |
| `STANDARD_DEDUCTION_BY_STATUS` | $29,200 / $14,600 / $21,900 | Federal standard deduction. Age 65+ adds $1,550 per spouse (joint) or $1,950 (single/HOH). |
| `LTCG_BRACKETS_BY_STATUS` | 0% to $94,050 / $47,025 / $63,000 | 15% to $583,750 / $518,900 / $551,350, then 20%. |
| `SS_WAGE_BASE` | `$168,600` | Social Security wage base, per earner. With `SOCIAL_SECURITY_TAX_RATE` 6.2%, `MEDICARE_TAX_RATE` 1.45%, `ADDITIONAL_MEDICARE_TAX_RATE` 0.9% above `ADDITIONAL_MEDICARE_THRESHOLD_BY_STATUS` ($250k joint / $200k otherwise, per return). |
| `ROTH_IRA_PHASEOUT_BY_STATUS` | $230k–$240k joint, $146k–$161k others | Direct Roth IRA phase-out (partner's Roth). |
| `YOUR_MARGINAL_TAX_RATE` | `0.05` | Flat **state** rate for `STATE_CHOICE = "Other"` (the app's *Another state (flat rate)*), applied above the federal standard deduction, Social Security exempt. |

**Unmarried couples.** With a partner in the plan (`PARTNER_AGE > 0`) and a status other than MFJ, the household files **two returns**: you on `FILING_STATUS` (Single or Head of household), your partner as Single. Wages, withdrawals, RMDs, Roth conversions, capital gains and Social Security are each taxed on their owner's return (`files_two_returns()`, `return_status()`).

### State tax

`STATE_CHOICE` is a two-letter code for any state or `"DC"`, read from `retirement_sim/state_tax_data.py`: brackets by filing status, standard deduction, personal exemptions, whether Social Security is taxed (exempt, taxed, or exempt below an income limit), retirement-income exclusions by age, state capital-gains exclusions, and quirks (Pennsylvania taxes 401(k) deferrals; California and New Jersey tax HSA contributions; California SDI 1.1% of wages). Each row carries its tax year and a confidence level (`high`, `medium`, or `approx`, which the app labels as approximate). City/county income taxes, credits and itemized deductions are not modeled. To verify or refresh the table, see [`state_tax_research_prompt.md`](state_tax_research_prompt.md).

Legacy values still work: `"CA"`, `"No state tax"` (zero) and `"Other"` (flat rate). Unknown values fall back to CA. `MODEL_CA_EXEMPTS_SOCIAL_SECURITY` (historical name) switches every state's Social Security exemption off when set `False`.

### NIIT

| Parameter | Default | Description |
|---|---|---|
| `NIIT_THRESHOLD_MFJ` / `NIIT_THRESHOLD_SINGLE` | `$250,000` / `$200,000` | MAGI threshold of the return. |
| `NIIT_RATE` | `0.038` | 3.8% surtax on investment income above the threshold. |

### Medicare IRMAA

`MEDICARE_IRMAA_BRACKETS_MFJ` and `MEDICARE_IRMAA_BRACKETS_SINGLE` (2025 CMS tiers: $212k / $106k first surcharge). An unmarried couple's household MAGI is split evenly and each person is tested on the individual tiers.

### Roth conversion target

`ROTH_CONVERSION_TARGET_BRACKET` defaults to `None`: fill ordinary income up to the top of the 12% bracket for the filing status ($94,300 joint, $47,150 single, $63,100 head of household; `ROTH_CONVERSION_TARGET_BY_STATUS`). A number applies to every return. A saved $94,300 under a non-joint status is treated as the old default and follows the status.

### Early withdrawal

| Parameter | Default | Description |
|---|---|---|
| `EARLY_WITHDRAWAL_AGE_401K_IRA` | `59.5` | Age for penalty-free traditional 401k/IRA access. |
| `EARLY_WITHDRAWAL_PENALTY_401K_IRA` | `0.10` | 10% penalty before that age. |
| `EARLY_WITHDRAWAL_AGE_HSA` | `65` | Age for penalty-free HSA non-medical withdrawals. |
| `EARLY_WITHDRAWAL_PENALTY_HSA` | `0.20` | 20% penalty for HSA non-medical before 65. |

---

## 10. Retirement strategy toggles

### Dynamic spending (guardrails)

Reduce spending when the portfolio underperforms, mimicking real behavior.

| Parameter | Default | Description |
|---|---|---|
| `DYNAMIC_SPENDING_ENABLED` | `True` | Master toggle. |
| `DISCRETIONARY_EXPENSE_RATIO` | `0.30` | Share of expenses considered cuttable (travel, dining, hobbies). With `MODEL_GUARDRAILS_EXCLUDE_HOUSING = True` (default) it applies to non-housing spending only; housing is never cut. |
| `GUARDRAIL_MIN_DISCRETIONARY_FACTOR` / `GUARDRAIL_MAX_DISCRETIONARY_FACTOR` | `0.60` / `1.40` | Clamp on the combined (guardrail × return-based) multiplier applied to the cuttable share. `0.0` allows the whole cuttable share to be cut. |

`SPENDING_GUARDRAILS` dict:

| Key | Default | Meaning |
|---|---|---|
| `floor_trigger` | `0.70` | Cut if portfolio < 70% of inflation-adjusted target. |
| `floor_reduction` | `0.15` | Cut discretionary by 15% when triggered. |
| `ceiling_trigger` | `1.30` | Optional spend-up threshold. |
| `ceiling_increase` | `0.00` | Default: no increase (conservative). Set to `0.10` for symmetric guardrails. |

### Return-based spending

Applied in addition to guardrails.

| Parameter | Default | Description |
|---|---|---|
| `RETURN_BASED_SPENDING_ENABLED` | `True` | Toggle year-over-year adjustments based on that year's return. |

`RETURN_BASED_SPENDING_RULES`:

| Key | Default | Meaning |
|---|---|---|
| `excellent_return_threshold` / `excellent_spending_boost` | `0.15` / `0.00` | Returns ≥15% → no boost (conservative). |
| `good_return_threshold` / `good_spending_boost` | `0.08` / `0.00` | Returns ≥8% → no boost. |
| `poor_return_threshold` / `poor_spending_cut` | `0.00` / `0.10` | Negative returns → cut 10%. |
| `bad_return_threshold` / `bad_spending_cut` | `-0.10` / `0.20` | Returns ≤-10% → cut 20%. |

### Roth conversion ladder

| Parameter | Default | Description |
|---|---|---|
| `ENABLE_ROTH_CONVERSION` | `True` | Convert traditional → Roth during low-income retirement years. |
| `ROTH_CONVERSION_TARGET_BRACKET` | `$94,300` | Convert enough to fill up to the top of this bracket (12% bracket). |
| `ROTH_CONVERSION_MAX_ANNUAL` | `$100,000` | Hard cap per year. |
| `ROTH_CONVERSION_STOP_AGE` | `67` | Stop once SS starts pushing up ordinary income. |

### ACA health insurance

| Parameter | Default | Description |
|---|---|---|
| `ACA_ENABLED` | `True` | Model pre-65 ACA marketplace costs. |
| `MODEL_ACA_AGE_RATED` | `True` | Price each marketplace member by age (federal 3:1 curve) plus children at home; subsidy from household-size FPL with the 400% cliff. `False` = legacy flat household premium. |
| `ACA_BENCHMARK_MONTHLY_AT_40` | `$650` | Benchmark (second-lowest) Silver premium for a 40-year-old, before subsidy (2026 San Diego, close to the US average of about $625). An input in the app's Assumptions panel: look yours up by ZIP code at healthcare.gov. |
| `ACA_CHILD_MONTHLY` | `$390` | Benchmark premium per child at home (also an input). |
| `ACA_OOP_PER_PERSON_ANNUAL` | `$1,500` | Out-of-pocket per marketplace member, net of `SPEND_HEALTH_MONTHLY` so it isn't counted twice. |
| `PARTNER_EMPLOYER_HEALTH_COVERAGE` | `True` | While a partner keeps working after you retire, their employer plan covers the household: no marketplace cost. Put the payroll premium in the living-expense base. |
| `ACA_BASE_MONTHLY_PREMIUM` | `$2,000` | Legacy path only: unsubsidized household premium. |

### Long-term care

| Parameter | Default | Description |
|---|---|---|
| `LTC_ENABLED` | `False` | Off by default. Enable if you don't have LTC insurance and want to stress test. |
| `LTC_START_AGE` | `85` | Age LTC risk becomes material. |
| `LTC_PROBABILITY` | `0.50` | 50% lifetime chance at advanced ages. |
| `LTC_DURATION_YEARS` | `3` | Average care duration. |
| `LTC_ANNUAL_COST` | `$100,000` | Facility + care (today's dollars). Grows at the healthcare real-excess rate (1.75%/yr) in the all-real frame. |

### Glide path

Shift from stocks to bonds over retirement.

| Parameter | Default | Description |
|---|---|---|
| `GLIDE_PATH_ENABLED` | `True` | Toggle glide path (otherwise uses fixed `STOCK_ALLOCATION`/`BOND_ALLOCATION`). |
| `GLIDE_PATH_START_STOCK_PCT` | `0.90` | Stock allocation at retirement. |
| `GLIDE_PATH_START_BOND_PCT` | `0.10` | Bond allocation at retirement. |
| `GLIDE_PATH_END_AGE` | `75` | Target age for end allocation. |
| `GLIDE_PATH_END_STOCK_PCT` | `0.60` | Stock allocation at `GLIDE_PATH_END_AGE`. |
| `GLIDE_PATH_END_BOND_PCT` | `0.40` | Bond allocation at `GLIDE_PATH_END_AGE`. |
| `GLIDE_PATH_HOLD_AFTER` | `True` | Hold end allocation steady past the target age. |

---

## 11. Simulation settings

| Parameter | Default | Description |
|---|---|---|
| `NUM_SIMULATIONS` | `10_000` | Monte Carlo path count. Lower (1,000–2,000) for fast iteration, keep at 10k for final numbers. |
| `EARLIEST_RETIREMENT_AGE` | `40` | Sweep lower bound when solving for earliest retirement age. |
| `LATEST_RETIREMENT_AGE` | `65` | Sweep upper bound. |
| `TARGET_SUCCESS_RATE` | `0.80` | Probability of not running out of money. 80% is the common planning target; 90–95% for very conservative. |
| `USE_HOME_AS_BACKUP` | `True` | If `True`, the simulation can tap `HOME_EQUITY * HOME_EQUITY_ACCESSIBLE_PCT` as a last-resort buffer (e.g., reverse mortgage or downsizing). |

---

## Further reading

- `retirement_sim/config.py` — authoritative source with helper functions (`get_401k_limit`, `calculate_social_security`, `calculate_aca_premium`, etc.).
- `examples/example_config.py` — sanitized template to copy.
- `README.md` — getting started and run commands.
