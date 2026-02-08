"""Tests for agent modules with mocked external services."""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.agents.supervisor import SupervisorAgent
from src.agents.base.base_scraper import BaseJobScraperAgent


class TestSupervisorAgent:
    """Tests for SupervisorAgent routing logic."""

    def setup_method(self):
        self.supervisor = SupervisorAgent()

    def test_should_continue_normal(self):
        state = {"errors": [], "iteration": 0}
        assert self.supervisor.should_continue(state) is True

    def test_should_continue_max_retries(self):
        state = {"errors": [{}, {}, {}], "iteration": 0}
        assert self.supervisor.should_continue(state) is False

    def test_should_continue_max_iterations(self):
        state = {"errors": [], "iteration": 101}
        assert self.supervisor.should_continue(state) is False

    def test_route_from_scrape_with_jobs(self):
        state = {
            "current_step": "scrape",
            "scraped_jobs": [{"id": 1}],
            "matched_jobs": [],
            "customized_resumes": {},
            "pending_applications": [],
            "errors": [],
            "iteration": 0,
        }
        assert self.supervisor.route(state) == "match"

    def test_route_from_scrape_no_jobs(self):
        state = {
            "current_step": "scrape",
            "scraped_jobs": [],
            "matched_jobs": [],
            "customized_resumes": {},
            "pending_applications": [],
            "errors": [],
            "iteration": 0,
        }
        assert self.supervisor.route(state) == "end"

    def test_route_from_match_with_matches(self):
        state = {
            "current_step": "match",
            "scraped_jobs": [{"id": 1}],
            "matched_jobs": [{"id": 1, "score": 85}],
            "customized_resumes": {},
            "pending_applications": [],
            "errors": [],
            "iteration": 0,
        }
        assert self.supervisor.route(state) == "customize"

    def test_route_from_match_no_matches(self):
        state = {
            "current_step": "match",
            "scraped_jobs": [{"id": 1}],
            "matched_jobs": [],
            "customized_resumes": {},
            "pending_applications": [],
            "errors": [],
            "iteration": 0,
        }
        assert self.supervisor.route(state) == "end"

    def test_route_from_customize(self):
        state = {
            "current_step": "customize",
            "scraped_jobs": [{"id": 1}],
            "matched_jobs": [{"id": 1}],
            "customized_resumes": {1: "resume"},
            "pending_applications": [{"job_id": 1}],
            "errors": [],
            "iteration": 0,
        }
        assert self.supervisor.route(state) == "apply"

    def test_route_from_apply(self):
        state = {
            "current_step": "apply",
            "scraped_jobs": [{"id": 1}],
            "matched_jobs": [{"id": 1}],
            "customized_resumes": {1: "resume"},
            "pending_applications": [],
            "errors": [],
            "iteration": 0,
        }
        assert self.supervisor.route(state) == "end"

    def test_route_default_start(self):
        state = {
            "current_step": "",
            "scraped_jobs": [],
            "matched_jobs": [],
            "customized_resumes": {},
            "pending_applications": [],
            "errors": [],
            "iteration": 0,
        }
        assert self.supervisor.route(state) == "scrape"

    def test_route_with_retryable_error(self):
        state = {
            "current_step": "match",
            "scraped_jobs": [{"id": 1}],
            "matched_jobs": [],
            "customized_resumes": {},
            "pending_applications": [],
            "errors": [{"step": "match", "retry_count": 0}],
            "iteration": 0,
        }
        assert self.supervisor.route(state) == "match"

    def test_route_error_max_retries_skip(self):
        state = {
            "current_step": "match",
            "scraped_jobs": [{"id": 1}],
            "matched_jobs": [],
            "customized_resumes": {},
            "pending_applications": [],
            "errors": [{"step": "match", "retry_count": 3}],
            "iteration": 0,
        }
        result = self.supervisor.route(state)
        assert result == "customize"

    def test_evaluate_results(self):
        state = {
            "scraped_jobs": [1, 2, 3, 4, 5],
            "matched_jobs": [1, 2, 3],
            "customized_resumes": {1: "r", 2: "r"},
            "submitted_applications": [1, 2],
            "errors": [{"e": 1}],
        }
        summary = self.supervisor.evaluate_results(state)
        assert summary["total_scraped"] == 5
        assert summary["total_matched"] == 3
        assert summary["total_submitted"] == 2
        assert summary["match_rate"] == 60.0

    def test_handle_checkpoint(self):
        state = {"iteration": 5}
        updated = self.supervisor.handle_checkpoint(state)
        assert updated["iteration"] == 6
        assert "last_checkpoint" in updated

    def test_next_after_known_step(self):
        assert self.supervisor._next_after("scrape") == "match"
        assert self.supervisor._next_after("match") == "customize"
        assert self.supervisor._next_after("apply") == "end"

    def test_next_after_unknown_step(self):
        assert self.supervisor._next_after("unknown") == "end"


class TestLinkedInScraperAgent:
    """Tests for LinkedInScraperAgent with mocked Selenium."""

    @patch("src.agents.linkedin_scraper.webdriver")
    def test_scraper_initialization(self, mock_webdriver):
        from src.agents.linkedin_scraper import LinkedInScraperAgent
        mock_webdriver.Chrome.return_value = MagicMock()
        agent = LinkedInScraperAgent()
        assert agent.config is not None

    @patch("src.agents.linkedin_scraper.webdriver")
    def test_scraper_has_run_method(self, mock_webdriver):
        from src.agents.linkedin_scraper import LinkedInScraperAgent
        mock_webdriver.Chrome.return_value = MagicMock()
        agent = LinkedInScraperAgent()
        assert hasattr(agent, "run")
        assert callable(agent.run)


class TestJobMatcherAgent:
    """Tests for JobMatcherAgent with mocked Claude API."""

    @patch("src.agents.job_matcher.anthropic.Anthropic")
    def test_matcher_initialization(self, mock_anthropic):
        from src.agents.job_matcher import JobMatcherAgent
        agent = JobMatcherAgent()
        assert agent.config is not None

    @patch("src.agents.job_matcher.anthropic.Anthropic")
    def test_matcher_has_required_methods(self, mock_anthropic):
        from src.agents.job_matcher import JobMatcherAgent
        agent = JobMatcherAgent()
        assert hasattr(agent, "analyze_job")
        assert hasattr(agent, "match_all_jobs")
        assert hasattr(agent, "run")


class TestResumeCustomizerAgent:
    """Tests for ResumeCustomizerAgent with mocked Claude API."""

    @patch("src.agents.resume_customizer.anthropic.Anthropic")
    def test_customizer_initialization(self, mock_anthropic):
        from src.agents.resume_customizer import ResumeCustomizerAgent
        agent = ResumeCustomizerAgent()
        assert agent.config is not None

    @patch("src.agents.resume_customizer.anthropic.Anthropic")
    def test_customizer_has_required_methods(self, mock_anthropic):
        from src.agents.resume_customizer import ResumeCustomizerAgent
        agent = ResumeCustomizerAgent()
        assert hasattr(agent, "customize_resume")
        assert hasattr(agent, "generate_cover_letter")
        assert hasattr(agent, "run")


class TestLinkedInApplicationAgent:
    """Tests for LinkedInApplicationAgent with mocked Selenium."""

    @patch("src.agents.linkedin_applier.webdriver")
    def test_applier_initialization(self, mock_webdriver):
        from src.agents.linkedin_applier import LinkedInApplicationAgent
        mock_webdriver.Chrome.return_value = MagicMock()
        agent = LinkedInApplicationAgent()
        assert agent.config is not None

    @patch("src.agents.linkedin_applier.webdriver")
    def test_applier_has_required_methods(self, mock_webdriver):
        from src.agents.linkedin_applier import LinkedInApplicationAgent
        mock_webdriver.Chrome.return_value = MagicMock()
        agent = LinkedInApplicationAgent()
        assert hasattr(agent, "navigate_to_job")
        assert hasattr(agent, "fill_form")
        assert hasattr(agent, "submit_application")
        assert hasattr(agent, "run")
