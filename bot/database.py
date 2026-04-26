from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bot.ranks import Rank


@dataclass
class UserRecord:
    telegram_id: int
    username: str | None
    full_name: str
    rank: Rank
    created_at: str
    updated_at: str


class Database:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id INTEGER,
                    action TEXT NOT NULL,
                    target_id INTEGER,
                    details TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def upsert_user(self, telegram_id: int, username: str | None, full_name: str, rank: Rank = Rank.USER) -> None:
        now = self._now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT telegram_id, rank, created_at FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO users (telegram_id, username, full_name, rank, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (telegram_id, username, full_name, int(rank), now, now),
                )
            else:
                conn.execute(
                    """
                    UPDATE users
                    SET username = ?, full_name = ?, updated_at = ?
                    WHERE telegram_id = ?
                    """,
                    (username, full_name, now, telegram_id),
                )

    def get_user(self, telegram_id: int) -> UserRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if row is None:
                return None
            return UserRecord(
                telegram_id=row["telegram_id"],
                username=row["username"],
                full_name=row["full_name"],
                rank=Rank(row["rank"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def set_rank(self, telegram_id: int, rank: Rank) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET rank = ?, updated_at = ? WHERE telegram_id = ?",
                (int(rank), now, telegram_id),
            )

    def write_audit(self, actor_id: int | None, action: str, target_id: int | None = None, details: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (actor_id, action, target_id, details, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (actor_id, action, target_id, details, self._now()),
            )

    def latest_logs(self, limit: int = 20) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()

    def list_user_ids(self) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT telegram_id FROM users").fetchall()
            return [int(row["telegram_id"]) for row in rows]

    def stats(self) -> dict[str, int]:
        with self._connect() as conn:
            user_count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
            log_count = conn.execute("SELECT COUNT(*) AS c FROM audit_logs").fetchone()["c"]
        return {"users": int(user_count), "logs": int(log_count)}
