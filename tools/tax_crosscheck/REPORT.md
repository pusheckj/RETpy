# Tax cross-check report: RETpy vs BiggerPockets Money tax engine

Generated 2026-11-25 by `tools/tax_crosscheck/crosscheck.py`. Oracle: BiggerPockets Money Income Tax Projection Calculator v1.11.2 (2026 tax year). Fixtures: 503. Tolerance: to the cent.

Buckets: **RETpy bug** (RETpy is wrong or inconsistent), **BPM simplification** (BPM does not model something RETpy does; RETpy wins), **modeling difference** (both are approximations; the choice is documented). Each state result is compared with RETpy's app-only rules switched off (personal exemptions and credits, retirement exclusions, capital-gains exclusion, taxed Social Security), so any remaining gap is a table or mechanics gap.

## 1. BPM's own default example

BPM engine reproduces its verified figures: **yes**. RETpy's tables reproduce the federal, state, credit and payroll parts: **yes**.

| Figure | Reference | BPM engine | Match |
| --- | ---: | ---: | --- |
| SE tax | 1,130.36 | 1,130.36 | yes |
| AGI | 178,434.82 | 178,434.82 | yes |
| QBI deduction | 1,486.96 | 1,486.96 | yes |
| Taxable income | 144,747.85 | 144,747.85 | yes |
| Federal ordinary tax | 19,728.53 | 19,728.53 | yes |
| LTCG tax | 1,050.00 | 1,050.00 | yes |
| W-2 FICA | 12,775.50 | 12,775.50 | yes |
| CO state tax | 6,368.91 | 6,368.91 | yes |
| Child tax credit | 4,400.00 | 4,400.00 | yes |
| All-in tax | 36,653.30 | 36,653.30 | yes |
| Take-home | 142,346.70 | 142,346.70 | yes |

| RETpy part | Reference | RETpy | Match |
| --- | ---: | ---: | --- |
| Federal ordinary tax (RETpy brackets on BPM's ordinary taxable income) | 19,728.53 | 19,728.53 | yes |
| LTCG tax (RETpy stacking on BPM's taxable income) | 1,050.00 | 1,050.00 | yes |
| CO state tax (RETpy 4.40% on BPM's state base) | 6,368.91 | 6,368.91 | yes |
| Child tax credit (RETpy) | 4,400.00 | 4,400.00 | yes |
| W-2 FICA (RETpy, two earners) | 12,775.50 | 12,775.50 | yes |

## 2. Summary

| Bucket | Fixtures |
| --- | ---: |
| match | 152 |
| BPM simplification | 228 |
| modeling difference | 42 |
| RETpy bug | 81 |

Unexplained differences: **0**.

Expected-gap edge cases that unexpectedly matched: **0**.

## 3. RETpy bugs (findings)

| Cause | Responsible | Fixtures | Largest gap ($) | Examples |
| --- | --- | ---: | ---: | --- |
| ltcg_tax: gains are taxed before Social Security is added to income, so taxable Social Security does not push gains up the stack or into NIIT; the same tables in IRS order give BPM's figure | account_simulation.py: AccountPortfolio._withdraw_single_pass, _tax_home_sale_gain; account_simulation.py: _true_up_social_security_tax, calculate_marginal_tax_on_income | 77 | 1,674.00 | CA-S-ORD-LTCG-SS, CA-MFJ-ORD-LTCG-SS, TX-S-ORD-LTCG-SS |
| the senior deduction shrinks as MAGI rises, but ordinary tax already booked is not re-priced when later gains or Social Security raise MAGI; the same tables in IRS order give BPM's figure | account_simulation.py: AccountPortfolio._withdraw_single_pass, _tax_home_sale_gain; config.standard_deduction_for_return | 2 | 396.00 | EDGE-niit-S-ss-order, EDGE-senior-S-cap-ltcg |
| ltcg_tax: unused standard deduction does not shelter gains (the stack starts at ordinary income minus the deduction, floored at 0); the same tables in IRS order give BPM's figure | account_simulation.py: AccountPortfolio._withdraw_single_pass, _tax_home_sale_gain | 2 | 4,830.00 | EDGE-ltcg-low-ordinary, EDGE-ltcg-no-ordinary |
| niit: gains are taxed before Social Security is added to income, so taxable Social Security does not push gains up the stack or into NIIT; the same tables in IRS order give BPM's figure | account_simulation.py: AccountPortfolio._withdraw_single_pass, _tax_home_sale_gain; account_simulation.py: _true_up_social_security_tax, calculate_marginal_tax_on_income | 1 | 912.00 | EDGE-niit-S-ss-order |

## 4. BPM simplifications (RETpy wins)

| Cause | Responsible | Fixtures | Largest gap ($) | Examples |
| --- | --- | ---: | ---: | --- |
| personal exemption (BPM does not model it); RETpy wins | state_tax_data.STATES rows above | 138 | 892.50 | IL-S-W2-low, IL-S-W2-high, IL-MFJ-W2-low |
| BPM tops the HoH 24% band at 201,775 (statute: 201,750), so its ordinary tax is up to $2 low above that | BPM TABLES.federal.hoh; RETpy config.FEDERAL_BRACKETS_BY_STATUS is right (Rev. Proc. 2025-32) | 40 | 2.00 | CA-HOH-W2-high, TX-HOH-W2-high, PA-HOH-W2-high |
| retirement-income exclusion (BPM taxes it all); RETpy wins (states: CO GA IA KY LA NY PA) | state_tax_data.STATES rows above | 37 | 4,560.00 | PA-S-ORD-LTCG, PA-S-ORD-LTCG-SS, PA-MFJ-ORD-LTCG |
| BPM lists Single's figures for head of household; RETpy keeps a real head-of-household schedule (states: ID MN ND NE OK OR VT) | state_tax_data.STATES rows above | 27 | 2,228.72 | ID-HOH-W2-low, ID-HOH-W2-high, ID-HOH-ORD-LTCG |
| personal exemption (BPM does not model it), retirement-income exclusion (BPM taxes it all); RETpy wins (states: IL MD MS OK) | state_tax_data.STATES rows above | 19 | 6,214.73 | IL-S-ORD-LTCG, IL-S-ORD-LTCG-SS, IL-MFJ-ORD-LTCG |
| exemption credits (BPM does not model them); RETpy wins (states: CA) | state_tax_data.STATES['CA'] | 13 | 632.00 | CA-S-W2-low, CA-S-W2-high, CA-S-ORD-LTCG |
| BPM's 8,350 / 16,700 deduction matches no federal or Arizona figure; RETpy follows the federal deduction (states: AZ) | state_tax_data.STATES['AZ'] | 12 | 395.00 | AZ-S-W2-low, AZ-S-W2-high, AZ-S-ORD-LTCG |
| state taxes Social Security (BPM exempts it everywhere); RETpy wins (states: MN MT NM) | state_tax_data.STATES rows above | 5 | 3,044.15 | MN-MFJ-ORD-LTCG-SS, MT-S-ORD-LTCG-SS, MT-MFJ-ORD-LTCG-SS |
| BPM gives a joint return one $3,360 deduction; Kentucky gives each taxpayer one (states: KY) | state_tax_data.STATES['KY'] | 4 | 117.60 | KY-MFJ-W2-low, KY-MFJ-W2-high, KY-MFJ-ORD-LTCG |
| personal exemption (BPM does not model it), state taxes Social Security (BPM exempts it everywhere); RETpy wins (states: RI VT) | state_tax_data.STATES rows above | 3 | 1,350.38 | RI-MFJ-ORD-LTCG-SS, VT-S-ORD-LTCG-SS, VT-MFJ-ORD-LTCG-SS |
| retirement-income exclusion (BPM taxes it all), state capital-gains exclusion (BPM taxes gains in full); RETpy wins (states: AR) | state_tax_data.STATES['AR'] | 2 | 592.00 | AR-S-ORD-LTCG-SS, AR-HOH-ORD-LTCG-SS |
| state capital-gains exclusion (BPM taxes gains in full); RETpy wins (states: ND) | state_tax_data.STATES['ND'] | 2 | 624.00 | ND-S-ORD-LTCG, ND-MFJ-ORD-LTCG |
| BPM needs MAGI over the top IRMAA boundary; CMS and RETpy put the top tier at or above it | BPM TABLES.irmaa; RETpy config.medicare_irmaa_tier | 2 | 1.00 | EDGE-irmaa-S-500000-at, EDGE-irmaa-MFJ-750000-at |

## 5. Modeling differences

| Cause | Responsible | Fixtures | Largest gap ($) | Examples |
| --- | --- | ---: | ---: | --- |
| BPM takes the top-of-range deduction; RETpy uses the income-tested floor (states: AL) | state_tax_data.STATES['AL'] | 12 | 175.00 | AL-S-W2-low, AL-S-W2-high, AL-S-ORD-LTCG |
| RETpy omits the SCIAD phase-out (BPM models it) (states: SC) | state_tax_data.STATES['SC'] | 12 | 1,563.00 | SC-S-W2-low, SC-S-W2-high, SC-S-ORD-LTCG |
| BPM takes the full standard deduction; RETpy leaves the sliding deduction out (0) (states: WI) | state_tax_data.STATES['WI'] | 12 | 1,976.76 | WI-S-W2-low, WI-S-W2-high, WI-S-ORD-LTCG |
| RETpy omits Arkansas's second table above $94,700 (adds up to about $290) (states: AR) | state_tax_data.STATES['AR'] | 8 | 287.26 | AR-S-W2-high, AR-S-ORD-LTCG, AR-MFJ-W2-low |
| RETpy omits Utah's taxpayer credit (states: UT) | state_tax_data.STATES['UT'] | 7 | 1,700.03 | UT-S-W2-low, UT-S-ORD-LTCG-SS, UT-MFJ-W2-low |

## 6. Every fixture

Each differing figure shows RETpy, then BPM (RETpy minus BPM). `state_tax` is RETpy with its app-only rules switched off.

| Fixture | Scenario | Bucket | Differences |
| --- | --- | --- | --- |
| CA-S-W2-low | W-2 $90,000 (CA, Single) | BPM simplification | - |
| CA-S-W2-high | W-2 $275,000 (CA, Single) | BPM simplification | - |
| CA-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (CA, Single) | BPM simplification | - |
| CA-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (CA, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| CA-MFJ-W2-low | W-2 $180,000 (CA, MFJ) | BPM simplification | - |
| CA-MFJ-W2-high | W-2 $550,000 (CA, MFJ) | BPM simplification | - |
| CA-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (CA, MFJ) | BPM simplification | - |
| CA-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (CA, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| CA-HOH-W2-low | W-2 $90,000 (CA, HoH) | BPM simplification | - |
| CA-HOH-W2-high | W-2 $275,000 (CA, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| CA-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (CA, HoH) | BPM simplification | - |
| CA-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (CA, HoH) | BPM simplification | - |
| TX-S-W2-low | W-2 $90,000 (TX, Single) | match | - |
| TX-S-W2-high | W-2 $275,000 (TX, Single) | match | - |
| TX-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (TX, Single) | match | - |
| TX-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (TX, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| TX-MFJ-W2-low | W-2 $180,000 (TX, MFJ) | match | - |
| TX-MFJ-W2-high | W-2 $550,000 (TX, MFJ) | match | - |
| TX-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (TX, MFJ) | match | - |
| TX-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (TX, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| TX-HOH-W2-low | W-2 $90,000 (TX, HoH) | match | - |
| TX-HOH-W2-high | W-2 $275,000 (TX, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| TX-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (TX, HoH) | match | - |
| TX-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (TX, HoH) | match | - |
| PA-S-W2-low | W-2 $90,000 (PA, Single) | match | - |
| PA-S-W2-high | W-2 $275,000 (PA, Single) | match | - |
| PA-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (PA, Single) | BPM simplification | - |
| PA-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (PA, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| PA-MFJ-W2-low | W-2 $180,000 (PA, MFJ) | match | - |
| PA-MFJ-W2-high | W-2 $550,000 (PA, MFJ) | match | - |
| PA-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (PA, MFJ) | BPM simplification | - |
| PA-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (PA, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| PA-HOH-W2-low | W-2 $90,000 (PA, HoH) | match | - |
| PA-HOH-W2-high | W-2 $275,000 (PA, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| PA-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (PA, HoH) | BPM simplification | - |
| PA-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (PA, HoH) | BPM simplification | - |
| IL-S-W2-low | W-2 $90,000 (IL, Single) | BPM simplification | - |
| IL-S-W2-high | W-2 $275,000 (IL, Single) | BPM simplification | - |
| IL-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (IL, Single) | BPM simplification | - |
| IL-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (IL, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| IL-MFJ-W2-low | W-2 $180,000 (IL, MFJ) | BPM simplification | - |
| IL-MFJ-W2-high | W-2 $550,000 (IL, MFJ) | BPM simplification | - |
| IL-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (IL, MFJ) | BPM simplification | - |
| IL-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (IL, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| IL-HOH-W2-low | W-2 $90,000 (IL, HoH) | BPM simplification | - |
| IL-HOH-W2-high | W-2 $275,000 (IL, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| IL-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (IL, HoH) | BPM simplification | - |
| IL-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (IL, HoH) | BPM simplification | - |
| NJ-S-W2-low | W-2 $90,000 (NJ, Single) | BPM simplification | - |
| NJ-S-W2-high | W-2 $275,000 (NJ, Single) | BPM simplification | - |
| NJ-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (NJ, Single) | BPM simplification | - |
| NJ-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (NJ, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| NJ-MFJ-W2-low | W-2 $180,000 (NJ, MFJ) | BPM simplification | - |
| NJ-MFJ-W2-high | W-2 $550,000 (NJ, MFJ) | BPM simplification | - |
| NJ-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (NJ, MFJ) | BPM simplification | - |
| NJ-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (NJ, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| NJ-HOH-W2-low | W-2 $90,000 (NJ, HoH) | BPM simplification | - |
| NJ-HOH-W2-high | W-2 $275,000 (NJ, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| NJ-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (NJ, HoH) | BPM simplification | - |
| NJ-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (NJ, HoH) | BPM simplification | - |
| AL-S-W2-low | W-2 $90,000 (AL, Single) | modeling difference | state_tax 4,335.00 vs 4,310.00 (+25.00) |
| AL-S-W2-high | W-2 $275,000 (AL, Single) | modeling difference | state_tax 13,585.00 vs 13,560.00 (+25.00) |
| AL-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (AL, Single) | modeling difference | state_tax 4,835.00 vs 4,810.00 (+25.00) |
| AL-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (AL, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50); state_tax 2,585.00 vs 2,560.00 (+25.00) |
| AL-MFJ-W2-low | W-2 $180,000 (AL, MFJ) | modeling difference | state_tax 8,670.00 vs 8,495.00 (+175.00) |
| AL-MFJ-W2-high | W-2 $550,000 (AL, MFJ) | modeling difference | state_tax 27,170.00 vs 26,995.00 (+175.00) |
| AL-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (AL, MFJ) | modeling difference | state_tax 9,670.00 vs 9,495.00 (+175.00) |
| AL-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (AL, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00); state_tax 5,170.00 vs 4,995.00 (+175.00) |
| AL-HOH-W2-low | W-2 $90,000 (AL, HoH) | modeling difference | state_tax 4,335.00 vs 4,310.00 (+25.00) |
| AL-HOH-W2-high | W-2 $275,000 (AL, HoH) | modeling difference | fed_ordinary 54,919.00 vs 54,917.00 (+2.00); state_tax 13,585.00 vs 13,560.00 (+25.00) |
| AL-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (AL, HoH) | modeling difference | state_tax 6,085.00 vs 6,060.00 (+25.00) |
| AL-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (AL, HoH) | modeling difference | state_tax 2,585.00 vs 2,560.00 (+25.00) |
| AR-S-W2-low | W-2 $90,000 (AR, Single) | match | - |
| AR-S-W2-high | W-2 $275,000 (AR, Single) | modeling difference | state_tax 9,716.45 vs 10,003.71 (-287.26) |
| AR-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (AR, Single) | modeling difference | state_tax 3,241.45 vs 3,518.71 (-277.26) |
| AR-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (AR, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| AR-MFJ-W2-low | W-2 $180,000 (AR, MFJ) | modeling difference | state_tax 6,110.06 vs 6,397.32 (-287.26) |
| AR-MFJ-W2-high | W-2 $550,000 (AR, MFJ) | modeling difference | state_tax 19,800.06 vs 20,087.32 (-287.26) |
| AR-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (AR, MFJ) | modeling difference | state_tax 6,850.06 vs 7,137.32 (-287.26) |
| AR-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (AR, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00); state_tax 3,520.06 vs 3,807.32 (-287.26) |
| AR-HOH-W2-low | W-2 $90,000 (AR, HoH) | match | - |
| AR-HOH-W2-high | W-2 $275,000 (AR, HoH) | modeling difference | fed_ordinary 54,919.00 vs 54,917.00 (+2.00); state_tax 9,716.45 vs 10,003.71 (-287.26) |
| AR-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (AR, HoH) | modeling difference | state_tax 4,166.45 vs 4,453.71 (-287.26) |
| AR-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (AR, HoH) | BPM simplification | - |
| AZ-S-W2-low | W-2 $90,000 (AZ, Single) | BPM simplification | state_tax 1,847.50 vs 2,041.25 (-193.75) |
| AZ-S-W2-high | W-2 $275,000 (AZ, Single) | BPM simplification | state_tax 6,472.50 vs 6,666.25 (-193.75) |
| AZ-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (AZ, Single) | BPM simplification | state_tax 2,097.50 vs 2,291.25 (-193.75) |
| AZ-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (AZ, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50); state_tax 972.50 vs 1,166.25 (-193.75) |
| AZ-MFJ-W2-low | W-2 $180,000 (AZ, MFJ) | BPM simplification | state_tax 3,695.00 vs 4,082.50 (-387.50) |
| AZ-MFJ-W2-high | W-2 $550,000 (AZ, MFJ) | BPM simplification | state_tax 12,945.00 vs 13,332.50 (-387.50) |
| AZ-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (AZ, MFJ) | BPM simplification | state_tax 4,195.00 vs 4,582.50 (-387.50) |
| AZ-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (AZ, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00); state_tax 1,945.00 vs 2,332.50 (-387.50) |
| AZ-HOH-W2-low | W-2 $90,000 (AZ, HoH) | BPM simplification | state_tax 1,646.25 vs 2,041.25 (-395.00) |
| AZ-HOH-W2-high | W-2 $275,000 (AZ, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00); state_tax 6,271.25 vs 6,666.25 (-395.00) |
| AZ-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (AZ, HoH) | BPM simplification | state_tax 2,521.25 vs 2,916.25 (-395.00) |
| AZ-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (AZ, HoH) | BPM simplification | state_tax 771.25 vs 1,166.25 (-395.00) |
| CO-S-W2-low | W-2 $90,000 (CO, Single) | match | - |
| CO-S-W2-high | W-2 $275,000 (CO, Single) | match | - |
| CO-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (CO, Single) | BPM simplification | - |
| CO-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (CO, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| CO-MFJ-W2-low | W-2 $180,000 (CO, MFJ) | match | - |
| CO-MFJ-W2-high | W-2 $550,000 (CO, MFJ) | match | - |
| CO-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (CO, MFJ) | BPM simplification | - |
| CO-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (CO, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| CO-HOH-W2-low | W-2 $90,000 (CO, HoH) | match | - |
| CO-HOH-W2-high | W-2 $275,000 (CO, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| CO-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (CO, HoH) | BPM simplification | - |
| CO-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (CO, HoH) | BPM simplification | - |
| GA-S-W2-low | W-2 $90,000 (GA, Single) | match | - |
| GA-S-W2-high | W-2 $275,000 (GA, Single) | match | - |
| GA-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (GA, Single) | BPM simplification | - |
| GA-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (GA, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| GA-MFJ-W2-low | W-2 $180,000 (GA, MFJ) | match | - |
| GA-MFJ-W2-high | W-2 $550,000 (GA, MFJ) | match | - |
| GA-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (GA, MFJ) | BPM simplification | - |
| GA-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (GA, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| GA-HOH-W2-low | W-2 $90,000 (GA, HoH) | match | - |
| GA-HOH-W2-high | W-2 $275,000 (GA, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| GA-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (GA, HoH) | BPM simplification | - |
| GA-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (GA, HoH) | BPM simplification | - |
| HI-S-W2-low | W-2 $90,000 (HI, Single) | BPM simplification | - |
| HI-S-W2-high | W-2 $275,000 (HI, Single) | BPM simplification | - |
| HI-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (HI, Single) | BPM simplification | - |
| HI-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (HI, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| HI-MFJ-W2-low | W-2 $180,000 (HI, MFJ) | BPM simplification | - |
| HI-MFJ-W2-high | W-2 $550,000 (HI, MFJ) | BPM simplification | - |
| HI-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (HI, MFJ) | BPM simplification | - |
| HI-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (HI, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| HI-HOH-W2-low | W-2 $90,000 (HI, HoH) | BPM simplification | - |
| HI-HOH-W2-high | W-2 $275,000 (HI, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| HI-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (HI, HoH) | BPM simplification | - |
| HI-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (HI, HoH) | BPM simplification | - |
| IA-S-W2-low | W-2 $90,000 (IA, Single) | match | - |
| IA-S-W2-high | W-2 $275,000 (IA, Single) | match | - |
| IA-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (IA, Single) | BPM simplification | - |
| IA-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (IA, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| IA-MFJ-W2-low | W-2 $180,000 (IA, MFJ) | match | - |
| IA-MFJ-W2-high | W-2 $550,000 (IA, MFJ) | match | - |
| IA-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (IA, MFJ) | BPM simplification | - |
| IA-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (IA, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| IA-HOH-W2-low | W-2 $90,000 (IA, HoH) | match | - |
| IA-HOH-W2-high | W-2 $275,000 (IA, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| IA-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (IA, HoH) | BPM simplification | - |
| IA-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (IA, HoH) | BPM simplification | - |
| ID-S-W2-low | W-2 $90,000 (ID, Single) | match | - |
| ID-S-W2-high | W-2 $275,000 (ID, Single) | match | - |
| ID-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (ID, Single) | match | - |
| ID-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (ID, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| ID-MFJ-W2-low | W-2 $180,000 (ID, MFJ) | match | - |
| ID-MFJ-W2-high | W-2 $550,000 (ID, MFJ) | match | - |
| ID-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (ID, MFJ) | match | - |
| ID-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (ID, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| ID-HOH-W2-low | W-2 $90,000 (ID, HoH) | BPM simplification | state_tax 2,980.19 vs 3,235.12 (-254.93) |
| ID-HOH-W2-high | W-2 $275,000 (ID, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00); state_tax 12,785.19 vs 13,040.12 (-254.93) |
| ID-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (ID, HoH) | BPM simplification | state_tax 4,835.19 vs 5,090.12 (-254.93) |
| ID-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (ID, HoH) | BPM simplification | state_tax 1,125.19 vs 1,380.12 (-254.93) |
| IN-S-W2-low | W-2 $90,000 (IN, Single) | BPM simplification | - |
| IN-S-W2-high | W-2 $275,000 (IN, Single) | BPM simplification | - |
| IN-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (IN, Single) | BPM simplification | - |
| IN-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (IN, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| IN-MFJ-W2-low | W-2 $180,000 (IN, MFJ) | BPM simplification | - |
| IN-MFJ-W2-high | W-2 $550,000 (IN, MFJ) | BPM simplification | - |
| IN-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (IN, MFJ) | BPM simplification | - |
| IN-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (IN, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| IN-HOH-W2-low | W-2 $90,000 (IN, HoH) | BPM simplification | - |
| IN-HOH-W2-high | W-2 $275,000 (IN, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| IN-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (IN, HoH) | BPM simplification | - |
| IN-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (IN, HoH) | BPM simplification | - |
| KY-S-W2-low | W-2 $90,000 (KY, Single) | match | - |
| KY-S-W2-high | W-2 $275,000 (KY, Single) | match | - |
| KY-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (KY, Single) | BPM simplification | - |
| KY-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (KY, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| KY-MFJ-W2-low | W-2 $180,000 (KY, MFJ) | BPM simplification | state_tax 6,064.80 vs 6,182.40 (-117.60) |
| KY-MFJ-W2-high | W-2 $550,000 (KY, MFJ) | BPM simplification | state_tax 19,014.80 vs 19,132.40 (-117.60) |
| KY-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (KY, MFJ) | BPM simplification | state_tax 6,764.80 vs 6,882.40 (-117.60) |
| KY-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (KY, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00); state_tax 3,614.80 vs 3,732.40 (-117.60) |
| KY-HOH-W2-low | W-2 $90,000 (KY, HoH) | match | - |
| KY-HOH-W2-high | W-2 $275,000 (KY, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| KY-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (KY, HoH) | BPM simplification | - |
| KY-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (KY, HoH) | BPM simplification | - |
| LA-S-W2-low | W-2 $90,000 (LA, Single) | match | - |
| LA-S-W2-high | W-2 $275,000 (LA, Single) | match | - |
| LA-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (LA, Single) | match | - |
| LA-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (LA, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| LA-MFJ-W2-low | W-2 $180,000 (LA, MFJ) | match | - |
| LA-MFJ-W2-high | W-2 $550,000 (LA, MFJ) | match | - |
| LA-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (LA, MFJ) | match | - |
| LA-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (LA, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| LA-HOH-W2-low | W-2 $90,000 (LA, HoH) | match | - |
| LA-HOH-W2-high | W-2 $275,000 (LA, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| LA-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (LA, HoH) | match | - |
| LA-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (LA, HoH) | BPM simplification | - |
| MA-S-W2-low | W-2 $90,000 (MA, Single) | BPM simplification | - |
| MA-S-W2-high | W-2 $275,000 (MA, Single) | BPM simplification | - |
| MA-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (MA, Single) | BPM simplification | - |
| MA-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (MA, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| MA-MFJ-W2-low | W-2 $180,000 (MA, MFJ) | BPM simplification | - |
| MA-MFJ-W2-high | W-2 $550,000 (MA, MFJ) | BPM simplification | - |
| MA-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (MA, MFJ) | BPM simplification | - |
| MA-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (MA, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| MA-HOH-W2-low | W-2 $90,000 (MA, HoH) | BPM simplification | - |
| MA-HOH-W2-high | W-2 $275,000 (MA, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| MA-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (MA, HoH) | BPM simplification | - |
| MA-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (MA, HoH) | BPM simplification | - |
| MD-S-W2-low | W-2 $90,000 (MD, Single) | BPM simplification | - |
| MD-S-W2-high | W-2 $275,000 (MD, Single) | BPM simplification | - |
| MD-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (MD, Single) | BPM simplification | - |
| MD-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (MD, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| MD-MFJ-W2-low | W-2 $180,000 (MD, MFJ) | BPM simplification | - |
| MD-MFJ-W2-high | W-2 $550,000 (MD, MFJ) | BPM simplification | - |
| MD-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (MD, MFJ) | BPM simplification | - |
| MD-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (MD, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| MD-HOH-W2-low | W-2 $90,000 (MD, HoH) | BPM simplification | - |
| MD-HOH-W2-high | W-2 $275,000 (MD, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| MD-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (MD, HoH) | BPM simplification | - |
| MD-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (MD, HoH) | BPM simplification | - |
| ME-S-W2-low | W-2 $90,000 (ME, Single) | BPM simplification | - |
| ME-S-W2-high | W-2 $275,000 (ME, Single) | BPM simplification | - |
| ME-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (ME, Single) | BPM simplification | - |
| ME-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (ME, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| ME-MFJ-W2-low | W-2 $180,000 (ME, MFJ) | BPM simplification | - |
| ME-MFJ-W2-high | W-2 $550,000 (ME, MFJ) | BPM simplification | - |
| ME-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (ME, MFJ) | BPM simplification | - |
| ME-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (ME, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| ME-HOH-W2-low | W-2 $90,000 (ME, HoH) | BPM simplification | - |
| ME-HOH-W2-high | W-2 $275,000 (ME, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| ME-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (ME, HoH) | BPM simplification | - |
| ME-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (ME, HoH) | BPM simplification | - |
| MN-S-W2-low | W-2 $90,000 (MN, Single) | match | - |
| MN-S-W2-high | W-2 $275,000 (MN, Single) | match | - |
| MN-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (MN, Single) | match | - |
| MN-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (MN, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| MN-MFJ-W2-low | W-2 $180,000 (MN, MFJ) | match | - |
| MN-MFJ-W2-high | W-2 $550,000 (MN, MFJ) | match | - |
| MN-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (MN, MFJ) | match | - |
| MN-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (MN, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| MN-HOH-W2-low | W-2 $90,000 (MN, HoH) | BPM simplification | state_tax 4,065.16 vs 4,596.60 (-531.45) |
| MN-HOH-W2-high | W-2 $275,000 (MN, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00); state_tax 17,656.72 vs 19,885.44 (-2,228.72) |
| MN-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (MN, HoH) | BPM simplification | state_tax 6,445.15 vs 6,979.44 (-534.29) |
| MN-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (MN, HoH) | BPM simplification | state_tax 1,770.85 vs 2,216.61 (-445.76) |
| MO-S-W2-low | W-2 $90,000 (MO, Single) | match | - |
| MO-S-W2-high | W-2 $275,000 (MO, Single) | match | - |
| MO-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (MO, Single) | match | - |
| MO-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (MO, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| MO-MFJ-W2-low | W-2 $180,000 (MO, MFJ) | match | - |
| MO-MFJ-W2-high | W-2 $550,000 (MO, MFJ) | match | - |
| MO-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (MO, MFJ) | match | - |
| MO-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (MO, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| MO-HOH-W2-low | W-2 $90,000 (MO, HoH) | match | - |
| MO-HOH-W2-high | W-2 $275,000 (MO, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| MO-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (MO, HoH) | match | - |
| MO-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (MO, HoH) | match | - |
| MS-S-W2-low | W-2 $90,000 (MS, Single) | BPM simplification | - |
| MS-S-W2-high | W-2 $275,000 (MS, Single) | BPM simplification | - |
| MS-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (MS, Single) | BPM simplification | - |
| MS-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (MS, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| MS-MFJ-W2-low | W-2 $180,000 (MS, MFJ) | BPM simplification | - |
| MS-MFJ-W2-high | W-2 $550,000 (MS, MFJ) | BPM simplification | - |
| MS-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (MS, MFJ) | BPM simplification | - |
| MS-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (MS, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| MS-HOH-W2-low | W-2 $90,000 (MS, HoH) | BPM simplification | - |
| MS-HOH-W2-high | W-2 $275,000 (MS, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| MS-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (MS, HoH) | BPM simplification | - |
| MS-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (MS, HoH) | BPM simplification | - |
| MT-S-W2-low | W-2 $90,000 (MT, Single) | match | - |
| MT-S-W2-high | W-2 $275,000 (MT, Single) | match | - |
| MT-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (MT, Single) | match | - |
| MT-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (MT, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| MT-MFJ-W2-low | W-2 $180,000 (MT, MFJ) | match | - |
| MT-MFJ-W2-high | W-2 $550,000 (MT, MFJ) | match | - |
| MT-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (MT, MFJ) | match | - |
| MT-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (MT, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| MT-HOH-W2-low | W-2 $90,000 (MT, HoH) | match | - |
| MT-HOH-W2-high | W-2 $275,000 (MT, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| MT-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (MT, HoH) | match | - |
| MT-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (MT, HoH) | BPM simplification | - |
| NC-S-W2-low | W-2 $90,000 (NC, Single) | match | - |
| NC-S-W2-high | W-2 $275,000 (NC, Single) | match | - |
| NC-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (NC, Single) | match | - |
| NC-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (NC, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| NC-MFJ-W2-low | W-2 $180,000 (NC, MFJ) | match | - |
| NC-MFJ-W2-high | W-2 $550,000 (NC, MFJ) | match | - |
| NC-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (NC, MFJ) | match | - |
| NC-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (NC, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| NC-HOH-W2-low | W-2 $90,000 (NC, HoH) | match | - |
| NC-HOH-W2-high | W-2 $275,000 (NC, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| NC-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (NC, HoH) | match | - |
| NC-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (NC, HoH) | match | - |
| ND-S-W2-low | W-2 $90,000 (ND, Single) | match | - |
| ND-S-W2-high | W-2 $275,000 (ND, Single) | match | - |
| ND-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (ND, Single) | BPM simplification | - |
| ND-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (ND, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| ND-MFJ-W2-low | W-2 $180,000 (ND, MFJ) | match | - |
| ND-MFJ-W2-high | W-2 $550,000 (ND, MFJ) | match | - |
| ND-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (ND, MFJ) | BPM simplification | - |
| ND-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (ND, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| ND-HOH-W2-low | W-2 $90,000 (ND, HoH) | BPM simplification | state_tax 53.62 vs 338.81 (-285.19) |
| ND-HOH-W2-high | W-2 $275,000 (ND, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00); state_tax 3,661.12 vs 3,979.45 (-318.32) |
| ND-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (ND, HoH) | BPM simplification | state_tax 736.12 vs 1,021.31 (-285.19) |
| ND-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (ND, HoH) | match | - |
| NE-S-W2-low | W-2 $90,000 (NE, Single) | match | - |
| NE-S-W2-high | W-2 $275,000 (NE, Single) | match | - |
| NE-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (NE, Single) | match | - |
| NE-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (NE, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| NE-MFJ-W2-low | W-2 $180,000 (NE, MFJ) | match | - |
| NE-MFJ-W2-high | W-2 $550,000 (NE, MFJ) | match | - |
| NE-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (NE, MFJ) | match | - |
| NE-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (NE, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| NE-HOH-W2-low | W-2 $90,000 (NE, HoH) | BPM simplification | state_tax 3,079.27 vs 3,391.46 (-312.18) |
| NE-HOH-W2-high | W-2 $275,000 (NE, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00); state_tax 11,496.77 vs 11,808.96 (-312.18) |
| NE-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (NE, HoH) | BPM simplification | state_tax 4,671.77 vs 4,983.96 (-312.18) |
| NE-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (NE, HoH) | BPM simplification | state_tax 1,486.77 vs 1,798.96 (-312.18) |
| NM-S-W2-low | W-2 $90,000 (NM, Single) | match | - |
| NM-S-W2-high | W-2 $275,000 (NM, Single) | match | - |
| NM-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (NM, Single) | match | - |
| NM-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (NM, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| NM-MFJ-W2-low | W-2 $180,000 (NM, MFJ) | match | - |
| NM-MFJ-W2-high | W-2 $550,000 (NM, MFJ) | match | - |
| NM-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (NM, MFJ) | match | - |
| NM-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (NM, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| NM-HOH-W2-low | W-2 $90,000 (NM, HoH) | match | - |
| NM-HOH-W2-high | W-2 $275,000 (NM, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| NM-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (NM, HoH) | match | - |
| NM-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (NM, HoH) | match | - |
| NY-S-W2-low | W-2 $90,000 (NY, Single) | match | - |
| NY-S-W2-high | W-2 $275,000 (NY, Single) | match | - |
| NY-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (NY, Single) | BPM simplification | - |
| NY-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (NY, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| NY-MFJ-W2-low | W-2 $180,000 (NY, MFJ) | match | - |
| NY-MFJ-W2-high | W-2 $550,000 (NY, MFJ) | match | - |
| NY-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (NY, MFJ) | BPM simplification | - |
| NY-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (NY, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| NY-HOH-W2-low | W-2 $90,000 (NY, HoH) | match | - |
| NY-HOH-W2-high | W-2 $275,000 (NY, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| NY-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (NY, HoH) | BPM simplification | - |
| NY-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (NY, HoH) | BPM simplification | - |
| OH-S-W2-low | W-2 $90,000 (OH, Single) | BPM simplification | - |
| OH-S-W2-high | W-2 $275,000 (OH, Single) | BPM simplification | - |
| OH-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (OH, Single) | BPM simplification | - |
| OH-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (OH, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| OH-MFJ-W2-low | W-2 $180,000 (OH, MFJ) | BPM simplification | - |
| OH-MFJ-W2-high | W-2 $550,000 (OH, MFJ) | BPM simplification | - |
| OH-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (OH, MFJ) | BPM simplification | - |
| OH-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (OH, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| OH-HOH-W2-low | W-2 $90,000 (OH, HoH) | BPM simplification | - |
| OH-HOH-W2-high | W-2 $275,000 (OH, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| OH-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (OH, HoH) | BPM simplification | - |
| OH-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (OH, HoH) | BPM simplification | - |
| OK-S-W2-low | W-2 $90,000 (OK, Single) | BPM simplification | - |
| OK-S-W2-high | W-2 $275,000 (OK, Single) | BPM simplification | - |
| OK-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (OK, Single) | BPM simplification | - |
| OK-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (OK, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| OK-MFJ-W2-low | W-2 $180,000 (OK, MFJ) | BPM simplification | - |
| OK-MFJ-W2-high | W-2 $550,000 (OK, MFJ) | BPM simplification | - |
| OK-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (OK, MFJ) | BPM simplification | - |
| OK-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (OK, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| OK-HOH-W2-low | W-2 $90,000 (OK, HoH) | BPM simplification | state_tax 3,199.75 vs 3,549.50 (-349.75) |
| OK-HOH-W2-high | W-2 $275,000 (OK, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00); state_tax 11,524.75 vs 11,874.50 (-349.75) |
| OK-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (OK, HoH) | BPM simplification | state_tax 4,774.75 vs 5,124.50 (-349.75) |
| OK-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (OK, HoH) | BPM simplification | state_tax 1,624.75 vs 1,974.50 (-349.75) |
| OR-S-W2-low | W-2 $90,000 (OR, Single) | match | - |
| OR-S-W2-high | W-2 $275,000 (OR, Single) | match | - |
| OR-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (OR, Single) | match | - |
| OR-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (OR, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| OR-MFJ-W2-low | W-2 $180,000 (OR, MFJ) | match | - |
| OR-MFJ-W2-high | W-2 $550,000 (OR, MFJ) | match | - |
| OR-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (OR, MFJ) | match | - |
| OR-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (OR, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| OR-HOH-W2-low | W-2 $90,000 (OR, HoH) | BPM simplification | state_tax 6,850.25 vs 6,982.38 (-132.12) |
| OR-HOH-W2-high | W-2 $275,000 (OR, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00); state_tax 23,274.42 vs 23,423.91 (-149.49) |
| OR-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (OR, HoH) | BPM simplification | state_tax 9,912.75 vs 10,044.88 (-132.12) |
| OR-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (OR, HoH) | BPM simplification | state_tax 3,787.75 vs 3,919.88 (-132.12) |
| RI-S-W2-low | W-2 $90,000 (RI, Single) | BPM simplification | - |
| RI-S-W2-high | W-2 $275,000 (RI, Single) | BPM simplification | - |
| RI-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (RI, Single) | BPM simplification | - |
| RI-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (RI, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| RI-MFJ-W2-low | W-2 $180,000 (RI, MFJ) | BPM simplification | - |
| RI-MFJ-W2-high | W-2 $550,000 (RI, MFJ) | BPM simplification | - |
| RI-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (RI, MFJ) | BPM simplification | - |
| RI-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (RI, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| RI-HOH-W2-low | W-2 $90,000 (RI, HoH) | BPM simplification | - |
| RI-HOH-W2-high | W-2 $275,000 (RI, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| RI-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (RI, HoH) | BPM simplification | - |
| RI-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (RI, HoH) | BPM simplification | - |
| SC-S-W2-low | W-2 $90,000 (SC, Single) | modeling difference | state_tax 2,941.50 vs 3,651.95 (-710.45) |
| SC-S-W2-high | W-2 $275,000 (SC, Single) | modeling difference | state_tax 12,580.00 vs 13,361.50 (-781.50) |
| SC-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (SC, Single) | modeling difference | state_tax 3,462.50 vs 4,244.00 (-781.50) |
| SC-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (SC, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50); state_tax 1,118.00 vs 1,693.47 (-575.47) |
| SC-MFJ-W2-low | W-2 $180,000 (SC, MFJ) | modeling difference | state_tax 6,849.00 vs 8,269.91 (-1,420.91) |
| SC-MFJ-W2-high | W-2 $550,000 (SC, MFJ) | modeling difference | state_tax 26,126.00 vs 27,689.00 (-1,563.00) |
| SC-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (SC, MFJ) | modeling difference | state_tax 7,891.00 vs 9,454.00 (-1,563.00) |
| SC-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (SC, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00); state_tax 3,202.00 vs 4,292.55 (-1,090.55) |
| SC-HOH-W2-low | W-2 $90,000 (SC, HoH) | modeling difference | state_tax 2,550.75 vs 2,977.02 (-426.27) |
| SC-HOH-W2-high | W-2 $275,000 (SC, HoH) | modeling difference | fed_ordinary 54,919.00 vs 54,917.00 (+2.00); state_tax 12,189.25 vs 13,361.50 (-1,172.25) |
| SC-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (SC, HoH) | modeling difference | state_tax 4,374.25 vs 5,297.84 (-923.59) |
| SC-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (SC, HoH) | modeling difference | state_tax 727.25 vs 1,018.54 (-291.29) |
| UT-S-W2-low | W-2 $90,000 (UT, Single) | modeling difference | state_tax 4,005.00 vs 3,965.95 (+39.05) |
| UT-S-W2-high | W-2 $275,000 (UT, Single) | match | - |
| UT-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (UT, Single) | match | - |
| UT-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (UT, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50); state_tax 2,447.50 vs 3,419.70 (-972.20) |
| UT-MFJ-W2-low | W-2 $180,000 (UT, MFJ) | modeling difference | state_tax 8,010.00 vs 7,931.90 (+78.10) |
| UT-MFJ-W2-high | W-2 $550,000 (UT, MFJ) | match | - |
| UT-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (UT, MFJ) | match | - |
| UT-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (UT, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00); state_tax 4,895.00 vs 6,595.03 (-1,700.03) |
| UT-HOH-W2-low | W-2 $90,000 (UT, HoH) | modeling difference | state_tax 4,005.00 vs 3,361.41 (+643.59) |
| UT-HOH-W2-high | W-2 $275,000 (UT, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| UT-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (UT, HoH) | modeling difference | state_tax 5,562.50 vs 5,373.91 (+188.59) |
| UT-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (UT, HoH) | modeling difference | state_tax 2,447.50 vs 2,815.16 (-367.66) |
| VA-S-W2-low | W-2 $90,000 (VA, Single) | BPM simplification | - |
| VA-S-W2-high | W-2 $275,000 (VA, Single) | BPM simplification | - |
| VA-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (VA, Single) | BPM simplification | - |
| VA-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (VA, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| VA-MFJ-W2-low | W-2 $180,000 (VA, MFJ) | BPM simplification | - |
| VA-MFJ-W2-high | W-2 $550,000 (VA, MFJ) | BPM simplification | - |
| VA-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (VA, MFJ) | BPM simplification | - |
| VA-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (VA, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| VA-HOH-W2-low | W-2 $90,000 (VA, HoH) | BPM simplification | - |
| VA-HOH-W2-high | W-2 $275,000 (VA, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| VA-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (VA, HoH) | BPM simplification | - |
| VA-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (VA, HoH) | BPM simplification | - |
| VT-S-W2-low | W-2 $90,000 (VT, Single) | BPM simplification | - |
| VT-S-W2-high | W-2 $275,000 (VT, Single) | BPM simplification | - |
| VT-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (VT, Single) | BPM simplification | - |
| VT-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (VT, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| VT-MFJ-W2-low | W-2 $180,000 (VT, MFJ) | BPM simplification | - |
| VT-MFJ-W2-high | W-2 $550,000 (VT, MFJ) | BPM simplification | - |
| VT-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (VT, MFJ) | BPM simplification | - |
| VT-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (VT, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| VT-HOH-W2-low | W-2 $90,000 (VT, HoH) | BPM simplification | state_tax 3,120.90 vs 3,829.60 (-708.70) |
| VT-HOH-W2-high | W-2 $275,000 (VT, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00); state_tax 16,312.90 vs 17,719.08 (-1,406.18) |
| VT-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (VT, HoH) | BPM simplification | state_tax 5,430.90 vs 6,139.60 (-708.70) |
| VT-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (VT, HoH) | BPM simplification | state_tax 1,470.65 vs 1,586.23 (-115.58) |
| WI-S-W2-low | W-2 $90,000 (WI, Single) | modeling difference | state_tax 4,166.46 vs 3,426.58 (+739.88) |
| WI-S-W2-high | W-2 $275,000 (WI, Single) | modeling difference | state_tax 13,971.46 vs 13,231.58 (+739.88) |
| WI-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (WI, Single) | modeling difference | state_tax 4,696.46 vs 3,956.58 (+739.88) |
| WI-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (WI, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50); state_tax 2,311.46 vs 1,669.77 (+641.69) |
| WI-MFJ-W2-low | W-2 $180,000 (WI, MFJ) | modeling difference | state_tax 8,735.31 vs 7,365.79 (+1,369.52) |
| WI-MFJ-W2-high | W-2 $550,000 (WI, MFJ) | modeling difference | state_tax 30,845.01 vs 28,868.25 (+1,976.76) |
| WI-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (WI, MFJ) | modeling difference | state_tax 9,795.31 vs 8,425.79 (+1,369.52) |
| WI-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (WI, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00); state_tax 5,025.31 vs 3,655.79 (+1,369.52) |
| WI-HOH-W2-low | W-2 $90,000 (WI, HoH) | modeling difference | state_tax 4,166.46 vs 3,426.58 (+739.88) |
| WI-HOH-W2-high | W-2 $275,000 (WI, HoH) | modeling difference | fed_ordinary 54,919.00 vs 54,917.00 (+2.00); state_tax 13,971.46 vs 13,231.58 (+739.88) |
| WI-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (WI, HoH) | modeling difference | state_tax 6,021.46 vs 5,281.58 (+739.88) |
| WI-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (WI, HoH) | modeling difference | state_tax 2,311.46 vs 1,669.77 (+641.69) |
| WV-S-W2-low | W-2 $90,000 (WV, Single) | BPM simplification | - |
| WV-S-W2-high | W-2 $275,000 (WV, Single) | BPM simplification | - |
| WV-S-ORD-LTCG | IRA/pension $60,000 + LTCG $40,000 (WV, Single) | BPM simplification | - |
| WV-S-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (WV, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| WV-MFJ-W2-low | W-2 $180,000 (WV, MFJ) | BPM simplification | - |
| WV-MFJ-W2-high | W-2 $550,000 (WV, MFJ) | BPM simplification | - |
| WV-MFJ-ORD-LTCG | IRA/pension $120,000 + LTCG $80,000 (WV, MFJ) | BPM simplification | - |
| WV-MFJ-ORD-LTCG-SS | pension $70,000 + LTCG $40,000 + SS $55,000 (WV, MFJ) | RETpy bug | ltcg_tax 0.00 vs 1,674.00 (-1,674.00) |
| WV-HOH-W2-low | W-2 $90,000 (WV, HoH) | BPM simplification | - |
| WV-HOH-W2-high | W-2 $275,000 (WV, HoH) | BPM simplification | fed_ordinary 54,919.00 vs 54,917.00 (+2.00) |
| WV-HOH-ORD-LTCG | IRA/pension $75,000 + LTCG $50,000 (WV, HoH) | BPM simplification | - |
| WV-HOH-ORD-LTCG-SS | pension $35,000 + LTCG $20,000 + SS $30,000 (WV, HoH) | BPM simplification | - |
| EDGE-niit-S-below | NIIT: Single MAGI 199,000 (below) (TX, Single) | match | - |
| EDGE-niit-S-at | NIIT: Single MAGI exactly 200,000 (TX, Single) | match | - |
| EDGE-niit-S-cross | NIIT: Single MAGI 210,000 (crosses, partial) (TX, Single) | match | - |
| EDGE-niit-S-full | NIIT: Single MAGI 300,000 (gains fully inside) (TX, Single) | match | - |
| EDGE-niit-MFJ-cross | NIIT: MFJ MAGI 270,000 (crosses, partial) (TX, MFJ) | match | - |
| EDGE-niit-HOH-cross | NIIT: HoH MAGI 210,000 (crosses, partial) (TX, HoH) | match | - |
| EDGE-niit-S-ss-order | NIIT: Single, Social Security pushes MAGI over 200,000 (TX, Single) | RETpy bug | fed_ordinary 32,042.00 vs 32,402.00 (-360.00); niit 0.00 vs 912.00 (-912.00) |
| EDGE-irmaa-S-109000-at | IRMAA: Single MAGI 109,000 (TX, Single) | match | - |
| EDGE-irmaa-S-109000-over | IRMAA: Single MAGI 109,001 (TX, Single) | match | - |
| EDGE-irmaa-S-137000-at | IRMAA: Single MAGI 137,000 (TX, Single) | match | - |
| EDGE-irmaa-S-137000-over | IRMAA: Single MAGI 137,001 (TX, Single) | match | - |
| EDGE-irmaa-S-500000-at | IRMAA: Single MAGI 500,000 (TX, Single) | BPM simplification | irmaa_tier 5.00 vs 4.00 (+1.00) |
| EDGE-irmaa-S-500000-over | IRMAA: Single MAGI 500,001 (TX, Single) | match | - |
| EDGE-irmaa-MFJ-218000-at | IRMAA: MFJ MAGI 218,000 (TX, MFJ) | match | - |
| EDGE-irmaa-MFJ-218000-over | IRMAA: MFJ MAGI 218,001 (TX, MFJ) | match | - |
| EDGE-irmaa-MFJ-274000-at | IRMAA: MFJ MAGI 274,000 (TX, MFJ) | match | - |
| EDGE-irmaa-MFJ-274000-over | IRMAA: MFJ MAGI 274,001 (TX, MFJ) | match | - |
| EDGE-irmaa-MFJ-750000-at | IRMAA: MFJ MAGI 750,000 (TX, MFJ) | BPM simplification | irmaa_tier 5.00 vs 4.00 (+1.00) |
| EDGE-irmaa-MFJ-750000-over | IRMAA: MFJ MAGI 750,001 (TX, MFJ) | match | - |
| EDGE-senior-S-75000 | Senior deduction: Single age 67+, MAGI 75,000 (TX, Single) | match | - |
| EDGE-senior-S-100000 | Senior deduction: Single age 67+, MAGI 100,000 (TX, Single) | match | - |
| EDGE-senior-S-175000 | Senior deduction: Single age 67+, MAGI 175,000 (TX, Single) | match | - |
| EDGE-senior-S-200000 | Senior deduction: Single age 67+, MAGI 200,000 (TX, Single) | match | - |
| EDGE-senior-MFJ-150000 | Senior deduction: MFJ age 67+, MAGI 150,000 (TX, MFJ) | match | - |
| EDGE-senior-MFJ-200000 | Senior deduction: MFJ age 67+, MAGI 200,000 (TX, MFJ) | match | - |
| EDGE-senior-MFJ-250000 | Senior deduction: MFJ age 67+, MAGI 250,000 (TX, MFJ) | match | - |
| EDGE-senior-MFJ-300000 | Senior deduction: MFJ age 67+, MAGI 300,000 (TX, MFJ) | match | - |
| EDGE-senior-HOH-75000 | Senior deduction: HoH age 67+, MAGI 75,000 (TX, HoH) | match | - |
| EDGE-senior-HOH-100000 | Senior deduction: HoH age 67+, MAGI 100,000 (TX, HoH) | match | - |
| EDGE-senior-HOH-175000 | Senior deduction: HoH age 67+, MAGI 175,000 (TX, HoH) | match | - |
| EDGE-senior-S-cap-ltcg | Senior deduction in phase-out with gains (Single 67, 90k + 30k LTCG) (TX, Single) | RETpy bug | fed_ordinary 9,397.00 vs 9,793.00 (-396.00) |
| EDGE-hoh-24-top | HoH: taxable income 201,760 (24% band tops at 201,750 by statute) (TX, HoH) | BPM simplification | fed_ordinary 39,210.20 vs 39,209.40 (+0.80) |
| EDGE-hoh-24-below | HoH: taxable income 201,700 (TX, HoH) | match | - |
| EDGE-hoh-32-top | HoH: taxable income 256,200 to 256,300 (TX, HoH) | BPM simplification | fed_ordinary 56,666.00 vs 56,664.00 (+2.00) |
| EDGE-single-24-top | Single: taxable income 201,780 (24% band tops at 201,775) (TX, Single) | match | - |
| EDGE-ltcg-0pct | LTCG wholly in the 0% band (Single 30k + 30k) (TX, Single) | match | - |
| EDGE-ltcg-straddle | LTCG straddling the 0% / 15% line (Single 45k + 30k) (TX, Single) | match | - |
| EDGE-ltcg-low-ordinary | Ordinary below the standard deduction, large gain (Single 10k + 60k) (TX, Single) | RETpy bug | ltcg_tax 1,582.50 vs 667.50 (+915.00) |
| EDGE-ltcg-no-ordinary | Gain only (MFJ 0 + 150k) (TX, MFJ) | RETpy bug | ltcg_tax 7,665.00 vs 2,835.00 (+4,830.00) |
| EDGE-ltcg-20pct | LTCG in the 20% band (Single 400k + 300k) (TX, Single) | match | - |
| EDGE-ss-zero | SS below the first base (Single pension 10k + SS 20k) (TX, Single) | match | - |
| EDGE-ss-half | SS in the 50% tier (Single pension 20k + SS 24k) (TX, Single) | match | - |
| EDGE-ss-85 | SS in the 85% tier (Single pension 50k + SS 36k) (TX, Single) | match | - |
| EDGE-ss-85-MFJ | SS in the 85% tier (MFJ pension 80k + SS 60k) (TX, MFJ) | match | - |
| EDGE-ss-ltcg-order | Gains with SS (Single 67: pension 35k + LTCG 20k + SS 30k) (TX, Single) | RETpy bug | ltcg_tax 0.00 vs 1,084.50 (-1,084.50) |
| EDGE-ca-sdi | CA SDI on W-2 wages (Single 150k) (CA, Single) | BPM simplification | - |
| EDGE-wage-base-MFJ | MFJ one earner 400k (over the 184,500 wage base) (TX, MFJ) | match | - |
## 7. Not compared

RETpy models none of these, so they are known gaps rather than findings: the qualified business income deduction (self-employment income), itemized deductions and the SALT cap, AMT, the earned income credit, and the ACA premium-credit cliff (BPM reports only the required-contribution percentage). BPM does not model them all either (AMT, EITC, loss carryforwards, local taxes).
