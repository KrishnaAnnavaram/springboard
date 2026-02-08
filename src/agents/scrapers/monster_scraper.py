"""Monster.com job scraper agent.

Monster is a general-purpose job board. This scraper uses Selenium
to search and extract job listings.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from src.agents.base.base_scraper import BaseJobScraperAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MonsterScraperAgent(BaseJobScraperAgent):
    """Scraper for Monster.com job board."""

    PLATFORM_NAME = "monster"
    BASE_URL = "https://www.monster.com"
    SEARCH_URL = "https://www.monster.com/jobs/search"

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
        logger.info("[monster] Chrome WebDriver initialised")

    def login(self) -> bool:
        """Monster searches work without login. Initialise browser.

        If credentials are set, attempt login.
        """
        import os

        if self.driver is None:
            self._init_driver()

        email = os.getenv("MONSTER_EMAIL", "")
        password = os.getenv("MONSTER_PASSWORD", "")

        if not email or not password:
            logger.info("[monster] No credentials — searching without login")
            return True

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait

            self.driver.get(f"{self.BASE_URL}/profile/sign-in")
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

            self.rate_limit()
            logger.info("[monster] Login attempted")
            return True

        except Exception as exc:
            logger.warning("[monster] Login failed (%s) — proceeding without auth", exc)
            return True

    def search_jobs(self, keywords: str, location: str, **filters: Any) -> List[Dict[str, Any]]:
        """Search Monster for jobs."""
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException, TimeoutException
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        max_jobs = filters.get("max_jobs", 50)
        jobs: List[Dict[str, Any]] = []

        params = {"q": keywords, "where": location}
        search_url = f"{self.SEARCH_URL}?{urlencode(params)}"
        logger.info("[monster] Searching: %s in %s", keywords, location)

        try:
            self.driver.get(search_url)
            self.rate_limit()

            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='svx-job-card'], .job-cardstyle, .results-card"))
                )
            except TimeoutException:
                logger.info("[monster] No results found")
                return jobs

            page = 1
            while len(jobs) < max_jobs:
                logger.info("[monster] Processing page %d (collected %d/%d)", page, len(jobs), max_jobs)

                cards = self.driver.find_elements(By.CSS_SELECTOR, "[data-testid='svx-job-card'], .job-cardstyle, article.job-card")
                if not cards:
                    break

                for card in cards:
                    if len(jobs) >= max_jobs:
                        break
                    try:
                        job = self._extract_monster_job(card)
                        if job and job.get("platform_job_id"):
                            if not any(j["platform_job_id"] == job["platform_job_id"] for j in jobs):
                                jobs.append(job)
                    except Exception:
                        logger.debug("[monster] Card extraction error", exc_info=True)
                    self.rate_limit(min_seconds=0.3, max_seconds=1.0)

                if len(jobs) >= max_jobs:
                    break
                page += 1
                try:
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, "a[aria-label='Next'], button[aria-label='Next']")
                    self.driver.execute_script("arguments[0].click();", next_btn)
                    self.rate_limit()
                except NoSuchElementException:
                    break

        except Exception:
            logger.exception("[monster] Error during search")

        logger.info("[monster] Search complete: %d jobs", len(jobs))
        return jobs

    def _extract_monster_job(self, card: Any) -> Optional[Dict[str, Any]]:
        """Extract job data from a Monster search card."""
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException

        title = ""
        href = ""
        for sel in ["a[data-testid='jobTitle']", "h2 a", ".job-cardstyle__title a", ".job-card-title a"]:
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

        company = ""
        for sel in ["[data-testid='company']", ".company span", ".job-cardstyle__company"]:
            try:
                company = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if company:
                    break
            except NoSuchElementException:
                continue

        location_text = ""
        for sel in ["[data-testid='jobLocation']", ".location span", ".job-cardstyle__location"]:
            try:
                location_text = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if location_text:
                    break
            except NoSuchElementException:
                continue

        salary = ""
        for sel in ["[data-testid='svx_jobCard-salary']", ".salary"]:
            try:
                salary = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if salary:
                    break
            except NoSuchElementException:
                continue

        # Extract job ID from URL
        job_id = ""
        if href:
            match = re.search(r"/job/([^/?]+)", href)
            if match:
                job_id = match.group(1)
            else:
                job_id = href.split("/")[-1].split("?")[0]

        return {
            "platform": self.PLATFORM_NAME,
            "platform_job_id": job_id,
            "title": title,
            "company": company,
            "location": location_text,
            "job_url": href,
            "salary_range": salary,
            "description": "",
            "requirements": "",
            "job_type": "",
            "experience_level": "",
            "is_easy_apply": False,
            "application_method": "external_link",
            "scraped_date": datetime.utcnow(),
            "status": "new",
        }

    def extract_job_details(self, job_url: str) -> Dict[str, Any]:
        """Extract full details from a Monster job page."""
        from selenium.webdriver.common.by import By

        if self.driver is None:
            self._init_driver()

        details: Dict[str, Any] = {}
        try:
            self.driver.get(job_url)
            self.rate_limit()

            for sel in ["[data-testid='svx-jobview-description']", "#JobDescription", ".job-description"]:
                try:
                    desc = self.driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                    if desc:
                        details["description"] = desc
                        break
                except Exception:
                    continue

        except Exception:
            logger.exception("[monster] Failed to extract details from %s", job_url)

        return details

    def apply_to_job(self, job_id: str, resume_path: str, cover_letter: str) -> bool:
        logger.info("[monster] Application for %s should be completed on site", job_id)
        return False

    def close(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
