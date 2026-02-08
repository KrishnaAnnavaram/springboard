"""Glassdoor job scraper placeholder.

This is a placeholder for future implementation. Glassdoor requires
authentication and has anti-scraping measures.
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.agents.base.base_scraper import BaseJobScraperAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GlassdoorScraperAgent(BaseJobScraperAgent):
    """Placeholder scraper for Glassdoor."""

    PLATFORM_NAME = "glassdoor"

    def login(self) -> bool:
        raise NotImplementedError("Glassdoor scraper is not yet implemented")

    def search_jobs(self, keywords: str, location: str, **filters: Any) -> List[Dict[str, Any]]:
        raise NotImplementedError("Glassdoor scraper is not yet implemented")

    def extract_job_details(self, job_url: str) -> Dict[str, Any]:
        raise NotImplementedError("Glassdoor scraper is not yet implemented")

    def apply_to_job(self, job_id: str, resume_path: str, cover_letter: str) -> bool:
        raise NotImplementedError("Glassdoor scraper is not yet implemented")
