from __future__ import annotations

import streamlit as st

from data import database_ready


def render_crash_events() -> None:
    """Display the Crash Events Identifier workspace."""

    # =========================================================================
    # PAGE HEADER
    # =========================================================================
    st.title("Crash Events Identifier")

    st.write(
        "Examine Composite Bridge sensor data for unusual activity that could "
        "indicate a vehicle collision or other significant impact event."
    )

    # =========================================================================
    # DATA STATUS
    # =========================================================================
    if not database_ready():
        st.warning(
            "Bridge data has not been loaded on this server. Use the Home page "
            "to load the data before searching for potential crash events."
        )

    # =========================================================================
    # PAGE DESCRIPTION
    # =========================================================================
    with st.container(border=True):
        st.subheader("About Crash Event Identification")

        st.write(
            "This tool will examine acceleration and deflection measurements for "
            "sudden, unusually large changes that may indicate a vehicle collision "
            "or another significant impact. Events identified by this tool will be "
            "treated as possible crash events that require additional review."
        )

    with st.container(border=True):
        st.subheader("Planned Features")

        st.markdown(
            """
            - Select a date and time range to analyze.
            - Screen acceleration data for sudden impact signatures.
            - Compare acceleration and deflection behavior around each event.
            - Rank possible events by severity.
            - Display the date and time of each identified event.
            - Graph sensor readings before, during, and after an event.
            - Export a list of possible crash events for further review.
            """
        )

    # =========================================================================
    # IMPORTANT INTERPRETATION NOTE
    # =========================================================================
    st.warning(
        "An identified event will not automatically confirm that a vehicle crash "
        "occurred. Large sensor responses may also be caused by heavy vehicles, "
        "construction activity, sensor problems, or other unusual bridge loading."
    )

    # =========================================================================
    # DEVELOPMENT STATUS
    # =========================================================================
    st.info(
        "The Crash Events Identifier workspace has been created. "
        "The event-detection controls and analytical calculations will be added "
        "in a future update."
    )
