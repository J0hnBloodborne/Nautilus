"""WHVX — API-based source with Nova/Astra/Orion embeds."""
from __future__ import annotations
import re, json, urllib.parse
from ..base import SourceResult, EmbedRef, MediaContext, EmbedResult, Stream, StreamFile, Caption
from ..fetcher import Fetcher
from ..runner import register_source, register_embed

WHVX_API = "https://api.whvx.net"
ORIGIN = "https://www.vidbinge.com"
WHVX_HEADERS = {"Origin": ORIGIN, "Referer": f"{ORIGIN}/"}


@register_source
class WHVX:
    id = "whvx"
    name = "WHVX"
    rank = 300
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # Get available providers  
        try:
            status_raw = await fetcher.get(f"{WHVX_API}/status", headers=WHVX_HEADERS)
            status = json.loads(status_raw) if isinstance(status_raw, str) else status_raw
        except Exception:
            status = {}

        providers = status.get("providers", ["nova", "astra", "orion"])
        if isinstance(providers, dict):
            providers = list(providers.keys())

        # Build media query for embeds
        media_query = {
            "title": ctx.title,
            "tmdbId": str(ctx.tmdb_id),
            "type": ctx.media_type,
            "releaseYear": ctx.year,
        }
        if ctx.media_type == "tv":
            media_query["season"] = str(ctx.season or 1)
            media_query["episode"] = str(ctx.episode or 1)

        query_string = urllib.parse.quote(json.dumps(media_query))
        embeds = []
        for provider in providers:
            if provider in ("nova", "astra", "orion"):
                embed_url = f"whvx://{provider}?query={query_string}"
                embeds.append(EmbedRef(embed_id=f"whvx-{provider}", url=embed_url))

        if not embeds:
            raise Exception("WHVX: no providers available")

        return SourceResult(embeds=embeds)


class _WHVXEmbed:
    """Base for Nova/Astra/Orion — all call the same WHVX API pattern."""

    provider_name: str = ""

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        # Extract query from our custom URL
        query_str = url.split("query=", 1)[-1] if "query=" in url else ""
        query_str = urllib.parse.unquote(query_str)
        try:
            query = json.loads(query_str)
        except Exception:
            raise Exception(f"WHVX-{self.provider_name}: invalid query")

        # Call WHVX search API
        search_url = f"{WHVX_API}/search"
        params = {"query": query_str, "provider": self.provider_name}

        try:
            result_raw = await fetcher.get(search_url, params=params, headers=WHVX_HEADERS)
            result = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
        except Exception as e:
            raise Exception(f"WHVX-{self.provider_name}: search failed: {e}")

        if not result or result.get("url") is None:
            raise Exception(f"WHVX-{self.provider_name}: no results")

        stream_url = result.get("url", "")
        stream_type = result.get("type", "hls")
        captions = []
        for sub in result.get("captions", []):
            captions.append(Caption(
                url=sub.get("url", ""),
                lang=sub.get("language", "en"),
                format=sub.get("type", "vtt")
            ))

        if stream_type == "file":
            qualities = []
            if isinstance(stream_url, dict):
                for q, u in stream_url.items():
                    qualities.append(StreamFile(url=u, quality=q))
            else:
                qualities.append(StreamFile(url=stream_url, quality="unknown"))
            return EmbedResult(streams=[
                Stream(stream_type="file", qualities=qualities, captions=captions,
                       headers=WHVX_HEADERS)
            ])
        else:
            return EmbedResult(streams=[
                Stream(stream_type="hls", playlist=stream_url, captions=captions,
                       headers=WHVX_HEADERS)
            ])


@register_embed
class NovaEmbed(_WHVXEmbed):
    id = "whvx-nova"
    name = "Nova"
    rank = 720
    provider_name = "nova"


@register_embed
class AstraEmbed(_WHVXEmbed):
    id = "whvx-astra"
    name = "Astra"
    rank = 710
    provider_name = "astra"


@register_embed
class OrionEmbed(_WHVXEmbed):
    id = "whvx-orion"
    name = "Orion"
    rank = 700
    provider_name = "orion"
