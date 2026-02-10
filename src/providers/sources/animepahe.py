"""
AnimePahe — anime source for high-quality anime episodes.
Uses consumet's AnimePahe provider for reliable streams.
"""
from __future__ import annotations
import json
from ..base import SourceResult, Stream, Caption, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

CONSUMET_APIS = [
    "https://api.consumet.org",
    "https://consumet-api.vercel.app",
]


@register_source
class AnimePahe:
    id = "animepahe"
    name = "AnimePahe"
    rank = 88
    media_types = ["tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        results = None
        api_base = None
        for api in CONSUMET_APIS:
            try:
                raw = await fetcher.get(
                    f"{api}/anime/animepahe/{ctx.title.replace(' ', '%20')}",
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
            raise ValueError("AnimePahe: anime not found")

        anime_id = results[0].get("id")
        if not anime_id:
            raise ValueError("AnimePahe: no anime ID")

        # Fetch info with episodes
        try:
            raw = await fetcher.get(
                f"{api_base}/anime/animepahe/info/{anime_id}",
                headers={"Accept": "application/json"},
            )
            info = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            raise ValueError(f"AnimePahe: info fetch failed: {e}")

        episodes = info.get("episodes", [])
        if not episodes:
            raise ValueError("AnimePahe: no episodes")

        ep_id = None
        for ep in episodes:
            if ep.get("number") == ctx.episode:
                ep_id = ep.get("id")
                break
        if not ep_id:
            raise ValueError(f"AnimePahe: ep {ctx.episode} not found")

        try:
            raw = await fetcher.get(
                f"{api_base}/anime/animepahe/watch/{ep_id}",
                headers={"Accept": "application/json"},
            )
            watch = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            raise ValueError(f"AnimePahe: stream failed: {e}")

        sources = watch.get("sources", [])
        if not sources:
            raise ValueError("AnimePahe: no sources")

        # Pick best quality
        best = sources[0]
        for s in sources:
            q = s.get("quality", "")
            if "1080" in q:
                best = s
                break
            elif "720" in q:
                best = s

        url = best.get("url", "")
        if not url:
            raise ValueError("AnimePahe: no URL")

        return SourceResult(streams=[
            Stream(stream_type="hls", playlist=url, captions=[])
        ])
