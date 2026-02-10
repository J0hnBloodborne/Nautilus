"""Dropload — packed JS → file:"..." → HLS (same pattern as upstream/streamvid)."""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream
from ..fetcher import Fetcher
from ..runner import register_embed
from .. import unpacker

PACKED_RE = re.compile(r'(eval\(function\(p,a,c,k,e,d\).*?\)\))', re.DOTALL)
FILE_RE = re.compile(r'file:"([^"]+)"')


@register_embed
class Dropload:
    id = "dropload"
    name = "Dropload"
    rank = 120

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url, headers={"Referer": url})
        packed = PACKED_RE.search(html)
        if not packed:
            raise Exception("Dropload packed JS not found")
        unpacked = unpacker.unpack(packed.group(1))
        m = FILE_RE.search(unpacked)
        if not m:
            raise Exception("Dropload file not found")
        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=m.group(1))
        ])
