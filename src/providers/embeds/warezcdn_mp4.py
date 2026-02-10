"""WarezCDN MP4 — decrypts stream ID → cloud.mail.ru CDN check → MP4."""
from __future__ import annotations
from urllib.parse import urlencode
from ..base import EmbedResult, Stream, StreamFile
from ..fetcher import Fetcher
from ..runner import register_embed
from .warezcdn_common import get_decrypted_id

CDN_IDS = list(range(50, 65))
WORKER_PROXY = "https://workerproxy.warezcdn.workers.dev"


@register_embed
class WarezCDNMp4:
    id = "warezcdnembedmp4"
    name = "WarezCDN MP4"
    rank = 82

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        decrypted_id = await get_decrypted_id(url, fetcher)

        # Check CDN URLs for a working one
        stream_url = None
        for cdn_id in CDN_IDS:
            test_url = f"https://cloclo{cdn_id}.cloud.mail.ru/weblink/view/{decrypted_id}"
            try:
                status = await fetcher.head(test_url, headers={"Range": "bytes=0-1"})
                if status in (200, 206):
                    stream_url = test_url
                    break
            except Exception:
                continue

        if not stream_url:
            raise ValueError("WarezCDN MP4: no working CDN found")

        proxied = f"{WORKER_PROXY}/?{urlencode({'url': stream_url})}"

        return EmbedResult(streams=[
            Stream(stream_type="file",
                   qualities=[StreamFile(url=proxied, quality="unknown")])
        ])
