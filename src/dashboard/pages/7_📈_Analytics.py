"""Analytics page - Charts, metrics, and insights."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from src.database.connection import get_db, init_db
from src.database.repositories.job_repository import JobRepository
from src.database.repositories.application_repository import ApplicationRepository

st.set_page_config(page_title="Springboard - Analytics", page_icon="📈", layout="wide")
st.title("📈 Analytics")

try:
    init_db()
except Exception:
    pass

try:
    with get_db() as session:
        job_repo = JobRepository(session)
        app_repo = ApplicationRepository(session)

        # Overview metrics
        st.subheader("Overview")
        col1, col2, col3, col4 = st.columns(4)
        total_scraped = job_repo.count_all()
        total_apps = app_repo.count_all()
        response_rate = app_repo.get_response_rate()

        all_jobs = job_repo.get_all(limit=10000)
        scores = [j.match_score for j in all_jobs if j.match_score is not None]
        avg_score = sum(scores) / len(scores) if scores else 0

        with col1:
            st.metric("Total Scraped", total_scraped)
        with col2:
            st.metric("Applications", total_apps)
        with col3:
            st.metric("Response Rate", f"{response_rate}%")
        with col4:
            st.metric("Avg Match Score", f"{avg_score:.1f}%")

        st.markdown("---")

        # Application Funnel
        st.subheader("Application Funnel")
        matched = job_repo.count_by_status("matched")
        applied = app_repo.count_by_status("submitted") + app_repo.count_by_status("viewed")
        responded = app_repo.count_by_status("interview") + app_repo.count_by_status("rejected") + app_repo.count_by_status("offer")
        interviews = app_repo.count_by_status("interview")
        offers = app_repo.count_by_status("offer")

        funnel_data = {
            "Stage": ["Scraped", "Matched", "Applied", "Responded", "Interview", "Offer"],
            "Count": [total_scraped, matched, applied, responded, interviews, offers],
        }

        if any(funnel_data["Count"]):
            fig_funnel = go.Figure(go.Funnel(
                y=funnel_data["Stage"],
                x=funnel_data["Count"],
                textinfo="value+percent initial",
                marker=dict(color=["#667eea", "#764ba2", "#f093fb", "#f5576c", "#4facfe", "#00f2fe"]),
            ))
            fig_funnel.update_layout(height=350, margin=dict(l=40, r=40, t=20, b=20))
            st.plotly_chart(fig_funnel, use_container_width=True)
        else:
            st.info("No data for funnel yet. Start searching and applying!")

        st.markdown("---")

        # Charts row
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            # Applications over time
            st.subheader("Applications Over Time")
            daily = app_repo.get_daily_counts(30)
            if daily:
                fig_timeline = go.Figure()
                fig_timeline.add_trace(go.Scatter(
                    x=[d["date"] for d in daily],
                    y=[d["count"] for d in daily],
                    mode="lines+markers",
                    fill="tozeroy",
                    line=dict(color="#667eea", width=2),
                ))
                fig_timeline.update_layout(
                    xaxis_title="Date", yaxis_title="Applications",
                    template="plotly_white", height=300,
                    margin=dict(l=40, r=20, t=10, b=40),
                )
                st.plotly_chart(fig_timeline, use_container_width=True)
            else:
                st.info("No timeline data available yet.")

        with chart_col2:
            # Status breakdown pie chart
            st.subheader("Status Breakdown")
            breakdown = app_repo.get_status_breakdown()
            if breakdown:
                fig_pie = px.pie(
                    names=list(breakdown.keys()),
                    values=list(breakdown.values()),
                    color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig_pie.update_layout(height=300, margin=dict(l=20, r=20, t=10, b=20))
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("No status data yet.")

        st.markdown("---")

        # More charts
        chart_col3, chart_col4 = st.columns(2)

        with chart_col3:
            # Top companies
            st.subheader("Top Companies")
            companies = job_repo.get_top_companies(20)
            if companies:
                fig_companies = go.Figure(go.Bar(
                    y=[c[0] for c in companies[:15]],
                    x=[c[1] for c in companies[:15]],
                    orientation="h",
                    marker_color="#764ba2",
                ))
                fig_companies.update_layout(
                    yaxis=dict(autorange="reversed"),
                    template="plotly_white", height=400,
                    margin=dict(l=150, r=20, t=10, b=40),
                )
                st.plotly_chart(fig_companies, use_container_width=True)
            else:
                st.info("No company data yet.")

        with chart_col4:
            # Match score distribution
            st.subheader("Match Score Distribution")
            if scores:
                fig_hist = px.histogram(
                    x=scores, nbins=20,
                    labels={"x": "Match Score", "y": "Count"},
                    color_discrete_sequence=["#667eea"],
                )
                fig_hist.update_layout(
                    template="plotly_white", height=400,
                    margin=dict(l=40, r=20, t=10, b=40),
                )
                st.plotly_chart(fig_hist, use_container_width=True)
            else:
                st.info("No match scores yet.")

        st.markdown("---")

        # Success metrics table
        st.subheader("Success Metrics by Company")
        if companies:
            metrics_data = []
            for company_name, job_count in companies[:20]:
                company_apps = [
                    a for a in app_repo.get_all(limit=1000)
                    if a.job and a.job.company == company_name
                ]
                total_co = len(company_apps)
                responded_co = len([a for a in company_apps if a.status in ("interview", "rejected", "offer")])
                interview_co = len([a for a in company_apps if a.status == "interview"])
                co_scores = [
                    a.job.match_score for a in company_apps
                    if a.job and a.job.match_score is not None
                ]
                avg_co_score = sum(co_scores) / len(co_scores) if co_scores else 0

                metrics_data.append({
                    "Company": company_name,
                    "Jobs": job_count,
                    "Applications": total_co,
                    "Response Rate": f"{(responded_co / total_co * 100):.0f}%" if total_co > 0 else "-",
                    "Interview Rate": f"{(interview_co / total_co * 100):.0f}%" if total_co > 0 else "-",
                    "Avg Match Score": f"{avg_co_score:.0f}%",
                })

            df_metrics = pd.DataFrame(metrics_data)
            st.dataframe(df_metrics, use_container_width=True, hide_index=True)

            csv = df_metrics.to_csv(index=False)
            st.download_button("📥 Export Metrics CSV", csv, "analytics_metrics.csv", "text/csv")
        else:
            st.info("No company metrics available yet.")

        # Export all data
        st.markdown("---")
        st.subheader("Export Data")
        exp_col1, exp_col2 = st.columns(2)
        with exp_col1:
            if all_jobs:
                jobs_data = [{
                    "Title": j.title, "Company": j.company, "Location": j.location,
                    "Match Score": j.match_score, "Status": j.status,
                    "Salary": j.salary_range, "URL": j.job_url,
                } for j in all_jobs]
                csv_jobs = pd.DataFrame(jobs_data).to_csv(index=False)
                st.download_button("📥 Export All Jobs", csv_jobs, "all_jobs.csv", "text/csv")

        with exp_col2:
            all_apps = app_repo.get_with_job_details(limit=10000)
            if all_apps:
                apps_data = [{
                    "Job": a.job.title if a.job else "?",
                    "Company": a.job.company if a.job else "?",
                    "Status": a.status,
                    "Applied": str(a.applied_date) if a.applied_date else "-",
                    "Score": a.job.match_score if a.job else 0,
                } for a in all_apps]
                csv_apps = pd.DataFrame(apps_data).to_csv(index=False)
                st.download_button("📥 Export All Applications", csv_apps, "all_applications.csv", "text/csv")

except Exception as e:
    st.error(f"Error loading analytics: {e}")
