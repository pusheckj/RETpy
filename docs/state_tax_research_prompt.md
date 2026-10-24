# State income tax: research prompt

The simulator's state tables (`retirement_sim/state_tax_data.py`) were written
without web access. Rates and brackets for most states are well known, but some
figures are best estimates, and every row should be checked against the
official source. Paste the prompt below into a web-enabled research assistant,
then update `state_tax_data.py` from its reply (and bump each row's `year` and
`confidence`).

Rows currently marked **approx** (the app labels them approximate): AL, AR, HI,
NE, WI. Rows marked **medium** leave out a credit, phase-out or local tax (see
each row's `note`): CO, CT, DE, GA, IA, ID, IN (county tax), KS, KY, LA, MD,
ME, MI, MN, MO, MS, MT, ND, NM, OH, OK, OR, RI, SC, UT, VT, WV.

---

## Prompt (copy from here)

You are a US state tax researcher. For **tax year 2025** (if a state has not
published 2025 figures, use 2024 and say so in the YEAR column), give the
individual income tax parameters of **all 50 states and the District of
Columbia**. Use only official sources (state revenue department forms,
instructions, rate schedules, or the statute). Do not estimate: if a figure is
not published, write `UNKNOWN`.

Return **one row per state per filing status**, three filing statuses per state
(`S` = single, `MFJ` = married filing jointly, `HOH` = head of household),
153 rows in total, in exactly this pipe-separated format, with no other text
between rows:

```
CODE|YEAR|STATUS|THRESHOLDS|RATES|STD_DEDUCTION|EXEMPTION|SS_TAXED|PENSION_EXCLUSION|LTCG_EXCLUSION|PAYROLL_TAX|LOCAL_TAX|SOURCE
```

Column rules:

- `CODE`: two-letter postal code (`DC` for the District).
- `YEAR`: the tax year the figures are for.
- `STATUS`: `S`, `MFJ` or `HOH`.
- `THRESHOLDS`: the UPPER limit of each bracket of taxable income, ascending,
  separated by `;`, last one `inf`. A flat tax is `inf`. No income tax is `inf`.
  Example: `10756;25499;40245;55866;70606;360659;432787;721314;inf`.
- `RATES`: the rate of each bracket as a decimal, same count and order as
  `THRESHOLDS`. Include any surtax as its own bracket (e.g. a 1% surtax above
  $1,000,000 splits the bracket at 1000000). No income tax is `0`.
- `STD_DEDUCTION`: dollars, or `FEDERAL` if the state uses the federal standard
  deduction, or `NONE`. If the deduction varies with income, give the amount at
  $100,000 of income and describe the rule in `SOURCE`.
- `EXEMPTION`: personal exemption deducted from income for this return in
  dollars (both spouses on MFJ), or `CREDIT:<dollars>` if it is a tax credit
  instead, or `NONE`. Note any income phase-out in `SOURCE`.
- `SS_TAXED`: `NO` (fully exempt), `YES` (taxed as on the federal return), or
  `BELOW:<income limit>` if exempt only below an income limit (say in `SOURCE`
  whether above the limit it is fully or partly taxed).
- `PENSION_EXCLUSION`: the yearly amount PER PERSON of distributions from a
  traditional 401(k) or IRA that is exempt, as `<min age>:<dollars>` tiers
  separated by `;` (e.g. `62:35000;65:65000`), `ALL` with a minimum age
  (`59.5:ALL`), or `NONE`. Say in `SOURCE` if it covers only government or
  employer pensions, or is income-tested.
- `LTCG_EXCLUSION`: share of long-term capital gains excluded (e.g. `0.44`),
  or `NONE`. Describe caps or special rates in `SOURCE`.
- `PAYROLL_TAX`: employee-paid state payroll taxes on wages (disability, paid
  family leave, unemployment, long-term care), as `<rate>@<wage cap or none>`,
  `+`-separated, or `NONE`. Example: `0.011@none`.
- `LOCAL_TAX`: `NONE`, or the typical local income tax rate range and where it
  applies (e.g. `2.25%-3.20% all counties`).
- `SOURCE`: the official URL(s), plus any rule the columns can't express.

Pay particular attention to, and double-check:

1. **Alabama**: standard deduction at $100k income per status; whether federal
   income tax paid is deductible and any cap; the $6,000 retirement exclusion
   at 65+.
2. **Arkansas**: the full bracket table for incomes above $100k and below; the
   standard deduction; the personal tax credit; the retirement exclusion; the
   capital-gains exclusion.
3. **Hawaii**: brackets and standard deduction for the year under Act 46 (2024).
4. **Nebraska**: standard deduction per status; head-of-household brackets;
   the personal exemption credit.
5. **Wisconsin**: the sliding standard deduction formula per status (maximum,
   income where it starts falling, rate it falls at).
6. **Idaho**: the zero bracket per status and the flat rate.
7. **Colorado**: the rate for the year (TABOR-adjusted vs 4.40%); the pension/
   Social Security subtraction by age.
8. **Connecticut, Minnesota, New Mexico, Rhode Island, Vermont**: the Social
   Security exemption income limits per status and how benefits are taxed
   above them; Connecticut and Rhode Island pension exclusions.
9. **Georgia, Kentucky, Louisiana, Mississippi, Missouri, Montana, North
   Carolina, Ohio, Oklahoma, Oregon, South Carolina, Utah, West Virginia,
   Iowa, Kansas, Indiana, Michigan**: confirm rates and brackets for the year
   (many changed in 2024-2026), the standard deduction / exemption, and any
   credits (Utah taxpayer credit; Oregon federal-tax subtraction and exemption
   credit; Ohio income-tested exemption).
10. **Maryland, Indiana, Ohio, Pennsylvania, Michigan, New York, Kentucky,
    Missouri, Delaware, Iowa, Alabama**: local income taxes (`LOCAL_TAX`).
11. **California, New Jersey, New York, Rhode Island, Hawaii, Washington,
    Massachusetts, Oregon, Colorado, Connecticut, Delaware, Maine, Maryland,
    Minnesota, Vermont**: employee payroll taxes (`PAYROLL_TAX`).
12. Whether **New Jersey** and **California** still tax HSA contributions, and
    whether **Pennsylvania** still taxes 401(k) employee deferrals.

## End of prompt

---

## Mapping the reply onto `state_tax_data.py`

| Reply column | Row field |
|---|---|
| `THRESHOLDS` + `RATES` | `brackets[status]` as `[(threshold, rate), ...]` with `INF` last |
| `STD_DEDUCTION` | `std_deduction[status]`, or `"federal"` |
| `EXEMPTION` | `exemption` (per person) or `{status: dollars}`; credits are not modeled yet (mention in `note`) |
| `SS_TAXED` | `social_security`: `"exempt"`, `"taxed"`, or `{"exempt_below_agi": {...}}` |
| `PENSION_EXCLUSION` | `retirement_exclusion`: `[{"min_age": ..., "per_person": ...}]` (`ALL` = `INF`) |
| `LTCG_EXCLUSION` | `ltcg_exclusion` |
| `PAYROLL_TAX` | `payroll`: `{"rate": ..., "wage_cap": ... or None}` (one combined rate) |
| `LOCAL_TAX` | `note` (local taxes are not modeled) |
| `YEAR` | `year`; set `confidence` to `"high"` once a row is fully verified |

After editing, run `python3 -m pytest tests/test_tax_rules.py -q` (the table
sanity checks) and the full suite.
