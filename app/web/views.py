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
    """Main dashboard page."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@web_router.get("/queue", response_class=HTMLResponse)
async def queue_page(request: Request) -> HTMLResponse:
    """Queue management page."""
    return templates.TemplateResponse("queue.html", {"request": request})


@web_router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request) -> HTMLResponse:
    """Play history page."""
    return templates.TemplateResponse("history.html", {"request": request})


@web_router.get("/providers", response_class=HTMLResponse)
async def providers_page(request: Request) -> HTMLResponse:
    """Provider management page."""
    return templates.TemplateResponse("providers.html", {"request": request})


@web_router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """Settings page."""
    return templates.TemplateResponse("settings.html", {"request": request})


@web_router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request) -> HTMLResponse:
    """Log viewer page."""
    return templates.TemplateResponse("logs.html", {"request": request})
