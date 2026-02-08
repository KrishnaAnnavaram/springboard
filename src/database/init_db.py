"""Database initialization script for Springboard application."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db, init_db
from src.database.models import User
from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def create_default_user() -> None:
    """Create the default user from config if not exists."""
    config = Config()
    defaults = config.user_defaults

    with get_db() as session:
        existing = session.query(User).first()
        if existing:
            logger.info("Default user already exists: %s", existing.name)
            return

        user = User(
            email=defaults.get("default_email", "user@example.com") or "user@example.com",
            name=defaults.get("default_name", "Job Seeker"),
            phone=defaults.get("default_phone", ""),
            linkedin_url=defaults.get("default_linkedin_url", ""),
            profile_data={},
            preferences={
                "target_roles": config.search_titles,
                "locations": config.search_locations,
                "remote_preference": config.job_search.get("remote_preference", "Remote"),
            },
        )
        session.add(user)
        logger.info("Created default user: %s", user.name)


def initialize() -> None:
    """Run full database initialization."""
    logger.info("Initializing database...")

    try:
        init_db()
        logger.info("Database tables created successfully.")

        create_default_user()
        logger.info("Database initialization complete.")

    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        raise


if __name__ == "__main__":
    initialize()
