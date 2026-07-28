"""
KickTV — Local Provider

Serves video files from the local filesystem (data/videos/).
"""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models import ProviderName, VideoCategory, VideoResult
from app.providers.base import BaseProvider, generate_video_id

# Supported video extensions
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".m4v"}


class LocalProvider(BaseProvider):
    """Serves videos from the local data/videos/ directory."""

    name = ProviderName.LOCAL
    display_name = "Local Files"
    description = "Plays video files from the local videos folder."
    requires_api_key = False

    def __init__(self) -> None:
        super().__init__()
        self._video_dir = settings.abs_video_cache_dir
        self._index: list[Path] = []
        self._position: int = 0

    def _scan_videos(self) -> list[Path]:
        """Recursively scan the video directory for supported files."""
        videos: list[Path] = []
        if not self._video_dir.exists():
            self.logger.warning("Video directory does not exist: %s", self._video_dir)
            return videos

        for root, _, files in os.walk(self._video_dir):
            for filename in sorted(files):
                filepath = Path(root) / filename
                if filepath.suffix.lower() in VIDEO_EXTENSIONS:
                    videos.append(filepath)

        self.logger.info("Scanned %d local video files", len(videos))
        return videos

    def _path_to_result(self, path: Path) -> VideoResult:
        """Convert a file path to a VideoResult."""
        # Try to infer category from parent folder name
        category = VideoCategory.CURIOSIDADES
        parent_name = path.parent.name.lower()
        for cat in VideoCategory:
            if cat.value.lower() in parent_name:
                category = cat
                break

        return VideoResult(
            url=str(path),
            title=path.stem.replace("_", " ").replace("-", " ").title(),
            duration=0,  # Could use ffprobe, but kept simple
            author="Local",
            category=category,
            provider=ProviderName.LOCAL,
            video_id=generate_video_id("local", str(path)),
        )

    async def search(
        self,
        query: str = "",
        category: Optional[VideoCategory] = None,
        limit: int = 10,
    ) -> list[VideoResult]:
        """Search local videos by filename or category folder."""
        videos = self._scan_videos()
        results: list[VideoResult] = []

        for path in videos:
            if query and query.lower() not in path.stem.lower():
                continue
            if category:
                parent = path.parent.name.lower()
                if category.value.lower() not in parent:
                    continue
            results.append(self._path_to_result(path))
            if len(results) >= limit:
                break

        return results

    async def random(
        self, category: Optional[VideoCategory] = None
    ) -> Optional[VideoResult]:
        """Get a random local video."""
        videos = self._scan_videos()
        if not videos:
            return None

        if category:
            filtered = [
                v for v in videos
                if category.value.lower() in v.parent.name.lower()
            ]
            videos = filtered or videos

        chosen = random.choice(videos)
        return self._path_to_result(chosen)

    async def next_video(self) -> Optional[VideoResult]:
        """Get the next local video in sequence."""
        if not self._index:
            self._index = self._scan_videos()
            random.shuffle(self._index)
            self._position = 0

        if not self._index:
            return None

        if self._position >= len(self._index):
            random.shuffle(self._index)
            self._position = 0

        path = self._index[self._position]
        self._position += 1
        return self._path_to_result(path)
