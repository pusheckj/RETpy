# Getting Started

This tutorial walks you from zero to your first Monte Carlo retirement simulation in about five minutes. By the end, you will have installed the package, run the default financial summary, executed a single Monte Carlo run, searched for the earliest feasible retirement age, and learned how to customize the model for your own situation.

---

## 1. Prerequisites

- **Python 3.9 or newer** (`python --version` to check)
- **pip** (ships with modern Python)
- A terminal and basic familiarity with virtual environments

Optional but recommended: `git` for cloning the repository.

---

## 2. Install

Clone the repository, create an isolated virtual environment, and install the dependencies:

```bash
git clone https://github.com/YOUR_USERNAME/retirement-monte-carlo.git
cd retirement-monte-carlo
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Verify the package imports cleanly:

```bash
python -c "import retirement_sim; print('OK')"
```

---

## 3. First Run: Print the Financial Summary

The package ships with an example config so you can see a working simulation before supplying any personal data. Print the default financial summary:

```bash
python -m retirement_sim.config
```

Sample output (illustrative example values only — not real financial advice):

```text
===== Retirement Model: Financial Summary (EXAMPLE DATA) =====
Household:          Partner A (age 35), Partner B (age 33)
Current year:       2026
Plan until age:     95

Account balances (starting):
  401(k)            $ 200,000
  Roth IRA          $  60,000
  Taxable brokerage $ 150,000
  HSA               $  25,000
  Cash / emergency  $  40,000
  TOTAL             $ 475,000

Annual contributions (illustrative):
  401(k) (combined) $  46,000
  Roth IRA          $  14,000
  Taxable savings   $  30,000

Return scenario:    historical (real returns)
Monte Carlo runs:   10,000
Target success:     80%
==============================================================
```

Numbers above are rounded placeholders from the example config. Your results will differ once you plug in real values.

---

## 4. Run a Single Monte Carlo

Open a Python REPL (or create a script) and run:

```python
from retirement_sim.account_simulation import run_monte_carlo_detailed

result = run_monte_carlo_detailed(retirement_age=55, n_simulations=1000)
print(f"Success rate: {result['success_rate']:.1%}")
```

A `success_rate` of 0.80 means the portfolio survived through the planning horizon in 80% of the simulated market paths. 1,000 simulations is enough to iterate quickly; bump to 10,000 for a final answer.

---

## 5. Find Your Earliest Retirement Age

Sweep retirement ages from 50 to 65 and stop at the first age that meets an 80% success threshold:

```python
from retirement_sim.account_simulation import run_monte_carlo_detailed

for age in range(50, 66):
    result = run_monte_carlo_detailed(retirement_age=age, n_simulations=2000)
    print(f"Retire at {age}: {result['success_rate']:.1%}")
    if result['success_rate'] >= 0.80:
        print(f"Earliest retirement: age {age}")
        break
```

Tip: lower `n_simulations` while exploring, then re-run at 10,000 on your chosen age for a tighter estimate.

---

## 6. Customize It for You

All inputs — balances, ages, income projections, expenses, tax assumptions — live in a single config module. The `examples/` directory contains a template and three realistic profile configs you can adapt:

```text
examples/
  example_config.py      # Documented template with every parameter
  basic_usage.py         # Scripted analysis walkthrough
  profile_early_career.py
  profile_mid_career.py
  profile_near_retirement.py
```

Copy the template and edit it in place:

```bash
cp examples/example_config.py my_config.py
# Edit my_config.py with your balances, ages, income, and expenses
```

Then point the simulator at your config instead of the shipped default. The simplest approach is to import from it:

```python
import my_config as cfg
from retirement_sim.account_simulation import AccountPortfolio, run_monte_carlo_detailed

# run_monte_carlo_detailed reads from retirement_sim.config by default.
# See docs/CONFIGURATION.md for how to swap in a custom config module.
```

**Privacy note:** `my_config.py` is listed in `.gitignore`, so your personal balances and income will never be accidentally committed or pushed. Keep personal data there — not in tracked files.

---

## 7. Next Steps

Deeper reading, in recommended order:

- [`docs/CONFIGURATION.md`](CONFIGURATION.md) — What every config parameter means and valid ranges.
- [`docs/METHODOLOGY.md`](METHODOLOGY.md) — How the Monte Carlo engine works: return models, withdrawal ordering, dynamic spending.
- [`docs/TAX_MODEL.md`](TAX_MODEL.md) — Federal and state tax assumptions, Social Security taxation, NIIT, IRMAA, and RMDs.
- [`examples/basic_usage.py`](../examples/basic_usage.py) — A scripted end-to-end analysis you can run and modify.

---

## 8. Troubleshooting

**`ImportError: No module named retirement_sim`**
Your virtual environment is not active, or dependencies were installed in a different environment. Reactivate and reinstall:

```bash
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**`KeyError` on `YOUR_COMPENSATION_BY_AGE` (or similar age-keyed dict)**
The simulation asked for an age that isn't in your income projection. Add entries covering the full range from your current age through your retirement age. Example:

```python
YOUR_COMPENSATION_BY_AGE = {
    35: 150_000,
    36: 155_000,
    # ... one entry per year until retirement
    54: 200_000,
}
```

**Simulation feels slow**
Each call to `run_monte_carlo_detailed` runs N full-lifetime simulations. While iterating on config, drop to `n_simulations=1000` (fast, ~1% noise on success rate) and only re-run at `n_simulations=10000` for a final number. For age sweeps, cache results to a dict instead of re-running.

**Results change every run**
Expected. Monte Carlo is stochastic. If you need reproducibility, set a NumPy seed before calling the simulator:

```python
import numpy as np
np.random.seed(42)
```

---

Questions or bug reports? Open an issue on GitHub. Contributions welcome — see `CONTRIBUTING.md`.
