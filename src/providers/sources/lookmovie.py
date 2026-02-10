"""LookMovie — API-based search → HLS streams with quality options. Disabled."""
from __future__ import annotations
import re
from ..base import SourceResult, MediaContext, Stream, Caption
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://lmscript.xyz"

LANG_MAP = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "russian": "ru", "japanese": "ja",
    "korean": "ko", "chinese": "zh",
}


@register_source
class LookMovie:
    id = "lookmovie"
    name = "LookMovie"
    rank = 50
    disabled = True
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        media_type = "movies" if ctx.media_type == "movie" else "shows"

        # Search
        search_res = await fetcher.get_json(
            f"{BASE}/v1/{media_type}/search",
            params={"filters[title]": ctx.title},
        )

        items = search_res.get("result", search_res) if isinstance(search_res, dict) else search_res
        if isinstance(items, dict):
            items = items.get("items", [])
        if not items:
            raise ValueError("LookMovie: no results")

        # Find best match
        match = None
        for item in (items if isinstance(items, list) else []):
            title = item.get("title", "")
            year = item.get("year")
            if ctx.title.lower() in title.lower():
                if not ctx.year or year == ctx.year:
                    match = item
                    break
        if not match:
            match = items[0] if isinstance(items, list) and items else None
        if not match:
            raise ValueError("LookMovie: no match")

        slug = match.get("slug", "")

        # Get streams
        if ctx.media_type == "movie":
            streams_res = await fetcher.get_json(
                f"{BASE}/v1/movies/view",
                params={"expand": "streams,subtitles", "filters[slug]": slug},
            )
        else:
            streams_res = await fetcher.get_json(
                f"{BASE}/v1/shows/view",
                params={
                    "expand": "streams,subtitles,seasons",
                    "filters[slug]": slug,
                },
            )

        result_data = streams_res.get("result", streams_res) if isinstance(streams_res, dict) else {}

        # Extract best HLS stream
        streams_list = result_data.get("streams", {})
        playlist = None
        if isinstance(streams_list, dict):
            # Try highest quality first
            for q in ["1080p", "1080", "720p", "720", "480p", "480", "auto"]:
                if q in streams_list:
                    playlist = streams_list[q]
                    break
            if not playlist:
                # Take first available
                for v in streams_list.values():
                    if isinstance(v, str) and v:
                        playlist = v
                        break
        elif isinstance(streams_list, str):
            playlist = streams_list

        if not playlist:
            raise ValueError("LookMovie: no stream found")

        # Subtitles
        captions = []
        subs = result_data.get("subtitles", [])
        if isinstance(subs, list):
            for sub in subs:
                lang = sub.get("language", sub.get("lang", ""))
                url = sub.get("file", sub.get("url", ""))
                if url:
                    lang_code = LANG_MAP.get(lang.lower(), lang[:2] if lang else "en")
                    fmt = "vtt" if url.endswith(".vtt") else "srt"
                    captions.append(Caption(url=url, lang=lang_code, format=fmt))

        return SourceResult(streams=[
            Stream(stream_type="hls", playlist=playlist, captions=captions)
        ])
