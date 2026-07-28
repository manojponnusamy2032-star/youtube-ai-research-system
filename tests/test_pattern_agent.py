"""
Tests for Pattern Agent and related components.

This module tests the Pattern models, database operations, PatternService,
and PatternAgent functionality.
"""

import json
import os
import tempfile
from collections import defaultdict
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.pattern import PatternStatistic, PatternReport, PatternSummary
from src.models.video import Video
from src.models.analysis import Analysis, DifficultyLevel
from src.database.database_service import DatabaseService
from src.services.pattern_service import PatternService, PatternServiceError
from src.agents.pattern_agent import PatternAgent


# ============================================================================
# Test Pattern Models
# ============================================================================

class TestPatternModels:
    """Test Pattern Pydantic models."""

    def test_create_pattern_statistic(self):
        """Test creating a pattern statistic."""
        stat = PatternStatistic(
            category="hook_types",
            pattern="question",
            count=50,
            percentage=25.0,
            average_views=10000.0,
            average_likes=500.0,
            average_comments=50.0,
            average_duration=600.0,
            highest_view_video="vid123",
            lowest_view_video="vid456"
        )

        assert stat.category == "hook_types"
        assert stat.pattern == "question"
        assert stat.count == 50
        assert stat.percentage == 25.0
        assert stat.average_views == 10000.0
        assert stat.highest_view_video == "vid123"

    def test_pattern_statistic_defaults(self):
        """Test pattern statistic with defaults."""
        stat = PatternStatistic(
            category="emotions",
            pattern="excited",
            count=10,
            percentage=5.0
        )

        assert stat.average_views == 0.0
        assert stat.average_likes == 0.0
        assert stat.average_comments == 0.0
        assert stat.average_duration == 0.0
        assert stat.highest_view_video is None
        assert stat.lowest_view_video is None

    def test_pattern_statistic_percentage_validation(self):
        """Test percentage validation."""
        with pytest.raises(ValidationError):
            PatternStatistic(
                category="test",
                pattern="test",
                count=1,
                percentage=150.0  # Invalid: > 100
            )

    def test_pattern_statistic_count_validation(self):
        """Test count validation."""
        with pytest.raises(ValidationError):
            PatternStatistic(
                category="test",
                pattern="test",
                count=-1,  # Invalid: negative
                percentage=0.0
            )

    def test_create_pattern_report(self):
        """Test creating a pattern report."""
        report = PatternReport(
            report_name="test_report",
            total_videos=100,
            average_confidence=0.85,
            analysis_coverage=95.0
        )

        assert report.report_name == "test_report"
        assert report.total_videos == 100
        assert report.average_confidence == 0.85
        assert report.statistics == []
        assert report.recommendations == []

    def test_create_pattern_summary(self):
        """Test creating a pattern summary."""
        summary = PatternSummary(
            videos_analyzed=100,
            patterns_found=50,
            reports_saved=1,
            top_hook="question",
            top_emotion="excited"
        )

        assert summary.videos_analyzed == 100
        assert summary.patterns_found == 50
        assert summary.reports_saved == 1
        assert summary.top_hook == "question"
        assert summary.top_emotion == "excited"


# ============================================================================
# Test Pattern Database Operations
# ============================================================================

class TestPatternDatabase:
    """Test pattern database operations."""

    @pytest.fixture
    def db_service(self, tmp_path):
        """Create a test database service."""
        db_path = str(tmp_path / "test.db")
        db = DatabaseService(db_path)
        db.connect()
        db.create_tables()
        yield db
        db.disconnect()

    def test_pattern_reports_table_created(self, db_service):
        """Test that pattern_reports table is created."""
        cursor = db_service.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pattern_reports'")
        result = cursor.fetchone()
        assert result is not None
        assert result['name'] == 'pattern_reports'

    def test_pattern_statistics_table_created(self, db_service):
        """Test that pattern_statistics table is created."""
        cursor = db_service.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pattern_statistics'")
        result = cursor.fetchone()
        assert result is not None
        assert result['name'] == 'pattern_statistics'

    def test_pattern_reports_columns(self, db_service):
        """Test pattern_reports table columns."""
        cursor = db_service.connection.cursor()
        cursor.execute("PRAGMA table_info(pattern_reports)")
        columns = {row['name'] for row in cursor.fetchall()}

        required = {'id', 'report_name', 'created_at', 'total_videos', 'average_confidence', 'json_report'}
        assert required.issubset(columns)

    def test_pattern_statistics_columns(self, db_service):
        """Test pattern_statistics table columns."""
        cursor = db_service.connection.cursor()
        cursor.execute("PRAGMA table_info(pattern_statistics)")
        columns = {row['name'] for row in cursor.fetchall()}

        required = {'id', 'category', 'pattern', 'count', 'percentage',
                     'average_views', 'average_likes', 'average_comments'}
        assert required.issubset(columns)

    def test_insert_pattern_report(self, db_service):
        """Test inserting a pattern report."""
        report_id = db_service.insert_pattern_report(
            report_name="test_report",
            total_videos=100,
            average_confidence=0.85,
            json_report='{"key": "value"}'
        )

        assert report_id > 0

    def test_insert_pattern_statistics(self, db_service):
        """Test inserting pattern statistics."""
        stats = [
            {
                'category': 'hook_types',
                'pattern': 'question',
                'count': 50,
                'percentage': 25.0,
                'average_views': 10000.0,
                'average_likes': 500.0,
                'average_comments': 50.0
            }
        ]

        db_service.insert_pattern_statistics(stats)

        results = db_service.get_pattern_statistics('hook_types')
        assert len(results) == 1
        assert results[0]['pattern'] == 'question'
        assert results[0]['count'] == 50

    def test_get_pattern_reports(self, db_service):
        """Test getting pattern reports."""
        db_service.insert_pattern_report(
            report_name="report1",
            total_videos=50,
            average_confidence=0.8,
            json_report='{}'
        )
        db_service.insert_pattern_report(
            report_name="report2",
            total_videos=100,
            average_confidence=0.9,
            json_report='{}'
        )

        reports = db_service.get_pattern_reports()
        assert len(reports) == 2
        # Both reports should be present (order may vary due to same timestamp)
        report_names = {r['report_name'] for r in reports}
        assert report_names == {'report1', 'report2'}
        # Verify report data
        for report in reports:
            assert 'id' in report
            assert 'created_at' in report
            assert 'json_report' in report

    def test_get_pattern_statistics_by_category(self, db_service):
        """Test getting pattern statistics by category."""
        stats = [
            {'category': 'hook_types', 'pattern': 'question', 'count': 30, 'percentage': 15.0,
             'average_views': 1000, 'average_likes': 50, 'average_comments': 5},
            {'category': 'hook_types', 'pattern': 'statistic', 'count': 20, 'percentage': 10.0,
             'average_views': 2000, 'average_likes': 100, 'average_comments': 10},
            {'category': 'emotions', 'pattern': 'excited', 'count': 25, 'percentage': 12.5,
             'average_views': 1500, 'average_likes': 75, 'average_comments': 8},
        ]
        db_service.insert_pattern_statistics(stats)

        hook_stats = db_service.get_pattern_statistics('hook_types')
        assert len(hook_stats) == 2
        assert hook_stats[0]['pattern'] == 'question'  # Sorted by count desc

        emotion_stats = db_service.get_pattern_statistics('emotions')
        assert len(emotion_stats) == 1
        assert emotion_stats[0]['pattern'] == 'excited'

    def test_get_all_analysis_with_video_data(self, db_service):
        """Test getting analysis with video data."""
        # Insert a video
        from datetime import datetime
        video = Video(
            video_id="vid123",
            title="Test Video",
            description="Test",
            channel="Test Channel",
            channel_id="channel123",
            published_at=datetime.now(),
            duration="PT10M",
            view_count=1000,
            like_count=100,
            comment_count=10,
            thumbnail_url="http://example.com/thumb.jpg",
            video_url="http://youtube.com/watch?v=vid123",
            search_keyword="test"
        )
        db_service.insert_video(video)

        # Insert analysis
        analysis = Analysis(
            video_id="vid123",
            hook_type="question",
            opening_summary="test",
            main_topic="test",
            sub_topics=[],
            target_audience="beginners",
            emotion="excited",
            story_structure="tutorial",
            title_formula="test",
            thumbnail_pattern="test",
            retention_techniques=[],
            cta_type="direct",
            keywords=[],
            psychological_triggers=[],
            value_proposition="test",
            difficulty_level=DifficultyLevel.BEGINNER,
            estimated_video_style="test",
            summary="test",
            confidence_score=0.9,
            analysis_model="llama3.2:latest"
        )
        db_service.insert_analysis(analysis)

        records = db_service.get_all_analysis_with_video_data()
        assert len(records) == 1
        assert records[0]['video_id'] == 'vid123'
        assert records[0]['hook_type'] == 'question'
        assert records[0]['view_count'] == 1000
        assert records[0]['like_count'] == 100


# ============================================================================
# Test Pattern Service
# ============================================================================

class TestPatternService:
    """Test PatternService."""

    @pytest.fixture
    def mock_db_service(self):
        """Create a mock database service."""
        return Mock(spec=DatabaseService)

    @pytest.fixture
    def pattern_service(self, mock_db_service):
        """Create a pattern service with mocked dependencies."""
        return PatternService(mock_db_service)

    def test_init(self, pattern_service, mock_db_service):
        """Test service initialization."""
        assert pattern_service.database_service == mock_db_service

    def test_parse_list_field_valid(self, pattern_service):
        """Test parsing a valid list field."""
        result = pattern_service._parse_list_field("['item1', 'item2', 'item3']")
        assert result == ['item1', 'item2', 'item3']

    def test_parse_list_field_empty(self, pattern_service):
        """Test parsing an empty list field."""
        result = pattern_service._parse_list_field("")
        assert result == []

    def test_parse_list_field_invalid(self, pattern_service):
        """Test parsing an invalid list field."""
        result = pattern_service._parse_list_field("not a list")
        assert result == ['not a list']

    def test_parse_duration_valid(self, pattern_service):
        """Test parsing a valid ISO 8601 duration."""
        result = pattern_service._parse_duration("PT10M30S")
        assert result == 630.0

    def test_parse_duration_hours(self, pattern_service):
        """Test parsing duration with hours."""
        result = pattern_service._parse_duration("PT1H30M")
        assert result == 5400.0

    def test_parse_duration_invalid(self, pattern_service):
        """Test parsing an invalid duration."""
        result = pattern_service._parse_duration("invalid")
        assert result == 0.0

    def test_parse_duration_empty(self, pattern_service):
        """Test parsing an empty duration."""
        result = pattern_service._parse_duration("")
        assert result == 0.0

    def test_calculate_pattern_statistics(self, pattern_service):
        """Test calculating pattern statistics."""
        records = [
            {'hook_type': 'question', 'view_count': 1000, 'like_count': 50,
             'comment_count': 10, 'duration': 'PT10M', 'video_id': 'vid1'},
            {'hook_type': 'question', 'view_count': 2000, 'like_count': 100,
             'comment_count': 20, 'duration': 'PT15M', 'video_id': 'vid2'},
            {'hook_type': 'statistic', 'view_count': 500, 'like_count': 25,
             'comment_count': 5, 'duration': 'PT5M', 'video_id': 'vid3'},
        ]

        stats = pattern_service._calculate_pattern_statistics(
            records, 'hook_types', 'hook_type', is_list_field=False
        )

        assert len(stats) == 2
        assert stats[0].pattern == 'question'
        assert stats[0].count == 2
        assert stats[0].percentage == pytest.approx(66.67, rel=1e-2)
        assert stats[0].average_views == 1500.0
        assert stats[0].highest_view_video == 'vid2'
        assert stats[0].lowest_view_video == 'vid1'

        assert stats[1].pattern == 'statistic'
        assert stats[1].count == 1

    def test_calculate_pattern_statistics_empty(self, pattern_service):
        """Test calculating statistics with no records."""
        stats = pattern_service._calculate_pattern_statistics(
            [], 'hook_types', 'hook_type', is_list_field=False
        )
        assert stats == []

    def test_calculate_pattern_statistics_list_field(self, pattern_service):
        """Test calculating statistics for a list field."""
        records = [
            {'keywords': "['python', 'tutorial']", 'view_count': 1000,
             'like_count': 50, 'comment_count': 10, 'duration': 'PT10M', 'video_id': 'vid1'},
            {'keywords': "['python', 'ai']", 'view_count': 2000,
             'like_count': 100, 'comment_count': 20, 'duration': 'PT15M', 'video_id': 'vid2'},
        ]

        stats = pattern_service._calculate_pattern_statistics(
            records, 'keywords', 'keywords', is_list_field=True
        )

        # 'python' appears in both records, 'tutorial' and 'ai' in one each
        assert len(stats) == 3
        python_stat = next(s for s in stats if s.pattern == 'python')
        assert python_stat.count == 2
        assert python_stat.percentage == 100.0

    def test_generate_recommendations_empty(self, pattern_service):
        """Test generating recommendations with no data."""
        recommendations = pattern_service._generate_recommendations([], 0, 0.0)
        assert len(recommendations) == 1
        assert "No analysis data" in recommendations[0]

    def test_generate_recommendations_with_data(self, pattern_service):
        """Test generating recommendations with data."""
        stats = [
            PatternStatistic(
                category='hook_types', pattern='question', count=50, percentage=50.0,
                average_views=1000, average_likes=50, average_comments=5
            ),
        ]
        recommendations = pattern_service._generate_recommendations(stats, 100, 0.85)
        assert len(recommendations) >= 2
        assert any("Dominant" in r for r in recommendations)
        assert any("confidence" in r.lower() for r in recommendations)

    def test_build_json_report(self, pattern_service):
        """Test building JSON report."""
        records = [
            {'hook_type': 'question', 'view_count': 1000, 'like_count': 50,
             'comment_count': 10, 'duration': 'PT10M', 'video_id': 'vid1',
             'confidence_score': 0.9, 'emotion': 'excited', 'story_structure': 'tutorial',
             'thumbnail_pattern': 'face+text', 'title_formula': 'how-to',
             'retention_techniques': "['examples']", 'cta_type': 'direct',
             'target_audience': 'beginners', 'difficulty_level': 'beginner',
             'estimated_video_style': 'tutorial', 'value_proposition': 'learn',
             'keywords': "['python']", 'psychological_triggers': "['social proof']",
             'sub_topics': "['basics']"},
        ]

        stats = [
            PatternStatistic(
                category='hook_types', pattern='question', count=1, percentage=100.0,
                average_views=1000, average_likes=50, average_comments=10
            ),
        ]

        report = pattern_service._build_json_report(records, stats, 1, 0.9, ["test recommendation"])

        assert report['dataset']['videos'] == 1
        assert report['dataset']['analyses'] == 1
        assert len(report['hook_types']) == 1
        assert report['hook_types'][0]['pattern'] == 'question'
        assert report['recommendations'] == ["test recommendation"]

    def test_analyze_patterns_no_data(self, pattern_service, mock_db_service):
        """Test analyzing patterns with no data."""
        mock_db_service.get_all_analysis_with_video_data.return_value = []

        stats, report = pattern_service.analyze_patterns()

        assert stats == []
        assert report['dataset']['videos'] == 0
        assert report['dataset']['analyses'] == 0

    def test_analyze_patterns_with_data(self, pattern_service, mock_db_service):
        """Test analyzing patterns with data."""
        mock_db_service.get_all_analysis_with_video_data.return_value = [
            {'hook_type': 'question', 'view_count': 1000, 'like_count': 50,
             'comment_count': 10, 'duration': 'PT10M', 'video_id': 'vid1',
             'confidence_score': 0.9, 'emotion': 'excited', 'story_structure': 'tutorial',
             'thumbnail_pattern': 'face+text', 'title_formula': 'how-to',
             'retention_techniques': "['examples']", 'cta_type': 'direct',
             'target_audience': 'beginners', 'difficulty_level': 'beginner',
             'estimated_video_style': 'tutorial', 'value_proposition': 'learn',
             'keywords': "['python']", 'psychological_triggers': "['social proof']",
             'sub_topics': "['basics']"},
            {'hook_type': 'question', 'view_count': 2000, 'like_count': 100,
             'comment_count': 20, 'duration': 'PT15M', 'video_id': 'vid2',
             'confidence_score': 0.8, 'emotion': 'excited', 'story_structure': 'tutorial',
             'thumbnail_pattern': 'face+text', 'title_formula': 'how-to',
             'retention_techniques': "['examples']", 'cta_type': 'direct',
             'target_audience': 'beginners', 'difficulty_level': 'beginner',
             'estimated_video_style': 'tutorial', 'value_proposition': 'learn',
             'keywords': "['python']", 'psychological_triggers': "['social proof']",
             'sub_topics': "['basics']"},
            {'hook_type': 'statistic', 'view_count': 500, 'like_count': 25,
             'comment_count': 5, 'duration': 'PT5M', 'video_id': 'vid3',
             'confidence_score': 0.7, 'emotion': 'calm', 'story_structure': 'listicle',
             'thumbnail_pattern': 'before-after', 'title_formula': 'number+topic',
             'retention_techniques': "['storytelling']", 'cta_type': 'indirect',
             'target_audience': 'professionals', 'difficulty_level': 'advanced',
             'estimated_video_style': 'vlog', 'value_proposition': 'entertain',
             'keywords': "['ai']", 'psychological_triggers': "['scarcity']",
             'sub_topics': "['trends']"},
        ]

        stats, report = pattern_service.analyze_patterns()

        assert len(stats) > 0
        assert report['dataset']['videos'] == 3
        assert report['dataset']['analyses'] == 3
        assert len(report['hook_types']) == 2
        assert report['hook_types'][0]['pattern'] == 'question'
        assert report['hook_types'][0]['count'] == 2
        assert len(report['recommendations']) > 0

    def test_save_report(self, pattern_service, mock_db_service):
        """Test saving a report."""
        mock_db_service.insert_pattern_report.return_value = 1
        mock_db_service.insert_pattern_statistics = Mock()

        stats = [
            PatternStatistic(
                category='hook_types', pattern='question', count=50, percentage=25.0,
                average_views=1000, average_likes=50, average_comments=5
            ),
        ]

        report_id = pattern_service.save_report(
            report_name="test_report",
            statistics=stats,
            json_report={'key': 'value'},
            total_videos=100,
            avg_confidence=0.85
        )

        assert report_id == 1
        mock_db_service.insert_pattern_report.assert_called_once()
        mock_db_service.insert_pattern_statistics.assert_called_once()

    def test_export_report(self, pattern_service, tmp_path):
        """Test exporting a report."""
        json_report = {'dataset': {'videos': 10, 'analyses': 10}, 'recommendations': []}
        output_dir = str(tmp_path / "reports")

        filepath = pattern_service.export_report(json_report, output_dir)

        assert os.path.exists(filepath)
        assert filepath.endswith('.json')

        with open(filepath, 'r') as f:
            loaded = json.load(f)
        assert loaded['dataset']['videos'] == 10

    def test_generate_summary(self, pattern_service):
        """Test generating a summary."""
        stats = [
            PatternStatistic(
                category='hook_types', pattern='question', count=50, percentage=25.0,
                average_views=1000, average_likes=50, average_comments=5
            ),
            PatternStatistic(
                category='emotions', pattern='excited', count=30, percentage=15.0,
                average_views=1000, average_likes=50, average_comments=5
            ),
        ]

        summary = pattern_service.generate_summary(stats, 200, 1)

        assert summary.videos_analyzed == 200
        assert summary.patterns_found == 2
        assert summary.reports_saved == 1
        assert summary.top_hook == 'question'
        assert summary.top_emotion == 'excited'

    def test_run(self, pattern_service, mock_db_service):
        """Test the complete run workflow."""
        mock_db_service.get_all_analysis_with_video_data.return_value = [
            {'hook_type': 'question', 'view_count': 1000, 'like_count': 50,
             'comment_count': 10, 'duration': 'PT10M', 'video_id': 'vid1',
             'confidence_score': 0.9, 'emotion': 'excited', 'story_structure': 'tutorial',
             'thumbnail_pattern': 'face+text', 'title_formula': 'how-to',
             'retention_techniques': "['examples']", 'cta_type': 'direct',
             'target_audience': 'beginners', 'difficulty_level': 'beginner',
             'estimated_video_style': 'tutorial', 'value_proposition': 'learn',
             'keywords': "['python']", 'psychological_triggers': "['social proof']",
             'sub_topics': "['basics']"},
        ]
        mock_db_service.insert_pattern_report.return_value = 1
        mock_db_service.insert_pattern_statistics = Mock()

        with patch.object(pattern_service, 'export_report', return_value="/tmp/test.json"):
            summary = pattern_service.run("test_report")

        assert summary.videos_analyzed == 1
        assert summary.patterns_found > 0
        assert summary.reports_saved == 1


# ============================================================================
# Test Pattern Agent
# ============================================================================

class TestPatternAgent:
    """Test PatternAgent."""

    @pytest.fixture
    def mock_pattern_service(self):
        """Create a mock pattern service."""
        service = Mock(spec=PatternService)
        return service

    @pytest.fixture
    def mock_db_service(self):
        """Create a mock database service."""
        return Mock(spec=DatabaseService)

    @pytest.fixture
    def pattern_agent(self, mock_pattern_service, mock_db_service):
        """Create a pattern agent with mocked dependencies."""
        return PatternAgent(mock_pattern_service, mock_db_service)

    def test_init(self, pattern_agent):
        """Test agent initialization."""
        assert pattern_agent.pattern_service is not None
        assert pattern_agent.database_service is not None
        assert pattern_agent.console is not None

    def test_run_no_analyses(self, pattern_agent, mock_db_service):
        """Test run with no analyses."""
        mock_db_service.get_analysis_count.return_value = 0
        mock_db_service.get_video_count.return_value = 10

        summary = pattern_agent.run()

        assert summary.videos_analyzed == 0
        assert summary.patterns_found == 0
        assert summary.reports_saved == 0

    def test_run_with_analyses(self, pattern_agent, mock_pattern_service, mock_db_service):
        """Test run with analyses."""
        mock_db_service.get_analysis_count.return_value = 50
        mock_db_service.get_video_count.return_value = 50

        summary = PatternSummary(
            videos_analyzed=50,
            patterns_found=100,
            reports_saved=1,
            top_hook="question",
            top_emotion="excited"
        )
        mock_pattern_service.run.return_value = summary

        result = pattern_agent.run()

        assert result.videos_analyzed == 50
        assert result.patterns_found == 100
        assert result.reports_saved == 1
        mock_pattern_service.run.assert_called_once()

    def test_run_with_custom_report_name(self, pattern_agent, mock_pattern_service, mock_db_service):
        """Test run with custom report name."""
        mock_db_service.get_analysis_count.return_value = 10
        mock_db_service.get_video_count.return_value = 10

        summary = PatternSummary(
            videos_analyzed=10,
            patterns_found=5,
            reports_saved=1
        )
        mock_pattern_service.run.return_value = summary

        pattern_agent.run("custom_report")

        mock_pattern_service.run.assert_called_once_with("custom_report")


# ============================================================================
# Test Integration
# ============================================================================

class TestPatternIntegration:
    """Test integration between pattern components."""

    def test_full_pattern_workflow(self, tmp_path):
        """Test full pattern analysis workflow with real database."""
        db_path = str(tmp_path / "test.db")

        with DatabaseService(db_path) as db:
            # Insert a video
            from datetime import datetime
            video = Video(
                video_id="vid123",
                title="Test Video",
                description="Test",
                channel="Test Channel",
                channel_id="channel123",
                published_at=datetime.now(),
                duration="PT10M",
                view_count=1000,
                like_count=100,
                comment_count=10,
                thumbnail_url="http://example.com/thumb.jpg",
                video_url="http://youtube.com/watch?v=vid123",
                search_keyword="test"
            )
            db.insert_video(video)

            # Insert analysis
            analysis = Analysis(
                video_id="vid123",
                hook_type="question",
                opening_summary="test",
                main_topic="test",
                sub_topics=["topic1"],
                target_audience="beginners",
                emotion="excited",
                story_structure="tutorial",
                title_formula="how-to",
                thumbnail_pattern="face+text",
                retention_techniques=["examples"],
                cta_type="direct",
                keywords=["python"],
                psychological_triggers=["social proof"],
                value_proposition="learn",
                difficulty_level=DifficultyLevel.BEGINNER,
                estimated_video_style="tutorial",
                summary="test",
                confidence_score=0.9,
                analysis_model="llama3.2:latest"
            )
            db.insert_analysis(analysis)

            # Create pattern service and run
            service = PatternService(db)
            stats, report = service.analyze_patterns()

            assert len(stats) > 0
            assert report['dataset']['videos'] == 1
            assert report['dataset']['analyses'] == 1
            assert len(report['hook_types']) == 1
            assert report['hook_types'][0]['pattern'] == 'question'
            assert len(report['recommendations']) > 0

    def test_pattern_database_schema(self, tmp_path):
        """Test that pattern schema is properly created."""
        db_path = str(tmp_path / "test.db")

        with DatabaseService(db_path) as db:
            cursor = db.connection.cursor()

            # Check pattern_reports table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pattern_reports'")
            assert cursor.fetchone() is not None

            # Check pattern_statistics table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pattern_statistics'")
            assert cursor.fetchone() is not None

            # Check indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='pattern_reports'")
            indexes = {row['name'] for row in cursor.fetchall()}
            assert 'idx_pattern_reports_name' in indexes

            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='pattern_statistics'")
            indexes = {row['name'] for row in cursor.fetchall()}
            assert 'idx_pattern_stats_category' in indexes

    def test_pattern_report_export(self, tmp_path):
        """Test pattern report export to JSON file."""
        db_path = str(tmp_path / "test.db")
        output_dir = str(tmp_path / "reports")

        with DatabaseService(db_path) as db:
            # Insert video and analysis
            from datetime import datetime
            video = Video(
                video_id="vid1",
                title="Test",
                description="Test",
                channel="Test",
                channel_id="ch1",
                published_at=datetime.now(),
                duration="PT5M",
                view_count=100,
                like_count=10,
                comment_count=1,
                thumbnail_url="http://example.com",
                video_url="http://youtube.com",
                search_keyword="test"
            )
            db.insert_video(video)

            analysis = Analysis(
                video_id="vid1",
                hook_type="question",
                opening_summary="test",
                main_topic="test",
                sub_topics=[],
                target_audience="beginners",
                emotion="excited",
                story_structure="tutorial",
                title_formula="how-to",
                thumbnail_pattern="face+text",
                retention_techniques=[],
                cta_type="direct",
                keywords=[],
                psychological_triggers=[],
                value_proposition="learn",
                difficulty_level=DifficultyLevel.BEGINNER,
                estimated_video_style="tutorial",
                summary="test",
                confidence_score=0.8,
                analysis_model="llama3.2:latest"
            )
            db.insert_analysis(analysis)

            # Run pattern service
            service = PatternService(db)
            stats, report = service.analyze_patterns()

            # Export report
            filepath = service.export_report(report, output_dir)

            assert os.path.exists(filepath)
            assert filepath.endswith('.json')

            with open(filepath, 'r') as f:
                loaded = json.load(f)
            assert loaded['dataset']['videos'] == 1
            assert loaded['dataset']['analyses'] == 1
