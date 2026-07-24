"""
config.py

Central configuration for the YouTube AI Research System.
Change values here instead of hardcoding them throughout the project.
"""

from pathlib import Path

# ==========================================================
# PROJECT PATHS
# ==========================================================

PROJECT_ROOT = Path(__file__).parent

DATABASE_DIR = PROJECT_ROOT / "database"
DATABASE_PATH = DATABASE_DIR / "youtube.db"

LOGS_DIR = PROJECT_ROOT / "logs"

OUTPUT_DIR = PROJECT_ROOT / "output"

# ==========================================================
# YOUTUBE SETTINGS
# ==========================================================

DEFAULT_SEARCH_KEYWORD = "stickman psychology"

MAX_RESULTS = 10

SEARCH_LANGUAGE = "en"

# ==========================================================
# DATABASE SETTINGS
# ==========================================================

ENABLE_DUPLICATE_CHECK = True

# ==========================================================
# LOGGING SETTINGS
# ==========================================================

LOG_LEVEL = "INFO"

LOG_FILE = LOGS_DIR / "collector.log"

# ==========================================================
# NETWORK SETTINGS
# ==========================================================

REQUEST_TIMEOUT = 30

MAX_RETRIES = 3

RETRY_DELAY = 2

# ==========================================================
# FUTURE AI SETTINGS
# ==========================================================

OLLAMA_MODEL = "qwen3:4b"

EMBEDDING_MODEL = ""

OPENAI_MODEL = ""