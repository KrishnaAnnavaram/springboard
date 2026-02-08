"""LinkedIn feed scraper for hiring posts.

Searches the LinkedIn feed/home for posts about hiring, specifically
targeting Gen AI Engineer and similar roles. Extracts post details
and saves them to the database as feed posts.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.base.base_scraper import BaseJobScraperAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Default keywords to search for in feed posts
DEFAULT_FEED_KEYWORDS = [
    "hiring",
    "Gen AI",
    "Generative AI Engineer",
    "we are hiring",
    "join our team",
    "looking for",
    "open position",
    "open role",
]


class LinkedInFeedScraperAgent(BaseJobScraperAgent):
    """Scrapes LinkedIn feed for hiring-related posts.

    Unlike normal job scrapers, this searches the LinkedIn news feed
    for posts by people or companies announcing job openings. This
    captures opportunities that may not appear in LinkedIn Jobs.
    """

    PLATFORM_NAME = "linkedin_feed"

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
        options.add_experimental_option("useAutomationExtension", False)

        self.driver = webdriver.Chrome(service=Service(), options=options)
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
        self.driver.implicitly_wait(10)
        self.driver.set_page_load_timeout(30)
        logger.info("[linkedin_feed] Chrome WebDriver initialised")

    def login(self) -> bool:
        """Authenticate to LinkedIn (required for feed access)."""
        from src.utils.config import Config

        if self.driver is None:
            self._init_driver()

        config = Config()
        email = config.linkedin_email
        password = config.linkedin_password

        if not email or not password:
            logger.error("[linkedin_feed] LinkedIn credentials required for feed access")
            return False

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait

            self.driver.get("https://www.linkedin.com/login")
            self.rate_limit()

            email_field = WebDriverWait(self.driver, 15).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "#username"))
            )
            email_field.clear()
            email_field.send_keys(email)

            password_field = self.driver.find_element(By.CSS_SELECTOR, "#password")
            password_field.clear()
            password_field.send_keys(password)

            self.rate_limit()
            submit = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            submit.click()

            try:
                WebDriverWait(self.driver, 20).until(EC.url_contains("/feed"))
                logger.info("[linkedin_feed] Login successful")
                return True
            except Exception:
                current = self.driver.current_url
                if "/checkpoint" in current or "/challenge" in current:
                    logger.warning("[linkedin_feed] Security checkpoint at %s", current)
                else:
                    logger.warning("[linkedin_feed] Did not reach /feed (at %s)", current)
                return False

        except Exception:
            logger.exception("[linkedin_feed] Login failed")
            return False

    def search_jobs(self, keywords: str, location: str, **filters: Any) -> List[Dict[str, Any]]:
        """Search LinkedIn feed for hiring posts.

        Args:
            keywords: Search query for feed posts.
            location: Not used for feed search.
            **filters: ``max_jobs`` (int), ``feed_keywords`` (List[str]).

        Returns:
            List of feed post dicts.
        """
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        max_posts = filters.get("max_jobs", 30)
        feed_keywords = filters.get("feed_keywords", DEFAULT_FEED_KEYWORDS)
        posts: List[Dict[str, Any]] = []

        # Use LinkedIn search with content type filter for posts
        search_query = keywords or "Gen AI Engineer hiring"
        search_url = f"https://www.linkedin.com/search/results/content/?keywords={search_query}&origin=GLOBAL_SEARCH_HEADER&sortBy=%22date_posted%22"

        logger.info("[linkedin_feed] Searching feed for: %s", search_query)

        try:
            self.driver.get(search_url)
            self.rate_limit()

            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".feed-shared-update-v2, .update-components-text, div.feed-shared-text"))
                )
            except Exception:
                logger.info("[linkedin_feed] No feed results found")
                return posts

            # Scroll to load more posts
            for _ in range(5):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                self.rate_limit(min_seconds=1.5, max_seconds=3.0)

            # Extract posts
            post_elements = self.driver.find_elements(By.CSS_SELECTOR, ".feed-shared-update-v2, div[data-urn*='activity']")

            for el in post_elements:
                if len(posts) >= max_posts:
                    break
                try:
                    post = self._extract_feed_post(el, feed_keywords)
                    if post and post.get("is_hiring_post"):
                        posts.append(post)
                except Exception:
                    logger.debug("[linkedin_feed] Post extraction error", exc_info=True)

        except Exception:
            logger.exception("[linkedin_feed] Error during feed search")

        logger.info("[linkedin_feed] Found %d hiring posts", len(posts))
        return posts

    def _extract_feed_post(self, element: Any, keywords: List[str]) -> Optional[Dict[str, Any]]:
        """Extract a post from a feed element and check if it's hiring-related."""
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException

        # Post text
        post_text = ""
        for sel in [".feed-shared-text .break-words", ".update-components-text", ".feed-shared-inline-show-more-text"]:
            try:
                post_text = element.find_element(By.CSS_SELECTOR, sel).text.strip()
                if post_text:
                    break
            except NoSuchElementException:
                continue

        if not post_text:
            return None

        # Check if post contains hiring keywords
        text_lower = post_text.lower()
        found_keywords = [kw for kw in keywords if kw.lower() in text_lower]
        is_hiring = len(found_keywords) > 0

        if not is_hiring:
            return None

        # Author name
        author_name = ""
        for sel in [".update-components-actor__name span", ".feed-shared-actor__name span", "span.feed-shared-actor__title"]:
            try:
                author_name = element.find_element(By.CSS_SELECTOR, sel).text.strip()
                if author_name:
                    break
            except NoSuchElementException:
                continue

        # Author profile URL
        author_url = ""
        for sel in ["a.update-components-actor__meta-link", "a.feed-shared-actor__container-link", "a.app-aware-link"]:
            try:
                author_url = element.find_element(By.CSS_SELECTOR, sel).get_attribute("href") or ""
                if author_url:
                    break
            except NoSuchElementException:
                continue

        # Post URL
        post_url = ""
        try:
            urn = element.get_attribute("data-urn") or ""
            if urn:
                activity_id = urn.split(":")[-1]
                post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}/"
        except Exception:
            pass

        # Engagement
        likes = 0
        comments = 0
        try:
            reactions_el = element.find_element(By.CSS_SELECTOR, ".social-details-social-counts__reactions-count, span.reactions-count")
            likes_text = reactions_el.text.strip().replace(",", "")
            likes = int(re.sub(r"[^\d]", "", likes_text)) if likes_text else 0
        except (NoSuchElementException, ValueError):
            pass

        try:
            comments_el = element.find_element(By.CSS_SELECTOR, ".social-details-social-counts__comments, button[aria-label*='comment']")
            comments_text = comments_el.text.strip().replace(",", "")
            comments = int(re.sub(r"[^\d]", "", comments_text)) if comments_text else 0
        except (NoSuchElementException, ValueError):
            pass

        # Try to extract company mentioned
        company = ""
        company_patterns = [
            r"(?:at|@)\s+([A-Z][A-Za-z0-9\s&]+)",
            r"([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\s+is\s+hiring",
        ]
        for pat in company_patterns:
            match = re.search(pat, post_text)
            if match:
                company = match.group(1).strip()
                break

        return {
            "platform": self.PLATFORM_NAME,
            "platform_job_id": post_url.split("/")[-2] if post_url else "",
            "title": f"Hiring Post: {found_keywords[0]}",
            "company": company,
            "location": "",
            "job_url": post_url,
            "description": post_text[:2000],
            "is_easy_apply": False,
            "application_method": "external_link",
            "scraped_date": datetime.utcnow(),
            "status": "new",
            # Feed-specific fields
            "is_hiring_post": True,
            "author_name": author_name,
            "author_profile_url": author_url,
            "post_text": post_text,
            "keywords_found": found_keywords,
            "likes": likes,
            "comments": comments,
            "platform_metadata": {
                "post_url": post_url,
                "author": author_name,
                "author_url": author_url,
                "engagement": {"likes": likes, "comments": comments},
                "keywords_matched": found_keywords,
            },
        }

    def extract_job_details(self, job_url: str) -> Dict[str, Any]:
        """Feed posts don't have separate detail pages."""
        return {}

    def apply_to_job(self, job_id: str, resume_path: str, cover_letter: str) -> bool:
        """Feed posts require manual follow-up."""
        logger.info("[linkedin_feed] Post %s requires manual application", job_id)
        return False

    def close(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
