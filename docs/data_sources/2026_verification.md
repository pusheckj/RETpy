# 2026 tax and cost-of-living verification — retirement planning app

Verified November 14, 2026 against primary sources (IRS, SSA, CMS, HHS/ASPE, FTB, BEA; KFF/Zillow/Numbeo where noted). Tax year 2026, returns filed early 2027. Law as it stands now, including the One Big Beautiful Bill Act (OBBBA).

## 1. Summary

- Standard deductions changed: MFJ 32200, single 16100, HOH 24150 (OBBBA 2025 base, indexed for 2026). The app held 2024 values.
- New OBBBA senior deduction not modeled: 6000 per person age 65+, MAGI phase-out from 75000 single / 150000 MFJ at 6% per person, tax years 2025-2028 only. Add it.
- Federal ordinary brackets and capital-gains thresholds all changed (Rev. Proc. 2025-32). LTCG 0% tops: single 49450, MFJ 98900, HOH 66200.
- California changed throughout: 2026 brackets, standard deduction 5900 single / 11800 MFJ and HOH (California does have one), exemption credits 158 / 316 / 491, a distinct HOH schedule, plus a separate 1% Behavioral Health Services Tax over 1000000 taxable income.
- IRMAA 2026 changed: standard Part B premium 202.90, Part B deductible 283, first tier boundary 109000 single / 218000 MFJ, based on 2024 MAGI.
- ACA 2026: enhanced premium tax credits expired December 31, 2025 and the 400% FPL cliff is back. Applicable percentages run 2.10% to 9.96% (9.96% at 300-400%), not the app's 4% / 6.5% / 9.5%. Benchmark premium is 625, not 650 (KFF, secondary).
- Confirmed unchanged: all 401(k)/IRA/HSA limits including the 11250 super catch-up, Roth IRA phase-outs, Social Security wage base 184500 and both earnings-test limits, FRA 67, child tax credit 2200 / refundable 1700 / floor 2500 with 200000 / 400000 phase-outs, student-loan 2500 with its phase-outs, and the unindexed NIIT, Additional Medicare Tax, and Social Security taxation thresholds.
- Poverty guidelines: the app's 15650 first person / 5500 additional is correct for 2026 marketplace coverage (it uses the 2025 guidelines). The 2026 guidelines (15960 / 5680) apply to 2027 coverage.
- Could not fully confirm from primary text: the HSA catch-up and the child-tax-credit floor and phase-out wording rest on statute-text mirrors (amounts corroborated; flagged in the YAML). California 2026 exemption-credit phase-out thresholds are unpublished; the YAML carries labeled estimates. Recheck both against the December 2026 FTB Form 540 booklet.
- Part B: BEA RPPs are 2024 (latest published). Values are renormalized so each US component equals 1.00 (raw US: goods 99.6, utilities 98.4, other services 100.1). The Bay Area row is a computed population-weighted blend of two BEA metros, not a BEA-published figure.
- State rents are modeled: no state ZORI exists, so rent is mean-of-metro ZORI x 1.172. Metro and US rents are exact single-family ZORI, October 2026, except Honolulu (June 2026 SFR anchor). State prices are September 2026 ZHVI; US and metro prices are October 2026.
- Carry is modeled: new-buyer property tax plus Insurance.com 2026 insurance on a 300000 dwelling. California new buyers pay about 0.0115, not the 0.0070 average-owner rate. Florida carry (0.0422) is driven by insurance. New York City and Washington DC metro carry are multi-jurisdiction estimates.
- Abroad: FX is ECB reference rates, November 13, 2026 (EUR/USD 1.1052, MXN 18.5931 per USD, THB 33.9151 per USD). Abroad goods/services/utilities are Numbeo-based estimates, not BEA-comparable, and health ratios use roughly age-40 premiums that understate costs at 60+. Lisbon price is the municipality (Greater Lisbon about 400900); Merida price is a house (90 sqm apartment about 194100).
- Legislative watch: the House passed a 3-year ACA enhanced-credit extension in January 2026 but the Senate had not approved it as of November 2026, so model current law (expired) and recheck. An OBBBA change removing repayment caps on excess advance premium tax credits after 2025 was flagged in secondary reporting but not verified here; do not model it from this report alone.

## 2. Part A data

```yaml
part_a:
  - key: limit_401k
    app_value: 24500
    verified_value: 24500
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/newsroom/401k-limit-increases-to-24500-for-2026-ira-limit-increases-to-7500"
    quote: "is increased to $24,500, up from $23,500 for 2025"
    notes: "Also in IRS Notice 2025-67, section 402(g)(1). Applies to 401(k), 403(b), governmental 457, and TSP."
  - key: limit_401k_catchup
    app_value: 8000
    verified_value: 8000
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/pub/irs-drop/n-25-67.pdf"
    quote: "that generally applies for individuals aged 50 or over is increased from $7,500 to $8,000"
    notes: "Section 414(v)(2)(B)(i) catch-up for applicable employer plans, ages 50+."
  - key: limit_401k_supercatchup
    app_value: 11250
    verified_value: 11250
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/newsroom/401k-limit-increases-to-24500-for-2026-ira-limit-increases-to-7500"
    quote: "For 2026, this higher catch-up contribution limit remains $11,250 instead of the $8,000 noted above."
    notes: "Ages 60, 61, 62, or 63 in 2026 (SECURE 2.0 section 109). It did not rise even though the regular catch-up rose to 8000."
  - key: limit_415c
    app_value: 72000
    verified_value: 72000
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/pub/irs-drop/n-25-67.pdf"
    quote: "The limitation for defined contribution plans under section 415(c)(1)(A) is increased in 2026 from $70,000 to $72,000."
    notes: "Total additions limit. The 25 percent of compensation limit under section 415(c)(1)(B) still applies separately."
  - key: limit_ira
    app_value: 7500
    verified_value: 7500
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/newsroom/401k-limit-increases-to-24500-for-2026-ira-limit-increases-to-7500"
    quote: "The limit on annual contributions to an IRA is increased to $7,500 from $7,000."
    notes: "Section 219(b)(5)(A). Applies to traditional and Roth IRA contributions combined."
  - key: limit_ira_catchup
    app_value: 1100
    verified_value: 1100
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/pub/irs-drop/n-25-67.pdf"
    quote: "for individuals who have attained age 50 before the close of the taxable year is increased from $1,000 to $1,100"
    notes: "First increase from the long-standing 1000; now indexed under SECURE 2.0 section 108."
  - key: limit_hsa_self
    app_value: 4400
    verified_value: 4400
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/irb/2025-21_IRB"
    quote: "For calendar year 2026, the annual limitation on deductions under § 223(b)(2)(A) for an individual with self-only coverage under a high deductible health plan is $4,400."
    notes: "Rev. Proc. 2025-19, Internal Revenue Bulletin 2025-21."
  - key: limit_hsa_family
    app_value: 8750
    verified_value: 8750
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/irb/2025-21_IRB"
    quote: "For calendar year 2026, the annual limitation on deductions under § 223(b)(2)(B) for an individual with family coverage under a high deductible health plan is $8,750."
    notes: "Rev. Proc. 2025-19."
  - key: limit_hsa_catchup
    app_value: 1000
    verified_value: 1000
    status: confirmed
    tax_year: 2026
    source_url: "https://law.lawstack.com/usc/26/223/"
    quote: "2009 and thereafter $1,000."
    notes: "26 U.S.C. section 223(b)(3)(B) table; fixed by statute, not indexed, for age 55+. Rev. Proc. 2025-19 does not restate it. Provenance caveat: statute text via a mirror, not uscode.house.gov directly; IRS Publication 969 states the limit is increased by 1000 at age 55+."
  - key: roth_catchup_wage_threshold
    app_value: 150000
    verified_value: 150000
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/pub/irs-drop/n-25-67.pdf"
    quote: "is increased from $145,000 to $150,000"
    notes: "The threshold is for 2025 wages and determines whether 2026 catch-up contributions must be designated Roth: 2025 FICA (section 3121(a)) wages above 150000 trigger the Roth requirement. Notice 2025-67, section 414(v)(7)(A)."
  - key: roth_phaseout_single
    app_value: [153000, 168000]
    verified_value: [153000, 168000]
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/newsroom/401k-limit-increases-to-24500-for-2026-ira-limit-increases-to-7500"
    quote: "The income phase-out range for taxpayers making contributions to a Roth IRA is increased to between $153,000 and $168,000 for singles and heads of household"
    notes: "MAGI phase-out, single and head of household. Pair is [low, high]."
  - key: roth_phaseout_mfj
    app_value: [242000, 252000]
    verified_value: [242000, 252000]
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/newsroom/401k-limit-increases-to-24500-for-2026-ira-limit-increases-to-7500"
    quote: "For married couples filing jointly, the income phase-out range is increased to between $242,000 and $252,000, up from between $236,000 and $246,000 for 2025."
    notes: "MAGI phase-out. Pair is [low, high]."
  - key: ss_wage_base
    app_value: 184500
    verified_value: 184500
    status: confirmed
    tax_year: 2026
    source_url: "https://www.ssa.gov/news/en/cola/factsheets/2026.html"
    quote: "Social Security (OASDI only) | $176,100 | $184,500"
    notes: "SSA 2026 COLA Fact Sheet, Maximum Taxable Earnings. Medicare (HI) has no limit."
  - key: ss_earnings_test_under_fra
    app_value: 24480
    verified_value: 24480
    status: confirmed
    tax_year: 2026
    source_url: "https://www.ssa.gov/news/en/cola/factsheets/2026.html"
    quote: "Under full retirement age | $23,400/yr. ($1,950/mo.) | $24,480/yr. ($2,040/mo.)"
    notes: "Monthly limit 2040. One dollar withheld for every 2 dollars of earnings above the limit."
  - key: ss_earnings_test_fra_year
    app_value: 65160
    verified_value: 65160
    status: confirmed
    tax_year: 2026
    source_url: "https://www.ssa.gov/news/en/cola/factsheets/2026.html"
    quote: "The year an individual reaches full retirement age | $62,160/yr. ($5,180/mo.) | $65,160/yr. ($5,430/mo.)"
    notes: "Monthly limit 5430. Applies only to earnings for months before attaining FRA. One dollar withheld for every 3 dollars above the limit. No limit from the month FRA is attained."
  - key: ss_fra_born_1960_plus
    app_value: 67
    verified_value: 67
    status: confirmed
    tax_year: 2026
    source_url: "https://www.ssa.gov/pubs/EN-05-10069.pdf"
    quote: "If you were born January 2, 1960 or later, then your full retirement age for retirement insurance benefits is 67."
    notes: "SSA Publication 05-10069. Edge case: born January 1 is treated as born the previous year, so January 1, 1960 uses the 1959 FRA of 66 and 10 months."
  - key: ctc_per_child
    app_value: 2200
    verified_value: 2200
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/pub/irs-drop/rp-25-32.pdf"
    quote: "For taxable years beginning in 2026, the maximum amount of the credit allowed under § 24(a) is $2,200."
    notes: "Rev. Proc. 2025-32 section 4.05(1). OBBBA set 2200 for 2025, inflation-adjusted thereafter with 100 rounding; it remains 2200 for 2026. Qualifying child must be under 17."
  - key: ctc_refundable_max
    app_value: 1700
    verified_value: 1700
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/pub/irs-drop/rp-25-32.pdf"
    quote: "For taxable years beginning in 2026, the amount used in § 24(d)(1)(A) to determine the amount of the credit under § 24 that may be refundable is $1,700."
    notes: "Rev. Proc. 2025-32 section 4.05(2). Per-child refundable (ACTC) cap."
  - key: ctc_earned_income_floor
    app_value: 2500
    verified_value: 2500
    status: confirmed
    tax_year: 2026
    source_url: "https://m.openjurist.org/26/usc/24"
    quote: 'Subsection (d)(1)(B)(i) shall be applied by substituting "$2,500" for "$3,000".'
    notes: "26 U.S.C. section 24(h)(6). ACTC equals 15 percent of earned income above 2500 (plus the 3+ child Social Security taxes alternative), capped at the refundable max. Provenance caveat: statute text via OpenJurist mirror, not uscode.house.gov directly."
  - key: ctc_phaseout_start_single
    app_value: 200000
    verified_value: 200000
    status: confirmed
    tax_year: 2026
    source_url: "https://m.openjurist.org/26/usc/24"
    quote: "the threshold amount shall be $400,000 in the case of a joint return ($200,000 in any other case)."
    notes: "26 U.S.C. section 24(h)(3). Any other case covers single, head of household, and married filing separately. Reduction is 50 per 1000 (or fraction) of MAGI over the threshold. Not indexed. Mirror provenance as above."
  - key: ctc_phaseout_start_mfj
    app_value: 400000
    verified_value: 400000
    status: confirmed
    tax_year: 2026
    source_url: "https://m.openjurist.org/26/usc/24"
    quote: "the threshold amount shall be $400,000 in the case of a joint return ($200,000 in any other case)."
    notes: "26 U.S.C. section 24(h)(3). Reduction 50 per 1000 of MAGI over the threshold. Not indexed. Mirror provenance as above."
  - key: student_loan_interest_max
    app_value: 2500
    verified_value: 2500
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/pub/irs-drop/rp-25-32.pdf"
    quote: "the $2,500 maximum deduction for interest paid on qualified education loans under § 221 begins to phase out"
    notes: "Rev. Proc. 2025-32 section 4.29. The 2500 cap is statutory and unindexed."
  - key: student_loan_phaseout_single
    app_value: [85000, 100000]
    verified_value: [85000, 100000]
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/pub/irs-drop/rp-25-32.pdf"
    quote: "with modified adjusted gross income in excess of $85,000 ($175,000 for joint returns)"
    notes: "Rev. Proc. 2025-32 section 4.29. Same section: completely phased out at 100000 or more (205000 or more joint). Pair is [low, high]."
  - key: student_loan_phaseout_mfj
    app_value: [175000, 205000]
    verified_value: [175000, 205000]
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/pub/irs-drop/rp-25-32.pdf"
    quote: "with modified adjusted gross income in excess of $85,000 ($175,000 for joint returns)"
    notes: "Rev. Proc. 2025-32 section 4.29. Same section: completely phased out at 205000 or more joint. Pair is [low, high]."
  - key: std_deduction_mfj
    app_value: 29200
    verified_value: 32200
    status: changed
    tax_year: 2026
    source_url: "https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2026-including-amendments-from-the-one-big-beautiful-bill"
    quote: "For tax year 2026, the standard deduction increases to $32,200 for married couples filing jointly."
    notes: "Corroborated by Rev. Proc. 2025-32 section 4.14. OBBBA set the 2025 base at 31500; 2026 is the indexed figure. App held the 2024 value."
  - key: std_deduction_single
    app_value: 14600
    verified_value: 16100
    status: changed
    tax_year: 2026
    source_url: "https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2026-including-amendments-from-the-one-big-beautiful-bill"
    quote: "For single taxpayers and married individuals filing separately, the standard deduction rises to $16,100 for tax year 2026"
    notes: "Corroborated by Rev. Proc. 2025-32 section 4.14. OBBBA 2025 base was 15750. Same amount applies to married filing separately. App held the 2024 value."
  - key: std_deduction_hoh
    app_value: 21900
    verified_value: 24150
    status: changed
    tax_year: 2026
    source_url: "https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2026-including-amendments-from-the-one-big-beautiful-bill"
    quote: "for heads of households, the standard deduction will be $24,150."
    notes: "Corroborated by Rev. Proc. 2025-32 section 4.14. OBBBA 2025 base was 23625. App held the 2024 value."
  - key: senior_extra_deduction
    app_value: "not modeled"
    verified_value:
      amount_per_person: 6000
      phaseout_start_single: 75000
      phaseout_start_mfj: 150000
      phaseout_rate_per_person: 0.06
      fully_phased_out_single: 175000
      fully_phased_out_mfj: 250000
      years: [2025, 2026, 2027, 2028]
      per_eligible_spouse: true
      ssn_required: true
      married_must_file_jointly: true
    status: changed
    tax_year: 2026
    source_url: "https://uscode.house.gov/us/usc/119-120/t26/s151/"
    quote: "there shall be allowed a deduction in an amount equal to $6,000 for each qualified individual with respect to the taxpayer"
    notes: "26 U.S.C. section 151(d)(5)(C), added by OBBBA section 70103. Phase-out: reduced by 6 percent of MAGI over 75000 (150000 joint), applied per qualified individual, so a two-spouse couple's combined deduction falls at 12 percent of joint MAGI above 150000. Fully-phased-out figures are derived arithmetic (6000 / 0.06). Age 65 must be attained before the close of the taxable year. Available whether itemizing or not, in addition to the existing age-65 additional standard deduction. Claimed on Schedule 1-A."
  - key: federal_brackets_2026
    app_value: "2024 brackets held flat"
    verified_value: {single: [[12400, 0.10], [50400, 0.12], [105700, 0.22], [201775, 0.24], [256225, 0.32], [640600, 0.35], [null, 0.37]], mfj: [[24800, 0.10], [100800, 0.12], [211400, 0.22], [403550, 0.24], [512450, 0.32], [768700, 0.35], [null, 0.37]], hoh: [[17700, 0.10], [67450, 0.12], [105700, 0.22], [201750, 0.24], [256200, 0.32], [640600, 0.35], [null, 0.37]]}
    status: changed
    tax_year: 2026
    source_url: "https://www.irs.gov/pub/irs-drop/rp-25-32.pdf"
    quote: "Not over $12,400 10% of the taxable income"
    notes: "Each pair is [band upper bound, rate]; null is the top band. All bands transcribed from Rev. Proc. 2025-32 section 4.01, Tables 1-3, and cross-checked against IR-2025-103 for single/MFJ. Do not copy single values into HOH: HOH 24% upper bound is 201750 and 32% upper bound is 256200, differing from single. MFS uses single thresholds except the 35% band ends at 384350."
  - key: ltcg_brackets_2026
    app_value: "2024 values"
    verified_value: {single: [49450, 545500], mfj: [98900, 613700], hoh: [66200, 579600]}
    status: changed
    tax_year: 2026
    source_url: "https://www.irs.gov/pub/irs-drop/rp-25-32.pdf"
    quote: "Married Individuals Filing Joint Returns and $98,900 $613,700"
    notes: "Rev. Proc. 2025-32 section 4.03, maximum zero rate and maximum 15% rate amounts. Each pair is [0% upper bound, 15% upper bound]; 20% applies above the second figure. Single is the table's All Other Individuals row. MFS: [49450, 306850]. Estates/trusts: [3300, 16250]."
  - key: niit_thresholds
    app_value: {single: 200000, mfj: 250000}
    verified_value: {single_hoh: 200000, mfj: 250000, mfs: 125000}
    status: confirmed
    tax_year: 2026
    source_url: "https://uscode.house.gov/us/usc/119-134/t26/s1411/"
    quote: "(1) in the case of a taxpayer making a joint return under section 6013 or a surviving spouse (as defined in section 2(a)), $250,000,"
    notes: "26 U.S.C. section 1411(b). Other cases: 200000. MFS is one-half of joint. Rate 3.8% on the lesser of net investment income or MAGI over the threshold. Not indexed."
  - key: addl_medicare_thresholds
    app_value: {single: 200000, mfj: 250000}
    verified_value: {liability_single_hoh: 200000, liability_mfj: 250000, liability_mfs: 125000, withholding_all: 200000, rate: 0.009}
    status: confirmed
    tax_year: 2026
    source_url: "https://www.irs.gov/taxtopics/tc560"
    quote: "$250,000 for married filing jointly; $125,000 for married filing separately; and $200,000 for all other taxpayers."
    notes: "IRS Topic 560. Liability thresholds differ by filing status (0.9% on Medicare wages, self-employment income, and RRTA compensation above the threshold). Employer withholding threshold is 200000 for everyone regardless of filing status. Not indexed."
  - key: ss_taxation_thresholds
    app_value: {single: [25000, 34000], mfj: [32000, 44000]}
    verified_value: {single_hoh: [25000, 34000], mfj: [32000, 44000], mfs_lived_with_spouse: [0, 0], mfs_lived_apart_all_year: [25000, 34000]}
    status: confirmed
    tax_year: 2026
    source_url: "https://uscode.house.gov/us/usc/119-124/t26/s86/"
    quote: "(A) except as otherwise provided in this paragraph, $25,000, (B) $32,000 in the case of a joint return"
    notes: "26 U.S.C. section 86(c) base amounts; adjusted base amounts are 34000 / 44000. Provisional income is MAGI without regard to section 86 (AGI plus tax-exempt interest) plus one-half of benefits. Up to 50% of benefits taxable above the base amount; up to 85% above the adjusted base amount. Not indexed."
  - key: irmaa_2026
    app_value: "2024-era values"
    verified_value:
      standard_part_b_premium: 202.90
      part_b_deductible: 283
      magi_year: 2024
      single_boundaries: [109000, 137000, 171000, 205000, 500000]
      mfj_boundaries: [218000, 274000, 342000, 410000, 750000]
      part_b_surcharge_by_tier: [0, 81.20, 202.90, 324.60, 446.30, 487.00]
      part_b_total_by_tier: [202.90, 284.10, 405.80, 527.50, 649.20, 689.90]
      part_d_surcharge_by_tier: [0, 14.50, 37.50, 60.40, 83.30, 91.00]
    status: changed
    tax_year: 2026
    source_url: "https://www.cms.gov/newsroom/fact-sheets/2026-medicare-parts-b-premiums-deductibles"
    quote: "The standard monthly premium for Medicare Part B enrollees will be $202.90 for 2026, an increase of $17.90 from $185.00 in 2025."
    notes: "CMS fact sheet, November 14, 2025. Tier 0 is MAGI at or below the first boundary; each later tier is MAGI above the previous boundary up to the next; the top tier is MAGI at or above 500000 single / 750000 MFJ. Part B total is standard premium plus surcharge. Part D surcharge is added to the beneficiary's own Part D premium. Amounts monthly, per person. MAGI is AGI plus tax-exempt interest, from the 2024 return. Annual Part B deductible 283. Married filing separately has separate tiers; see the CMS fact sheet."
  - key: fpl_2026
    app_value: {first_person: 15650, each_additional: 5500}
    verified_value: {first_person: 15650, each_additional: 5500, guideline_year: 2025, coverage_year: 2026}
    status: confirmed
    tax_year: 2026
    source_url: "https://aspe.hhs.gov/topics/poverty-economic-mobility/poverty-guidelines/prior-hhs-poverty-guidelines-federal-register-references"
    quote: "| 2025 | $15,650 | $5,500 | ($32,150) |"
    notes: "2026 marketplace coverage uses the 2025 guidelines, so the app values are correct for that use. The 2026 guidelines (15960 first person, 5680 each additional) apply to 2027 marketplace coverage. Figures are for the 48 contiguous states plus DC."
  - key: aca_2026_subsidy_rules
    app_value: {cliff_fpl: 400, cap_at_150: 0.04, cap_at_200: 0.065, cap_300_400: 0.095}
    verified_value:
      enhanced_credits_expired: true
      cliff_at_400_pct: true
      required_contribution: 0.0996
      applicable_percentages:
        - {fpl_low: 0, fpl_high: 133, initial: 0.0210, final: 0.0210}
        - {fpl_low: 133, fpl_high: 150, initial: 0.0314, final: 0.0419}
        - {fpl_low: 150, fpl_high: 200, initial: 0.0419, final: 0.0660}
        - {fpl_low: 200, fpl_high: 250, initial: 0.0660, final: 0.0844}
        - {fpl_low: 250, fpl_high: 300, initial: 0.0844, final: 0.0996}
        - {fpl_low: 300, fpl_high: 400, initial: 0.0996, final: 0.0996}
    status: changed
    tax_year: 2026
    source_url: "https://www.irs.gov/pub/irs-drop/rp-25-25.pdf"
    quote: "Less than 133% 2.10% 2.10%"
    notes: "Rev. Proc. 2025-25 section 3.01 table; section 3.02 sets the required contribution percentage at 9.96%. The applicable percentage rises linearly from initial to final across each FPL band. Below 100% FPL generally no credit. Enhanced credits expired December 31, 2025; no extension was enacted as of November 2026 (House passed a 3-year extension January 8, 2026; Senate had not approved it). No premium tax credit above 400% FPL for 2026. Replace the app caps with 4.19% at 150%, 6.60% at 200%, 9.96% at 300-400%."
  - key: aca_benchmark_premium
    app_value: 650
    verified_value: 625
    status: changed
    tax_year: 2026
    source_url: "https://www.kff.org/affordable-care-act/state-indicator/marketplace-average-benchmark-premiums/"
    quote: "| United States | 625 |"
    notes: "SECONDARY source: KFF analysis of CMS plan data; no single CMS-published national-average benchmark figure was found. Average monthly premium for the second-lowest-cost silver (benchmark) plan for a 40-year-old, before premium tax credits, county premiums weighted by plan selections. 2025 value was 497."
  - key: ca_brackets_2026
    app_value: "2024 brackets, standard deduction, and exemption credits held flat"
    verified_value:
      single: [[11456, 0.01], [27157, 0.02], [42861, 0.04], [59498, 0.06], [75197, 0.08], [384109, 0.093], [460927, 0.103], [768213, 0.113], [null, 0.123]]
      mfj: [[22912, 0.01], [54314, 0.02], [85722, 0.04], [118996, 0.06], [150394, 0.08], [768218, 0.093], [921854, 0.103], [1536426, 0.113], [null, 0.123]]
      hoh: [[22927, 0.01], [54316, 0.02], [70018, 0.04], [86654, 0.06], [102356, 0.08], [522385, 0.093], [626864, 0.103], [1044771, 0.113], [null, 0.123]]
      standard_deduction: {single: 5900, mfs: 5900, mfj: 11800, hoh: 11800, surviving_spouse: 11800}
      exemption_credits: {personal_single_separate_hoh_each: 158, personal_mfj_total: 316, dependent_each: 491, senior_each: 158, blind_each: 158}
      exemption_credit_phaseout_2025_verified: {single_mfs: 252203, mfj: 504411, hoh: 378310}
      exemption_credit_phaseout_2026_estimated: {single_mfs: 260778, mfj: 521561, hoh: 391173}
      phaseout_mechanism: "reduce each credit by 6 per 2500 of federal AGI over threshold, 1250 if MFS, rounded up"
      behavioral_health_services_tax: {threshold_taxable_income: 1000000, rate: 0.01}
    status: changed
    tax_year: 2026
    source_url: "https://www.ftb.ca.gov/about-ftb/newsroom/tax-news/2026/10.html"
    quote: "768,213 | & OVER | 74,675.27 + 12.30% of the amount over 768,213"
    notes: "FTB Tax News, October 2026 (3.4% CCPI). Brackets apply to Form 540 taxable income, after the standard or itemized deduction. California HAS a standard deduction (5900 / 11800) in addition to exemption credits. HOH is a distinct schedule, not MFJ-like. Senior/blind 158 each is inferred from the 2025 Form 540 structure (personal, blind, and senior each 153); recheck on the December 2026 Form 540. 2026 phase-out thresholds are unpublished; estimates are 2025 thresholds x 1.034. BHST is a separate 1% on taxable income over 1000000, all statuses, not a 10th bracket."
```

## 3. Part B data

```csv
code,name,kind,goods,services,utilities,health,price,rent,carry,data_year,source_notes
US,US average,us,1.0000,1.0000,1.0000,1.0000,364812,2243,0.0201,2026,"BEA RPP 2024 renormalized US=1.00; KFF 2026 benchmark 625; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 1913); carry: new-buyer tax 0.0105 + insurance 0.0096 (Insurance.com 2026, 300000 dwelling)."
AL,Alabama,state,0.9679,0.9660,0.8598,1.0320,238614,1574,0.0161,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 645; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1343 x 1.172; carry: tax 0.0037 + insurance 0.0124."
AK,Alaska,state,1.0673,1.0210,1.2093,1.6512,397932,2411,0.0144,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 1032; ZHVI Sep 2026; rent modeled: mean-metro ZORI 2057 x 1.172; carry: tax 0.0094 + insurance 0.0050."
AZ,Arizona,state,0.9578,1.0270,0.9380,0.8512,416733,1962,0.0128,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 532; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1674 x 1.172; carry: tax 0.0048 (LPV travels with parcel; new construction higher) + insurance 0.0080."
AR,Arkansas,state,0.9398,0.9520,0.7591,1.2384,224158,1345,0.0174,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 774; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1148 x 1.172; carry: tax 0.0067 (modeled reset uplift) + insurance 0.0107."
CA,California,state,1.0653,1.0250,1.6148,0.9120,761538,2721,0.0170,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 570; ZHVI Sep 2026; rent modeled: mean-metro ZORI 2322 x 1.172 (understates population-weighted rent); carry: new-buyer Prop 13 tax 0.0115 + insurance 0.0055."
CO,Colorado,state,0.9910,0.9950,0.8638,0.8912,529013,2447,0.0234,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 557; ZHVI Sep 2026; rent modeled: mean-metro ZORI 2088 x 1.172; carry: tax 0.0050 + insurance 0.0184."
CT,Connecticut,state,0.9769,1.0260,1.4888,1.3920,447319,2555,0.0225,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 870; ZHVI Sep 2026; rent modeled: mean-metro ZORI 2180 x 1.172; carry: tax 0.0154 + insurance 0.0071."
DE,Delaware,state,0.9659,1.0110,1.0549,1.1056,405061,2181,0.0103,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 691; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1861 x 1.172; carry: tax 0.0054 + insurance 0.0049."
DC,District of Columbia,state,1.0693,1.0290,1.1463,0.9760,567271,2911,0.0125,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 610; ZHVI Sep 2026; rent: exact Zillow city ZORI 2484 x 1.172; carry: tax 0.0073 + insurance 0.0052."
FL,Florida,state,0.9849,1.0120,0.9157,1.0928,375361,2243,0.0422,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 683; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1914 x 1.172; carry: new-buyer tax 0.0140 (Save Our Homes resets) + insurance 0.0282; flood excluded."
GA,Georgia,state,0.9930,0.9720,0.9431,0.9840,329115,1712,0.0156,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 615; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1461 x 1.172; carry: tax 0.0079 + insurance 0.0077."
HI,Hawaii,state,1.1205,1.0280,1.9329,0.8656,832932,3879,0.0055,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 541; ZHVI Sep 2026; rent modeled: mean-metro ZORI 3310 x 1.172; carry: tax 0.0030 + insurance 0.0025 (hurricane wind often separate)."
ID,Idaho,state,0.9669,0.9890,0.7154,0.7840,476754,1861,0.0130,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 490; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1588 x 1.172; carry: tax 0.0050 + insurance 0.0080."
IL,Illinois,state,1.0422,1.0010,0.8638,1.0336,295943,1326,0.0281,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 646; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1131 x 1.172; carry: tax 0.0188 + insurance 0.0093."
IN,Indiana,state,0.9588,0.9900,0.8689,0.7584,257165,1361,0.0172,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 474; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1161 x 1.172; carry: tax 0.0076 + insurance 0.0096."
IA,Iowa,state,0.9408,0.9281,0.8465,0.8016,236623,1335,0.0238,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 501; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1139 x 1.172; carry: tax 0.0133 + insurance 0.0105."
KS,Kansas,state,0.9438,0.9371,0.8984,1.0720,246055,1220,0.0297,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 670; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1041 x 1.172; carry: tax 0.0121 + insurance 0.0176."
KY,Kentucky,state,0.9639,0.9720,0.7652,0.9440,230909,1378,0.0223,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 590; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1176 x 1.172; carry: tax 0.0074 + insurance 0.0149."
LA,Louisiana,state,0.9408,0.9560,0.7266,1.0336,213867,1645,0.0228,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 646; ZHVI Sep 2026; rent modeled: ZORI 1404 x 1.172, least certain state rent (other methods 1277-1500); carry: tax 0.0055 + insurance 0.0173."
ME,Maine,state,0.9759,1.0310,1.3740,1.1344,412002,2019,0.0141,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 709; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1723 x 1.172; carry: tax 0.0098 + insurance 0.0043."
MD,Maryland,state,1.0291,1.0150,1.1270,0.6624,424890,2073,0.0185,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 414; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1769 x 1.172; carry: tax 0.0110 (modeled reset uplift) + insurance 0.0075."
MA,Massachusetts,state,0.9920,1.0280,1.5457,0.7904,655219,2670,0.0170,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 494; ZHVI Sep 2026; rent modeled: mean-metro ZORI 2278 x 1.172; carry: tax 0.0100 + insurance 0.0070."
MI,Michigan,state,0.9639,1.0080,1.0183,0.8368,263760,1582,0.0280,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 523; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1350 x 1.172; carry: new-buyer tax 0.0178 (Proposal A resets) + insurance 0.0102."
MN,Minnesota,state,1.0090,1.0010,0.9228,0.7168,348778,1485,0.0211,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 448; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1267 x 1.172; carry: tax 0.0100 + insurance 0.0111."
MS,Mississippi,state,0.9659,0.9600,0.7967,1.0592,194531,1683,0.0145,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 662; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1436 x 1.172; carry: tax 0.0058 + insurance 0.0087."
MO,Missouri,state,0.9669,0.9510,0.8069,0.9680,265387,1324,0.0215,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 605; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1130 x 1.172; carry: tax 0.0089 + insurance 0.0126."
MT,Montana,state,0.9639,0.9860,0.7348,1.1072,467275,1968,0.0162,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 692; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1679 x 1.172; carry: tax 0.0055 + insurance 0.0107."
NE,Nebraska,state,0.9448,0.9291,0.7683,1.1360,278299,1478,0.0328,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 710; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1261 x 1.172; carry: tax 0.0144 + insurance 0.0184."
NV,Nevada,state,0.9669,0.9860,0.9197,0.7952,440739,2251,0.0113,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 497; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1921 x 1.172; carry: tax 0.0050 + insurance 0.0063."
NH,New Hampshire,state,0.9900,1.0380,1.3587,0.6416,510937,2215,0.0194,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 401; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1890 x 1.172; carry: tax 0.0150 + insurance 0.0044."
NJ,New Jersey,state,1.0753,1.0340,1.1606,0.8720,575123,2404,0.0236,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 545; ZHVI Sep 2026; rent modeled: mean-metro ZORI 2051 x 1.172; carry: tax 0.0188 + insurance 0.0048."
NM,New Mexico,state,0.9649,0.9840,0.7917,0.9968,315812,1856,0.0212,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 623; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1584 x 1.172; carry: tax 0.0095 (modeled reset uplift) + insurance 0.0117."
NY,New York,state,1.0773,1.0400,1.3659,1.3072,524942,1856,0.0191,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 817; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1584 x 1.172 (understates population-weighted rent); carry: tax 0.0130 + insurance 0.0061."
NC,North Carolina,state,0.9699,0.9810,0.9004,1.0208,332159,1754,0.0193,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 638; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1497 x 1.172; carry: tax 0.0066 + insurance 0.0127."
ND,North Dakota,state,0.9608,0.9111,0.7490,0.9120,290657,1348,0.0187,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 570; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1150 x 1.172; carry: tax 0.0092 + insurance 0.0095."
OH,Ohio,state,0.9408,0.9880,0.9736,0.8208,245982,1401,0.0206,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 513; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1195 x 1.172; carry: tax 0.0136 + insurance 0.0070."
OK,Oklahoma,state,0.9418,0.9540,0.7510,0.9664,220801,1354,0.0274,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 604; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1155 x 1.172; carry: tax 0.0095 (modeled reset uplift) + insurance 0.0179."
OR,Oregon,state,1.0572,1.0020,1.0874,0.8688,492753,2029,0.0136,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 543; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1731 x 1.172; carry: tax 0.0081 (Measure 50 MAV travels with parcel; new construction far higher) + insurance 0.0055."
PA,Pennsylvania,state,0.9980,0.9970,1.1108,0.9152,287078,1526,0.0174,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 572; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1302 x 1.172; carry: tax 0.0126 + insurance 0.0048."
RI,Rhode Island,state,0.9759,1.0270,1.4909,0.8096,508507,2539,0.0191,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 506; ZHVI Sep 2026; rent modeled: mean-metro ZORI 2166 x 1.172; carry: tax 0.0112 + insurance 0.0079."
SC,South Carolina,state,0.9669,0.9820,0.8974,0.9024,304319,1794,0.0155,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 564; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1531 x 1.172; carry: tax 0.0059 (modeled reset uplift) + insurance 0.0096."
SD,South Dakota,state,0.9588,0.9181,0.8100,1.0480,317874,1478,0.0225,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 655; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1261 x 1.172; carry: tax 0.0100 + insurance 0.0125."
TN,Tennessee,state,0.9659,0.9500,0.7327,1.1376,330844,1610,0.0159,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 711; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1374 x 1.172; carry: tax 0.0052 + insurance 0.0107."
TX,Texas,state,0.9849,0.9700,0.8892,1.0576,296424,1628,0.0303,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 661; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1389 x 1.172; carry: net tax 0.0150 after 140000 school exemption (MUD/PID suburbs higher) + insurance 0.0153."
UT,Utah,state,0.9679,0.9890,0.7998,1.0240,532920,1964,0.0107,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 640; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1676 x 1.172; carry: tax 0.0048 + insurance 0.0059."
VT,Vermont,state,0.9769,1.0150,1.2785,2.0784,391900,2244,0.0185,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 1299; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1915 x 1.172; carry: tax 0.0151 + insurance 0.0034. Note: VT premiums do not vary by age, so the 40-year-old health ratio understates the 60-year-old advantage."
VA,Virginia,state,1.0080,1.0010,0.9370,0.7280,412252,1818,0.0143,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 455; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1551 x 1.172; carry: tax 0.0078 + insurance 0.0065."
WA,Washington,state,1.0482,1.0380,0.9441,0.9792,587533,2050,0.0134,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 612; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1749 x 1.172 (understates population-weighted rent); carry: tax 0.0075 + insurance 0.0059."
WV,West Virginia,state,0.9689,0.9980,0.9370,1.7168,176576,1341,0.0116,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 1073; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1144 x 1.172; carry: tax 0.0051 + insurance 0.0065."
WI,Wisconsin,state,0.9468,0.9940,0.9136,0.9776,337196,1522,0.0193,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 611; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1299 x 1.172; carry: tax 0.0132 + insurance 0.0061."
WY,Wyoming,state,0.9578,1.0030,0.7967,1.7440,369044,1863,0.0122,2026,"BEA RPP 2024 renormalized; KFF 2026 benchmark 1090; ZHVI Sep 2026; rent modeled: mean-metro ZORI 1590 x 1.172; carry: tax 0.0053 + insurance 0.0069."
M_SFB,San Francisco Bay Area,metro,1.0795,1.0434,1.7060,0.9120,1254980,4362,0.0170,2026,"BEA RPP 2024 COMPUTED: population-weighted blend of San Francisco-Oakland-Fremont (70.05%) and San Jose-Sunnyvale-Santa Clara (29.95%); not BEA-published. Health is CA KFF 570. Price/rent are the same population-weighted blend of Zillow metro ZHVI/SFR ZORI Oct 2026 (all-units 3550); carry: tax 0.0115 + insurance 0.0055."
M_LAX,Los Angeles,metro,1.0703,1.0430,1.6118,0.9120,950752,4417,0.0173,2026,"BEA RPP 2024 Los Angeles-Long Beach-Anaheim renormalized; health is CA KFF 570; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 2913); carry: LA County tax 0.0118 + insurance 0.0055."
M_SAN,San Diego,metro,1.0843,0.9950,1.7703,0.9120,929026,4135,0.0170,2026,"BEA RPP 2024 San Diego-Chula Vista-Carlsbad renormalized; health is CA KFF 570; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 2936); carry: tax 0.0115 + insurance 0.0055."
M_SEA,Seattle,metro,1.0442,1.0669,0.9431,0.9792,711435,3349,0.0134,2026,"BEA RPP 2024 Seattle-Tacoma-Bellevue renormalized; health is WA KFF 612; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 2225); carry: tax 0.0075 + insurance 0.0059."
M_PDX,Portland OR,metro,1.0562,1.0000,1.0874,0.8688,535582,2663,0.0136,2026,"BEA RPP 2024 Portland-Vancouver-Hillsboro renormalized; health is OR KFF 543 (WA side would be 612); ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 1799); carry: existing-home tax 0.0081 + insurance 0.0055 (new construction far higher)."
M_NYC,New York City,metro,1.1074,1.0569,1.2907,1.3072,730894,3490,0.0156,2026,"BEA RPP 2024 New York-Newark-Jersey City renormalized; health is NY KFF 817 (NJ side 545, far cheaper); ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 3450); carry ESTIMATED: tax 0.0095 midpoint + insurance 0.0061."
M_BOS,Boston,metro,1.0010,1.0350,1.5122,0.7904,726271,3498,0.0121,2026,"BEA RPP 2024 Boston-Cambridge-Newton renormalized; health is MA KFF 494; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 2945); carry: Boston tax 0.0051 + insurance 0.0070."
M_WDC,Washington DC,metro,1.0522,1.0220,1.0843,0.9760,568160,3159,0.0151,2026,"BEA RPP 2024 Washington-Arlington-Alexandria renormalized; health is DC KFF 610 (VA 455 and MD 414 suburbs much cheaper; weakest metro health assignment); ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 2379); carry is unweighted mean of DC/VA/MD: tax 0.0087 + insurance 0.0064, use total only."
M_PHL,Philadelphia,metro,0.9719,1.0300,1.1626,0.9152,385629,2260,0.0174,2026,"BEA RPP 2024 Philadelphia-Camden-Wilmington renormalized; health is PA KFF 572; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 1884); carry: tax 0.0126 + insurance 0.0048."
M_DEN,Denver,metro,1.0141,0.9930,0.8933,0.8912,552109,2875,0.0234,2026,"BEA RPP 2024 Denver-Aurora-Centennial renormalized; health is CO KFF 557; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 1884); carry: tax 0.0050 + insurance 0.0184."
M_AUS,Austin,metro,0.9418,0.9610,0.8333,1.0576,410026,2260,0.0303,2026,"BEA RPP 2024 Austin-Round Rock-San Marcos renormalized; health is TX KFF 661; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 1584); carry: net tax 0.0150 + insurance 0.0153."
M_DFW,Dallas–Fort Worth,metro,1.0321,0.9960,0.9217,1.0576,355891,2325,0.0303,2026,"BEA RPP 2024 Dallas-Fort Worth-Arlington renormalized; health is TX KFF 661; ZHVI Oct 2026 (Zillow Dallas row, CBSA 19100); rent is SFR ZORI Oct 2026 (all-units 1647); carry: net tax 0.0150 + insurance 0.0153."
M_HOU,Houston,metro,1.0100,0.9550,0.9685,1.0576,300750,2188,0.0303,2026,"BEA RPP 2024 Houston-Pasadena-The Woodlands renormalized; health is TX KFF 661; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 1622); carry: net tax 0.0150 + insurance 0.0153."
M_CHI,Chicago,metro,1.0773,1.0040,0.8496,1.0336,357746,2509,0.0281,2026,"BEA RPP 2024 Chicago-Naperville-Elgin renormalized; health is IL KFF 646; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 2123); carry: tax 0.0188 + insurance 0.0093."
M_MSP,Minneapolis–St. Paul,metro,1.0351,1.0430,0.9502,0.7168,384858,2465,0.0211,2026,"BEA RPP 2024 Minneapolis-St. Paul-Bloomington renormalized; health is MN KFF 448; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 1733); carry: tax 0.0100 + insurance 0.0111."
M_ATL,Atlanta,metro,1.0080,0.9660,0.9776,0.9840,373053,2247,0.0156,2026,"BEA RPP 2024 Atlanta-Sandy Springs-Roswell renormalized; health is GA KFF 615; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 1828); carry: tax 0.0079 + insurance 0.0077."
M_MIA,Miami,metro,1.0402,1.0899,0.9878,1.0928,480084,3407,0.0450,2026,"BEA RPP 2024 Miami-Fort Lauderdale-West Palm Beach renormalized; health is FL KFF 683; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 2652); carry: Miami new-buyer tax 0.0168 + insurance 0.0282 (Miami MSA insurance higher, carry up to about 0.0508)."
M_PHX,Phoenix,metro,0.9538,1.0390,0.9482,0.8512,438736,2290,0.0128,2026,"BEA RPP 2024 Phoenix-Mesa-Chandler renormalized; health is AZ KFF 532; ZHVI Oct 2026; rent is SFR ZORI Oct 2026 (all-units 1717); carry: existing-home tax 0.0048 + insurance 0.0080 (new builds higher)."
M_HNL,Honolulu,metro,1.1205,1.0280,1.9035,0.8656,855973,3630,0.0055,2026,"BEA RPP 2024 Urban Honolulu renormalized; health is HI KFF 541; price/rent Sep 2026 via second-hand Zillow CSV mirrors (all-units 3015); rent is a June 2026 SFR anchor, re-pull exact Oct 2026 SFR ZORI; carry: tax 0.0030 + insurance 0.0025."
X_PT,Portugal (Lisbon area),abroad,0.615,0.738,0.70,0.1327,621500,2403,0.0022,2026,"ESTIMATED, Numbeo Nov 2026 (not BEA): goods = groceries index 47.0 / US 76.4; services = mean of COL ratio 51.7/69.7 and restaurant ratio 55.1/75 est. US; utilities EST from Numbeo basic-utilities bill vs US. FX ECB 13 Nov 2026 EUR/USD 1.1052. Price: Lisbon municipality Idealista Oct 2026 6248 EUR/sqm x 90 sqm (Greater Lisbon about 400900); rent: Numbeo 3-bed midpoint; health: local private 995/yr vs US 7500; carry: IMI 0.30% x VPT at 60% of price + insurance."
X_IT,Italy (Bologna),abroad,0.794,0.923,1.05,0.2947,381400,1843,0.0005,2026,"ESTIMATED, Numbeo Nov 2026 (not BEA): goods = groceries 60.7 / US 76.4; services = mean of COL ratio 62.0/69.7 and restaurant ratio 71.7/75 est. US; utilities EST (Numbeo basic utilities 212.70 EUR/mo, expensive gas heating). FX ECB 13 Nov 2026 EUR/USD 1.1052. Price: Immobiliare.it Aug 2026 3834 EUR/sqm x 90 sqm; rent: Numbeo 3-bed midpoint; health: voluntary SSN 2210/yr vs US 7500; carry: resident main-home IMU 0 + insurance (non-resident about 0.0042)."
X_ES,Spain (Valencia),abroad,0.577,0.758,0.75,0.2121,346300,2001,0.0044,2026,"ESTIMATED, Numbeo Nov 2026 (not BEA): goods = groceries 44.1 / US 76.4; services = mean of COL ratio 49.4/69.7 and restaurant ratio 60.6/75 est. US; utilities EST from Numbeo basic-utilities bill vs US. FX ECB 13 Nov 2026 EUR/USD 1.1052. Price: Idealista Oct 2026 3482 EUR/sqm x 90 sqm; rent: Numbeo 3-bed midpoint; health: private 1591/yr vs US 7500; carry: IBI 0.5784% x cadastral at 60% + insurance (conflicting secondary IBI 0.72%/1.07%, verify ordinance)."
X_MX,Mexico (Merida),abroad,0.570,0.620,0.45,0.3600,289400,1103,0.0033,2026,"ESTIMATED, Numbeo Nov 2026 (not BEA): goods = groceries 43.5 / US 76.4; services = mean of COL ratio 42.3/69.7 and restaurant ratio 47.5/75 est. US; utilities EST (electricity/water with AC). FX ECB-derived 13 Nov 2026 MXN 18.5931/USD. Price: median house MXN 5380000 (90 sqm apartment about 194100); rent: Numbeo 3-bed midpoint; health: local private 2700/yr vs US 7500; carry: predial + insurance excl. fideicomiso (incl. trust about 0.0054; applicability unresolved)."
X_TH,Thailand (Chiang Mai),abroad,0.490,0.342,0.55,0.1180,181200,851,0.0080,2026,"ESTIMATED, Numbeo Nov 2026 (not BEA): goods = groceries 37.4 / US 76.4; services = mean of COL ratio 30.7/69.7 and restaurant ratio 18.3/75 est. US (Numbeo indices volatile: 2026 annual COL 34.8); utilities EST. FX ECB-derived 13 Nov 2026 THB 33.9151/USD. Price: Numbeo blended 68277 THB/sqm x 90 sqm, condo freehold only (49% quota); rent: Numbeo 3-bed midpoint; health: expat inpatient plan 885/yr EST vs US 7500; carry: land/building tax + condo common fee (tax-only 0.0001)."
```
