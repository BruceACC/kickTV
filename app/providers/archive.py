"""
KickTV — Internet Archive Provider

Fetches public-domain videos from the Internet Archive.
Uses the IA Advanced Search API and the metadata API.
"""

from __future__ import annotations

import random
from typing import Optional

import aiohttp

from app.models import ProviderName, VideoCategory, VideoResult
from app.providers.base import BaseProvider, generate_video_id

IA_SEARCH_URL = "https://archive.org/advancedsearch.php"
IA_METADATA_URL = "https://archive.org/metadata"
IA_DOWNLOAD_URL = "https://archive.org/download"

# Map categories to Archive.org collections and search terms
CATEGORY_COLLECTIONS: dict[VideoCategory, dict] = {
    VideoCategory.PELICULAS_CLASICAS: {
        "collection": "feature_films",
        "query": "mediatype:movies",
    },
    VideoCategory.DOCUMENTALES: {
        "collection": "documentaries",
        "query": "mediatype:movies AND subject:documentary",
    },
    VideoCategory.TERROR: {
        "collection": "feature_films",
        "query": 'mediatype:movies AND subject:(horror OR scary)',
    },
    VideoCategory.CIENCIA: {
        "collection": "prelinger",
        "query": "mediatype:movies AND subject:science",
    },
    VideoCategory.NATURALEZA: {
        "collection": "prelinger",
        "query": "mediatype:movies AND subject:nature",
    },
    VideoCategory.ESPACIO: {
        "collection": "nasa",
        "query": "mediatype:movies AND subject:(space OR NASA)",
    },
}

# Default query for categories without specific collections
DEFAULT_IA_QUERY = "mediatype:movies AND NOT collection:test_collection"


class ArchiveProvider(BaseProvider):
    """Fetches public-domain videos from the Internet Archive."""

    name = ProviderName.ARCHIVE
    display_name = "Internet Archive"
    description = "Public domain videos from archive.org"
    requires_api_key = False

    def __init__(self) -> None:
        super().__init__()
        self._page_cache: dict[str, int] = {}

    async def _search_items(
        self, query: str, rows: int = 10, page: int = 1
    ) -> list[dict]:
        """Search the Internet Archive Advanced Search API."""
        params = {
            "q": query,
            "fl[]": ["identifier", "title", "creator", "description", "runtime"],
            "sort[]": "downloads desc",
            "rows": rows,
            "page": page,
            "output": "json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    IA_SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        docs = data.get("response", {}).get("docs", [])
                        return docs
                    else:
                        self.logger.error("IA search error: %d", resp.status)
                        return []
        except Exception as e:
            self.logger.error("IA search failed: %s", e)
            return []

    async def _get_video_url(self, identifier: str) -> Optional[str]:
        """Get the best video file URL for an Archive.org item."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{IA_METADATA_URL}/{identifier}",
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
        except Exception as e:
            self.logger.error("IA metadata failed for %s: %s", identifier, e)
            return None

        files = data.get("files", [])
        # Prefer MP4, then h.264, then MPEG4
        mp4_files = [
            f for f in files
            if f.get("format", "").upper() in ("MPEG4", "H.264", "512KB MPEG4")
            and f.get("name", "").lower().endswith((".mp4", ".m4v"))
        ]
        if not mp4_files:
            # Fallback: any video format
            mp4_files = [
                f for f in files
                if f.get("name", "").lower().endswith((".mp4", ".avi", ".mkv", ".ogv"))
            ]
        if not mp4_files:
            return None

        # Pick the largest file (usually best quality)
        best = max(mp4_files, key=lambda f: int(f.get("size", "0") or "0"))
        filename = best["name"]
        return f"{IA_DOWNLOAD_URL}/{identifier}/{filename}"

    def _parse_runtime(self, runtime: str) -> int:
        """Parse runtime string (e.g., '1:23:45' or '45:12') to seconds."""
        if not runtime:
            return 0
        parts = runtime.strip().split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            else:
                return int(float(parts[0]))
        except (ValueError, IndexError):
            return 0

    async def _item_to_result(
        self, item: dict, category: VideoCategory
    ) -> Optional[VideoResult]:
        """Convert an IA search result to a VideoResult with resolved video URL."""
        identifier = item.get("identifier", "")
        if not identifier:
            return None

        video_url = await self._get_video_url(identifier)
        if not video_url:
            return None

        runtime = item.get("runtime", "")
        creator = item.get("creator", "")
        if isinstance(creator, list):
            creator = creator[0] if creator else "Unknown"

        return VideoResult(
            url=video_url,
            title=item.get("title", identifier).strip(),
            duration=self._parse_runtime(str(runtime)),
            author=str(creator) or "Internet Archive",
            category=category,
            provider=ProviderName.ARCHIVE,
            description=str(item.get("description", ""))[:200],
            video_id=generate_video_id("archive", identifier),
            license="Public Domain",
        )

    async def search(
        self,
        query: str = "",
        category: Optional[VideoCategory] = None,
        limit: int = 5,
    ) -> list[VideoResult]:
        """Search Internet Archive for videos."""
        cat = category or VideoCategory.PELICULAS_CLASICAS

        if query:
            ia_query = f"mediatype:movies AND ({query})"
        else:
            cat_config = CATEGORY_COLLECTIONS.get(cat)
            if cat_config:
                ia_query = cat_config["query"]
            else:
                keywords = self.get_keywords(cat)
                keyword = random.choice(keywords)
                ia_query = f"mediatype:movies AND ({keyword})"

        page_key = ia_query[:50]
        page = self._page_cache.get(page_key, 1)

        items = await self._search_items(ia_query, rows=limit * 2, page=page)
        self._page_cache[page_key] = page + 1

        results: list[VideoResult] = []
        for item in items:
            if len(results) >= limit:
                break
            result = await self._item_to_result(item, cat)
            if result:
                results.append(result)

        self.logger.info("Archive search: found %d videos", len(results))
        return results

    async def random(
        self, category: Optional[VideoCategory] = None
    ) -> Optional[VideoResult]:
        """Get a random video from the Internet Archive."""
        cat = category or random.choice(
            [VideoCategory.PELICULAS_CLASICAS, VideoCategory.DOCUMENTALES, VideoCategory.CIENCIA]
        )
        results = await self.search(category=cat, limit=5)
        return random.choice(results) if results else None

    async def next_video(self) -> Optional[VideoResult]:
        """Get the next video from the Internet Archive."""
        return await self.random()
