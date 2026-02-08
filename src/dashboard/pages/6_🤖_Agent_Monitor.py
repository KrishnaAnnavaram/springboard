"""Agent Monitor page - Visualize workflow and control agents."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import json
from datetime import datetime

from src.database.connection import init_db
from src.utils.config import Config

st.set_page_config(page_title="Springboard - Agent Monitor", page_icon="🤖", layout="wide")
st.title("🤖 Agent Monitor")

try:
    init_db()
except Exception:
    pass

config = Config()

# Initialize session state
if "workflow_running" not in st.session_state:
    st.session_state.workflow_running = False
if "workflow_status" not in st.session_state:
    st.session_state.workflow_status = "idle"
if "activity_log" not in st.session_state:
    st.session_state.activity_log = []
if "workflow_errors" not in st.session_state:
    st.session_state.workflow_errors = []
if "workflow_state" not in st.session_state:
    st.session_state.workflow_state = {}
if "agent_stats" not in st.session_state:
    st.session_state.agent_stats = {
        "scraper": {"processed": 0, "status": "idle", "last_activity": None},
        "matcher": {"processed": 0, "status": "idle", "last_activity": None},
        "customizer": {"processed": 0, "status": "idle", "last_activity": None},
        "applier": {"processed": 0, "status": "idle", "last_activity": None},
    }

# Workflow Pipeline Visualization
st.subheader("Workflow Pipeline")

agents_info = [
    ("scraper", "LinkedIn Scraper", "Scrape jobs from LinkedIn"),
    ("matcher", "Job Matcher", "Score jobs with AI"),
    ("customizer", "Resume Customizer", "Tailor resumes & cover letters"),
    ("applier", "Application Submitter", "Submit Easy Apply"),
]

cols = st.columns(len(agents_info))
for i, (key, name, desc) in enumerate(agents_info):
    stat = st.session_state.agent_stats.get(key, {})
    status = stat.get("status", "idle")
    icons = {"idle": "⚪", "running": "🟢", "completed": "✅", "failed": "🔴"}

    with cols[i]:
        st.markdown(f"### {icons.get(status, '⚪')} {name}")
        st.caption(desc)
        st.metric("Processed", stat.get("processed", 0))
        last = stat.get("last_activity")
        if last:
            st.caption(f"Last: {last}")
        else:
            st.caption("No activity yet")

        if i < len(agents_info) - 1:
            st.markdown("")

st.markdown("---")

# Control Panel
st.subheader("Control Panel")
ctrl_cols = st.columns(5)

with ctrl_cols[0]:
    if st.button("▶️ Start Workflow", use_container_width=True, disabled=st.session_state.workflow_running):
        st.session_state.workflow_running = True
        st.session_state.workflow_status = "running"
        st.session_state.activity_log.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": "INFO",
            "message": "Workflow started",
        })
        st.success("Workflow started! Monitor progress below.")
        st.rerun()

with ctrl_cols[1]:
    if st.button("⏸️ Pause", use_container_width=True, disabled=not st.session_state.workflow_running):
        st.session_state.workflow_status = "paused"
        st.session_state.activity_log.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": "WARNING",
            "message": "Workflow paused by user",
        })
        st.info("Workflow paused.")

with ctrl_cols[2]:
    if st.button("⏹️ Stop", use_container_width=True, disabled=not st.session_state.workflow_running):
        st.session_state.workflow_running = False
        st.session_state.workflow_status = "stopped"
        st.session_state.activity_log.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": "WARNING",
            "message": "Workflow stopped by user",
        })
        st.warning("Workflow stopped.")

with ctrl_cols[3]:
    if st.button("🔄 Restart", use_container_width=True):
        st.session_state.workflow_running = True
        st.session_state.workflow_status = "running"
        st.session_state.workflow_errors = []
        st.session_state.activity_log.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": "INFO",
            "message": "Workflow restarted",
        })
        st.success("Workflow restarted!")
        st.rerun()

with ctrl_cols[4]:
    status = st.session_state.workflow_status
    status_colors = {
        "running": "🟢", "paused": "🟡", "stopped": "🔴",
        "idle": "⚪", "completed": "✅", "failed": "🔴",
    }
    st.markdown(f"### {status_colors.get(status, '⚪')} {status.title()}")

st.markdown("---")

# Activity Log
st.subheader("Activity Log")
log_container = st.container()
with log_container:
    if st.session_state.activity_log:
        for entry in reversed(st.session_state.activity_log[-50:]):
            level = entry.get("level", "INFO")
            colors = {"INFO": "blue", "WARNING": "orange", "ERROR": "red"}
            color = colors.get(level, "gray")
            st.markdown(
                f":{color}[`[{entry['time']}] [{level}]`] {entry['message']}"
            )
    else:
        st.info("No activity yet. Start the workflow to see logs.")

st.markdown("---")

# State Viewer
col_state, col_errors = st.columns(2)

with col_state:
    st.subheader("Workflow State")
    state_data = st.session_state.workflow_state or {
        "status": st.session_state.workflow_status,
        "current_step": "none",
        "iteration": 0,
        "scraped_jobs": 0,
        "matched_jobs": 0,
        "pending_applications": 0,
        "submitted_applications": 0,
    }
    st.json(state_data)

with col_errors:
    st.subheader("Error Log")
    if st.session_state.workflow_errors:
        for i, err in enumerate(st.session_state.workflow_errors):
            with st.expander(f"❌ {err.get('step', 'Unknown')} - {err.get('time', '')}", expanded=False):
                st.write(f"**Error:** {err.get('message', 'Unknown error')}")
                if st.button("🔄 Retry", key=f"retry_err_{i}"):
                    st.session_state.activity_log.append({
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "level": "INFO",
                        "message": f"Retrying step: {err.get('step', 'Unknown')}",
                    })
                    st.rerun()
    else:
        st.success("No errors!")

st.markdown("---")

# Performance Metrics
st.subheader("Performance Metrics")
perf_cols = st.columns(4)
with perf_cols[0]:
    st.metric("API Calls", st.session_state.get("api_calls", 0))
with perf_cols[1]:
    st.metric("Tokens Used", f"{st.session_state.get('tokens_used', 0):,}")
with perf_cols[2]:
    tokens = st.session_state.get("tokens_used", 0)
    cost = tokens * 0.000003
    st.metric("Est. Cost", f"${cost:.4f}")
with perf_cols[3]:
    st.metric("Avg Response", f"{st.session_state.get('avg_response_time', 0):.1f}s")
