"""FshareTV — search and delegate to embed scrapers."""
from __future__ import annotations
import re, json
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://fsharetv.co"


@register_source
class FshareTV:
    id = "fsharetv"
    name = "FshareTV"
    rank = 220
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # Search
        search_html = await fetcher.get(f"{BASE}/search",
                                        params={"q": ctx.title},
                                        headers={"Referer": BASE})

        # Find matching items: <a href="/movie/..." or /tv/...
        results = re.findall(r'href="(/(?:movie|tv)/[^"]+)"[^>]*>.*?class="title"[^>]*>([^<]+)',
                             search_html, re.DOTALL)
        if not results:
            # Try simpler pattern
            results = re.findall(r'href="(/(?:movie|tv|film|series)/[^"]+)"', search_html)
            results = [(r, "") for r in results]

        if not results:
            raise Exception("FshareTV: no results")

        # Pick best match
        match_path = results[0][0]
        for path, title in results:
            if ctx.title.lower() in title.lower():
                match_path = path
                break

        # Get watch page
        watch_url = f"{BASE}{match_path}"
        if ctx.media_type == "tv" and ctx.season and ctx.episode:
            watch_url = f"{watch_url}/season-{ctx.season}/episode-{ctx.episode}"
        page = await fetcher.get(watch_url, headers={"Referer": BASE})

        # Extract iframe embed URLs
        embeds = []
        iframes = re.findall(r'<iframe[^>]*(?:data-src|src)="([^"]+)"', page, re.IGNORECASE)
        for url in iframes:
            url = url if url.startswith("http") else f"https:{url}"
            embed = _identify_embed(url)
            if embed:
                embeds.append(embed)

        # Also look for server link buttons
        servers = re.findall(r'data-url="([^"]+)"', page)
        for url in servers:
            url = url if url.startswith("http") else f"https:{url}"
            embed = _identify_embed(url)
            if embed:
                embeds.append(embed)

        if not embeds:
            raise Exception("FshareTV: no embeds found")

        return SourceResult(embeds=embeds)


def _identify_embed(url: str) -> EmbedRef | None:
    url_lower = url.lower()
    embed_map = {
        "mixdrop": "mixdrop", "voe": "voe", "dood": "dood", "d0o0d": "dood",
        "d000d": "dood", "streamtape": "streamtape", "filemoon": "filemoon",
        "streamwish": "streamwish", "swish": "streamwish",
        "upstream": "upstream", "mp4upload": "mp4upload",
        "ridoo": "ridoo", "filelions": "filelions", "streamvid": "streamvid",
        "turbovid": "turbovid", "closeload": "closeload",
    }
    for key, embed_id in embed_map.items():
        if key in url_lower:
            return EmbedRef(embed_id=embed_id, url=url)
    return None
