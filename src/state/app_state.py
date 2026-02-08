"""Application state definitions for LangGraph workflow.

LangGraph requires that list-valued state fields use ``Annotated`` with a
reducer function so that node return values are *merged* rather than
silently replaced.  We use ``operator.add`` for list fields so that each
node's output is appended to the existing list.
"""

import operator
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class AppState(TypedDict, total=False):
    """State schema for the Springboard LangGraph workflow.

    Fields annotated with ``Annotated[..., operator.add]`` accumulate values
    across nodes (LangGraph reducer pattern).  Scalar / dict fields are
    overwritten by the latest node return.
    """

    # User context
    user_profile: Dict[str, Any]
    search_criteria: Dict[str, Any]

    # Job pipeline — list fields use add-reducer
    scraped_jobs: Annotated[List[Dict[str, Any]], operator.add]
    matched_jobs: Annotated[List[Dict[str, Any]], operator.add]

    # Customization outputs (dict — latest node wins)
    customized_resumes: Dict[int, str]
    cover_letters: Dict[int, str]

    # Application tracking
    pending_applications: Annotated[List[Dict[str, Any]], operator.add]
    submitted_applications: Annotated[List[Dict[str, Any]], operator.add]

    # Feed posts from LinkedIn feed scraping
    feed_posts: Annotated[List[Dict[str, Any]], operator.add]

    # Workflow control (scalars — latest node wins)
    current_step: str
    next_step: str
    iteration: int
    errors: Annotated[List[Dict[str, Any]], operator.add]

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
    """Create a fresh initial state for the workflow."""
    return AppState(
        user_profile=user_profile or {},
        search_criteria=search_criteria or {},
        scraped_jobs=[],
        matched_jobs=[],
        customized_resumes={},
        cover_letters={},
        pending_applications=[],
        submitted_applications=[],
        feed_posts=[],
        current_step="",
        next_step="scrape",
        iteration=0,
        errors=[],
        started_at=datetime.utcnow().isoformat(),
        last_checkpoint="",
        status="running",
        summary={},
    )
