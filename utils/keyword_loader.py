"""
Loads search keywords from keywords.txt
"""

from pathlib import Path

KEYWORDS_FILE = Path("keywords.txt")


def load_keywords():
    """
    Read keywords.txt and return a list of keywords.
    """

    if not KEYWORDS_FILE.exists():
        return []

    with open(KEYWORDS_FILE, "r", encoding="utf-8") as file:

        keywords = [
            line.strip()
            for line in file
            if line.strip()
        ]

    return keywords