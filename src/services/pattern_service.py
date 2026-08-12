"""Statistics service for extracting viral patterns from analysis records."""

from __future__ import annotations

import ast
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Optional

from src.database.database_service import DatabaseService
from src.models.pattern import PatternStatistic, PatternSummary
from src.models.pattern_report import PatternReport


class PatternServiceError(Exception):
    """Raised when pattern report generation fails."""


class PatternService:
    """Aggregate analysis-table signals into a normalized pattern report."""

    CATEGORY_FIELDS = {
        "hook_types": "hook_type",
        "emotions": "emotion",
        "story_structures": "story_structure",
        "thumbnail_patterns": "thumbnail_pattern",
        "title_formulas": "title_formula",
        "cta_types": "cta_type",
        "target_audiences": "target_audience",
        "difficulty_levels": "difficulty_level",
        "video_styles": "estimated_video_style",
        "value_propositions": "value_proposition",
    }
    LIST_FIELDS = {
        "retention_techniques": "retention_techniques",
        "keywords": "keywords",
        "psychological_triggers": "psychological_triggers",
        "sub_topics": "sub_topics",
    }

    def __init__(self, database_service: DatabaseService) -> None:
        self.database_service = database_service

    def load_analysis(self) -> list[dict[str, Any]]:
        """Load full analysis data with video metadata from database service."""
        return self.database_service.get_all_analysis_with_video_data()

    def count_hooks(self, rows: list[dict[str, Any]]) -> dict[str, float]:
        """Count hook type frequencies as percentages."""
        return self._count_scalar(rows, ("hook_type",))

    def count_story_structures(self, rows: list[dict[str, Any]]) -> dict[str, float]:
        """Count story structure frequencies as percentages."""
        return self._count_scalar(rows, ("story_structure",))

    def count_emotions(self, rows: list[dict[str, Any]]) -> dict[str, float]:
        """Count emotional trigger frequencies as percentages."""
        return self._count_scalar(rows, ("emotional_trigger", "emotion"))

    def count_titles(self, rows: list[dict[str, Any]]) -> dict[str, float]:
        """Count title formula frequencies as percentages."""
        return self._count_scalar(rows, ("title_formula",))

    def count_thumbnails(self, rows: list[dict[str, Any]]) -> dict[str, float]:
        """Count thumbnail psychology frequencies as percentages."""
        return self._count_scalar(rows, ("thumbnail_psychology", "thumbnail_pattern"))

    def count_retention(self, rows: list[dict[str, Any]]) -> dict[str, float]:
        """Count retention technique frequencies as percentages."""
        counter: Counter[str] = Counter()
        for row in rows:
            values = self._extract_values(row, ("retention_technique", "retention_techniques"), as_list=True)
            counter.update(values)
        return self._to_percentages(counter)

    def calculate_average_score(self, rows: list[dict[str, Any]]) -> float:
        """Calculate average viral score across all records."""
        scores = [self._as_float(self._first_value(row, ("viral_score",))) for row in rows]
        valid_scores = [score for score in scores if score is not None]
        return round(mean(valid_scores), 2) if valid_scores else 0.0

    def find_top_channels(self, rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
        """Return channels ranked by average viral score then average views."""
        return self._top_entities(rows, ("channel",), key_name="channel", limit=limit)

    def find_top_topics(self, rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
        """Return topics ranked by average viral score then average views."""
        return self._top_entities(rows, ("topic", "main_topic"), key_name="topic", limit=limit)

    def generate_report(self) -> dict[str, Any]:
        """Build and return the full pattern report in JSON-ready form."""
        rows = self.load_analysis()
        hooks = self.count_hooks(rows)
        stories = self.count_story_structures(rows)
        emotions = self.count_emotions(rows)
        titles = self.count_titles(rows)
        thumbnails = self.count_thumbnails(rows)
        retention = self.count_retention(rows)
        report = PatternReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            videos_analyzed=len(rows),
            hooks=hooks,
            stories=stories,
            emotions=emotions,
            titles=titles,
            thumbnail_psychology=thumbnails,
            retention=retention,
            top_channels=self.find_top_channels(rows),
            top_topics=self.find_top_topics(rows),
            average_viral_score=self.calculate_average_score(rows),
            confidence=self._calculate_confidence(hooks, stories, emotions, thumbnails, retention, len(rows)),
        )
        return report.to_dict()

    def _count_scalar(self, rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, float]:
        """Count scalar-field frequencies for the first available key."""
        counter: Counter[str] = Counter()
        for row in rows:
            values = self._extract_values(row, keys, as_list=False)
            counter.update(values)
        return self._to_percentages(counter)

    def _extract_values(
        self, row: dict[str, Any], keys: tuple[str, ...], as_list: bool
    ) -> list[str]:
        """Normalize scalar/list values from multiple possible source keys."""
        raw_value = self._first_value(row, keys)
        if raw_value is None:
            return []
        if as_list:
            return self._normalize_list(raw_value)
        normalized = str(raw_value).strip()
        return [normalized] if normalized else []

    def _first_value(self, row: dict[str, Any], keys: tuple[str, ...]) -> Any:
        """Get first present non-empty value from candidate keys."""
        for key in keys:
            if key in row and row[key] not in (None, ""):
                return row[key]
        return None

    def _normalize_list(self, value: Any) -> list[str]:
        """Normalize string/list field values into a cleaned list."""
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            try:
                parsed = ast.literal_eval(value)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except (ValueError, SyntaxError):
                pass
            return [item.strip() for item in value.split(",") if item.strip()]
        return []

    def _parse_list_field(self, field_value: str) -> list[str]:
        """Backward-compatible list field parser."""
        return self._normalize_list(field_value)

    def _parse_duration(self, duration: str) -> float:
        """Parse ISO-8601 duration string into seconds."""
        if not duration:
            return 0.0
        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
        if not match:
            return 0.0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return float(hours * 3600 + minutes * 60 + seconds)

    def _calculate_pattern_statistics(
        self,
        records: list[dict[str, Any]],
        category: str,
        field_name: str,
        is_list_field: bool = False,
    ) -> list[PatternStatistic]:
        """Backward-compatible statistic builder for legacy report flows."""
        if not records:
            return []
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            values = self._parse_list_field(str(record.get(field_name, ""))) if is_list_field else [record.get(field_name, "")]
            for value in values:
                if str(value).strip():
                    grouped[str(value).strip()].append(record)
        stats: list[PatternStatistic] = []
        for pattern, entries in grouped.items():
            views = [self._as_float(item.get("view_count")) or 0.0 for item in entries]
            likes = [self._as_float(item.get("like_count")) or 0.0 for item in entries]
            comments = [self._as_float(item.get("comment_count")) or 0.0 for item in entries]
            durations = [self._parse_duration(str(item.get("duration", ""))) for item in entries]
            top = max(entries, key=lambda item: self._as_float(item.get("view_count")) or 0.0)
            low = min(entries, key=lambda item: self._as_float(item.get("view_count")) or 0.0)
            stats.append(PatternStatistic(
                category=category,
                pattern=pattern,
                count=len(entries),
                percentage=round(len(entries) / len(records) * 100, 2),
                average_views=round(mean(views), 2),
                average_likes=round(mean(likes), 2),
                average_comments=round(mean(comments), 2),
                average_duration=round(mean(durations), 2),
                highest_view_video=top.get("video_id"),
                lowest_view_video=low.get("video_id"),
            ))
        stats.sort(key=lambda item: item.count, reverse=True)
        return stats

    def _generate_recommendations(
        self, all_statistics: list[PatternStatistic], total_videos: int, avg_confidence: float
    ) -> list[str]:
        """Generate recommendations from dominant patterns and confidence."""
        if total_videos == 0:
            return ["No analysis data available. Run the Analysis Agent first."]
        recommendations: list[str] = []
        by_category: dict[str, list[PatternStatistic]] = defaultdict(list)
        for stat in all_statistics:
            by_category[stat.category].append(stat)
        for category, stats in by_category.items():
            if stats and stats[0].percentage >= 30:
                recommendations.append(
                    f"Dominant {category.replace('_', ' ')}: '{stats[0].pattern}' appears in {stats[0].percentage:.1f}% of videos."
                )
        recommendations.append(f"Average confidence score is {avg_confidence:.2f}.")
        recommendations.append(f"Analyzed {total_videos} videos across {len(by_category)} categories.")
        return recommendations

    def _build_json_report(
        self,
        records: list[dict[str, Any]],
        all_statistics: list[PatternStatistic],
        total_videos: int,
        avg_confidence: float,
        recommendations: list[str],
    ) -> dict[str, Any]:
        """Build legacy JSON report format used by existing PatternAgent."""
        by_category: dict[str, list[PatternStatistic]] = defaultdict(list)
        for stat in all_statistics:
            by_category[stat.category].append(stat)

        def _as_list(stats: list[PatternStatistic]) -> list[dict[str, Any]]:
            return [
                {
                    "pattern": item.pattern,
                    "count": item.count,
                    "percentage": item.percentage,
                    "average_views": item.average_views,
                    "average_likes": item.average_likes,
                    "average_comments": item.average_comments,
                }
                for item in stats
            ]

        return {
            "dataset": {"videos": total_videos, "analyses": len(records)},
            "hook_types": _as_list(by_category.get("hook_types", [])),
            "emotions": _as_list(by_category.get("emotions", [])),
            "story_structures": _as_list(by_category.get("story_structures", [])),
            "thumbnail_patterns": _as_list(by_category.get("thumbnail_patterns", [])),
            "title_formulas": _as_list(by_category.get("title_formulas", [])),
            "retention_techniques": _as_list(by_category.get("retention_techniques", [])),
            "recommendations": recommendations,
            "average_confidence": avg_confidence,
        }

    def analyze_patterns(self) -> tuple[list[PatternStatistic], dict[str, Any]]:
        """Legacy full aggregation used by existing tests and PatternAgent."""
        records = self.load_analysis()
        if not records:
            return [], {"dataset": {"videos": 0, "analyses": 0}, "recommendations": []}
        confidence_scores = [self._as_float(record.get("confidence_score")) or 0.0 for record in records]
        avg_confidence = mean(confidence_scores) if confidence_scores else 0.0
        all_stats: list[PatternStatistic] = []
        for category, field_name in self.CATEGORY_FIELDS.items():
            all_stats.extend(self._calculate_pattern_statistics(records, category, field_name, False))
        for category, field_name in self.LIST_FIELDS.items():
            all_stats.extend(self._calculate_pattern_statistics(records, category, field_name, True))
        recommendations = self._generate_recommendations(all_stats, len(records), avg_confidence)
        report = self._build_json_report(records, all_stats, len(records), avg_confidence, recommendations)
        return all_stats, report

    def save_report(
        self,
        report_name: str,
        statistics: list[PatternStatistic],
        json_report: dict[str, Any],
        total_videos: int,
        avg_confidence: float,
    ) -> int:
        """Save pattern report and statistics through DatabaseService."""
        report_id = self.database_service.insert_pattern_report(
            report_name=report_name,
            total_videos=total_videos,
            average_confidence=avg_confidence,
            json_report=json.dumps(json_report, indent=2, default=str),
        )
        stat_rows = [
            {
                "category": item.category,
                "pattern": item.pattern,
                "count": item.count,
                "percentage": item.percentage,
                "average_views": item.average_views,
                "average_likes": item.average_likes,
                "average_comments": item.average_comments,
            }
            for item in statistics
        ]
        self.database_service.insert_pattern_statistics(stat_rows)
        return report_id

    def export_report(self, json_report: dict[str, Any], output_dir: str = "data/output/reports") -> str:
        """Write report JSON to disk and return the output path."""
        os.makedirs(output_dir, exist_ok=True)
        filename = f"pattern_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(json_report, handle, indent=2, ensure_ascii=False, default=str)
        return filepath

    def generate_summary(
        self, statistics: list[PatternStatistic], total_videos: int, reports_saved: int
    ) -> PatternSummary:
        """Build summary snapshot used by pattern agent dashboard."""
        by_category: dict[str, list[PatternStatistic]] = defaultdict(list)
        for item in statistics:
            by_category[item.category].append(item)
        return PatternSummary(
            videos_analyzed=total_videos,
            patterns_found=len(statistics),
            reports_saved=reports_saved,
            top_hook=by_category["hook_types"][0].pattern if by_category.get("hook_types") else None,
            top_emotion=by_category["emotions"][0].pattern if by_category.get("emotions") else None,
            top_story_structure=by_category["story_structures"][0].pattern if by_category.get("story_structures") else None,
            top_thumbnail_pattern=by_category["thumbnail_patterns"][0].pattern if by_category.get("thumbnail_patterns") else None,
            top_title_formula=by_category["title_formulas"][0].pattern if by_category.get("title_formulas") else None,
        )

    def run(self, report_name: Optional[str] = None) -> PatternSummary:
        """Legacy workflow: analyze, persist, export, and summarize."""
        final_name = report_name or f"pattern_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        stats, json_report = self.analyze_patterns()
        records = self.load_analysis()
        confidence = mean([self._as_float(item.get("confidence_score")) or 0.0 for item in records]) if records else 0.0
        self.save_report(final_name, stats, json_report, len(records), confidence)
        self.export_report(json_report)
        return self.generate_summary(stats, len(records), 1)

    def get_latest_summary(self) -> str:
        """Return latest generated report as string payload."""
        return str(self.generate_report())

    def _to_percentages(self, counter: Counter[str]) -> dict[str, float]:
        """Convert counts into sorted frequency percentages."""
        total = sum(counter.values())
        if total == 0:
            return {}
        ordered = counter.most_common()
        return {label: round((count / total) * 100, 2) for label, count in ordered}

    def _top_entities(
        self, rows: list[dict[str, Any]], keys: tuple[str, ...], key_name: str, limit: int
    ) -> list[dict[str, Any]]:
        """Calculate top-performing channels/topics with summary metrics."""
        grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"scores": [], "views": []})
        for row in rows:
            entity = self._first_value(row, keys)
            if entity is None:
                continue
            grouped[str(entity)]["scores"].append(self._as_float(self._first_value(row, ("viral_score",))) or 0.0)
            grouped[str(entity)]["views"].append(self._as_float(self._first_value(row, ("views", "view_count"))) or 0.0)
        ranked = [
            {
                key_name: name,
                "videos": len(data["scores"]),
                "average_viral_score": round(mean(data["scores"]), 2),
                "average_views": round(mean(data["views"]), 2),
            }
            for name, data in grouped.items()
            if data["scores"]
        ]
        ranked.sort(key=lambda item: (item["average_viral_score"], item["average_views"]), reverse=True)
        return ranked[:limit]

    def _calculate_confidence(
        self,
        hooks: dict[str, float],
        stories: dict[str, float],
        emotions: dict[str, float],
        thumbnails: dict[str, float],
        retention: dict[str, float],
        videos_analyzed: int,
    ) -> float:
        """Estimate confidence from concentration of top patterns and sample size."""
        top_frequencies = [self._top_value(group) for group in (hooks, stories, emotions, thumbnails, retention)]
        signal_strength = mean(top_frequencies) / 100 if top_frequencies else 0.0
        sample_factor = min(1.0, videos_analyzed / 100)
        return round(signal_strength * sample_factor, 2)

    def _top_value(self, values: dict[str, float]) -> float:
        """Get highest percentage value from a distribution."""
        return max(values.values()) if values else 0.0

    def _as_float(self, value: Any) -> float | None:
        """Safely coerce numeric-like values to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
