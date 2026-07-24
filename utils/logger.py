"""
logger.py

Central logging configuration for the YouTube AI Research System.
"""

import logging

from config import LOGS_DIR, LOG_FILE, LOG_LEVEL

# Create logs directory if it doesn't exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Create logger
logger = logging.getLogger("youtube_research")

# Prevent duplicate handlers if imported multiple times
if not logger.handlers:

    logger.setLevel(LOG_LEVEL)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Save logs to file
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)

    # Show logs in terminal
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)