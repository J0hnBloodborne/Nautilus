import httpx

class VidSrcProScraper:
    """
    Target: vidsrc.pro / vidsrc.net
    Status: Often faster and higher quality than .to
    """
    # These domains rotate. Check FMHY if they die.
    BASE_URL = "https://vidsrc.pro"

    async def get_stream(self, tmdb_id: int, media_type: str = "movie", season: int = None, episode: int = None):
        async with httpx.AsyncClient() as client:
            try:
                # 1. Construct the Embed URL
                if media_type == "movie":
                    url = f"{self.BASE_URL}/embed/movie/{tmdb_id}"
                elif media_type == "tv" or media_type == "show":
                    url = f"{self.BASE_URL}/embed/tv/{tmdb_id}/{season}/{episode}"
                else:
                    return None

                # 2. Verify it is alive (Status 200)
                # We use a short timeout to fail fast
                resp = await client.head(url, timeout=4.0, follow_redirects=True)
                if resp.status_code < 400:
                    return url
                    
            except Exception:
                return None
        return None