import httpx

class UniversalScraper:
    """
    The Hydra: Expanded Edition.
    """
    PROVIDERS = [
        # --- TIER S: The Heavy Hitters ---
        {"name": "VidSrc.to",  "url": "https://vidsrc.to/embed/{type}/{id}/{s}/{e}"},
        {"name": "VidSrc.pro", "url": "https://vidsrc.pro/embed/{type}/{id}/{s}/{e}"},
        {"name": "VidLink",    "url": "https://vidlink.pro/{type}/{id}/{s}/{e}"},
        
        # --- TIER A: Solid Backups ---
        {"name": "SuperEmbed", "url": "https://multiembed.mov/directstream.php?video_id={id}&tmdb=1&s={s}&e={e}"},
        {"name": "2Embed",     "url": "https://www.2embed.cc/embed{type}/{id}&s={s}&e={e}"},
        {"name": "Vidsrc.net", "url": "https://vidsrc.net/embed/{type}/{id}/{s}/{e}"},
        {"name": "Vidsrc.vip", "url": "https://vidsrc.vip/embed/{type}/{id}/{s}/{e}"},
        {"name": "Vidsrc.xyz", "url": "https://vidsrc.xyz/embed/{type}/{id}/{s}/{e}"},
        
        # --- TIER B: The Wildcards ---
        {"name": "AutoEmbed",  "url": "https://autoembed.to/{type}/tmdb/{id}-{s}-{e}"},
        {"name": "Smashy",     "url": "https://embed.smashystream.com/playere.php?tmdb={id}&s={s}&e={e}"},
        {"name": "NontonGo",   "url": "https://www.nontongo.win/embed/{type}/{id}/{s}/{e}"},
        {"name": "AniVid",     "url": "https://anivid.net/embed/{type}/{id}/{s}/{e}"} 
    ]

    async def get_stream(self, tmdb_id: int, media_type: str, season: int = 1, episode: int = 1, specific_source: str = None):
        async with httpx.AsyncClient() as client:
            
            type_slug = "movie" if media_type == "movie" else "tv"
            
            targets = [p for p in self.PROVIDERS if p['name'] == specific_source] if specific_source else self.PROVIDERS

            for provider in targets:
                try:
                    # Construct URL Logic
                    if media_type == "movie":
                        url = provider['url'].replace("/{s}/{e}", "").replace("&s={s}&e={e}", "").replace("-{s}-{e}", "")
                        url = url.format(type=type_slug, id=tmdb_id)
                    else:
                        url = provider['url'].format(type=type_slug, id=tmdb_id, s=season, e=episode)

                    # HEAD request with Redirect Following enabled (Critical for Aggregators)
                    resp = await client.head(url, timeout=2.5, follow_redirects=True)
                    
                    if resp.status_code < 400:
                        return {
                            "url": url, 
                            "source": provider['name'],
                            "type": "embed" 
                        }
                except Exception:
                    continue
            
            return None