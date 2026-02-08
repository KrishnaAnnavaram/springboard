"""Handshake job scraper agent.

Handshake (joinhandshake.com) is a career platform focused on college
students and recent graduates. It requires university SSO credentials
for full access.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from src.agents.base.base_scraper import BaseJobScraperAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HandshakeScraperAgent(BaseJobScraperAgent):
    """Scraper for Handshake early-career job platform."""

    PLATFORM_NAME = "handshake"
    BASE_URL = "https://app.joinhandshake.com"

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

        self.driver = webdriver.Chrome(service=Service(), options=options)
        self.driver.implicitly_wait(10)
        self.driver.set_page_load_timeout(30)
        logger.info("[handshake] Chrome WebDriver initialised")

    def login(self) -> bool:
        """Authenticate to Handshake.

        Handshake requires university SSO. This attempts email/password
        login which may redirect to an SSO page.
        """
        if self.driver is None:
            self._init_driver()

        email = os.getenv("HANDSHAKE_EMAIL", "")
        password = os.getenv("HANDSHAKE_PASSWORD", "")

        if not email or not password:
            logger.warning("[handshake] No credentials configured — login required for Handshake")
            return False

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait

            self.driver.get(f"{self.BASE_URL}/login")
            self.rate_limit()

            email_field = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='email'], #email-address-input"))
            )
            email_field.clear()
            email_field.send_keys(email)

            # Handshake may show a "Next" button before password
            try:
                next_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], .sign-in-button")
                next_btn.click()
                self.rate_limit()
            except Exception:
                pass

            # Check if redirected to university SSO
            current_url = self.driver.current_url
            if "sso" in current_url.lower() or "saml" in current_url.lower():
                logger.warning("[handshake] Redirected to university SSO — manual auth needed")
                return False

            # Try password entry
            try:
                pw_field = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
                )
                pw_field.clear()
                pw_field.send_keys(password)

                submit = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                submit.click()
                self.rate_limit()
            except Exception:
                logger.warning("[handshake] Could not find password field")
                return False

            # Verify login
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-hook='user-menu'], .user-menu"))
                )
                logger.info("[handshake] Login successful")
                return True
            except Exception:
                logger.warning("[handshake] Post-login verification failed")
                return False

        except Exception as exc:
            logger.exception("[handshake] Login failed: %s", exc)
            return False

    def search_jobs(self, keywords: str, location: str, **filters: Any) -> List[Dict[str, Any]]:
        """Search Handshake for jobs."""
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException, TimeoutException
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        max_jobs = filters.get("max_jobs", 50)
        jobs: List[Dict[str, Any]] = []

        search_url = f"{self.BASE_URL}/postings?page=1&per_page=25&sort_direction=desc&sort_column=default&query={keywords}"
        logger.info("[handshake] Searching: %s", keywords)

        try:
            self.driver.get(search_url)
            self.rate_limit()

            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-hook='jobs-card'], .style__card___"))
                )
            except TimeoutException:
                logger.info("[handshake] No results or page didn't load")
                return jobs

            cards = self.driver.find_elements(By.CSS_SELECTOR, "[data-hook='jobs-card'], .style__card___, a[data-hook]")
            for card in cards[:max_jobs]:
                try:
                    job = self._extract_handshake_job(card)
                    if job and job.get("platform_job_id"):
                        jobs.append(job)
                except Exception:
                    logger.debug("[handshake] Card extraction error", exc_info=True)
                self.rate_limit(min_seconds=0.3, max_seconds=1.0)

        except Exception:
            logger.exception("[handshake] Error during search")

        logger.info("[handshake] Search complete: %d jobs", len(jobs))
        return jobs

    def _extract_handshake_job(self, card: Any) -> Optional[Dict[str, Any]]:
        """Extract job data from a Handshake card."""
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException

        title = ""
        href = ""
        for sel in ["[data-hook='jobs-card-title'] a", "a.posting-title", "h3 a"]:
            try:
                el = card.find_element(By.CSS_SELECTOR, sel)
                title = el.text.strip()
                href = el.get_attribute("href") or ""
                if title:
                    break
            except NoSuchElementException:
                continue

        if not title:
            try:
                title = card.text.split("\n")[0].strip()
                href = card.get_attribute("href") or ""
            except Exception:
                return None

        company = ""
        for sel in ["[data-hook='employer-name']", ".employer-name", "span.company"]:
            try:
                company = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if company:
                    break
            except NoSuchElementException:
                continue

        location_text = ""
        for sel in ["[data-hook='jobs-card-location']", ".location"]:
            try:
                location_text = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                if location_text:
                    break
            except NoSuchElementException:
                continue

        job_id = ""
        if href:
            match = re.search(r"/postings/(\d+)", href)
            if match:
                job_id = match.group(1)

        return {
            "platform": self.PLATFORM_NAME,
            "platform_job_id": job_id,
            "title": title,
            "company": company,
            "location": location_text,
            "job_url": href,
            "description": "",
            "requirements": "",
            "salary_range": "",
            "job_type": "",
            "experience_level": "Entry level",
            "is_easy_apply": False,
            "application_method": "external_link",
            "scraped_date": datetime.utcnow(),
            "status": "new",
        }

    def extract_job_details(self, job_url: str) -> Dict[str, Any]:
        from selenium.webdriver.common.by import By

        if self.driver is None:
            self._init_driver()

        details: Dict[str, Any] = {}
        try:
            self.driver.get(job_url)
            self.rate_limit()

            for sel in [".posting-description", "[data-hook='job-description']", ".description"]:
                try:
                    desc = self.driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                    if desc:
                        details["description"] = desc
                        break
                except Exception:
                    continue
        except Exception:
            logger.exception("[handshake] Failed to extract details from %s", job_url)
        return details

    def apply_to_job(self, job_id: str, resume_path: str, cover_letter: str) -> bool:
        logger.info("[handshake] Application for %s should be completed on platform", job_id)
        return False

    def close(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
