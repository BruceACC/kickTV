"""
KickTV — Pexels Provider

Fetches free stock videos from the Pexels API.
API docs: https://www.pexels.com/api/documentation/
"""

from __future__ import annotations

import random
from typing import Optional

import aiohttp

from app.config import settings
from app.models import ProviderName, VideoCategory, VideoResult
from app.providers.base import BaseProvider, generate_video_id

PEXELS_API_BASE = "https://api.pexels.com/videos"


class PexelsProvider(BaseProvider):
    """Fetches videos from the Pexels free stock video API."""

    name = ProviderName.PEXELS
    display_name = "Pexels"
    description = "Free stock videos from Pexels.com"
    requires_api_key = True

    def __init__(self) -> None:
        super().__init__()
        self._api_key = settings.pexels_api_key
        self._page_cache: dict[str, int] = {}  # track pages per query

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self._api_key}

    async def _fetch(
        self, endpoint: str, params: dict
    ) -> Optional[dict]:
        """Make a request to the Pexels API."""
        if not self.has_api_key:
            self.logger.warning("Pexels API key not configured")
            return None

        url = f"{PEXELS_API_BASE}/{endpoint}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=self._headers(), params=params, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        self.logger.error("Pexels API error: %d %s", resp.status, await resp.text())
                        return None
        except Exception as e:
            self.logger.error("Pexels request failed: %s", e)
            return None

    def _parse_video(self, raw: dict, category: VideoCategory) -> Optional[VideoResult]:
        """Parse a Pexels API video object into VideoResult."""
        video_files = raw.get("video_files", [])
        if not video_files:
            return None

        # Prefer HD quality
        best_file = None
        for vf in video_files:
            quality = vf.get("quality", "")
            width = vf.get("width", 0)
            if quality == "hd" and width >= 1280:
                best_file = vf
                break
        if not best_file:
            # Fallback to any file with reasonable resolution
            for vf in sorted(video_files, key=lambda x: x.get("width", 0), reverse=True):
                if vf.get("width", 0) >= 640:
                    best_file = vf
                    break
        if not best_file and video_files:
            best_file = video_files[0]
        if not best_file:
            return None

        video_url = best_file.get("link", "")
        if not video_url:
            return None

        user = raw.get("user", {})
        return VideoResult(
            url=video_url,
            title=raw.get("url", "").split("/")[-2].replace("-", " ").title() if raw.get("url") else "Pexels Video",
            duration=raw.get("duration", 0),
            author=user.get("name", "Pexels"),
            category=category,
            provider=ProviderName.PEXELS,
            thumbnail=raw.get("image", ""),
            video_id=generate_video_id("pexels", str(raw.get("id", ""))),
            license="Pexels License",
        )

    async def search(
        self,
        query: str = "",
        category: Optional[VideoCategory] = None,
        limit: int = 10,
    ) -> list[VideoResult]:
        """Search Pexels for videos."""
        cat = category or VideoCategory.NATURALEZA
        if not query:
            keywords = self.get_keywords(cat)
            query = random.choice(keywords)

        # Rotate pages to get variety
        page_key = query
        page = self._page_cache.get(page_key, 1)

        data = await self._fetch("search", {
            "query": query,
            "per_page": min(limit, 15),
            "page": page,
            "size": "medium",
        })

        if not data:
            return []

        # Update page for next call
        total_pages = (data.get("total_results", 0) // 15) + 1
        self._page_cache[page_key] = (page % max(total_pages, 1)) + 1

        results: list[VideoResult] = []
        for raw_video in data.get("videos", []):
            parsed = self._parse_video(raw_video, cat)
            if parsed:
                results.append(parsed)

        self.logger.info("Pexels search '%s': found %d videos", query, len(results))
        return results

    async def random(
        self, category: Optional[VideoCategory] = None
    ) -> Optional[VideoResult]:
        """Get a random video from Pexels."""
        cat = category or random.choice(list(VideoCategory))
        keywords = self.get_keywords(cat)
        query = random.choice(keywords)

        data = await self._fetch("search", {
            "query": query,
            "per_page": 15,
            "page": random.randint(1, 5),
        })

        if not data or not data.get("videos"):
            return None

        raw = random.choice(data["videos"])
        return self._parse_video(raw, cat)

    async def next_video(self) -> Optional[VideoResult]:
        """Get the next video from Pexels using random category rotation."""
        return await self.random()
