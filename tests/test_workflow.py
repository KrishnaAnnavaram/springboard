"""Tests for LangGraph workflow integration."""

from unittest.mock import MagicMock, patch

import pytest

from src.state.app_state import AppState, create_initial_state


class TestAppState:
    """Tests for application state management."""

    def test_create_initial_state(self):
        state = create_initial_state()
        assert state["scraped_jobs"] == []
        assert state["matched_jobs"] == []
        assert state["customized_resumes"] == {}
        assert state["cover_letters"] == {}
        assert state["pending_applications"] == []
        assert state["submitted_applications"] == []
        assert state["current_step"] == ""
        assert state["next_step"] == "scrape"
        assert state["iteration"] == 0
        assert state["errors"] == []
        assert state["status"] == "running"

    def test_create_initial_state_with_profile(self):
        profile = {"name": "Test User", "skills": ["Python"]}
        criteria = {"keywords": ["Engineer"], "location": "Remote"}
        state = create_initial_state(user_profile=profile, search_criteria=criteria)
        assert state["user_profile"]["name"] == "Test User"
        assert state["search_criteria"]["location"] == "Remote"

    def test_state_has_timestamps(self):
        state = create_initial_state()
        assert "started_at" in state
        assert state["started_at"] != ""


class TestWorkflowNodes:
    """Tests for individual workflow node functions."""

    @patch("src.graph.nodes.LinkedInScraperAgent")
    def test_scrape_node_success(self, mock_scraper_cls):
        from src.graph.nodes import scrape_node

        mock_instance = MagicMock()
        mock_instance.run.return_value = [
            {"id": 1, "title": "Engineer", "company": "TestCo"}
        ]
        mock_scraper_cls.return_value = mock_instance

        state = create_initial_state(
            search_criteria={"keywords": ["Engineer"], "location": "Remote", "max_jobs": 10}
        )
        result = scrape_node(state)

        assert len(result["scraped_jobs"]) == 1
        assert result["current_step"] == "scrape"

    @patch("src.graph.nodes.LinkedInScraperAgent")
    def test_scrape_node_failure(self, mock_scraper_cls):
        from src.graph.nodes import scrape_node

        mock_scraper_cls.return_value.run.side_effect = Exception("Network error")

        state = create_initial_state()
        result = scrape_node(state)

        assert "errors" in result
        assert len(result["errors"]) == 1
        assert result["errors"][0]["step"] == "scrape"

    @patch("src.graph.nodes.JobMatcherAgent")
    def test_match_node_success(self, mock_matcher_cls):
        from src.graph.nodes import match_node

        mock_instance = MagicMock()
        mock_instance.run.return_value = [
            {"id": 1, "title": "Engineer", "match_score": 85}
        ]
        mock_instance.config = MagicMock()
        mock_instance.config.auto_apply_threshold = 80
        mock_matcher_cls.return_value = mock_instance

        state = create_initial_state(user_profile={"name": "Test"})
        result = match_node(state)

        assert len(result["matched_jobs"]) == 1
        assert result["current_step"] == "match"

    @patch("src.graph.nodes.ResumeCustomizerAgent")
    def test_customize_node_success(self, mock_customizer_cls):
        from src.graph.nodes import customize_node

        mock_instance = MagicMock()
        mock_instance.run.return_value = {
            "resume_text": "Customized resume",
            "cover_letter": "Dear Hiring Manager...",
        }
        mock_customizer_cls.return_value = mock_instance

        state = create_initial_state()
        state["pending_applications"] = [{"job_id": 1}]
        result = customize_node(state)

        assert 1 in result["customized_resumes"]
        assert result["current_step"] == "customize"

    @patch("src.graph.nodes.LinkedInApplicationAgent")
    def test_apply_node_success(self, mock_applier_cls):
        from src.graph.nodes import apply_node

        mock_instance = MagicMock()
        mock_instance.run.return_value = {
            "success": True,
            "screenshot_path": "/tmp/screenshot.png",
        }
        mock_applier_cls.return_value = mock_instance

        state = create_initial_state()
        state["pending_applications"] = [
            {"job_id": 1, "job_title": "Engineer", "company": "TestCo"}
        ]
        state["customized_resumes"] = {1: "Resume text"}
        state["cover_letters"] = {1: "Cover letter"}
        result = apply_node(state)

        assert len(result["submitted_applications"]) == 1
        assert result["status"] == "completed"

    def test_supervisor_node(self):
        from src.graph.nodes import supervisor_node

        state = create_initial_state()
        state["current_step"] = "scrape"
        state["scraped_jobs"] = [{"id": 1}]
        state["matched_jobs"] = []
        state["customized_resumes"] = {}
        state["pending_applications"] = []

        result = supervisor_node(state)
        assert "next_step" in result


class TestWorkflowGraph:
    """Tests for workflow graph construction."""

    def test_build_workflow(self):
        from src.graph.workflow import build_workflow
        graph = build_workflow()
        assert graph is not None

    def test_compile_workflow(self):
        from src.graph.workflow import compile_workflow
        compiled = compile_workflow()
        assert compiled is not None

    @patch("src.graph.nodes.LinkedInScraperAgent")
    @patch("src.graph.nodes.JobMatcherAgent")
    def test_workflow_scrape_to_end(self, mock_matcher_cls, mock_scraper_cls):
        """Test workflow ends when no jobs are scraped."""
        from src.graph.workflow import compile_workflow

        mock_scraper_cls.return_value.run.return_value = []
        mock_matcher = MagicMock()
        mock_matcher.run.return_value = []
        mock_matcher.config = MagicMock()
        mock_matcher.config.auto_apply_threshold = 80
        mock_matcher_cls.return_value = mock_matcher

        compiled = compile_workflow()
        initial = create_initial_state(
            search_criteria={"keywords": ["Test"], "location": "Remote", "max_jobs": 5}
        )

        result = compiled.invoke(initial)
        assert result is not None
