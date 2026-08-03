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

@router.get("/tmdb/tv/{tmdb_id}")
async def get_tv_info(tmdb_id: int):
    """Get detailed TV show info (including seasons and episode counts)."""
    if not tmdb_client.is_configured():
        raise HTTPException(status_code=500, detail="TMDB API Key no configurada")
    details = await tmdb_client.get_tv_details(tmdb_id)
    return {"success": True, "details": details}

@router.get("/tmdb/now_playing")
async def get_now_playing():
    """Get now playing/upcoming movies for the carousel."""
    if not tmdb_client.is_configured():
        raise HTTPException(status_code=500, detail="TMDB API Key no configurada")
    results = await tmdb_client.get_now_playing()
    return {"success": True, "results": results}

@router.get("/tmdb/top_movies")
async def get_top_movies():
    if not tmdb_client.is_configured(): raise HTTPException(status_code=500, detail="TMDB Key error")
    return {"success": True, "results": await tmdb_client.get_top_movies()}

@router.get("/tmdb/top_series")
async def get_top_series():
    if not tmdb_client.is_configured(): raise HTTPException(status_code=500, detail="TMDB Key error")
    return {"success": True, "results": await tmdb_client.get_top_series()}

@router.get("/tmdb/top_anime")
async def get_top_anime():
    if not tmdb_client.is_configured(): raise HTTPException(status_code=500, detail="TMDB Key error")
    return {"success": True, "results": await tmdb_client.get_top_anime()}

@router.get("/youtube/trailer")
async def get_youtube_trailer(query: str = Query(..., min_length=2)):
    """Search YouTube for a trailer and return the video URL."""
    from app.models import VideoCategory
    youtube_provider = queue.get_providers().get(ProviderName.YOUTUBE)
    if not youtube_provider:
        raise HTTPException(status_code=500, detail="YouTube Provider not registered")
    
    # Use the internal _api_search method
    results = await youtube_provider._api_search(f"{query} trailer", VideoCategory.PELICULAS, limit=1)
    if not results:
        raise HTTPException(status_code=404, detail="Trailer not found")
        
    return {"success": True, "video": results[0].model_dump()}

class InjectTrailerRequest(BaseModel):
    title: str
    
@router.post("/queue/inject_trailer")
async def inject_trailer(req: InjectTrailerRequest) -> dict:
    """Search for a trailer and inject it directly into the queue."""
    from app.models import VideoCategory, QueueItem
    youtube_provider = queue.get_providers().get(ProviderName.YOUTUBE)
    if not youtube_provider:
        raise HTTPException(status_code=500, detail="YouTube Provider not registered")
        
    results = await youtube_provider._api_search(f"{req.title} trailer oficial español", VideoCategory.PELICULAS, limit=1)
    if not results:
        raise HTTPException(status_code=404, detail="Trailer no encontrado en YouTube")
        
    video = results[0]
    # Mark it clearly as a trailer in the title
    video.title = f"[TRÁILER] {video.title}"
    
    async with queue._lock:
        item = QueueItem(position=0, video=video)
        queue._queue.appendleft(item)
        
    return {"success": True, "message": f"Injected trailer for {req.title}"}

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


# ── VIP Auth ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str

@router.post("/auth/login")
async def login_vip(req: LoginRequest):
    """Verifica la contraseña VIP y devuelve success si es correcta."""
    if not settings.vip_password:
        # If no password is set, anyone can get in (for local testing)
        return {"success": True}
        
    if req.password == settings.vip_password:
        return {"success": True}
    
    raise HTTPException(status_code=401, detail="Contraseña incorrecta")

# ── Custom Features ─────────────────────────────────────────

@router.get("/youtube/channel_music")
async def get_channel_music():
    """Fetch latest videos from the custom background music channel."""
    import aiohttp
    import xml.etree.ElementTree as ET
    url = "https://www.youtube.com/feeds/videos.xml?channel_id=UCphgohC7NIotJNHyfJUmnIX"
    video_ids = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    content = await resp.text()
                    root = ET.fromstring(content)
                    ns = {"yt": "http://www.youtube.com/xml/schemas/2015", "atom": "http://www.w3.org/2005/Atom"}
                    for entry in root.findall("atom:entry", ns):
                        vid = entry.find("yt:videoId", ns)
                        if vid is not None and vid.text:
                            video_ids.append(vid.text)
    except Exception as e:
        logger.error(f"Error fetching channel music: {e}")
    
    if not video_ids:
        video_ids = ['BsuFR4OR8sQ', 'TJLGWZT6O5s', '-cXUGAFSMpo', 'ai11onkXyZg']
        
    return {"success": True, "videos": video_ids}
