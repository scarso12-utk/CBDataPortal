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
    "The Composite Bridge Data Portal provides a centralized way to load, "
    "visualize, inspect, and export long-term monitoring data from the composite "
    "bridge in Morgan County, Tennessee."
)


# =============================================================================
# PROJECT OVERVIEW
# =============================================================================
st.subheader("Composite Bridge Research")
st.markdown(
    """
The bridge is monitored as part of ongoing research into the behavior and
long-term performance of composite bridge systems. Its instrumentation records
structural response, environmental conditions, and activity over time. These
measurements help researchers examine how the bridge responds to traffic,
temperature changes, humidity, vibration, and other conditions.
"""
)


# =============================================================================
# MONITORED DATA
# =============================================================================
st.subheader("Available Data")

acceleration_column, deflection_column, environmental_column = st.columns(3)

with acceleration_column:
    with st.container(border=True):
        st.markdown("### Acceleration")
        st.write(
            "Two acceleration devices provide X-, Y-, and Z-axis readings. "
            "The portal also supports the calculated acceleration magnitude."
        )

with deflection_column:
    with st.container(border=True):
        st.markdown("### Deflection")
        st.write(
            "The deflection dataset records changes in the bridge deck's "
            "position over time for structural-response analysis."
        )

with environmental_column:
    with st.container(border=True):
        st.markdown("### Environmental")
        st.write(
            "Environmental measurements include eight embedded temperature "
            "sensors, ambient temperature, average temperature, humidity, and count data."
        )


# =============================================================================
# PORTAL WORKFLOW
# =============================================================================
st.subheader("How the Portal Works")
st.markdown(
    """
1. **Home** securely retrieves the latest CSV files from the project's private
   Amazon S3 bucket and loads them into DuckDB.
2. **Graphing** filters selected variables in DuckDB and creates an interactive
   Plotly graph with zoom, hover, box selection, and selection statistics.
3. **Export Center** combines any selected variables by exact timestamp and
   produces one CSV or one Excel file for the requested time range.
4. **About** documents the project and the purpose of this application.
"""
)


# =============================================================================
# DATA HANDLING NOTES
# =============================================================================
st.subheader("Data Handling")
st.markdown(
    """
- Unix timestamps are displayed in the **America/New_York** time zone.
- DuckDB performs filtering and thinning before results enter application memory.
- Data gaps longer than ten minutes are not connected by graph lines.
- Excel exports are disabled when the filtered output exceeds Excel's worksheet row limit.
- AWS credentials and the shared portal password are stored through Streamlit Secrets,
  not inside the published Python source code.
"""
)


# =============================================================================
# RESEARCH CONTEXT
# =============================================================================
st.info(
    "This portal is intended to support the University of Tennessee composite "
    "bridge research workflow and make the monitoring data easier to use."
)
