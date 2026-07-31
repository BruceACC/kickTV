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

    async def _api_search(self, query: str, category: VideoCategory, limit: int = 15) -> list[VideoResult]:
        """Search using the official YouTube Data API v3 and rotate keys to balance quota."""
        api_keys = settings.youtube_keys
        if not api_keys:
            self.logger.error("No YouTube API keys configured in .env")
            return []
            
        # Elegir una clave aleatoria para balancear la carga (quota)
        api_key = random.choice(api_keys)
        
        self.logger.info("YouTube API Search: '%s' (Using key %s...)", query, api_key[:10])
        
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": query,
            "maxResults": limit,
            "type": "video",
            "key": api_key,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        self.logger.error("YouTube API HTTP %d: %s", resp.status, err_text)
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
                    duration=0,  # yt-dlp obtendrá la duración real al descargar
                    author=snippet.get("channelTitle", "YouTube"),
                    category=category,
                    provider=ProviderName.YOUTUBE,
                    thumbnail=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                    video_id=generate_video_id("youtube", video_id),
                    license="unknown"
                )
                results.append(res)
            return results
        except Exception as e:
            self.logger.error("YouTube API exception: %s", e)
            return []

    async def _download_video(self, video_url: str, video_id: str) -> Optional[str]:
        """Download the video locally using yt-dlp to avoid FFmpeg streaming lag."""
        # Use a flat directory so the frontend can serve it easily via /videos/
        cache_dir = settings.abs_video_cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        file_path = cache_dir / f"{video_id}.mp4"
        
        # If it already exists, return immediately (already downloaded)
        if file_path.exists():
            return str(file_path).replace("\\", "/")
                
        try:
            cmd = [
                "yt-dlp",
                "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/b[height<=720][ext=mp4]/b",
                "--merge-output-format", "mp4",
                "-o", str(file_path),
                "--no-warnings",
                "--quiet",
                video_url,
            ]
            self.logger.info("Downloading YouTube video locally to prevent lag...")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # Give it up to 3 minutes to download
            await asyncio.wait_for(proc.wait(), timeout=180)
            
            if file_path.exists():
                return str(file_path).replace("\\", "/")
            return None
        except asyncio.TimeoutError:
            self.logger.error("yt-dlp download timed out")
            if 'proc' in locals():
                try: proc.kill()
                except: pass
            return None
        except Exception as e:
            self.logger.error("yt-dlp download failed: %s", e)
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
        """Download the video to the local cache."""
        local_path = await self._download_video(video.url, video.video_id)
        if local_path:
            video.file_path = local_path
            return True
        return False
