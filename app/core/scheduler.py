"""
KickTV — Scheduler

Background jobs using APScheduler:
  - Queue replenishment
  - Video cache cleanup
  - Stats recording
  - Health checks
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.queue_manager import queue

from app.core.system_monitor import monitor
from app.database import db
from app.utils.video import clean_video_cache

logger = logging.getLogger("kicktv")

scheduler = AsyncIOScheduler()


async def job_fill_queue() -> None:
    """Ensure the queue maintains minimum items."""
    try:
        if queue.size < 5:
            added = await queue.fill()
            if added:
                logger.info("Scheduler: added %d items to queue", added)
    except Exception as e:
        logger.error("Scheduler: queue fill failed: %s", e)


async def job_record_stats() -> None:
    """Record system stats snapshot to DB."""
    try:
        stats = monitor.get_stats()
        await db.record_stats({
            "cpu_percent": stats.cpu_percent,
            "ram_percent": stats.ram_percent,
            "fps": 30,
            "bitrate": 0,
            "frames_dropped": 0,
            "queue_size": queue.size,
        })
    except Exception as e:
        logger.error("Scheduler: stats recording failed: %s", e)


async def job_clean_cache() -> None:
    """Clean old files from the video cache."""
    try:
        removed = clean_video_cache(max_files=100)
        if removed:
            logger.info("Scheduler: cleaned %d cached files", removed)
    except Exception as e:
        logger.error("Scheduler: cache cleanup failed: %s", e)





async def job_remove_invalid() -> None:
    """Remove invalid videos from the queue."""
    try:
        removed = await queue.remove_invalid()
        if removed:
            logger.info("Scheduler: removed %d invalid queue items", removed)
    except Exception as e:
        logger.error("Scheduler: invalid video removal failed: %s", e)


def setup_scheduler() -> AsyncIOScheduler:
    """Configure and return the scheduler with all jobs."""
    # Queue replenishment — every 3 minutes
    scheduler.add_job(
        job_fill_queue,
        trigger=IntervalTrigger(minutes=3),
        id="fill_queue",
        name="Fill Queue",
        replace_existing=True,
    )

    # Stats recording — every 30 seconds
    scheduler.add_job(
        job_record_stats,
        trigger=IntervalTrigger(seconds=30),
        id="record_stats",
        name="Record Stats",
        replace_existing=True,
    )

    # Cache cleanup — every hour
    scheduler.add_job(
        job_clean_cache,
        trigger=IntervalTrigger(hours=1),
        id="clean_cache",
        name="Clean Cache",
        replace_existing=True,
    )



    # Remove invalid videos — every 30 minutes
    scheduler.add_job(
        job_remove_invalid,
        trigger=IntervalTrigger(minutes=30),
        id="remove_invalid",
        name="Remove Invalid Videos",
        replace_existing=True,
    )

    logger.info("Scheduler configured with %d jobs", len(scheduler.get_jobs()))
    return scheduler
