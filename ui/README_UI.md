# Retirement Monte Carlo — Streamlit UI

> **New to the command line?** See [`../HOW_TO_RUN.md`](../HOW_TO_RUN.md) for a beginner-friendly, step-by-step guide (Windows and Mac).

## Overview

A simple, elegant UI for the retirement Monte Carlo simulator, built with Streamlit and styled after modern personal-finance dashboards. New visitors land on a welcome screen with two starting points, the **Money check-up** (a quick savings, emergency-fund and budget review) and the **Retirement planner**. The planner opens with a short guided setup, then shows a single page: a top bar with your key numbers and the Run button, a linear sidebar of input sections, and results that run automatically and refresh as you edit.

## Main screen

```
+----------------------------------------------------------------+
| Top bar: household | net worth | gross income | target age |     |
|          success rate | [ Run ] | simulations | Settings       |
+--------------+-------------------------------------------------+
| Money check- | EARLIEST RETIREMENT AGE (hero) + key stats      |
| up | Planner | Success rate by retirement age                  |
|--------------| Income | Spending | Savings | Debt payoff | Tax |
|              | What if                                         |
| > About you  | Freedom milestones, portfolio needed to retire, |
| > Family     | life expectancy, withdrawal rate,               |
| > Income     | bridge to 59.5                                  |
| > Taxes      | Deep dives                                      |
| > House      |                                                 |
| > Expenses   |                                                 |
| > Debts      |                                                 |
| > Accounts   |                                                 |
| > Investments|                                                 |
| > Retirement |                                                 |
| > Assumptions|                                                 |
| FAQ          |                                                 |
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

- **Welcome**: pick the *Money check-up* or the *Retirement planner*. A switch at the top of the sidebar moves between them at any time.
- **Guided setup** (planner, first visit): a short series of screens with a "how to answer" line under each question. Check-up answers carry over. *Skip for now* goes straight to the planner, and a banner offers to finish later.
- **Linear sidebar** (one section at a time, in advisor order): About you, Family (children, college), Income, Taxes, House (rent or mortgage, home moves, extra mortgage payments), Expenses (monthly spending, then big purchases and goals: car, retirement vacation), Debts (credit cards, student, car and other loans: balance, APR, minimum; an extra monthly payment; highest rate or smallest balance first; the mortgage stays in House), Accounts (starting balances), Investments (what you save each year, plus returns, stock/bond mix, inflation, glide path and Roth conversion), Retirement (your and your partner's retirement ages, spending, Social Security, success target, early retirement access: Rule of 55, 72(t), Roth ladder, stop saving early), Assumptions (advanced: spending rules and pre-Medicare healthcare). Each section reads and writes `st.session_state.user_overrides`.
- **Top bar**: your household numbers, the **Run** button, the simulation count, and the **Settings** popover (privacy and Remember me, theme, profile presets, Save / Load profile, print summary, export).
- **Results run automatically** when you change an input; Run re-runs on demand. Sections run from most basic to most niche:
  - **Retirement**: the hero metric (earliest retirement age at your target success rate) with a success band (Needs attention under 65%, Fair, Good, Strong from 90%), the success rate as a count of simulated markets, and the spending-guardrail cushion in dollars. Under it, **Ways to reach your goal**: a few changes (retire later, spend less in retirement, a partner who works longer, one year later plus a smaller cut), each its own simulation on the main run's market paths. *Try it* previews one; *Keep this change* writes it into your inputs and reruns, with *Undo*. A plan already above 95% gets *You have room* instead (how much earlier, or how much more spending, still meets your target). Then success rate by retirement age, key stats, and the investable portfolio range over time (*Range + milestones*, the default, *Box plot* or *Point cloud (violin)*; Range + milestones is a median line with 50% and 80% bands and markers for retirement, mortgage payoff, college, 59½, Social Security, RMDs, debts paid off and plan end).
  - **Income** (*Over time*, and below it *Where this year's pay goes*: a Sankey of one working year from pay to taxes, savings and spending, with an age picker), **Spending**, **Savings**, **Debt payoff** (debt-free date, interest, when each debt is paid off, avalanche vs snowball, a pay-more-each-month what-if with a balance chart, a rough effect on retirement, and *Things to know about debt*) and **Tax**.
  - **What if**: the when-can-you-retire curve, lifecycle what-ifs and scenario comparison.
  - **Freedom milestones** (net worth and invested ladders, Coast FIRE and FIRE in places you can edit, and other markers such as the emergency fund, Lean and Barista FIRE; each place has a *Confirm with simulation* button), the portfolio needed to retire, life expectancy, withdrawal rate and bridge to 59.5.
  - **Deep dives** (last): tabs for trajectories, withdrawal, sensitivity, stress tests (a historical replay by start year, then one-click shocks), Roth conversions (a heat map of conversion plans with Use best / Undo) and mortgage paydown.
- **Folding sections**: click or tap any section heading (or press Enter or Space on it) to fold it to its heading; click again to open it. *Collapse all* / *Expand all* sit above the first section. Folding happens in the browser (no rerun) and the browser remembers it across reloads.
- **FAQ**: in the sidebar, for reference while you fill in inputs.

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
│   ├── welcome.py            # first screen
│   ├── guided_setup.py       # first-visit question flow
│   ├── simple_mode.py        # Money check-up
│   ├── top_bar.py
│   ├── profile_picker.py
│   ├── sec_about_you.py
│   ├── sec_family.py
│   ├── account_inputs.py
│   ├── sec_income.py
│   ├── sec_taxes.py
│   ├── sec_house.py
│   ├── sec_expenses.py
│   ├── sec_big_purchases.py     (car, vacation; drawn inside Expenses)
│   ├── sec_savings.py
│   ├── sec_retirement_goals.py
│   ├── sec_early_access.py      (drawn at the end of Retirement)
│   ├── sec_assumptions.py
│   ├── ...
│   ├── hero_metric.py
│   ├── goal_levers.py        (Ways to reach your goal, under the hero)
│   ├── success_by_age.py
│   └── ...
├── utils/
│   ├── config_builder.py     # UI state -> simulator config
│   ├── sim_runner.py         # Cached Monte Carlo wrapper
│   ├── goal_levers.py        # the goal levers as a Plan + the guardrail cushion
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
