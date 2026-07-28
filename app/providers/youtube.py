"""
KickTV — YouTube Provider

Uses YouTube Data API v3 for searching videos to improve speed and stability,
and yt-dlp to extract the direct stream URL before playback.
Implements category-based caching to minimize API quota usage.
"""

from __future__ import annotations

import asyncio
import random
import aiohttp
from typing import Optional

from app.config import settings
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
    Fetches Creative Commons licensed videos using YouTube Data API v3.
    Caches 50 results per search to minimize quota usage.
    """

    name = ProviderName.YOUTUBE
    display_name = "YouTube API"
    description = "Creative Commons videos via Official API"
    requires_api_key = True

    def __init__(self) -> None:
        super().__init__()
        self._enabled = settings.provider_youtube_enabled
        self._api_key = settings.youtube_api_key
        
        # Cache per category to save API quota
        self._cache: dict[VideoCategory, list[VideoResult]] = {cat: [] for cat in VideoCategory}

    async def _api_search(self, query: str, category: VideoCategory, limit: int = 50) -> list[VideoResult]:
        """Run search using official YouTube API."""
        if not self._api_key:
            self.logger.error("YouTube API Key missing")
            return []
            
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "videoLicense": "creativeCommon",
            "maxResults": str(limit),
            "key": self._api_key,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        self.logger.error("YouTube API Error %d: %s", resp.status, text)
                        return []
                    data = await resp.json()
                    
            results: list[VideoResult] = []
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                video_id = item.get("id", {}).get("videoId")
                if not video_id:
                    continue
                    
                res = VideoResult(
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    title=snippet.get("title", "YouTube Video"),
                    duration=0,  # Data API search doesn't return duration.
                    author=snippet.get("channelTitle", "YouTube"),
                    category=category,
                    provider=ProviderName.YOUTUBE,
                    thumbnail=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                    video_id=generate_video_id("youtube", video_id),
                    license="Creative Commons"
                )
                results.append(res)
            return results
        except Exception as e:
            self.logger.error("YouTube API Request failed: %s", e)
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

    async def search(
        self,
        query: str = "",
        category: Optional[VideoCategory] = None,
        limit: int = 50,
    ) -> list[VideoResult]:
        """Search YouTube using API."""
        cat = category or VideoCategory.NATURALEZA

        if not query:
            queries = SEARCH_QUERIES.get(cat, ["#shorts peru"])
            query = random.choice(queries)

        results = await self._api_search(query, cat, limit=limit)
        self.logger.info("YouTube API search '%s': found %d videos", query, len(results))
        return results

    async def random(
        self, category: Optional[VideoCategory] = None
    ) -> Optional[VideoResult]:
        """Get a random video using cached API results to save quota."""
        cat = category or random.choice(list(SEARCH_QUERIES.keys()))
        
        # 1. If cache for this category is empty, fetch 50 new videos via API
        if not self._cache.get(cat):
            self.logger.info("YouTube cache empty for %s, fetching from API...", cat.value)
            results = await self.search(category=cat, limit=50)
            if results:
                # Shuffle the batch so they play in random order
                random.shuffle(results)
                self._cache[cat] = results
                
        # 2. Pop one video from the cache
        if self._cache.get(cat):
            return self._cache[cat].pop()
            
        return None

    async def next_video(self) -> Optional[VideoResult]:
        """Get the next video."""
        return await self.random()

    async def validate_video(self, video: VideoResult) -> bool:
        """Fetch the direct stream URL right before playback."""
        direct_url = await self._get_direct_url(video.url)
        if direct_url:
            video.url = direct_url
            return True
        return False
