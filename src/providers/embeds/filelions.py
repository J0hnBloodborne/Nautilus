"""FileLions — regex file:" extraction → HLS."""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream
from ..fetcher import Fetcher
from ..runner import register_embed

LINK_RE = re.compile(r'file:\s*"(http[^"]+)"')


@register_embed
class FileLions:
    id = "filelions"
    name = "FileLions"
    rank = 115

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url, headers={"Referer": url})
        m = LINK_RE.search(html)
        if not m:
            raise Exception("FileLions file not found")
        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=m.group(1))
        ])
