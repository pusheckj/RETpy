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
  functions), `debts.py` (the consumer-debt payoff math, shared by the engine,
  the planner's Debts screens and the Money check-up), and
  `historical_returns.py` (optional historical backtesting data, not used by
  the default parametric Monte Carlo).
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

## Overrides that skipped the side panel

The side panel writes a value for every input it draws (the expense boxes, the
employer match, Auto-allocate's contribution amounts, the partner's retirement,
plan-until and claim ages), so a plan that went through it carries them all. A
preset, a test or a script that passes a bare dict to the engine would otherwise
simulate the config's sample values for those instead, and get a different answer
for the same household.

`config_builder.build_config_overrides` closes that gap with one function,
`sidebar_defaults`: for a dict that names its household (`YOUR_AGE` and
`PARTNER_AGE`) it fills what the dict leaves out (a missing key or `None`) with
the side panel's own defaults, through the panel's own helpers
(`expense_categories.expense_defaults`, `household.partner_defaults`,
`derived.auto_allocate_defaults`). It never replaces a value that is there, so a
saved profile (which holds all of them) is unchanged. Core inputs (ages, pay,
balances, the home loan) are not filled; a dict that does not name its household is
a patch on the config's sample household and is left alone. Auto-allocate fills the
contribution amounts only when the dict states none; once any is stated (a saved
profile, a Manual or Keep-my-amounts plan) they are kept. `tests/test_preset_defaults.py`
checks that every preset, run directly, reaches the engine as it does after the side
panel drew it.

Where a default existed in two places they now agree in one: the glide path starts at
`cfg.GLIDE_PATH_START_STOCK_PCT` (80%, the accumulation mix) in the side panel as well
as in the config.

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
`YOUR_HSA_TOTAL`). Because those derived values
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

## Simulation work as plans: server, fork pool, or the visitor's browser

Every heavy analysis in `utils/sim_runner.py` (`plan_full_analysis`,
`plan_networth_analysis`, `plan_swr_analysis`, `plan_mortgage_paydown`) is a
`Plan`: a job of independent, seeded engine calls plus a `finish` step.

- The job format lives engine-side in `retirement_sim/mc_jobs.py`:
  `{"base": config snapshot, "patches": [config diffs], "calls": [[fn, patch, args]]}`,
  carried as JSON (`dumps`/`loads` tag tuples, int-keyed dicts and inf/nan).
- Each call seeds its own RNG, so any mix of executors gives identical results:
  this process, its fork pool (`_run_calls`), or the visitor's browser. Inside
  a call every simulated path restarts its own stream: path `i` of a run is
  seeded `mc_jobs.PATH_SEED + i` (`account_simulation.path_seed`). So how a run
  is split into chunks doesn't matter, a small input change only moves the paths
  it really tips, and the target-age run, the age scan and the FI / SWR sweep
  points all replay the same market paths (common random numbers).
- `retirement_sim.mc_jobs.scan_age` stops early at ages far from the target, so
  the success-by-age curve costs about half as much. The ages near the target,
  which decide the earliest age, always get every run.
- `utils/browser_compute.py` hands calls to `components/browser_compute/`: a
  hidden component running Pyodide in Web Workers, with the engine sources sent
  from the server.
- The main result's detailed calls (`Plan.local`) always run on the server. Its
  age scan goes to the browser only when the workers are already loaded.
- The follow-up analyses (levers, what-if baseline, FI, SWR, mortgage) go to the
  browser when it is up. Otherwise they go to a background process pool
  (`sim_runner.submit_plan_bg`). The pool starts its workers with `forkserver`
  (`spawn` where a local socket is not allowed), never by forking the threaded
  Streamlit process, and lowers their priority. Each task runs `mc_jobs.run_local`,
  which applies the plan's own config snapshot, so no `CONFIG_LOCK` is held while
  the workers compute.
  Nothing polls. When a chunk finishes, a pool thread pokes the session's waker
  (`utils/session_wake.py`). Every rerun redraws the page, so it waits until every
  pending plan is ready, or 20 seconds after the first one is, and then asks Streamlit
  for one rerun of the session, the same request `st.rerun()` makes: no widget state of its own, so
  it merges with a visitor's pending edit and never drops it. It waits while the
  visitor's own run is going. The rerun's first step, `app._drain_extras`, stores
  finished plans through `drain_bg`. The waker reaches Streamlit's session object,
  which has no public handle; when it cannot (another Streamlit version) the
  analyses run as in the next sentence. `_begin_run` and a profile switch cancel
  pending chunks, and `_begin_run` bumps `_extras_gen`, so a late result from old
  inputs is dropped. With `RETIREMENT_SIM_BG_EXTRAS=0`, or if the pool cannot
  start, they run on the script thread through `app._server_extras_step` (one per
  run, after the page is drawn).
- The on-load run (`app._autorun_all`) sets its once-only guard when the run
  ends, not before. Streamlit stops a script for a newer run (the browser workers
  report loading progress, and each report reruns the script), and a run stopped
  that way must start again.
- Replies are untrusted input: JSON only, size-capped, sanity-checked. Anything
  unusable, failed or past its deadline is run by the server.
- Messages are acknowledged (`{boot, seq}` / `ack`), because Streamlit keeps
  only a component's latest value.

## Charts and caches that hold user data in memory

- **One chart per screen.** `plot_theme.show_chart` reads `st.session_state["_viewport_narrow"]`.
  The browser sets it from `plot_theme.NARROW_VIEWPORT_QUERY` (`max-width: 1130px`).
  The query covers phones and the tablet band where the side panel leaves a 520-700 px main pane.
  Once the key is set, only one chart is drawn, so no CSS can swap it. A CSS rule that shows the
  compact `mc-narrow-` chart must stay inside the query. `tests/test_narrow_contract.py` checks this.
- **Per-session figure memo.** `st.session_state["_fig_cache"]` keeps up to 48 styled figures.
  They die with the session.
- **Shared Freedom memo.** `utils/milestones._BUILD_MEMO` is one dictionary per server process.
  It keeps the inputs and results of the last 32 plans, so on a hosted server they stay in memory
  after those visitors leave. It is never written to disk. It holds no names or account numbers,
  only the numbers and place choices of a plan. A server restart clears it.

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
