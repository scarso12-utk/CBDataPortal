from __future__ import annotations

import streamlit as st

from data import database_ready


def render_frequency_analysis() -> None:
    """Display the FFT and Frequency Analysis workspace."""

    # =========================================================================
    # PAGE HEADER
    # =========================================================================
    st.title("FFT / Frequency Analysis")

    st.write(
        "Analyze the Composite Bridge acceleration data in the frequency domain "
        "to better understand the bridge's vibration behavior."
    )

    # =========================================================================
    # DATA STATUS
    # =========================================================================
    if not database_ready():
        st.warning(
            "Bridge data has not been loaded on this server. Use the Home page "
            "to load the data before performing a frequency analysis."
        )

    # =========================================================================
    # PAGE DESCRIPTION
    # =========================================================================
    with st.container(border=True):
        st.subheader("About Frequency Analysis")

        st.write(
            "This tool will use Fast Fourier Transform (FFT) methods to convert "
            "acceleration measurements from the time domain into the frequency "
            "domain. This will help identify the frequencies at which the bridge "
            "experiences the strongest vibrations."
        )

    with st.container(border=True):
        st.subheader("Planned Features")

        st.markdown(
            """
            - Select an acceleration axis or acceleration magnitude.
            - Choose a specific date and time range.
            - Generate an FFT or frequency-spectrum graph.
            - Identify dominant vibration frequencies.
            - Compare frequency behavior across different time periods.
            - Export frequency-analysis results.
            """
        )

    # =========================================================================
    # DEVELOPMENT STATUS
    # =========================================================================
    st.info(
        "The FFT and Frequency Analysis workspace has been created. "
        "The data-selection controls and statistical analysis features will be "
        "added in a future update."
    )
