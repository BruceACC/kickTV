"""
KickTV — General Helpers

Miscellaneous utility functions used across the application.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def format_duration(seconds: int) -> str:
    """Format seconds into human-readable duration (e.g., '1h 23m 45s')."""
    if seconds <= 0:
        return "0s"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def format_uptime(started_at: datetime | None) -> str:
    """Format uptime from a start timestamp."""
    if not started_at:
        return "0h 0m"
    delta = datetime.utcnow() - started_at
    return format_duration(int(delta.total_seconds()))


def truncate(text: str, max_length: int = 50) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def bytes_to_human(num_bytes: int | float) -> str:
    """Convert bytes to human-readable format (KB, MB, GB)."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def sanitize_filename(name: str) -> str:
    """Remove invalid characters from a filename."""
    import re
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name)
    return cleaned.strip()[:200]
