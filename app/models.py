"""
KickTV — Data Models

Pydantic models and enums used throughout the application.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ───────────────────────────────────────────────────────


class VideoCategory(str, Enum):
    """Available content categories."""
    TERROR = "terror"
    CURIOSIDADES = "curiosidades"
    DOCUMENTALES = "documentales"
    NATURALEZA = "naturaleza"
    ANIMALES = "animales"
    GAMING = "gaming"
    TECNOLOGIA = "tecnología"
    ESPACIO = "espacio"
    PELICULAS_CLASICAS = "películas clásicas"
    MEMES = "memes"
    SHORTS = "shorts"
    TRAILERS = "trailers"
    CIENCIA = "ciencia"


class ProviderName(str, Enum):
    """Registered content providers."""
    LOCAL = "local"
    PEXELS = "pexels"
    PIXABAY = "pixabay"
    ARCHIVE = "archive"
    YOUTUBE = "youtube"
    REDDIT = "reddit"
    UNLIMPLAY = "unlimplay"


class StreamState(str, Enum):
    """Possible stream states."""
    STOPPED = "stopped"
    STARTING = "starting"
    LIVE = "live"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class VideoDuration(str, Enum):
    """Duration classification for queue balancing."""
    SHORT = "short"       # < 3 minutes
    MEDIUM = "medium"     # 3–15 minutes
    LONG = "long"         # > 15 minutes


# ── Video Models ────────────────────────────────────────────────


class VideoResult(BaseModel):
    """A video returned by a provider."""
    url: str
    title: str = "Untitled"
    duration: int = 0                                  # seconds
    author: str = "Unknown"
    category: VideoCategory = VideoCategory.CURIOSIDADES
    provider: ProviderName = ProviderName.LOCAL
    thumbnail: str = ""
    description: str = ""
    license: str = ""
    video_id: str = ""                                 # unique provider id

    @property
    def duration_class(self) -> VideoDuration:
        """Classify video by duration."""
        if self.duration < 180:
            return VideoDuration.SHORT
        elif self.duration <= 900:
            return VideoDuration.MEDIUM
        else:
            return VideoDuration.LONG


class QueueItem(BaseModel):
    """An item in the playback queue."""
    position: int = 0
    video: VideoResult
    added_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "pending"  # pending | playing | played | error


# ── Stream Models ───────────────────────────────────────────────


class StreamStatus(BaseModel):
    """Current stream state and metrics."""
    state: StreamState = StreamState.STOPPED
    current_video: Optional[VideoResult] = None
    next_video: Optional[VideoResult] = None
    uptime_seconds: int = 0
    total_videos_played: int = 0
    current_fps: float = 0.0
    current_bitrate: str = "0k"
    frames_dropped: int = 0
    reconnect_count: int = 0
    ffmpeg_pid: Optional[int] = None
    started_at: Optional[datetime] = None


class SystemStats(BaseModel):
    """System resource metrics."""
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    ram_used_mb: float = 0.0
    ram_total_mb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    ffmpeg_pid: Optional[int] = None
    ffmpeg_cpu: float = 0.0
    ffmpeg_ram_mb: float = 0.0


# ── Provider Models ─────────────────────────────────────────────


class ProviderConfig(BaseModel):
    """Provider status and configuration."""
    name: ProviderName
    enabled: bool = True
    display_name: str = ""
    description: str = ""
    requires_api_key: bool = False
    has_api_key: bool = False
    videos_served: int = 0
    errors: int = 0
    last_used: Optional[datetime] = None


# ── Settings Models ─────────────────────────────────────────────


class StreamSettings(BaseModel):
    """User-adjustable stream settings."""
    stream_url: str
    bitrate: str
    fps: int
    resolution: str
    preset: str
    audio_bitrate: str


# ── Log Models ──────────────────────────────────────────────────


class LogEntry(BaseModel):
    """A log entry for the API."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str = "INFO"
    module: str = "app"
    message: str = ""


# ── API Response Models ─────────────────────────────────────────


class APIResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool = True
    message: str = ""
    data: Optional[dict] = None


class StatsResponse(BaseModel):
    """Combined stats for the dashboard."""
    stream: StreamStatus
    system: SystemStats
    queue_size: int = 0
    history_count: int = 0
    providers_active: int = 0
    total_errors: int = 0
    uptime_formatted: str = "0h 0m"
