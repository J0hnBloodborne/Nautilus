"""
EE3 (encrypted-endpoint) — scrapes rips.cc for direct MP4 streams.
Movies only. Returns file-based streams with optional VTT subs.
"""
from __future__ import annotations
import re
import json
from ..base import MediaContext, SourceResult, Stream, StreamFile, Caption
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://rips.cc"


@register_source
class EE3Source:
    id = "ee3"
    name = "EE3"
    rank = 80
    media_types = ["movie"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # Step 1: search for the movie
        search_url = f"{BASE}/api/search"
        try:
            results = await fetcher.get_json(
                search_url,
                params={"query": ctx.title},
            )
        except Exception:
            return SourceResult()

        if not results:
            return SourceResult()

        # Find matching result
        target = None
        for item in (results if isinstance(results, list) else results.get("results", [])):
            imdb = item.get("imdb_id", "")
            title = item.get("title", "")
            if (ctx.imdb_id and imdb == ctx.imdb_id) or title.lower().strip() == ctx.title.lower().strip():
                target = item
                break

        if not target:
            # Just use first result
            items = results if isinstance(results, list) else results.get("results", [])
            if items:
                target = items[0]

        if not target:
            return SourceResult()

        # Step 2: get stream details
        detail_id = target.get("id") or target.get("_id", "")
        if not detail_id:
            return SourceResult()

        try:
            details = await fetcher.get_json(f"{BASE}/api/movie/{detail_id}")
        except Exception:
            return SourceResult()

        msg = details.get("message", {}) if isinstance(details, dict) else {}
        stream_url = msg.get("url") or msg.get("stream_url", "")
        if not stream_url:
            return SourceResult()

        # Captions
        captions = []
        imdb_id = msg.get("imdbID") or ctx.imdb_id
        if msg.get("subs", "").lower() == "yes" and imdb_id:
            captions.append(Caption(
                url=f"{BASE}/subs/{imdb_id}.vtt",
                lang="en",
                format="vtt",
            ))

        return SourceResult(streams=[
            Stream(
                stream_type="file",
                qualities=[StreamFile(url=stream_url, quality="720")],
                captions=captions,
            )
        ])
