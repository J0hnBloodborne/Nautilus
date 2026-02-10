"""
VidSrc — vidsrc.me embed with hash-based source resolution.
Disabled: uses vidsrcembed + streambucket.
"""
from __future__ import annotations
import re
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

VIDSRC_BASE = "https://vidsrc.me"
VIDSRC_RCP_BASE = "https://vidsrc.stream"


def _decode_src(encoded: str, seed: str) -> str:
    """XOR decode with seed string."""
    decoded = []
    seed_len = len(seed)
    for i in range(0, len(encoded), 2):
        byte = int(encoded[i:i + 2], 16)
        seed_char = ord(seed[(i // 2) % seed_len])
        decoded.append(chr(byte ^ seed_char))
    return "".join(decoded)


@register_source
class VidSrc:
    id = "vidsrc"
    name = "VidSrc"
    rank = 90
    disabled = True
    media_types = ["movie", "tv"]

    async def _get_embeds(self, starting_url: str, fetcher: Fetcher) -> list:
        html = await fetcher.get(VIDSRC_BASE + starting_url)
        # Find source hashes
        hashes = re.findall(r'class="server"[^>]*data-hash="([^"]+)"', html)
        embeds = []

        for h in hashes:
            try:
                rcp_html = await fetcher.get(
                    f"{VIDSRC_RCP_BASE}/rcp/{h}",
                    headers={"Referer": VIDSRC_BASE},
                )
                enc_m = re.search(r'id="hidden"[^>]*data-h="([^"]+)"', rcp_html)
                seed_m = re.search(r'<body[^>]*data-i="([^"]+)"', rcp_html)
                if not enc_m or not seed_m:
                    continue

                redirect_url = _decode_src(enc_m.group(1), seed_m.group(1))
                if redirect_url.startswith("//"):
                    redirect_url = f"https:{redirect_url}"

                final_url = await fetcher.get_final_url(redirect_url, headers={"Referer": VIDSRC_BASE})
                from urllib.parse import urlparse
                host = urlparse(final_url).hostname or ""

                if "vidsrc.stream" in host:
                    embeds.append(EmbedRef(embed_id="vidsrcembed", url=final_url))
                elif "streambucket.net" in host:
                    embeds.append(EmbedRef(embed_id="streambucket", url=final_url))
            except Exception:
                continue

        return embeds

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        if ctx.media_type == "movie":
            embeds = await self._get_embeds(f"/embed/{ctx.tmdb_id}", fetcher)
        else:
            # Find episode-specific iframe URL
            html = await fetcher.get(f"{VIDSRC_BASE}/embed/{ctx.tmdb_id}")
            ep_m = re.search(
                rf'class="ep"[^>]*data-s="{ctx.season}"[^>]*data-e="{ctx.episode}"[^>]*data-iframe="([^"]+)"',
                html,
            )
            if not ep_m:
                raise ValueError("VidSrc: episode not found")
            embeds = await self._get_embeds(ep_m.group(1), fetcher)

        return SourceResult(embeds=embeds)
