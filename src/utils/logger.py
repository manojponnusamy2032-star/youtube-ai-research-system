"""
Logging configuration for YouTube AI Research System.

This module provides a centralized logging configuration for the entire application.
"""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = "yairs",
    level: int = logging.INFO,
    log_file: Optional[str] = "logs/yairs.log",
    console_output: bool = True
) -> logging.Logger:
    """
    Set up and configure a logger instance.
    
    Args:
        name: Logger name (default: "yairs")
        level: Logging level (default: logging.INFO)
        log_file: Path to log file (default: "logs/yairs.log")
        console_output: Whether to output to console (default: True)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent adding handlers multiple times
    if logger.handlers:
        return logger
    
    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Logger name (typically __name__ from calling module)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(f"yairs.{name}")