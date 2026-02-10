"""
AutoEmbed embed scraper.
Fetches the embed page, extracts HLS playlist from the player JS.
"""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream
from ..fetcher import Fetcher
from ..runner import register_embed

FILE_RE = re.compile(r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']')
SRC_RE = re.compile(r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']')
M3U8_RE = re.compile(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)')


@register_embed
class AutoEmbedEmbed:
    id = "autoembed"
    name = "AutoEmbed"
    rank = 10

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url, headers={"Referer": "https://autoembed.cc/"})

        # Try multiple patterns to find the HLS URL
        for pattern in [FILE_RE, SRC_RE, M3U8_RE]:
            match = pattern.search(html)
            if match:
                return EmbedResult(streams=[
                    Stream(stream_type="hls", playlist=match.group(1))
                ])

        raise ValueError("AutoEmbed: no HLS URL found")
