"""Repository for LinkedIn feed post database operations."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.models import LinkedInFeedPost
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FeedPostRepository:
    """Data access layer for LinkedIn feed hiring posts."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs) -> LinkedInFeedPost:
        """Create a new feed post record."""
        post = LinkedInFeedPost(**kwargs)
        self.session.add(post)
        self.session.flush()
        logger.info("Saved feed post by %s", post.author_name)
        return post

    def get_by_id(self, post_id: int) -> Optional[LinkedInFeedPost]:
        return self.session.query(LinkedInFeedPost).filter(LinkedInFeedPost.id == post_id).first()

    def get_by_url(self, post_url: str) -> Optional[LinkedInFeedPost]:
        return self.session.query(LinkedInFeedPost).filter(LinkedInFeedPost.post_url == post_url).first()

    def get_all(self, limit: int = 100) -> List[LinkedInFeedPost]:
        return (
            self.session.query(LinkedInFeedPost)
            .order_by(LinkedInFeedPost.scraped_date.desc())
            .limit(limit)
            .all()
        )

    def get_by_status(self, status: str, limit: int = 100) -> List[LinkedInFeedPost]:
        return (
            self.session.query(LinkedInFeedPost)
            .filter(LinkedInFeedPost.status == status)
            .order_by(LinkedInFeedPost.scraped_date.desc())
            .limit(limit)
            .all()
        )

    def update_status(self, post_id: int, status: str) -> Optional[LinkedInFeedPost]:
        post = self.get_by_id(post_id)
        if post:
            post.status = status
            self.session.flush()
        return post

    def count_all(self) -> int:
        return self.session.query(func.count(LinkedInFeedPost.id)).scalar() or 0

    def count_by_status(self, status: str) -> int:
        return (
            self.session.query(func.count(LinkedInFeedPost.id))
            .filter(LinkedInFeedPost.status == status)
            .scalar() or 0
        )
