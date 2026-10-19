# Retirement Monte Carlo — Streamlit UI

> **New to the command line?** See [`../HOW_TO_RUN.md`](../HOW_TO_RUN.md) for a beginner-friendly, step-by-step guide (Windows and Mac).

## Overview

A simple, elegant UI for the retirement Monte Carlo simulator, built with Streamlit and styled after modern personal-finance dashboards like Personal Capital and Wealthfront. The sidebar walks you through a single linear flow of expandable sections (about you, accounts, income, taxes, expenses, savings, retirement goals, assumptions) so the interface stays uncluttered. The main panel leads with charts that auto-update as you edit sidebar inputs, then a hero metric (earliest retirement age at your target success rate) and deep-dive tabs for trajectories, income, taxes, withdrawals, and sensitivity analysis once you click Run.

## Screenshots

ASCII mockup of the main screen:

```
+----------------------------------------------------------------+
| Retirement Monte Carlo                                         |
+--------------+-------------------------------------------------+
| Theme toggle | +-- Portfolio breakdown --------------------+   |
| Save / Load  |   Auto-updates as you edit sidebar inputs       |
| [Median 25 v]|                                                 |
|--------------| +-- Net worth projection --------------------+  |
| > About you  |   Auto-updates as you edit sidebar inputs       |
| > Accounts   |                                                 |
| > Income     | +-- Savings projection / Spending --------+     |
| > Taxes      |   Auto-updates as you edit sidebar inputs       |
| > Expenses   |                                                 |
| > Savings    | (Click Run ▶ to unlock results below)           |
| > Retirement |                                                 |
|   goals      | +-----------------------------------------+     |
| > Assumptions|  EARLIEST RETIREMENT AGE                  |     |
|              |          46                               |     |
| [ Run ▶ ]    |          with 80% success probability     |     |
| FAQ          | +-----------------------------------------+     |
|              | [ Trajectories | Income | Tax | Withdrawal      |
|              |   | Sensitivity ]                                |
+--------------+-------------------------------------------------+
```

## Quick Start

```bash
cd <project-root>
pip install -r ui/requirements-ui.txt
bash ui/run.sh          # macOS/Linux
ui\run.bat              # Windows
# or directly, on any OS:
streamlit run ui/app.py
```

The app opens at http://localhost:8501.

## Navigating the UI

- **Theme toggle, Save / Load, Profile picker** (top of sidebar): switch light/dark mode; download your current inputs as a JSON file or upload a previously saved file to restore them; instantly load a preset household — median 25-year-old, young professional, mid-career couple, near-retirement, or custom.
- **Linear sidebar walkthrough** (one section at a time, in advisor order): About you, Accounts (starting balances), Income, Taxes, Expenses, Savings, Retirement goals, Assumptions (advanced). Each is an expandable section reading/writing `st.session_state.user_overrides`.
- **Run ▶ simulation**: sits below the sidebar sections and kicks off 1,000 Monte Carlo simulations.
- **FAQ**: below the Run button, for reference while you fill in inputs.
- **Main panel — always visible**: portfolio breakdown, net worth projection, savings projection, and spending charts auto-update immediately as you change sidebar inputs, with no Run required.
- **Main panel — after Run**: hero metric → success rate by retirement age → key stats → fan chart → allocation & income composition charts.
- **Deep dives tabs** (after Run): individual trajectories, income-source breakdown, tax analysis, withdrawal strategy, sensitivity.

## Design Philosophy

- Clean neutral palette (off-white backgrounds, teal accent)
- Large readable typography (Inter font family)
- Generous whitespace
- Progressive disclosure — simple first, complexity available on demand
- Responsive charts (Plotly)

## Architecture

```
ui/
├── app.py                    # Entry point
├── components/               # Each a render(st, ...) function
│   ├── header.py
│   ├── profile_picker.py
│   ├── sec_about_you.py
│   ├── account_inputs.py
│   ├── sec_income.py
│   ├── sec_taxes.py
│   ├── sec_expenses.py
│   ├── sec_savings.py
│   ├── sec_retirement_goals.py
│   ├── sec_assumptions.py
│   ├── ...
│   ├── hero_metric.py
│   ├── fan_chart.py
│   └── ...
├── utils/
│   ├── config_builder.py     # UI state -> simulator config
│   ├── sim_runner.py         # Cached Monte Carlo wrapper
│   └── formatting.py         # $, %, age helpers
├── styles/theme.css          # Custom CSS
└── run.sh                    # Launcher script
```

## Session State Model

- `st.session_state.user_overrides`: dict of config overrides (keys match `retirement_sim.config`)
- `st.session_state.results`: output of `run_full_analysis` or `None`
- `st.session_state.profile`: name of currently selected profile

## Extending the UI

Each component is a `def render(st, **kwargs):` module. To add a new input, create a file in `components/`, define `render(st)` that reads/writes `st.session_state.user_overrides`, and add it to `ui/app.py`.

## License

MIT — see [`../LICENSE`](../LICENSE).
