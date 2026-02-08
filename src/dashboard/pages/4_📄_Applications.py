"""Applications page - Track and manage job applications."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime

from src.database.connection import get_db, init_db
from src.database.repositories.application_repository import ApplicationRepository
from src.database.repositories.job_repository import JobRepository

st.set_page_config(page_title="Springboard - Applications", page_icon="📄", layout="wide")
st.title("📄 Applications")

try:
    init_db()
except Exception:
    pass

# Status tabs
statuses = ["All", "Pending", "Submitted", "Viewed", "Interview", "Rejected", "Offer"]
tabs = st.tabs(statuses)

try:
    with get_db() as session:
        app_repo = ApplicationRepository(session)

        # Stats row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Applications", app_repo.count_all())
        with col2:
            st.metric("Response Rate", f"{app_repo.get_response_rate()}%")
        with col3:
            st.metric("Interviews", app_repo.count_by_status("interview"))
        with col4:
            st.metric("Offers", app_repo.count_by_status("offer"))

        st.markdown("---")

        for i, status_name in enumerate(statuses):
            with tabs[i]:
                if status_name == "All":
                    apps = app_repo.get_with_job_details(limit=100)
                else:
                    apps = app_repo.get_by_status(status_name.lower(), limit=100)

                if not apps:
                    st.info(f"No {status_name.lower()} applications yet.")
                    continue

                # Build dataframe
                data = []
                for app in apps:
                    job_title = app.job.title if app.job else "Unknown"
                    company = app.job.company if app.job else "Unknown"
                    score = app.job.match_score if app.job and app.job.match_score else 0
                    applied = app.applied_date.strftime("%Y-%m-%d") if app.applied_date else "-"
                    data.append({
                        "ID": app.id,
                        "Status": app.status.title(),
                        "Job Title": job_title,
                        "Company": company,
                        "Applied": applied,
                        "Match Score": f"{score:.0f}%" if score else "-",
                    })

                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Application details
                st.markdown("#### Application Details")
                for app in apps:
                    job_title = app.job.title if app.job else "Unknown"
                    company = app.job.company if app.job else "Unknown"
                    status_icons = {
                        "pending": "⏳", "submitted": "📤", "viewed": "👀",
                        "interview": "🎯", "rejected": "❌", "offer": "🎉",
                    }
                    icon = status_icons.get(app.status, "📋")

                    with st.expander(f"{icon} {job_title} at {company}"):
                        detail_col1, detail_col2 = st.columns(2)
                        with detail_col1:
                            st.markdown(f"**Status:** {app.status.title()}")
                            st.markdown(f"**Applied:** {app.applied_date or 'Not yet'}")
                            st.markdown(f"**Response:** {app.response_date or 'Awaiting'}")
                            if app.resume_version:
                                st.markdown(f"**Resume:** {app.resume_version}")

                        with detail_col2:
                            new_status = st.selectbox(
                                "Update Status",
                                ["pending", "submitted", "viewed", "interview", "rejected", "offer"],
                                index=["pending", "submitted", "viewed", "interview", "rejected", "offer"].index(app.status) if app.status in ["pending", "submitted", "viewed", "interview", "rejected", "offer"] else 0,
                                key=f"status_{app.id}",
                            )
                            if st.button("Update", key=f"update_{app.id}"):
                                try:
                                    with get_db() as s:
                                        ApplicationRepository(s).update_status(app.id, new_status)
                                    st.success("Status updated!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")

                            note_text = st.text_input("Add Note", key=f"note_{app.id}")
                            if st.button("Add Note", key=f"addnote_{app.id}") and note_text:
                                try:
                                    with get_db() as s:
                                        ApplicationRepository(s).add_note(app.id, note_text)
                                    st.success("Note added!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")

                        if app.notes:
                            st.markdown("**Notes:**")
                            st.text(app.notes)

                        if app.cover_letter_text:
                            st.markdown("**Cover Letter:**")
                            st.text(app.cover_letter_text[:500])

                # Export
                if data:
                    csv = pd.DataFrame(data).to_csv(index=False)
                    st.download_button(
                        "📥 Export to CSV",
                        csv,
                        "applications.csv",
                        "text/csv",
                        key=f"export_{status_name}",
                    )

except Exception as e:
    st.error(f"Error loading applications: {e}")
