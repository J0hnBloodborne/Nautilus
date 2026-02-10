"""SmashyStream (O / opstream) — delegates to SmashyStream F."""
from __future__ import annotations
from ..base import EmbedResult
from ..fetcher import Fetcher
from ..runner import register_embed


@register_embed
class SmashyStreamO:
    id = "smashystream-o"
    name = "SmashyStream (O)"
    rank = 70

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        from .smashystream_f import SmashyStreamF
        return await SmashyStreamF().scrape(url, fetcher)
