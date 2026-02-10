"""VidCloud — delegates to UpCloud (same rabbitstream.net domain)."""
from __future__ import annotations
from ..base import EmbedResult
from ..fetcher import Fetcher
from ..runner import register_embed


@register_embed
class VidCloudEmbed:
    id = "vidcloud"
    name = "VidCloud"
    rank = 201
    disabled = True

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        from .upcloud import UpCloudEmbed
        uc = UpCloudEmbed()
        return await uc.scrape(url, fetcher)
