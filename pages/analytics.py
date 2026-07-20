from __future__ import annotations

import streamlit as st

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
    "anomaly": {
        "title": "Anomaly Detection",
        "icon": ":material/troubleshoot:",
        "description": (
            "Find readings and time periods that differ substantially from the "
            "bridge's typical behavior."
        ),
    },
    "impact": {
        "title": "Impact Event Identification",
        "icon": ":material/warning:",
        "description": (
            "Screen acceleration and deflection data for candidate impact events "
            "that warrant closer review."
        ),
    },
}


# =============================================================================
# NAVIGATION FUNCTIONS
# =============================================================================
def open_view(view_name: str) -> None:
    """Open one of the internal analytics views."""
    st.session_state[ANALYTICS_VIEW_KEY] = view_name


def return_to_analytics() -> None:
    """Return to the main Analytics page."""
    st.session_state[ANALYTICS_VIEW_KEY] = "overview"


# =============================================================================
# INDIVIDUAL ANALYTICS VIEWS
# =============================================================================
def render_placeholder(view_name: str) -> None:
    """Display a placeholder until the selected analysis is implemented."""
    view = ANALYTICS_VIEWS[view_name]

    if st.button(
        "Back to Analytics",
        icon=":material/arrow_back:",
        key=f"analytics_back_{view_name}",
    ):
        return_to_analytics()
        st.rerun()

    st.title(view["title"])
    st.write(view["description"])

    if not database_ready():
        st.warning(
            "Bridge data has not been loaded on this server. Use the Home page "
            "to load the data before running an analysis."
        )

    st.info(
        "This analysis workspace has been added to the portal, but its analytical "
        "controls and calculations have not been implemented yet."
    )


# =============================================================================
# ANALYTICS LANDING PAGE
# =============================================================================
def render_overview() -> None:
    """Display the Analytics landing page and its three available tools."""
    st.title("Analytics")

    st.write(
        "Choose an analytical workspace below. These specialized tools are "
        "available only through this Analytics page."
    )

    if not database_ready():
        st.warning(
            "Bridge data has not been loaded on this server. You can review the "
            "available tools, but data must be loaded from the Home page before "
            "an analysis can run."
        )

    for view_name, view in ANALYTICS_VIEWS.items():
        with st.container(border=True):
            st.subheader(view["title"])
            st.write(view["description"])

            if st.button(
                f"Open {view['title']}",
                icon=view["icon"],
                width="stretch",
                key=f"analytics_open_{view_name}",
            ):
                open_view(view_name)
                st.rerun()


# =============================================================================
# PAGE ROUTING
# Only analytics.py is registered in app.py. These internal views therefore do
# not appear as separate pages in the sidebar.
# =============================================================================
current_view = st.session_state.get(ANALYTICS_VIEW_KEY, "overview")

if current_view in ANALYTICS_VIEWS:
    render_placeholder(current_view)
else:
    render_overview()
