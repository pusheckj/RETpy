# Tax cross-check (dev tool)

Checks RETpy's tax math against a second, independent tax engine: the BiggerPockets Money
(BPM) Income Tax Projection Calculator, v1.11.2, tax year 2026. Not part of the app and not
packaged (`pyproject.toml` ships only `retirement_sim*`).

## Run it

```bash
python3 tools/tax_crosscheck/crosscheck.py --bpm-source /path/to/calc_tax.html
# or: export BPM_TAX_SOURCE=/path/to/calc_tax.html
```

* Needs Node (any recent version) and Python 3. About 10 seconds on a laptop.
* `calc_tax.html` is the BPM tax calculator page (a single HTML file with the engine inside).
  It is not stored in this repo. The runner only reads it.
* Writes `tools/tax_crosscheck/REPORT.md` (override with `--report`). Nothing else in the repo
  changes. Intermediate JSON goes to a temp folder, or to `--work-dir`.
* `--states quick` runs six states for a fast check, `--states all` runs all 51, or give codes
  (`--states CA,TX,GA`). The default is CA, TX, PA, IL, NJ and every state whose 2026 table
  differs from the old one or from BPM.
* Exit code 1 means the BPM default example no longer reproduces, or a difference has no known
  cause ("unexplained" in the report).

## How it works

| File | Job |
| --- | --- |
| `crosscheck.py` | The driver: builds fixtures, runs both sides, compares to the cent, buckets every difference, writes the report. Never imports `retirement_sim`. |
| `bpm_runner.mjs` | Cuts `BPMTaxEngine` out of the page, runs `compute()` on each fixture in a Node `vm` (no DOM). |
| `app_side.py` | RETpy side. One fresh Python process per fixture, so changes to `retirement_sim.config` (filing status, state, ages) die with the process. |

Order of work: RETpy first (it supplies its age 65+ and senior deductions, which BPM takes in its
"other OBBBA deductions" field), then BPM, then the comparison.

RETpy engine paths used: `config.working_year_taxes` for wages, and `AccountPortfolio` (marginal
tax on ordinary income, `_tax_home_sale_gain` for gains, `_true_up_social_security_tax`) for
retirement income, booked in the order the engine books them.

## Fixtures

1. BPM's own default example (MFJ, CO, 2 children). The BPM engine must reproduce its verified
   figures (all-in $36,653.30 and ten more), and RETpy's tables must reproduce the federal,
   state, child-credit and payroll parts when fed BPM's intermediate figures.
2. A grid: Single, MFJ and HoH, by each state in the list, by four income mixes: wages (two
   levels), IRA/pension plus long-term gains, and pension plus gains plus Social Security.
   Standard deduction, no children.
3. Edge cases: NIIT threshold crossing, IRMAA tier boundaries (including the top tier), the senior
   deduction phase-out, the head-of-household 24% bracket top, capital-gains stacking, Social
   Security taxability tiers, the Social Security wage base, California payroll tax.

Compared per fixture: federal ordinary tax, long-term gains tax, NIIT, AGI, taxable Social
Security, IRMAA tier, FICA (wages), CA payroll tax, and state tax.

## Reading the report

Every fixture lands in one bucket:

* **match**: the same to the cent.
* **BPM simplification**: BPM leaves something out that RETpy models (personal exemptions,
  Social Security rules, retirement and gains exclusions, a real head-of-household schedule), or
  BPM has an error. RETpy wins.
* **modeling difference**: both are approximations and the choice is documented (for example
  RETpy leaves out Utah's taxpayer credit and Arkansas's second table).
* **RETpy bug**: RETpy is wrong or inconsistent. Each one names the code that is responsible.

State tax is compared with RETpy's app-only rules switched off (exemptions and credits, retirement
exclusions, gains exclusion, taxed Social Security). The harness re-runs the fixture with each rule
alone to name the rules that moved the result. Whatever still differs must have an entry in
`STATE_KNOWN` in `crosscheck.py`; otherwise it is "unexplained" and the run fails.

For gains and NIIT, the harness also computes the same return straight from RETpy's tables in IRS
order. If that matches BPM but the engine does not, the tables are right and the engine sequencing
is the cause.

## Updating for a new tax year

Re-run against the new BPM page. A table change in `retirement_sim/state_tax_data.py` or
`config.py` should leave the report with zero unexplained rows. Pinned state results live in
`tests/test_state_tax_2026.py` and do not need Node.
