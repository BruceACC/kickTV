import asyncio
import aiohttp
import re
import json
import subprocess

async def run():
    url = "https://unlimplay.com/f/embed/movie/550"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://unlimplay.com/"
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=15) as resp:
            text = await resp.text()
            match = re.search(r'finalizePlayer\((.*?)\);', text)
            if match:
                data = json.loads(match.group(1))
                video_url = None
                for lang, servers in data.items():
                    if "direct 2" in servers: video_url = servers["direct 2"]; break
                    if "direct" in servers: video_url = servers["direct"]; break
                
                if video_url:
                    print("URL:", video_url)
                    subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", video_url])
                else:
                    print("No direct url found")

asyncio.run(run())
