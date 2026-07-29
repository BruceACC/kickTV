"""
KickTV — Instagram Provider

Uses Instagram's oEmbed API for basic metadata and yt-dlp with cookies
for Reels discovery and local download.

Requirements:
  - Instagram cookies exported from browser (cookies.txt format)
  - yt-dlp installed with FFmpeg

Note: If no cookies file is configured, the provider auto-disables
with a warning log. This ensures the system never breaks.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Optional

import aiohttp

from app.config import settings
from app.models import ProviderName, VideoCategory, VideoResult
from app.providers.base import BaseProvider, generate_video_id


# ── Curated Instagram Reels profiles by category ─────────────

INSTAGRAM_SOURCES: dict[VideoCategory, list[str]] = {
    VideoCategory.HUMOR: [
        "https://www.instagram.com/humor.global/reels/",
        "https://www.instagram.com/comedy/reels/",
    ],
    VideoCategory.MEMES: [
        "https://www.instagram.com/memes/reels/",
        "https://www.instagram.com/memezar/reels/",
    ],
    VideoCategory.GAMING: [
        "https://www.instagram.com/gaming/reels/",
        "https://www.instagram.com/gamingclips/reels/",
    ],
    VideoCategory.ANIMALES: [
        "https://www.instagram.com/animals/reels/",
        "https://www.instagram.com/cute.pets/reels/",
    ],
    VideoCategory.MUSICA: [
        "https://www.instagram.com/music/reels/",
        "https://www.instagram.com/songs/reels/",
    ],
    VideoCategory.ASOMBRO: [
        "https://www.instagram.com/satisfying/reels/",
        "https://www.instagram.com/oddlysatisfying/reels/",
    ],
    VideoCategory.CURIOSIDADES: [
        "https://www.instagram.com/facts/reels/",
        "https://www.instagram.com/didyouknow/reels/",
    ],
    VideoCategory.TECNOLOGIA: [
        "https://www.instagram.com/tech/reels/",
        "https://www.instagram.com/gadgets/reels/",
    ],
}

# Keywords in title/description → category mapping
KEYWORD_CATEGORY_MAP: dict[str, VideoCategory] = {
    "funny": VideoCategory.HUMOR,
    "comedy": VideoCategory.HUMOR,
    "laugh": VideoCategory.HUMOR,
    "meme": VideoCategory.MEMES,
    "gaming": VideoCategory.GAMING,
    "gamer": VideoCategory.GAMING,
    "pet": VideoCategory.ANIMALES,
    "animal": VideoCategory.ANIMALES,
    "dog": VideoCategory.ANIMALES,
    "cat": VideoCategory.ANIMALES,
    "music": VideoCategory.MUSICA,
    "dance": VideoCategory.MUSICA,
    "song": VideoCategory.MUSICA,
    "satisfying": VideoCategory.ASOMBRO,
    "amazing": VideoCategory.ASOMBRO,
    "fact": VideoCategory.CURIOSIDADES,
    "tech": VideoCategory.TECNOLOGIA,
}


class InstagramProvider(BaseProvider):
    """
    Instagram Reels provider using oEmbed API + yt-dlp with cookies.

    Flow:
      1. Check: Verify cookies file exists, auto-disable if not
      2. Discovery: yt-dlp --flat-playlist --cookies on Reels pages
      3. Metadata: Instagram oEmbed API (limited fields)
      4. Playback: yt-dlp --cookies local download → temp file → FFmpeg
    """

    name = ProviderName.INSTAGRAM
    display_name = "Instagram Reels"
    description = "Public Instagram Reels via oEmbed API"
    requires_api_key = False  # Needs cookies, not an API key

    def __init__(self) -> None:
        super().__init__()
        self._enabled = settings.provider_instagram_enabled
        self._cookies_file = settings.instagram_cookies_file
        self._cache: dict[VideoCategory, list[VideoResult]] = {
            cat: [] for cat in VideoCategory
        }
        self._discovery_lock = asyncio.Lock()

        # Auto-disable if no cookies configured
        if self._enabled and not self._has_valid_cookies():
            self.logger.warning(
                "Instagram provider disabled: no cookies file configured. "
                "Set INSTAGRAM_COOKIES_FILE in .env to enable."
            )
            self._enabled = False

    def _has_valid_cookies(self) -> bool:
        """Check if a valid cookies file is configured and exists."""
        if not self._cookies_file:
            return False
        cookies_path = Path(self._cookies_file)
        if not cookies_path.is_absolute():
            from app.config import BASE_DIR
            cookies_path = BASE_DIR / cookies_path
        return cookies_path.exists()

    def _get_cookies_path(self) -> str:
        """Get absolute path to cookies file."""
        cookies_path = Path(self._cookies_file)
        if not cookies_path.is_absolute():
            from app.config import BASE_DIR
            cookies_path = BASE_DIR / cookies_path
        return str(cookies_path)

    # ── oEmbed metadata ───────────────────────────────────────

    async def _get_oembed(self, video_url: str) -> Optional[dict]:
        """
        Fetch metadata from Instagram's oEmbed API.
        Note: As of Nov 2025, author_name and thumbnail_url are deprecated.
        """
        oembed_url = "https://graph.facebook.com/v22.0/instagram_oembed"
        params = {"url": video_url, "omitscript": "true"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    oembed_url, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        self.logger.debug(
                            "Instagram oEmbed returned %d for %s", resp.status, video_url
                        )
                        return None
        except Exception as e:
            self.logger.debug("Instagram oEmbed error: %s", e)
            return None

    # ── Video discovery via yt-dlp ────────────────────────────

    async def _discover_videos(
        self, source_url: str, limit: int = 15
    ) -> list[str]:
        """
        Use yt-dlp --flat-playlist with cookies to extract Reel URLs.
        """
        cookies_path = self._get_cookies_path()

        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--print", "url",
            "--playlist-end", str(limit),
            "--cookies", cookies_path,
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
                if line and "instagram.com" in line:
                    urls.append(line)

            self.logger.info(
                "Instagram discovery: found %d Reels from %s",
                len(urls),
                source_url.split("/")[-2] if "/" in source_url else source_url,
            )
            return urls

        except asyncio.TimeoutError:
            self.logger.warning("Instagram discovery timed out for %s", source_url)
            return []
        except Exception as e:
            self.logger.error("Instagram discovery error: %s", e)
            return []

    # ── Auto-classify ─────────────────────────────────────────

    def _classify_video(self, title: str, fallback: VideoCategory) -> VideoCategory:
        """Classify video based on keywords in the title."""
        title_lower = title.lower()
        for keyword, category in KEYWORD_CATEGORY_MAP.items():
            if keyword in title_lower:
                return category
        return fallback

    # ── Local download ────────────────────────────────────────

    async def _download_video(self, video_url: str) -> Optional[str]:
        """Download Instagram Reel locally using yt-dlp with cookies."""
        cache_dir = settings.abs_video_cache_dir / "ig_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        file_path = cache_dir / "temp_ig.mp4"

        # Delete previous temp file
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass

        cookies_path = self._get_cookies_path()

        try:
            cmd = [
                "yt-dlp",
                "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/b[height<=720][ext=mp4]/b",
                "--merge-output-format", "mp4",
                "--cookies", cookies_path,
                "-o", str(file_path),
                "--no-warnings",
                "--quiet",
                video_url,
            ]
            self.logger.info("Downloading Instagram Reel locally...")
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
            self.logger.error("Instagram download timed out")
            if "proc" in locals():
                try:
                    proc.kill()
                except Exception:
                    pass
            return None
        except Exception as e:
            self.logger.error("Instagram download failed: %s", e)
            return None

    # ── Provider interface ────────────────────────────────────

    async def search(
        self,
        query: str = "",
        category: Optional[VideoCategory] = None,
        limit: int = 15,
    ) -> list[VideoResult]:
        """Search for Instagram Reels by discovering URLs from profile pages."""
        cat = category or random.choice(list(INSTAGRAM_SOURCES.keys()))
        sources = INSTAGRAM_SOURCES.get(cat, list(INSTAGRAM_SOURCES.values())[0])
        source_url = random.choice(sources)

        # Discover Reel URLs
        video_urls = await self._discover_videos(source_url, limit=limit)
        if not video_urls:
            self.logger.warning("No Instagram Reels found for %s", cat.value)
            return []

        # Enrich with oEmbed metadata
        results: list[VideoResult] = []
        for url in video_urls:
            oembed = await self._get_oembed(url)

            title = "Instagram Reel"
            author = "Instagram"

            if oembed:
                # title field from oEmbed is usually the embed HTML title
                title = oembed.get("title", title)
                # author_name is deprecated but may still work for some
                author = oembed.get("author_name", author)

            video_cat = self._classify_video(title, cat)

            result = VideoResult(
                url=url,
                title=title[:100],
                duration=0,
                author=author,
                category=video_cat,
                provider=ProviderName.INSTAGRAM,
                video_id=generate_video_id("instagram", url),
            )
            results.append(result)

            await asyncio.sleep(0.3)  # Rate limit protection

        self.logger.info(
            "Instagram search for '%s': enriched %d Reels", cat.value, len(results)
        )
        return results

    async def random(
        self, category: Optional[VideoCategory] = None
    ) -> Optional[VideoResult]:
        """Get a random Instagram Reel using cached results."""
        cat = category or random.choice(list(INSTAGRAM_SOURCES.keys()))

        if not self._cache.get(cat):
            async with self._discovery_lock:
                if not self._cache.get(cat):
                    self.logger.info(
                        "Instagram cache empty for %s, discovering...", cat.value
                    )
                    results = await self.search(category=cat, limit=15)
                    if results:
                        random.shuffle(results)
                        self._cache[cat] = results

        if self._cache.get(cat):
            return self._cache[cat].pop()

        return None

    async def next_video(self) -> Optional[VideoResult]:
        """Get the next Instagram Reel."""
        return await self.random()

    async def validate_video(self, video: VideoResult) -> bool:
        """Download Reel locally before playback."""
        local_path = await self._download_video(video.url)
        if local_path:
            video.url = local_path
            return True
        return False
