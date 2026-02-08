"""LangGraph workflow definition for the Springboard application.

Graph layout::

    feed_scrape ──┐
                  ├──> scrape ──> match ──> supervisor ──┬──> customize ──> apply ──> END
                  │                           │          │
                  │                           └──────────┘  (retry / skip logic)
"""

from typing import Any, Dict

from langgraph.graph import END, StateGraph

from src.graph.nodes import (
    apply_node,
    customize_node,
    feed_scrape_node,
    match_node,
    scrape_node,
    supervisor_node,
)
from src.state.app_state import AppState
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _route_supervisor(state: Dict[str, Any]) -> str:
    """Conditional edge function for supervisor routing."""
    next_step = state.get("next_step", "end")
    logger.debug("Supervisor routing decision: %s", next_step)

    valid_nodes = {"scrape", "match", "customize", "apply", "feed_scrape"}
    if next_step == "end":
        return END
    if next_step in valid_nodes:
        return next_step

    logger.warning("Unknown next_step '%s', ending workflow.", next_step)
    return END


def build_workflow() -> StateGraph:
    """Build and return the LangGraph StateGraph.

    Flow:
        feed_scrape -> scrape -> match -> supervisor -> customize -> apply -> END
    The supervisor can route back to any step for retries.
    """
    logger.info("Building Springboard workflow graph...")

    graph = StateGraph(AppState)

    # Add all nodes
    graph.add_node("feed_scrape", feed_scrape_node)
    graph.add_node("scrape", scrape_node)
    graph.add_node("match", match_node)
    graph.add_node("customize", customize_node)
    graph.add_node("apply", apply_node)
    graph.add_node("supervisor", supervisor_node)

    # Entry point: start with feed scraping
    graph.set_entry_point("feed_scrape")

    # Linear edges
    graph.add_edge("feed_scrape", "scrape")
    graph.add_edge("scrape", "match")
    graph.add_edge("match", "supervisor")

    # Conditional routing from supervisor
    graph.add_conditional_edges(
        "supervisor",
        _route_supervisor,
        {
            "scrape": "scrape",
            "match": "match",
            "customize": "customize",
            "apply": "apply",
            "feed_scrape": "feed_scrape",
            END: END,
        },
    )

    # After customize, go to apply; after apply, end
    graph.add_edge("customize", "apply")
    graph.add_edge("apply", END)

    logger.info("Workflow graph built successfully.")
    return graph


def compile_workflow():
    """Build and compile the workflow graph."""
    graph = build_workflow()
    compiled = graph.compile()
    logger.info("Workflow compiled successfully.")
    return compiled


def run_workflow(
    user_profile: Dict[str, Any],
    search_criteria: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute the full Springboard workflow.

    Args:
        user_profile: User profile data for matching.
        search_criteria: Job search parameters (keywords, location, platforms, etc.).

    Returns:
        Final workflow state with results.
    """
    from src.state.app_state import create_initial_state

    logger.info("Starting Springboard workflow...")
    logger.info("Search criteria: %s", search_criteria)

    initial_state = create_initial_state(
        user_profile=user_profile,
        search_criteria=search_criteria,
    )

    compiled = compile_workflow()

    try:
        final_state = compiled.invoke(initial_state)
        logger.info("Workflow completed successfully.")
        return final_state
    except Exception as e:
        logger.error("Workflow execution failed: %s", e)
        raise
