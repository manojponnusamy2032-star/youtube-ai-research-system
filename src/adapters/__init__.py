"""Adapter interface placeholders (Principle 4).

Each submodule exposes a small typed interface so future open-source
implementations can be plugged in behind a stable contract.  Only the
renderer adapter is wired today; the rest are placeholders by design.
"""
from src.adapters.renderer.base import RendererAdapter

__all__ = ["RendererAdapter"]
