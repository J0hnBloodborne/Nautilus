"""
ZoeChip — search + AJAX-based season/episode/source resolution.
Disabled. Delegates to upcloud/vidcloud/upstream/mixdrop.
"""
from __future__ import annotations
import re
from urllib.parse import urlparse
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://zoechip.cc"


@register_source
class ZoeChip:
    id = "zoechip"
    name = "ZoeChip"
    rank = 62
    disabled = True
    media_types = ["movie", "tv"]

    async def _search(self, ctx: MediaContext, fetcher: Fetcher) -> str:
        """Search and return item ID."""
        slug = ctx.title.lower().replace(" ", "-")
        html = await fetcher.get(f"{BASE}/search/{slug}")

        results = []
        for m in re.finditer(
            r'class="film-name"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*title="([^"]*)"',
            html,
        ):
            href, title = m.group(1), m.group(2)
            item_id = href.rstrip("/").split("-")[-1]
            # Try to extract year
            year_m = re.search(r'class="fdi-item"[^>]*>(\d{4})<', html[m.end():m.end() + 500])
            year = int(year_m.group(1)) if year_m else 0
            results.append({"title": title, "href": href, "id": item_id, "year": year})

        for r in results:
            if ctx.title.lower() in r["title"].lower():
                if not ctx.year or r["year"] == ctx.year or r["year"] == 0:
                    return r["id"]
        if results:
            return results[0]["id"]
        raise ValueError("ZoeChip: no results")

    async def _get_season_id(self, show_id: str, season: int, fetcher: Fetcher) -> str:
        html = await fetcher.get(f"{BASE}/ajax/season/list/{show_id}")
        for m in re.finditer(r'data-id="(\d+)"[^>]*>\s*Season\s+(\d+)', html):
            if int(m.group(2)) == season:
                return m.group(1)
        raise ValueError(f"ZoeChip: season {season} not found")

    async def _get_episode_id(self, season_id: str, episode: int, fetcher: Fetcher) -> str:
        html = await fetcher.get(f"{BASE}/ajax/season/episodes/{season_id}")
        for m in re.finditer(r'data-id="(\d+)"[^>]*title="[^"]*Eps\s+(\d+):', html):
            if int(m.group(2)) == episode:
                return m.group(1)
        raise ValueError(f"ZoeChip: episode {episode} not found")

    async def _get_sources(self, item_id: str, is_movie: bool, fetcher: Fetcher) -> list:
        endpoint = "list" if is_movie else "servers"
        attr = "data-linkid" if is_movie else "data-id"
        html = await fetcher.get(f"{BASE}/ajax/episode/{endpoint}/{item_id}")
        sources = []
        for m in re.finditer(rf'{attr}="(\d+)"[^>]*title="([^"]*)"', html):
            sources.append({"id": m.group(1), "title": m.group(2)})
        return sources

    async def _resolve_source(self, source_id: str, fetcher: Fetcher) -> str | None:
        try:
            details = await fetcher.get_json(f"{BASE}/ajax/sources/{source_id}")
            if details.get("type") != "iframe":
                return None
            return details.get("link")
        except Exception:
            return None

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        item_id = await self._search(ctx, fetcher)

        if ctx.media_type == "movie":
            sources = await self._get_sources(item_id, True, fetcher)
        else:
            season_id = await self._get_season_id(item_id, ctx.season, fetcher)
            episode_id = await self._get_episode_id(season_id, ctx.episode, fetcher)
            sources = await self._get_sources(episode_id, False, fetcher)

        embeds = []
        upcloud_found = False
        for source in sources:
            link = await self._resolve_source(source["id"], fetcher)
            if not link:
                continue
            host = urlparse(link).hostname or ""

            if "rabbitstream" in host:
                if not upcloud_found:
                    embeds.append(EmbedRef(embed_id="upcloud", url=link))
                    upcloud_found = True
                else:
                    embeds.append(EmbedRef(embed_id="vidcloud", url=link))
            elif "upstream" in host:
                embeds.append(EmbedRef(embed_id="upstream", url=link))
            elif "mixdrop" in host:
                embeds.append(EmbedRef(embed_id="mixdrop", url=link))

        return SourceResult(embeds=embeds)
