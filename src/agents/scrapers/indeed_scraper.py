"""Indeed.com job scraper agent.

Indeed is one of the largest job search engines. This scraper searches
for jobs using Selenium and extracts structured listings. Indeed does
not require login for basic searches.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlencode

from src.agents.base.base_scraper import BaseJobScraperAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


class IndeedScraperAgent(BaseJobScraperAgent):
    """Scraper for Indeed.com job search engine."""

    PLATFORM_NAME = "indeed"
    BASE_URL = "https://www.indeed.com"
    SEARCH_URL = "https://www.indeed.com/jobs"

    def __init__(self) -> None:
        super().__init__()
        self.driver: Optional[Any] = None

    def _init_driver(self) -> None:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        self.driver = webdriver.Chrome(service=Service(), options=options)
        self.driver.implicitly_wait(10)
        self.driver.set_page_load_timeout(30)
        logger.info("[indeed] Chrome WebDriver initialised")

    def login(self) -> bool:
        """Indeed searches work without login. Initialise browser."""
        if self.driver is None:
            self._init_driver()
        logger.info("[indeed] Browser ready (no login required)")
        return True

    def search_jobs(self, keywords: str, location: str, **filters: Any) -> List[Dict[str, Any]]:
        """Search Indeed for jobs.

        Args:
            keywords: Search query.
            location: Location filter.
            **filters: ``max_jobs`` (int).
        """
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException, TimeoutException
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        max_jobs = filters.get("max_jobs", 50)
        jobs: List[Dict[str, Any]] = []

        params = {"q": keywords, "l": location, "fromage": "14"}  # Last 14 days
        search_url = f"{self.SEARCH_URL}?{urlencode(params, quote_via=quote_plus)}"
        logger.info("[indeed] Searching: %s in %s", keywords, location)

        try:
            self.driver.get(search_url)
            self.rate_limit()

            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".job_seen_beacon, .resultContent, .jobsearch-ResultsList"))
                )
            except TimeoutException:
                logger.info("[indeed] No results found")
                return jobs

            start = 0
            while len(jobs) < max_jobs:
                logger.info("[indeed] Processing results (offset=%d, collected %d/%d)", start, len(jobs), max_jobs)

                cards = self.driver.find_elements(By.CSS_SELECTOR, ".job_seen_beacon, .resultContent, div[data-jk]")
                if not cards:
                    break

                for card in cards:
                    if len(jobs) >= max_jobs:
                        break
                    try:
                        job = self._extract_indeed_job(card)
                        if job and job.get("platform_job_id"):
                            if not any(j["platform_job_id"] == job["platform_job_id"] for j in jobs):
                                jobs.append(job)
                    except Exception:
                        logger.debug("[indeed] Card extraction error", exc_info=True)
                    self.rate_limit(min_seconds=0.3, max_seconds=1.0)

                # Navigate to next page
                if len(jobs) >= max_jobs:
                    break
                start += 10
                try:
                    next_link = self.driver.find_element(By.CSS_SELECTOR, "a[data-testid='pagination-page-next'], a[aria-label='Next Page']")
                    self.driver.execute_script("arguments[0].click();", next_link)
                    self.rate_limit()
                except NoSuchElementException:
                    break

        except Exception:
            logger.exception("[indeed] Error during search")

        logger.info("[indeed] Search complete: %d jobs", len(jobs))
        return jobs

    def _extract_indeed_job(self, card: Any) -> Optional[Dict[str, Any]]:
        """Extract job data from an Indeed search result card."""
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException

        # Title
        title = ""
        href = ""
        for sel in ["h2.jobTitle a", "a.jcs-JobTitle", ".jobTitle a", "h2 a"]:
            try:
                el = card.find_element(By.CSS_SELECTOR, sel)
                title = el.text.strip()
                href = el.get_attribute("href") or ""
                if title:
                    break
            except NoSuchElementException:
                continue

        if not title:
            return None

        # Company
        company = ""
        for sel in ["span[data-testid='company-name']", ".companyName", ".company"]:
            try:
                company = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if company:
                    break
            except NoSuchElementException:
                continue

        # Location
        location_text = ""
        for sel in ["div[data-testid='text-location']", ".companyLocation", ".location"]:
            try:
                location_text = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if location_text:
                    break
            except NoSuchElementException:
                continue

        # Salary
        salary = ""
        for sel in ["div[data-testid='attribute_snippet_testid'] span", ".salary-snippet-container", ".estimated-salary"]:
            try:
                salary = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if salary and "$" in salary:
                    break
            except NoSuchElementException:
                continue

        # Snippet
        snippet = ""
        for sel in [".job-snippet", ".underShelfFooter", "div[data-testid='job-snippet']"]:
            try:
                snippet = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if snippet:
                    break
            except NoSuchElementException:
                continue

        # Job ID from data attribute or URL
        job_id = ""
        try:
            job_id = card.get_attribute("data-jk") or ""
        except Exception:
            pass
        if not job_id and href:
            match = re.search(r"jk=([a-f0-9]+)", href)
            if match:
                job_id = match.group(1)

        # Detect "Apply on Indeed" vs external
        is_easy_apply = False
        try:
            apply_el = card.find_element(By.CSS_SELECTOR, ".ialbl, .iaLabel, span[class*='iaLabel']")
            if "easily apply" in apply_el.text.lower() or "apply" in apply_el.text.lower():
                is_easy_apply = True
        except NoSuchElementException:
            pass

        return {
            "platform": self.PLATFORM_NAME,
            "platform_job_id": job_id,
            "title": title,
            "company": company,
            "location": location_text,
            "job_url": href if href.startswith("http") else f"{self.BASE_URL}{href}",
            "description": snippet,
            "requirements": "",
            "salary_range": salary,
            "job_type": "",
            "experience_level": "",
            "is_easy_apply": is_easy_apply,
            "application_method": "easy_apply" if is_easy_apply else "company_site",
            "scraped_date": datetime.utcnow(),
            "status": "new",
        }

    def extract_job_details(self, job_url: str) -> Dict[str, Any]:
        """Navigate to an Indeed job page and extract full details."""
        from selenium.webdriver.common.by import By

        if self.driver is None:
            self._init_driver()

        details: Dict[str, Any] = {}
        try:
            self.driver.get(job_url)
            self.rate_limit()

            for sel in ["#jobDescriptionText", ".jobsearch-jobDescriptionText", ".jobDescription"]:
                try:
                    desc = self.driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                    if desc:
                        details["description"] = desc
                        break
                except Exception:
                    continue

            # Extract salary from detail page
            for sel in ["#salaryInfoAndJobType", ".salary-snippet-container"]:
                try:
                    sal = self.driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                    if sal:
                        details["salary_range"] = sal
                        break
                except Exception:
                    continue

        except Exception:
            logger.exception("[indeed] Failed to extract details from %s", job_url)

        return details

    def apply_to_job(self, job_id: str, resume_path: str, cover_letter: str) -> bool:
        """Indeed applications typically redirect to company sites.

        Direct Indeed Easy Apply automation is not implemented.
        """
        logger.info("[indeed] Application for %s should be completed on the job site", job_id)
        return False

    def close(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
