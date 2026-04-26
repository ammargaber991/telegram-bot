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
    tag: str | None
    message_count: int
    warns: int
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
                    tag TEXT,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    warns INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            for col, ddl in {
                "tag": "ALTER TABLE users ADD COLUMN tag TEXT",
                "message_count": "ALTER TABLE users ADD COLUMN message_count INTEGER NOT NULL DEFAULT 0",
                "warns": "ALTER TABLE users ADD COLUMN warns INTEGER NOT NULL DEFAULT 0",
            }.items():
                if col not in cols:
                    conn.execute(ddl)

            conn.execute("CREATE TABLE IF NOT EXISTS ranks (telegram_id INTEGER PRIMARY KEY, rank INTEGER NOT NULL, updated_at TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS tags (telegram_id INTEGER PRIMARY KEY, tag TEXT NOT NULL, updated_at TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS permissions (telegram_id INTEGER NOT NULL, permission TEXT NOT NULL, granted_at TEXT NOT NULL, PRIMARY KEY(telegram_id, permission))")
            conn.execute("CREATE TABLE IF NOT EXISTS warns (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL, actor_id INTEGER, reason TEXT, created_at TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER, action TEXT NOT NULL, target_id INTEGER, details TEXT, created_at TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0)")
            conn.execute("CREATE TABLE IF NOT EXISTS settings (chat_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(chat_id, key))")
            conn.execute("CREATE TABLE IF NOT EXISTS filters (chat_id INTEGER NOT NULL, word TEXT NOT NULL, PRIMARY KEY(chat_id, word))")
            conn.execute("CREATE TABLE IF NOT EXISTS member_events (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL, event TEXT NOT NULL, created_at TEXT NOT NULL)")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def upsert_user(self, telegram_id: int, username: str | None, full_name: str, rank: Rank = Rank.MEMBER) -> None:
        now = self._now()
        with self._connect() as conn:
            existing = conn.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO users (telegram_id, username, full_name, rank, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (telegram_id, username, full_name, int(rank), now, now),
                )
            else:
                conn.execute("UPDATE users SET username = ?, full_name = ?, updated_at = ? WHERE telegram_id = ?", (username, full_name, now, telegram_id))

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
                tag=row["tag"],
                message_count=row["message_count"],
                warns=row["warns"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def set_rank(self, telegram_id: int, rank: Rank) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute("UPDATE users SET rank = ?, updated_at = ? WHERE telegram_id = ?", (int(rank), now, telegram_id))
            conn.execute("INSERT INTO ranks (telegram_id, rank, updated_at) VALUES (?, ?, ?) ON CONFLICT(telegram_id) DO UPDATE SET rank=excluded.rank, updated_at=excluded.updated_at", (telegram_id, int(rank), now))

    def set_tag(self, telegram_id: int, tag: str | None) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute("UPDATE users SET tag = ?, updated_at = ? WHERE telegram_id = ?", (tag, now, telegram_id))
            if tag:
                conn.execute("INSERT INTO tags (telegram_id, tag, updated_at) VALUES (?, ?, ?) ON CONFLICT(telegram_id) DO UPDATE SET tag=excluded.tag, updated_at=excluded.updated_at", (telegram_id, tag, now))
            else:
                conn.execute("DELETE FROM tags WHERE telegram_id = ?", (telegram_id,))

    def list_tags(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT telegram_id, tag, updated_at FROM tags ORDER BY updated_at DESC").fetchall()

    def increment_message(self, telegram_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE users SET message_count = message_count + 1, updated_at = ? WHERE telegram_id = ?", (self._now(), telegram_id))


    def grant_permission(self, telegram_id: int, permission: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO permissions (telegram_id, permission, granted_at) VALUES (?, ?, ?)", (telegram_id, permission.lower(), self._now()))

    def revoke_permission(self, telegram_id: int, permission: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM permissions WHERE telegram_id = ? AND permission = ?", (telegram_id, permission.lower()))

    def permissions_of(self, telegram_id: int) -> list[str]:
        with self._connect() as conn:
            return [r["permission"] for r in conn.execute("SELECT permission FROM permissions WHERE telegram_id = ? ORDER BY permission", (telegram_id,)).fetchall()]

    def has_permission(self, telegram_id: int, permission: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM permissions WHERE telegram_id = ? AND permission = ?", (telegram_id, permission.lower())).fetchone()
            return row is not None
    def add_warn(self, telegram_id: int, actor_id: int | None, reason: str | None) -> int:
        with self._connect() as conn:
            conn.execute("INSERT INTO warns (telegram_id, actor_id, reason, created_at) VALUES (?, ?, ?, ?)", (telegram_id, actor_id, reason, self._now()))
            conn.execute("UPDATE users SET warns = warns + 1, updated_at = ? WHERE telegram_id = ?", (self._now(), telegram_id))
            return conn.execute("SELECT COUNT(*) AS c FROM warns WHERE telegram_id = ?", (telegram_id,)).fetchone()["c"]

    def clear_warn(self, telegram_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM warns WHERE telegram_id = ?", (telegram_id,))
            conn.execute("UPDATE users SET warns = 0, updated_at = ? WHERE telegram_id = ?", (self._now(), telegram_id))

    def warns_count(self, telegram_id: int) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS c FROM warns WHERE telegram_id = ?", (telegram_id,)).fetchone()["c"])

    def write_audit(self, actor_id: int | None, action: str, target_id: int | None = None, details: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO logs (actor_id, action, target_id, details, created_at) VALUES (?, ?, ?, ?, ?)", (actor_id, action, target_id, details, self._now()))

    def latest_logs(self, limit: int = 20) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()

    def list_user_ids(self) -> list[int]:
        with self._connect() as conn:
            return [int(row["telegram_id"]) for row in conn.execute("SELECT telegram_id FROM users").fetchall()]

    def top_active(self, limit: int = 10) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT full_name, telegram_id, message_count FROM users ORDER BY message_count DESC LIMIT ?", (limit,)).fetchall()

    def top_admins(self, limit: int = 10) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT full_name, telegram_id, rank FROM users WHERE rank >= ? ORDER BY message_count DESC LIMIT ?", (int(Rank.ADMIN), limit)).fetchall()

    def stats(self) -> dict[str, int]:
        with self._connect() as conn:
            user_count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
            log_count = conn.execute("SELECT COUNT(*) AS c FROM logs").fetchone()["c"]
            warns_count = conn.execute("SELECT COUNT(*) AS c FROM warns").fetchone()["c"]
        return {"users": int(user_count), "logs": int(log_count), "warns": int(warns_count)}


    def record_event(self, telegram_id: int, event: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO member_events (telegram_id, event, created_at) VALUES (?, ?, ?)", (telegram_id, event, self._now()))

    def joins_today(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS c FROM member_events WHERE event = 'join' AND DATE(created_at) = DATE('now')").fetchone()["c"])

    def leaves_today(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS c FROM member_events WHERE event = 'leave' AND DATE(created_at) = DATE('now')").fetchone()["c"])
    def set_setting(self, chat_id: int, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO settings (chat_id, key, value) VALUES (?, ?, ?) ON CONFLICT(chat_id, key) DO UPDATE SET value=excluded.value", (chat_id, key, value))

    def get_setting(self, chat_id: int, key: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE chat_id = ? AND key = ?", (chat_id, key)).fetchone()
            return row["value"] if row else default

    def add_filter(self, chat_id: int, word: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO filters (chat_id, word) VALUES (?, ?)", (chat_id, word.lower()))

    def list_filters(self, chat_id: int) -> list[str]:
        with self._connect() as conn:
            return [row["word"] for row in conn.execute("SELECT word FROM filters WHERE chat_id = ?", (chat_id,)).fetchall()]
