"""Settings control for the persisted simulation cache.

The Monte Carlo results are cached to disk (see ``utils.disk_cache``) so the
page loads instantly instead of recomputing ~95s of simulation on every reload.
That cache is keyed on a fingerprint of the ENGINE SOURCE, so editing the model
invalidates it automatically -- this panel exists for the two cases automation
can't cover:

  * you want to force a fresh recompute (e.g. to re-roll the random draws)
  * you want to see whether the cache is actually being used
"""
from __future__ import annotations

try:
    from utils.formatting import money  # noqa: F401  (kept for consistency)
except ImportError:  # pragma: no cover
    pass


def render(st) -> None:
    try:
        from utils import disk_cache
        from utils.sim_runner import clear_cache
    except ImportError:  # pragma: no cover
        from ui.utils import disk_cache  # type: ignore
        from ui.utils.sim_runner import clear_cache  # type: ignore

    with st.expander("Simulation cache", expanded=False, icon=":material/bolt:"):
        try:
            s = disk_cache.stats()
        except Exception as exc:
            st.caption(f"Cache unavailable: {exc}")
            return

        mb = s.get("bytes", 0) / 1_048_576.0
        st.caption(
            f"**{s.get('entries', 0)}** saved result(s) · {mb:.1f} MB · "
            f"model `{s.get('engine', '?')}`"
        )
        st.caption(
            "Results are reused across reloads and restarts. Editing the model "
            "invalidates them automatically, so this is only for forcing a "
            "fresh recompute."
        )
        if st.button("↻ Recompute everything", key="cache_clear_btn",
                     width="stretch",
                     help="Delete saved results and re-run the simulations now."):
            clear_cache(include_disk=True)
            # Drop the warmed results + the once-per-session autorun guard so
            # _autorun_all fires again on the next script run.
            for k in ("results", "whatif_results", "fi_result", "swr_result",
                      "sensitivity_results", "break_even_result",
                      "stress_preset_results", "last_run_inputs_hash",
                      "_autorun_done"):
                st.session_state.pop(k, None)
            st.success("Cache cleared — recomputing.")
            try:
                st.rerun()
            except Exception:
                pass
