"""Orchestration agent for the Springboard multi-agent system.

The ``OrchestratorAgent`` is the central coordinator that manages the
lifecycle of all sub-agents (scrapers, matcher, customizer, applier).
It decides which platforms to scrape, dispatches work, aggregates
results, handles errors, and reports progress through a callback
interface so the dashboard can display real-time updates.
"""

from __future__ import annotations

import traceback
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.agents.base.base_scraper import BaseJobScraperAgent
from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Platform registry — maps platform name -> scraper class
# ---------------------------------------------------------------------------

_SCRAPER_REGISTRY: Dict[str, type] = {}


def register_scraper(platform: str, cls: type) -> None:
    """Register a scraper class for a platform name."""
    _SCRAPER_REGISTRY[platform] = cls
    logger.debug("Registered scraper for platform '%s': %s", platform, cls.__name__)


def get_scraper_for_platform(platform: str) -> BaseJobScraperAgent:
    """Instantiate the scraper for *platform*.

    Raises:
        ValueError: If no scraper is registered for *platform*.
    """
    cls = _SCRAPER_REGISTRY.get(platform)
    if cls is None:
        raise ValueError(f"No scraper registered for platform '{platform}'. Available: {list(_SCRAPER_REGISTRY.keys())}")
    return cls()


def list_registered_platforms() -> List[str]:
    """Return names of all registered platforms."""
    return list(_SCRAPER_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Auto-register scrapers on import
# ---------------------------------------------------------------------------

def _auto_register() -> None:
    """Import all scraper modules so they self-register."""
    try:
        from src.agents.scrapers.linkedin_platform_scraper import LinkedInPlatformScraper
        register_scraper("linkedin", LinkedInPlatformScraper)
    except ImportError:
        logger.debug("LinkedIn platform scraper not available")

    try:
        from src.agents.scrapers.dice_scraper import DiceScraperAgent
        register_scraper("dice", DiceScraperAgent)
    except ImportError:
        logger.debug("Dice scraper not available")

    try:
        from src.agents.scrapers.indeed_scraper import IndeedScraperAgent
        register_scraper("indeed", IndeedScraperAgent)
    except ImportError:
        logger.debug("Indeed scraper not available")

    try:
        from src.agents.scrapers.monster_scraper import MonsterScraperAgent
        register_scraper("monster", MonsterScraperAgent)
    except ImportError:
        logger.debug("Monster scraper not available")

    try:
        from src.agents.scrapers.handshake_scraper import HandshakeScraperAgent
        register_scraper("handshake", HandshakeScraperAgent)
    except ImportError:
        logger.debug("Handshake scraper not available")

    try:
        from src.agents.scrapers.linkedin_feed_scraper import LinkedInFeedScraperAgent
        register_scraper("linkedin_feed", LinkedInFeedScraperAgent)
    except ImportError:
        logger.debug("LinkedIn feed scraper not available")


_auto_register()


# ---------------------------------------------------------------------------
# Progress callback type
# ---------------------------------------------------------------------------

ProgressCallback = Optional[Callable[[Dict[str, Any]], None]]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class OrchestratorAgent:
    """Central coordinator for the multi-agent job automation system.

    The orchestrator:
    * Reads enabled platforms from config
    * Dispatches scraping work to each platform's agent
    * Aggregates results into a unified job list
    * Delegates matching, customisation, and application to specialised agents
    * Provides real-time progress updates via an optional callback
    * Handles errors gracefully — one failing platform does not abort others

    Usage::

        orchestrator = OrchestratorAgent(on_progress=my_callback)
        result = orchestrator.run_full_pipeline(search_criteria)
    """

    def __init__(self, on_progress: ProgressCallback = None) -> None:
        self.config = Config()
        self._on_progress = on_progress
        self._errors: List[Dict[str, Any]] = []
        logger.info("OrchestratorAgent initialised")

    # ------------------------------------------------------------------
    # Progress reporting
    # ------------------------------------------------------------------

    def _report(self, step: str, status: str, message: str, data: Optional[Dict] = None) -> None:
        """Emit a progress event.

        Args:
            step: Pipeline step name (e.g. ``"scrape"``, ``"match"``).
            status: ``"started"``, ``"completed"``, ``"failed"``.
            message: Human-readable description.
            data: Optional extra data payload.
        """
        event: Dict[str, Any] = {
            "step": step,
            "status": status,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if data:
            event["data"] = data

        logger.info("[Orchestrator] %s — %s: %s", step, status, message)
        if self._on_progress:
            try:
                self._on_progress(event)
            except Exception:
                logger.debug("Progress callback raised an exception", exc_info=True)

    # ------------------------------------------------------------------
    # Platform management
    # ------------------------------------------------------------------

    def get_enabled_platforms(self) -> List[str]:
        """Return platform names that are enabled in config and have a registered scraper.

        Returns:
            Sorted list of enabled platform names.
        """
        platforms_config = self.config.get("platforms") or {}
        enabled: List[str] = []

        for name, settings in platforms_config.items():
            if isinstance(settings, dict) and settings.get("enabled", False):
                if name in _SCRAPER_REGISTRY:
                    enabled.append(name)
                else:
                    logger.warning("Platform '%s' enabled in config but no scraper registered", name)

        # Sort by priority (lower = first)
        enabled.sort(key=lambda n: (platforms_config.get(n, {}) or {}).get("priority", 99))

        # If nothing is configured, default to whatever scrapers are registered
        if not enabled and _SCRAPER_REGISTRY:
            enabled = list(_SCRAPER_REGISTRY.keys())
            logger.info("No platforms configured — using all registered: %s", enabled)

        return enabled

    # ------------------------------------------------------------------
    # Scraping phase
    # ------------------------------------------------------------------

    def scrape_all_platforms(
        self,
        keywords: Optional[List[str]] = None,
        location: Optional[str] = None,
        max_jobs: int = 50,
        platforms: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Run scrapers across all enabled platforms.

        Each platform runs independently — a failure on one does not
        block others.

        Args:
            keywords: Search terms.
            location: Location filter.
            max_jobs: Max jobs per platform.
            platforms: Override list of platform names to scrape.

        Returns:
            Combined list of jobs from all platforms.
        """
        target_platforms = platforms or self.get_enabled_platforms()
        all_jobs: List[Dict[str, Any]] = []

        self._report("scrape", "started", f"Scraping {len(target_platforms)} platforms: {target_platforms}")

        for platform_name in target_platforms:
            self._report("scrape", "started", f"Starting {platform_name} scraper")
            try:
                scraper = get_scraper_for_platform(platform_name)
                jobs = scraper.run(
                    keywords=keywords,
                    location=location,
                    max_jobs=max_jobs,
                )
                all_jobs.extend(jobs)
                self._report(
                    "scrape", "completed",
                    f"{platform_name}: collected {len(jobs)} jobs",
                    {"platform": platform_name, "count": len(jobs)},
                )
            except Exception as exc:
                error_info = {
                    "step": "scrape",
                    "platform": platform_name,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                self._errors.append(error_info)
                self._report("scrape", "failed", f"{platform_name} failed: {exc}")
                logger.exception("[Orchestrator] %s scraper failed", platform_name)

        self._report(
            "scrape", "completed",
            f"Scraping complete: {len(all_jobs)} total jobs from {len(target_platforms)} platforms",
            {"total_jobs": len(all_jobs)},
        )
        return all_jobs

    # ------------------------------------------------------------------
    # Matching phase
    # ------------------------------------------------------------------

    def run_matching(self, user_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run the job matcher agent on all unmatched jobs.

        Args:
            user_profile: Optional profile override.

        Returns:
            Summary dict from the matcher.
        """
        self._report("match", "started", "Starting AI job matching")
        try:
            from src.agents.job_matcher import JobMatcherAgent
            matcher = JobMatcherAgent()
            result = matcher.run()
            self._report(
                "match", "completed",
                f"Matching complete: {result.get('succeeded', 0)} scored, {result.get('failed', 0)} failed",
                result,
            )
            return result
        except Exception as exc:
            self._errors.append({
                "step": "match", "error": str(exc),
                "traceback": traceback.format_exc(),
                "timestamp": datetime.utcnow().isoformat(),
            })
            self._report("match", "failed", f"Matching failed: {exc}")
            return {"processed": 0, "succeeded": 0, "failed": 0, "error": str(exc)}

    # ------------------------------------------------------------------
    # Customisation phase
    # ------------------------------------------------------------------

    def run_customization(self) -> List[Dict[str, Any]]:
        """Run the resume customizer on all matched jobs.

        Returns:
            List of result dicts per processed job.
        """
        self._report("customize", "started", "Starting resume customisation")
        try:
            from src.agents.resume_customizer import ResumeCustomizerAgent
            customizer = ResumeCustomizerAgent()
            results = customizer.run()
            succeeded = sum(1 for r in results if r.get("status") == "resume_customized")
            self._report(
                "customize", "completed",
                f"Customisation complete: {succeeded}/{len(results)} succeeded",
                {"total": len(results), "succeeded": succeeded},
            )
            return results
        except Exception as exc:
            self._errors.append({
                "step": "customize", "error": str(exc),
                "traceback": traceback.format_exc(),
                "timestamp": datetime.utcnow().isoformat(),
            })
            self._report("customize", "failed", f"Customisation failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Application phase
    # ------------------------------------------------------------------

    def run_applications(self) -> Dict[str, Any]:
        """Run the application submitter on approved jobs.

        Returns:
            Summary dict with submission statistics.
        """
        self._report("apply", "started", "Starting application submission")
        try:
            from src.agents.linkedin_applier import LinkedInApplicationAgent
            with LinkedInApplicationAgent() as applier:
                result = applier.run()
            self._report(
                "apply", "completed",
                f"Applications: {result.get('submitted', 0)} submitted, {result.get('failed', 0)} failed",
                result,
            )
            return result
        except Exception as exc:
            self._errors.append({
                "step": "apply", "error": str(exc),
                "traceback": traceback.format_exc(),
                "timestamp": datetime.utcnow().isoformat(),
            })
            self._report("apply", "failed", f"Application submission failed: {exc}")
            return {"submitted": 0, "failed": 0, "total_processed": 0, "errors": [str(exc)]}

    # ------------------------------------------------------------------
    # Feed scraping
    # ------------------------------------------------------------------

    def scrape_feed(
        self,
        feed_keywords: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Scrape LinkedIn feed for hiring posts.

        Args:
            feed_keywords: Keywords to search in feed posts.

        Returns:
            List of feed post dicts.
        """
        self._report("feed_scrape", "started", "Scraping LinkedIn feed for hiring posts")
        try:
            if "linkedin_feed" not in _SCRAPER_REGISTRY:
                self._report("feed_scrape", "completed", "LinkedIn feed scraper not available")
                return []

            scraper = get_scraper_for_platform("linkedin_feed")
            posts = scraper.run(keywords=feed_keywords)
            self._report(
                "feed_scrape", "completed",
                f"Found {len(posts)} hiring posts",
                {"count": len(posts)},
            )
            return posts
        except Exception as exc:
            self._errors.append({
                "step": "feed_scrape", "error": str(exc),
                "timestamp": datetime.utcnow().isoformat(),
            })
            self._report("feed_scrape", "failed", f"Feed scraping failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def run_full_pipeline(
        self,
        search_criteria: Optional[Dict[str, Any]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
        skip_apply: bool = False,
    ) -> Dict[str, Any]:
        """Execute the complete job automation pipeline.

        Steps:
            1. Scrape jobs from all enabled platforms
            2. Score/match jobs against user profile
            3. Customise resumes and cover letters
            4. Submit applications (unless ``skip_apply=True``)

        Args:
            search_criteria: Search parameters (keywords, location, etc.).
            user_profile: Optional profile data override.
            skip_apply: If True, skip the application submission step.

        Returns:
            Pipeline summary with per-step results.
        """
        criteria = search_criteria or {}
        started_at = datetime.utcnow().isoformat()
        self._errors = []

        self._report("pipeline", "started", "Full pipeline started")

        # Step 1: Scrape
        all_jobs = self.scrape_all_platforms(
            keywords=criteria.get("keywords"),
            location=criteria.get("location"),
            max_jobs=criteria.get("max_jobs", 50),
            platforms=criteria.get("platforms"),
        )

        # Step 2: Match
        match_result = self.run_matching(user_profile)

        # Step 3: Customise
        customization_results = self.run_customization()

        # Step 4: Apply
        apply_result: Dict[str, Any] = {}
        if not skip_apply:
            apply_result = self.run_applications()

        summary = {
            "started_at": started_at,
            "completed_at": datetime.utcnow().isoformat(),
            "total_scraped": len(all_jobs),
            "total_matched": match_result.get("succeeded", 0),
            "total_customized": len([r for r in customization_results if r.get("status") == "resume_customized"]),
            "total_submitted": apply_result.get("submitted", 0),
            "total_errors": len(self._errors),
            "errors": self._errors,
            "platforms_scraped": list(set(j.get("platform", "unknown") for j in all_jobs)),
        }

        self._report("pipeline", "completed", f"Pipeline complete: {summary['total_scraped']} scraped, {summary['total_matched']} matched, {summary['total_submitted']} applied")
        return summary

    # ------------------------------------------------------------------
    # Status query
    # ------------------------------------------------------------------

    def get_platform_status(self) -> List[Dict[str, Any]]:
        """Get connection status for all configured platforms.

        Returns:
            List of dicts with ``platform``, ``enabled``, ``registered``,
            ``has_credentials``.
        """
        platforms_config = self.config.get("platforms") or {}
        result = []

        # Include configured platforms
        for name, settings in platforms_config.items():
            if not isinstance(settings, dict):
                continue
            result.append({
                "platform": name,
                "enabled": settings.get("enabled", False),
                "registered": name in _SCRAPER_REGISTRY,
                "has_credentials": self._check_credentials(name),
                "priority": settings.get("priority", 99),
            })

        # Include registered but not configured
        for name in _SCRAPER_REGISTRY:
            if name not in platforms_config:
                result.append({
                    "platform": name,
                    "enabled": False,
                    "registered": True,
                    "has_credentials": self._check_credentials(name),
                    "priority": 99,
                })

        return sorted(result, key=lambda x: x.get("priority", 99))

    def _check_credentials(self, platform: str) -> bool:
        """Check if credentials are configured for a platform."""
        import os
        prefix = platform.upper().replace("_FEED", "")
        email = os.getenv(f"{prefix}_EMAIL", "")
        password = os.getenv(f"{prefix}_PASSWORD", "")
        return bool(email and password)
