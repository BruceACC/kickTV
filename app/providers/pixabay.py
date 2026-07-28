"""
KickTV — Pixabay Provider

Fetches free stock videos from the Pixabay API.
API docs: https://pixabay.com/api/docs/
"""

from __future__ import annotations

import random
from typing import Optional

import aiohttp

from app.config import settings
from app.models import ProviderName, VideoCategory, VideoResult
from app.providers.base import BaseProvider, generate_video_id

PIXABAY_API_URL = "https://pixabay.com/api/videos/"


class PixabayProvider(BaseProvider):
    """Fetches videos from the Pixabay free stock video API."""

    name = ProviderName.PIXABAY
    display_name = "Pixabay"
    description = "Free stock videos from Pixabay.com"
    requires_api_key = True

    def __init__(self) -> None:
        super().__init__()
        self._api_key = settings.pixabay_api_key
        self._page_cache: dict[str, int] = {}

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    async def _fetch(self, params: dict) -> Optional[dict]:
        """Make a request to the Pixabay API."""
        if not self.has_api_key:
            self.logger.warning("Pixabay API key not configured")
            return None

        params["key"] = self._api_key
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    PIXABAY_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        self.logger.error("Pixabay API error: %d", resp.status)
                        return None
        except Exception as e:
            self.logger.error("Pixabay request failed: %s", e)
            return None

    def _parse_video(self, raw: dict, category: VideoCategory) -> Optional[VideoResult]:
        """Parse a Pixabay API video hit into a VideoResult."""
        videos = raw.get("videos", {})

        # Prefer large or medium quality
        video_data = videos.get("large") or videos.get("medium") or videos.get("small")
        if not video_data:
            return None

        video_url = video_data.get("url", "")
        if not video_url:
            return None

        return VideoResult(
            url=video_url,
            title=raw.get("tags", "Pixabay Video").replace(",", " -").title(),
            duration=raw.get("duration", 0),
            author=raw.get("user", "Pixabay"),
            category=category,
            provider=ProviderName.PIXABAY,
            thumbnail=raw.get("userImageURL", ""),
            video_id=generate_video_id("pixabay", str(raw.get("id", ""))),
            license="Pixabay License",
        )

    async def search(
        self,
        query: str = "",
        category: Optional[VideoCategory] = None,
        limit: int = 10,
    ) -> list[VideoResult]:
        """Search Pixabay for videos."""
        cat = category or VideoCategory.NATURALEZA
        if not query:
            keywords = self.get_keywords(cat)
            query = random.choice(keywords)

        page_key = query
        page = self._page_cache.get(page_key, 1)

        data = await self._fetch({
            "q": query,
            "per_page": min(limit, 20),
            "page": page,
            "video_type": "film",
            "safesearch": "true",
        })

        if not data:
            return []

        total_hits = data.get("totalHits", 0)
        total_pages = (total_hits // 20) + 1
        self._page_cache[page_key] = (page % max(total_pages, 1)) + 1

        results: list[VideoResult] = []
        for hit in data.get("hits", []):
            parsed = self._parse_video(hit, cat)
            if parsed:
                results.append(parsed)

        self.logger.info("Pixabay search '%s': found %d videos", query, len(results))
        return results

    async def random(
        self, category: Optional[VideoCategory] = None
    ) -> Optional[VideoResult]:
        """Get a random video from Pixabay."""
        cat = category or random.choice(list(VideoCategory))
        keywords = self.get_keywords(cat)
        query = random.choice(keywords)

        data = await self._fetch({
            "q": query,
            "per_page": 20,
            "page": random.randint(1, 3),
            "safesearch": "true",
        })

        if not data or not data.get("hits"):
            return None

        hit = random.choice(data["hits"])
        return self._parse_video(hit, cat)

    async def next_video(self) -> Optional[VideoResult]:
        """Get next video from Pixabay using random category."""
        return await self.random()
