"""
Ridoo embed scraper.
Simple regex extraction of HLS URL from embed page.
"""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream
from ..fetcher import Fetcher
from ..runner import register_embed

REFERER = "https://ridomovies.tv/"
FILE_RE = re.compile(r'file:"([^"]+)"')


@register_embed
class RidooEmbed:
    id = "ridoo"
    name = "Ridoo"
    rank = 105

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url, headers={"Referer": REFERER})
        match = FILE_RE.search(html)
        if not match:
            raise ValueError("Ridoo stream URL not found")

        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=match.group(1))
        ])
