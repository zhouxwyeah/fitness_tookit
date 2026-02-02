"""Configuration management for fitness_toolkit."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def _get_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Config:
    """Application configuration."""
    
    # Base paths
    BASE_DIR = Path(__file__).parent.parent
    DATA_DIR = BASE_DIR / "data"
    LOGS_DIR = BASE_DIR / "logs"
    DOWNLOADS_DIR = BASE_DIR / "downloads"
    
    # Database
    DATABASE_PATH = DATA_DIR / "fitness.db"
    
    # Security
    ENCRYPTION_KEY = os.environ.get("FITNESS_ENCRYPTION_KEY")
    
    # Logging
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    
    # Web
    WEB_HOST = "127.0.0.1"
    WEB_PORT = 5000
    
    # API Settings
    MAX_RETRY_COUNT = 3
    RETRY_DELAY_BASE = 1  # seconds
    REQUEST_TIMEOUT = 30  # seconds
    RATE_LIMIT_DELAY = 1  # seconds between requests

    # Duplicate detection / confirmation
    # When Garmin upload returns an empty result, we confirm duplicates by searching
    # Garmin activities near the COROS start time.
    DUPLICATE_CONFIRM_WINDOW_SECONDS = _get_int_env(
        "FITNESS_DUPLICATE_CONFIRM_WINDOW_SECONDS",
        15 * 60,
    )
    DUPLICATE_CONFIRM_SEARCH_DAYS = _get_int_env(
        "FITNESS_DUPLICATE_CONFIRM_SEARCH_DAYS",
        1,
    )
    
    @classmethod
    def ensure_directories(cls):
        """Ensure all required directories exist."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        cls.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    
    def __repr__(self):
        return f"Config(BASE_DIR={self.BASE_DIR}, DATABASE={self.DATABASE_PATH})"
