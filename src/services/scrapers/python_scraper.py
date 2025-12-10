from playwright.async_api import async_playwright
import asyncio

async def get_stream_url(tmdb_id: str, media_type: str, season: int = None, episode: int = None):
    """
    Launches a headless browser to scrape the direct m3u8 stream.
    Tries multiple providers (VidLink, VidSrc, etc.) until a stream is found.
    """
    
    # Define providers and their URL constructors
    providers = [
        {
            "name": "VidLink",
            "movie": f"https://vidlink.pro/movie/{tmdb_id}",
            "tv": f"https://vidlink.pro/tv/{tmdb_id}/{season}/{episode}"
        },
        {
            "name": "VidSrc.to",
            "movie": f"https://vidsrc.to/embed/movie/{tmdb_id}",
            "tv": f"https://vidsrc.to/embed/tv/{tmdb_id}/{season}/{episode}"
        },
        {
            "name": "VidSrc.cc",
            "movie": f"https://vidsrc.cc/v2/embed/movie/{tmdb_id}",
            "tv": f"https://vidsrc.cc/v2/embed/tv/{tmdb_id}/{season}/{episode}"
        },
        {
            "name": "SuperEmbed",
            "movie": f"https://multiembed.mov/directstream.php?video_id={tmdb_id}&tmdb=1",
            "tv": f"https://multiembed.mov/directstream.php?video_id={tmdb_id}&tmdb=1&s={season}&e={episode}"
        },
        {
            "name": "AutoEmbed",
            "movie": f"https://autoembed.to/movie/tmdb/{tmdb_id}",
            "tv": f"https://autoembed.to/tv/tmdb/{tmdb_id}-{season}-{episode}"
        },
        {
            "name": "VidSrc.me",
            "movie": f"https://vidsrc.me/embed/movie?tmdb={tmdb_id}",
            "tv": f"https://vidsrc.me/embed/tv?tmdb={tmdb_id}&season={season}&episode={episode}"
        },
        {
            "name": "VidSrc.xyz",
            "movie": f"https://vidsrc.xyz/embed/movie/{tmdb_id}",
            "tv": f"https://vidsrc.xyz/embed/tv/{tmdb_id}/{season}/{episode}"
        },
        {
            "name": "2Embed",
            "movie": f"https://www.2embed.cc/embed/{tmdb_id}",
            "tv": f"https://www.2embed.cc/embedtv/{tmdb_id}&s={season}&e={episode}"
        },
        {
            "name": "SmashyStream",
            "movie": f"https://embed.smashystream.com/playere.php?tmdb={tmdb_id}",
            "tv": f"https://embed.smashystream.com/playere.php?tmdb={tmdb_id}&season={season}&episode={episode}"
        }
    ]

    found_url = None

    async with async_playwright() as p:
        # Launch browser (headless=True is invisible)
        browser = await p.chromium.launch(headless=True)
        
        # Create a context with a real user agent
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        for provider in providers:
            if found_url:
                break
                
            target_url = provider['tv'] if media_type == 'tv' else provider['movie']
            print(f"Scraping {provider['name']}: {target_url}")
            
            page = await context.new_page()
            
            # Event listener for network requests
            async def handle_request(request):
                nonlocal found_url
                # Look for the master playlist
                if ".m3u8" in request.url and "master" in request.url:
                    found_url = request.url

            page.on("request", handle_request)

            try:
                await page.goto(target_url, timeout=10000)
                
                # Wait loop
                for _ in range(8): # 4 seconds per provider
                    if found_url:
                        break
                    await asyncio.sleep(0.5)
                    
                    # Try to click play button
                    if not found_url:
                        try:
                            play_button = await page.query_selector('#play-button, .play-button, button.play, .play')
                            if play_button:
                                await play_button.click()
                        except Exception:
                            pass
                            
            except Exception as e:
                print(f"Error scraping {provider['name']}: {e}")
            finally:
                await page.close()

        await browser.close()

    return found_url
