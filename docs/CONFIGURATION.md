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
| `PARTNER_AGE` | `25` | Spouse/partner current age. Used for joint filing, RMDs, and SS. |
| `CURRENT_YEAR` | `2026` | Baseline calendar year for the simulation. |
| `YOUR_BIRTH_YEAR` | derived | `CURRENT_YEAR − YOUR_AGE` (likewise `PARTNER_BIRTH_YEAR`). Sets the SECURE 2.0 RMD start age (73 if born 1951–1959, else 75). Not an input. |
| `PARTNER_BIRTH_YEAR` | `2001` | Same purpose for partner. |
| `PLAN_UNTIL_AGE` | `95` | Simulation horizon. Run longer if longevity is a concern — about 30–40% of couples have one spouse living past 90. |
| `YEARS_UNTIL_WEDDING` | `1` | Years until legal marriage. Set to `0` if already married. Triggers MFJ filing and any income-based contribution limits for the partner. |

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
| `HOME_EQUITY_ACCESSIBLE_PCT` | `0.85` | Fraction of equity recoverable after selling costs (agent fees, transfer taxes). Only used if `USE_HOME_AS_BACKUP = True`. |

`HOME_EQUITY` is auto-computed as `HOME_VALUE - MORTGAGE_BALANCE`.

---

## 4. Income

### Your compensation

Income is specified age-by-age through some cutoff (default: age 40), then projected forward with growth rates.

```python
YOUR_COMPENSATION_BY_AGE = {
    31: {"base": 200_000, "bonus": 20_000, "rsu_gross": 150_000,
         "total_comp": 370_000, "after_tax": 240_000, "saved": 130_000},
    32: {...},
    # ... continue through the last age you want to hard-code
}
```

Required keys per age: `base`, `bonus`, `rsu_gross`, `total_comp`, `after_tax`, `saved`. The `saved` number is what gets contributed to taxable accounts after living expenses — this is the load-bearing field for savings projections.

| Parameter | Default | Description |
|---|---|---|
| `YOUR_SALARY_GROWTH_RATE` | `0.04` | 4%/yr growth used beyond the last age in the table. |
| `YOUR_BONUS_PCT` | `0.16` | Bonus as a fraction of salary beyond the table. |
| `YOUR_RSU_PCT` | `0.85` | RSU grant as a fraction of salary beyond the table. Set to `0` if you don't get RSUs. |

Make sure the table covers every age from `YOUR_AGE` through the year you plan to retire; anything beyond is projected from the last entry.

### Partner compensation

| Parameter | Default | Description |
|---|---|---|
| `PARTNER_SALARY` | `$42,000` | Current salary. |
| `PARTNER_SALARY_GROWTH_RATE` | `0.04` | Annual real salary growth. |

### Your contributions

| Parameter | Default | Description |
|---|---|---|
| `YOUR_401K_CONTRIBUTION` | `$23,000` | Your annual 401(k) deferral. Capped by `get_401k_limit()`. |
| `YOUR_401K_MATCH_PCT` | `0.06` | Employer match as a fraction of base salary (6% = full match up to 6%). |
| `YOUR_HSA_CONTRIBUTION` | `$7,550` | Your HSA contribution. |
| `YOUR_HSA_MATCH` | `$750` | Employer HSA contribution. |
| `YOUR_BACKDOOR_ROTH` | `$7,000` | Annual backdoor Roth IRA conversion. |
| `YOUR_ESPP_PCT` | `0.10` | Fraction of base salary routed through ESPP. |
| `YOUR_ESPP_DISCOUNT` | `0.15` | ESPP purchase discount (15% is typical). |

### Partner contributions and spending

| Parameter | Default | Description |
|---|---|---|
| `PARTNER_401K_CONTRIBUTION` | `$23,000` | Partner 401(k) contribution. |
| `PARTNER_401K_MATCH` | `$0` | Flat-dollar employer match. Set `0` if no match. |
| `PARTNER_ROTH_CONTRIBUTION` | `$7,000` | Partner Roth IRA contribution. Auto-stops after marriage if joint income exceeds Roth limits. |
| `PARTNER_ANNUAL_SPENDING` | `$24,000` | Partner's personal spending — kept separate from household expenses. |
| `PARTNER_ESTIMATED_TAX_RATE` | `0.25` | Effective federal+state rate used to estimate partner's take-home. |

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
| `YEARS_UNTIL_FIRST_CHILD` | `3` | Years until first child. Set to large number to disable. |
| `YEARS_BETWEEN_CHILDREN` | `2` | Gap between first and second child. |
| `FIRST_CHILD_MONTHLY_COST` | `$2,100` | Added to expenses once first child arrives. |
| `BOTH_CHILDREN_MONTHLY_COST` | `$3,500` | Total once second child arrives (not additive with the first). |
| `CHILD_LEAVES_HOME_AGE` | `18` | Age child moves out and stops costing money. |

### College funding (529)

| Parameter | Default | Description |
|---|---|---|
| `COLLEGE_FUNDING_PCT` | `0.00` | Fraction of college cost funded from the simulation. `0` disables 529 modeling. |
| `COLLEGE_ANNUAL_COST` | `$40,000` | Per-child annual cost (today's dollars). |
| `COLLEGE_YEARS` | `4` | Duration of college expenses per child. |

---

## 6. Retirement expenses

| Parameter | Default | Description |
|---|---|---|
| `BASE_RETIREMENT_EXPENSES_NO_MORTGAGE` | auto-computed | Sum of `YOUR_OTHER_ANNUAL + UTILITIES_ANNUAL + PARTNER_ANNUAL_SPENDING`. Don't edit directly — change the inputs. |
| `EARLY_RETIREMENT_LEISURE_INCREASE` | `$10,000` | Extra annual spending ages 50–70 (travel, hobbies). |
| `LATE_RETIREMENT_LEISURE_DECREASE` | `0.15` | 15% reduction in discretionary spending after age 75 as activity drops off. |

### Healthcare by age

`HEALTHCARE_COSTS_BY_AGE` maps life stage to annual healthcare cost (today's dollars, couple):

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
| `SS_CLAIM_AGE` | `67` | Age both you and partner claim. 62–70. |
| `YOUR_SS_MONTHLY_FRA` | `$2,000` | Your monthly benefit at full retirement age (67). |
| `PARTNER_SS_MONTHLY_FRA` | `$1,800` | Partner's monthly benefit at FRA. |
| `EARLY_SS_AGE` | `62` | Earliest SS claim. ~30% benefit reduction vs FRA. |
| `DELAYED_SS_AGE` | `70` | Latest SS claim. ~24% benefit increase vs FRA. |

Social Security benefits are entered in today's dollars. Because SS is COLA-indexed, in the all-real frame they are held **flat in real terms** (no growth beyond general CPI) — no nominal inflation is applied.

---

## 9. Tax configuration

| Parameter | Default | Description |
|---|---|---|
| `STANDARD_DEDUCTION_MFJ_2024` | `$29,200` | MFJ standard deduction. CPI-indexed in reality, so held flat at its 2024 real value in the all-real frame. Age-65+ adds `$1,550` per spouse via `ADDITIONAL_STD_DEDUCTION_65_PLUS`. |
| `YOUR_MARGINAL_TAX_RATE` | `0.22` | Rough marginal rate used for ESPP/RSU tax estimation during accumulation. Withdrawal taxes during retirement use the full bracket calculation. |

### State tax

`CaliforniaTaxBrackets` holds 2024 CA brackets. If you live in another state, replace this class with your state's brackets, or set the class to a zero-bracket schedule to simulate a no-income-tax state (FL, TX, WA, etc.). CA also taxes LTCG as ordinary income (~9.3%); other states vary.

### NIIT

| Parameter | Default | Description |
|---|---|---|
| `NIIT_THRESHOLD_MFJ` | `$250,000` | MAGI threshold for Net Investment Income Tax. |
| `NIIT_RATE` | `0.038` | 3.8% surtax on investment income above the threshold. Affects high-income households during accumulation and early retirement. |

### Medicare IRMAA

`MEDICARE_IRMAA_BRACKETS_MFJ` lists income thresholds and monthly Part B/D surcharges. Triggered at age 65 based on MAGI from two years prior. Only affects high-income retirees; under $206k MAGI you'll pay the base Part B premium with no surcharge.

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
| `ACA_BENCHMARK_MONTHLY_AT_40` | `$650` | Benchmark (second-lowest) Silver premium for a 40-year-old. Adjust for your region from healthcare.gov. |
| `ACA_CHILD_MONTHLY` | `$390` | Benchmark premium per child at home. |
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
