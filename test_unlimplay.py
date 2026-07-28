import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        async def handle_route(route, request):
            url = request.url
            if ".m3u8" in url or ".mp4" in url or "stream" in url.lower() or "video" in url.lower():
                print("FOUND POTENTIAL VIDEO URL:", url)
            await route.continue_()
            
        await page.route("**/*", handle_route)
        
        print("Navigating to Unlimplay movie...")
        try:
            await page.goto("https://unlimplay.com/f/embed/movie/157336", wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            print("Goto timeout:", e)
            
        await asyncio.sleep(3)
        try:
            print("Clicking play button...")
            await page.click("#overlay-play", force=True, timeout=3000)
        except Exception as e:
            print("Click failed:", e)
            
        await asyncio.sleep(2)
        print("Clicking center of screen...")
        await page.mouse.click(500, 300)
        await asyncio.sleep(1)
        await page.mouse.click(500, 300)
        await asyncio.sleep(5)
        
        await browser.close()

asyncio.run(run())
