"""Nites — search + delegates to bFlix embed."""
from __future__ import annotations
import re
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://w1.nites.is"


@register_source
class Nites:
    id = "nites"
    name = "Nites"
    rank = 45
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # Search via wp-admin AJAX
        search_html = await fetcher.post(
            f"{BASE}/wp-admin/admin-ajax.php",
            data={
                "action": "ajax_pagination",
                "query_vars": "mixed",
                "search": ctx.title,
            },
        )
        if isinstance(search_html, dict):
            search_html = str(search_html)

        # Parse results: <a class="lnk-blk" href="...">
        results = re.findall(
            r'class="entry-title"[^>]*>([^<]+)</.*?class="year"[^>]*>(\d{4})</.*?class="lnk-blk"\s+href="([^"]+)"',
            search_html, re.DOTALL
        )
        if not results:
            # Simpler fallback
            results = re.findall(r'href="(https?://[^"]*nites[^"]*(?:movie|series)[^"]+)"', search_html)
            if not results:
                raise Exception("Nites: no results")
            watch_url = results[0] if isinstance(results[0], str) else results[0][0]
        else:
            # Find match
            watch_url = None
            for title, year, url in results:
                if ctx.title.lower() in title.lower() and (not ctx.year or str(ctx.year) == year):
                    watch_url = url
                    break
            if not watch_url:
                watch_url = results[0][2]

        # For TV: convert /series/slug/ → /episode/slug-SxE/
        if ctx.media_type == "tv" and "/series/" in watch_url:
            slug = re.search(r'/series/([^/]+)', watch_url)
            if slug:
                watch_url = watch_url.replace(
                    f"/series/{slug.group(1)}",
                    f"/episode/{slug.group(1)}-{ctx.season or 1}x{ctx.episode or 1}"
                )

        # Get watch page
        page = await fetcher.get(watch_url)

        # Find bflix iframe — look for iframe in video options
        iframe_m = re.search(r'data-lazy-src="([^"]+)"', page)
        if not iframe_m:
            iframe_m = re.search(r'<iframe[^>]*src="([^"]+)"', page, re.IGNORECASE)
        if not iframe_m:
            raise Exception("Nites: no embed found")

        embed_url = iframe_m.group(1)
        if not embed_url.startswith("http"):
            embed_url = f"https:{embed_url}"

        # Get the actual iframe src from the embed page
        embed_page = await fetcher.get(embed_url)
        inner_iframe = re.search(r'<iframe[^>]*src="([^"]+)"', embed_page, re.IGNORECASE)
        if inner_iframe:
            final_url = inner_iframe.group(1)
            if not final_url.startswith("http"):
                final_url = f"https:{final_url}"
        else:
            final_url = embed_url

        # Identify embed type
        embeds = []
        url_lower = final_url.lower()
        if "bflix" in url_lower:
            embeds.append(EmbedRef(embed_id="bflix", url=final_url))
        elif "filemoon" in url_lower:
            embeds.append(EmbedRef(embed_id="filemoon", url=final_url))
        elif "streamwish" in url_lower:
            embeds.append(EmbedRef(embed_id="streamwish", url=final_url))
        else:
            embeds.append(EmbedRef(embed_id="bflix", url=final_url))

        if not embeds:
            raise Exception("Nites: no embed identified")

        return SourceResult(embeds=embeds)
