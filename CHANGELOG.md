# Changelog

All notable changes to this project will be documented in this file. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Planner sidebar: **Big purchases & goals** (car, retirement vacation) is now the last part of **Expenses**, and **Early retirement access** (Rule of 55, 72(t) payments, Roth ladder, stop saving early) is now the last part of **Retirement**. The two separate sections are gone, so the sidebar reads About you, Family, Income, Taxes, House, Expenses, Accounts, Investments, Retirement, Assumptions (advanced). No setting, widget key or saved-profile value changed.

### Added
- Planner: new **Freedom milestones** section on the results page, right after Retirement. It shows the markers of freedom you pass on the way: net worth and invested ladders ($100K, $250K, $500K, $1M, ...), **Coast FIRE** and **FIRE** in a set of places (US regions and countries abroad), and other markers (6 and 12 months of emergency fund, investments cover the essentials, Barista FIRE, a year of returns pays a year of costs, mortgage paid off). Each is *Reached*, *In progress* with the age and year it arrives, or *Not in this plan*; the next one is highlighted. The test is a quick rule (invested balance against that place's yearly spending divided by a withdrawal rate) that runs with no simulation. Each place has a **Confirm with simulation** button that runs the Monte Carlo with that place's spending and state tax, on the server or in your browser. The built-in places and their cost factors are rough, made-up estimates: edit them, hide them, or add your own. Edits are saved with the profile (Save / Load, Remember me, profile switching) under one new key, `MS_PLACES`; older profiles load unchanged
- Engine: new `RETIREMENT_STATE_CHOICE` setting (default `None` = same as `STATE_CHOICE`, so no existing plan changes). It sets the state whose income tax applies to retirement-year withdrawals, Roth conversions and RMDs, while working years keep `STATE_CHOICE`. The Freedom milestones check uses it to test retiring in another place
- Planner top card: the title moved up beside the Run / simulations / Settings controls, and the *Retirement plan | Spending* switch moved to the bottom right, next to the metrics, in a larger size (56px tall, 17px text). Where it does not fit beside the metrics it takes a full-width line of its own. The card is shorter. Same widgets and keys
- Planner sidebar: new **Investments** section holds everything about growing the money: *Saving each year* (what goes into each account, the four savings modes, Max out buttons, summary figures; this was the Savings section) and *Returns and mix* (return scenario, stock allocation, fees, volatility drag, inflation, glide path, Roth conversion; these came from Assumptions). **Retirement goals** is now just **Retirement**, and **Accounts** moves to just before Investments. Assumptions (advanced) keeps dynamic spending and pre-Medicare healthcare. No setting, widget key or saved-profile value changed.
- Planner sidebar: the **Target retirement age** and **Partner's retirement age** sliders moved from About you to the top of **Retirement goals** (under "When you retire"). Same settings and saved values; the target age still applies before the sections above it are drawn.
- Planner: the *Money check-up | Retirement planner* switch moved to the top of the side panel, above About you, matching the section cards' width. Phones and a closed panel keep the switch at the top of the page
- Planner sidebar: new **Family** section (children and college) and **House** section (rent or mortgage, home moves, extra mortgage payments), each with a short summary line. The controls moved out of Expenses and Big purchases & goals; keys and saved profiles are unchanged
- Interactive Streamlit UI in `ui/` — financial-advisor-style dashboard with Monte Carlo fan chart, success-by-age visualization, allocation glide path, income-source breakdown, tax analysis, withdrawal strategy, and sensitivity analysis tabs
- Profile presets: median US 25-year-old household, young professional, mid-career couple, near-retirement
- Editable compensation table in the UI (`st.data_editor`)
- Config builder (`ui/utils/config_builder.py`) that translates UI convenience keys into full config overrides
- Launcher script `ui/run.sh` for one-command UI startup

## [0.1.0] - 2026-05-13

Initial public release.

### Added
- Planner sidebar: new **Investments** section holds everything about growing the money: *Saving each year* (what goes into each account, the four savings modes, Max out buttons, summary figures; this was the Savings section) and *Returns and mix* (return scenario, stock allocation, fees, volatility drag, inflation, glide path, Roth conversion; these came from Assumptions). **Retirement goals** is now just **Retirement**, and **Accounts** moves to just before Investments. Assumptions (advanced) keeps dynamic spending and pre-Medicare healthcare. No setting, widget key or saved-profile value changed.

- Monte Carlo simulation engine with per-account tracking
- 2024 US federal + California state income tax brackets
- Long-term capital gains tax modeling (federal + state)
- Social Security modeling (FRA, early claiming 62, delayed 70)
- Required Minimum Distribution calculations (SECURE 2.0)
- ACA marketplace premiums with income-based subsidies
- Medicare IRMAA tier calculations
- Net Investment Income Tax (NIIT) for high earners
- Roth conversion strategy during early retirement
- Dynamic spending guardrails (portfolio-performance-based)
- Return-based spending flexibility
- Asset allocation glide path (age-based stock/bond shift)
- Long-term care modeling (disabled by default)
- Category-specific inflation (general, healthcare, housing, childcare)
- Volatility drag adjustment for geometric returns
- Stock/bond return correlation via Cholesky decomposition
- Historical S&P 500 returns (2000-2024) for sequence-of-returns risk
- Example configs for young-professional / mid-career-couple / near-retirement profiles
- Pytest suite covering tax brackets, withdrawals, edge cases
