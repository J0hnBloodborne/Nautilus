"""Goojara — POST search via xhrr.php → embed redirect detection. Disabled."""
from __future__ import annotations
import re
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://goojara.to"

EMBED_MAP = {
    "wootly": "wootly",
    "upstream": "upstream",
    "mixdrop": "mixdrop",
    "dood": "dood",
}


@register_source
class Goojara:
    id = "goojara"
    name = "Goojara"
    rank = 70
    disabled = True
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # Search via POST
        search_html = await fetcher.post(
            f"{BASE}/xhrr.php",
            data={"q": ctx.title},
            headers={
                "Referer": f"{BASE}/",
                "Cookie": "aession=1234567890abcdef",
            },
        )

        # Find results
        results = re.findall(
            r'href="([^"]+)"[^>]*>\s*(.*?)\s*</a>',
            search_html,
            re.DOTALL,
        )

        watch_url = None
        for href, title in results:
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            if ctx.title.lower() in clean_title.lower():
                watch_url = href
                break
        if not watch_url and results:
            watch_url = results[0][0]
        if not watch_url:
            raise ValueError("Goojara: no results")

        if not watch_url.startswith("http"):
            watch_url = f"{BASE}{watch_url}"

        # For TV, navigate to specific episode
        if ctx.media_type == "tv":
            show_html = await fetcher.get(watch_url)
            # Find episode link pattern
            ep_pattern = re.compile(
                rf'href="([^"]*)"[^>]*>.*?S0*{ctx.season}E0*{ctx.episode}',
                re.I | re.DOTALL,
            )
            ep_m = ep_pattern.search(show_html)
            if ep_m:
                watch_url = ep_m.group(1)
                if not watch_url.startswith("http"):
                    watch_url = f"{BASE}{watch_url}"

        # Get watch page
        page = await fetcher.get(watch_url)

        # Find embed links
        embed_links = re.findall(
            r'href="([^"]+)"[^>]*class="[^"]*hd-1[^"]*"',
            page,
        )
        if not embed_links:
            embed_links = re.findall(r'href="([^"]+)"[^>]*class="[^"]*jdownload[^"]*"', page)

        embeds = []
        for link in embed_links:
            if not link.startswith("http"):
                link = f"{BASE}{link}"
            try:
                final_url = await fetcher.get_final_url(link)
                for key, eid in EMBED_MAP.items():
                    if key in final_url:
                        embeds.append(EmbedRef(embed_id=eid, url=final_url))
                        break
            except Exception:
                continue

        return SourceResult(embeds=embeds)
