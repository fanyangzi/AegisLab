"""Small SQLite repository with no ORM dependency.

Reviews are stored as an auditable JSON snapshot. Keeping the snapshot in one
row makes the offline demo deterministic and leaves room for a later event
store without coupling the domain models to SQLAlchemy.
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _dump(model: Any) -> Dict[str, Any]:
    value = model.model_dump() if hasattr(model, "model_dump") else model.dict()
    return value


def _json(value: Any) -> str:
    return json.dumps(value, default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item), ensure_ascii=False)


def _load(value: str) -> Dict[str, Any]:
    return json.loads(value)


class SQLiteRepository:
    def __init__(self, path: Optional[str] = None):
        configured = path or os.getenv("LABSAFETY_DB_PATH", "backend/aegislab.db")
        self.path = str(Path(configured).expanduser())
        self._memory_connection: Optional[sqlite3.Connection] = None
        if self.path == ":memory:":
            self._memory_connection = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_connection.row_factory = sqlite3.Row
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            return self._memory_connection
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reviews_updated ON reviews(updated_at DESC);
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_entity ON audit_events(entity_type, entity_id, id DESC);
                """
            )

    def save_review(self, review: Any) -> None:
        data = _dump(review)
        now = data["updated_at"]
        created = data["created_at"]
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO reviews(id,status,title,payload,created_at,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET status=excluded.status,title=excluded.title,
                     payload=excluded.payload,updated_at=excluded.updated_at""",
                (data["id"], data["status"], data["title"], _json(data), str(created), str(now)),
            )

    def get_review(self, review_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM reviews WHERE id=?", (review_id,)).fetchone()
        return _load(row["payload"]) if row else None

    def list_reviews(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM reviews ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [_load(row["payload"]) for row in rows]

    def save_incident(self, drill: Any) -> None:
        data = _dump(drill)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO incidents(id,status,name,payload,created_at) VALUES(?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET status=excluded.status,name=excluded.name,payload=excluded.payload""",
                (data["id"], data["status"], data["name"], _json(data), str(data["created_at"])),
            )

    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM incidents WHERE id=?", (incident_id,)).fetchone()
        return _load(row["payload"]) if row else None

    def list_incidents(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM incidents ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [_load(row["payload"]) for row in rows]

    def add_event(self, entity_type: str, entity_id: str, event_type: str, actor: str, payload: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_events(entity_type,entity_id,event_type,actor,payload,created_at) VALUES(?,?,?,?,?,datetime('now'))",
                (entity_type, entity_id, event_type, actor, _json(payload)),
            )

    def list_events(self, entity_type: str, entity_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id,event_type,actor,payload,created_at FROM audit_events WHERE entity_type=? AND entity_id=? ORDER BY id ASC",
                (entity_type, entity_id),
            ).fetchall()
        return [
            {"id": row["id"], "event_type": row["event_type"], "actor": row["actor"], "payload": _load(row["payload"]), "created_at": row["created_at"]}
            for row in rows
        ]

    def ping(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False
