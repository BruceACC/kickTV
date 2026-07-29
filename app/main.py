"""
KickTV — Main Application

FastAPI application factory with all routes, middleware, startup/shutdown events.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.api.websocket import ws_router
from app.config import settings
from app.core.queue_manager import queue
from app.core.scheduler import setup_scheduler, scheduler
from app.database import db
from app.logger import get_logger, setup_logging

from app.providers.youtube import YouTubeProvider
from app.providers.tiktok import TikTokProvider
from app.providers.instagram import InstagramProvider
from app.web.views import web_router


logger = get_logger("kicktv")


def _register_providers() -> None:
    """Register all content providers based on configuration."""
    # YouTube (CC)
    youtube = YouTubeProvider()
    youtube.enabled = settings.provider_youtube_enabled
    queue.register_provider(youtube)

    # TikTok
    tiktok = TikTokProvider()
    tiktok.enabled = settings.provider_tiktok_enabled
    queue.register_provider(tiktok)

    # Instagram Reels
    instagram = InstagramProvider()
    instagram.enabled = settings.provider_instagram_enabled
    queue.register_provider(instagram)

    providers = queue.get_providers()
    enabled = sum(1 for p in providers.values() if p.enabled)
    logger.info("Registered %d providers (%d enabled)", len(providers), enabled)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # ── Startup ────────────────────────────────────
    setup_logging()
    logger.info("=" * 50)
    logger.info("  KickTV — Starting Up")
    logger.info("=" * 50)

    # Ensure directories exist
    settings.ensure_directories()

    # Connect database
    await db.connect()
    logger.info("Database connected: %s", settings.abs_database_path)

    # Register providers
    _register_providers()

    # Initialize queue
    await queue.initialize()

    # Start scheduler
    setup_scheduler()
    scheduler.start()
    logger.info("Scheduler started")

    logger.info("Dashboard: http://%s:%d", settings.dashboard_host, settings.dashboard_port)
    logger.info("API docs:  http://%s:%d/docs", settings.dashboard_host, settings.dashboard_port)
    logger.info("=" * 50)

    # Auto-start stream if configured
    if settings.auto_start:
        from app.core.stream_engine import engine
        logger.info("AUTO_START enabled — starting stream automatically...")
        await engine.start()
        logger.info("[OK] Stream auto-started")

    yield

    # ── Shutdown ───────────────────────────────────
    logger.info("Shutting down KickTV...")

    # Stop stream engine
    from app.core.stream_engine import engine
    if engine.is_running:
        await engine.stop()

    # Stop scheduler
    if scheduler.running:
        scheduler.shutdown(wait=False)

    # Close database
    await db.close()

    logger.info("KickTV shut down cleanly")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="KickTV",
        description="Automatic 24/7 TV Channel for Kick",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Mount static files
    static_dir = Path(__file__).parent / "web" / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Mount HLS directory for local preview
    settings.abs_hls_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/hls", StaticFiles(directory=str(settings.abs_hls_dir)), name="hls")

    # Include routers
    app.include_router(api_router)
    app.include_router(ws_router)
    app.include_router(web_router)

    return app


# Application instance
app = create_app()
