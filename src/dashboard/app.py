"""Main Streamlit dashboard application for Springboard."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st

from src.database.connection import get_db, init_db
from src.utils.config import Config

# Page configuration
st.set_page_config(
    page_title="Springboard - Job Automation",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #6c757d;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 12px;
        color: white;
        text-align: center;
    }
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
    }
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.85;
    }
    .status-running { color: #28a745; }
    .status-paused { color: #ffc107; }
    .status-stopped { color: #dc3545; }
    .status-idle { color: #6c757d; }
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
    }
    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }
    div[data-testid="stSidebar"] .stMarkdown {
        color: #e0e0e0;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state() -> None:
    """Initialize Streamlit session state variables."""
    if "db_initialized" not in st.session_state:
        try:
            init_db()
            st.session_state.db_initialized = True
        except Exception as e:
            st.error(f"Database initialization failed: {e}")
            st.session_state.db_initialized = False

    if "config" not in st.session_state:
        st.session_state.config = Config()

    if "workflow_running" not in st.session_state:
        st.session_state.workflow_running = False

    if "workflow_status" not in st.session_state:
        st.session_state.workflow_status = "idle"


def render_sidebar() -> None:
    """Render the sidebar with navigation and quick stats."""
    with st.sidebar:
        st.markdown("# 🚀 Springboard")
        st.markdown("*LinkedIn Job Automation*")
        st.markdown("---")

        # Quick stats
        try:
            with get_db() as session:
                from src.database.repositories.job_repository import JobRepository
                from src.database.repositories.application_repository import ApplicationRepository

                job_repo = JobRepository(session)
                app_repo = ApplicationRepository(session)

                st.markdown("### Quick Stats")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Jobs", job_repo.count_all())
                with col2:
                    st.metric("Applied", app_repo.count_all())

                col3, col4 = st.columns(2)
                with col3:
                    st.metric("Today", app_repo.count_today())
                with col4:
                    st.metric("Rate", f"{app_repo.get_response_rate()}%")
        except Exception:
            st.markdown("*Stats loading...*")

        st.markdown("---")

        # Workflow status
        status = st.session_state.get("workflow_status", "idle")
        status_icons = {
            "running": "🟢",
            "paused": "🟡",
            "stopped": "🔴",
            "idle": "⚪",
            "completed": "✅",
        }
        st.markdown(f"**Status:** {status_icons.get(status, '⚪')} {status.title()}")


def main() -> None:
    """Main dashboard entry point."""
    init_session_state()
    render_sidebar()

    st.markdown('<div class="main-header">Welcome to Springboard</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">AI-powered LinkedIn job application automation</div>',
        unsafe_allow_html=True,
    )

    # Overview metrics
    try:
        with get_db() as session:
            from src.database.repositories.job_repository import JobRepository
            from src.database.repositories.application_repository import ApplicationRepository

            job_repo = JobRepository(session)
            app_repo = ApplicationRepository(session)

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📋 Total Jobs Scraped", job_repo.count_all())
            with col2:
                st.metric("📤 Applications Sent", app_repo.count_all())
            with col3:
                st.metric("📊 Response Rate", f"{app_repo.get_response_rate()}%")
            with col4:
                interviews = app_repo.count_by_status("interview")
                st.metric("🎯 Interviews", interviews)
    except Exception as e:
        st.warning(f"Could not load metrics: {e}")

    st.markdown("---")

    # Quick actions
    st.markdown("### Quick Actions")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🔍 Start Job Search", use_container_width=True):
            st.switch_page("pages/2_🔍_Job_Search.py")
    with col2:
        if st.button("📋 View Matches", use_container_width=True):
            st.switch_page("pages/3_📋_Jobs.py")
    with col3:
        if st.button("📄 Applications", use_container_width=True):
            st.switch_page("pages/4_📄_Applications.py")
    with col4:
        if st.button("👤 Update Profile", use_container_width=True):
            st.switch_page("pages/5_👤_Profile.py")

    st.markdown("---")

    # System status
    st.markdown("### Agent Status")
    agents = [
        ("LinkedIn Scraper", "idle", "Waiting for search command"),
        ("Job Matcher", "idle", "Waiting for jobs to analyze"),
        ("Resume Customizer", "idle", "Waiting for matched jobs"),
        ("Application Submitter", "idle", "Waiting for customized applications"),
    ]

    for name, status, desc in agents:
        with st.expander(f"{'🟢' if status == 'running' else '⚪'} {name}", expanded=False):
            st.write(f"**Status:** {status.title()}")
            st.write(f"**Activity:** {desc}")


if __name__ == "__main__":
    main()
