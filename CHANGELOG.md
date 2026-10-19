# Changelog

All notable changes to this project will be documented in this file. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Interactive Streamlit UI in `ui/` — financial-advisor-style dashboard with Monte Carlo fan chart, success-by-age visualization, allocation glide path, income-source breakdown, tax analysis, withdrawal strategy, and sensitivity analysis tabs
- Profile presets: median US 25-year-old household, young professional, mid-career couple, near-retirement
- Editable compensation table in the UI (`st.data_editor`)
- Config builder (`ui/utils/config_builder.py`) that translates UI convenience keys into full config overrides
- Launcher script `ui/run.sh` for one-command UI startup

## [0.1.0] - 2026-05-13

Initial public release.

### Added

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
