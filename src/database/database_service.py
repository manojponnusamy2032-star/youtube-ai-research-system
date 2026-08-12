"""
Database service for YouTube AI Research System.

This module handles all SQLite database operations including
schema creation, video insertion, transcript storage, and duplicate detection.
"""

import logging
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional, Dict, Any

from src.models.video import Video
from src.models.transcript import Transcript, TranscriptMethod, TranscriptStatus
from src.models.analysis import Analysis

from src.models.idea import Idea

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
        # thread-local storage for per-thread connections
        self._local = threading.local()
        # lock protects creation/teardown of per-thread connections
        self._conn_lock = threading.RLock()
        self._connected = False
        self._ensure_database_directory()
    
    def _ensure_database_directory(self) -> None:
        """Create database directory if it doesn't exist."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Database directory ensured at: {db_dir}")
    
    @property
    def connection(self) -> Optional[sqlite3.Connection]:
        """Return a thread-local sqlite3 connection if connected, else None.

        Connections are created per-thread with check_same_thread=False and
        WAL journaling for safer concurrent readers/writers.
        """
        if not getattr(self, "_connected", False):
            return None
        conn = getattr(self._local, "conn", None)
        if conn is None:
            with self._conn_lock:
                # Re-check inside lock
                conn = getattr(self._local, "conn", None)
                if conn is None:
                    try:
                        # Add a timeout to avoid immediate 'database is locked' failures
                        conn = sqlite3.connect(
                            self.db_path,
                            check_same_thread=False,
                            detect_types=sqlite3.PARSE_DECLTYPES,
                            timeout=30.0,
                        )
                        conn.row_factory = sqlite3.Row
                        # Pragmas for improved concurrency and safety
                        try:
                            conn.execute("PRAGMA journal_mode=WAL;")
                            conn.execute("PRAGMA synchronous=NORMAL;")
                            # Allow some time waiting when DB is busy instead of failing fast
                            conn.execute("PRAGMA busy_timeout = 5000;")
                            # Do not force foreign_keys pragma to preserve backward compatibility with tests and older deployments
                            # conn.execute("PRAGMA foreign_keys = ON;")
                        except sqlite3.Error:
                            # Some SQLite builds may not support these pragmas; ignore failures
                            pass
                        self._local.conn = conn
                        logger.debug("Opened DB connection for thread %s", threading.get_ident())
                    except sqlite3.Error as e:
                        logger.error("Failed to open DB connection for thread %s: %s", threading.get_ident(), e)
                        raise
        return conn

    def connect(self) -> None:
        """Mark service as connected and ensure a connection for the current thread.

        Safe to call from multiple threads; connection creation is guarded by an RLock.
        """
        try:
            with self._conn_lock:
                # create a connection for the current thread
                self._connected = True
                _ = self.connection  # triggers creation
            logger.info(f"Database connected (per-thread connections enabled): {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            self._connected = False
            raise
    
    def disconnect(self) -> None:
        """Close the current thread's database connection and mark as disconnected.

        Note: other threads may still hold connections; they will be closed when those threads exit.
        """
        with self._conn_lock:
            conn = getattr(self._local, "conn", None)
            if conn:
                try:
                    conn.close()
                except sqlite3.Error:
                    logger.exception("Error closing DB connection for thread %s", threading.get_ident())
                finally:
                    self._local.conn = None
            self._connected = False
        logger.info("Database connection closed for current thread and service marked disconnected")
    
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

        create_generated_titles_table = """
        CREATE TABLE IF NOT EXISTS generated_titles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            title TEXT NOT NULL,
            pattern TEXT NOT NULL,
            emotion TEXT NOT NULL,
            formula TEXT NOT NULL,
            estimated_ctr REAL NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """

        create_generated_hooks_table = """
        CREATE TABLE IF NOT EXISTS generated_hooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            hook_type TEXT NOT NULL,
            script TEXT NOT NULL,
            retention_score REAL NOT NULL,
            candidates_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """

        create_generated_thumbnails_table = """
        CREATE TABLE IF NOT EXISTS generated_thumbnails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            concept TEXT NOT NULL,
            layout TEXT NOT NULL,
            text_overlay TEXT NOT NULL,
            color_palette TEXT NOT NULL,
            emotion TEXT NOT NULL,
            image_prompt TEXT NOT NULL,
            thumbnail_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """

        create_generated_scripts_table = """
        CREATE TABLE IF NOT EXISTS generated_scripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            intro TEXT NOT NULL,
            sections_json TEXT NOT NULL,
            cta TEXT NOT NULL,
            estimated_duration_minutes INTEGER NOT NULL,
            script_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """

        create_scripts_table = """
        CREATE TABLE IF NOT EXISTS scripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idea_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            hook TEXT NOT NULL,
            introduction TEXT NOT NULL,
            body TEXT NOT NULL,
            conclusion TEXT NOT NULL,
            call_to_action TEXT NOT NULL,
            estimated_duration INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """

        create_generated_seo_table = """
        CREATE TABLE IF NOT EXISTS generated_seo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            description TEXT NOT NULL,
            keywords_json TEXT NOT NULL,
            hashtags_json TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            chapters_json TEXT NOT NULL,
            seo_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """

        create_content_packages_table = """
        CREATE TABLE IF NOT EXISTS content_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            best_title_json TEXT NOT NULL,
            thumbnail_json TEXT NOT NULL,
            hook_json TEXT NOT NULL,
            script_json TEXT NOT NULL,
            seo_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            package_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """

        create_workflows_table = """
        CREATE TABLE IF NOT EXISTS workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id TEXT UNIQUE NOT NULL,
            workflow_type TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            result_json TEXT,
            error_text TEXT,
            progress_percentage INTEGER DEFAULT 0,
            current_stage TEXT,
            processed_videos INTEGER DEFAULT 0,
            failed_videos INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0,
            timeout_reason TEXT,
            started_at TEXT,
            last_stage_at TEXT,
            duration_seconds REAL DEFAULT 0.0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        );
        """

        create_workflow_logs_table = """
        CREATE TABLE IF NOT EXISTS workflow_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id TEXT NOT NULL,
                    stage TEXT,
                    status TEXT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    error_text TEXT,
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
        CREATE INDEX IF NOT EXISTS idx_generated_titles_topic ON generated_titles(topic);
        CREATE INDEX IF NOT EXISTS idx_generated_hooks_topic ON generated_hooks(topic);
        CREATE INDEX IF NOT EXISTS idx_generated_thumbnails_topic ON generated_thumbnails(topic);
        CREATE INDEX IF NOT EXISTS idx_generated_scripts_topic ON generated_scripts(topic);
        CREATE INDEX IF NOT EXISTS idx_generated_seo_topic ON generated_seo(topic);
        CREATE INDEX IF NOT EXISTS idx_content_packages_topic ON content_packages(topic);
        CREATE INDEX IF NOT EXISTS idx_workflows_workflow_id ON workflows(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status);
        CREATE INDEX IF NOT EXISTS idx_workflow_logs_workflow_id ON workflow_logs(workflow_id);
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(create_videos_table)
            cursor.execute(create_transcripts_table)
            cursor.execute(create_analysis_table)
            cursor.execute(create_pattern_reports_table)
            cursor.execute(create_pattern_statistics_table)
            cursor.execute(create_recommendations_table)
            cursor.execute(create_generated_titles_table)
            cursor.execute(create_generated_hooks_table)
            cursor.execute(create_generated_thumbnails_table)
            cursor.execute(create_generated_scripts_table)
            cursor.execute(create_scripts_table)
            cursor.execute(create_generated_seo_table)
            cursor.execute(create_content_packages_table)
            cursor.execute(create_workflows_table)
            cursor.execute(create_workflow_logs_table)
            cursor.executescript(create_indexes_query)
            self.connection.commit()
            logger.info("Database tables and indexes created successfully")
        except sqlite3.Error as e:
            logger.exception("Failed to create tables: %s", e)
            raise
        # Ensure migrations table exists and record baseline if necessary
        try:
            self._ensure_migrations_table()
        except Exception:
            # Non-fatal: migrations are advisory and should not block startup
            logger.exception("Failed to ensure migrations table after create_tables")

        # Ensure additional workflow columns exist for older DBs
        try:
            self._ensure_workflow_columns()
        except Exception:
            logger.exception("Failed to ensure workflow columns")

    def _ensure_migrations_table(self) -> None:
        """Create schema_migrations table if missing and record baseline state.

        This provides a lightweight migration ledger so future schema changes
        can be applied in a controlled way. If the migrations table is empty
        on first run, record a baseline marker to avoid reapplying initial schema.
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        create_migrations_table = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT
        );
        """
        try:
            with self.transaction() as cur:
                cur.execute(create_migrations_table)
                # If no records exist, insert a baseline record to mark current schema
                cur.execute("SELECT COUNT(*) FROM schema_migrations")
                row = cur.fetchone()
                if row and int(row[0]) == 0:
                    cur.execute(
                        "INSERT INTO schema_migrations (id, applied_at, description) VALUES (?, CURRENT_TIMESTAMP, ?)",
                        ("baseline_2026_08_06", "Initial schema baseline"),
                    )
            logger.info("Ensured schema_migrations table and recorded baseline if needed")
        except sqlite3.Error as e:
            logger.exception("Failed to ensure migrations table: %s", e)
            raise

    def _ensure_workflow_columns(self) -> None:
        """Ensure workflows and workflow_logs tables have new columns required for orchestration.

        Uses PRAGMA table_info to detect missing columns and applies ALTER TABLE ADD COLUMN where needed.
        This keeps existing databases backward compatible while enabling new features.
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        try:
            cursor = self.connection.cursor()
            # workflow columns to ensure
            required = {
                "workflows": {
                    "retry_count": "INTEGER DEFAULT 0",
                    "timeout_reason": "TEXT",
                },
                "workflow_logs": {
                    "stage": "TEXT",
                    "status": "TEXT",
                    "error_text": "TEXT",
                },
            }
            for table, cols in required.items():
                cursor.execute(f"PRAGMA table_info({table})")
                existing = {row[1] for row in cursor.fetchall()}
                for col, col_def in cols.items():
                    if col not in existing:
                        try:
                            logger.info("Adding missing column %s to table %s", col, table)
                            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
                        except sqlite3.Error:
                            # ignore failures to add column (older SQLite, permission issues)
                            logger.exception("Failed to add column %s to %s", col, table)
            self.connection.commit()
        except sqlite3.Error as e:
            logger.exception("Failed to ensure workflow columns: %s", e)
            try:
                self.connection.rollback()
            except Exception:
                pass
            raise

    def apply_migrations(self, migrations: List[Dict[str, Any]]) -> List[str]:
        """Apply a list of migrations.

        Each migration is a dict containing:
          - id: unique migration id
          - description: short description
          - sql: SQL string to execute (or 'up' for multi-statement)

        Returns list of applied migration ids.
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        applied: List[str] = []
        try:
            # Read already applied migrations
            cursor = self.connection.cursor()
            cursor.execute("SELECT id FROM schema_migrations")
            rows = cursor.fetchall()
            seen = {r[0] for r in rows}

            for mig in migrations:
                mid = mig.get("id")
                desc = mig.get("description", "")
                sql = mig.get("sql")
                if mid in seen:
                    logger.debug("Skipping already-applied migration: %s", mid)
                    continue
                logger.info("Applying migration: %s - %s", mid, desc)
                # Apply migration inside transaction
                with self.transaction() as cur:
                    if isinstance(sql, str):
                        # allow multi-statement scripts
                        cur.executescript(sql)
                    else:
                        raise ValueError("Migration 'sql' must be a string containing SQL statements")
                    cur.execute(
                        "INSERT INTO schema_migrations (id, applied_at, description) VALUES (?, CURRENT_TIMESTAMP, ?)",
                        (mid, desc),
                    )
                applied.append(mid)
            return applied
        except sqlite3.Error as e:
            logger.exception("Failed to apply migrations: %s", e)
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

    # ------------------------------------------------------------------
    # Title generation operations
    # ------------------------------------------------------------------

    def insert_generated_titles(self, topic: str, titles: List[Dict[str, Any]]) -> int:
        """
        Insert generated title candidates for a topic.

        Args:
            topic: Topic these titles were generated for
            titles: List of title metadata dictionaries

        Returns:
            Number of inserted rows
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")

        if not titles:
            return 0

        query = """
        INSERT INTO generated_titles (
            topic, title, pattern, emotion, formula, estimated_ctr, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        payload = [
            (
                topic,
                str(item.get("title", "")),
                str(item.get("pattern_used", "")),
                str(item.get("emotion", "")),
                str(item.get("title_formula", "")),
                float(item.get("estimated_ctr", 0.0)),
                float(item.get("confidence", 0.0)),
            )
            for item in titles
        ]

        try:
            cursor = self.connection.cursor()
            cursor.executemany(query, payload)
            self.connection.commit()
            return len(payload)
        except sqlite3.Error as e:
            logger.error(f"Failed to insert generated titles: {e}")
            self.connection.rollback()
            raise

    def get_generated_titles(
        self,
        topic: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch generated titles, optionally filtered by topic.

        Args:
            topic: Topic to filter by
            limit: Max rows to return

        Returns:
            List of generated title rows as dictionaries
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")

        filters = []
        params: list[Any] = []
        if topic:
            filters.append("topic = ?")
            params.append(topic)
        if start_date:
            filters.append("created_at >= ?")
            params.append(start_date)
        if end_date:
            filters.append("created_at <= ?")
            params.append(end_date)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        query = f"SELECT * FROM generated_titles {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to get generated titles: {e}")
            raise

    # ------------------------------------------------------------------
    # Content generation operations
    # ------------------------------------------------------------------

    def insert_generated_hook(
        self,
        topic: str,
        hook: Dict[str, Any],
        candidates: List[Dict[str, Any]],
    ) -> int:
        """Insert generated hook and its candidate set."""
        return self._insert_and_commit(
            """
            INSERT INTO generated_hooks (
                topic, hook_type, script, retention_score, candidates_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                topic,
                str(hook.get("hook_type", "")),
                str(hook.get("script", "")),
                float(hook.get("retention_score", 0.0)),
                json.dumps(candidates),
            ),
        )

    def get_generated_hooks(self, topic: Optional[str] = None, limit: int = 20, offset: int = 0, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve generated hooks with optional filtering and pagination."""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        filters = []
        params: list[Any] = []
        if topic:
            filters.append("topic = ?")
            params.append(topic)
        if start_date:
            filters.append("created_at >= ?")
            params.append(start_date)
        if end_date:
            filters.append("created_at <= ?")
            params.append(end_date)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        query = f"SELECT * FROM generated_hooks {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.exception("Failed to fetch generated hooks: %s", e)
            raise

    def insert_generated_thumbnail(self, topic: str, thumbnail: Dict[str, Any]) -> int:
        """Insert generated thumbnail strategy payload."""
        return self._insert_and_commit(
            """
            INSERT INTO generated_thumbnails (
                topic, concept, layout, text_overlay, color_palette, emotion, image_prompt, thumbnail_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                topic,
                str(thumbnail.get("concept", "")),
                str(thumbnail.get("layout", "")),
                str(thumbnail.get("text", "")),
                json.dumps(list(thumbnail.get("color_palette", []))),
                str(thumbnail.get("emotion", "")),
                str(thumbnail.get("image_prompt", "")),
                json.dumps(thumbnail),
            ),
        )

    def get_generated_thumbnails(self, topic: Optional[str] = None, limit: int = 20, offset: int = 0, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve generated thumbnails with optional filtering and pagination."""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        filters = []
        params: list[Any] = []
        if topic:
            filters.append("topic = ?")
            params.append(topic)
        if start_date:
            filters.append("created_at >= ?")
            params.append(start_date)
        if end_date:
            filters.append("created_at <= ?")
            params.append(end_date)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        query = f"SELECT * FROM generated_thumbnails {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.exception("Failed to fetch generated thumbnails: %s", e)
            raise

    def insert_generated_script(self, topic: str, script: Dict[str, Any]) -> int:
        """Insert generated script payload."""
        return self._insert_and_commit(
            """
            INSERT INTO generated_scripts (
                topic, intro, sections_json, cta, estimated_duration_minutes, script_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                topic,
                str(script.get("intro", "")),
                json.dumps(list(script.get("sections", []))),
                str(script.get("cta", "")),
                int(script.get("estimated_duration_minutes", 0)),
                json.dumps(script),
            ),
        )

    def get_generated_scripts(self, topic: Optional[str] = None, limit: int = 20, offset: int = 0, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve generated scripts with optional filtering and pagination."""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        filters = []
        params: list[Any] = []
        if topic:
            filters.append("topic = ?")
            params.append(topic)
        if start_date:
            filters.append("created_at >= ?")
            params.append(start_date)
        if end_date:
            filters.append("created_at <= ?")
            params.append(end_date)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        query = f"SELECT * FROM generated_scripts {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.exception("Failed to fetch generated scripts: %s", e)
            raise

    def insert_generated_seo(self, topic: str, seo: Dict[str, Any]) -> int:
        """Insert generated SEO payload."""
        return self._insert_and_commit(
            """
            INSERT INTO generated_seo (
                topic, description, keywords_json, hashtags_json, tags_json, chapters_json, seo_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                topic,
                str(seo.get("description", "")),
                json.dumps(list(seo.get("keywords", []))),
                json.dumps(list(seo.get("hashtags", []))),
                json.dumps(list(seo.get("tags", []))),
                json.dumps(list(seo.get("chapters", []))),
                json.dumps(seo),
            ),
        )

    def get_generated_seo(self, topic: Optional[str] = None, limit: int = 20, offset: int = 0, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve generated SEO entries with optional filtering and pagination."""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        filters = []
        params: list[Any] = []
        if topic:
            filters.append("topic = ?")
            params.append(topic)
        if start_date:
            filters.append("created_at >= ?")
            params.append(start_date)
        if end_date:
            filters.append("created_at <= ?")
            params.append(end_date)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        query = f"SELECT * FROM generated_seo {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.exception("Failed to fetch generated seo: %s", e)
            raise

    def insert_content_package(self, package: Dict[str, Any]) -> int:
        """Insert finalized content package payload."""
        return self._insert_and_commit(
            """
            INSERT INTO content_packages (
                topic, best_title_json, thumbnail_json, hook_json, script_json, seo_json, confidence, package_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(package.get("topic", "")),
                json.dumps(package.get("best_title", {})),
                json.dumps(package.get("thumbnail", {})),
                json.dumps(package.get("hook", {})),
                json.dumps(package.get("script", {})),
                json.dumps(package.get("seo", {})),
                float(package.get("confidence", 0.0)),
                json.dumps(package),
            ),
        )

    def get_content_package_count(self) -> int:
        """Return number of generated content packages."""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM content_packages")
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def get_content_packages(self, topic: str | None = None, limit: int = 20, offset: int = 0, sort: str = "desc") -> list[Dict[str, Any]]:
        """Return content packages with optional topic filter, pagination, and sorting by created_at."""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        order = "DESC" if sort.lower() == "desc" else "ASC"
        if topic:
            query = f"SELECT id, topic, best_title_json, package_json, created_at FROM content_packages WHERE topic = ? ORDER BY created_at {order} LIMIT ? OFFSET ?"
            params = (topic, limit, offset)
        else:
            query = f"SELECT id, topic, best_title_json, package_json, created_at FROM content_packages ORDER BY created_at {order} LIMIT ? OFFSET ?"
            params = (limit, offset)
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            results: list[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                try:
                    d["best_title"] = json.loads(d.get("best_title_json") or "null")
                except Exception:
                    d["best_title"] = None
                try:
                    d["package_json"] = json.loads(d.get("package_json") or "null")
                except Exception:
                    d["package_json"] = {}
                results.append({"id": d.get("id"), "topic": d.get("topic"), "best_title": d.get("best_title"), "created_at": d.get("created_at"), "package_json": d.get("package_json")})
            return results
        except sqlite3.Error as e:
            logger.exception("Failed to query content packages: %s", e)
            raise

    def get_content_package_by_id(self, package_id: int) -> Dict[str, Any] | None:
        """Return single content package by primary id."""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        query = "SELECT id, topic, best_title_json, package_json, created_at FROM content_packages WHERE id = ?"
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (package_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["best_title"] = json.loads(d.get("best_title_json") or "null")
            except Exception:
                d["best_title"] = None
            try:
                d["package_json"] = json.loads(d.get("package_json") or "null")
            except Exception:
                d["package_json"] = {}
            return {"id": d.get("id"), "topic": d.get("topic"), "best_title": d.get("best_title"), "created_at": d.get("created_at"), "package_json": d.get("package_json")}
        except sqlite3.Error as e:
            logger.exception("Failed to fetch content package id %s: %s", package_id, e)
            raise

    def create_workflow_record(self, workflow_id: str, workflow_type: str, payload: Dict[str, Any]) -> int:
        """Create a persistent workflow record in the workflows table.

        Args:
            workflow_id: UUID string for the workflow
            workflow_type: logical workflow type (e.g., 'research')
            payload: original payload dict

        Returns:
            inserted row id
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        query = """
        INSERT INTO workflows (workflow_id, workflow_type, status, payload_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        try:
            with self.transaction() as cur:
                cur.execute(query, (workflow_id, workflow_type, "pending", json.dumps(payload)))
                return int(cur.lastrowid)
        except sqlite3.Error as e:
            logger.exception("Failed to create workflow record %s: %s", workflow_id, e)
            raise

    def update_workflow_record(self, workflow_id: str, **changes: Any) -> None:
        """Update fields of an existing workflow record.

        Supported changes: status, result, error, completed_at, progress_percentage, current_stage,
        processed_videos, failed_videos, started_at, last_stage_at, duration_seconds, retry_count, timeout_reason
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        fields = []
        params: list[Any] = []
        mapping = {
            "status": ("status = ?", lambda v: str(v)),
            "result": ("result_json = ?", lambda v: json.dumps(v)),
            "error": ("error_text = ?", lambda v: str(v)),
            "completed_at": ("completed_at = ?", lambda v: str(v)),
            "progress_percentage": ("progress_percentage = ?", lambda v: int(v)),
            "current_stage": ("current_stage = ?", lambda v: str(v)),
            "processed_videos": ("processed_videos = ?", lambda v: int(v)),
            "failed_videos": ("failed_videos = ?", lambda v: int(v)),
            "started_at": ("started_at = ?", lambda v: str(v)),
            "last_stage_at": ("last_stage_at = ?", lambda v: str(v)),
            "duration_seconds": ("duration_seconds = ?", lambda v: float(v)),
            "retry_count": ("retry_count = ?", lambda v: int(v)),
            "timeout_reason": ("timeout_reason = ?", lambda v: str(v)),
        }
        for key, value in changes.items():
            if key in mapping:
                field_sql, conv = mapping[key]
                fields.append(field_sql)
                params.append(conv(value))
        if not fields:
            return
        fields.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE workflows SET {', '.join(fields)} WHERE workflow_id = ?"
        params.append(workflow_id)
        try:
            with self.transaction() as cur:
                cur.execute(query, tuple(params))
        except sqlite3.Error as e:
            logger.exception("Failed to update workflow %s: %s", workflow_id, e)
            raise

    def get_workflow_record(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a workflow record by workflow_id."""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        query = "SELECT * FROM workflows WHERE workflow_id = ?"
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (workflow_id,))
            row = cursor.fetchone()
            if not row:
                return None
            record = dict(row)
            # Parse JSON fields
            if record.get("payload_json"):
                try:
                    record["payload"] = json.loads(record.get("payload_json"))
                except Exception:
                    record["payload"] = record.get("payload_json")
            if record.get("result_json"):
                try:
                    record["result"] = json.loads(record.get("result_json"))
                except Exception:
                    record["result"] = record.get("result_json")
            # Ensure numeric fields are proper types
            for k in ("progress_percentage", "processed_videos", "failed_videos", "retry_count"):
                if k in record and record[k] is not None:
                    try:
                        record[k] = int(record[k])
                    except Exception:
                        pass
            return record
        except sqlite3.Error as e:
            logger.exception("Failed to fetch workflow %s: %s", workflow_id, e)
            raise

    def get_workflow_metrics(self) -> Dict[str, int]:
        """Return aggregate counts for workflows by status."""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM workflows")
            total = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM workflows WHERE status = 'running'")
            running = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM workflows WHERE status = 'completed'")
            completed = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM workflows WHERE status = 'failed'")
            failed = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM workflows WHERE status = 'queued' OR status = 'pending'")
            queued = int(cursor.fetchone()[0])
            return {
                "workflows_total": total,
                "workflows_queued": queued,
                "workflows_running": running,
                "workflows_completed": completed,
                "workflows_failed": failed,
            }
        except sqlite3.Error as e:
            logger.exception("Failed to compute workflow metrics: %s", e)
            raise

    def _execute_with_retry(self, fn, *args, retries: int = 3, backoff: float = 0.1, **kwargs):
        """Execute a database callable with retries on OperationalError (e.g., database is locked).

        fn is a callable that performs DB operations (like cursor.execute) and returns a value.
        """
        attempt = 0
        while True:
            try:
                return fn(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if attempt >= retries:
                    logger.exception("Database operation failed after %s attempts: %s", retries + 1, e)
                    raise
                sleep_time = backoff * (2 ** attempt)
                logger.warning("OperationalError on DB operation, retrying in %.2fs (attempt %d): %s", sleep_time, attempt + 1, e)
                time.sleep(sleep_time)
                attempt += 1

    @contextmanager
    def transaction(self):
        """Context manager for transactions. Commits on success, rolls back on exception.

        Commits are retried on sqlite3.OperationalError with exponential backoff to handle
        transient 'database is locked' errors when multiple threads/processes access SQLite.

        Usage:
            with db.transaction() as cur:
                cur.execute(...)
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        conn = self.connection
        cur = conn.cursor()
        try:
            yield cur
            # commit with retry for transient locking issues
            attempt = 0
            max_attempts = 4
            backoff = 0.05
            while True:
                try:
                    conn.commit()
                    break
                except sqlite3.OperationalError as e:
                    if attempt >= max_attempts - 1:
                        logger.exception("Failed to commit transaction after %d attempts: %s", max_attempts, e)
                        raise
                    sleep_time = backoff * (2 ** attempt)
                    logger.warning("Commit failed due to OperationalError, retrying in %.2fs: %s", sleep_time, e)
                    time.sleep(sleep_time)
                    attempt += 1
        except Exception:
            try:
                conn.rollback()
            except sqlite3.Error:
                logger.exception("Failed to rollback transaction for thread %s", threading.get_ident())
            raise

    def _insert_and_commit(self, query: str, params: tuple[Any, ...]) -> int:
        """Execute an INSERT query and return inserted row id with strong error logging.

        Uses transaction() which provides commit retry semantics and avoids leaving the
        database in an inconsistent state on transient failures.
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        try:
            with self.transaction() as cur:
                # Use execute_with_retry wrapper around the cursor.execute call
                def _exec(q, p):
                    return cur.execute(q, p)

                self._execute_with_retry(_exec, query, params)
                return int(cur.lastrowid)
        except sqlite3.Error as e:
            logger.exception("Failed to execute insert query. Query=%s Params=%s Error=%s", query, params, e)
            raise

    def insert_workflow_log(self, workflow_id: str, level: str, message: str, stage: str | None = None, status: str | None = None, error_text: str | None = None) -> int:
        """Append a log entry for a workflow with optional stage, status, and error information."""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        query = "INSERT INTO workflow_logs (workflow_id, stage, status, level, message, error_text) VALUES (?, ?, ?, ?, ?, ?)"
        try:
            with self.transaction() as cur:
                def _exec(q, p):
                    return cur.execute(q, p)
                self._execute_with_retry(_exec, query, (workflow_id, stage, status, level, message, error_text))
                return int(cur.lastrowid)
        except sqlite3.Error as e:
            logger.exception("Failed to insert workflow log for %s: %s", workflow_id, e)
            raise

    def get_workflow_logs(
        self,
        workflow_id: str,
        limit: int = 500,
        offset: int = 0,
        stage: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return workflow logs ordered by id ascending with optional filters and pagination.

        Args:
            workflow_id: workflow identifier
            limit: max rows to return
            offset: row offset
            stage: optional stage name to filter
            start_date: inclusive lower bound for created_at (ISO format)
            end_date: inclusive upper bound for created_at (ISO format)
        """
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        base_query = "SELECT workflow_id, stage, status, level, message, error_text, created_at FROM workflow_logs WHERE workflow_id = ?"
        params: List[Any] = [workflow_id]
        if stage:
            base_query += " AND stage = ?"
            params.append(stage)
        if start_date:
            base_query += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            base_query += " AND created_at <= ?"
            params.append(end_date)
        base_query += " ORDER BY id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        try:
            cursor = self.connection.cursor()
            # Use execute_with_retry for robust reads in highly contested DBs
            def _exec(q, p):
                return cursor.execute(q, p)
            self._execute_with_retry(_exec, base_query, tuple(params))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.exception("Failed to read workflow logs for %s: %s", workflow_id, e)
            raise
    
    def __enter__(self) -> "DatabaseService":
        """Context manager entry point."""
        self.connect()
        self.create_tables()
        return self

    def get_workflows_by_status(self, statuses: List[str]) -> List[Dict[str, Any]]:
        """Return workflows matching any of the provided statuses (safe for resume)."""
        if not self.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        placeholders = ",".join(["?" for _ in statuses])
        query = f"SELECT * FROM workflows WHERE status IN ({placeholders}) ORDER BY created_at ASC"
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, tuple(statuses))
            rows = cursor.fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                d = dict(row)
                if d.get("payload_json"):
                    try:
                        d["payload"] = json.loads(d.get("payload_json"))
                    except Exception:
                        d["payload"] = d.get("payload_json")
                results.append(d)
            return results
        except sqlite3.Error as e:
            logger.exception("Failed to query workflows by status %s: %s", statuses, e)
            raise
    
    def __exit__(self, exc_type: Optional[type], exc_val: Optional[BaseException], exc_tb: Optional[object]) -> None:
        """Context manager exit point."""
        self.disconnect()

    def insert_idea(self, idea: Idea) -> int:
        """
        Insert a generated idea.

        Args:
            idea: Idea to store

        Returns:
            Inserted row ID.
        """

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO ideas (
                title,
                hook,
                emotion,
                topic,
                virality_score,
                confidence_score,
                source_pattern_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                idea.title,
                idea.hook,
                idea.emotion,
                idea.topic,
                idea.virality_score,
                idea.confidence_score,
                idea.source_pattern_id,
            ),
        )

        self.connection.commit()

        return cursor.lastrowid


    def get_top_ideas(
        self,
        limit: int = 10,
    ) -> list[Idea]:
        """
        Return the highest virality ideas.
        """

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                title,
                hook,
                emotion,
                topic,
                virality_score,
                confidence_score,
                source_pattern_id,
                created_at
            FROM ideas
            ORDER BY virality_score DESC,
                     confidence_score DESC
            LIMIT ?
            """,
            (limit,),
        )

        rows = cursor.fetchall()

        return [Idea.model_validate(dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # Script operations
    # ------------------------------------------------------------------

    def insert_script(self, script) -> int:
        """
        Insert a generated script.

        Returns:
            Inserted script id.
        """

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO scripts (
                idea_id,
                title,
                hook,
                introduction,
                body,
                conclusion,
                call_to_action,
                estimated_duration
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                script.idea_id,
                script.title,
                script.hook,
                script.introduction,
                script.body,
                script.conclusion,
                script.call_to_action,
                script.estimated_duration,
            ),
        )

        self.connection.commit()

        return cursor.lastrowid


    def script_exists(self, idea_id: int) -> bool:
        """
        Check whether a script already exists for an idea.
        """

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM scripts
            WHERE idea_id = ?
            """,
            (idea_id,),
        )

        return cursor.fetchone()[0] > 0


    def get_pending_ideas(
        self,
        limit: int = 10,
    ):
        """
        Return ideas that don't yet have scripts.
        """

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT i.*
            FROM ideas i
            LEFT JOIN scripts s
                ON i.id = s.idea_id
            WHERE s.id IS NULL
            ORDER BY i.virality_score DESC,
                    i.confidence_score DESC
            LIMIT ?
            """,
            (limit,),
        )

        rows = cursor.fetchall()

        return [Idea.model_validate(dict(row)) for row in rows]


    def get_script_count(self) -> int:
        """
        Total generated scripts.
        """

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM scripts
            """
        )

        return cursor.fetchone()[0]