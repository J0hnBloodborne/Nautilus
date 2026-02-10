"""
AutoEmbed source — constructs embed URLs and delegates to embed scrapers.
"""
from __future__ import annotations
from ..base import MediaContext, SourceResult, EmbedRef
from ..fetcher import Fetcher
from ..runner import register_source


@register_source
class AutoEmbedSource:
    id = "autoembed-src"
    name = "AutoEmbed"
    rank = 100
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        if ctx.media_type == "movie":
            url = f"https://autoembed.cc/embed/oplayer.php?id={ctx.tmdb_id}"
        else:
            url = f"https://autoembed.cc/embed/oplayer.php?id={ctx.tmdb_id}&s={ctx.season}&e={ctx.episode}"

        # AutoEmbed returns HLS playlists directly — wrap as an embed
        return SourceResult(embeds=[
            EmbedRef(embed_id="autoembed", url=url),
        ])
