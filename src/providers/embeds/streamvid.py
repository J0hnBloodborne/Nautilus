"""StreamVid — packed JS → src:"..." → HLS."""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream
from ..fetcher import Fetcher
from ..runner import register_embed
from .. import unpacker

PACKED_RE = re.compile(r'(eval\(function\(p,a,c,k,e,d\).*\)\)\))', re.DOTALL)
LINK_RE = re.compile(r'src:"(https://[^"]+)"')


@register_embed
class StreamVid:
    id = "streamvid"
    name = "StreamVid"
    rank = 215

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url)
        packed = PACKED_RE.search(html)
        if not packed:
            raise Exception("StreamVid packed not found")
        unpacked = unpacker.unpack(packed.group(1))
        m = LINK_RE.search(unpacked)
        if not m:
            raise Exception("StreamVid link not found")
        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=m.group(1))
        ])
