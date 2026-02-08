"""Repository for Resume database operations."""

from typing import List, Optional

from sqlalchemy.orm import Session

from src.database.models import Resume
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ResumeRepository:
    """Data access layer for resume versions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs) -> Resume:
        """Create a new resume version."""
        resume = Resume(**kwargs)
        self.session.add(resume)
        self.session.flush()
        logger.info("Created resume: %s", resume.version_name)
        return resume

    def get_by_id(self, resume_id: int) -> Optional[Resume]:
        """Get a resume by primary key."""
        return self.session.query(Resume).filter(Resume.id == resume_id).first()

    def get_primary(self, user_id: int) -> Optional[Resume]:
        """Get the primary resume for a user."""
        return (
            self.session.query(Resume)
            .filter(Resume.user_id == user_id, Resume.is_primary.is_(True))
            .first()
        )

    def get_all_for_user(self, user_id: int) -> List[Resume]:
        """Get all resume versions for a user."""
        return (
            self.session.query(Resume)
            .filter(Resume.user_id == user_id)
            .order_by(Resume.created_at.desc())
            .all()
        )

    def set_primary(self, resume_id: int, user_id: int) -> Optional[Resume]:
        """Set a resume as primary, unsetting others."""
        self.session.query(Resume).filter(
            Resume.user_id == user_id
        ).update({"is_primary": False})

        resume = self.get_by_id(resume_id)
        if resume:
            resume.is_primary = True
            self.session.flush()
            logger.info("Set resume %d as primary", resume_id)
        return resume

    def update_content(self, resume_id: int, content_text: str) -> Optional[Resume]:
        """Update resume text content."""
        resume = self.get_by_id(resume_id)
        if resume:
            resume.content_text = content_text
            self.session.flush()
        return resume

    def delete(self, resume_id: int) -> bool:
        """Delete a resume by ID."""
        resume = self.get_by_id(resume_id)
        if resume:
            self.session.delete(resume)
            self.session.flush()
            logger.info("Deleted resume %d", resume_id)
            return True
        return False

    def count_for_user(self, user_id: int) -> int:
        """Count resumes for a user."""
        return (
            self.session.query(Resume)
            .filter(Resume.user_id == user_id)
            .count()
        )
