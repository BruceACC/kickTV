"""
KickTV — Database Layer

Async SQLite database with aiosqlite.
Handles all persistence: videos, history, errors, stats, settings.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from app.config import settings


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or settings.abs_database_path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Open database connection and initialize schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._init_schema()

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        """Get active database connection."""
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db

    # ── Schema ──────────────────────────────────────────────

    async def _init_schema(self) -> None:
        """Create all tables if they don't exist."""
        await self.db.executescript("""
            CREATE TABLE IF NOT EXISTS videos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id    TEXT UNIQUE,
                url         TEXT NOT NULL,
                title       TEXT DEFAULT 'Untitled',
                duration    INTEGER DEFAULT 0,
                author      TEXT DEFAULT 'Unknown',
                category    TEXT DEFAULT 'curiosidades',
                provider    TEXT DEFAULT 'local',
                thumbnail   TEXT DEFAULT '',
                description TEXT DEFAULT '',
                license     TEXT DEFAULT '',
                is_valid    INTEGER DEFAULT 1,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS play_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id    TEXT NOT NULL,
                url         TEXT NOT NULL,
                title       TEXT DEFAULT '',
                author      TEXT DEFAULT '',
                category    TEXT DEFAULT '',
                provider    TEXT DEFAULT '',
                duration    INTEGER DEFAULT 0,
                played_at   TEXT DEFAULT (datetime('now')),
                play_duration INTEGER DEFAULT 0,
                completed   INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS errors (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source      TEXT DEFAULT 'app',
                error_type  TEXT DEFAULT '',
                message     TEXT NOT NULL,
                details     TEXT DEFAULT '',
                video_url   TEXT DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS stats (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                cpu_percent REAL DEFAULT 0,
                ram_percent REAL DEFAULT 0,
                fps         REAL DEFAULT 0,
                bitrate     TEXT DEFAULT '0k',
                frames_dropped INTEGER DEFAULT 0,
                queue_size  INTEGER DEFAULT 0,
                recorded_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS providers (
                name        TEXT PRIMARY KEY,
                enabled     INTEGER DEFAULT 1,
                videos_served INTEGER DEFAULT 0,
                errors      INTEGER DEFAULT 0,
                last_used   TEXT DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS categories (
                name        TEXT PRIMARY KEY,
                enabled     INTEGER DEFAULT 1,
                weight      REAL DEFAULT 1.0,
                keywords    TEXT DEFAULT '[]'
            );

            CREATE INDEX IF NOT EXISTS idx_play_history_video_id ON play_history(video_id);
            CREATE INDEX IF NOT EXISTS idx_play_history_played_at ON play_history(played_at);
            CREATE INDEX IF NOT EXISTS idx_videos_provider ON videos(provider);
            CREATE INDEX IF NOT EXISTS idx_errors_created_at ON errors(created_at);
        """)
        await self.db.commit()
        await self._seed_defaults()

    async def _seed_defaults(self) -> None:
        """Insert default categories and provider configs."""
        default_categories = [
            ("terror", 1, 1.0, '["horror", "scary", "creepy", "haunted"]'),
            ("curiosidades", 1, 1.0, '["curiosities", "facts", "interesting", "amazing"]'),
            ("documentales", 1, 1.0, '["documentary", "documental", "investigation"]'),
            ("naturaleza", 1, 1.0, '["nature", "landscape", "forest", "ocean", "mountain"]'),
            ("animales", 1, 1.0, '["animals", "wildlife", "pets", "dogs", "cats"]'),
            ("gaming", 1, 1.0, '["gaming", "videogames", "gameplay", "esports"]'),
            ("tecnología", 1, 1.0, '["technology", "tech", "gadgets", "AI", "programming"]'),
            ("espacio", 1, 1.0, '["space", "universe", "NASA", "planets", "astronomy"]'),
            ("películas clásicas", 1, 1.0, '["classic film", "public domain movie", "vintage film"]'),
            ("memes", 1, 1.0, '["memes", "funny", "humor", "comedy", "viral"]'),
            ("shorts", 1, 1.0, '["short", "clip", "vine", "tiktok"]'),
            ("trailers", 1, 1.0, '["trailer", "movie trailer", "game trailer", "teaser"]'),
            ("ciencia", 1, 1.0, '["science", "physics", "chemistry", "biology", "experiment"]'),
        ]
        for name, enabled, weight, keywords in default_categories:
            await self.db.execute(
                "INSERT OR IGNORE INTO categories (name, enabled, weight, keywords) VALUES (?, ?, ?, ?)",
                (name, enabled, weight, keywords),
            )

        default_providers = ["local", "pexels", "pixabay", "archive", "youtube", "reddit"]
        for provider in default_providers:
            await self.db.execute(
                "INSERT OR IGNORE INTO providers (name, enabled) VALUES (?, 1)",
                (provider,),
            )
        await self.db.commit()

    # ── Video CRUD ──────────────────────────────────────────

    async def save_video(self, video_data: dict[str, Any]) -> int:
        """Save or update a video record. Returns row id."""
        video_id = video_data.get("video_id", "")
        existing = await self.db.execute_fetchall(
            "SELECT id FROM videos WHERE video_id = ?", (video_id,)
        )
        if existing:
            await self.db.execute(
                """UPDATE videos SET url=?, title=?, duration=?, author=?,
                   category=?, provider=?, thumbnail=?, updated_at=datetime('now')
                   WHERE video_id=?""",
                (
                    video_data.get("url", ""),
                    video_data.get("title", "Untitled"),
                    video_data.get("duration", 0),
                    video_data.get("author", "Unknown"),
                    video_data.get("category", "curiosidades"),
                    video_data.get("provider", "local"),
                    video_data.get("thumbnail", ""),
                    video_id,
                ),
            )
            await self.db.commit()
            return existing[0][0]
        else:
            cursor = await self.db.execute(
                """INSERT INTO videos (video_id, url, title, duration, author,
                   category, provider, thumbnail, description, license)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    video_id,
                    video_data.get("url", ""),
                    video_data.get("title", "Untitled"),
                    video_data.get("duration", 0),
                    video_data.get("author", "Unknown"),
                    video_data.get("category", "curiosidades"),
                    video_data.get("provider", "local"),
                    video_data.get("thumbnail", ""),
                    video_data.get("description", ""),
                    video_data.get("license", ""),
                ),
            )
            await self.db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    async def mark_video_invalid(self, video_id: str) -> None:
        """Mark a video as invalid (won't be queued again)."""
        await self.db.execute(
            "UPDATE videos SET is_valid = 0 WHERE video_id = ?", (video_id,)
        )
        await self.db.commit()

    # ── History ─────────────────────────────────────────────

    async def add_to_history(self, video_data: dict[str, Any]) -> None:
        """Record a played video in history."""
        await self.db.execute(
            """INSERT INTO play_history
               (video_id, url, title, author, category, provider, duration, completed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                video_data.get("video_id", ""),
                video_data.get("url", ""),
                video_data.get("title", ""),
                video_data.get("author", ""),
                video_data.get("category", ""),
                video_data.get("provider", ""),
                video_data.get("duration", 0),
                video_data.get("completed", 0),
            ),
        )
        await self.db.commit()

    async def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Get play history, most recent first."""
        rows = await self.db.execute_fetchall(
            "SELECT * FROM play_history ORDER BY played_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(row) for row in rows]

    async def get_recent_video_ids(self, limit: int = 500) -> set[str]:
        """Get set of recently played video IDs to avoid repeats."""
        rows = await self.db.execute_fetchall(
            "SELECT DISTINCT video_id FROM play_history ORDER BY played_at DESC LIMIT ?",
            (limit,),
        )
        return {row[0] for row in rows}

    async def get_last_author(self) -> str:
        """Get the author of the last played video."""
        rows = await self.db.execute_fetchall(
            "SELECT author FROM play_history ORDER BY played_at DESC LIMIT 1"
        )
        return rows[0][0] if rows else ""

    async def get_last_category(self) -> str:
        """Get the category of the last played video."""
        rows = await self.db.execute_fetchall(
            "SELECT category FROM play_history ORDER BY played_at DESC LIMIT 1"
        )
        return rows[0][0] if rows else ""

    async def get_history_count(self) -> int:
        """Total number of plays."""
        rows = await self.db.execute_fetchall("SELECT COUNT(*) FROM play_history")
        return rows[0][0]

    # ── Errors ──────────────────────────────────────────────

    async def log_error(
        self,
        message: str,
        source: str = "app",
        error_type: str = "",
        details: str = "",
        video_url: str = "",
    ) -> None:
        """Record an error event."""
        await self.db.execute(
            """INSERT INTO errors (source, error_type, message, details, video_url)
               VALUES (?, ?, ?, ?, ?)""",
            (source, error_type, message, details, video_url),
        )
        await self.db.commit()

    async def get_errors(self, limit: int = 50) -> list[dict]:
        """Get recent errors."""
        rows = await self.db.execute_fetchall(
            "SELECT * FROM errors ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in rows]

    async def get_error_count(self) -> int:
        """Total number of recorded errors."""
        rows = await self.db.execute_fetchall("SELECT COUNT(*) FROM errors")
        return rows[0][0]

    # ── Settings ────────────────────────────────────────────

    async def get_setting(self, key: str, default: str = "") -> str:
        """Get a setting value."""
        rows = await self.db.execute_fetchall(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        return rows[0][0] if rows else default

    async def set_setting(self, key: str, value: str) -> None:
        """Set a setting value."""
        await self.db.execute(
            """INSERT INTO settings (key, value, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET value=?, updated_at=datetime('now')""",
            (key, value, value),
        )
        await self.db.commit()

    # ── Stats ───────────────────────────────────────────────

    async def record_stats(self, stats: dict[str, Any]) -> None:
        """Record system stats snapshot."""
        await self.db.execute(
            """INSERT INTO stats (cpu_percent, ram_percent, fps, bitrate,
               frames_dropped, queue_size) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                stats.get("cpu_percent", 0),
                stats.get("ram_percent", 0),
                stats.get("fps", 0),
                stats.get("bitrate", "0k"),
                stats.get("frames_dropped", 0),
                stats.get("queue_size", 0),
            ),
        )
        await self.db.commit()

    async def get_stats_history(self, limit: int = 60) -> list[dict]:
        """Get recent stats snapshots."""
        rows = await self.db.execute_fetchall(
            "SELECT * FROM stats ORDER BY recorded_at DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in rows]

    # ── Providers ───────────────────────────────────────────

    async def get_provider_status(self, name: str) -> Optional[dict]:
        """Get provider config from DB."""
        rows = await self.db.execute_fetchall(
            "SELECT * FROM providers WHERE name = ?", (name,)
        )
        return dict(rows[0]) if rows else None

    async def set_provider_enabled(self, name: str, enabled: bool) -> None:
        """Enable or disable a provider."""
        await self.db.execute(
            "UPDATE providers SET enabled = ? WHERE name = ?", (int(enabled), name)
        )
        await self.db.commit()

    async def increment_provider_stats(
        self, name: str, videos: int = 0, errors: int = 0
    ) -> None:
        """Increment provider counters."""
        if videos:
            await self.db.execute(
                """UPDATE providers SET videos_served = videos_served + ?,
                   last_used = datetime('now') WHERE name = ?""",
                (videos, name),
            )
        if errors:
            await self.db.execute(
                "UPDATE providers SET errors = errors + ? WHERE name = ?",
                (errors, name),
            )
        await self.db.commit()

    async def get_all_providers(self) -> list[dict]:
        """Get all providers status."""
        rows = await self.db.execute_fetchall("SELECT * FROM providers")
        return [dict(row) for row in rows]

    # ── Categories ──────────────────────────────────────────

    async def get_categories(self) -> list[dict]:
        """Get all categories."""
        rows = await self.db.execute_fetchall(
            "SELECT * FROM categories ORDER BY name"
        )
        result = []
        for row in rows:
            d = dict(row)
            d["keywords"] = json.loads(d.get("keywords", "[]"))
            result.append(d)
        return result

    async def get_enabled_categories(self) -> list[dict]:
        """Get only enabled categories."""
        rows = await self.db.execute_fetchall(
            "SELECT * FROM categories WHERE enabled = 1 ORDER BY name"
        )
        result = []
        for row in rows:
            d = dict(row)
            d["keywords"] = json.loads(d.get("keywords", "[]"))
            result.append(d)
        return result

    async def set_category_enabled(self, name: str, enabled: bool) -> None:
        """Enable or disable a category."""
        await self.db.execute(
            "UPDATE categories SET enabled = ? WHERE name = ?", (int(enabled), name)
        )
        await self.db.commit()

    async def add_category(
        self, name: str, keywords: list[str], weight: float = 1.0
    ) -> None:
        """Add a new category."""
        await self.db.execute(
            "INSERT OR IGNORE INTO categories (name, enabled, weight, keywords) VALUES (?, 1, ?, ?)",
            (name, weight, json.dumps(keywords)),
        )
        await self.db.commit()


# Singleton
db = Database()
