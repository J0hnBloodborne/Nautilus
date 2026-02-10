"""
MP4Upload embed scraper.
Extracts direct MP4 URL from player.src() in embed page.
"""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream, StreamFile
from ..fetcher import Fetcher
from ..runner import register_embed

SRC_RE = re.compile(r'player\.src\(\s*\{\s*type:\s*"[^"]+",\s*src:\s*"([^"]+)"', re.DOTALL)


@register_embed
class MP4UploadEmbed:
    id = "mp4upload"
    name = "MP4Upload"
    rank = 170

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url)
        match = SRC_RE.search(html)
        if not match:
            raise ValueError("MP4Upload stream URL not found")

        stream_url = match.group(1)
        return EmbedResult(streams=[
            Stream(
                stream_type="file",
                qualities=[StreamFile(url=stream_url, quality="1080")],
            )
        ])
