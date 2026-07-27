"""
Tests for Collector Agent and related components.

This module contains unit and integration tests for the Collector Agent,
YouTube service, and database service.
"""

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

import pytest
from rich.console import Console

from src.models.video import Video
from src.services.youtube_service import YouTubeService, YouTubeAPIError
from src.database.database_service import DatabaseService
from src.agents.collector_agent import CollectorAgent
from src.utils.config import Config


# ============================================================================
# Video Model Tests
# ============================================================================

class TestVideoModel:
    """Test suite for Video Pydantic model."""
    
    def test_create_video_with_valid_data(self):
        """Test creating a Video with valid data."""
        video = Video(
            video_id="test123",
            title="Test Video",
            description="Test description",
            channel="Test Channel",
            channel_id="UC123",
            published_at=datetime.now(timezone.utc),
            duration="PT10M30S",
            view_count=1000,
            like_count=100,
            comment_count=50,
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=test123",
            search_keyword="python"
        )
        
        assert video.video_id == "test123"
        assert video.title == "Test Video"
        assert video.view_count == 1000
    
    def test_video_id_validation(self):
        """Test video_id validation."""
        with pytest.raises(ValueError):
            Video(
                video_id="",
                title="Test",
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
    
    def test_title_validation(self):
        """Test title validation."""
        with pytest.raises(ValueError, match="title cannot be empty"):
            Video(
                video_id="test123",
                title="   ",
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
    
    def test_view_count_validation(self):
        """Test view_count must be non-negative."""
        with pytest.raises(ValueError):
            Video(
                video_id="test123",
                title="Test",
                channel="Test",
                channel_id="UC123",
                published_at=datetime.now(timezone.utc),
                duration="PT10M",
                view_count=-1,
                like_count=0,
                comment_count=0,
                thumbnail_url="https://example.com/thumb.jpg",
                video_url="https://youtube.com/watch?v=test",
                search_keyword="test"
            )


# ============================================================================
# Database Service Tests
# ============================================================================

class TestDatabaseService:
    """Test suite for DatabaseService."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        db_service = DatabaseService(db_path)
        yield db_service
        
        # Cleanup
        db_service.disconnect()
        Path(db_path).unlink(missing_ok=True)
    
    def test_connect_and_create_tables(self, temp_db):
        """Test database connection and table creation."""
        temp_db.connect()
        temp_db.create_tables()
        
        # Verify tables exist
        cursor = temp_db.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='videos'")
        result = cursor.fetchone()
        assert result is not None
    
    def test_insert_video(self, temp_db):
        """Test inserting a single video."""
        temp_db.connect()
        temp_db.create_tables()
        
        video = Video(
            video_id="test123",
            title="Test Video",
            description="Test description",
            channel="Test Channel",
            channel_id="UC123",
            published_at=datetime.now(timezone.utc),
            duration="PT10M30S",
            view_count=1000,
            like_count=100,
            comment_count=50,
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=test123",
            search_keyword="python"
        )
        
        result = temp_db.insert_video(video)
        assert result is True
        
        # Verify insertion
        assert temp_db.video_exists("test123") is True
        assert temp_db.get_video_count() == 1
    
    def test_insert_duplicate_video(self, temp_db):
        """Test duplicate video detection."""
        temp_db.connect()
        temp_db.create_tables()
        
        video = Video(
            video_id="test123",
            title="Test Video",
            description="Test description",
            channel="Test Channel",
            channel_id="UC123",
            published_at=datetime.now(timezone.utc),
            duration="PT10M30S",
            view_count=1000,
            like_count=100,
            comment_count=50,
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=test123",
            search_keyword="python"
        )
        
        # Insert first time
        result1 = temp_db.insert_video(video)
        assert result1 is True
        
        # Insert again (should be skipped)
        result2 = temp_db.insert_video(video)
        assert result2 is False
        
        # Verify only one video in database
        assert temp_db.get_video_count() == 1
    
    def test_insert_videos_batch(self, temp_db):
        """Test batch video insertion."""
        temp_db.connect()
        temp_db.create_tables()
        
        videos = [
            Video(
                video_id=f"video{i}",
                title=f"Video {i}",
                description=f"Description {i}",
                channel="Test Channel",
                channel_id="UC123",
                published_at=datetime.now(timezone.utc),
                duration="PT10M",
                view_count=1000,
                like_count=100,
                comment_count=50,
                thumbnail_url="https://example.com/thumb.jpg",
                video_url=f"https://youtube.com/watch?v=video{i}",
                search_keyword="python"
            )
            for i in range(5)
        ]
        
        inserted, skipped = temp_db.insert_videos_batch(videos)
        assert inserted == 5
        assert skipped == 0
        assert temp_db.get_video_count() == 5
    
    def test_context_manager(self):
        """Test database service as context manager."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        with DatabaseService(db_path) as db:
            db.create_tables()
            video = Video(
                video_id="test123",
                title="Test Video",
                description="Test description",
                channel="Test Channel",
                channel_id="UC123",
                published_at=datetime.now(timezone.utc),
                duration="PT10M30S",
                view_count=1000,
                like_count=100,
                comment_count=50,
                thumbnail_url="https://example.com/thumb.jpg",
                video_url="https://youtube.com/watch?v=test123",
                search_keyword="python"
            )
            db.insert_video(video)
            assert db.get_video_count() == 1
        
        # Verify connection is closed
        Path(db_path).unlink(missing_ok=True)


# ============================================================================
# YouTube Service Tests
# ============================================================================

class TestYouTubeService:
    """Test suite for YouTubeService."""
    
    def test_init_with_valid_api_key(self):
        """Test initialization with valid API key."""
        service = YouTubeService(api_key="test-api-key")
        assert service.api_key == "test-api-key"
    
    def test_init_with_empty_api_key(self):
        """Test initialization with empty API key."""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            YouTubeService(api_key="")
    
    def test_parse_video_item(self):
        """Test parsing YouTube API response into Video model."""
        service = YouTubeService(api_key="test-api-key")
        
        mock_item = {
            "id": "abc123",
            "snippet": {
                "title": "Test Video",
                "description": "Test description",
                "channelTitle": "Test Channel",
                "channelId": "UC123",
                "publishedAt": "2024-01-01T00:00:00Z",
                "thumbnails": {
                    "medium": {"url": "https://example.com/thumb.jpg"}
                }
            },
            "statistics": {
                "viewCount": "1000",
                "likeCount": "100",
                "commentCount": "50"
            },
            "contentDetails": {
                "duration": "PT10M30S"
            }
        }
        
        video = service.parse_video_item(mock_item, "python")
        
        assert video.video_id == "abc123"
        assert video.title == "Test Video"
        assert video.channel == "Test Channel"
        assert video.view_count == 1000
        assert video.search_keyword == "python"
    
    @patch('src.services.youtube_service.requests.Session')
    def test_search_videos(self, mock_session_class):
        """Test video search functionality."""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "items": [
                {
                    "id": {"videoId": "vid1"},
                    "snippet": {"title": "Video 1"}
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        
        mock_session = Mock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        service = YouTubeService(api_key="test-key")
        results = service.search_videos("python", max_results=10)
        
        assert len(results) == 1
        assert results[0]["id"]["videoId"] == "vid1"


# ============================================================================
# Collector Agent Tests
# ============================================================================

class TestCollectorAgent:
    """Test suite for CollectorAgent."""
    
    @pytest.fixture
    def mock_services(self):
        """Create mock services for testing."""
        youtube_service = Mock(spec=YouTubeService)
        database_service = Mock(spec=DatabaseService)
        return youtube_service, database_service
    
    def test_init(self, mock_services):
        """Test CollectorAgent initialization."""
        youtube_service, database_service = mock_services
        agent = CollectorAgent(youtube_service, database_service)
        
        assert agent.youtube_service == youtube_service
        assert agent.database_service == database_service
        assert agent.console is not None
    
    def test_run_with_valid_keyword(self, mock_services):
        """Test running collection with valid keyword."""
        youtube_service, database_service = mock_services
        
        # Mock YouTube service responses
        mock_video_item = {
            "id": "test123",
            "snippet": {
                "title": "Test Video",
                "description": "Test description",
                "channelTitle": "Test Channel",
                "channelId": "UC123",
                "publishedAt": "2024-01-01T00:00:00Z",
                "thumbnails": {"medium": {"url": "https://example.com/thumb.jpg"}}
            },
            "statistics": {
                "viewCount": "1000",
                "likeCount": "100",
                "commentCount": "50"
            },
            "contentDetails": {
                "duration": "PT10M30S"
            }
        }
        
        youtube_service.search_and_get_details.return_value = [mock_video_item]
        youtube_service.parse_video_item.return_value = Video(
            video_id="test123",
            title="Test Video",
            description="Test description",
            channel="Test Channel",
            channel_id="UC123",
            published_at=datetime.now(timezone.utc),
            duration="PT10M30S",
            view_count=1000,
            like_count=100,
            comment_count=50,
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=test123",
            search_keyword="python"
        )
        
        database_service.insert_videos_batch.return_value = (1, 0)
        
        agent = CollectorAgent(youtube_service, database_service)
        new_count, skipped_count = agent.run("python", 10)
        
        assert new_count == 1
        assert skipped_count == 0
        youtube_service.search_and_get_details.assert_called_once_with("python", 10)
        database_service.insert_videos_batch.assert_called_once()
    
    def test_run_with_empty_keyword(self, mock_services):
        """Test running collection with empty keyword."""
        youtube_service, database_service = mock_services
        agent = CollectorAgent(youtube_service, database_service)
        
        with pytest.raises(ValueError, match="Search keyword cannot be empty"):
            agent.run("")
    
    def test_run_with_invalid_max_results(self, mock_services):
        """Test running collection with invalid max_results."""
        youtube_service, database_service = mock_services
        agent = CollectorAgent(youtube_service, database_service)
        
        with pytest.raises(ValueError, match="max_results must be between 1 and 50"):
            agent.run("python", 100)


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for the complete collection workflow."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        db_service = DatabaseService(db_path)
        db_service.connect()
        db_service.create_tables()
        
        yield db_service
        
        db_service.disconnect()
        Path(db_path).unlink(missing_ok=True)
    
    def test_full_workflow_mocked(self, temp_db):
        """Test complete workflow with mocked YouTube API."""
        # This would require mocking the YouTube API responses
        # and running the full collection workflow
        pass


# ============================================================================
# Configuration Tests
# ============================================================================

class TestConfig:
    """Test suite for configuration."""
    
    def test_config_with_env_vars(self, monkeypatch):
        """Test configuration with environment variables."""
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        monkeypatch.setenv("DEFAULT_MAX_RESULTS", "25")
        
        # Create a new config instance with validation
        from src.utils.config import Config
        config = Config(validate=True)
        
        assert config.YOUTUBE_API_KEY == "test-key"
        assert config.DEFAULT_MAX_RESULTS == 25
