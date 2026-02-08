"""Profile page - Manage user profile, skills, and preferences."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import json

from src.database.connection import get_db, init_db
from src.database.repositories.user_repository import UserRepository
from src.database.repositories.resume_repository import ResumeRepository

st.set_page_config(page_title="Springboard - Profile", page_icon="👤", layout="wide")
st.title("👤 Profile Management")

try:
    init_db()
except Exception:
    pass

# Load existing user
user = None
try:
    with get_db() as session:
        repo = UserRepository(session)
        user = repo.get_default_user()
except Exception:
    pass

# Initialize session state
if "experiences" not in st.session_state:
    if user and user.profile_data and "work_experience" in user.profile_data:
        st.session_state.experiences = user.profile_data["work_experience"]
    else:
        st.session_state.experiences = []

if "education" not in st.session_state:
    if user and user.profile_data and "education" in user.profile_data:
        st.session_state.education = user.profile_data["education"]
    else:
        st.session_state.education = []

# Personal Information
st.subheader("Personal Information")
col1, col2 = st.columns(2)
with col1:
    name = st.text_input("Full Name", value=user.name if user else "")
    email = st.text_input("Email", value=user.email if user else "")
with col2:
    phone = st.text_input("Phone", value=user.phone if user else "")
    linkedin_url = st.text_input("LinkedIn URL", value=user.linkedin_url if user else "")

st.markdown("---")

# Work Experience
st.subheader("Work Experience")

for i, exp in enumerate(st.session_state.experiences):
    with st.expander(f"{exp.get('title', 'Position')} at {exp.get('company', 'Company')}", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.experiences[i]["company"] = st.text_input(
                "Company", value=exp.get("company", ""), key=f"exp_company_{i}"
            )
            st.session_state.experiences[i]["title"] = st.text_input(
                "Title", value=exp.get("title", ""), key=f"exp_title_{i}"
            )
        with col2:
            st.session_state.experiences[i]["years"] = st.number_input(
                "Years", value=exp.get("years", 1), min_value=0, max_value=50, key=f"exp_years_{i}"
            )
        st.session_state.experiences[i]["description"] = st.text_area(
            "Description", value=exp.get("description", ""), key=f"exp_desc_{i}"
        )
        if st.button("🗑️ Remove", key=f"remove_exp_{i}"):
            st.session_state.experiences.pop(i)
            st.rerun()

if st.button("➕ Add Experience"):
    st.session_state.experiences.append({
        "company": "", "title": "", "years": 1, "description": ""
    })
    st.rerun()

st.markdown("---")

# Skills
st.subheader("Skills")
current_skills = ""
if user and user.profile_data and "skills" in user.profile_data:
    current_skills = ", ".join(user.profile_data["skills"])
skills_text = st.text_area(
    "Skills (comma-separated)",
    value=current_skills,
    help="Enter your skills separated by commas.",
)

skill_levels = {}
if skills_text.strip():
    skills_list = [s.strip() for s in skills_text.split(",") if s.strip()]
    cols = st.columns(min(len(skills_list), 4))
    existing_levels = {}
    if user and user.profile_data:
        existing_levels = user.profile_data.get("skill_levels", {})
    for i, skill in enumerate(skills_list[:20]):
        with cols[i % 4]:
            level = st.selectbox(
                skill,
                ["Beginner", "Intermediate", "Advanced", "Expert"],
                index=["Beginner", "Intermediate", "Advanced", "Expert"].index(
                    existing_levels.get(skill, "Intermediate")
                ) if existing_levels.get(skill) in ["Beginner", "Intermediate", "Advanced", "Expert"] else 1,
                key=f"skill_level_{i}",
            )
            skill_levels[skill] = level

st.markdown("---")

# Education
st.subheader("Education")
for i, edu in enumerate(st.session_state.education):
    with st.expander(f"{edu.get('degree', 'Degree')} - {edu.get('institution', 'Institution')}", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.education[i]["institution"] = st.text_input(
                "Institution", value=edu.get("institution", ""), key=f"edu_inst_{i}"
            )
            st.session_state.education[i]["degree"] = st.text_input(
                "Degree", value=edu.get("degree", ""), key=f"edu_deg_{i}"
            )
        with col2:
            st.session_state.education[i]["field"] = st.text_input(
                "Field of Study", value=edu.get("field", ""), key=f"edu_field_{i}"
            )
            st.session_state.education[i]["year"] = st.number_input(
                "Graduation Year", value=edu.get("year", 2020),
                min_value=1950, max_value=2030, key=f"edu_year_{i}"
            )
        if st.button("🗑️ Remove", key=f"remove_edu_{i}"):
            st.session_state.education.pop(i)
            st.rerun()

if st.button("➕ Add Education"):
    st.session_state.education.append({
        "institution": "", "degree": "", "field": "", "year": 2020
    })
    st.rerun()

st.markdown("---")

# Job Preferences
st.subheader("Job Preferences")
prefs = user.preferences if user and user.preferences else {}

col1, col2 = st.columns(2)
with col1:
    target_roles = st.text_area(
        "Target Roles (one per line)",
        value="\n".join(prefs.get("target_roles", [])),
    )
    preferred_locations = st.text_area(
        "Preferred Locations (one per line)",
        value="\n".join(prefs.get("locations", [])),
    )
with col2:
    pref_sal1, pref_sal2 = st.columns(2)
    with pref_sal1:
        pref_salary_min = st.number_input(
            "Min Salary ($)", value=prefs.get("salary_min", 100000), step=10000
        )
    with pref_sal2:
        pref_salary_max = st.number_input(
            "Max Salary ($)", value=prefs.get("salary_max", 200000), step=10000
        )
    remote_pref = st.selectbox(
        "Remote Preference",
        ["On-site", "Remote", "Hybrid"],
        index=["On-site", "Remote", "Hybrid"].index(prefs.get("remote_preference", "Remote"))
        if prefs.get("remote_preference") in ["On-site", "Remote", "Hybrid"] else 1,
    )
    company_size = st.multiselect(
        "Company Size Preference",
        ["Startup (1-50)", "Small (51-200)", "Medium (201-1000)", "Large (1001-5000)", "Enterprise (5000+)"],
        default=prefs.get("company_size", []),
    )

st.markdown("---")

# Resume Upload
st.subheader("Base Resume")
uploaded_file = st.file_uploader(
    "Upload your base resume", type=["txt", "pdf", "docx"],
    help="Upload your primary resume. This will be customized for each application."
)

resume_content = ""
if uploaded_file:
    if uploaded_file.type == "text/plain":
        resume_content = uploaded_file.read().decode("utf-8")
        st.text_area("Resume Preview", value=resume_content, height=200, disabled=True)
    else:
        st.info(f"Uploaded: {uploaded_file.name} ({uploaded_file.size} bytes)")
        resume_content = f"[Uploaded file: {uploaded_file.name}]"

# Show existing resume
try:
    with get_db() as session:
        resume_repo = ResumeRepository(session)
        if user:
            primary = resume_repo.get_primary(user.id)
            if primary and primary.content_text:
                st.markdown("**Current Resume:**")
                st.text_area("Current Resume Content", value=primary.content_text[:1000], height=150, disabled=True)
except Exception:
    pass

st.markdown("---")

# Save Profile
if st.button("💾 Save Profile", type="primary", use_container_width=True):
    try:
        skills_list = [s.strip() for s in skills_text.split(",") if s.strip()] if skills_text else []

        profile_data = {
            "skills": skills_list,
            "skill_levels": skill_levels,
            "work_experience": st.session_state.experiences,
            "education": st.session_state.education,
            "experience_years": sum(e.get("years", 0) for e in st.session_state.experiences),
        }

        preferences = {
            "target_roles": [r.strip() for r in target_roles.split("\n") if r.strip()],
            "locations": [l.strip() for l in preferred_locations.split("\n") if l.strip()],
            "salary_min": pref_salary_min,
            "salary_max": pref_salary_max,
            "remote_preference": remote_pref,
            "company_size": company_size,
        }

        with get_db() as session:
            repo = UserRepository(session)
            if user:
                repo.update_profile(user.id, name=name, email=email, phone=phone, linkedin_url=linkedin_url)
                repo.update_profile_data(user.id, profile_data)
                repo.update_preferences(user.id, preferences)
            else:
                new_user = repo.create(
                    name=name, email=email, phone=phone, linkedin_url=linkedin_url,
                    profile_data=profile_data, preferences=preferences,
                )
                user = new_user

            if resume_content:
                resume_repo = ResumeRepository(session)
                resume_repo.create(
                    user_id=user.id,
                    version_name=f"Upload - {uploaded_file.name}" if uploaded_file else "Manual Entry",
                    content_text=resume_content,
                    is_primary=True,
                )

        st.success("Profile saved successfully!")

    except Exception as e:
        st.error(f"Error saving profile: {e}")
