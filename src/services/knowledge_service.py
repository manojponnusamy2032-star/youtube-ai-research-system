"""Service layer for storing and querying reusable viral knowledge entries."""

from __future__ import annotations

import sqlite3
from typing import Any

from src.database.database_service import DatabaseService
from src.models.knowledge import KnowledgeEntry


class KnowledgeService:
    """Persist and query normalized pattern knowledge in SQLite."""

    def __init__(self, database_service: DatabaseService) -> None:
        self.database_service = database_service
        self._ensure_table()

    def save_entry(self, entry: KnowledgeEntry) -> int:
        """Save one knowledge entry and return inserted row id."""
        connection = self._connection()
        query = """
        INSERT INTO knowledge (
            category, pattern, frequency, average_views, confidence, recommendation
        ) VALUES (?, ?, ?, ?, ?, ?)
        """
        cursor = connection.cursor()
        cursor.execute(
            query,
            (
                entry.category,
                entry.pattern,
                entry.frequency,
                entry.average_views,
                entry.confidence,
                entry.recommendation,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)

    def save_many(self, entries: list[KnowledgeEntry]) -> int:
        """Save multiple knowledge entries in one transaction."""
        if not entries:
            return 0
        connection = self._connection()
        query = """
        INSERT INTO knowledge (
            category, pattern, frequency, average_views, confidence, recommendation
        ) VALUES (?, ?, ?, ?, ?, ?)
        """
        payload = [
            (
                item.category,
                item.pattern,
                item.frequency,
                item.average_views,
                item.confidence,
                item.recommendation,
            )
            for item in entries
        ]
        connection.cursor().executemany(query, payload)
        connection.commit()
        return len(entries)

    def get_by_category(self, category: str) -> list[KnowledgeEntry]:
        """Fetch entries for a specific category sorted by confidence."""
        query = """
        SELECT * FROM knowledge
        WHERE category = ?
        ORDER BY confidence DESC, frequency DESC
        """
        rows = self._fetch_rows(query, (category,))
        return [self._to_entry(row) for row in rows]

    def get_best_patterns(self, limit: int = 10) -> list[KnowledgeEntry]:
        """Get highest confidence patterns across all categories."""
        query = """
        SELECT * FROM knowledge
        ORDER BY confidence DESC, frequency DESC, average_views DESC
        LIMIT ?
        """
        rows = self._fetch_rows(query, (limit,))
        return [self._to_entry(row) for row in rows]

    def search(self, query_text: str, limit: int = 20) -> list[KnowledgeEntry]:
        """Search entries by pattern or recommendation text."""
        query = """
        SELECT * FROM knowledge
        WHERE pattern LIKE ? OR recommendation LIKE ?
        ORDER BY confidence DESC, frequency DESC
        LIMIT ?
        """
        like = f"%{query_text}%"
        rows = self._fetch_rows(query, (like, like, limit))
        return [self._to_entry(row) for row in rows]

    def _ensure_table(self) -> None:
        """Create knowledge table if it does not exist."""
        connection = self._connection()
        query = """
        CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            pattern TEXT NOT NULL,
            frequency REAL NOT NULL,
            average_views REAL NOT NULL DEFAULT 0,
            confidence REAL NOT NULL,
            recommendation TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
        connection.cursor().execute(query)
        connection.commit()

    def _fetch_rows(self, query: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        """Execute a read query and return all rows."""
        cursor = self._connection().cursor()
        cursor.execute(query, params)
        return cursor.fetchall()

    def _connection(self) -> sqlite3.Connection:
        """Return active SQLite connection or raise if disconnected."""
        if not self.database_service.connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self.database_service.connection

    def _to_entry(self, row: sqlite3.Row) -> KnowledgeEntry:
        """Map sqlite row to KnowledgeEntry model."""
        return KnowledgeEntry(
            id=int(row["id"]),
            category=str(row["category"]),
            pattern=str(row["pattern"]),
            frequency=float(row["frequency"]),
            average_views=float(row["average_views"]),
            confidence=float(row["confidence"]),
            recommendation=str(row["recommendation"]),
            created_at=str(row["created_at"]) if row["created_at"] else None,
        )
