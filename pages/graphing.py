from __future__ import annotations

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# =============================================================================
# LOCAL APPLICATION IMPORTS
# =============================================================================
from data import (
    MAX_GRAPH_POINTS,
    TIME_ZONE,
    PortalDataError,
    build_series_specs,
    database_ready,
    get_logo_path,
    get_metadata,
    get_variable_groups,
    overall_time_bounds,
    query_graph_data,
)


# =============================================================================
# GRAPHING SETTINGS
# =============================================================================
PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]
GAP_BREAK_SECONDS = 10 * 60
GRAPH_HEIGHT = 650
TIME_RANGE_OPTIONS = [
    "Entire Dataset",
    "Last Week",
    "Last Day",
    "Last Hour",
    "Last 10 Minutes",
    "Range from Export Center",
    "Custom Range",
]


# =============================================================================
# PAGE HEADER
# =============================================================================
logo_path = get_logo_path(PROJECT_DIRECTORY / "logo.png")
if logo_path is not None and logo_path.exists():
    left, center, right = st.columns([1, 3, 1])
    with center:
        st.image(
            str(logo_path),
            width=int(st.session_state.get("_portal_theme", {}).get("logo_width", 700)),
        )

st.title("Graphing")
st.write(
    "Select bridge variables and a time range, then generate an interactive "
    "Plotly graph. Use zoom, pan, hover, box select, or lasso select to explore it."
)


# =============================================================================
# DATA AVAILABILITY CHECK
# =============================================================================
if not database_ready():
    st.warning("Press Load Data on the Home page before creating a graph.")
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
    """Convert Graphing page time controls into Unix timestamps."""
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
    if selected_range == "Range from Export Center":
        export_start = st.session_state.get("export_start_unix")
        export_end = st.session_state.get("export_end_unix")
        if export_start is None or export_end is None:
            raise PortalDataError(
                "No Export Center range is available yet. Open the Export Center "
                "and calculate an export size first."
            )
        return float(export_start), float(export_end)

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
# VARIABLE AND TIME CONTROLS
# =============================================================================
control_column, graph_column = st.columns([1, 3], gap="large")

with control_column:
    with st.container(border=True):
        st.subheader("Graph Controls")
        selected_range = st.selectbox(
            "Time Range",
            TIME_RANGE_OPTIONS,
            index=0,
            key="graph_time_range",
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
                value=False,
                key="graph_use_data_start",
            )
            start_date = st.date_input(
                "Start Date",
                value=data_start_datetime.date(),
                disabled=use_data_start,
                key="graph_start_date",
            )
            start_time = st.time_input(
                "Start Time",
                value=data_start_datetime.time().replace(microsecond=0),
                step=60,
                disabled=use_data_start,
                key="graph_start_time",
            )

            st.markdown("#### End Time")
            use_data_end = st.checkbox(
                "Use end of data",
                value=False,
                key="graph_use_data_end",
            )
            end_date = st.date_input(
                "End Date",
                value=data_end_datetime.date(),
                disabled=use_data_end,
                key="graph_end_date",
            )
            end_time = st.time_input(
                "End Time",
                value=data_end_datetime.time().replace(microsecond=0),
                step=60,
                disabled=use_data_end,
                key="graph_end_time",
            )

        if selected_range == "Range from Export Center":
            linked_start = st.session_state.get("export_start_unix")
            linked_end = st.session_state.get("export_end_unix")
            if linked_start is None or linked_end is None:
                st.warning(
                    "Calculate an export size in the Export Center before using "
                    "its time range here."
                )
            else:
                linked_start_text = datetime.fromtimestamp(
                    float(linked_start), eastern_zone
                ).strftime("%Y-%m-%d %I:%M:%S %p %Z")
                linked_end_text = datetime.fromtimestamp(
                    float(linked_end), eastern_zone
                ).strftime("%Y-%m-%d %I:%M:%S %p %Z")
                st.info(
                    f"Using Export Center range: {linked_start_text} through "
                    f"{linked_end_text}."
                )

        st.markdown("#### Minimum Point Frequency")
        frequency_left, frequency_right = st.columns(2)
        with frequency_left:
            frequency_minutes = st.number_input(
                "Minutes",
                min_value=0,
                value=0,
                step=1,
                key="graph_frequency_minutes",
            )
        with frequency_right:
            frequency_seconds = st.number_input(
                "Seconds",
                min_value=0,
                value=0,
                step=1,
                key="graph_frequency_seconds",
            )

        st.markdown("#### Variables")
        selections: dict[str, list[str]] = {}
        for group in get_variable_groups(metadata):
            selections[group["key"]] = st.multiselect(
                group["label"],
                options=group["variables"],
                default=[],
                key=f"graph_variables_{group['key']}",
            )

        generate_graph = st.button(
            "Generate Graph",
            type="primary",
            width="stretch",
            key="graph_generate_button",
        )

        st.caption(
            f"Graphs are limited to {MAX_GRAPH_POINTS:,} points for browser stability. "
            "Increase the minimum frequency for long time ranges."
        )


# =============================================================================
# GRAPH QUERY
# =============================================================================
if generate_graph:
    try:
        selected_specs = build_series_specs(metadata, selections)
        if not selected_specs:
            raise PortalDataError("Select at least one variable to graph.")

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

        with st.spinner("Querying DuckDB and preparing the graph..."):
            graph_data = query_graph_data(
                selected_specs,
                start_unix,
                end_unix,
                minimum_frequency,
            )

        if graph_data.empty:
            raise PortalDataError(
                "The selected variables contain no usable data in this time range."
            )

        st.session_state["graph_data"] = graph_data
        st.session_state["graph_start_unix"] = start_unix
        st.session_state["graph_end_unix"] = end_unix
        st.session_state["graph_render_id"] = int(
            st.session_state.get("graph_render_id", 0)
        ) + 1
        st.session_state["graph_description"] = (
            f"{len(selected_specs)} series · {len(graph_data):,} plotted points"
        )
    except PortalDataError as exc:
        st.session_state.pop("graph_data", None)
        st.error(str(exc))
    except Exception as exc:
        st.session_state.pop("graph_data", None)
        st.error(f"The graph could not be generated: {exc}")


# =============================================================================
# PLOTLY GRAPH CREATION
# =============================================================================
with graph_column:
    graph_data = st.session_state.get("graph_data")

    if graph_data is None or graph_data.empty:
        st.info("Choose variables and press Generate Graph.")
    else:
        theme_settings = st.session_state.get("_portal_theme", {})
        graph_background = theme_settings.get("graph_background", "#FFFFFF")
        graph_grid = theme_settings.get("graph_grid", "#A9A9A9")
        graph_font = theme_settings.get("font_family", "Arial, sans-serif")

        st.caption(st.session_state.get("graph_description", ""))
        figure = go.Figure()

        for series_name, series_data in graph_data.groupby("Series", sort=False):
            series_data = series_data.sort_values("DateTime")
            x_values: list[object] = []
            y_values: list[object] = []
            custom_values: list[list[str] | None] = []
            previous_time = None

            # Insert None values so Plotly does not draw across gaps over 10 minutes.
            for row in series_data.itertuples(index=False):
                current_time = row.DateTime
                if (
                    previous_time is not None
                    and (current_time - previous_time).total_seconds() > GAP_BREAK_SECONDS
                ):
                    x_values.append(None)
                    y_values.append(None)
                    custom_values.append(None)

                x_values.append(current_time)
                y_values.append(float(row.Value))
                custom_values.append([str(series_name)])
                previous_time = current_time

            figure.add_trace(
                go.Scattergl(
                    x=x_values,
                    y=y_values,
                    customdata=custom_values,
                    name=str(series_name),
                    mode="lines+markers",
                    line={"width": 2},
                    marker={"size": 4},
                    connectgaps=False,
                    hovertemplate=(
                        "Time: %{x}<br>"
                        "Value: %{y}<br>"
                        "Series: %{customdata[0]}"
                        "<extra></extra>"
                    ),
                )
            )

        figure.update_layout(
            title="Selected Bridge Data",
            height=GRAPH_HEIGHT,
            xaxis={"title": "Time", "gridcolor": graph_grid},
            yaxis={"title": "Value", "gridcolor": graph_grid},
            plot_bgcolor=graph_background,
            paper_bgcolor=graph_background,
            dragmode="zoom",
            legend={"title": {"text": "Data"}},
            margin={"l": 60, "r": 30, "t": 60, "b": 60},
            hovermode="closest",
            font={"family": graph_font},
        )

        graph_event = st.plotly_chart(
            figure,
            width="stretch",
            theme=None,
            key=f"bridge_graph_{st.session_state.get('graph_render_id', 0)}",
            on_select="rerun",
            selection_mode=("points", "box", "lasso"),
            config={
                "displaylogo": False,
                "scrollZoom": True,
                "responsive": True,
            },
        )

        # =====================================================================
        # BOX AND LASSO SELECTION STATISTICS
        # This section stays hidden until the user selects graph points.
        # =====================================================================
        try:
            selected_points = list(graph_event.selection.points)
        except (AttributeError, TypeError):
            selected_points = list(
                (graph_event or {}).get("selection", {}).get("points", [])
            )

        if selected_points:
            selected_values = pd.to_numeric(
                pd.Series([point.get("y") for point in selected_points]),
                errors="coerce",
            ).dropna()
            selected_times = pd.to_datetime(
                pd.Series([point.get("x") for point in selected_points]),
                errors="coerce",
            ).dropna()

            if not selected_values.empty and not selected_times.empty:
                st.subheader("Box Select Stats")
                count_column, average_column, maximum_column = st.columns(3)
                count_column.metric("Selected Points", f"{len(selected_values):,}")
                average_column.metric("Average", f"{selected_values.mean():.4f}")
                maximum_column.metric("Maximum", f"{selected_values.max():.4f}")
                st.write(
                    "**Time span:** "
                    f"{selected_times.min()} to {selected_times.max()}"
                )
