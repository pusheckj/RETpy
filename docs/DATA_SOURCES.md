# Data sources

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
- **Growth:** pre-Medicare premiums grow 6.0% a year nominal, from the owner's validated assumptions file (3.25% a year after the model's 2.75% inflation). Medicare, long-term care and out-of-pocket costs keep the 4.5% healthcare rate.

### Limits and open points

- Prices are for a rating area, not a county. The estimator reports the area figure equals the county's own benchmark in 68% of federal-exchange counties and is never above it.
- Statewide averages weight rating areas by plan count, an enrollment proxy. They sit within about 1 to 3% (median) of KFF's own averages, but up to 10 to 12% off in SD, ND and AZ.
- The pediatric dental add-on, state premium credits, Medicaid and CHIP, cost-sharing reductions and maximum-out-of-pocket years are not modeled.
- The credit table is held fixed in every future year. The law re-indexes it each year, so later-year credits run slightly generous.
- The Alabama case (rating area 1, two adults 35, children 5 and 3, income $80,000: Silver $2,134.11 a month, Bronze $1,287.61, credit $18,909.16 a year, out-of-pocket $3,200) is a test (`tests/test_healthcare_area.py`). The estimator's own checks recompute it from the same tables; no live example exists to compare to.
- **San Diego.** The data prices ZIP 92101 (price group 19) at $561.13 a month for the benchmark Silver plan at age 40. That is below the app's earlier $650 and below California's statewide $633. Group 19 covers the whole San Diego metro. The $650 figure matches groups 19d ($651.58) and 19f ($650.37), which the crosswalk gives to only four remote ZIP codes (91934, 92004, 92066, 92070). The statewide $633 is a KFF enrollment-weighted figure across California. We could not check group 19 against Covered California's own files, which are not in this package.
- The shipped data is plan year 2027. When the 2028 files appear, add a `2028/` folder and point `healthcare_data.YEAR` at it.
