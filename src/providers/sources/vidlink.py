"""VidLink — reliable HLS source via vidlink.pro API."""
from __future__ import annotations
import json, re
from ..base import SourceResult, Stream, Caption, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://vidlink.pro"


@register_source
class VidLink:
    id = "vidlink"
    name = "VidLink"
    rank = 350          # High rank — very reliable
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        if ctx.media_type == "movie":
            url = f"{BASE}/api/movie/{ctx.tmdb_id}"
        else:
            url = f"{BASE}/api/tv/{ctx.tmdb_id}/{ctx.season}/{ctx.episode}"

        headers = {
            "Referer": f"{BASE}/",
            "Origin": BASE,
        }

        raw = await fetcher.get(url, headers=headers)
        data = json.loads(raw) if isinstance(raw, str) else raw

        if not data:
            raise ValueError("VidLink: empty response")

        # VidLink returns a source object with stream URL
        source_data = data.get("source") or data
        stream_url = None
        captions = []

        # Try direct HLS URL
        if isinstance(source_data, dict):
            stream_url = source_data.get("url") or source_data.get("file") or source_data.get("source")
        elif isinstance(source_data, str):
            stream_url = source_data

        # Also check top-level
        if not stream_url:
            stream_url = data.get("url") or data.get("file") or data.get("stream")

        # Try sources array
        if not stream_url:
            sources = data.get("sources") or []
            if isinstance(sources, list) and sources:
                for s in sources:
                    if isinstance(s, dict) and s.get("file"):
                        stream_url = s["file"]
                        break
                    elif isinstance(s, str):
                        stream_url = s
                        break

        if not stream_url:
            raise ValueError("VidLink: no stream URL found")

        # Subtitles
        subs = data.get("subtitles") or data.get("tracks") or data.get("captions") or []
        for sub in subs:
            if isinstance(sub, dict):
                sub_url = sub.get("file") or sub.get("url") or sub.get("src") or ""
                label = sub.get("label") or sub.get("language") or sub.get("lang") or ""
                lang = sub.get("lang") or sub.get("srclang") or label[:2].lower() if label else "en"
                if sub_url and sub.get("kind", "captions") in ("captions", "subtitles", ""):
                    fmt = "vtt" if ".vtt" in sub_url else "srt"
                    captions.append(Caption(url=sub_url, lang=lang, format=fmt))

        return SourceResult(streams=[
            Stream(stream_type="hls", playlist=stream_url, captions=captions, headers=headers)
        ])
