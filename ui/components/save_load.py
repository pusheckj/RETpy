"""Sidebar component for saving/loading a profile of user inputs.

Renders inside an expander at the top of the sidebar. Lets the user:
  - Download the current ``st.session_state.user_overrides`` as a JSON file.
  - Upload a previously saved JSON file AND explicitly click "Load" to apply.

The explicit two-step (upload → click Load) avoids the uploader
auto-retriggering on every rerun, which was causing sidebar values to reset
after clicking "Run simulation".
"""
from __future__ import annotations

from datetime import date

try:
    # Preferred: package-relative import.
    from utils.config_builder import comp_table_edited_by_hand
    from utils.file_reader import read_file
    from utils.profile_io import serialize_overrides, deserialize_overrides
    from utils.widget_sync import (
        sync_widgets_from_overrides,
        reset_input_widget_state,
    )
except Exception:  # pragma: no cover - fallback for unusual sys.path configs
    from ui.utils.config_builder import comp_table_edited_by_hand  # type: ignore
    from ui.utils.file_reader import read_file  # type: ignore
    from ui.utils.profile_io import serialize_overrides, deserialize_overrides  # type: ignore
    from ui.utils.widget_sync import (  # type: ignore
        sync_widgets_from_overrides,
        reset_input_widget_state,
    )


def _apply_restored(st, restored: dict, source_name: str) -> None:
    """Wipe known widget state, install the restored overrides, and repopulate."""
    # Shared with the profile dropdown so both paths clear the SAME keys — this
    # previously cleared only the mapped keys, leaving the compensation editor
    # (and its "customized" flag) holding the prior profile's numbers, which
    # were then fed straight back into the simulation.
    reset_input_widget_state(st)
    st.session_state["user_overrides"] = dict(restored)
    # The Income section always writes the pay table, so only a table that differs from
    # the one built from the saved inputs counts as edited by hand.
    st.session_state["si_comp_customized"] = comp_table_edited_by_hand(restored)
    st.session_state["profile"] = "Custom (keep current values)"
    st.session_state["results"] = None  # stale after a load
    # Follow-ups still computing (pool) or queued belong to the old inputs: cancel them, and
    # bump the generation so a chunk that finishes later is dropped.
    try:
        from utils import sim_runner as _sr
        _sr.cancel_entries(st.session_state.pop("_extras_bg", None))
    except Exception:  # pragma: no cover
        st.session_state.pop("_extras_bg", None)
    st.session_state.pop("_extras_pending", None)
    st.session_state["_extras_gen"] = st.session_state.get("_extras_gen", 0) + 1
    sync_widgets_from_overrides(st)
    st.session_state["_save_load_last_load"] = source_name


def render(st) -> None:
    # The load button reruns the app, so its success message is kept in session
    # state and shown on the next run (it would be gone before it was painted).
    loaded_msg = st.session_state.pop("_save_load_msg", None)
    if loaded_msg:
        st.success(loaded_msg)
    with st.expander("Save / Load profile", expanded=False, icon=":material/save:"):
        overrides = st.session_state.get("user_overrides", {}) or {}

        # --- Download ---
        try:
            json_blob = serialize_overrides(overrides)
            filename = f"retirement_inputs_{date.today().isoformat()}.json"
            st.download_button(
                label="⬇ Download current inputs",
                data=json_blob,
                file_name=filename,
                mime="application/json",
                width="stretch",
                key="save_load_download_btn",
            )
        except Exception as exc:
            st.error(f"Couldn't prepare the download: {exc}")

        st.caption("Save your inputs to restore or share later.")

        st.markdown(
            '<hr style="margin: 12px 0 8px 0; border: 0; border-top: 1px solid #e5e7eb;">',
            unsafe_allow_html=True,
        )

        # --- Upload: explicit two-step (stage a file, then click Load) ---
        # The browser reads the file itself (utils/file_reader.py): st.file_uploader's separate
        # HTTP upload fails on phones whose connection drops while the file picker is open.
        n = st.session_state.get("_save_load_upload_n", 0)
        uploaded = read_file(st, "Upload saved inputs", key=f"save_load_upload_{n}")

        # Preview + Load button appear only when a file is staged.
        if uploaded is not None:
            # Parse once per file to offer a preview.
            try:
                preview = deserialize_overrides(uploaded["text"])
            except ValueError as exc:
                st.error(f"Couldn't read that file: {exc}")
                preview = None
            except Exception as exc:  # pragma: no cover
                st.error(f"Something went wrong reading that file: {exc}")
                preview = None

            if isinstance(preview, dict):
                st.caption(f"**{uploaded['name']}**: {len(preview)} inputs ready to load.")
                if st.button(
                    "Load these inputs",
                    key="save_load_apply_btn",
                    width="stretch",
                    type="primary",
                ):
                    _apply_restored(st, preview, uploaded["name"])
                    st.session_state["_save_load_msg"] = f"Loaded {len(preview)} inputs from {uploaded['name']}."
                    # A new component key clears the staged file, so the button goes away.
                    st.session_state["_save_load_upload_n"] = n + 1
                    st.session_state.pop(f"save_load_upload_{n}", None)   # drop the file's text
                    try:
                        st.rerun()
                    except Exception:
                        pass
            elif preview is not None:
                st.error("That file doesn't contain saved inputs.")

        # Show the last-loaded filename (nice touch for the user).
        last = st.session_state.get("_save_load_last_load")
        if last:
            st.caption(f"Last loaded: {last}")
