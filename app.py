from __future__ import annotations

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import hmac
from pathlib import Path

# =============================================================================
# THIRD-PARTY IMPORTS
# =============================================================================
import streamlit as st

# =============================================================================
# LOCAL APPLICATION IMPORTS
# =============================================================================
from data import database_ready, get_database_summary


# =============================================================================
# APPEARANCE SETTINGS
# Change the values in this section to update the entire portal.
# =============================================================================
PORTAL_TITLE = "Composite Bridge Data Portal"
PAGE_ICON = "🌉"
FONT_FAMILY = "Arial, sans-serif"
TITLE_COLOR = "#000000"
TEXT_COLOR = "#000000"
BACKGROUND_COLOR = "#B0C4DE"
SIDEBAR_COLOR = "#FFFDD0"
BUTTON_COLOR = "#87CEEB"
BUTTON_HOVER_COLOR = "#FFFAFA"
BUTTON_TEXT_COLOR = "#000000"
DROPDOWN_BACKGROUND_COLOR = "#FFFFFF"
DROPDOWN_TEXT_COLOR = "#000000"
DROPDOWN_OPTION_HOVER_COLOR = "#FFFDD0"
GRAPH_BACKGROUND_COLOR = "#FFFFFF"
GRAPH_GRID_COLOR = "#A9A9A9"
ERROR_COLOR = "#B00020"
SUCCESS_COLOR = "#176B2C"
CARD_BORDER_COLOR = "rgba(0, 0, 0, 0.22)"
TITLE_SIZE = "32px"
LOGO_WIDTH = 700


# =============================================================================
# APPLICATION PATHS
# =============================================================================
APP_DIRECTORY = Path(__file__).resolve().parent


# =============================================================================
# STREAMLIT PAGE CONFIGURATION
# This must be the first Streamlit command executed by the application.
# =============================================================================
st.set_page_config(
    page_title=PORTAL_TITLE,
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# SHARED PORTAL STYLING
# These styles are injected once and apply to every registered page.
# =============================================================================
st.markdown(
    f"""
    <style>
        :root {{
            --portal-background: {BACKGROUND_COLOR};
            --portal-sidebar: {SIDEBAR_COLOR};
            --portal-button: {BUTTON_COLOR};
            --portal-button-hover: {BUTTON_HOVER_COLOR};
            --portal-button-text: {BUTTON_TEXT_COLOR};
            --portal-dropdown-background: {DROPDOWN_BACKGROUND_COLOR};
            --portal-dropdown-text: {DROPDOWN_TEXT_COLOR};
            --portal-dropdown-hover: {DROPDOWN_OPTION_HOVER_COLOR};
            --portal-text: {TEXT_COLOR};
            --portal-title: {TITLE_COLOR};
            --portal-error: {ERROR_COLOR};
            --portal-success: {SUCCESS_COLOR};
            --portal-card-border: {CARD_BORDER_COLOR};
            --portal-font: {FONT_FAMILY};
        }}

        html, body, [class*="css"], [data-testid="stAppViewContainer"] {{
            font-family: var(--portal-font);
            color: var(--portal-text);
        }}

        [data-testid="stAppViewContainer"] {{
            background-color: var(--portal-background);
        }}

        [data-testid="stHeader"] {{
            background-color: transparent;
        }}

        [data-testid="stSidebar"] > div:first-child {{
            background-color: var(--portal-sidebar);
        }}

        h1, h2, h3, h4, h5, h6 {{
            color: var(--portal-title);
            font-family: var(--portal-font);
        }}

        h1 {{
            font-size: {TITLE_SIZE};
        }}

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] > button {{
            background-color: var(--portal-button);
            border: 1px solid rgba(0, 0, 0, 0.35);
            color: var(--portal-button-text);
            font-family: var(--portal-font);
            font-weight: 600;
        }}

        .stButton > button:hover:not(:disabled),
        .stDownloadButton > button:hover:not(:disabled),
        [data-testid="stFormSubmitButton"] > button:hover:not(:disabled) {{
            background-color: var(--portal-button-hover);
            border-color: rgba(0, 0, 0, 0.55);
            color: var(--portal-button-text);
        }}

        /* Select boxes and multiselects. */
        [data-testid="stSelectbox"] [data-baseweb="select"],
        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stSelectbox"] [role="combobox"],
        [data-testid="stMultiSelect"] [data-baseweb="select"],
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div {{
            background-color: var(--portal-dropdown-background) !important;
            color: var(--portal-dropdown-text) !important;
        }}

        [data-testid="stSelectbox"] span,
        [data-testid="stSelectbox"] input,
        [data-testid="stMultiSelect"] span,
        [data-testid="stMultiSelect"] input {{
            color: var(--portal-dropdown-text) !important;
        }}

        /* Frequency fields, including their minus and plus controls. */
        [data-testid="stNumberInput"] [data-baseweb="input"],
        [data-testid="stNumberInput"] [data-baseweb="input"] > div,
        [data-testid="stNumberInput"] input,
        [data-testid="stNumberInput"] button {{
            background-color: var(--portal-dropdown-background) !important;
            color: var(--portal-dropdown-text) !important;
        }}

        [data-baseweb="popover"] [role="listbox"] {{
            background-color: var(--portal-dropdown-background) !important;
        }}

        [data-baseweb="popover"] [role="option"] {{
            background-color: var(--portal-dropdown-background) !important;
            color: var(--portal-dropdown-text) !important;
        }}

        [data-baseweb="popover"] [role="option"]:hover,
        [data-baseweb="popover"] [role="option"][aria-selected="true"] {{
            background-color: var(--portal-dropdown-hover) !important;
            color: var(--portal-dropdown-text) !important;
        }}

        [data-testid="stMetric"],
        [data-testid="stVerticalBlockBorderWrapper"] {{
            background-color: rgba(255, 255, 255, 0.34);
            border-radius: 7px;
        }}

        .portal-card {{
            background-color: rgba(255, 255, 255, 0.34);
            border: 1px solid var(--portal-card-border);
            border-radius: 7px;
            padding: 1rem 1.1rem;
            margin-bottom: 1rem;
        }}

        .portal-success {{
            color: var(--portal-success);
            font-weight: 700;
        }}

        .portal-error {{
            color: var(--portal-error);
            font-weight: 700;
        }}

        /* The disabled Excel option becomes red when the row limit is exceeded. */
        .st-key-excel_format_disabled button {{
            background-color: #D9534F !important;
            border-color: #A52A2A !important;
            color: #FFFFFF !important;
            opacity: 1 !important;
        }}

        .excel-limit-message {{
            color: #B00020;
            font-weight: 700;
            margin-top: 0.25rem;
        }}

        .logo-wrap {{
            text-align: center;
            margin: 0 auto 1rem auto;
        }}

        .small-note {{
            font-size: 0.9rem;
            opacity: 0.88;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Make graph-specific theme values available to page scripts while keeping all
# user-editable appearance controls together near the top of this file.
st.session_state["_portal_theme"] = {
    "graph_background": GRAPH_BACKGROUND_COLOR,
    "graph_grid": GRAPH_GRID_COLOR,
    "font_family": FONT_FAMILY,
    "logo_width": LOGO_WIDTH,
}


# =============================================================================
# PASSWORD CONFIGURATION
# The password is read from Streamlit Secrets and is never stored in this file.
# =============================================================================
def get_portal_password() -> str | None:
    """Return the shared portal password from Streamlit Secrets."""
    try:
        portal_secrets = st.secrets.get("portal", {})
        password = portal_secrets.get("password")
    except (FileNotFoundError, KeyError):
        password = None

    return str(password) if password else None


def hide_sidebar_before_login() -> None:
    """Hide the empty sidebar and its expand control on the login screen."""
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"],
            [data-testid="stSidebarCollapsedControl"] {
                display: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_login_screen() -> None:
    """Display the shared-password gate."""
    hide_sidebar_before_login()

    st.markdown(
        f"<h1 style='text-align:center'>{PORTAL_TITLE}</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center'>Enter the shared portal password to continue.</p>",
        unsafe_allow_html=True,
    )

    configured_password = get_portal_password()
    if configured_password is None:
        st.error(
            "The portal password has not been configured. Add [portal].password "
            "to Streamlit Secrets before using the application."
        )
        return

    with st.form("portal_login_form", clear_on_submit=False):
        entered_password = st.text_input(
            "Password",
            type="password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button("Enter Portal", width="stretch")

    if submitted:
        if hmac.compare_digest(entered_password, configured_password):
            st.session_state["portal_authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")


# =============================================================================
# AUTHENTICATION STATE
# =============================================================================
if "portal_authenticated" not in st.session_state:
    st.session_state["portal_authenticated"] = False


# =============================================================================
# PAGE DEFINITIONS
# Protected pages are registered only after the password has been accepted.
# =============================================================================
login_page = st.Page(
    render_login_screen,
    title="Log In",
    icon=":material/login:",
    default=True,
)

home_page = st.Page(
    "pages/home.py",
    title="Home",
    icon=":material/home:",
    default=True,
)

graphing_page = st.Page(
    "pages/graphing.py",
    title="Graphing",
    icon=":material/show_chart:",
)

export_page = st.Page(
    "pages/export_center.py",
    title="Export Center",
    icon=":material/download:",
)

about_page = st.Page(
    "pages/about.py",
    title="About",
    icon=":material/info:",
)


# =============================================================================
# AUTHENTICATED NAVIGATION
# st.navigation is called on every run. Before login, only the hidden login
# page is registered, so the protected pages cannot be opened from the sidebar
# or by entering their URLs directly.
# =============================================================================
if not st.session_state["portal_authenticated"]:
    navigation = st.navigation(
        [login_page],
        position="hidden",
    )
    navigation.run()
    st.stop()


navigation = st.navigation(
    [
        home_page,
        graphing_page,
        export_page,
        about_page,
    ],
    position="sidebar",
    expanded=True,
)


# =============================================================================
# SHARED SIDEBAR STATUS AND LOGOUT CONTROLS
# These controls are created only after authentication succeeds.
# =============================================================================
st.sidebar.divider()

if database_ready():
    summary = get_database_summary()
    st.sidebar.markdown(
        "<span class='portal-success'>● Data loaded</span>",
        unsafe_allow_html=True,
    )
    if summary.get("loaded_at"):
        st.sidebar.caption(f"Last loaded: {summary['loaded_at']}")
else:
    st.sidebar.markdown(
        "<span class='portal-error'>● Data not loaded</span>",
        unsafe_allow_html=True,
    )

if st.sidebar.button("Log Out", width="stretch"):
    st.session_state.clear()
    st.rerun()


# =============================================================================
# RUN THE SELECTED PROTECTED PAGE
# =============================================================================
navigation.run()
