"""
KickTV — Reddit Provider

Fetches publicly available video content from Reddit's public JSON API.
Only accesses content from subreddits with public video posts.
"""

from __future__ import annotations

import random
from typing import Optional

import aiohttp

from app.models import ProviderName, VideoCategory, VideoResult
from app.providers.base import BaseProvider, generate_video_id

REDDIT_BASE = "https://www.reddit.com"

# Map categories to relevant subreddits
CATEGORY_SUBREDDITS: dict[VideoCategory, list[str]] = {
    VideoCategory.NATURALEZA: ["NatureIsFuckingLit", "nature", "EarthPorn"],
    VideoCategory.ANIMALES: ["AnimalsBeingDerps", "aww", "NatureIsFuckingLit"],
    VideoCategory.ESPACIO: ["space", "Astronomy", "spaceporn"],
    VideoCategory.CIENCIA: ["science", "Physics", "chemicalreactiongifs"],
    VideoCategory.TECNOLOGIA: ["technology", "gadgets", "programming"],
    VideoCategory.GAMING: ["gaming", "GamePhysics", "pcgaming"],
    VideoCategory.MEMES: ["funny", "memes", "Unexpected"],
    VideoCategory.CURIOSIDADES: ["interestingasfuck", "Damnthatsinteresting", "todayilearned"],
    VideoCategory.TERROR: ["creepy", "oddlyterrifying"],
    VideoCategory.DOCUMENTALES: ["Documentaries", "mealtimevideos"],
    VideoCategory.SHORTS: ["TikTokCringe", "youtubehaiku"],
    VideoCategory.TRAILERS: ["movies", "trailers"],
    VideoCategory.PELICULAS_CLASICAS: ["classicfilms", "OldSchoolCool"],
}

USER_AGENT = "KickTV/1.0 (automated TV channel bot)"


class RedditProvider(BaseProvider):
    """Fetches video posts from Reddit's public JSON API."""

    name = ProviderName.REDDIT
    display_name = "Reddit"
    description = "Public video posts from Reddit"
    requires_api_key = False

    def __init__(self) -> None:
        super().__init__()
        self._used_posts: set[str] = set()

    async def _fetch_subreddit(
        self, subreddit: str, sort: str = "hot", limit: int = 25
    ) -> list[dict]:
        """Fetch posts from a subreddit's JSON API."""
        url = f"{REDDIT_BASE}/r/{subreddit}/{sort}.json"
        headers = {"User-Agent": USER_AGENT}
        params = {"limit": limit, "raw_json": 1}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        posts = data.get("data", {}).get("children", [])
                        return [p.get("data", {}) for p in posts]
                    else:
                        self.logger.error(
                            "Reddit API error for r/%s: %d", subreddit, resp.status
                        )
                        return []
        except Exception as e:
            self.logger.error("Reddit fetch failed for r/%s: %s", subreddit, e)
            return []

    def _extract_video_url(self, post: dict) -> Optional[str]:
        """Extract a usable video URL from a Reddit post."""
        # Reddit-hosted video (v.redd.it)
        media = post.get("media")
        if media and "reddit_video" in media:
            rv = media["reddit_video"]
            url = rv.get("fallback_url", "")
            if url:
                # Remove query params for cleaner URL
                return url.split("?")[0]

        # Direct video links
        url = post.get("url", "")
        if url and any(url.lower().endswith(ext) for ext in (".mp4", ".webm", ".mov")):
            return url

        return None

    def _parse_post(self, post: dict, category: VideoCategory) -> Optional[VideoResult]:
        """Convert a Reddit post into a VideoResult."""
        video_url = self._extract_video_url(post)
        if not video_url:
            return None

        post_id = post.get("id", "")
        if post_id in self._used_posts:
            return None

        # Get duration from reddit_video if available
        duration = 0
        media = post.get("media")
        if media and "reddit_video" in media:
            duration = media["reddit_video"].get("duration", 0)

        return VideoResult(
            url=video_url,
            title=post.get("title", "Reddit Video")[:100],
            duration=int(duration) if duration else 0,
            author=f"u/{post.get('author', 'unknown')}",
            category=category,
            provider=ProviderName.REDDIT,
            thumbnail=post.get("thumbnail", ""),
            video_id=generate_video_id("reddit", post_id),
            description=f"r/{post.get('subreddit', '')} • {post.get('score', 0)} upvotes",
        )

    async def search(
        self,
        query: str = "",
        category: Optional[VideoCategory] = None,
        limit: int = 10,
    ) -> list[VideoResult]:
        """Search Reddit for video posts by category."""
        cat = category or VideoCategory.CURIOSIDADES
        subreddits = CATEGORY_SUBREDDITS.get(cat, ["videos"])

        results: list[VideoResult] = []
        for subreddit in subreddits:
            if len(results) >= limit:
                break
            posts = await self._fetch_subreddit(subreddit, sort="hot", limit=25)
            for post in posts:
                if len(results) >= limit:
                    break
                # Filter: must be a video post
                if not post.get("is_video", False) and not self._extract_video_url(post):
                    continue
                # Filter by query if provided
                if query and query.lower() not in post.get("title", "").lower():
                    continue
                parsed = self._parse_post(post, cat)
                if parsed:
                    results.append(parsed)

        self.logger.info("Reddit search: found %d videos", len(results))
        return results

    async def random(
        self, category: Optional[VideoCategory] = None
    ) -> Optional[VideoResult]:
        """Get a random video post from Reddit."""
        cat = category or random.choice(list(CATEGORY_SUBREDDITS.keys()))
        subreddits = CATEGORY_SUBREDDITS.get(cat, ["videos"])
        subreddit = random.choice(subreddits)

        sort = random.choice(["hot", "top", "new"])
        posts = await self._fetch_subreddit(subreddit, sort=sort, limit=25)

        # Filter to video posts only
        video_posts = [
            p for p in posts
            if p.get("is_video") or self._extract_video_url(p)
        ]

        if not video_posts:
            return None

        post = random.choice(video_posts)
        result = self._parse_post(post, cat)

        if result:
            self._used_posts.add(post.get("id", ""))
            # Keep used set bounded
            if len(self._used_posts) > 500:
                self._used_posts = set(list(self._used_posts)[-250:])

        return result

    async def next_video(self) -> Optional[VideoResult]:
        """Get the next video from Reddit."""
        return await self.random()
