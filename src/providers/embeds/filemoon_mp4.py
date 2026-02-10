"""Filemoon MP4 — converts Filemoon HLS URL to direct MP4 download."""
from __future__ import annotations
from ..base import EmbedResult, Stream, StreamFile
from ..fetcher import Fetcher
from ..runner import register_embed
import re


@register_embed
class FilemoonMp4:
    id = "filemoon-mp4"
    name = "Filemoon MP4"
    rank = 399

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        from .filemoon import FilemoonEmbed
        fm = FilemoonEmbed()
        result = await fm.scrape(url, fetcher)

        if not result.streams:
            raise ValueError("Filemoon MP4: no HLS stream from base scraper")

        hls_stream = result.streams[0]
        if hls_stream.stream_type != "hls" or not hls_stream.playlist:
            raise ValueError("Filemoon MP4: expected HLS stream")

        mp4_url = re.sub(r'/hls2?/', '/download/', hls_stream.playlist)
        mp4_url = re.sub(r'\.m3u8$', '.mp4', mp4_url)

        return EmbedResult(streams=[
            Stream(
                stream_type="file",
                qualities=[StreamFile(url=mp4_url, quality="unknown")],
                captions=hls_stream.captions,
            )
        ])
