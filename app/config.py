"""
KickTV — Application Configuration

Loads settings from .env file using pydantic-settings.
All configuration is centralized here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )



    # ── Dashboard ───────────────────────────────────────────
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000

    # ── Provider API Keys ───────────────────────────────────
    pexels_api_key: str = ""
    tmdb_api_key: str = ""
    pixabay_api_key: str = ""
    youtube_api_key: str = ""

    # ── Provider Toggles ────────────────────────────────────
    provider_local_enabled: bool = True
    provider_pexels_enabled: bool = True
    provider_pixabay_enabled: bool = True
    provider_archive_enabled: bool = True
    provider_youtube_enabled: bool = False
    provider_youtube_weight: int = 60
    provider_tiktok_enabled: bool = True
    provider_tiktok_weight: int = 15
    tiktok_cookies_file: str = "tiktok/cookies.txt"

    provider_instagram_enabled: bool = True
    provider_instagram_weight: int = 15

    provider_reddit_enabled: bool = True
    provider_reddit_weight: int = 40

    instagram_cookies_file: str = "instagram/cookies.txt"  # Path to cookies.txt for yt-dlp

    # ── Queue ───────────────────────────────────────────────
    queue_min_size: int = 5
    queue_max_history: int = 10
    video_cache_dir: str = "data/videos"
    max_video_duration: int = 14400  # seconds (4 hours)
    min_video_duration: int = 5  # seconds

    # ── Database ────────────────────────────────────────────
    database_path: str = "data/db/kicktv.db"

    # ── Logging ─────────────────────────────────────────────
    log_dir: str = "logs"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # ── Auto-Start & Preview ────────────────────────────────
    auto_start: bool = False  # Start streaming automatically on server boot
    local_preview: bool = False # Generate local HLS preview for dashboard
    hls_dir: str = "data/hls"

    # (Removed obsolete stream_url and resolution properties)
    @property
    def abs_video_cache_dir(self) -> Path:
        """Absolute path to video cache directory."""
        p = Path(self.video_cache_dir)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def abs_database_path(self) -> Path:
        """Absolute path to database file."""
        p = Path(self.database_path)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def abs_log_dir(self) -> Path:
        """Absolute path to log directory."""
        p = Path(self.log_dir)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def abs_hls_dir(self) -> Path:
        """Absolute path to HLS directory."""
        p = Path(self.hls_dir)
        return p if p.is_absolute() else BASE_DIR / p

    # Validation removed
    def ensure_directories(self) -> None:
        """Create all required directories."""
        self.abs_video_cache_dir.mkdir(parents=True, exist_ok=True)
        self.abs_database_path.parent.mkdir(parents=True, exist_ok=True)
        self.abs_log_dir.mkdir(parents=True, exist_ok=True)
        self.abs_hls_dir.mkdir(parents=True, exist_ok=True)
        # Log subdirectories
        (self.abs_log_dir / "app").mkdir(exist_ok=True)
        (self.abs_log_dir / "ffmpeg").mkdir(exist_ok=True)
        (self.abs_log_dir / "providers").mkdir(exist_ok=True)
        (self.abs_log_dir / "errors").mkdir(exist_ok=True)


# Singleton instance
settings = Settings()
