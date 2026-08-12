"""Tests for RenderAssetResolver service."""

from __future__ import annotations

import pytest

from src.services.render_asset_resolver import LocalRenderAssetResolver, RenderAssetResolver


def test_asset_id_resolves_correctly() -> None:
    """Test that asset ID resolves to correct path."""
    resolver = LocalRenderAssetResolver()
    
    result = resolver.resolve_asset("abc")
    
    assert result == "assets/abc"


def test_character_id_resolves_correctly() -> None:
    """Test that character ID resolves to correct path."""
    resolver = LocalRenderAssetResolver()
    
    result = resolver.resolve_character("char_1")
    
    assert result == "assets/characters/char_1"


def test_multiple_assets_resolve_deterministically() -> None:
    """Test that multiple assets resolve deterministically."""
    resolver = LocalRenderAssetResolver()
    
    asset_ids = ["asset1", "asset2", "asset3"]
    results = [resolver.resolve_asset(asset_id) for asset_id in asset_ids]
    
    assert results == ["assets/asset1", "assets/asset2", "assets/asset3"]


def test_multiple_characters_resolve_deterministically() -> None:
    """Test that multiple characters resolve deterministically."""
    resolver = LocalRenderAssetResolver()
    
    character_ids = ["char_host", "char_guest", "char_narrator"]
    results = [resolver.resolve_character(char_id) for char_id in character_ids]
    
    assert results == [
        "assets/characters/char_host",
        "assets/characters/char_guest",
        "assets/characters/char_narrator",
    ]


def test_empty_asset_id_rejected() -> None:
    """Test that empty asset ID raises ValueError."""
    resolver = LocalRenderAssetResolver()
    
    with pytest.raises(ValueError, match="asset_id cannot be empty"):
        resolver.resolve_asset("")
    
    with pytest.raises(ValueError, match="asset_id cannot be empty"):
        resolver.resolve_asset("   ")


def test_empty_character_id_rejected() -> None:
    """Test that empty character ID raises ValueError."""
    resolver = LocalRenderAssetResolver()
    
    with pytest.raises(ValueError, match="character_id cannot be empty"):
        resolver.resolve_character("")
    
    with pytest.raises(ValueError, match="character_id cannot be empty"):
        resolver.resolve_character("\t")


def test_custom_asset_root_works() -> None:
    """Test that custom asset root directory is used."""
    resolver = LocalRenderAssetResolver(asset_root="custom_assets")
    
    asset_result = resolver.resolve_asset("test_asset")
    character_result = resolver.resolve_character("test_char")
    
    assert asset_result == "custom_assets/test_asset"
    assert character_result == "custom_assets/characters/test_char"


def test_same_id_always_produces_same_reference() -> None:
    """Test that same ID always produces the same reference."""
    resolver = LocalRenderAssetResolver()
    
    result1 = resolver.resolve_asset("consistent_id")
    result2 = resolver.resolve_asset("consistent_id")
    result3 = resolver.resolve_asset("consistent_id")
    
    assert result1 == result2 == result3
    assert result1 == "assets/consistent_id"


def test_resolver_can_be_injected_through_abstraction() -> None:
    """Test that resolver can be used through its abstraction."""
    
    class CustomResolver(RenderAssetResolver):
        def resolve_asset(self, asset_id: str) -> str:
            return f"custom://assets/{asset_id}"
        
        def resolve_character(self, character_id: str) -> str:
            return f"custom://characters/{character_id}"
    
    resolver: RenderAssetResolver = CustomResolver()
    
    asset_result = resolver.resolve_asset("test_asset")
    character_result = resolver.resolve_character("test_char")
    
    assert asset_result == "custom://assets/test_asset"
    assert character_result == "custom://characters/test_char"


def test_asset_id_with_special_characters() -> None:
    """Test that asset IDs with special characters are handled correctly."""
    resolver = LocalRenderAssetResolver()
    
    # Test with hyphens and underscores
    result = resolver.resolve_asset("my-asset_123")
    assert result == "assets/my-asset_123"
    
    # Test with dots
    result = resolver.resolve_asset("asset.v2")
    assert result == "assets/asset.v2"


def test_character_id_with_namespace() -> None:
    """Test that character IDs with namespaces are handled correctly."""
    resolver = LocalRenderAssetResolver()
    
    result = resolver.resolve_character("project_hero")
    assert result == "assets/characters/project_hero"