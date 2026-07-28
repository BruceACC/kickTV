"""
KickTV — Video Utilities

Helper functions for video downloading, validation, and probing.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import aiohttp

from app.config import settings

logger = logging.getLogger("kicktv")


async def download_video(
    url: str,
    dest_dir: Optional[Path] = None,
    filename: Optional[str] = None,
    timeout: int = 120,
) -> Optional[Path]:
    """
    Download a video file to the local cache.

    Args:
        url: Video URL to download.
        dest_dir: Destination directory. Defaults to video cache dir.
        filename: Target filename. Auto-generated if not provided.
        timeout: Download timeout in seconds.

    Returns:
        Path to downloaded file, or None on failure.
    """
    dest = dest_dir or settings.abs_video_cache_dir
    dest.mkdir(parents=True, exist_ok=True)

    if not filename:
        # Extract extension from URL or default to .mp4
        ext = ".mp4"
        url_path = url.split("?")[0]
        for candidate_ext in (".mp4", ".webm", ".mkv", ".avi", ".mov"):
            if url_path.lower().endswith(candidate_ext):
                ext = candidate_ext
                break
        filename = f"{uuid.uuid4().hex[:12]}{ext}"

    filepath = dest / filename

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status != 200:
                    logger.error("Download failed (%d): %s", resp.status, url[:100])
                    return None

                content_length = resp.headers.get("Content-Length")
                if content_length and int(content_length) < 1000:
                    logger.warning("File too small (%s bytes): %s", content_length, url[:100])
                    return None

                with open(filepath, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        f.write(chunk)

        # Verify file size
        if filepath.stat().st_size < 10000:  # Less than 10KB is suspicious
            logger.warning("Downloaded file too small, removing: %s", filepath)
            filepath.unlink(missing_ok=True)
            return None

        logger.info("Downloaded: %s -> %s", url[:80], filepath.name)
        return filepath

    except asyncio.TimeoutError:
        logger.error("Download timed out: %s", url[:100])
        filepath.unlink(missing_ok=True)
        return None
    except Exception as e:
        logger.error("Download error: %s — %s", url[:100], e)
        filepath.unlink(missing_ok=True)
        return None


async def probe_video(filepath: str) -> Optional[dict]:
    """
    Use ffprobe to get video metadata (duration, resolution, codec).

    Returns dict with 'duration', 'width', 'height', 'codec' or None.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(filepath),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)

        if not stdout:
            return None

        import json
        data = json.loads(stdout.decode("utf-8"))

        # Extract video stream info
        duration = float(data.get("format", {}).get("duration", 0))
        width = 0
        height = 0
        codec = ""

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = stream.get("width", 0)
                height = stream.get("height", 0)
                codec = stream.get("codec_name", "")
                break

        return {
            "duration": int(duration),
            "width": width,
            "height": height,
            "codec": codec,
        }
    except Exception as e:
        logger.error("ffprobe failed for %s: %s", filepath, e)
        return None


async def validate_url(url: str, timeout: int = 10) -> bool:
    """
    Check if a URL is accessible with a HEAD request.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
            ) as resp:
                return resp.status in (200, 206, 301, 302)
    except Exception:
        return False


def clean_video_cache(max_files: int = 100) -> int:
    """
    Remove oldest cached videos if cache exceeds max_files.
    Returns the number of files removed.
    """
    cache_dir = settings.abs_video_cache_dir
    if not cache_dir.exists():
        return 0

    files = sorted(cache_dir.iterdir(), key=lambda f: f.stat().st_mtime)
    video_files = [f for f in files if f.is_file() and f.suffix.lower() in {
        ".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv",
    }]

    removed = 0
    while len(video_files) > max_files:
        oldest = video_files.pop(0)
        try:
            oldest.unlink()
            removed += 1
        except OSError:
            pass

    if removed:
        logger.info("Cleaned %d old video files from cache", removed)
    return removed
