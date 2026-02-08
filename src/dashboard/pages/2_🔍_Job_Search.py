"""Job Search page - Configure and launch job searches."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st

from src.utils.config import Config
from src.database.connection import init_db

st.set_page_config(page_title="Springboard - Job Search", page_icon="🔍", layout="wide")
st.title("🔍 Job Search")

try:
    init_db()
except Exception:
    pass

config = Config()

# Initialize session state for search templates
if "search_templates" not in st.session_state:
    st.session_state.search_templates = {}

if "last_search_criteria" not in st.session_state:
    st.session_state.last_search_criteria = {}

# Search Configuration Form
with st.form("search_form"):
    st.subheader("Search Criteria")

    col1, col2 = st.columns(2)
    with col1:
        job_titles = st.text_area(
            "Job Titles (one per line)",
            value="\n".join(config.search_titles),
            height=120,
            help="Enter job titles to search for, one per line.",
        )
        location = st.text_input(
            "Location",
            value=config.search_locations[0] if config.search_locations else "United States",
        )
        experience_level = st.selectbox(
            "Experience Level",
            ["Entry level", "Associate", "Mid-Senior level", "Director", "Executive"],
            index=2,
        )

    with col2:
        remote_preference = st.selectbox(
            "Remote Preference",
            ["On-site", "Remote", "Hybrid"],
            index=1,
        )
        salary_col1, salary_col2 = st.columns(2)
        with salary_col1:
            salary_min = st.number_input("Min Salary ($)", value=100000, step=10000, min_value=0)
        with salary_col2:
            salary_max = st.number_input("Max Salary ($)", value=200000, step=10000, min_value=0)

    st.markdown("---")
    st.subheader("Search Settings")

    col3, col4 = st.columns(2)
    with col3:
        easy_apply_only = st.checkbox("Easy Apply Only", value=config.easy_apply_only)
        max_jobs = st.slider("Max Jobs to Scrape", 10, 200, config.max_jobs_per_search)
        match_threshold = st.slider(
            "Match Threshold (%)", 0, 100, config.min_match_score,
            help="Only show jobs with match score above this threshold.",
        )

    with col4:
        auto_apply = st.checkbox(
            "Auto-Apply to High Matches",
            value=False,
            help=f"Automatically apply to jobs scoring above {config.auto_apply_threshold}%.",
        )
        max_daily = st.slider(
            "Max Applications Per Day",
            1, 50, config.max_applications_per_day,
        )
        min_delay = st.number_input(
            "Min Delay Between Actions (sec)",
            value=config.automation.get("min_delay_between_actions", 3),
            min_value=1,
        )
        max_delay = st.number_input(
            "Max Delay Between Actions (sec)",
            value=config.automation.get("max_delay_between_actions", 8),
            min_value=2,
        )

    submitted = st.form_submit_button("🚀 Start Search", use_container_width=True)

    if submitted:
        criteria = {
            "keywords": [t.strip() for t in job_titles.strip().split("\n") if t.strip()],
            "location": location,
            "experience_level": experience_level,
            "remote_preference": remote_preference,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "easy_apply_only": easy_apply_only,
            "max_jobs": max_jobs,
            "match_threshold": match_threshold,
            "auto_apply": auto_apply,
            "max_daily": max_daily,
            "min_delay": min_delay,
            "max_delay": max_delay,
        }
        st.session_state.last_search_criteria = criteria
        st.success("Search criteria saved! Navigate to Agent Monitor to launch the workflow.")
        st.json(criteria)

st.markdown("---")

# Search Templates
st.subheader("Search Templates")
col_save, col_load = st.columns(2)

with col_save:
    template_name = st.text_input("Template Name")
    if st.button("💾 Save Current as Template") and template_name:
        if st.session_state.last_search_criteria:
            st.session_state.search_templates[template_name] = (
                st.session_state.last_search_criteria.copy()
            )
            st.success(f"Template '{template_name}' saved!")
        else:
            st.warning("No search criteria to save. Submit the form first.")

with col_load:
    templates = list(st.session_state.search_templates.keys())
    if templates:
        selected = st.selectbox("Load Template", templates)
        if st.button("📂 Load Template"):
            st.session_state.last_search_criteria = (
                st.session_state.search_templates[selected].copy()
            )
            st.success(f"Template '{selected}' loaded! Refresh the page to see values.")
    else:
        st.info("No saved templates yet.")
