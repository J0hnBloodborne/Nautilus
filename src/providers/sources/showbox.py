"""
Showbox — TripleDES encrypted API, delegates to febbox-mp4.
Disabled: CF_BLOCKED.
"""
from __future__ import annotations
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source
from ..embeds.febbox_mp4 import _send_request


@register_source
class Showbox:
    id = "showbox"
    name = "Showbox"
    rank = 150
    disabled = True
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        search_query = {
            "module": "Search4",
            "page": "1",
            "type": "all",
            "keyword": ctx.title,
            "pagelimit": "20",
        }
        search_res = await _send_request(fetcher, search_query, alt_api=True)
        items = search_res.get("data", {}).get("list", [])

        # Find match
        match = None
        for item in items:
            title = item.get("title", "")
            year = item.get("year")
            if ctx.title.lower() in title.lower():
                if not ctx.year or year == ctx.year:
                    match = item
                    break
        if not match:
            raise ValueError("Showbox: no results")

        mid = match["id"]
        season = ctx.season if ctx.media_type == "tv" else ""
        episode = ctx.episode if ctx.media_type == "tv" else ""

        return SourceResult(embeds=[
            EmbedRef(
                embed_id="febbox-mp4",
                url=f"/{ctx.media_type}/{mid}/{season}/{episode}",
            )
        ])
