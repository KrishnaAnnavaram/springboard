"""Repository for User database operations."""

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.database.models import User
from src.utils.logger import get_logger

logger = get_logger(__name__)


class UserRepository:
    """Data access layer for user profiles."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs) -> User:
        """Create a new user."""
        user = User(**kwargs)
        self.session.add(user)
        self.session.flush()
        logger.info("Created user: %s", user.name)
        return user

    def get_by_id(self, user_id: int) -> Optional[User]:
        """Get a user by primary key."""
        return self.session.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        return self.session.query(User).filter(User.email == email).first()

    def get_default_user(self) -> Optional[User]:
        """Get the first/default user."""
        return self.session.query(User).first()

    def get_all(self) -> List[User]:
        """Get all users."""
        return self.session.query(User).all()

    def update_profile(self, user_id: int, **kwargs) -> Optional[User]:
        """Update user profile fields."""
        user = self.get_by_id(user_id)
        if user:
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            self.session.flush()
            logger.info("Updated profile for user %d", user_id)
        return user

    def update_preferences(self, user_id: int, preferences: Dict) -> Optional[User]:
        """Update user job preferences."""
        user = self.get_by_id(user_id)
        if user:
            current = user.preferences or {}
            current.update(preferences)
            user.preferences = current
            self.session.flush()
            logger.info("Updated preferences for user %d", user_id)
        return user

    def update_profile_data(self, user_id: int, profile_data: Dict) -> Optional[User]:
        """Update user profile data (skills, experience, etc.)."""
        user = self.get_by_id(user_id)
        if user:
            current = user.profile_data or {}
            current.update(profile_data)
            user.profile_data = current
            self.session.flush()
            logger.info("Updated profile data for user %d", user_id)
        return user

    def delete(self, user_id: int) -> bool:
        """Delete a user by ID."""
        user = self.get_by_id(user_id)
        if user:
            self.session.delete(user)
            self.session.flush()
            logger.info("Deleted user %d", user_id)
            return True
        return False
