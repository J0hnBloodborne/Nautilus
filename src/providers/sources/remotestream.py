"""
RemoteStream — simple direct-URL HLS provider.
Provides m3u8 playlists at predictable URLs based on TMDB ID.
"""
from __future__ import annotations
from ..base import MediaContext, SourceResult, Stream
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://fsa.remotestre.am"
REFERER = "https://remotestre.am/"
ORIGIN = "https://remotestre.am"


@register_source
class RemoteStream:
    id = "remotestream"
    name = "RemoteStream"
    rank = 180
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        if ctx.media_type == "movie":
            playlist = f"{BASE}/Movies/{ctx.tmdb_id}/{ctx.tmdb_id}.m3u8"
        else:
            playlist = f"{BASE}/Shows/{ctx.tmdb_id}/{ctx.season}/{ctx.episode}/{ctx.episode}.m3u8"

        # Validate that the playlist exists
        try:
            status = await fetcher.head(
                playlist,
                headers={"Referer": REFERER},
            )
            if status >= 400:
                return SourceResult()
        except Exception:
            return SourceResult()

        return SourceResult(streams=[
            Stream(
                stream_type="hls",
                playlist=playlist,
                headers={"Referer": REFERER, "Origin": ORIGIN},
            )
        ])
