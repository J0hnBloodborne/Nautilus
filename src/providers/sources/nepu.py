"""Nepu — search + AJAX embed → HLS direct. Disabled."""
from __future__ import annotations
import re
from ..base import SourceResult, MediaContext, Stream
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://nepu.to"


@register_source
class Nepu:
    id = "nepu"
    name = "Nepu"
    rank = 80
    disabled = True
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # Search
        search_html = await fetcher.get(
            f"{BASE}/ajax/posts",
            params={"q": ctx.title},
            headers={"Referer": f"{BASE}/", "Origin": BASE},
        )

        # Find matching result
        results = re.findall(r'href="([^"]+)"[^>]*>\s*(.*?)\s*<', search_html, re.DOTALL)
        video_url = None
        for href, title in results:
            if ctx.title.lower() in title.lower():
                video_url = href
                break
        if not video_url and results:
            video_url = results[0][0]
        if not video_url:
            raise ValueError("Nepu: no results")

        if not video_url.startswith("http"):
            video_url = f"{BASE}{video_url}"

        # Get video page
        page = await fetcher.get(video_url, headers={"Referer": BASE, "Origin": BASE})

        # Find data-embed attribute
        embed_m = re.search(r'data-embed="([^"]+)"', page)
        if not embed_m:
            raise ValueError("Nepu: no embed data")

        # POST to /ajax/embed
        embed_res = await fetcher.post(
            f"{BASE}/ajax/embed",
            data={"id": embed_m.group(1)},
            headers={"Referer": video_url, "Origin": BASE},
        )

        file_m = re.search(r'"file"\s*:\s*"(https?://[^"]+)"', embed_res)
        if not file_m:
            raise ValueError("Nepu: HLS not found")

        return SourceResult(streams=[
            Stream(stream_type="hls", playlist=file_m.group(1),
                   headers={"Referer": BASE + "/", "Origin": BASE})
        ])
