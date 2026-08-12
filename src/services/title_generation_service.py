"""Service for generating explainable, high-performing YouTube title ideas."""

from __future__ import annotations

from statistics import mean
from typing import Any

from src.database.database_service import DatabaseService
from src.models.title import TitleCandidate
from src.services.knowledge_service import KnowledgeService
from src.services.pattern_service import PatternService


class TitleGenerationService:
    """Generate and rank title candidates using knowledge, patterns, and trends."""

    TITLE_CATEGORIES = [
        "Curiosity", "Shock", "Transformation", "Listicle", "Challenge",
        "Story", "Mistake", "Secrets", "Comparison", "Ranking",
        "Tutorial", "Before/After", "Question",
    ]
    FORMULA_LIBRARY = {
        "Curiosity": ["The {topic} Shift Nobody Talks About ({trend})", "I Tried {topic} for 30 Days - Here's What Changed"],
        "Shock": ["{topic} Is Broken in {year}: What We Found", "I Was Wrong About {topic} (And It Cost Me)"],
        "Transformation": ["From Zero to Results With {topic}: {audience} Playbook", "How {topic} Transformed My {niche} Strategy"],
        "Listicle": ["{number} {topic} Moves That Boost Results Fast", "{number} {topic} Mistakes Blocking Growth"],
        "Challenge": ["I Tried the {topic} Challenge for {timeframe}", "Can You Survive This {topic} Challenge?"],
        "Story": ["How {audience} Used {topic} to Win in {timeframe}", "My {topic} Story: From Frustration to Traction"],
        "Mistake": ["Stop Doing This in {topic}: {number} Costly Mistakes", "The Biggest {topic} Mistake I Made"],
        "Secrets": ["{number} {topic} Secrets Top Creators Hide", "The {topic} Secret Framework That Actually Works"],
        "Comparison": ["{topic} vs {trend}: Which Wins for {audience}?", "{topic} vs Traditional Methods: Honest Results"],
        "Ranking": ["Ranking {number} {topic} Strategies by Real Outcomes", "Top {number} {topic} Tactics (Worst to Best)"],
        "Tutorial": ["How I Use {topic} to Get Better Results ({year} Guide)", "How to Master {topic} Step by Step"],
        "Before/After": ["{topic} Before vs After: The Real Difference", "Before and After {topic}: What Actually Changed"],
        "Question": ["Can {topic} Really Deliver Faster Results?", "Is {topic} Worth It for {audience}?"],
    }

    def __init__(
        self,
        database_service: DatabaseService,
        knowledge_service: KnowledgeService,
        pattern_service: PatternService,
    ) -> None:
        self.database_service = database_service
        self.knowledge_service = knowledge_service
        self.pattern_service = pattern_service

    def generate_titles(
        self,
        topic: str,
        niche: str | None = None,
        audience: str | None = None,
        trend_data: Any = None,
        count: int = 20,
    ) -> list[TitleCandidate]:
        """Generate ranked, explainable title candidates and persist them."""
        if not topic or not topic.strip():
            raise ValueError("topic is required")
        pattern_report = self.pattern_service.generate_report()
        knowledge = self._load_knowledge(topic, niche)
        trend_terms = self._extract_trend_terms(trend_data)
        generated = self._generate_candidate_pool(topic, niche, audience, pattern_report, knowledge, trend_terms, count)
        ranked = self.rank_titles(generated)[:count]
        self.database_service.insert_generated_titles(topic.strip(), [item.to_dict() for item in ranked])
        return ranked

    def score_title(
        self,
        title: str,
        pattern_frequency: float,
        knowledge_confidence: float,
        trend_relevance: float,
        emotion_strength: float,
        historical_performance: float,
        title_formula: str,
    ) -> float:
        """Score a title using weighted strategic and quality signals."""
        length_score = self._title_length_score(title)
        formula_quality = self._formula_quality(title_formula)
        weighted = (
            0.20 * pattern_frequency
            + 0.20 * knowledge_confidence
            + 0.15 * trend_relevance
            + 0.15 * emotion_strength
            + 0.15 * historical_performance
            + 0.10 * length_score
            + 0.05 * formula_quality
        )
        return round(min(99.0, max(1.0, weighted)), 2)

    def estimate_ctr(self, score: float) -> float:
        """Estimate CTR from title score."""
        ctr = 3.0 + (max(0.0, score) * 0.08)
        return round(min(15.0, ctr), 2)

    def choose_pattern(
        self,
        category: str,
        knowledge_entries: list[dict[str, Any]],
        pattern_report: dict[str, Any],
    ) -> tuple[str, float, float, float]:
        """Choose best pattern signal for a category."""
        kb_match = self._best_knowledge_pattern(category, knowledge_entries)
        if kb_match:
            return kb_match
        report_map = self._report_distribution(category, pattern_report)
        if report_map:
            pattern, frequency = max(report_map.items(), key=lambda item: item[1])
            return pattern, float(frequency), 60.0, 0.0
        return category, 40.0, 50.0, 0.0

    def choose_formula(self, category: str, index: int = 0) -> str:
        """Choose formula template for a category in a deterministic way."""
        formulas = self.FORMULA_LIBRARY.get(category, ["How I Use {topic} for Better Results"])
        return formulas[index % len(formulas)]

    def build_title(
        self,
        topic: str,
        formula: str,
        pattern: str,
        niche: str | None,
        audience: str | None,
        trend_terms: list[str],
        index: int,
    ) -> str:
        """Render a concrete title from a formula template."""
        trend = trend_terms[index % len(trend_terms)] if trend_terms else "2026 Trends"
        values = {
            "topic": topic.strip(),
            "pattern": pattern,
            "niche": niche or "creator",
            "audience": audience or "creators",
            "trend": trend,
            "number": str(5 + (index % 7)),
            "timeframe": f"{14 + index % 30} Days",
            "year": "2026",
        }
        title = formula.format(**values)
        return title[:100].strip()

    def rank_titles(self, candidates: list[TitleCandidate]) -> list[TitleCandidate]:
        """Sort titles by confidence and estimated CTR."""
        return sorted(candidates, key=lambda item: (item.confidence, item.estimated_ctr), reverse=True)

    def _generate_candidate_pool(
        self,
        topic: str,
        niche: str | None,
        audience: str | None,
        pattern_report: dict[str, Any],
        knowledge_entries: list[dict[str, Any]],
        trend_terms: list[str],
        count: int,
    ) -> list[TitleCandidate]:
        """Generate deterministic candidate pool and deduplicate by title text."""
        results: list[TitleCandidate] = []
        seen: set[str] = set()
        for index in range(count * 2):
            category = self.TITLE_CATEGORIES[index % len(self.TITLE_CATEGORIES)]
            pattern, frequency, knowledge_confidence, avg_views = self.choose_pattern(category, knowledge_entries, pattern_report)
            formula = self.choose_formula(category, index)
            title = self.build_title(topic, formula, pattern, niche, audience, trend_terms, index)
            if title in seen:
                continue
            seen.add(title)
            score = self.score_title(
                title=title,
                pattern_frequency=frequency,
                knowledge_confidence=knowledge_confidence,
                trend_relevance=self._trend_relevance(title, trend_terms),
                emotion_strength=self._emotion_strength(category),
                historical_performance=self._historical_performance(topic, formula, avg_views),
                title_formula=formula,
            )
            results.append(TitleCandidate(
                title=title,
                pattern_used=pattern,
                emotion=category,
                title_formula=formula,
                estimated_ctr=self.estimate_ctr(score),
                confidence=score,
                reason=self._reason(pattern, category, frequency, knowledge_confidence),
            ))
            if len(results) >= count:
                break
        return results

    def _load_knowledge(self, topic: str, niche: str | None) -> list[dict[str, Any]]:
        """Load relevant knowledge entries as dictionaries."""
        entries = [item.to_dict() for item in self.knowledge_service.search(topic, limit=50)]
        if niche:
            entries.extend(item.to_dict() for item in self.knowledge_service.search(niche, limit=30))
        if not entries:
            entries = [item.to_dict() for item in self.knowledge_service.get_best_patterns(limit=30)]
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in entries:
            unique[(entry.get("category", ""), entry.get("pattern", ""))] = entry
        return list(unique.values())

    def _extract_trend_terms(self, trend_data: Any) -> list[str]:
        """Normalize trend payload into a list of phrases."""
        # Delegate to shared utility to avoid duplication
        from src.utils.generation_utils import normalize_trends

        return normalize_trends(trend_data)

    def select_best_title(self, titles: list[dict[str, Any]], topic: str) -> dict[str, Any]:
        """Select the highest-confidence title candidate or a sensible fallback.

        This method centralizes "best title" selection so other services can reuse it.
        """
        if not titles:
            return {"title": f"{topic} Blueprint for 2026", "confidence": 70.0, "estimated_ctr": 6.5}
        ranked = sorted(
            titles,
            key=lambda item: (float(item.get("confidence", 0.0)), float(item.get("estimated_ctr", 0.0))),
            reverse=True,
        )
        return ranked[0]

    def _best_knowledge_pattern(self, category: str, entries: list[dict[str, Any]]) -> tuple[str, float, float, float] | None:
        """Find strongest knowledge pattern match for category."""
        if not entries:
            return None
        category_map = {
            "Curiosity": {"Hook", "Emotion"},
            "Shock": {"Hook", "Emotion"},
            "Question": {"Hook", "Title"},
            "Transformation": {"Story", "Title"},
            "Before/After": {"Story", "Title"},
            "Story": {"Story"},
            "Listicle": {"Title"},
            "Ranking": {"Title"},
            "Tutorial": {"Title"},
            "Comparison": {"Title"},
            "Challenge": {"Retention"},
            "Mistake": {"Emotion", "Title"},
            "Secrets": {"Emotion", "Title"},
        }
        allowed = category_map.get(category, set())
        filtered = [
            item for item in entries
            if not allowed or str(item.get("category", "")) in allowed
        ]
        source = filtered if filtered else entries
        scored = sorted(
            source,
            key=lambda item: (float(item.get("confidence", 0.0)), float(item.get("frequency", 0.0))),
            reverse=True,
        )
        best = scored[0]
        return (
            str(best.get("pattern", category)),
            float(best.get("frequency", 50.0)),
            float(best.get("confidence", 60.0)),
            float(best.get("average_views", 0.0)),
        )

    def _report_distribution(self, category: str, report: dict[str, Any]) -> dict[str, float]:
        """Map title category to relevant pattern report distribution."""
        key_map = {
            "Curiosity": "hooks", "Shock": "hooks", "Question": "hooks",
            "Transformation": "stories", "Before/After": "stories", "Story": "stories",
            "Listicle": "titles", "Ranking": "titles", "Tutorial": "titles",
            "Mistake": "emotions", "Secrets": "emotions", "Challenge": "retention",
            "Comparison": "titles",
        }
        value = report.get(key_map.get(category, "titles"), {})
        return value if isinstance(value, dict) else {}

    def _trend_relevance(self, title: str, trends: list[str]) -> float:
        """Calculate trend relevance score for a candidate title."""
        if not trends:
            return 50.0
        lowered = title.lower()
        match_count = len([term for term in trends if term.lower() in lowered])
        return min(100.0, 55.0 + match_count * 20.0)

    def _emotion_strength(self, category: str) -> float:
        """Return emotion strength priors by title category."""
        scores = {
            "Curiosity": 92, "Shock": 90, "Transformation": 88, "Listicle": 78,
            "Challenge": 82, "Story": 85, "Mistake": 80, "Secrets": 89,
            "Comparison": 76, "Ranking": 74, "Tutorial": 72, "Before/After": 84,
            "Question": 86,
        }
        return float(scores.get(category, 75))

    def _historical_performance(self, topic: str, formula: str, avg_views_hint: float) -> float:
        """Estimate historical performance using analysis/video history and hints."""
        rows = self.database_service.get_all_analysis_with_video_data()
        if not rows and avg_views_hint <= 0:
            return 50.0
        scoped = [row for row in rows if topic.lower() in str(row.get("main_topic", "")).lower()]
        base_rows = scoped if scoped else rows
        row_views = [float(row.get("view_count", 0) or 0) for row in base_rows]
        overall_avg = mean(row_views) if row_views else 1.0
        formula_rows = [row for row in base_rows if str(row.get("title_formula", "")).lower() in formula.lower()]
        formula_avg = mean(float(row.get("view_count", 0) or 0) for row in formula_rows) if formula_rows else overall_avg
        combined = max(formula_avg, avg_views_hint)
        return round(min(100.0, 40.0 + (combined / max(overall_avg, 1.0)) * 20.0), 2)

    def _title_length_score(self, title: str) -> float:
        """Score title length toward high-performing range."""
        length = len(title)
        if 45 <= length <= 70:
            return 100.0
        if 35 <= length < 45 or 70 < length <= 85:
            return 80.0
        return 60.0

    def _formula_quality(self, formula: str) -> float:
        """Score intrinsic quality of formula patterns."""
        quality_signals = ["How", "vs", "Before", "After", "Secrets", "Mistakes", "Ranking"]
        hits = sum(1 for signal in quality_signals if signal.lower() in formula.lower())
        return min(100.0, 60.0 + hits * 8.0)

    def _reason(self, pattern: str, category: str, frequency: float, confidence: float) -> str:
        """Create explainability text for each generated title."""
        return (
            f"Based on '{pattern}' in {category.lower()} patterns "
            f"(frequency {frequency:.1f}%, confidence {confidence:.1f})."
        )
