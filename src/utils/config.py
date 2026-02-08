"""Configuration management for Springboard application."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv


class Config:
    """Centralized configuration loader from .env and YAML files."""

    _instance: Optional["Config"] = None
    _config: Dict[str, Any] = {}

    def __new__(cls) -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """Load configuration from .env and YAML files."""
        project_root = Path(__file__).parent.parent.parent
        load_dotenv(project_root / ".env")

        config_path = project_root / "config" / "config.yaml"
        if config_path.exists():
            with open(config_path, "r") as f:
                self._config = yaml.safe_load(f) or {}

    @property
    def project_root(self) -> Path:
        return Path(__file__).parent.parent.parent

    # --- Environment Variables ---

    @property
    def linkedin_email(self) -> str:
        return os.getenv("LINKEDIN_EMAIL", "")

    @property
    def linkedin_password(self) -> str:
        return os.getenv("LINKEDIN_PASSWORD", "")

    @property
    def anthropic_api_key(self) -> str:
        return os.getenv("ANTHROPIC_API_KEY", "")

    @property
    def database_url(self) -> str:
        default = f"sqlite:///{self.project_root / 'data' / 'springboard.db'}"
        return os.getenv("DATABASE_URL", default)

    @property
    def log_level(self) -> str:
        return os.getenv("LOG_LEVEL", "INFO")

    @property
    def max_applications_per_day(self) -> int:
        return int(os.getenv("MAX_APPLICATIONS_PER_DAY", "20"))

    @property
    def scraping_delay(self) -> int:
        return int(os.getenv("SCRAPING_DELAY", "5"))

    # --- YAML Config Sections ---

    @property
    def user_defaults(self) -> Dict[str, Any]:
        return self._config.get("user", {})

    @property
    def job_search(self) -> Dict[str, Any]:
        return self._config.get("job_search", {})

    @property
    def matching(self) -> Dict[str, Any]:
        return self._config.get("matching", {})

    @property
    def automation(self) -> Dict[str, Any]:
        return self._config.get("automation", {})

    @property
    def linkedin_config(self) -> Dict[str, Any]:
        return self._config.get("linkedin", {})

    @property
    def anthropic_config(self) -> Dict[str, Any]:
        return self._config.get("anthropic", {})

    @property
    def database_config(self) -> Dict[str, Any]:
        return self._config.get("database", {})

    @property
    def platforms_config(self) -> Dict[str, Any]:
        return self._config.get("platforms", {})

    @property
    def logging_config(self) -> Dict[str, Any]:
        return self._config.get("logging", {})

    # --- Convenience Accessors ---

    @property
    def anthropic_model(self) -> str:
        return self.anthropic_config.get("model", "claude-sonnet-4-5-20250929")

    @property
    def anthropic_max_tokens(self) -> int:
        return self.anthropic_config.get("max_tokens", 4096)

    @property
    def anthropic_temperature(self) -> float:
        return self.anthropic_config.get("temperature", 0.3)

    @property
    def match_weights(self) -> Dict[str, float]:
        return self.matching.get("weights", {
            "skills": 0.40,
            "experience": 0.25,
            "location": 0.15,
            "salary": 0.10,
            "company": 0.10,
        })

    @property
    def min_match_score(self) -> int:
        return self.matching.get("min_match_score", 60)

    @property
    def auto_apply_threshold(self) -> int:
        return self.matching.get("auto_apply_threshold", 80)

    @property
    def search_titles(self) -> list:
        return self.job_search.get("titles", [])

    @property
    def search_locations(self) -> list:
        return self.job_search.get("locations", [])

    @property
    def easy_apply_only(self) -> bool:
        return self.job_search.get("easy_apply_only", True)

    @property
    def max_jobs_per_search(self) -> int:
        return self.job_search.get("max_jobs_per_search", 50)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a nested config value using dot notation."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None
        cls._config = {}
