import asyncio
import aiohttp
import re
import json

async def run():
    url = "https://unlimplay.com/f/embed/movie/680"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Referer": "https://unlimplay.com/"
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            text = await resp.text()
            
            match = re.search(r'finalizePlayer\((.*?)\);', text)
            if match:
                data = json.loads(match.group(1))
                print(json.dumps(data, indent=2))
            else:
                print("finalizePlayer not found")

asyncio.run(run())
