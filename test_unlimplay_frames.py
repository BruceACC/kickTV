import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        async def handle_route(route, request):
            url = request.url
            if ".m3u8" in url or ".mp4" in url:
                with open("test_unlimplay_url.txt", "a") as f:
                    f.write(f"FOUND STREAM: {url}\n")
            await route.continue_()
            
        await page.route("**/*", handle_route)
        
        await page.goto("https://unlimplay.com/f/embed/movie/157336", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(5)
        
        html = await page.content()
        with open("test_unlimplay_body.html", "w", encoding="utf-8") as f:
            f.write(html)
            
        # Try clicking the play button inside any iframes if present
        for frame in page.frames:
            if frame != page.main_frame:
                try:
                    await frame.click("#overlay-play", timeout=2000)
                except:
                    pass
                    
        # Click center of screen
        await page.mouse.click(500, 300)
        await asyncio.sleep(1)
        await page.mouse.click(500, 300)
        
        await asyncio.sleep(5)
        await browser.close()

asyncio.run(run())
