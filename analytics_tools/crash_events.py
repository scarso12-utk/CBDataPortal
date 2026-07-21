from __future__ import annotations

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
from datetime import datetime
from zoneinfo import ZoneInfo

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import pandas as pd
import streamlit as st

# =============================================================================
# LOCAL APPLICATION IMPORTS
# =============================================================================
from data import (
    DATABASE_LOCK,
    TIME_ZONE,
    PortalDataError,
    configure_duckdb,
    connect_duckdb,
    database_ready,
    find_column,
    get_metadata,
    quote_identifier,
)


# =============================================================================
# VEHICLE EVENT SETTINGS
# =============================================================================
# Acceleration measurements separated by more than this amount begin a new
# burst. The bridge data examined during development contained approximately
# 80 measurements over 3.5 seconds in each burst.
DEFAULT_BURST_GAP_SECONDS = 1.0

# A Count increase may be written after the acceleration burst has ended.
# Forty-five seconds allows for the delayed Count update while keeping the
# association close enough to the preceding acceleration event.
DEFAULT_MAX_EVENT_DELAY_SECONDS = 45

TIME_RANGE_OPTIONS = [
    "Entire Overlapping Dataset",
    "Last Year",
    "Last 30 Days",
    "Last Week",
    "Custom Range",
]

RESULT_COLUMNS = [
    "Vehicle Event Time",
    "Acceleration End",
    "Count Update Time",
    "Count Increase",
    "Delay (seconds)",
    "Acceleration Samples",
    "Maximum Magnitude",
    "Maximum |X|",
    "Maximum |Y|",
    "Maximum |Z|",
    "Confirmation",
]


# =============================================================================
# TIME HELPERS
# =============================================================================
def combine_local_date_and_time(selected_date, selected_time) -> datetime:
    """Combine Streamlit date/time inputs in the portal's local time zone."""
    if isinstance(selected_date, tuple):
        selected_date = selected_date[0]
    return datetime.combine(selected_date, selected_time).replace(
        tzinfo=ZoneInfo(TIME_ZONE)
    )


def overlapping_time_bounds(
    metadata: dict[str, dict],
) -> tuple[float, float]:
    """Return the time range shared by acceleration and environmental data."""
    missing = [name for name in ("accell", "envir") if name not in metadata]
    if missing:
        raise PortalDataError(
            "Vehicle-event identification requires both accell.csv and envir.csv."
        )

    start_unix = max(
        float(metadata["accell"]["start_unix"]),
        float(metadata["envir"]["start_unix"]),
    )
    end_unix = min(
        float(metadata["accell"]["end_unix"]),
        float(metadata["envir"]["end_unix"]),
    )
    if end_unix <= start_unix:
        raise PortalDataError(
            "The loaded acceleration and environmental datasets do not overlap in time."
        )
    return start_unix, end_unix


def resolve_time_range(
    selected_range: str,
    overlap_start: float,
    overlap_end: float,
    start_date,
    start_time,
    end_date,
    end_time,
) -> tuple[float, float]:
    """Resolve the selected control values into Unix timestamps."""
    if selected_range == "Entire Overlapping Dataset":
        return overlap_start, overlap_end
    if selected_range == "Last Year":
        return max(overlap_start, overlap_end - 365 * 24 * 60 * 60), overlap_end
    if selected_range == "Last 30 Days":
        return max(overlap_start, overlap_end - 30 * 24 * 60 * 60), overlap_end
    if selected_range == "Last Week":
        return max(overlap_start, overlap_end - 7 * 24 * 60 * 60), overlap_end

    start_unix = float(combine_local_date_and_time(start_date, start_time).timestamp())
    end_unix = float(combine_local_date_and_time(end_date, end_time).timestamp())
    start_unix = max(start_unix, overlap_start)
    end_unix = min(end_unix, overlap_end)

    if end_unix <= start_unix:
        raise PortalDataError(
            "End Time must be after Start Time and within the overlapping data range."
        )
    return start_unix, end_unix


# =============================================================================
# SQL HELPERS
# =============================================================================
def numeric_expression(column: str | None) -> str:
    """Return a nullable numeric SQL expression for an optional column."""
    if column is None:
        return "NULL::DOUBLE"
    return f"TRY_CAST({quote_identifier(column)} AS DOUBLE)"


def query_count_increases(
    connection,
    metadata: dict[str, dict],
    start_unix: float,
    end_unix: float,
    lookback_seconds: float,
) -> pd.DataFrame:
    """Return only positive changes in the environmental Count value."""
    dataset = metadata["envir"]
    count_column = find_column(list(dataset.get("columns", [])), "Count")
    if count_column is None:
        raise PortalDataError("envir.csv does not contain a usable Count column.")

    table = quote_identifier(dataset["table"])
    time_expression = numeric_expression(dataset["time_col"])
    count_expression = numeric_expression(count_column)
    query_start = start_unix - max(120.0, lookback_seconds * 2.0)

    return connection.execute(
        f"""
        WITH source AS (
            SELECT
                {time_expression} AS time_num,
                {count_expression} AS count_num
            FROM {table}
            WHERE {time_expression} BETWEEN ? AND ?
              AND {count_expression} IS NOT NULL
        ),
        ordered AS (
            SELECT
                time_num,
                count_num,
                LAG(count_num) OVER (ORDER BY time_num) AS previous_count
            FROM source
        )
        SELECT
            time_num AS count_time,
            count_num - previous_count AS count_increase
        FROM ordered
        WHERE time_num BETWEEN ? AND ?
          AND count_num > previous_count
        ORDER BY time_num
        """,
        [query_start, end_unix, start_unix, end_unix],
    ).fetchdf()


def query_acceleration_bursts(
    connection,
    metadata: dict[str, dict],
    start_unix: float,
    end_unix: float,
    delay_seconds: float,
    burst_gap_seconds: float,
) -> pd.DataFrame:
    """Condense raw acceleration measurements into distinct bursts."""
    dataset = metadata["accell"]
    columns = list(dataset.get("columns", []))
    x_column = find_column(columns, "X")
    y_column = find_column(columns, "Y")
    z_column = find_column(columns, "Z")
    magnitude_column = find_column(columns, "Magnitude")

    if not any((x_column, y_column, z_column, magnitude_column)):
        raise PortalDataError(
            "accell.csv does not contain X, Y, Z, or Magnitude acceleration values."
        )

    time_expression = numeric_expression(dataset["time_col"])
    x_expression = numeric_expression(x_column)
    y_expression = numeric_expression(y_column)
    z_expression = numeric_expression(z_column)

    if magnitude_column is not None:
        magnitude_expression = numeric_expression(magnitude_column)
    elif all((x_column, y_column, z_column)):
        magnitude_expression = (
            f"SQRT(POW({x_expression}, 2) + POW({y_expression}, 2) "
            f"+ POW({z_expression}, 2))"
        )
    else:
        magnitude_expression = "NULL::DOUBLE"

    query_start = start_unix - delay_seconds - burst_gap_seconds
    table = quote_identifier(dataset["table"])

    return connection.execute(
        f"""
        WITH source AS (
            SELECT
                {time_expression} AS time_num,
                {magnitude_expression} AS magnitude_num,
                {x_expression} AS x_num,
                {y_expression} AS y_num,
                {z_expression} AS z_num
            FROM {table}
            WHERE {time_expression} BETWEEN ? AND ?
        ),
        ordered AS (
            SELECT
                *,
                LAG(time_num) OVER (ORDER BY time_num) AS previous_time
            FROM source
            WHERE time_num IS NOT NULL
        ),
        marked AS (
            SELECT
                *,
                CASE
                    WHEN previous_time IS NULL
                      OR time_num - previous_time > ?
                    THEN 1 ELSE 0
                END AS begins_burst
            FROM ordered
        ),
        grouped AS (
            SELECT
                *,
                SUM(begins_burst) OVER (
                    ORDER BY time_num ROWS UNBOUNDED PRECEDING
                ) AS burst_id
            FROM marked
        )
        SELECT
            MIN(time_num) AS burst_start,
            MAX(time_num) AS burst_end,
            COUNT(*) AS sample_count,
            MAX(magnitude_num) AS maximum_magnitude,
            MAX(ABS(x_num)) AS maximum_abs_x,
            MAX(ABS(y_num)) AS maximum_abs_y,
            MAX(ABS(z_num)) AS maximum_abs_z
        FROM grouped
        GROUP BY burst_id
        HAVING MAX(time_num) >= ? - ?
           AND MIN(time_num) <= ?
        ORDER BY burst_start
        """,
        [
            query_start,
            end_unix,
            burst_gap_seconds,
            start_unix,
            delay_seconds,
            end_unix,
        ],
    ).fetchdf()


# =============================================================================
# EVENT MATCHING
# =============================================================================
def match_confirmed_events(
    count_changes: pd.DataFrame,
    bursts: pd.DataFrame,
    max_delay_seconds: float,
) -> pd.DataFrame:
    """Match Count increases to completed acceleration bursts conservatively.

    The lookback window and reported delay are measured from each burst's end.
    A burst is confirmed only when the Count increase can accommodate every
    unmatched burst in that window. For example, one Count increase and two
    candidate bursts is ambiguous, so neither is reported as confirmed.
    """
    if count_changes.empty or bursts.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    available = bursts.copy().reset_index(drop=True)
    available["matched"] = False
    matched_rows: list[dict] = []

    for count_row in count_changes.itertuples(index=False):
        count_time = float(count_row.count_time)
        increase = max(1, int(round(float(count_row.count_increase))))
        earliest_time = count_time - max_delay_seconds

        candidates = available[
            (~available["matched"])
            & (available["burst_end"] >= earliest_time)
            & (available["burst_end"] <= count_time)
        ]

        # More acceleration bursts than counted vehicles makes the association
        # ambiguous. Excluding these cases favors precision over recall.
        if candidates.empty or len(candidates) > increase:
            continue

        for burst_index, burst in candidates.iterrows():
            available.at[burst_index, "matched"] = True
            matched_rows.append(
                {
                    "Vehicle Event Time": float(burst["burst_start"]),
                    "Acceleration End": float(burst["burst_end"]),
                    "Count Update Time": count_time,
                    "Count Increase": increase,
                    "Delay (seconds)": round(
                        count_time - float(burst["burst_end"]), 3
                    ),
                    "Acceleration Samples": int(burst["sample_count"]),
                    "Maximum Magnitude": burst["maximum_magnitude"],
                    "Maximum |X|": burst["maximum_abs_x"],
                    "Maximum |Y|": burst["maximum_abs_y"],
                    "Maximum |Z|": burst["maximum_abs_z"],
                    "Confirmation": "Confirmed by Count + Acceleration",
                }
            )

    return pd.DataFrame(matched_rows, columns=RESULT_COLUMNS)


def identify_vehicle_events(
    start_unix: float,
    end_unix: float,
    max_delay_seconds: float = DEFAULT_MAX_EVENT_DELAY_SECONDS,
    burst_gap_seconds: float = DEFAULT_BURST_GAP_SECONDS,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Identify high-confidence vehicle crossings in a selected time range."""
    if end_unix <= start_unix:
        raise PortalDataError("End Time must be after Start Time.")
    if max_delay_seconds <= 0:
        raise PortalDataError("Maximum Count delay must be greater than zero.")
    if burst_gap_seconds <= 0:
        raise PortalDataError("Acceleration burst gap must be greater than zero.")

    metadata = get_metadata()
    with DATABASE_LOCK:
        connection = connect_duckdb()
        try:
            configure_duckdb(connection)
            count_changes = query_count_increases(
                connection,
                metadata,
                start_unix,
                end_unix,
                max_delay_seconds,
            )
            bursts = query_acceleration_bursts(
                connection,
                metadata,
                start_unix,
                end_unix,
                max_delay_seconds,
                burst_gap_seconds,
            )
        finally:
            connection.close()

    events = match_confirmed_events(
        count_changes,
        bursts,
        max_delay_seconds,
    )
    summary = {
        "count_increases": len(count_changes),
        "acceleration_bursts": len(bursts),
        "confirmed_events": len(events),
    }
    return events, summary


def format_event_times(events: pd.DataFrame) -> pd.DataFrame:
    """Convert Unix event timestamps to readable Eastern Time values."""
    formatted = events.copy()
    for column in ("Vehicle Event Time", "Acceleration End", "Count Update Time"):
        formatted[column] = pd.to_datetime(
            formatted[column], unit="s", utc=True
        ).dt.tz_convert(TIME_ZONE)
    return formatted


# =============================================================================
# STREAMLIT WORKSPACE
# =============================================================================
def render_crash_events() -> None:
    """Display the high-confidence vehicle-event identification workspace."""
    st.title("Vehicle Events Identifier")
    st.write(
        "Identify likely vehicle crossings by requiring both an acceleration "
        "burst and an increase in the environmental Count variable."
    )

    if not database_ready():
        st.warning(
            "Bridge data has not been loaded on this server. Use the Home page "
            "to load the data before identifying vehicle events."
        )
        return

    try:
        metadata = get_metadata()
        overlap_start, overlap_end = overlapping_time_bounds(metadata)
    except PortalDataError as exc:
        st.error(str(exc))
        return

    eastern_zone = ZoneInfo(TIME_ZONE)
    start_datetime = datetime.fromtimestamp(overlap_start, eastern_zone)
    end_datetime = datetime.fromtimestamp(overlap_end, eastern_zone)

    with st.container(border=True):
        st.subheader("Identification Controls")
        selected_range = st.selectbox(
            "Time Range",
            TIME_RANGE_OPTIONS,
            index=3,
            key="vehicle_event_time_range",
        )

        start_date = start_datetime.date()
        start_time = start_datetime.time().replace(microsecond=0)
        end_date = end_datetime.date()
        end_time = end_datetime.time().replace(microsecond=0)

        if selected_range == "Custom Range":
            start_column, end_column = st.columns(2)
            with start_column:
                st.markdown("#### Start Time")
                start_date = st.date_input(
                    "Start Date",
                    value=start_datetime.date(),
                    min_value=start_datetime.date(),
                    max_value=end_datetime.date(),
                    key="vehicle_event_start_date",
                )
                start_time = st.time_input(
                    "Start Time",
                    value=start_datetime.time().replace(microsecond=0),
                    step=60,
                    key="vehicle_event_start_time",
                )
            with end_column:
                st.markdown("#### End Time")
                end_date = st.date_input(
                    "End Date",
                    value=end_datetime.date(),
                    min_value=start_datetime.date(),
                    max_value=end_datetime.date(),
                    key="vehicle_event_end_date",
                )
                end_time = st.time_input(
                    "End Time",
                    value=end_datetime.time().replace(microsecond=0),
                    step=60,
                    key="vehicle_event_end_time",
                )

        parameter_column, explanation_column = st.columns([1, 2])
        with parameter_column:
            maximum_delay = st.number_input(
                "Maximum Count Delay (seconds)",
                min_value=1,
                max_value=300,
                value=DEFAULT_MAX_EVENT_DELAY_SECONDS,
                step=1,
                key="vehicle_event_maximum_delay",
            )
        with explanation_column:
            st.info(
                "The default 45-second window measures the delay from the end "
                "of an acceleration burst to the later Count update. A burst "
                "must end before the Count update to qualify."
            )

        run_identification = st.button(
            "Identify Vehicle Events",
            type="primary",
            width="stretch",
            key="vehicle_event_run",
        )

    if run_identification:
        try:
            selected_start, selected_end = resolve_time_range(
                selected_range,
                overlap_start,
                overlap_end,
                start_date,
                start_time,
                end_date,
                end_time,
            )
            with st.spinner(
                "Comparing Count increases with acceleration bursts..."
            ):
                events, summary = identify_vehicle_events(
                    selected_start,
                    selected_end,
                    max_delay_seconds=float(maximum_delay),
                )

            st.session_state["vehicle_event_results"] = events
            st.session_state["vehicle_event_summary"] = summary
            st.session_state["vehicle_event_parameters"] = {
                "start": selected_start,
                "end": selected_end,
                "delay": int(maximum_delay),
            }
        except PortalDataError as exc:
            st.session_state.pop("vehicle_event_results", None)
            st.error(str(exc))
        except Exception as exc:
            st.session_state.pop("vehicle_event_results", None)
            st.error(f"Vehicle events could not be identified: {exc}")

    events = st.session_state.get("vehicle_event_results")
    summary = st.session_state.get("vehicle_event_summary", {})
    parameters = st.session_state.get("vehicle_event_parameters", {})

    if events is None:
        with st.container(border=True):
            st.subheader("How Confirmation Works")
            st.markdown(
                """
                - Acceleration readings are grouped into distinct bursts.
                - Positive changes in `Count` are treated as vehicle detections.
                - Decreases in `Count` are treated as counter resets and ignored.
                - A burst is confirmed only when a later Count increase occurs
                  within the selected delay window after the burst ends.
                - Ambiguous windows containing more bursts than counted vehicles
                  are excluded instead of guessed.
                """
            )
        return

    st.subheader("Identification Results")
    metric_one, metric_two, metric_three = st.columns(3)
    metric_one.metric("Count Increases", int(summary.get("count_increases", 0)))
    metric_two.metric(
        "Acceleration Bursts", int(summary.get("acceleration_bursts", 0))
    )
    metric_three.metric("Confirmed Events", int(summary.get("confirmed_events", 0)))

    if events.empty:
        st.warning(
            "No events met both confirmation requirements in this time range. "
            "Unmatched signals were intentionally excluded."
        )
        return

    display_events = format_event_times(events)
    st.success(
        f"Found {len(display_events):,} high-confidence vehicle event"
        f"{'s' if len(display_events) != 1 else ''}."
    )
    st.dataframe(
        display_events,
        width="stretch",
        hide_index=True,
        column_config={
            "Vehicle Event Time": st.column_config.DatetimeColumn(
                "Vehicle Event Time", format="YYYY-MM-DD hh:mm:ss.SSS a"
            ),
            "Acceleration End": st.column_config.DatetimeColumn(
                "Acceleration End", format="YYYY-MM-DD hh:mm:ss.SSS a"
            ),
            "Count Update Time": st.column_config.DatetimeColumn(
                "Count Update Time", format="YYYY-MM-DD hh:mm:ss.SSS a"
            ),
            "Maximum Magnitude": st.column_config.NumberColumn(format="%.5f"),
            "Maximum |X|": st.column_config.NumberColumn(format="%.5f"),
            "Maximum |Y|": st.column_config.NumberColumn(format="%.5f"),
            "Maximum |Z|": st.column_config.NumberColumn(format="%.5f"),
        },
    )

    export_events = display_events.copy()
    for column in ("Vehicle Event Time", "Acceleration End", "Count Update Time"):
        export_events[column] = export_events[column].astype(str)

    range_start_text = datetime.fromtimestamp(
        float(parameters.get("start", overlap_start)), eastern_zone
    ).strftime("%Y-%m-%d_%H-%M-%S_ET")
    range_end_text = datetime.fromtimestamp(
        float(parameters.get("end", overlap_end)), eastern_zone
    ).strftime("%Y-%m-%d_%H-%M-%S_ET")
    download_filename = (
        f"VehicleEvents-{range_start_text}-to-{range_end_text}.csv"
    )

    st.download_button(
        "Download Confirmed Events as CSV",
        data=export_events.to_csv(index=False).encode("utf-8"),
        file_name=download_filename,
        mime="text/csv",
        width="stretch",
        key="vehicle_event_download",
    )

    st.caption(
        "Results use a one-directional matching window of "
        f"{int(parameters.get('delay', DEFAULT_MAX_EVENT_DELAY_SECONDS))} seconds "
        "measured from acceleration-burst end to Count update. "
        "Dual-sensor agreement provides strong evidence of a vehicle crossing, "
        "but it should not be interpreted as absolute physical proof."
    )
