"""Home page - Dashboard overview with metrics and activity feed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta

from src.database.connection import get_db, init_db
from src.database.repositories.job_repository import JobRepository
from src.database.repositories.application_repository import ApplicationRepository

st.set_page_config(page_title="Springboard - Home", page_icon="🏠", layout="wide")
st.title("🏠 Dashboard")

try:
    init_db()
except Exception:
    pass

# Metrics row
try:
    with get_db() as session:
        job_repo = JobRepository(session)
        app_repo = ApplicationRepository(session)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📋 Total Jobs", job_repo.count_all())
        with col2:
            st.metric("📤 Applications Sent", app_repo.count_all())
        with col3:
            st.metric("📊 Response Rate", f"{app_repo.get_response_rate()}%")
        with col4:
            st.metric("🎯 Interviews", app_repo.count_by_status("interview"))

        st.markdown("---")

        # Application timeline chart
        st.subheader("Application Timeline (Last 30 Days)")
        daily = app_repo.get_daily_counts(30)
        if daily:
            dates = [d["date"] for d in daily]
            counts = [d["count"] for d in daily]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=dates, y=counts, mode="lines+markers",
                name="Applications", line=dict(color="#667eea", width=3),
                marker=dict(size=8),
            ))
            fig.update_layout(
                xaxis_title="Date", yaxis_title="Applications",
                template="plotly_white", height=350,
                margin=dict(l=40, r=40, t=20, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No application data yet. Start applying to see your timeline!")

        st.markdown("---")

        # Recent activity
        st.subheader("Recent Activity")
        recent_apps = app_repo.get_with_job_details(limit=20)
        if recent_apps:
            for app in recent_apps:
                status_icons = {
                    "pending": "⏳", "submitted": "📤", "viewed": "👀",
                    "interview": "🎯", "rejected": "❌", "offer": "🎉",
                }
                icon = status_icons.get(app.status, "📋")
                job_title = app.job.title if app.job else "Unknown"
                company = app.job.company if app.job else "Unknown"
                date_str = app.applied_date.strftime("%b %d, %Y") if app.applied_date else "Pending"
                st.markdown(
                    f"{icon} **{job_title}** at {company} — *{app.status.title()}* ({date_str})"
                )
        else:
            st.info("No applications yet. Start your job search!")

        st.markdown("---")

        # Quick Actions
        st.subheader("Quick Actions")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.button("🔍 Start Search", use_container_width=True)
        with col2:
            st.button("📋 View Matches", use_container_width=True)
        with col3:
            st.button("📄 Applications", use_container_width=True)
        with col4:
            st.button("👤 Update Profile", use_container_width=True)

        st.markdown("---")

        # Agent Status
        st.subheader("Agent Status")
        agents = [
            ("LinkedIn Scraper", "idle", f"{job_repo.count_today()} jobs today"),
            ("Job Matcher", "idle", f"{job_repo.count_by_status('matched')} matched"),
            ("Resume Customizer", "idle", "Ready"),
            ("Application Submitter", "idle", f"{app_repo.count_today()} applied today"),
        ]
        cols = st.columns(4)
        for i, (name, status, detail) in enumerate(agents):
            with cols[i]:
                status_color = "🟢" if status == "running" else "⚪"
                st.markdown(f"### {status_color} {name}")
                st.caption(f"Status: {status.title()}")
                st.caption(detail)

except Exception as e:
    st.error(f"Error loading dashboard: {e}")
