"""KissAsian — FormData search → mp4upload/streamsb embeds. Disabled."""
from __future__ import annotations
import re
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://kissasian.sh"


@register_source
class KissAsian:
    id = "kissasian"
    name = "KissAsian"
    rank = 40
    disabled = True
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # Search
        search_html = await fetcher.post(
            f"{BASE}/Search/SearchSuggest",
            data={"type": "Movie", "keyword": ctx.title},
            headers={"Referer": BASE, "X-Requested-With": "XMLHttpRequest"},
        )

        results = re.findall(r'href="([^"]+)"[^>]*>\s*(.*?)\s*</a>', search_html, re.DOTALL)
        watch_url = None
        for href, title in results:
            clean = re.sub(r'<[^>]+>', '', title).strip()
            if ctx.title.lower() in clean.lower():
                watch_url = href
                break
        if not watch_url and results:
            watch_url = results[0][0]
        if not watch_url:
            raise ValueError("KissAsian: no results")

        if not watch_url.startswith("http"):
            watch_url = f"{BASE}{watch_url}"

        if ctx.media_type == "tv":
            # Navigate to episode
            page = await fetcher.get(watch_url)
            ep_m = re.search(
                rf'href="([^"]*Episode-{ctx.episode}[^"]*)"',
                page, re.I,
            )
            if ep_m:
                watch_url = ep_m.group(1)
                if not watch_url.startswith("http"):
                    watch_url = f"{BASE}{watch_url}"

        page = await fetcher.get(watch_url)

        # Find server iframes
        embeds = []
        for m in re.finditer(r'data-video="([^"]+)"', page):
            embed_url = m.group(1)
            if not embed_url.startswith("http"):
                embed_url = f"https:{embed_url}"

            if "mp4upload" in embed_url:
                embeds.append(EmbedRef(embed_id="mp4upload", url=embed_url))
            elif "streamsb" in embed_url or "sbembed" in embed_url:
                embeds.append(EmbedRef(embed_id="streamsb", url=embed_url))

        return SourceResult(embeds=embeds)
