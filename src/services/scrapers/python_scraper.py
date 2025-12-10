from playwright.async_api import async_playwright
import asyncio

async def get_stream_url(tmdb_id: str, media_type: str, season: int = None, episode: int = None):
    """
    Launches a headless browser to scrape the direct m3u8 stream from VidLink.
    """
    # Construct the target URL (VidLink structure)
    if media_type == 'tv':
        target_url = f"https://vidlink.pro/tv/{tmdb_id}/{season}/{episode}"
    else:
        target_url = f"https://vidlink.pro/movie/{tmdb_id}"

    found_url = None

    async with async_playwright() as p:
        # Launch browser (headless=True is invisible)
        # We use chromium as it is the most reliable for this
        browser = await p.chromium.launch(headless=True)
        
        # Create a context with a real user agent to avoid basic bot detection
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Event listener for network requests
        async def handle_request(request):
            nonlocal found_url
            # Look for the master playlist
            # VidLink often uses 'master.m3u8' or similar patterns
            if ".m3u8" in request.url and "master" in request.url:
                found_url = request.url

        page.on("request", handle_request)

        try:
            print(f"Scraping: {target_url}")
            await page.goto(target_url, timeout=15000)
            
            # Wait a bit for the player to load and requests to fire
            # We poll for the URL to be found
            for _ in range(10): # Try for 5 seconds (10 * 0.5s)
                if found_url:
                    break
                await asyncio.sleep(0.5)
                
                # Optional: Try to click a play button if it exists and we haven't found it yet
                if not found_url:
                    try:
                        play_button = await page.query_selector('#play-button, .play-button, button.play')
                        if play_button:
                            await play_button.click()
                    except Exception:
                        pass

        except Exception as e:
            print(f"Scraping error: {e}")
        finally:
            await browser.close()

    return found_url
