"""
Configuration management for YouTube AI Research System.

This module provides centralized configuration using environment variables
and default values.
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional


class Config:
    """
    Configuration class for YAIRS application.
    
    Loads configuration from environment variables with sensible defaults.
    All configuration values are validated on initialization.
    """
    
    def __init__(self, validate: bool = True) -> None:
        """
        Initialize and validate configuration.
        
        Args:
            validate: Whether to validate configuration (default: True)
        """
        # Base paths
        self.BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
        self.DATA_DIR: Path = self.BASE_DIR / "data"
        self.LOGS_DIR: Path = self.BASE_DIR / "logs"
        
        # YouTube API
        self.YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")
        
        # Database
        self.DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/database/youtube.db")
        
        # Collection defaults
        self.DEFAULT_MAX_RESULTS: int = int(os.getenv("DEFAULT_MAX_RESULTS", "50"))
        self.DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "en")
        self.DEFAULT_REGION: str = os.getenv("DEFAULT_REGION", "US")
        
        # Logging
        self.LOG_LEVEL: int = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper())
        self.LOG_FILE: str = os.getenv("LOG_FILE", "logs/yairs.log")
        
        if validate:
            self._validate()
        self._ensure_directories()
    
    def _validate(self) -> None:
        """Validate configuration values."""
        if not self.YOUTUBE_API_KEY:
            raise ValueError(
                "YouTube API key is required. Set YOUTUBE_API_KEY environment variable."
            )
        
        if self.DEFAULT_MAX_RESULTS < 1 or self.DEFAULT_MAX_RESULTS > 50:
            raise ValueError("DEFAULT_MAX_RESULTS must be between 1 and 50")
    
    def _ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    @property
    def database_url(self) -> str:
        """Get the full database URL."""
        return str(self.BASE_DIR / self.DATABASE_PATH)
    
    def __repr__(self) -> str:
        """String representation of config (hiding sensitive data)."""
        return (
            f"Config(\n"
            f"  BASE_DIR={self.BASE_DIR},\n"
            f"  DATABASE_PATH={self.DATABASE_PATH},\n"
            f"  DEFAULT_MAX_RESULTS={self.DEFAULT_MAX_RESULTS},\n"
            f"  DEFAULT_LANGUAGE={self.DEFAULT_LANGUAGE},\n"
            f"  DEFAULT_REGION={self.DEFAULT_REGION},\n"
            f"  LOG_LEVEL={logging.getLevelName(self.LOG_LEVEL)},\n"
            f"  LOG_FILE={self.LOG_FILE}\n"
            f")"
        )


# Global config instance (lazy initialization)
_config_instance: Optional[Config] = None


def get_config(validate: bool = True) -> Config:
    """
    Get the global config instance.
    
    Args:
        validate: Whether to validate configuration (default: True)
        
    Returns:
        Config instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(validate=validate)
    return _config_instance


# For backward compatibility, create a lazy config proxy
class _LazyConfig:
    """Lazy config proxy that defers initialization until first access."""
    
    def __getattr__(self, name: str) -> Any:
        """Get attribute from config, initializing if needed."""
        config = get_config(validate=True)
        return getattr(config, name)
    
    def __repr__(self) -> str:
        """String representation."""
        config = get_config(validate=True)
        return repr(config)


config = _LazyConfig()
