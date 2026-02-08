"""Shared test fixtures for Springboard test suite."""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Set test environment before importing app modules
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"
os.environ["LINKEDIN_EMAIL"] = "test@example.com"
os.environ["LINKEDIN_PASSWORD"] = "testpassword"

from src.database.models import Base, User, LinkedInJob, Application, Resume
from src.utils.config import Config


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config singleton between tests."""
    Config.reset()
    yield
    Config.reset()


@pytest.fixture
def engine():
    """Create a test database engine."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Session:
    """Create a test database session."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def sample_user(db_session) -> User:
    """Create a sample user for testing."""
    user = User(
        email="testuser@example.com",
        name="Test User",
        phone="555-0100",
        linkedin_url="https://linkedin.com/in/testuser",
        profile_data={
            "skills": ["Python", "JavaScript", "SQL", "React", "AWS"],
            "experience_years": 5,
            "education": [{"degree": "BS Computer Science", "institution": "Test University"}],
            "work_experience": [
                {
                    "title": "Software Engineer",
                    "company": "Tech Corp",
                    "years": 3,
                    "description": "Built web applications with Python and React",
                },
                {
                    "title": "Junior Developer",
                    "company": "Startup Inc",
                    "years": 2,
                    "description": "Full-stack development",
                },
            ],
        },
        preferences={
            "target_roles": ["Software Engineer", "Senior Software Engineer"],
            "locations": ["Remote", "San Francisco"],
            "salary_min": 120000,
            "salary_max": 180000,
            "remote_preference": "Remote",
        },
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_jobs(db_session) -> list:
    """Create sample job postings for testing."""
    jobs = [
        LinkedInJob(
            linkedin_job_id="job_001",
            title="Senior Software Engineer",
            company="Google",
            company_url="https://google.com",
            location="Remote",
            description="We are looking for a Senior Software Engineer to join our team. "
            "You will build scalable systems using Python, React, and AWS.",
            requirements="5+ years experience, Python, JavaScript, Cloud platforms",
            salary_range="$150,000 - $200,000",
            job_type="Full-time",
            experience_level="Mid-Senior level",
            job_url="https://linkedin.com/jobs/view/job_001",
            is_easy_apply=True,
            status="new",
        ),
        LinkedInJob(
            linkedin_job_id="job_002",
            title="Backend Developer",
            company="Meta",
            company_url="https://meta.com",
            location="Menlo Park, CA",
            description="Backend developer role working on distributed systems.",
            requirements="3+ years, Java or Python, distributed systems",
            salary_range="$140,000 - $190,000",
            job_type="Full-time",
            experience_level="Mid-Senior level",
            job_url="https://linkedin.com/jobs/view/job_002",
            is_easy_apply=True,
            status="new",
        ),
        LinkedInJob(
            linkedin_job_id="job_003",
            title="Data Analyst",
            company="Startup XYZ",
            location="New York, NY",
            description="Analyzing business data and creating dashboards.",
            requirements="2+ years, SQL, Excel, Tableau",
            salary_range="$80,000 - $100,000",
            job_type="Full-time",
            experience_level="Associate",
            job_url="https://linkedin.com/jobs/view/job_003",
            is_easy_apply=False,
            status="new",
        ),
    ]
    db_session.add_all(jobs)
    db_session.commit()
    return jobs


@pytest.fixture
def sample_resume(db_session, sample_user) -> Resume:
    """Create a sample resume for testing."""
    resume = Resume(
        user_id=sample_user.id,
        version_name="Base Resume v1",
        content_text=(
            "Test User\nSoftware Engineer\n\n"
            "Experience:\n"
            "- Software Engineer at Tech Corp (3 years)\n"
            "- Junior Developer at Startup Inc (2 years)\n\n"
            "Skills: Python, JavaScript, SQL, React, AWS\n\n"
            "Education: BS Computer Science, Test University"
        ),
        is_primary=True,
    )
    db_session.add(resume)
    db_session.commit()
    return resume


@pytest.fixture
def sample_application(db_session, sample_user, sample_jobs) -> Application:
    """Create a sample application for testing."""
    from datetime import datetime

    app = Application(
        job_id=sample_jobs[0].id,
        user_id=sample_user.id,
        status="submitted",
        applied_date=datetime.utcnow(),
        resume_version="Base Resume v1",
        cover_letter_text="Dear Hiring Manager, I am excited to apply...",
        notes="[2024-01-15 10:00] Applied via Easy Apply",
    )
    db_session.add(app)
    db_session.commit()
    return app
