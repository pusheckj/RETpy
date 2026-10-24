# Retirement Monte Carlo

> Open-source Monte Carlo retirement simulator with realistic tax modeling.

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pytest-brightgreen.svg)](tests/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-orange.svg)](CONTRIBUTING.md)

> **New to the command line?** See [`HOW_TO_RUN.md`](HOW_TO_RUN.md) for a beginner-friendly, step-by-step guide (Windows and Mac).

## What It Does

Retirement Monte Carlo answers a deceptively hard question: *"What's the earliest age someone could retire with X% probability of success?"* It runs thousands of stochastic simulations against a realistic model of the US tax code, account types, and spending patterns to produce an honest estimate of when a portfolio can sustainably support retirement.

Key features:

- Account-level tracking across 401(k), Roth IRA, Traditional IRA, HSA, taxable brokerage, and cash
- Tax-efficient withdrawal ordering that changes at age 59.5
- Full 2024 US federal and California income tax brackets
- Social Security modeling with claiming-age adjustments (62 through 70)
- ACA marketplace premium subsidies and Medicare IRMAA surcharges
- Required Minimum Distributions under SECURE 2.0 rules
- Roth conversion ladder support during low-income early retirement years
- Guyton-Klinger-style dynamic spending guardrails
- Return-based spending flexibility
- Glide-path asset allocation that shifts toward bonds over time
- Long-term care cost modeling
- Category-specific inflation (general, healthcare, housing, childcare)
- Children: any number, each with their own monthly cost, leave-home age and optional 529 college savings
- Stock/bond return correlation modeling

## Why Another Retirement Calculator?

Most retirement calculators are either black-box web forms or spreadsheets that flatten the tax code into a single effective rate. This project takes a different approach:

- **Account-level tracking.** Every dollar is tagged by account type, so withdrawal order, RMDs, and tax-free Roth growth are modeled explicitly — not approximated.
- **Real tax brackets.** Federal, California, Social Security provisional income, NIIT, and IRMAA are applied the way the IRS actually applies them.
- **Transparent Python.** Everything is auditable code, not a sealed SaaS. Readers can fork it, extend it, plug in a different return distribution, or add a tax regime.
- **Honest defaults.** The simulator reports when a plan fails, why it failed, and what changed — not just a reassuring green checkmark.

## Quick Start

```bash
git clone https://github.com/pusheckj/RETpy.git
cd RETpy
pip install -r requirements.txt
```

Print a human-readable summary of the currently configured financial profile:

```bash
python -m retirement_sim.config
```

Then run a Monte Carlo from Python:

```python
from retirement_sim.account_simulation import run_monte_carlo_detailed

result = run_monte_carlo_detailed(retirement_age=50, n_simulations=5000)

print(f"Retirement age:   {result['retirement_age']}")
print(f"Success rate:     {result['success_rate']:.1%}")
print(f"Median end value: ${result['median_ending_balance']:,.0f}")
```

## Try the interactive UI

A polished Streamlit UI ships with the package — inspired by Personal Capital and Wealthfront dashboards — with always-visible quick inputs, advanced parameters tucked into dropdowns, and Plotly charts for Monte Carlo fan projections, success-by-age curves, allocation glide paths, and tax flow.

```bash
pip install -r ui/requirements-ui.txt
bash ui/run.sh          # macOS/Linux
ui\run.bat              # Windows (or: streamlit run ui/app.py, on any OS)
```

The app opens at http://localhost:8501. See [`ui/README_UI.md`](ui/README_UI.md) for a full walkthrough.
To host it for other people (invite-only, free), see [`docs/HOSTING.md`](docs/HOSTING.md).

Features:
- 📊 **Profile presets** — load a median 25-year-old household, young professional, mid-career couple, or near-retirement couple in one click
- ⚡ **Quick inputs** — current age, income, savings, target retirement age (always visible)
- 🔧 **Advanced dropdowns** — account-by-account balances, editable compensation table, home/mortgage, family events, return assumptions, Social Security, Roth conversions, spending guardrails, glide path, healthcare, LTC
- 📈 **Results dashboard** — hero earliest-retirement age card, KPI stats row, Monte Carlo fan chart, success-rate-by-age bars, allocation and income composition
- 🔍 **Deep-dive tabs** — individual trajectories, income sources, tax analysis, withdrawal strategy, and sensitivity analysis

## Example Output

```text
================================================================
  Retirement Monte Carlo — Results (illustrative figures)
================================================================
Retirement age:       50
Simulations:          5,000
Plan horizon:         Age 50 through 90

Success rate:         84.2%
Median end balance:   $1,250,000
10th percentile:      $0  (portfolio depleted at age 83)
90th percentile:      $4,800,000

Starting portfolio:   $500,000
Average real return:  5.1%
Failures driven by:   Sequence-of-returns risk (early drawdown)
================================================================
```

> Numbers above are illustrative, not a recommendation.

## Configuration

All financial assumptions live in [`retirement_sim/config.py`](retirement_sim/config.py). Users can either edit that file directly or import a custom config module and pass it into the simulator. See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for a full walkthrough, and [`examples/`](examples/) for pre-built profiles covering common situations (dual-income no-kids, single earner with children, FIRE, coast-FIRE, late start).

At minimum, users typically edit:

- Starting account balances (401(k), Roth, Traditional, HSA, taxable, cash)
- Compensation and savings rate projections by age
- Active return scenario (`conservative`, `historical`, `pessimistic`)
- Feature toggles (`INCLUDE_SOCIAL_SECURITY`, `DYNAMIC_SPENDING_ENABLED`, `GLIDE_PATH_ENABLED`, `ENABLE_ROTH_CONVERSION`, `LTC_ENABLED`)

## What's Modeled

### Taxes

- Federal income tax brackets (2024, married-filing-jointly and single)
- California state income tax brackets
- Long-term capital gains rates with 0% / 15% / 20% thresholds
- Social Security provisional income taxation (up to 85% taxable)
- Net Investment Income Tax (NIIT) at 3.8%
- Medicare IRMAA premium surcharges
- Standard deduction with inflation adjustment

### Income

- W-2 compensation projections by age
- Social Security benefit estimation with claiming-age multipliers (62-70)
- Spousal benefit coordination
- Required Minimum Distributions under SECURE 2.0 (age 73/75 phase-in)
- Optional Roth conversion ladder during low-income early retirement

### Expenses

- Category-specific inflation rates (general CPI, healthcare, housing, childcare)
- Pre-Medicare healthcare via ACA marketplace with subsidy calculation
- Medicare Part B/D premiums with IRMAA
- Child expense modeling: any number of children (daycare, K-12, extracurriculars), with each child's college saved in their own 529
- Long-term care shock modeling with duration and cost distributions
- Housing transitions (mortgage payoff, downsize events)

### Returns

- Parametric Monte Carlo on stock and bond real returns
- Stock/bond correlation matrix
- Asset allocation glide path (equity share decreases with age)
- Optional historical bootstrap from S&P 500 data back to 1926

### Withdrawal Strategy

- Tax-efficient ordering: cash → taxable (LTCG) → Roth basis → Traditional → HSA
- Post-59.5 reordering to prioritize Traditional before Roth
- Guyton-Klinger dynamic spending guardrails
- Return-based spending adjustments (spend more after strong years, less after weak)
- Early-withdrawal penalty accounting (10% on Traditional, 20% on non-medical HSA)

## What's NOT Modeled

Transparency matters. The following are deliberately out of scope:

- State-specific income taxes other than California
- Federal estate tax and gift tax planning
- Self-employment tax, SEP-IRA, or Solo 401(k) mechanics
- Annuity products (immediate, deferred, QLAC)
- Pension income and survivor-benefit elections
- Rental real estate income, depreciation, and 1031 exchanges
- Qualified Charitable Distributions (QCDs) from IRAs
- Specific healthcare plan shopping (bronze vs. silver vs. gold)
- Medicaid spend-down and asset protection planning
- Stock-based compensation (RSU/ISO/NSO) tax optimization
- International tax treatment or expatriation

Users who need any of these should treat this tool as a starting point and layer in their own modeling — or better yet, open a PR.

## Project Layout

```text
retirement-monte-carlo/
├── retirement_sim/          # Core simulation package
├── ui/                      # Streamlit UI (Personal Capital–style dashboard)
│   ├── app.py
│   ├── components/          # Input + result render components
│   ├── utils/               # sim_runner, formatting, config_builder
│   ├── styles/theme.css
│   └── run.sh
├── examples/                # Example profile configs
├── docs/                    # Methodology and tax model
└── tests/                   # Pytest suite
```

## Running Tests

```bash
pytest tests/
```

For a single test file or test case:

```bash
pytest tests/test_simulation.py -v
pytest tests/test_simulation.py::TestFederalTaxBrackets::test_zero_income -v
```

## Contributing

Contributions are welcome — bug reports, tax-code updates, new return models, and additional example profiles are all valuable. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development setup, code style, and pull request expectations.

## Disclaimer

This software is provided for educational and personal planning purposes only. It is not financial, tax, legal, or investment advice. Tax rules, contribution limits, Social Security formulas, and Medicare premiums change every year, and the defaults shipped with this package will drift out of date. Anyone making a real retirement decision should consult a Certified Financial Planner (CFP), a CPA, or another licensed professional who can account for their full situation. The authors and contributors accept no liability for decisions made using this tool.

## License

Released under the [MIT License](LICENSE).