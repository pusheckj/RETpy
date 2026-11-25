# Data sources

Where the figures in `retirement_sim` come from, and which ones were checked against a second source.

## Federal, Medicare, ACA, California

Tax year 2026. Primary sources (IRS, SSA, CMS, FTB), each with its quote, are listed in
[`data_sources/2026_verification.md`](data_sources/2026_verification.md). Federal tables are in
`retirement_sim/config.py`.

## State income tax (all 50 states and DC), tax year 2026

`retirement_sim/state_tax_data.py` holds the brackets and standard deductions of every state and DC for
2026. They come from the **BiggerPockets Money Income Tax Projection Calculator** (v1.11.2, captured
2026-11-25, https://biggerpocketsmoney.com/tax-projection/). Thank you to BiggerPockets Money for
publishing the tool and its tables. The calculator says its state figures follow the Tax Foundation 2026
tables, updated through October 2026 for new laws and agency guidance. It names these agencies for
single states:

| State | Source named by the calculator |
| --- | --- |
| CA | California Franchise Tax Board, Tax News October 2026 (2026 indexing); EDD for the 2026 SDI rate |
| GA | Georgia Department of Revenue, HB 463 (May 2026): flat 4.99%, new standard deductions |
| HI | Hawaii Department of Taxation, Act 46: 2026 standard deductions |
| ME | Maine Revenue Services, 2026 schedule revised 5/20/26: standard deductions and the new 2% surcharge |
| WV | West Virginia Tax Division, SB 392 (March 2026): rates cut 5% |
| AR | 2026 special session: top rate 3.7%, retroactive to January 1 |
| UT | SB 60 (2026): 4.45%; taxpayer credit amounts from the 2026 draft TC-40 (rev. 10/20/26) |
| SC | H.4216 (March 2026): two rates and the SCIAD deduction |

RETpy did not re-fetch these agency documents. Each is as cited by the calculator. The calculator itself
says its state results are simplified estimates and that a CFP/CPA review is pending. The cross-check below
tests RETpy's arithmetic against the calculator's engine. It does not prove the calculator's tables are
right.

### What was taken, what was kept

Only `brackets` and `std_deduction` were updated, plus `year` (2026 for every row) and the notes of the rows
that changed. Everything RETpy models that the calculator does not stays as it was: Social Security
treatment, retirement-income exclusions, capital-gains exclusions, personal exemptions, the Pennsylvania
401(k) rule, HSA add-backs, and California's credits, surtax and SDI. Confidence labels are kept too, except
Arizona (now `medium`), Utah and South Carolina (now `approx`). California's row is unchanged.

32 rows changed. Top rate, Single schedule, old to new:

| State | Top rate | State | Top rate | State | Top rate |
| --- | --- | --- | --- | --- | --- |
| AR | 3.9% to 3.7% | KY | 4% to 3.5% | NE | 5.84% to 4.55% |
| CO | 4.25% to 4.40% | LA | 4.25% to 3% | NM | 5.9% (lower brackets) |
| GA | 5.39% to 4.99% | MA | 9% (surtax from $1,107,750) | NY | 10.9% (lower rates cut 0.1%) |
| HI | 11% (wider brackets) | MD | 5.75% to 6.5% | OH | 3.5% to 2.75% |
| IA | 5.7% to 3.8% | ME | 7.15% to 9.15% | OK | 4.75% to 4.5% |
| ID | 5.695% to 5.3% | MN | 9.85% (indexed) | OR | 9.9% (indexed) |
| IN | 3.05% to 2.95% | MO | 4.8% to 4.7% | RI | 5.99% (indexed) |
| MS | 4.7% to 4% | MT | 5.9% to 5.65% | SC | 6.2% to 5.21% |
| NC | 4.5% to 3.99% | ND | 2.5% (indexed) | UT | 4.55% to 4.45% |
| VA | 5.75% (deduction only) | VT | 8.75% (indexed) | WI | 7.65% (indexed) |
| WV | 5.12% to 4.58% | AZ | 2.5% (deduction only) | | |

The other 18 rows (AL, AK, CT, DE, DC, FL, IL, KS, MI, NV, NH, NJ, PA, SD, TN, TX, WA, WY) already equal
the calculator's 2026 figures, so they only changed their year. AL keeps a deduction that differs
from the calculator's (below).

### Where RETpy differs from the calculator on purpose

| Row | What RETpy does | Why |
| --- | --- | --- |
| AZ | $8,350 single / $16,700 joint, as the calculator lists | Arizona follows federal law as it stood before the 2025 changes, which gives about these amounts. The head-of-household figure is the single amount and may be low. Not checked against the Arizona Department of Revenue 2026 form. Confidence is `medium` |
| AL | Income-tested deduction floor ($2,500 / $5,000) | The calculator takes the top of the range |
| WI | No standard deduction (the sliding deduction is left out) | The calculator takes the full $13,960 and says it understates tax for high earners |
| KY | Joint return gets two $3,360 deductions | The calculator gives one; Kentucky gives each taxpayer one |
| LA | Personal exemption set to 0 | The 2025 reform replaced it with the $12,875 / $25,750 standard deduction; keeping both would count it twice |
| MN, ND, NE, VT, OK, OR, ID, MT, LA | Head of household keeps its own schedule | The calculator lists Single's figures for head of household. OK, OR and ID use the joint brackets (as before) with 2026 numbers. MT uses 1.5 times the single band ($71,250), as before. LA uses the joint deduction ($25,750). NE uses the earlier head-of-household thresholds with 2026 rates. MN, ND and VT keep the earlier head-of-household brackets. MN, NE, OK, OR and VT keep the earlier head-of-household deduction. The MN, ND, VT, NE, OK, OR head-of-household deductions and thresholds are earlier figures, and the MT and LA ones are derived, not taken from a 2026 source |
| Federal HoH | 24% band tops at $201,750 | The calculator tops it at $201,775, which is wrong (Rev. Proc. 2025-32) |
| OH | 2.75% from $13,977 | Ohio charges $332 plus 2.75% above $26,050. One bracket set cannot hold the jump, so the rate starts where the formula crosses zero. Exact above $26,050, up to $332 high below it |
| AR | Graduated table only | Above $94,700 of taxable income Arkansas uses a second table that adds up to about $290. Not modeled |
| UT | Flat 4.45%, no credit | The taxpayer credit (6% of the federal deduction, cut by 1.3 cents per dollar of income above $18,696 single / $37,392 joint) is left out. Lower incomes are overstated by up to about $1,900. Confidence is now `approx` |
| SC | $15,000 / $30,000 / $22,500 deduction, no phase-out | The deduction phases out between $40,000 and $95,000 (single). Tax is understated above $40,000 by up to about $780 single / $1,560 joint. Confidence is now `approx` |

### Not updated

Amounts that sit outside `brackets` and `std_deduction` are still the earlier values. The calculator's notes give
newer figures for some: Illinois exemption $2,925 (RETpy $2,775), Michigan $5,900 ($5,600), Maine $5,300 ($5,000),
Ohio $2,400 ($1,900, income-tested). Retirement-income exclusion limits were not touched either, and
state credits that RETpy leaves out (for example Delaware's, Nebraska's and Oregon's) stay out. A later pass can
refresh them.

### Cross-check

`tools/tax_crosscheck/` runs the same returns through the calculator's engine and through RETpy and
compares them to the cent. The latest run is in [`tools/tax_crosscheck/REPORT.md`](../tools/tax_crosscheck/REPORT.md).
Pinned results are in `tests/test_state_tax_2026.py`. They need no Node.

## Local childcare and spending benchmark (`ui/data/budget/`)

Two features show typical costs for households like yours: the childcare suggestion in the Family section and "Your spending vs similar households" in the Spending tab (plus one line in the Money check-up). How they work: `docs/METHODOLOGY.md`, section 15.4.

### Where the data comes from

The data files are copied unchanged from **BiggerPockets Money's Household Spending Comparison v2.4.0**, a free tool at https://biggerpocketsmoney.com/budget/ (captured 2026-11-25). Its numbers come from US government sources:

| File | Content | Agency and source |
|---|---|---|
| `ce_xtab.json` | Yearly spending by income fifth, with household-size and age ratios | US Bureau of Labor Statistics (BLS), Consumer Expenditure Surveys 2025: Table 1101 (income fifths, released 2026-10-29), Table 1400 (size), Table 1300 (age) |
| `cpi_factors.json` | Price growth from the 2025 average to 2026, by group | BLS Consumer Price Index, September 2026 release |
| `locations.json` | 739 areas: price levels and rents | US Bureau of Economic Analysis (BEA), Regional Price Parities 2024. US Department of Housing and Urban Development (HUD), Fair Market Rents FY2027 |
| `childcare_state_prices.json`, `childcare_county_medians.json`, `childcare_county_crosswalk.json` | Yearly childcare price by age tier, for 51 states and DC and 615 counties; which county each area uses | US Department of Labor, National Database of Childcare Prices (NDCP), 2022 |
| `constants.json`, `rpp_map.json` | Rent-by-income factors, phone share of utilities, childcare age weights and CPI constants, mapping of groups to price indexes | BiggerPockets Money's method, from the tool's own code. The rent-by-income factors cite Census ACS 2025 table B25122 |

BiggerPockets Money's own README for these files (their formulas, worked examples and known quirks) is the reference for the numbers. The tool says its figures are "statistical averages of what peers spend, not targets and not advice". So do we.

### What is BiggerPockets Money's choice, not a published figure

These are BPM's method. We use them and say so on the page and in the code:

- **Dampening 0.5** on the size and age adjustments (`DAMP` in `ce_xtab.json`). Income already tracks size and age, so the full ratios would count them twice.
- **Childcare age weights** (`AGE_WEIGHT` in `constants.json`): how a household's children spread over infant, toddler, preschool and school-age, by the parent's age band and household size. The app does not use them. They stay in the code (`bpm_weights`) so the tests can reproduce BPM's worked example.
- **Childcare scaling.** A state's price is scaled by the area's BEA Rents index, kept between 0.65 and 1.70, when you pick an area with no county figure. A county median is used as it is.
- **Housing from HUD rent.** With an area, housing is the HUD Fair Market Rent for BPM's bedroom count, times a rent-by-income factor (0.75, 0.85, 1.00, 1.25, 1.25). Utilities keep only the phone and internet share.
- **Price index for each group**: goods for food, transport and clothing; other services for health and entertainment; all items for other and utilities.
- **CPI carry**: 1.172 from 2022 to 2025 and 1.0299 from 2025 to 2026 for childcare, and the group factors in `cpi_factors.json`.

### What this app changes

- **Childcare weights are ours.** The childcare box covers a child's first five years, so the weights follow NDCP's tiers over ages 0 to 4: 0.4 infant, 0.2 toddler, 0.4 preschool. For a child already born they cover only the years still ahead.
- **Household size.** Housing and utilities are sized for everyone at home now. The other rows use the adults only, because the comparison leaves out your children's costs. Food counts everyone when your figure comes from statements.
- BEA price levels are **renormalized** so each US component is exactly 1.00, the way `ui/utils/place_costs.py` does (raw BEA US goods is 99.6 and other services 100.1). BPM reads them raw. The tests reproduce BPM's worked examples with the raw reading.
- The survey's **Pensions** line (payroll tax, retirement contributions, life insurance) is left out. The planner models those elsewhere.
- Groups are folded into the app's categories (housing with utilities, clothing with Fun and discretionary, your partner's spending with Other), and the tab compares your plan's monthly inputs, or your statement averages.
- A state with no area picked uses the state's own childcare price as it is. BPM's tool always works from an area, and scales a state price by that area's rents.
- **Income-group cutoffs are estimates.** BPM asks you to pick the group and ships no dollar cutoffs. Only the first, $32,623, is in its data. The others (`QUINTILE_UPPER` in `ui/utils/budget_compare.py`) are round numbers scaled from Census, not published CE figures. Replace them with the BLS CE 2025 Table 1101 cutoffs. The page lets people pick their group by hand.
- Not used: BPM's address and city aliases (`aliases.json`), its childcare participation and setting-mix factors (inactive in its calculator), and its fixed-versus-flexible sliders.

### Vintages

BLS CE 2025 (released 2026-10-29). BEA RPP 2024. HUD FMR FY2027. DOL NDCP 2022, carried to 2026 with the BLS day-care price index. BLS CPI September 2026. Refresh by re-running BPM's extractor against a new capture of their tool and copying the JSON files.

## Healthcare prices by area (plan year 2027)

The healthcare-by-area feature prices the marketplace plan you buy before Medicare for where you live. Its tables and its price formulas come from the **Healthcare Costs Estimator v3.6.2** by **BiggerPockets Money** (<https://biggerpocketsmoney.com/healthcarecosts/>, captured 2026-11-25). We use the estimator's method as published and thank BiggerPockets Money for it.

The tables behind the estimator are public government data. They are shipped in `retirement_sim/data/healthcare/2027/` (about 155 KB):

| File | What it holds | Original source |
|---|---|---|
| `rating_areas_ffe.json` | Benchmark Silver prices at ages 21, 30, 40, 50, 60 and 64, a child price and the lowest Bronze price, for 342 rating areas in 29 states on the federal exchange | CMS 2027 Rate PUF and Plan Attributes PUF (posted October 2026) |
| `sbe_benchmarks.json` | The same for 22 state-exchange states and DC, as statewide averages, with New York and Vermont family tiers | KFF 2027 marketplace average benchmark premiums |
| `ca_pricing_groups.json` | 46 California price groups in 19 regions | Covered California 2027 QHP Individual Product Prices (2026-08-18) |
| `age_factors.json`, `age_curves.json` | The federal age curve and the state curves filed by UT, AL, MS, DC, MA, MN and OR | CMS Market Rating Reforms; 2027 Rate PUF |
| `zipra_encoded.json`, `zip3_prefixes.json` | ZIP code to rating area (base-36 ranges, decoded in `healthcare_data.py`) and ZIP prefix to state | HUD-USPS ZIP-County crosswalk (June 2026) joined to the CMS 2027 county-to-area map |
| `ptc_table.json` | The premium tax credit table: percent of income expected toward the benchmark plan | IRS Rev. Proc. 2026-26 |
| `fpl_2026.json` | Poverty guidelines (the 2026 guidelines set 2027 credits) | HHS ASPE |
| `oop_curve.json` | Out-of-pocket cost by age, the Bronze multiplier (1.30) and the 2027 maximum | Planning estimates informed by AHRQ MEPS, adjusted upward by BiggerPockets Money; ACA maximums from 45 CFR 156.130 |
| `state_names.json` | State codes and names | |

Not shipped (not needed): the one-row-per-ZIP and ZIP-range crosswalks (2.8 MB; the encoded file holds the same ranges), Medicaid and CHIP limits, state credits, cost-sharing reductions and the location search index.

### How the model uses it

- **Price at an age:** the state's filed age curve where one exists, otherwise the federal curve with the filed prices interpolated in federal-factor space (linear in age would overprice young adults by up to 5.6%). New York and Vermont use one community rate times a family-tier multiple. Children: only the three oldest under 21 are charged (45 CFR 147.102(c)), at the child age factors, and 21 to 25 at adult prices.
- **Plan:** Benchmark Silver (default) or the lowest-cost Bronze, priced through the area's Bronze-to-Silver ratio. The credit always follows Silver.
- **Credit:** benchmark Silver less income times the applicable percentage, capped at the plan's price, and none at or above 400% of the poverty line. Income is the plan's own income each simulated year.
- **Out-of-pocket:** per person by age from the curve, Bronze times 1.30.
- **Growth:** pre-Medicare premiums grow 6.0% a year nominal for every plan, from the owner's validated assumptions file (3.25% a year after the model's 2.75% inflation). The full price grows before the credit. Medicare, long-term care and out-of-pocket costs keep the 4.5% healthcare rate.

### Limits and open points

- The 2027 prices are applied from today (2026) on, as today's dollars. The model does not take one year off for the gap between the 2027 plan year and now.
- Prices are for a rating area, not a county. The estimator reports the area figure equals the county's own benchmark in 68% of federal-exchange counties and is never above it.
- Statewide averages weight rating areas by plan count, an enrollment proxy. They sit within about 1 to 3% (median) of KFF's own averages, but up to 10 to 12% off in SD, ND and AZ.
- The pediatric dental add-on, state premium credits, Medicaid and CHIP, cost-sharing reductions and maximum-out-of-pocket years are not modeled.
- The credit table is held fixed in every future year. The law re-indexes it each year, so later-year credits run slightly generous.
- The Alabama case (rating area 1, two adults 35, children 5 and 3, income $80,000: Silver $2,134.11 a month, Bronze $1,287.61, credit $18,909.16 a year, out-of-pocket $3,200) is a test (`tests/test_healthcare_area.py`). The estimator's own checks recompute it from the same tables; no live example exists to compare to.
- **San Diego.** The data prices ZIP 92101 (price group 19) at $561.13 a month for the benchmark Silver plan at age 40. That is below the app's earlier $650 and below California's statewide $633. Group 19 covers the whole San Diego metro. The $650 figure matches groups 19d ($651.58) and 19f ($650.37), which the crosswalk gives to only four remote ZIP codes (91934, 92004, 92066, 92070). The statewide $633 is a KFF enrollment-weighted figure across California. We could not check group 19 against Covered California's own files, which are not in this package.
- The shipped data is plan year 2027. When the 2028 files appear, add a `2028/` folder and point `healthcare_data.YEAR` at it.
