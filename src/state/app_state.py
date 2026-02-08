"""Application state definitions for LangGraph workflow."""

from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict


class AppState(TypedDict, total=False):
    """State schema for the Springboard LangGraph workflow.

    This TypedDict defines all state fields that flow through the graph nodes.
    Each node reads from and writes to this shared state.
    """

    # User context
    user_profile: Dict[str, Any]
    search_criteria: Dict[str, Any]

    # Job pipeline
    scraped_jobs: List[Dict[str, Any]]
    matched_jobs: List[Dict[str, Any]]

    # Customization outputs
    customized_resumes: Dict[int, str]  # job_id -> resume text
    cover_letters: Dict[int, str]  # job_id -> cover letter text

    # Application tracking
    pending_applications: List[Dict[str, Any]]
    submitted_applications: List[Dict[str, Any]]

    # Workflow control
    current_step: str
    next_step: str
    iteration: int
    errors: List[Dict[str, Any]]

    # Timestamps
    started_at: str
    last_checkpoint: str

    # Workflow status
    status: str  # "running", "paused", "completed", "failed"
    summary: Dict[str, Any]


def create_initial_state(
    user_profile: Optional[Dict[str, Any]] = None,
    search_criteria: Optional[Dict[str, Any]] = None,
) -> AppState:
    """Create a fresh initial state for the workflow.

    Args:
        user_profile: User profile data.
        search_criteria: Job search parameters.

    Returns:
        Initialized AppState dictionary.
    """
    return AppState(
        user_profile=user_profile or {},
        search_criteria=search_criteria or {},
        scraped_jobs=[],
        matched_jobs=[],
        customized_resumes={},
        cover_letters={},
        pending_applications=[],
        submitted_applications=[],
        current_step="",
        next_step="scrape",
        iteration=0,
        errors=[],
        started_at=datetime.utcnow().isoformat(),
        last_checkpoint="",
        status="running",
        summary={},
    )
