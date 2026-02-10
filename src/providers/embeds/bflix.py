"""bFlix — packed JS → MP4 URL extraction."""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream, StreamFile
from ..fetcher import Fetcher
from ..runner import register_embed
from .. import unpacker

PACKED_RE = re.compile(r'(eval\(function\(p,a,c,k,e,d\).*?\)\))', re.DOTALL)
MP4_RE = re.compile(r'(https?://[^\s"\']+\.mp4)')


@register_embed
class BFlix:
    id = "bflix"
    name = "bFlix"
    rank = 113

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url)
        packed = PACKED_RE.search(html)
        if not packed:
            raise Exception("bFlix packed JS not found")
        unpacked = unpacker.unpack(packed.group(1))
        m = MP4_RE.search(unpacked)
        if not m:
            raise Exception("bFlix MP4 not found")
        return EmbedResult(streams=[
            Stream(stream_type="file",
                   qualities=[StreamFile(url=m.group(1), quality="unknown")],
                   headers={"Referer": "https://bflix.gs/"})
        ])
