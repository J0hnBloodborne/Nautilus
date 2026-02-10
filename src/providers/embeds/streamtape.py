"""StreamTape — robotlink innerHTML URL construction."""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream, StreamFile
from ..fetcher import Fetcher
from ..runner import register_embed

ROBOT_RE = re.compile(r"robotlink'\)\.innerHTML\s*=\s*'([^']*)'")
TOKEN_RE = re.compile(r"\+\s*\('([^']*)'")


@register_embed
class StreamTape:
    id = "streamtape"
    name = "StreamTape"
    rank = 160

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url, headers={"Referer": "https://streamtape.com/"})
        m = re.search(r"robotlink'\)\.innerHTML = (.*)'\s*;", html)
        if not m:
            raise Exception("StreamTape robotlink not found")
        raw = m.group(1)
        # Format: '//streamtape.com/get_video?...'+ ('xYz123')
        parts = raw.split("+ ('")
        if len(parts) < 2:
            raise Exception("StreamTape URL parse failed")
        first_half = parts[0].strip().strip("'").strip()
        second_half = parts[1].split("')")[0].strip()
        # second_half starts with 3 chars that overlap with first_half
        stream_url = f"https:{first_half}{second_half[3:]}"
        return EmbedResult(streams=[
            Stream(stream_type="file",
                   qualities=[StreamFile(url=stream_url, quality="unknown")],
                   headers={"Referer": "https://streamtape.com"})
        ])
