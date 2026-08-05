"""
KickTV — Web Views

Jinja2 template rendering routes for the dashboard pages.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

web_router = APIRouter(tags=["web"])


@web_router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Redirect main page to the M3U8 Player."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/tv.m3u8")

@web_router.get("/tv.m3u8")
@web_router.get("/tv")
async def tv_player_m3u8(request: Request):
    """M3U8 Playlist for OBS Studio/VLC."""
    from fastapi.responses import PlainTextResponse
    
    base_url = str(request.base_url).rstrip("/")
    stream_url = f"{base_url}/api/player/next.mp4"
    
    lines = [
        "#EXTM3U",
        "#EXTINF:-1,KickTV Stream (Activa 'Bucle' en OBS para TV 24/7)",
        stream_url
    ]
        
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    
    return PlainTextResponse("\n".join(lines), media_type="application/vnd.apple.mpegurl", headers=headers)

@web_router.get("/queen", response_class=HTMLResponse)
async def queen_page(request: Request) -> HTMLResponse:
    """Secret page to inject Unlimplay movies/series (Public for viewers)."""
    return templates.TemplateResponse("request.html", {"request": request})

@web_router.get("/vip", response_class=HTMLResponse)
async def vip_page(request: Request) -> HTMLResponse:
    """Private cinema for VIP viewers."""
    from app.config import settings
    vip_code = request.cookies.get("vip_code", "")
    
    # Check if a password is set and it doesn't match the cookie
    if settings.vip_password and vip_code != settings.vip_password:
        return templates.TemplateResponse("login.html", {"request": request})
        
    return templates.TemplateResponse("queen.html", {"request": request})

@web_router.get("/vip/{media_type}/{tmdb_id}", response_class=HTMLResponse)
async def vip_detail_page(request: Request, media_type: str, tmdb_id: int) -> HTMLResponse:
    """Detailed VIP page for a specific movie or series."""
    from app.config import settings
    vip_code = request.cookies.get("vip_code", "")
    
    # Check if a password is set and it doesn't match the cookie
    if settings.vip_password and vip_code != settings.vip_password:
        return templates.TemplateResponse("login.html", {"request": request})
        
    return templates.TemplateResponse("vip_detail.html", {
        "request": request,
        "media_type": media_type,
        "tmdb_id": tmdb_id
    })
