"""
VidSrc embed — base64-obfuscated HLS URL extraction.
"""
from __future__ import annotations
import re, base64
from ..base import EmbedResult, Stream
from ..fetcher import Fetcher
from ..runner import register_embed

HLS_RE = re.compile(r'file:"([^"]+)"')
SET_PASS_RE = re.compile(r'var pass_path = "([^"]*set_pass\.php[^"]*)";')
RCP_BASE = "https://vidsrc.stream"


def _format_hls_b64(data: str) -> str:
    """Remove obfuscation markers and decode."""
    cleaned = re.sub(r'/@#@/[^=/]+=', '', data)
    # Recurse if more markers remain
    if re.search(r'/@#@/[^=/]+=', cleaned):
        return _format_hls_b64(cleaned)
    return cleaned


@register_embed
class VidSrcEmbed:
    id = "vidsrcembed"
    name = "VidSrc"
    rank = 197

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url, headers={"Referer": url})

        hls_match = HLS_RE.search(html)
        if not hls_match:
            raise ValueError("VidSrc: HLS URL not found")

        raw = hls_match.group(1)[2:]  # Skip first 2 chars
        cleaned = _format_hls_b64(raw)
        final_url = base64.b64decode(cleaned).decode("utf-8")

        if ".m3u8" not in final_url:
            raise ValueError("VidSrc: decoded URL is not HLS")

        # Try to hit set_pass endpoint (optional, doesn't affect playback)
        sp_match = SET_PASS_RE.search(html)
        if sp_match:
            sp_link = sp_match.group(1)
            if sp_link.startswith("//"):
                sp_link = f"https:{sp_link}"
            try:
                await fetcher.get(sp_link, headers={"Referer": url})
            except Exception:
                pass

        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=final_url,
                   headers={"Referer": RCP_BASE, "Origin": RCP_BASE})
        ])
