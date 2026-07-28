"""
Tests for Transcript Agent and related components.

This module contains unit and integration tests for the Transcript model,
TranscriptService, TranscriptAgent, and transcript database operations.
"""

import logging
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call, PropertyMock
from typing import Generator

import pytest
from rich.console import Console

from src.models.transcript import Transcript, TranscriptMethod, TranscriptStatus
from src.database.database_service import DatabaseService
from src.services.transcript_service import TranscriptService
from src.agents.transcript_agent import TranscriptAgent


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    try:
        Path(db_path).unlink(missing_ok=True)
    except PermissionError:
        pass


@pytest.fixture
def db_service(temp_db_path: str) -> Generator[DatabaseService, None, None]:
    """Create a DatabaseService connected to a temp DB."""
    db = DatabaseService(db_path=temp_db_path)
    db.connect()
    db.create_tables()
    yield db
    try:
        db.disconnect()
    except Exception:
        pass


@pytest.fixture
def transcript_service(db_service: DatabaseService) -> TranscriptService:
    """Create a TranscriptService with mocked external dependencies."""
    return TranscriptService(database_service=db_service, downloads_dir=tempfile.gettempdir())


# ============================================================================
# Transcript Model Tests
# ============================================================================

class TestTranscriptModel:
    """Test suite for Transcript Pydantic model."""

    def test_create_transcript_with_valid_data(self):
        """Test creating a Transcript with valid data."""
        transcript = Transcript(
            video_id="abc123",
            language="en",
            transcript="Hello world this is a transcript",
            method=TranscriptMethod.YOUTUBE_API,
            status=TranscriptStatus.COMPLETED
        )
        
        assert transcript.video_id == "abc123"
        assert transcript.language == "en"
        assert transcript.transcript == "Hello world this is a transcript"
        assert transcript.method == TranscriptMethod.YOUTUBE_API
        assert transcript.status == TranscriptStatus.COMPLETED

    def test_transcript_video_id_validation(self):
        """Test video_id validation."""
        with pytest.raises(ValueError):
            Transcript(
                video_id="",
                transcript="test",
                method=TranscriptMethod.YOUTUBE_API
            )

    def test_transcript_defaults(self):
        """Test default values."""
        transcript = Transcript(
            video_id="abc123",
            transcript="test transcript",
            method=TranscriptMethod.WHISPER
        )
        
        assert transcript.language == "en"
        assert transcript.status == TranscriptStatus.COMPLETED
        assert transcript.created_at is None

    def test_transcript_method_enum_values(self):
        """Test TranscriptMethod enum values."""
        assert TranscriptMethod.YOUTUBE_API.value == "youtube_api"
        assert TranscriptMethod.YTDLP_CAPTIONS.value == "ytdlp_captions"
        assert TranscriptMethod.WHISPER.value == "whisper"

    def test_transcript_status_enum_values(self):
        """Test TranscriptStatus enum values."""
        assert TranscriptStatus.COMPLETED.value == "completed"
        assert TranscriptStatus.FAILED.value == "failed"


# ============================================================================
# Transcript Database Tests
# ============================================================================

class TestTranscriptDatabase:
    """Test suite for transcript database operations."""

    def test_transcripts_table_created(self, db_service: DatabaseService, temp_db_path: str):
        """Verify the transcripts table was created."""
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transcripts'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_transcripts_table_columns(self, db_service: DatabaseService, temp_db_path: str):
        """Verify all expected columns exist."""
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(transcripts)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()
        
        expected_columns = {
            "id": "INTEGER",
            "video_id": "TEXT",
            "language": "TEXT",
            "transcript": "TEXT",
            "method": "TEXT",
            "status": "TEXT",
            "created_at": "TEXT",
        }
        
        for col_name, col_type in expected_columns.items():
            assert col_name in columns, f"Missing column: {col_name}"

    def test_insert_transcript(self, db_service: DatabaseService):
        """Test inserting a transcript."""
        transcript = Transcript(
            video_id="abc123",
            language="en",
            transcript="Hello world",
            method=TranscriptMethod.YOUTUBE_API
        )
        
        result = db_service.insert_transcript(transcript)
        assert result is True
        assert db_service.transcript_exists("abc123") is True

    def test_insert_duplicate_transcript(self, db_service: DatabaseService):
        """Test duplicate transcript prevention."""
        transcript = Transcript(
            video_id="abc123",
            language="en",
            transcript="Hello world",
            method=TranscriptMethod.YOUTUBE_API
        )
        
        result1 = db_service.insert_transcript(transcript)
        result2 = db_service.insert_transcript(transcript)
        
        assert result1 is True
        assert result2 is False

    def test_get_videos_without_transcripts(self, db_service: DatabaseService):
        """Test fetching videos that need transcripts."""
        # No videos in DB yet
        videos = db_service.get_videos_without_transcripts(10)
        assert videos == []

    def test_get_transcript_count(self, db_service: DatabaseService):
        """Test transcript count."""
        assert db_service.get_transcript_count() == 0
        
        t1 = Transcript(video_id="v1", transcript="t1", method=TranscriptMethod.YOUTUBE_API)
        t2 = Transcript(video_id="v2", transcript="t2", method=TranscriptMethod.WHISPER)
        
        db_service.insert_transcript(t1)
        db_service.insert_transcript(t2)
        
        assert db_service.get_transcript_count() == 2

    def test_get_transcript_count_by_method(self, db_service: DatabaseService):
        """Test transcript count by method."""
        t1 = Transcript(video_id="v1", transcript="t1", method=TranscriptMethod.YOUTUBE_API)
        t2 = Transcript(video_id="v2", transcript="t2", method=TranscriptMethod.YOUTUBE_API)
        t3 = Transcript(video_id="v3", transcript="t3", method=TranscriptMethod.WHISPER)
        
        db_service.insert_transcript(t1)
        db_service.insert_transcript(t2)
        db_service.insert_transcript(t3)
        
        assert db_service.get_transcript_count_by_method("youtube_api") == 2
        assert db_service.get_transcript_count_by_method("whisper") == 1
        assert db_service.get_transcript_count_by_method("ytdlp_captions") == 0

    def test_get_failed_transcript_count(self, db_service: DatabaseService):
        """Test failed transcript count."""
        t1 = Transcript(video_id="v1", transcript="t1", method=TranscriptMethod.YOUTUBE_API)
        t2 = Transcript(
            video_id="v2", transcript="", method=TranscriptMethod.YOUTUBE_API,
            status=TranscriptStatus.FAILED
        )
        
        db_service.insert_transcript(t1)
        db_service.insert_transcript(t2)
        
        assert db_service.get_failed_transcript_count() == 1


# ============================================================================
# TranscriptService Tests
# ============================================================================

class TestTranscriptService:
    """Test suite for TranscriptService."""

    def test_init(self, db_service: DatabaseService):
        """Test TranscriptService initialization."""
        service = TranscriptService(database_service=db_service)
        assert service.database_service == db_service
        assert service.downloads_dir.exists()

    def test_clean_transcript(self, transcript_service: TranscriptService):
        """Test transcript cleaning."""
        dirty = "  Hello   world  this   is   a   test  "
        clean = transcript_service._clean_transcript(dirty)
        assert clean == "Hello world this is a test"

    def test_clean_transcript_html_entities(self, transcript_service: TranscriptService):
        """Test HTML entity removal."""
        amp = chr(38)  # ampersand character
        dirty = "I&#39;m a test " + amp + "amp; more"
        clean = transcript_service._clean_transcript(dirty)
        assert "&#39;" not in clean
        assert amp + "amp;" not in clean

    def test_clean_transcript_empty(self, transcript_service: TranscriptService):
        """Test cleaning empty text."""
        assert transcript_service._clean_transcript("") == ""
        assert transcript_service._clean_transcript(None) == ""

    @patch('youtube_transcript_api.YouTubeTranscriptApi')
    def test_try_youtube_transcript_api_success(self, mock_api, transcript_service: TranscriptService):
        """Test successful transcript retrieval via youtube-transcript-api."""
        # Mock the transcript list
        mock_transcript_list = MagicMock()
        mock_transcript_data = MagicMock()
        mock_transcript_data.language_code = "en"
        mock_transcript_data.fetch.return_value = [
            {'text': 'Hello', 'start': 0.0, 'duration': 1.0},
            {'text': 'world', 'start': 1.0, 'duration': 1.0},
        ]
        
        mock_transcript_list.find_transcript.return_value = mock_transcript_data
        mock_api.list_transcripts.return_value = mock_transcript_list
        
        result = transcript_service._try_youtube_transcript_api("abc123")
        
        assert result is not None
        assert result.video_id == "abc123"
        assert result.language == "en"
        assert "Hello" in result.transcript
        assert "world" in result.transcript
        assert result.method == TranscriptMethod.YOUTUBE_API
        assert result.status == TranscriptStatus.COMPLETED

    @patch('youtube_transcript_api.YouTubeTranscriptApi')
    def test_try_youtube_transcript_api_no_transcript(self, mock_api, transcript_service: TranscriptService):
        """Test when no transcript is available."""
        from youtube_transcript_api._errors import NoTranscriptFound
        
        mock_api.list_transcripts.side_effect = NoTranscriptFound("abc123", ["en"], {})
        
        result = transcript_service._try_youtube_transcript_api("abc123")
        assert result is None

    @patch('youtube_transcript_api.YouTubeTranscriptApi')
    def test_try_youtube_transcript_api_disabled(self, mock_api, transcript_service: TranscriptService):
        """Test when transcripts are disabled."""
        from youtube_transcript_api._errors import TranscriptsDisabled
        
        mock_api.list_transcripts.side_effect = TranscriptsDisabled("Disabled")
        
        result = transcript_service._try_youtube_transcript_api("abc123")
        assert result is None

    @patch('yt_dlp.YoutubeDL')
    def test_try_ytdlp_captions_no_captions(self, mock_ydl, transcript_service: TranscriptService):
        """Test yt-dlp captions when no captions exist."""
        mock_ydl_instance = MagicMock()
        mock_ydl.return_value.__enter__.return_value = mock_ydl_instance
        
        mock_ydl_instance.extract_info.return_value = {
            'id': 'abc123',
            'subtitles': {},
            'automatic_captions': {}
        }
        
        result = transcript_service._try_ytdlp_captions("abc123")
        assert result is None

    def test_process_video_already_exists(self, db_service: DatabaseService, transcript_service: TranscriptService):
        """Test processing a video that already has a transcript."""
        transcript = Transcript(
            video_id="abc123",
            transcript="test",
            method=TranscriptMethod.YOUTUBE_API
        )
        db_service.insert_transcript(transcript)
        
        success, method = transcript_service.process_video("abc123")
        assert success is True
        assert method == "already_exists"

    def test_save_transcript(self, transcript_service: TranscriptService):
        """Test saving a transcript."""
        transcript = Transcript(
            video_id="test123",
            transcript="test content",
            method=TranscriptMethod.YOUTUBE_API
        )
        
        result = transcript_service.save_transcript(transcript)
        assert result is True
        assert transcript_service.database_service.transcript_exists("test123") is True


# ============================================================================
# TranscriptAgent Tests
# ============================================================================

class TestTranscriptAgent:
    """Test suite for TranscriptAgent."""

    @pytest.fixture
    def mock_services(self):
        """Create mock services for testing."""
        transcript_service = Mock(spec=TranscriptService)
        database_service = Mock(spec=DatabaseService)
        # Add transcript-specific methods to the mock
        database_service.get_videos_without_transcripts = Mock(return_value=[])
        return transcript_service, database_service

    def test_init(self, mock_services):
        """Test TranscriptAgent initialization."""
        transcript_service, database_service = mock_services
        agent = TranscriptAgent(transcript_service, database_service)
        
        assert agent.transcript_service == transcript_service
        assert agent.database_service == database_service
        assert agent.console is not None

    def test_run_no_videos(self, mock_services):
        """Test run when no videos need transcripts."""
        transcript_service, database_service = mock_services
        database_service.get_videos_without_transcripts.return_value = []
        
        agent = TranscriptAgent(transcript_service, database_service)
        with patch.object(agent, '_print_banner'):
            result = agent.run(50)
        
        assert result == (0, 0, 0, 0)

    def test_run_with_videos(self, mock_services):
        """Test run with videos to process."""
        transcript_service, database_service = mock_services
        database_service.get_videos_without_transcripts.return_value = ["v1", "v2", "v3"]
        
        # Mock process_video results
        transcript_service.process_video.side_effect = [
            (True, "youtube_api"),
            (True, "ytdlp_captions"),
            (False, None),
        ]
        
        agent = TranscriptAgent(transcript_service, database_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                result = agent.run(50)
        
        assert result == (1, 1, 0, 1)
        assert transcript_service.process_video.call_count == 3

    def test_run_all_methods(self, mock_services):
        """Test run with all transcript methods represented."""
        transcript_service, database_service = mock_services
        database_service.get_videos_without_transcripts.return_value = ["v1", "v2", "v3", "v4"]
        
        transcript_service.process_video.side_effect = [
            (True, "youtube_api"),
            (True, "ytdlp_captions"),
            (True, "whisper"),
            (False, None),
        ]
        
        agent = TranscriptAgent(transcript_service, database_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                result = agent.run(50)
        
        assert result == (1, 1, 1, 1)

    def test_run_with_already_exists(self, mock_services):
        """Test run with already existing transcripts."""
        transcript_service, database_service = mock_services
        database_service.get_videos_without_transcripts.return_value = ["v1", "v2"]
        
        transcript_service.process_video.side_effect = [
            (True, "already_exists"),
            (True, "youtube_api"),
        ]
        
        agent = TranscriptAgent(transcript_service, database_service)
        with patch.object(agent, '_print_banner'):
            with patch.object(agent, '_print_summary'):
                result = agent.run(50)
        
        assert result == (2, 0, 0, 0)  # both counted as youtube_api


# ============================================================================
# Integration Tests
# ============================================================================

class TestTranscriptIntegration:
    """Integration tests for transcript workflow."""

    def test_full_transcript_workflow_mocked(self, db_service: DatabaseService, temp_db_path: str):
        """Test complete transcript workflow with mocked external APIs."""
        # Insert a video into the database
        from src.models.video import Video
        from datetime import datetime, timezone
        
        video = Video(
            video_id="test_video_1",
            title="Test Video",
            description="Test",
            channel="Test Channel",
            channel_id="UCtest",
            published_at=datetime.now(timezone.utc),
            duration="PT10M",
            view_count=1000,
            like_count=100,
            comment_count=50,
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=test_video_1",
            search_keyword="test"
        )
        db_service.insert_video(video)
        
        # Verify video exists
        assert db_service.video_exists("test_video_1") is True
        
        # Verify no transcript yet
        assert db_service.transcript_exists("test_video_1") is False
        
        # Verify get_videos_without_transcripts returns it
        videos = db_service.get_videos_without_transcripts(10)
        assert "test_video_1" in videos
        
        # Insert a transcript
        transcript = Transcript(
            video_id="test_video_1",
            language="en",
            transcript="This is a test transcript",
            method=TranscriptMethod.YOUTUBE_API
        )
        db_service.insert_transcript(transcript)
        
        # Verify transcript exists
        assert db_service.transcript_exists("test_video_1") is True
        
        # Verify counts
        assert db_service.get_transcript_count() == 1
        assert db_service.get_transcript_count_by_method("youtube_api") == 1
        
        # Verify video no longer appears in "without transcripts" list
        videos = db_service.get_videos_without_transcripts(10)
        assert "test_video_1" not in videos

    def test_transcript_database_schema(self, db_service: DatabaseService, temp_db_path: str):
        """Verify the transcripts table schema is correct."""
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        
        # Check UNIQUE constraint on video_id
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='transcripts'")
        row = cursor.fetchone()
        assert row is not None, "transcripts table not found"
        create_sql = row[0]
        assert "UNIQUE" in create_sql.upper()
        assert "video_id" in create_sql
        
        # Check indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        assert "idx_transcript_video_id" in indexes
        assert "idx_transcript_status" in indexes
        
        conn.close()