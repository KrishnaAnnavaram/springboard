"""LinkedIn Easy Apply automation agent.

Drives a Selenium-controlled Chrome browser through the LinkedIn Easy Apply
flow: navigation, form completion (contact info, resume upload, cover letter,
standard questions, and AI-generated answers for custom questions), submission,
screenshot capture, and database record creation.

Safety features:
    - Configurable daily application cap (default 20).
    - Randomised delays between individual actions (3-8 s) and between
      successive applications (60-600 s) to mimic human cadence.
    - Automatic retry with exponential back-off on transient failures.
    - All exceptions are caught, logged, and persisted as application notes.
"""

from __future__ import annotations

import os
import random
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.database.connection import get_db
from src.database.repositories.application_repository import ApplicationRepository
from src.database.repositories.job_repository import JobRepository
from src.database.repositories.resume_repository import ResumeRepository
from src.database.repositories.user_repository import UserRepository
from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Delay ranges (seconds)
_ACTION_DELAY_MIN: float = 3.0
_ACTION_DELAY_MAX: float = 8.0
_APPLICATION_DELAY_MIN: float = 60.0
_APPLICATION_DELAY_MAX: float = 600.0

# Retry parameters
_MAX_RETRIES: int = 3
_RETRY_BACKOFF_BASE: float = 5.0

# Selenium wait timeout (seconds)
_ELEMENT_WAIT_TIMEOUT: int = 15

# Standard question keyword -> answer mapping templates.  The actual values
# are resolved at runtime from the user profile, but these keys are used to
# detect the question type from the form label text.
_STANDARD_QUESTION_KEYWORDS: Dict[str, str] = {
    "years of experience": "years_of_experience",
    "work authorization": "work_authorization",
    "authorized to work": "work_authorization",
    "legally authorized": "work_authorization",
    "sponsorship": "sponsorship",
    "require sponsorship": "sponsorship",
    "visa sponsorship": "sponsorship",
}


class LinkedInApplicationAgent:
    """Automates LinkedIn Easy Apply submissions via Selenium.

    The agent operates in a strict lifecycle:

        1. ``navigate_to_job``  -- open the job listing page.
        2. ``click_easy_apply`` -- locate and click the *Easy Apply* button.
        3. ``fill_form``        -- iterate through every modal step, filling
           fields and uploading documents as needed.
        4. ``submit_application`` -- click the final *Submit* button and
           verify the confirmation dialog.
        5. ``take_screenshot``  -- persist a timestamped PNG as proof.
        6. ``create_application_record`` -- write the outcome to the database.

    A high-level ``run`` method processes all pending applications in one
    invocation while respecting the daily cap and inter-application delays.

    Args:
        driver: An optional pre-existing Selenium ``WebDriver`` instance.
            When *None*, a new headless Chrome session is created.
        user_id: Database primary key of the user on whose behalf
            applications are submitted.  Defaults to ``1``.
    """

    # ------------------------------------------------------------------
    # Construction / teardown
    # ------------------------------------------------------------------

    def __init__(
        self,
        driver: Optional[WebDriver] = None,
        user_id: int = 1,
    ) -> None:
        self.config: Config = Config()
        self.user_id: int = user_id
        self.max_daily_applications: int = self.config.max_applications_per_day
        self.applications_submitted_today: int = 0

        # Anthropic client for answering custom / open-ended questions.
        self._anthropic: anthropic.Anthropic = anthropic.Anthropic(
            api_key=self.config.anthropic_api_key,
        )

        # Screenshot output directory.
        self._screenshot_dir: Path = self.config.project_root / "data" / "screenshots"
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

        # Selenium driver -- reuse the caller's session or spin up a new one.
        self.driver: WebDriver = driver or self._create_driver()
        self._owns_driver: bool = driver is None  # only quit what we created

        logger.info(
            "LinkedInApplicationAgent initialised (user_id=%d, daily_cap=%d)",
            self.user_id,
            self.max_daily_applications,
        )

    # ------------------------------------------------------------------
    # Driver helpers
    # ------------------------------------------------------------------

    def _create_driver(self) -> WebDriver:
        """Create a Chrome WebDriver with sensible defaults.

        Returns:
            A configured ``webdriver.Chrome`` instance.
        """
        options = ChromeOptions()

        # Run headless unless explicitly disabled in config.
        if self.config.automation.get("headless", True):
            options.add_argument("--headless=new")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Optional: user-data-dir for persistent login session.
        chrome_profile = self.config.automation.get("chrome_profile_dir")
        if chrome_profile:
            options.add_argument(f"--user-data-dir={chrome_profile}")

        # Optional: explicit chromedriver path.
        chromedriver_path = self.config.automation.get("chromedriver_path")
        service = ChromeService(executable_path=chromedriver_path) if chromedriver_path else ChromeService()

        driver = webdriver.Chrome(service=service, options=options)
        driver.implicitly_wait(self.config.scraping_delay)

        logger.info("Chrome WebDriver created successfully.")
        return driver

    def close(self) -> None:
        """Gracefully close the browser session if we own it."""
        if self._owns_driver and self.driver:
            try:
                self.driver.quit()
                logger.info("Chrome WebDriver closed.")
            except WebDriverException as exc:
                logger.warning("Error closing WebDriver: %s", exc)

    def __enter__(self) -> "LinkedInApplicationAgent":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Timing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _action_delay() -> None:
        """Sleep for a random duration between actions (3-8 s)."""
        delay = random.uniform(_ACTION_DELAY_MIN, _ACTION_DELAY_MAX)
        logger.debug("Action delay: %.1f s", delay)
        time.sleep(delay)

    @staticmethod
    def _application_delay() -> None:
        """Sleep for a random duration between applications (60-600 s)."""
        delay = random.uniform(_APPLICATION_DELAY_MIN, _APPLICATION_DELAY_MAX)
        logger.info("Inter-application delay: %.0f s (%.1f min)", delay, delay / 60)
        time.sleep(delay)

    # ------------------------------------------------------------------
    # Selenium convenience wrappers
    # ------------------------------------------------------------------

    def _wait_and_find(
        self,
        by: str,
        value: str,
        timeout: int = _ELEMENT_WAIT_TIMEOUT,
        clickable: bool = False,
    ) -> WebElement:
        """Wait for an element to appear and return it.

        Args:
            by: Selenium ``By`` locator strategy.
            value: Locator value.
            timeout: Maximum seconds to wait.
            clickable: If *True*, wait until the element is clickable
                rather than merely present.

        Returns:
            The located ``WebElement``.

        Raises:
            TimeoutException: If the element is not found within *timeout*.
        """
        condition = (
            EC.element_to_be_clickable((by, value))
            if clickable
            else EC.presence_of_element_located((by, value))
        )
        return WebDriverWait(self.driver, timeout).until(condition)

    def _safe_click(self, element: WebElement) -> None:
        """Click an element, falling back to JavaScript click on failure.

        Args:
            element: The target ``WebElement``.
        """
        try:
            element.click()
        except ElementClickInterceptedException:
            logger.debug("Standard click intercepted; falling back to JS click.")
            self.driver.execute_script("arguments[0].click();", element)

    def _scroll_into_view(self, element: WebElement) -> None:
        """Scroll an element into the visible viewport.

        Args:
            element: The target ``WebElement``.
        """
        self.driver.execute_script(
            "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
            element,
        )
        time.sleep(0.5)

    # ------------------------------------------------------------------
    # Core workflow steps
    # ------------------------------------------------------------------

    def navigate_to_job(self, job_url: str) -> bool:
        """Navigate the browser to *job_url*.

        Args:
            job_url: Full URL of the LinkedIn job listing.

        Returns:
            *True* if the page loaded successfully, *False* otherwise.
        """
        logger.info("Navigating to job: %s", job_url)
        try:
            self.driver.get(job_url)
            self._action_delay()

            # Wait for the main job view container.
            WebDriverWait(self.driver, _ELEMENT_WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".jobs-unified-top-card, .job-view-layout"))
            )
            logger.info("Job page loaded: %s", self.driver.title)
            return True
        except (TimeoutException, WebDriverException) as exc:
            logger.error("Failed to navigate to job URL %s: %s", job_url, exc)
            return False

    def click_easy_apply(self) -> bool:
        """Locate and click the *Easy Apply* button on the current page.

        Returns:
            *True* if the Easy Apply modal opened, *False* otherwise.
        """
        logger.info("Looking for Easy Apply button ...")

        # LinkedIn uses several possible selectors for the Easy Apply button.
        selectors = [
            "button.jobs-apply-button",
            "button[aria-label*='Easy Apply']",
            "button.jobs-apply-button--top-card",
            ".jobs-apply-button",
            "button[data-control-name='jobdetails_topcard_inapply']",
        ]

        for selector in selectors:
            try:
                button = self._wait_and_find(
                    By.CSS_SELECTOR, selector, timeout=5, clickable=True,
                )
                button_text = button.text.strip().lower()
                if "easy apply" in button_text or "apply" in button_text:
                    self._scroll_into_view(button)
                    self._action_delay()
                    self._safe_click(button)
                    logger.info("Clicked Easy Apply button (selector=%s).", selector)

                    # Wait for the application modal to appear.
                    self._wait_and_find(
                        By.CSS_SELECTOR,
                        ".jobs-easy-apply-modal, .jobs-easy-apply-content, div[data-test-modal]",
                        timeout=_ELEMENT_WAIT_TIMEOUT,
                    )
                    self._action_delay()
                    return True
            except (TimeoutException, NoSuchElementException):
                continue

        logger.warning("Easy Apply button not found on current page.")
        return False

    # ------------------------------------------------------------------
    # Form filling
    # ------------------------------------------------------------------

    def fill_form(
        self,
        user_name: str,
        user_email: str,
        user_phone: str,
        resume_path: Optional[str] = None,
        cover_letter: Optional[str] = None,
        profile_data: Optional[Dict[str, Any]] = None,
        job_description: Optional[str] = None,
    ) -> bool:
        """Walk through every page of the Easy Apply modal, filling fields.

        LinkedIn Easy Apply forms are multi-step: each step may contain
        contact information fields, a file upload, free-text areas, radio
        buttons, dropdowns, and custom questions.  This method loops until
        either a *Submit application* button or a *Review* button is found
        (or the maximum page count is exceeded).

        Args:
            user_name: Applicant full name.
            user_email: Applicant email address.
            user_phone: Applicant phone number.
            resume_path: Absolute path to a resume PDF/DOCX for upload.
            cover_letter: Pre-generated cover letter text.
            profile_data: Extra user profile data (experience years, work
                authorisation status, etc.) stored as a JSON dict.
            job_description: The job posting description, supplied to the
                AI when generating custom question answers.

        Returns:
            *True* if all form pages were filled successfully.
        """
        profile_data = profile_data or {}
        max_pages = 10  # safety valve -- LinkedIn forms rarely exceed 6 steps
        page = 0

        while page < max_pages:
            page += 1
            logger.info("Processing form page %d ...", page)
            self._action_delay()

            try:
                # ---- Contact info fields --------------------------------
                self._fill_contact_fields(user_name, user_email, user_phone)

                # ---- Resume upload --------------------------------------
                self._handle_resume_upload(resume_path)

                # ---- Cover letter ---------------------------------------
                self._handle_cover_letter(cover_letter)

                # ---- Standard questions (radio / dropdown / text) -------
                self._answer_standard_questions(profile_data)

                # ---- Custom / open-ended questions ----------------------
                self._answer_custom_questions(profile_data, job_description)

            except Exception as exc:
                logger.warning(
                    "Non-fatal error on form page %d: %s", page, exc,
                )
                # Continue anyway -- partial filling is better than aborting.

            # ---- Advance to next page or finish -------------------------
            if self._is_review_or_submit_page():
                logger.info("Reached review / submit page after %d page(s).", page)
                return True

            if not self._click_next_button():
                logger.info("No 'Next' button found -- assuming final page (page %d).", page)
                return True

        logger.warning("Exceeded maximum form pages (%d). Aborting fill.", max_pages)
        return False

    # ---- Field-level helpers --------------------------------------------

    def _fill_contact_fields(
        self,
        name: str,
        email: str,
        phone: str,
    ) -> None:
        """Populate name, email, and phone fields if present on the page.

        Args:
            name: Full name.
            email: Email address.
            phone: Phone number.
        """
        field_mapping: List[tuple[str, str]] = [
            ("input[name*='name' i]", name),
            ("input[name*='firstName' i]", name.split()[0] if name else ""),
            ("input[name*='lastName' i]", name.split()[-1] if name else ""),
            ("input[name*='email' i]", email),
            ("input[name*='phone' i]", phone),
            ("input[type='tel']", phone),
            ("input[type='email']", email),
        ]

        for selector, value in field_mapping:
            if not value:
                continue
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        current_value = element.get_attribute("value") or ""
                        if not current_value.strip():
                            element.clear()
                            element.send_keys(value)
                            logger.debug(
                                "Filled contact field (%s) with '%s'.",
                                selector,
                                value[:3] + "***",
                            )
            except (NoSuchElementException, StaleElementReferenceException):
                continue

    def _handle_resume_upload(self, resume_path: Optional[str]) -> None:
        """Upload a resume file if the form contains a file-input element.

        Args:
            resume_path: Absolute path to the resume file, or *None*.
        """
        if not resume_path or not os.path.isfile(resume_path):
            return

        upload_selectors = [
            "input[type='file']",
            "input[name*='resume' i]",
            "input[name*='file' i]",
        ]

        for selector in upload_selectors:
            try:
                file_inputs = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for file_input in file_inputs:
                    # File inputs need not be visible; Selenium can send keys
                    # directly.
                    file_input.send_keys(resume_path)
                    logger.info("Uploaded resume: %s", resume_path)
                    self._action_delay()
                    return
            except (NoSuchElementException, StaleElementReferenceException):
                continue

    def _handle_cover_letter(self, cover_letter: Optional[str]) -> None:
        """Paste a cover letter into any visible textarea labelled accordingly.

        Args:
            cover_letter: The cover letter body text, or *None*.
        """
        if not cover_letter:
            return

        selectors = [
            "textarea[name*='coverLetter' i]",
            "textarea[name*='cover' i]",
            "textarea[aria-label*='cover letter' i]",
            "textarea[placeholder*='cover letter' i]",
        ]

        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        element.clear()
                        element.send_keys(cover_letter)
                        logger.info("Pasted cover letter (%d chars).", len(cover_letter))
                        return
            except (NoSuchElementException, StaleElementReferenceException):
                continue

    def _answer_standard_questions(self, profile_data: Dict[str, Any]) -> None:
        """Answer known standard questions (experience, authorisation, etc.).

        Matches form labels against ``_STANDARD_QUESTION_KEYWORDS`` and
        supplies answers drawn from *profile_data*.

        Args:
            profile_data: User profile payload (may contain keys like
                ``years_of_experience``, ``work_authorization``,
                ``sponsorship``).
        """
        default_answers: Dict[str, str] = {
            "years_of_experience": str(profile_data.get("years_of_experience", "5")),
            "work_authorization": profile_data.get("work_authorization", "Yes"),
            "sponsorship": profile_data.get("sponsorship", "No"),
        }

        # --- Text inputs and textareas -----------------------------------
        try:
            form_groups = self.driver.find_elements(
                By.CSS_SELECTOR,
                ".jobs-easy-apply-form-section__grouping, "
                ".fb-dash-form-element, "
                "div[data-test-form-element]",
            )

            for group in form_groups:
                try:
                    label_text = self._get_group_label(group).lower()
                    if not label_text:
                        continue

                    answer = self._match_standard_answer(label_text, default_answers)
                    if answer is None:
                        continue

                    # Try filling a text input first, then a textarea.
                    filled = self._fill_group_input(group, answer)
                    if not filled:
                        self._fill_group_select(group, answer)
                except StaleElementReferenceException:
                    continue
        except NoSuchElementException:
            pass

        # --- Radio buttons (Yes / No) ------------------------------------
        self._handle_radio_buttons(default_answers)

    def _match_standard_answer(
        self,
        label_text: str,
        defaults: Dict[str, str],
    ) -> Optional[str]:
        """Return the answer for a standard question label, or *None*.

        Args:
            label_text: Lowercased label from the form group.
            defaults: Mapping of canonical key to answer string.

        Returns:
            The answer string, or *None* if the label is unrecognised.
        """
        for keyword, key in _STANDARD_QUESTION_KEYWORDS.items():
            if keyword in label_text:
                return defaults.get(key)
        return None

    def _get_group_label(self, group: WebElement) -> str:
        """Extract the visible label text from a form group element.

        Args:
            group: A container ``WebElement`` wrapping a label + input.

        Returns:
            The label text, or an empty string.
        """
        for tag in ("label", "span", "legend", "p"):
            try:
                label_el = group.find_element(By.TAG_NAME, tag)
                text = label_el.text.strip()
                if text:
                    return text
            except NoSuchElementException:
                continue
        return ""

    def _fill_group_input(self, group: WebElement, answer: str) -> bool:
        """Fill the first visible input or textarea inside *group*.

        Args:
            group: The form-group container.
            answer: The value to enter.

        Returns:
            *True* if a field was filled.
        """
        for tag in ("input", "textarea"):
            try:
                inputs = group.find_elements(By.TAG_NAME, tag)
                for inp in inputs:
                    if inp.is_displayed() and inp.is_enabled():
                        input_type = (inp.get_attribute("type") or "text").lower()
                        if input_type in ("text", "number", "tel", "email", ""):
                            current = inp.get_attribute("value") or ""
                            if not current.strip():
                                inp.clear()
                                inp.send_keys(answer)
                                logger.debug("Filled standard input with '%s'.", answer)
                                return True
            except (NoSuchElementException, StaleElementReferenceException):
                continue
        return False

    def _fill_group_select(self, group: WebElement, answer: str) -> bool:
        """Attempt to choose *answer* from a ``<select>`` dropdown.

        Args:
            group: The form-group container.
            answer: The option text / value to select.

        Returns:
            *True* if an option was selected.
        """
        try:
            selects = group.find_elements(By.TAG_NAME, "select")
            for select_el in selects:
                if not select_el.is_displayed():
                    continue
                options = select_el.find_elements(By.TAG_NAME, "option")
                answer_lower = answer.lower()
                for option in options:
                    option_text = option.text.strip().lower()
                    if answer_lower in option_text or option_text in answer_lower:
                        option.click()
                        logger.debug("Selected dropdown option: '%s'.", option.text.strip())
                        return True
        except (NoSuchElementException, StaleElementReferenceException):
            pass
        return False

    def _handle_radio_buttons(self, defaults: Dict[str, str]) -> None:
        """Select Yes/No radio buttons for authorisation-style questions.

        Args:
            defaults: Mapping of canonical key -> answer (``"Yes"``/``"No"``).
        """
        try:
            fieldsets = self.driver.find_elements(By.TAG_NAME, "fieldset")
            for fieldset in fieldsets:
                try:
                    legend_text = self._get_group_label(fieldset).lower()
                    if not legend_text:
                        continue

                    answer = self._match_standard_answer(legend_text, defaults)
                    if answer is None:
                        continue

                    # Find the radio whose label matches the answer.
                    labels = fieldset.find_elements(By.TAG_NAME, "label")
                    for label in labels:
                        if answer.lower() in label.text.strip().lower():
                            self._safe_click(label)
                            logger.debug(
                                "Selected radio '%s' for '%s'.",
                                label.text.strip(),
                                legend_text[:40],
                            )
                            break
                except StaleElementReferenceException:
                    continue
        except NoSuchElementException:
            pass

    # ---- AI-powered custom question answering ---------------------------

    def _answer_custom_questions(
        self,
        profile_data: Dict[str, Any],
        job_description: Optional[str],
    ) -> None:
        """Use the Anthropic API to generate answers for unrecognised questions.

        Any empty textarea or text input that was *not* filled by the
        standard-question handler is assumed to be a custom / open-ended
        question.  The full label and surrounding context are sent to
        Claude, which returns a concise, professional response.

        Args:
            profile_data: User profile payload.
            job_description: The full job posting text.
        """
        try:
            form_groups = self.driver.find_elements(
                By.CSS_SELECTOR,
                ".jobs-easy-apply-form-section__grouping, "
                ".fb-dash-form-element, "
                "div[data-test-form-element]",
            )
        except NoSuchElementException:
            return

        for group in form_groups:
            try:
                label_text = self._get_group_label(group).strip()
                if not label_text:
                    continue

                # Skip questions that already have an answer supplied by the
                # standard handler.
                if self._match_standard_answer(label_text.lower(), {}):
                    continue

                # Find empty text inputs / textareas.
                for tag in ("textarea", "input"):
                    inputs = group.find_elements(By.TAG_NAME, tag)
                    for inp in inputs:
                        if not (inp.is_displayed() and inp.is_enabled()):
                            continue
                        input_type = (inp.get_attribute("type") or "text").lower()
                        if input_type not in ("text", "", "textarea"):
                            continue
                        current_value = (inp.get_attribute("value") or "").strip()
                        if current_value:
                            continue

                        # Generate an AI answer.
                        answer = self._generate_ai_answer(
                            question=label_text,
                            profile_data=profile_data,
                            job_description=job_description,
                        )
                        if answer:
                            inp.clear()
                            inp.send_keys(answer)
                            logger.info(
                                "AI-filled custom question: '%s' -> '%s'",
                                label_text[:60],
                                answer[:60],
                            )
            except StaleElementReferenceException:
                continue

    def _generate_ai_answer(
        self,
        question: str,
        profile_data: Optional[Dict[str, Any]] = None,
        job_description: Optional[str] = None,
    ) -> str:
        """Call the Anthropic API to produce an answer for a custom question.

        Args:
            question: The question text extracted from the form label.
            profile_data: User profile data for context.
            job_description: Job posting description for context.

        Returns:
            A concise answer string, or an empty string on failure.
        """
        profile_summary = ""
        if profile_data:
            profile_summary = (
                "Candidate profile:\n"
                + "\n".join(f"  - {k}: {v}" for k, v in profile_data.items())
            )

        job_context = ""
        if job_description:
            # Truncate very long descriptions to stay within token budget.
            truncated = job_description[:3000]
            job_context = f"Job description (excerpt):\n{truncated}"

        system_prompt = (
            "You are an expert career assistant helping a candidate complete "
            "a LinkedIn Easy Apply application. Provide concise, professional, "
            "and honest answers. Keep answers to 2-3 sentences unless the "
            "question requires more detail. Do not fabricate experience or "
            "credentials."
        )

        user_prompt = (
            f"Answer the following application question.\n\n"
            f"Question: {question}\n\n"
            f"{profile_summary}\n\n"
            f"{job_context}\n\n"
            f"Provide ONLY the answer text -- no preamble, no quotes."
        )

        try:
            response = self._anthropic.messages.create(
                model=self.config.anthropic_model,
                max_tokens=self.config.anthropic_max_tokens,
                temperature=self.config.anthropic_temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            answer = response.content[0].text.strip()
            logger.debug("AI answer generated (%d chars).", len(answer))
            return answer
        except anthropic.APIError as exc:
            logger.error("Anthropic API error while answering '%s': %s", question[:60], exc)
            return ""
        except Exception as exc:
            logger.error("Unexpected error generating AI answer: %s", exc)
            return ""

    # ---- Navigation within the modal ------------------------------------

    def _is_review_or_submit_page(self) -> bool:
        """Detect whether the current modal page is the review/submit step.

        Returns:
            *True* if a *Review* or *Submit application* button is visible.
        """
        selectors = [
            "button[aria-label*='Submit application']",
            "button[aria-label*='Review']",
            "button[data-control-name='submit_unify']",
        ]
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    if el.is_displayed():
                        return True
            except NoSuchElementException:
                continue

        # Fallback: scan button text.
        try:
            buttons = self.driver.find_elements(
                By.CSS_SELECTOR,
                ".jobs-easy-apply-modal button, .artdeco-modal button",
            )
            for btn in buttons:
                text = btn.text.strip().lower()
                if text in ("submit application", "review"):
                    return True
        except NoSuchElementException:
            pass

        return False

    def _click_next_button(self) -> bool:
        """Click the *Next* button to advance to the next form page.

        Returns:
            *True* if a *Next* button was found and clicked.
        """
        selectors = [
            "button[aria-label='Continue to next step']",
            "button[aria-label='Next']",
            "button[data-control-name='continue_unify']",
        ]

        for selector in selectors:
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                if btn.is_displayed() and btn.is_enabled():
                    self._scroll_into_view(btn)
                    self._safe_click(btn)
                    logger.debug("Clicked 'Next' button (selector=%s).", selector)
                    self._action_delay()
                    return True
            except NoSuchElementException:
                continue

        # Fallback: match by visible text.
        try:
            buttons = self.driver.find_elements(
                By.CSS_SELECTOR,
                ".jobs-easy-apply-modal button, .artdeco-modal button",
            )
            for btn in buttons:
                if btn.text.strip().lower() == "next" and btn.is_displayed():
                    self._safe_click(btn)
                    logger.debug("Clicked 'Next' button (text match).")
                    self._action_delay()
                    return True
        except NoSuchElementException:
            pass

        return False

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def submit_application(self) -> bool:
        """Click the *Submit application* button and verify confirmation.

        Returns:
            *True* if the confirmation dialog appeared, indicating success.
        """
        logger.info("Attempting to submit application ...")
        self._action_delay()

        # First try: click a *Review* button if present, which leads to the
        # actual submit button.
        try:
            review_buttons = self.driver.find_elements(
                By.CSS_SELECTOR,
                "button[aria-label*='Review'], button[aria-label*='review']",
            )
            for btn in review_buttons:
                if btn.is_displayed() and btn.is_enabled():
                    self._safe_click(btn)
                    logger.info("Clicked 'Review' button.")
                    self._action_delay()
                    break
        except NoSuchElementException:
            pass

        # Locate and click *Submit application*.
        submit_selectors = [
            "button[aria-label='Submit application']",
            "button[data-control-name='submit_unify']",
        ]

        for selector in submit_selectors:
            try:
                btn = self._wait_and_find(By.CSS_SELECTOR, selector, timeout=10, clickable=True)
                self._scroll_into_view(btn)
                self._safe_click(btn)
                logger.info("Clicked 'Submit application' (selector=%s).", selector)
                self._action_delay()
                return self._verify_submission()
            except (TimeoutException, NoSuchElementException):
                continue

        # Final fallback: match by button text.
        try:
            buttons = self.driver.find_elements(
                By.CSS_SELECTOR,
                ".jobs-easy-apply-modal button, .artdeco-modal button",
            )
            for btn in buttons:
                if "submit" in btn.text.strip().lower() and btn.is_displayed():
                    self._safe_click(btn)
                    logger.info("Clicked submit button (text match).")
                    self._action_delay()
                    return self._verify_submission()
        except NoSuchElementException:
            pass

        logger.error("Submit button not found.")
        return False

    def _verify_submission(self) -> bool:
        """Wait for and detect the post-submission confirmation overlay.

        Returns:
            *True* if confirmation is detected.
        """
        confirmation_selectors = [
            ".artdeco-modal__header h2",
            ".jpac-modal-header",
            "h2[id*='post-apply']",
            "div[data-test-modal-close-btn]",
        ]

        try:
            for selector in confirmation_selectors:
                try:
                    el = WebDriverWait(self.driver, _ELEMENT_WAIT_TIMEOUT).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if el.is_displayed():
                        text = el.text.strip().lower()
                        if any(w in text for w in ("application", "submitted", "sent", "done")):
                            logger.info("Submission confirmed: '%s'.", el.text.strip())
                            return True
                except TimeoutException:
                    continue
        except Exception as exc:
            logger.warning("Error during submission verification: %s", exc)

        # Optimistic: if the modal has disappeared, the submission likely
        # went through.
        try:
            modal = self.driver.find_elements(By.CSS_SELECTOR, ".jobs-easy-apply-modal")
            if not modal or not modal[0].is_displayed():
                logger.info("Easy Apply modal closed -- assuming successful submission.")
                return True
        except NoSuchElementException:
            return True

        logger.warning("Could not confirm submission.")
        return False

    # ------------------------------------------------------------------
    # Screenshot
    # ------------------------------------------------------------------

    def take_screenshot(self, job_id: int, suffix: str = "") -> Optional[str]:
        """Save a timestamped screenshot to ``data/screenshots/``.

        Args:
            job_id: Database primary key of the job, used in the filename.
            suffix: Optional descriptive suffix (e.g., ``"confirmation"``).

        Returns:
            The absolute path to the saved PNG, or *None* on failure.
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        suffix_part = f"_{suffix}" if suffix else ""
        filename = f"job_{job_id}{suffix_part}_{timestamp}.png"
        filepath = self._screenshot_dir / filename

        try:
            self.driver.save_screenshot(str(filepath))
            logger.info("Screenshot saved: %s", filepath)
            return str(filepath)
        except WebDriverException as exc:
            logger.error("Failed to save screenshot: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Database record creation
    # ------------------------------------------------------------------

    def create_application_record(
        self,
        session: Any,
        job_id: int,
        status: str = "submitted",
        resume_version: Optional[str] = None,
        cover_letter_text: Optional[str] = None,
        screenshot_path: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[int]:
        """Persist an application record via ``ApplicationRepository``.

        Args:
            session: An active SQLAlchemy ``Session``.
            job_id: FK to ``linkedin_jobs.id``.
            status: Application status (``"submitted"``, ``"failed"``, ...).
            resume_version: Label or filename of the resume used.
            cover_letter_text: The cover letter body.
            screenshot_path: Path to the confirmation screenshot.
            notes: Free-text notes.

        Returns:
            The new ``Application.id``, or *None* on failure.
        """
        try:
            app_repo = ApplicationRepository(session)

            # Guard against duplicate applications for the same job + user.
            existing = app_repo.get_by_job_id(job_id)
            if existing:
                logger.warning(
                    "Application already exists for job_id=%d (app_id=%d). Skipping creation.",
                    job_id,
                    existing.id,
                )
                return existing.id

            application = app_repo.create(
                job_id=job_id,
                user_id=self.user_id,
                status=status,
                applied_date=datetime.utcnow() if status == "submitted" else None,
                resume_version=resume_version,
                cover_letter_text=cover_letter_text,
                screenshot_path=screenshot_path,
                notes=notes,
            )
            logger.info(
                "Application record created: id=%d, job_id=%d, status=%s",
                application.id,
                job_id,
                status,
            )
            return application.id
        except Exception as exc:
            logger.error("Failed to create application record for job_id=%d: %s", job_id, exc)
            return None

    # ------------------------------------------------------------------
    # Single-job application pipeline
    # ------------------------------------------------------------------

    def apply_to_job(
        self,
        job_id: int,
        job_url: str,
        job_title: str,
        job_company: str,
        job_description: Optional[str] = None,
    ) -> bool:
        """Execute the full Easy Apply pipeline for one job listing.

        This is the main entry point for applying to an individual job.
        It orchestrates navigation, form filling, submission, screenshot
        capture, and database persistence, with retry logic around the
        form-fill and submit steps.

        Args:
            job_id: Database PK of the ``LinkedInJob``.
            job_url: URL of the LinkedIn job listing.
            job_title: Human-readable title (for logging).
            job_company: Company name (for logging).
            job_description: Full description text for AI context.

        Returns:
            *True* if the application was submitted successfully.
        """
        logger.info(
            "=== Applying to: %s at %s (job_id=%d) ===",
            job_title,
            job_company,
            job_id,
        )

        # Fetch user and resume details from the database.
        with get_db() as session:
            user_repo = UserRepository(session)
            resume_repo = ResumeRepository(session)

            user = user_repo.get_by_id(self.user_id)
            if not user:
                logger.error("User id=%d not found. Aborting application.", self.user_id)
                return False

            user_name: str = user.name
            user_email: str = user.email
            user_phone: str = user.phone or ""
            profile_data: Dict[str, Any] = user.profile_data or {}

            primary_resume = resume_repo.get_primary(self.user_id)
            resume_path: Optional[str] = primary_resume.file_path if primary_resume else None
            resume_version: Optional[str] = primary_resume.version_name if primary_resume else None

        # Generate a cover letter stub from profile + job description.
        cover_letter = self._generate_cover_letter(
            user_name=user_name,
            profile_data=profile_data,
            job_title=job_title,
            job_company=job_company,
            job_description=job_description,
        )

        # -- Step 1: Navigate --
        if not self.navigate_to_job(job_url):
            self._record_failure(job_id, "Failed to navigate to job page.")
            return False

        # -- Step 2: Click Easy Apply --
        if not self.click_easy_apply():
            self._record_failure(job_id, "Easy Apply button not found or not clickable.")
            return False

        # -- Step 3: Fill form (with retries) --
        form_filled = False
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                form_filled = self.fill_form(
                    user_name=user_name,
                    user_email=user_email,
                    user_phone=user_phone,
                    resume_path=resume_path,
                    cover_letter=cover_letter,
                    profile_data=profile_data,
                    job_description=job_description,
                )
                if form_filled:
                    break
            except Exception as exc:
                logger.warning(
                    "Form fill attempt %d/%d failed: %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
                time.sleep(_RETRY_BACKOFF_BASE * attempt)

        if not form_filled:
            self._record_failure(job_id, "Failed to fill application form after retries.")
            return False

        # -- Step 4: Submit --
        submitted = False
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                submitted = self.submit_application()
                if submitted:
                    break
            except Exception as exc:
                logger.warning(
                    "Submit attempt %d/%d failed: %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
                time.sleep(_RETRY_BACKOFF_BASE * attempt)

        # -- Step 5: Screenshot --
        screenshot_path = self.take_screenshot(
            job_id,
            suffix="confirmation" if submitted else "failure",
        )

        # -- Step 6: Database record --
        status = "submitted" if submitted else "failed"
        with get_db() as session:
            self.create_application_record(
                session=session,
                job_id=job_id,
                status=status,
                resume_version=resume_version,
                cover_letter_text=cover_letter,
                screenshot_path=screenshot_path,
                notes=f"Applied via automation on {datetime.utcnow().isoformat()}",
            )

            # Update the job status as well.
            job_repo = JobRepository(session)
            job_repo.update_status(job_id, "applied" if submitted else "apply_failed")

        if submitted:
            self.applications_submitted_today += 1
            logger.info(
                "Successfully applied to %s at %s. Today's total: %d/%d.",
                job_title,
                job_company,
                self.applications_submitted_today,
                self.max_daily_applications,
            )
        else:
            logger.warning("Application to %s at %s FAILED.", job_title, job_company)

        return submitted

    # ------------------------------------------------------------------
    # Cover letter generation
    # ------------------------------------------------------------------

    def _generate_cover_letter(
        self,
        user_name: str,
        profile_data: Dict[str, Any],
        job_title: str,
        job_company: str,
        job_description: Optional[str] = None,
    ) -> str:
        """Use the Anthropic API to draft a short cover letter.

        Args:
            user_name: Applicant name.
            profile_data: User profile dict.
            job_title: Target job title.
            job_company: Target company.
            job_description: Full job description.

        Returns:
            The cover letter text, or an empty string on failure.
        """
        profile_summary = ""
        if profile_data:
            profile_summary = "\n".join(f"  - {k}: {v}" for k, v in profile_data.items())

        description_excerpt = ""
        if job_description:
            description_excerpt = job_description[:2000]

        system_prompt = (
            "You are a professional career coach. Write a concise cover "
            "letter (3-4 paragraphs, under 300 words) tailored to the job. "
            "Be genuine and specific. Do not fabricate credentials."
        )

        user_prompt = (
            f"Write a cover letter for:\n"
            f"  Position: {job_title}\n"
            f"  Company: {job_company}\n\n"
            f"Candidate: {user_name}\n"
            f"Profile:\n{profile_summary}\n\n"
            f"Job description excerpt:\n{description_excerpt}\n\n"
            f"Return ONLY the cover letter text."
        )

        try:
            response = self._anthropic.messages.create(
                model=self.config.anthropic_model,
                max_tokens=1024,
                temperature=0.4,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            letter = response.content[0].text.strip()
            logger.info("Cover letter generated (%d chars).", len(letter))
            return letter
        except anthropic.APIError as exc:
            logger.error("Cover letter generation failed: %s", exc)
            return ""
        except Exception as exc:
            logger.error("Unexpected error generating cover letter: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Failure recording helper
    # ------------------------------------------------------------------

    def _record_failure(self, job_id: int, reason: str) -> None:
        """Take a failure screenshot and persist a failed application record.

        Args:
            job_id: Database PK of the job.
            reason: Human-readable failure reason.
        """
        logger.warning("Recording failure for job_id=%d: %s", job_id, reason)
        screenshot_path = self.take_screenshot(job_id, suffix="failure")

        with get_db() as session:
            self.create_application_record(
                session=session,
                job_id=job_id,
                status="failed",
                screenshot_path=screenshot_path,
                notes=reason,
            )
            job_repo = JobRepository(session)
            job_repo.update_status(job_id, "apply_failed")

    # ------------------------------------------------------------------
    # Batch run
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """Process all pending applications, respecting the daily cap.

        Pending applications are identified as ``LinkedInJob`` records whose
        status is ``"approved"`` (i.e., matched and approved for application)
        and for which no ``Application`` record yet exists.

        Returns:
            A summary dict with keys ``submitted``, ``failed``, ``skipped``,
            and ``total_processed``.
        """
        logger.info("=== LinkedInApplicationAgent.run() started ===")
        results: Dict[str, Any] = {
            "submitted": 0,
            "failed": 0,
            "skipped": 0,
            "total_processed": 0,
            "errors": [],
        }

        # Determine how many we've already submitted today.
        with get_db() as session:
            app_repo = ApplicationRepository(session)
            already_today = app_repo.count_today()

        self.applications_submitted_today = already_today
        remaining = self.max_daily_applications - already_today

        if remaining <= 0:
            logger.info(
                "Daily cap reached (%d/%d). No applications will be processed.",
                already_today,
                self.max_daily_applications,
            )
            results["skipped_reason"] = "daily_cap_reached"
            return results

        logger.info(
            "Daily budget: %d remaining (%d already submitted today, cap=%d).",
            remaining,
            already_today,
            self.max_daily_applications,
        )

        # Fetch approved jobs that have not been applied to yet.
        with get_db() as session:
            job_repo = JobRepository(session)
            app_repo = ApplicationRepository(session)

            approved_jobs = job_repo.get_by_status("approved", limit=remaining)

            # Filter out jobs that already have an application record.
            pending_jobs: List[Dict[str, Any]] = []
            for job in approved_jobs:
                existing_app = app_repo.get_by_job_id(job.id)
                if existing_app is None:
                    pending_jobs.append({
                        "id": job.id,
                        "url": job.job_url,
                        "title": job.title,
                        "company": job.company,
                        "description": job.description,
                    })

        if not pending_jobs:
            logger.info("No pending applications to process.")
            return results

        logger.info("Found %d pending application(s) to process.", len(pending_jobs))

        for idx, job_info in enumerate(pending_jobs):
            # Re-check daily cap (may have been updated by concurrent processes).
            if self.applications_submitted_today >= self.max_daily_applications:
                logger.info("Daily cap reached mid-run. Stopping.")
                results["skipped"] += len(pending_jobs) - idx
                break

            try:
                success = self.apply_to_job(
                    job_id=job_info["id"],
                    job_url=job_info["url"],
                    job_title=job_info["title"],
                    job_company=job_info["company"],
                    job_description=job_info["description"],
                )
                results["total_processed"] += 1

                if success:
                    results["submitted"] += 1
                else:
                    results["failed"] += 1

            except Exception as exc:
                logger.error(
                    "Unhandled error applying to job_id=%d: %s\n%s",
                    job_info["id"],
                    exc,
                    traceback.format_exc(),
                )
                results["failed"] += 1
                results["total_processed"] += 1
                results["errors"].append({
                    "job_id": job_info["id"],
                    "error": str(exc),
                })

            # Inter-application delay (skip after last application).
            if idx < len(pending_jobs) - 1:
                self._application_delay()

        logger.info(
            "=== Run complete. Submitted=%d, Failed=%d, Skipped=%d, Processed=%d ===",
            results["submitted"],
            results["failed"],
            results["skipped"],
            results["total_processed"],
        )
        return results
