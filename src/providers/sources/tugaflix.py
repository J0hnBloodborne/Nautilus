"""Tugaflix — Portuguese streaming, delegates to streamtape/dood."""
from __future__ import annotations
import re
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://tugaflix.best"


@register_source
class Tugaflix:
    id = "tugaflix"
    name = "Tugaflix"
    rank = 73
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # Search
        search_path = "/filmes/" if ctx.media_type == "movie" else "/series/"
        search_html = await fetcher.get(BASE + search_path, params={"s": ctx.title})

        # Parse results: poster links with titles
        results = re.findall(
            r'<a[^>]*href="([^"]+)"[^>]*title="([^"]*?)(?:\s*\((\d{4})\))?"',
            search_html,
        )
        watch_url = None
        for url, title, year in results:
            if ctx.title.lower() in title.lower():
                if not ctx.year or (year and str(ctx.year) == year):
                    watch_url = url
                    break
        if not watch_url and results:
            watch_url = results[0][0]
        if not watch_url:
            raise ValueError("Tugaflix: no results")

        embeds = []

        if ctx.media_type == "movie":
            # POST with play=
            video_page = await fetcher.post(watch_url, data={"play": ""})

            for m in re.finditer(r'class="play[^"]*"[^>]*>\s*<a[^>]*href="([^"]+)"', video_page):
                embed_url = m.group(1)
                if not embed_url.startswith("https://"):
                    embed_url = f"https://{embed_url}"
                try:
                    redir = await fetcher.get(embed_url)
                    dl_m = re.search(r'href="([^"]+)"[^>]*>.*?Download\s+Filme', redir, re.I | re.DOTALL)
                    if dl_m:
                        final = dl_m.group(1)
                        if "streamtape" in final:
                            embeds.append(EmbedRef(embed_id="streamtape", url=final))
                        elif "dood" in final:
                            embeds.append(EmbedRef(embed_id="dood", url=final))
                except Exception:
                    continue
        else:
            # TV: POST with SxxEyy key
            s = str(ctx.season).zfill(2)
            e = str(ctx.episode).zfill(2)
            video_page = await fetcher.post(watch_url, data={f"S{s}E{e}": ""})

            iframe_m = re.search(r'<iframe[^>]*name="player"[^>]*src="([^"]+)"', video_page, re.I)
            if iframe_m:
                iframe_url = iframe_m.group(1)
                if not iframe_url.startswith("https:"):
                    iframe_url = f"https:{iframe_url}"
                player_page = await fetcher.post(iframe_url, data={"submit": ""})
                dl_m = re.search(r'href="([^"]+)"[^>]*>.*?Download\s+Episodio', player_page, re.I | re.DOTALL)
                if dl_m:
                    final = dl_m.group(1)
                    if "streamtape" in final:
                        embeds.append(EmbedRef(embed_id="streamtape", url=final))
                    elif "dood" in final:
                        embeds.append(EmbedRef(embed_id="dood", url=final))

        return SourceResult(embeds=embeds)
