"""Repository for Application database operations."""

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.models import Application, LinkedInJob
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ApplicationRepository:
    """Data access layer for job applications."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs) -> Application:
        """Create a new application record."""
        application = Application(**kwargs)
        self.session.add(application)
        self.session.flush()
        logger.info("Created application for job_id=%d", application.job_id)
        return application

    def get_by_id(self, app_id: int) -> Optional[Application]:
        """Get an application by primary key."""
        return self.session.query(Application).filter(Application.id == app_id).first()

    def get_by_job_id(self, job_id: int) -> Optional[Application]:
        """Get application for a specific job."""
        return (
            self.session.query(Application)
            .filter(Application.job_id == job_id)
            .first()
        )

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Application]:
        """Get all applications with pagination."""
        return (
            self.session.query(Application)
            .order_by(Application.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_by_status(self, status: str, limit: int = 100) -> List[Application]:
        """Get applications filtered by status."""
        return (
            self.session.query(Application)
            .filter(Application.status == status)
            .order_by(Application.created_at.desc())
            .limit(limit)
            .all()
        )

    def update_status(self, app_id: int, status: str) -> Optional[Application]:
        """Update application status."""
        app = self.get_by_id(app_id)
        if app:
            app.status = status
            if status == "submitted" and not app.applied_date:
                app.applied_date = datetime.utcnow()
            if status in ("interview", "rejected", "offer") and not app.response_date:
                app.response_date = datetime.utcnow()
            self.session.flush()
            logger.info("Updated application %d status to %s", app_id, status)
        return app

    def add_note(self, app_id: int, note: str) -> Optional[Application]:
        """Append a note to the application."""
        app = self.get_by_id(app_id)
        if app:
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
            new_note = f"[{timestamp}] {note}"
            if app.notes:
                app.notes = f"{app.notes}\n{new_note}"
            else:
                app.notes = new_note
            self.session.flush()
        return app

    def count_all(self) -> int:
        """Count total applications."""
        return self.session.query(func.count(Application.id)).scalar() or 0

    def count_today(self) -> int:
        """Count applications submitted today."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            self.session.query(func.count(Application.id))
            .filter(Application.applied_date >= today)
            .filter(Application.status != "pending")
            .scalar() or 0
        )

    def count_by_status(self, status: str) -> int:
        """Count applications with a specific status."""
        return (
            self.session.query(func.count(Application.id))
            .filter(Application.status == status)
            .scalar() or 0
        )

    def get_response_rate(self) -> float:
        """Calculate the response rate (responded / total submitted)."""
        total = (
            self.session.query(func.count(Application.id))
            .filter(Application.status != "pending")
            .scalar() or 0
        )
        if total == 0:
            return 0.0

        responded = (
            self.session.query(func.count(Application.id))
            .filter(Application.status.in_(["interview", "offer", "rejected"]))
            .scalar() or 0
        )
        return round((responded / total) * 100, 1)

    def get_daily_counts(self, days: int = 30) -> List[Dict]:
        """Get application counts per day for the last N days."""
        start_date = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - __import__("datetime").timedelta(days=days)

        results = (
            self.session.query(
                func.date(Application.applied_date).label("date"),
                func.count(Application.id).label("count"),
            )
            .filter(Application.applied_date >= start_date)
            .filter(Application.applied_date.isnot(None))
            .group_by(func.date(Application.applied_date))
            .order_by(func.date(Application.applied_date))
            .all()
        )

        return [{"date": str(r.date), "count": r.count} for r in results]

    def get_status_breakdown(self) -> Dict[str, int]:
        """Get count of applications per status."""
        results = (
            self.session.query(
                Application.status,
                func.count(Application.id).label("count"),
            )
            .group_by(Application.status)
            .all()
        )
        return {r.status: r.count for r in results}

    def get_with_job_details(self, limit: int = 100, offset: int = 0) -> List[Application]:
        """Get applications with job details eagerly loaded."""
        return (
            self.session.query(Application)
            .join(LinkedInJob)
            .order_by(Application.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
