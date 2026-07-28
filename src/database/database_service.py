"""
Database service for YouTube AI Research System.

This module handles all SQLite database operations including
schema creation, video insertion, transcript storage, and duplicate detection.
"""

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any

from src.models.video import Video
from src.models.transcript import Transcript, TranscriptStatus
from src.models.analysis import Analysis

logger = logging.getLogger(__name__)


class DatabaseService:
    """
    Service for managing SQLite database operations.
    
    Handles database initialization, schema creation, and video metadata storage
    with duplicate detection based on video_id.
    
    Attributes:
        db_path: Path to the SQLite database file
        connection: Active database connection
    """
    
    def __init__(self, db_path: str = "data/database/youtube.db") -> None:
        """
        Initialize the database service.
        
        Args:
            db_path: Path to the SQLite database file (default: data/database/youtube.db)
        """
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None
        self._ensure_database_directory()
    
    def _ensure_database_directory(self) -> None:
        """Create database directory if it doesn't exist."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Database directory ensured at: {db_dir}")
    
    def connect(self) -> None:
        """Establish connection to the SQLite database."""
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row
            logger.info(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def disconnect(self) -> None:
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Database connection closed")
    
    def create_tables(self) -> None:
        """
        Create database tables if they don't exist.
        
        Creates the videos and transcripts tables with all required fields
        and indexes for optimal query performance.
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        create_videos_table = """
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            channel TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            published_at TEXT NOT NULL,
            duration TEXT NOT NULL,
            view_count INTEGER NOT NULL,
            like_count INTEGER NOT NULL,
            comment_count INTEGER NOT NULL,
            thumbnail_url TEXT NOT NULL,
            video_url TEXT NOT NULL,
            search_keyword TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        create_transcripts_table = """
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            language TEXT NOT NULL DEFAULT 'en',
            transcript TEXT NOT NULL,
            method TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES videos(video_id)
        );
        """
        
        create_analysis_table = """
        CREATE TABLE IF NOT EXISTS analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            hook_type TEXT NOT NULL,
            opening_summary TEXT NOT NULL,
            main_topic TEXT NOT NULL,
            sub_topics TEXT NOT NULL,
            target_audience TEXT NOT NULL,
            emotion TEXT NOT NULL,
            story_structure TEXT NOT NULL,
            title_formula TEXT NOT NULL,
            thumbnail_pattern TEXT NOT NULL,
            retention_techniques TEXT NOT NULL,
            cta_type TEXT NOT NULL,
            keywords TEXT NOT NULL,
            psychological_triggers TEXT NOT NULL,
            value_proposition TEXT NOT NULL,
            difficulty_level TEXT NOT NULL,
            estimated_video_style TEXT NOT NULL,
            summary TEXT NOT NULL,
            confidence_score REAL NOT NULL,
            analysis_model TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES videos(video_id)
        );
        """
        
        create_pattern_reports_table = """
        CREATE TABLE IF NOT EXISTS pattern_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            total_videos INTEGER NOT NULL DEFAULT 0,
            average_confidence REAL NOT NULL DEFAULT 0.0,
            json_report TEXT NOT NULL
        );
        """

        create_pattern_statistics_table = """
        CREATE TABLE IF NOT EXISTS pattern_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            pattern TEXT NOT NULL,
            count INTEGER NOT NULL,
            percentage REAL NOT NULL,
            average_views REAL NOT NULL DEFAULT 0.0,
            average_likes REAL NOT NULL DEFAULT 0.0,
            average_comments REAL NOT NULL DEFAULT 0.0
        );
        """

        create_recommendations_table = """
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            reason TEXT NOT NULL,
            supporting_patterns TEXT NOT NULL,
            confidence REAL NOT NULL,
            priority TEXT NOT NULL,
            expected_impact TEXT NOT NULL,
            implementation_steps TEXT NOT NULL,
            example_patterns TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """

        create_indexes_query = """
        CREATE INDEX IF NOT EXISTS idx_video_id ON videos(video_id);
        CREATE INDEX IF NOT EXISTS idx_search_keyword ON videos(search_keyword);
        CREATE INDEX IF NOT EXISTS idx_channel_id ON videos(channel_id);
        CREATE INDEX IF NOT EXISTS idx_published_at ON videos(published_at);
        CREATE INDEX IF NOT EXISTS idx_transcript_video_id ON transcripts(video_id);
        CREATE INDEX IF NOT EXISTS idx_transcript_status ON transcripts(status);
        CREATE INDEX IF NOT EXISTS idx_analysis_video_id ON analysis(video_id);
        CREATE INDEX IF NOT EXISTS idx_analysis_model ON analysis(analysis_model);
        CREATE INDEX IF NOT EXISTS idx_pattern_reports_name ON pattern_reports(report_name);
        CREATE INDEX IF NOT EXISTS idx_pattern_stats_category ON pattern_statistics(category);
        CREATE INDEX IF NOT EXISTS idx_recommendations_category ON recommendations(category);
        CREATE INDEX IF NOT EXISTS idx_recommendations_priority ON recommendations(priority);
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(create_videos_table)
            cursor.execute(create_transcripts_table)
            cursor.execute(create_analysis_table)
            cursor.execute(create_pattern_reports_table)
            cursor.execute(create_pattern_statistics_table)
            cursor.execute(create_recommendations_table)
            cursor.executescript(create_indexes_query)
            self.connection.commit()
            logger.info("Database tables and indexes created successfully")
        except sqlite3.Error as e:
            logger.error(f"Failed to create tables: {e}")
            raise
    
    def insert_video(self, video: Video) -> bool:
        """
        Insert a video into the database.
        
        Args:
            video: Video model instance to insert
            
        Returns:
            True if video was inserted, False if it already exists (duplicate)
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        insert_query = """
        INSERT OR IGNORE INTO videos (
            video_id, title, description, channel, channel_id,
            published_at, duration, view_count, like_count,
            comment_count, thumbnail_url, video_url, search_keyword
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(insert_query, (
                video.video_id,
                video.title,
                video.description,
                video.channel,
                video.channel_id,
                video.published_at.isoformat(),
                video.duration,
                video.view_count,
                video.like_count,
                video.comment_count,
                str(video.thumbnail_url),
                str(video.video_url),
                video.search_keyword
            ))
            self.connection.commit()
            
            if cursor.rowcount > 0:
                logger.debug(f"Inserted video: {video.video_id} - {video.title}")
                return True
            else:
                logger.debug(f"Duplicate video skipped: {video.video_id}")
                return False
                
        except sqlite3.Error as e:
            logger.error(f"Failed to insert video {video.video_id}: {e}")
            self.connection.rollback()
            raise
    
    def insert_videos_batch(self, videos: List[Video]) -> tuple[int, int]:
        """
        Insert multiple videos into the database.
        
        Args:
            videos: List of Video model instances to insert
            
        Returns:
            Tuple of (inserted_count, skipped_count)
        """
        inserted = 0
        skipped = 0
        
        for video in videos:
            try:
                if self.insert_video(video):
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error(f"Failed to insert video {video.video_id}: {e}")
                skipped += 1
        
        return inserted, skipped
    
    def video_exists(self, video_id: str) -> bool:
        """
        Check if a video already exists in the database.
        
        Args:
            video_id: YouTube video ID to check
            
        Returns:
            True if video exists, False otherwise
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = "SELECT COUNT(*) FROM videos WHERE video_id = ?"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (video_id,))
            count = cursor.fetchone()[0]
            return count > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to check video existence: {e}")
            raise
    
    def get_video_count(self) -> int:
        """
        Get total number of videos in the database.
        
        Returns:
            Total count of videos
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = "SELECT COUNT(*) FROM videos"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            count = cursor.fetchone()[0]
            return count
        except sqlite3.Error as e:
            logger.error(f"Failed to get video count: {e}")
            raise
    
    # ------------------------------------------------------------------
    # Transcript operations
    # ------------------------------------------------------------------
    
    def insert_transcript(self, transcript: Transcript) -> bool:
        """
        Insert a transcript into the database.
        
        Args:
            transcript: Transcript model instance to insert
            
        Returns:
            True if inserted, False if duplicate
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        insert_query = """
        INSERT OR IGNORE INTO transcripts (
            video_id, language, transcript, method, status
        ) VALUES (?, ?, ?, ?, ?)
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(insert_query, (
                transcript.video_id,
                transcript.language,
                transcript.transcript,
                transcript.method.value,
                transcript.status.value
            ))
            self.connection.commit()
            
            if cursor.rowcount > 0:
                logger.debug(f"Inserted transcript for video: {transcript.video_id}")
                return True
            else:
                logger.debug(f"Duplicate transcript skipped: {transcript.video_id}")
                return False
                
        except sqlite3.Error as e:
            logger.error(f"Failed to insert transcript for {transcript.video_id}: {e}")
            self.connection.rollback()
            raise
    
    def transcript_exists(self, video_id: str) -> bool:
        """
        Check if a transcript already exists for a video.
        
        Args:
            video_id: YouTube video ID to check
            
        Returns:
            True if transcript exists, False otherwise
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = "SELECT COUNT(*) FROM transcripts WHERE video_id = ?"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (video_id,))
            count = cursor.fetchone()[0]
            return count > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to check transcript existence: {e}")
            raise
    
    def get_videos_without_transcripts(self, limit: int = 50) -> List[str]:
        """
        Get video IDs that don't have transcripts yet.
        
        Args:
            limit: Maximum number of video IDs to return
            
        Returns:
            List of video_id strings
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = """
        SELECT v.video_id FROM videos v
        LEFT JOIN transcripts t ON v.video_id = t.video_id
        WHERE t.video_id IS NULL
        LIMIT ?
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to get videos without transcripts: {e}")
            raise
    
    def get_transcript_count(self) -> int:
        """
        Get total number of transcripts in the database.
        
        Returns:
            Total count of transcripts
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = "SELECT COUNT(*) FROM transcripts"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            count = cursor.fetchone()[0]
            return count
        except sqlite3.Error as e:
            logger.error(f"Failed to get transcript count: {e}")
            raise
    
    def get_transcript_count_by_method(self, method: str) -> int:
        """
        Get count of transcripts retrieved by a specific method.
        
        Args:
            method: Retrieval method name
            
        Returns:
            Count of transcripts with that method
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = "SELECT COUNT(*) FROM transcripts WHERE method = ?"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (method,))
            count = cursor.fetchone()[0]
            return count
        except sqlite3.Error as e:
            logger.error(f"Failed to get transcript count by method: {e}")
            raise
    
    def get_failed_transcript_count(self) -> int:
        """
        Get count of failed transcript attempts.
        
        Returns:
            Count of transcripts with status 'failed'
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = "SELECT COUNT(*) FROM transcripts WHERE status = ?"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (TranscriptStatus.FAILED.value,))
            count = cursor.fetchone()[0]
            return count
        except sqlite3.Error as e:
            logger.error(f"Failed to get failed transcript count: {e}")
            raise
    
    # ------------------------------------------------------------------
    # Analysis operations
    # ------------------------------------------------------------------
    
    def insert_analysis(self, analysis: Analysis) -> bool:
        """
        Insert an analysis result into the database.
        
        Args:
            analysis: Analysis model instance to insert
            
        Returns:
            True if inserted, False if duplicate
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        insert_query = """
        INSERT OR IGNORE INTO analysis (
            video_id, hook_type, opening_summary, main_topic, sub_topics,
            target_audience, emotion, story_structure, title_formula,
            thumbnail_pattern, retention_techniques, cta_type, keywords,
            psychological_triggers, value_proposition, difficulty_level,
            estimated_video_style, summary, confidence_score, analysis_model
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(insert_query, (
                analysis.video_id,
                analysis.hook_type,
                analysis.opening_summary,
                analysis.main_topic,
                str(analysis.sub_topics),
                analysis.target_audience,
                analysis.emotion,
                analysis.story_structure,
                analysis.title_formula,
                analysis.thumbnail_pattern,
                str(analysis.retention_techniques),
                analysis.cta_type,
                str(analysis.keywords),
                str(analysis.psychological_triggers),
                analysis.value_proposition,
                analysis.difficulty_level.value,
                analysis.estimated_video_style,
                analysis.summary,
                analysis.confidence_score,
                analysis.analysis_model
            ))
            self.connection.commit()
            
            if cursor.rowcount > 0:
                logger.debug(f"Inserted analysis for video: {analysis.video_id}")
                return True
            else:
                logger.debug(f"Duplicate analysis skipped: {analysis.video_id}")
                return False
                
        except sqlite3.Error as e:
            logger.error(f"Failed to insert analysis for {analysis.video_id}: {e}")
            self.connection.rollback()
            raise
    
    def analysis_exists(self, video_id: str) -> bool:
        """
        Check if an analysis already exists for a video.
        
        Args:
            video_id: YouTube video ID to check
            
        Returns:
            True if analysis exists, False otherwise
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = "SELECT COUNT(*) FROM analysis WHERE video_id = ?"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (video_id,))
            count = cursor.fetchone()[0]
            return count > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to check analysis existence: {e}")
            raise
    
    def get_videos_without_analysis(self, limit: int = 50) -> List[str]:
        """
        Get video IDs that have transcripts but no analysis yet.
        
        Args:
            limit: Maximum number of video IDs to return
            
        Returns:
            List of video_id strings
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = """
        SELECT t.video_id FROM transcripts t
        LEFT JOIN analysis a ON t.video_id = a.video_id
        WHERE a.video_id IS NULL
        AND t.status = 'completed'
        LIMIT ?
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to get videos without analysis: {e}")
            raise
    
    def get_analysis_count(self) -> int:
        """
        Get total number of analyses in the database.
        
        Returns:
            Total count of analyses
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = "SELECT COUNT(*) FROM analysis"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            count = cursor.fetchone()[0]
            return count
        except sqlite3.Error as e:
            logger.error(f"Failed to get analysis count: {e}")
            raise
    
    def get_analysis_count_by_model(self, model: str) -> int:
        """
        Get count of analyses performed by a specific model.
        
        Args:
            model: Model name
            
        Returns:
            Count of analyses with that model
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = "SELECT COUNT(*) FROM analysis WHERE analysis_model = ?"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (model,))
            count = cursor.fetchone()[0]
            return count
        except sqlite3.Error as e:
            logger.error(f"Failed to get analysis count by model: {e}")
            raise
    
    def get_transcript_by_video_id(self, video_id: str) -> Optional[Transcript]:
        """
        Get a transcript by video ID.
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            Transcript model instance or None if not found
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = "SELECT * FROM transcripts WHERE video_id = ?"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (video_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Convert row to dictionary
            row_dict = dict(row)
            
            return Transcript(
                video_id=row_dict['video_id'],
                language=row_dict['language'],
                transcript=row_dict['transcript'],
                method=TranscriptMethod(row_dict['method']),
                status=TranscriptStatus(row_dict['status']),
                created_at=row_dict.get('created_at')
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to get transcript for {video_id}: {e}")
            raise
    
    # ------------------------------------------------------------------
    # Pattern operations
    # ------------------------------------------------------------------
    
    def insert_pattern_report(
        self,
        report_name: str,
        total_videos: int,
        average_confidence: float,
        json_report: str
    ) -> int:
        """
        Insert a pattern report into the database.
        
        Args:
            report_name: Name of the report
            total_videos: Total number of videos analyzed
            average_confidence: Average confidence score
            json_report: JSON report data as string
            
        Returns:
            ID of the inserted report
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        insert_query = """
        INSERT INTO pattern_reports (
            report_name, total_videos, average_confidence, json_report
        ) VALUES (?, ?, ?, ?)
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(insert_query, (
                report_name,
                total_videos,
                average_confidence,
                json_report
            ))
            self.connection.commit()
            report_id = cursor.lastrowid
            logger.info(f"Inserted pattern report: {report_name} (id: {report_id})")
            return report_id
        except sqlite3.Error as e:
            logger.error(f"Failed to insert pattern report: {e}")
            self.connection.rollback()
            raise
    
    def insert_pattern_statistics(self, statistics: List[Dict[str, Any]]) -> None:
        """
        Insert pattern statistics into the database.
        
        Args:
            statistics: List of statistic dictionaries
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        insert_query = """
        INSERT INTO pattern_statistics (
            category, pattern, count, percentage,
            average_views, average_likes, average_comments
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        
        try:
            cursor = self.connection.cursor()
            for stat in statistics:
                cursor.execute(insert_query, (
                    stat['category'],
                    stat['pattern'],
                    stat['count'],
                    stat['percentage'],
                    stat.get('average_views', 0.0),
                    stat.get('average_likes', 0.0),
                    stat.get('average_comments', 0.0)
                ))
            self.connection.commit()
            logger.info(f"Inserted {len(statistics)} pattern statistics")
        except sqlite3.Error as e:
            logger.error(f"Failed to insert pattern statistics: {e}")
            self.connection.rollback()
            raise
    
    def get_pattern_reports(self) -> List[Dict[str, Any]]:
        """
        Get all pattern reports.
        
        Returns:
            List of report dictionaries
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = "SELECT * FROM pattern_reports ORDER BY created_at DESC"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to get pattern reports: {e}")
            raise
    
    def get_pattern_statistics(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get pattern statistics, optionally filtered by category.
        
        Args:
            category: Category to filter by (optional)
            
        Returns:
            List of statistic dictionaries
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        if category:
            query = "SELECT * FROM pattern_statistics WHERE category = ? ORDER BY count DESC"
            params = (category,)
        else:
            query = "SELECT * FROM pattern_statistics ORDER BY category, count DESC"
            params = ()
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to get pattern statistics: {e}")
            raise
    
    def get_all_analysis_with_video_data(self) -> List[Dict[str, Any]]:
        """
        Get all analysis records joined with video metadata.
        
        Returns:
            List of dictionaries containing analysis and video data
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        query = """
        SELECT 
            a.video_id,
            a.hook_type,
            a.opening_summary,
            a.main_topic,
            a.sub_topics,
            a.target_audience,
            a.emotion,
            a.story_structure,
            a.title_formula,
            a.thumbnail_pattern,
            a.retention_techniques,
            a.cta_type,
            a.keywords,
            a.psychological_triggers,
            a.value_proposition,
            a.difficulty_level,
            a.estimated_video_style,
            a.summary,
            a.confidence_score,
            a.analysis_model,
            v.title,
            v.channel,
            v.view_count,
            v.like_count,
            v.comment_count,
            v.duration
        FROM analysis a
        JOIN videos v ON a.video_id = v.video_id
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to get analysis with video data: {e}")
            raise
    
    def __enter__(self) -> "DatabaseService":
        """Context manager entry point."""
        self.connect()
        self.create_tables()
        return self
    
    def __exit__(self, exc_type: Optional[type], exc_val: Optional[BaseException], exc_tb: Optional[object]) -> None:
        """Context manager exit point."""
        self.disconnect()
