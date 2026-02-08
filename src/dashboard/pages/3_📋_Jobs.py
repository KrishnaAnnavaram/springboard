"""Jobs page - Browse, filter, and manage scraped job listings."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st

from src.database.connection import get_db, init_db
from src.database.repositories.job_repository import JobRepository

st.set_page_config(page_title="Springboard - Jobs", page_icon="📋", layout="wide")
st.title("📋 Job Listings")

try:
    init_db()
except Exception:
    pass

# Tabs
tab_all, tab_matched, tab_saved, tab_applied, tab_ignored = st.tabs(
    ["All Jobs", "Matched", "Saved", "Applied", "Ignored"]
)

# Filters in sidebar
with st.sidebar:
    st.markdown("### Filters")
    filter_query = st.text_input("Search", placeholder="Title, company, or keyword...")
    filter_location = st.text_input("Location", placeholder="e.g. Remote, New York...")
    filter_company = st.text_input("Company", placeholder="e.g. Google...")
    filter_min_score = st.slider("Min Match Score", 0, 100, 0)

    sort_by = st.selectbox("Sort By", [
        "Date (Newest)", "Match Score (Highest)", "Company (A-Z)"
    ])

    page_size = 20
    page_num = st.number_input("Page", min_value=1, value=1, step=1)


def render_job_list(jobs, show_actions: bool = True) -> None:
    """Render a list of jobs as cards."""
    if not jobs:
        st.info("No jobs found matching your criteria.")
        return

    st.caption(f"Showing {len(jobs)} jobs")

    for job in jobs:
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                badges = ""
                if job.is_easy_apply:
                    badges += " 🟢 Easy Apply"
                st.markdown(f"### {job.title}{badges}")
                st.markdown(f"**{job.company}** · {job.location or 'Location not specified'}")
                if job.salary_range:
                    st.markdown(f"💰 {job.salary_range}")

            with col2:
                if job.match_score is not None:
                    score = int(job.match_score)
                    color = "normal" if score >= 70 else "off"
                    st.metric("Match", f"{score}%")
                    st.progress(score / 100)
                else:
                    st.caption("Not scored")

            with col3:
                if job.scraped_date:
                    st.caption(job.scraped_date.strftime("%b %d, %Y"))
                st.caption(f"Status: {job.status}")

            with st.expander("View Details"):
                if job.description:
                    st.markdown("**Description:**")
                    st.write(job.description[:2000])
                if job.requirements:
                    st.markdown("**Requirements:**")
                    st.write(job.requirements[:1000])
                if job.match_reasoning:
                    st.markdown("**Match Analysis:**")
                    st.info(job.match_reasoning)
                if job.job_url:
                    st.markdown(f"[View on LinkedIn]({job.job_url})")

                if show_actions:
                    action_cols = st.columns(3)
                    with action_cols[0]:
                        if st.button("⭐ Save", key=f"save_{job.id}"):
                            try:
                                with get_db() as s:
                                    JobRepository(s).update_status(job.id, "saved")
                                st.success("Job saved!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with action_cols[1]:
                        if st.button("📤 Apply Now", key=f"apply_{job.id}"):
                            st.info("Navigate to Agent Monitor to start the application workflow.")
                    with action_cols[2]:
                        if st.button("🚫 Ignore", key=f"ignore_{job.id}"):
                            try:
                                with get_db() as s:
                                    JobRepository(s).update_status(job.id, "ignored")
                                st.success("Job ignored.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

            st.markdown("---")


def get_filtered_jobs(session, status_filter=None):
    """Get jobs with applied filters and sorting."""
    repo = JobRepository(session)
    offset = (page_num - 1) * page_size

    if filter_query or filter_location or filter_min_score > 0:
        jobs = repo.search(
            query=filter_query or "",
            status=status_filter,
            min_score=filter_min_score if filter_min_score > 0 else None,
            location=filter_location or None,
            limit=page_size,
        )
    elif status_filter:
        jobs = repo.get_by_status(status_filter, limit=page_size)
    else:
        jobs = repo.get_all(limit=page_size, offset=offset)

    if filter_company:
        jobs = [j for j in jobs if filter_company.lower() in (j.company or "").lower()]

    if sort_by == "Match Score (Highest)":
        jobs.sort(key=lambda j: j.match_score or 0, reverse=True)
    elif sort_by == "Company (A-Z)":
        jobs.sort(key=lambda j: (j.company or "").lower())

    return jobs


try:
    with get_db() as session:
        repo = JobRepository(session)

        with tab_all:
            jobs = get_filtered_jobs(session)
            st.caption(f"Total: {repo.count_all()} jobs")
            render_job_list(jobs)

        with tab_matched:
            jobs = repo.get_matched_jobs(min_score=max(filter_min_score, 60), limit=page_size)
            render_job_list(jobs)

        with tab_saved:
            jobs = get_filtered_jobs(session, status_filter="saved")
            render_job_list(jobs)

        with tab_applied:
            jobs = get_filtered_jobs(session, status_filter="applied")
            render_job_list(jobs, show_actions=False)

        with tab_ignored:
            jobs = get_filtered_jobs(session, status_filter="ignored")
            render_job_list(jobs)

except Exception as e:
    st.error(f"Error loading jobs: {e}")
