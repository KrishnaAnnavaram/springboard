"""LangGraph node functions for the Springboard workflow."""

from datetime import datetime
from typing import Any, Dict

from src.agents.job_matcher import JobMatcherAgent
from src.agents.linkedin_applier import LinkedInApplicationAgent
from src.agents.linkedin_scraper import LinkedInScraperAgent
from src.agents.resume_customizer import ResumeCustomizerAgent
from src.agents.supervisor import SupervisorAgent
from src.state.app_state import AppState
from src.utils.logger import get_logger

logger = get_logger(__name__)


def scrape_node(state: AppState) -> Dict[str, Any]:
    """Execute the LinkedIn scraping step.

    Searches LinkedIn for jobs based on search criteria and saves them to the database.

    Args:
        state: Current workflow state with search_criteria.

    Returns:
        Updated state fields with scraped_jobs and current_step.
    """
    logger.info("=== SCRAPE NODE: Starting job scraping ===")

    try:
        scraper = LinkedInScraperAgent()
        criteria = state.get("search_criteria", {})

        jobs = scraper.run(
            keywords=criteria.get("keywords", []),
            location=criteria.get("location", ""),
            max_jobs=criteria.get("max_jobs", 50),
        )

        logger.info("Scraped %d jobs from LinkedIn", len(jobs))

        return {
            "scraped_jobs": jobs,
            "current_step": "scrape",
            "last_checkpoint": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Scrape node failed: %s", e)
        errors = state.get("errors", [])
        errors.append({
            "step": "scrape",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": len([err for err in errors if err.get("step") == "scrape"]),
        })
        return {
            "errors": errors,
            "current_step": "scrape",
        }


def match_node(state: AppState) -> Dict[str, Any]:
    """Execute the job matching step.

    Analyzes scraped jobs against user profile using AI-powered scoring.

    Args:
        state: Current workflow state with scraped_jobs and user_profile.

    Returns:
        Updated state fields with matched_jobs and current_step.
    """
    logger.info("=== MATCH NODE: Starting job matching ===")

    try:
        matcher = JobMatcherAgent()
        user_profile = state.get("user_profile", {})

        matched = matcher.run(user_profile=user_profile)

        logger.info("Matched %d jobs above threshold", len(matched))

        # Build pending applications list from high-scoring matches
        pending = []
        for job in matched:
            if job.get("match_score", 0) >= matcher.config.auto_apply_threshold:
                pending.append({
                    "job_id": job["id"],
                    "job_title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "match_score": job.get("match_score", 0),
                })

        return {
            "matched_jobs": matched,
            "pending_applications": pending,
            "current_step": "match",
            "last_checkpoint": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Match node failed: %s", e)
        errors = state.get("errors", [])
        errors.append({
            "step": "match",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": len([err for err in errors if err.get("step") == "match"]),
        })
        return {
            "errors": errors,
            "current_step": "match",
        }


def customize_node(state: AppState) -> Dict[str, Any]:
    """Execute the resume customization step.

    Generates tailored resumes and cover letters for matched jobs.

    Args:
        state: Current workflow state with matched_jobs and user_profile.

    Returns:
        Updated state fields with customized_resumes and cover_letters.
    """
    logger.info("=== CUSTOMIZE NODE: Starting resume customization ===")

    try:
        customizer = ResumeCustomizerAgent()
        pending = state.get("pending_applications", [])

        resumes = {}
        cover_letters = {}

        for app in pending:
            job_id = app["job_id"]
            try:
                result = customizer.run(job_id=job_id)
                if result:
                    resumes[job_id] = result.get("resume_text", "")
                    cover_letters[job_id] = result.get("cover_letter", "")
                    logger.info("Customized resume for job %d", job_id)
            except Exception as e:
                logger.warning("Failed to customize for job %d: %s", job_id, e)
                continue

        logger.info("Customized %d resumes and cover letters", len(resumes))

        return {
            "customized_resumes": resumes,
            "cover_letters": cover_letters,
            "current_step": "customize",
            "last_checkpoint": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Customize node failed: %s", e)
        errors = state.get("errors", [])
        errors.append({
            "step": "customize",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": len([err for err in errors if err.get("step") == "customize"]),
        })
        return {
            "errors": errors,
            "current_step": "customize",
        }


def apply_node(state: AppState) -> Dict[str, Any]:
    """Execute the application submission step.

    Submits applications via LinkedIn Easy Apply for pending jobs.

    Args:
        state: Current workflow state with pending_applications and customized data.

    Returns:
        Updated state fields with submitted_applications.
    """
    logger.info("=== APPLY NODE: Starting application submission ===")

    try:
        applier = LinkedInApplicationAgent()
        pending = state.get("pending_applications", [])
        resumes = state.get("customized_resumes", {})
        cover_letters = state.get("cover_letters", {})
        submitted = state.get("submitted_applications", [])

        for app in pending:
            job_id = app["job_id"]
            try:
                result = applier.run(
                    job_id=job_id,
                    resume_text=resumes.get(job_id, ""),
                    cover_letter=cover_letters.get(job_id, ""),
                )
                if result and result.get("success"):
                    submitted.append({
                        "job_id": job_id,
                        "job_title": app.get("job_title", ""),
                        "company": app.get("company", ""),
                        "applied_at": datetime.utcnow().isoformat(),
                        "screenshot": result.get("screenshot_path", ""),
                    })
                    logger.info("Submitted application for job %d", job_id)
            except Exception as e:
                logger.warning("Failed to apply for job %d: %s", job_id, e)
                continue

        logger.info("Submitted %d applications", len(submitted))

        return {
            "submitted_applications": submitted,
            "current_step": "apply",
            "status": "completed",
            "last_checkpoint": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Apply node failed: %s", e)
        errors = state.get("errors", [])
        errors.append({
            "step": "apply",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": len([err for err in errors if err.get("step") == "apply"]),
        })
        return {
            "errors": errors,
            "current_step": "apply",
        }


def supervisor_node(state: AppState) -> Dict[str, Any]:
    """Execute the supervisor routing step.

    Evaluates current state and determines the next workflow step.

    Args:
        state: Current workflow state.

    Returns:
        Updated state with next_step and checkpoint info.
    """
    logger.info("=== SUPERVISOR NODE: Evaluating workflow state ===")

    supervisor = SupervisorAgent()
    next_step = supervisor.route(state)
    state_update = supervisor.handle_checkpoint(state)

    logger.info("Supervisor routing to: %s", next_step)

    return {
        "next_step": next_step,
        "iteration": state_update.get("iteration", 0),
        "last_checkpoint": state_update.get("last_checkpoint", ""),
    }
