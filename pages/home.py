from __future__ import annotations

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import pandas as pd
import streamlit as st

# =============================================================================
# LOCAL APPLICATION IMPORTS
# =============================================================================
from data import (
    PortalDataError,
    database_ready,
    format_unix_time,
    get_database_summary,
    get_metadata,
    initialize_database,
)


PAGE_TITLE = "Composite Bridge Data Portal"


# =============================================================================
# PAGE HEADER
# =============================================================================
st.title(PAGE_TITLE)
st.write(
    "Load the latest acceleration, deflection, and environmental data from "
    "Amazon S3 into DuckDB. After loading finishes, use the sidebar to graph "
    "or export the data."
)


# =============================================================================
# DATA LOAD BUTTON
# =============================================================================
if st.button("Load Data", type="primary", width="stretch"):
    progress_bar = st.progress(0.0, text="Preparing data load...")

    def update_progress(message: str, fraction: float) -> None:
        """Update the Home page progress indicator during S3 and DuckDB work."""
        progress_bar.progress(fraction, text=message)

    try:
        with st.status("Loading Composite Bridge data...", expanded=True) as status:
            status.write("Connecting to the private S3 bucket.")
            metadata, database_rebuilt = initialize_database(update_progress)
            status.write("Verifying the DuckDB tables and time ranges.")
            status.update(
                label="Composite Bridge data loaded successfully.",
                state="complete",
                expanded=False,
            )

        # Clear results created from an older database while retaining login state.
        for key in list(st.session_state.keys()):
            if key.startswith("graph_") or key.startswith("export_"):
                del st.session_state[key]

        st.session_state["home_last_load_rebuilt"] = database_rebuilt
        st.success(
            "The DuckDB database was rebuilt with the latest S3 data."
            if database_rebuilt
            else "The S3 files were unchanged, so the existing DuckDB database was reused."
        )
    except PortalDataError as exc:
        progress_bar.empty()
        st.error(str(exc))
    except Exception as exc:
        progress_bar.empty()
        st.error(f"An unexpected data-loading error occurred: {exc}")


# =============================================================================
# CURRENT DATABASE STATUS
# =============================================================================
st.divider()
st.subheader("Data Status")

if not database_ready():
    st.warning("The bridge data has not been loaded on this server yet.")
    st.info(
        "The first load can take several minutes because the three large CSV "
        "files must be downloaded and imported into DuckDB."
    )
else:
    metadata = get_metadata()
    summary = get_database_summary()
    st.markdown("<span class='portal-success'>● DuckDB is ready</span>", unsafe_allow_html=True)
    if summary.get("loaded_at"):
        st.caption(f"Last successful load: {summary['loaded_at']}")

    rows: list[dict[str, object]] = []
    for item in metadata.values():
        rows.append(
            {
                "Dataset": item.get("display_name", item.get("name", "Dataset")),
                "Rows": int(item.get("row_count", 0)),
                "First Reading": format_unix_time(float(item["start_unix"])),
                "Latest Reading": format_unix_time(float(item["end_unix"])),
            }
        )

    status_frame = pd.DataFrame(rows)
    st.dataframe(
        status_frame,
        hide_index=True,
        width="stretch",
        column_config={
            "Rows": st.column_config.NumberColumn(format="localized"),
        },
    )

    graph_column, export_column = st.columns(2)
    with graph_column:
        st.page_link(
            "pages/graphing.py",
            label="Open Graphing Page",
            icon=":material/show_chart:",
            width="stretch",
        )
    with export_column:
        st.page_link(
            "pages/export_center.py",
            label="Open Export Center",
            icon=":material/download:",
            width="stretch",
        )
analytics_column, about_column = st.columns(2)

with analytics_column:
    st.page_link(
        "pages/analytics.py",
        label="Open Analytics Page",
        icon=":material/analytics:",
        width="stretch",
    )

with about_column:
    st.page_link(
        "pages/about.py",
        label="Open About Page",
        icon=":material/info:",
        width="stretch",
    )
