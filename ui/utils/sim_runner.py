"""Cached Monte Carlo runner for the UI.

Wraps ``retirement_sim.account_simulation.run_monte_carlo_detailed`` to:
1. Apply user overrides onto the shared config module.
2. Run Monte Carlo at a TARGET retirement age and scan a range of ages.
3. Return a structured dict consumable by the UI components.
4. Cache results (keyed on hashable overrides) via ``functools.lru_cache``.
"""
from __future__ import annotations

import logging
import os
import threading
import concurrent.futures as _cf
import multiprocessing as _mp
from typing import Any, Dict, List, Tuple, TypedDict

import numpy as np

# app.py is responsible for putting the project root on sys.path before importing us.
from retirement_sim import account_simulation as sim
from retirement_sim import config as cfg
from retirement_sim import mc_parallel as _mcp

from utils.config_builder import build_config_overrides
from utils.config_builder import _UI_ONLY_KEYS as _BUILDER_UI_ONLY_KEYS

# Single source of truth for the lifecycle-preset -> {category: {age: mult}}
# mapping (finding #11). Reused so the ENGINE honors the exact same pattern the
# spending chart renders, instead of re-deriving it.
from components.spending_inputs import compute_lifecycle_multipliers as _compute_lifecycle_multipliers

logger = logging.getLogger(__name__)

# The engine reads one shared ``retirement_sim.config`` module, and a run works by
# writing the user's inputs onto it (_apply_overrides) and putting the originals
# back afterwards (_restore_overrides). Streamlit serves every visitor from one
# process, so two overlapping runs would compute one person's plan with the
# other's inputs. CONFIG_LOCK is held from each apply to its matching restore
# (re-entrant, so nested runs in one thread are fine); app.py also holds it for
# every script and fragment rerun, because the UI reads cfg defaults too.
CONFIG_LOCK = threading.RLock()


# =============================================================================
# Override-wiring guard (root cause of the inert-control class)
#
# ``_apply_overrides`` only writes a key onto ``cfg`` when ``hasattr(cfg, key)``
# is true. Any override key that is neither declared on ``cfg`` nor a
# legitimately UI-only key is therefore SILENTLY DROPPED — the control looks
# wired in the UI but never reaches the Monte Carlo engine. That silent no-op
# is the shared mechanism behind the inert-control findings (filing status,
# retirement-spending mode, rent, spending-lifecycle preset, ...).
#
# ``UI_ONLY_KEYS`` enumerates the keys that are *intentionally* consumed before
# ``cfg`` (translated / dropped inside ``build_config_overrides``) and so must
# NOT be flagged. ``audit_override_keys`` returns every remaining key that a
# fresh ``cfg`` does not declare, so callers/tests can fail fast on new inert
# controls instead of silently no-op'ing.
# =============================================================================

# Keys that live only in UI state (translated or consumed before they would
# reach ``cfg``) and so are legitimately absent from the config module. Seeded
# from ``config_builder._UI_ONLY_KEYS`` (the single source of truth for the
# translation layer) and extended with any additional pure-UI-state keys.
UI_ONLY_KEYS: frozenset = frozenset(_BUILDER_UI_ONLY_KEYS) | frozenset({
    # (none beyond the builder set today — kept explicit for future additions,
    #  e.g. theme / active-profile selectors that never map onto cfg.)
})


def audit_override_keys(built_overrides: dict) -> List[str]:
    """Return override keys that would be silently dropped by ``_apply_overrides``.

    A key is "dropped" when it is neither a legitimately UI-only key nor a real
    attribute on a fresh ``cfg``. Such keys are genuine inert controls: the UI
    sets them but the engine never reads them.

    ``built_overrides`` should be the output of ``build_config_overrides`` (i.e.
    after the UI->config translation layer has run).
    """
    return sorted(
        key
        for key in built_overrides
        if key not in UI_ONLY_KEYS and not hasattr(cfg, key)
    )


# =============================================================================
# Chart row TypedDicts
#
# These document the per-year dict shapes returned by the "best-effort
# per-year annotations" helpers below (``_approximate_income_sources``,
# ``_compute_allocation_by_year``, ``_approximate_savings_contributions``,
# ``_approximate_taxes``). They exist purely for readability/IDE support —
# the functions still build and return plain ``dict`` instances at runtime,
# so this is a documentation/type-hint-only addition with no behavior change.
# =============================================================================

class IncomeSourceYearRow(TypedDict):
    """One row of ``income_sources_by_year`` (see ``_approximate_income_sources``)."""
    age: int
    ss: float
    traditional: float
    roth: float
    taxable: float
    hsa: float
    # finding #14 — Roth-conversion TRANSFER (traditional -> Roth), not
    # spending/income. Kept as its own field so chart code can render it as a
    # clearly-labeled band/line distinct from the withdrawal/income series
    # above (none of which include it) rather than have it silently vanish.
    roth_conversion: float


class AllocationYearRow(TypedDict):
    """One row of ``allocation_by_year`` (see ``_compute_allocation_by_year``)."""
    age: int
    stock_pct: float
    bond_pct: float


class SavingsContributionYearRow(TypedDict):
    """One row of ``savings_contributions_by_year`` (see ``_approximate_savings_contributions``)."""
    age: int
    your_401k: float
    your_employer_match: float
    your_hsa: float
    your_roth: float
    your_aftertax_roth: float
    your_brokerage: float
    partner_401k: float
    partner_roth: float
    partner_brokerage: float
    # Household income that year, for the savings-rate chart. gross_income is
    # pre-tax total comp (you) + partner salary; after_tax_income is take-home.
    # Both drop when a partner has retired early (their income is zeroed).
    gross_income: float
    after_tax_income: float


class TaxYearRow(TypedDict):
    """One row of ``taxes_by_year`` (see ``_approximate_taxes``)."""
    age: int
    federal: float
    state: float
    ltcg: float
    niit: float
    gross_income: float


# =============================================================================
# Overrides management
# =============================================================================

def _apply_overrides(overrides: dict) -> dict:
    """Apply overrides onto the shared config module. Return the previous values.

    Takes CONFIG_LOCK and keeps it until the matching _restore_overrides, so
    callers must pair the two (try/finally), as every caller here does."""
    CONFIG_LOCK.acquire()
    try:
        return _write_overrides(overrides)
    except BaseException:
        CONFIG_LOCK.release()
        raise


def _write_overrides(overrides: dict) -> dict:
    """Unlocked body of _apply_overrides."""
    # Root-cause guard: warn (do not crash) about any override that will be
    # silently dropped because it is neither UI-only nor a real cfg attribute.
    dropped = audit_override_keys(overrides)
    if dropped:
        logger.warning(
            "sim_runner: %d override key(s) silently dropped (not on cfg, not UI-only) "
            "and will NOT reach the Monte Carlo engine: %s",
            len(dropped),
            ", ".join(dropped),
        )

    original: dict = {}
    for key, value in overrides.items():
        if hasattr(cfg, key):
            original[key] = getattr(cfg, key)
            setattr(cfg, key, value)

    # Then, recompute derived values so downstream sim sees consistent state
    _recompute_derived(original)
    return original


def _recompute_derived(original: dict) -> None:
    """Recompute every derived constant on cfg. Snapshot originals into `original` so we can restore.

    COUPLING WARNING: the formulas below are a hand-maintained MIRROR of the
    derived-value calculations in ``config.py`` (each block cites the
    ``config.py`` line it mirrors, e.g. "config.py:608"). They must be kept
    in sync manually — this module does not import or call config.py's
    derivation logic, it duplicates it so overrides can be recomputed without
    re-importing/reloading the whole config module. Whenever a derivation
    formula in ``config.py`` changes (new inputs, changed multipliers, a
    renamed source attribute, etc.), the corresponding block here MUST be
    updated to match, or UI-driven overrides will silently compute stale/
    incorrect derived values while a fresh run of config.py would be correct.
    """
    derived_keys = [
        "MORTGAGE_ANNUAL", "UTILITIES_ANNUAL", "YOUR_OTHER_ANNUAL",
        "PARTNER_ANNUAL_SPENDING", "CURRENT_ANNUAL_EXPENSES",
        "HOME_EQUITY", "BASE_RETIREMENT_EXPENSES_NO_MORTGAGE",
        "RETIREMENT_ANNUAL_EXPENSES", "YOUR_HSA_TOTAL",
        "COLLEGE_TARGET_PER_CHILD", "SAVINGS_529_PER_CHILD_ANNUAL",
        "TOTAL_RETIREMENT_ACCOUNTS", "TOTAL_TAXABLE", "TOTAL_CASH",
        "TOTAL_INVESTMENTS", "TOTAL_NET_WORTH",
        # Bond partners derived from their stock-allocation knobs (finding #1).
        "BOND_ALLOCATION",
        "GLIDE_PATH_START_BOND_PCT", "GLIDE_PATH_END_BOND_PCT",
        # Return-scenario parameters copied from the active scenario (finding #2).
        "EXPECTED_STOCK_RETURN", "EXPECTED_BOND_RETURN",
        "STOCK_VOLATILITY", "BOND_VOLATILITY",
        # Annual child costs derived from the monthly overrides (finding #5).
        "FIRST_CHILD_ANNUAL_COST", "BOTH_CHILDREN_ANNUAL_COST",
        # Annual health premiums derived from the monthly overrides (finding #12).
        "ACA_BASE_ANNUAL_PREMIUM", "MEDICARE_ANNUAL_PREMIUM",
        # Lifecycle multiplier dict derived from the preset name (finding #11).
        "SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE",
        # Birth years (and the primary's RMD start age) follow from age.
        "YOUR_BIRTH_YEAR", "PARTNER_BIRTH_YEAR", "RMD_START_AGE",
    ]
    for k in derived_keys:
        if k not in original and hasattr(cfg, k):
            original[k] = getattr(cfg, k)

    # Now recompute
    if hasattr(cfg, "MORTGAGE_MONTHLY"):
        cfg.MORTGAGE_ANNUAL = cfg.MORTGAGE_MONTHLY * 12
    if hasattr(cfg, "UTILITIES_MONTHLY"):
        cfg.UTILITIES_ANNUAL = cfg.UTILITIES_MONTHLY * 12
    if hasattr(cfg, "YOUR_OTHER_MONTHLY"):
        cfg.YOUR_OTHER_ANNUAL = cfg.YOUR_OTHER_MONTHLY * 12
    if hasattr(cfg, "PARTNER_MONTHLY_SPENDING"):
        cfg.PARTNER_ANNUAL_SPENDING = cfg.PARTNER_MONTHLY_SPENDING * 12
    if hasattr(cfg, "HOME_VALUE") and hasattr(cfg, "MORTGAGE_BALANCE"):
        cfg.HOME_EQUITY = cfg.HOME_VALUE - cfg.MORTGAGE_BALANCE
    # Non-housing living-expense base: prefer the granular SPEND_* categories when
    # any are present (so editing them in the Expenses section flows into the sim),
    # otherwise fall back to the legacy YOUR_OTHER / UTILITIES bundle. Mirrors
    # config.granular_nonhousing_annual() so UI overrides and a fresh config agree.
    granular_base = None
    granular_fn = getattr(cfg, "granular_nonhousing_annual", None)
    if callable(granular_fn):
        granular_base = granular_fn()
    if granular_base is not None:
        if hasattr(cfg, "MORTGAGE_ANNUAL"):
            cfg.CURRENT_ANNUAL_EXPENSES = cfg.MORTGAGE_ANNUAL + granular_base
        cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE = granular_base
    else:
        # CONSERVATION (#18d): the household EXPENSE totals must use
        # PARTNER_OTHER_MONTHLY (the knob granular_nonhousing_annual() /
        # CURRENT_ANNUAL_EXPENSES / BASE_RETIREMENT_EXPENSES_NO_MORTGAGE actually
        # consume), NOT PARTNER_MONTHLY_SPENDING (which is the partner-savings-math
        # knob). The two default to the same value today, but overriding only
        # PARTNER_OTHER_MONTHLY (the expense knob) previously left this legacy
        # fallback silently using the stale PARTNER_MONTHLY_SPENDING.
        if hasattr(cfg, "MORTGAGE_ANNUAL") and hasattr(cfg, "UTILITIES_ANNUAL") and hasattr(cfg, "YOUR_OTHER_ANNUAL") and hasattr(cfg, "PARTNER_OTHER_MONTHLY"):
            cfg.CURRENT_ANNUAL_EXPENSES = cfg.MORTGAGE_ANNUAL + cfg.UTILITIES_ANNUAL + cfg.YOUR_OTHER_ANNUAL + (cfg.PARTNER_OTHER_MONTHLY * 12)
        if hasattr(cfg, "YOUR_OTHER_ANNUAL") and hasattr(cfg, "UTILITIES_ANNUAL") and hasattr(cfg, "PARTNER_OTHER_MONTHLY"):
            cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE = cfg.YOUR_OTHER_ANNUAL + cfg.UTILITIES_ANNUAL + (cfg.PARTNER_OTHER_MONTHLY * 12)
    # config.py:608 — RETIREMENT_ANNUAL_EXPENSES = BASE_RETIREMENT_EXPENSES_NO_MORTGAGE.
    # Route through cfg.retirement_living_base() so the RETIREMENT_SPENDING_MODE
    # (% of today / absolute / same) is reflected in this display constant too
    # (finding #7). The engine derives its own base via calculate_annual_expenses
    # (retirement=True); this keeps the snapshot value consistent with it.
    if hasattr(cfg, "BASE_RETIREMENT_EXPENSES_NO_MORTGAGE"):
        living_base_fn = getattr(cfg, "retirement_living_base", None)
        if callable(living_base_fn):
            cfg.RETIREMENT_ANNUAL_EXPENSES = living_base_fn()
        else:
            cfg.RETIREMENT_ANNUAL_EXPENSES = cfg.BASE_RETIREMENT_EXPENSES_NO_MORTGAGE
    # config.py:165 — YOUR_HSA_TOTAL = YOUR_HSA_CONTRIBUTION + YOUR_HSA_MATCH
    if hasattr(cfg, "YOUR_HSA_CONTRIBUTION") and hasattr(cfg, "YOUR_HSA_MATCH"):
        cfg.YOUR_HSA_TOTAL = cfg.YOUR_HSA_CONTRIBUTION + cfg.YOUR_HSA_MATCH
    # config.py:417 — COLLEGE_TARGET_PER_CHILD = COLLEGE_ANNUAL_COST * COLLEGE_YEARS * COLLEGE_FUNDING_PCT
    if hasattr(cfg, "COLLEGE_ANNUAL_COST") and hasattr(cfg, "COLLEGE_YEARS") and hasattr(cfg, "COLLEGE_FUNDING_PCT"):
        cfg.COLLEGE_TARGET_PER_CHILD = cfg.COLLEGE_ANNUAL_COST * cfg.COLLEGE_YEARS * cfg.COLLEGE_FUNDING_PCT
        # config.py:565 — SAVINGS_529_PER_CHILD_ANNUAL = COLLEGE_TARGET_PER_CHILD / 18.
        # Without recomputing this, overriding COLLEGE_FUNDING_PCT updated the
        # target but left the annual 529 contribution stale (0) — so enabling
        # college funding in the UI produced ZERO simulated 529 savings.
        cfg.SAVINGS_529_PER_CHILD_ANNUAL = cfg.COLLEGE_TARGET_PER_CHILD / 18.0

    # finding #1 (PHANTOM LEVERAGE) — the UI exposes only the STOCK side of each
    # allocation pair; the engine reads STOCK_ALLOCATION *and* BOND_ALLOCATION
    # (account_simulation.py:1853-1857) and the glide-path stock/bond pairs
    # (config.py:1517-1518). If a stock knob is overridden but its bond partner
    # is left at the config default, stock+bond no longer sums to 1.0 and the
    # engine silently invests >100% (e.g. STOCK_ALLOCATION=1.0 + default
    # BOND_ALLOCATION=0.20 = 120% invested). Derive each bond partner as
    # 1 - stock (clamped to [0,1]) so the sleeves always sum to 1.0.
    _clamp01 = lambda x: max(0.0, min(1.0, x))
    if hasattr(cfg, "STOCK_ALLOCATION"):
        cfg.BOND_ALLOCATION = _clamp01(1.0 - cfg.STOCK_ALLOCATION)
    if hasattr(cfg, "GLIDE_PATH_START_STOCK_PCT"):
        cfg.GLIDE_PATH_START_BOND_PCT = _clamp01(1.0 - cfg.GLIDE_PATH_START_STOCK_PCT)
    if hasattr(cfg, "GLIDE_PATH_END_STOCK_PCT"):
        cfg.GLIDE_PATH_END_BOND_PCT = _clamp01(1.0 - cfg.GLIDE_PATH_END_STOCK_PCT)

    # finding #2 (RETURN SCENARIO) — the Conservative/Historical/Pessimistic
    # dropdown sets ACTIVE_RETURN_SCENARIO, but the engine reads the static
    # EXPECTED_STOCK_RETURN / EXPECTED_BOND_RETURN / STOCK_VOLATILITY /
    # BOND_VOLATILITY globals (account_simulation.py:149-179), not
    # get_return_parameters(). Copy the active scenario's parameters into those
    # globals so flipping the dropdown actually moves the Monte Carlo. Uses
    # cfg.get_return_parameters (config.py:796) — the single source of truth for
    # the scenario dict keys (stock_return/bond_return/stock_volatility/
    # bond_volatility) — so this stays in sync if a scenario is retuned.
    get_params = getattr(cfg, "get_return_parameters", None)
    if hasattr(cfg, "ACTIVE_RETURN_SCENARIO") and callable(get_params):
        params = get_params(cfg.ACTIVE_RETURN_SCENARIO)
        cfg.EXPECTED_STOCK_RETURN = params["stock_return"]
        cfg.EXPECTED_BOND_RETURN = params["bond_return"]
        cfg.STOCK_VOLATILITY = params["stock_volatility"]
        cfg.BOND_VOLATILITY = params["bond_volatility"]

    # finding #5 (CHILD COSTS) — the child-cost sliders set the *_MONTHLY_COST
    # overrides, but calculate_child_expenses (config.py:495-504) reads the
    # *_ANNUAL_COST derived constants. Mirror config.py:468/472 so the sliders
    # actually feed the engine.
    # config.py — YOUR_BIRTH_YEAR / PARTNER_BIRTH_YEAR = CURRENT_YEAR - age, and
    # RMD_START_AGE = get_rmd_start_age(YOUR_BIRTH_YEAR).
    cfg.YOUR_BIRTH_YEAR = int(cfg.CURRENT_YEAR) - int(cfg.YOUR_AGE)
    cfg.PARTNER_BIRTH_YEAR = int(cfg.CURRENT_YEAR) - int(cfg.PARTNER_AGE)
    cfg.RMD_START_AGE = cfg.get_rmd_start_age(cfg.YOUR_BIRTH_YEAR)

    if hasattr(cfg, "FIRST_CHILD_MONTHLY_COST"):
        cfg.FIRST_CHILD_ANNUAL_COST = cfg.FIRST_CHILD_MONTHLY_COST * 12
    if hasattr(cfg, "BOTH_CHILDREN_MONTHLY_COST"):
        cfg.BOTH_CHILDREN_ANNUAL_COST = cfg.BOTH_CHILDREN_MONTHLY_COST * 12

    # finding #12 (HEALTH PREMIUMS) — calculate_aca_premium / the Medicare cost
    # path read the *_ANNUAL_PREMIUM derived constants (config.py:1445/1462),
    # not the *_MONTHLY_PREMIUM overrides. Mirror config.py:1307/1332.
    if hasattr(cfg, "ACA_BASE_MONTHLY_PREMIUM"):
        cfg.ACA_BASE_ANNUAL_PREMIUM = cfg.ACA_BASE_MONTHLY_PREMIUM * 12
    if hasattr(cfg, "MEDICARE_MONTHLY_PREMIUM"):
        cfg.MEDICARE_ANNUAL_PREMIUM = cfg.MEDICARE_MONTHLY_PREMIUM * 12

    # finding #11 (SPENDING LIFECYCLE PRESET) — the UI writes only the preset
    # NAME (SPEND_LIFECYCLE_PRESET); the per-age multiplier dict the engine
    # consumes (cfg.SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE) is derived live in the UI
    # via compute_lifecycle_multipliers. Recompute it here from the SAME helper
    # so the engine honors the exact pattern the spending chart shows. Reuses the
    # UI helper (single source of truth for the preset -> multiplier mapping).
    if hasattr(cfg, "SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE"):
        preset = str(getattr(cfg, "SPEND_LIFECYCLE_PRESET", "Flat (no change)"))
        cfg.SPEND_LIFECYCLE_MULTIPLIERS_BY_AGE = _compute_lifecycle_multipliers(
            preset=preset,
            current_age=int(getattr(cfg, "YOUR_AGE", 25)),
            retirement_age=int(getattr(cfg, "YOUR_AGE", 25)),
            plan_until_age=int(getattr(cfg, "PLAN_UNTIL_AGE", 90)),
            years_until_first_child=int(getattr(cfg, "YEARS_UNTIL_FIRST_CHILD", 99)),
            child_leaves_home_age=int(getattr(cfg, "CHILD_LEAVES_HOME_AGE", 18)),
        )

    # Totals
    acct_retirement_keys = ["YOUR_401K", "YOUR_ROTH_IRA", "YOUR_TRADITIONAL_IRA", "YOUR_HSA", "PARTNER_401K", "PARTNER_ROTH_IRA"]
    if all(hasattr(cfg, k) for k in acct_retirement_keys):
        cfg.TOTAL_RETIREMENT_ACCOUNTS = sum(getattr(cfg, k) for k in acct_retirement_keys)
    if hasattr(cfg, "YOUR_BROKERAGE") and hasattr(cfg, "PARTNER_BROKERAGE"):
        cfg.TOTAL_TAXABLE = cfg.YOUR_BROKERAGE + cfg.PARTNER_BROKERAGE
    if hasattr(cfg, "YOUR_CASH") and hasattr(cfg, "PARTNER_CASH"):
        cfg.TOTAL_CASH = cfg.YOUR_CASH + cfg.PARTNER_CASH
    if hasattr(cfg, "TOTAL_RETIREMENT_ACCOUNTS") and hasattr(cfg, "TOTAL_TAXABLE") and hasattr(cfg, "TOTAL_CASH"):
        cfg.TOTAL_INVESTMENTS = cfg.TOTAL_RETIREMENT_ACCOUNTS + cfg.TOTAL_TAXABLE + cfg.TOTAL_CASH
    if hasattr(cfg, "TOTAL_INVESTMENTS") and hasattr(cfg, "HOME_EQUITY"):
        cfg.TOTAL_NET_WORTH = cfg.TOTAL_INVESTMENTS + cfg.HOME_EQUITY

    # An EXPECTED_INFLATION override (the slider) must propagate into the already-built
    # INFLATION_RATES dict so general CPI stays the single source of truth. Snapshot the
    # prior nested value under a sentinel key so _restore_overrides can revert it (the
    # dict object itself is shared by reference, so a top-level snapshot won't restore it).
    if hasattr(cfg, "INFLATION_RATES") and hasattr(cfg, "EXPECTED_INFLATION"):
        if "INFLATION_RATES.general" not in original:
            original["INFLATION_RATES.general"] = cfg.INFLATION_RATES["general"]
        cfg.INFLATION_RATES["general"] = cfg.EXPECTED_INFLATION


def _restore_overrides(original: dict) -> None:
    """Put back the values _apply_overrides replaced, then release CONFIG_LOCK."""
    try:
        for key, value in original.items():
            if key == "INFLATION_RATES.general":
                cfg.INFLATION_RATES["general"] = value
            else:
                setattr(cfg, key, value)
    finally:
        CONFIG_LOCK.release()


def _freeze(value: Any) -> Any:
    """Recursively convert a value into a hashable form."""
    if isinstance(value, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze(v) for v in value))
    return value


def _hashable(overrides: dict) -> tuple:
    """Flatten a (possibly deeply-nested) dict into a hashable tuple for cache keys."""
    return tuple(sorted((k, _freeze(v)) for k, v in overrides.items()))


# ---------------------------------------------------------------------------
# Disk tier (see utils/disk_cache.py). Wrapped in try/except at every call so a
# missing/broken cache degrades to plain recompute and never breaks a run.
# ---------------------------------------------------------------------------

def _disk():
    try:
        from utils import disk_cache
    except ImportError:  # pragma: no cover - unusual sys.path layouts
        try:
            from ui.utils import disk_cache  # type: ignore
        except ImportError:
            return None
    return disk_cache


def _disk_key(kind: str, key) -> "str | None":
    d = _disk()
    if d is None:
        return None
    try:
        return d.stable_key(kind, key)
    except Exception:
        return None


def _disk_load(dk: "str | None"):
    d = _disk()
    if d is None or dk is None:
        return None
    try:
        return d.load(dk)
    except Exception:
        return None


def _disk_store(dk: "str | None", value) -> None:
    d = _disk()
    if d is None or dk is None or value is None:
        return
    try:
        d.store(dk, value)
    except Exception:
        pass


# =============================================================================
# Public API
# =============================================================================

def run_full_analysis(
    user_overrides: dict,
    n_simulations: int = 1000,
    target_retirement_age: int = 55,
    scan_age_range: tuple = (25, 76, 1),
    progress_callback=None,
) -> Dict[str, Any]:
    """Run the full simulation suite for the UI.

    Scans retirement ages (lighter sim count) to build a success-by-age curve,
    then runs the full Monte Carlo at the target age to gather trajectories
    and detailed annual breakdowns.

    ``progress_callback`` (optional) is invoked as ``callback(fraction, message)``
    during a fresh compute. It is deliberately NOT part of the cache key: a cache
    hit returns instantly and simply skips the progress calls.
    """
    key = (_hashable(user_overrides), n_simulations, target_retirement_age, tuple(scan_age_range))
    return _CACHE.get_or_compute(
        key, user_overrides, n_simulations, target_retirement_age, scan_age_range,
        progress_callback=progress_callback,
    )


# Manual LRU cache: ``functools.lru_cache`` requires all arguments hashable
# (dicts are not), so we keep the user-facing signature ergonomic and maintain
# our own bounded LRU keyed on a pre-flattened tuple.
class _SimCache:
    def __init__(self, maxsize: int = 32):
        self.maxsize = maxsize
        self._data: Dict[tuple, Dict[str, Any]] = {}
        self._order: List[tuple] = []

    def get_or_compute(self, key, overrides, n_sims, target_age, scan_range, progress_callback=None):
        if key in self._data:
            # Refresh LRU order. A cache hit returns instantly, so the progress
            # callback is intentionally never invoked here (nor is it part of
            # the cache key).
            self._order.remove(key)
            self._order.append(key)
            return self._data[key]

        # Disk tier: survives a process restart (Streamlit reloads the whole
        # process on any UI-file edit, which used to throw away every result).
        dk = _disk_key("full", key)
        result = _disk_load(dk)
        if result is None:
            result = _compute_full_analysis(
                overrides, n_sims, target_age, scan_range, progress_callback=progress_callback
            )
            _disk_store(dk, result)

        self._data[key] = result
        self._order.append(key)
        if len(self._order) > self.maxsize:
            oldest = self._order.pop(0)
            self._data.pop(oldest, None)
        return result

    def clear(self):
        self._data.clear()
        self._order.clear()


_CACHE = _SimCache()

# Separate small cache for the net-worth ("FI number") sweep, keyed on frozen
# overrides + sim count + work cap.
_NW_CACHE: Dict[tuple, Any] = {}

# Separate small cache for the safe-withdrawal-rate sweep.
_SWR_CACHE: Dict[tuple, Any] = {}


def clear_cache(include_disk: bool = True) -> None:
    """Clear the cached simulation results (call after editing the underlying model).

    Clears the persisted tier too by default. Note the disk tier is already
    salted with a fingerprint of the engine source, so an actual model edit
    invalidates it automatically -- this is for the explicit "recompute
    everything now" case.
    """
    _CACHE.clear()
    _NW_CACHE.clear()
    _SWR_CACHE.clear()
    if include_disk:
        d = _disk()
        if d is not None:
            try:
                d.clear()
            except Exception:
                pass


def run_networth_analysis(
    user_overrides: dict,
    n_simulations: int = 1000,
    max_work_age: int = 70,
    progress_callback=None,
) -> Dict[str, Any]:
    """Find the investable net worth at which the household can stop working.

    Sweeps candidate portfolio targets; for each, ``run_monte_carlo_networth``
    simulates working until the investable balance first hits the target (or the
    work cap), then retiring. Returns the ``fi_number`` (smallest target meeting
    ``TARGET_SUCCESS_RATE``, interpolated between grid points), the typical age it
    is reached, the success-vs-net-worth curve, and today's investable balance.
    """
    key = (_hashable(user_overrides), int(n_simulations), int(max_work_age))
    if key in _NW_CACHE:
        return _NW_CACHE[key]
    _dk = _disk_key("networth", key)
    _hit = _disk_load(_dk)
    if _hit is not None:
        _NW_CACHE[key] = _hit
        return _hit

    original = _apply_overrides(build_config_overrides(user_overrides))
    try:
        target = float(getattr(cfg, "TARGET_SUCCESS_RATE", 0.80))
        current_inv = float(sim.create_initial_portfolio().get_investable_balance())
        exp = float(getattr(cfg, "CURRENT_ANNUAL_EXPENSES", 100_000) or 100_000)
        # Sweep from "retire right now" (today's investable balance) upward. Starting
        # at current_inv — rather than an arbitrary 0.9*current_inv floor — means an
        # already-FI household is detected honestly (grid[0] = retire-now) instead of
        # being pinned to a fabricated floor figure below their own balance.
        lo = max(0.0, current_inv)
        hi = max(lo * 1.5, 45.0 * exp, lo + 1_000_000.0)
        grid = list(np.linspace(lo, hi, 14))
        # Cap the per-point sim count so the (serial) sweep stays responsive even
        # when the main selector is set high (e.g. 25k) — precision past ~1k/point
        # is dwarfed by the grid spacing anyway.
        scan_sims = max(300, min(int(n_simulations), 3000) // 3)

        curve: List[dict] = []
        for i, N in enumerate(grid):
            r = sim.run_monte_carlo_networth(N, n_simulations=scan_sims,
                                             max_work_age=max_work_age, random_seed=3000 + i)
            curve.append({
                "networth": float(N),
                "success": float(r["success_rate"]),
                "median_retire_age": r["median_retire_age"],
                "p10_retire_age": r["p10_retire_age"],
                "p90_retire_age": r["p90_retire_age"],
            })
            if progress_callback:
                progress_callback((i + 1) / len(grid), f"Net-worth target ${N/1e6:.1f}M")

        # FI number = smallest target meeting the plan threshold. Two guards vs.
        # naive first-crossing: (1) if retiring today already clears the target the
        # household is already FI (don't report a target above their balance); (2)
        # a crossing must be *confirmed* by the next grid point (or be the last),
        # so a single upward-noisy point on a flat curve can't understate the number.
        already_fi = bool(curve) and curve[0]["success"] >= target

        def _confirmed(j: int) -> bool:
            return curve[j]["success"] >= target and (
                j == len(curve) - 1 or curve[j + 1]["success"] >= target
            )

        fi_number = None
        fi_age = None
        fi_age_low = None
        fi_age_high = None
        if already_fi:
            fi_number = current_inv
            fi_age = float(getattr(cfg, "YOUR_AGE", 0))
            fi_age_low = fi_age
            fi_age_high = fi_age
        else:
            for j in range(1, len(curve)):
                if _confirmed(j):
                    a, b = curve[j - 1], curve[j]
                    span = b["success"] - a["success"]
                    frac = ((target - a["success"]) / span) if span > 1e-9 else 0.0
                    frac = min(1.0, max(0.0, frac))
                    fi_number = a["networth"] + frac * (b["networth"] - a["networth"])
                    aa, ba = (a["median_retire_age"] or 0), (b["median_retire_age"] or 0)
                    fi_age = aa + frac * (ba - aa)

                    # Blend the p10/p90 range with the SAME frac as the median, so the
                    # displayed "usually X–Y" range and the headline age come from one
                    # consistent interpolation (median stays inside the range).
                    def _blend(key):
                        av, bv = a.get(key), b.get(key)
                        if av is None or bv is None:
                            return bv if bv is not None else av
                        return av + frac * (bv - av)
                    fi_age_low = _blend("p10_retire_age")
                    fi_age_high = _blend("p90_retire_age")
                    break

        result = {
            "fi_number": fi_number,
            "fi_median_retire_age": fi_age,
            "fi_age_low": fi_age_low,
            "fi_age_high": fi_age_high,
            "already_fi": already_fi,
            "target_success": target,
            "current_investable": current_inv,
            "success_by_networth": curve,
            "max_work_age": int(max_work_age),
        }
        _NW_CACHE[key] = result
        _disk_store(_dk, result)
        if len(_NW_CACHE) > 24:
            _NW_CACHE.pop(next(iter(_NW_CACHE)))
        return result
    finally:
        _restore_overrides(original)


def _investable_at_retirement(retirement_age: int, n: int = 40, seed: int = 98765) -> float:
    """Median investable balance AT the retirement year across n detailed sims
    (accumulation-only, independent of retirement spending). Excludes 529.
    Seeded so the SWR anchor is reproducible run-to-run."""
    import random as _random
    np.random.seed(seed)
    _random.seed(seed)
    vals = []
    for _ in range(n):
        try:
            _ok, pf = sim.run_detailed_simulation(retirement_age, verbose=False)
        except Exception:
            continue
        rec = next((r for r in (getattr(pf, "yearly_history", None) or [])
                    if int(r.get("age", -1)) == retirement_age), None)
        if rec:
            total = float(rec.get("total", 0.0) or 0.0)
            c529 = float((rec.get("by_type") or {}).get("college_529", 0.0) or 0.0)
            vals.append(max(0.0, total - c529))
    return float(np.median(vals)) if vals else 0.0


def _median_year1_withdrawal(retirement_age: int, n: int = 20, seed: int = 13579) -> float:
    """Median first-retirement-year total portfolio withdrawal across n sims,
    at the CURRENT cfg spending settings. Seeded so the same accumulation paths
    are reused across the SWR grid (realized rate then moves monotonically with
    the swept spending, not with RNG noise)."""
    import random as _random
    np.random.seed(seed)
    _random.seed(seed)
    vals = []
    for _ in range(n):
        try:
            _ok, pf = sim.run_detailed_simulation(retirement_age, verbose=False)
        except Exception:
            continue
        log = getattr(pf, "withdrawal_log", None) or []
        row = next((r for r in log if int(r.get("age", -1)) == retirement_age),
                   (log[0] if log else None))
        if row:
            vals.append(float(row.get("total", 0.0) or 0.0))
    return float(np.median(vals)) if vals else 0.0


def _swr_crossing(curve: List[dict], target: float):
    """Largest realized withdrawal rate whose success still meets target (success
    is monotonically DESCENDING in rate). None if even the lowest rate misses."""
    if not curve:
        return None
    if curve[0]["success"] < target:
        return None
    if curve[-1]["success"] >= target:
        return curve[-1]["realized_rate"]
    for j in range(1, len(curve)):
        if curve[j]["success"] < target:
            a, b = curve[j - 1], curve[j]
            span = a["success"] - b["success"]
            frac = ((a["success"] - target) / span) if span > 1e-9 else 0.0
            frac = min(1.0, max(0.0, frac))
            return a["realized_rate"] + frac * (b["realized_rate"] - a["realized_rate"])
    return curve[-1]["realized_rate"]


def run_swr_analysis(user_overrides: dict, n_simulations: int = 1000,
                     target_retirement_age: int = 55, progress_callback=None) -> Dict[str, Any]:
    """Personalized safe-withdrawal-rate sweep.

    Sweeps the initial retirement spending from ~3%–6% of the investable balance
    AT retirement, runs the Monte Carlo at each, and returns success rate vs the
    REALIZED initial total-withdrawal rate (so the curve shares an axis with the
    user's actual plan). ``swr_rate`` is the highest rate still meeting
    TARGET_SUCCESS_RATE. NOTE: RETIREMENT_SPENDING_ABSOLUTE sets the non-housing
    living base; housing/healthcare/kids are layered on top by the engine, which
    is exactly why we plot the REALIZED total rate rather than the input rate.
    """
    key = (_hashable(user_overrides), int(n_simulations), int(target_retirement_age))
    if key in _SWR_CACHE:
        return _SWR_CACHE[key]
    _dk = _disk_key("swr", key)
    _hit = _disk_load(_dk)
    if _hit is not None:
        _SWR_CACHE[key] = _hit
        return _hit

    original = _apply_overrides(build_config_overrides(user_overrides))
    _spend_keys = ("RETIREMENT_SPENDING_MODE", "RETIREMENT_SPENDING_ABSOLUTE", "RETIREMENT_SPENDING_PCT")
    spend_snap = {k: getattr(cfg, k, None) for k in _spend_keys}
    try:
        target = float(getattr(cfg, "TARGET_SUCCESS_RATE", 0.80))
        ra = int(target_retirement_age)
        inv0 = _investable_at_retirement(ra)
        if inv0 <= 0:
            result = {"error": "no-investable", "investable_at_retirement": 0.0,
                      "success_by_rate": [], "swr_rate": None, "target_success": target,
                      "retirement_age": ra}
            _SWR_CACHE[key] = result
            return result

        # Anchor the sweep on the user's ACTUAL plan, not an arbitrary % band.
        # Total year-1 withdrawal W0 = living base (the knob) + fixed costs
        # (housing/healthcare/kids, layered on top by the engine). To hit a target
        # TOTAL withdrawal of m*W0 we set the living base to m*W0 - fixed. Sweeping
        # m in [0.6, 1.6] brackets the user's plan (m=1) so the crossing is found.
        living_0 = float(getattr(cfg, "retirement_living_base", lambda: 0.0)())
        w0 = _median_year1_withdrawal(ra)
        if w0 <= 0:
            w0 = 0.04 * inv0  # fallback anchor if the baseline draw is unavailable
        fixed = max(0.0, w0 - living_0)
        actual_rate = w0 / inv0

        m_grid = list(np.linspace(0.6, 1.6, 13))
        scan_sims = max(300, min(int(n_simulations), 3000))
        curve: List[dict] = []
        for i, m in enumerate(m_grid):
            living = max(0.0, m * w0 - fixed)
            setattr(cfg, "RETIREMENT_SPENDING_MODE", "Absolute amount ($/yr)")
            setattr(cfg, "RETIREMENT_SPENDING_ABSOLUTE", float(living))
            realized = _median_year1_withdrawal(ra) / inv0 if inv0 > 0 else float(m * actual_rate)
            r = sim.run_monte_carlo_detailed(ra, n_simulations=scan_sims, random_seed=5000 + i)
            curve.append({
                "realized_rate": float(realized),
                "spending": float(m * w0),
                "success": float(r.get("success_rate", 0.0)),
            })
            if progress_callback:
                progress_callback((i + 1) / len(m_grid), f"Withdrawal {realized * 100:.1f}%")

        # Order by realized rate for a monotone x-axis; success DESCENDS with rate.
        curve.sort(key=lambda c: c["realized_rate"])
        swr_rate = _swr_crossing(curve, target)

        result = {
            "success_by_rate": curve,
            "swr_rate": swr_rate,
            "actual_rate": float(actual_rate),
            "target_success": target,
            "investable_at_retirement": inv0,
            "retirement_age": ra,
        }
        _SWR_CACHE[key] = result
        _disk_store(_dk, result)
        if len(_SWR_CACHE) > 24:
            _SWR_CACHE.pop(next(iter(_SWR_CACHE)))
        return result
    finally:
        for k, v in spend_snap.items():
            try:
                setattr(cfg, k, v)
            except Exception:
                pass
        _restore_overrides(original)


#: Lifecycle toggle flags that gate one-off/recurring life events in the engine.
#: When ANY of these is on, the plan diverges from a toggle-free baseline —
#: see ``run_whatif_delta``.
LIFECYCLE_TOGGLE_KEYS = (
    "CAR_ONETIME_ENABLED",
    "CAR_RECURRING_ENABLED",
    "HOUSE_MOVE_ENABLED",
    "RETIREMENT_VACATION_ENABLED",
)


def active_lifecycle_toggles(user_overrides: dict) -> List[str]:
    """Return the subset of ``LIFECYCLE_TOGGLE_KEYS`` that are truthy.

    Falls back to ``cfg``'s default for a key the caller hasn't overridden,
    so this reflects the toggle state that will actually be simulated.
    """
    active = []
    for key in LIFECYCLE_TOGGLE_KEYS:
        value = user_overrides.get(key, getattr(cfg, key, False))
        if bool(value):
            active.append(key)
    return active


def run_whatif_delta(
    user_overrides: dict,
    n_simulations: int = 1000,
    target_retirement_age: int = 55,
    scan_age_range: tuple = (25, 76, 1),
    progress_callback=None,
) -> Dict[str, Any]:
    """Run the scenario (overrides as-is) and a baseline (all lifecycle
    toggles forced off), returning both full results plus the deltas.

    Both runs reuse ``run_full_analysis`` (same caching, same engine entry
    point) — no engine changes. Intended to be called only when at least one
    lifecycle toggle is active; callers should check ``active_lifecycle_toggles``
    first to avoid the extra baseline simulation when nothing is toggled on.

    Returns:
        {
          "scenario": <run_full_analysis result>,
          "baseline": <run_full_analysis result, all 4 toggles False>,
          "active_toggles": [str, ...],
          "delta": {
            "earliest_retirement_age": int | None,   # scenario - baseline (None if either is None)
            "success_rate": float,                    # scenario - baseline, at target age
            "median_final": float,                    # scenario - baseline
          },
        }
    """
    active_toggles = active_lifecycle_toggles(user_overrides)

    # Two full analyses run here, so split the progress bar in half: the
    # scenario drives the first 50%, the baseline the second 50%. Only forward
    # the callback when one was actually provided (keeps the no-progress path —
    # and callers that monkeypatch run_full_analysis without the kwarg — intact).
    scenario_kwargs: dict = {}
    baseline_kwargs: dict = {}
    if progress_callback is not None:
        def scenario_cb(frac, msg):
            progress_callback(frac * 0.5, msg)

        def baseline_cb(frac, msg):
            progress_callback(0.5 + frac * 0.5, msg)

        scenario_kwargs["progress_callback"] = scenario_cb
        baseline_kwargs["progress_callback"] = baseline_cb

    scenario = run_full_analysis(
        user_overrides, n_simulations=n_simulations,
        target_retirement_age=target_retirement_age, scan_age_range=scan_age_range,
        **scenario_kwargs,
    )

    baseline_overrides = {**user_overrides, **{key: False for key in LIFECYCLE_TOGGLE_KEYS}}
    baseline = run_full_analysis(
        baseline_overrides, n_simulations=n_simulations,
        target_retirement_age=target_retirement_age, scan_age_range=scan_age_range,
        **baseline_kwargs,
    )

    scenario_earliest = scenario.get("earliest_retirement_age")
    baseline_earliest = baseline.get("earliest_retirement_age")
    if scenario_earliest is None or baseline_earliest is None:
        earliest_delta = None
    else:
        earliest_delta = int(scenario_earliest) - int(baseline_earliest)

    scenario_primary = scenario.get("primary_result", {}) or {}
    baseline_primary = baseline.get("primary_result", {}) or {}

    return {
        "scenario": scenario,
        "baseline": baseline,
        "active_toggles": active_toggles,
        "delta": {
            "earliest_retirement_age": earliest_delta,
            "success_rate": float(scenario_primary.get("success_rate", 0.0)) - float(baseline_primary.get("success_rate", 0.0)),
            "median_final": float(scenario_primary.get("median_final", 0.0)) - float(baseline_primary.get("median_final", 0.0)),
        },
    }


def sweep_break_even(
    user_overrides: dict,
    param_name: str,
    values: List[float],
    target_retirement_age: int,
    target_success_rate: float,
    n_simulations: int = 500,
) -> Dict[str, Any]:
    """Sweep one numeric override across ``values`` at a fixed retirement age and
    find the break-even value: the first (lowest) value whose success rate is
    >= ``target_success_rate``.

    Reuses ``run_full_analysis`` for every point (same caching, same engine
    entry point) — no changes to the simulation engine itself. Intended for a
    small grid (e.g. 5-15 points); each point is a fresh Monte Carlo run.

    Args:
        user_overrides: The base overrides dict (as held in session state).
        param_name: Key to vary. Must be a key ``run_full_analysis`` will pass
            through ``build_config_overrides`` onto ``cfg`` (e.g. a plain
            numeric config attribute like ``YOUR_401K_CONTRIBUTION``).
        values: Candidate values to try, in ascending order.
        target_retirement_age: Retirement age held fixed for every point.
        target_success_rate: The success rate threshold to cross.
        n_simulations: Monte Carlo count per point (kept small by callers).

    Returns:
        {
          "param_name": str,
          "values": [float, ...],
          "success_rates": [float, ...],
          "break_even_value": float | None,   # first value crossing target, or None
          "target_success_rate": float,
        }
    """
    success_rates: List[float] = []
    break_even_value = None

    for value in values:
        merged = {**user_overrides, param_name: value}
        try:
            res = run_full_analysis(
                merged, n_simulations=n_simulations, target_retirement_age=target_retirement_age
            )
            primary = res.get("primary_result", {}) or {}
            rate = float(primary.get("success_rate", 0.0))
        except Exception:
            rate = 0.0
        success_rates.append(rate)
        if break_even_value is None and rate >= target_success_rate:
            break_even_value = value

    return {
        "param_name": param_name,
        "values": list(values),
        "success_rates": success_rates,
        "break_even_value": break_even_value,
        "target_success_rate": target_success_rate,
    }


# =============================================================================
# Work functions (uncached)
# =============================================================================

# --- Parallel Monte Carlo (fork pool) with an identical in-process fallback --
# Each unit of work is a ``mc_parallel.sim_task`` batch: (age, n_sims, detail_k,
# seed). Deterministic per-task seeds mean the PARALLEL result and the SERIAL
# fallback are byte-identical — the pool only changes HOW the work runs, not the
# numbers. We use the "fork" start method so workers inherit the parent's
# already-configured ``cfg`` (spawn would re-import __main__, i.e. re-run the
# whole Streamlit app in every worker). On any pool failure we transparently
# run the same tasks in-process, so the result is identical either way.

_PARALLEL_MIN_TASKS = 4  # not worth spinning up a pool for trivially small work

# Fixed number of chunks the target-age Monte Carlo is split into. Deliberately
# NOT os.cpu_count(): each chunk j is seeded 2000+j, so the seed set — and thus
# the headline success_rate / median / percentiles — must not depend on the
# machine's core count (that made a saved profile report different numbers on a
# laptop vs a server). The parallel pool still sizes from os.cpu_count() in
# _run_sim_tasks; only this seed partition is pinned.
_PRIMARY_CHUNKS = 8


def _split_count(total: int, parts: int) -> List[int]:
    """Split ``total`` into up to ``parts`` near-equal positive chunk sizes."""
    if total <= 0:
        return []
    parts = max(1, min(parts, total))
    base, rem = divmod(total, parts)
    return [base + (1 if i < rem else 0) for i in range(parts)]


def _emit_progress(progress_callback, done: int, total: int) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(done / total if total else 1.0,
                          f"Running Monte Carlo… ({done}/{total} batches)")
    except Exception:
        pass


def _available_cpus() -> int:
    """CPUs this process may use. On Linux, sched_getaffinity respects a
    container's CPU set, where os.cpu_count() reports every host CPU."""
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:  # macOS / Windows
        return os.cpu_count() or 1


def _max_workers() -> int:
    """Pool size cap: RETIREMENT_SIM_MAX_WORKERS (1 = never fork). Defaults to 8
    locally and 2 when hosted (small shared containers)."""
    from utils.hosting import is_hosted
    default = 2 if is_hosted() else 8
    try:
        return max(1, int(os.environ.get("RETIREMENT_SIM_MAX_WORKERS", default)))
    except ValueError:
        return default


def _run_sim_tasks(tasks: List[Tuple[str, tuple]], progress_callback=None) -> List[Tuple[str, dict]]:
    """Run ``mc_parallel.sim_task`` over ``[(kind, task_tuple), ...]``.

    Tries a fork ``ProcessPoolExecutor`` first (workers inherit the parent's
    fully-configured ``cfg``); on ANY failure falls back to running the same
    tasks in-process. Because each task carries its own seed, both paths yield
    identical results — the pool is a pure speed optimization.
    """
    total = len(tasks)
    n_cores = _available_cpus()
    max_workers = _max_workers()
    if (total >= _PARALLEL_MIN_TASKS and n_cores > 1 and max_workers > 1
            and hasattr(_mp, "get_context")):
        try:
            ctx = _mp.get_context("fork")
            n_workers = max(2, min(n_cores - 1, max_workers))
            # Key each future by its task index so results can be re-sorted back
            # into submit order. Aggregates are order-invariant, but sample_paths /
            # the representative path depend on task order, so completion order
            # (as_completed) would make which paths display non-deterministic.
            results_by_idx: Dict[int, Tuple[str, dict]] = {}
            done = 0
            with _cf.ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx) as ex:
                fut_meta = {ex.submit(_mcp.sim_task, t): (idx, kind)
                            for idx, (kind, t) in enumerate(tasks)}
                # Generous overall timeout: a real fork deadlock (rare) raises
                # TimeoutError -> caught below -> clean serial fallback, instead
                # of freezing the UI forever.
                for fut in _cf.as_completed(fut_meta, timeout=300):
                    idx, kind = fut_meta[fut]
                    results_by_idx[idx] = (kind, fut.result())
                    done += 1
                    _emit_progress(progress_callback, done, total)
            return [results_by_idx[i] for i in range(len(tasks))]
        except Exception as e:  # BrokenProcessPool, fork/pickle issues, …
            logger.warning("parallel MC pool unavailable (%s); running serially in-process", e)
    # Serial fallback — identical results (same per-task seeds).
    out = []
    for idx, (kind, t) in enumerate(tasks, 1):
        out.append((kind, _mcp.sim_task(t)))
        _emit_progress(progress_callback, idx, total)
    return out


def _median_withdrawal_log_from_data(paths, logs, successes=None) -> List[dict]:
    """Like ``_median_withdrawal_log`` but takes per-path withdrawal LOGS (lists
    of plain dicts) instead of portfolio objects — the parallel workers return
    picklable logs, not portfolios. Same survivor-preference + depletion guard.
    """
    if not paths or not logs:
        return []
    n = min(len(paths), len(logs))
    if successes is None:
        successes = [None] * n
    candidates = [i for i in range(n) if paths[i]]
    if not candidates:
        return []
    survivors = [i for i in candidates if successes[i]] if any(
        s is not None for s in successes[:n]
    ) else candidates
    pool = survivors if survivors else candidates
    finals = np.array([paths[i][-1][1] for i in pool], dtype=float)
    median_val = float(np.median(finals))
    best_i = pool[int(np.argmin(np.abs(finals - median_val)))]
    log = logs[best_i] or []
    rows: List[dict] = []
    for src in log:
        row = dict(src)
        pv = float(row.get("portfolio_value", 0.0) or 0.0)
        total = float(row.get("total", 0.0) or 0.0)
        if pv <= max(1.0, total):
            row["depleted"] = True
            row["withdrawal_pct"] = min(float(row.get("withdrawal_pct", 0.0) or 0.0), 1.0)
        else:
            row.setdefault("depleted", False)
        rows.append(row)
    return rows


def _spending_percentiles(spending_logs, field: str = "living") -> List[dict]:
    """Per-age spending percentiles across MC paths, for the spending-range boxplot.

    ``spending_logs`` is a list of per-path logs (each a list of
    ``{'age','living','total'}`` rows from ``portfolio.spending_log``). Returns
    ``[{age, p10, p25, p50, p75, p90, n}, ...]`` sorted by age, using ``field``
    ('living' = guardrail-adjusted base spending, the market/guardrail-driven
    quantity; 'total' also includes healthcare/LTC/car). Values are today's
    (real) dollars — the chart may inflate them for a nominal view.
    """
    from collections import defaultdict
    by_age = defaultdict(list)
    for log in spending_logs or []:
        for row in (log or []):
            try:
                a = int(row.get("age"))
                v = float(row.get(field, 0.0))
            except (TypeError, ValueError):
                continue
            by_age[a].append(v)
    out: List[dict] = []
    for a in sorted(by_age):
        vals = by_age[a]
        if not vals:
            continue
        # Capped, evenly-spaced sample of raw values for the point-cloud/violin view.
        n = len(vals)
        idx = (np.linspace(0, n - 1, 80).astype(int) if n > 80 else np.arange(n))
        out.append({
            "age": a,
            "p10": float(np.percentile(vals, 10)),
            "p25": float(np.percentile(vals, 25)),
            "p50": float(np.percentile(vals, 50)),
            "p75": float(np.percentile(vals, 75)),
            "p90": float(np.percentile(vals, 90)),
            "samples": [round(float(vals[i]), 2) for i in idx],
            "n": len(vals),
        })
    return out


def _assemble_primary_from_chunks(retirement_age: int, chunks: List[dict]) -> dict:
    """Build the ``primary_result`` dict from parallel ``sim_task`` chunk outputs.

    Aggregate stats (success rate / percentiles) use ALL sims across chunks; the
    trajectory + withdrawal-log detail uses the per-path samples the workers
    kept. This runs the primary sims ONCE (no separate trajectory batch), so it
    also removes the old redundant ~300-sim re-run.
    """
    finals: List[float] = []
    successes = 0
    n = 0
    details: List[dict] = []
    for r in chunks:
        finals.extend(r.get("finals", []))
        successes += int(r.get("successes", 0))
        n += int(r.get("n", 0))
        details.extend(r.get("details", []))

    if n == 0:
        # Nothing ran (all errored) — defer to the legacy serial path.
        return _run_primary_at_age(retirement_age, 200)

    success_rate = successes / n
    median_final = float(np.median(finals)) if finals else 0.0
    p10_final = float(np.percentile(finals, 10)) if finals else 0.0
    p90_final = float(np.percentile(finals, 90)) if finals else 0.0

    paths = [d["trajectory"] for d in details if d.get("trajectory")]
    det_successes = [bool(d.get("success")) for d in details if d.get("trajectory")]
    logs = [d.get("withdrawal_log", []) for d in details if d.get("trajectory")]
    if not paths:
        paths = [_synthetic_trajectory(retirement_age)]
        det_successes = [False]
        logs = [[]]

    median_traj, p10_traj, p90_traj = _percentile_trajectories(paths)
    sample_paths = paths[: min(20, len(paths))]
    allocation_by_year = _compute_allocation_by_year(median_traj, retirement_age)
    savings_contributions_by_year = _approximate_savings_contributions(retirement_age)
    withdrawals_by_year = _median_withdrawal_log_from_data(paths, logs, det_successes)
    income_sources_by_year = _approximate_income_sources(withdrawals_by_year, retirement_age)
    taxes_by_year = _approximate_taxes(withdrawals_by_year, retirement_age)
    spending_logs = [d.get("spending_log", []) for d in details if d.get("trajectory")]
    spending_by_year = _spending_percentiles(spending_logs)
    bytype_logs = [d.get("bytype", []) for d in details if d.get("trajectory")]

    return {
        "retirement_age": retirement_age,
        "success_rate": success_rate,
        "median_final": median_final,
        "p10_final": p10_final,
        "p90_final": p90_final,
        "median_trajectory": median_traj,
        "p10_trajectory": p10_traj,
        "p90_trajectory": p90_traj,
        "sample_paths": sample_paths,
        "income_sources_by_year": income_sources_by_year,
        "allocation_by_year": allocation_by_year,
        "taxes_by_year": taxes_by_year,
        "savings_contributions_by_year": savings_contributions_by_year,
        "withdrawals_by_year": withdrawals_by_year,
        "spending_by_year": spending_by_year,
        "networth_by_year": _networth_percentiles(paths),
        "accessible_by_year": _accessible_percentiles(bytype_logs, logs, retirement_age),
    }


def _compute_full_analysis(
    user_overrides: dict,
    n_simulations: int,
    target_retirement_age: int,
    scan_age_range: tuple,
    progress_callback=None,
) -> Dict[str, Any]:
    original = _apply_overrides(build_config_overrides(user_overrides))
    try:
        your_age = int(getattr(cfg, "YOUR_AGE", 25))
        if target_retirement_age < your_age:
            target_retirement_age = your_age  # silently clamp; UI slider should prevent this

        scan_sims = max(200, n_simulations // 4)
        start = max(scan_age_range[0], your_age)
        stop = max(scan_age_range[1], your_age + 5)
        step = scan_age_range[2]
        scan_ages = list(range(start, stop, step))
        target_success = float(getattr(cfg, "TARGET_SUCCESS_RATE", 0.80))
        detail_cap = min(300, max(50, n_simulations // 3))

        # Work list: one batch per scan age (no per-path detail) + the target's
        # N sims split into per-core chunks (WITH trajectory/log detail). Each
        # task carries a deterministic seed so parallel == serial fallback.
        tasks: List[Tuple[str, tuple]] = [
            ("scan", (age, scan_sims, 0, 1000 + i)) for i, age in enumerate(scan_ages)
        ]
        n_chunks = max(1, min(_PRIMARY_CHUNKS, n_simulations))
        chunk_sizes = _split_count(n_simulations, n_chunks)
        detail_per = max(1, -(-detail_cap // max(1, len(chunk_sizes))))  # ceil-divide
        tasks += [
            ("primary", (target_retirement_age, size, detail_per, 2000 + j))
            for j, size in enumerate(chunk_sizes)
        ]

        results = _run_sim_tasks(tasks, progress_callback=progress_callback)

        success_by_age: Dict[int, float] = {}
        primary_chunks: List[dict] = []
        for kind, r in results:
            if kind == "scan":
                success_by_age[r["age"]] = (r["successes"] / r["n"]) if r["n"] else 0.0
            else:
                primary_chunks.append(r)

        earliest = next(
            (age for age in sorted(success_by_age) if success_by_age[age] >= target_success),
            None,
        )
        primary = _assemble_primary_from_chunks(target_retirement_age, primary_chunks)

        # Record the count ACTUALLY run (the UI's n_simulations), not cfg's
        # NUM_SIMULATIONS default — otherwise "out of N simulations" in the UI
        # would show the config default (10,000) regardless of the real run.
        snap = _snapshot_config()
        snap["NUM_SIMULATIONS"] = int(n_simulations)

        return {
            "earliest_retirement_age": earliest,
            "success_rate_by_age": success_by_age,
            "primary_result": primary,
            "config_snapshot": snap,
        }
    finally:
        _restore_overrides(original)


def _run_primary_at_age(retirement_age: int, n_simulations: int) -> dict:
    """Full Monte Carlo at ``retirement_age`` + trajectory collection for charts."""
    overall = sim.run_monte_carlo_detailed(
        retirement_age=retirement_age, n_simulations=n_simulations, random_seed=7000
    )
    if isinstance(overall, dict):
        success_rate = float(overall.get("success_rate", 0.0))
        median_final = float(overall.get("median_final", 0.0))
        p10_final = float(overall.get("percentile_10", overall.get("p10_final", 0.0)))
        p90_final = float(overall.get("percentile_90", overall.get("p90_final", 0.0)))
    else:
        success_rate = median_final = p10_final = p90_final = 0.0

    # Collect per-year trajectories by running N individual sims and reading
    # portfolio.yearly_history. This is the ACTUAL model output — no fallback
    # needed because run_detailed_simulation returns (success, portfolio).
    # Seed numpy+random so this legacy/degraded fallback path is reproducible
    # run-to-run (matching the seeded parallel/serial task path).
    import random as _random
    np.random.seed(7001)
    _random.seed(7001)
    n_paths = min(300, max(50, n_simulations // 3))
    paths, portfolios, successes = _collect_trajectories(retirement_age, n_paths=n_paths)
    median_traj, p10_traj, p90_traj = _percentile_trajectories(paths)
    sample_paths = paths[: min(20, len(paths))]

    allocation_by_year = _compute_allocation_by_year(median_traj, retirement_age)
    savings_contributions_by_year = _approximate_savings_contributions(retirement_age)

    # Pick a representative SURVIVING simulation (median final balance among the
    # paths that lasted the full horizon) and expose its per-year withdrawal_log.
    # A depleted path's log stops early and its last year spikes toward ~100% as
    # the portfolio hits zero, so we deliberately avoid it — the breakdown must
    # span retirement_age..PLAN_UNTIL_AGE. income_sources_by_year and
    # taxes_by_year for retirement years are derived directly from this same log
    # so all three charts stay internally consistent.
    withdrawals_by_year = _median_withdrawal_log(paths, portfolios, successes)

    income_sources_by_year = _approximate_income_sources(withdrawals_by_year, retirement_age)
    taxes_by_year = _approximate_taxes(withdrawals_by_year, retirement_age)
    spending_logs = [getattr(p, "spending_log", []) or [] for p in portfolios if p is not None]
    spending_by_year = _spending_percentiles(spending_logs)
    bytype_logs = [_bytype_log_from_portfolio(p) for p in portfolios if p is not None]
    wlogs = [list(getattr(p, "withdrawal_log", []) or []) for p in portfolios if p is not None]

    return {
        "retirement_age": retirement_age,
        "success_rate": success_rate,
        "median_final": median_final,
        "p10_final": p10_final,
        "p90_final": p90_final,
        "median_trajectory": median_traj,
        "p10_trajectory": p10_traj,
        "p90_trajectory": p90_traj,
        "sample_paths": sample_paths,
        "income_sources_by_year": income_sources_by_year,
        "allocation_by_year": allocation_by_year,
        "taxes_by_year": taxes_by_year,
        "savings_contributions_by_year": savings_contributions_by_year,
        "withdrawals_by_year": withdrawals_by_year,
        "spending_by_year": spending_by_year,
        "networth_by_year": _networth_percentiles(paths),
        "accessible_by_year": _accessible_percentiles(bytype_logs, wlogs, retirement_age),
    }


def _collect_trajectories(retirement_age: int, n_paths: int):
    """Run N individual sims; return (trajectories, portfolios, successes).

    Returns three parallel lists so callers that need per-portfolio state
    (e.g. withdrawal_log) or per-path survival (whether the path lasted the
    full horizon) can index into the actual results.
    """
    paths: List[List[Tuple[int, float]]] = []
    portfolios: list = []
    successes: List[bool] = []
    for _ in range(n_paths):
        try:
            success, portfolio = sim.run_detailed_simulation(retirement_age, verbose=False)
        except Exception:
            continue
        traj = _trajectory_from_portfolio(portfolio)
        if traj:
            paths.append(traj)
            portfolios.append(portfolio)
            successes.append(bool(success))
    if not paths:
        paths = [_synthetic_trajectory(retirement_age)]
        portfolios = [None]
        successes = [False]
    return paths, portfolios, successes


def _trajectory_from_portfolio(portfolio) -> List[Tuple[int, float]]:
    """Read ``portfolio.yearly_history`` into [(age, total_balance), ...]."""
    out: List[Tuple[int, float]] = []
    history = getattr(portfolio, "yearly_history", None) or []
    for record in history:
        try:
            age = int(record["age"])
            total = float(record["total"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append((age, total))
    return out


def _synthetic_trajectory(retirement_age: int) -> List[Tuple[int, float]]:
    """Fallback only if no simulation succeeded; purely for chart placeholder."""
    start_age = int(getattr(cfg, "YOUR_AGE", 35))
    end_age = int(getattr(cfg, "PLAN_UNTIL_AGE", 90))
    value = float(getattr(cfg, "TOTAL_INVESTMENTS", 100_000))
    path: List[Tuple[int, float]] = []
    for age in range(start_age, end_age + 1):
        if age <= retirement_age:
            value = value * 1.05 + 20_000
        else:
            value = max(0.0, value * 1.03 - 60_000)
        path.append((age, value))
    return path


def _percentile_trajectories(paths: List[List[Tuple[int, float]]]):
    """p10/p50/p90 of balances at each age, across the FULL horizon.

    Paths have different lengths: a path that depletes stops recording, so its
    trajectory ends early (last balance ~$0). We align every path on the union
    age axis and treat a depleted path as $0 for the years AFTER it ran out,
    rather than truncating ALL paths to the shortest one (the old ``min_len``
    approach clipped the median/band to the earliest failure age). Survivors
    dominate the upper percentiles; the low percentiles correctly fall toward
    $0 in years where many paths have already failed.
    """
    if not paths:
        return [], [], []
    all_ages = sorted({int(a) for p in paths for (a, _) in p})
    if not all_ages:
        return [], [], []
    ages = list(range(all_ages[0], all_ages[-1] + 1))
    rows = []
    for p in paths:
        by_age = {int(a): float(v) for a, v in p}
        # Missing years (after a depletion) count as $0 — the path is broke.
        rows.append([by_age.get(age, 0.0) for age in ages])
    matrix = np.array(rows)
    p10 = np.percentile(matrix, 10, axis=0)
    p50 = np.percentile(matrix, 50, axis=0)
    p90 = np.percentile(matrix, 90, axis=0)
    return (
        list(zip(ages, p50.tolist())),
        list(zip(ages, p10.tolist())),
        list(zip(ages, p90.tolist())),
    )


def _networth_percentiles(paths: List[List[Tuple[int, float]]]) -> List[dict]:
    """Per-age p10/p25/p50/p75/p90 of net worth across paths, for the net-worth
    box plot. Uses the SAME full-horizon alignment as _percentile_trajectories
    (a depleted path counts as $0 in years after it ran out). Returns
    ``[{age, p10, p25, p50, p75, p90}, ...]`` sorted by age (today's dollars)."""
    if not paths:
        return []
    all_ages = sorted({int(a) for p in paths for (a, _) in p})
    if not all_ages:
        return []
    ages = list(range(all_ages[0], all_ages[-1] + 1))
    rows = []
    for p in paths:
        by_age = {int(a): float(v) for a, v in p}
        rows.append([by_age.get(age, 0.0) for age in ages])
    matrix = np.array(rows)
    q = {p: np.percentile(matrix, p, axis=0) for p in (10, 25, 50, 75, 90)}
    # A capped, evenly-spaced sample of raw path values per age drives the
    # optional point-cloud / violin view (percentiles alone can't reconstruct it).
    n_paths = matrix.shape[0]
    idx = (np.linspace(0, n_paths - 1, 80).astype(int) if n_paths > 80
           else np.arange(n_paths))
    return [
        {"age": int(a), "p10": float(q[10][i]), "p25": float(q[25][i]),
         "p50": float(q[50][i]), "p75": float(q[75][i]), "p90": float(q[90][i]),
         "samples": [round(float(v), 2) for v in matrix[idx, i]]}
        for i, a in enumerate(ages)
    ]


# =============================================================================
# Best-effort per-year annotations (the simulator does not expose these directly).
# =============================================================================

def _bytype_log_from_portfolio(portfolio) -> List[dict]:
    """Per-year balance-by-category from a portfolio's yearly_history (serial
    path); mirrors mc_parallel._bytype_from_portfolio."""
    out: List[dict] = []
    for record in (getattr(portfolio, "yearly_history", None) or []):
        try:
            bt = record.get("by_type") or {}
            row = {"age": int(record["age"])}
            for k, v in bt.items():
                row[str(k)] = float(v)
            out.append(row)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _accessible_percentiles(bytype_logs: List[List[dict]], withdrawal_logs: List[List[dict]],
                            retirement_age: int) -> List[dict]:
    """Per bridge-year (retirement_age .. the 59.5 threshold), the median
    penalty-free ("accessible") balance by source PLUS the median annual
    withdrawal and penalty — all cross-path medians so the bridge chart and its
    verdict are computed on the SAME statistical object.

    Accessible = cash + taxable brokerage + Roth (contribution basis APPROXIMATED
    by the full Roth balance). Penalized = traditional 401k/IRA + HSA. The
    reported ``accessible`` is the SUM of the per-source medians (so the stacked
    chart height equals the accessible figure). ``burn`` = median total annual
    withdrawal; ``penalty`` = median early-withdrawal penalty paid. A path that
    depleted before an age contributes $0 there.
    """
    early = float(getattr(cfg, "EARLY_WITHDRAWAL_AGE_401K_IRA", 59.5))
    if retirement_age > early:
        return []
    hi_age = int(early) + 1  # include the 59->60 transition around 59.5
    per_bt = [{int(r["age"]): r for r in (log or []) if "age" in r} for log in bytype_logs]
    per_wd = [{int(r["age"]): r for r in (log or []) if "age" in r} for log in (withdrawal_logs or [])]
    if not per_bt:
        return []
    out: List[dict] = []
    for a in range(int(retirement_age), hi_age + 1):
        cash, taxable, roth, penal = [], [], [], []
        for d in per_bt:
            r = d.get(a)
            cash.append(float(r.get("cash", 0.0)) if r else 0.0)
            taxable.append(float(r.get("taxable", 0.0)) if r else 0.0)
            roth.append((float(r.get("roth_ira", 0.0)) + float(r.get("roth_401k", 0.0))) if r else 0.0)
            penal.append((float(r.get("traditional_401k", 0.0)) + float(r.get("traditional_ira", 0.0))
                          + float(r.get("hsa", 0.0))) if r else 0.0)
        if not cash:
            continue
        burn, pen = [], []
        for d in per_wd:
            r = d.get(a)
            burn.append(float(r.get("total", 0.0)) if r else 0.0)
            pen.append(float(r.get("penalties", 0.0)) if r else 0.0)
        cash_m = float(np.percentile(cash, 50))
        tax_m = float(np.percentile(taxable, 50))
        roth_m = float(np.percentile(roth, 50))
        out.append({
            "age": a,
            "cash": cash_m,
            "taxable": tax_m,
            "roth": roth_m,
            "penalized": float(np.percentile(penal, 50)),
            "accessible": cash_m + tax_m + roth_m,  # = stacked chart height
            "burn": float(np.percentile(burn, 50)) if burn else 0.0,
            "penalty": float(np.percentile(pen, 50)) if pen else 0.0,
        })
    return out


def _median_withdrawal_log(paths, portfolios, successes=None) -> List[dict]:
    """Select a REPRESENTATIVE, full-horizon simulation and return its
    ``portfolio.withdrawal_log`` as a list of plain dicts.

    We prefer a SURVIVING path — one that lasted from ``retirement_age`` through
    ``PLAN_UNTIL_AGE`` — and among survivors pick the one whose final balance is
    closest to the survivors' median. A depleted path's log stops early (its last
    year spikes toward ~100% as the portfolio hits zero), so choosing it would
    truncate the withdrawal chart and paint a spurious 100% bar. Only if NO path
    survives do we fall back to the closest-to-median path overall.

    This gives the UI a single, internally-consistent per-year withdrawal
    breakdown (one simulation path) rather than a cross-sim average that
    wouldn't correspond to a real scenario.
    """
    if not paths or not portfolios:
        return []

    n = min(len(paths), len(portfolios))
    if successes is None:
        successes = [None] * n

    # Candidate indices: those with a usable portfolio + trajectory.
    candidates = [
        i for i in range(n)
        if portfolios[i] is not None and paths[i]
    ]
    if not candidates:
        return []

    # Prefer survivors (paths that lasted the full horizon). When the success
    # flag isn't available, treat every usable candidate as eligible.
    survivors = [i for i in candidates if successes[i]] if any(
        s is not None for s in successes[:n]
    ) else candidates
    pool = survivors if survivors else candidates

    finals = np.array([paths[i][-1][1] for i in pool], dtype=float)
    median_val = float(np.median(finals))
    best_i = pool[int(np.argmin(np.abs(finals - median_val)))]

    chosen = portfolios[best_i]
    log = getattr(chosen, "withdrawal_log", None) or []
    # Shallow-copy each row so downstream mutations can't affect the portfolio,
    # and guard the withdrawal % so a near-zero (depleted) portfolio does not
    # emit a spurious ~100% bar. If the pre-withdrawal balance is negligible
    # relative to the amount withdrawn, the fraction is meaningless — cap it and
    # flag the row as a depletion year so the chart can annotate rather than
    # render a bogus full-height stack.
    rows: List[dict] = []
    for src in log:
        row = dict(src)
        pv = float(row.get("portfolio_value", 0.0) or 0.0)
        total = float(row.get("total", 0.0) or 0.0)
        if pv <= max(1.0, total):
            row["depleted"] = True
            row["withdrawal_pct"] = min(float(row.get("withdrawal_pct", 0.0) or 0.0), 1.0)
        else:
            row.setdefault("depleted", False)
        rows.append(row)
    return rows


def _approximate_income_sources(withdrawal_rows: List[dict], retirement_age: int) -> List[IncomeSourceYearRow]:
    """Real per-year retirement income breakdown from the representative
    ``withdrawal_log`` (see ``_median_withdrawal_log``), plus real Social
    Security income for the same path.

    Account draws are mapped directly from the log (no hardcoded split).
    ``cash`` draws are folded into ``taxable`` — both are already-taxed
    dollars with no further income tax due — because the chart's fixed
    5-series layout has no separate cash bucket.
    """
    ss_claim_age = int(getattr(cfg, "SS_CLAIM_AGE", 67))
    include_ss = bool(getattr(cfg, "INCLUDE_SOCIAL_SECURITY", False))
    calc_ss = getattr(cfg, "calculate_social_security", None)

    out: List[dict] = []
    for row in withdrawal_rows:
        age = int(row.get("age", 0))
        if age < retirement_age:
            continue
        ss = 0.0
        if include_ss and calc_ss is not None and age >= ss_claim_age:
            try:
                ss = float(calc_ss(age, ss_claim_age))
            except Exception:
                ss = 0.0
        out.append({
            "age": age,
            "ss": ss,
            "traditional": float(row.get("traditional", 0.0)),
            "roth": float(row.get("roth", 0.0)),
            "taxable": float(row.get("taxable", 0.0)) + float(row.get("cash", 0.0)),
            "hsa": float(row.get("hsa", 0.0)),
            # Transfer, not income — see IncomeSourceYearRow docstring above.
            "roth_conversion": float(row.get("roth_conversion", 0.0)),
        })
    return out


def _compute_allocation_by_year(median_traj, retirement_age: int) -> List[AllocationYearRow]:
    calc_alloc = getattr(cfg, "calculate_asset_allocation", None)
    if calc_alloc is None:
        return []
    start_age = int(getattr(cfg, "YOUR_AGE", 25))
    end_age = int(getattr(cfg, "PLAN_UNTIL_AGE", 90))
    # Use configured age range so the chart spans current age → plan end
    # regardless of how far any single simulation path advanced. Fall back to
    # median_traj ages only if config is misconfigured.
    if end_age > start_age:
        ages = list(range(start_age, end_age + 1))
    else:
        ages = [int(age) for age, _ in median_traj] if median_traj else []
    out: List[dict] = []
    for age in ages:
        try:
            stock, bond = calc_alloc(age, retirement_age)
            out.append({
                "age": int(age),
                "stock_pct": float(stock),
                "bond_pct": float(bond),
            })
        except Exception:
            continue
    return out


def _approximate_savings_contributions(retirement_age: int) -> List[SavingsContributionYearRow]:
    """Per-year contribution breakdown from current age to retirement.

    Pulls YOUR_COMPENSATION_BY_AGE + partner defaults from cfg so the rows
    reflect overrides applied for this run. Values are static defaults per year
    (no stochastic noise); this drives the savings stacked-bar chart.

    HAND-SYNCED with ``components/income_over_time.py`` (the Income tile), which
    projects the same working-years income from ``user_overrides``. Both read the
    comp table and, past its last age, grow the last row by
    ``(1 + YOUR_SALARY_GROWTH_RATE) ** years``. Change one -> change the other,
    or the two screens disagree about the same run.
    See ``tests/test_income_parity.py``.

    NOTE: the ``age in comp_by_age`` / ``max(comp_by_age.keys())`` lookups below
    require INT keys. Profiles are stored as JSON (string keys) and restored by
    ``utils.profile_io._restore_int_keys``; if that ever regresses this function
    silently falls into its ``else`` branch and reports ZERO income.

    finding #9 — ``your_brokerage``/``partner_brokerage`` are derived from the
    SAME residual-sweep formula ``simulate_accumulation_year`` uses in Auto
    mode (account_simulation.py): residual = household_after_tax - living -
    after_tax_electives, split pro-rata by each person's own after-tax
    capacity, with the flat *_BROKERAGE_CONTRIBUTION override acting as a
    floor. Previously this used the pre-baked ``comp['saved']`` (a static ~10%-
    of-after-tax formula) which ignores the sweep entirely and understated
    real brokerage contributions by ~50%. Manual mode (no sweep) falls back to
    the flat override / ``comp['saved']`` exactly as the engine's MANUAL branch
    does.
    """
    start_age = int(getattr(cfg, "YOUR_AGE", 25))
    # Use target retirement age as exclusive upper bound.
    end_age = int(retirement_age)
    if end_age <= start_age:
        return []

    comp_by_age = getattr(cfg, "YOUR_COMPENSATION_BY_AGE", {}) or {}
    last_known_age = max(comp_by_age.keys()) if comp_by_age else start_age
    salary_growth = float(getattr(cfg, "YOUR_SALARY_GROWTH_RATE", 0.03))
    partner_growth = float(getattr(cfg, "PARTNER_SALARY_GROWTH_RATE", 0.02))

    your_401k_desired = float(getattr(cfg, "YOUR_401K_CONTRIBUTION", 0))
    your_match_pct = float(getattr(cfg, "YOUR_401K_MATCH_PCT", 0))
    your_hsa_total = float(getattr(cfg, "YOUR_HSA_TOTAL", 0))
    calc_529 = getattr(cfg, "calculate_529_contribution", None)
    calc_expenses = getattr(cfg, "calculate_annual_expenses", None)

    partner_salary_base = float(getattr(cfg, "PARTNER_SALARY", 0))
    partner_401k = float(getattr(cfg, "PARTNER_401K_CONTRIBUTION", 0))
    partner_roth_desired = float(getattr(cfg, "PARTNER_ROTH_CONTRIBUTION", 0))
    years_until_wedding = int(getattr(cfg, "YEARS_UNTIL_WEDDING", 0))
    partner_spending = float(getattr(cfg, "PARTNER_ANNUAL_SPENDING", 0))
    partner_tax_rate = float(getattr(cfg, "PARTNER_ESTIMATED_TAX_RATE", 0.2))
    your_ira_limit_fn = getattr(cfg, "get_ira_limit", None)
    # finding #9 (backdoor-Roth sub-bug): read the REAL configured desired
    # contribution (``simulate_accumulation_year`` uses
    # ``getattr(cfg, "YOUR_BACKDOOR_ROTH", your_ira_limit)``), not a hardcoded
    # $7,000 -- the base config default is $0 (only the "My situation" profile
    # happens to set it to $7,000), so the hardcode silently mismatched the
    # engine's residual/electives for every other profile and desired amount.
    your_backdoor_desired = getattr(cfg, "YOUR_BACKDOOR_ROTH", None)
    current_year = int(getattr(cfg, "CURRENT_YEAR", 2024))
    after_tax_pct = float(getattr(cfg, "YOUR_AFTER_TAX_401K_PCT", 0.0) or 0.0)
    total_limit_fn = getattr(cfg, "get_401k_total_limit", None)
    your_401k_limit_fn = getattr(cfg, "get_401k_limit", None)
    savings_mode = str(getattr(cfg, "SAVINGS_MODE", "Auto-allocate (recommended)"))
    your_brokerage_override = getattr(cfg, "YOUR_BROKERAGE_CONTRIBUTION", None)
    partner_brokerage_override = getattr(cfg, "PARTNER_BROKERAGE_CONTRIBUTION", None)

    # Partner's own working boundary (separate-partner-retirement-age feature).
    # This loop only spans the primary's working years, so by default the partner
    # is working throughout (== prior behavior). When PARTNER_RETIREMENT_AGE puts
    # the partner's retirement before the primary's, their contributions drop to
    # zero on time.
    _pra = getattr(cfg, "PARTNER_RETIREMENT_AGE", None)
    _partner_age0 = int(getattr(cfg, "PARTNER_AGE", 0))
    _has_partner = _partner_age0 > 0
    _age_gap = start_age - _partner_age0  # primary_age - partner_age

    def _partner_working(a: int) -> bool:
        if not _has_partner or _pra is None:
            return True
        return (a - _age_gap) < int(_pra)

    out: List[dict] = []
    for age in range(start_age, end_age):
        # Primary user
        if age in comp_by_age:
            base = float(comp_by_age[age].get("base", 0))
            saved = float(comp_by_age[age].get("saved", 0))
            your_after_tax = float(comp_by_age[age].get("after_tax", 0))
            your_gross = float(comp_by_age[age].get("total_comp", base))
        elif comp_by_age:
            last_comp = comp_by_age[last_known_age]
            years_beyond = age - last_known_age
            factor = (1 + salary_growth) ** max(0, years_beyond)
            base = float(last_comp.get("base", 0)) * factor
            saved = float(last_comp.get("saved", 0)) * factor
            your_after_tax = float(last_comp.get("after_tax", 0)) * factor
            your_gross = float(last_comp.get("total_comp", last_comp.get("base", 0))) * factor
        else:
            base = 0.0
            saved = 0.0
            your_after_tax = 0.0
            your_gross = 0.0

        employer_match = base * your_match_pct

        # Mega backdoor after-tax 401(k) -> Roth (mirrors the engine): fill the
        # 415(c) room after the employee deferral + employer match, funded from
        # take-home (an after-tax elective, so it reduces the brokerage sweep).
        your_after_tax_401k = 0.0
        if after_tax_pct > 0 and total_limit_fn is not None:
            yr = current_year + (age - start_age)
            try:
                total_limit = float(total_limit_fn(age, yr))
            except Exception:
                total_limit = 69000.0
            # Mirror the engine: cap the employee deferral at the IRS limit before
            # computing 415(c) room (the engine uses min(desired, limit)).
            k_limit = float(your_401k_limit_fn(age, yr)) if your_401k_limit_fn else 23000.0
            capped_401k = min(float(your_401k_desired), k_limit)
            room = max(0.0, total_limit - capped_401k - employer_match)
            your_after_tax_401k = min(after_tax_pct * base, room)

        # Backdoor Roth limited by IRA limit for the year (mirrors
        # simulate_accumulation_year: desired amount defaults to the IRA limit
        # itself when YOUR_BACKDOOR_ROTH is unset, then both are capped by it).
        if your_ira_limit_fn is not None:
            try:
                ira_cap = float(your_ira_limit_fn(age, current_year + (age - start_age)))
            except Exception:
                ira_cap = 7000.0
        else:
            ira_cap = 7000.0
        your_backdoor = float(your_backdoor_desired) if your_backdoor_desired is not None else ira_cap
        your_roth_contribution = min(your_backdoor, ira_cap)

        # 529 (treated as spend — not saved into brokerage)
        contribution_529 = 0.0
        if calc_529 is not None:
            try:
                contribution_529 = float(calc_529(age))
            except Exception:
                contribution_529 = 0.0

        # Partner pre-tax/Roth + after-tax income (mirrors
        # simulate_accumulation_year's partner block).
        years_from_now = age - start_age
        partner_salary = partner_salary_base * ((1 + partner_growth) ** max(0, years_from_now))
        partner_taxable = max(0.0, partner_salary - partner_401k)
        partner_after_tax = partner_taxable * (1 - partner_tax_rate)
        # Direct partner Roth is only funded pre-marriage (MFJ income
        # phase-out kicks in after) -- see simulate_accumulation_year:
        # ``0.0 if married else min(partner_roth_desired, ira_limit)``.
        # Previously this chart used the flat PARTNER_ROTH_CONTRIBUTION
        # unconditionally, phantom-crediting a post-marriage elective (and
        # understating the brokerage sweep by the same amount) every year
        # after YEARS_UNTIL_WEDDING.
        married = years_from_now >= years_until_wedding
        partner_roth = 0.0 if married else partner_roth_desired

        # Zero the partner's earnings/contributions once they've retired (feature).
        partner_401k_year = partner_401k
        if not _partner_working(age):
            partner_salary = 0.0
            partner_taxable = 0.0
            partner_after_tax = 0.0
            partner_roth = 0.0
            partner_401k_year = 0.0

        if savings_mode.startswith("Auto") and calc_expenses is not None:
            # AUTO — same residual sweep as simulate_accumulation_year:
            # household_after_tax - living - after_tax_electives, then attributed
            # by the "split expenses evenly, bank your own remainder" rule (each
            # covers half of living from their own income; the residual lands
            # mostly in the higher earner's brokerage).
            try:
                living = float(calc_expenses(age, 1.0, childcare_factor=1.0))
            except Exception:
                living = 0.0
            your_electives = your_roth_contribution + contribution_529 + your_after_tax_401k
            partner_electives = partner_roth
            household_after_tax = your_after_tax + partner_after_tax
            residual = max(0.0, household_after_tax - living - your_electives - partner_electives)

            your_floor = float(your_brokerage_override) if your_brokerage_override else 0.0
            partner_floor = float(partner_brokerage_override) if partner_brokerage_override else 0.0
            total_brokerage = max(residual, your_floor + partner_floor)

            half_living = 0.5 * living
            your_capacity = max(0.0, your_after_tax - your_electives)
            partner_capacity = max(0.0, partner_after_tax - partner_electives)
            if bool(getattr(cfg, "PRIMARY_PAYS_HOUSING", False)):
                # Same housing term the engine splits off: the mortgage, or the
                # owner's post-payoff carrying cost (cfg.owner_housing_annual).
                _oh = getattr(cfg, "owner_housing_annual", None)
                _hm = getattr(cfg, "has_mortgage", None)
                if _oh is not None:
                    mortgage_year = float(_oh(age))
                else:
                    mortgage_year = (float(getattr(cfg, "MORTGAGE_ANNUAL", 0.0))
                                     if (_hm is None or _hm(age)) else 0.0)
                rest = max(0.0, living - mortgage_year)
                your_expense = mortgage_year + 0.5 * rest
                partner_expense = 0.5 * rest
            else:
                your_expense = partner_expense = half_living
            your_after_half = your_capacity - your_expense
            partner_after_half = partner_capacity - partner_expense
            pos_total = max(0.0, your_after_half) + max(0.0, partner_after_half)
            your_share = (max(0.0, your_after_half) / pos_total) if pos_total > 0 else 1.0
            your_brokerage = max(0.0, total_brokerage * your_share)
            partner_brokerage = max(0.0, total_brokerage - your_brokerage)
        else:
            # MANUAL — flat override or legacy comp['saved']-based formula,
            # matching simulate_accumulation_year's MANUAL branch exactly.
            if your_brokerage_override is not None and float(your_brokerage_override) > 0:
                your_brokerage = float(your_brokerage_override)
            else:
                your_brokerage = max(0.0, saved - your_roth_contribution - contribution_529 - your_after_tax_401k)

            if partner_brokerage_override is not None and float(partner_brokerage_override) > 0:
                partner_brokerage = float(partner_brokerage_override)
            else:
                partner_brokerage = max(0.0, partner_after_tax - partner_roth - partner_spending)

        out.append({
            "age": int(age),
            "your_401k": float(your_401k_desired),
            "your_employer_match": float(employer_match),
            "your_hsa": float(your_hsa_total),
            "your_roth": float(your_roth_contribution),
            "your_aftertax_roth": float(your_after_tax_401k),
            "your_brokerage": float(your_brokerage),
            "partner_401k": float(partner_401k_year),
            "partner_roth": float(partner_roth),
            "partner_brokerage": float(partner_brokerage),
            # Household income for the savings-rate chart. partner_salary /
            # partner_after_tax are already 0 when the partner has retired early.
            "gross_income": float(your_gross + partner_salary),
            "after_tax_income": float(your_after_tax + partner_after_tax),
        })
    return out


def _approximate_taxes(withdrawal_rows: List[dict], retirement_age: int) -> List[TaxYearRow]:
    """Per-year tax breakdown covering current age through plan end.

    Working-years: total tax = comp['total_comp'] - comp['after_tax'] (the
    SAME per-age fields the engine's cashflow uses — see
    ``YOUR_COMPENSATION_BY_AGE`` in config.py), which already reflects bonus +
    RSU + real effective rate, plus partner tax via
    ``PARTNER_ESTIMATED_TAX_RATE`` (the same rate the engine applies). Split
    75/25 into federal/state for display only; the combined dollar total is
    real (finding #10 — previously used a flat 18%/6% of base-salary-only
    gross, understating working-years tax by omitting bonus/RSU entirely).
    Retirement-years: REAL taxes from the representative ``withdrawal_log``
    (see ``_median_withdrawal_log`` / engine's per-year tax logging). The log
    only records a combined income-tax total (``total_taxes``, which already
    nets out federal + state + LTCG + Roth-conversion + RMD + SS tax minus
    penalties) plus the separable ``niit``; there is no per-year federal/state/
    LTCG split available, so the combined amount minus niit (already included
    in total_taxes — see finding #17) is reported under ``federal`` and
    ``state``/``ltcg`` are left at 0 rather than invented via an arbitrary
    ratio. The dollar total (federal+state+ltcg+niit) is real and counts NIIT
    exactly once. Provides ``gross_income`` so downstream effective-rate
    calcs work.
    """
    start_age = int(getattr(cfg, "YOUR_AGE", 25))
    end_age = int(getattr(cfg, "PLAN_UNTIL_AGE", 90))
    # Use configured age range so tax chart spans current age → plan end
    # regardless of how far any single simulation path advanced.
    if end_age > start_age:
        ages = list(range(start_age, end_age + 1))
    else:
        ages = [int(row.get("age", 0)) for row in withdrawal_rows] if withdrawal_rows else []

    taxes_by_age = {int(row.get("age", -1)): row for row in withdrawal_rows}

    comp_by_age = getattr(cfg, "YOUR_COMPENSATION_BY_AGE", {}) or {}
    last_known_age = max(comp_by_age.keys()) if comp_by_age else start_age
    salary_growth = float(getattr(cfg, "YOUR_SALARY_GROWTH_RATE", 0.03))
    partner_growth = float(getattr(cfg, "PARTNER_SALARY_GROWTH_RATE", 0.02))
    partner_salary_base = float(getattr(cfg, "PARTNER_SALARY", 0))

    out: List[dict] = []
    for age in ages:
        if age < retirement_age:
            # Working year: real total tax dollars from the SAME comp-table
            # fields the engine uses for cashflow (finding #10). comp['after_tax']
            # already nets federal + state + payroll tax on total_comp (base +
            # bonus + rsu_gross — see config.py YOUR_COMPENSATION_BY_AGE), so
            # total_comp - after_tax is the real tax paid, not an 18%-of-base-only
            # guess. Partner's tax uses the SAME PARTNER_ESTIMATED_TAX_RATE the
            # engine applies to partner_taxable_income (account_simulation.py).
            if age in comp_by_age:
                your_total_comp = float(comp_by_age[age].get("total_comp", 0))
                your_after_tax = float(comp_by_age[age].get("after_tax", 0))
            elif comp_by_age:
                last = comp_by_age[last_known_age]
                factor = (1 + salary_growth) ** max(0, age - last_known_age)
                your_total_comp = float(last.get("total_comp", 0)) * factor
                your_after_tax = float(last.get("after_tax", 0)) * factor
            else:
                your_total_comp = 0.0
                your_after_tax = 0.0
            your_tax = max(0.0, your_total_comp - your_after_tax)

            partner_salary = partner_salary_base * ((1 + partner_growth) ** max(0, age - start_age))
            partner_401k = float(getattr(cfg, "PARTNER_401K_CONTRIBUTION", 0))
            partner_tax_rate = float(getattr(cfg, "PARTNER_ESTIMATED_TAX_RATE", 0.20))
            partner_tax = max(0.0, partner_salary - partner_401k) * partner_tax_rate

            gross = your_total_comp + partner_salary
            total_tax = your_tax + partner_tax
            # Split the real total into federal/state using the same 75/25
            # (~18%/~6% of a blended 24% effective rate) proportion as before,
            # now applied to the correct dollar total instead of an
            # under-counted gross.
            federal = total_tax * 0.75
            state = total_tax * 0.25
            out.append({
                "age": int(age),
                "federal": float(federal),
                "state": float(state),
                "ltcg": 0.0,
                "niit": 0.0,
                "gross_income": float(gross),
            })
        else:
            # Retirement year: real taxes from the representative withdrawal_log
            # row for this age (falls back to zeros if the log doesn't cover it,
            # e.g. the representative path failed/ended before this age).
            # gross_income = withdrawals (already includes RMDs) + real SS income,
            # since SS is a separate income source netted out of `total` upstream.
            row = taxes_by_age.get(age)
            if row is not None:
                total_taxes = float(row.get("total_taxes", 0.0))
                niit = float(row.get("niit", 0.0))
                ss_income = 0.0
                if bool(getattr(cfg, "INCLUDE_SOCIAL_SECURITY", False)):
                    ss_claim_age = int(getattr(cfg, "SS_CLAIM_AGE", 67))
                    calc_ss = getattr(cfg, "calculate_social_security", None)
                    if calc_ss is not None and age >= ss_claim_age:
                        try:
                            ss_income = float(calc_ss(age, ss_claim_age))
                        except Exception:
                            ss_income = 0.0
                gross_income = float(row.get("total", 0.0)) + ss_income
            else:
                total_taxes = 0.0
                niit = 0.0
                gross_income = 0.0
            out.append({
                "age": int(age),
                # finding #17 — `total_taxes` already INCLUDES niit (see
                # _flush_withdrawal_log: NIIT is folded into total_taxes_paid,
                # and niit is only separated out for display). Subtract it back
                # out of the `federal` bucket so `federal + state + ltcg + niit`
                # (the chart's _total()) recovers the real total exactly once,
                # instead of double-counting NIIT on top of an already-inclusive
                # federal figure.
                "federal": max(0.0, total_taxes - niit),
                "state": 0.0,
                "ltcg": 0.0,
                "niit": niit,
                "gross_income": gross_income,
            })
    return out


def _snapshot_config() -> dict:
    keys = [
        "YOUR_AGE", "PARTNER_AGE", "YOUR_BIRTH_YEAR", "PARTNER_BIRTH_YEAR",
        "TOTAL_INVESTMENTS", "TOTAL_NET_WORTH", "CURRENT_ANNUAL_EXPENSES",
        "PLAN_UNTIL_AGE", "TARGET_SUCCESS_RATE", "NUM_SIMULATIONS",
        "ACTIVE_RETURN_SCENARIO", "INCLUDE_SOCIAL_SECURITY",
        "DYNAMIC_SPENDING_ENABLED", "ENABLE_ROTH_CONVERSION",
        "SS_CLAIM_AGE",
    ]
    return {k: getattr(cfg, k, None) for k in keys}


def _payoff_projection_for(overrides: dict, extra: float) -> dict:
    """Deterministic payoff projection under ``overrides`` + ``extra`` principal.

    Applies the overrides onto cfg (same monkeypatch discipline as every other
    entry point here) so the projection sees the user's real loan, then restores.
    """
    try:
        from retirement_sim.account_simulation import mortgage_payoff_projection
    except Exception:
        return {}
    original = _apply_overrides(build_config_overrides(overrides))
    try:
        return mortgage_payoff_projection(extra)
    except Exception:
        return {}
    finally:
        _restore_overrides(original)


def run_mortgage_paydown_analysis(
    user_overrides: dict,
    n_simulations: int = 500,
    target_retirement_age: int = 55,
    extra_grid: "List[float] | None" = None,
    progress_callback=None,
) -> Dict[str, Any]:
    """Sweep EXTRA annual mortgage principal and measure the effect on success.

    Answers "is prepaying the mortgage worth it?" by re-running the plan at
    several extra-principal levels and reporting success rate, the age the loan
    is retired, and lifetime interest avoided.

    Why this is a fair test rather than a rigged one: the extra payment is
    charged as real cash (so it competes with investing the same dollars), the
    loan is amortised faster, and -- critically -- the scheduled payment STOPS
    once the balance hits zero, which is the entire benefit of prepaying. See
    the note on ``cfg.EXTRA_MORTGAGE_PAYMENT_ANNUAL``.

    The comparison is apples-to-apples: every point uses the same simulation
    count and the same retirement age, and point 0 is the untouched baseline.

    Returns
    -------
    {
      "curve": [{extra, success_rate, median_final, p10_final,
                 payoff_age, delta_success}, ...],
      "baseline_success": float,
      "baseline_payoff_age": int | None,
      "best_extra": float | None,     # grid point with the highest success
      "best_delta": float,            # its gain over baseline, in points
      "helps": bool,                  # does ANY prepayment beat baseline?
      "n_simulations": int,
    }
    """
    if extra_grid is None:
        extra_grid = [0.0, 6_000.0, 12_000.0, 24_000.0, 36_000.0, 60_000.0]
    grid = [float(max(0.0, v)) for v in extra_grid]
    if 0.0 not in grid:
        grid = [0.0] + grid          # the baseline must be on the curve
    grid = sorted(set(grid))

    key = (_hashable(user_overrides), int(n_simulations),
           int(target_retirement_age), tuple(grid))
    dk = _disk_key("mortgage_paydown", key)
    hit = _disk_load(dk)
    if hit is not None:
        return hit

    curve: List[Dict[str, Any]] = []
    for i, extra in enumerate(grid):
        if progress_callback:
            progress_callback(i / len(grid), f"Extra ${extra:,.0f}/yr")
        merged = dict(user_overrides)
        merged["EXTRA_MORTGAGE_PAYMENT_ANNUAL"] = extra
        try:
            res = run_full_analysis(
                merged, n_simulations=n_simulations,
                target_retirement_age=target_retirement_age,
            )
        except Exception:
            continue
        pr = res.get("primary_result", {}) or {}
        # Payoff age + interest come from the DETERMINISTIC amortisation
        # projection, not from Monte Carlo output: the schedule depends only on
        # (balance, rate, payment, extra), so it is exact and free -- and the
        # per-year loan state isn't surfaced in the result dict anyway.
        proj = _payoff_projection_for(merged, extra)
        sr_ = float(pr.get("success_rate", 0.0))
        n = max(1, int(n_simulations))
        curve.append({
            "extra": extra,
            "success_rate": sr_,
            # Binomial standard error, so the UI can say plainly which
            # differences are inside the noise instead of implying precision
            # the sample size doesn't support.
            "success_se": (sr_ * (1.0 - sr_) / n) ** 0.5,
            "median_final": float(pr.get("median_final", 0.0)),
            "p10_final": float(pr.get("p10_final", 0.0)),
            "payoff_age": proj.get("payoff_age"),
            "total_interest": proj.get("total_interest"),
            "years_saved": proj.get("years_saved_vs_scheduled"),
        })

    if not curve:
        return {"curve": [], "baseline_success": 0.0, "baseline_payoff_age": None,
                "best_extra": None, "best_delta": 0.0, "helps": False,
                "n_simulations": int(n_simulations)}

    base = next((c for c in curve if c["extra"] == 0.0), curve[0])
    for c in curve:
        c["delta_success"] = c["success_rate"] - base["success_rate"]

    # Noise floor for a DIFFERENCE of two independent rates.
    base_se = base.get("success_se", 0.0)
    for c in curve:
        se_diff = ((base_se ** 2) + (c.get("success_se", 0.0) ** 2)) ** 0.5
        c["delta_se"] = se_diff
        c["significant"] = abs(c["delta_success"]) > 2.0 * se_diff

    best = max(curve, key=lambda c: c["success_rate"])
    result = {
        "curve": curve,
        "baseline_success": base["success_rate"],
        "baseline_payoff_age": base.get("payoff_age"),
        "best_extra": best["extra"] if best["extra"] != 0.0 else None,
        "best_delta": best["success_rate"] - base["success_rate"],
        "helps": best["success_rate"] > base["success_rate"],
        # Only claim prepayment helps if the best point clears the noise floor.
        "helps_significantly": bool(best.get("significant"))
        and best["success_rate"] > base["success_rate"],
        "noise_floor_pp": 2.0 * base_se * 100.0,
        "n_simulations": int(n_simulations),
    }
    if progress_callback:
        progress_callback(1.0, "Mortgage sweep complete")
    _disk_store(dk, result)
    return result
