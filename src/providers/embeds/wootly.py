"""Wootly — cookie-based auth flow → /grabd → MP4 stream. IP_LOCKED."""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream, StreamFile
from ..fetcher import Fetcher
from ..runner import register_embed

WOOTLY_BASE = "https://www.wootly.ch"


@register_embed
class WootlyEmbed:
    id = "wootly"
    name = "Wootly"
    rank = 172

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        # Step 1: GET the initial page, capture wootsses cookie
        html1 = await fetcher.get(url)
        # Find iframe
        iframe_m = re.search(r'<iframe[^>]*src="([^"]+)"', html1, re.I)
        if not iframe_m:
            raise ValueError("Wootly: no iframe found")

        iframe_src = iframe_m.group(1)

        # Step 2: GET iframe, POST with qdf=1
        iframe_html = await fetcher.post(
            iframe_src,
            data={"qdf": "1"},
            headers={"Referer": iframe_src},
        )

        # Step 3: Extract tk and vd from inline script
        tk_m = re.search(r'tk=([^;\s]+)', iframe_html)
        vd_m = re.search(r'vd=([^,;\s]+)', iframe_html)
        if not tk_m or not vd_m:
            raise ValueError("Wootly: tk/vd not found")

        tk = tk_m.group(1).strip('"\'')
        vd = vd_m.group(1).strip('"\'')

        # Step 4: GET /grabd with tk and vd
        stream_url = await fetcher.get(
            f"{WOOTLY_BASE}/grabd",
            params={"t": tk, "id": vd},
        )

        stream_url = stream_url.strip().strip('"')
        if not stream_url or not stream_url.startswith("http"):
            raise ValueError("Wootly: invalid stream URL")

        return EmbedResult(streams=[
            Stream(stream_type="file",
                   qualities=[StreamFile(url=stream_url, quality="unknown")])
        ])
