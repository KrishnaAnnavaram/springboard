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
        assert state["feed_posts"] == []
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
    """Tests for individual workflow node functions.

    Node functions now call agents with NO arguments (agents read from
    config/DB internally), so mocks are set up accordingly.
    """

    @patch("src.graph.nodes.OrchestratorAgent")
    def test_scrape_node_orchestrator_success(self, mock_orch_cls):
        from src.graph.nodes import scrape_node

        mock_instance = MagicMock()
        mock_instance.scrape_all_platforms.return_value = [
            {"id": 1, "title": "Engineer", "company": "TestCo", "platform": "linkedin"}
        ]
        mock_orch_cls.return_value = mock_instance

        state = create_initial_state(
            search_criteria={"keywords": ["Engineer"], "location": "Remote", "max_jobs": 10}
        )
        result = scrape_node(state)

        assert len(result["scraped_jobs"]) == 1
        assert result["current_step"] == "scrape"

    @patch("src.graph.nodes.OrchestratorAgent")
    @patch("src.graph.nodes.LinkedInScraperAgent")
    def test_scrape_node_falls_back_to_legacy(self, mock_scraper_cls, mock_orch_cls):
        """When orchestrator fails, fallback to legacy LinkedIn scraper."""
        from src.graph.nodes import scrape_node

        mock_orch_cls.return_value.scrape_all_platforms.side_effect = Exception("No platforms")
        mock_scraper = MagicMock()
        mock_scraper.scraped_jobs = [{"id": 1, "title": "Fallback"}]
        mock_scraper.run.return_value = None  # LinkedInScraperAgent.run() returns None
        mock_scraper_cls.return_value = mock_scraper

        state = create_initial_state()
        result = scrape_node(state)

        assert len(result["scraped_jobs"]) == 1
        assert result["current_step"] == "scrape"
        mock_scraper.run.assert_called_once()  # called with no args

    @patch("src.graph.nodes.OrchestratorAgent")
    @patch("src.graph.nodes.LinkedInScraperAgent")
    def test_scrape_node_total_failure(self, mock_scraper_cls, mock_orch_cls):
        """When both orchestrator and legacy scraper fail."""
        from src.graph.nodes import scrape_node

        mock_orch_cls.return_value.scrape_all_platforms.side_effect = Exception("No platforms")
        mock_scraper_cls.return_value.run.side_effect = Exception("Network error")

        state = create_initial_state()
        result = scrape_node(state)

        assert "errors" in result
        assert len(result["errors"]) == 1
        assert result["errors"][0]["step"] == "scrape"

    @patch("src.graph.nodes.JobMatcherAgent")
    def test_match_node_success(self, mock_matcher_cls):
        from src.graph.nodes import match_node

        # matcher.run() returns summary dict, not a list
        mock_instance = MagicMock()
        mock_instance.run.return_value = {"processed": 5, "succeeded": 3, "failed": 2}
        mock_instance.config = MagicMock()
        mock_instance.config.auto_apply_threshold = 80
        mock_instance.config.min_match_score = 60
        mock_matcher_cls.return_value = mock_instance

        # Mock the local imports inside match_node
        mock_job = MagicMock()
        mock_job.id = 1
        mock_job.title = "Engineer"
        mock_job.company = "TestCo"
        mock_job.location = "Remote"
        mock_job.match_score = 85
        mock_job.match_reasoning = "Good fit"
        mock_job.platform = "linkedin"

        mock_repo = MagicMock()
        mock_repo.get_matched_jobs.return_value = [mock_job]

        mock_session = MagicMock()

        with patch("src.database.connection.get_db") as mock_get_db, \
             patch("src.database.repositories.job_repository.JobRepository", return_value=mock_repo):
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

            state = create_initial_state(user_profile={"name": "Test"})
            result = match_node(state)

        assert result["current_step"] == "match"
        mock_instance.run.assert_called_once()  # no args

    @patch("src.graph.nodes.ResumeCustomizerAgent")
    def test_customize_node_success(self, mock_customizer_cls):
        from src.graph.nodes import customize_node

        # customizer.run() returns List[Dict] with per-job results
        mock_instance = MagicMock()
        mock_instance.run.return_value = [
            {
                "job_id": 1,
                "status": "success",
                "resume_text": "Customized resume",
                "cover_letter": "Dear Hiring Manager...",
            },
            {
                "job_id": 2,
                "status": "failed",
                "resume_text": "",
                "cover_letter": "",
            },
        ]
        mock_customizer_cls.return_value = mock_instance

        state = create_initial_state()
        result = customize_node(state)

        assert 1 in result["customized_resumes"]
        assert 2 not in result["customized_resumes"]  # failed entries excluded
        assert result["current_step"] == "customize"
        mock_instance.run.assert_called_once()  # no args

    @patch("src.graph.nodes.LinkedInApplicationAgent")
    def test_apply_node_success(self, mock_applier_cls):
        from src.graph.nodes import apply_node

        # applier.run() returns summary dict with details list
        mock_instance = MagicMock()
        mock_instance.run.return_value = {
            "processed": 1,
            "succeeded": 1,
            "failed": 0,
            "details": [
                {"job_id": 1, "title": "Engineer", "company": "TestCo", "status": "success"},
            ],
        }
        mock_applier_cls.return_value = mock_instance

        state = create_initial_state()
        result = apply_node(state)

        assert len(result["submitted_applications"]) == 1
        assert result["status"] == "completed"
        mock_instance.run.assert_called_once()  # no args

    @patch("src.graph.nodes.OrchestratorAgent")
    def test_feed_scrape_node_success(self, mock_orch_cls):
        from src.graph.nodes import feed_scrape_node

        mock_instance = MagicMock()
        mock_instance.scrape_feed.return_value = [
            {"author": "Recruiter", "text": "We are hiring!", "keywords_found": ["hiring"]},
        ]
        mock_orch_cls.return_value = mock_instance

        state = create_initial_state()
        result = feed_scrape_node(state)

        assert len(result["feed_posts"]) == 1
        assert result["current_step"] == "feed_scrape"

    @patch("src.graph.nodes.OrchestratorAgent")
    def test_feed_scrape_node_failure(self, mock_orch_cls):
        from src.graph.nodes import feed_scrape_node

        mock_orch_cls.return_value.scrape_feed.side_effect = Exception("Feed error")

        state = create_initial_state()
        result = feed_scrape_node(state)

        assert "errors" in result
        assert result["errors"][0]["step"] == "feed_scrape"

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

    def test_workflow_has_feed_scrape_node(self):
        from src.graph.workflow import build_workflow
        graph = build_workflow()
        assert "feed_scrape" in graph.nodes
