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
