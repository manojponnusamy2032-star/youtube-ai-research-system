"""TTS adapter interface placeholder (Principle 4)."""
from __future__ import annotations
from abc import ABC, abstractmethod


class TTSAdapter(ABC):
    """Interface for a future open-source TTS implementation."""

    @abstractmethod
    def synthesize(self, text: str, output_path: str) -> str:
        raise NotImplementedError
