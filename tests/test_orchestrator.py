"""Tests for the OrchestratorAgent and multi-platform architecture."""

from unittest.mock import MagicMock, patch

import pytest

from src.agents.base.base_scraper import BaseJobScraperAgent
from src.agents.orchestrator import (
    OrchestratorAgent,
    register_scraper,
    get_scraper_for_platform,
    list_registered_platforms,
    _SCRAPER_REGISTRY,
)


class TestBaseJobScraperAgent:
    """Tests for the abstract base scraper."""

    def test_cannot_instantiate_abc(self):
        """ABC cannot be directly instantiated."""
        with pytest.raises(TypeError):
            BaseJobScraperAgent()

    def test_concrete_implementation(self):
        """A concrete subclass can be instantiated."""

        class DummyScraper(BaseJobScraperAgent):
            PLATFORM_NAME = "dummy"

            def login(self):
                return True

            def search_jobs(self, keywords, location, **filters):
                return [{"title": "Test Job", "platform_job_id": "d_001"}]

            def extract_job_details(self, job_url):
                return {"title": "Test Job"}

            def apply_to_job(self, job_id, resume_path, cover_letter):
                return True

        scraper = DummyScraper()
        assert scraper.PLATFORM_NAME == "dummy"
        assert scraper.login() is True
        results = scraper.search_jobs(["Python"], "Remote")
        assert len(results) == 1


class TestPlatformRegistry:
    """Tests for the platform registry system."""

    def test_list_registered_platforms(self):
        """All expected platforms should be registered after auto-register."""
        platforms = list_registered_platforms()
        assert "linkedin" in platforms
        assert "dice" in platforms
        assert "indeed" in platforms

    def test_get_scraper_for_known_platform(self):
        """Should return a scraper instance for a registered platform."""
        scraper = get_scraper_for_platform("dice")
        assert scraper is not None
        assert scraper.PLATFORM_NAME == "dice"

    def test_get_scraper_for_unknown_platform(self):
        """Should raise ValueError for unknown platform."""
        with pytest.raises(ValueError, match="No scraper registered"):
            get_scraper_for_platform("nonexistent_platform")

    def test_register_custom_scraper(self):
        """Should allow registering a custom scraper."""

        class CustomScraper(BaseJobScraperAgent):
            PLATFORM_NAME = "custom_test"

            def login(self):
                return True

            def search_jobs(self, keywords, location, **filters):
                return []

            def extract_job_details(self, job_url):
                return {}

            def apply_to_job(self, job_id, resume_path, cover_letter):
                return False

        register_scraper("custom_test", CustomScraper)
        assert "custom_test" in list_registered_platforms()
        scraper = get_scraper_for_platform("custom_test")
        assert scraper.PLATFORM_NAME == "custom_test"

        # Cleanup
        _SCRAPER_REGISTRY.pop("custom_test", None)


class TestOrchestratorAgent:
    """Tests for the OrchestratorAgent."""

    def test_initialization(self):
        orch = OrchestratorAgent()
        assert orch is not None

    def test_initialization_with_progress_callback(self):
        callback = MagicMock()
        orch = OrchestratorAgent(on_progress=callback)
        assert orch._on_progress is callback

    def test_get_enabled_platforms(self):
        orch = OrchestratorAgent()
        enabled = orch.get_enabled_platforms()
        assert isinstance(enabled, list)

    @patch("src.agents.orchestrator.get_scraper_for_platform")
    def test_scrape_all_platforms_success(self, mock_get_scraper):
        mock_scraper = MagicMock()
        mock_scraper.run.return_value = [
            {"title": "Job 1", "platform": "dice"},
        ]
        mock_get_scraper.return_value = mock_scraper

        orch = OrchestratorAgent()
        results = orch.scrape_all_platforms(
            keywords=["Python"],
            location="Remote",
            max_jobs=10,
            platforms=["dice"],
        )
        assert len(results) == 1
        mock_scraper.run.assert_called_once()

    @patch("src.agents.orchestrator.get_scraper_for_platform")
    def test_scrape_all_platforms_with_error_isolation(self, mock_get_scraper):
        """A failing platform should not prevent others from running."""
        failing_scraper = MagicMock()
        failing_scraper.run.side_effect = Exception("Platform down")

        working_scraper = MagicMock()
        working_scraper.run.return_value = [{"title": "Good Job"}]

        def side_effect(platform):
            if platform == "dice":
                return failing_scraper
            return working_scraper

        mock_get_scraper.side_effect = side_effect

        orch = OrchestratorAgent()
        results = orch.scrape_all_platforms(
            keywords=["Python"],
            location="Remote",
            max_jobs=10,
            platforms=["dice", "indeed"],
        )
        # Indeed should succeed even though Dice failed
        assert len(results) == 1

    def test_get_platform_status(self):
        orch = OrchestratorAgent()
        status = orch.get_platform_status()
        assert isinstance(status, list)
        for item in status:
            assert "platform" in item
            assert "enabled" in item
