"""LinkedIn scraper that conforms to the BaseJobScraperAgent interface.

Wraps the existing ``LinkedInScraperAgent`` to fit the multi-platform
architecture.  The original class remains available for backward
compatibility; this adapter delegates to it for all Selenium work.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from src.agents.base.base_scraper import BaseJobScraperAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LinkedInPlatformScraper(BaseJobScraperAgent):
    """Multi-platform adapter for the LinkedIn scraper.

    Delegates to ``LinkedInScraperAgent`` for the actual Selenium
    interactions, while providing the ``BaseJobScraperAgent`` interface
    expected by the orchestrator.
    """

    PLATFORM_NAME = "linkedin"

    def __init__(self) -> None:
        super().__init__()
        from src.agents.linkedin_scraper import LinkedInScraperAgent
        self._inner = LinkedInScraperAgent()

    # ------------------------------------------------------------------
    # BaseJobScraperAgent interface
    # ------------------------------------------------------------------

    def login(self) -> bool:
        """Authenticate to LinkedIn."""
        logger.info("[linkedin] Initialising browser and logging in")
        self._inner._init_driver()
        return self._inner.login()

    def search_jobs(self, keywords: str, location: str, **filters: Any) -> List[Dict[str, Any]]:
        """Search LinkedIn for jobs.

        Args:
            keywords: Search query.
            location: Location filter.
            **filters: ``easy_apply`` (bool), ``max_jobs`` (int).

        Returns:
            List of job dicts.
        """
        easy_apply = filters.get("easy_apply", self._inner.config.easy_apply_only)
        jobs = self._inner.search_jobs(keywords, location, easy_apply=easy_apply)
        # Normalise keys for the generic model
        for j in jobs:
            j.setdefault("platform", self.PLATFORM_NAME)
            j.setdefault("platform_job_id", j.get("linkedin_job_id", ""))
            j.setdefault("application_method", "easy_apply" if j.get("is_easy_apply") else "external_link")
        return jobs

    def extract_job_details(self, job_url: str) -> Dict[str, Any]:
        """Extract full details from a LinkedIn job page.

        This is a simplified implementation that navigates to the URL
        and scrapes the detail pane.
        """
        if self._inner.driver is None:
            self._inner._init_driver()
            self._inner.login()

        try:
            self._inner.driver.get(job_url)
            self._inner._rate_limit()
            return {
                "description": self._inner._extract_description(),
                "requirements": self._inner._extract_requirements(),
                "salary_range": self._inner._extract_salary(),
                "job_type": self._inner._extract_job_type(),
                "experience_level": self._inner._extract_experience_level(),
            }
        except Exception:
            logger.exception("[linkedin] Failed to extract details from %s", job_url)
            return {}

    def apply_to_job(self, job_id: str, resume_path: str, cover_letter: str) -> bool:
        """Submit an Easy Apply application on LinkedIn.

        Delegates to the ``LinkedInApplicationAgent`` for the actual
        form submission.
        """
        try:
            from src.agents.linkedin_applier import LinkedInApplicationAgent
            with LinkedInApplicationAgent() as applier:
                result = applier.apply_to_single_job(job_id, resume_path, cover_letter)
                return result.get("success", False) if isinstance(result, dict) else bool(result)
        except Exception:
            logger.exception("[linkedin] Application submission failed for job %s", job_id)
            return False

    def close(self) -> None:
        """Shut down the Selenium browser."""
        self._inner._quit_driver()

    def test_login(self) -> Dict[str, Any]:
        """Test LinkedIn authentication and return status details.

        Returns:
            Dict with ``success``, ``message``, and optional ``error``.
        """
        try:
            self._inner._init_driver()
            success = self._inner.login()
            return {
                "success": success,
                "message": "Connected to LinkedIn" if success else "Login failed",
                "page_title": self._inner.driver.title if self._inner.driver else "N/A",
            }
        except Exception as exc:
            return {"success": False, "message": str(exc), "error": str(exc)}
        finally:
            self._inner._quit_driver()
