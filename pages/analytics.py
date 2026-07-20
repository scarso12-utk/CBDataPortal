from __future__ import annotations

import streamlit as st

from analytics_tools.crash_events import render_crash_events
from analytics_tools.frequency import render_frequency_analysis
from data import database_ready

# =============================================================================
# ANALYTICS PAGE SETTINGS
# =============================================================================
ANALYTICS_VIEW_KEY = "analytics_current_view"

ANALYTICS_VIEWS = {
    "frequency": {
        "title": "FFT / Frequency Analysis",
        "icon": ":material/graphic_eq:",
        "description": (
            "Explore acceleration signals in the frequency domain and identify "
            "dominant vibration frequencies."
        ),
    },
    "crash_events": {
        "title": "Vehicle Events Identifier",
        "icon": ":material/directions_car:",
        "description": (
            "Identify high-confidence vehicle crossings by matching acceleration "
            "bursts with increases in the environmental Count variable."
        ),
    },
}


# =============================================================================
# NAVIGATION FUNCTIONS
# =============================================================================
def open_analytics_view(view_name: str) -> None:
    """Open one of the internal analytics tools."""
    st.session_state[ANALYTICS_VIEW_KEY] = view_name


def return_to_analytics() -> None:
    """Return to the main Analytics landing page."""
    st.session_state[ANALYTICS_VIEW_KEY] = "overview"


# =============================================================================
# ANALYTICS LANDING PAGE
# =============================================================================
def render_analytics_overview() -> None:
    """Display the Analytics landing page."""
    st.title("Analytics")

    st.write(
        "Choose an analytical workspace below. These specialized tools are "
        "available only through the Analytics page."
    )

    if not database_ready():
        st.warning(
            "Bridge data has not been loaded on this server. You can review the "
            "available tools, but data must be loaded from the Home page before "
            "an analysis can run."
        )

    # -------------------------------------------------------------------------
    # FFT / FREQUENCY ANALYSIS
    # -------------------------------------------------------------------------
    frequency_view = ANALYTICS_VIEWS["frequency"]

    with st.container(border=True):
        st.subheader(frequency_view["title"])
        st.write(frequency_view["description"])

        if st.button(
            "Open FFT / Frequency Analysis",
            icon=frequency_view["icon"],
            width="stretch",
            key="analytics_open_frequency",
        ):
            open_analytics_view("frequency")
            st.rerun()

    # -------------------------------------------------------------------------
    # CRASH EVENTS IDENTIFIER
    # -------------------------------------------------------------------------
    crash_view = ANALYTICS_VIEWS["crash_events"]

    with st.container(border=True):
        st.subheader(crash_view["title"])
        st.write(crash_view["description"])

        if st.button(
            "Open Vehicle Events Identifier",
            icon=crash_view["icon"],
            width="stretch",
            key="analytics_open_crash_events",
        ):
            open_analytics_view("crash_events")
            st.rerun()


# =============================================================================
# INDIVIDUAL ANALYTICS VIEWS
# =============================================================================
def render_selected_analytics_view(view_name: str) -> None:
    """Display the selected analytics tool."""

    if st.button(
        "Back to Analytics",
        icon=":material/arrow_back:",
        key=f"analytics_back_{view_name}",
    ):
        return_to_analytics()
        st.rerun()

    if view_name == "frequency":
        render_frequency_analysis()

    elif view_name == "crash_events":
        render_crash_events()

    else:
        return_to_analytics()
        st.rerun()


# =============================================================================
# PAGE ROUTING
# Only analytics.py is registered in app.py. The two analytical tools therefore
# do not appear as separate pages in the sidebar.
# =============================================================================
current_view = st.session_state.get(ANALYTICS_VIEW_KEY, "overview")

if current_view in ANALYTICS_VIEWS:
    render_selected_analytics_view(current_view)
else:
    render_analytics_overview()
