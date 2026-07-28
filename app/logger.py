"""
KickTV — Logging Configuration

Sets up rotating file handlers for different log types,
and a broadcast mechanism for real-time log streaming via WebSocket.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Callable, Optional

from app.config import settings


# Maximum log lines kept in memory for the web dashboard
MAX_LOG_BUFFER = 500


class LogBroadcaster:
    """
    Holds recent log lines in memory and broadcasts new entries
    to registered WebSocket listeners.
    """

    def __init__(self, max_buffer: int = MAX_LOG_BUFFER) -> None:
        self._buffer: deque[dict] = deque(maxlen=max_buffer)
        self._listeners: list[Callable] = []

    def add_entry(self, entry: dict) -> None:
        """Add a log entry and notify listeners."""
        self._buffer.append(entry)
        for listener in self._listeners:
            try:
                listener(entry)
            except Exception:
                pass

    def get_recent(self, count: int = 100) -> list[dict]:
        """Get last N log entries."""
        items = list(self._buffer)
        return items[-count:]

    def register(self, callback: Callable) -> None:
        """Register a listener for new log entries."""
        self._listeners.append(callback)

    def unregister(self, callback: Callable) -> None:
        """Unregister a listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)


# Global broadcaster
log_broadcaster = LogBroadcaster()


class BroadcastHandler(logging.Handler):
    """Custom handler that sends log records to the LogBroadcaster."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "module": record.name,
                "message": self.format(record),
            }
            log_broadcaster.add_entry(entry)
        except Exception:
            self.handleError(record)


def setup_logging() -> None:
    """Configure all loggers with file and broadcast handlers."""
    log_dir = settings.abs_log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Shared formatter
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)-8s] [%(name)-12s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Broadcast handler (sends to WebSocket clients)
    broadcast_handler = BroadcastHandler()
    broadcast_handler.setFormatter(fmt)
    broadcast_handler.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    console_handler.setLevel(log_level)

    # ── App Logger ──────────────────────────────────────
    app_logger = logging.getLogger("kicktv")
    app_logger.setLevel(log_level)
    app_logger.handlers.clear()

    app_file = TimedRotatingFileHandler(
        str(log_dir / "app" / "app.log"),
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    app_file.setFormatter(fmt)
    app_logger.addHandler(app_file)
    app_logger.addHandler(console_handler)
    app_logger.addHandler(broadcast_handler)

    # ── FFmpeg Logger ───────────────────────────────────
    ffmpeg_logger = logging.getLogger("kicktv.ffmpeg")
    ffmpeg_logger.setLevel(log_level)
    ffmpeg_logger.handlers.clear()
    ffmpeg_logger.propagate = False

    ffmpeg_file = TimedRotatingFileHandler(
        str(log_dir / "ffmpeg" / "ffmpeg.log"),
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    ffmpeg_file.setFormatter(fmt)
    ffmpeg_logger.addHandler(ffmpeg_file)
    ffmpeg_logger.addHandler(broadcast_handler)

    # ── Provider Logger ─────────────────────────────────
    provider_logger = logging.getLogger("kicktv.providers")
    provider_logger.setLevel(log_level)
    provider_logger.handlers.clear()
    provider_logger.propagate = False

    provider_file = TimedRotatingFileHandler(
        str(log_dir / "providers" / "providers.log"),
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    provider_file.setFormatter(fmt)
    provider_logger.addHandler(provider_file)
    provider_logger.addHandler(broadcast_handler)

    # ── Error Logger ────────────────────────────────────
    error_logger = logging.getLogger("kicktv.errors")
    error_logger.setLevel(logging.ERROR)
    error_logger.handlers.clear()
    error_logger.propagate = False

    error_file = RotatingFileHandler(
        str(log_dir / "errors" / "errors.log"),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    error_file.setFormatter(fmt)
    error_logger.addHandler(error_file)
    error_logger.addHandler(broadcast_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def get_logger(name: str = "kicktv") -> logging.Logger:
    """Get a named logger under the kicktv namespace."""
    return logging.getLogger(name)
