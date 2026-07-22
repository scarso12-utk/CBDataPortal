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
LAST_GRAPH_RANGE_KEY = "portal_last_graph_range"
LAST_EXPORT_RANGE_KEY = "portal_last_export_range"
SERIES_COLORS = (
    "#636EFA",
    "#EF553B",
    "#00CC96",
    "#AB63FA",
    "#FFA15A",
    "#19D3F3",
    "#FF6692",
    "#B6E880",
    "#FF97FF",
    "#FECB52",
    "#2E91E5",
    "#E15F99",
    "#1CA71C",
    "#FB0D0D",
    "#DA16FF",
    "#222A2A",
    "#B68100",
    "#750D86",
    "#EB663B",
    "#511CFB",
    "#00A08B",
    "#FB00D1",
    "#6C7C32",
    "#AF0038",
)
AXIS_TITLES = {
    "Deflection": "Deflection (mm)",
    "Temp0": "Temperature Sensor 0 (°C)",
    "Temp1": "Temperature Sensor 1 (°C)",
    "Temp2": "Temperature Sensor 2 (°C)",
    "Temp3": "Temperature Sensor 3 (°C)",
    "Temp4": "Temperature Sensor 4 (°C)",
    "Temp5": "Temperature Sensor 5 (°C)",
    "Temp6": "Temperature Sensor 6 (°C)",
    "Temp7": "Temperature Sensor 7 (°C)",
    "Temperature": "Ambient Temperature Sensor (°C)",
    "Average Temp": "Average Temperature (°C)",
    "Humidity": "Humidity (%)",
    "Count": "Vehicle Count",
}


def axis_title_for_spec(spec: dict[str, object]) -> str:
    """Return the requested unit-bearing y-axis title for one graph series."""
    variable = str(spec.get("variable", "Value"))
    series_label = str(spec.get("series_label", variable))

    if str(spec.get("dataset", "")) == "accell":
        device_number = 1 if "Device 1" in series_label else 2
        if variable == "Magnitude":
            return f"Device {device_number} Acceleration Magnitude (mm/s2)"
        return f"Device {device_number} {variable} Acceleration (mm/s2)"

    return AXIS_TITLES.get(variable, series_label)


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
saved_graph_range = st.session_state.get(LAST_GRAPH_RANGE_KEY, {})
saved_graph_start_datetime = datetime.fromtimestamp(
    float(saved_graph_range.get("start", data_start_unix)), eastern_zone
)
saved_graph_end_datetime = datetime.fromtimestamp(
    float(saved_graph_range.get("end", data_end_unix)), eastern_zone
)


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
        saved_export_range = st.session_state.get(LAST_EXPORT_RANGE_KEY, {})
        export_start = saved_export_range.get("start")
        export_end = saved_export_range.get("end")
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
            index=(
                TIME_RANGE_OPTIONS.index("Range from Export Center")
                if st.session_state.get(LAST_EXPORT_RANGE_KEY)
                else (
                    TIME_RANGE_OPTIONS.index("Custom Range")
                    if saved_graph_range
                    else 0
                )
            ),
            key="graph_time_range",
        )

        use_data_start = True
        use_data_end = True
        start_date = saved_graph_start_datetime.date()
        start_time = saved_graph_start_datetime.time().replace(microsecond=0)
        end_date = saved_graph_end_datetime.date()
        end_time = saved_graph_end_datetime.time().replace(microsecond=0)

        if selected_range == "Custom Range":
            st.markdown("#### Start Time")
            use_data_start = st.checkbox(
                "Use start of data",
                value=False,
                key="graph_use_data_start",
            )
            start_date = st.date_input(
                "Start Date",
                value=saved_graph_start_datetime.date(),
                disabled=use_data_start,
                key="graph_start_date",
            )
            start_time = st.time_input(
                "Start Time",
                value=saved_graph_start_datetime.time().replace(microsecond=0),
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
                value=saved_graph_end_datetime.date(),
                disabled=use_data_end,
                key="graph_end_date",
            )
            end_time = st.time_input(
                "End Time",
                value=saved_graph_end_datetime.time().replace(microsecond=0),
                step=60,
                disabled=use_data_end,
                key="graph_end_time",
            )

        if selected_range == "Range from Export Center":
            saved_export_range = st.session_state.get(LAST_EXPORT_RANGE_KEY, {})
            linked_start = saved_export_range.get("start")
            linked_end = saved_export_range.get("end")
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

        st.markdown("#### Minimum Point Interval")
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
            "Increase the minimum point interval for long time ranges."
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

        graphed_series = set(graph_data["Series"].astype(str).unique())
        graph_series_info = [
            {
                "series_name": str(spec["series_label"]),
                "axis_title": axis_title_for_spec(spec),
            }
            for spec in selected_specs
            if str(spec["series_label"]) in graphed_series
        ]

        st.session_state["graph_data"] = graph_data
        st.session_state["graph_series_info"] = graph_series_info
        st.session_state["graph_start_unix"] = start_unix
        st.session_state["graph_end_unix"] = end_unix
        st.session_state[LAST_GRAPH_RANGE_KEY] = {
            "start": float(start_unix),
            "end": float(end_unix),
        }
        st.session_state["graph_render_id"] = int(
            st.session_state.get("graph_render_id", 0)
        ) + 1
        st.session_state["graph_description"] = (
            f"{len(selected_specs)} series · {len(graph_data):,} plotted points"
        )
    except PortalDataError as exc:
        st.session_state.pop("graph_data", None)
        st.session_state.pop("graph_series_info", None)
        st.error(str(exc))
    except Exception as exc:
        st.session_state.pop("graph_data", None)
        st.session_state.pop("graph_series_info", None)
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

        available_series = list(graph_data["Series"].astype(str).unique())
        stored_series_info = st.session_state.get("graph_series_info", [])
        graph_series_info = [
            {
                "series_name": str(item.get("series_name", "")),
                "axis_title": str(item.get("axis_title", item.get("series_name", ""))),
            }
            for item in stored_series_info
            if isinstance(item, dict)
            and str(item.get("series_name", "")) in available_series
        ]
        configured_names = {item["series_name"] for item in graph_series_info}
        graph_series_info.extend(
            {
                "series_name": series_name,
                "axis_title": series_name,
            }
            for series_name in available_series
            if series_name not in configured_names
        )

        render_id = int(st.session_state.get("graph_render_id", 0))
        axis_checkbox_keys = {
            item["series_name"]: f"graph_axis_{render_id}_{index}"
            for index, item in enumerate(graph_series_info)
        }
        enabled_axis_info = [
            item
            for item in graph_series_info
            if bool(
                st.session_state.get(axis_checkbox_keys[item["series_name"]], False)
            )
        ]

        series_colors = {
            item["series_name"]: SERIES_COLORS[index % len(SERIES_COLORS)]
            for index, item in enumerate(graph_series_info)
        }
        series_axis_references = {
            item["series_name"]: "y" for item in graph_series_info
        }

        if enabled_axis_info:
            axis_layout: dict[str, dict[str, object]] = {
                "yaxis": {
                    "visible": False,
                    "showgrid": False,
                    "zeroline": False,
                }
            }
            for enabled_index, item in enumerate(enabled_axis_info):
                axis_number = enabled_index + 2
                axis_name = f"yaxis{axis_number}"
                axis_reference = f"y{axis_number}"
                axis_color = series_colors[item["series_name"]]
                is_left_axis = enabled_index == 0

                series_axis_references[item["series_name"]] = axis_reference
                axis_settings: dict[str, object] = {
                    "title": {
                        "text": item["axis_title"],
                        "font": {"color": axis_color},
                    },
                    "tickfont": {"color": axis_color},
                    "linecolor": axis_color,
                    "tickcolor": axis_color,
                    "showline": True,
                    "linewidth": 2,
                    "ticks": "outside",
                    "overlaying": "y",
                    "anchor": "free",
                    "side": "left" if is_left_axis else "right",
                    "position": 0.0 if is_left_axis else 1.0,
                    "showgrid": is_left_axis,
                    "gridcolor": graph_grid,
                    "zeroline": False,
                    "automargin": True,
                }
                if not is_left_axis:
                    axis_settings["autoshift"] = True
                axis_layout[axis_name] = axis_settings
        else:
            axis_layout = {
                "yaxis": {
                    "title": "Value",
                    "gridcolor": graph_grid,
                    "automargin": True,
                }
            }

        series_text = graph_data["Series"].astype(str)
        for item in graph_series_info:
            series_name = item["series_name"]
            series_data = graph_data.loc[series_text == series_name].sort_values(
                "DateTime"
            )
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
                    yaxis=series_axis_references[series_name],
                    mode="lines+markers",
                    line={"width": 2, "color": series_colors[series_name]},
                    marker={"size": 4, "color": series_colors[series_name]},
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
            plot_bgcolor=graph_background,
            paper_bgcolor=graph_background,
            dragmode="zoom",
            legend={"title": {"text": "Data"}},
            margin={
                "l": 80,
                "r": min(500, 60 + max(0, len(enabled_axis_info) - 1) * 45),
                "t": 60,
                "b": 60,
            },
            hovermode="closest",
            font={"family": graph_font},
            **axis_layout,
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

        st.markdown("#### Y-Axes")
        st.caption(
            "Select the variables that should have their own color-coded y-axis. "
            "Data lines remain visible when an axis is unchecked."
        )
        for item in graph_series_info:
            st.checkbox(
                item["axis_title"],
                value=False,
                key=axis_checkbox_keys[item["series_name"]],
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
