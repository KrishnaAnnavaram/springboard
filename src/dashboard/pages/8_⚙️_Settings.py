"""Settings page - Configure credentials, automation, and system settings."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import os
import shutil
from datetime import datetime, time

import streamlit as st

from src.database.connection import get_db, get_engine, init_db
from src.utils.config import Config

st.set_page_config(page_title="Springboard - Settings", page_icon="⚙️", layout="wide")
st.title("⚙️ Settings")

try:
    init_db()
except Exception:
    pass

config = Config()

# LinkedIn Credentials
st.subheader("LinkedIn Credentials")
col1, col2 = st.columns(2)
with col1:
    li_email = st.text_input("LinkedIn Email", value=config.linkedin_email or "Not configured")
    li_password = st.text_input("LinkedIn Password", type="password", placeholder="Enter new password to update")
with col2:
    st.markdown("**Session Status**")
    st.markdown("⚪ Not connected")
    if st.button("🔗 Test Connection"):
        if config.linkedin_email and config.linkedin_password:
            st.info("Connection test would launch browser in production. Credentials are configured.")
        else:
            st.warning("Please configure LinkedIn credentials in .env file.")

st.markdown("---")

# Anthropic API
st.subheader("Anthropic API")
col3, col4 = st.columns(2)
with col3:
    api_key = config.anthropic_api_key
    masked = f"sk-ant-...{api_key[-4:]}" if api_key and len(api_key) > 4 else "Not configured"
    st.text_input("API Key", value=masked, disabled=True)
    new_api_key = st.text_input("Update API Key", type="password", placeholder="Enter new API key")
with col4:
    st.markdown(f"**Model:** {config.anthropic_model}")
    st.markdown(f"**Max Tokens:** {config.anthropic_max_tokens}")
    if st.button("🧪 Test API"):
        if config.anthropic_api_key:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=config.anthropic_api_key)
                response = client.messages.create(
                    model=config.anthropic_model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Say 'ok'"}],
                )
                st.success(f"API connection successful! Response: {response.content[0].text}")
            except Exception as e:
                st.error(f"API test failed: {e}")
        else:
            st.warning("No API key configured.")

st.markdown("---")

# Automation Settings
st.subheader("Automation Settings")
auto_col1, auto_col2 = st.columns(2)
with auto_col1:
    max_apps = st.number_input(
        "Max Applications Per Day",
        value=config.max_applications_per_day,
        min_value=1, max_value=100,
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

with auto_col2:
    auto_threshold = st.slider(
        "Auto-Apply Threshold (%)",
        0, 100, config.auto_apply_threshold,
        help="Auto-apply to jobs scoring above this threshold.",
    )
    work_start = st.time_input(
        "Working Hours Start",
        value=time(config.automation.get("working_hours", {}).get("start", 9), 0),
    )
    work_end = st.time_input(
        "Working Hours End",
        value=time(config.automation.get("working_hours", {}).get("end", 17), 0),
    )

st.markdown("---")

# Notification Settings
st.subheader("Notification Settings")
notif_col1, notif_col2 = st.columns(2)
with notif_col1:
    email_alerts = st.checkbox("Enable Email Alerts", value=False)
    if email_alerts:
        alert_email = st.text_input("Alert Email Address")
with notif_col2:
    alert_triggers = st.multiselect(
        "Alert Triggers",
        ["New Matches Found", "Application Submitted", "Response Received", "Daily Summary"],
        default=["Response Received"],
    )

st.markdown("---")

# Database Management
st.subheader("Database Management")
db_col1, db_col2 = st.columns(2)
with db_col1:
    st.markdown(f"**Database URL:** `{config.database_url}`")
    if st.button("🔌 Test Connection"):
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            st.success("Database connection successful!")
        except Exception as e:
            st.error(f"Connection failed: {e}")

    db_path = config.database_url.replace("sqlite:///", "")
    if os.path.exists(db_path):
        size = os.path.getsize(db_path)
        st.markdown(f"**Size:** {size / 1024:.1f} KB")
    else:
        st.markdown("**Size:** N/A")

with db_col2:
    if st.button("💾 Backup Database"):
        try:
            db_path = config.database_url.replace("sqlite:///", "")
            if os.path.exists(db_path):
                backup_dir = config.project_root / "data" / "backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = backup_dir / f"springboard_backup_{timestamp}.db"
                shutil.copy2(db_path, backup_path)
                st.success(f"Backup created: {backup_path.name}")
            else:
                st.warning("Database file not found.")
        except Exception as e:
            st.error(f"Backup failed: {e}")

    if st.button("🗑️ Clear Old Data (90+ days)"):
        confirm = st.checkbox("I confirm I want to delete old data", key="confirm_clear")
        if confirm:
            st.info("Old data clearing would be implemented in production.")
        else:
            st.warning("Please confirm before clearing data.")

st.markdown("---")

# Advanced Settings
st.subheader("Advanced Settings")
adv_col1, adv_col2 = st.columns(2)
with adv_col1:
    debug_logging = st.toggle("Debug Logging", value=config.log_level.upper() == "DEBUG")
    headless_mode = st.toggle(
        "Browser Headless Mode",
        value=config.linkedin_config.get("browser", {}).get("headless", True),
    )

with adv_col2:
    if st.button("🧹 Clear Cache"):
        st.cache_data.clear()
        st.success("Cache cleared!")

    if st.button("📋 View Log File"):
        log_path = config.project_root / "data" / "logs" / "springboard.log"
        if log_path.exists():
            with open(log_path) as f:
                lines = f.readlines()
                st.text_area("Log Output (last 50 lines)", value="".join(lines[-50:]), height=300)
        else:
            st.info("No log file found yet.")

st.markdown("---")

# Save Settings
if st.button("💾 Save Settings", type="primary", use_container_width=True):
    try:
        settings_summary = {
            "max_applications_per_day": max_apps,
            "auto_apply_threshold": auto_threshold,
            "min_delay": min_delay,
            "max_delay": max_delay,
            "working_hours": f"{work_start} - {work_end}",
            "debug_logging": debug_logging,
            "headless_mode": headless_mode,
            "email_alerts": email_alerts,
            "alert_triggers": alert_triggers,
        }
        st.session_state.saved_settings = settings_summary
        st.success("Settings saved successfully!")
        st.json(settings_summary)
    except Exception as e:
        st.error(f"Error saving settings: {e}")
