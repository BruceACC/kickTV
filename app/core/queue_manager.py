"""
KickTV — Smart Queue Manager

Manages the video playback queue with intelligent selection rules:
  - No repeat videos (tracks last N played)
  - No same author consecutively
  - Alternates categories (weighted round-robin)
  - Alternates duration classes (short/medium/long)
  - Maintains persistent history in SQLite
  - Auto-removes invalid/expired videos
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections import deque
from typing import Optional

from app.config import settings
from app.database import db
from app.models import (
    ProviderName,
    QueueItem,
    VideoCategory,
    VideoDuration,
    VideoResult,
)
from app.providers.base import BaseProvider

logger = logging.getLogger("kicktv")


class SmartQueue:
    """
    Intelligent video queue that balances content across categories,
    providers, authors, and duration classes.
    """

    def __init__(self) -> None:
        self._queue: deque[QueueItem] = deque(maxlen=50)
        self._played_ids: set[str] = set()
        self._last_author: str = ""
        self._last_category: str = ""
        self._last_duration_class: VideoDuration = VideoDuration.MEDIUM
        self._category_index: int = 0
        self._providers: dict[ProviderName, BaseProvider] = {}
        self._lock = asyncio.Lock()
        self._filling = False
        self._file_to_delete: Optional[str] = None
        self._download_task: Optional[asyncio.Task] = None

    def register_provider(self, provider: BaseProvider) -> None:
        """Register a content provider."""
        self._providers[provider.name] = provider
        logger.info("Queue: registered provider '%s'", provider.name.value)

    def get_providers(self) -> dict[ProviderName, BaseProvider]:
        """Get all registered providers."""
        return self._providers.copy()

    @property
    def size(self) -> int:
        """Number of items in the queue."""
        return len(self._queue)

    @property
    def items(self) -> list[QueueItem]:
        """Get a copy of queue items."""
        return list(self._queue)

    async def initialize(self) -> None:
        """Load history from database to seed the deduplication set."""
        try:
            self._played_ids = await db.get_recent_video_ids(
                limit=settings.queue_max_history
            )
            self._last_author = await db.get_last_author()
            self._last_category = await db.get_last_category()
            logger.info(
                "Queue initialized: %d played IDs loaded", len(self._played_ids)
            )
            
            # Start background download worker
            if not self._download_task:
                self._download_task = asyncio.create_task(self._download_worker())
                
        except Exception as e:
            logger.error("Queue initialization failed: %s", e)

    def _get_enabled_providers(self) -> list[BaseProvider]:
        """Get list of currently enabled providers."""
        return [p for p in self._providers.values() if p.enabled]

    def _get_target_category(self, enabled_categories: list[dict]) -> VideoCategory:
        """
        Pick the next category using weighted round-robin.
        Avoids repeating the same category as last time.
        """
        if not enabled_categories:
            return random.choice(list(VideoCategory))

        # Build weighted list
        weighted: list[VideoCategory] = []
        for cat_info in enabled_categories:
            cat_name = cat_info["name"]
            weight = cat_info.get("weight", 1.0)
            try:
                cat_enum = VideoCategory(cat_name)
                weighted.extend([cat_enum] * max(1, int(weight)))
            except ValueError:
                continue

        if not weighted:
            return random.choice(list(VideoCategory))

        # Try to pick a different category than last time
        candidates = [c for c in weighted if c.value != self._last_category]
        if not candidates:
            candidates = weighted

        return random.choice(candidates)

    def _get_target_duration(self) -> VideoDuration:
        """Alternate duration classes to keep content varied."""
        rotation = {
            VideoDuration.SHORT: VideoDuration.MEDIUM,
            VideoDuration.MEDIUM: VideoDuration.LONG,
            VideoDuration.LONG: VideoDuration.SHORT,
        }
        return rotation.get(self._last_duration_class, VideoDuration.MEDIUM)

    def _is_acceptable(self, video: VideoResult) -> bool:
        """
        Check if a video passes all queue rules:
        - Not already played recently
        - Not same author as last video
        - Within duration bounds
        """
        # Rule 1: No repeats
        if video.video_id in self._played_ids:
            logger.warning(f"Rejecting {video.video_id}: already played")
            return False

        # Rule 2: No same author consecutively (unless it's Local fallback)
        if video.author and video.author == self._last_author and video.provider != ProviderName.LOCAL:
            logger.warning(f"Rejecting {video.video_id}: same author ({video.author})")
            return False

        # Rule 3: Duration within bounds
        if video.duration > 0:
            if video.duration < settings.min_video_duration:
                logger.warning(f"Rejecting {video.video_id}: too short ({video.duration}s)")
                return False
            if video.duration > settings.max_video_duration:
                logger.warning(f"Rejecting {video.video_id}: too long ({video.duration}s)")
                return False

        return True

    async def _fetch_video(
        self, category: VideoCategory
    ) -> Optional[VideoResult]:
        """
        Try to get a video from any enabled provider for the given category.
        Tries providers in random order for variety.
        """
        providers = self._get_enabled_providers()
        if not providers:
            logger.warning("No enabled providers available")
            return None

        # Weighted selection logic
        ordered_providers = []
        candidates = list(providers)
        
        cand_weights = []
        for p in candidates:
            if p.name == ProviderName.YOUTUBE:
                cand_weights.append(settings.provider_youtube_weight)
            elif p.name == ProviderName.TIKTOK:
                cand_weights.append(settings.provider_tiktok_weight)
            elif p.name == ProviderName.INSTAGRAM:
                cand_weights.append(settings.provider_instagram_weight)
            else:
                cand_weights.append(50)  # Default weight for others
                
        while candidates:
            total = sum(cand_weights)
            if total <= 0:
                idx = random.randint(0, len(candidates) - 1)
            else:
                idx = random.choices(range(len(candidates)), weights=cand_weights, k=1)[0]
            ordered_providers.append(candidates.pop(idx))
            cand_weights.pop(idx)

        for provider in ordered_providers:
            try:
                # Add a timeout so a broken provider doesn't freeze everything
                video = await asyncio.wait_for(
                    provider.random(category=category), timeout=45.0
                )
                if video and self._is_acceptable(video):
                    return video
            except asyncio.TimeoutError:
                logger.error("Provider '%s' timed out", provider.name.value)
            except Exception as e:
                logger.error(
                    "Provider '%s' failed: %s", provider.name.value, e
                )
                # Record error in DB
                try:
                    await db.increment_provider_stats(
                        provider.name.value, errors=1
                    )
                    await db.log_error(
                        message=str(e),
                        source=f"provider.{provider.name.value}",
                        error_type="fetch_error",
                    )
                except Exception:
                    pass

        return None

    async def fill(self, target_size: Optional[int] = None) -> int:
        """
        Fill the queue up to the target size.

        Returns the number of videos added.
        """
        if self._filling:
            return 0

        self._filling = True
        try:
            target = target_size or settings.queue_min_size
            added = 0
            max_attempts = target * 4  # Avoid infinite loops
            attempts = 0

            # Load enabled categories
            try:
                enabled_categories = await db.get_enabled_categories()
            except Exception:
                enabled_categories = []

            while self.size < target and attempts < max_attempts:
                attempts += 1

                # Pick target category
                category = self._get_target_category(enabled_categories)

                # Fetch a video (WITHOUT HOLDING THE LOCK)
                video = await self._fetch_video(category)
                if not video:
                    # Try with any category as fallback
                    video = await self._fetch_video(
                        random.choice(list(VideoCategory))
                    )

                if video:
                    # Now acquire lock just to append
                    async with self._lock:
                        item = QueueItem(
                            position=self.size,
                            video=video,
                        )
                        self._queue.append(item)
                    
                    added += 1
                    logger.info(
                        "Queue + [%s] '%s' by %s (%s)",
                        video.category.value,
                        video.title[:40],
                        video.author[:20],
                        video.provider.value,
                    )
                else:
                    # Brief pause before retrying
                    await asyncio.sleep(1)

            if added:
                logger.info("Queue filled: +%d items (total: %d)", added, self.size)
            return added
        finally:
            self._filling = False

    async def _download_worker(self) -> None:
        """Background task that pre-downloads videos in the queue."""
        while True:
            try:
                # Ensure queue has at least 10 items
                if self.size < 10:
                    await self.fill(10)
                
                # Check for undownloaded videos
                # Copy items to avoid modifying while iterating
                for item in self.items:
                        if item.video.is_iframe or item.video.file_path:
                            continue  # No need to download iframes or already downloaded files
                            
                        provider = self._providers.get(item.video.provider)
                        if provider:
                            logger.info("Pre-fetching video '%s'...", item.video.title[:30])
                            # This will block until downloaded
                            valid = await provider.validate_video(item.video)
                            if not valid:
                                # Remove from queue if it failed to download
                                try:
                                    self._queue.remove(item)
                                except ValueError:
                                    pass
                
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Download worker error: %s", e)
                await asyncio.sleep(10)

    async def next(self) -> Optional[VideoResult]:
        """
        Pop the next video from the queue.
        Updates history tracking state.
        """
        # Cleanup previous file
        if getattr(self, "_file_to_delete", None):
            try:
                import os
                if os.path.exists(self._file_to_delete):
                    os.remove(self._file_to_delete)
                    logger.info("Auto-cleaned video file: %s", self._file_to_delete)
            except Exception as e:
                logger.error("Failed to delete %s: %s", self._file_to_delete, e)
            self._file_to_delete = None

        if self.size == 0:
            await self.fill(10)

        item = None
        # Find the first item that is fully downloaded or is an iframe
        while self.size > 0:
            for i, q_item in enumerate(self._queue):
                if q_item.video.file_path or q_item.video.is_iframe:
                    item = q_item
                    del self._queue[i]
                    break
            
            if item:
                break
                
            logger.info("Waiting for next video to finish downloading...")
            await asyncio.sleep(2)

        if not item:
            return None

        video = item.video
        
        # Schedule this file for deletion on the NEXT call to next()
        if not video.is_iframe:
            self._file_to_delete = video.file_path

        # Update tracking state
        self._played_ids.add(video.video_id)
        self._last_author = video.author
        self._last_category = video.category.value
        self._last_duration_class = video.duration_class

        # Keep played IDs bounded
        if len(self._played_ids) > settings.queue_max_history:
            excess = len(self._played_ids) - settings.queue_max_history
            self._played_ids = set(list(self._played_ids)[excess:])

        # Record in DB
        try:
            await db.add_to_history(video.model_dump())
            await db.save_video(video.model_dump())
            await db.increment_provider_stats(video.provider.value, videos=1)
        except Exception as e:
            logger.error("Failed to record history: %s", e)

        # Trigger background fill if queue is getting low
        if self.size < 10:
            asyncio.create_task(self.fill(10))

        self._last_played_file = item.video.file_path or item.video.url
        logger.info("Now playing: %s", self._last_played_file)

        return video

    def peek(self) -> Optional[VideoResult]:
        """Look at the next video without removing it."""
        if self._queue:
            return self._queue[0].video
        return None

    def skip(self) -> Optional[VideoResult]:
        """Remove the next item from the queue without playing it."""
        if self._queue:
            item = self._queue.popleft()
            return item.video
        return None

    def clear(self) -> None:
        """Clear the entire queue."""
        self._queue.clear()
        logger.info("Queue cleared")

    async def inject_movie(self, tmdb_id: str, duration: int, title: str, is_tv: bool = False, season: int = 1, episode: int = 1) -> None:
        """Inject a requested movie/tv show at the front of the queue using Unlimplay."""
        async with self._lock:
            if is_tv:
                url = f"https://unlimplay.com/f/embed/tv/{tmdb_id}/{season}/{episode}?autoplay=1&autoPlay=1"
            else:
                url = f"https://unlimplay.com/f/embed/movie/{tmdb_id}?autoplay=1&autoPlay=1"
                
            video = VideoResult(
                url=url,
                title=title,
                duration=duration,
                author="Unlimplay",
                category=VideoCategory.PELICULAS,
                provider=ProviderName.UNLIMPLAY,
                video_id=f"unlimplay_{tmdb_id}_{season}_{episode}",
                is_iframe=True
            )
            
            item = QueueItem(
                position=0,
                video=video
            )
            
            self._queue.appendleft(item)
            logger.info("Injected movie %s to the front of the queue", title)

    async def remove_invalid(self) -> int:
        """
        Check each queued video and remove any that are no longer valid.
        Returns count of removed items.
        """
        valid_items: deque[QueueItem] = deque()
        removed = 0

        for item in self._queue:
            provider = self._providers.get(item.video.provider)
            if provider:
                try:
                    is_valid = await provider.validate_video(item.video)
                    if is_valid:
                        valid_items.append(item)
                    else:
                        removed += 1
                        await db.mark_video_invalid(item.video.video_id)
                except Exception:
                    valid_items.append(item)  # Keep on validation error
            else:
                valid_items.append(item)

        if removed:
            self._queue = valid_items
            logger.info("Removed %d invalid videos from queue", removed)

        return removed


# Singleton
queue = SmartQueue()
