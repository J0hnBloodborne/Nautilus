"""
Anitaku (GoGoAnime) — anime source using consumet API.
Provides HLS streams for anime episodes.
"""
from __future__ import annotations
import json, re
from ..base import SourceResult, Stream, EmbedRef, Caption, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

# Public consumet API instances
CONSUMET_APIS = [
    "https://api.consumet.org",
    "https://consumet-api.vercel.app",
]


@register_source
class Anitaku:
    id = "anitaku"
    name = "Anitaku"
    rank = 85
    media_types = ["tv"]  # Anime is TV-like (episodes)

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # Search for the anime by title
        results = None
        api_base = None
        for api in CONSUMET_APIS:
            try:
                raw = await fetcher.get(
                    f"{api}/anime/gogoanime/{ctx.title.replace(' ', '%20')}",
                    headers={"Accept": "application/json"},
                )
                data = json.loads(raw) if isinstance(raw, str) else raw
                if data and data.get("results"):
                    results = data["results"]
                    api_base = api
                    break
            except Exception:
                continue

        if not results or not api_base:
            raise ValueError("Anitaku: anime not found")

        # Pick best match
        anime_id = results[0].get("id")
        if not anime_id:
            raise ValueError("Anitaku: no anime ID")

        # Fetch episode list
        try:
            raw = await fetcher.get(
                f"{api_base}/anime/gogoanime/info/{anime_id}",
                headers={"Accept": "application/json"},
            )
            info = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            raise ValueError(f"Anitaku: info fetch failed: {e}")

        episodes = info.get("episodes", [])
        if not episodes:
            raise ValueError("Anitaku: no episodes found")

        # Find matching episode
        ep_id = None
        for ep in episodes:
            if ep.get("number") == ctx.episode:
                ep_id = ep.get("id")
                break

        if not ep_id:
            raise ValueError(f"Anitaku: episode {ctx.episode} not found")

        # Get stream sources
        try:
            raw = await fetcher.get(
                f"{api_base}/anime/gogoanime/watch/{ep_id}",
                headers={"Accept": "application/json"},
            )
            watch = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            raise ValueError(f"Anitaku: stream fetch failed: {e}")

        sources = watch.get("sources", [])
        if not sources:
            raise ValueError("Anitaku: no sources in response")

        # Pick best quality source
        best = None
        for s in sources:
            quality = s.get("quality", "default")
            if "1080" in quality:
                best = s
                break
            elif "720" in quality and not best:
                best = s
            elif "default" in quality and not best:
                best = s
        if not best:
            best = sources[0]

        url = best.get("url", "")
        if not url:
            raise ValueError("Anitaku: no stream URL")

        return SourceResult(streams=[
            Stream(stream_type="hls", playlist=url, captions=[])
        ])
