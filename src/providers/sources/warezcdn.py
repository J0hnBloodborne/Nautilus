"""
WarezCDN source — IMDB-based, delegates to mixdrop + warezcdn embeds.
"""
from __future__ import annotations
import re, json
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

WAREZCDN_BASE = "https://embed.warezcdn.com"
WAREZCDN_API = "https://warezcdn.com/embed"


async def _get_external_player_url(fetcher: Fetcher, embed_id: str, embed_url: str) -> str:
    """Get real embed URL via warezcdn getPlay.php redirect."""
    from urllib.parse import urlencode
    params = {"id": embed_url, "sv": embed_id}
    real_url = await fetcher.get(
        f"{WAREZCDN_API}/getPlay.php",
        params=params,
        headers={"Referer": f"{WAREZCDN_API}/getEmbed.php?{urlencode(params)}"},
    )
    m = re.search(r'window\.location\.href="([^"]*)"', real_url)
    if not m:
        raise ValueError("WarezCDN: embed redirect not found")
    return m.group(1)


@register_source
class WarezCDN:
    id = "warezcdn"
    name = "WarezCDN"
    rank = 35
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        if not ctx.imdb_id:
            raise ValueError("WarezCDN requires IMDB ID")

        embeds = []

        if ctx.media_type == "movie":
            page = await fetcher.get(f"{WAREZCDN_BASE}/filme/{ctx.imdb_id}")

            for m in re.finditer(
                r'data-load-embed-host="([^"]+)"[^>]*data-load-embed="([^"]+)"', page
            ):
                host, embed_url = m.group(1), m.group(2)
                if host == "mixdrop":
                    try:
                        real_url = await _get_external_player_url(fetcher, "mixdrop", embed_url)
                        embeds.append(EmbedRef(embed_id="mixdrop", url=real_url))
                    except Exception:
                        pass
                elif host == "warezcdn":
                    embeds.append(EmbedRef(embed_id="warezcdnembedhls", url=embed_url))
                    embeds.append(EmbedRef(embed_id="warezcdnembedmp4", url=embed_url))
        else:
            url = f"{WAREZCDN_BASE}/serie/{ctx.imdb_id}/{ctx.season}/{ctx.episode}"
            page = await fetcher.get(url)

            ep_id_m = re.search(r"\$\('\[data-load-episode-content=\"(\d+)\"\]'\)", page)
            if not ep_id_m:
                raise ValueError("WarezCDN: episode ID not found")

            streams_data = await fetcher.post(
                f"{WAREZCDN_BASE}/serieAjax.php",
                data={"getAudios": ep_id_m.group(1)},
                headers={
                    "Origin": WAREZCDN_BASE,
                    "Referer": url,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            streams = json.loads(streams_data)
            lst = streams.get("list", {}).get("0", {})

            if lst.get("mixdropStatus") == "3":
                try:
                    real_url = await _get_external_player_url(fetcher, "mixdrop", lst["id"])
                    embeds.append(EmbedRef(embed_id="mixdrop", url=real_url))
                except Exception:
                    pass

            if lst.get("warezcdnStatus") == "3":
                embeds.append(EmbedRef(embed_id="warezcdnembedhls", url=lst["id"]))
                embeds.append(EmbedRef(embed_id="warezcdnembedmp4", url=lst["id"]))

        return SourceResult(embeds=embeds)
