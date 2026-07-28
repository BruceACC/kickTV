import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        async def on_request(route, request):
            url = request.url
            if not url.endswith((".js", ".css", ".png", ".jpg", ".woff2")):
                print("REQUEST:", url[:100])
            await route.continue_()
            
        await page.route("**/*", on_request)
        
        try:
            print("Navigating to Interstellar...")
            await page.goto("https://unlimplay.com/f/embed/movie/157336", wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            print("goto timeout:", e)
            
        await asyncio.sleep(2)
        try:
            print("Clicking play button...")
            await page.click("#overlay-play", force=True, timeout=2000)
            await asyncio.sleep(2)
        except Exception as e:
            print("click error:", e)
            pass
            
        print("Clicking center...")
        await page.mouse.click(500, 300)
        await asyncio.sleep(1)
        await page.mouse.click(500, 300)
        await asyncio.sleep(3)
        
        await browser.close()
        print("Done")

asyncio.run(run())
