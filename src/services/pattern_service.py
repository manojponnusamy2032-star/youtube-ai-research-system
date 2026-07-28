"""
Pattern service for YouTube AI Research System.

This module handles aggregation of analysis results into pattern statistics,
including frequency analysis, ranking, and report generation.
"""

import ast
import json
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from src.database.database_service import DatabaseService
from src.models.pattern import PatternStatistic, PatternReport, PatternSummary

logger = logging.getLogger(__name__)


class PatternServiceError(Exception):
    """Custom exception for pattern service errors."""
    pass


class PatternService:
    """
    Service for aggregating analysis results into pattern intelligence.

    Responsibilities:
    - Load analysis records from database
    - Aggregate statistics for each pattern category
    - Generate rankings and frequencies
    - Calculate video metrics (views, likes, comments, duration)
    - Save reports to database and export JSON

    Attributes:
        database_service: DatabaseService instance
    """

    # Categories to analyze - each maps to an analysis field
    CATEGORY_FIELDS = {
        'hook_types': 'hook_type',
        'emotions': 'emotion',
        'story_structures': 'story_structure',
        'thumbnail_patterns': 'thumbnail_pattern',
        'title_formulas': 'title_formula',
        'cta_types': 'cta_type',
        'target_audiences': 'target_audience',
        'difficulty_levels': 'difficulty_level',
        'video_styles': 'estimated_video_style',
        'value_propositions': 'value_proposition',
    }

    # List-type fields that need special parsing
    LIST_FIELDS = {
        'retention_techniques': 'retention_techniques',
        'keywords': 'keywords',
        'psychological_triggers': 'psychological_triggers',
        'sub_topics': 'sub_topics',
    }

    def __init__(self, database_service: DatabaseService) -> None:
        """
        Initialize the pattern service.

        Args:
            database_service: DatabaseService instance
        """
        self.database_service = database_service
        logger.info("Pattern service initialized")

    def _load_analysis_records(self) -> List[Dict[str, Any]]:
        """
        Load all analysis records joined with video data.

        Returns:
            List of analysis records with video metadata
        """
        records = self.database_service.get_all_analysis_with_video_data()
        logger.info(f"Loaded {len(records)} analysis records for pattern analysis")
        return records

    def _parse_list_field(self, field_value: str) -> List[str]:
        """
        Parse a string representation of a list into actual list.

        Args:
            field_value: String representation of a list

        Returns:
            List of strings
        """
        if not field_value:
            return []

        try:
            result = ast.literal_eval(field_value)
            if isinstance(result, list):
                return [str(item).strip() for item in result if item]
            return [str(result).strip()]
        except (ValueError, SyntaxError):
            # Fallback: split by comma
            return [item.strip() for item in field_value.split(',') if item.strip()]

    def _parse_duration(self, duration: str) -> float:
        """
        Parse ISO 8601 duration string to seconds.

        Args:
            duration: ISO 8601 duration string (e.g., 'PT10M30S')

        Returns:
            Duration in seconds
        """
        if not duration or duration == 'unknown':
            return 0.0

        import re

        # Parse ISO 8601 duration: PT#H#M#S
        match = re.match(
            r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',
            duration
        )
        if not match:
            return 0.0

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        return float(hours * 3600 + minutes * 60 + seconds)

    def _calculate_pattern_statistics(
        self,
        records: List[Dict[str, Any]],
        category: str,
        field_name: str,
        is_list_field: bool = False
    ) -> List[PatternStatistic]:
        """
        Calculate statistics for a single pattern category.

        Args:
            records: Analysis records
            category: Category name
            field_name: Analysis field to aggregate
            is_list_field: Whether the field is a list type

        Returns:
            List of PatternStatistic sorted by count descending
        """
        total_records = len(records)
        if total_records == 0:
            return []

        # Group records by pattern value
        pattern_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for record in records:
            field_value = record.get(field_name, '')

            if is_list_field:
                items = self._parse_list_field(field_value)
                for item in items:
                    if item:
                        pattern_groups[item].append(record)
            else:
                if field_value:
                    pattern_groups[field_value].append(record)

        statistics = []
        for pattern, group_records in pattern_groups.items():
            count = len(group_records)
            percentage = (count / total_records) * 100

            # Calculate video metrics
            views = [r.get('view_count', 0) for r in group_records]
            likes = [r.get('like_count', 0) for r in group_records]
            comments = [r.get('comment_count', 0) for r in group_records]
            durations = [self._parse_duration(r.get('duration', '')) for r in group_records]

            # Find highest and lowest view videos
            highest_view_record = max(group_records, key=lambda r: r.get('view_count', 0))
            lowest_view_record = min(group_records, key=lambda r: r.get('view_count', 0))

            stat = PatternStatistic(
                category=category,
                pattern=pattern,
                count=count,
                percentage=round(percentage, 2),
                average_views=round(sum(views) / count, 2) if count > 0 else 0.0,
                average_likes=round(sum(likes) / count, 2) if count > 0 else 0.0,
                average_comments=round(sum(comments) / count, 2) if count > 0 else 0.0,
                average_duration=round(sum(durations) / count, 2) if count > 0 else 0.0,
                highest_view_video=highest_view_record.get('video_id'),
                lowest_view_video=lowest_view_record.get('video_id')
            )
            statistics.append(stat)

        # Sort by count descending
        statistics.sort(key=lambda s: s.count, reverse=True)
        return statistics

    def _generate_recommendations(
        self,
        all_statistics: List[PatternStatistic],
        total_videos: int,
        avg_confidence: float
    ) -> List[str]:
        """
        Generate actionable recommendations based on pattern analysis.

        Args:
            all_statistics: All pattern statistics
            total_videos: Total number of videos analyzed
            avg_confidence: Average confidence score

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if total_videos == 0:
            recommendations.append("No analysis data available. Run the Analysis Agent first.")
            return recommendations

        # Group statistics by category
        by_category: Dict[str, List[PatternStatistic]] = defaultdict(list)
        for stat in all_statistics:
            by_category[stat.category].append(stat)

        # Generate recommendations for top patterns
        for category, stats in by_category.items():
            if not stats:
                continue

            top = stats[0]
            if top.percentage >= 30:
                recommendations.append(
                    f"Dominant {category.replace('_', ' ')}: '{top.pattern}' "
                    f"appears in {top.percentage:.1f}% of videos. "
                    f"Consider diversifying this element."
                )
            elif top.percentage < 10 and len(stats) > 1:
                recommendations.append(
                    f"Highly fragmented {category.replace('_', ' ')} distribution. "
                    f"No single pattern dominates ({top.percentage:.1f}% max). "
                    f"This indicates diverse content strategy."
                )

        # Confidence-based recommendation
        if avg_confidence < 0.5:
            recommendations.append(
                f"Average confidence score is low ({avg_confidence:.2f}). "
                f"Consider improving transcript quality or analysis prompts."
            )
        elif avg_confidence >= 0.8:
            recommendations.append(
                f"High confidence score ({avg_confidence:.2f}). "
                f"Analysis results are reliable for pattern detection."
            )

        # Coverage recommendation
        recommendations.append(
            f"Analyzed {total_videos} videos across "
            f"{len(by_category)} pattern categories. "
            f"Continue collecting data for stronger pattern insights."
        )

        return recommendations

    def _build_json_report(
        self,
        records: List[Dict[str, Any]],
        all_statistics: List[PatternStatistic],
        total_videos: int,
        avg_confidence: float,
        recommendations: List[str]
    ) -> Dict[str, Any]:
        """
        Build the full JSON report structure.

        Args:
            records: Analysis records
            all_statistics: All pattern statistics
            total_videos: Total videos
            avg_confidence: Average confidence
            recommendations: List of recommendations

        Returns:
            Complete JSON report dictionary
        """
        # Group statistics by category
        by_category: Dict[str, List[PatternStatistic]] = defaultdict(list)
        for stat in all_statistics:
            by_category[stat.category].append(stat)

        def category_to_list(stats: List[PatternStatistic]) -> List[Dict[str, Any]]:
            return [
                {
                    'pattern': s.pattern,
                    'count': s.count,
                    'percentage': s.percentage,
                    'average_views': s.average_views,
                    'average_likes': s.average_likes,
                    'average_comments': s.average_comments
                }
                for s in stats
            ]

        report = {
            'dataset': {
                'videos': total_videos,
                'analyses': len(records)
            },
            'hook_types': category_to_list(by_category.get('hook_types', [])),
            'emotions': category_to_list(by_category.get('emotions', [])),
            'story_structures': category_to_list(by_category.get('story_structures', [])),
            'thumbnail_patterns': category_to_list(by_category.get('thumbnail_patterns', [])),
            'title_formulas': category_to_list(by_category.get('title_formulas', [])),
            'retention_techniques': category_to_list(by_category.get('retention_techniques', [])),
            'cta_types': category_to_list(by_category.get('cta_types', [])),
            'target_audiences': category_to_list(by_category.get('target_audiences', [])),
            'psychological_triggers': category_to_list(by_category.get('psychological_triggers', [])),
            'keyword_clusters': category_to_list(by_category.get('keywords', [])),
            'sub_topics': category_to_list(by_category.get('sub_topics', [])),
            'difficulty_levels': category_to_list(by_category.get('difficulty_levels', [])),
            'video_styles': category_to_list(by_category.get('video_styles', [])),
            'value_propositions': category_to_list(by_category.get('value_propositions', [])),
            'recommendations': recommendations
        }

        return report

    def analyze_patterns(self) -> Tuple[List[PatternStatistic], Dict[str, Any]]:
        """
        Perform complete pattern analysis on all stored analysis records.

        Returns:
            Tuple of (pattern_statistics, json_report)
        """
        # Load records
        records = self._load_analysis_records()

        if not records:
            logger.warning("No analysis records found for pattern analysis")
            return [], {'dataset': {'videos': 0, 'analyses': 0}, 'recommendations': []}

        total_videos = len(records)

        # Calculate average confidence
        confidence_scores = [r.get('confidence_score', 0.0) for r in records]
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

        # Calculate statistics for each category
        all_statistics: List[PatternStatistic] = []

        # Scalar field categories
        for category, field_name in self.CATEGORY_FIELDS.items():
            stats = self._calculate_pattern_statistics(
                records, category, field_name, is_list_field=False
            )
            all_statistics.extend(stats)

        # List field categories
        for category, field_name in self.LIST_FIELDS.items():
            stats = self._calculate_pattern_statistics(
                records, category, field_name, is_list_field=True
            )
            all_statistics.extend(stats)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            all_statistics, total_videos, avg_confidence
        )

        # Build JSON report
        json_report = self._build_json_report(
            records, all_statistics, total_videos, avg_confidence, recommendations
        )

        logger.info(
            f"Pattern analysis complete: "
            f"{len(all_statistics)} statistics across "
            f"{len(self.CATEGORY_FIELDS) + len(self.LIST_FIELDS)} categories"
        )

        return all_statistics, json_report

    def save_report(
        self,
        report_name: str,
        statistics: List[PatternStatistic],
        json_report: Dict[str, Any],
        total_videos: int,
        avg_confidence: float
    ) -> int:
        """
        Save pattern report and statistics to database.

        Args:
            report_name: Name of the report
            statistics: Pattern statistics
            json_report: JSON report data
            total_videos: Total videos analyzed
            avg_confidence: Average confidence score

        Returns:
            ID of the saved report
        """
        # Save report
        json_str = json.dumps(json_report, indent=2, default=str)
        report_id = self.database_service.insert_pattern_report(
            report_name=report_name,
            total_videos=total_videos,
            average_confidence=avg_confidence,
            json_report=json_str
        )

        # Save statistics
        stat_dicts = []
        for stat in statistics:
            stat_dicts.append({
                'category': stat.category,
                'pattern': stat.pattern,
                'count': stat.count,
                'percentage': stat.percentage,
                'average_views': stat.average_views,
                'average_likes': stat.average_likes,
                'average_comments': stat.average_comments
            })

        self.database_service.insert_pattern_statistics(stat_dicts)

        logger.info(f"Saved pattern report '{report_name}' with {len(statistics)} statistics")
        return report_id

    def export_report(
        self,
        json_report: Dict[str, Any],
        output_dir: str = "data/output/reports"
    ) -> str:
        """
        Export JSON report to file.

        Args:
            json_report: Report data dictionary
            output_dir: Output directory path

        Returns:
            Path to the exported file
        """
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"pattern_report_{timestamp}.json"
        filepath = os.path.join(output_dir, filename)

        # Write JSON file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(json_report, f, indent=2, default=str, ensure_ascii=False)

        logger.info(f"Exported pattern report to: {filepath}")
        return filepath

    def generate_summary(
        self,
        statistics: List[PatternStatistic],
        total_videos: int,
        reports_saved: int
    ) -> PatternSummary:
        """
        Generate a summary of pattern analysis results.

        Args:
            statistics: Pattern statistics
            total_videos: Total videos analyzed
            reports_saved: Number of reports saved

        Returns:
            PatternSummary instance
        """
        # Group by category
        by_category: Dict[str, List[PatternStatistic]] = defaultdict(list)
        for stat in statistics:
            by_category[stat.category].append(stat)

        def get_top(category: str) -> Optional[str]:
            stats = by_category.get(category, [])
            return stats[0].pattern if stats else None

        summary = PatternSummary(
            videos_analyzed=total_videos,
            patterns_found=len(statistics),
            reports_saved=reports_saved,
            top_hook=get_top('hook_types'),
            top_emotion=get_top('emotions'),
            top_story_structure=get_top('story_structures'),
            top_thumbnail_pattern=get_top('thumbnail_patterns'),
            top_title_formula=get_top('title_formulas')
        )

        return summary

    def run(self, report_name: Optional[str] = None) -> PatternSummary:
        """
        Execute complete pattern analysis workflow.

        Args:
            report_name: Optional custom report name

        Returns:
            PatternSummary with results
        """
        if not report_name:
            report_name = f"pattern_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Analyze patterns
        statistics, json_report = self.analyze_patterns()

        # Calculate metrics
        records = self._load_analysis_records()
        total_videos = len(records)
        confidence_scores = [r.get('confidence_score', 0.0) for r in records]
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

        # Save report
        report_id = self.save_report(
            report_name=report_name,
            statistics=statistics,
            json_report=json_report,
            total_videos=total_videos,
            avg_confidence=avg_confidence
        )

        # Export JSON
        self.export_report(json_report)

        # Generate summary
        summary = self.generate_summary(statistics, total_videos, 1)

        logger.info(f"Pattern analysis workflow complete: {summary.patterns_found} patterns found")
        return summary
