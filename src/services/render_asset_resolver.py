"""Service for resolving render asset and character identifiers to deterministic references."""

from __future__ import annotations

from typing import Any


class RenderAssetResolver:
    """Abstract base class for resolving render assets."""

    def resolve_asset(self, asset_id: str) -> str:
        """Resolve an asset ID to a deterministic reference.
        
        Args:
            asset_id: Asset identifier
            
        Returns:
            Resolved asset reference path
        """
        raise NotImplementedError

    def resolve_character(self, character_id: str) -> str:
        """Resolve a character ID to a deterministic reference.
        
        Args:
            character_id: Character identifier
            
        Returns:
            Resolved character reference path
        """
        raise NotImplementedError


class LocalRenderAssetResolver(RenderAssetResolver):
    """Deterministic local asset resolver that maps IDs to filesystem paths."""

    def __init__(self, asset_root: str = "assets") -> None:
        """Initialize the resolver with an asset root directory.
        
        Args:
            asset_root: Root directory for assets (default: "assets")
        """
        self.asset_root = asset_root

    def resolve_asset(self, asset_id: str) -> str:
        """Resolve an asset ID to a deterministic filesystem path.
        
        Args:
            asset_id: Asset identifier
            
        Returns:
            Resolved asset path in format: {asset_root}/{asset_id}
            
        Raises:
            ValueError: If asset_id is empty or whitespace-only
        """
        if not asset_id or not str(asset_id).strip():
            raise ValueError("asset_id cannot be empty")
        
        asset_id_str = str(asset_id).strip()
        return f"{self.asset_root}/{asset_id_str}"

    def resolve_character(self, character_id: str) -> str:
        """Resolve a character ID to a deterministic filesystem path.
        
        Args:
            character_id: Character identifier
            
        Returns:
            Resolved character path in format: {asset_root}/characters/{character_id}
            
        Raises:
            ValueError: If character_id is empty or whitespace-only
        """
        if not character_id or not str(character_id).strip():
            raise ValueError("character_id cannot be empty")
        
        character_id_str = str(character_id).strip()
        return f"{self.asset_root}/characters/{character_id_str}"