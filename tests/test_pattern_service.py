"""Unit tests for dataset-wide pattern aggregation service."""

from __future__ import annotations

from unittest.mock import Mock

from src.services.pattern_service import PatternService


def _sample_rows() -> list[dict[str, object]]:
    return [
        {
            "hook_type": "Curiosity Hook",
            "emotion": "Curiosity",
            "story_structure": "Problem-Solution",
            "title_formula": "How to X",
            "thumbnail_pattern": "Mystery Face",
            "retention_techniques": "['Open Loop', 'Pattern Interrupt']",
            "viral_score": 88,
            "main_topic": "AI",
            "channel": "Channel A",
            "view_count": 1000000,
        },
        {
            "hook_type": "Curiosity Hook",
            "emotion": "Fear",
            "story_structure": "Problem-Solution",
            "title_formula": "How to X",
            "thumbnail_pattern": "Mystery Face",
            "retention_techniques": "['Open Loop']",
            "viral_score": 92,
            "main_topic": "AI",
            "channel": "Channel A",
            "view_count": 900000,
        },
        {
            "hook_type": "Fear Hook",
            "emotion": "Fear",
            "story_structure": "Before-After",
            "title_formula": "Mistakes to Avoid",
            "thumbnail_pattern": "Bold Text",
            "retention_techniques": "['Teaser']",
            "viral_score": 70,
            "main_topic": "Productivity",
            "channel": "Channel B",
            "view_count": 500000,
        },
    ]


def test_count_methods_return_percentage_distribution() -> None:
    mock_db = Mock()
    service = PatternService(mock_db)
    rows = _sample_rows()

    hooks = service.count_hooks(rows)
    stories = service.count_story_structures(rows)
    emotions = service.count_emotions(rows)
    retention = service.count_retention(rows)

    assert hooks["Curiosity Hook"] == 66.67
    assert stories["Problem-Solution"] == 66.67
    assert emotions["Fear"] == 66.67
    assert retention["Open Loop"] == 50.0


def test_generate_report_returns_required_shape() -> None:
    mock_db = Mock()
    mock_db.get_all_analysis_with_video_data.return_value = _sample_rows()
    service = PatternService(mock_db)

    report = service.generate_report()

    assert report["videos_analyzed"] == 3
    assert report["hooks"]["Curiosity Hook"] == 66.67
    assert report["stories"]["Problem-Solution"] == 66.67
    assert report["average_viral_score"] == 83.33
    assert len(report["top_channels"]) == 2
    assert report["top_channels"][0]["channel"] == "Channel A"
    assert len(report["top_topics"]) == 2
    assert report["top_topics"][0]["topic"] == "AI"
    assert 0.0 <= report["confidence"] <= 1.0
