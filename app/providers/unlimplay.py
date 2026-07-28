"""
Unlimplay Provider using aiohttp for fast and direct extraction of video links.
"""

import asyncio
import logging
import random
import re
import json
from typing import Optional

import aiohttp

from app.models import ProviderName, VideoCategory, VideoResult
from app.providers.base import BaseProvider

logger = logging.getLogger("kicktv.providers.unlimplay")

# List of popular TMDB Movie IDs to stream
POPULAR_MOVIES = [
    (157336, "Interstellar"),
    (27205, "Inception"),
    (603, "The Matrix"),
    (299534, "Avengers: Endgame"),
    (634649, "Spider-Man: No Way Home"),
    (475557, "Joker"),
    (414906, "The Batman"),
    (502356, "The Super Mario Bros. Movie"),
    (862, "Toy Story"),
    (808, "Shrek"),
    (550, "Fight Club"),
    (680, "Pulp Fiction"),
    (13, "Forrest Gump"),
    (98, "Gladiator"),
    (597, "Titanic"),
    (19995, "Avatar"),
    (1226863, "Despicable Me 4"),
    (1022789, "Inside Out 2"),
    (533535, "Deadpool & Wolverine")
]

class UnlimplayProvider(BaseProvider):
    name = ProviderName.UNLIMPLAY
    
    def __init__(self):
        super().__init__()

    async def check_auth(self) -> bool:
        """No auth required."""
        return True

    async def search(
        self,
        query: str = "",
        category: Optional[VideoCategory] = None,
        limit: int = 5,
    ) -> list[VideoResult]:
        """
        Picks a random movie from our list and extracts the direct .m3u8 URL quickly via regex.
        """
        # Pick a random movie
        tmdb_id, title = random.choice(POPULAR_MOVIES)
        url = f"https://unlimplay.com/f/embed/movie/{tmdb_id}"
        
        logger.info(f"Extracting video link for '{title}' ({url})...")
        
        video_url = None
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Referer": "https://unlimplay.com/"
        }
        
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        match = re.search(r'finalizePlayer\((.*?)\);', text)
                        if match:
                            try:
                                data = json.loads(match.group(1))
                                # Buscamos la URL 'direct' en cualquier idioma disponible
                                for lang, servers in data.items():
                                    if "direct 2" in servers:
                                        video_url = servers["direct 2"]
                                        break
                                    if "direct" in servers:
                                        video_url = servers["direct"]
                                        break
                            except Exception as json_e:
                                logger.error(f"Error parsing finalizePlayer JSON: {json_e}")
                    else:
                        logger.error(f"Unlimplay returned status {resp.status}")
                        
        except Exception as e:
            logger.error(f"Error fetching Unlimplay data: {e}")
            return []

        if not video_url:
            logger.error(f"Failed to find direct stream for {title}")
            return []
            
        logger.info(f"Successfully extracted direct video stream for '{title}'!")
        
        # Since these are full movies, duration is generally around 120 mins
        estimated_duration = 7200
        
        result = VideoResult(
            url=video_url,
            title=title,
            duration=estimated_duration,
            author="Unlimplay",
            category=VideoCategory.PELICULAS_CLASICAS,
            provider=self.name,
            video_id=str(tmdb_id)
        )
        
        return [result]

    async def random(
        self, category: Optional[VideoCategory] = None
    ) -> Optional[VideoResult]:
        """Get a random movie."""
        results = await self.search()
        return results[0] if results else None

    async def next_video(self) -> Optional[VideoResult]:
        """Get the next video."""
        return await self.random()
