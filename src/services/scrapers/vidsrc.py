import httpx

class VidSrcScraper:
    """
    Tier 1 Scraper: Maps TMDB IDs to Embed Streams.
    Source: Trusted FMHY Providers.
    """
    # These domains rotate. If streams break, update this list.
    BASE_URLS = [
        "https://vidsrc.to",
        "https://vidsrc.me",
        "https://vidsrc.cc"
    ]

    async def get_stream(self, tmdb_id: int, media_type: str = "movie", season: int = None, episode: int = None):
        async with httpx.AsyncClient() as client:
            for base in self.BASE_URLS:
                try:
                    # Construct the URL based on type
                    if media_type == "movie":
                        url = f"{base}/embed/movie/{tmdb_id}"
                    elif media_type == "tv" or media_type == "show":
                        # Handle case where frontend sends 'show' or 'tv'
                        url = f"{base}/embed/tv/{tmdb_id}/{season}/{episode}"
                    else:
                        continue

                    # Verify the link is alive (Status 200)
                    # We use a short timeout (2s) to fail fast if a mirror is down
                    resp = await client.head(url, timeout=2.0)
                    
                    if resp.status_code < 400:
                        return url
                except Exception:
                    # If one mirror fails, try the next
                    continue
            
            return None