import httpx

class UniversalScraper:
    PROVIDERS = [
        {"name": "VidLink",    "url": "https://vidlink.pro/{type}/{id}/{s}/{e}"},
        {"name": "VidSrc.to",  "url": "https://vidsrc.to/embed/{type}/{id}/{s}/{e}"},
        {"name": "VidSrc.net", "url": "https://vidsrc.net/embed/{type}/{id}/{s}/{e}"},
        {"name": "SuperEmbed", "url": "https://multiembed.mov/directstream.php?video_id={id}&tmdb=1&s={s}&e={e}"},
        {"name": "VidSrc.cc",  "url": "https://vidsrc.cc/v2/embed/{type}/{id}/{s}/{e}"}, # New
        {"name": "AutoEmbed",  "url": "https://autoembed.to/{type}/tmdb/{id}-{s}-{e}"},  # New
    ]

    async def get_stream(self, tmdb_id: int, media_type: str, season: int = 1, episode: int = 1, specific_source: str = None):
        async with httpx.AsyncClient() as client:
            type_slug = "movie" if media_type == "movie" else "tv"
            targets = [p for p in self.PROVIDERS if p['name'] == specific_source] if specific_source else self.PROVIDERS

            for provider in targets:
                try:
                    if media_type == "movie":
                        url = provider['url'].replace("/{s}/{e}", "") \
                                             .replace("&s={s}&e={e}", "") \
                                             .replace("-{s}-{e}", "") \
                                             .format(type=type_slug, id=tmdb_id)
                    else:
                        url = provider['url'].format(type=type_slug, id=tmdb_id, s=season, e=episode)
                    resp = await client.head(url, timeout=1.5, follow_redirects=True)
                    
                    if resp.status_code < 400:
                        return { 
                            "url": url, 
                            "source": provider['name'], 
                            "type": "embed" 
                        }
                except Exception:
                    continue
            
            return None