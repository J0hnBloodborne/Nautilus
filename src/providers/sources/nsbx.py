"""NSBX — API-based source, delegates to Delta embed."""
from __future__ import annotations
import json, urllib.parse
from ..base import (SourceResult, EmbedRef, MediaContext,
                    EmbedResult, Stream, StreamFile, Caption)
from ..fetcher import Fetcher
from ..runner import register_source, register_embed

NSBX_API = "https://nsbx.ru"


@register_source
class NSBX:
    id = "nsbx"
    name = "NSBX"
    rank = 130
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        query = {
            "title": ctx.title,
            "releaseYear": ctx.year,
            "tmdbId": str(ctx.tmdb_id),
            "imdbId": ctx.imdb_id or "",
            "type": ctx.media_type,
            "season": str(ctx.season or ""),
            "episode": str(ctx.episode or ""),
        }

        search_url = f"{NSBX_API}/api/search?query={urllib.parse.quote(json.dumps(query))}"
        raw = await fetcher.get(search_url)
        try:
            result = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            raise Exception("NSBX: search parse failed")

        embed_list = result.get("embeds", [])
        if not embed_list:
            raise Exception("NSBX: no embeds returned")

        embeds = []
        for embed in embed_list:
            embed_id = embed.get("embedId", "delta")
            resource_id = embed.get("resourceId", "")
            url = f"nsbx://{embed_id}?resourceId={urllib.parse.quote(resource_id)}"
            embeds.append(EmbedRef(embed_id="nsbx-delta", url=url))

        return SourceResult(embeds=embeds)


@register_embed
class DeltaEmbed:
    id = "nsbx-delta"
    name = "Delta"
    rank = 200

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        # Extract resourceId from our custom URL
        resource_id = ""
        if "resourceId=" in url:
            resource_id = urllib.parse.unquote(url.split("resourceId=", 1)[1])

        # Also extract embedId
        embed_id = "delta"
        if "nsbx://" in url:
            embed_id = url.split("nsbx://")[1].split("?")[0]

        api_url = f"{NSBX_API}/api/source/{embed_id}/?resourceId={urllib.parse.quote(resource_id)}"
        raw = await fetcher.get(api_url)
        try:
            result = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            raise Exception("Delta: API failed")

        streams = []
        for s in result.get("stream", []):
            stream_type = s.get("type", "hls")
            if stream_type == "hls":
                captions = []
                for c in s.get("captions", []):
                    captions.append(Caption(
                        url=c.get("url", ""),
                        lang=c.get("language", "en"),
                        format=c.get("type", "vtt")
                    ))
                streams.append(Stream(
                    stream_type="hls",
                    playlist=s.get("playlist", ""),
                    captions=captions,
                ))
            elif stream_type == "file":
                qualities_data = s.get("qualities", {})
                qualities = []
                for q, info in qualities_data.items():
                    q_url = info.get("url", "") if isinstance(info, dict) else str(info)
                    qualities.append(StreamFile(url=q_url, quality=q))
                captions = []
                for c in s.get("captions", []):
                    captions.append(Caption(
                        url=c.get("url", ""),
                        lang=c.get("language", "en"),
                        format=c.get("type", "vtt")
                    ))
                streams.append(Stream(
                    stream_type="file", qualities=qualities, captions=captions
                ))

        if not streams:
            raise Exception("Delta: no streams")

        return EmbedResult(streams=streams)
