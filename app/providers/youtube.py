"""
KickTV — YouTube Provider

Uses yt-dlp to find Creative Commons licensed videos only.
This provider is disabled by default and should only be used
when compatible with YouTube's Terms of Service.
"""

from __future__ import annotations

import asyncio
import random
from typing import Optional

from app.models import ProviderName, VideoCategory, VideoResult
from app.providers.base import BaseProvider, generate_video_id

# Search queries customized for shorts, reactions, football, summaries
SEARCH_QUERIES: dict[VideoCategory, list[str]] = {
    VideoCategory.NATURALEZA: [
        "futbol peruano resumen", "mejores jugadas futbol #shorts", "reacciones futbol peru",
    ],
    VideoCategory.CIENCIA: [
        "resumen peliculas", "reacciones peliculas #shorts", "resumen anime",
    ],
    VideoCategory.ESPACIO: [
        "clips streamers peru", "mejores momentos twitch", "clips divertidos #shorts",
    ],
    VideoCategory.DOCUMENTALES: [
        "resumen series", "te lo resumo", "reacciones series #shorts",
    ],
    VideoCategory.TECNOLOGIA: [
        "reacciones virales #shorts", "comentarios graciosos", "curiosidades",
    ],
    VideoCategory.ANIMALES: [
        "videos graciosos peru #shorts", "memes peru #shorts",
    ],
}


class YouTubeProvider(BaseProvider):
    """
    Fetches Creative Commons licensed videos using yt-dlp.

    IMPORTANT: This provider is disabled by default. It only searches for
    videos with Creative Commons licenses to comply with YouTube's TOS.
    """

    name = ProviderName.YOUTUBE
    display_name = "YouTube (CC)"
    description = "Creative Commons licensed videos via yt-dlp"
    requires_api_key = False

    def __init__(self) -> None:
        super().__init__()
        self._enabled = False  # Disabled by default

    async def _ytdlp_search(
        self, query: str, limit: int = 5
    ) -> list[dict]:
        """Run yt-dlp search in a subprocess to avoid blocking."""
        try:
            cmd = [
                "yt-dlp",
                f"ytsearch{limit}:{query}",
                "--dump-json",
                "--flat-playlist",
                "--no-download",
                "--no-warnings",
                "--quiet",
                "--extractor-args", "youtube:player_client=web",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            results: list[dict] = []
            if stdout:
                import json
                for line in stdout.decode("utf-8", errors="replace").strip().split("\n"):
                    line = line.strip()
                    if line:
                        try:
                            results.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            return results
        except asyncio.TimeoutError:
            self.logger.warning("yt-dlp search timed out for: %s", query)
            return []
        except FileNotFoundError:
            self.logger.error("yt-dlp not found. Install it with: pip install yt-dlp")
            return []
        except Exception as e:
            self.logger.error("yt-dlp search failed: %s", e)
            return []

    async def _get_direct_url(self, video_url: str) -> Optional[str]:
        """Get direct download URL using yt-dlp -g."""
        try:
            cmd = [
                "yt-dlp",
                "-g",
                "-f", "b",
                "--no-warnings",
                "--quiet",
                video_url,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
            if stdout:
                url = stdout.decode("utf-8").strip().split("\n")[0]
                return url if url.startswith("http") else None
            return None
        except Exception as e:
            self.logger.error("yt-dlp URL extraction failed: %s", e)
            return None

    def _parse_result(self, raw: dict, category: VideoCategory) -> Optional[VideoResult]:
        """Parse a yt-dlp JSON result into a VideoResult."""
        video_id = raw.get("id", "")
        url = raw.get("url") or raw.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
        title = raw.get("title", "YouTube Video")
        duration = raw.get("duration") or 0

        if not video_id:
            return None

        return VideoResult(
            url=url,
            title=title,
            duration=int(duration) if duration else 0,
            author=raw.get("uploader", raw.get("channel", "YouTube")),
            category=category,
            provider=ProviderName.YOUTUBE,
            thumbnail=raw.get("thumbnail", ""),
            video_id=generate_video_id("youtube", video_id),
            license=raw.get("license", "Creative Commons"),
        )

    async def search(
        self,
        query: str = "",
        category: Optional[VideoCategory] = None,
        limit: int = 5,
    ) -> list[VideoResult]:
        """Search YouTube for Creative Commons videos."""
        cat = category or VideoCategory.NATURALEZA

        if not query:
            queries = SEARCH_QUERIES.get(cat, ["#shorts peru", "reacciones"])
            query = random.choice(queries)

        raw_results = await self._ytdlp_search(query, limit=limit)

        results: list[VideoResult] = []
        for raw in raw_results:
            parsed = self._parse_result(raw, cat)
            if parsed:
                results.append(parsed)

        self.logger.info("YouTube CC search '%s': found %d videos", query, len(results))
        return results

    async def random(
        self, category: Optional[VideoCategory] = None
    ) -> Optional[VideoResult]:
        """Get a random video."""
        cat = category or random.choice(list(SEARCH_QUERIES.keys()))
        results = await self.search(category=cat, limit=30)
        return random.choice(results) if results else None

    async def next_video(self) -> Optional[VideoResult]:
        """Get the next CC video from YouTube."""
        return await self.random()

    async def validate_video(self, video: VideoResult) -> bool:
        """Fetch the direct stream URL right before playback."""
        direct_url = await self._get_direct_url(video.url)
        if direct_url:
            video.url = direct_url
            return True
        return False
