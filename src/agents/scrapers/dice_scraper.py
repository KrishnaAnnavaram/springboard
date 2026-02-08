"""Dice.com job scraper agent.

Dice is a technology-focused job board. This scraper uses Selenium to
search for jobs and extract structured data from listings.
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


class DiceScraperAgent(BaseJobScraperAgent):
    """Scraper for Dice.com technology job board."""

    PLATFORM_NAME = "dice"
    BASE_URL = "https://www.dice.com"
    SEARCH_URL = "https://www.dice.com/jobs"

    def __init__(self) -> None:
        super().__init__()
        self.driver: Optional[Any] = None

    def _init_driver(self) -> None:
        """Create a Selenium Chrome WebDriver."""
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
        logger.info("[dice] Chrome WebDriver initialised")

    # ------------------------------------------------------------------
    # BaseJobScraperAgent interface
    # ------------------------------------------------------------------

    def login(self) -> bool:
        """Dice allows searching without login. Initialise browser only.

        If credentials are set, attempt login for better results.
        """
        import os

        if self.driver is None:
            self._init_driver()

        email = os.getenv("DICE_EMAIL", "")
        password = os.getenv("DICE_PASSWORD", "")

        if not email or not password:
            logger.info("[dice] No credentials — proceeding without login")
            return True

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait

            self.driver.get(f"{self.BASE_URL}/dashboard/login")
            self.rate_limit()

            email_field = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='email'], #email"))
            )
            email_field.clear()
            email_field.send_keys(email)

            password_field = self.driver.find_element(By.CSS_SELECTOR, "input[name='password'], #password")
            password_field.clear()
            password_field.send_keys(password)

            submit = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            submit.click()

            WebDriverWait(self.driver, 15).until(EC.url_contains("/dashboard"))
            logger.info("[dice] Login successful")
            return True

        except Exception as exc:
            logger.warning("[dice] Login failed (%s) — proceeding without auth", exc)
            return True  # Dice works without login

    def search_jobs(self, keywords: str, location: str, **filters: Any) -> List[Dict[str, Any]]:
        """Search Dice for jobs.

        Args:
            keywords: Search query.
            location: Location filter.
            **filters: ``max_jobs`` (int).

        Returns:
            List of job dictionaries.
        """
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException, TimeoutException
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        max_jobs = filters.get("max_jobs", 50)
        jobs: List[Dict[str, Any]] = []

        params = {"q": keywords, "location": location, "countryCode": "US", "radius": "30", "radiusUnit": "mi", "page": "1", "pageSize": "20"}
        search_url = f"{self.SEARCH_URL}?{urlencode(params)}"

        logger.info("[dice] Searching: %s in %s", keywords, location)

        try:
            self.driver.get(search_url)
            self.rate_limit()

            # Wait for results to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-cy='search-card'], .card, .search-card"))
                )
            except TimeoutException:
                logger.info("[dice] No results found or page didn't load")
                return jobs

            page = 1
            while len(jobs) < max_jobs:
                logger.info("[dice] Processing page %d (collected %d/%d)", page, len(jobs), max_jobs)

                # Extract job cards
                card_selectors = ["[data-cy='search-card']", ".card.search-card", "dhi-search-card"]
                cards = []
                for sel in card_selectors:
                    cards = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    if cards:
                        break

                if not cards:
                    logger.info("[dice] No job cards found on page %d", page)
                    break

                for card in cards:
                    if len(jobs) >= max_jobs:
                        break
                    try:
                        job = self._extract_dice_job(card)
                        if job and job.get("platform_job_id"):
                            if not any(j["platform_job_id"] == job["platform_job_id"] for j in jobs):
                                jobs.append(job)
                    except Exception:
                        logger.debug("[dice] Failed to extract card", exc_info=True)
                    self.rate_limit(min_seconds=0.5, max_seconds=1.5)

                # Next page
                if len(jobs) >= max_jobs:
                    break
                page += 1
                try:
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, "li.pagination-next a, a[aria-label='Next']")
                    self.driver.execute_script("arguments[0].click();", next_btn)
                    self.rate_limit()
                except NoSuchElementException:
                    break

        except Exception:
            logger.exception("[dice] Error during search")

        logger.info("[dice] Search complete: %d jobs collected", len(jobs))
        return jobs

    def _extract_dice_job(self, card: Any) -> Optional[Dict[str, Any]]:
        """Extract job data from a Dice search card element."""
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException

        try:
            title_el = card.find_element(By.CSS_SELECTOR, "a.card-title-link, h5 a, [data-cy='card-title-link']")
            title = title_el.text.strip()
            href = title_el.get_attribute("href") or ""
        except NoSuchElementException:
            return None

        company = ""
        for sel in ["a[data-cy='search-result-company-name']", ".card-company a", ".company-name"]:
            try:
                company = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if company:
                    break
            except NoSuchElementException:
                continue

        location_text = ""
        for sel in ["span[data-cy='search-result-location']", ".search-result-location", ".card-location"]:
            try:
                location_text = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if location_text:
                    break
            except NoSuchElementException:
                continue

        posted = ""
        for sel in ["span[data-cy='card-posted-date']", ".posted-date"]:
            try:
                posted = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if posted:
                    break
            except NoSuchElementException:
                continue

        # Extract job ID from URL
        job_id = ""
        match = re.search(r"/job-detail/([a-f0-9-]+)", href)
        if match:
            job_id = match.group(1)
        elif href:
            job_id = href.split("/")[-1].split("?")[0]

        return {
            "platform": self.PLATFORM_NAME,
            "platform_job_id": job_id,
            "title": title,
            "company": company,
            "location": location_text,
            "job_url": href,
            "posted_date_text": posted,
            "description": "",
            "requirements": "",
            "salary_range": "",
            "job_type": "",
            "experience_level": "",
            "is_easy_apply": False,
            "application_method": "external_link",
            "scraped_date": datetime.utcnow(),
            "status": "new",
        }

    def extract_job_details(self, job_url: str) -> Dict[str, Any]:
        """Navigate to a Dice job page and extract full details."""
        from selenium.webdriver.common.by import By

        if self.driver is None:
            self._init_driver()

        details: Dict[str, Any] = {}
        try:
            self.driver.get(job_url)
            self.rate_limit()

            for sel in ["[data-testid='jobdescription-content']", "#jobdescSec", ".job-description", "#jobDescription"]:
                try:
                    desc_el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    details["description"] = desc_el.text.strip()
                    break
                except Exception:
                    continue

            # Skills / requirements
            try:
                skills_els = self.driver.find_elements(By.CSS_SELECTOR, ".chip, .skill-badge, [data-cy='skillsList'] span")
                if skills_els:
                    details["requirements"] = ", ".join(el.text.strip() for el in skills_els if el.text.strip())
            except Exception:
                pass

            # Salary
            try:
                for sel in [".compensation", "[data-cy='compensationText']"]:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    if el.text.strip():
                        details["salary_range"] = el.text.strip()
                        break
            except Exception:
                pass

        except Exception:
            logger.exception("[dice] Failed to extract details from %s", job_url)

        return details

    def apply_to_job(self, job_id: str, resume_path: str, cover_letter: str) -> bool:
        """Dice typically redirects to company sites for applications.

        Returns False since direct application is not automated here.
        """
        logger.info("[dice] Application for %s must be completed on company site", job_id)
        return False

    def close(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
