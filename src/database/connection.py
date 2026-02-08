"""Database connection management for Springboard application."""

from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from src.database.models import Base
from src.utils.config import Config

_engine: Optional[Engine] = None
_session_factory: Optional[scoped_session] = None


def get_engine() -> Engine:
    """Get or create the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        config = Config()
        url = config.database_url
        db_config = config.database_config

        connect_args = {}
        engine_kwargs = {
            "echo": db_config.get("echo", False),
        }

        if url.startswith("sqlite"):
            # SQLite uses StaticPool/NullPool — pool_size is not supported.
            connect_args["check_same_thread"] = False
        else:
            engine_kwargs["pool_size"] = db_config.get("pool_size", 5)
            engine_kwargs["max_overflow"] = db_config.get("max_overflow", 10)
            engine_kwargs["pool_timeout"] = db_config.get("pool_timeout", 30)

        _engine = create_engine(url, connect_args=connect_args, **engine_kwargs)
    return _engine


def get_session_factory() -> scoped_session:
    """Get or create the scoped session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        _session_factory = scoped_session(factory)
    return _session_factory


def get_session() -> Session:
    """Get a new database session."""
    factory = get_session_factory()
    return factory()


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager for database sessions with automatic cleanup.

    Usage:
        with get_db() as session:
            session.query(User).all()
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all database tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)


def reset_engine() -> None:
    """Reset engine and session factory (for testing)."""
    global _engine, _session_factory
    if _session_factory:
        _session_factory.remove()
    if _engine:
        _engine.dispose()
    _engine = None
    _session_factory = None
