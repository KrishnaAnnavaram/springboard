"""AI-powered job matching agent using Anthropic Claude API.

Analyzes job postings against a user's profile to produce weighted match
scores and human-readable reasoning. Scores are persisted through
JobRepository so downstream workflow steps (resume customisation, auto-apply)
can act on them.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from src.database.connection import get_db
from src.database.repositories.job_repository import JobRepository
from src.database.repositories.user_repository import UserRepository
from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert career-matching assistant. Your task is to evaluate how well
a job posting matches a candidate's profile and return a structured JSON
assessment.

You MUST respond with valid JSON only -- no markdown fences, no commentary
outside the JSON object.

Scoring categories (each 0-100):
1. **skills** -- overlap of required/preferred skills with the candidate's
   skill set, weighted by proficiency level.
2. **experience** -- alignment of years of experience and seniority level.
3. **location** -- whether the job location matches the candidate's
   preference (exact match, remote-friendly, willingness to relocate).
4. **salary** -- whether the offered salary range falls within the
   candidate's expectations.
5. **company** -- alignment with the candidate's target companies,
   preferred industries, and company-size preferences.

Response schema:
{
  "scores": {
    "skills": <int 0-100>,
    "experience": <int 0-100>,
    "location": <int 0-100>,
    "salary": <int 0-100>,
    "company": <int 0-100>
  },
  "reasoning": {
    "skills": "<one-sentence explanation>",
    "experience": "<one-sentence explanation>",
    "location": "<one-sentence explanation>",
    "salary": "<one-sentence explanation>",
    "company": "<one-sentence explanation>"
  },
  "overall_summary": "<2-3 sentence summary of fit>",
  "key_strengths": ["<strength1>", "<strength2>"],
  "key_gaps": ["<gap1>", "<gap2>"]
}
"""

_USER_PROMPT_TEMPLATE = """\
## Job Posting
- **Title:** {title}
- **Company:** {company}
- **Location:** {location}
- **Job Type:** {job_type}
- **Experience Level:** {experience_level}
- **Salary Range:** {salary_range}

### Description
{description}

### Requirements
{requirements}

---

## Candidate Profile
- **Name:** {user_name}
- **Skills:** {skills}
- **Experience (years):** {years_experience}
- **Seniority Level:** {seniority}
- **Preferred Locations:** {preferred_locations}
- **Open to Remote:** {open_to_remote}
- **Open to Relocation:** {open_to_relocation}
- **Salary Expectation:** {salary_expectation}
- **Target Companies:** {target_companies}
- **Preferred Industries:** {preferred_industries}
- **Preferred Company Size:** {preferred_company_size}

### Additional Context
{additional_context}

---

Evaluate the match and return your assessment as JSON.
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class JobMatcherAgent:
    """Evaluate job postings against a user profile using Claude.

    The agent:
    * Builds a structured prompt from job + profile data.
    * Calls the Anthropic messages API with retry / back-off.
    * Parses the structured JSON response into category scores.
    * Computes a weighted overall score.
    * Persists scores and reasoning via ``JobRepository``.

    Usage::

        agent = JobMatcherAgent()
        agent.run()                    # match all unmatched jobs
        # -- or --
        result = agent.analyze_job(job_dict, profile_dict)
    """

    # Default weights mirrored from config for documentation purposes.
    _DEFAULT_WEIGHTS: Dict[str, float] = {
        "skills": 0.40,
        "experience": 0.25,
        "location": 0.15,
        "salary": 0.10,
        "company": 0.10,
    }

    def __init__(self) -> None:
        """Initialise configuration, Anthropic client, and scoring weights."""
        self.config = Config()

        # Anthropic client
        api_key = self.config.anthropic_api_key
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Please configure it in .env"
            )
        self.client = anthropic.Anthropic(api_key=api_key)

        # Model parameters
        self.model: str = self.config.anthropic_model
        self.max_tokens: int = self.config.anthropic_max_tokens
        self.temperature: float = self.config.anthropic_temperature
        self.timeout: int = self.config.anthropic_config.get("timeout", 60)

        # Retry parameters
        self.max_retries: int = self.config.automation.get("retry_attempts", 3)
        self.backoff_factor: float = self.config.automation.get(
            "retry_backoff_factor", 2
        )

        # Scoring weights (configurable via config.yaml)
        self.weights: Dict[str, float] = self.config.match_weights

        logger.info(
            "JobMatcherAgent initialised (model=%s, weights=%s)",
            self.model,
            self.weights,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """Main entry point: fetch unmatched jobs and score them all.

        Returns:
            Summary dict with counts of processed, succeeded, and failed jobs.
        """
        logger.info("Starting job matching run")

        with get_db() as session:
            user_repo = UserRepository(session)
            user = user_repo.get_default_user()

            if user is None:
                logger.error("No user profile found. Cannot run matching.")
                return {
                    "processed": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "error": "No user profile found",
                }

            user_profile = self._build_user_profile(user)
            results = self.match_all_jobs(session, user_profile)

        logger.info(
            "Job matching run complete: processed=%d, succeeded=%d, failed=%d",
            results["processed"],
            results["succeeded"],
            results["failed"],
        )
        return results

    def match_all_jobs(
        self,
        session: Any,
        user_profile: Dict[str, Any],
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Score all unmatched jobs in the database.

        Args:
            session: Active SQLAlchemy session.
            user_profile: Normalised user profile dictionary.
            limit: Maximum number of unmatched jobs to process per batch.

        Returns:
            Summary dict with processing statistics.
        """
        job_repo = JobRepository(session)
        unmatched_jobs = job_repo.get_unmatched_jobs(limit=limit)

        processed = 0
        succeeded = 0
        failed = 0

        if not unmatched_jobs:
            logger.info("No unmatched jobs to process.")
            return {"processed": 0, "succeeded": 0, "failed": 0}

        logger.info("Found %d unmatched jobs to process.", len(unmatched_jobs))

        for job in unmatched_jobs:
            processed += 1
            job_dict = self._job_model_to_dict(job)

            try:
                result = self.analyze_job(job_dict, user_profile)
                score = result["overall_score"]
                reasoning = self.generate_reasoning(result)

                job_repo.update_match_score(
                    job_id=job.id,
                    score=score,
                    reasoning=reasoning,
                )
                succeeded += 1

                logger.info(
                    "Matched job %d (%s at %s): score=%.1f",
                    job.id,
                    job.title,
                    job.company,
                    score,
                )

            except Exception:
                failed += 1
                logger.exception(
                    "Failed to match job %d (%s at %s)",
                    job.id,
                    job.title,
                    job.company,
                )

        return {"processed": processed, "succeeded": succeeded, "failed": failed}

    def analyze_job(
        self,
        job: Dict[str, Any],
        user_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyse a single job against the user profile.

        Args:
            job: Dictionary describing the job posting.
            user_profile: Dictionary describing the candidate.

        Returns:
            Dictionary containing:
            - ``scores``: per-category scores (0-100)
            - ``overall_score``: weighted aggregate (0-100)
            - ``reasoning``: per-category explanations
            - ``overall_summary``: narrative summary
            - ``key_strengths``: list of strengths
            - ``key_gaps``: list of gaps
        """
        prompt = self._build_prompt(job, user_profile)
        raw_response = self._call_claude(prompt)
        parsed = self._parse_response(raw_response)
        overall_score = self._compute_overall_score(parsed["scores"])

        return {
            "scores": parsed["scores"],
            "overall_score": overall_score,
            "reasoning": parsed.get("reasoning", {}),
            "overall_summary": parsed.get("overall_summary", ""),
            "key_strengths": parsed.get("key_strengths", []),
            "key_gaps": parsed.get("key_gaps", []),
        }

    def generate_reasoning(self, match_result: Dict[str, Any]) -> str:
        """Produce a human-readable explanation of the match result.

        Args:
            match_result: Output from :meth:`analyze_job`.

        Returns:
            Multi-line string summarising the match.
        """
        lines: List[str] = []
        overall = match_result.get("overall_score", 0)
        lines.append(f"Overall Match Score: {overall:.1f}/100")
        lines.append("")

        # Per-category breakdown
        scores = match_result.get("scores", {})
        reasoning = match_result.get("reasoning", {})
        for category in ("skills", "experience", "location", "salary", "company"):
            cat_score = scores.get(category, 0)
            weight = self.weights.get(category, 0)
            weighted = cat_score * weight
            explanation = reasoning.get(category, "N/A")
            lines.append(
                f"  {category.title():12s}: {cat_score:3d}/100 "
                f"(weight {weight:.0%}, contribution {weighted:.1f}) "
                f"-- {explanation}"
            )

        lines.append("")

        # Summary
        summary = match_result.get("overall_summary", "")
        if summary:
            lines.append(f"Summary: {summary}")

        # Strengths / gaps
        strengths = match_result.get("key_strengths", [])
        if strengths:
            lines.append("Strengths: " + "; ".join(strengths))

        gaps = match_result.get("key_gaps", [])
        if gaps:
            lines.append("Gaps: " + "; ".join(gaps))

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Claude API interaction
    # ------------------------------------------------------------------

    def _call_claude(self, user_prompt: str) -> str:
        """Send a prompt to Claude with exponential-backoff retry.

        Args:
            user_prompt: The fully-rendered user message.

        Returns:
            Raw text content from Claude's response.

        Raises:
            anthropic.APIError: If all retry attempts are exhausted.
        """
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "Calling Claude API (attempt %d/%d)", attempt, self.max_retries
                )

                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                    timeout=self.timeout,
                )

                text = response.content[0].text
                logger.debug(
                    "Claude API responded (usage: input=%d, output=%d tokens)",
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
                return text

            except anthropic.RateLimitError as exc:
                last_exception = exc
                wait = self.backoff_factor ** attempt
                logger.warning(
                    "Rate limited on attempt %d/%d. Retrying in %.1fs.",
                    attempt,
                    self.max_retries,
                    wait,
                )
                time.sleep(wait)

            except anthropic.APIStatusError as exc:
                last_exception = exc
                # Retry on transient server errors (5xx)
                if exc.status_code >= 500:
                    wait = self.backoff_factor ** attempt
                    logger.warning(
                        "Server error %d on attempt %d/%d. Retrying in %.1fs.",
                        exc.status_code,
                        attempt,
                        self.max_retries,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    # Client errors (4xx except 429) are not retryable
                    logger.error(
                        "Non-retryable API error (status %d): %s",
                        exc.status_code,
                        exc.message,
                    )
                    raise

            except anthropic.APIConnectionError as exc:
                last_exception = exc
                wait = self.backoff_factor ** attempt
                logger.warning(
                    "Connection error on attempt %d/%d. Retrying in %.1fs.",
                    attempt,
                    self.max_retries,
                    wait,
                )
                time.sleep(wait)

        # All retries exhausted
        logger.error("All %d API attempts failed.", self.max_retries)
        raise last_exception  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        job: Dict[str, Any],
        user_profile: Dict[str, Any],
    ) -> str:
        """Render the user prompt from job and profile data.

        Args:
            job: Job posting dictionary.
            user_profile: Candidate profile dictionary.

        Returns:
            Fully-rendered prompt string.
        """
        skills_list = user_profile.get("skills", [])
        if isinstance(skills_list, list):
            skills_str = ", ".join(
                f"{s['name']} ({s.get('proficiency', 'N/A')})"
                if isinstance(s, dict)
                else str(s)
                for s in skills_list
            )
        else:
            skills_str = str(skills_list)

        preferred_locations = user_profile.get("preferred_locations", [])
        if isinstance(preferred_locations, list):
            locations_str = ", ".join(str(loc) for loc in preferred_locations)
        else:
            locations_str = str(preferred_locations)

        target_companies = user_profile.get("target_companies", [])
        if isinstance(target_companies, list):
            companies_str = ", ".join(str(c) for c in target_companies)
        else:
            companies_str = str(target_companies)

        preferred_industries = user_profile.get("preferred_industries", [])
        if isinstance(preferred_industries, list):
            industries_str = ", ".join(str(i) for i in preferred_industries)
        else:
            industries_str = str(preferred_industries)

        return _USER_PROMPT_TEMPLATE.format(
            title=job.get("title", "N/A"),
            company=job.get("company", "N/A"),
            location=job.get("location", "N/A"),
            job_type=job.get("job_type", "N/A"),
            experience_level=job.get("experience_level", "N/A"),
            salary_range=job.get("salary_range", "N/A"),
            description=job.get("description", "No description provided."),
            requirements=job.get("requirements", "No requirements listed."),
            user_name=user_profile.get("name", "Candidate"),
            skills=skills_str or "Not specified",
            years_experience=user_profile.get("years_experience", "N/A"),
            seniority=user_profile.get("seniority", "N/A"),
            preferred_locations=locations_str or "Not specified",
            open_to_remote=user_profile.get("open_to_remote", "N/A"),
            open_to_relocation=user_profile.get("open_to_relocation", "N/A"),
            salary_expectation=user_profile.get("salary_expectation", "N/A"),
            target_companies=companies_str or "Not specified",
            preferred_industries=industries_str or "Not specified",
            preferred_company_size=user_profile.get(
                "preferred_company_size", "Not specified"
            ),
            additional_context=user_profile.get("additional_context", "None"),
        )

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, raw_text: str) -> Dict[str, Any]:
        """Parse Claude's JSON response into a validated dictionary.

        If the model wraps the JSON in markdown code-fences we strip them
        before parsing.  Missing or malformed fields fall back to safe
        defaults so that the overall pipeline never crashes from a single
        bad response.

        Args:
            raw_text: The raw string returned by Claude.

        Returns:
            Parsed and validated result dictionary.
        """
        cleaned = raw_text.strip()

        # Strip optional markdown fences
        if cleaned.startswith("```"):
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error("Failed to parse Claude response as JSON: %s", cleaned[:500])
            return self._fallback_scores()

        return self._validate_parsed(data)

    def _validate_parsed(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalise parsed API response data.

        Ensures every expected category is present and scores are clamped
        to 0-100.

        Args:
            data: Raw parsed JSON dict.

        Returns:
            Normalised result dict.
        """
        categories = ("skills", "experience", "location", "salary", "company")

        scores_raw = data.get("scores", {})
        scores: Dict[str, int] = {}
        for cat in categories:
            value = scores_raw.get(cat, 0)
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = 0
            scores[cat] = max(0, min(100, value))

        reasoning_raw = data.get("reasoning", {})
        reasoning: Dict[str, str] = {}
        for cat in categories:
            reasoning[cat] = str(reasoning_raw.get(cat, "No explanation provided."))

        return {
            "scores": scores,
            "reasoning": reasoning,
            "overall_summary": str(data.get("overall_summary", "")),
            "key_strengths": data.get("key_strengths", []),
            "key_gaps": data.get("key_gaps", []),
        }

    @staticmethod
    def _fallback_scores() -> Dict[str, Any]:
        """Return a safe fallback when parsing fails entirely.

        Returns:
            Dictionary with zero scores and error messaging.
        """
        categories = ("skills", "experience", "location", "salary", "company")
        return {
            "scores": {cat: 0 for cat in categories},
            "reasoning": {
                cat: "Unable to evaluate -- API response could not be parsed."
                for cat in categories
            },
            "overall_summary": "Matching failed due to an unparseable API response.",
            "key_strengths": [],
            "key_gaps": ["Unable to evaluate this job."],
        }

    # ------------------------------------------------------------------
    # Score computation
    # ------------------------------------------------------------------

    def _compute_overall_score(self, scores: Dict[str, int]) -> float:
        """Compute the weighted overall score.

        Args:
            scores: Per-category scores (0-100).

        Returns:
            Weighted average as a float (0-100), rounded to one decimal.
        """
        total = 0.0
        weight_sum = 0.0
        for category, weight in self.weights.items():
            total += scores.get(category, 0) * weight
            weight_sum += weight

        # Guard against misconfigured weights that don't sum to 1.0
        if weight_sum > 0 and abs(weight_sum - 1.0) > 0.001:
            total = total / weight_sum

        return round(total, 1)

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_profile(user: Any) -> Dict[str, Any]:
        """Convert an ORM ``User`` model into a flat profile dictionary.

        Merges ``user.profile_data`` and ``user.preferences`` into a
        single dict suitable for prompt rendering.

        Args:
            user: SQLAlchemy ``User`` instance.

        Returns:
            Normalised profile dictionary.
        """
        profile_data: Dict[str, Any] = user.profile_data or {}
        preferences: Dict[str, Any] = user.preferences or {}

        return {
            "name": user.name,
            "email": user.email,
            "skills": profile_data.get("skills", []),
            "years_experience": profile_data.get("years_experience", "N/A"),
            "seniority": profile_data.get("seniority", "N/A"),
            "additional_context": profile_data.get("summary", "None"),
            # Preferences
            "preferred_locations": preferences.get("locations", []),
            "open_to_remote": preferences.get("open_to_remote", True),
            "open_to_relocation": preferences.get("open_to_relocation", False),
            "salary_expectation": preferences.get("salary_expectation", "N/A"),
            "target_companies": preferences.get("target_companies", []),
            "preferred_industries": preferences.get("preferred_industries", []),
            "preferred_company_size": preferences.get(
                "preferred_company_size", "Not specified"
            ),
        }

    @staticmethod
    def _job_model_to_dict(job: Any) -> Dict[str, Any]:
        """Convert an ORM ``LinkedInJob`` model into a plain dictionary.

        Args:
            job: SQLAlchemy ``LinkedInJob`` instance.

        Returns:
            Dictionary with all fields used by the prompt builder.
        """
        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description,
            "requirements": job.requirements,
            "salary_range": job.salary_range,
            "job_type": job.job_type,
            "experience_level": job.experience_level,
        }
