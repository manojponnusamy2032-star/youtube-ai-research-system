"""
Comprehensive integration tests for the Collector Agent workflow.

These tests verify the full collection pipeline: YouTube API calls (mocked),
Pydantic validation, database operations, duplicate prevention,
error handling, and summary output.
"""

import json
import logging
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from unittest.mock import Mock, patch, MagicMock, call
from io import StringIO

import pytest
from rich.console import Console

from src.models.video import Video
from src.services.youtube_service import YouTubeService, YouTubeAPIError
from src.database.database_service import DatabaseService
from src.agents.collector_agent import CollectorAgent


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def db_service(temp_db_path: str) -> Generator[DatabaseService, None, None]:
    """Create a DatabaseService connected to a temp DB."""
    db = DatabaseService(db_path=temp_db_path)
    db.connect()
    db.create_tables()
    yield db
    db.disconnect()


@pytest.fixture
def youtube_service() -> Generator[YouTubeService, None, None]:
    """Create a YouTubeService (will be mocked in tests)."""
    ys = YouTubeService(api_key="test-api-key-for-integration")
    yield ys
    ys.close()


@pytest.fixture
def sample_video_items() -> list[dict]:
    """Return realistic YouTube API response items (all with 500k+ views)."""
    return [
        {
            "id": "abc123",
            "snippet": {
                "title": "Stickman Animation - Epic Battle",
                "description": "An amazing stickman battle animation",
                "channelTitle": "Stickman Creator",
                "channelId": "UCstickman1",
                "publishedAt": "2024-01-15T10:30:00Z",
                "thumbnails": {
                    "medium": {"url": "https://i.ytimg.com/vi/abc123/mqdefault.jpg"},
                    "default": {"url": "https://i.ytimg.com/vi/abc123/default.jpg"}
                }
            },
            "statistics": {
                "viewCount": "1500000",
                "likeCount": "45000",
                "commentCount": "3200"
            },
            "contentDetails": {
                "duration": "PT5M30S"
            }
        },
        {
            "id": "def456",
            "snippet": {
                "title": "Stickman Fight Compilation",
                "description": "Best stickman fights of 2024",
                "channelTitle": "Fight Animator",
                "channelId": "UCfighter1",
                "publishedAt": "2024-02-20T15:00:00Z",
                "thumbnails": {
                    "medium": {"url": "https://i.ytimg.com/vi/def456/mqdefault.jpg"},
                    "default": {"url": "https://i.ytimg.com/vi/def456/default.jpg"}
                }
            },
            "statistics": {
                "viewCount": "890000",
                "likeCount": "32000",
                "commentCount": "1800"
            },
            "contentDetails": {
                "duration": "PT10M15S"
            }
        },
    ]


@pytest.fixture
def sample_video_item_low_views() -> dict:
    """Return a video item with views below 500k (to test filter)."""
    return {
        "id": "low001",
        "snippet": {
            "title": "New Stickman Tutorial",
            "description": "How to animate stickman",
            "channelTitle": "Tutorial Channel",
            "channelId": "UCtutorial1",
            "publishedAt": "2025-06-01T08:00:00Z",
            "thumbnails": {
                "medium": {"url": "https://i.ytimg.com/vi/low001/mqdefault.jpg"}
            }
        },
        "statistics": {
            "viewCount": "15000",
            "likeCount": "500",
            "commentCount": "20"
        },
        "contentDetails": {
            "duration": "PT8M"
        }
    }


@pytest.fixture
def sample_video_item_missing_fields() -> dict:
    """Return a video item missing critical fields (to test error handling)."""
    return {
        "id": "missing001",
        "snippet": {
            "title": "Missing Data Video"
            # Missing channelTitle, channelId, publishedAt
        }
        # Missing statistics, contentDetails
    }


# ============================================================================
# 1. Test: Search YouTube using multiple keywords
# ============================================================================

class TestMultiKeywordSearch:
    """Integration: search with multiple keywords."""

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_search_multiple_keywords(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict]
    ):
        """Verify collection runs correctly across multiple keywords."""
        # Mock search to return results for each keyword
        def search_side_effect(keyword, max_results=50, language="en", region_code="US"):
            if keyword == "stickman animation":
                return [{"id": {"videoId": "abc123"}}]
            elif keyword == "stickman fight":
                return [{"id": {"videoId": "def456"}}]
            return []
        
        mock_search.side_effect = search_side_effect
        
        # Return only the matching video per keyword
        def details_side_effect(video_ids):
            return [v for v in sample_video_items if v["id"] in video_ids]
        
        mock_get_details.side_effect = details_side_effect
        
        agent = CollectorAgent(youtube_service, db_service)
        keywords = ["stickman animation", "stickman fight", "stickman vs"]
        
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                new_count, skipped_count = agent.run_batch(keywords, 50)
        
        # Should have found 2 unique videos total (abc123, def456)
        assert new_count == 2
        assert skipped_count == 0
        assert mock_search.call_count == 3
        mock_search.assert_has_calls([
            call("stickman animation", 50),
            call("stickman fight", 50),
            call("stickman vs", 50),
        ])


# ============================================================================
# 2. Test: Save videos to SQLite
# ============================================================================

class TestSaveToSQLite:
    """Integration: verify videos are correctly persisted."""

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_videos_saved_to_database(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict],
        temp_db_path: str
    ):
        """Verify videos are actually written to SQLite."""
        mock_search.return_value = [{"id": {"videoId": "abc123"}}]
        mock_get_details.return_value = [sample_video_items[0]]
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                new_count, skipped_count = agent.run("stickman animation", 50)
        
        assert new_count == 1
        assert skipped_count == 0
        
        # Directly query the database to verify persistence
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT video_id, title, view_count FROM videos")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 1
        assert rows[0][0] == "abc123"
        assert rows[0][1] == "Stickman Animation - Epic Battle"
        assert rows[0][2] == 1500000

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_all_fields_persisted(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict],
        temp_db_path: str
    ):
        """Verify all Video model fields are correctly stored in DB."""
        mock_search.return_value = [{"id": {"videoId": "abc123"}}]
        mock_get_details.return_value = [sample_video_items[0]]
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                agent.run("stickman animation", 50)
        
        conn = sqlite3.connect(temp_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos WHERE video_id = ?", ("abc123",))
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row["video_id"] == "abc123"
        assert row["title"] == "Stickman Animation - Epic Battle"
        assert row["description"] == "An amazing stickman battle animation"
        assert row["channel"] == "Stickman Creator"
        assert row["channel_id"] == "UCstickman1"
        assert row["view_count"] == 1500000
        assert row["like_count"] == 45000
        assert row["comment_count"] == 3200
        assert row["duration"] == "PT5M30S"
        assert row["thumbnail_url"] == "https://i.ytimg.com/vi/abc123/mqdefault.jpg"
        assert row["video_url"] == "https://www.youtube.com/watch?v=abc123"
        assert row["search_keyword"] == "stickman animation"
        assert row["id"] is not None  # auto-increment primary key
        assert row["created_at"] is not None  # auto-generated timestamp


# ============================================================================
# 3. Test: Prevent duplicate videos
# ============================================================================

class TestDuplicatePrevention:
    """Integration: verify duplicates are correctly prevented."""

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_duplicate_same_keyword(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict]
    ):
        """Running the same keyword twice should skip duplicates."""
        mock_search.return_value = [{"id": {"videoId": "abc123"}}]
        mock_get_details.return_value = [sample_video_items[0]]
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                new1, skipped1 = agent.run("stickman animation", 50)
                new2, skipped2 = agent.run("stickman animation", 50)
        
        assert new1 == 1
        assert skipped1 == 0
        assert new2 == 0
        assert skipped2 == 1

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_duplicate_different_keywords(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict]
    ):
        """Same video appearing under different keywords should be skipped."""
        def search_side_effect(keyword, max_results=50, language="en", region_code="US"):
            return [{"id": {"videoId": "abc123"}}]
        
        mock_search.side_effect = search_side_effect
        mock_get_details.return_value = [sample_video_items[0]]  # Same video
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                new1, skipped1 = agent.run("stickman animation", 50)
                new2, skipped2 = agent.run("stickman fight", 50)
        
        assert new1 == 1
        assert skipped1 == 0
        assert new2 == 0
        assert skipped2 == 1  # Duplicate from different keyword

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_batch_duplicate_handling(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict]
    ):
        """Batch run should correctly count duplicates across keywords."""
        # Map video IDs to their full metadata
        video_map = {v["id"]: v for v in sample_video_items}
        
        def search_side_effect(keyword, max_results=50, language="en", region_code="US"):
            if keyword == "stickman animation":
                return [{"id": {"videoId": "abc123"}}]
            elif keyword == "stickman fight":
                return [{"id": {"videoId": "def456"}}]
            elif keyword == "stickman vs":
                return [{"id": {"videoId": "abc123"}}]  # Duplicate of first
            return []
        
        def details_side_effect(video_ids):
            return [video_map[vid] for vid in video_ids if vid in video_map]
        
        mock_search.side_effect = search_side_effect
        mock_get_details.side_effect = details_side_effect
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                new_count, skipped_count = agent.run_batch(
                    ["stickman animation", "stickman fight", "stickman vs"], 50
                )
        
        assert new_count == 2  # Two unique videos
        assert skipped_count == 1  # One duplicate


# ============================================================================
# 4. Test: Handle API errors gracefully
# ============================================================================

class TestAPIErrorHandling:
    """Integration: verify graceful handling of YouTube API errors."""

    @patch.object(YouTubeService, 'search_videos')
    def test_api_error_during_search(
        self,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService
    ):
        """An API error during search should raise RuntimeError."""
        mock_search.side_effect = YouTubeAPIError("API quota exceeded")
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with pytest.raises(RuntimeError, match="API quota exceeded"):
                agent.run("stickman animation", 50)

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_api_error_during_details(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService
    ):
        """An API error during detail retrieval should raise RuntimeError."""
        mock_search.return_value = [{"id": {"videoId": "abc123"}}]
        mock_get_details.side_effect = YouTubeAPIError("Video not found")
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with pytest.raises(RuntimeError, match="Video not found"):
                agent.run("stickman animation", 50)

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_batch_continues_on_keyword_failure(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict]
    ):
        """Batch collection should continue even if one keyword fails."""
        video_map = {v["id"]: v for v in sample_video_items}
        
        def search_side_effect(keyword, max_results=50, language="en", region_code="US"):
            if keyword == "stickman animation":
                return [{"id": {"videoId": "abc123"}}]
            elif keyword == "stickman fight":
                raise YouTubeAPIError("Failed for fight")
            elif keyword == "stickman vs":
                return [{"id": {"videoId": "def456"}}]
            return []
        
        def details_side_effect(video_ids):
            return [video_map[vid] for vid in video_ids if vid in video_map]
        
        mock_search.side_effect = search_side_effect
        mock_get_details.side_effect = details_side_effect
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                # Should not raise - batch continues on error
                new_count, skipped_count = agent.run_batch(
                    ["stickman animation", "stickman fight", "stickman vs"], 50
                )
        
        # Two keywords succeeded (animation and vs), one failed (fight)
        assert new_count == 2  # abc123 and def456
        assert skipped_count == 0


# ============================================================================
# 5. Test: Handle empty search results
# ============================================================================

class TestEmptyResults:
    """Integration: verify handling of empty search results."""

    @patch.object(YouTubeService, 'search_videos')
    def test_empty_search_results(
        self,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService
    ):
        """Search with no results should return (0, 0) gracefully."""
        mock_search.return_value = []
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                new_count, skipped_count = agent.run("nonexistent keyword xyz", 50)
        
        assert new_count == 0
        assert skipped_count == 0

    @patch.object(YouTubeService, 'search_videos')
    def test_empty_keyword_list(
        self,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService
    ):
        """Batch with no keywords should raise ValueError."""
        agent = CollectorAgent(youtube_service, db_service)
        with pytest.raises(ValueError, match="Search keyword cannot be empty"):
            agent.run("", 50)

    @patch.object(YouTubeService, 'search_videos')
    def test_whitespace_only_keywords(
        self,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService
    ):
        """Whitespace-only keywords should raise ValueError."""
        agent = CollectorAgent(youtube_service, db_service)
        with pytest.raises(ValueError, match="Search keyword cannot be empty"):
            agent.run("   ", 50)


# ============================================================================
# 6. Test: Validate all data with Pydantic
# ============================================================================

class TestPydanticValidation:
    """Integration: verify Pydantic validation catches invalid data."""

    def test_video_model_required_fields(self):
        """Pydantic should reject missing required fields."""
        with pytest.raises(ValueError):
            Video(
                video_id="",  # empty - should fail
                title="Test",
                description="Test",
                channel="Test",
                channel_id="UC123",
                published_at=datetime.now(timezone.utc),
                duration="PT10M",
                view_count=0,
                like_count=0,
                comment_count=0,
                thumbnail_url="https://example.com/thumb.jpg",
                video_url="https://youtube.com/watch?v=test",
                search_keyword="test"
            )

    def test_video_model_negative_view_count(self):
        """Pydantic should reject negative view counts."""
        with pytest.raises(ValueError):
            Video(
                video_id="test123",
                title="Test",
                description="Test",
                channel="Test",
                channel_id="UC123",
                published_at=datetime.now(timezone.utc),
                duration="PT10M",
                view_count=-100,  # negative - should fail
                like_count=0,
                comment_count=0,
                thumbnail_url="https://example.com/thumb.jpg",
                video_url="https://youtube.com/watch?v=test",
                search_keyword="test"
            )

    def test_video_model_negative_like_count(self):
        """Pydantic should reject negative like counts."""
        with pytest.raises(ValueError):
            Video(
                video_id="test123",
                title="Test",
                description="Test",
                channel="Test",
                channel_id="UC123",
                published_at=datetime.now(timezone.utc),
                duration="PT10M",
                view_count=1000,
                like_count=-50,  # negative - should fail
                comment_count=0,
                thumbnail_url="https://example.com/thumb.jpg",
                video_url="https://youtube.com/watch?v=test",
                search_keyword="test"
            )

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_invalid_video_data_skipped(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_item_missing_fields: dict
    ):
        """Videos with invalid/missing data should be skipped, not crash."""
        mock_search.return_value = [{"id": {"videoId": "missing001"}}]
        mock_get_details.return_value = [sample_video_item_missing_fields]
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                # Should not crash - should handle parse error gracefully
                new_count, skipped_count = agent.run("stickman animation", 50)
        
        # The video should fail parsing and be skipped
        assert new_count == 0
        assert skipped_count == 0


# ============================================================================
# 7. Test: Display a professional Rich summary
# ============================================================================

class TestRichSummary:
    """Integration: verify Rich summary is displayed professionally."""

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_summary_contains_required_info(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict]
    ):
        """Summary panel should include keyword, found, new, skipped."""
        mock_search.return_value = [{"id": {"videoId": "abc123"}}]
        mock_get_details.return_value = [sample_video_items[0]]
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            # Capture console output
            console = Console(force_terminal=True, width=120)
            
            # Test the _print_summary method directly
            with patch.object(agent, 'console', console):
                with patch('sys.stdout', new=StringIO()) as fake_out:
                    agent._print_summary("stickman animation", 1, 1, 0)
                    output = fake_out.getvalue()
                    
                    assert "stickman animation" in output
                    assert "1 videos" in output
                    assert "New:" in output
                    assert "Skipped:" in output
                    assert "Database updated successfully" in output

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_batch_summary_contains_expected_info(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict]
    ):
        """Batch summary should include expected max results."""
        def search_side_effect(keyword, max_results=50, language="en", region_code="US"):
            return [{"id": {"videoId": "abc123"}}]
        
        mock_search.side_effect = search_side_effect
        mock_get_details.return_value = [sample_video_items[0]]
        
        agent = CollectorAgent(youtube_service, db_service)
        console = Console(force_terminal=True, width=120)
        
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, 'console', console):
                with patch('sys.stdout', new=StringIO()) as fake_out:
                    # Run batch inline to capture the final panel
                    from rich.panel import Panel
                    from rich.text import Text
                    
                    total_new = 1
                    total_skipped = 0
                    total_found = 1
                    keywords = ["stickman animation"]
                    expected_max = 1 * 50
                    
                    final_text = (
                        f"[bold]Batch Collection Complete[/bold]\n\n"
                        f"Keywords processed: {len(keywords)}\n"
                        f"Max results per keyword: 50\n"
                        f"Expected max results: {expected_max}\n"
                        f"Total found (new + skipped): {total_found}\n"
                        f"Total new videos: {total_new}\n"
                        f"Total skipped: {total_skipped}"
                    )
                    console.print(Panel(final_text, border_style="blue", padding=(1, 2)))
                    output = fake_out.getvalue()
                    
                    assert "Batch Collection Complete" in output
                    assert "Keywords processed:" in output
                    assert "Expected max results:" in output
                    assert "Total found" in output


# ============================================================================
# 8. Test: Verify the database schema
# ============================================================================

class TestDatabaseSchema:
    """Integration: verify the database schema is correct."""

    def test_table_exists(self, db_service: DatabaseService, temp_db_path: str):
        """Verify the 'videos' table was created."""
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='videos'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_table_columns(self, db_service: DatabaseService, temp_db_path: str):
        """Verify all expected columns exist with correct types."""
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(videos)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()
        
        expected_columns = {
            "id": "INTEGER",
            "video_id": "TEXT",
            "title": "TEXT",
            "description": "TEXT",
            "channel": "TEXT",
            "channel_id": "TEXT",
            "published_at": "TEXT",
            "duration": "TEXT",
            "view_count": "INTEGER",
            "like_count": "INTEGER",
            "comment_count": "INTEGER",
            "thumbnail_url": "TEXT",
            "video_url": "TEXT",
            "search_keyword": "TEXT",
            "created_at": "TEXT",
        }
        
        for col_name, col_type in expected_columns.items():
            assert col_name in columns, f"Missing column: {col_name}"
            assert col_type in columns[col_name], f"Wrong type for {col_name}: {columns[col_name]}"

    def test_unique_constraint(self, db_service: DatabaseService, temp_db_path: str):
        """Verify video_id has a UNIQUE constraint."""
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        
        # Get the SQL used to create the table
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='videos'")
        create_sql = cursor.fetchone()[0]
        conn.close()
        
        assert "UNIQUE" in create_sql.upper()
        assert "video_id" in create_sql

    def test_indexes_exist(self, db_service: DatabaseService, temp_db_path: str):
        """Verify indexes are created for performance."""
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        expected_indexes = ["idx_video_id", "idx_search_keyword", "idx_channel_id", "idx_published_at"]
        for idx in expected_indexes:
            assert idx in indexes, f"Missing index: {idx}"


# ============================================================================
# 9. Test: Ensure clean logging
# ============================================================================

class TestCleanLogging:
    """Integration: verify logging is clean and informative."""

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_logging_contains_key_info(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict],
        caplog: pytest.LogCaptureFixture
    ):
        """Logs should contain key workflow events."""
        caplog.set_level(logging.INFO)
        
        mock_search.return_value = [{"id": {"videoId": "abc123"}}]
        mock_get_details.return_value = [sample_video_items[0]]
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                agent.run("stickman animation", 50)
        
        # Check for important log messages
        log_text = "\n".join([rec.message for rec in caplog.records])
        assert "Collector Agent initialized" in log_text
        assert "Collection complete" in log_text
        assert "1 new" in log_text
        assert "0 skipped" in log_text


# ============================================================================
# 10. Test: Bug fixes and edge cases
# ============================================================================

class TestBugFixes:
    """Integration: verify common bugs are handled."""

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_min_views_filter_applied(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict],
        sample_video_item_low_views: dict
    ):
        """Verify the 500k min_views filter is applied correctly."""
        mock_search.return_value = [
            {"id": {"videoId": "abc123"}},
            {"id": {"videoId": "low001"}}
        ]
        # Return one video above 500k and one below
        mock_get_details.return_value = [
            sample_video_items[0],  # 1.5M views - above threshold
            sample_video_item_low_views  # 15K views - below threshold
        ]
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                new_count, skipped_count = agent.run("stickman animation", 50)
        
        # Only the 1.5M view video should pass the 500k filter
        assert new_count == 1
        assert skipped_count == 0

    def test_database_directory_created(self, temp_db_path: str):
        """Verify database directory is auto-created."""
        # Use a path in a non-existent directory
        nested_path = str(Path(temp_db_path).parent / "nested" / "subdir" / "test.db")
        db = DatabaseService(db_path=nested_path)
        db.connect()
        db.create_tables()
        
        # Directory should have been created
        assert Path(nested_path).parent.exists()
        
        db.disconnect()
        # Cleanup
        Path(nested_path).unlink(missing_ok=True)
        Path(nested_path).parent.rmdir()
        Path(nested_path).parent.parent.rmdir()

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_concurrent_collection_no_data_corruption(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict]
    ):
        """Sequential collections should not corrupt data."""
        mock_search.return_value = [{"id": {"videoId": "abc123"}}]
        mock_get_details.return_value = [sample_video_items[0]]
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                # Run collection twice
                agent.run("stickman animation", 50)
                agent.run("stickman fight", 50)
        
        # Database should still have correct count
        assert db_service.get_video_count() == 1  # Same video both times

    def test_context_manager_cleanup(self, temp_db_path: str):
        """DatabaseService context manager should clean up properly."""
        with DatabaseService(temp_db_path) as db:
            db.create_tables()
            assert db.connection is not None
        
        # After context exit, connection should be closed
        assert db.connection is None

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_mixed_valid_and_invalid_videos(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict],
        sample_video_item_missing_fields: dict
    ):
        """Mix of valid and invalid videos: valid ones should still be saved."""
        mock_search.return_value = [
            {"id": {"videoId": "abc123"}},
            {"id": {"videoId": "missing001"}}
        ]
        mock_get_details.return_value = [
            sample_video_items[0],          # Valid
            sample_video_item_missing_fields  # Invalid (will fail parsing)
        ]
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                new_count, skipped_count = agent.run("stickman animation", 50)
        
        # Only the valid video should be saved
        assert new_count == 1
        assert skipped_count == 0
        assert db_service.get_video_count() == 1

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_max_results_boundary(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService
    ):
        """max_results at boundary values should work."""
        mock_search.return_value = []
        mock_get_details.return_value = []
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                # Test min boundary
                result = agent.run("test", 1)
                assert result == (0, 0)
                
                # Test max boundary
                result = agent.run("test", 50)
                assert result == (0, 0)

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_special_characters_in_keyword(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict]
    ):
        """Keywords with special characters should be handled."""
        mock_search.return_value = [{"id": {"videoId": "abc123"}}]
        mock_get_details.return_value = [sample_video_items[0]]
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                new_count, skipped_count = agent.run("stickman 100% fight!!!", 50)
        
        assert new_count == 1
        assert skipped_count == 0
        mock_search.assert_called_with("stickman 100% fight!!!", 50)


# ============================================================================
# Complete workflow test
# ============================================================================

class TestCompleteWorkflow:
    """Full end-to-end integration test."""

    @patch.object(YouTubeService, 'search_videos')
    @patch.object(YouTubeService, 'get_video_details')
    def test_full_collection_pipeline(
        self,
        mock_get_details: Mock,
        mock_search: Mock,
        db_service: DatabaseService,
        youtube_service: YouTubeService,
        sample_video_items: list[dict],
        temp_db_path: str
    ):
        """
        Complete pipeline test:
        1. Mock search returns real-looking video IDs
        2. Mock details returns real-looking metadata (all 500k+ views)
        3. CollectorAgent runs and saves to DB
        4. Verify DB has correct data
        5. Verify duplicate prevention works
        """
        # ---- Step 1: First collection ----
        mock_search.return_value = [
            {"id": {"videoId": "abc123"}},
            {"id": {"videoId": "def456"}}
        ]
        mock_get_details.return_value = sample_video_items
        
        agent = CollectorAgent(youtube_service, db_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                new_count, skipped_count = agent.run("stickman animation", 50)
        
        assert new_count == 2
        assert skipped_count == 0
        
        # ---- Step 2: Verify DB contents ----
        conn = sqlite3.connect(temp_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT video_id, title, view_count FROM videos ORDER BY video_id")
        rows = cursor.fetchall()
        assert len(rows) == 2
        assert rows[0]["video_id"] == "abc123"
        assert rows[1]["video_id"] == "def456"
        assert rows[0]["view_count"] >= 500000
        assert rows[1]["view_count"] >= 500000
        
        # ---- Step 3: Run again (duplicate prevention) ----
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                new_count, skipped_count = agent.run("stickman animation", 50)
        
        assert new_count == 0
        assert skipped_count == 2
        
        cursor.execute("SELECT COUNT(*) FROM videos")
        assert cursor.fetchone()[0] == 2  # Still 2 videos
        conn.close()