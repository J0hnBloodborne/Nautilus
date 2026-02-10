"""FlixHQ — search + AJAX source resolution → upcloud/vidcloud embeds. Disabled."""
from __future__ import annotations
import re
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://flixhq.to"


@register_source
class FlixHQ:
    id = "flixhq"
    name = "FlixHQ"
    rank = 61
    disabled = True
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # Search
        search_url = f"{BASE}/search/{ctx.title.replace(' ', '-')}"
        search_html = await fetcher.get(search_url)

        # Parse results: .film-detail .film-name a[href]
        results = re.findall(
            r'class="film-name"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*title="([^"]*)"',
            search_html,
        )

        # Find matching movie/show
        match_href = None
        for href, title in results:
            if ctx.title.lower() in title.lower():
                match_href = href
                break
        if not match_href and results:
            match_href = results[0][0]
        if not match_href:
            raise ValueError("FlixHQ: no results")

        # Extract ID from URL (last segment after -)
        item_id = match_href.rstrip("/").split("-")[-1]

        if ctx.media_type == "movie":
            # Get movie sources (AJAX)
            sources_html = await fetcher.get(
                f"{BASE}/ajax/episode/list/{item_id}",
            )
        else:
            # Get season list
            seasons_html = await fetcher.get(
                f"{BASE}/ajax/season/list/{item_id}",
            )
            # Find season ID
            season_ids = re.findall(
                r'data-id="(\d+)"[^>]*>\s*Season\s+(\d+)',
                seasons_html,
            )
            season_id = None
            for sid, snum in season_ids:
                if int(snum) == ctx.season:
                    season_id = sid
                    break
            if not season_id:
                raise ValueError("FlixHQ: season not found")

            # Get episodes
            eps_html = await fetcher.get(
                f"{BASE}/ajax/season/episodes/{season_id}",
            )
            ep_pattern = re.compile(
                rf'data-id="(\d+)"[^>]*title="[^"]*Eps\s+{ctx.episode}:',
            )
            ep_m = ep_pattern.search(eps_html)
            if not ep_m:
                raise ValueError("FlixHQ: episode not found")

            sources_html = await fetcher.get(
                f"{BASE}/ajax/episode/servers/{ep_m.group(1)}",
            )

        # Parse server links
        servers = re.findall(
            r'data-linkid="(\d+)"[^>]*title="([^"]*)"',
            sources_html,
        )
        if not servers:
            servers = re.findall(r'data-id="(\d+)"[^>]*title="([^"]*)"', sources_html)

        embeds = []
        upcloud_found = False
        for link_id, title in servers:
            # Get iframe URL
            try:
                details = await fetcher.get_json(f"{BASE}/ajax/sources/{link_id}")
                iframe_url = details.get("link", "")
                if not iframe_url:
                    continue

                from urllib.parse import urlparse
                host = urlparse(iframe_url).hostname or ""

                if "rabbitstream" in host:
                    if not upcloud_found:
                        embeds.append(EmbedRef(embed_id="upcloud", url=iframe_url))
                        upcloud_found = True
                    else:
                        embeds.append(EmbedRef(embed_id="vidcloud", url=iframe_url))
                elif "upstream" in host:
                    embeds.append(EmbedRef(embed_id="upstream", url=iframe_url))
                elif "mixdrop" in host:
                    embeds.append(EmbedRef(embed_id="mixdrop", url=iframe_url))
            except Exception:
                continue

        return SourceResult(embeds=embeds)
