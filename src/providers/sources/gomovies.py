"""GoMovies — search + server resolution → multiple embeds. Disabled."""
from __future__ import annotations
import re
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://gomovies.sx"


@register_source
class GoMovies:
    id = "gomovies"
    name = "GoMovies"
    rank = 60
    disabled = True
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        search_html = await fetcher.get(
            f"{BASE}/search/{ctx.title.replace(' ', '-')}",
        )

        results = re.findall(
            r'class="film-name"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*title="([^"]*)"',
            search_html,
        )

        match_href = None
        for href, title in results:
            if ctx.title.lower() in title.lower():
                match_href = href
                break
        if not match_href and results:
            match_href = results[0][0]
        if not match_href:
            raise ValueError("GoMovies: no results")

        item_id = match_href.rstrip("/").split("-")[-1]

        if ctx.media_type == "movie":
            sources_html = await fetcher.get(f"{BASE}/ajax/episode/list/{item_id}")
        else:
            # Season list
            seasons_html = await fetcher.get(f"{BASE}/ajax/season/list/{item_id}")
            season_ids = re.findall(r'data-id="(\d+)"[^>]*>\s*Season\s+(\d+)', seasons_html)
            season_id = None
            for sid, snum in season_ids:
                if int(snum) == ctx.season:
                    season_id = sid
                    break
            if not season_id:
                raise ValueError("GoMovies: season not found")

            eps_html = await fetcher.get(f"{BASE}/ajax/season/episodes/{season_id}")
            ep_m = re.search(rf'data-id="(\d+)"[^>]*title="[^"]*Eps\s+{ctx.episode}:', eps_html)
            if not ep_m:
                raise ValueError("GoMovies: episode not found")

            sources_html = await fetcher.get(f"{BASE}/ajax/episode/servers/{ep_m.group(1)}")

        servers = re.findall(r'data-linkid="(\d+)"[^>]*title="([^"]*)"', sources_html)
        if not servers:
            servers = re.findall(r'data-id="(\d+)"[^>]*title="([^"]*)"', sources_html)

        embeds = []
        upcloud_found = False

        HOST_MAP = {
            "rabbitstream": ("upcloud", "vidcloud"),
            "upstream": ("upstream",),
            "mixdrop": ("mixdrop",),
            "voe": ("voe",),
            "dood": ("dood",),
        }

        for link_id, title in servers:
            try:
                details = await fetcher.get_json(f"{BASE}/ajax/sources/{link_id}")
                iframe_url = details.get("link", "")
                if not iframe_url:
                    continue

                from urllib.parse import urlparse
                host = urlparse(iframe_url).hostname or ""

                for key, ids in HOST_MAP.items():
                    if key in host:
                        if key == "rabbitstream":
                            if not upcloud_found:
                                embeds.append(EmbedRef(embed_id="upcloud", url=iframe_url))
                                upcloud_found = True
                            else:
                                embeds.append(EmbedRef(embed_id="vidcloud", url=iframe_url))
                        else:
                            embeds.append(EmbedRef(embed_id=ids[0], url=iframe_url))
                        break
            except Exception:
                continue

        return SourceResult(embeds=embeds)
