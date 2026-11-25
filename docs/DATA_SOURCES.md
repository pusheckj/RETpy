# Data sources

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
- **Childcare age weights** (`AGE_WEIGHT` in `constants.json`): how a household's children spread over infant, toddler, preschool and school-age, by the parent's age band and household size. With full-time paid care the school-age weight moves to preschool.
- **Childcare scaling.** A state's price is scaled by the area's BEA Rents index, kept between 0.65 and 1.70, when you pick an area with no county figure. A county median is used as it is.
- **Housing from HUD rent.** With an area, housing is the HUD Fair Market Rent for BPM's bedroom count, times a rent-by-income factor (0.75, 0.85, 1.00, 1.25, 1.25). Utilities keep only the phone and internet share.
- **Price index for each group**: goods for food, transport and clothing; other services for health and entertainment; all items for other and utilities.
- **CPI carry**: 1.172 from 2022 to 2025 and 1.0299 from 2025 to 2026 for childcare, and the group factors in `cpi_factors.json`.

### What this app changes

- BEA price levels are **renormalized** so each US component is exactly 1.00, the way `ui/utils/place_costs.py` does (raw BEA US goods is 99.6 and other services 100.1). BPM reads them raw. The tests reproduce BPM's worked examples with the raw reading.
- The survey's **Pensions** line (payroll tax, retirement contributions, life insurance) is left out. The planner models those elsewhere.
- Groups are folded into the app's categories (housing with utilities, clothing with Fun and discretionary, your partner's spending with Other), and the tab compares your plan's monthly inputs, or your statement averages.
- A state with no area picked uses the state's own childcare price as it is. BPM's tool always works from an area, and scales a state price by that area's rents.
- **Income-group cutoffs are rough estimates.** BPM asks you to pick the group and ships no dollar cutoffs. Only the first, $32,623, is in its data. The others (`QUINTILE_UPPER` in `ui/utils/budget_compare.py`) are round numbers, not published figures. Replace them with the BLS CE Table 1101 cutoffs. The page lets people pick their group by hand.
- Not used: BPM's address and city aliases (`aliases.json`), its childcare participation and setting-mix factors (inactive in its calculator), and its fixed-versus-flexible sliders.

### Vintages

BLS CE 2025 (released 2026-10-29). BEA RPP 2024. HUD FMR FY2027. DOL NDCP 2022, carried to 2026 with the BLS day-care price index. BLS CPI September 2026. Refresh by re-running BPM's extractor against a new capture of their tool and copying the JSON files.
