"""Supervisor agent for workflow routing and error handling."""

from typing import Any, Dict, List, Optional

from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SupervisorAgent:
    """Decision-making agent for LangGraph workflow routing.

    Determines the next step in the workflow based on current state,
    handles error recovery, and manages checkpoints.
    """

    def __init__(self) -> None:
        self.config = Config()
        self.max_retries = self.config.automation.get("retry_attempts", 3)

    def should_continue(self, state: Dict[str, Any]) -> bool:
        """Determine if the workflow should continue processing.

        Args:
            state: Current workflow state.

        Returns:
            True if workflow should continue, False to stop.
        """
        errors = state.get("errors", [])
        if len(errors) >= self.max_retries:
            logger.warning(
                "Max retries (%d) reached. Stopping workflow.", self.max_retries
            )
            return False

        iteration = state.get("iteration", 0)
        if iteration > 100:
            logger.warning("Max iterations reached. Stopping workflow.")
            return False

        return True

    def route(self, state: Dict[str, Any]) -> str:
        """Determine the next node to execute based on current state.

        Args:
            state: Current workflow state.

        Returns:
            Name of the next node to execute.
        """
        current_step = state.get("current_step", "")
        errors = state.get("errors", [])
        scraped_jobs = state.get("scraped_jobs", [])
        matched_jobs = state.get("matched_jobs", [])
        customized_resumes = state.get("customized_resumes", {})
        pending_applications = state.get("pending_applications", [])

        logger.info(
            "Routing from step '%s' | scraped=%d, matched=%d, customized=%d, pending=%d",
            current_step,
            len(scraped_jobs),
            len(matched_jobs),
            len(customized_resumes),
            len(pending_applications),
        )

        if not self.should_continue(state):
            logger.info("Supervisor decided to end workflow.")
            return "end"

        # Handle errors with retry
        if errors:
            last_error = errors[-1] if errors else {}
            failed_step = last_error.get("step", "")
            retry_count = last_error.get("retry_count", 0)

            if retry_count < self.max_retries:
                logger.info(
                    "Retrying step '%s' (attempt %d/%d)",
                    failed_step, retry_count + 1, self.max_retries,
                )
                return failed_step
            else:
                logger.warning("Skipping step '%s' after max retries.", failed_step)
                return self._next_after(failed_step)

        # Normal routing logic
        if current_step == "scrape":
            if scraped_jobs:
                return "match"
            else:
                logger.info("No jobs scraped. Ending workflow.")
                return "end"

        elif current_step == "match":
            if matched_jobs:
                return "customize"
            else:
                logger.info("No matched jobs above threshold. Ending workflow.")
                return "end"

        elif current_step == "customize":
            if pending_applications:
                return "apply"
            else:
                logger.info("No applications pending. Ending workflow.")
                return "end"

        elif current_step == "apply":
            logger.info("Application phase complete. Ending workflow.")
            return "end"

        # Default: start from scraping
        logger.info("Starting workflow from scrape step.")
        return "scrape"

    def _next_after(self, step: str) -> str:
        """Get the next logical step after a given step.

        Args:
            step: The current/failed step name.

        Returns:
            Name of the next step.
        """
        order = ["scrape", "match", "customize", "apply", "end"]
        try:
            idx = order.index(step)
            return order[min(idx + 1, len(order) - 1)]
        except ValueError:
            return "end"

    def evaluate_results(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate workflow results and generate summary.

        Args:
            state: Final workflow state.

        Returns:
            Summary dictionary with statistics.
        """
        scraped = len(state.get("scraped_jobs", []))
        matched = len(state.get("matched_jobs", []))
        customized = len(state.get("customized_resumes", {}))
        submitted = len(state.get("submitted_applications", []))
        errors = len(state.get("errors", []))

        summary = {
            "total_scraped": scraped,
            "total_matched": matched,
            "total_customized": customized,
            "total_submitted": submitted,
            "total_errors": errors,
            "match_rate": round((matched / scraped * 100), 1) if scraped > 0 else 0,
            "apply_rate": round((submitted / matched * 100), 1) if matched > 0 else 0,
        }

        logger.info("Workflow summary: %s", summary)
        return summary

    def handle_checkpoint(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Update state with checkpoint information.

        Args:
            state: Current workflow state.

        Returns:
            Updated state with checkpoint timestamp.
        """
        from datetime import datetime

        state["last_checkpoint"] = datetime.utcnow().isoformat()
        state["iteration"] = state.get("iteration", 0) + 1
        logger.debug(
            "Checkpoint saved at iteration %d", state["iteration"]
        )
        return state
