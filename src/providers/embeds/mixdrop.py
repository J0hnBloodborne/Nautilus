"""MixDrop — packed JS → MDCore.wurl → direct MP4."""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream, StreamFile
from ..fetcher import Fetcher
from ..runner import register_embed
from .. import unpacker

BASE = "https://mixdrop.ag"
PACKED_RE = re.compile(r'(eval\(function\(p,a,c,k,e,d\)\{.*?\}\)\))', re.DOTALL)
LINK_RE = re.compile(r'MDCore\.wurl="(.*?)";')


@register_embed
class MixDrop:
    id = "mixdrop"
    name = "MixDrop"
    rank = 198

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        embed_id = url.rstrip("/").split("/")[-1]
        html = await fetcher.get(f"{BASE}/e/{embed_id}")
        packed = PACKED_RE.search(html)
        if not packed:
            raise Exception("MixDrop packed JS not found")
        unpacked = unpacker.unpack(packed.group(1))
        m = LINK_RE.search(unpacked)
        if not m:
            raise Exception("MixDrop wurl not found")
        stream_url = m.group(1)
        if not stream_url.startswith("http"):
            stream_url = f"https:{stream_url}"
        return EmbedResult(streams=[
            Stream(stream_type="file", qualities=[StreamFile(url=stream_url, quality="unknown")],
                   headers={"Referer": f"{BASE}/"})
        ])
