"""SQLAlchemy ORM models for Springboard application."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class User(Base):
    """User profile and preferences."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    profile_data = Column(JSON, nullable=True)
    preferences = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    applications = relationship("Application", back_populates="user", lazy="dynamic")
    resumes = relationship("Resume", back_populates="user", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, name='{self.name}', email='{self.email}')>"


class LinkedInJob(Base):
    """Scraped LinkedIn job posting."""

    __tablename__ = "linkedin_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    linkedin_job_id = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    company = Column(String(255), nullable=False)
    company_url = Column(String(500), nullable=True)
    location = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    requirements = Column(Text, nullable=True)
    salary_range = Column(String(255), nullable=True)
    job_type = Column(String(100), nullable=True)
    experience_level = Column(String(100), nullable=True)
    posted_date = Column(DateTime, nullable=True)
    scraped_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    job_url = Column(String(1000), nullable=False)
    is_easy_apply = Column(Boolean, default=False, nullable=False)
    match_score = Column(Float, nullable=True)
    match_reasoning = Column(Text, nullable=True)
    status = Column(String(50), default="new", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    applications = relationship("Application", back_populates="job", lazy="dynamic")

    __table_args__ = (
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_match_score", "match_score"),
        Index("ix_jobs_company", "company"),
        Index("ix_jobs_scraped_date", "scraped_date"),
    )

    def __repr__(self) -> str:
        return f"<LinkedInJob(id={self.id}, title='{self.title}', company='{self.company}', score={self.match_score})>"


class Application(Base):
    """Job application record."""

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("linkedin_jobs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    applied_date = Column(DateTime, nullable=True)
    response_date = Column(DateTime, nullable=True)
    resume_version = Column(String(255), nullable=True)
    cover_letter_text = Column(Text, nullable=True)
    linkedin_application_id = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    screenshot_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    job = relationship("LinkedInJob", back_populates="applications")
    user = relationship("User", back_populates="applications")

    __table_args__ = (
        Index("ix_applications_status", "status"),
        Index("ix_applications_applied_date", "applied_date"),
        Index("ix_applications_job_user", "job_id", "user_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Application(id={self.id}, job_id={self.job_id}, status='{self.status}')>"


class Resume(Base):
    """Resume version storage."""

    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    version_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=True)
    content_text = Column(Text, nullable=True)
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="resumes")

    def __repr__(self) -> str:
        return f"<Resume(id={self.id}, version='{self.version_name}', primary={self.is_primary})>"
