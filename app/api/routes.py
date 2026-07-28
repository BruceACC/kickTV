"""
KickTV — REST API Routes

All API endpoints for managing the stream, queue, providers, and settings.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.core.queue_manager import queue
from app.core.stream_engine import engine
from app.core.system_monitor import monitor
from app.database import db
from app.logger import log_broadcaster
from app.models import (
    APIResponse,
    ProviderName,
    StatsResponse,
    StreamState,
    StreamStatus,
    SystemStats,
)
from app.utils.helpers import format_uptime

logger = logging.getLogger("kicktv")

router = APIRouter(prefix="/api", tags=["api"])


# ── Status ──────────────────────────────────────────────────


@router.get("/status")
async def get_status() -> dict:
    """Get current stream status and system metrics."""
    stream = engine.status
    system = monitor.get_stats()
    error_count = await db.get_error_count()
    history_count = await db.get_history_count()
    providers_data = await db.get_all_providers()
    active_providers = sum(1 for p in providers_data if p.get("enabled"))

    return {
        "success": True,
        "data": {
            "stream": stream.model_dump(),
            "system": system.model_dump(),
            "queue_size": queue.size,
            "history_count": history_count,
            "providers_active": active_providers,
            "total_errors": error_count,
            "uptime_formatted": format_uptime(stream.started_at),
        },
    }


# ── Stream Control ──────────────────────────────────────────


@router.post("/start")
async def start_stream() -> dict:
    """Start the stream."""
    if engine.is_running:
        return {"success": False, "message": "Stream is already running"}
    result = await engine.start()
    return {
        "success": result,
        "message": "Stream started" if result else "Failed to start stream",
    }


@router.post("/stop")
async def stop_stream() -> dict:
    """Stop the stream."""
    if not engine.is_running:
        return {"success": False, "message": "Stream is not running"}
    result = await engine.stop()
    return {
        "success": result,
        "message": "Stream stopped" if result else "Failed to stop stream",
    }


@router.post("/restart")
async def restart_stream() -> dict:
    """Restart the stream."""
    result = await engine.restart()
    return {
        "success": result,
        "message": "Stream restarted" if result else "Failed to restart stream",
    }


@router.post("/skip")
async def skip_video() -> dict:
    """Skip the currently playing video."""
    result = await engine.skip_current()
    return {
        "success": result,
        "message": "Video skipped" if result else "Cannot skip (stream not running)",
    }


# ── Queue ───────────────────────────────────────────────────


@router.get("/queue")
async def get_queue() -> dict:
    """Get current playback queue."""
    items = queue.items
    return {
        "success": True,
        "data": {
            "size": len(items),
            "items": [
                {
                    "position": i,
                    "title": item.video.title,
                    "author": item.video.author,
                    "category": item.video.category.value,
                    "provider": item.video.provider.value,
                    "duration": item.video.duration,
                    "added_at": item.added_at.isoformat(),
                }
                for i, item in enumerate(items)
            ],
        },
    }


@router.post("/queue/fill")
async def fill_queue() -> dict:
    """Manually trigger queue fill."""
    added = await queue.fill(target_size=10)
    return {
        "success": True,
        "message": f"Added {added} videos to queue",
        "data": {"added": added, "queue_size": queue.size},
    }


@router.post("/queue/clear")
async def clear_queue() -> dict:
    """Clear the queue."""
    queue.clear()
    return {"success": True, "message": "Queue cleared"}


# ── History ─────────────────────────────────────────────────


@router.get("/history")
async def get_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Get play history."""
    history = await db.get_history(limit=limit, offset=offset)
    total = await db.get_history_count()
    return {
        "success": True,
        "data": {
            "total": total,
            "items": history,
        },
    }


# ── Providers ───────────────────────────────────────────────


@router.get("/providers")
async def get_providers() -> dict:
    """Get all provider statuses."""
    db_providers = await db.get_all_providers()
    registered = queue.get_providers()

    providers_list = []
    for p_data in db_providers:
        name = p_data["name"]
        provider = registered.get(ProviderName(name)) if name in [e.value for e in ProviderName] else None

        if not provider:
            continue

        providers_list.append({
            "name": name,
            "display_name": provider.display_name,
            "description": provider.description,
            "enabled": bool(p_data.get("enabled")),
            "requires_api_key": provider.requires_api_key,
            "has_api_key": provider.has_api_key if hasattr(provider, "has_api_key") else True,
            "videos_served": p_data.get("videos_served", 0),
            "errors": p_data.get("errors", 0),
            "last_used": p_data.get("last_used"),
        })

    return {"success": True, "data": providers_list}


class ProviderToggle(BaseModel):
    enabled: bool


@router.put("/providers/{name}")
async def toggle_provider(name: str, body: ProviderToggle) -> dict:
    """Enable or disable a provider."""
    try:
        provider_name = ProviderName(name)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    providers = queue.get_providers()
    provider = providers.get(provider_name)
    if provider:
        provider.enabled = body.enabled

    await db.set_provider_enabled(name, body.enabled)
    return {
        "success": True,
        "message": f"Provider '{name}' {'enabled' if body.enabled else 'disabled'}",
    }


# ── Settings ────────────────────────────────────────────────


@router.get("/settings")
async def get_settings() -> dict:
    """Get current stream settings."""
    return {
        "success": True,
        "data": {
            "stream_url": settings.stream_url,
            "bitrate": settings.bitrate,
            "fps": settings.fps,
            "resolution": settings.resolution,
            "preset": settings.preset,
            "audio_bitrate": settings.audio_bitrate,
            "queue_min_size": settings.queue_min_size,
            "max_video_duration": settings.max_video_duration,
            "min_video_duration": settings.min_video_duration,
        },
    }


# ── Logs ────────────────────────────────────────────────────


@router.get("/logs")
async def get_logs(
    count: int = Query(default=100, ge=1, le=1000),
) -> dict:
    """Get recent log entries."""
    logs = log_broadcaster.get_recent(count)
    return {"success": True, "data": logs}


# ── Stats ───────────────────────────────────────────────────


@router.get("/stats")
async def get_stats() -> dict:
    """Get system stats history."""
    stats_history = await db.get_stats_history(limit=60)
    return {"success": True, "data": stats_history}


# ── Categories ──────────────────────────────────────────────


@router.get("/categories")
async def get_categories() -> dict:
    """Get all categories."""
    categories = await db.get_categories()
    return {"success": True, "data": categories}


class CategoryToggle(BaseModel):
    enabled: bool


@router.put("/categories/{name}")
async def toggle_category(name: str, body: CategoryToggle) -> dict:
    """Enable or disable a category."""
    await db.set_category_enabled(name, body.enabled)
    return {
        "success": True,
        "message": f"Category '{name}' {'enabled' if body.enabled else 'disabled'}",
    }


class NewCategory(BaseModel):
    name: str
    keywords: list[str] = []


@router.post("/categories")
async def add_category(body: NewCategory) -> dict:
    """Add a new category."""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Category name is required")
    await db.add_category(body.name.strip().lower(), body.keywords)
    return {"success": True, "message": f"Category '{body.name}' added"}


# ── Errors ──────────────────────────────────────────────────


@router.get("/errors")
async def get_errors(
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    """Get recent errors."""
    errors = await db.get_errors(limit=limit)
    return {"success": True, "data": errors}
