import logging
import aiohttp
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger("kicktv.tmdb")

TMDB_BASE_URL = "https://api.themoviedb.org/3"

class TMDBClient:
    def __init__(self):
        self.api_key = settings.tmdb_api_key
        self.headers = {
            "accept": "application/json"
        }
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.is_configured():
            logger.error("TMDB API Key not configured")
            return {}

        url = f"{TMDB_BASE_URL}{endpoint}"
        if not params:
            params = {}
        # Use query param fallback if token isn't standard Bearer (sometimes users provide api_key instead)
        if len(self.api_key) == 32:
            params["api_key"] = self.api_key
            if "Authorization" in self.headers:
                del self.headers["Authorization"]
        
        params["language"] = "es-ES" # Preferred language

        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"TMDB API error: {response.status} - {await response.text()}")
                        return {}
            except Exception as e:
                logger.error(f"TMDB request failed: {e}")
                return {}

    async def search_multi(self, query: str) -> List[Dict[str, Any]]:
        """Search for movies and TV shows."""
        data = await self._get("/search/multi", {"query": query, "include_adult": "false"})
        results = data.get("results", [])
        
        # Filter only movies and tv shows
        filtered = [
            r for r in results 
            if r.get("media_type") in ["movie", "tv"]
        ]
        
        # Sort by popularity descending
        filtered.sort(key=lambda x: x.get("popularity", 0), reverse=True)
        return filtered

    async def get_now_playing(self) -> List[Dict[str, Any]]:
        """Get movies playing now or upcoming for the carousel."""
        import datetime
        current_year = datetime.datetime.now().year
        data = await self._get("/discover/movie", {
            "primary_release_year": str(current_year),
            "sort_by": "popularity.desc",
            "include_adult": "false"
        })
        results = data.get("results", [])
        for r in results:
            r["media_type"] = "movie"
        return results

    async def get_movie_details(self, tmdb_id: int) -> Dict[str, Any]:
        """Get movie details including runtime."""
        return await self._get(f"/movie/{tmdb_id}")

    async def get_tv_details(self, tmdb_id: int) -> Dict[str, Any]:
        """Get TV details (runtime is usually an array of episode runtimes)."""
        return await self._get(f"/tv/{tmdb_id}")

    async def get_top_movies(self) -> List[Dict[str, Any]]:
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        data = await self._get("/discover/movie", {
            "sort_by": "popularity.desc",
            "release_date.lte": today,
            "vote_count.gte": 100
        })
        results = data.get("results", [])[:15]
        for r in results: r["media_type"] = "movie"
        return results

    async def get_top_series(self) -> List[Dict[str, Any]]:
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        data = await self._get("/discover/tv", {
            "sort_by": "popularity.desc",
            "first_air_date.lte": today,
            "without_genres": "16", # 16 is Animation
            "vote_count.gte": 100
        })
        results = data.get("results", [])[:15]
        for r in results: r["media_type"] = "tv"
        return results

    async def get_top_anime(self) -> List[Dict[str, Any]]:
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        data = await self._get("/discover/tv", {
            "sort_by": "popularity.desc",
            "first_air_date.lte": today,
            "with_genres": "16", # 16 is Animation
            "with_original_language": "ja", # Japanese audio (Anime)
            "vote_count.gte": 50
        })
        results = data.get("results", [])[:15]
        for r in results: r["media_type"] = "tv"
        return results

tmdb_client = TMDBClient()
