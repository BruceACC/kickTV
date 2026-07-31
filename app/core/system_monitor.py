"""
KickTV — System Monitor

Collects CPU, RAM, disk, and FFmpeg process metrics.
"""

from __future__ import annotations

import logging
from typing import Optional

import psutil


from app.models import SystemStats

logger = logging.getLogger("kicktv")


class SystemMonitor:
    """Collects system-level and FFmpeg-process metrics."""

    def get_stats(self) -> SystemStats:
        """Collect a snapshot of current system metrics."""
        stats = SystemStats()

        try:
            # Global CPU
            stats.cpu_percent = psutil.cpu_percent(interval=0.1)

            # Memory
            mem = psutil.virtual_memory()
            stats.ram_percent = mem.percent
            stats.ram_used_mb = round(mem.used / (1024 * 1024), 1)
            stats.ram_total_mb = round(mem.total / (1024 * 1024), 1)

            # Disk
            disk = psutil.disk_usage("/")
            stats.disk_percent = disk.percent
            stats.disk_used_gb = round(disk.used / (1024 ** 3), 1)
            stats.disk_total_gb = round(disk.total / (1024 ** 3), 1)

        except Exception as e:
            logger.error("Error collecting system stats: %s", e)



        return stats


# Singleton
monitor = SystemMonitor()
