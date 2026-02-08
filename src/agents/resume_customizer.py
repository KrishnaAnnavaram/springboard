"""AI-powered resume customization and cover letter generation agent.

Uses the Anthropic Claude API to tailor resumes and generate cover letters
for specific job postings, optimizing for ATS compatibility and relevance.
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from src.database.connection import get_db
from src.database.repositories.job_repository import JobRepository
from src.database.repositories.resume_repository import ResumeRepository
from src.database.repositories.user_repository import UserRepository
from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ResumeCustomizerAgent:
    """Agent that customizes resumes and generates cover letters using Claude.

    This agent processes matched job postings by tailoring the user's base
    resume to each position and generating a personalized cover letter.
    Results are persisted to the database for downstream application workflows.

    Attributes:
        config: Application configuration singleton.
        client: Anthropic API client instance.
        model: Claude model identifier from config.
        max_tokens: Maximum token limit for API responses.
        temperature: Sampling temperature for generation.
        max_retries: Number of retry attempts for API calls.
        backoff_factor: Multiplier for exponential backoff between retries.
    """

    # Status constants for job processing pipeline
    STATUS_MATCHED = "matched"
    STATUS_RESUME_CUSTOMIZED = "resume_customized"
    STATUS_CUSTOMIZATION_FAILED = "customization_failed"

    def __init__(self) -> None:
        """Initialize the agent with API client and configuration."""
        self.config = Config()
        self.client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
        self.model: str = self.config.anthropic_model
        self.max_tokens: int = self.config.anthropic_max_tokens
        self.temperature: float = self.config.anthropic_temperature

        automation = self.config.automation
        self.max_retries: int = automation.get("retry_attempts", 3)
        self.backoff_factor: int = automation.get("retry_backoff_factor", 2)

        logger.info(
            "ResumeCustomizerAgent initialized (model=%s, max_retries=%d)",
            self.model,
            self.max_retries,
        )

    # ------------------------------------------------------------------
    # Core public API
    # ------------------------------------------------------------------

    def customize_resume(
        self, base_resume_text: str, job: Dict[str, Any]
    ) -> str:
        """Customize a resume for a specific job posting.

        Analyzes the job requirements, extracts keywords, reorders
        experience sections by relevance, emphasizes matching skills,
        and optimizes formatting for ATS parsing.

        Args:
            base_resume_text: The user's original/primary resume content.
            job: Dictionary with job details. Expected keys include
                ``title``, ``company``, ``description``, ``requirements``,
                ``location``, ``experience_level``, and ``job_type``.

        Returns:
            The customized resume as plain text.

        Raises:
            RuntimeError: If all retry attempts are exhausted.
        """
        title = job.get("title", "Unknown Position")
        company = job.get("company", "Unknown Company")

        logger.info("Customizing resume for '%s' at %s", title, company)

        system_prompt = self._build_resume_system_prompt()
        user_prompt = self._build_resume_user_prompt(base_resume_text, job)

        customized_text = self._call_api(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            purpose=f"resume customization for {title} at {company}",
        )

        logger.info(
            "Resume customized successfully for '%s' at %s (%d chars)",
            title,
            company,
            len(customized_text),
        )
        return customized_text

    def generate_cover_letter(
        self, job: Dict[str, Any], profile: Dict[str, Any]
    ) -> str:
        """Generate a personalized cover letter for a job posting.

        Creates a professional 250-400 word cover letter that connects
        the candidate's background to the specific role and company.

        Args:
            job: Dictionary with job details (same schema as
                :meth:`customize_resume`).
            profile: Dictionary with user profile data. Expected keys
                include ``name``, ``email``, ``phone``, ``skills``,
                ``experience``, and ``summary``.

        Returns:
            The generated cover letter as plain text.

        Raises:
            RuntimeError: If all retry attempts are exhausted.
        """
        title = job.get("title", "Unknown Position")
        company = job.get("company", "Unknown Company")

        logger.info("Generating cover letter for '%s' at %s", title, company)

        system_prompt = self._build_cover_letter_system_prompt()
        user_prompt = self._build_cover_letter_user_prompt(job, profile)

        cover_letter = self._call_api(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            purpose=f"cover letter for {title} at {company}",
        )

        logger.info(
            "Cover letter generated for '%s' at %s (%d chars)",
            title,
            company,
            len(cover_letter),
        )
        return cover_letter

    def run(self) -> List[Dict[str, Any]]:
        """Process all matched jobs that need resume customization.

        Retrieves matched jobs from the database, customizes the user's
        primary resume for each, generates a cover letter, and stores
        both artifacts. Jobs are transitioned to ``resume_customized``
        status on success or ``customization_failed`` on error.

        Returns:
            A list of result dictionaries, one per processed job, each
            containing ``job_id``, ``job_title``, ``company``,
            ``resume_id`` (or ``None``), ``cover_letter`` (or ``None``),
            and ``status``.
        """
        logger.info("Starting resume customization run")
        results: List[Dict[str, Any]] = []

        with get_db() as session:
            job_repo = JobRepository(session)
            resume_repo = ResumeRepository(session)
            user_repo = UserRepository(session)

            # Resolve the default user and their primary resume
            user = user_repo.get_default_user()
            if user is None:
                logger.error("No default user found; aborting run")
                return results

            primary_resume = resume_repo.get_primary(user.id)
            if primary_resume is None or not primary_resume.content_text:
                logger.error(
                    "No primary resume with content found for user %d; aborting run",
                    user.id,
                )
                return results

            base_resume_text: str = primary_resume.content_text

            # Build user profile dict from the User model
            profile = self._build_profile_dict(user)

            # Fetch matched jobs awaiting customization
            jobs = job_repo.get_by_status(self.STATUS_MATCHED)
            if not jobs:
                logger.info("No matched jobs pending customization")
                return results

            logger.info("Processing %d matched jobs for customization", len(jobs))

            for job_model in jobs:
                result = self._process_single_job(
                    job_model=job_model,
                    base_resume_text=base_resume_text,
                    profile=profile,
                    user_id=user.id,
                    job_repo=job_repo,
                    resume_repo=resume_repo,
                    session=session,
                )
                results.append(result)

        logger.info(
            "Resume customization run complete: %d processed, %d succeeded, %d failed",
            len(results),
            sum(1 for r in results if r["status"] == self.STATUS_RESUME_CUSTOMIZED),
            sum(1 for r in results if r["status"] == self.STATUS_CUSTOMIZATION_FAILED),
        )
        return results

    # ------------------------------------------------------------------
    # Internal helpers -- job processing
    # ------------------------------------------------------------------

    def _process_single_job(
        self,
        job_model: Any,
        base_resume_text: str,
        profile: Dict[str, Any],
        user_id: int,
        job_repo: JobRepository,
        resume_repo: ResumeRepository,
        session: Any,
    ) -> Dict[str, Any]:
        """Customize resume and generate cover letter for one job.

        On success the job status is updated to ``resume_customized`` and
        a new :class:`Resume` record is created.  On failure the status
        is set to ``customization_failed``.

        Returns:
            A result dictionary for the processed job.
        """
        job_dict = self._job_model_to_dict(job_model)
        job_id: int = job_model.id
        title: str = job_model.title
        company: str = job_model.company

        result: Dict[str, Any] = {
            "job_id": job_id,
            "job_title": title,
            "company": company,
            "resume_id": None,
            "cover_letter": None,
            "status": self.STATUS_CUSTOMIZATION_FAILED,
        }

        try:
            # --- Customize resume ---
            customized_text = self.customize_resume(base_resume_text, job_dict)

            # --- Generate cover letter ---
            cover_letter = self.generate_cover_letter(job_dict, profile)

            # --- Persist resume version ---
            version_name = (
                f"{title} - {company} "
                f"({datetime.utcnow().strftime('%Y-%m-%d')})"
            )
            new_resume = resume_repo.create(
                user_id=user_id,
                version_name=version_name,
                content_text=customized_text,
                is_primary=False,
            )

            # --- Update job status ---
            job_repo.update_status(job_id, self.STATUS_RESUME_CUSTOMIZED)

            result["resume_id"] = new_resume.id
            result["cover_letter"] = cover_letter
            result["status"] = self.STATUS_RESUME_CUSTOMIZED

            logger.info(
                "Successfully customized resume (id=%d) and cover letter for job %d ('%s' at %s)",
                new_resume.id,
                job_id,
                title,
                company,
            )

        except Exception:
            logger.exception(
                "Failed to customize resume for job %d ('%s' at %s)",
                job_id,
                title,
                company,
            )
            try:
                job_repo.update_status(job_id, self.STATUS_CUSTOMIZATION_FAILED)
            except Exception:
                logger.exception(
                    "Failed to update status to '%s' for job %d",
                    self.STATUS_CUSTOMIZATION_FAILED,
                    job_id,
                )

        return result

    # ------------------------------------------------------------------
    # Internal helpers -- API interaction
    # ------------------------------------------------------------------

    def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        purpose: str,
    ) -> str:
        """Call the Anthropic API with retry and exponential backoff.

        Args:
            system_prompt: The system-level instruction for Claude.
            user_prompt: The user-level message content.
            purpose: Human-readable label for logging (e.g.
                ``"resume customization for SWE at Acme"``).

        Returns:
            The text content of the first response block.

        Raises:
            RuntimeError: When all retry attempts fail.
        """
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "API call attempt %d/%d for %s",
                    attempt,
                    self.max_retries,
                    purpose,
                )

                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )

                text = response.content[0].text
                logger.debug(
                    "API call succeeded on attempt %d for %s "
                    "(input_tokens=%d, output_tokens=%d)",
                    attempt,
                    purpose,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
                return text

            except anthropic.RateLimitError as exc:
                last_exception = exc
                wait = self.backoff_factor ** attempt
                logger.warning(
                    "Rate limited on attempt %d/%d for %s; "
                    "retrying in %ds",
                    attempt,
                    self.max_retries,
                    purpose,
                    wait,
                )
                time.sleep(wait)

            except anthropic.APIStatusError as exc:
                last_exception = exc
                # Do not retry on client errors (4xx) other than 429
                if 400 <= exc.status_code < 500:
                    logger.error(
                        "Non-retryable API error (%d) for %s: %s",
                        exc.status_code,
                        purpose,
                        exc.message,
                    )
                    raise RuntimeError(
                        f"Anthropic API error ({exc.status_code}) during "
                        f"{purpose}: {exc.message}"
                    ) from exc

                wait = self.backoff_factor ** attempt
                logger.warning(
                    "API error (%d) on attempt %d/%d for %s; "
                    "retrying in %ds: %s",
                    exc.status_code,
                    attempt,
                    self.max_retries,
                    purpose,
                    wait,
                    exc.message,
                )
                time.sleep(wait)

            except anthropic.APIConnectionError as exc:
                last_exception = exc
                wait = self.backoff_factor ** attempt
                logger.warning(
                    "Connection error on attempt %d/%d for %s; "
                    "retrying in %ds: %s",
                    attempt,
                    self.max_retries,
                    purpose,
                    wait,
                    exc,
                )
                time.sleep(wait)

        raise RuntimeError(
            f"All {self.max_retries} API attempts exhausted for {purpose}"
        ) from last_exception

    # ------------------------------------------------------------------
    # Internal helpers -- prompt construction
    # ------------------------------------------------------------------

    def _build_resume_system_prompt(self) -> str:
        """Return the system prompt for resume customization."""
        return (
            "You are an expert resume writer and career coach specializing "
            "in ATS-optimized resumes. Your task is to customize a base "
            "resume for a specific job posting.\n\n"
            "Follow these rules strictly:\n"
            "1. KEYWORD OPTIMIZATION: Identify the critical keywords, "
            "skills, and qualifications from the job description and "
            "weave them naturally into the resume.\n"
            "2. EXPERIENCE REORDERING: Reorder bullet points and "
            "experience entries so the most relevant items for this "
            "specific role appear first.\n"
            "3. SKILL EMPHASIS: Promote skills that directly match "
            "the job requirements to prominent positions. Group "
            "matching technical and soft skills near the top.\n"
            "4. ATS FORMATTING: Use simple, clean formatting. Avoid "
            "tables, columns, graphics, headers/footers, and special "
            "characters. Use standard section headings (Experience, "
            "Education, Skills, Projects, Certifications).\n"
            "5. QUANTIFICATION: Where possible, strengthen bullet "
            "points with metrics and quantified achievements.\n"
            "6. TRUTHFULNESS: Never fabricate experience, skills, or "
            "credentials. Only reorganize and rephrase existing content.\n"
            "7. CONCISENESS: Keep the resume to a professional length. "
            "Remove or condense irrelevant details.\n\n"
            "Return ONLY the customized resume text. Do not include "
            "any commentary, explanations, or markdown formatting."
        )

    def _build_resume_user_prompt(
        self, base_resume_text: str, job: Dict[str, Any]
    ) -> str:
        """Construct the user prompt for resume customization."""
        job_section = self._format_job_details(job)

        return (
            f"BASE RESUME:\n"
            f"{'=' * 60}\n"
            f"{base_resume_text}\n"
            f"{'=' * 60}\n\n"
            f"TARGET JOB POSTING:\n"
            f"{'=' * 60}\n"
            f"{job_section}\n"
            f"{'=' * 60}\n\n"
            "Please customize the base resume for this specific job "
            "posting. Analyze the job requirements, extract the key "
            "skills and qualifications, then tailor the resume "
            "accordingly. Reorder experience by relevance, emphasize "
            "matching skills, and optimize for ATS keyword scanning."
        )

    def _build_cover_letter_system_prompt(self) -> str:
        """Return the system prompt for cover letter generation."""
        return (
            "You are an expert career coach and professional writer "
            "specializing in compelling cover letters.\n\n"
            "Write a personalized cover letter following these guidelines:\n"
            "1. LENGTH: 250-400 words. Be concise and impactful.\n"
            "2. STRUCTURE: Opening hook, 1-2 body paragraphs connecting "
            "experience to role, and a confident closing with call to "
            "action.\n"
            "3. PERSONALIZATION: Reference the specific company name, "
            "role title, and details from the job description.\n"
            "4. VALUE PROPOSITION: Focus on what the candidate brings "
            "to the company, not what they want from the job.\n"
            "5. TONE: Professional yet personable. Confident without "
            "being arrogant.\n"
            "6. SPECIFICITY: Include concrete examples and "
            "achievements that relate to the job requirements.\n"
            "7. KEYWORDS: Naturally incorporate relevant keywords "
            "from the job posting.\n\n"
            "Return ONLY the cover letter text. Do not include "
            "commentary, explanations, or markdown formatting. "
            "Do not include placeholder addresses or dates."
        )

    def _build_cover_letter_user_prompt(
        self, job: Dict[str, Any], profile: Dict[str, Any]
    ) -> str:
        """Construct the user prompt for cover letter generation."""
        job_section = self._format_job_details(job)
        profile_section = self._format_profile(profile)

        return (
            f"CANDIDATE PROFILE:\n"
            f"{'=' * 60}\n"
            f"{profile_section}\n"
            f"{'=' * 60}\n\n"
            f"TARGET JOB POSTING:\n"
            f"{'=' * 60}\n"
            f"{job_section}\n"
            f"{'=' * 60}\n\n"
            "Write a personalized cover letter (250-400 words) for "
            "this candidate applying to this specific role. Connect "
            "their experience and skills directly to the job "
            "requirements."
        )

    # ------------------------------------------------------------------
    # Internal helpers -- data formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_job_details(job: Dict[str, Any]) -> str:
        """Format a job dictionary into a readable text block."""
        parts: List[str] = []

        if job.get("title"):
            parts.append(f"Title: {job['title']}")
        if job.get("company"):
            parts.append(f"Company: {job['company']}")
        if job.get("location"):
            parts.append(f"Location: {job['location']}")
        if job.get("job_type"):
            parts.append(f"Job Type: {job['job_type']}")
        if job.get("experience_level"):
            parts.append(f"Experience Level: {job['experience_level']}")
        if job.get("salary_range"):
            parts.append(f"Salary Range: {job['salary_range']}")
        if job.get("description"):
            parts.append(f"\nJob Description:\n{job['description']}")
        if job.get("requirements"):
            parts.append(f"\nRequirements:\n{job['requirements']}")

        return "\n".join(parts)

    @staticmethod
    def _format_profile(profile: Dict[str, Any]) -> str:
        """Format a user profile dictionary into a readable text block."""
        parts: List[str] = []

        if profile.get("name"):
            parts.append(f"Name: {profile['name']}")
        if profile.get("email"):
            parts.append(f"Email: {profile['email']}")
        if profile.get("phone"):
            parts.append(f"Phone: {profile['phone']}")
        if profile.get("linkedin_url"):
            parts.append(f"LinkedIn: {profile['linkedin_url']}")

        # Profile data fields (stored in user.profile_data JSON)
        if profile.get("summary"):
            parts.append(f"\nProfessional Summary:\n{profile['summary']}")

        if profile.get("skills"):
            skills = profile["skills"]
            if isinstance(skills, list):
                skills = ", ".join(skills)
            parts.append(f"\nSkills: {skills}")

        if profile.get("experience"):
            experience = profile["experience"]
            if isinstance(experience, list):
                exp_lines = []
                for entry in experience:
                    if isinstance(entry, dict):
                        role = entry.get("title", "")
                        org = entry.get("company", "")
                        duration = entry.get("duration", "")
                        desc = entry.get("description", "")
                        exp_lines.append(
                            f"- {role} at {org}"
                            + (f" ({duration})" if duration else "")
                            + (f"\n  {desc}" if desc else "")
                        )
                    else:
                        exp_lines.append(f"- {entry}")
                parts.append(f"\nExperience:\n" + "\n".join(exp_lines))
            else:
                parts.append(f"\nExperience:\n{experience}")

        if profile.get("education"):
            education = profile["education"]
            if isinstance(education, list):
                edu_lines = []
                for entry in education:
                    if isinstance(entry, dict):
                        degree = entry.get("degree", "")
                        school = entry.get("school", "")
                        edu_lines.append(f"- {degree}, {school}")
                    else:
                        edu_lines.append(f"- {entry}")
                parts.append(f"\nEducation:\n" + "\n".join(edu_lines))
            else:
                parts.append(f"\nEducation:\n{education}")

        if profile.get("certifications"):
            certs = profile["certifications"]
            if isinstance(certs, list):
                parts.append(
                    "\nCertifications:\n" + "\n".join(f"- {c}" for c in certs)
                )
            else:
                parts.append(f"\nCertifications:\n{certs}")

        return "\n".join(parts)

    @staticmethod
    def _job_model_to_dict(job_model: Any) -> Dict[str, Any]:
        """Convert a LinkedInJob ORM model to a plain dictionary."""
        return {
            "id": job_model.id,
            "title": job_model.title,
            "company": job_model.company,
            "location": job_model.location,
            "description": job_model.description,
            "requirements": job_model.requirements,
            "salary_range": job_model.salary_range,
            "job_type": job_model.job_type,
            "experience_level": job_model.experience_level,
            "job_url": job_model.job_url,
            "match_score": job_model.match_score,
        }

    @staticmethod
    def _build_profile_dict(user: Any) -> Dict[str, Any]:
        """Build a flat profile dictionary from a User ORM model.

        Merges top-level user fields with the nested ``profile_data``
        JSON column so that prompt builders receive a single dict.
        """
        profile: Dict[str, Any] = {
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "linkedin_url": user.linkedin_url,
        }

        if user.profile_data and isinstance(user.profile_data, dict):
            profile.update(user.profile_data)

        return profile
