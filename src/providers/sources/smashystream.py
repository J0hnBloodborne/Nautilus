"""SmashyStream — generates embed URLs for video1 + opstream."""
from __future__ import annotations
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source


@register_source
class SmashyStream:
    id = "smashystream"
    name = "SmashyStream"
    rank = 30
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        if ctx.media_type == "movie":
            query = f"?tmdb={ctx.tmdb_id}"
        else:
            query = f"?tmdbId={ctx.tmdb_id}&season={ctx.season}&episode={ctx.episode}"

        return SourceResult(embeds=[
            EmbedRef(embed_id="smashystream-f",
                     url=f"https://embed.smashystream.com/video1dn.php{query}"),
            EmbedRef(embed_id="smashystream-o",
                     url=f"https://embed.smashystream.com/videoop.php{query}"),
        ])
