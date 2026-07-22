from __future__ import annotations

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import streamlit as st


# =============================================================================
# PAGE HEADER
# =============================================================================
st.title("Composite Bridge Data AI")

st.write(
    "This page will provide a natural-language interface for asking complex "
    "questions about the Composite Bridge monitoring data."
)

st.info(
    "Composite Bridge Data AI is not active yet. An OpenAI API account and API "
    "key must be configured before questions can be submitted."
)


# =============================================================================
# PLANNED WORKFLOW
# =============================================================================
st.subheader("Planned Workflow")

st.markdown(
    """
1. Enter a question about the acceleration, deflection, environmental, or
   vehicle-count data.
2. The AI interprets the question and selects the appropriate controlled
   analysis.
3. DuckDB performs the exact calculations on the bridge data.
4. The AI explains the results in clear language.
"""
)


# =============================================================================
# EXAMPLE QUESTION
# =============================================================================
st.subheader("Example Question")

st.code(
    "When there is an acceleration event and the Count increases within one "
    "minute, what is the average time between the start of the acceleration "
    "event and the Count increase, in seconds?",
    language=None,
)

st.caption(
    "When this feature is activated, the OpenAI API key will be stored securely "
    "in Streamlit Secrets and will not be included in the repository."
)
