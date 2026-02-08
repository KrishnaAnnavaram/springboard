"""LinkedIn job scraper agent using Selenium WebDriver with Chrome.

This module provides a production-ready agent that automates LinkedIn job
searching and scraping. It handles authentication, paginated search results,
job detail extraction, and persistent storage via the JobRepository.
"""

import random
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.database.connection import get_db
from src.database.repositories.job_repository import JobRepository
from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LinkedInScraperAgent:
    """Selenium-based agent that scrapes LinkedIn job postings.

    The agent logs in to LinkedIn, searches for jobs using configured keywords
    and locations, extracts structured data from each listing, and persists
    the results through ``JobRepository``.

    Attributes:
        config: Application configuration singleton.
        driver: Selenium WebDriver instance (created during ``_init_driver``).
        scraped_jobs: In-memory buffer of extracted job dictionaries awaiting
            database persistence.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        """Initialise the scraper with configuration but without a browser."""
        self.config: Config = Config()
        self.driver: Optional[WebDriver] = None
        self.scraped_jobs: List[Dict[str, Any]] = []

        # Pull convenience references from config.
        self._linkedin_cfg: Dict[str, Any] = self.config.linkedin_config
        self._browser_cfg: Dict[str, Any] = self._linkedin_cfg.get("browser", {})
        self._urls: Dict[str, str] = self._linkedin_cfg.get("urls", {})
        self._selectors: Dict[str, str] = self._linkedin_cfg.get("selectors", {})
        self._automation: Dict[str, Any] = self.config.automation

        # Delay bounds for rate-limiting.
        self._min_delay: float = float(self._automation.get("min_delay_between_actions", 3))
        self._max_delay: float = float(self._automation.get("max_delay_between_actions", 5))

        # Retry settings.
        self._retry_attempts: int = int(self._automation.get("retry_attempts", 3))
        self._retry_backoff: float = float(self._automation.get("retry_backoff_factor", 2))

        logger.info("LinkedInScraperAgent initialised")

    # ------------------------------------------------------------------
    # Driver management
    # ------------------------------------------------------------------

    def _init_driver(self) -> None:
        """Create and configure the Chrome WebDriver instance.

        Chrome options are derived from the ``linkedin.browser`` section of
        the YAML configuration.  The driver is stored on ``self.driver``.

        Raises:
            WebDriverException: If Chrome or ChromeDriver cannot be started.
        """
        try:
            options = Options()

            # Headless mode.
            if self._browser_cfg.get("headless", True):
                options.add_argument("--headless=new")

            # Standard hardening flags.
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")

            # Window dimensions.
            width = self._browser_cfg.get("window_width", 1920)
            height = self._browser_cfg.get("window_height", 1080)
            options.add_argument(f"--window-size={width},{height}")

            # Custom user-agent.
            user_agent = self._browser_cfg.get(
                "user_agent",
                (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            options.add_argument(f"--user-agent={user_agent}")

            # Reduce automation fingerprinting.
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            service = Service()
            self.driver = webdriver.Chrome(service=service, options=options)

            # Override the navigator.webdriver flag.
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
            )

            # Reasonable implicit and page-load timeouts.
            self.driver.implicitly_wait(10)
            self.driver.set_page_load_timeout(30)

            logger.info("Chrome WebDriver initialised (headless=%s)", self._browser_cfg.get("headless", True))

        except WebDriverException:
            logger.exception("Failed to initialise Chrome WebDriver")
            raise

    def _quit_driver(self) -> None:
        """Safely close the WebDriver session."""
        if self.driver is not None:
            try:
                self.driver.quit()
                logger.info("Chrome WebDriver session closed")
            except WebDriverException:
                logger.warning("Error while closing WebDriver session", exc_info=True)
            finally:
                self.driver = None

    # ------------------------------------------------------------------
    # Rate-limiting helpers
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        """Sleep for a random duration between the configured bounds."""
        delay = random.uniform(self._min_delay, self._max_delay)
        logger.debug("Rate-limit pause: %.2f s", delay)
        time.sleep(delay)

    def _wait_for_element(
        self,
        by: str,
        value: str,
        timeout: int = 15,
        condition: str = "presence",
    ) -> Optional[WebElement]:
        """Wait for a DOM element matching the given locator.

        Args:
            by: Selenium ``By`` strategy (e.g. ``By.CSS_SELECTOR``).
            value: Locator value.
            timeout: Maximum seconds to wait.
            condition: One of ``"presence"``, ``"visible"``, or ``"clickable"``.

        Returns:
            The located ``WebElement``, or ``None`` on timeout.
        """
        try:
            wait = WebDriverWait(self.driver, timeout)
            conditions_map = {
                "presence": EC.presence_of_element_located,
                "visible": EC.visibility_of_element_located,
                "clickable": EC.element_to_be_clickable,
            }
            ec_func = conditions_map.get(condition, EC.presence_of_element_located)
            return wait.until(ec_func((by, value)))
        except TimeoutException:
            logger.debug("Timeout waiting for element: %s=%s", by, value)
            return None

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------

    def _retry(
        self,
        func: Any,
        *args: Any,
        attempts: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        """Execute *func* with exponential-backoff retry.

        Args:
            func: Callable to invoke.
            *args: Positional arguments forwarded to *func*.
            attempts: Override for the default retry count.
            **kwargs: Keyword arguments forwarded to *func*.

        Returns:
            The return value of *func* on success.

        Raises:
            Exception: The last exception raised by *func* after all
                attempts have been exhausted.
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
                        "Attempt %d/%d for %s failed (%s). Retrying in %.1f s ...",
                        attempt,
                        max_attempts,
                        func.__name__,
                        exc,
                        backoff,
                    )
                    time.sleep(backoff)
                else:
                    logger.error(
                        "All %d attempts for %s exhausted. Last error: %s",
                        max_attempts,
                        func.__name__,
                        exc,
                    )

        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self) -> bool:
        """Authenticate to LinkedIn using credentials from configuration.

        Credentials are read from the environment variables
        ``LINKEDIN_EMAIL`` and ``LINKEDIN_PASSWORD`` via the ``Config``
        singleton.

        Returns:
            ``True`` if the login appears successful (the feed page loads),
            ``False`` otherwise.
        """
        email = self.config.linkedin_email
        password = self.config.linkedin_password

        if not email or not password:
            logger.error("LinkedIn credentials are not configured. Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD.")
            return False

        try:
            login_url = self._urls.get("login", "https://www.linkedin.com/login")
            logger.info("Navigating to LinkedIn login page: %s", login_url)
            self.driver.get(login_url)
            self._rate_limit()

            # -- Email field --
            email_selector = self._selectors.get("login_email", "#username")
            email_field = self._wait_for_element(By.CSS_SELECTOR, email_selector, condition="visible")
            if email_field is None:
                logger.error("Could not locate the email input field (%s)", email_selector)
                return False
            email_field.clear()
            email_field.send_keys(email)

            # -- Password field --
            password_selector = self._selectors.get("login_password", "#password")
            password_field = self._wait_for_element(By.CSS_SELECTOR, password_selector, condition="visible")
            if password_field is None:
                logger.error("Could not locate the password input field (%s)", password_selector)
                return False
            password_field.clear()
            password_field.send_keys(password)

            self._rate_limit()

            # -- Submit --
            submit_selector = self._selectors.get("login_button", "button[type='submit']")
            submit_button = self._wait_for_element(By.CSS_SELECTOR, submit_selector, condition="clickable")
            if submit_button is None:
                logger.error("Could not locate the login submit button (%s)", submit_selector)
                return False
            submit_button.click()

            # Wait for post-login navigation.
            feed_url = self._urls.get("feed", "https://www.linkedin.com/feed/")
            try:
                WebDriverWait(self.driver, 20).until(EC.url_contains("/feed"))
                logger.info("Login successful -- redirected to feed")
                return True
            except TimeoutException:
                current = self.driver.current_url
                # Some accounts redirect to a checkpoint or onboarding page.
                if "/checkpoint" in current or "/challenge" in current:
                    logger.warning(
                        "Login hit a security checkpoint at %s. Manual intervention may be needed.",
                        current,
                    )
                else:
                    logger.warning("Post-login redirect did not reach /feed (current URL: %s)", current)
                return False

        except WebDriverException:
            logger.exception("WebDriver error during login")
            return False

    # ------------------------------------------------------------------
    # Job search
    # ------------------------------------------------------------------

    def search_jobs(
        self,
        keywords: str,
        location: str,
        easy_apply: bool = True,
    ) -> List[Dict[str, Any]]:
        """Search LinkedIn for jobs and return extracted listings.

        The method builds a LinkedIn Jobs search URL with the supplied
        parameters, scrolls through paginated results, and extracts
        structured data from each job card.

        Args:
            keywords: Search query (e.g. ``"Software Engineer"``).
            location: Geographic filter (e.g. ``"Remote"``).
            easy_apply: If ``True``, restrict results to Easy Apply jobs.

        Returns:
            A list of dictionaries, each containing the extracted fields for
            one job posting.
        """
        jobs: List[Dict[str, Any]] = []
        max_jobs = self.config.max_jobs_per_search

        try:
            search_url = self._build_search_url(keywords, location, easy_apply)
            logger.info(
                "Starting job search: keywords=%r, location=%r, easy_apply=%s",
                keywords,
                location,
                easy_apply,
            )
            self.driver.get(search_url)
            self._rate_limit()

            # Let the initial result set render.
            self._wait_for_element(
                By.CSS_SELECTOR,
                ".jobs-search-results-list",
                timeout=20,
                condition="presence",
            )

            page = 1
            while len(jobs) < max_jobs:
                logger.info("Processing search results page %d (collected %d/%d)", page, len(jobs), max_jobs)

                # Scroll to load lazy-rendered cards.
                self._scroll_results_panel()

                job_cards = self._get_job_cards()
                if not job_cards:
                    logger.info("No job cards found on page %d -- ending pagination", page)
                    break

                for card in job_cards:
                    if len(jobs) >= max_jobs:
                        break

                    try:
                        job_data = self._extract_job_from_card(card)
                        if job_data and job_data.get("linkedin_job_id"):
                            # Skip duplicates within this search run.
                            if not any(j["linkedin_job_id"] == job_data["linkedin_job_id"] for j in jobs):
                                jobs.append(job_data)
                                logger.debug(
                                    "Extracted job: %s at %s (ID %s)",
                                    job_data.get("title"),
                                    job_data.get("company"),
                                    job_data.get("linkedin_job_id"),
                                )
                    except (StaleElementReferenceException, NoSuchElementException):
                        logger.warning("Stale/missing card element -- skipping")
                        continue

                    self._rate_limit()

                # Attempt to go to the next page.
                if len(jobs) < max_jobs and not self._go_to_next_page():
                    logger.info("No further pages available -- ending pagination")
                    break

                page += 1
                self._rate_limit()

            logger.info(
                "Search complete for %r / %r. Collected %d jobs.",
                keywords,
                location,
                len(jobs),
            )

        except WebDriverException:
            logger.exception("WebDriver error during job search")
        except Exception:
            logger.exception("Unexpected error during job search")

        return jobs

    def _build_search_url(self, keywords: str, location: str, easy_apply: bool) -> str:
        """Construct a LinkedIn Jobs search URL with query parameters.

        Args:
            keywords: Job search keywords.
            location: Location filter.
            easy_apply: Whether to enable the Easy Apply filter.

        Returns:
            Fully-qualified search URL string.
        """
        from urllib.parse import quote_plus, urlencode

        base = self._urls.get("jobs", "https://www.linkedin.com/jobs/search/")
        params: Dict[str, str] = {
            "keywords": keywords,
            "location": location,
        }
        if easy_apply:
            params["f_AL"] = "true"

        url = f"{base}?{urlencode(params, quote_via=quote_plus)}"
        logger.debug("Built search URL: %s", url)
        return url

    # ------------------------------------------------------------------
    # Results scrolling and pagination
    # ------------------------------------------------------------------

    def _scroll_results_panel(self, scroll_pause: float = 1.5, max_scrolls: int = 5) -> None:
        """Scroll the job results panel to trigger lazy loading.

        Args:
            scroll_pause: Seconds to wait between scroll increments.
            max_scrolls: Maximum number of scroll actions to perform.
        """
        try:
            results_container = self.driver.find_element(
                By.CSS_SELECTOR, ".jobs-search-results-list"
            )

            for i in range(max_scrolls):
                self.driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight;",
                    results_container,
                )
                time.sleep(scroll_pause)

                # Check if we've reached the bottom.
                new_height = self.driver.execute_script(
                    "return arguments[0].scrollHeight;", results_container
                )
                current_scroll = self.driver.execute_script(
                    "return arguments[0].scrollTop + arguments[0].clientHeight;",
                    results_container,
                )
                if current_scroll >= new_height:
                    logger.debug("Results panel fully scrolled after %d iterations", i + 1)
                    break

        except NoSuchElementException:
            logger.debug("Results container not found -- attempting full-page scroll fallback")
            for _ in range(max_scrolls):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(scroll_pause)

        except WebDriverException:
            logger.warning("Error while scrolling results panel", exc_info=True)

    def _get_job_cards(self) -> List[WebElement]:
        """Locate all visible job card elements on the current page.

        Returns:
            A list of Selenium ``WebElement`` objects representing job cards.
        """
        selectors = [
            ".jobs-search-results__list-item",
            ".job-card-container",
            "li.jobs-search-results__list-item",
            ".scaffold-layout__list-item",
        ]

        for selector in selectors:
            try:
                cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if cards:
                    logger.debug("Found %d job cards with selector %r", len(cards), selector)
                    return cards
            except WebDriverException:
                continue

        logger.warning("No job cards found with any known selector")
        return []

    def _go_to_next_page(self) -> bool:
        """Click the next-page button in the pagination bar.

        Returns:
            ``True`` if navigation to the next page succeeded, ``False``
            otherwise.
        """
        try:
            # Look for pagination controls.
            pagination = self._wait_for_element(
                By.CSS_SELECTOR,
                ".artdeco-pagination",
                timeout=5,
                condition="presence",
            )
            if pagination is None:
                return False

            # Find the currently active page button, then click the next sibling.
            active_page = pagination.find_elements(By.CSS_SELECTOR, "li.active, li.selected, li[class*='active']")
            if not active_page:
                # Fallback: look for a generic "Next" button.
                next_btn = pagination.find_elements(By.CSS_SELECTOR, "button[aria-label='Next']")
                if next_btn and next_btn[0].is_enabled():
                    self.driver.execute_script("arguments[0].click();", next_btn[0])
                    self._rate_limit()
                    return True
                return False

            next_li = active_page[-1].find_element(By.XPATH, "following-sibling::li")
            next_button = next_li.find_element(By.TAG_NAME, "button")
            self.driver.execute_script("arguments[0].click();", next_button)

            # Wait for the new page to render.
            time.sleep(2)
            self._rate_limit()

            logger.debug("Navigated to next search results page")
            return True

        except (NoSuchElementException, ElementClickInterceptedException):
            logger.debug("No next page available or click intercepted")
            return False
        except WebDriverException:
            logger.warning("Error navigating to next page", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Job data extraction
    # ------------------------------------------------------------------

    def _extract_job_from_card(self, card: WebElement) -> Optional[Dict[str, Any]]:
        """Click a job card and extract detailed information.

        The method clicks the card element to load the detail pane on the
        right-hand side, then scrapes all available fields.

        Args:
            card: The job card ``WebElement``.

        Returns:
            A dictionary of extracted job fields, or ``None`` if extraction
            fails.
        """
        try:
            # Scroll the card into view and click to load details.
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
            time.sleep(0.5)

            clickable = card.find_elements(By.CSS_SELECTOR, "a.job-card-container__link, a.job-card-list__title")
            if clickable:
                self.driver.execute_script("arguments[0].click();", clickable[0])
            else:
                self.driver.execute_script("arguments[0].click();", card)

            # Wait for the detail pane to load.
            self._wait_for_element(
                By.CSS_SELECTOR,
                ".jobs-search__job-details, .job-details-jobs-unified-top-card",
                timeout=10,
                condition="presence",
            )
            time.sleep(1)

            job_data: Dict[str, Any] = {
                "title": self._extract_title(card),
                "company": self._extract_company(card),
                "location": self._extract_location(card),
                "linkedin_job_id": self._extract_job_id(card),
                "job_url": self._extract_job_url(card),
                "is_easy_apply": self._detect_easy_apply(),
                "description": self._extract_description(),
                "requirements": self._extract_requirements(),
                "salary_range": self._extract_salary(),
                "job_type": self._extract_job_type(),
                "experience_level": self._extract_experience_level(),
                "posted_date": self._extract_posted_date(),
                "scraped_date": datetime.utcnow(),
                "status": "new",
            }

            return job_data

        except (StaleElementReferenceException, NoSuchElementException):
            logger.debug("Card became stale or element missing during extraction")
            return None
        except WebDriverException:
            logger.warning("WebDriver error extracting job from card", exc_info=True)
            return None

    # -- Individual field extractors --

    def _extract_title(self, card: WebElement) -> str:
        """Extract the job title from a card or the detail pane."""
        selectors = [
            "a.job-card-list__title span",
            "a.job-card-list__title",
            ".job-card-container__link span",
            ".job-card-list__title--link span",
            "h2.job-card-container__link span",
        ]
        for sel in selectors:
            try:
                el = card.find_element(By.CSS_SELECTOR, sel)
                text = el.text.strip()
                if text:
                    return text
            except NoSuchElementException:
                continue

        # Fallback: try the detail pane.
        try:
            detail_title = self.driver.find_element(
                By.CSS_SELECTOR,
                ".jobs-unified-top-card__job-title, .job-details-jobs-unified-top-card__job-title, h1.t-24",
            )
            return detail_title.text.strip()
        except NoSuchElementException:
            return ""

    def _extract_company(self, card: WebElement) -> str:
        """Extract the company name from a card or the detail pane."""
        selectors = [
            ".job-card-container__primary-description",
            ".job-card-container__company-name",
            ".artdeco-entity-lockup__subtitle span",
        ]
        for sel in selectors:
            try:
                el = card.find_element(By.CSS_SELECTOR, sel)
                text = el.text.strip()
                if text:
                    return text
            except NoSuchElementException:
                continue

        try:
            detail_company = self.driver.find_element(
                By.CSS_SELECTOR,
                ".jobs-unified-top-card__company-name a, .job-details-jobs-unified-top-card__company-name a",
            )
            return detail_company.text.strip()
        except NoSuchElementException:
            return ""

    def _extract_location(self, card: WebElement) -> str:
        """Extract the location from a card or the detail pane."""
        selectors = [
            ".job-card-container__metadata-item",
            ".artdeco-entity-lockup__caption span",
            ".job-card-container__metadata-wrapper li",
        ]
        for sel in selectors:
            try:
                el = card.find_element(By.CSS_SELECTOR, sel)
                text = el.text.strip()
                if text:
                    return text
            except NoSuchElementException:
                continue

        try:
            detail_loc = self.driver.find_element(
                By.CSS_SELECTOR,
                ".jobs-unified-top-card__bullet, .job-details-jobs-unified-top-card__bullet",
            )
            return detail_loc.text.strip()
        except NoSuchElementException:
            return ""

    def _extract_job_id(self, card: WebElement) -> str:
        """Extract the LinkedIn job ID from a card element's data attributes or URL."""
        # Try data-job-id attribute.
        try:
            job_id = card.get_attribute("data-job-id")
            if job_id:
                return job_id.strip()
        except WebDriverException:
            pass

        # Try data-occludable-job-id.
        try:
            job_id = card.get_attribute("data-occludable-job-id")
            if job_id:
                return job_id.strip()
        except WebDriverException:
            pass

        # Parse from the card's anchor href.
        try:
            link = card.find_element(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
            href = link.get_attribute("href") or ""
            match = re.search(r"/jobs/view/(\d+)", href)
            if match:
                return match.group(1)
        except (NoSuchElementException, WebDriverException):
            pass

        # Fallback: parse from current page URL.
        try:
            current_url = self.driver.current_url
            match = re.search(r"currentJobId=(\d+)", current_url)
            if match:
                return match.group(1)
        except WebDriverException:
            pass

        return ""

    def _extract_job_url(self, card: WebElement) -> str:
        """Extract the canonical URL for the job posting."""
        try:
            link = card.find_element(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
            href = link.get_attribute("href") or ""
            # Strip tracking parameters for a clean URL.
            base_url = href.split("?")[0]
            if base_url:
                return base_url
        except (NoSuchElementException, WebDriverException):
            pass

        # Construct from job ID.
        job_id = self._extract_job_id(card)
        if job_id:
            return f"https://www.linkedin.com/jobs/view/{job_id}/"
        return ""

    def _detect_easy_apply(self) -> bool:
        """Check whether the currently displayed job offers Easy Apply."""
        easy_apply_indicators = [
            ".jobs-apply-button--top-card .jobs-apply-button",
            "button.jobs-apply-button",
            ".jobs-s-apply button",
        ]

        for selector in easy_apply_indicators:
            try:
                buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for btn in buttons:
                    btn_text = btn.text.strip().lower()
                    if "easy apply" in btn_text:
                        return True
            except WebDriverException:
                continue

        # Check for the Easy Apply badge anywhere in the detail pane.
        try:
            badge_elements = self.driver.find_elements(
                By.XPATH, "//*[contains(text(), 'Easy Apply')]"
            )
            if badge_elements:
                return True
        except WebDriverException:
            pass

        return False

    def _extract_description(self) -> str:
        """Extract the full job description from the detail pane."""
        selectors = [
            ".jobs-description-content__text",
            ".jobs-description__content",
            "#job-details",
            ".jobs-box__html-content",
        ]

        for sel in selectors:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, sel)
                text = el.text.strip()
                if text:
                    return text
            except NoSuchElementException:
                continue

        return ""

    def _extract_requirements(self) -> str:
        """Extract job requirements or qualifications from the description.

        LinkedIn does not typically separate requirements into a distinct
        element.  This method attempts to identify a requirements section
        within the full description text.

        Returns:
            The requirements section if found, otherwise an empty string.
        """
        description = self._extract_description()
        if not description:
            return ""

        # Common section headings that precede requirements.
        requirement_headers = [
            r"(?i)(?:minimum\s+)?qualifications?",
            r"(?i)requirements?",
            r"(?i)what\s+you(?:'ll)?\s+need",
            r"(?i)must[\s-]+have",
            r"(?i)skills?\s+(?:&|and)\s+(?:experience|qualifications?)",
            r"(?i)who\s+you\s+are",
        ]

        for pattern in requirement_headers:
            match = re.search(pattern, description)
            if match:
                start = match.start()
                # Return from the header to either the next major section or end.
                section = description[start:]

                # Try to find the end of the section.
                next_section = re.search(
                    r"\n\s*(?:About|Benefits|Perks|What We Offer|Responsibilities|Nice to have|Preferred)\b",
                    section[len(match.group()):],
                    re.IGNORECASE,
                )
                if next_section:
                    return section[: len(match.group()) + next_section.start()].strip()
                return section.strip()

        return ""

    def _extract_salary(self) -> str:
        """Extract salary information if present in the detail pane."""
        selectors = [
            ".jobs-unified-top-card__job-insight span:nth-child(1)",
            ".salary-main-rail__data-body",
            ".compensation__salary",
        ]

        for sel in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    text = el.text.strip()
                    if text and ("$" in text or "salary" in text.lower() or "/yr" in text.lower()):
                        return text
            except WebDriverException:
                continue

        # Regex fallback: search the page source for salary patterns.
        try:
            page_source = self.driver.page_source
            salary_match = re.search(
                r"\$[\d,]+(?:\.\d+)?(?:\s*[-\u2013]\s*\$[\d,]+(?:\.\d+)?)?(?:\s*/\s*(?:yr|year|hr|hour))?",
                page_source,
            )
            if salary_match:
                return salary_match.group(0)
        except WebDriverException:
            pass

        return ""

    def _extract_job_type(self) -> str:
        """Extract the job type (Full-time, Part-time, Contract, etc.)."""
        try:
            insights = self.driver.find_elements(
                By.CSS_SELECTOR,
                ".jobs-unified-top-card__job-insight span, .job-details-jobs-unified-top-card__job-insight span",
            )
            job_types = {"full-time", "part-time", "contract", "temporary", "internship", "volunteer", "other"}
            for insight in insights:
                text = insight.text.strip().lower()
                for jt in job_types:
                    if jt in text:
                        return insight.text.strip()
        except WebDriverException:
            pass

        return ""

    def _extract_experience_level(self) -> str:
        """Extract the seniority / experience level."""
        try:
            insights = self.driver.find_elements(
                By.CSS_SELECTOR,
                ".jobs-unified-top-card__job-insight span, .job-details-jobs-unified-top-card__job-insight span",
            )
            levels = {
                "internship", "entry level", "associate", "mid-senior level",
                "director", "executive", "not applicable",
            }
            for insight in insights:
                text = insight.text.strip().lower()
                for level in levels:
                    if level in text:
                        return insight.text.strip()
        except WebDriverException:
            pass

        return ""

    def _extract_posted_date(self) -> Optional[datetime]:
        """Attempt to parse the posting date from the detail pane.

        Returns:
            A ``datetime`` if a relative time string is found and parsed,
            otherwise ``None``.
        """
        selectors = [
            ".jobs-unified-top-card__posted-date",
            ".job-details-jobs-unified-top-card__posted-date",
            "span.tvm__text--low-emphasis",
        ]

        for sel in selectors:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, sel)
                text = el.text.strip().lower()
                return self._parse_relative_date(text)
            except (NoSuchElementException, WebDriverException):
                continue

        return None

    @staticmethod
    def _parse_relative_date(text: str) -> Optional[datetime]:
        """Convert a relative date string (e.g. '2 days ago') to a datetime.

        Args:
            text: A string like ``"3 hours ago"``, ``"1 week ago"``, etc.

        Returns:
            An approximate ``datetime``, or ``None`` if parsing fails.
        """
        now = datetime.utcnow()
        match = re.search(r"(\d+)\s+(minute|hour|day|week|month)s?\s+ago", text)
        if not match:
            if "just now" in text or "moment" in text:
                return now
            return None

        value = int(match.group(1))
        unit = match.group(2)

        from datetime import timedelta

        deltas = {
            "minute": timedelta(minutes=value),
            "hour": timedelta(hours=value),
            "day": timedelta(days=value),
            "week": timedelta(weeks=value),
            "month": timedelta(days=value * 30),
        }
        delta = deltas.get(unit)
        return (now - delta) if delta else None

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    def save_jobs_to_db(self, jobs: Optional[List[Dict[str, Any]]] = None) -> int:
        """Persist scraped jobs to the database via ``JobRepository``.

        Duplicate jobs (by ``linkedin_job_id``) are silently skipped.

        Args:
            jobs: List of job dictionaries.  If ``None``, the internal
                ``self.scraped_jobs`` buffer is used.

        Returns:
            The number of *new* jobs successfully saved.
        """
        jobs_to_save = jobs if jobs is not None else self.scraped_jobs
        if not jobs_to_save:
            logger.info("No jobs to save")
            return 0

        saved_count = 0

        try:
            with get_db() as session:
                repo = JobRepository(session)

                for job_data in jobs_to_save:
                    try:
                        linkedin_job_id = job_data.get("linkedin_job_id", "")
                        if not linkedin_job_id:
                            logger.warning("Skipping job with no LinkedIn ID: %s", job_data.get("title", "<unknown>"))
                            continue

                        # Duplicate check.
                        existing = repo.get_by_linkedin_id(linkedin_job_id)
                        if existing is not None:
                            logger.debug("Job %s already exists in database -- skipping", linkedin_job_id)
                            continue

                        repo.create(
                            linkedin_job_id=linkedin_job_id,
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
                            status=job_data.get("status", "new"),
                        )
                        saved_count += 1

                    except Exception:
                        logger.exception(
                            "Failed to save job %s",
                            job_data.get("linkedin_job_id", "<unknown>"),
                        )
                        continue

            logger.info("Saved %d new jobs to database (of %d total scraped)", saved_count, len(jobs_to_save))

        except Exception:
            logger.exception("Database error while saving jobs")

        return saved_count

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Execute the full scraping pipeline.

        Steps:
            1. Initialise the Chrome WebDriver.
            2. Log in to LinkedIn.
            3. For each configured *title* x *location* pair, search and
               scrape job listings.
            4. Persist all collected jobs to the database.
            5. Shut down the WebDriver.
        """
        logger.info("=== LinkedInScraperAgent run started ===")

        try:
            # Step 1 -- browser.
            self._retry(self._init_driver)

            # Step 2 -- authentication.
            logged_in = self._retry(self.login)
            if not logged_in:
                logger.error("Login failed after retries -- aborting run")
                return

            # Step 3 -- search.
            titles = self.config.search_titles or ["Software Engineer"]
            locations = self.config.search_locations or ["United States"]
            easy_apply = self.config.easy_apply_only

            for title in titles:
                for location in locations:
                    try:
                        jobs = self._retry(
                            self.search_jobs,
                            title,
                            location,
                            easy_apply,
                        )
                        self.scraped_jobs.extend(jobs)
                        logger.info(
                            "Collected %d jobs for %r in %r (buffer total: %d)",
                            len(jobs),
                            title,
                            location,
                            len(self.scraped_jobs),
                        )
                    except Exception:
                        logger.exception("Failed search for %r in %r", title, location)
                        continue

                    self._rate_limit()

            # Step 4 -- persist.
            saved = self.save_jobs_to_db()
            logger.info(
                "Pipeline complete. Scraped %d jobs, saved %d new entries.",
                len(self.scraped_jobs),
                saved,
            )

        except Exception:
            logger.exception("Fatal error in LinkedInScraperAgent.run()")

        finally:
            # Step 5 -- cleanup.
            self._quit_driver()
            logger.info("=== LinkedInScraperAgent run finished ===")
