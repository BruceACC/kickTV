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


from app.core.tmdb import tmdb_client

class InjectRequest(BaseModel):
    tmdb_id: str
    is_tv: bool = False
    season: int = 1
    episode: int = 1
    title: Optional[str] = None
    duration: Optional[int] = None

@router.get("/tmdb/search")
async def search_tmdb(query: str = Query(..., min_length=2)):
    """Search TMDB for movies and TV shows."""
    if not tmdb_client.is_configured():
        raise HTTPException(status_code=500, detail="TMDB API Key no configurada")
    results = await tmdb_client.search_multi(query)
    return {"success": True, "results": results}

@router.post("/queue/inject")
async def inject_movie(req: InjectRequest) -> dict:
    """Inject a movie/series from Unlimplay into the front of the queue."""
    title = req.title
    duration = req.duration

    if not title or not duration:
        if req.is_tv:
            details = await tmdb_client.get_tv_details(int(req.tmdb_id))
            title = details.get("name", f"TV Show {req.tmdb_id}")
            # Try to get episode runtime, default to 45 mins
            runtimes = details.get("episode_run_time", [])
            duration_mins = runtimes[0] if runtimes else 45
            duration_mins = duration_mins or 45
            duration = duration_mins * 60
        else:
            details = await tmdb_client.get_movie_details(int(req.tmdb_id))
            title = details.get("title", f"Movie {req.tmdb_id}")
            duration_mins = details.get("runtime", 120)
            duration_mins = duration_mins or 120
            duration = duration_mins * 60

    await queue.inject_movie(
        tmdb_id=req.tmdb_id,
        duration=duration,
        title=title,
        is_tv=req.is_tv,
        season=req.season,
        episode=req.episode
    )
    return {"success": True, "message": f"Injected {title}"}


@router.get("/queue")
async def get_queue() -> dict:
    """Get the current queue state."""
    items = []
    for item in queue.items:
        items.append({
            "title": item.video.title,
            "category": item.video.category.value,
            "provider": item.video.provider.value,
            "is_iframe": item.video.is_iframe,
            "duration": item.video.duration
        })
    return {"success": True, "queue": items, "size": queue.size}


# ── Web Player ──────────────────────────────────────────────


@router.get("/player/next")
async def get_next_video() -> dict:
    """Get the next video URL for the Web TV Player."""
    import os
    video = await queue.next()
    if not video:
        raise HTTPException(status_code=404, detail="No videos available in queue")
    
    if video.is_iframe:
        media_url = video.url
    else:
        try:
            rel_path = os.path.relpath(video.file_path, settings.video_cache_dir)
            media_url = f"/videos/{rel_path.replace(os.sep, '/')}"
        except ValueError:
            # Fallback if relpath fails
            filename = os.path.basename(video.file_path)
            media_url = f"/videos/{filename}"
        
    return {
        "success": True,
        "url": media_url,
        "is_iframe": video.is_iframe,
        "duration": video.duration,
        "title": video.title,
        "author": video.author,
        "category": video.category.value
    }

