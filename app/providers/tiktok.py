"""
KickTV — TikTok Provider

Uses TikTok's oEmbed API for metadata and yt-dlp for video discovery
and local download. No authentication required.

Discovery strategy:
  - Curated hashtag/profile URLs per category
  - yt-dlp --flat-playlist to extract video URLs from hashtag pages
  - oEmbed API for metadata (title, author, thumbnail)
  - Local download before playback (same as YouTube provider)
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Optional

import aiohttp

from app.config import settings
from app.models import ProviderName, VideoCategory, VideoResult
from app.providers.base import BaseProvider, generate_video_id


# ── Curated TikTok sources by category ────────────────────────

TIKTOK_SOURCES: dict[VideoCategory, list[str]] = {
    VideoCategory.HUMOR: [
        "https://www.tiktok.com/tag/humor",
        "https://www.tiktok.com/tag/comedia",
        "https://www.tiktok.com/tag/chistes",
        "https://www.tiktok.com/tag/risa",
    ],
    VideoCategory.MEMES: [
        "https://www.tiktok.com/tag/memes",
        "https://www.tiktok.com/tag/memesespanol",
        "https://www.tiktok.com/tag/memesviral",
    ],
    VideoCategory.GAMING: [
        "https://www.tiktok.com/tag/gaming",
        "https://www.tiktok.com/tag/gamer",
        "https://www.tiktok.com/tag/gamingclips",
    ],
    VideoCategory.CURIOSIDADES: [
        "https://www.tiktok.com/tag/curiosidades",
        "https://www.tiktok.com/tag/sabíasque",
        "https://www.tiktok.com/tag/datoscuriosos",
    ],
    VideoCategory.ASOMBRO: [
        "https://www.tiktok.com/tag/satisfying",
        "https://www.tiktok.com/tag/increíble",
        "https://www.tiktok.com/tag/amazing",
    ],
    VideoCategory.MUSICA: [
        "https://www.tiktok.com/tag/musica",
        "https://www.tiktok.com/tag/musicaenvivo",
        "https://www.tiktok.com/tag/cover",
    ],
    VideoCategory.ANIMALES: [
        "https://www.tiktok.com/tag/mascotas",
        "https://www.tiktok.com/tag/animalesgraciosos",
        "https://www.tiktok.com/tag/pets",
    ],
    VideoCategory.TECNOLOGIA: [
        "https://www.tiktok.com/tag/tech",
        "https://www.tiktok.com/tag/tecnologia",
        "https://www.tiktok.com/tag/gadgets",
    ],
    VideoCategory.SUSPENSO: [
        "https://www.tiktok.com/tag/terror",
        "https://www.tiktok.com/tag/misterio",
        "https://www.tiktok.com/tag/suspenso",
    ],
}

# Hashtag keywords → category mapping for auto-classification
HASHTAG_CATEGORY_MAP: dict[str, VideoCategory] = {
    "humor": VideoCategory.HUMOR,
    "comedia": VideoCategory.HUMOR,
    "chistes": VideoCategory.HUMOR,
    "risa": VideoCategory.HUMOR,
    "funny": VideoCategory.HUMOR,
    "memes": VideoCategory.MEMES,
    "meme": VideoCategory.MEMES,
    "gaming": VideoCategory.GAMING,
    "gamer": VideoCategory.GAMING,
    "curiosidades": VideoCategory.CURIOSIDADES,
    "datos": VideoCategory.CURIOSIDADES,
    "satisfying": VideoCategory.ASOMBRO,
    "amazing": VideoCategory.ASOMBRO,
    "increible": VideoCategory.ASOMBRO,
    "musica": VideoCategory.MUSICA,
    "music": VideoCategory.MUSICA,
    "dance": VideoCategory.MUSICA,
    "mascotas": VideoCategory.ANIMALES,
    "pets": VideoCategory.ANIMALES,
    "animales": VideoCategory.ANIMALES,
    "tech": VideoCategory.TECNOLOGIA,
    "tecnologia": VideoCategory.TECNOLOGIA,
    "terror": VideoCategory.SUSPENSO,
    "misterio": VideoCategory.SUSPENSO,
    "suspenso": VideoCategory.SUSPENSO,
}


class TikTokProvider(BaseProvider):
    """
    TikTok content provider using oEmbed API + yt-dlp.

    Flow:
      1. Discovery: yt-dlp --flat-playlist on hashtag pages → list of video URLs
      2. Metadata: TikTok oEmbed API → title, author, thumbnail
      3. Playback: yt-dlp local download → temp file → FFmpeg
    """

    name = ProviderName.TIKTOK
    display_name = "TikTok"
    description = "Public TikTok videos via oEmbed API"
    requires_api_key = False

    def __init__(self) -> None:
        super().__init__()
        self._enabled = settings.provider_tiktok_enabled
        # Cache per category to avoid repeated yt-dlp calls
        self._cache: dict[VideoCategory, list[VideoResult]] = {
            cat: [] for cat in VideoCategory
        }
        self._discovery_lock = asyncio.Lock()

    # ── oEmbed metadata ───────────────────────────────────────

    async def _get_oembed(self, video_url: str) -> Optional[dict]:
        """Fetch metadata from TikTok's oEmbed API."""
        oembed_url = "https://www.tiktok.com/oembed"
        params = {"url": video_url}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    oembed_url, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        self.logger.debug(
                            "TikTok oEmbed returned %d for %s", resp.status, video_url
                        )
                        return None
        except Exception as e:
            self.logger.debug("TikTok oEmbed error: %s", e)
            return None

    # ── Video discovery via yt-dlp ────────────────────────────

    async def _discover_videos(
        self, source_url: str, limit: int = 20
    ) -> list[str]:
        """
        Use yt-dlp --flat-playlist to extract video URLs from a
        TikTok hashtag or profile page.
        """
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--print", "url",
            "--playlist-end", str(limit),
            "--no-warnings",
            "--quiet",
            source_url,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)

            urls = []
            for line in stdout.decode("utf-8", errors="ignore").strip().split("\n"):
                line = line.strip()
                if line and "tiktok.com" in line:
                    urls.append(line)

            self.logger.info(
                "TikTok discovery from %s: found %d videos",
                source_url.split("/")[-1],
                len(urls),
            )
            return urls

        except asyncio.TimeoutError:
            self.logger.warning("TikTok discovery timed out for %s", source_url)
            return []
        except Exception as e:
            self.logger.error("TikTok discovery error: %s", e)
            return []

    # ── Auto-classify by hashtags ─────────────────────────────

    def _classify_video(self, title: str, fallback: VideoCategory) -> VideoCategory:
        """Classify a video based on hashtags in the title."""
        title_lower = title.lower()
        for keyword, category in HASHTAG_CATEGORY_MAP.items():
            if keyword in title_lower:
                return category
        return fallback

    # ── Local download ────────────────────────────────────────

    async def _download_video(self, video_url: str) -> Optional[str]:
        """Download TikTok video locally using yt-dlp."""
        cache_dir = settings.abs_video_cache_dir / "tiktok_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        file_path = cache_dir / "temp_tiktok.mp4"

        # Delete previous temp file
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass

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
            self.logger.info("Downloading TikTok video locally...")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=120)

            if file_path.exists():
                return str(file_path).replace("\\", "/")
            return None

        except asyncio.TimeoutError:
            self.logger.error("TikTok download timed out")
            if "proc" in locals():
                try:
                    proc.kill()
                except Exception:
                    pass
            return None
        except Exception as e:
            self.logger.error("TikTok download failed: %s", e)
            return None

    # ── Provider interface ────────────────────────────────────

    async def search(
        self,
        query: str = "",
        category: Optional[VideoCategory] = None,
        limit: int = 20,
    ) -> list[VideoResult]:
        """
        Search for TikTok videos by discovering URLs from hashtag pages
        and enriching them with oEmbed metadata.
        """
        cat = category or random.choice(list(TIKTOK_SOURCES.keys()))
        sources = TIKTOK_SOURCES.get(cat, list(TIKTOK_SOURCES.values())[0])
        source_url = random.choice(sources)

        # Discover video URLs
        video_urls = await self._discover_videos(source_url, limit=limit)
        if not video_urls:
            self.logger.warning("No TikTok videos found for %s", cat.value)
            return []

        # Fetch metadata for each video via oEmbed
        results: list[VideoResult] = []
        for url in video_urls:
            oembed = await self._get_oembed(url)

            title = "TikTok Video"
            author = "TikTok"
            thumbnail = ""

            if oembed:
                title = oembed.get("title", title)
                author = oembed.get("author_name", author)
                thumbnail = oembed.get("thumbnail_url", "")

            # Auto-classify based on hashtags in title
            video_cat = self._classify_video(title, cat)

            result = VideoResult(
                url=url,
                title=title[:100],  # Truncate long TikTok descriptions
                duration=0,  # TikTok oEmbed doesn't provide duration
                author=author,
                category=video_cat,
                provider=ProviderName.TIKTOK,
                thumbnail=thumbnail,
                video_id=generate_video_id("tiktok", url),
            )
            results.append(result)

            # Small delay to avoid rate-limiting oEmbed
            await asyncio.sleep(0.2)

        self.logger.info(
            "TikTok search for '%s': enriched %d videos", cat.value, len(results)
        )
        return results

    async def random(
        self, category: Optional[VideoCategory] = None
    ) -> Optional[VideoResult]:
        """Get a random TikTok video using cached results."""
        cat = category or random.choice(list(TIKTOK_SOURCES.keys()))

        # If cache is empty, fetch new batch
        if not self._cache.get(cat):
            async with self._discovery_lock:
                # Double-check after acquiring lock
                if not self._cache.get(cat):
                    self.logger.info(
                        "TikTok cache empty for %s, discovering...", cat.value
                    )
                    results = await self.search(category=cat, limit=20)
                    if results:
                        random.shuffle(results)
                        self._cache[cat] = results

        # Pop one from cache
        if self._cache.get(cat):
            return self._cache[cat].pop()

        return None

    async def next_video(self) -> Optional[VideoResult]:
        """Get the next TikTok video."""
        return await self.random()

    async def validate_video(self, video: VideoResult) -> bool:
        """Download video locally before playback to avoid streaming lag."""
        local_path = await self._download_video(video.url)
        if local_path:
            video.url = local_path
            return True
        return False
