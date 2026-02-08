"""Structured logging setup for Springboard application."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from src.utils.config import Config


def get_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """Create a configured logger instance.

    Args:
        name: Logger name (typically __name__).
        log_file: Optional override for log file path.

    Returns:
        Configured logging.Logger instance.
    """
    config = Config()
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logger.setLevel(log_level)

    log_format = config.logging_config.get(
        "format",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    formatter = logging.Formatter(log_format)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    if log_file is None:
        log_file = config.logging_config.get(
            "file",
            str(config.project_root / "data" / "logs" / "springboard.log")
        )

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    max_bytes = config.logging_config.get("max_bytes", 10_485_760)
    backup_count = config.logging_config.get("backup_count", 5)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
