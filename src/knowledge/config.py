"""Configuration for the Knowledge Brain subsystem."""

from __future__ import annotations

import os
from pathlib import Path


class KnowledgeConfig:
    """Configuration for the Obsidian vault and knowledge subsystem."""

    # Default vault structure
    VAULT_FOLDERS = [
        "00_Inbox",
        "01_Projects",
        "02_Knowledge",
        "03_Research",
        "04_Insights",
        "05_Decisions",
        "06_Lessons",
        "07_Sources",
        "99_Index",
    ]

    def __init__(self, vault_path: str | Path | None = None) -> None:
        """Initialize knowledge configuration.

        Args:
            vault_path: Path to the Obsidian vault directory. If None,
                reads from KNOWLEDGE_VAULT_PATH env var or defaults to
                ./data/obsidian_vault relative to the project root.
        """
        if vault_path is not None:
            self.vault_path = Path(vault_path)
        else:
            env_path = os.getenv("KNOWLEDGE_VAULT_PATH")
            if env_path:
                self.vault_path = Path(env_path)
            else:
                # Default relative to project root (two levels up from this file)
                project_root = Path(__file__).resolve().parent.parent.parent
                self.vault_path = project_root / "data" / "obsidian_vault"

    def ensure_vault(self) -> Path:
        """Create the vault directory structure if it doesn't exist.

        Returns:
            The resolved vault path.
        """
        self.vault_path.mkdir(parents=True, exist_ok=True)
        for folder in self.VAULT_FOLDERS:
            (self.vault_path / folder).mkdir(parents=True, exist_ok=True)
        return self.vault_path

    def folder_for(self, folder_name: str) -> Path:
        """Return the absolute path for a vault subfolder."""
        return self.vault_path / folder_name

    def resolve_path(self, relative_path: str | Path) -> Path:
        """Resolve a path relative to the vault, preventing traversal.

        Args:
            relative_path: Path relative to the vault root.

        Returns:
            Absolute path inside the vault.

        Raises:
            ValueError: If the resolved path escapes the vault.
        """
        vault_root = self.vault_path.resolve()
        candidate = (vault_root / relative_path).resolve()
        if not str(candidate).startswith(str(vault_root)):
            raise ValueError(f"Path escapes vault: {relative_path}")
        return candidate