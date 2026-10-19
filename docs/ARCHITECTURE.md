# Architecture

This document explains how the pieces of this repository fit together, and
flags the one coupling that makes `retirement_sim/config.py` riskier to
refactor than it looks. Read this before splitting, renaming, or moving
anything in `retirement_sim/` or `ui/`.

## Engine vs. UI split

The repository has two layers:

- **`retirement_sim/`** — the simulation engine. A plain importable package
  with no UI dependencies: `config.py` (all financial data/parameters, plus
  derived constants computed at import time), `account_simulation.py` (the
  `AccountPortfolio` class and the accumulation/retirement year simulation
  functions), and `historical_returns.py` (optional historical backtesting
  data, not used by the default parametric Monte Carlo).
- **`ui/`** — a Streamlit application that sits on top of the engine.
  `app.py` is the entry point; it adds the project root to `sys.path` so it
  can `import retirement_sim` alongside its own local `components/` (render
  functions) and `utils/` (logic) packages.

The engine has no knowledge of the UI. All coupling runs one direction: `ui/`
imports and drives `retirement_sim/`.

## CRITICAL coupling: `sim_runner.py` monkeypatches `retirement_sim.config`

`ui/utils/sim_runner.py` is the only place the UI calls into the engine. To
let users override financial assumptions from widgets without threading a
config object through every function signature, it takes the shortcut of
mutating the **shared, already-imported** `retirement_sim.config` module in
place:

1. `_apply_overrides(overrides)` iterates the override dict and calls
   `setattr(cfg, key, value)` directly on the `retirement_sim.config` module
   object for every key that already exists on it. It records each
   previous value in an `original` dict as it goes.
2. It then calls `_recompute_derived(original)` (see below) before the sim
   runs, so derived constants reflect the overridden primitives.
3. The simulation runs against `cfg` as global state — `account_simulation.py`
   does `import config as cfg` and reads module attributes at call time, so
   whatever `sim_runner` just `setattr`'d is what the engine sees.
4. `_restore_overrides(original)` is called after the run to `setattr` every
   key back to its pre-override value, returning the shared module to its
   original state for the next caller.

This means **`retirement_sim.config` is treated as global, mutable,
single-threaded state for the duration of one simulation run.** There is no
per-run config object — every UI-triggered simulation temporarily rewrites
the one shared module, runs, then rewrites it back.

### Why this makes `config.py` high-risk to split into submodules

Because overrides are applied via `setattr(cfg, key, value)` where `cfg` is
literally `retirement_sim.config`, every overridable name must be a
**top-level attribute of that one flat module**. If `config.py` were split
into submodules (e.g. `config/accounts.py`, `config/tax.py`,
`config/expenses.py` re-exported through `config/__init__.py`), `setattr`
on the package's `__init__` module would only rebind the re-exported name in
that namespace — it would not update the attribute inside the submodule
where the *rest of the engine* actually reads it from (if any code does
`from .accounts import YOUR_401K` or reads `accounts.YOUR_401K` directly).
Any override would silently stop propagating into the value the simulation
actually uses, and the failure would be silent (no error — just stale
numbers), which is why this class of bug is dangerous.

**Practical consequence:** keep `retirement_sim/config.py` a single flat
module namespace. If it must be split for size/readability reasons in the
future, `sim_runner.py`'s override mechanism needs to be redesigned at the
same time (e.g. to build a fresh config namespace per run, or to walk
submodules), not treated as an independent change.

## `_recompute_derived` mirrors `config.py`'s derived values

`config.py` computes several constants from primitives at import time (e.g.
`MORTGAGE_ANNUAL = MORTGAGE_MONTHLY * 12`, `CURRENT_ANNUAL_EXPENSES`,
`HOME_EQUITY`, `TOTAL_INVESTMENTS`, `TOTAL_NET_WORTH`, `RETIREMENT_ANNUAL_EXPENSES`,
`YOUR_HSA_TOTAL`, `COLLEGE_TARGET_PER_CHILD`). Because those derived values
were already computed once at import time, overriding a primitive via
`setattr` (e.g. changing `MORTGAGE_MONTHLY`) does **not** automatically
recompute the derived constants that depend on it — Python doesn't
re-execute module-level code on attribute assignment.

`ui/utils/sim_runner.py::_recompute_derived` exists specifically to close
that gap: after `_apply_overrides` sets the overridden primitives, it
re-derives each downstream constant by hand, using the same formulas as
`config.py`, and writes them back onto `cfg` so the engine sees consistent
state. It also snapshots the derived constants' prior values into the same
`original` dict so `_restore_overrides` can revert them too. `INFLATION_RATES`
is a special case — it's a dict, so `_recompute_derived` mutates
`INFLATION_RATES["general"]` in place under a synthetic
`"INFLATION_RATES.general"` key (a plain top-level snapshot wouldn't restore
a nested dict entry, since the dict object itself is shared by reference).

**Consequence for maintainers:** every time a derived constant's formula
changes in `config.py`, or a new derived constant is added that depends on
overridable primitives, `_recompute_derived` must be updated to match — the
comments in that function reference specific `config.py` line numbers/formulas
for exactly this reason. The two implementations (the module-level formula in
`config.py`, and the hand-copy in `_recompute_derived`) are not automatically
kept in sync; there's no test that fails if they drift, so treat this as a
manual invariant to check whenever `config.py`'s derived section changes.

## Two-copy situation: `retirement_sim/` (here) vs. the `retirement_model/` sandbox

This packaged directory is
one of **two independent copies** of the simulator that exist side by side in
the parent repository:

| Copy | Role | Import style |
|------|------|---------------|
| `retirement_model/` (sibling directory, outside this package) | Original personal working sandbox: the core model plus many one-off analysis scripts, notebooks, and personal financial data. Flat modules (`config.py`, `account_simulation.py`), imported as `import config`. | Run from inside `retirement_model/`. |
| `retirement_sim/` (this directory) | Cleaned-up, open-source-ready distribution: same core model repackaged as an installable package, with generic/illustrative defaults, docs, examples, tests, and this Streamlit UI. | `from retirement_sim import config, account_simulation`. |

The two copies are **not symlinked and have diverged** — they are separate
files that must be edited independently. A fix or feature added to the
engine logic in one copy does not automatically apply to the other. Active
UI development happens only in this packaged copy; if a change is meant to
affect the model's numeric/logic behavior generally (not just the UI), check
whether it needs to be ported to `retirement_model/` as well, and vice versa.

## See also

- [`README.md`](../README.md) — project overview, quick start, and doc index.
- [`docs/CONFIGURATION.md`](CONFIGURATION.md) — how to edit `config.py` / build custom configs.
- [`docs/METHODOLOGY.md`](METHODOLOGY.md) — simulation methodology.
- [`docs/TAX_MODEL.md`](TAX_MODEL.md) — tax modeling details.
- [`ui/README_UI.md`](../ui/README_UI.md) — Streamlit UI usage.
