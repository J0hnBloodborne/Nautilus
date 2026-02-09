import httpx

class UniversalScraper:
    # Sudo-Flix Inspired Provider List (Augmented)
    PROVIDERS = [
        # Prime Candidates (Most reliable)
        {"name": "VidSrc.to",  "url": "https://vidsrc.to/embed/{type}/{id}/{s}/{e}"},
        {"name": "VidSrc.pro", "url": "https://vidsrc.pro/embed/{type}/{id}/{s}/{e}"}, # Often unblocked
        {"name": "SuperEmbed", "url": "https://multiembed.mov/directstream.php?video_id={id}&tmdb=1&s={s}&e={e}"},
        
        # Secondaries
        {"name": "2Embed",     "url": "https://www.2embed.cc/embed/{id}"}, # Movies only? need logic
        {"name": "SmashyStream", "url": "https://embed.smashystream.com/playere.php?tmdb={id}"},
        {"name": "AutoEmbed",  "url": "https://autoembed.to/{type}/tmdb/{id}-{s}-{e}"},
        
        # Backups
        {"name": "VidSrc.net", "url": "https://vidsrc.net/embed/{type}/{id}/{s}/{e}"},
        {"name": "VidLink",    "url": "https://vidlink.pro/{type}/{id}/{s}/{e}"},
    ]

    async def get_stream(self, tmdb_id: int, media_type: str, season: int = 1, episode: int = 1, specific_source: str = None):
        async with httpx.AsyncClient() as client:
            type_slug = "movie" if media_type == "movie" else "tv"
            targets = [p for p in self.PROVIDERS if p['name'] == specific_source] if specific_source else self.PROVIDERS

            # Parallel checking could be better, but let's stick to sequential priority for now
            for provider in targets:
                try:
                    # Construct URL
                    url = provider['url']
                    
                    # Special handling for different formats
                    if "2embed.cc" in url:
                        if media_type == "tv": 
                            url = f"https://www.2embed.cc/embedtv/{tmdb_id}&s={season}&e={episode}"
                        else:
                            url = f"https://www.2embed.cc/embed/{tmdb_id}"
                            
                    elif "smashystream" in url:
                        if media_type == "tv":
                            url = f"https://embed.smashystream.com/playere.php?tmdb={tmdb_id}&season={season}&episode={episode}"
                        else:
                            url = f"https://embed.smashystream.com/playere.php?tmdb={tmdb_id}"

                    else:
                        # Standard format
                        if media_type == "movie":
                            url = url.replace("/{s}/{e}", "") \
                                     .replace("&s={s}&e={e}", "") \
                                     .replace("-{s}-{e}", "") \
                                     .format(type=type_slug, id=tmdb_id)
                        else:
                            url = url.format(type=type_slug, id=tmdb_id, s=season, e=episode)
                    
                    # Validate
                    # Some sources block HEAD requests or return 403 but work in browser.
                    # We accept 403 as "Success" for embeds because the browser will handle the user agent/cookies.
                    resp = await client.head(url, timeout=2.0, follow_redirects=True)
                    
                    if resp.status_code < 405: # Accept 403, 401, 200
                        return { 
                            "url": url, 
                            "source": provider['name'], 
                            "type": "embed" 
                        }
                except Exception:
                    continue
            
            return None