"""SQLite database layer with WAL mode for concurrent access."""
import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from endstone_architect.models import BuildArea, BuildSession


class ArchitectDatabase:
    """SQLite database for areas and sessions."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._closed = False
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _ensure_connection(self):
        """Ensure database connection is open, reconnect if needed."""
        if self._closed:
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
            self._closed = False

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS areas (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                dimension TEXT NOT NULL,
                min_x INTEGER, min_y INTEGER, min_z INTEGER,
                max_x INTEGER, max_y INTEGER, max_z INTEGER,
                enabled INTEGER DEFAULT 1,
                required_tags TEXT,
                tag_mode TEXT DEFAULT 'ANY',
                blocked_items TEXT,
                given_items TEXT
            );
            
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT,
                player_xuid TEXT,
                area_id TEXT,
                access_type TEXT,
                tag_used TEXT,
                start_time REAL,
                end_time REAL,
                close_reason TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_sessions_area ON sessions(area_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_player ON sessions(player_xuid);
        """)
        self.conn.commit()
        
        # Migration: Add given_items column if it doesn't exist (for existing databases)
        try:
            self.conn.execute("ALTER TABLE areas ADD COLUMN given_items TEXT")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

    def save_area(self, area: BuildArea) -> None:
        """Insert or update an area."""
        self._ensure_connection()
        self.conn.execute("""
            INSERT OR REPLACE INTO areas 
            (id, type, dimension, min_x, min_y, min_z, max_x, max_y, max_z, 
             enabled, required_tags, tag_mode, blocked_items, given_items)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            area.id, area.type, area.dimension,
            area.min_x, area.min_y, area.min_z,
            area.max_x, area.max_y, area.max_z,
            1 if area.enabled else 0,
            json.dumps(area.required_tags),
            area.tag_mode,
            json.dumps(area.blocked_items),
            json.dumps(area.given_items)
        ))
        self.conn.commit()

    def get_area(self, area_id: str) -> Optional[BuildArea]:
        """Get a single area by ID."""
        self._ensure_connection()
        row = self.conn.execute(
            "SELECT * FROM areas WHERE id = ?", (area_id,)
        ).fetchone()
        return self._row_to_area(row) if row else None

    def get_all_areas(self) -> List[BuildArea]:
        """Get all areas."""
        self._ensure_connection()
        rows = self.conn.execute("SELECT * FROM areas").fetchall()
        return [self._row_to_area(row) for row in rows]

    def delete_area(self, area_id: str) -> None:
        """Delete an area by ID."""
        self._ensure_connection()
        self.conn.execute("DELETE FROM areas WHERE id = ?", (area_id,))
        self.conn.commit()

    def _row_to_area(self, row: sqlite3.Row) -> BuildArea:
        # Handle missing given_items column for backwards compatibility
        given_items = []
        try:
            given_items = json.loads(row["given_items"] or "[]")
        except (KeyError, TypeError):
            pass
        
        return BuildArea(
            id=row["id"],
            type=row["type"],
            dimension=row["dimension"],
            min_x=row["min_x"],
            min_y=row["min_y"],
            min_z=row["min_z"],
            max_x=row["max_x"],
            max_y=row["max_y"],
            max_z=row["max_z"],
            enabled=bool(row["enabled"]),
            required_tags=json.loads(row["required_tags"] or "[]"),
            tag_mode=row["tag_mode"],
            blocked_items=json.loads(row["blocked_items"] or "[]"),
            given_items=given_items
        )

    def save_session(self, session: BuildSession) -> None:
        """Save a build session."""
        self._ensure_connection()
        self.conn.execute("""
            INSERT INTO sessions 
            (player_name, player_xuid, area_id, access_type, tag_used, 
             start_time, end_time, close_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.player_name, session.player_xuid, session.area_id,
            session.access_type, session.tag_used, session.start_time,
            session.end_time, session.close_reason
        ))
        self.conn.commit()

    def get_recent_sessions(self, limit: int = 100) -> List[dict]:
        """Get recent sessions as dictionaries."""
        self._ensure_connection()
        rows = self.conn.execute(
            "SELECT * FROM sessions ORDER BY start_time DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self):
        """Close database connection."""
        self._closed = True
        self.conn.close()
