"""
KickTV — Base Provider

Abstract base class that all content providers must implement.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Optional

from app.models import ProviderName, VideoCategory, VideoResult

logger = logging.getLogger("kicktv.providers")


# Mapping of categories to English search keywords
CATEGORY_KEYWORDS: dict[VideoCategory, list[str]] = {
    VideoCategory.TERROR: ["horror", "scary", "creepy", "haunted", "dark"],
    VideoCategory.CURIOSIDADES: ["curiosities", "facts", "interesting", "amazing", "unusual"],
    VideoCategory.DOCUMENTALES: ["documentary", "investigation", "history"],
    VideoCategory.NATURALEZA: ["nature", "landscape", "forest", "ocean", "mountain", "sunset"],
    VideoCategory.ANIMALES: ["animals", "wildlife", "pets", "dogs", "cats", "birds"],
    VideoCategory.GAMING: ["gaming", "videogames", "gameplay", "esports", "retro games"],
    VideoCategory.TECNOLOGIA: ["technology", "tech", "gadgets", "AI", "robots", "programming"],
    VideoCategory.ESPACIO: ["space", "universe", "NASA", "planets", "astronomy", "stars"],
    VideoCategory.PELICULAS_CLASICAS: ["classic film", "vintage movie", "public domain film", "old movie"],
    VideoCategory.MEMES: ["memes", "funny", "humor", "comedy", "viral", "laugh"],
    VideoCategory.SHORTS: ["short film", "clip", "short video", "micro film"],
    VideoCategory.TRAILERS: ["trailer", "movie trailer", "game trailer", "teaser", "preview"],
    VideoCategory.CIENCIA: ["science", "physics", "chemistry", "biology", "experiment", "lab"],
}


def generate_video_id(provider: str, url: str) -> str:
    """Generate a deterministic video ID from provider name and URL."""
    raw = f"{provider}:{url}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class BaseProvider(ABC):
    """
    Abstract base class for content providers.

    Each provider must implement:
      - search(query, category)  → search for videos matching a query/category
      - random(category)         → get a random video, optionally in a category
      - next_video()             → get the next video to play
    """

    name: ProviderName = ProviderName.LOCAL
    display_name: str = "Base Provider"
    description: str = ""
    requires_api_key: bool = False

    def __init__(self) -> None:
        self._enabled: bool = True
        self.logger = logging.getLogger(f"kicktv.providers.{self.name.value}")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        self.logger.info("Provider %s %s", self.name.value, "enabled" if value else "disabled")

    @abstractmethod
    async def search(
        self,
        query: str = "",
        category: Optional[VideoCategory] = None,
        limit: int = 10,
    ) -> list[VideoResult]:
        """
        Search for videos matching a query or category.

        Args:
            query: Search query string.
            category: Optional category filter.
            limit: Maximum number of results.

        Returns:
            List of VideoResult objects.
        """
        ...

    @abstractmethod
    async def random(
        self, category: Optional[VideoCategory] = None
    ) -> Optional[VideoResult]:
        """
        Get a random video, optionally filtered by category.

        Args:
            category: Optional category to pick from.

        Returns:
            A VideoResult or None if nothing found.
        """
        ...

    @abstractmethod
    async def next_video(self) -> Optional[VideoResult]:
        """
        Get the next video to play from this provider.

        Returns:
            A VideoResult or None if nothing available.
        """
        ...

    def get_keywords(self, category: VideoCategory) -> list[str]:
        """Get search keywords for a category."""
        return CATEGORY_KEYWORDS.get(category, ["interesting"])

    async def validate_video(self, video: VideoResult) -> bool:
        """
        Check if a video URL is still valid/accessible.
        Default implementation returns True; providers may override.
        """
        return True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name.value} enabled={self.enabled}>"
