# Contributing

## Welcome

Thanks for taking the time to contribute! This project is a Monte Carlo
retirement simulator, and it gets better every time someone adds a tax
bracket, fixes an edge case, or clarifies the docs. Contributions of any
size are welcome — bug reports, tests, code, and documentation improvements
all help.

## Getting started

1. Fork the repository on GitHub, then clone your fork:

   ```bash
   git clone https://github.com/<your-username>/<repo>.git
   cd <repo>
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install runtime dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Install the package in editable mode with development dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

5. Run the test suite to confirm your environment is healthy:

   ```bash
   pytest tests/
   ```

Create a feature branch off `main` (e.g. `git checkout -b fix/sep-ira-limits`)
and you're ready to go.

## What we're looking for

High-value contribution areas:

- **Bug fixes** with a reproducer test that fails before the fix and passes after.
- **New tax and account types** — SEP-IRA, SIMPLE IRA, 403(b), 457(b),
  inherited IRAs, solo 401(k), etc.
- **Additional state tax brackets.** Only California is implemented today;
  any US state is fair game.
- **Additional return scenarios** or historical return datasets (e.g.
  country-specific equity/bond series, alternative asset classes).
- **Performance improvements**, especially vectorizing the Monte Carlo loop
  across simulations instead of iterating year-by-year per run.
- **Better visualization utilities** — success-rate plots, withdrawal
  waterfalls, sensitivity charts, interactive notebooks.
- **Documentation improvements** — clearer examples, more thorough API
  docs, tutorials, assumption write-ups.

If you're planning a large change, open an issue first so we can align on
the approach before you invest time.

## Code standards

- **Type hints** on all public functions and class methods.
- **Docstrings** with `Args:` and `Returns:` sections on any non-trivial
  function. Google or NumPy style is fine — just be consistent within a file.
- **Pure functions where possible.** Avoid mutating module-level globals;
  prefer passing configuration in as arguments or using dataclasses.
- **Deterministic simulations.** Any Monte Carlo code must be reproducible
  given a seed. Tests that exercise randomness should call
  `np.random.seed()` (or accept a seeded `np.random.Generator`) so results
  are stable across runs.
- **New tax logic must have dedicated tests** that compare output against a
  reference calculation — IRS worksheets, a state tax authority's published
  tables, or a second independent tool.
- Follow existing formatting. This project uses `ruff` for linting and
  formatting; run it before pushing:

  ```bash
  ruff check . && ruff format --check .
  ```

## Testing guidelines

- Every new tax calculation needs unit tests verifying it against IRS
  published values (or an equivalent authoritative second source for state
  taxes). Cite the source in the test's docstring or a comment.
- Cover the obvious edge cases:
  - zero income / zero balance
  - extreme values (very high income, very large portfolios)
  - age boundaries: **59.5** (early-withdrawal penalty), **65** (Medicare),
    **73** and **75** (RMD start ages), plus whatever boundary your change
    touches
- Use `pytest` fixtures for common scenarios (a representative portfolio, a
  standard household, a known-good tax year) instead of re-building them in
  every test.
- Keep tests fast. If a test needs a full Monte Carlo run, mark it with
  `@pytest.mark.slow` so the default suite stays quick. For the fast local
  loop, run:

  ```bash
  pytest -m "not slow"
  ```

## Pull request process

1. **One logical change per PR.** Split unrelated refactors into their own
   PRs — it makes review faster and bisecting easier later.
2. **Update `CHANGELOG.md`** under the `[Unreleased]` section with a short
   entry describing the user-visible change.
3. **Ensure linting and the full test suite pass locally:**

   ```bash
   ruff check . && ruff format --check .
   pytest tests/
   ```

4. **Link related issues** in the PR description (e.g. `Closes #123`).
5. Write a clear PR description: what changed, why, and how you verified
   it. Include before/after numbers if you're changing simulation results.
6. Expect review feedback — it's how we keep the math trustworthy. Please
   respond to comments rather than force-pushing silently.

## Conduct

Please follow standard open-source etiquette: be kind, assume good faith,
and critique code rather than people. We want this to be a welcoming
project for contributors at any experience level.
