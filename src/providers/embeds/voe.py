"""Voe.sx — regex HLS extraction."""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream
from ..fetcher import Fetcher
from ..runner import register_embed

LINK_RE = re.compile(r"'hls':\s*'(http[^']+)'")


@register_embed
class Voe:
    id = "voe"
    name = "Voe"
    rank = 180

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url, headers={"Referer": "https://voe.sx/"})
        m = LINK_RE.search(html)
        if not m:
            raise Exception("Voe HLS not found")
        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=m.group(1),
                   headers={"Referer": "https://voe.sx"})
        ])
