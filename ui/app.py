"""
Retirement Monte Carlo - Streamlit UI

License: MIT

Run:
    cd <project-root>
    streamlit run ui/app.py
"""
from __future__ import annotations

import functools
import sys
from pathlib import Path

# Ensure both the project root (so `retirement_sim` is importable) AND the ui/
# directory (so `components.*` and `utils.*` are importable) are on sys.path.
UI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = UI_DIR.parent
for p in (PROJECT_ROOT, UI_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import streamlit as st

# Page config MUST be the first Streamlit call.
st.set_page_config(
    page_title="Retirement Monte Carlo",
    page_icon="📈",
    layout="wide",
    # "auto" (not "expanded"): Streamlit auto-collapses the sidebar on narrow
    # viewports. Forcing it open put a 328px overlay over a 390px phone screen —
    # the sidebar covered the Run button, which then could not be clicked at all
    # until the user found the « control. Desktop behaviour is unchanged (auto
    # shows the sidebar on wide viewports).
    initial_sidebar_state="auto",
)


def _inject_css() -> None:
    css_path = UI_DIR / "styles" / "theme.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)


def _init_state() -> None:
    # Components may not be built yet; import lazily so partial builds still render.
    # Default the app to the personal profile and seed its values so the very
    # first render (before any profile-change event) already reflects it.
    default_profile = "Median US 25-year-old household"
    seed_overrides: dict = {}
    comp_customized = False
    try:
        from components.profile_picker import DEFAULT_PROFILE, PROFILES
        default_profile = DEFAULT_PROFILE  # your own profile when present
        preset = PROFILES.get(default_profile)
        if preset:
            seed_overrides = dict(preset)
            comp_customized = "YOUR_COMPENSATION_BY_AGE" in preset
    except Exception:
        default_profile = "Median US 25-year-old household"

    defaults = {
        "user_overrides": seed_overrides,
        "results": None,
        "whatif_results": None,
        "profile": default_profile,
        "si_comp_customized": comp_customized,
        "last_run_inputs_hash": None,
        "pinned_scenarios": {},
        "n_simulations": SIM_COUNT_DEFAULT,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# Simulation-count options shown next to the Run button.
from utils.hosting import is_hosted as _is_hosted

# Hosted containers have a CPU or two shared by every visitor: start at 500.
SIM_COUNT_OPTIONS = ([500] if _is_hosted() else []) + [1000, 5000, 10000, 25000]
SIM_COUNT_DEFAULT = 500 if _is_hosted() else 1000

# Compute every displayed simulation on page load instead of waiting for button
# clicks (see _autorun_all). Results persist via utils.disk_cache, so the cold
# cost is paid once rather than on every reload. Set False for the old
# click-to-run behaviour.
AUTORUN_ON_LOAD = True


def _inputs_fingerprint(overrides: dict, n_sims) -> "int | None":
    """Stable hash of the inputs that drive a run, so persisted results can be
    detected as stale after the user edits the sidebar. Returns None if the
    overrides aren't hashable (then staleness detection is simply skipped)."""
    try:
        from utils.sim_runner import _hashable
        return hash((_hashable(overrides), int(n_sims)))
    except Exception:
        return None


def _results_are_fresh() -> bool:
    """True when a run exists AND the current inputs still match the run that
    produced it — i.e. re-running would reproduce the same numbers, so the Run
    button should be inactive. Any sidebar/sim-count change makes this False
    again (the fingerprint no longer matches), re-enabling the button.

    Returns False if fingerprints can't be computed (never wrongly disables).
    """
    if st.session_state.get("results") is None:
        return False
    last = st.session_state.get("last_run_inputs_hash")
    cur = _inputs_fingerprint(
        st.session_state.user_overrides,
        st.session_state.get("n_simulations", SIM_COUNT_DEFAULT),
    )
    return last is not None and cur is not None and last == cur


def _results_are_stale() -> bool:
    """True only when we can PROVE the stored run no longer matches the inputs.

    Deliberately NOT ``not _results_are_fresh()``: when a fingerprint can't be
    computed both are False, so an un-hashable override never produces a false
    "your results are stale" nag (the Run button stays enabled instead, which is
    the safe direction for that control).
    """
    if st.session_state.get("results") is None:
        return False
    last = st.session_state.get("last_run_inputs_hash")
    cur = _inputs_fingerprint(
        st.session_state.user_overrides,
        st.session_state.get("n_simulations", SIM_COUNT_DEFAULT),
    )
    return last is not None and cur is not None and last != cur


# Shared help text on a Run button that is inactive because results are current.
_FRESH_RUN_HELP = ("Results already reflect your current inputs. Change a "
                   "sidebar parameter (or the simulation count) to re-enable.")


def _validate_run_inputs(overrides: dict, target_age: int) -> list:
    """Hard-invalid input combinations that would otherwise be silently clamped
    by the engine (producing a result attributed to the wrong age). Delegates to
    the shared validator so the main Run and the FI/SWR sweeps gate identically."""
    try:
        from utils.validation import validate_run_inputs
    except ImportError:  # pragma: no cover
        from ui.utils.validation import validate_run_inputs  # type: ignore
    return validate_run_inputs(overrides, target_age)



def _autorun_all(progress_container=None) -> None:
    """Compute every simulation the page displays, once, on load.

    Without this the user lands on a page of empty placeholders and has to click
    Run, then "Calculate my number", then "Find my safe withdrawal rate" before
    seeing anything -- every single reload, because Streamlit's session state
    dies with the browser session.

    Starts the main Monte Carlo (hero metric, success-by-age, every chart);
    when it is in, the what-if baseline (only when a lifecycle toggle is on), the
    FI-number, SWR and mortgage-paydown sweeps follow (see ``_begin_run``).

    Results are persisted by ``utils.disk_cache``, so this whole sequence is a
    ONE-TIME cost: later loads (and app restarts, which is when the in-memory
    cache used to be lost) replay from disk in milliseconds.

    Fires EXACTLY ONCE per browser session, on first page open. It must not
    re-fire on any input change: Streamlit reruns the script on every keystroke,
    so simulating per keystroke would make the app unusable. Sidebar edits,
    profile switches and JSON loads all fall through to waiting for an explicit
    Run (edits mark results stale; the other two clear them).

    The deep-dive sweeps (Sensitivity, break-even, stress presets) stay
    on-demand: each explores a different override set, so warming all of them
    would multiply the first-load cost for panels the user may never open. They
    now share the same disk cache, so the first click is the only slow one.
    """
    if not AUTORUN_ON_LOAD:
        return
    # EXACTLY ONCE per browser session, on first page open -- never again.
    #
    # Not after a sidebar edit (Streamlit reruns the script on every keystroke,
    # so re-simulating per keystroke would make the app unusable), and not after
    # a profile switch or JSON load either: those clear `results`, and the guard
    # is preserved across profile switches (see profile_picker._PRESERVE) so they
    # fall through to waiting for an explicit Run. Cached results make the one
    # attempt cheap -- see utils.disk_cache.
    if st.session_state.get("_autorun_done"):
        return
    if st.session_state.get("results") is not None:
        st.session_state["_autorun_done"] = True
        return

    overrides = st.session_state.user_overrides
    target_age = int(overrides.get("TARGET_RETIREMENT_AGE", 55))
    # Don't auto-run an invalid input combination: the manual path surfaces the
    # specific errors, and retrying on every rerun would spam them.
    if _validate_run_inputs(overrides, target_age):
        st.session_state["_autorun_done"] = True
        return

    # Set the guard BEFORE computing so a mid-run exception can't turn into a
    # retry loop on the next rerun.
    st.session_state["_autorun_done"] = True

    n_sims = int(st.session_state.get("n_simulations", SIM_COUNT_DEFAULT))
    _pc = progress_container if progress_container is not None else st
    prog = _pc.progress(0.0, text="Preparing your plan… starting simulations")

    def _seg(lo, hi, label):
        def _cb(frac, _msg=None):
            try:
                f = lo + (hi - lo) * min(1.0, max(0.0, float(frac)))
                prog.progress(f, text=f"{label} — {int(round(f * 100))}%")
            except Exception:
                pass
        return _cb

    try:
        # The main result first; the what-if baseline and the net-worth, safe-
        # withdrawal and mortgage sweeps fill in after it (_queue_extras).
        _begin_run(overrides, n_sims, target_age, _seg(0.0, 1.0, "Running the main simulation"))
    except Exception as e:
        import logging
        logging.getLogger("retirement_ui").exception("Auto-run failed")
        st.warning(
            f"Couldn't finish preparing the plan automatically ({e}). "
            "Use Run to try again."
        )
    finally:
        prog.empty()


def _begin_run(overrides: dict, n_sims: int, target_age: int, progress_callback=None) -> None:
    """Start a run. The main result's detailed part (trajectories, logs) runs
    here right away; its success-by-age scan goes to the visitor's browser if
    its workers are ready (utils/browser_compute.py) -- never waiting for a
    Pyodide download -- else runs here too. When the main
    result is in, ``_finish_main`` stores it and queues the other analyses."""
    from utils import sim_runner as sr
    from utils import browser_compute as bc
    bc.cancel(st)                                   # a new run supersedes pending work
    st.session_state.pop("_extras_pending", None)
    st.session_state.pop("_main_pending", None)
    overrides = dict(overrides)
    plan = sr.plan_full_analysis(overrides, int(n_sims), int(target_age))
    done = functools.partial(_finish_main, overrides, int(n_sims), int(target_age))
    if plan.result is not None:
        done(plan.result)
    elif bc.ready(st):
        st.session_state["_main_pending"] = True
        bc.submit(st, "main", plan, done, run_here=plan.local, progress_callback=progress_callback)
    else:
        done(sr.execute_plan(plan, progress_callback))


def _finish_main(overrides: dict, n_sims: int, target_age: int, result: dict) -> None:
    st.session_state.results = result
    st.session_state.whatif_results = None
    # The input fingerprint lets the page flag results as stale after a later
    # sidebar edit (mirrors the FI section's staleness guard).
    st.session_state.last_run_inputs_hash = _inputs_fingerprint(overrides, n_sims)
    st.session_state.pop("_main_pending", None)
    # Reset lazy-load flags so fresh results render PROGRESSIVELY (only the
    # above-fold charts in the burst; the rest load on scroll).
    for _k in [k for k in st.session_state.keys() if isinstance(k, str) and k.startswith("_lz_")]:
        st.session_state[_k] = False
    _queue_extras(overrides, n_sims, target_age, result)


def _queue_extras(overrides: dict, n_sims: int, target_age: int, main_result: dict) -> None:
    """The analyses that follow the main result: what-if baseline (lifecycle
    toggles on), FI number, safe withdrawal rate, mortgage paydown. Each goes
    to the browser, or -- without one -- to ``_server_extras_step``, which runs
    them here one per script run after the page is drawn, so the main result
    never waits for them."""
    from utils import sim_runner as sr
    from utils import browser_compute as bc
    # FI + SWR carry the fingerprint their own sections compute, so each renders
    # as "up to date" and its button starts inactive.
    stamp = _inputs_fingerprint(overrides, n_sims)

    def keep(key, stamped):
        def store(res):
            if stamped and isinstance(res, dict):
                res = {**res, "_inputs_hash": stamp}
            st.session_state[key] = res
        return store

    def whatif(baseline):
        st.session_state.whatif_results = sr.whatif_from(overrides, main_result, baseline)

    plans = []
    if sr.active_lifecycle_toggles(overrides):
        plans.append(("whatif", sr.plan_full_analysis(sr.whatif_baseline_overrides(overrides),
                                                      n_sims, target_age), whatif))
    plans.append(("fi", sr.plan_networth_analysis(overrides, n_simulations=n_sims), keep("fi_result", True)))
    plans.append(("swr", sr.plan_swr_analysis(overrides, n_sims, target_age), keep("swr_result", True)))
    # Higher sim count: this sweep reports DIFFERENCES between grid points, and
    # at 1k runs the binomial noise (~1.5pp) swamps the effect being measured.
    plans.append(("mortgage", sr.plan_mortgage_paydown(overrides, max(2000, n_sims), target_age),
                  keep("mortgage_paydown_result", False)))
    server = []
    for kind, plan, store in plans:
        if plan.result is not None:
            store(plan.result)
        elif bc.usable(st):
            bc.submit(st, kind, plan, store)
        else:
            server.append((kind, plan, store))
    st.session_state["_extras_pending"] = server


def _server_extras_step() -> None:
    """Without a browser to help: one queued analysis per script run, after the
    page is drawn, then rerun to show it."""
    queue = st.session_state.get("_extras_pending") or []
    if not queue:
        return
    kind, plan, store = queue.pop(0)
    from utils import sim_runner as sr
    try:
        store(sr.execute_plan(plan))
    except Exception:
        import logging
        logging.getLogger("retirement_ui").exception("Background analysis %s failed", kind)
    st.rerun()


def _bc_poll_body() -> None:
    """While browser jobs are pending: every few seconds, let the server take
    over any the browser can't finish (unavailable, or past its deadline)."""
    from utils import browser_compute as bc
    if bc.take_over_one(st):
        st.rerun()


def _run_simulation(progress_container=None) -> None:
    """Run the full Monte Carlo analysis using current sidebar inputs.

    Shared by the main-panel and sidebar Run buttons so behavior stays
    identical. The progress bar renders in ``progress_container`` (a full-width
    ``st.empty()`` slot passed by ``main``) so its label has room and never wraps;
    falls back to the default location if none is given.

    If any lifecycle toggle (car/house-move/vacation) is active, also runs a
    baseline (toggles forced off) via ``run_whatif_delta`` so the WHAT-IF pane
    can render. That extra baseline simulation is skipped entirely when no
    toggle is on, so the no-toggle default path is unchanged. When it DOES run,
    the two phases share a single monotonic 0→100% bar (main analysis fills the
    first part, the what-if baseline the rest) instead of counting to 100% twice.
    """
    # Gate hard-invalid input combinations up front so the engine never silently
    # clamps them into a result attributed to a different age than the UI shows.
    _overrides = st.session_state.user_overrides
    _target = int(_overrides.get("TARGET_RETIREMENT_AGE", 55))
    _errs = _validate_run_inputs(_overrides, _target)
    if _errs:
        for _e in _errs:
            st.error(_e)
        # Clear stale results so the top-bar success metric doesn't keep showing
        # a previous run's number against the now-invalid target age.
        st.session_state.results = None
        st.session_state.whatif_results = None
        st.session_state.last_run_inputs_hash = None
        return

    _pc = progress_container if progress_container is not None else st
    prog = _pc.progress(0.0, text="Running Monte Carlo… 0%")

    try:
        target_age = int(st.session_state.user_overrides.get("TARGET_RETIREMENT_AGE", 55))
        n_sims = int(st.session_state.get("n_simulations", SIM_COUNT_DEFAULT))

        def _cb(frac, msg):
            try:
                f = min(1.0, max(0.0, float(frac)))
                prog.progress(f, text=f"Running Monte Carlo… {int(round(f * 100))}%")
            except Exception:
                pass

        _begin_run(st.session_state.user_overrides, n_sims, target_age, _cb)
    except Exception as e:
        # Report to the user and the server log, then CLEAR the run state — the
        # same cleanup the validation-failure branch above does, so the top bar
        # doesn't keep advertising the previous run's success rate under the new
        # inputs. Deliberately NOT re-raised: this function is invoked from
        # inside `_safe_render("components.top_bar", …)`, so a propagating
        # exception replaced the entire top bar (Run button, sim-count selector,
        # Settings/profile/save-load popover) with the generic placeholder,
        # leaving no in-app way to change an input and retry.
        import logging
        logging.getLogger("retirement_ui").exception("Simulation failed")
        st.error(f"Simulation failed: {e}")
        st.session_state.results = None
        st.session_state.whatif_results = None
        st.session_state.last_run_inputs_hash = None
        return
    finally:
        # Always retire the progress bar — on the failure path it used to freeze
        # at whatever percentage it had reached.
        prog.empty()
    # Rerun so the whole app — including the top-bar Success-rate metric — picks
    # up the fresh results (the bar renders near the top, before this ran).
    st.rerun()


def _as_fragment(fn):
    """Wrap a render closure in st.fragment so interacting with a control INSIDE
    it (e.g. a chart's view toggle) reruns ONLY that section, not the whole app
    (which would re-render all ~20 Plotly charts). Each call site must use a
    distinct function name so Streamlit gives each its own fragment identity."""
    _f = getattr(st, "fragment", None)
    try:
        return _f(_config_locked(fn)) if _f else fn
    except Exception:
        return fn


def _config_locked(fn):
    """Run ``fn`` holding the engine-config lock (see sim_runner.CONFIG_LOCK):
    a fragment rerun skips main(), so it takes the lock itself. functools.wraps
    keeps the name Streamlit derives the fragment's identity from."""
    from utils.sim_runner import CONFIG_LOCK

    @functools.wraps(fn)
    def _locked(*args, **kwargs):
        with CONFIG_LOCK:
            return fn(*args, **kwargs)
    return _locked


_bc_poll = st.fragment(run_every=3)(_config_locked(_bc_poll_body)) if hasattr(st, "fragment") else None


# Sections the phone bar can jump to: (tile key suffix, chip label).
_JUMP_SECTIONS = [("retirement", "Retirement"), ("fi", "Net worth"), ("swr", "Withdrawal"),
                  ("bridge", "Bridge to 59½"), ("spending", "Spending"), ("savings", "Savings"),
                  ("income", "Income"), ("tax", "Tax"), ("lifespan", "Lifespan")]


def _phone_bar(results) -> None:
    """Phone-only sticky bar (theme.css shows it under 640px wide): chips that
    jump to each section, plus the headline result once the top card has
    scrolled away. The page script (components.animations) does the jumping,
    highlights the section in view, and hides chips for sections not shown."""
    from components.top_bar import _resolve_success, _resolve_target_age
    success, _hint = _resolve_success(results)
    age = _resolve_target_age(st.session_state.user_overrides)
    chips = "".join(f'<a role="button" data-mc-jump="{k}">{label}</a>' for k, label in _JUMP_SECTIONS)
    with st.container(key="mc-phonebar"):
        st.markdown(f'<div class="mc-phonebar"><span class="mc-phonebar-status"><b>{success}</b>'
                    f' · retire at {age}</span><nav class="mc-phonebar-chips">{chips}</nav></div>',
                    unsafe_allow_html=True)


def _lazy_ph(key: str, min_h: int = 320) -> None:
    """Skeleton placeholder + a hidden 'load' button for a lazy section. The
    animation engine's IntersectionObserver clicks the button when this nears
    the viewport, rerunning the enclosing fragment to render the real content —
    so off-screen charts don't render until needed (breaks up the render burst)."""
    st.markdown(
        f'<div class="mc-lazy" data-lazy="{key}" style="min-height:{min_h}px"></div>',
        unsafe_allow_html=True,
    )
    if st.button("load", key=f"_lzb_{key}"):
        st.session_state[f"_lz_{key}"] = True
        try:
            st.rerun(scope="fragment")
        except Exception:
            pass


def _safe_render(module_path: str, fn_name: str = "render", *args, **kwargs):
    """Import and call a component's render function.

    If the component isn't built yet or errors out, render a placeholder so the
    rest of the app still loads. This keeps the app usable during parallel
    development.
    """
    try:
        import importlib
        module = importlib.import_module(module_path)
        fn = getattr(module, fn_name)
        return fn(st, *args, **kwargs)
    except Exception as e:
        import traceback
        import logging
        # Log to the server console too — the inline placeholder is easy to miss,
        # so a swallowed component failure would otherwise be invisible to an operator.
        logging.getLogger("retirement_ui").exception("Component failed to render: %s", module_path)
        # User-facing copy stays plain (matching the placeholders every other
        # component shows); the exception type/message and full traceback stay
        # available one click away for debugging.
        st.error("This section couldn't be displayed.")
        with st.expander("Details", expanded=False):
            st.caption(f"`{module_path}` — {type(e).__name__}: {e}")
            st.code(traceback.format_exc())
        return None


def _topbar_run(_st, progress_container=None) -> None:
    """Run-simulation button — lives in the top bar's Run column.

    Goes inactive once results reflect the current inputs, so it's visually
    clear there's nothing to re-run until a parameter changes. The progress bar
    renders in ``progress_container`` (a full-width slot) so its label has room.
    """
    fresh = _results_are_fresh()
    if _st.button("✓ Up to date" if fresh else "▶ Run simulation",
                  width="stretch", type="primary", key="topbar_run_button",
                  disabled=fresh, help=_FRESH_RUN_HELP if fresh else None):
        _run_simulation(progress_container)


def _topbar_sims(_st) -> None:
    """Simulation-count selector — lives in the top bar's Sims column."""
    _st.selectbox(
        "Simulations",
        options=SIM_COUNT_OPTIONS,
        format_func=lambda n: f"{n:,}",
        key="n_simulations",
        label_visibility="collapsed",
        help="Number of Monte Carlo simulations. More = smoother, more precise results (and a longer run).",
    )


def _topbar_head(_st):
    """The top card's toolbar row: the Retirement plan | Spending switch on the
    left, and empty slots on the right that top_bar.render fills with the Run
    button, simulation count and Settings once the sidebar has synced. Returns
    (view, (run_slot, sims_slot, settings_slot)); a deselected switch returns
    None, which main() treats as the plan."""
    nav_col, run_col, sims_col, settings_col = _st.columns(
        [0.50, 0.18, 0.15, 0.17], vertical_alignment="center")
    with nav_col:
        view = _st.segmented_control("View", ["Retirement plan", "Spending"], default="Retirement plan",
                                     key="main_view", label_visibility="collapsed")
    return view, (run_col.empty(), sims_col.empty(), settings_col.empty())


def _resolve_mode():
    """'simple', 'full', or None (show the welcome screen). The owner's own
    machine -- not hosted, with a personal profile -- goes straight to the
    planner, so the welcome screen is for everyone else."""
    mode = st.session_state.get("app_mode")
    if mode in ("simple", "full"):
        return mode
    try:
        from utils.hosting import is_hosted
        from components.profile_picker import load_personal_profile
        if not is_hosted() and load_personal_profile() is not None:
            st.session_state.app_mode = "full"
            from components import guided_setup
            if not guided_setup.started(st):
                guided_setup.mark_done(st)       # the owner's planner is already set up
            return "full"
    except Exception:
        pass
    return None


def _loading_screen() -> None:
    """Shown for the instant the browser takes to report saved data."""
    with st.container(key="mc-loading"):
        st.markdown('<div class="mc-loading">Loading…</div>', unsafe_allow_html=True)
        if st.button("Continue", key="device_skip", type="tertiary"):
            st.session_state._device_skip = True
            st.rerun()


def _restore_from_device(store) -> None:
    """Once per session: bring back what the visitor chose to remember."""
    if st.session_state.get("_device_restored") or store["status"] != "ready":
        return
    st.session_state._device_restored = True
    data = store.get("data") or {}
    if not data.get("remember"):
        return
    st.session_state.remember_device = True
    if data.get("mode") in ("simple", "full"):
        st.session_state.app_mode = data["mode"]
    try:
        if isinstance(data.get("simple"), dict):
            from utils.simple_finance import normalize_inputs
            st.session_state.simple_inputs = normalize_inputs(data["simple"])
        if isinstance(data.get("full"), str):
            from utils.profile_io import deserialize_overrides
            from utils.widget_sync import sync_widgets_from_overrides
            st.session_state.user_overrides = deserialize_overrides(data["full"])
            sync_widgets_from_overrides(st)
        from components import guided_setup
        setup = guided_setup.restore(data.get("setup"))
        if setup:
            st.session_state[guided_setup.STATE] = setup
        elif isinstance(data.get("full"), str):
            guided_setup.mark_done(st)           # saved before the walkthrough existed
    except Exception:  # an unreadable saved copy must never break the app
        pass


def _save_to_device() -> None:
    """If the visitor turned on Remember me, keep their inputs in their browser.
    (device_store writes only when something changed.)"""
    if not st.session_state.get("remember_device"):
        return
    payload = {"remember": True, "mode": st.session_state.get("app_mode")}
    if isinstance(st.session_state.get("simple_inputs"), dict):
        payload["simple"] = st.session_state.simple_inputs
    if st.session_state.get("app_mode") == "full" or st.session_state.get("_full_touched"):
        from utils.profile_io import serialize_overrides
        payload["full"] = serialize_overrides(st.session_state.user_overrides)
        st.session_state._full_touched = True
    setup = st.session_state.get("setup")
    if isinstance(setup, dict):
        payload["setup"] = {k: setup.get(k) for k in ("status", "step", "seen", "checkup")}
    try:
        from utils import device_store
        device_store.save(st, payload)
    except Exception:
        pass


def _privacy_controls(_st) -> None:
    """Remember me on this device + Forget my data (both versions)."""
    from utils import device_store
    state = st.session_state.get(device_store.STATE_KEY_PREFIX + device_store.DEFAULT_KEY) or {}
    unavailable = state.get("status") == "unavailable"
    # The setting lives in a plain session key: Streamlit drops a widget's
    # value after any run that doesn't draw it (e.g. a run cut short by the
    # first simulation), which silently switched saving off.
    if "remember_device_toggle" not in st.session_state:
        st.session_state.remember_device_toggle = bool(st.session_state.get("remember_device"))
    on = _st.toggle("Remember me on this device", key="remember_device_toggle", disabled=unavailable,
                    help="Saves your inputs in this browser only, so they're here next time. "
                         "The saved copy lives in this browser only; the server does not store it.")
    st.session_state.remember_device = bool(on)
    if unavailable:
        _st.caption("This browser blocks saving (private browsing?), so nothing can be remembered.")
    elif on:
        _st.caption("Your inputs are saved in this browser only.")
    if _st.button("Forget my data on this device", key="device_forget", type="tertiary",
                  icon=":material/delete:"):
        device_store.forget(st)
        st.session_state.remember_device = False
        st.session_state.pop("remember_device_toggle", None)
        st.rerun()


MODES = {"simple": "Money check-up", "full": "Retirement planner"}


def _on_mode_switch(key: str) -> None:
    picked = st.session_state.get(key)
    st.session_state.app_mode = next(m for m, label in MODES.items() if label == picked)


def _mode_switch(current: str, in_gutter: bool = False) -> None:
    """Money check-up | Retirement planner: the same switch, top right, on the
    check-up, the setup walkthrough and the planner. Each version keeps its own
    answers; switching never loses them. A horizontal radio styled as a
    segmented toggle (it always has a choice, unlike st.segmented_control, and
    Streamlit's AppTest can rerun it). ``in_gutter``: the planner's sits in the
    page's top gutter (theme.css), so its top card keeps the side panel's top edge."""
    key = f"mode_switch_{current}"
    st.session_state[key] = MODES[current]
    with st.container(key="mc-mode-switch-gutter" if in_gutter else "mc-mode-switch",
                      horizontal=True, horizontal_alignment="right"):
        st.radio("Version", list(MODES.values()), key=key, horizontal=True,
                 label_visibility="collapsed", on_change=_on_mode_switch, args=(key,))


def _render_simple() -> None:
    """The simple money check-up (components.simple_mode), with a way across."""
    with st.container(key="mc-simple-root"):
        _mode_switch("simple")
        _safe_render("components.simple_mode")
        with st.container(border=True, key="mc-tile-simple-privacy"):
            st.markdown('<div class="mc-section">Your data</div>', unsafe_allow_html=True)
            _privacy_controls(st)


def _topbar_settings(_st) -> None:
    """Theme / profile / save-load — lives in the top bar's Settings popover."""
    _privacy_controls(_st)
    _st.divider()
    _safe_render("components.theme_toggle")
    _st.divider()
    _safe_render("components.profile_picker")
    _safe_render("components.save_load")
    _safe_render("components.print_summary")
    _safe_render("components.export_page")
    _safe_render("components.cache_panel")


def _inject_keyboard_nav() -> None:
    """Arrow-key navigation for the sidebar sections, injected via a 0-height
    component iframe that reaches the parent document:
      ArrowUp / ArrowDown  -> move the highlighted section up / down
      ArrowRight / ArrowLeft -> expand / collapse the highlighted section
    Ignored while typing in an input / slider / dropdown. Installed once
    (guarded on window.parent) so reruns don't stack listeners.
    """
    import streamlit.components.v1 as components
    components.html(
        """
        <script>
        (function(){
          const P = window.parent;
          const doc = P.document;

          // ---- Segmented-toggle tagging (RE-INSTALLED on every iframe load) ----
          // Tag horizontal radio groups (flex-direction:row) so CSS renders them
          // as soft-segmented toggles; vertical mode-radios keep their layout.
          // This must refresh on each render: Streamlit recreates this component
          // iframe on every full rerun, tearing down the previous iframe's JS
          // realm and killing its MutationObserver. A one-time guard therefore
          // left a DEAD observer after the first run, so result-area chart
          // toggles (rendered on later runs) never got tagged. We define a fresh
          // tagger bound to THIS live realm, disconnect/clear any stale
          // observer+timer, and add a low-frequency interval as a safety net for
          // fragment reruns (which don't recreate the iframe).
          // Only inspect radiogroups that are NOT yet classified — once each is
          // tagged .mc-seg (horizontal) or data-mc-vert (vertical), it's skipped,
          // so the interval does ~zero work at idle (no periodic getComputedStyle
          // forced-style-recalc, which was a source of micro-stutter).
          function tagRadios(){
            doc.querySelectorAll('[role="radiogroup"]:not(.mc-seg):not([data-mc-vert])').forEach(function(g){
              try {
                if (P.getComputedStyle(g).flexDirection === 'row') g.classList.add('mc-seg');
                else g.setAttribute('data-mc-vert', '1');
              } catch(e){}
            });
          }
          tagRadios();
          if (P.__mcTagInterval) { try { P.clearInterval(P.__mcTagInterval); } catch(e){} }
          if (P.__mcTagObserver) { try { P.__mcTagObserver.disconnect(); } catch(e){} }
          // The MutationObserver below re-tags on any DOM change (incl. fragment
          // reruns), so no idle polling interval is needed — keeps idle at zero work.
          try {
            let _pending = false;
            P.__mcTagObserver = new P.MutationObserver(function(){
              if (_pending) return; _pending = true;
              P.setTimeout(function(){ _pending = false; tagRadios(); }, 60);
            });
            P.__mcTagObserver.observe(doc.body, {childList: true, subtree: true});
          } catch(e){}

          // ---- Keyboard nav (install ONCE; one keydown listener is enough) ----
          if (doc.__mcArrowNav) return;
          doc.__mcArrowNav = true;

          let idx = -1;
          function expanders(){
            const sb = doc.querySelector('[data-testid="stSidebar"]');
            if (!sb) return [];
            // Top-level section expanders only — skip expanders nested inside
            // another section (they'd be hidden when their parent is collapsed).
            return Array.from(sb.querySelectorAll('[data-testid="stExpander"]'))
              .filter(e => !e.parentElement.closest('[data-testid="stExpander"]'));
          }
          function paint(list){
            list.forEach((e,i)=> e.classList.toggle('mc-kbd-focus', i===idx));
            if(list[idx]) list[idx].scrollIntoView({block:'nearest'});
          }
          function isOpen(e){ const d=e.querySelector('details'); return d ? d.open : false; }
          function summ(e){ return e.querySelector('summary'); }
          doc.addEventListener('keydown', function(ev){
            const ae = doc.activeElement;
            if (ae) {
              const t = ae.tagName;
              if (t==='INPUT'||t==='TEXTAREA'||t==='SELECT'||ae.isContentEditable) return;
              if (ae.getAttribute && ae.getAttribute('role')==='slider') return;
              if (ae.closest && (ae.closest('[data-baseweb="select"]')||ae.closest('[data-baseweb="slider"]'))) return;
            }
            const k = ev.key;
            if (k!=='ArrowUp'&&k!=='ArrowDown'&&k!=='ArrowLeft'&&k!=='ArrowRight') return;
            const list = expanders();
            if(!list.length) return;
            if(idx>=list.length) idx=list.length-1;
            if(k==='ArrowDown'){ idx = idx<0 ? 0 : Math.min(idx+1, list.length-1); }
            else if(k==='ArrowUp'){ idx = idx<0 ? 0 : Math.max(idx-1, 0); }
            else {
              if(idx<0) idx=0;
              const open = isOpen(list[idx]); const s = summ(list[idx]);
              if(k==='ArrowRight' && !open && s){ s.click(); }
              if(k==='ArrowLeft' && open && s){ s.click(); }
            }
            paint(list);
            ev.preventDefault();
          }, true);
        })();
        </script>
        """,
        height=0,
    )


def _spending_stats(st) -> list:
    """Top-card figures for the Spending view: average monthly spending and months counted."""
    try:
        from components.spending_dashboard import statement_data, session_actual
        data = statement_data(st)
        if data is None:
            return [("Statements", "none yet")]
        monthly = sum(session_actual(st, data).values())
        return [("Average spending / month", f"${monthly:,.0f}", "Avg spend / month"),
                ("Months counted", str(len(data["complete"])))]
    except Exception:
        return [("Statements", "unavailable")]


def main() -> None:
    _inject_css()
    _init_state()

    # Dark-mode + font CSS must be injected always (not only when the Settings
    # popover is open), so it happens here at the top based on persisted state.
    try:
        from components.theme_toggle import inject_theme_css, inject_font_css
        inject_theme_css(st)
        inject_font_css(st)
    except Exception:
        pass

    # Animation & interaction layer (hover, count-up, reveals, ripple, sliding
    # segmented indicator, celebration confetti, …). Injected after the theme so
    # its CSS can reference the theme tokens; the JS engine re-installs per run.
    try:
        from components.animations import inject_animations
        inject_animations(st)
    except Exception:
        pass

    # Saved inputs live only in the visitor's own browser (opt-in "Remember me").
    # The first run of each session waits for the browser to answer, so the
    # welcome screen doesn't flash before a remembered choice is restored.
    from utils import device_store
    store = device_store.sync(st)
    if store["status"] == "loading" and not st.session_state.get("_device_skip"):
        _loading_screen()
        st.stop()
    _restore_from_device(store)

    # Which version: the welcome screen picks; the simple check-up and the full
    # planner each render on their own (the simple one never touches the engine).
    mode = _resolve_mode()
    if mode is None:
        with st.container(key="mc-welcome"):
            from components import welcome
            chosen = welcome.render(st)
        if chosen:
            st.session_state.app_mode = chosen
            st.rerun()
        return
    if mode == "simple":
        _render_simple()
        _save_to_device()
        return

    # Browser computation: drawn first on every full-mode run (hidden) so its
    # workers stay alive across reruns -- including during the guided setup,
    # which gives them time to download Pyodide before the first run.
    from utils import browser_compute
    browser_compute.render(st)
    if browser_compute.pending(st) and _bc_poll is not None:
        _bc_poll()

    # New planner visitors get the guided setup first, starting from their
    # check-up answers if they used it. It replaces the planner and its side
    # panel until they finish or skip.
    from components import guided_setup
    if not guided_setup.started(st):
        guided_setup.begin(st, st.session_state.get("simple_inputs"))
    if guided_setup.active(st):
        with st.container(key="mc-setup-root"):
            _mode_switch("full")
            _safe_render("components.guided_setup")
        _save_to_device()
        return
    _mode_switch("full", in_gutter=True)

    # Full-width slot for the Run-simulation progress bar. Created BEFORE the top
    # bar (whose Run button fires inline during its own render) so the bar has the
    # whole content width — inside the narrow top-bar column its label wrapped at
    # 100%. Empty renders zero-height, so it's invisible outside a run.
    progress_slot = st.empty()

    # -------- Fixed top bar (full width) --------
    # Metrics + Run button + simulation-count selector + a Settings popover
    # (theme / profile / save-load).
    #
    # The slot is created HERE (so the bar keeps its DOM position above the main
    # panel) but is FILLED AFTER the sidebar renders. The sidebar sections are
    # what write the widget values back into ``user_overrides``
    # (e.g. sec_about_you -> TARGET_RETIREMENT_AGE); rendering the bar before
    # them made every metric read the PREVIOUS rerun's overrides, so the top bar
    # sat one edit behind the sidebar (drag the age slider 40->43 and the bar
    # showed 42). Deferring the fill makes it read post-sidebar state.
    # The top card is built NOW: its toolbar row (Retirement plan | Spending
    # switch, plus empty slots for the controls) and an empty slot for the
    # metrics row; the slots are filled after the sidebar + autorun (below). Drawing the switch here keeps it usable during a
    # cold-cache autorun, and deciding the view before the autorun means opening
    # Spending never waits on a Monte Carlo (it shares nothing with the
    # simulation). The autorun's once-per-session guard is untouched, so it fires
    # the first time the plan view is shown.
    topbar_slot = st.empty()
    with topbar_slot.container(key="mc-topbar"):
        view, control_slots = _topbar_head(st)
        spending_view = view == "Spending"
        topbar_body = st.empty()

    # -------- Sidebar (inputs) --------
    with st.sidebar:
        # Linear walkthrough, in advisor order (9 sections + FAQ).
        _safe_render("components.sec_about_you")
        _safe_render("components.account_inputs")     # 🏦 Starting balances
        _safe_render("components.sec_income")
        _safe_render("components.sec_taxes")
        _safe_render("components.sec_expenses")
        _safe_render("components.sec_big_purchases")
        _safe_render("components.sec_savings")
        _safe_render("components.sec_retirement_goals")
        _safe_render("components.sec_early_access")
        _safe_render("components.sec_assumptions")

        _safe_render("components.faq")
        # Phones only (theme.css): a sticky button that closes the full-screen
        # inputs panel, and starts the run when inputs changed (page script).
        st.markdown('<div class="mc-show-results"><a role="button" data-mc-show-results="1">'
                    'Show results</a></div>', unsafe_allow_html=True)

    # Compute everything the page shows, without waiting for button clicks.
    # Must run AFTER the sidebar has synced user_overrides (so it uses the real
    # inputs) and BEFORE the top bar / main panel paint (so they see results).
    if not spending_view:
        _autorun_all(progress_container=progress_slot)
    if st.session_state.get("_main_pending"):
        progress_slot.progress(0.9, text="Finishing in your browser…")

    # Now that the sidebar has synced user_overrides, paint the top bar.
    with topbar_body:
        _safe_render("components.top_bar",
                     results=st.session_state.results,
                     overrides=st.session_state.user_overrides,
                     profile=st.session_state.get("profile"),
                     run_render=functools.partial(_topbar_run, progress_container=progress_slot),
                     sims_render=_topbar_sims,
                     settings_render=_topbar_settings,
                     in_card=True, control_slots=control_slots,
                     title="Spending" if spending_view else "Retirement Monte Carlo",
                     stats=_spending_stats(st) if spending_view else None)


    # Spending view: statements only, no simulation.
    # Inputs are final here (sidebar synced, top card drawn): save now, not at
    # the end of the run -- the lazy chart sections below trigger reruns that
    # often cut a long run short before it reaches the bottom.
    _save_to_device()

    if spending_view:
        _safe_render("components.spending_dashboard")
        return

    if guided_setup.skipped(st):
        guided_setup.render_banner(st)

    # -------- Main panel — organized into topic sections --------
    # Deterministic charts auto-update from sidebar inputs; results-dependent
    # ones fill in after a run. Each section renders regardless so its layout is
    # stable; the results-based pieces self-guard (render nothing pre-run).
    results = st.session_state.results
    whatif_results = st.session_state.get("whatif_results")

    def _subheader(text: str) -> None:
        st.markdown(f'<div class="mc-section">{text}</div>', unsafe_allow_html=True)

    def _run_hint(what: str) -> None:
        if results is None:
            st.caption(f"Run a simulation to see {what}.")

    # Staleness banner. The top bar recomputes Net worth / Income / Target age
    # LIVE from the sidebar but takes Success rate from the stored run, so after
    # any edit the two disagree with no marker. The fingerprint recorded by
    # `_run_simulation` already tracks exactly this (it's what disables the Run
    # button) — surface it, the way the FI-number and SWR sections do for their
    # own cached results.
    _phone_bar(results)

    if _results_are_stale():
        st.warning("Your inputs changed since this simulation ran — the results "
                   "below (including the top-bar success rate) are from the "
                   "previous inputs. Click **Run simulation** to refresh.")

    # ============================ 1. RETIREMENT ============================
    with st.container(border=True, key="mc-tile-retirement"):
        st.markdown('<div class="mc-section">Retirement</div>', unsafe_allow_html=True)
        @_as_fragment
        def _sec_portfolio():
            _safe_render("components.portfolio_breakdown",
                         user_overrides=st.session_state.user_overrides, show_header=False)
        _sec_portfolio()
        _safe_render("components.net_worth_projection_chart", results=results)
        if results:
            _safe_render("components.hero_metric", results=results)
            _safe_render("components.decision_narrative", results=results)
            _safe_render("components.success_by_age", results=results)
            _safe_render("components.stats_row", results=results)
            # Below-the-fold Retirement charts — lazy (load as you scroll down).
            @_as_fragment
            def _sec_ret_more():
                if st.session_state.get("_lz_ret_more"):
                    _safe_render("components.net_worth_box_chart", results=results)
                    _safe_render("components.first_decade_stress", results=results)
                    _safe_render("components.allocation_chart", results=results)
                else:
                    _lazy_ph("ret_more", 700)
            _sec_ret_more()
        else:
            _run_hint("your earliest retirement age, success rate, and portfolio projection")

    # ==================== 1b. NET WORTH TO RETIRE (FI number) ====================
    # "How much do we need?" (net-worth trigger) as a complement to "when?".
    # Self-contained: has its own button + sweep, independent of the main run.
    with st.container(border=True, key="mc-tile-fi"):
        _safe_render("components.fi_number_section")

    # ==================== 1c. SAFE WITHDRAWAL RATE ====================
    # Personalized 4%-rule: button-gated sweep (independent of the main run).
    with st.container(border=True, key="mc-tile-swr"):
        _safe_render("components.swr_curve_section", results=results)

    # ==================== 1d. BRIDGE TO 59½ ====================
    # Penalty-free liquidity through the pre-59.5 gap years (results-dependent).
    if results:
        with st.container(border=True, key="mc-tile-bridge"):
            _safe_render("components.bridge_years_gauge", results=results)

    # ============================ 2. SPENDING ============================
    @_as_fragment
    def _tile_spending():
        with st.container(border=True, key="mc-tile-spending"):
            st.markdown('<div class="mc-section">Spending</div>', unsafe_allow_html=True)
            if st.session_state.get("_lz_spending"):
                _safe_render("components.spending_chart", results=results)
                if results:
                    _safe_render("components.spending_range_chart", results=results)
                    _safe_render("components.withdrawal_drawdown_chart", results=results)
            else:
                _lazy_ph("spending", 460)
    _tile_spending()

    # ============================ 3. SAVINGS ============================
    @_as_fragment
    def _tile_savings():
        with st.container(border=True, key="mc-tile-savings"):
            st.markdown('<div class="mc-section">Savings</div>', unsafe_allow_html=True)
            if st.session_state.get("_lz_savings"):
                # Both charts show the simulation's own contributions, so they
                # need a run (as the savings-rate chart always did).
                if results:
                    _safe_render("components.savings_projection_chart", results=results)
                    _safe_render("components.savings_rate_chart", results=results)
                else:
                    _run_hint("your savings by account and savings rate over time")
            else:
                _lazy_ph("savings", 440)
    _tile_savings()

    # ============================ 4. INCOME ============================
    @_as_fragment
    def _tile_income():
        with st.container(border=True, key="mc-tile-income"):
            st.markdown('<div class="mc-section">Income</div>', unsafe_allow_html=True)
            if st.session_state.get("_lz_income"):
                _safe_render("components.income_over_time", results=results)
            else:
                _lazy_ph("income", 440)
    _tile_income()

    # ============================ 5. TAX ============================
    @_as_fragment
    def _tile_tax():
        with st.container(border=True, key="mc-tile-tax"):
            st.markdown('<div class="mc-section">Tax</div>', unsafe_allow_html=True)
            if st.session_state.get("_lz_tax"):
                if results:
                    _safe_render("components.tax_tab", results=results)
                else:
                    _run_hint("your projected taxes by year")
            else:
                _lazy_ph("tax", 440)
    _tile_tax()

    # ======================= LIFE EXPECTANCY =======================
    # Placed just above What-if (per layout). Lazy: renders when scrolled near;
    # each tile is its own fragment, so loading one doesn't touch the others.
    @_as_fragment
    def _tile_lifespan():
        with st.container(border=True, key="mc-tile-lifespan"):
            if st.session_state.get("_lz_lifespan"):
                _safe_render("components.life_expectancy_section")
            else:
                _lazy_ph("lifespan", 440)
    _tile_lifespan()

    # ============================ 6. WHAT IF ============================
    # Collapsed by default AND lazy — its charts (incl. 3 deep-dive tabs) render
    # only once the section is expanded and scrolled to, so they never load on
    # the initial results burst.
    with st.expander("What if", expanded=False, icon=":material/compare_arrows:"):
        @_as_fragment
        def _tile_whatif():
            if not results:
                st.caption("Run a simulation to see what-if scenario comparisons and "
                           "deep-dive analyses.")
            elif st.session_state.get("_lz_whatif"):
                _safe_render("components.whatif_retirement_curve", results=results)
                st.divider()
                if whatif_results and whatif_results.get("active_toggles"):
                    _safe_render("components.what_if_pane", results=whatif_results)
                _safe_render("components.scenario_compare", results=results)
                _subheader("Deep dives")
                tabs = st.tabs(["Trajectories", "Withdrawal", "Sensitivity", "Stress tests", "Mortgage paydown"])
                with tabs[0]:
                    _safe_render("components.trajectories_tab", results=results)
                with tabs[1]:
                    _safe_render("components.withdrawal_tab", results=results)
                with tabs[2]:
                    _safe_render("components.sensitivity_tab", results=results)
                with tabs[3]:
                    _safe_render("components.stress_presets", results=results)
                with tabs[4]:
                    _safe_render("components.mortgage_paydown_tab", results=results)
            else:
                _lazy_ph("whatif", 500)
        _tile_whatif()

    # Arrow-key navigation for the sidebar sections (injected once).
    _inject_keyboard_nav()

    # After the page is drawn: a browser job the server must take over, then
    # the analyses queued for the server (one per run, each followed by a rerun).
    if browser_compute.take_over_one(st):
        st.rerun()
    if browser_compute.unsent(st):
        st.rerun()                      # hand the new jobs to the browser
    _server_extras_step()


if __name__ == "__main__":
    # One visitor's rerun at a time: the UI and the engine share one config module
    # (see sim_runner.CONFIG_LOCK), so overlapping sessions could see each other's
    # inputs. Reruns from cache take well under a second; a fresh simulation makes
    # other visitors wait for it to finish.
    from utils.sim_runner import CONFIG_LOCK
    with CONFIG_LOCK:
        main()
