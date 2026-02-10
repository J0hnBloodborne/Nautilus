"""BombTheIrish — embed hub with base64-encoded URLs."""
from __future__ import annotations
import re, base64
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://bombthe.irish"


@register_source
class BombTheIrish:
    id = "bombtheirish"
    name = "BombTheIrish"
    rank = 40
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        if ctx.media_type == "movie":
            url = f"{BASE}/embed/movie/{ctx.tmdb_id}"
        else:
            url = f"{BASE}/embed/tv/{ctx.tmdb_id}/{ctx.season or 1}/{ctx.episode or 1}"

        html = await fetcher.get(url, headers={"Referer": BASE})

        # Parse dropdown menu links
        # Pattern: <a data-url="base64encoded_url" ... >embed_name</a>
        links = re.findall(r'data-url="([^"]+)"[^>]*>([^<]*)<', html)
        if not links:
            # Fallback: look for direct iframe
            iframes = re.findall(r'<iframe[^>]*src="([^"]+)"', html, re.IGNORECASE)
            links = [(url, "") for url in iframes]

        embeds = []
        for encoded_url, label in links:
            try:
                # Some URLs are base64 encoded
                if not encoded_url.startswith("http"):
                    decoded = base64.b64decode(encoded_url).decode("utf-8", errors="ignore")
                else:
                    decoded = encoded_url

                if not decoded.startswith("http"):
                    continue

                embed = _identify_embed(decoded)
                if embed:
                    embeds.append(embed)
            except Exception:
                continue

        if not embeds:
            raise Exception("BombTheIrish: no embeds found")

        return SourceResult(embeds=embeds)


def _identify_embed(url: str) -> EmbedRef | None:
    url_lower = url.lower()
    embed_map = {
        "mixdrop": "mixdrop", "voe": "voe", "dood": "dood", "d0o0d": "dood",
        "d000d": "dood", "streamtape": "streamtape", "filemoon": "filemoon",
        "streamwish": "streamwish", "upstream": "upstream",
        "mp4upload": "mp4upload", "ridoo": "ridoo", "filelions": "filelions",
        "streamvid": "streamvid", "turbovid": "turbovid",
        "closeload": "closeload", "vidsrc": "vidsrc",
    }
    for key, embed_id in embed_map.items():
        if key in url_lower:
            return EmbedRef(embed_id=embed_id, url=url)
    # Unknown embed — still return it with a generic ID
    return EmbedRef(embed_id="unknown", url=url)
