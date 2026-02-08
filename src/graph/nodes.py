"""LangGraph node functions for the Springboard workflow.

Each node wraps an agent call and translates the result into state updates.
Agents are self-contained — they read search criteria and user profiles from
the config / database rather than accepting them as arguments — so nodes
act primarily as error-boundary wrappers with progress reporting.
"""

from datetime import datetime
from typing import Any, Dict, List

from src.agents.job_matcher import JobMatcherAgent
from src.agents.linkedin_applier import LinkedInApplicationAgent
from src.agents.linkedin_scraper import LinkedInScraperAgent
from src.agents.resume_customizer import ResumeCustomizerAgent
from src.agents.supervisor import SupervisorAgent
from src.agents.orchestrator import OrchestratorAgent
from src.state.app_state import AppState
from src.utils.logger import get_logger

logger = get_logger(__name__)


def scrape_node(state: AppState) -> Dict[str, Any]:
    """Execute the multi-platform scraping step.

    Uses the OrchestratorAgent to scrape jobs across all enabled platforms.
    Falls back to the legacy LinkedInScraperAgent if the orchestrator fails.
    """
    logger.info("=== SCRAPE NODE: Starting job scraping ===")

    try:
        criteria = state.get("search_criteria", {})
        keywords = criteria.get("keywords", [])
        location = criteria.get("location", "")
        max_jobs = criteria.get("max_jobs", 50)
        platforms = criteria.get("platforms", None)

        try:
            orchestrator = OrchestratorAgent()
            jobs = orchestrator.scrape_all_platforms(
                keywords=keywords,
                location=location,
                max_jobs=max_jobs,
                platforms=platforms,
            )
            logger.info("Orchestrator scraped %d jobs across platforms", len(jobs))
        except Exception as orch_err:
            logger.warning(
                "Orchestrator failed (%s), falling back to LinkedIn-only scraper",
                orch_err,
            )
            # Fallback: legacy LinkedIn scraper (takes no arguments, reads config)
            scraper = LinkedInScraperAgent()
            scraper.run()
            jobs = scraper.scraped_jobs or []
            logger.info("Legacy scraper found %d jobs", len(jobs))

        return {
            "scraped_jobs": jobs,
            "current_step": "scrape",
            "last_checkpoint": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Scrape node failed: %s", e)
        errors = list(state.get("errors", []))
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

    JobMatcherAgent.run() takes NO arguments — it reads unmatched jobs from
    the DB, scores them via Claude, and persists scores.  Returns a summary
    dict ``{processed, succeeded, failed}`` (not a list of jobs).
    """
    logger.info("=== MATCH NODE: Starting job matching ===")

    try:
        matcher = JobMatcherAgent()
        result = matcher.run()  # no arguments

        logger.info(
            "Matcher: %d processed, %d succeeded, %d failed",
            result.get("processed", 0),
            result.get("succeeded", 0),
            result.get("failed", 0),
        )

        # Fetch matched jobs from DB for downstream nodes
        from src.database.connection import get_db
        from src.database.repositories.job_repository import JobRepository

        matched_jobs: List[Dict[str, Any]] = []
        pending: List[Dict[str, Any]] = []

        with get_db() as session:
            repo = JobRepository(session)
            min_score = matcher.config.min_match_score
            threshold = matcher.config.auto_apply_threshold
            db_jobs = repo.get_matched_jobs(min_score=min_score)

            for job in db_jobs:
                job_dict = {
                    "id": job.id,
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "match_score": job.match_score,
                    "platform": getattr(job, "platform", "linkedin"),
                }
                matched_jobs.append(job_dict)

                if job.match_score and job.match_score >= threshold:
                    pending.append({
                        "job_id": job.id,
                        "job_title": job.title,
                        "company": job.company,
                        "match_score": job.match_score,
                    })

        logger.info(
            "Found %d matched jobs, %d above auto-apply threshold",
            len(matched_jobs), len(pending),
        )

        return {
            "matched_jobs": matched_jobs,
            "pending_applications": pending,
            "current_step": "match",
            "last_checkpoint": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Match node failed: %s", e)
        errors = list(state.get("errors", []))
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

    ResumeCustomizerAgent.run() takes NO arguments — it fetches matched jobs
    from the DB and processes them.  Returns ``List[Dict]`` with per-job
    results containing job_id, resume_text, cover_letter, status.
    """
    logger.info("=== CUSTOMIZE NODE: Starting resume customization ===")

    try:
        customizer = ResumeCustomizerAgent()
        results = customizer.run()  # no arguments

        resumes: Dict[int, str] = {}
        cover_letters: Dict[int, str] = {}

        for item in results:
            job_id = item.get("job_id")
            if job_id and item.get("status") == "success":
                resumes[job_id] = item.get("resume_text", "")
                cover_letters[job_id] = item.get("cover_letter", "")

        logger.info("Customized %d resumes and cover letters", len(resumes))

        return {
            "customized_resumes": resumes,
            "cover_letters": cover_letters,
            "current_step": "customize",
            "last_checkpoint": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Customize node failed: %s", e)
        errors = list(state.get("errors", []))
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

    LinkedInApplicationAgent.run() takes NO arguments — it reads approved
    jobs from the DB and submits Easy Apply applications.  Returns a summary
    dict ``{processed, succeeded, failed, details}``.
    """
    logger.info("=== APPLY NODE: Starting application submission ===")

    try:
        applier = LinkedInApplicationAgent()
        result = applier.run()  # no arguments

        logger.info(
            "Applications: %d processed, %d succeeded, %d failed",
            result.get("processed", 0),
            result.get("succeeded", 0),
            result.get("failed", 0),
        )

        submitted = list(state.get("submitted_applications", []))
        for detail in result.get("details", []):
            if detail.get("status") == "success":
                submitted.append({
                    "job_id": detail.get("job_id"),
                    "job_title": detail.get("title", ""),
                    "company": detail.get("company", ""),
                    "applied_at": datetime.utcnow().isoformat(),
                })

        return {
            "submitted_applications": submitted,
            "current_step": "apply",
            "status": "completed",
            "last_checkpoint": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Apply node failed: %s", e)
        errors = list(state.get("errors", []))
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


def feed_scrape_node(state: AppState) -> Dict[str, Any]:
    """Execute the LinkedIn feed scraping step for hiring posts."""
    logger.info("=== FEED SCRAPE NODE: Scanning LinkedIn feed for hiring posts ===")

    try:
        orchestrator = OrchestratorAgent()
        criteria = state.get("search_criteria", {})
        feed_keywords = criteria.get("feed_keywords", None)

        posts = orchestrator.scrape_feed(feed_keywords=feed_keywords)
        logger.info("Found %d hiring-related feed posts", len(posts))

        return {
            "feed_posts": posts,
            "current_step": "feed_scrape",
            "last_checkpoint": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("Feed scrape node failed: %s", e)
        errors = list(state.get("errors", []))
        errors.append({
            "step": "feed_scrape",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        })
        return {
            "errors": errors,
            "current_step": "feed_scrape",
        }


def supervisor_node(state: AppState) -> Dict[str, Any]:
    """Execute the supervisor routing step."""
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
