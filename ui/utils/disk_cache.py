"""Disk-backed persistence for the Monte Carlo result caches.

``sim_runner`` already memoises results in-process, which makes a browser
refresh cheap — but the process holds that memory, so restarting the app (or
editing any UI file, which makes Streamlit reload) throws it all away and the
user waits out a full cold recompute again.

This adds a second, on-disk tier underneath the in-memory one:

    memory hit -> instant
    disk hit   -> deserialise (milliseconds)
    miss       -> compute, then write both tiers

Two correctness properties matter more than speed here:

1. **Keys must be stable across processes.** Python's builtin ``hash()`` is
   randomised per-process for str/bytes (PYTHONHASHSEED), so the in-session
   fingerprints used for staleness detection are useless as filenames. Keys
   here are sha256 over a canonical repr instead.

2. **Cached numbers must never outlive the model that produced them.** Every
   key is salted with a fingerprint of the engine source (``retirement_sim``
   ``*.py``), so editing config.py or account_simulation.py silently
   invalidates every stored entry rather than serving numbers from the old
   model. This project changes the engine often; without that salt a stale
   cache would quietly present pre-fix results as current.

Failure is always non-fatal: a corrupt, unreadable, or unwritable cache
degrades to "recompute", never to an exception.
"""
from __future__ import annotations

import datetime
import hashlib
import logging
import os
import pickle
import tempfile
from typing import Any, Callable, Optional

logger = logging.getLogger("retirement_ui.disk_cache")

# Bump to invalidate every entry after changing the stored payload SHAPE
# (as opposed to the engine maths, which the source fingerprint already covers).
_FORMAT_VERSION = "v3"   # v2: primary_result gained p25/p75_final, n_simulations, sample_successes; spending over all runs
                         # v3: withdrawals/income/taxes by year are per-age medians across runs (+ withdrawals_basis)

_DIR_NAME = ".sim_cache"
_MAX_FILES = 400          # generous; entries are small and pruned oldest-first

_engine_fp_cache: Optional[str] = None


def _project_root() -> str:
    # ui/utils/disk_cache.py -> <project root>
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def cache_dir() -> str:
    return os.path.join(_project_root(), _DIR_NAME)


def engine_fingerprint() -> str:
    """sha256 over the engine's source so any model edit invalidates the cache.

    Computed once per process (the source cannot change under a running
    interpreter without a reload, which creates a new process anyway).
    """
    global _engine_fp_cache
    if _engine_fp_cache is not None:
        return _engine_fp_cache
    h = hashlib.sha256()
    # The engine reads the current year from the clock (config.CURRENT_YEAR),
    # so a new year must not serve last year's results.
    h.update(str(datetime.date.today().year).encode("utf-8"))
    engine = os.path.join(_project_root(), "retirement_sim")
    try:
        for name in sorted(os.listdir(engine)):
            if not name.endswith(".py"):
                continue
            path = os.path.join(engine, name)
            h.update(name.encode("utf-8"))
            with open(path, "rb") as fh:
                h.update(fh.read())
    except Exception:
        # Can't read the engine -> use a random-ish salt so we simply don't
        # serve stale results (degrades to always-miss rather than wrong-hit).
        h.update(os.urandom(16))
    _engine_fp_cache = h.hexdigest()[:16]
    return _engine_fp_cache


def stable_key(*parts: Any) -> str:
    """Process-stable key over arbitrary (already-frozen) values."""
    h = hashlib.sha256()
    h.update(_FORMAT_VERSION.encode("utf-8"))
    h.update(engine_fingerprint().encode("utf-8"))
    for p in parts:
        h.update(repr(p).encode("utf-8", errors="replace"))
        h.update(b"\x1f")
    return h.hexdigest()[:40]


def _path_for(key: str) -> str:
    return os.path.join(cache_dir(), f"{key}.pkl")


def load(key: str) -> Any:
    """Return the cached value, or None on any miss/corruption."""
    try:
        with open(_path_for(key), "rb") as fh:
            return pickle.load(fh)
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.warning("disk_cache: discarding unreadable entry %s (%s)", key, exc)
        try:
            os.remove(_path_for(key))
        except Exception:
            pass
        return None


def store(key: str, value: Any) -> None:
    """Persist a value. Never raises."""
    try:
        d = cache_dir()
        os.makedirs(d, exist_ok=True)
        # Write to a temp file in the same dir then rename, so a crash or a
        # second process can never observe a half-written pickle.
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                pickle.dump(value, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, _path_for(key))
        except Exception:
            try:
                os.remove(tmp)
            except Exception:
                pass
            raise
        _prune(d)
    except Exception as exc:
        logger.warning("disk_cache: could not persist %s (%s)", key, exc)


def _prune(d: str) -> None:
    """Keep the directory bounded, dropping least-recently-modified first."""
    try:
        entries = [(os.path.getmtime(os.path.join(d, f)), f)
                   for f in os.listdir(d) if f.endswith(".pkl")]
        if len(entries) <= _MAX_FILES:
            return
        for _mtime, name in sorted(entries)[: len(entries) - _MAX_FILES]:
            try:
                os.remove(os.path.join(d, name))
            except Exception:
                pass
    except Exception:
        pass


def get_or_compute(key: str, compute: Callable[[], Any]) -> Any:
    """Disk-tier wrapper: return the stored value or compute+store it."""
    hit = load(key)
    if hit is not None:
        return hit
    value = compute()
    if value is not None:
        store(key, value)
    return value


def clear() -> None:
    """Delete every persisted entry."""
    d = cache_dir()
    try:
        for f in os.listdir(d):
            if f.endswith((".pkl", ".tmp")):
                try:
                    os.remove(os.path.join(d, f))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.warning("disk_cache: clear failed (%s)", exc)


def stats() -> dict:
    d = cache_dir()
    try:
        files = [f for f in os.listdir(d) if f.endswith(".pkl")]
        size = sum(os.path.getsize(os.path.join(d, f)) for f in files)
        return {"dir": d, "entries": len(files), "bytes": size,
                "engine": engine_fingerprint()}
    except FileNotFoundError:
        return {"dir": d, "entries": 0, "bytes": 0, "engine": engine_fingerprint()}
