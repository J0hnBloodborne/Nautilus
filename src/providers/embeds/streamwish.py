"""
Streamwish embed scraper.
Uses packed JS deobfuscation → extracts HLS playlist URL.
"""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream
from ..fetcher import Fetcher
from ..runner import register_embed
from .. import unpacker

PACKED_RE = re.compile(r'(eval\(function\(p,a,c,k,e,d\).*?\)\)\))', re.DOTALL)
LINK_RE = re.compile(r'file:"(https?://[^"]+)"')


@register_embed
class StreamwishEmbed:
    id = "streamwish"
    name = "Streamwish"
    rank = 216

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url)
        packed = PACKED_RE.search(html)
        if not packed:
            raise ValueError("Packed JS not found")

        unpacked = unpacker.unpack(packed.group(1))
        link = LINK_RE.search(unpacked)
        if not link:
            raise ValueError("HLS link not found in unpacked JS")

        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=link.group(1))
        ])
