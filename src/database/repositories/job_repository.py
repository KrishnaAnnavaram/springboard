"""Repository for job database operations (multi-platform)."""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.models import LinkedInJob, LinkedInFeedPost
from src.utils.logger import get_logger

logger = get_logger(__name__)


class JobRepository:
    """Data access layer for job postings from all platforms."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs) -> LinkedInJob:
        """Create a new job record.

        For multi-platform support, if ``platform_job_id`` is provided
        but ``linkedin_job_id`` is not, the latter is set automatically
        using the pattern ``{platform}_{platform_job_id}``.
        """
        # Ensure linkedin_job_id is set for backward compatibility
        if "linkedin_job_id" not in kwargs or not kwargs["linkedin_job_id"]:
            platform = kwargs.get("platform", "linkedin")
            pid = kwargs.get("platform_job_id", "")
            if pid:
                kwargs["linkedin_job_id"] = f"{platform}_{pid}"
                kwargs.setdefault("platform_job_id", pid)
            else:
                kwargs.setdefault("linkedin_job_id", kwargs.get("job_url", str(datetime.utcnow().timestamp())))
        kwargs.setdefault("platform", "linkedin")
        kwargs.setdefault("job_url", "")
        job = LinkedInJob(**kwargs)
        self.session.add(job)
        self.session.flush()
        logger.info("Created job: %s at %s [%s]", job.title, job.company, job.platform)
        return job

    def get_by_id(self, job_id: int) -> Optional[LinkedInJob]:
        """Get a job by its primary key."""
        return self.session.query(LinkedInJob).filter(LinkedInJob.id == job_id).first()

    def get_by_linkedin_id(self, linkedin_job_id: str) -> Optional[LinkedInJob]:
        """Get a job by its LinkedIn job ID (backward compatible)."""
        return (
            self.session.query(LinkedInJob)
            .filter(LinkedInJob.linkedin_job_id == linkedin_job_id)
            .first()
        )

    def get_by_platform_job_id(self, platform_job_id: str, platform: str = "linkedin") -> Optional[LinkedInJob]:
        """Get a job by platform-specific job ID."""
        composite_id = f"{platform}_{platform_job_id}"
        return (
            self.session.query(LinkedInJob)
            .filter(
                (LinkedInJob.linkedin_job_id == composite_id)
                | (LinkedInJob.platform_job_id == platform_job_id)
            )
            .first()
        )

    def filter_by_platform(self, platform: str, limit: int = 100) -> List[LinkedInJob]:
        """Get all jobs from a specific platform."""
        return (
            self.session.query(LinkedInJob)
            .filter(LinkedInJob.platform == platform)
            .order_by(LinkedInJob.scraped_date.desc())
            .limit(limit)
            .all()
        )

    def get_all(self, limit: int = 100, offset: int = 0) -> List[LinkedInJob]:
        """Get all jobs with pagination."""
        return (
            self.session.query(LinkedInJob)
            .order_by(LinkedInJob.scraped_date.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_by_status(self, status: str, limit: int = 100) -> List[LinkedInJob]:
        """Get jobs filtered by status."""
        return (
            self.session.query(LinkedInJob)
            .filter(LinkedInJob.status == status)
            .order_by(LinkedInJob.scraped_date.desc())
            .limit(limit)
            .all()
        )

    def get_matched_jobs(self, min_score: float = 60.0, limit: int = 100) -> List[LinkedInJob]:
        """Get jobs with match score above threshold."""
        return (
            self.session.query(LinkedInJob)
            .filter(LinkedInJob.match_score >= min_score)
            .order_by(LinkedInJob.match_score.desc())
            .limit(limit)
            .all()
        )

    def update_match_score(
        self, job_id: int, score: float, reasoning: str
    ) -> Optional[LinkedInJob]:
        """Update a job's match score and reasoning."""
        job = self.get_by_id(job_id)
        if job:
            job.match_score = score
            job.match_reasoning = reasoning
            job.status = "matched"
            self.session.flush()
            logger.info("Updated match score for job %d: %.1f", job_id, score)
        return job

    def update_status(self, job_id: int, status: str) -> Optional[LinkedInJob]:
        """Update job status."""
        job = self.get_by_id(job_id)
        if job:
            job.status = status
            self.session.flush()
        return job

    def count_all(self) -> int:
        """Count total jobs."""
        return self.session.query(func.count(LinkedInJob.id)).scalar() or 0

    def count_today(self) -> int:
        """Count jobs scraped today."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            self.session.query(func.count(LinkedInJob.id))
            .filter(LinkedInJob.scraped_date >= today)
            .scalar() or 0
        )

    def count_by_status(self, status: str) -> int:
        """Count jobs with a specific status."""
        return (
            self.session.query(func.count(LinkedInJob.id))
            .filter(LinkedInJob.status == status)
            .scalar() or 0
        )

    def search(
        self,
        query: str,
        status: Optional[str] = None,
        min_score: Optional[float] = None,
        location: Optional[str] = None,
        limit: int = 50,
    ) -> List[LinkedInJob]:
        """Search jobs by keyword with optional filters."""
        q = self.session.query(LinkedInJob)

        if query:
            search_term = f"%{query}%"
            q = q.filter(
                (LinkedInJob.title.ilike(search_term))
                | (LinkedInJob.company.ilike(search_term))
                | (LinkedInJob.description.ilike(search_term))
            )

        if status:
            q = q.filter(LinkedInJob.status == status)

        if min_score is not None:
            q = q.filter(LinkedInJob.match_score >= min_score)

        if location:
            q = q.filter(LinkedInJob.location.ilike(f"%{location}%"))

        return q.order_by(LinkedInJob.scraped_date.desc()).limit(limit).all()

    def get_unmatched_jobs(self, limit: int = 50) -> List[LinkedInJob]:
        """Get jobs that haven't been matched yet."""
        return (
            self.session.query(LinkedInJob)
            .filter(LinkedInJob.match_score.is_(None))
            .filter(LinkedInJob.status == "new")
            .order_by(LinkedInJob.scraped_date.desc())
            .limit(limit)
            .all()
        )

    def get_jobs_by_date_range(
        self, start_date: datetime, end_date: datetime
    ) -> List[LinkedInJob]:
        """Get jobs scraped within a date range."""
        return (
            self.session.query(LinkedInJob)
            .filter(LinkedInJob.scraped_date.between(start_date, end_date))
            .order_by(LinkedInJob.scraped_date.desc())
            .all()
        )

    def get_top_companies(self, limit: int = 20) -> List[tuple]:
        """Get companies with the most job postings."""
        return (
            self.session.query(
                LinkedInJob.company,
                func.count(LinkedInJob.id).label("count"),
            )
            .group_by(LinkedInJob.company)
            .order_by(func.count(LinkedInJob.id).desc())
            .limit(limit)
            .all()
        )
