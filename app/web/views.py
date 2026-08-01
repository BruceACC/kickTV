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
async def dashboard(request: Request) -> HTMLResponse:
    """Redirect main page to the TV Player."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/tv")

@web_router.get("/tv", response_class=HTMLResponse)
async def tv_player_page(request: Request) -> HTMLResponse:
    """Web TV Player for OBS Studio."""
    return templates.TemplateResponse("player.html", {"request": request})

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
