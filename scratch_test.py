import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        m3u8_url = None
        
        def handle_request(route, request):
            nonlocal m3u8_url
            if ".m3u8" in request.url or ".mp4" in request.url:
                print(f"Found media URL: {request.url}")
                m3u8_url = request.url
            asyncio.create_task(route.continue_())
            
        await page.route("**/*", handle_request)
        
        print("Navigating to Unlimplay...")
        await page.goto("https://unlimplay.com/f/embed/movie/1226863", wait_until="networkidle")
        
        # Try to click play if there's a play button
        try:
            # Look for common play button selectors
            print("Trying to click play...")
            await page.click(".jw-icon-display, .vjs-big-play-button, button.play", timeout=5000)
        except Exception as e:
            print(f"Could not click play: {e}")
            
        await page.wait_for_timeout(5000) # Wait a bit for requests
        
        await browser.close()
        
        if m3u8_url:
            print(f"\nSUCCESS! Extracted URL: {m3u8_url}")
        else:
            print("\nFAILED to find media URL.")

if __name__ == "__main__":
    asyncio.run(run())
