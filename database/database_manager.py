"""
database.py

Handles all SQLite database operations for the YouTube Research Agent.

Current responsibilities:
1. Connect to the database
2. Create the videos table (if it doesn't exist)
"""

import sqlite3
from config import DATABASE_PATH 
from datetime import datetime
from models import Video, Channel



def get_connection():
    """
    Create and return a connection to the SQLite database.
    Creates the database folder automatically if needed.
    """
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DATABASE_PATH)

    # Allows accessing columns by name instead of index
    conn.row_factory = sqlite3.Row

    return conn


def create_tables():
    """
    Create all database tables required by the project.
    Safe to run multiple times.
    """

    conn = get_connection()
    cursor = conn.cursor()

    # ============================
    # CHANNELS TABLE
    # ============================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS channels (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        channel_id TEXT UNIQUE NOT NULL,

        channel_name TEXT,

        channel_url TEXT,

        subscriber_count INTEGER,

        total_videos INTEGER,

        verified INTEGER,

        country TEXT,

        description TEXT,

        collected_at TEXT

    );
    """)

    # ============================
    # VIDEOS TABLE
    # ============================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS videos (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        youtube_video_id TEXT UNIQUE NOT NULL,

        title TEXT NOT NULL,

        channel_id TEXT,

        views INTEGER,

        duration INTEGER,

        upload_date TEXT,

        thumbnail_url TEXT,

        video_url TEXT,

        search_keyword TEXT,

        collected_at TEXT,

        FOREIGN KEY(channel_id)
            REFERENCES channels(channel_id)

    );
    """)

    conn.commit()
    conn.close()

    print("✅ Database initialized successfully.")


def insert_video(video  : Video):
    """
    Insert a video into the database.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR IGNORE INTO videos (

        youtube_video_id,
        title,
        channel_id,
        views,
        duration,
        upload_date,
        thumbnail_url,
        video_url,
        search_keyword,
        collected_at

    )

    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

    """, (

        

        video.youtube_video_id,
        video.title,
        video.channel_id,
        video.views,
        video.duration,
        video.upload_date,
        video.thumbnail_url,
        video.video_url,
        video.search_keyword,
        video.collected_at

    ))

    conn.commit()
    conn.close()

def video_exists(youtube_video_id):
    """
    Check whether a video already exists in the database.
    Returns True if found, otherwise False.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM videos WHERE youtube_video_id = ?",
        (youtube_video_id,)
    )

    exists = cursor.fetchone() is not None

    conn.close()

    return exists


def get_all_videos():
    """
    Return all videos from the database as a list of dictionaries.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM videos")

    rows = cursor.fetchall()

    conn.close()

    # Convert sqlite rows to normal Python dictionaries
    return [dict(row) for row in rows]


def insert_channel(channel):
    """
    Insert a channel if it doesn't already exist.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR IGNORE INTO channels (

        channel_id,
        channel_name,
        channel_url,
        subscriber_count,
        total_videos,
        verified,
        country,
        description,
        collected_at

    )

    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

    """, (



        channel.channel_id,
        channel.name,
        f"https://www.youtube.com/channel/{channel.channel_id}",
        None,
        None,
        None,
        None,
        None,
        datetime.now().isoformat()

    ))

    conn.commit()
    conn.close()


