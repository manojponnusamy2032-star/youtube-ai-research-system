"""Unit tests for knowledge persistence and querying service."""

from __future__ import annotations

from src.database.database_service import DatabaseService
from src.models.knowledge import KnowledgeEntry
from src.services.knowledge_service import KnowledgeService


def _entry(
    category: str,
    pattern: str,
    frequency: float,
    views: float,
    confidence: float,
) -> KnowledgeEntry:
    return KnowledgeEntry(
        category=category,
        pattern=pattern,
        frequency=frequency,
        average_views=views,
        confidence=confidence,
        recommendation=f"Prefer {pattern} usage.",
    )


def test_save_entry_and_get_by_category(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "test.db"))
    db.connect()
    db.create_tables()
    service = KnowledgeService(db)

    row_id = service.save_entry(_entry("Hook", "Curiosity", 68, 5_200_000, 94))
    results = service.get_by_category("Hook")

    assert row_id > 0
    assert len(results) == 1
    assert results[0].pattern == "Curiosity"
    assert results[0].confidence == 94.0
    db.disconnect()


def test_save_many_and_get_best_patterns(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "test.db"))
    db.connect()
    db.create_tables()
    service = KnowledgeService(db)

    inserted = service.save_many([
        _entry("Hook", "Curiosity", 68, 5_200_000, 94),
        _entry("Hook", "Fear", 21, 2_200_000, 80),
        _entry("Story", "Problem-Solution", 72, 4_000_000, 90),
    ])
    best = service.get_best_patterns(limit=2)

    assert inserted == 3
    assert len(best) == 2
    assert best[0].pattern == "Curiosity"
    assert best[1].pattern == "Problem-Solution"
    db.disconnect()


def test_search_patterns(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "test.db"))
    db.connect()
    db.create_tables()
    service = KnowledgeService(db)

    service.save_many([
        _entry("Hook", "Curiosity", 68, 5_200_000, 94),
        _entry("Title", "Transformation Promise", 41, 3_000_000, 88),
    ])
    matches = service.search("transformation")

    assert len(matches) == 1
    assert matches[0].category == "Title"
    assert matches[0].pattern == "Transformation Promise"
    db.disconnect()
