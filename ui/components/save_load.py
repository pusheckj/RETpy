"""Sidebar component for saving/loading a profile of user inputs.

Renders inside an expander at the top of the sidebar. Lets the user:
  - Download the current ``st.session_state.user_overrides`` as a JSON file.
  - Upload a previously saved JSON file AND explicitly click "Load" to apply.

The explicit two-step (upload → click Load) avoids the file_uploader
auto-retriggering on every rerun, which was causing sidebar values to reset
after clicking "Run simulation".
"""
from __future__ import annotations

from datetime import date

try:
    # Preferred: package-relative import.
    from utils.profile_io import serialize_overrides, deserialize_overrides
    from utils.widget_sync import (
        sync_widgets_from_overrides,
        reset_input_widget_state,
    )
except Exception:  # pragma: no cover - fallback for unusual sys.path configs
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
    st.session_state["si_comp_customized"] = bool(restored.get("YOUR_COMPENSATION_BY_AGE"))
    st.session_state["profile"] = "Custom (keep current values)"
    st.session_state["results"] = None  # stale after a load
    sync_widgets_from_overrides(st)
    st.session_state["_save_load_last_load"] = source_name


def render(st) -> None:
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
            st.error(f"Could not prepare download: {exc}")

        st.caption("Save your inputs to restore or share later.")

        st.markdown(
            '<hr style="margin: 12px 0 8px 0; border: 0; border-top: 1px solid #e5e7eb;">',
            unsafe_allow_html=True,
        )

        # --- Upload: explicit two-step (stage a file, then click Load) ---
        uploaded = st.file_uploader(
            "Upload saved inputs",
            type=["json"],
            key="save_load_upload",
        )

        # Preview + Load button appear only when a file is staged.
        if uploaded is not None:
            # Parse once per file to offer a preview.
            try:
                raw = uploaded.getvalue()
                if isinstance(raw, bytes):
                    raw_text = raw.decode("utf-8")
                else:
                    raw_text = str(raw)
                preview = deserialize_overrides(raw_text)
            except ValueError as exc:
                st.error(f"Could not parse file: {exc}")
                preview = None
            except Exception as exc:  # pragma: no cover
                st.error(f"Unexpected error reading file: {exc}")
                preview = None

            if isinstance(preview, dict):
                st.caption(f"**{uploaded.name}** — {len(preview)} input(s) ready.")
                if st.button(
                    "📥 Load staged profile",
                    key="save_load_apply_btn",
                    width="stretch",
                    type="primary",
                ):
                    _apply_restored(st, preview, uploaded.name)
                    st.success(f"Loaded {len(preview)} input(s) from {uploaded.name}.")
                    try:
                        st.rerun()
                    except Exception:
                        pass
            elif preview is not None:
                st.error("Uploaded file did not contain a valid overrides dict.")

        # Show the last-loaded filename (nice touch for the user).
        last = st.session_state.get("_save_load_last_load")
        if last:
            st.caption(f"Last loaded: {last}")
