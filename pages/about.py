from __future__ import annotations

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import streamlit as st


# =============================================================================
# PAGE HEADER
# =============================================================================
st.title("About")

st.write(
    "The Composite Bridge Data Portal provides a centralized, password-protected "
    "application for loading, visualizing, analyzing, and exporting long-term "
    "monitoring data from the composite bridge in Morgan County, Tennessee."
)


# =============================================================================
# PROJECT OVERVIEW
# =============================================================================
st.subheader("Composite Bridge Research")

st.markdown(
    """
The bridge is monitored as part of ongoing research into the structural behavior
and long-term performance of composite bridge systems. Sensors installed on the
bridge record its response to traffic, vibration, temperature changes, humidity,
and other environmental and loading conditions.

The monitoring system has collected several years of time-stamped measurements.
This portal makes those large datasets easier to access and use for research.
"""
)


# =============================================================================
# BRIDGE INSTRUMENTATION
# =============================================================================
st.subheader("Bridge Instrumentation")

st.markdown(
    """
The bridge monitoring system includes:

- Two three-axis accelerometers for measuring forces and vibrations.
- Two three-axis magnetometers used for vehicle-counting measurements.
- Eight embedded digital temperature sensors.
- One ambient humidity sensor.
- One thermally isolated ambient temperature sensor.
- One non-contact absolute deflection sensor for measuring bridge-deck movement.
"""
)


# =============================================================================
# AVAILABLE DATA
# =============================================================================
st.subheader("Available Data")

acceleration_column, deflection_column, environmental_column = st.columns(3)

with acceleration_column:
    with st.container(border=True):
        st.markdown("### Acceleration")

        st.write(
            "Acceleration data includes device identification, X-, Y-, and Z-axis "
            "measurements, and calculated acceleration magnitude."
        )

with deflection_column:
    with st.container(border=True):
        st.markdown("### Deflection")

        st.write(
            "Deflection data records small changes in the bridge deck's position "
            "over time for structural-response analysis."
        )

with environmental_column:
    with st.container(border=True):
        st.markdown("### Environmental")

        st.write(
            "Environmental data includes eight embedded temperature readings, "
            "ambient temperature, average temperature, humidity, and count data."
        )


# =============================================================================
# PORTAL FEATURES
# =============================================================================
st.subheader("Portal Features")

st.markdown(
    """
1. **Home** securely retrieves the latest CSV files from the project's private
   Amazon S3 bucket and loads them into a local DuckDB database.

2. **Graphing** filters selected variables and creates an interactive Plotly
   graph with zooming, panning, hovering, box selection, and selection statistics.

3. **Export Center** filters selected variables and creates a CSV or Excel file
   for the requested date and time range.

4. **Analytics** provides access to specialized analytical workspaces for FFT
   and frequency analysis and possible crash-event identification.

5. **About** documents the bridge research, available data, portal features,
   and data-handling process.
"""
)


# =============================================================================
# ANALYTICS
# =============================================================================
st.subheader("Analytics Workspaces")

frequency_column, crash_column = st.columns(2)

with frequency_column:
    with st.container(border=True):
        st.markdown("### FFT / Frequency Analysis")

        st.write(
            "This workspace is intended to analyze acceleration measurements in "
            "the frequency domain and help identify dominant bridge-vibration "
            "frequencies."
        )

with crash_column:
    with st.container(border=True):
        st.markdown("### Crash Events Identifier")

        st.write(
            "This workspace is intended to screen acceleration and deflection "
            "data for unusual activity that could indicate a collision or other "
            "significant impact event."
        )

st.caption(
    "The analytical calculations and data-selection controls for these "
    "workspaces are planned for a future update."
)


# =============================================================================
# DATA HANDLING
# =============================================================================
st.subheader("Data Handling")

st.markdown(
    """
- Source CSV files are stored in a private Amazon S3 bucket.
- DuckDB is used to query the large datasets efficiently.
- Filtering and frequency thinning occur before results enter application memory.
- Unix timestamps are displayed in the **America/New_York** time zone.
- Graph lines are broken when consecutive readings are separated by more than
  ten minutes.
- Excel exports are disabled when the filtered output exceeds Excel's worksheet
  row limit.
- Temporary exports are removed automatically after their retention period.
- AWS credentials and the shared portal password are stored through Streamlit
  Secrets rather than in the published Python source code.
"""
)


# =============================================================================
# ANALYTICS INTERPRETATION
# =============================================================================
st.warning(
    "Events identified by future analytical tools should be treated as possible "
    "events requiring additional review. A large sensor response does not by "
    "itself confirm that a vehicle crash occurred."
)


# =============================================================================
# RESEARCH CONTEXT
# =============================================================================
st.info(
    "This portal supports the University of Tennessee composite bridge research "
    "workflow and is intended to make the bridge-monitoring data easier to "
    "access, visualize, analyze, and export."
)
