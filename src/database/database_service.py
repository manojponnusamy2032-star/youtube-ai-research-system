"""
Database service for YouTube AI Research System.

This module handles all SQLite database operations including
schema creation, video insertion, and duplicate detection.
"""

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

from src.models.video import Video

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
        
        Creates the videos table with all required fields and indexes
        for optimal query performance.
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        create_table_query = """
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
        
        create_indexes_query = """
        CREATE INDEX IF NOT EXISTS idx_video_id ON videos(video_id);
        CREATE INDEX IF NOT EXISTS idx_search_keyword ON videos(search_keyword);
        CREATE INDEX IF NOT EXISTS idx_channel_id ON videos(channel_id);
        CREATE INDEX IF NOT EXISTS idx_published_at ON videos(published_at);
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(create_table_query)
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
    
    def __enter__(self) -> "DatabaseService":
        """Context manager entry point."""
        self.connect()
        self.create_tables()
        return self
    
    def __exit__(self, exc_type: Optional[type], exc_val: Optional[BaseException], exc_tb: Optional[object]) -> None:
        """Context manager exit point."""
        self.disconnect()