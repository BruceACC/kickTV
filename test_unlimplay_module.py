import asyncio
from app.providers.unlimplay import UnlimplayProvider

async def run():
    p = UnlimplayProvider()
    res = await p.search()
    print("Result:", res)

asyncio.run(run())
