"""Abstract base class for all job platform scraper agents.

Every platform scraper (LinkedIn, Dice, Indeed, Monster, Handshake, etc.)
must inherit from this base and implement the abstract methods. The base
provides shared utilities for rate limiting, retry logic, and database
persistence.
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.database.connection import get_db
from src.database.repositories.job_repository import JobRepository
from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BaseJobScraperAgent(ABC):
    """Abstract base class all job platform scrapers must implement.

    Subclasses provide platform-specific logic for login, search,
    detail extraction, and application submission. This base handles
    rate limiting, exponential-backoff retry, and database persistence.

    Class attributes:
        PLATFORM_NAME: Unique identifier for the platform (e.g. ``"linkedin"``).
    """

    PLATFORM_NAME: str = "unknown"

    def __init__(self) -> None:
        self.config = Config()
        automation = self.config.automation
        self._min_delay: float = float(automation.get("min_delay_between_actions", 3))
        self._max_delay: float = float(automation.get("max_delay_between_actions", 8))
        self._retry_attempts: int = int(automation.get("retry_attempts", 3))
        self._retry_backoff: float = float(automation.get("retry_backoff_factor", 2))
        logger.info("%s scraper initialised", self.PLATFORM_NAME.title())

    # ------------------------------------------------------------------
    # Abstract interface — every scraper must implement these
    # ------------------------------------------------------------------

    @abstractmethod
    def login(self) -> bool:
        """Authenticate to the platform.

        Returns:
            ``True`` if login succeeded.
        """

    @abstractmethod
    def search_jobs(
        self,
        keywords: str,
        location: str,
        **filters: Any,
    ) -> List[Dict[str, Any]]:
        """Search for jobs on the platform.

        Args:
            keywords: Search query string.
            location: Geographic filter.
            **filters: Platform-specific filters (e.g. ``easy_apply=True``).

        Returns:
            List of job dictionaries with at minimum ``platform_job_id``,
            ``title``, ``company``, ``location``, ``job_url``, and
            ``platform``.
        """

    @abstractmethod
    def extract_job_details(self, job_url: str) -> Dict[str, Any]:
        """Extract full details from a single job posting page.

        Args:
            job_url: URL of the job posting.

        Returns:
            Dictionary containing all available fields (description,
            requirements, salary, etc.).
        """

    @abstractmethod
    def apply_to_job(
        self,
        job_id: str,
        resume_path: str,
        cover_letter: str,
    ) -> bool:
        """Submit an application for a job.

        Args:
            job_id: Platform-specific job identifier.
            resume_path: Path to the resume file.
            cover_letter: Cover letter text.

        Returns:
            ``True`` if the application was submitted successfully.
        """

    def close(self) -> None:
        """Release any resources (browser sessions, connections, etc.).

        The default implementation is a no-op. Subclasses that manage
        external resources should override this.
        """

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def rate_limit(self, min_seconds: Optional[float] = None, max_seconds: Optional[float] = None) -> None:
        """Sleep for a random duration to respect platform rate limits.

        Args:
            min_seconds: Override minimum delay (defaults to config value).
            max_seconds: Override maximum delay (defaults to config value).
        """
        lo = min_seconds if min_seconds is not None else self._min_delay
        hi = max_seconds if max_seconds is not None else self._max_delay
        delay = random.uniform(lo, hi)
        logger.debug("[%s] Rate-limit pause: %.2f s", self.PLATFORM_NAME, delay)
        time.sleep(delay)

    def retry(self, func: Any, *args: Any, attempts: Optional[int] = None, **kwargs: Any) -> Any:
        """Execute *func* with exponential-backoff retry.

        Args:
            func: Callable to invoke.
            *args: Positional arguments forwarded to *func*.
            attempts: Override for the default retry count.
            **kwargs: Keyword arguments forwarded to *func*.

        Returns:
            The return value of *func* on success.

        Raises:
            Exception: The last exception if all attempts fail.
        """
        max_attempts = attempts if attempts is not None else self._retry_attempts
        last_exc: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts:
                    backoff = self._retry_backoff ** attempt
                    logger.warning(
                        "[%s] Attempt %d/%d for %s failed (%s). Retrying in %.1f s",
                        self.PLATFORM_NAME, attempt, max_attempts,
                        getattr(func, "__name__", str(func)), exc, backoff,
                    )
                    time.sleep(backoff)
                else:
                    logger.error(
                        "[%s] All %d attempts for %s exhausted: %s",
                        self.PLATFORM_NAME, max_attempts,
                        getattr(func, "__name__", str(func)), exc,
                    )
        raise last_exc  # type: ignore[misc]

    def save_to_database(self, jobs: List[Dict[str, Any]]) -> int:
        """Persist scraped jobs to the database.

        Duplicate jobs (matching ``platform`` + ``platform_job_id``) are
        silently skipped.

        Args:
            jobs: List of job dictionaries. Each must include
                ``platform_job_id`` and ``platform``.

        Returns:
            Number of newly created records.
        """
        if not jobs:
            logger.info("[%s] No jobs to save", self.PLATFORM_NAME)
            return 0

        saved = 0
        try:
            with get_db() as session:
                repo = JobRepository(session)
                for job_data in jobs:
                    pid = job_data.get("platform_job_id") or job_data.get("linkedin_job_id", "")
                    if not pid:
                        continue
                    existing = repo.get_by_platform_job_id(pid, self.PLATFORM_NAME)
                    if existing:
                        continue
                    repo.create(
                        platform_job_id=pid,
                        platform=self.PLATFORM_NAME,
                        title=job_data.get("title", ""),
                        company=job_data.get("company", ""),
                        location=job_data.get("location", ""),
                        description=job_data.get("description", ""),
                        requirements=job_data.get("requirements", ""),
                        salary_range=job_data.get("salary_range", ""),
                        job_type=job_data.get("job_type", ""),
                        experience_level=job_data.get("experience_level", ""),
                        posted_date=job_data.get("posted_date"),
                        job_url=job_data.get("job_url", ""),
                        is_easy_apply=job_data.get("is_easy_apply", False),
                        application_method=job_data.get("application_method", "external_link"),
                        platform_metadata=job_data.get("platform_metadata"),
                        status="new",
                    )
                    saved += 1
            logger.info("[%s] Saved %d new jobs (of %d scraped)", self.PLATFORM_NAME, saved, len(jobs))
        except Exception:
            logger.exception("[%s] Database error saving jobs", self.PLATFORM_NAME)
        return saved

    def run(
        self,
        keywords: Optional[List[str]] = None,
        location: Optional[str] = None,
        max_jobs: int = 50,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Execute the full scraping pipeline for this platform.

        Args:
            keywords: List of search terms. Defaults to config titles.
            location: Location filter. Defaults to first config location.
            max_jobs: Maximum jobs to collect.
            **kwargs: Extra platform-specific options.

        Returns:
            List of all scraped job dictionaries.
        """
        titles = keywords or self.config.search_titles or ["Software Engineer"]
        loc = location or (self.config.search_locations[0] if self.config.search_locations else "United States")

        all_jobs: List[Dict[str, Any]] = []
        try:
            logged_in = self.login()
            if not logged_in:
                logger.error("[%s] Login failed — aborting", self.PLATFORM_NAME)
                return all_jobs

            for title in titles:
                if len(all_jobs) >= max_jobs:
                    break
                try:
                    jobs = self.search_jobs(title, loc, max_jobs=max_jobs - len(all_jobs), **kwargs)
                    all_jobs.extend(jobs)
                    logger.info("[%s] Collected %d jobs for '%s' in '%s'", self.PLATFORM_NAME, len(jobs), title, loc)
                except Exception:
                    logger.exception("[%s] Search failed for '%s' in '%s'", self.PLATFORM_NAME, title, loc)
                self.rate_limit()

            self.save_to_database(all_jobs)
        finally:
            self.close()

        logger.info("[%s] Run complete — %d total jobs", self.PLATFORM_NAME, len(all_jobs))
        return all_jobs

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "BaseJobScraperAgent":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
