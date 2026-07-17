from __future__ import annotations

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import streamlit as st

# =============================================================================
# LOCAL APPLICATION IMPORTS
# =============================================================================
from data import (
    EXCEL_MAX_DATA_ROWS,
    TIME_ZONE,
    PortalDataError,
    build_series_specs,
    count_export_rows,
    create_export_file,
    database_ready,
    get_metadata,
    get_variable_groups,
    human_file_size,
    overall_time_bounds,
)


# =============================================================================
# EXPORT PAGE SETTINGS
# =============================================================================
TIME_RANGE_OPTIONS = [
    "Entire Dataset",
    "Last Week",
    "Last Day",
    "Last Hour",
    "Last 10 Minutes",
    "Custom Range",
]


# =============================================================================
# PAGE HEADER
# =============================================================================
st.title("Export Center")
st.write(
    "Select any combination of bridge variables and export the filtered result "
    "as one CSV or one Excel file. Variables are aligned by exact timestamp."
)
st.caption(
    "Because the three datasets use different sampling frequencies, cells remain "
    "blank when a selected variable has no reading at another dataset's timestamp."
)


# =============================================================================
# DATA AVAILABILITY CHECK
# =============================================================================
if not database_ready():
    st.warning("Press Load Data on the Home page before exporting data.")
    st.page_link(
        "pages/home.py",
        label="Return to Home",
        icon=":material/home:",
    )
    st.stop()

metadata = get_metadata()
data_start_unix, data_end_unix = overall_time_bounds(metadata)
eastern_zone = ZoneInfo(TIME_ZONE)
data_start_datetime = datetime.fromtimestamp(data_start_unix, eastern_zone)
data_end_datetime = datetime.fromtimestamp(data_end_unix, eastern_zone)


# =============================================================================
# TIME RANGE RESOLUTION
# =============================================================================
def combine_local_date_and_time(selected_date, selected_time) -> datetime:
    """Combine Streamlit date/time inputs into a timezone-aware portal datetime."""
    # Streamlit normally returns one date. This guard also handles the unlikely
    # case where a browser/session returns a one-item tuple.
    if isinstance(selected_date, tuple):
        selected_date = selected_date[0]

    return datetime.combine(selected_date, selected_time).replace(tzinfo=eastern_zone)


def resolve_selected_time_range(
    selected_range: str,
    use_data_start: bool,
    start_date,
    start_time,
    use_data_end: bool,
    end_date,
    end_time,
) -> tuple[float, float]:
    """Convert Export Center time controls into Unix timestamps."""
    if selected_range == "Entire Dataset":
        return data_start_unix, data_end_unix
    if selected_range == "Last Week":
        return data_end_unix - 7 * 24 * 60 * 60, data_end_unix
    if selected_range == "Last Day":
        return data_end_unix - 24 * 60 * 60, data_end_unix
    if selected_range == "Last Hour":
        return data_end_unix - 60 * 60, data_end_unix
    if selected_range == "Last 10 Minutes":
        return data_end_unix - 10 * 60, data_end_unix

    start_datetime = (
        data_start_datetime
        if use_data_start
        else combine_local_date_and_time(start_date, start_time)
    )
    end_datetime = (
        data_end_datetime
        if use_data_end
        else combine_local_date_and_time(end_date, end_time)
    )
    if end_datetime <= start_datetime:
        raise PortalDataError("End Time must be after Start Time.")
    return float(start_datetime.timestamp()), float(end_datetime.timestamp())


# =============================================================================
# EXPORT SELECTION CONTROLS
# =============================================================================
selection_column, output_column = st.columns([1, 2], gap="large")

with selection_column:
    with st.container(border=True):
        st.subheader("Export Selection")
        selected_range = st.selectbox(
            "Time Range",
            TIME_RANGE_OPTIONS,
            index=0,
            key="export_time_range",
        )

        use_data_start = True
        use_data_end = True
        start_date = data_start_datetime.date()
        start_time = data_start_datetime.time().replace(microsecond=0)
        end_date = data_end_datetime.date()
        end_time = data_end_datetime.time().replace(microsecond=0)

        if selected_range == "Custom Range":
            st.markdown("#### Start Time")
            use_data_start = st.checkbox(
                "Use start of data",
                value=True,
                key="export_use_data_start",
            )
            start_date = st.date_input(
                "Start Date",
                value=data_start_datetime.date(),
                disabled=use_data_start,
                key="export_start_date",
            )
            start_time = st.time_input(
                "Start Time",
                value=data_start_datetime.time().replace(microsecond=0),
                step=60,
                disabled=use_data_start,
                key="export_start_time",
            )

            st.markdown("#### End Time")
            use_data_end = st.checkbox(
                "Use end of data",
                value=True,
                key="export_use_data_end",
            )
            end_date = st.date_input(
                "End Date",
                value=data_end_datetime.date(),
                disabled=use_data_end,
                key="export_end_date",
            )
            end_time = st.time_input(
                "End Time",
                value=data_end_datetime.time().replace(microsecond=0),
                step=60,
                disabled=use_data_end,
                key="export_end_time",
            )

        st.markdown("#### Minimum Point Frequency")
        frequency_left, frequency_right = st.columns(2)
        with frequency_left:
            frequency_minutes = st.number_input(
                "Minutes",
                min_value=0,
                value=0,
                step=1,
                key="export_frequency_minutes",
            )
        with frequency_right:
            frequency_seconds = st.number_input(
                "Seconds",
                min_value=0,
                value=0,
                step=1,
                key="export_frequency_seconds",
            )

        st.markdown("#### Variables")
        selections: dict[str, list[str]] = {}
        for group in get_variable_groups(metadata):
            selections[group["key"]] = st.multiselect(
                group["label"],
                options=group["variables"],
                default=[],
                key=f"export_variables_{group['key']}",
            )

        calculate_export = st.button(
            "Calculate Export Size",
            type="primary",
            width="stretch",
            key="export_calculate_button",
        )


# =============================================================================
# SELECTION FINGERPRINT
# A fingerprint prevents an old row count or file from being reused after the
# user changes variables, dates, or frequency settings.
# =============================================================================
fingerprint_document = {
    "selected_range": selected_range,
    "use_data_start": use_data_start,
    "start_date": str(start_date),
    "start_time": str(start_time),
    "use_data_end": use_data_end,
    "end_date": str(end_date),
    "end_time": str(end_time),
    "frequency_minutes": int(frequency_minutes),
    "frequency_seconds": int(frequency_seconds),
    "selections": selections,
}
current_fingerprint = json.dumps(fingerprint_document, sort_keys=True)

if (
    st.session_state.get("export_fingerprint")
    and st.session_state.get("export_fingerprint") != current_fingerprint
):
    for key in (
        "export_fingerprint",
        "export_specs",
        "export_start_unix",
        "export_end_unix",
        "export_minimum_frequency",
        "export_row_count",
        "export_file_path",
        "export_file_format",
        "export_file_rows",
    ):
        st.session_state.pop(key, None)


# =============================================================================
# EXACT EXPORT ROW COUNT
# =============================================================================
if calculate_export:
    try:
        selected_specs = build_series_specs(metadata, selections)
        if not selected_specs:
            raise PortalDataError("Select at least one variable to export.")

        start_unix, end_unix = resolve_selected_time_range(
            selected_range,
            use_data_start,
            start_date,
            start_time,
            use_data_end,
            end_date,
            end_time,
        )
        minimum_frequency = max(
            0.0,
            float(frequency_minutes) * 60 + float(frequency_seconds),
        )

        with st.spinner("Calculating the exact combined export size..."):
            export_row_count = count_export_rows(
                selected_specs,
                start_unix,
                end_unix,
                minimum_frequency,
            )

        if export_row_count == 0:
            raise PortalDataError(
                "The selected variables contain no usable data in this time range."
            )

        st.session_state["export_fingerprint"] = current_fingerprint
        st.session_state["export_specs"] = selected_specs
        st.session_state["export_start_unix"] = start_unix
        st.session_state["export_end_unix"] = end_unix
        st.session_state["export_minimum_frequency"] = minimum_frequency
        st.session_state["export_row_count"] = export_row_count
        st.session_state.pop("export_file_path", None)
    except PortalDataError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"The export size could not be calculated: {exc}")


# =============================================================================
# FILE FORMAT AND EXPORT PREPARATION
# =============================================================================
with output_column:
    st.subheader("Export Options")

    if st.session_state.get("export_fingerprint") != current_fingerprint:
        st.info(
            "Choose variables and a time range, then press Calculate Export Size."
        )
    else:
        export_row_count = int(st.session_state.get("export_row_count", 0))
        excel_too_large = export_row_count > EXCEL_MAX_DATA_ROWS

        row_metric, excel_metric = st.columns(2)
        row_metric.metric("Combined Data Rows", f"{export_row_count:,}")
        excel_metric.metric(
            "Excel Data-Row Limit",
            f"{EXCEL_MAX_DATA_ROWS:,}",
        )

        st.markdown("#### File Format")
        if "export_selected_format" not in st.session_state:
            st.session_state["export_selected_format"] = "csv"

        if excel_too_large and st.session_state["export_selected_format"] == "excel":
            st.session_state["export_selected_format"] = "csv"
            st.session_state.pop("export_file_path", None)

        csv_column, excel_column = st.columns(2)
        with csv_column:
            if st.button(
                "CSV",
                type=(
                    "primary"
                    if st.session_state["export_selected_format"] == "csv"
                    else "secondary"
                ),
                width="stretch",
                key="csv_format_button",
            ):
                st.session_state["export_selected_format"] = "csv"
                st.session_state.pop("export_file_path", None)

        with excel_column:
            if excel_too_large:
                st.button(
                    "Excel",
                    disabled=True,
                    width="stretch",
                    key="excel_format_disabled",
                )
                st.markdown(
                    "<div class='excel-limit-message'>"
                    "Data set is too large for an Excel file"
                    "</div>",
                    unsafe_allow_html=True,
                )
            elif st.button(
                "Excel",
                type=(
                    "primary"
                    if st.session_state["export_selected_format"] == "excel"
                    else "secondary"
                ),
                width="stretch",
                key="excel_format_button",
            ):
                st.session_state["export_selected_format"] = "excel"
                st.session_state.pop("export_file_path", None)

        selected_format = st.session_state["export_selected_format"]
        st.write(f"Selected format: **{selected_format.upper()}**")

        prepare_file = st.button(
            f"Prepare {selected_format.upper()} File",
            type="primary",
            width="stretch",
            key="export_prepare_button",
        )

        if prepare_file:
            try:
                with st.spinner(
                    f"Creating one {selected_format.upper()} file in DuckDB..."
                ):
                    file_path, file_rows = create_export_file(
                        st.session_state["export_specs"],
                        float(st.session_state["export_start_unix"]),
                        float(st.session_state["export_end_unix"]),
                        float(st.session_state["export_minimum_frequency"]),
                        selected_format,
                    )

                st.session_state["export_file_path"] = str(file_path)
                st.session_state["export_file_format"] = selected_format
                st.session_state["export_file_rows"] = file_rows
                st.success(f"Prepared {file_rows:,} rows successfully.")
            except PortalDataError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"The export file could not be created: {exc}")

        prepared_path_value = st.session_state.get("export_file_path")
        if prepared_path_value:
            prepared_path = Path(prepared_path_value)
            if prepared_path.exists():
                prepared_format = st.session_state.get("export_file_format", "csv")
                mime_type = (
                    "text/csv"
                    if prepared_format == "csv"
                    else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.caption(
                    f"Ready: {prepared_path.name} "
                    f"({human_file_size(prepared_path.stat().st_size)})"
                )

                with prepared_path.open("rb") as prepared_file:
                    st.download_button(
                        "Download Export",
                        data=prepared_file,
                        file_name=prepared_path.name,
                        mime=mime_type,
                        type="primary",
                        width="stretch",
                        on_click="ignore",
                    )
            else:
                st.session_state.pop("export_file_path", None)
