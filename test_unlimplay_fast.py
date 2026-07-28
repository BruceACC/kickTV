import asyncio
import aiohttp
import re
import json

async def run():
    url = "https://unlimplay.com/f/embed/movie/157336"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Referer": "https://unlimplay.com/"
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            text = await resp.text()
            
            # Find the finalizePlayer argument
            match = re.search(r'finalizePlayer\((.*?)\);', text)
            if match:
                data = json.loads(match.group(1))
                
                # Check all languages and servers
                for lang, servers in data.items():
                    if "direct" in servers:
                        direct_url = servers["direct"]
                        print(f"FOUND DIRECT IN {lang}: {direct_url}")
                        return
                    if "remux" in servers:
                        print(f"FOUND REMUX IN {lang}: {servers['remux']}")
                        
                print("No direct stream found.")
                print(json.dumps(data, indent=2))
            else:
                print("finalizePlayer not found")

asyncio.run(run())
