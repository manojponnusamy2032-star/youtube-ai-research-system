"""Tests for deterministic, explainable title generation service."""

from __future__ import annotations

from src.database.database_service import DatabaseService
from src.models.knowledge import KnowledgeEntry
from src.models.title import TitleCandidate
from src.services.knowledge_service import KnowledgeService
from src.services.title_generation_service import TitleGenerationService


class PatternServiceStub:
    """Stub pattern service returning stable aggregate report."""

    def generate_report(self) -> dict[str, object]:
        return {
            "hooks": {"Curiosity": 68.0, "Shock": 11.0},
            "stories": {"Transformation": 52.0, "Before/After": 31.0},
            "emotions": {"Curiosity": 70.0, "Fear": 20.0},
            "titles": {"How I ...": 44.0, "Top X ...": 33.0},
            "thumbnail_psychology": {"Mystery": 41.0},
            "retention": {"Open Loop": 60.0},
            "confidence": 0.92,
        }


def _seed_knowledge(service: KnowledgeService) -> None:
    service.save_many([
        KnowledgeEntry("Hook", "Curiosity", 68.0, 5_200_000, 94.0, "Prefer curiosity hooks."),
        KnowledgeEntry("Emotion", "Curiosity", 62.0, 4_900_000, 91.0, "Curiosity sustains retention."),
        KnowledgeEntry("Title", "How I ...", 58.0, 4_700_000, 90.0, "Use personal proof formulas."),
    ])


def test_generate_titles_returns_20_ranked_items_and_persists(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "titles.db"))
    db.connect()
    db.create_tables()
    knowledge_service = KnowledgeService(db)
    _seed_knowledge(knowledge_service)
    service = TitleGenerationService(db, knowledge_service, PatternServiceStub())

    titles = service.generate_titles(
        topic="YouTube automation",
        niche="faceless channel",
        audience="beginners",
        trend_data=["AI Shorts", "Automation workflow"],
        count=20,
    )
    persisted = db.get_generated_titles(topic="YouTube automation", limit=30)

    assert len(titles) == 20
    assert len(persisted) == 20
    assert all(item.reason for item in titles)
    assert titles == sorted(titles, key=lambda item: (item.confidence, item.estimated_ctr), reverse=True)
    db.disconnect()


def test_score_title_and_estimate_ctr_are_consistent(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "titles.db"))
    db.connect()
    db.create_tables()
    knowledge_service = KnowledgeService(db)
    service = TitleGenerationService(db, knowledge_service, PatternServiceStub())

    score = service.score_title(
        title="How I Used AI to Grow a Channel in 30 Days",
        pattern_frequency=68.0,
        knowledge_confidence=94.0,
        trend_relevance=80.0,
        emotion_strength=90.0,
        historical_performance=85.0,
        title_formula="How I ...",
    )
    ctr = service.estimate_ctr(score)

    assert 1.0 <= score <= 99.0
    assert 3.0 <= ctr <= 15.0
    db.disconnect()


def test_choose_pattern_prefers_knowledge_when_available(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "titles.db"))
    db.connect()
    db.create_tables()
    knowledge_service = KnowledgeService(db)
    _seed_knowledge(knowledge_service)
    service = TitleGenerationService(db, knowledge_service, PatternServiceStub())

    entries = [entry.to_dict() for entry in knowledge_service.get_best_patterns(limit=10)]
    pattern, frequency, confidence, _ = service.choose_pattern("Curiosity", entries, PatternServiceStub().generate_report())

    assert pattern == "Curiosity"
    assert frequency == 68.0
    assert confidence == 94.0
    db.disconnect()


def test_rank_titles_orders_by_confidence_and_ctr(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "titles.db"))
    db.connect()
    db.create_tables()
    knowledge_service = KnowledgeService(db)
    service = TitleGenerationService(db, knowledge_service, PatternServiceStub())

    ranked = service.rank_titles([
        TitleCandidate("A", "Curiosity", "Curiosity", "How", 7.2, 82.0, "reason"),
        TitleCandidate("B", "Shock", "Shock", "Why", 8.9, 90.0, "reason"),
        TitleCandidate("C", "Story", "Story", "How", 8.1, 90.0, "reason"),
    ])

    assert [item.title for item in ranked] == ["B", "C", "A"]
    db.disconnect()


def test_generate_titles_with_empty_knowledge_and_trends(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "titles.db"))
    db.connect()
    db.create_tables()
    knowledge_service = KnowledgeService(db)
    service = TitleGenerationService(db, knowledge_service, PatternServiceStub())

    titles = service.generate_titles(topic="Python automation", count=20)

    assert len(titles) == 20
    assert all(item.title for item in titles)
    assert all(item.pattern_used for item in titles)
    db.disconnect()
