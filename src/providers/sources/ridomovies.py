"""RidoMovies — API search, delegates to CloseLoad/Ridoo embeds."""
from __future__ import annotations
import re, json
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://ridomovies.tv"
API = f"{BASE}/core/api"


@register_source
class RidoMovies:
    id = "ridomovies"
    name = "RidoMovies"
    rank = 120
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # 1. Search
        search_raw = await fetcher.get(f"{API}/search", params={"q": ctx.title})
        try:
            data = json.loads(search_raw) if isinstance(search_raw, str) else search_raw
        except Exception:
            raise Exception("RidoMovies: search parse failed")

        items = data.get("data", {}).get("items", []) if isinstance(data.get("data"), dict) else data.get("data", [])
        if not items:
            raise Exception("RidoMovies: no results")

        # Find matching
        match = None
        for item in items:
            title = item.get("title", "")
            year = str(item.get("releaseDate", ""))[:4]
            slug = item.get("slug", "")
            if ctx.title.lower() in title.lower() and (not ctx.year or year == str(ctx.year)):
                match = item
                break
        if not match:
            match = items[0]

        slug = match.get("slug", "")
        content_type = match.get("contentType", "movie")

        # 2. Get the watch page
        watch_url = f"{BASE}/{content_type}/{slug}" if content_type == "movie" else f"{BASE}/{content_type}/{slug}"
        page = await fetcher.get(watch_url, headers={"Referer": BASE})

        # For TV, find specific episode page
        if ctx.media_type == "tv" and ctx.season and ctx.episode:
            ep_url = f"{API}/episodes?id={match.get('id','')}&seasonNumber={ctx.season}"
            ep_raw = await fetcher.get(ep_url)
            try:
                ep_data = json.loads(ep_raw) if isinstance(ep_raw, str) else ep_raw
            except Exception:
                ep_data = {}
            episodes = ep_data.get("data", [])
            for ep in episodes:
                if ep.get("episodeNumber") == ctx.episode:
                    ep_slug = ep.get("slug", "")
                    if ep_slug:
                        page = await fetcher.get(f"{BASE}/watch/{ep_slug}",
                                                 headers={"Referer": BASE})
                    break

        # 3. Extract iframe sources → embed refs
        embeds = []
        # Pattern: data-src="..." or src="..." in iframe tags
        iframes = re.findall(r'<iframe[^>]*(?:data-src|src)="([^"]+)"', page, re.IGNORECASE)
        for iframe_url in iframes:
            url = iframe_url if iframe_url.startswith("http") else f"https:{iframe_url}"
            if "closeload" in url.lower():
                embeds.append(EmbedRef(embed_id="closeload", url=url))
            elif "ridoo" in url.lower():
                embeds.append(EmbedRef(embed_id="ridoo", url=url))
            elif "streamwish" in url.lower() or "swish" in url.lower():
                embeds.append(EmbedRef(embed_id="streamwish", url=url))
            elif "filemoon" in url.lower():
                embeds.append(EmbedRef(embed_id="filemoon", url=url))
            else:
                embeds.append(EmbedRef(embed_id="closeload", url=url))

        # Also look for server links
        servers = re.findall(r'data-link-id="([^"]+)"', page)
        for sid in servers:
            link_raw = await fetcher.get(f"{API}/links/go/{sid}",
                                         headers={"Referer": watch_url})
            try:
                link_data = json.loads(link_raw) if isinstance(link_raw, str) else link_raw
                embed_url = link_data.get("data", {}).get("link", "")
                if embed_url:
                    if "closeload" in embed_url:
                        embeds.append(EmbedRef(embed_id="closeload", url=embed_url))
                    elif "ridoo" in embed_url:
                        embeds.append(EmbedRef(embed_id="ridoo", url=embed_url))
                    else:
                        embeds.append(EmbedRef(embed_id="closeload", url=embed_url))
            except Exception:
                continue

        if not embeds:
            raise Exception("RidoMovies: no embeds found")

        return SourceResult(embeds=embeds)
